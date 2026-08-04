"""Internal: zone output functions and net name mapping.

Wave 4, Phase 3, candidate 4: net-name-to-index resolution and the zone
specs delegate to the ``temper-io-types`` ``kicad_write`` kernels; this shim
keeps the kiutils board I/O and ``Zone`` item construction.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from kiutils.board import Board as KiBoard
from kiutils.items.common import Position
from kiutils.items.zones import Zone, ZonePolygon
from temper_io_types import (
    net_name_to_index_map,
    write_zones_plan,
)

from temper_placer.io._write_types import WriteResult
from temper_placer.io.kicad_exporter import _validate_4_layer_output


def build_net_name_to_index_map(pcb_path: Path) -> dict[str, int]:
    """Extract net name → index mapping from a KiCad PCB file.

    KiCad uses integer net indices internally, but our Trace objects
    use net names. This function builds the mapping for conversion.
    """
    try:
        ki_board = KiBoard.from_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}") from e

    return net_name_to_index_map(ki_board.nets)


def write_zones_to_pcb(
    template_pcb: Path,
    output_pcb: Path,
    zones: list[dict],  # {net_name, layer, polygon_pts}
    net_name_to_index: dict[str, int] | None = None,
) -> WriteResult:
    """
    Add zones to a KiCad PCB file.

    Net-index resolution and the zone specs run in the ``temper-io-types``
    ``write_zones_plan`` kernel; the kiutils ``Zone`` construction (with the
    pinned per-zone try/except) stays here.
    """
    warnings: list[str] = []
    zones_added = 0

    try:
        ki_board = KiBoard.from_file(str(template_pcb))
    except Exception as e:
        raise ValueError(f"Failed to load template PCB: {e}") from e

    if net_name_to_index is None:
        net_name_to_index = build_net_name_to_index_map(template_pcb)

    if not hasattr(ki_board, "zones") or ki_board.zones is None:
        ki_board.zones = []

    zone_specs, _, warnings = write_zones_plan(zones, net_name_to_index)

    for net_name, net_index, layer, pts, min_thickness in zone_specs:
        try:
            zone = Zone(
                netName=net_name,
                net=net_index,
                layers=[layer],
                tstamp=str(uuid.uuid4()),
                polygons=[ZonePolygon(coordinates=[Position(p[0], p[1]) for p in pts])],
                # Default fill settings
                minThickness=min_thickness,
            )
            ki_board.zones.append(zone)
            zones_added += 1
        except Exception as e:
            warnings.append(f"Failed to add zone for {net_name}: {e}")

    try:
        _validate_4_layer_output(ki_board)
        ki_board.to_file(str(output_pcb))
    except Exception as e:
        raise ValueError(f"Failed to write output PCB: {e}") from e

    return WriteResult(
        output_path=output_pcb,
        components_updated=zones_added,
        components_skipped=0,
        warnings=warnings,
    )
