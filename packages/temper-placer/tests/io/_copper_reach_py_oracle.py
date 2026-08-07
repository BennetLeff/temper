"""Verbatim pin of `io/real_board.py::_copper_reach_mm` at d7a22b5d16d4db7d47be39f9d7580921eb9e5263.

DO NOT EDIT to make a test pass. This is the reference the Rust is measured
against; editing it inverts the proof.
"""

from __future__ import annotations

import math
from typing import Any

from temper_placer.core.pad_geometry import pad_bounding_radius


def copper_reach_mm(pads: list[dict[str, Any]], rotation_deg: float) -> float:
    """How far this component's copper extends from its own origin.

    Verbatim from real_board.py. `rotation_deg` is accepted and discarded --
    |offset| and the bounding radius are both rotation-invariant.
    """
    del rotation_deg  # provably irrelevant; see docstring
    if not pads:
        return 0.0
    return max(
        math.hypot(*p["offset"])
        + pad_bounding_radius(p["width"], p["height"], p["shape"], p["roundrect_ratio"])
        for p in pads
    )
