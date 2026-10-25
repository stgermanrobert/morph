# Changelog

All notable changes to Morph. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-25

First public release.

### Convert
- Audio (MP3, M4A, FLAC, WAV, OGG, OPUS) and video (MP4, MKV, WEBM, MOV, GIF) conversion, several files in parallel.
- Instant lossless remux when the codecs allow it, with automatic re-encoding as a fallback.
- Three quality levels per format, with the exact encoder setting shown.

### Download
- Downloads from YouTube and 1000+ sites through yt-dlp: MP3 with cover art and tags, M4A or MP4 video, playlists included.
- Spotify links (tracks, albums, public playlists) using public information only:
  - matched on YouTube by duration and official channel;
  - Spotify tags and cover art;
  - fills in missing cover art when a playlist is downloaded again.

### Integration
- "Analyze" button that opens any result in Oído.

### Interface
- English, Spanish and Russian, switchable from the header.

### Distribution
- Windows installer that needs no admin rights, portable ZIP, with FFmpeg, yt-dlp and Deno bundled.
