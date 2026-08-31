"""Internal: zone output functions and net name mapping.

kiutils-free (Wave 4 Phase 3, formats/IO): board I/O goes through the
Rust parse engine's text path — ``extract_net_map_from_text_py`` reads
the net name → index map, ``zone_sexpr_py`` constructs each zone's
s-expression content, and ``append_items_to_board_py`` inserts the
items into the KiNode tree and serializes back to text. No kiutils
``Board`` object is loaded or mutated.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import temper_design_bundle_python as _tdb
from temper_io_types import kicad_write_geometry as _GEOM

from temper_placer.io._write_types import WriteResult


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
    content = Path(pcb_path).read_text(encoding="utf-8")
    return _tdb.parse_engine.extract_net_map_from_text_py(content)


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
    warnings: list[str] = []
    zones_added = 0

    content = Path(template_pcb).read_text(encoding="utf-8")

    if net_name_to_index is None:
        net_name_to_index = _tdb.parse_engine.extract_net_map_from_text_py(content)

    item_sexprs: list[str] = []

    for zone_def in zones:
        net_name = zone_def["net_name"]
        layer = zone_def["layer"]
        pts = zone_def["polygon_pts"]

        net_index = _GEOM.resolve_net_index_default_py(net_name, net_name_to_index)

        try:
            item_sexprs.append(
                _GEOM.zone_sexpr_py(
                    net_name,
                    net_index,
                    layer,
                    str(uuid.uuid4()),
                    [(p[0], p[1]) for p in pts],
                )
            )
            zones_added += 1
        except Exception as e:
            warnings.append(f"Failed to add zone for {net_name}: {e}")

    result_text = _tdb.parse_engine.append_items_to_board_py(content, item_sexprs)

    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    output_pcb.write_text(result_text, encoding="utf-8")

    return WriteResult(
        output_path=output_pcb,
        components_updated=zones_added,
        components_skipped=0,
        warnings=warnings,
    )
