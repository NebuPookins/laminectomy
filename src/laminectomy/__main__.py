"""Command line entry point.

    laminectomy [FOLDER]          open the desktop window (FOLDER is optional)
    laminectomy build FOLDER -o OUT   write a viewer folder without the window
    laminectomy serve OUT             serve a viewer folder written by build
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .build import build
from .logs import configure_logging
from .serve import serve

_COMMANDS = {"build", "serve"}


def _cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="laminectomy")
    commands = parser.add_subparsers(dest="command", required=True)

    build_cmd = commands.add_parser("build", help="write a viewer folder without opening the window")
    build_cmd.add_argument("source", type=Path, help="Unity project folder, or built game folder (containing *_Data)")
    build_cmd.add_argument("-o", "--out", type=Path, required=True, help="folder to write the viewer into")
    build_cmd.add_argument("-j", "--workers", type=int, default=os.cpu_count() or 4, help="parallel workers")

    serve_cmd = commands.add_parser("serve", help="serve a viewer folder written by build")
    serve_cmd.add_argument("out", type=Path)
    serve_cmd.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)
    if args.command == "serve":
        serve(args.out.resolve(), args.port)
        return
    summary = build(args.source, args.out, args.workers)
    print(
        f"Built {summary.rigs} rigs from a {summary.mode} into {summary.out}"
        f" ({summary.without_atlas} skeletons had no atlas and were skipped,"
        f" {summary.errors} errors; see the log above)"
    )


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in _COMMANDS | {"-h", "--help"}:
        _cli(args)
        return
    # Imported here so the command line works without a GUI toolkit installed.
    from .gui import run

    initial = Path(args[0]) if args else None
    raise SystemExit(run(initial))


if __name__ == "__main__":
    main()
