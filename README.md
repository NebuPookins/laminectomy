# laminectomy

Find Spine rigs in a Unity project or a built Unity game, and browse them.

- **Editor projects**: raw `.atlas` files with their `.json` / `.skel` and PNG
  pages next to them under `Assets/`.
- **Built games**: Spine data pulled out of `*.assets`, `level*` files and
  AssetBundles under `StreamingAssets/`, with their textures.

Each rig is shown with its skeleton, a fixed atlas and premultiplied PNG pages,
played by spine-player.

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

On Linux, building from source also needs the PyGObject build dependencies
(`libgirepository1.0-dev libcairo2-dev pkg-config` on Debian/Ubuntu).

## Use the window

The window uses the operating system's web view: WebView2 on Windows, WebKit on
macOS, and WebKitGTK on Linux. On Linux, install WebKitGTK first (GTK3 comes with it):
`webkit2gtk-4.1` (Arch), `gir1.2-webkit2-4.1` (Debian/Ubuntu), `webkit2gtk4.1` (Fedora).
The Linux executable does not bundle GTK or WebKit. Without them, use the command line below.

```sh
.venv/bin/laminectomy                       # opens the window; click "Choose game folder…"
.venv/bin/laminectomy /path/to/game         # opens the window and loads that folder straight away
```

Pick the folder that contains the game's `*_Data` directory, or a Unity project's
folder (the one with `Assets/`). Extraction runs in memory. Nothing is written to
disk, and the rigs appear in the embedded viewer as soon as they are ready.

## Use the command line

```sh
# Write a viewer folder to disk, without opening the window
.venv/bin/laminectomy build /path/to/game -o ./out

# Serve a viewer folder written by build, on http://127.0.0.1:8765/
.venv/bin/laminectomy serve ./out
```

## Logging

Everything the app does is logged to stderr, including the full traceback for
any failure. Failed files are listed in the log and in the window, and the rest
of the folder still loads. For more detail, run with:

```sh
LAMINECTOMY_LOG=DEBUG .venv/bin/laminectomy /path/to/game
```

## What the viewer folder contains

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
- Skeletons with no matching atlas are skipped and counted.
- The viewer needs internet access to load spine-player from the CDN.
- Spine data here is 4.1.x. The viewer pins spine-player 4.1.56 to match.

## Tests

```sh
.venv/bin/pytest
```
