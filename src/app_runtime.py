"""
Shared runtime: resource paths (source tree or PyInstaller .exe), bundled binaries (FFmpeg, Deno),
the Inter typeface, the Windows taskbar icon and the header logo.
Import this BEFORE any module that looks up ffmpeg on PATH.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ASSETS = BASE / "assets"
BIN = BASE / "bin"

# FFmpeg / ffprobe / Deno shipped with the installer take precedence over system copies
if BIN.is_dir():
    os.environ["PATH"] = str(BIN) + os.pathsep + os.environ.get("PATH", "")


def set_windows_app_id(app_id: str):
    """Without this, Windows groups the app under the Python icon on the taskbar."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:  # noqa: BLE001
            pass


def load_fonts() -> str:
    from PySide6.QtGui import QFontDatabase
    family = ""
    for f in sorted((ASSETS / "fonts").glob("*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(f))
        if fid >= 0 and not family:
            fams = QFontDatabase.applicationFontFamilies(fid)
            family = fams[0] if fams else ""
    return family or "Segoe UI"


def app_icon(name: str):
    from PySide6.QtGui import QIcon
    ico = ASSETS / f"{name}.ico"
    return QIcon(str(ico)) if ico.exists() else QIcon(str(ASSETS / "icon_256.png"))


def logo_label(height: int = 30):
    """Header logo (icon + wordmark), crisp on HiDPI screens."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QPixmap
    from PySide6.QtWidgets import QLabel
    pm = QPixmap(str(ASSETS / "logo_ui.png"))
    dpr = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
    if not pm.isNull():
        pm = pm.scaledToHeight(int(height * dpr), Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
    lb = QLabel()
    lb.setPixmap(pm)
    return lb
