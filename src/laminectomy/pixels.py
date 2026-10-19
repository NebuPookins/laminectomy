"""Pixel helpers for texture pages."""

from __future__ import annotations

import numpy as np
from PIL import Image


def premultiply(image: Image.Image) -> Image.Image:
    """Multiply colour channels by alpha, the layout Spine expects for pma pages."""
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)
    rgba[..., :3] *= rgba[..., 3:4] / 255.0
    return Image.fromarray(np.rint(rgba).astype(np.uint8))
