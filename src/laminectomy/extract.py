"""Find Spine rigs in Unity data and write each one as a self-contained folder.

Two input shapes are supported:

* Built games: serialized ``.assets`` / ``level*`` files and AssetBundles under
  ``StreamingAssets``. Skeletons and atlases are TextAssets, pages are Texture2D.
* Editor projects: raw ``.atlas`` files with their ``.json`` / ``.skel`` and PNG
  pages sitting beside them under ``Assets``.

Every rig is written as ``<out>/rigs/<source>/<rig>/`` with the skeleton, its
atlas, and premultiplied PNG pages.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import UnityPy
from PIL import Image

from .atlas import page_names, prepare
from .pixels import premultiply

_VERSION = re.compile(rb"[34]\.[018]\.\d")
_BUNDLE_MAGICS = (b"UnityFS", b"UnityWe", b"UnityRa")
_SKIPPED_SUFFIXES = (".manifest", ".customManifest")
_PROJECT_SKIPPED_DIRS = frozenset({"Library", "Temp", "Logs", "Packages", "obj"})


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


@dataclass(frozen=True)
class RigEntry:
    """One rig as listed in rigs.json. ``atlas`` is None when no atlas was found."""

    group: str
    source: str
    rig: str
    dir: str
    skel: str
    atlas: str | None
    missing_pages: tuple[str, ...]

    def as_json(self) -> dict[str, Any]:
        return {
            "label": f"{self.source}  ·  {self.rig}",
            "group": self.group,
            "dir": self.dir,
            "skel": self.skel,
            "atlas": self.atlas,
            "missing_pages": list(self.missing_pages),
        }


# --- Unity built data --------------------------------------------------------

def is_unity_bundle(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(7) in _BUNDLE_MAGICS
    except OSError:
        return False


def find_game_sources(data_dir: Path) -> list[Path]:
    """Serialized files and bundles that may hold Spine data."""
    serialized = [
        p
        for p in data_dir.iterdir()
        if p.is_file()
        and (p.suffix == ".assets" or p.name.startswith("level") or p.name == "globalgamemanagers")
    ]
    streaming = data_dir / "StreamingAssets"
    bundles = (
        [
            p
            for p in streaming.rglob("*")
            if p.is_file() and not p.name.endswith(_SKIPPED_SUFFIXES) and is_unity_bundle(p)
        ]
        if streaming.is_dir()
        else []
    )
    return sorted(serialized) + sorted(bundles)


def _classify_skeleton(name: str, raw: bytes) -> str | None:
    if b'"spine"' in raw[:4000]:
        return "json"
    if (name.endswith(".skel") or _VERSION.search(raw[:200])) and len(raw) > 1000:
        return "skel"
    return None


def _skeleton_base(name: str) -> str:
    for suffix in (".skel", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _pick_atlas(base: str, atlases: Mapping[str, str]) -> str | None:
    if f"{base}.atlas" in atlases:
        return f"{base}.atlas"
    return next((name for name in atlases if name.startswith(base)), None)


def _unique_dir(parent: Path, base: str, taken: set[str]) -> Path:
    name = safe(base)
    counter = 2
    while name in taken:
        name = f"{safe(base)}__{counter}"
        counter += 1
    taken.add(name)
    return parent / name


def extract_unity_file(job: tuple[Path, str, Path]) -> list[RigEntry]:
    """Pull every Spine rig out of one serialized file or bundle."""
    path, source, out_rigs = job
    try:
        env = UnityPy.load(str(path))
    except Exception:
        return []

    texts: list[tuple[str, bytes]] = []
    textures_needed: set[str] = set()
    for obj in env.objects:
        if obj.type.name != "TextAsset":
            continue
        data = obj.read()
        raw = data.m_Script.encode("utf-8", "surrogateescape") if isinstance(data.m_Script, str) else bytes(data.m_Script)
        texts.append((data.m_Name, raw))

    atlases = {
        name: raw.decode("utf-8", "surrogateescape") for name, raw in texts if name.endswith(".atlas")
    }
    skeletons: list[tuple[str, str, bytes, str | None]] = []
    for name, raw in texts:
        if name.endswith(".atlas"):
            continue
        kind = _classify_skeleton(name, raw)
        if kind is None:
            continue
        base = _skeleton_base(name)
        atlas_name = _pick_atlas(base, atlases)
        skeletons.append((base, kind, raw, atlas_name))
        if atlas_name:
            textures_needed.update(page[:-4] for page in page_names(atlases[atlas_name]))

    images: dict[str, Image.Image] = {}
    if textures_needed:
        for obj in env.objects:
            if obj.type.name != "Texture2D":
                continue
            data = obj.read()
            if data.m_Name not in textures_needed or data.m_Name in images:
                continue
            try:
                images[data.m_Name] = data.image
            except Exception:
                continue

    out_root = out_rigs.parent
    source_dir = out_rigs / safe(source)
    taken: set[str] = set()
    entries: list[RigEntry] = []
    for base, kind, raw, atlas_name in skeletons:
        dest = _unique_dir(source_dir, base, taken)
        entries.append(
            _write_rig(
                dest=dest,
                out_root=out_root,
                group=_unity_group(source),
                source=source,
                base=base,
                kind=kind,
                skeleton=raw,
                atlas_text=atlases.get(atlas_name) if atlas_name else None,
                pages={name: images[name[:-4]] for name in _atlas_pages(atlases, atlas_name) if name[:-4] in images},
            )
        )
    return entries


def _atlas_pages(atlases: Mapping[str, str], atlas_name: str | None) -> tuple[str, ...]:
    return page_names(atlases[atlas_name]) if atlas_name else ()


def _unity_group(source: str) -> str:
    parts = Path(source).parts
    if parts and parts[0] == "StreamingAssets" and len(parts) > 1:
        return parts[1]
    return parts[0] if parts else source


def _project_group(source: str) -> str:
    parts = Path(source).parts
    if parts and parts[0] == "Assets" and len(parts) > 1:
        return parts[1]
    return parts[0] if parts else source


# --- Editor projects ---------------------------------------------------------

def find_project_atlases(project: Path) -> list[Path]:
    return sorted(
        atlas
        for atlas in project.rglob("*.atlas")
        if not (set(atlas.relative_to(project).parts) & _PROJECT_SKIPPED_DIRS)
    )


def extract_project_atlas(job: tuple[Path, Path, Path]) -> list[RigEntry]:
    """Copy one raw Spine rig (atlas, skeleton and PNG pages) out of an editor project."""
    atlas_path, project, out_rigs = job
    text = atlas_path.read_text(encoding="utf-8", errors="surrogateescape")
    skeleton_path = next(
        (p for p in (atlas_path.with_suffix(".json"), atlas_path.with_suffix(".skel")) if p.is_file()),
        None,
    )
    if skeleton_path is None:
        return []
    kind = "json" if skeleton_path.suffix == ".json" else "skel"
    source = str(atlas_path.relative_to(project).parent / atlas_path.stem)
    pages: dict[str, Image.Image] = {}
    for name in page_names(text):
        page_file = atlas_path.parent / name
        if page_file.is_file():
            pages[name] = Image.open(page_file)
    dest = out_rigs / safe(str(atlas_path.relative_to(project).parent)) / safe(atlas_path.stem)
    entry = _write_rig(
        dest=dest,
        out_root=out_rigs.parent,
        group=_project_group(source),
        source=source,
        base=atlas_path.stem,
        kind=kind,
        skeleton=skeleton_path.read_bytes(),
        atlas_text=text,
        pages=pages,
    )
    return [entry]


# --- Shared writer -----------------------------------------------------------

def _write_rig(
    *,
    dest: Path,
    out_root: Path,
    group: str,
    source: str,
    base: str,
    kind: str,
    skeleton: bytes,
    atlas_text: str | None,
    pages: Mapping[str, Image.Image],
) -> RigEntry:
    dest.mkdir(parents=True, exist_ok=True)
    ext = "json" if kind == "json" else "skel"
    skel_name = f"{safe(base)}.{ext}"
    (dest / skel_name).write_bytes(skeleton)
    atlas_name: str | None = None
    missing: tuple[str, ...] = ()
    if atlas_text is not None:
        sizes = {name: image.size for name, image in pages.items()}
        (dest / f"{safe(base)}.atlas").write_text(prepare(atlas_text, sizes), encoding="utf-8")
        atlas_name = f"{safe(base)}.atlas"
        for name, image in pages.items():
            premultiply(image).save(dest / name)
        missing = tuple(name for name in page_names(atlas_text) if name not in pages)
    return RigEntry(
        group=group,
        source=source,
        rig=base,
        dir=dest.relative_to(out_root).as_posix(),
        skel=skel_name,
        atlas=atlas_name,
        missing_pages=missing,
    )
