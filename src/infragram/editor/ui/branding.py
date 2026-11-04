"""The pangolin mascot, embedded so exported editors work offline."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=3)
def mascot_uri(size: int = 128) -> str:
    """Embed the appropriately sized export instead of the full-resolution master."""
    if size not in (32, 64, 128):
        raise ValueError("Mascot exports are available at 32, 64, and 128 pixels")
    image_type = "png" if size == 32 else "webp"
    artwork = Path(__file__).with_name("assets") / f"mascot-{size}.{image_type}"
    return f"data:image/{image_type};base64," + base64.b64encode(artwork.read_bytes()).decode(
        "ascii"
    )
