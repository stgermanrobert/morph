#!/usr/bin/env python3
"""
Morph — audio/video converter and downloader.
Engine: FFmpeg (conversion) · yt-dlp (YouTube and 1000+ sites).
Spotify: reads the link's public metadata (no account, no login, no API) and fetches each track from YouTube.

Instalar:  pip install -U PySide6 "yt-dlp[default]"
Ejecutar:  python morph.py     (o doble clic en morph.pyw para que no abra consola)
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

import app_runtime as RT  # noqa: I001  (first: puts the bundled FFmpeg and Deno on PATH)
from PySide6.QtCore import QObject, QProcess, QRunnable, QSettings, QSize, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut
import i18n
import locales
from i18n import tr
from ui_icons import icon
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

APP = "Morph"
__version__ = "1.0.0"
REPO_URL = "https://github.com/stgermanrobert/morph"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # oculta consolas en Windows
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

AUDIO_FORMATS = ["mp3", "m4a", "flac", "wav", "ogg", "opus"]
VIDEO_FORMATS = ["mp4", "mkv", "webm", "mov", "gif"]
QUALITIES = ["Maximum", "High", "Light"]
MEDIA_EXT = {
    "mp3", "m4a", "aac", "flac", "wav", "ogg", "opus", "wma", "aif", "aiff", "alac", "amr", "ac3",
    "mp4", "mkv", "webm", "mov", "avi", "wmv", "flv", "m4v", "mpg", "mpeg", "ts", "mts", "m2ts",
    "3gp", "gif", "vob", "ogv",
}

# ──────────────────────────────────────────────────────────────────────────────
#  FFmpeg engine (pure functions, no GUI)
# ──────────────────────────────────────────────────────────────────────────────
# (encoder args per quality, visible description per quality)
AUDIO_SPEC = {
    "mp3":  ([["-c:a", "libmp3lame", "-b:a", "320k"], ["-c:a", "libmp3lame", "-q:a", "2"],
              ["-c:a", "libmp3lame", "-b:a", "128k"]],
             ["320 kbps CBR", "VBR V2 (170–210 kbps)", "128 kbps CBR"]),
    "m4a":  ([["-c:a", "aac", "-b:a", "256k"], ["-c:a", "aac", "-b:a", "192k"], ["-c:a", "aac", "-b:a", "128k"]],
             ["AAC 256 kbps", "AAC 192 kbps", "AAC 128 kbps"]),
    "opus": ([["-c:a", "libopus", "-b:a", "192k"], ["-c:a", "libopus", "-b:a", "128k"],
              ["-c:a", "libopus", "-b:a", "96k"]],
             ["Opus 192 kbps", "Opus 128 kbps", "Opus 96 kbps"]),
    "ogg":  ([["-c:a", "libvorbis", "-q:a", "8"], ["-c:a", "libvorbis", "-q:a", "6"],
              ["-c:a", "libvorbis", "-q:a", "4"]],
             ["Vorbis q8", "Vorbis q6", "Vorbis q4"]),
    "flac": ([["-c:a", "flac", "-compression_level", "5"]] * 3, ["Lossless"] * 3),
    "wav":  ([["-c:a", "pcm_s24le"], ["-c:a", "pcm_s16le"], ["-c:a", "pcm_s16le"]],
             ["PCM 24-bit", "PCM 16-bit", "PCM 16-bit"]),
}
X264 = [("18", "fast"), ("21", "fast"), ("26", "veryfast")]
VP9 = [("30", "4"), ("34", "5"), ("40", "6")]
GIF = [(720, 15), (480, 12), (320, 10)]

COPY_OK = {  # codec combinations that can be remuxed without re-encoding (instant, lossless)
    "mp4":  ({"h264", "hevc", "av1"}, {"aac", "mp3", "ac3", "eac3", "alac", "opus"}),
    "mov":  ({"h264", "hevc", "prores"}, {"aac", "mp3", "alac", "pcm_s16le", "pcm_s24le"}),
    "webm": ({"vp8", "vp9", "av1"}, {"opus", "vorbis"}),
    "mkv":  ({"h264", "hevc", "vp8", "vp9", "av1", "mpeg4", "mpeg2video", "prores"},
             {"aac", "mp3", "ac3", "eac3", "dts", "flac", "opus", "vorbis", "alac", "truehd",
              "pcm_s16le", "pcm_s24le"}),
}


def describe(fmt: str, q: int) -> str:
    if fmt in AUDIO_SPEC:
        return tr(AUDIO_SPEC[fmt][1][q])
    if fmt == "gif":
        w, fps = GIF[q]
        return tr("{w}px · {fps} fps · optimized palette", w=w, fps=fps)
    if fmt == "webm":
        return tr("Remux when possible · otherwise VP9 CRF {crf} + Opus", crf=VP9[q][0])
    return tr("Remux when possible · otherwise H.264 CRF {crf} + AAC", crf=X264[q][0])


def probe(path: Path) -> dict:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,codec_name:stream_disposition=attached_pic",
         "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    data = json.loads(out.stdout or "{}")
    v, a = None, []
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic"):
            v = v or s.get("codec_name")
        elif s.get("codec_type") == "audio":
            a.append(s.get("codec_name"))
    try:
        dur = float(data.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        dur = 0.0
    return {"video": v, "audio": a, "duration": dur}


def can_copy(fmt: str, info: dict) -> bool:
    if fmt not in COPY_OK or not info["video"]:
        return False
    vids, auds = COPY_OK[fmt]
    return info["video"] in vids and all(c in auds for c in info["audio"])


def build_cmd(src: Path, dst: Path, fmt: str, q: int, info: dict, force_encode=False) -> tuple[list, bool]:
    """Devuelve (comando, es_remux)."""
    base = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            "-i", str(src), "-progress", "pipe:1", "-nostats"]
    if fmt in AUDIO_SPEC:
        if not info["audio"]:
            raise ValueError(tr("The file has no audio"))
        return base + ["-vn", "-map", "0:a:0", "-map_metadata", "0", *AUDIO_SPEC[fmt][0][q], str(dst)], False
    if not info["video"]:
        raise ValueError(tr("The file has no video"))
    if fmt == "gif":
        w, fps = GIF[q]
        vf = (f"fps={fps},scale='min({w},iw)':-2:flags=lanczos,split[a][b];"
              f"[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a")
        return base + ["-an", "-vf", vf, "-loop", "0", str(dst)], False
    maps = ["-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0"]
    faststart = ["-movflags", "+faststart"] if fmt in ("mp4", "mov") else []
    if not force_encode and can_copy(fmt, info):
        return base + maps + ["-c", "copy", *faststart, str(dst)], True
    if fmt == "webm":
        crf, cpu = VP9[q]
        enc = ["-c:v", "libvpx-vp9", "-crf", crf, "-b:v", "0", "-row-mt", "1", "-deadline", "good",
               "-cpu-used", cpu, "-c:a", "libopus", "-b:a", "128k"]
    else:
        crf, preset = X264[q]
        enc = ["-c:v", "libx264", "-crf", crf, "-preset", preset, "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k"]
    return base + maps + enc + faststart + [str(dst)], False


def unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    i = 1
    while (c := p.with_name(f"{p.stem} ({i}){p.suffix}")).exists():
        i += 1
    return c


def fmt_time(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


# ──────────────────────────────────────────────────────────────────────────────
#  Spotify without the API: public metadata (embed page / meta tags) → YouTube search
# ──────────────────────────────────────────────────────────────────────────────
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
SP_RE = re.compile(r"(?:open\.spotify\.com/(?:intl-[a-zA-Z-]+/)?(?:embed/)?|spotify:)"
                   r"(track|album|playlist)[/:]([A-Za-z0-9]{22})")
NOISE = ("live", "en vivo", "en directo", "cover", "remix", "karaoke", "instrumental", "sped up",
         "slowed", "8d", "nightcore", "reverb", "acoustic", "acústico", "lyrics video", "letra")


def is_spotify(url: str) -> bool:
    return any(h in url for h in ("open.spotify.com", "spotify.link", "spoti.fi")) or url.startswith("spotify:")


def http_get(url: str, timeout=20) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace"), r.geturl()


def _walk(o):
    stack = [o]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            yield x
            stack.extend(reversed(list(x.values())))
        elif isinstance(x, list):
            stack.extend(reversed(x))


def _json_blobs(html: str) -> list:
    out = []
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.S):
        body = m.group(1).strip()
        if not body or body[0] not in "{[":
            continue
        try:
            out.append(json.loads(body))
        except ValueError:
            pass
    return out


def _artists(d: dict) -> list[str]:
    a = d.get("artists")
    if isinstance(a, dict):
        a = a.get("items")
    if isinstance(a, list):
        names = []
        for x in a:
            if isinstance(x, dict):
                n = x.get("name") or (x.get("profile") or {}).get("name")
                if n:
                    names.append(n)
        if names:
            return names
    sub = d.get("subtitle") or d.get("artist")
    if isinstance(sub, str) and sub.strip():
        return [p.strip() for p in sub.replace(" ", " ").split(",") if p.strip()]
    return []


def _duration(d: dict) -> float:
    for k in ("duration", "duration_ms", "durationMs"):
        v = d.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return v / 1000
        if isinstance(v, dict) and isinstance(v.get("totalMilliseconds"), (int, float)):
            return v["totalMilliseconds"] / 1000
    return 0.0


def _cover(d: dict) -> str:
    best, best_w = "", -1
    for k in ("coverArt", "visualIdentity", "images", "image", "albumOfTrack", "album"):
        if k not in d:
            continue
        for x in _walk(d[k]):
            url = x.get("url")
            if isinstance(url, str) and url.startswith("http") and ("scdn" in url or "image" in url):
                w = x.get("width") or x.get("maxWidth") or 0
                if isinstance(w, (int, float)) and w > best_w:
                    best, best_w = url, w
    return best


def _track(d: dict, album="", cover="") -> dict:
    return {"uri": d.get("uri", ""), "title": (d.get("title") or d.get("name") or "").strip(), "artists": _artists(d),
            "duration": _duration(d), "album": album, "cover": _cover(d) or cover}


def spotify_tracks(url: str) -> tuple[str, list[dict]]:
    """Returns (collection name, [tracks]) using only Spotify's public pages."""
    if "spotify.link" in url or "spoti.fi" in url:   # short links from the app
        _, url = http_get(url)
    m = SP_RE.search(url)
    if not m:
        raise RuntimeError(tr("Unrecognized Spotify link (track, album or playlist)"))
    kind, sid = m.groups()
    uri = f"spotify:{kind}:{sid}"
    tracks, name = [], ""
    try:
        html, _ = http_get(f"https://open.spotify.com/embed/{kind}/{sid}")
        dicts = [d for blob in _json_blobs(html) for d in _walk(blob)]
        entity = next((d for d in dicts if d.get("uri") == uri and (d.get("name") or d.get("title"))), None)
        if entity is None:
            entity = next((d for d in dicts if isinstance(d.get("trackList"), list)), None)
        if entity:
            name = (entity.get("name") or entity.get("title") or "").strip()
            if kind == "track":
                tracks = [_track(entity)]
            else:
                album = name if kind == "album" else ""
                cov = _cover(entity) if kind == "album" else ""
                items = entity.get("trackList")
                if not isinstance(items, list):
                    items = [d for d in _walk(entity) if str(d.get("uri", "")).startswith("spotify:track:")]
                seen = set()
                for it in items:
                    if isinstance(it, dict) and it.get("uri") not in seen and (it.get("title") or it.get("name")):
                        seen.add(it.get("uri"))
                        tracks.append(_track(it, album, cov))
                        if kind == "album":
                            tracks[-1]["num"] = len(tracks)
    except Exception:  # noqa: BLE001  → fall back to plan B
        tracks = []
    if not tracks and kind == "track":   # plan B: meta tags of the regular page
        html, _ = http_get(f"https://open.spotify.com/track/{sid}")

        def meta(prop):
            mm = re.search(rf'<meta[^>]+(?:property|name)="{re.escape(prop)}"[^>]+content="([^"]*)"', html)
            return __import__("html").unescape(mm.group(1)) if mm else ""
        title, desc = meta("og:title"), meta("og:description")
        parts = [p.strip() for p in desc.split("·")]
        dur = meta("music:duration")
        if title:
            tracks = [{"title": title, "artists": [parts[0]] if parts and parts[0] else [],
                       "duration": float(dur) if dur.isdigit() else 0.0,
                       "album": parts[1] if len(parts) > 2 else "", "cover": meta("og:image")}]
            name = title
    tracks = [t for t in tracks if t["title"]]
    if not tracks:
        raise RuntimeError(tr("Couldn't read Spotify's public page (private playlist?)"))
    return name, tracks


def pick_match(entries: list[dict], t: dict) -> dict | None:
    """Picks the closest YouTube result: duration, official channel (- Topic), no odd versions."""
    tl, best = t["title"].lower(), None
    artist = (t["artists"][0] if t["artists"] else "").lower()
    for e in entries:
        if not e or not e.get("id"):
            continue
        title = (e.get("title") or "").lower()
        ch = (e.get("channel") or e.get("uploader") or "").lower()
        d = e.get("duration") or 0
        score = abs(d - t["duration"]) if d and t["duration"] else 25
        if d and t["duration"] and abs(d - t["duration"]) > 20:
            score += 40
        score += sum(60 for w in NOISE if w in title and w not in tl)
        if ch.endswith(" - topic"):
            score -= 15
        if artist and artist in f"{title} {ch}":
            score -= 5
        if not any(w in title for w in re.findall(r"\w{3,}", tl)[:3]):
            score += 30
        if best is None or score < best[0]:
            best = (score, e)
    return best[1] if best else None


def enrich_cover(t: dict):
    """Playlist entries carry no cover art: fetch it from the track's own page."""
    if t.get("cover") or not str(t.get("uri", "")).startswith("spotify:track:"):
        return
    try:
        _, one = spotify_tracks(t["uri"])
        t["cover"] = one[0].get("cover", "")
        t["album"] = t.get("album") or one[0].get("album", "")
    except Exception:  # noqa: BLE001
        pass


def has_cover(path: Path) -> bool:
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v", "-show_entries",
                        "stream=codec_type", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, creationflags=NO_WINDOW)
    return "video" in r.stdout


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", s).strip(" .")[:150] or "audio"


def tag_audio(path: Path, t: dict, number: int | None = None):
    """Tags + Spotify cover art via FFmpeg (no re-encoding)."""
    cover = None
    if t.get("cover"):
        try:
            req = urllib.request.Request(t["cover"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = r.read()
            fd, cover = tempfile.mkstemp(suffix=".jpg")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
        except Exception:  # noqa: BLE001
            cover = None
    tmp = path.with_name(path.stem + ".tagging" + path.suffix)
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(path)]
    if cover:
        cmd += ["-i", cover, "-map", "0:a", "-map", "1:0", "-c", "copy", "-disposition:v:0", "attached_pic"]
        if path.suffix == ".mp3":
            cmd += ["-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)"]
    else:
        cmd += ["-map", "0:a", "-c", "copy"]
    cmd += ["-map_metadata", "-1", "-metadata", f"title={t['title']}",
            "-metadata", f"artist={', '.join(t['artists'])}"]
    if t.get("album"):
        cmd += ["-metadata", f"album={t['album']}"]
    if number:
        cmd += ["-metadata", f"track={number}"]
    if path.suffix == ".mp3":
        cmd += ["-id3v2_version", "3"]
    cmd.append(str(tmp))
    r = subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW)
    if cover:
        os.unlink(cover)
    if r.returncode == 0:
        os.replace(tmp, path)
    else:
        tmp.unlink(missing_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
#  Workers
# ──────────────────────────────────────────────────────────────────────────────
class Bus(QObject):
    progress = Signal(int, float, str)   # job_id, 0..1 (-1 = indeterminado), texto
    finished = Signal(int, bool, str, str)  # job_id, ok, texto, ruta_salida


class Cancel:
    def __init__(self):
        self.flag = threading.Event()
        self.procs: set[subprocess.Popen] = set()
        self.lock = threading.Lock()

    def add(self, p):
        with self.lock:
            self.procs.add(p)

    def remove(self, p):
        with self.lock:
            self.procs.discard(p)

    def fire(self):
        self.flag.set()
        with self.lock:
            for p in list(self.procs):
                try:
                    p.kill()
                except OSError:
                    pass


class ConvertTask(QRunnable):
    def __init__(self, jid, src: Path, fmt, q, out_dir: Path | None, bus: Bus, cancel: Cancel):
        super().__init__()
        self.jid, self.src, self.fmt, self.q, self.out_dir, self.bus, self.cancel = \
            jid, src, fmt, q, out_dir, bus, cancel

    def run(self):
        if self.cancel.flag.is_set():
            return self.bus.finished.emit(self.jid, False, tr("Canceled"), "")
        try:
            info = probe(self.src)
            folder = self.out_dir or self.src.parent
            dst = unique_path(folder / f"{self.src.stem}.{self.fmt}")
            ok, err, remux = self._run(info, dst, force=False)
            if not ok and remux and not self.cancel.flag.is_set():   # remux failed → re-encode
                dst.unlink(missing_ok=True)
                ok, err, _ = self._run(info, dst, force=True)
            if ok:
                note = tr("Done · lossless remux") if remux else tr("Done")
                self.bus.finished.emit(self.jid, True, note, str(dst))
            else:
                dst.unlink(missing_ok=True)
                msg = tr("Canceled") if self.cancel.flag.is_set() else (err or tr("FFmpeg error"))
                self.bus.finished.emit(self.jid, False, msg, "")
        except Exception as e:  # noqa: BLE001
            self.bus.finished.emit(self.jid, False, str(e), "")

    def _run(self, info, dst, force):
        cmd, remux = build_cmd(self.src, dst, self.fmt, self.q, info, force_encode=force)
        dur = info["duration"]
        self.bus.progress.emit(self.jid, 0.0 if dur else -1, tr("Remuxing…") if remux else tr("Converting…"))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        self.cancel.add(proc)
        err_lines: list[str] = []
        t = threading.Thread(target=lambda: err_lines.extend(proc.stderr), daemon=True)
        t.start()
        speed = ""
        for line in proc.stdout:
            k, _, v = line.strip().partition("=")
            if k == "speed":
                speed = v.strip()
            elif k == "out_time_us" and v.isdigit() and dur:
                frac = min(1.0, int(v) / 1e6 / dur)
                tail = f" · {speed}" if speed not in ("", "N/A", "0x") else ""
                self.bus.progress.emit(self.jid, frac, f"{frac * 100:.0f}%{tail}")
        proc.wait()
        t.join(timeout=2)
        self.cancel.remove(proc)
        err = next((l.strip() for l in reversed(err_lines) if l.strip()), "")
        return proc.returncode == 0, err[:160], remux


class DownloadTask(QRunnable):
    def __init__(self, jid, url, mode, playlist, out_dir: Path, bus: Bus, cancel: Cancel):
        super().__init__()
        self.jid, self.url, self.mode, self.playlist, self.out_dir, self.bus, self.cancel = \
            jid, url, mode, playlist, out_dir, bus, cancel
        self.last = ""

    def run(self):
        try:
            if is_spotify(self.url):
                return self._spotify()
            self._ytdlp()
        except Exception as e:  # noqa: BLE001
            msg = tr("Canceled") if self.cancel.flag.is_set() else str(e).replace("ERROR: ", "")[:200]
            self.bus.finished.emit(self.jid, False, msg, "")

    def _ytdlp(self):
        import yt_dlp
        from yt_dlp.utils import DownloadCancelled

        def hook(d):
            if self.cancel.flag.is_set():
                raise DownloadCancelled()
            title = (d.get("info_dict") or {}).get("title", "")
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes", 0)
                spd = d.get("speed")
                spd_t = f" · {spd / 1_048_576:.1f} MB/s" if spd else ""
                if total:
                    self.bus.progress.emit(self.jid, done / total, f"{done / total * 100:.0f}%{spd_t} · {title}")
                else:
                    self.bus.progress.emit(self.jid, -1, tr("Downloading…") + f"{spd_t} · {title}")
            elif d["status"] == "finished":
                self.bus.progress.emit(self.jid, -1, tr("Processing with FFmpeg…") + f" · {title}")

        def pp_hook(d):
            if d.get("status") == "finished":
                fp = (d.get("info_dict") or {}).get("filepath")
                if fp:
                    self.last = fp

        opts = {
            "outtmpl": str(self.out_dir / "%(title)s.%(ext)s"),
            "windowsfilenames": True,
            "noplaylist": not self.playlist,
            "progress_hooks": [hook],
            "postprocessor_hooks": [pp_hook],
            "quiet": True, "no_warnings": True, "noprogress": True,
            "ignoreerrors": "only_download" if self.playlist else False,
        }
        if FFMPEG:
            opts["ffmpeg_location"] = str(Path(FFMPEG).parent)
        if self.mode in ("mp3", "m4a"):
            pps = [{"key": "FFmpegExtractAudio", "preferredcodec": self.mode,
                    "preferredquality": "0" if self.mode == "mp3" else "256"},
                   {"key": "FFmpegMetadata"}]
            if self.mode == "mp3":  # embedded cover art (FFmpeg only, no extra dependencies)
                opts["writethumbnail"] = True
                pps.append({"key": "EmbedThumbnail"})
            opts.update(format="bestaudio/best", postprocessors=pps)
        else:
            opts.update(format="bv*[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b",
                        merge_output_format="mp4")
        with yt_dlp.YoutubeDL(opts) as ydl:
            code = ydl.download([self.url])
        if self.cancel.flag.is_set():
            return self.bus.finished.emit(self.jid, False, tr("Canceled"), "")
        out = self.last or str(self.out_dir)
        self.bus.finished.emit(self.jid, code == 0, tr("Done") if code == 0 else tr("Finished with errors"), out)

    def _spotify(self):
        import yt_dlp
        from yt_dlp.utils import DownloadCancelled
        fmt = "m4a" if self.mode == "m4a" else "mp3"
        self.bus.progress.emit(self.jid, -1, tr("Reading the Spotify link…"))
        name, tracks = spotify_tracks(self.url)
        n = len(tracks)
        folder = self.out_dir / safe_name(name) if n > 1 and name else self.out_dir
        folder.mkdir(parents=True, exist_ok=True)
        base = {"quiet": True, "no_warnings": True, "noprogress": True}
        if FFMPEG:
            base["ffmpeg_location"] = str(Path(FFMPEG).parent)
        ok, missing, last = 0, [], ""
        for i, t in enumerate(tracks, 1):
            if self.cancel.flag.is_set():
                break
            artist = ", ".join(t["artists"])
            label_ = f"{artist} - {t['title']}" if artist else t["title"]
            stem = safe_name(label_)
            done_path = folder / f"{stem}.{fmt}"
            pre = f"{i}/{n} · " if n > 1 else ""
            if done_path.exists():
                ok += 1
                last = str(done_path)
                if not has_cover(done_path):   # downloaded earlier without cover art → add it
                    self.bus.progress.emit(self.jid, (i - 1) / n if n > 1 else -1, pre + tr("Adding cover art") + f" · {label_}")
                    enrich_cover(t)
                    if t.get("cover"):
                        tag_audio(done_path, t, t.get("num"))
                continue
            self.bus.progress.emit(self.jid, (i - 1) / n if n > 1 else -1, pre + tr("Searching: {name}", name=label_))
            try:
                q = f"{t['artists'][0]} - {t['title']}" if t["artists"] else t["title"]
                with yt_dlp.YoutubeDL({**base, "extract_flat": "in_playlist", "skip_download": True}) as ydl:
                    res = ydl.extract_info(f"ytsearch6:{q}", download=False) or {}
                hit = pick_match(res.get("entries") or [], t)
                if not hit:
                    missing.append(label_)
                    continue

                def hook(d, i=i):
                    if self.cancel.flag.is_set():
                        raise DownloadCancelled()
                    if d["status"] == "downloading":
                        tot = d.get("total_bytes") or d.get("total_bytes_estimate")
                        frac = d.get("downloaded_bytes", 0) / tot if tot else 0
                        self.bus.progress.emit(self.jid, ((i - 1) + frac * 0.9) / n,
                                               f"{pre}{frac * 100:.0f}% · {label_}")

                opts = {**base, "format": "bestaudio/best", "outtmpl": str(folder / f"{stem}.%(ext)s"),
                        "progress_hooks": [hook],
                        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": fmt,
                                            "preferredquality": "0" if fmt == "mp3" else "256"}]}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([f"https://www.youtube.com/watch?v={hit['id']}"])
                if done_path.exists():
                    self.bus.progress.emit(self.jid, (i - 0.05) / n, pre + tr("Tags and cover art") + f" · {label_}")
                    enrich_cover(t)
                    tag_audio(done_path, t, t.get("num"))
                    ok += 1
                    last = str(done_path)
                else:
                    missing.append(label_)
            except DownloadCancelled:
                break
            except Exception:  # noqa: BLE001
                if self.cancel.flag.is_set():
                    break
                missing.append(label_)
        if self.cancel.flag.is_set():
            return self.bus.finished.emit(self.jid, False, tr("Canceled · {ok}/{n} downloaded", ok=ok, n=n), str(folder))
        if n == 1:
            msg = tr("Done") if ok else tr("Couldn't find that track on YouTube")
            return self.bus.finished.emit(self.jid, bool(ok), msg, last)
        msg = tr("{ok}/{n} tracks", ok=ok, n=n) + (" · " + tr("not found: {names}", names=", ".join(missing[:3]) + ("…" if len(missing) > 3 else ""))
                                    if missing else "")
        self.bus.finished.emit(self.jid, ok > 0, msg, str(folder))


# ──────────────────────────────────────────────────────────────────────────────
#  UI
# ──────────────────────────────────────────────────────────────────────────────
# Morph palette: dark base shared with Oído + the logo's cyan → blue → violet gradient and coral
BG, SURFACE, SURFACE2, BORDER = "#0B0D10", "#161A20", "#1D222A", "#232833"
TEXT, MUTED = "#E6E8ED", "#9CA3AF"
CYAN, BLUE, VIOLET, CORAL = "#00E5FF", "#2F6BFF", "#6E1BFF", "#FC615E"
ACCENT, ACCENT_INK, DANGER, OK = "#4C8DFF", "#FFFFFF", CORAL, "#34D399"
GRAD = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {CYAN}, stop:0.5 {BLUE}, stop:1 {VIOLET})"
GRAD_H = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4CF0FF, stop:0.5 #5A8BFF, stop:1 #8F55FF)"

QSS = f"""
* {{ font-family:'Inter','Segoe UI Variable Text','Segoe UI',sans-serif; color:{TEXT}; }}
QWidget#root {{ background:{BG}; }}
QLabel#h {{ color:{MUTED}; font-size:11px; font-weight:600; letter-spacing:1.2px; }}
QLabel#hint {{ color:{MUTED}; font-size:12px; }}
QLabel#muted {{ color:{MUTED}; font-size:12px; }}

QFrame#segWrap {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:12px; }}
QPushButton#seg {{ background:transparent; border:none; border-radius:9px; padding:7px 18px;
                  color:{MUTED}; font-weight:600; font-size:13px; }}
QPushButton#seg:hover {{ color:{TEXT}; }}
QPushButton#seg:checked {{ background:{SURFACE2}; color:{TEXT}; }}

QFrame#drop {{ background:{SURFACE}; border:1.5px dashed {BORDER}; border-radius:18px; }}
QFrame#drop[hot="true"] {{ border-color:{CYAN}; background:#0F1A24; }}
QLabel#dropTitle {{ font-size:16px; font-weight:600; }}

QFrame#card {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:16px; }}

QPushButton#chip {{ background:{SURFACE2}; border:1px solid {BORDER}; border-radius:9px;
                   padding:6px 12px; font-weight:600; font-size:12px; color:{MUTED}; min-width:34px; }}
QPushButton#chip:hover {{ color:{TEXT}; border-color:#363B47; }}
QPushButton#chip:checked {{ background:{GRAD}; border-color:transparent; color:#FFFFFF; }}
QPushButton#chip:disabled {{ color:#4A4F59; }}

QPushButton#ghost {{ background:transparent; border:1px solid {BORDER}; border-radius:10px;
                    padding:7px 12px; color:{TEXT}; font-size:12px; }}
QPushButton#ghost:hover {{ background:{SURFACE2}; }}
QPushButton#primary {{ background:{GRAD}; color:#FFFFFF; border:none; border-radius:12px;
                      padding:12px 22px; font-size:14px; font-weight:700; }}
QPushButton#primary:hover {{ background:{GRAD_H}; }}
QPushButton#primary:disabled {{ background:{SURFACE2}; color:#5A5F69; }}
QPushButton#danger {{ background:transparent; color:{DANGER}; border:1px solid #4A2A2E; border-radius:12px;
                     padding:12px 18px; font-size:13px; font-weight:600; }}
QPushButton#danger:hover {{ background:#2A1719; }}
QPushButton#icon {{ background:transparent; border:none; color:{MUTED}; font-size:12px; padding:4px 8px; border-radius:7px; }}
QPushButton#icon:hover {{ background:{SURFACE2}; color:{TEXT}; }}
QComboBox {{ background:transparent; border:1px solid {BORDER}; border-radius:9px; padding:5px 8px; }}
QComboBox QAbstractItemView {{ background:{SURFACE2}; selection-background-color:{BORDER}; }}
QPushButton#verBtn {{ background:transparent; border:none; color:{MUTED}; font-size:11px; padding:4px 6px; }}
QPushButton#verBtn:hover {{ color:{TEXT}; }}

QLineEdit {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:12px; padding:12px 14px;
            font-size:14px; selection-background-color:{BLUE}; selection-color:#FFFFFF; }}
QLineEdit:focus {{ border-color:{BLUE}; }}
QCheckBox {{ color:{MUTED}; font-size:12px; spacing:8px; }}
QCheckBox::indicator {{ width:16px; height:16px; border-radius:5px; border:1px solid {BORDER}; background:{SURFACE2}; }}
QCheckBox::indicator:checked {{ background:{GRAD}; border-color:transparent; }}

QFrame#row {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:12px; }}
QLabel#badge {{ background:{SURFACE2}; border-radius:7px; padding:4px 8px; font-size:10px; font-weight:700;
               color:{MUTED}; letter-spacing:0.5px; }}
QLabel#rowTitle {{ font-size:13px; font-weight:600; }}
QLabel#rowSub {{ font-size:11px; color:{MUTED}; }}
QLabel#rowSub[state="ok"] {{ color:{OK}; }}
QLabel#rowSub[state="err"] {{ color:{DANGER}; }}
QProgressBar {{ background:{SURFACE2}; border:none; border-radius:2px; max-height:4px; min-height:4px; }}
QProgressBar::chunk {{ background:qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CYAN}, stop:1 {VIOLET}); border-radius:2px; }}
QProgressBar[state="ok"]::chunk {{ background:{OK}; }}
QProgressBar[state="err"]::chunk {{ background:{DANGER}; }}

QScrollArea {{ background:transparent; border:none; }}
QScrollArea > QWidget > QWidget {{ background:transparent; }}
QScrollBar:vertical {{ background:transparent; width:8px; margin:2px; }}
QScrollBar::handle:vertical {{ background:{BORDER}; border-radius:4px; min-height:30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; }}
QToolTip {{ background:{SURFACE2}; color:{TEXT}; border:1px solid {BORDER}; padding:6px; border-radius:6px; }}
"""


def find_oido() -> list[str] | None:
    """Command that opens Oído: installed (registry / default folder) or from source."""
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\GermanRobert\Oido") as k:
                exe = Path(winreg.QueryValueEx(k, "InstallPath")[0]) / "Oido.exe"
                if exe.exists():
                    return [str(exe)]
        except OSError:
            pass
        exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Oido" / "Oido.exe"
        if exe.exists():
            return [str(exe)]
    here = Path(__file__).resolve().parent
    for c in (here / "oido.py", here.parent / "oido" / "oido.py", here.parent.parent / "oido" / "src" / "oido.py"):
        if c.exists():
            exe = Path(sys.executable)
            pyw = exe.with_name("pythonw.exe")
            return [str(pyw if pyw.exists() else exe), str(c)]
    return None


def open_in_oido(path: str, parent=None):
    cmd = find_oido()
    if not cmd:
        r = QMessageBox.question(parent, APP, tr("Oído isn't installed.\n\nOído is Morph's sister app: it shows the "
                                                 "spectrogram and the real quality of your files.\nOpen the download page?"))
        if r == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl("https://github.com/stgermanrobert/oido/releases/latest"))
        return
    subprocess.Popen([*cmd, path], creationflags=NO_WINDOW)


def repolish(w, **props):
    for k, v in props.items():
        w.setProperty(k, v)
    w.style().unpolish(w)
    w.style().polish(w)


HEADINGS = ("AUDIO", "VIDEO", "QUALITY", "SAVE TO", "FORMAT")


def label(text, name=None):
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    if name == "h":
        # Same width on every row, wide enough for the longest heading in the current language
        lb.ensurePolished()
        fm = lb.fontMetrics()
        lb.setFixedWidth(max(78, max(fm.horizontalAdvance(tr(t)) for t in HEADINGS) + 16))
    return lb


class Row(QFrame):
    def __init__(self, badge, title, sub, on_remove):
        super().__init__()
        self.setObjectName("row")
        self.out_path = ""
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 10, 12)
        lay.setSpacing(12)
        self.badge = label(badge, "badge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedWidth(116)
        lay.addWidget(self.badge)
        mid = QVBoxLayout()
        mid.setSpacing(5)
        self.title = label(title, "rowTitle")
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.sub = label(sub, "rowSub")
        self.sub.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        mid.addWidget(self.title)
        mid.addWidget(self.bar)
        mid.addWidget(self.sub)
        lay.addLayout(mid, 1)
        self.open_btn = QPushButton(tr("Open"))
        self.open_btn.setIcon(icon("open", TEXT, CYAN))
        self.open_btn.setObjectName("ghost")
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.hide()
        self.open_btn.clicked.connect(self._open)
        lay.addWidget(self.open_btn)
        self.an_btn = QPushButton(tr("Analyze"))
        self.an_btn.setIcon(icon("analyze", TEXT, "#C6F44A"))
        self.an_btn.setObjectName("ghost")
        self.an_btn.setCursor(Qt.PointingHandCursor)
        self.an_btn.setToolTip(tr("Open in Oído: real quality, spectrogram and mix"))
        self.an_btn.hide()
        self.an_btn.clicked.connect(lambda: open_in_oido(self.out_path, self))
        lay.addWidget(self.an_btn)
        self.rm = QPushButton("")
        self.rm.setIcon(icon("close", MUTED))
        self.rm.setObjectName("icon")
        self.rm.setCursor(Qt.PointingHandCursor)
        self.rm.setToolTip(tr("Remove from list"))
        self.rm.clicked.connect(lambda: on_remove(self))
        lay.addWidget(self.rm)

    def set_progress(self, frac, text):
        if frac < 0:
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(frac * 1000))
        self.sub.setText(text)
        repolish(self.sub, state="")

    def set_done(self, ok, text, path):
        self.bar.setRange(0, 1000)
        self.bar.setValue(1000)
        repolish(self.bar, state="ok" if ok else "err")
        self.sub.setText(text)
        self.sub.setToolTip(text)
        repolish(self.sub, state="ok" if ok else "err")
        self.out_path = path
        self.open_btn.setVisible(ok and bool(path))
        p = Path(path) if path else None
        self.an_btn.setVisible(bool(ok and p and (p.is_dir() or p.suffix.lower().lstrip(".") in MEDIA_EXT - {"gif"})))

    def reset(self):
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        repolish(self.bar, state="")
        self.open_btn.hide()
        self.an_btn.hide()

    def _open(self):
        p = Path(self.out_path)
        if os.name == "nt" and p.is_file():
            subprocess.Popen(["explorer", "/select,", str(p)], creationflags=NO_WINDOW)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p if p.is_dir() else p.parent)))


class RowList(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        self.v = QVBoxLayout(host)
        self.v.setContentsMargins(0, 0, 4, 0)
        self.v.setSpacing(8)
        self.v.addStretch(1)
        self.setWidget(host)

    def add(self, row):
        self.v.insertWidget(self.v.count() - 1, row)

    def remove(self, row):
        self.v.removeWidget(row)
        row.deleteLater()


class DropZone(QFrame):
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("drop")
        self.setCursor(Qt.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignCenter)
        v.setSpacing(4)
        self.icon = QLabel()
        self.icon.setPixmap(icon("download", TEXT, CYAN, 64).pixmap(34, 34))
        self.icon.setAlignment(Qt.AlignCenter)
        self.t = label(tr("Drop files or folders here"), "dropTitle")
        self.t.setAlignment(Qt.AlignCenter)
        self.s = label(tr("or click to browse · Ctrl+O"), "hint")
        self.s.setAlignment(Qt.AlignCenter)
        for w in (self.icon, self.t, self.s):
            v.addWidget(w)
        self.compact(False)

    def compact(self, on):
        self.setFixedHeight(64 if on else 170)
        self.icon.setVisible(not on)
        self.s.setText("＋  " + tr("Add more files · click or drag") if on else tr("or click to browse · Ctrl+O"))
        self.t.setVisible(not on)

    def hot(self, on):
        repolish(self, hot="true" if on else "false")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


def chip_group(names, checked, parent_layout, tooltip_fn=None):
    """names: keys (shown upper-cased) or (key, label) pairs."""
    grp = QButtonGroup(parent_layout)
    grp.setExclusive(True)
    for item in names:
        n, text = item if isinstance(item, tuple) else (item, item.upper())
        b = QPushButton(text)
        b.setObjectName("chip")
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setProperty("key", n)
        if tooltip_fn:
            b.setToolTip(tooltip_fn(n))
        grp.addButton(b)
        parent_layout.addWidget(b)
        if n == checked:
            b.setChecked(True)
    return grp


class Morph(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle(APP)
        self.setAcceptDrops(True)
        self.resize(820, 760)
        self.setMinimumSize(640, 600)
        self.cfg = QSettings("GermanRobert", APP)
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(max(1, min(4, (os.cpu_count() or 2) // 2)))
        self.bus = Bus()
        self.bus.progress.connect(self._on_progress)
        self.bus.finished.connect(self._on_finished)
        self.next_id = 0
        self.rows: dict[int, Row] = {}
        self.pending: dict[Row, Path] = {}     # conversion rows not started yet
        self.active_conv: set[int] = set()
        self.active_dl: set[int] = set()
        self.cancel_conv = Cancel()
        self.cancel_dl = Cancel()
        self.out_dir = self._saved_dir("out_dir", None)
        self.dl_dir = self._saved_dir("dl_dir", Path.home() / "Downloads")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(18)

        # Header
        head = QHBoxLayout()
        head.addWidget(RT.logo_label(30))
        head.addSpacing(10)
        ver = QPushButton(f"v{__version__}")
        ver.setObjectName("verBtn")
        ver.setIcon(icon("github", MUTED))
        ver.setCursor(Qt.PointingHandCursor)
        ver.setToolTip(tr("View the project on GitHub"))
        ver.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        head.addWidget(ver)
        self.lang_box = QComboBox()
        self.lang_box.setObjectName("lang")
        self.lang_box.setToolTip(tr("Language"))
        for code, name in i18n.LANGS.items():
            self.lang_box.addItem(name, code)
        self.lang_box.setCurrentIndex(list(i18n.LANGS).index(i18n.current()))
        self.lang_box.currentIndexChanged.connect(self._change_lang)
        head.addWidget(self.lang_box)
        head.addStretch(1)
        seg = QFrame()
        seg.setObjectName("segWrap")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(4, 4, 4, 4)
        sl.setSpacing(2)
        self.tabs = QButtonGroup(self)
        for i, (t, ic) in enumerate(((tr("Convert"), "convert"), (tr("Download"), "download"))):
            b = QPushButton(" " + t)
            b.setIcon(icon(ic, TEXT, CYAN))
            b.setIconSize(QSize(16, 16))
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.tabs.addButton(b, i)
            sl.addWidget(b)
        self.tabs.button(0).setChecked(True)
        head.addWidget(seg)
        root.addLayout(head)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_convert())
        self.stack.addWidget(self._build_download())
        self.tabs.idClicked.connect(self.stack.setCurrentIndex)
        root.addWidget(self.stack, 1)

        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._pick_files)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self._tab(0))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self._tab(1))
        self._refresh_convert_ui()

    # ── helpers ──
    def _saved_dir(self, key, default):
        v = self.cfg.value(key, "")
        return Path(v) if v and Path(v).is_dir() else default

    def _tab(self, i):
        self.tabs.button(i).setChecked(True)
        self.stack.setCurrentIndex(i)

    def _new_id(self):
        self.next_id += 1
        return self.next_id

    # ── Convertir ──
    def _build_convert(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        self.drop = DropZone()
        self.drop.clicked.connect(self._pick_files)
        v.addWidget(self.drop)
        self.conv_list = RowList()
        v.addWidget(self.conv_list, 1)

        card = QFrame()
        card.setObjectName("card")
        c = QVBoxLayout(card)
        c.setContentsMargins(18, 16, 18, 16)
        c.setSpacing(12)

        fmt_saved = self.cfg.value("fmt", "mp3")
        q_saved = int(self.cfg.value("quality", 0))

        r1 = QHBoxLayout()
        r1.setSpacing(6)
        r1.addWidget(label(tr("AUDIO"), "h"))
        ga = chip_group(AUDIO_FORMATS, fmt_saved, r1)
        r1.addStretch(1)
        c.addLayout(r1)
        r1b = QHBoxLayout()
        r1b.setSpacing(6)
        r1b.addWidget(label(tr("VIDEO"), "h"))
        gv = chip_group(VIDEO_FORMATS, fmt_saved, r1b)
        r1b.addStretch(1)
        r1 = r1b
        self.fmt_buttons = ga.buttons() + gv.buttons()
        self.fmt_group = QButtonGroup(self)  # unificar exclusividad entre ambos grupos
        for b in self.fmt_buttons:
            ga.removeButton(b) if b in ga.buttons() else gv.removeButton(b)
            self.fmt_group.addButton(b)
        if not self.fmt_group.checkedButton():
            self.fmt_buttons[0].setChecked(True)
        self.fmt_group.buttonClicked.connect(lambda _: self._refresh_convert_ui())
        c.addLayout(r1)

        r2 = QHBoxLayout()
        r2.setSpacing(6)
        r2.addWidget(label(tr("QUALITY"), "h"))
        self.q_group = QButtonGroup(self)
        for i, n in enumerate(QUALITIES):
            b = QPushButton(tr(n))
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.q_group.addButton(b, i)
            r2.addWidget(b)
        self.q_group.button(q_saved if 0 <= q_saved < 3 else 0).setChecked(True)
        self.q_group.idClicked.connect(lambda _: self._refresh_convert_ui())
        r2.addSpacing(10)
        self.spec = label("", "hint")
        r2.addWidget(self.spec, 1)
        c.addLayout(r2)

        r3 = QHBoxLayout()
        r3.setSpacing(8)
        r3.addWidget(label(tr("SAVE TO"), "h"))
        self.out_btn = QPushButton()
        self.out_btn.setObjectName("ghost")
        self.out_btn.setCursor(Qt.PointingHandCursor)
        self.out_btn.clicked.connect(self._pick_out_dir)
        r3.addWidget(self.out_btn)
        self.out_reset = QPushButton(tr("Next to the original"))
        self.out_reset.setObjectName("icon")
        self.out_reset.setCursor(Qt.PointingHandCursor)
        self.out_reset.clicked.connect(self._reset_out_dir)
        r3.addWidget(self.out_reset)
        r3.addStretch(1)
        self.clear_btn = QPushButton(tr("Clear finished"))
        self.clear_btn.setObjectName("icon")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_done)
        r3.addWidget(self.clear_btn)
        self.conv_cancel = QPushButton(tr("Cancel"))
        self.conv_cancel.setObjectName("danger")
        self.conv_cancel.setCursor(Qt.PointingHandCursor)
        self.conv_cancel.clicked.connect(self._cancel_convert)
        r3.addWidget(self.conv_cancel)
        self.go = QPushButton(tr("Convert"))
        self.go.setObjectName("primary")
        self.go.setCursor(Qt.PointingHandCursor)
        self.go.clicked.connect(self._start_convert)
        r3.addWidget(self.go)
        c.addLayout(r3)
        v.addWidget(card)
        return page

    def _fmt(self):
        b = self.fmt_group.checkedButton()
        return b.property("key") if b else "mp3"

    def _q(self):
        return max(0, self.q_group.checkedId())

    def _refresh_convert_ui(self):
        fmt, q = self._fmt(), self._q()
        self.spec.setText(describe(fmt, q))
        is_flac = fmt == "flac"
        for b in self.q_group.buttons():
            b.setEnabled(not is_flac)
        self.cfg.setValue("fmt", fmt)
        self.cfg.setValue("quality", q)
        self.out_btn.setIcon(icon("folder", TEXT, CYAN))
        self.out_btn.setText(f" {self.out_dir.name or str(self.out_dir)}" if self.out_dir else " " + tr("Choose folder…"))
        self.out_reset.setVisible(bool(self.out_dir))
        n = len(self.pending)
        busy = bool(self.active_conv)
        self.go.setText(tr("Convert {n}  →  {fmt}", n=n, fmt=fmt.upper()) if n else tr("Convert  →  {fmt}", fmt=fmt.upper()))
        self.go.setMinimumWidth(self.go.fontMetrics().horizontalAdvance(self.go.text()) + 60)
        self.clear_btn.setVisible(any(r not in self.pending for r in self.rows.values()
                                      if r.parentWidget() is self.conv_list.widget()))
        self.go.setEnabled(n > 0)
        self.conv_cancel.setVisible(busy)
        self.drop.compact(bool(self.pending) or busy or self.conv_list.v.count() > 1)

    def _pick_files(self):
        self._tab(0)
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("Choose files"), str(self.cfg.value("last_in", str(Path.home()))),
            tr("Audio/Video") + " (" + " ".join(f"*.{e}" for e in sorted(MEDIA_EXT)) + ");;" + tr("All files") + " (*)")
        if files:
            self.cfg.setValue("last_in", str(Path(files[0]).parent))
            self._add_files([Path(f) for f in files])

    def _add_files(self, paths):
        seen = set(self.pending.values())
        for p in paths:
            items = [p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else []
            for f in items:
                if f.suffix.lower().lstrip(".") not in MEDIA_EXT and p.is_dir():
                    continue
                if f in seen:
                    continue
                seen.add(f)
                size = f.stat().st_size / 1_048_576
                row = Row(f.suffix.lstrip(".").upper() or "?", f.name, f"{size:.1f} MB · " + tr("queued"), self._remove_row)
                self.conv_list.add(row)
                self.pending[row] = f
        self._refresh_convert_ui()

    def _remove_row(self, row):
        jid = next((k for k, r in self.rows.items() if r is row), None)
        if jid in self.active_conv or jid in self.active_dl:
            return  # no quitar trabajos en curso
        self.pending.pop(row, None)
        if jid is not None:
            self.rows.pop(jid, None)
        (self.conv_list if row.parentWidget() is self.conv_list.widget() else self.dl_list).remove(row)
        self._refresh_convert_ui()

    def _clear_done(self):
        for jid, row in list(self.rows.items()):
            if jid not in self.active_conv and row not in self.pending and row.parentWidget() is self.conv_list.widget():
                self.rows.pop(jid)
                self.conv_list.remove(row)
        self._refresh_convert_ui()

    def _pick_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, tr("Output folder"), str(self.out_dir or Path.home()))
        if d:
            self.out_dir = Path(d)
            self.cfg.setValue("out_dir", d)
            self._refresh_convert_ui()

    def _reset_out_dir(self):
        self.out_dir = None
        self.cfg.setValue("out_dir", "")
        self._refresh_convert_ui()

    def _start_convert(self):
        if not self.pending:
            return
        if not self.active_conv:
            self.cancel_conv = Cancel()
        fmt, q = self._fmt(), self._q()
        for row, src in list(self.pending.items()):
            jid = self._new_id()
            self.rows[jid] = row
            row.reset()
            row.badge.setText(f"{src.suffix.lstrip('.').upper()} → {fmt.upper()}")
            row.set_progress(0, tr("Waiting…"))
            self.active_conv.add(jid)
            self.pool.start(ConvertTask(jid, src, fmt, q, self.out_dir, self.bus, self.cancel_conv))
        self.pending.clear()
        self._refresh_convert_ui()

    def _cancel_convert(self):
        self.cancel_conv.fire()

    # ── Descargar ──
    def _build_download(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        card = QFrame()
        card.setObjectName("card")
        c = QVBoxLayout(card)
        c.setContentsMargins(18, 18, 18, 18)
        c.setSpacing(12)
        r0 = QHBoxLayout()
        r0.setSpacing(8)
        self.url = QLineEdit()
        self.url.setPlaceholderText(tr("Paste a YouTube, Spotify, SoundCloud or Vimeo link…"))
        self.url.returnPressed.connect(self._start_download)
        r0.addWidget(self.url, 1)
        paste = QPushButton(" " + tr("Paste"))
        paste.setIcon(icon("paste", TEXT, CYAN))
        paste.setObjectName("ghost")
        paste.setCursor(Qt.PointingHandCursor)
        paste.clicked.connect(self._paste_and_go)
        r0.addWidget(paste)
        c.addLayout(r0)

        r1 = QHBoxLayout()
        r1.setSpacing(6)
        r1.addWidget(label(tr("FORMAT"), "h"))
        self.dl_group = chip_group([("mp3", "MP3"), ("m4a", "M4A"), ("video", tr("Video MP4"))], self.cfg.value("dl_mode", "mp3"), r1)
        if not self.dl_group.checkedButton():
            self.dl_group.buttons()[0].setChecked(True)
        self.dl_group.buttonClicked.connect(lambda b: self.cfg.setValue("dl_mode", b.property("key")))
        r1.addSpacing(12)
        self.playlist = QCheckBox(tr("Download the whole playlist"))
        r1.addWidget(self.playlist)
        r1.addStretch(1)
        c.addLayout(r1)

        r2 = QHBoxLayout()
        r2.setSpacing(8)
        r2.addWidget(label(tr("SAVE TO"), "h"))
        self.dl_btn_dir = QPushButton(f" {self.dl_dir.name}")
        self.dl_btn_dir.setIcon(icon("folder", TEXT, CYAN))
        self.dl_btn_dir.setObjectName("ghost")
        self.dl_btn_dir.setCursor(Qt.PointingHandCursor)
        self.dl_btn_dir.clicked.connect(self._pick_dl_dir)
        r2.addWidget(self.dl_btn_dir)
        r2.addStretch(1)
        self.dl_cancel = QPushButton(tr("Cancel"))
        self.dl_cancel.setObjectName("danger")
        self.dl_cancel.setCursor(Qt.PointingHandCursor)
        self.dl_cancel.clicked.connect(lambda: self.cancel_dl.fire())
        self.dl_cancel.hide()
        r2.addWidget(self.dl_cancel)
        go = QPushButton(tr("Download"))
        go.setObjectName("primary")
        go.setCursor(Qt.PointingHandCursor)
        go.clicked.connect(self._start_download)
        r2.addWidget(go)
        c.addLayout(r2)
        v.addWidget(card)

        note = label(tr("MP3 comes out at top-quality VBR with cover art and tags. Spotify links: Morph reads the link's "
                        "public info (no account, no login) and fetches each track from YouTube, tagged with Spotify's "
                        "cover art."), "muted")
        note.setWordWrap(True)
        v.addWidget(note)
        self.dl_list = RowList()
        v.addWidget(self.dl_list, 1)
        return page

    def _paste_and_go(self):
        txt = QGuiApplicationClipboard().strip()
        if txt:
            self.url.setText(txt)
            self._start_download()

    def _pick_dl_dir(self):
        d = QFileDialog.getExistingDirectory(self, tr("Save downloads to"), str(self.dl_dir))
        if d:
            self.dl_dir = Path(d)
            self.cfg.setValue("dl_dir", d)
            self.dl_btn_dir.setText(f" {self.dl_dir.name}")

    def _start_download(self):
        url = self.url.text().strip()
        if not url:
            self.url.setFocus()
            return
        if not url.startswith(("http://", "https://", "spotify:")):
            url = "https://" + url
        mode_key = self.dl_group.checkedButton().property("key")
        mode = {"mp3": "mp3", "m4a": "m4a"}.get(mode_key, "mp4")   # "video" → mp4
        if not self.active_dl:
            self.cancel_dl = Cancel()
        jid = self._new_id()
        is_sp = is_spotify(url)
        row = Row(("SPOTIFY" if is_sp else "WEB") + f" → {mode.upper()}", url, tr("Starting…"), self._remove_row)
        self.rows[jid] = row
        self.dl_list.add(row)
        row.set_progress(-1, tr("Starting…"))
        self.active_dl.add(jid)
        self.dl_cancel.show()
        self.url.clear()
        if not importlib.util.find_spec("yt_dlp"):
            return self._on_finished(jid, False, tr("yt-dlp is missing:") + '  pip install -U "yt-dlp[default]"', "")
        self.pool.start(DownloadTask(jid, url, mode, self.playlist.isChecked(), self.dl_dir, self.bus, self.cancel_dl))

    # ── language ──
    def _change_lang(self, _):
        code = self.lang_box.currentData()
        if code == i18n.current():
            return
        self.cfg.setValue("lang", code)
        i18n.setup(locales.CATALOGS, code)
        if self.active_conv or self.active_dl:
            QMessageBox.information(self, APP, tr("The new language will apply the next time you open Morph."))
            return
        if QMessageBox.question(self, APP, tr("Restart Morph now to switch the language?")) == QMessageBox.Yes:
            prog = sys.executable
            args = [] if getattr(sys, "frozen", False) else [str(Path(__file__).resolve())]
            QProcess.startDetached(prog, args)
            QApplication.quit()

    # ── signals ──
    def _on_progress(self, jid, frac, text):
        if (row := self.rows.get(jid)):
            row.set_progress(frac, text)

    def _on_finished(self, jid, ok, text, path):
        row = self.rows.get(jid)
        if row:
            if ok and path and Path(path).is_file():
                row.title.setText(Path(path).name)
            row.set_done(ok, text, path)
        self.active_conv.discard(jid)
        self.active_dl.discard(jid)
        self.dl_cancel.setVisible(bool(self.active_dl))
        self._refresh_convert_ui()

    # ── drag & drop ──
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.drop.hot(True)
            self._tab(0)

    def dragLeaveEvent(self, e):
        self.drop.hot(False)

    def dropEvent(self, e):
        self.drop.hot(False)
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self._add_files(paths)
        else:  # a link was dropped from the browser
            urls = [u.toString() for u in e.mimeData().urls()]
            if urls:
                self._tab(1)
                self.url.setText(urls[0])

    def closeEvent(self, e):
        if self.active_conv or self.active_dl:
            r = QMessageBox.question(self, APP, tr("Jobs are still running. Cancel them and quit?"))
            if r != QMessageBox.Yes:
                return e.ignore()
            self.cancel_conv.fire()
            self.cancel_dl.fire()
        e.accept()


def QGuiApplicationClipboard() -> str:
    return QApplication.clipboard().text() or ""


def selftest(report: str) -> int:
    """Build self-test: converts with the bundled FFmpeg and checks yt-dlp/Deno."""
    import time
    lines, ok = [], True
    try:
        d = Path(tempfile.mkdtemp())
        wav = d / "t.wav"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=4", str(wav)],
                       check=True, creationflags=NO_WINDOW)
        mp4 = d / "v.mp4"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x240:d=2", "-f", "lavfi",
                        "-i", "sine=d=2", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(mp4)],
                       check=True, creationflags=NO_WINDOW)
        lines.append(f"ffmpeg={FFMPEG}")
        bus, res = Bus(), {}
        bus.finished.connect(lambda j, okk, t, pth: res.__setitem__(j, (okk, t, pth)))
        jobs = [(wav, "mp3", 0), (wav, "flac", 0), (mp4, "mkv", 1), (mp4, "webm", 2), (mp4, "gif", 2)]
        for i, (src, fmt, q) in enumerate(jobs):
            ConvertTask(i, src, fmt, q, d, bus, Cancel()).run()
        app = QApplication.instance()
        app.processEvents()
        for i, (src, fmt, _) in enumerate(jobs):
            okk, t, pth = res.get(i, (False, "no result", ""))
            lines.append(f"{src.suffix}->{fmt}: {okk} {t}")
            ok &= okk and Path(pth).exists()
        import yt_dlp
        lines.append(f"yt-dlp={yt_dlp.version.__version__}")
        deno = shutil.which("deno")
        lines.append(f"deno={deno}")
        if RT.FROZEN:
            ok &= bool(deno)
        w = Morph()
        w.show()
        t0 = time.time()
        while time.time() - t0 < 1:
            app.processEvents()
        w.close()
    except Exception as e:  # noqa: BLE001
        ok = False
        lines.append(f"ERROR {e!r}")
    lines.append("SELFTEST " + ("OK" if ok else "FAIL"))
    Path(report).write_text("\n".join(lines), encoding="utf-8")
    return 0 if ok else 1


def main():
    RT.set_windows_app_id("GermanRobert.Morph")
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(RT.app_icon("morph"))
    family = RT.load_fonts()
    i18n.setup(locales.CATALOGS, QSettings("GermanRobert", APP).value("lang", None))
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    f = QFont(family)
    f.setPointSizeF(9.5)
    app.setFont(f)
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        return selftest(sys.argv[2])
    if not (FFMPEG and FFPROBE):
        QMessageBox.critical(None, APP, tr("FFmpeg not found.\n\nReinstall Morph or, if you're running from source, "
                                           "install FFmpeg with:\n    winget install Gyan.FFmpeg"))
        return 1
    w = Morph()
    w.setWindowTitle(f"{APP} {__version__}")
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
