"""Internal: zone output functions and net name mapping.

Delegation shim over ``temper-io-types``' ``kicad_write_geometry`` kernels:
the net-name → index map build and the zones writer's index resolution. The
kiutils board I/O stays here (KiCad-format boundary); note the zone ``tstamp``
is still ``uuid.uuid4()`` in the pre-migration code and is deliberately NOT
determinized here — that would be a behaviour change no bit-identical
differential could pin (see ``kicad_write_geometry.rs``'s module docstring).
"""

from __future__ import annotations

from pathlib import Path

from kiutils.board import Board as KiBoard
from temper_io_types import kicad_write_geometry as _GEOM

from temper_placer.io._write_types import WriteResult
from temper_placer.io.kicad_exporter import _validate_4_layer_output


def _net_index_map_from_nets(nets) -> dict[str, int]:
    """Build a ``{net.name: net.number}`` dict from a board's ``nets`` list.

    ``hasattr(net, "name") and hasattr(net, "number")`` guards skip net objects
    missing either attribute; duplicate names resolve last-wins (dict
    insertion overwrites in place).
    """
    return _GEOM.build_net_name_to_index_map_py(nets)


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
        net_map = _net_index_map_from_nets(ki_board.nets)

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

        net_index = _GEOM.resolve_net_index_default_py(net_name, net_name_to_index)

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
