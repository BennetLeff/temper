"""
KiCad PCB writer for exporting optimized placements — re-export hub.

All implementation lives in ``io._write_*`` internal modules.
This file exposes the public API for backward compatibility.
"""

from __future__ import annotations

from temper_placer.io._write_board import (
    add_isolation_slots_to_pcb,
    compute_to247_isolation_slots,
    export_placements,
    extract_original_angles,
    state_to_placements,
    validate_output_pcb,
    write_placements_to_pcb,
)
from temper_placer.io._write_modules import (
    add_bounding_boxes_to_pcb,
    add_silkscreen_labels,
)
from temper_placer.io._write_tracks import (
    get_routing_statistics,
    strip_routing,
    strip_routing_preserve_nets,
    write_routes_to_pcb,
)
from temper_placer.io._write_types import (
    IsolationSlotResult,
    PlacementUpdate,
    StrippingResult,
    WriteResult,
)
from temper_placer.io._write_zones import (
    write_zones_to_pcb,
)


def placements_to_json(placements: dict[str, PlacementUpdate]) -> dict:
    """Convert placements to a JSON-serializable dictionary."""
    return {
        ref: {
            "x": update.x,
            "y": update.y,
            "rotation": update.rotation,
        }
        for ref, update in placements.items()
    }


def placements_from_json(data: dict) -> dict[str, PlacementUpdate]:
    """Load placements from a JSON-deserialized dictionary."""
    return {
        ref: PlacementUpdate(
            ref=ref,
            x=float(values["x"]),
            y=float(values["y"]),
            rotation=float(values["rotation"]),
        )
        for ref, values in data.items()
    }


__all__ = [
    # Types
    "IsolationSlotResult",
    "PlacementUpdate",
    "StrippingResult",
    "WriteResult",
    # Board placement
    "export_placements",
    "extract_original_angles",
    "state_to_placements",
    "validate_output_pcb",
    "write_placements_to_pcb",
    # Isolation slots
    "add_isolation_slots_to_pcb",
    "compute_to247_isolation_slots",
    # Module annotations
    "add_bounding_boxes_to_pcb",
    "add_silkscreen_labels",
    # Tracks
    "get_routing_statistics",
    "strip_routing",
    "strip_routing_preserve_nets",
    "write_routes_to_pcb",
    # Zones
    "write_zones_to_pcb",
    # JSON helpers
    "placements_from_json",
    "placements_to_json",
]
