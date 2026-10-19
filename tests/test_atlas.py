from laminectomy.atlas import page_names, parse, prepare

NEW_FORMAT = """page.png
size: 200, 100
filter: Linear, Linear
Face
bounds: 20, 10, 40, 20
offsets: 2, 4, 30, 24
rotate: false
"""

OLD_FORMAT = """page.png
  size: 200, 100
  format: RGBA8888
Eye
  rotate: false
  xy: 4, 6
  size: 40, 20
  orig: 40, 20
  offset: 0, 0
  index: -1
"""


def region_fields(text: str, region: str) -> dict[str, str]:
    (page,) = parse(text).pages
    (match,) = (r for r in page.regions if r.name == region)
    return {f.key: f.value for f in match.fields}


def header_keys(text: str) -> list[str]:
    (page,) = parse(text).pages
    return [f.key for f in page.header]


def test_new_format_regions_are_scaled_with_the_page():
    fitted = prepare(NEW_FORMAT, {"page.png": (100, 50)})

    fields = region_fields(fitted, "Face")
    assert fields["bounds"] == "10, 5, 20, 10"
    assert fields["offsets"] == "1, 2, 15, 12"


def test_old_format_regions_are_scaled_with_the_page():
    fitted = prepare(OLD_FORMAT, {"page.png": (100, 50)})

    fields = region_fields(fitted, "Eye")
    assert fields["xy"] == "2, 3"
    assert fields["size"] == "20, 10"
    assert fields["orig"] == "20, 10"
    assert fields["offset"] == "0, 0"


def test_page_size_is_replaced_with_the_real_texture_size():
    fitted = prepare(NEW_FORMAT, {"page.png": (100, 50)})

    assert "size: 100, 50" in fitted


def test_matching_size_leaves_regions_alone():
    text = NEW_FORMAT.replace("size: 200, 100", "size: 100, 50")
    fitted = prepare(text, {"page.png": (100, 50)})

    assert region_fields(fitted, "Face") == region_fields(text, "Face")


def test_preparing_twice_changes_nothing():
    once = prepare(NEW_FORMAT, {"page.png": (100, 50)})
    twice = prepare(once, {"page.png": (100, 50)})

    assert twice == once


def test_pma_flag_goes_right_after_size_exactly_once():
    fitted = prepare(NEW_FORMAT, {"page.png": (200, 100)})

    keys = header_keys(fitted)
    assert keys[:2] == ["size", "pma"]
    assert keys.count("pma") == 1


def test_original_indentation_is_kept_on_rewritten_lines():
    text = "page.png\n\tsize: 200, 100\n\tfilter: Linear, Linear\nFace\n\tbounds: 20, 10, 40, 20\n"

    lines = prepare(text, {"page.png": (100, 50)}).splitlines()

    assert "\tsize: 100, 50" in lines
    assert "\tbounds: 10, 5, 20, 10" in lines
    assert "pma: true" in lines


def test_pages_without_a_known_texture_keep_their_size():
    fitted = prepare(NEW_FORMAT, {})

    assert "size: 200, 100" in fitted
    assert region_fields(fitted, "Face")["bounds"] == "20, 10, 40, 20"


def test_pages_stay_separated_by_a_blank_line():
    text = NEW_FORMAT + "second.png\nsize: 8, 8\nOne\nbounds: 0, 0, 4, 4\n"

    lines = prepare(text, {}).splitlines()

    assert "" in lines
    assert lines.index("second.png") == lines.index("") + 1


def test_page_names_lists_every_page():
    text = NEW_FORMAT + "second.png\nsize: 8, 8\nOne\nbounds: 0, 0, 4, 4\n"

    assert page_names(text) == ("page.png", "second.png")
