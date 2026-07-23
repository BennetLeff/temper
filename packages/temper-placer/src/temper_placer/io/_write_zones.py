"""Internal: zone output functions and net name mapping."""

from __future__ import annotations

from pathlib import Path

from kiutils.board import Board as KiBoard

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

    net_map = {}
    if hasattr(ki_board, "nets") and ki_board.nets:
        for net in ki_board.nets:
            if hasattr(net, "name") and hasattr(net, "number"):
                net_map[net.name] = net.number

    return net_map


def write_zones_to_pcb(
    template_pcb: Path,
    output_pcb: Path,
    zones: list[dict],  # {net_name, layer, polygon_pts}
    net_name_to_index: dict[str, int] | None = None,
) -> WriteResult:
    """
    Add zones to a KiCad PCB file.

    Args:
        template_pcb: Path to template PCB.
        output_pcb: Path to output PCB.
        zones: List of dicts with keys:
               - net_name: str
               - layer: str
               - polygon_pts: list of (x, y) tuples
        net_name_to_index: Optional map of net name -> index.

    Returns:
        WriteResult.
    """
    from kiutils.items.common import Position
    from kiutils.items.zones import Zone, ZonePolygon

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

    for zone_def in zones:
        net_name = zone_def["net_name"]
        layer = zone_def["layer"]
        pts = zone_def["polygon_pts"]

        net_index = net_name_to_index.get(net_name, 0)

        try:
            import uuid

            zone = Zone(
                netName=net_name,
                net=net_index,
                layers=[layer],
                tstamp=str(uuid.uuid4()),
                polygons=[ZonePolygon(coordinates=[Position(p[0], p[1]) for p in pts])],
                # Default fill settings
                minThickness=0.254,
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
