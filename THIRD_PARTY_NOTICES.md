# Third-party notices

Morph's **source code** is released under the **MIT** license (see `LICENSE`).
The **installer and portable ZIP** also ship the components below, each under its own license.

| Component | Used for | License | Source |
|---|---|---|---|
| **FFmpeg / ffprobe** (BtbN static build) | Decoding, converting and measuring audio/video | **GPL v3** (`win64-gpl` build) | https://ffmpeg.org · https://github.com/BtbN/FFmpeg-Builds |
| **Qt 6 / PySide6 / shiboken6** | User interface | **LGPL v3** | https://www.qt.io · https://code.qt.io/cgit/pyside/pyside-setup.git |
| **Python** | Interpreter | PSF License | https://www.python.org |
| **Inter** (typeface) | User interface | SIL Open Font License 1.1 | https://github.com/rsms/inter |
| **yt-dlp** | Downloads | Unlicense | https://github.com/yt-dlp/yt-dlp |
| **yt-dlp-ejs** | YouTube JavaScript challenges | Unlicense AND MIT AND ISC | https://github.com/yt-dlp/ejs |
| **Deno** | JavaScript runtime for yt-dlp | MIT | https://github.com/denoland/deno |
| **mutagen** | Audio metadata (through yt-dlp) | **GPL-2.0-or-later** | https://github.com/quodlibet/mutagen |
| **requests** | HTTP (through yt-dlp) | Apache-2.0 | https://github.com/psf/requests |
| **urllib3**, **brotli**, **charset-normalizer** | HTTP (through yt-dlp) | MIT | PyPI |
| **certifi** | Root certificates | MPL-2.0 | https://github.com/certifi/python-certifi |
| **websockets**, **idna** | Networking (through yt-dlp) | BSD-3-Clause | PyPI |
| **pycryptodomex** | Cryptography (through yt-dlp) | BSD / public domain | https://github.com/Legrandin/pycryptodome |

## Notes

- **FFmpeg** ships as a **separate program** (`_internal/bin/ffmpeg.exe`, `ffprobe.exe`) that Morph runs as an external process. Its license is in `_internal/bin/FFmpeg-LICENSE.txt` and the exact build origin in `_internal/bin/FFmpeg-SOURCE.txt`. FFmpeg's source code is at https://ffmpeg.org/download.html and the build scripts at https://github.com/BtbN/FFmpeg-Builds.
- **Qt / PySide6** ships as separate dynamic libraries (`.dll` files inside `_internal/`) that can be replaced with other compatible versions, as the LGPL v3 allows.
- Morph's binary package includes **GPL** components (FFmpeg, mutagen). Morph's own code remains MIT; the binary distribution as a whole follows the GPL's terms, and Morph's complete source code is in this repository.
- If you need the corresponding source code of any of these components and the links above no longer work, open an issue in this repository.
