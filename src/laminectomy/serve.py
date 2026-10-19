"""Serve a built rig folder on localhost."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def serve(root: Path, port: int) -> None:
    if not (root / "rigs.json").is_file():
        raise SystemExit(f"{root} has no rigs.json; run `laminectomy build` first")
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Viewing {root} at http://127.0.0.1:{port}/  (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print()
