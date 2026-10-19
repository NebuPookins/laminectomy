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
