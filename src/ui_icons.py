"""
Vector UI icons (style-guide look: 2 px rounded strokes, white + accent color).
Drawn as SVG and turned into QIcon at runtime, so they stay crisp at any scale.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# {fg} = main stroke color, {ac} = accent color
_SVG = {
    "ab": '<text x="2" y="17" font-family="Inter,Segoe UI,sans-serif" font-size="13" font-weight="700" fill="{fg}">A</text>'
          '<path d="M12 4v16" stroke="{fg}" stroke-opacity=".5"/>'
          '<text x="14" y="17" font-family="Inter,Segoe UI,sans-serif" font-size="13" font-weight="700" fill="{ac}">B</text>',
    "folder": '<path d="M3 7.5V18a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9.5a2 2 0 0 0-2-2h-7l-2-2.5H5a2 2 0 0 0-2 2z" stroke="{fg}"/>'
              '<path d="M12 7.5h7" stroke="{ac}"/>',
    "export": '<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5" stroke="{ac}"/><path d="M4 13v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5" stroke="{fg}"/>',
    "download": '<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5" stroke="{ac}"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" stroke="{fg}"/>',
    "star": '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" stroke="{ac}"/>',
    "star_fill": '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" stroke="{ac}" fill="{ac}"/>',
    "badge": '<circle cx="12" cy="9.5" r="5.5" stroke="{ac}"/><path d="m9.7 9.6 1.6 1.6 3-3" stroke="{ac}"/>'
             '<path d="m8.5 14 -2 6 3-1 1.5 2.5 1-4M15.5 14l2 6-3-1-1.5 2.5-1-4" stroke="{fg}"/>',
    "play": '<path d="M8 5.5v13l10-6.5z" fill="{fg}" stroke="{fg}"/>',
    "pause": '<path d="M8.5 5.5v13M15.5 5.5v13" stroke="{fg}" stroke-width="3"/>',
    "mono": '<circle cx="12" cy="12" r="8" stroke="{fg}"/><circle cx="12" cy="12" r="3.2" stroke="{ac}"/>',
    "side": '<circle cx="9" cy="12" r="6" stroke="{fg}"/><circle cx="15" cy="12" r="6" stroke="{ac}"/>',
    "low": '<path d="M3 10c3-3 6 3 9 0s6 3 9 0M3 15c3-3 6 3 9 0s6 3 9 0" stroke="{fg}"/>',
    "high": '<path d="m3 9 3-3 3 3 3-3 3 3 3-3 3 3M3 14l3-3 3 3 3-3 3 3 3-3 3 3M3 19l3-3 3 3 3-3 3 3 3-3 3 3" stroke="{ac}"/>',
    "normal": '<path d="M3 12h2M7 8v8M11 5v14M15 8v8M19 10v4M21 12h0" stroke="{fg}"/>',
    "scale": '<path d="M5 19v-4M10 19v-7M15 19V9M20 19V5" stroke="{fg}"/><path d="M20 19V5" stroke="{ac}"/>',
    "loudness": '<path d="M3 12h1M6 9v6M9 6v12M12 3v18M15 7v10M18 10v4M21 12h0" stroke="{ac}"/>',
    "scope": '<path d="M12 3v18M3 12h18" stroke="{fg}" stroke-opacity=".45"/>'
             '<g fill="{ac}"><circle cx="12" cy="7" r="1.3"/><circle cx="9.5" cy="9.5" r="1.3"/><circle cx="14.5" cy="9.5" r="1.3"/>'
             '<circle cx="12" cy="12" r="1.3"/><circle cx="7" cy="12" r="1.3"/><circle cx="17" cy="12" r="1.3"/>'
             '<circle cx="9.5" cy="14.5" r="1.3"/><circle cx="14.5" cy="14.5" r="1.3"/><circle cx="12" cy="17" r="1.3"/></g>',
    "learn": '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v15H5.5A1.5 1.5 0 0 0 4 20.5zM20 5.5A1.5 1.5 0 0 0 18.5 4H13v15h5.5a1.5 1.5 0 0 1 1.5 1.5z" stroke="{fg}"/>'
             '<path d="M15.5 8h2" stroke="{ac}"/>',
    "quality": '<circle cx="12" cy="12" r="8.5" stroke="{fg}"/><path d="m8.3 12.2 2.4 2.4 5-5" stroke="{ac}"/>',
    "convert": '<path d="M4 9h13l-3.5-3.5" stroke="{fg}"/><path d="M20 15H7l3.5 3.5" stroke="{ac}"/>',
    "link": '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1" stroke="{fg}"/>'
            '<path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1" stroke="{ac}"/>',
    "paste": '<rect x="6" y="5" width="12" height="15" rx="2" stroke="{fg}"/><path d="M9.5 3.5h5v3h-5z" stroke="{ac}"/>',
    "info": '<circle cx="12" cy="12" r="8.5" stroke="{fg}"/><path d="M12 11v5" stroke="{ac}"/><circle cx="12" cy="8" r=".6" fill="{ac}" stroke="{ac}"/>',
    "close": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11" stroke="{fg}"/>',
    "open": '<path d="M14 4h6v6M20 4l-8.5 8.5" stroke="{ac}"/><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" stroke="{fg}"/>',
    "analyze": '<path d="M3 12h2M7 9v6M11 6v12M15 9v6" stroke="{fg}"/><circle cx="17.5" cy="15.5" r="3.2" stroke="{ac}"/><path d="m20 18 2 2" stroke="{ac}"/>',
    "swap": '<path d="M7 4 3.5 7.5 7 11M3.5 7.5H17" stroke="{fg}"/><path d="m17 13 3.5 3.5L17 20M20.5 16.5H7" stroke="{ac}"/>',
    "github": '<path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 '
              '4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12.3 12.3 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 '
              '4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" stroke="{fg}"/>',
}

_cache: dict = {}


def svg(name: str, fg="#E6E8ED", ac="#C6F44A") -> str:
    body = _SVG[name].format(fg=fg, ac=ac)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def icon(name: str, fg="#E6E8ED", ac="#C6F44A", size=48) -> QIcon:
    key = (name, fg, ac, size)
    if key not in _cache:
        r = QSvgRenderer(QByteArray(svg(name, fg, ac).encode()))
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p, QRectF(0, 0, size, size))
        p.end()
        _cache[key] = QIcon(pm)
    return _cache[key]
