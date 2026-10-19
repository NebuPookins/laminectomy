"""Command line entry point: ``laminectomy build|serve|run``."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .build import BuildSummary, build
from .serve import serve


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="laminectomy", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    def add_build_args(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("source", type=Path, help="Unity project folder, or built game folder (containing *_Data)")
        sub.add_argument("-o", "--out", type=Path, required=True, help="folder to write the rig viewer into")
        sub.add_argument("-j", "--workers", type=int, default=os.cpu_count() or 4, help="parallel workers")

    build_cmd = commands.add_parser("build", help="extract rigs into a viewer folder")
    add_build_args(build_cmd)

    serve_cmd = commands.add_parser("serve", help="serve an existing viewer folder")
    serve_cmd.add_argument("out", type=Path)
    serve_cmd.add_argument("--port", type=int, default=8765)

    run_cmd = commands.add_parser("run", help="build if needed, then serve")
    add_build_args(run_cmd)
    run_cmd.add_argument("--port", type=int, default=8765)
    run_cmd.add_argument("--rebuild", action="store_true", help="rebuild even if the folder already has rigs")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    if args.command == "serve":
        serve(args.out.resolve(), args.port)
        return
    if args.command == "build":
        _report(build(args.source, args.out, args.workers))
        return
    if args.rebuild or not (args.out / "rigs.json").is_file():
        _report(build(args.source, args.out, args.workers))
    serve(args.out.resolve(), args.port)


def _report(summary: BuildSummary) -> None:
    print(
        f"Built {summary.rigs} rigs from a {summary.mode} into {summary.out}"
        f" ({summary.without_atlas} skeletons had no atlas and were skipped)"
    )


if __name__ == "__main__":
    main()
