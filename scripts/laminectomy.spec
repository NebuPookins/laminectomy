# PyInstaller spec for the laminectomy executable.
#
# Run through scripts/build_binary.py, which sets LAMINECTOMY_EXE_NAME. A spec is used
# instead of plain command-line options so the bundled data files can be filtered.
#
# SPECPATH is provided by PyInstaller and points at this directory.

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH).resolve().parent
EXE_NAME = os.environ["LAMINECTOMY_EXE_NAME"]

# Qt modules the app never imports. Excluding them shrinks the bundle without touching the
# web engine the viewer needs. Add a module here only after confirming the app still runs.
UNUSED_QT_MODULES = [
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQml",
    "PySide6.QtDesigner",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtGraphs",
    "PySide6.QtMultimedia",
    "PySide6.QtSpatialAudio",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSerialBus",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebSockets",
]

# Native packages UnityPy loads at run time. PyInstaller misses their shared libraries,
# data files, or both, so each one is collected in full.
NATIVE_PACKAGES = [
    "fmod_toolkit",
    "texture2ddecoder",
    "etcpak",
    "astc_encoder",
    "tpk_ar",
    # astc_encoder imports archspec at load time and needs its CPU database files.
    "archspec",
]

datas = [(str(ROOT / "src" / "laminectomy" / "web"), "laminectomy/web")]
binaries = []
hiddenimports = []
for package in NATIVE_PACKAGES:
    package_datas, package_binaries, package_imports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_imports
datas += collect_data_files("UnityPy")

a = Analysis(
    [str(ROOT / "scripts" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=UNUSED_QT_MODULES,
)


def _is_droppable_translation(dest: str) -> bool:
    """Translation files the app never shows: Qt's .qm catalogues, and WebEngine locale
    packs other than English. WebEngine still needs en-US.pak, so that one stays."""
    parts = Path(dest).parts
    if "translations" not in parts:
        return False
    if parts[-1].endswith(".qm"):
        return True
    if "qtwebengine_locales" in parts and parts[-1].endswith(".pak"):
        return parts[-1] != "en-US.pak"
    return False


dropped = [dest for dest, _, _ in a.datas if _is_droppable_translation(dest)]
print(f"Dropping {len(dropped)} translation data files")
a.datas = [entry for entry in a.datas if not _is_droppable_translation(entry[0])]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name=EXE_NAME,
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
