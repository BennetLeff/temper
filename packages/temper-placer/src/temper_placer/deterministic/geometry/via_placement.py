"""Via placement with mask clearance (deterministic router helper).

The pure compute is implemented in Rust in the ``temper-geometry`` crate
(Wave 4 **Phase 5, first slice** — deterministic leaf stages). This module
keeps the pre-migration public API unchanged and delegates; ``PadInfo``
remains a plain Python dataclass (the boundary crosses flattened fields).

Bit-exactness: ``distance`` pins ``math.sqrt(dx ** 2 + dy ** 2)`` with
``** 2`` as libm ``pow`` (NOT ``x * x``) and correctly-rounded IEEE
``sqrt``; the spiral search keeps the oracle's deterministic radius/angle
order and the strict ``< required`` validity predicate. Verified by
``tests/deterministic/test_via_placement_rust_differential.py`` (oracle:
``tests/deterministic/_via_placement_py_oracle.py``) and the PBT suite
``tests/deterministic/test_via_placement_pbt.py``; the structural proof is
in ``packages/temper-geometry/VERIFICATION.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

import temper_geometry as _tg


@dataclass
class PadInfo:
    position: tuple[float, float]
    radius: float
    mask_expansion: float


def distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return _tg.via_distance(p1[0], p1[1], p2[0], p2[1])


def _flatten(pads: list[PadInfo]) -> list[float]:
    out = []
    for pad in pads:
        out.extend([pad.position[0], pad.position[1], pad.radius, pad.mask_expansion])
    return out


def is_via_position_valid(
    pos: tuple[float, float],
    pads: list[PadInfo],
    via_mask_radius: float,
    min_clearance: float = 0.1,
) -> bool:
    """Check if via at pos has sufficient mask clearance to all pads."""
    return _tg.is_via_position_valid(pos[0], pos[1], _flatten(pads), via_mask_radius, min_clearance)


def place_via_with_clearance(
    target_pos: tuple[float, float],
    pads: list[PadInfo],
    via_mask_radius: float,
    min_clearance: float = 0.1,
    max_search_radius: float = 2.0,
) -> tuple[float, float] | None:
    """Find valid via position near target, respecting mask clearances."""
    return _tg.place_via_with_clearance(
        target_pos[0],
        target_pos[1],
        _flatten(pads),
        via_mask_radius,
        min_clearance,
        max_search_radius,
    )


__all__ = ["PadInfo", "distance", "is_via_position_valid", "place_via_with_clearance"]
