"""
Via deduplication for PCB export.

Removes duplicate vias at the same (x, y) coordinates to avoid KiCad DRC
holes_co_located violations.
"""

from dataclasses import dataclass
from typing import List

from temper_placer.io.export_types import TraceVia


@dataclass(frozen=True)
class ViaKey:
    """Unique identifier for via position (ignores net)."""
    x_mm: float
    y_mm: float

    @classmethod
    def from_via(cls, via: TraceVia, tolerance_mm: float = 0.001) -> "ViaKey":
        """Round to tolerance to handle floating point errors."""
        return cls(
            x_mm=round(via.position[0] / tolerance_mm) * tolerance_mm,
            y_mm=round(via.position[1] / tolerance_mm) * tolerance_mm
        )


def deduplicate_vias(vias: List[TraceVia], tolerance_mm: float = 0.001) -> List[TraceVia]:
    """Remove duplicate vias at same (x, y) location.

    Strategy: Keep first via for each position, discard duplicates.
    Nets sharing a via position is OKAY electrically (they're connected).

    Args:
        vias: List of TraceVia objects from routing
        tolerance_mm: Position tolerance for considering vias identical

    Returns:
        Deduplicated list of vias
    """
    seen: dict[ViaKey, TraceVia] = {}

    for via in vias:
        key = ViaKey.from_via(via, tolerance_mm)
        if key not in seen:
            seen[key] = via

    return list(seen.values())
