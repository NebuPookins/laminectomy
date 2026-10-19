"""Find Spine rigs in Unity data and return them as in-memory Rig values.

Two input shapes are supported:

* Built games: serialized ``.assets`` / ``level*`` files and AssetBundles under
  ``StreamingAssets``. Skeletons and atlases are TextAssets, pages are Texture2D.
* Editor projects: raw ``.atlas`` files with their ``.json`` / ``.skel`` and PNG
  pages sitting beside them under ``Assets``.

Nothing here touches the output folder. Failures are logged with their traceback
and also returned in ``Extraction.errors``, so the caller can show them. They are
never silently dropped.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import UnityPy
from PIL import Image

from .atlas import page_names, prepare
from .pixels import png_bytes, premultiply

logger = logging.getLogger(__name__)

_VERSION = re.compile(rb"[34]\.[018]\.\d")
_BUNDLE_MAGICS = (b"UnityFS", b"UnityWe", b"UnityRa")
_SKIPPED_SUFFIXES = (".manifest", ".customManifest")
_PROJECT_SKIPPED_DIRS = frozenset({"Library", "Temp", "Logs", "Packages", "obj"})


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


@dataclass(frozen=True)
class Rig:
    """One Spine rig, fully in memory.

    ``key`` is the rig's folder path inside the viewer (``rigs/<source>/<name>``).
    ``pages`` holds premultiplied PNG bytes. ``atlas_text`` is None when no atlas
    was found, and such rigs are not shown in the viewer.
    """

    key: str
    group: str
    source: str
    name: str
    skeleton_name: str
    skeleton: bytes
    atlas_name: str | None
    atlas_text: str | None
    pages: tuple[tuple[str, bytes], ...]
    missing_pages: tuple[str, ...]

    @property
    def viewable(self) -> bool:
        return self.atlas_text is not None


@dataclass(frozen=True)
class Extraction:
    """What one input file produced: its rigs, plus a message for every failure."""

    rigs: tuple[Rig, ...]
    errors: tuple[str, ...]


def unique_key(key: str, taken: set[str]) -> str:
    candidate = key
    counter = 2
    while candidate in taken:
        candidate = f"{key}__{counter}"
        counter += 1
    taken.add(candidate)
    return candidate


def make_rig(
    *,
    key: str,
    group: str,
    source: str,
    name: str,
    kind: str,
    skeleton: bytes,
    atlas_text: str | None,
    pages: Mapping[str, Image.Image],
) -> Rig:
    skeleton_name = f"{safe(name)}.{'json' if kind == 'json' else 'skel'}"
    if atlas_text is None:
        logger.info("rig %s (%s) has no atlas; it will not be viewable", key, source)
        return Rig(key, group, source, name, skeleton_name, skeleton, None, None, (), ())
    sizes = {page: image.size for page, image in pages.items()}
    encoded = tuple((page, png_bytes(premultiply(image))) for page, image in pages.items())
    missing = tuple(page for page in page_names(atlas_text) if page not in pages)
    if missing:
        logger.warning("rig %s (%s) is missing texture pages: %s", key, source, ", ".join(missing))
    logger.debug("rig %s: %d pages, %d skeleton bytes", key, len(encoded), len(skeleton))
    return Rig(
        key=key,
        group=group,
        source=source,
        name=name,
        skeleton_name=skeleton_name,
        skeleton=skeleton,
        atlas_name=f"{safe(name)}.atlas",
        atlas_text=prepare(atlas_text, sizes),
        pages=encoded,
        missing_pages=missing,
    )


# --- Unity built data --------------------------------------------------------

def is_unity_bundle(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(7) in _BUNDLE_MAGICS
    except OSError:
        logger.warning("could not read %s to check whether it is a bundle", path, exc_info=True)
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
    logger.info("found %d serialized files and %d bundles under %s", len(serialized), len(bundles), data_dir)
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


def _unity_group(source: str) -> str:
    parts = Path(source).parts
    if parts and parts[0] == "StreamingAssets" and len(parts) > 1:
        return parts[1]
    return parts[0] if parts else source


def extract_unity_file(job: tuple[Path, str]) -> Extraction:
    """Pull every Spine rig out of one serialized file or bundle."""
    path, source = job
    logger.info("reading %s", source)
    try:
        env = UnityPy.load(str(path))
    except Exception as exc:
        logger.exception("UnityPy could not open %s", source)
        return Extraction((), (f"{source}: could not open the file ({exc!r})",))

    errors: list[str] = []
    texts: list[tuple[str, bytes]] = []
    for obj in env.objects:
        if obj.type.name != "TextAsset":
            continue
        data = obj.read()
        raw = (
            data.m_Script.encode("utf-8", "surrogateescape")
            if isinstance(data.m_Script, str)
            else bytes(data.m_Script)
        )
        texts.append((data.m_Name, raw))

    atlases = {
        name: raw.decode("utf-8", "surrogateescape") for name, raw in texts if name.endswith(".atlas")
    }
    skeletons: list[tuple[str, str, bytes, str | None]] = []
    needed: set[str] = set()
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
            needed.update(page[:-4] for page in page_names(atlases[atlas_name]))

    images: dict[str, Image.Image] = {}
    if needed:
        for obj in env.objects:
            if obj.type.name != "Texture2D":
                continue
            data = obj.read()
            if data.m_Name not in needed or data.m_Name in images:
                continue
            try:
                images[data.m_Name] = data.image
            except Exception as exc:
                logger.exception("could not decode texture %r in %s", data.m_Name, source)
                errors.append(f"{source}: texture {data.m_Name!r} could not be decoded ({exc!r})")

    taken: set[str] = set()
    rigs: list[Rig] = []
    for base, kind, raw, atlas_name in skeletons:
        atlas_text = atlases[atlas_name] if atlas_name else None
        page_images = {
            page: images[page[:-4]]
            for page in (page_names(atlas_text) if atlas_text else ())
            if page[:-4] in images
        }
        rigs.append(
            make_rig(
                key=unique_key(f"rigs/{safe(source)}/{safe(base)}", taken),
                group=_unity_group(source),
                source=source,
                name=base,
                kind=kind,
                skeleton=raw,
                atlas_text=atlas_text,
                pages=page_images,
            )
        )
    logger.info("%s: %d rigs, %d errors", source, len(rigs), len(errors))
    return Extraction(tuple(rigs), tuple(errors))


# --- Editor projects ---------------------------------------------------------

def find_project_atlases(project: Path) -> list[Path]:
    return sorted(
        atlas
        for atlas in project.rglob("*.atlas")
        if not (set(atlas.relative_to(project).parts) & _PROJECT_SKIPPED_DIRS)
    )


def _project_group(source: str) -> str:
    parts = Path(source).parts
    if parts and parts[0] == "Assets" and len(parts) > 1:
        return parts[1]
    return parts[0] if parts else source


def extract_project_atlas(job: tuple[Path, Path]) -> Extraction:
    """Read one raw Spine rig (atlas, skeleton and PNG pages) from an editor project."""
    atlas_path, project = job
    relative = atlas_path.relative_to(project)
    source = relative.with_suffix("").as_posix()
    logger.info("reading %s", source)
    try:
        text = atlas_path.read_text(encoding="utf-8", errors="surrogateescape")
        skeleton_path = next(
            (p for p in (atlas_path.with_suffix(".json"), atlas_path.with_suffix(".skel")) if p.is_file()),
            None,
        )
        if skeleton_path is None:
            logger.warning("%s has no .json or .skel beside it; skipped", source)
            return Extraction((), (f"{source}: no skeleton (.json or .skel) beside the atlas",))
        pages: dict[str, Image.Image] = {}
        for name in page_names(text):
            page_file = atlas_path.parent / name
            if page_file.is_file():
                pages[name] = Image.open(page_file)
            else:
                logger.warning("%s: texture page %s not found", source, name)
        rig = make_rig(
            key=f"rigs/{safe(relative.parent.as_posix())}/{safe(atlas_path.stem)}",
            group=_project_group(source),
            source=source,
            name=atlas_path.stem,
            kind="json" if skeleton_path.suffix == ".json" else "skel",
            skeleton=skeleton_path.read_bytes(),
            atlas_text=text,
            pages=pages,
        )
        return Extraction((rig,), ())
    except Exception as exc:
        logger.exception("could not read project rig %s", source)
        return Extraction((), (f"{source}: could not be read ({exc!r})",))
