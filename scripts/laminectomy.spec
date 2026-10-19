# PyInstaller spec for the laminectomy executable.
#
# Run through scripts/build_binary.py, which sets LAMINECTOMY_EXE_NAME. A spec is used
# instead of plain command-line options so the bundled data files can be filtered.
#
# SPECPATH is provided by PyInstaller and points at this directory.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH).resolve().parent
EXE_NAME = os.environ["LAMINECTOMY_EXE_NAME"]

# Qt bindings pywebview can use as a backend. The app uses the OS web view (WebView2,
# WebKit, or GTK + WebKitGTK), so none of these may end up in the bundle.
EXCLUDED_MODULES = [
    "PySide6", "PyQt5", "PyQt6", "qtpy",
    # pywebview's GTK backend imports these from the system at run time (see below). Naming
    # them keeps PyInstaller's gi hooks, which bundle the whole GTK stack, from running.
    "gi.repository.Gtk", "gi.repository.Gdk", "gi.repository.Gio", "gi.repository.GLib",
    "gi.repository.WebKit2",
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
# gi loads these overrides (e.g. GLib.idle_add) by name at run time, which PyInstaller cannot
# see now that the gi.repository hooks that would have added them are excluded.
hiddenimports = [f"gi.overrides.{name}" for name in ("GLib", "GObject", "Gio", "Gdk", "Gtk", "Pango", "GdkPixbuf")]
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
    excludes=EXCLUDED_MODULES,
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

# On Linux the window is pywebview's GTK backend, which needs PyGObject. Only PyGObject's
# own Python package (gi/, with its _gi*.so extension modules) is bundled. GTK, WebKitGTK,
# GLib and the typelibs must come from the user's system, because
#   - WebKitGTK starts helper processes (WebKitWebProcess, WebKitNetworkProcess) from
#     paths compiled into the system library, and a bundled copy of a different version
#     crashes against them, and
#   - two copies of GLib in one process crash.
# PyInstaller's gi.repository.* hooks would bundle all of it, plus runtime hooks that point
# GI_TYPELIB_PATH, GTK_DATA_PREFIX, GIO_MODULE_DIR, GDK_PIXBUF_MODULE_FILE and XDG_DATA_DIRS
# at the bundle. EXCLUDED_MODULES stops those hooks from running. The filters below are a
# safety net for what still slips in (libraries gi/_gi*.so links against, and the pyi_rth_gi
# runtime hook, which would set GI_TYPELIB_PATH to a directory that no longer exists).
_SYSTEM_LIB_PREFIXES = (
    "libgtk", "libgdk", "libwebkit2gtk", "libjavascriptcore", "libsoup", "libglib",
    "libgobject", "libgio", "libgmodule", "libgthread", "libgirepository", "libcairo",
    "libpango", "libharfbuzz", "libatk", "libatspi", "libepoxy", "libwayland",
    "libxkbcommon", "libfontconfig", "libfreetype", "libgdk_pixbuf", "libffi",
)
_SYSTEM_DATA_DIRS = ("gi_typelibs", "gio_modules", "share", "etc", "lib")
_GI_RUNTIME_HOOKS = ("pyi_rth_gi", "pyi_rth_gio", "pyi_rth_glib", "pyi_rth_gtk", "pyi_rth_gdkpixbuf")


def _is_system_gtk_stack(dest: str) -> bool:
    """Shared libraries, typelibs and GTK/GLib data that the system provides on Linux.
    PyGObject's own files under gi/ are kept."""
    parts = Path(dest).parts
    if not parts or parts[0] == "gi":
        return False
    name = parts[-1]
    # Top-level libraries only: packages such as Pillow bring their own, in *.libs/.
    if len(parts) == 1 and (name.startswith(("libX", "libxcb")) or name.startswith(_SYSTEM_LIB_PREFIXES)):
        return True
    return name.endswith(".typelib") or parts[0] in _SYSTEM_DATA_DIRS


if sys.platform.startswith("linux"):
    print("Linux bundled binaries before filtering:", sorted(dest for dest, _, _ in a.binaries))
    dropped = [entry[0] for entry in a.binaries + a.datas if _is_system_gtk_stack(entry[0])]
    print(f"Dropping {len(dropped)} system GTK/GLib libraries and data files")
    a.binaries = [entry for entry in a.binaries if not _is_system_gtk_stack(entry[0])]
    a.datas = [entry for entry in a.datas if not _is_system_gtk_stack(entry[0])]
    hooks = [entry[0] for entry in a.scripts if entry[0] in _GI_RUNTIME_HOOKS]
    print(f"Dropping {len(hooks)} gi runtime hooks: {hooks}")
    a.scripts = [entry for entry in a.scripts if entry[0] not in _GI_RUNTIME_HOOKS]

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
