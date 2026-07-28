"""Integer tick quantizers used by the finite-resolution simulator."""

from __future__ import annotations

import math
from typing import Literal

Quantizer = Literal["floor", "nearest", "ceiling"]


def quantize(time: float, delta: float, method: Quantizer = "floor") -> int:
    """Map a non-negative continuous timestamp to a non-negative integer tick."""
    if delta <= 0:
        raise ValueError("delta must be positive")
    if time < 0:
        raise ValueError("timestamps must be non-negative")
    scaled = time / delta
    if method == "floor":
        tick = math.floor(scaled)
    elif method == "nearest":
        tick = math.floor(scaled + 0.5)
    elif method == "ceiling":
        tick = math.ceil(scaled)
    else:
        raise ValueError(f"unknown quantizer: {method}")
    return max(0, int(tick))
