"""Build a single-file executable for the platform this script runs on.

Output: dist/laminectomy-<os>-<arch>[.exe]. PyInstaller cannot cross-compile,
so run this on each target OS (CI does this).
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]

_OS_NAMES = {"Linux": "linux", "Windows": "windows", "Darwin": "macos"}
_ARCH_NAMES = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}


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


def platform_tag() -> str:
    system = _OS_NAMES[platform.system()]
    arch = _ARCH_NAMES[platform.machine().lower()]
    return f"{system}-{arch}"


def main() -> None:
    web_dir = ROOT / "src" / "laminectomy" / "web"
    PyInstaller.__main__.run(
        [
            "--onefile",
            "--clean",
            "--noconfirm",
            "--name",
            f"laminectomy-{platform_tag()}",
            "--paths",
            str(ROOT / "src"),
            # The viewer page is read at build time through importlib.resources.
            "--add-data",
            f"{web_dir}{os.pathsep}laminectomy/web",
            "--collect-data",
            "UnityPy",
            # UnityPy loads these native decoders at run time; PyInstaller misses their shared libraries.
            "--collect-all",
            "fmod_toolkit",
            "--collect-all",
            "texture2ddecoder",
            "--collect-all",
            "etcpak",
            "--collect-all",
            "astc_encoder",
            "--collect-all",
            "tpk_ar",
            # astc_encoder imports archspec at load time and needs its CPU database files.
            "--collect-all",
            "archspec",
            *[item for module in UNUSED_QT_MODULES for item in ("--exclude-module", module)],
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(ROOT / "build"),
            "--specpath",
            str(ROOT / "build"),
            str(ROOT / "scripts" / "launcher.py"),
        ]
    )


if __name__ == "__main__":
    main()
