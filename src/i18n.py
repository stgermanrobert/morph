"""
Minimal i18n: English source strings, translated through per-language catalogs (locales.py).

    tr("Open files")                          -> "Abrir archivos" (es)
    tr("{n} files", n=3)                      -> placeholders are filled after translation
"""
from __future__ import annotations

LANGS = {"en": "English", "es": "Español", "ru": "Русский"}
_lang = "en"
_catalogs: dict[str, dict[str, str]] = {}


def setup(catalogs: dict[str, dict[str, str]], lang: str | None):
    global _lang, _catalogs
    _catalogs = catalogs
    _lang = lang if lang in LANGS else system_language()


def system_language() -> str:
    try:
        from PySide6.QtCore import QLocale
        code = QLocale.system().name()[:2].lower()
    except Exception:  # noqa: BLE001
        code = "en"
    return code if code in LANGS else "en"


def current() -> str:
    return _lang


def tr(text: str, **kw) -> str:
    out = _catalogs.get(_lang, {}).get(text, text)
    return out.format(**kw) if kw else out
