"""Serve an in-memory viewer file set on 127.0.0.1, from a background thread."""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

logger = logging.getLogger(__name__)

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".json": "application/json",
    ".png": "image/png",
    ".atlas": "text/plain; charset=utf-8",
}


def content_type(path: str) -> str:
    dot = path.rfind(".")
    return _CONTENT_TYPES.get(path[dot:].lower() if dot != -1 else "", "application/octet-stream")


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        path = unquote(urlsplit(self.path).path).lstrip("/") or "index.html"
        body = self.server.files.get(path)
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type(path))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        logger.debug("%s %s", self.address_string(), format % args)


class _Server(ThreadingHTTPServer):
    def __init__(self, files: Mapping[str, bytes]) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.files = files


@dataclass
class ViewerServer:
    url: str
    _server: _Server
    _thread: threading.Thread

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def start_viewer(files: Mapping[str, bytes]) -> ViewerServer:
    server = _Server(files)
    thread = threading.Thread(target=server.serve_forever, name="laminectomy-viewer", daemon=True)
    thread.start()
    port = server.server_address[1]
    return ViewerServer(url=f"http://127.0.0.1:{port}/", _server=server, _thread=thread)
