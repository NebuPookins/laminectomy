import json
from io import BytesIO
from urllib.request import urlopen

import numpy as np
from PIL import Image

from laminectomy.build import detect_source, load_source, viewer_files, write_files
from laminectomy.memory_server import start_viewer

ATLAS = """Hero.png
\tsize: 8, 8
\tfilter: Linear, Linear
Face
\tbounds: 2, 2, 4, 4
\toffsets: 0, 0, 4, 4
\trotate: false
"""


def _make_project(root):
    rig_dir = root / "Assets" / "Spine" / "rig"
    rig_dir.mkdir(parents=True)
    (root / "ProjectSettings").mkdir()
    (rig_dir / "Hero.json").write_text('{"skeleton": {"spine": "4.1.24"}}')
    (rig_dir / "Hero.atlas").write_text(ATLAS)
    # The atlas declares 8x8 but the real page is 4x4, so the rig must be fitted to it.
    page = np.zeros((4, 4, 4), dtype=np.uint8)
    page[..., :3] = 200
    page[..., 3] = 128
    Image.fromarray(page).save(rig_dir / "Hero.png")
    return root


def test_loads_a_project_into_memory(tmp_path):
    project = _make_project(tmp_path / "project")

    rigs = load_source(detect_source(project), workers=1).rigs

    assert len(rigs) == 1
    rig = rigs[0]
    assert rig.key.startswith("rigs/") and rig.key.endswith("/Hero")
    assert rig.viewable
    assert "size: 4, 4" in rig.atlas_text
    (page_name, png) = rig.pages[0]
    assert page_name == "Hero.png"
    decoded = np.asarray(Image.open(BytesIO(png)).convert("RGBA"))
    assert decoded.shape == (4, 4, 4)
    assert decoded[0, 0, 3] == 128
    assert decoded[0, 0, 0] == 100  # 200 premultiplied by alpha 128


def test_viewer_files_list_the_rig_and_include_its_files(tmp_path):
    rigs = load_source(detect_source(_make_project(tmp_path / "project")), workers=1).rigs
    rig = rigs[0]

    files = viewer_files(rigs, b"<html>viewer</html>")

    listing = json.loads(files["rigs.json"])
    assert [entry["dir"] for entry in listing] == [rig.key]
    assert files["index.html"] == b"<html>viewer</html>"
    assert f"{rig.key}/Hero.json" in files
    assert f"{rig.key}/Hero.atlas" in files
    assert f"{rig.key}/Hero.png" in files


def test_memory_server_serves_the_same_bytes(tmp_path):
    rigs = load_source(detect_source(_make_project(tmp_path / "project")), workers=1).rigs
    files = viewer_files(rigs, b"<html>viewer</html>")
    viewer = start_viewer(files)
    try:
        assert urlopen(viewer.url).read() == files["index.html"]
        assert urlopen(viewer.url + "rigs.json").read() == files["rigs.json"]
        rig_key = json.loads(files["rigs.json"])[0]["dir"]
        assert urlopen(f"{viewer.url}{rig_key}/Hero.png").read() == files[f"{rig_key}/Hero.png"]
    finally:
        viewer.stop()


def test_a_broken_rig_is_reported_not_dropped(tmp_path):
    project = tmp_path / "project"
    rig_dir = project / "Assets" / "Spine" / "broken"
    rig_dir.mkdir(parents=True)
    (project / "ProjectSettings").mkdir()
    (rig_dir / "Broken.atlas").write_text(ATLAS)  # no skeleton beside it

    loaded = load_source(detect_source(project), workers=1)

    assert loaded.rigs == ()
    assert any("no skeleton" in message for message in loaded.errors)


def test_disk_output_matches_the_in_memory_files(tmp_path):
    rigs = load_source(detect_source(_make_project(tmp_path / "project")), workers=1).rigs
    files = viewer_files(rigs, b"<html>viewer</html>")
    out = tmp_path / "out"

    write_files(out, files)

    for relative, data in files.items():
        assert (out / relative).read_bytes() == data
