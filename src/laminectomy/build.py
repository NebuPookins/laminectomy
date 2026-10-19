"""Load rigs from a Unity project or built game, and turn them into viewer files."""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path
from typing import Any

from .extract import (
    Extraction,
    Rig,
    extract_project_atlas,
    extract_unity_file,
    find_game_sources,
    find_project_atlases,
)
from .logs import configure_logging

logger = logging.getLogger(__name__)

Progress = Callable[[int, int], None]


@dataclass(frozen=True)
class Source:
    mode: str  # "game" or "project"
    root: Path  # the *_Data folder for games, the project folder for projects


def locate_built_data(path: Path) -> Path | None:
    """The ``*_Data`` folder of a built game, given the game folder or the data folder."""
    if path.name.endswith("_Data") and path.is_dir():
        return path
    candidates = [c for c in path.iterdir() if c.is_dir() and c.name.endswith("_Data")] if path.is_dir() else []
    return candidates[0] if len(candidates) == 1 else None


def detect_source(path: Path) -> Source:
    """Work out whether ``path`` is an editor project or a built game, or raise ValueError."""
    if not path.is_dir():
        raise ValueError(f"Not a folder: {path}")
    if (path / "Assets").is_dir() and (path / "ProjectSettings").is_dir():
        return Source("project", path)
    data = locate_built_data(path)
    if data is not None:
        return Source("game", data)
    raise ValueError(f"{path} is neither a Unity project (Assets/) nor a built game (*_Data/)")


def _jobs(source: Source) -> tuple[Callable[[Any], Extraction], list[Any]]:
    if source.mode == "project":
        return extract_project_atlas, [(atlas, source.root) for atlas in find_project_atlases(source.root)]
    return extract_unity_file, [
        (path, path.relative_to(source.root).as_posix()) for path in find_game_sources(source.root)
    ]


def _unique_keys(rigs: Sequence[Rig]) -> tuple[Rig, ...]:
    taken: set[str] = set()
    out: list[Rig] = []
    for rig in rigs:
        key, counter = rig.key, 2
        while key in taken:
            key = f"{rig.key}__{counter}"
            counter += 1
        taken.add(key)
        out.append(rig if key == rig.key else replace(rig, key=key))
    return tuple(out)


@dataclass(frozen=True)
class Loaded:
    """Everything one load produced: the rigs, and a message for every failure."""

    rigs: tuple[Rig, ...]
    errors: tuple[str, ...]


def load_source(source: Source, workers: int | None = None, progress: Progress | None = None) -> Loaded:
    """Extract every rig in memory. Safe to call from a worker thread.

    A file that fails is logged with its traceback and listed in ``errors``. The
    other files still load.
    """
    worker, jobs = _jobs(source)
    logger.info("loading %s folder %s: %d input files", source.mode, source.root, len(jobs))
    if not jobs:
        logger.warning("no input files to read under %s", source.root)
        return Loaded((), ())
    rigs: list[Rig] = []
    errors: list[str] = []
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=workers or os.cpu_count() or 4,
        mp_context=context,
        initializer=configure_logging,  # worker processes start with no logging configured
    ) as pool:
        futures = {pool.submit(worker, job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), start=1):
            try:
                result = future.result()
            except Exception as exc:
                logger.exception("worker failed on %s", futures[future])
                errors.append(f"{futures[future]}: worker failed ({exc!r})")
            else:
                rigs.extend(result.rigs)
                errors.extend(result.errors)
            if progress is not None:
                progress(done, len(futures))
    ordered = _unique_keys(sorted(rigs, key=lambda r: (r.group, r.source, r.name)))
    logger.info("loaded %d rigs (%d viewable) with %d errors", len(ordered), sum(r.viewable for r in ordered), len(errors))
    if not any(r.viewable for r in ordered):
        logger.warning("no viewable Spine rigs found under %s", source.root)
    for message in errors:
        logger.error("%s", message)
    return Loaded(ordered, tuple(errors))


def rig_files(rig: Rig) -> dict[str, bytes]:
    """The files one rig needs in the viewer, keyed by path relative to the viewer root."""
    files_out: dict[str, bytes] = {
        f"{rig.key}/{rig.skeleton_name}": rig.skeleton,
        f"{rig.key}/{rig.atlas_name}": (rig.atlas_text or "").encode("utf-8"),
    }
    files_out.update({f"{rig.key}/{page}": data for page, data in rig.pages})
    return files_out


def viewer_files(rigs: Sequence[Rig], viewer_html: bytes) -> dict[str, bytes]:
    """Every file the viewer needs: the page, its rig list, and the viewable rigs."""
    viewable = [rig for rig in rigs if rig.viewable]
    listing = [
        {
            "label": f"{rig.source}  ·  {rig.name}",
            "group": rig.group,
            "dir": rig.key,
            "skel": rig.skeleton_name,
            "atlas": rig.atlas_name,
            "missing_pages": list(rig.missing_pages),
        }
        for rig in viewable
    ]
    out: dict[str, bytes] = {
        "index.html": viewer_html,
        "rigs.json": json.dumps(listing, indent=1, ensure_ascii=False).encode("utf-8"),
    }
    for rig in viewable:
        out.update(rig_files(rig))
    return out


def viewer_html() -> bytes:
    return (files("laminectomy") / "web" / "index.html").read_bytes()


def write_files(out: Path, entries: Mapping[str, bytes]) -> None:
    """Write a viewer file set into ``out``, replacing any earlier rigs there."""
    rigs_dir = out / "rigs"
    if rigs_dir.exists():
        shutil.rmtree(rigs_dir)
    for relative, data in entries.items():
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


@dataclass(frozen=True)
class BuildSummary:
    mode: str
    rigs: int
    without_atlas: int
    out: Path
    errors: int


def build(input_path: Path, out: Path, workers: int | None = None) -> BuildSummary:
    """Command line path: extract everything and write a viewer folder to ``out``."""
    source = detect_source(input_path.resolve())
    loaded = load_source(source, workers)
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    write_files(out, viewer_files(loaded.rigs, viewer_html()))
    viewable = sum(rig.viewable for rig in loaded.rigs)
    logger.info("wrote %d viewable rigs to %s", viewable, out)
    return BuildSummary(source.mode, viewable, len(loaded.rigs) - viewable, out, len(loaded.errors))
