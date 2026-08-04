"""
KiCad PCB writer for exporting optimized placements — re-export hub.

All implementation lives in ``io._write_*`` internal modules.
This file exposes the public API for backward compatibility.

Wave 4, Phase 3, candidate 4: the JSON helpers delegate to the
``temper-io-types`` ``kicad_write`` kernels; the ``_write_*`` modules are
delegation shims over the same kernels.
"""

from __future__ import annotations

from temper_io_types import placements_from_json, placements_to_json

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
