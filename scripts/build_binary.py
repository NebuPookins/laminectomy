"""Build a single-file executable for the platform this script runs on.

Output: dist/laminectomy-<os>-<arch>[.exe]. PyInstaller cannot cross-compile,
so run this on each target OS (CI does this). The options live in
scripts/laminectomy.spec, because the bundled data files have to be filtered.
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
    exe_name = f"laminectomy-{platform_tag()}"
    os.environ["LAMINECTOMY_EXE_NAME"] = exe_name
    PyInstaller.__main__.run(
        [
            "--clean",
            "--noconfirm",
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(ROOT / "build"),
            str(ROOT / "scripts" / "laminectomy.spec"),
        ]
    )


if __name__ == "__main__":
    main()
