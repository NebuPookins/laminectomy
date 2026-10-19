"""Desktop window: pick a game or project folder, extract it in memory, and view the rigs.

The window is a pywebview window that shows launcher.html. That page has the folder
picker and the progress bar, and shows the viewer in an iframe. Both pages are served
from a local in-memory server, so nothing is written to disk.

Python calls into the page with ``evaluate_js``; the page calls Python through
``window.pywebview.api``. The page's function names are listed in launcher.html.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from importlib.resources import files
from pathlib import Path
from typing import Any

import webview
from webview.errors import WebViewException

from .build import detect_source, load_source, viewer_files, viewer_html
from .logs import configure_logging
from .memory_server import ViewerServer, start_viewer

logger = logging.getLogger(__name__)


_LINUX_BACKEND_HELP = """\
Laminectomy could not open its window: no GUI backend was found.
The desktop window needs WebKitGTK. Install it with your package manager:
  Arch:           webkit2gtk-4.1
  Debian/Ubuntu:  gir1.2-webkit2-4.1
  Fedora:         webkit2gtk4.1
Or skip the window: run `laminectomy build FOLDER -o OUT`, then `laminectomy serve OUT`."""


def _launcher_html() -> bytes:
    return (files("laminectomy") / "web" / "launcher.html").read_bytes()


class Launcher:
    """The object the page sees as ``window.pywebview.api``."""

    def __init__(self, server: ViewerServer, launcher_html: bytes) -> None:
        self._server = server
        self._launcher_files: dict[str, bytes] = {"index.html": launcher_html}
        self._window: Any = None
        self._busy = threading.Lock()

    def attach(self, window: Any) -> None:
        self._window = window

    # --- called from the page -----------------------------------------------

    def choose_folder(self) -> str | None:
        chosen = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not chosen:
            logger.info("folder selection cancelled")
            return None
        logger.info("folder chosen: %s", chosen[0])
        self.start_load(chosen[0])
        return chosen[0]

    # --- Python side ----------------------------------------------------------

    def start_load(self, path: str) -> None:
        if not self._busy.acquire(blocking=False):
            logger.warning("ignored a request to load %s: a load is already running", path)
            return
        self._call("onStart", path)
        threading.Thread(target=self._load, args=(path,), name="laminectomy-load", daemon=True).start()

    def _load(self, path: str) -> None:
        try:
            source = detect_source(Path(path))
            result = load_source(source, progress=lambda done, total: self._call("onProgress", done, total))
            viewer = viewer_files(result.rigs, viewer_html())
            listing = json.loads(viewer["rigs.json"])
            served = {f"viewer/{name}": data for name, data in viewer.items()}
            self._server.replace_files({**self._launcher_files, **served})
            self._call("onLoaded", len(listing), len(result.errors))
        except Exception as exc:
            logger.exception("could not load %s", path)
            self._call("onError", f"{exc}. Details are in the log.")
        finally:
            self._busy.release()

    def _call(self, name: str, *args: object) -> None:
        arguments = ", ".join(json.dumps(arg) for arg in args)
        self._window.evaluate_js(f"{name}({arguments})")


def run(initial: Path | None = None) -> int:
    configure_logging()
    logger.info("starting window (python %s, platform %s)", sys.version.split()[0], sys.platform)
    server = start_viewer({"index.html": _launcher_html()})
    launcher = Launcher(server, _launcher_html())
    window = webview.create_window("Laminectomy", url=server.url, js_api=launcher, width=1200, height=820)
    launcher.attach(window)

    def on_started() -> None:
        if initial is not None:
            window.events.loaded.wait()
            launcher.start_load(str(initial))

    try:
        webview.start(on_started)
    except WebViewException:
        logger.exception("pywebview could not start a window (platform %s)", sys.platform)
        if sys.platform.startswith("linux"):
            print(_LINUX_BACKEND_HELP, file=sys.stderr)
        return 1
    finally:
        logger.info("window closed; stopping the viewer server")
        server.stop()
    return 0
