# laminectomy

Find Spine rigs in a Unity project or a built Unity game, extract them, and
browse them in a local web viewer.

- **Editor projects**: raw `.atlas` files with their `.json` / `.skel` and PNG
  pages next to them under `Assets/` are copied out.
- **Built games**: Spine data is pulled out of `*.assets`, `level*` files and
  AssetBundles under `StreamingAssets/`, with their textures.

Each rig gets a folder with its skeleton, a fixed atlas and premultiplied PNG
pages, which spine-player can display directly.

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Use

```sh
# Build the viewer folder from a game (the folder that contains *_Data) or a project (contains Assets/)
.venv/bin/laminectomy build /path/to/game -o ./out

# Serve an existing viewer folder on http://127.0.0.1:8765/
.venv/bin/laminectomy serve ./out

# Build if needed, then serve
.venv/bin/laminectomy run /path/to/game -o ./out
.venv/bin/laminectomy run /path/to/game -o ./out --rebuild   # force a rebuild
```

Then open the URL it prints and choose a rig from the dropdown.

## What the output contains

```
out/
  index.html        viewer page (loads spine-player 4.1.56 from jsDelivr)
  rigs.json         list of rigs the viewer shows
  rigs/<source>/<rig>/
      <rig>.json or <rig>.skel
      <rig>.atlas
      <page>.png    premultiplied texture pages
```

## Notes

- Unity downsizes large textures on import, so the page size written in an
  atlas can differ from the exported PNG. laminectomy rescales each region to
  the real page size, including `bounds`, `offsets`, `orig`, and the older
  `xy` / `size` / `offset` fields, and it marks pages premultiplied. This is
  what stops trimmed pieces (such as faces) from drifting out of place.
- Skeletons with no matching atlas are skipped. The build summary reports how
  many.
- The viewer needs internet access to load spine-player from the CDN.
- Spine data here is 4.1.x. The viewer pins spine-player 4.1.56 to match.

## Tests

```sh
.venv/bin/pytest
```
