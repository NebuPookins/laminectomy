"""Turn a Unity project or built game into a browsable folder of rigs."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from importlib.resources import files
from multiprocessing import Pool
from pathlib import Path

from .extract import (
    RigEntry,
    extract_project_atlas,
    extract_unity_file,
    find_game_sources,
    find_project_atlases,
)


@dataclass(frozen=True)
class BuildSummary:
    mode: str
    rigs: int
    without_atlas: int
    out: Path


def locate_built_data(path: Path) -> Path | None:
    """The ``*_Data`` folder of a built game, given the game folder or the data folder."""
    if path.name.endswith("_Data") and path.is_dir():
        return path
    candidates = [c for c in path.iterdir() if c.is_dir() and c.name.endswith("_Data")] if path.is_dir() else []
    return candidates[0] if len(candidates) == 1 else None


def detect_mode(path: Path) -> tuple[str, Path]:
    if not path.is_dir():
        raise SystemExit(f"not a folder: {path}")
    if (path / "Assets").is_dir() and (path / "ProjectSettings").is_dir():
        return "project", path
    data = locate_built_data(path)
    if data is not None:
        return "game", data
    raise SystemExit(f"{path} is neither a Unity project (Assets/) nor a built game (*_Data/)")


def _gather(mode: str, root: Path, out_rigs: Path, workers: int) -> list[RigEntry]:
    if mode == "project":
        jobs = [(atlas, root, out_rigs) for atlas in find_project_atlases(root)]
        worker = extract_project_atlas
    else:
        jobs = [(path, path.relative_to(root).as_posix(), out_rigs) for path in find_game_sources(root)]
        worker = extract_unity_file
    if not jobs:
        return []
    with Pool(workers) as pool:
        return [entry for batch in pool.imap_unordered(worker, jobs, chunksize=2) for entry in batch]


def build(input_path: Path, out: Path, workers: int = 4) -> BuildSummary:
    mode, root = detect_mode(input_path.resolve())
    out = out.resolve()
    rigs_dir = out / "rigs"
    if rigs_dir.exists():
        shutil.rmtree(rigs_dir)
    rigs_dir.mkdir(parents=True, exist_ok=True)

    entries = _gather(mode, root, rigs_dir, workers)
    viewable = sorted(
        (e for e in entries if e.atlas is not None),
        key=lambda e: (e.group, e.source, e.rig),
    )
    (out / "rigs.json").write_text(
        json.dumps([e.as_json() for e in viewable], indent=1, ensure_ascii=False), encoding="utf-8"
    )
    (out / "index.html").write_bytes((files("laminectomy") / "web" / "index.html").read_bytes())
    return BuildSummary(
        mode=mode,
        rigs=len(viewable),
        without_atlas=len(entries) - len(viewable),
        out=out,
    )
