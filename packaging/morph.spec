# -*- mode: python ; coding: utf-8 -*-
# PyInstaller, one-folder build: starts faster and trips fewer antivirus heuristics than one-file,
# and keeps the Qt DLLs as separate files, as the LGPL expects.
from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

a = Analysis(
    [str(SRC / "morph.py")],
    pathex=[str(SRC)],
    datas=[(str(SRC / "assets"), "assets")],
    hiddenimports=['PySide6.QtSvg', 'yt_dlp', 'yt_dlp_ejs'],
    excludes=['tkinter', 'matplotlib', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick', 'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQml', 'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtDesigner', 'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtBluetooth', 'PySide6.QtPositioning', 'PySide6.QtLocation', 'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtWebSockets', 'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.QtGraphs', 'PySide6.QtHttpServer', 'PySide6.QtSpatialAudio', 'PySide6.QtTextToSpeech', 'PySide6.QtMultimedia'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Morph",
    icon=str(ROOT / "packaging" / "morph.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Morph", upx=False)
