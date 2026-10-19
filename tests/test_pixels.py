import numpy as np
from PIL import Image

from laminectomy.pixels import premultiply


def _single_pixel(rgba: tuple[int, int, int, int]) -> tuple[int, ...]:
    image = Image.new("RGBA", (1, 1), rgba)
    return premultiply(image).getpixel((0, 0))


def test_fully_transparent_pixels_lose_their_colour():
    assert _single_pixel((200, 150, 90, 0)) == (0, 0, 0, 0)


def test_opaque_pixels_are_unchanged():
    assert _single_pixel((200, 150, 90, 255)) == (200, 150, 90, 255)


def test_half_alpha_halves_the_colour():
    assert _single_pixel((200, 100, 50, 128)) == (100, 50, 25, 128)


def test_output_keeps_the_size():
    image = Image.new("RGBA", (3, 2), (10, 20, 30, 40))

    assert np.asarray(premultiply(image)).shape == (2, 3, 4)
