"""Desktop window: pick a game or project folder, extract it in memory, and view the rigs.

Extraction runs on a worker thread, so the window stays responsive. The result
is served from memory on 127.0.0.1 and shown in an embedded web view, so
nothing is written to disk.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .build import detect_source, load_source, viewer_files, viewer_html
from .logs import configure_logging
from .memory_server import ViewerServer, start_viewer

logger = logging.getLogger(__name__)


class _Loader(QThread):
    progress = Signal(int, int)
    loaded = Signal(object)  # {"files": dict[str, bytes], "count": int, "errors": tuple[str, ...]}
    failed = Signal(str)

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path

    def run(self) -> None:
        try:
            source = detect_source(self._path)
            result = load_source(source, progress=self.progress.emit)
            files = viewer_files(result.rigs, viewer_html())
            listing = json.loads(files["rigs.json"])
            self.loaded.emit({"files": files, "count": len(listing), "errors": result.errors})
        except Exception as exc:
            logger.exception("could not load %s", self._path)
            self.failed.emit(f"{exc}\n\nDetails are in the log (run with LAMINECTOMY_LOG=DEBUG for more).")


class MainWindow(QMainWindow):
    def __init__(self, initial: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Laminectomy")
        self.resize(1200, 820)
        self._viewer: ViewerServer | None = None
        self._loader: _Loader | None = None

        self._choose = QPushButton("Choose game folder…")
        self._path_label = QLabel("No folder selected")
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._status = QLabel(
            "Choose a built game's folder (the one containing *_Data), or a Unity project's folder."
        )
        self._web = QWebEngineView()
        self._web.setVisible(False)

        top = QHBoxLayout()
        top.addWidget(self._choose)
        top.addWidget(self._path_label, 1)

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self._progress)
        layout.addWidget(self._status)
        layout.addWidget(self._web, 1)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self._choose.clicked.connect(self._pick_folder)
        if initial is not None:
            self._open(initial)

    # --- actions -----------------------------------------------------------

    def _pick_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose game folder")
        if chosen:
            self._open(Path(chosen))

    def _open(self, path: Path) -> None:
        if self._loader is not None and self._loader.isRunning():
            return
        self._path_label.setText(str(path))
        self._choose.setEnabled(False)
        self._progress.setRange(0, 0)  # busy until the first file reports
        self._progress.setVisible(True)
        self._status.setText("Reading game data…")

        self._loader = _Loader(path)
        self._loader.progress.connect(self._on_progress)
        self._loader.loaded.connect(self._on_loaded)
        self._loader.failed.connect(self._on_failed)
        self._loader.start()

    # --- loader callbacks (run on the GUI thread) --------------------------

    def _on_progress(self, done: int, total: int) -> None:
        self._progress.setRange(0, total)
        self._progress.setValue(done)
        self._status.setText(f"Extracting: {done} of {total} data files")

    def _on_loaded(self, result: dict) -> None:
        if self._viewer is not None:
            self._viewer.stop()
        self._viewer = start_viewer(result["files"])
        self._web.load(QUrl(self._viewer.url))
        self._web.setVisible(True)
        self._finish_loading()
        errors = result["errors"]
        if result["count"] == 0:
            logger.warning("no viewable Spine rigs found in %s", self._path_label.text())
            self._status.setText(
                "No Spine rigs were found in this folder. Check that it is the game's *_Data folder "
                "or a Unity project. The log shows which files were read."
            )
        else:
            self._status.setText(f"{result['count']} rigs loaded. Nothing was written to disk.")
        if errors:
            self._status.setText(
                f"{result['count']} rigs loaded, but {len(errors)} files had errors. See the log for details."
            )
            QMessageBox.warning(self, "Some files could not be loaded", "\n".join(errors[:20]))

    def _on_failed(self, message: str) -> None:
        self._finish_loading()
        self._status.setText(message)
        QMessageBox.critical(self, "Could not load this folder", message)

    def _finish_loading(self) -> None:
        self._progress.setVisible(False)
        self._choose.setEnabled(True)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self._viewer is not None:
            self._viewer.stop()
        if self._loader is not None:
            self._loader.wait()
        super().closeEvent(event)


# Software rendering avoids the OpenGL setup that failed on some machines
# ("Could not initialize GLX", then SIGABRT). Users can override either setting
# by exporting the variable before starting the app.
_RENDERING_DEFAULTS = {
    "QT_OPENGL": "software",
    # SwiftShader keeps WebGL working in software; --disable-gpu would turn WebGL off
    # and spine-player would refuse to start.
    "QTWEBENGINE_CHROMIUM_FLAGS": "--use-angle=swiftshader --enable-unsafe-swiftshader",
}


def _apply_rendering_defaults() -> None:
    for name, value in _RENDERING_DEFAULTS.items():
        if name in os.environ:
            logger.info("%s is already set to %r; leaving it alone", name, os.environ[name])
        else:
            os.environ[name] = value
            logger.info("%s set to %r for stable rendering", name, value)


def run(initial: Path | None = None) -> int:
    configure_logging()
    _apply_rendering_defaults()
    logger.info("starting window (python %s, platform %s)", sys.version.split()[0], sys.platform)
    app = QApplication([sys.argv[0]])
    window = MainWindow(initial)
    window.show()
    return app.exec()
