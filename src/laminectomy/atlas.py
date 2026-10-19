"""Spine atlas parsing and repair.

Unity downsizes large textures on import, so the page size written in a Spine
atlas can differ from the PNG that was exported. Region coordinates have to be
scaled to the real page, and each page needs the premultiplied-alpha flag.

Everything here is pure: atlas text in, atlas text out.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

# Region fields measured in texture pixels. Values come in (x, y) or (w, h)
# pairs, or (x, y, w, h) quads, so even indices scale by x and odd by y.
SCALED_REGION_KEYS = frozenset({"bounds", "offsets", "xy", "offset", "orig", "size"})

_KEY_LINE = re.compile(r"^\s*([A-Za-z]+)\s*:\s*(.*)$")


@dataclass(frozen=True)
class Field:
    key: str
    value: str
    # Leading whitespace of the original line. Spine's parser is sensitive to it,
    # so it is kept as written instead of being normalized.
    indent: str = "\t"


@dataclass(frozen=True)
class Region:
    name: str
    fields: tuple[Field, ...]


@dataclass(frozen=True)
class Page:
    name: str
    header: tuple[Field, ...]
    regions: tuple[Region, ...]


@dataclass(frozen=True)
class Atlas:
    pages: tuple[Page, ...]


def _is_page_name(line: str) -> bool:
    return bool(line) and not line[0].isspace() and line.endswith(".png") and ":" not in line


def _chunk_pages(text: str) -> list[tuple[str, list[str]]]:
    chunks: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if _is_page_name(line):
            chunks.append((line, []))
        elif chunks:
            chunks[-1][1].append(line)
    return chunks


def _parse_page(name: str, lines: list[str]) -> Page:
    header: list[Field] = []
    regions: list[Region] = []
    region_name: str | None = None
    region_fields: list[Field] = []
    for line in lines:
        match = _KEY_LINE.match(line)
        indent = line[: len(line) - len(line.lstrip())]
        if match and region_name is None:
            header.append(Field(match.group(1), match.group(2).strip(), indent))
        elif match:
            region_fields.append(Field(match.group(1), match.group(2).strip(), indent))
        else:
            if region_name is not None:
                regions.append(Region(region_name, tuple(region_fields)))
            region_name = line.strip()
            region_fields = []
    if region_name is not None:
        regions.append(Region(region_name, tuple(region_fields)))
    return Page(name, tuple(header), tuple(regions))


def parse(text: str) -> Atlas:
    return Atlas(tuple(_parse_page(name, lines) for name, lines in _chunk_pages(text)))


def render(atlas: Atlas) -> str:
    out: list[str] = []
    for index, page in enumerate(atlas.pages):
        if index:
            out.append("")  # Spine separates pages with a blank line.
        out.append(page.name)
        out.extend(f"{field.indent}{field.key}: {field.value}" for field in page.header)
        for region in page.regions:
            out.append(region.name)
            out.extend(f"{field.indent}{field.key}: {field.value}" for field in region.fields)
    return "\n".join(out) + "\n"


def page_names(text: str) -> tuple[str, ...]:
    return tuple(name for name, _ in _chunk_pages(text))


def _parse_size(value: str) -> tuple[int, int]:
    width, height = (int(part) for part in value.split(","))
    return width, height


def _scale_values(values: list[int], fx: float, fy: float) -> list[int]:
    return [round(v * (fx if i % 2 == 0 else fy)) for i, v in enumerate(values)]


def _scale_field(field: Field, fx: float, fy: float) -> Field:
    if field.key not in SCALED_REGION_KEYS:
        return field
    values = [int(part) for part in field.value.split(",")]
    scaled = _scale_values(values, fx, fy)
    return Field(field.key, ", ".join(str(v) for v in scaled), field.indent)


def fit_page(page: Page, actual: tuple[int, int]) -> Page:
    """Rescale a page and its regions so they match the real texture size."""
    size_field = next((f for f in page.header if f.key == "size"), None)
    if size_field is None:
        return page
    declared = _parse_size(size_field.value)
    if declared == actual:
        return page
    fx, fy = actual[0] / declared[0], actual[1] / declared[1]
    header = tuple(
        Field("size", f"{actual[0]}, {actual[1]}", f.indent) if f is size_field else f
        for f in page.header
    )
    regions = tuple(
        Region(region.name, tuple(_scale_field(f, fx, fy) for f in region.fields))
        for region in page.regions
    )
    return Page(page.name, header, regions)


def ensure_pma(page: Page) -> Page:
    """Mark the page premultiplied, placed right after its size line."""
    if any(f.key == "pma" for f in page.header):
        return page
    size_index = next((i for i, f in enumerate(page.header) if f.key == "size"), None)
    # The unindented form is what Unity-exported atlases that render correctly use.
    marker = Field("pma", "true", "")
    index = 0 if size_index is None else size_index + 1
    header = page.header[:index] + (marker,) + page.header[index:]
    return Page(page.name, header, page.regions)


def prepare(text: str, actual_sizes: Mapping[str, tuple[int, int]]) -> str:
    """Fit every page with a known texture size and mark it premultiplied."""
    atlas = parse(text)
    pages = tuple(
        ensure_pma(fit_page(page, actual_sizes[page.name]) if page.name in actual_sizes else page)
        for page in atlas.pages
    )
    return render(Atlas(pages))
