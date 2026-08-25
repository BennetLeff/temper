"""Internal: trace/via route writing and stripping functions.

kiutils-free (Wave 4 Phase 3, formats/IO): board I/O goes through the
Rust parse engine's text path — ``extract_net_map_from_text_py`` reads
net name→index, ``strip_trace_items_py`` removes trace items from the
tree, ``segment_sexpr_py`` / ``via_sexpr_py`` construct per-item
s-expressions, and ``append_items_to_board_py`` inserts them into the
KiNode tree and serializes back to text.

The deterministic emission keys, stable tstamp derivation, and net-index
resolution are Rust kernels (unchanged). The emission order (sorted by
total keys) is preserved.
"""

from __future__ import annotations

from pathlib import Path

import temper_design_bundle_python as _tdb
from temper_io_types import kicad_write_geometry as _GEOM

from temper_placer.core.board import LAYER_NAME_TO_IDX, STANDARD_LAYER_ORDER
from temper_placer.io._write_types import StrippingResult, WriteResult

_UNRANKED_LAYER = len(STANDARD_LAYER_ORDER)


def _stable_tstamp(kind: str, key: tuple) -> str:
    """A reproducible KiCad object UUID derived from the object's own identity.

    See the pre-migration docstring for the uniqueness/reproducibility
    argument. The sha256 + RFC 4122 v4 derivation lives in Rust
    (``stable_tstamp_py``).
    """
    return _GEOM.stable_tstamp_py(kind, key)


def _resolve_net_index(net: object, net_name_to_index: dict[str, int]) -> int:
    """Board net index actually written for ``net`` (0 when unknown)."""
    return _GEOM.resolve_net_index_py(net, net_name_to_index)


def _trace_emission_key(route: object, net_name_to_index: dict[str, int]) -> tuple:
    """Total order over ``Trace`` objects for deterministic emission."""
    return _GEOM.trace_emission_key_py(route, net_name_to_index, LAYER_NAME_TO_IDX, _UNRANKED_LAYER)


def _via_emission_key(via: object, net_name_to_index: dict[str, int]) -> tuple:
    """Total order over ``Via`` objects for deterministic emission."""
    return _GEOM.via_emission_key_py(via, net_name_to_index)


def strip_routing(
    input_pcb: Path,
    output_pcb: Path,
    keep_zones: bool = True,
    keep_fills: bool = False,
) -> StrippingResult:
    """
    Remove traces and vias from a KiCad PCB file while preserving components and netlist.

    See the pre-migration docstring for full details on what is removed/kept.
    """
    warnings: list[str] = []

    content = Path(input_pcb).read_text(encoding="utf-8")

    # Count components for verification
    footprints = _tdb.parse_engine.extract_footprint_info_py(content)
    components_preserved = len(footprints)

    text, traces_removed, vias_removed, zones_removed = _tdb.parse_engine.strip_trace_items_py(
        content, keep_zones, keep_fills
    )

    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    output_pcb.write_text(text, encoding="utf-8")

    return StrippingResult(
        output_path=output_pcb,
        traces_removed=traces_removed,
        vias_removed=vias_removed,
        zones_removed=zones_removed,
        components_preserved=components_preserved,
        warnings=warnings,
    )


def strip_routing_preserve_nets(
    input_pcb: Path,
    output_pcb: Path,
) -> StrippingResult:
    """
    Strip routing with net assignment verification.

    Verifies net assignments are preserved after stripping by re-parsing
    the output and comparing pad→net mappings.
    """
    content = Path(input_pcb).read_text(encoding="utf-8")

    # Capture net assignments from input using the Rust parse engine
    parse_result = _tdb.parse_engine.parse_kicad_pcb(content, normalize=False)
    input_net_assignments: dict[str, dict[str, str]] = {}
    for pad in parse_result.pads:
        comp_ref = pad.component_ref if pad.component_ref else None
        if comp_ref:
            if comp_ref not in input_net_assignments:
                input_net_assignments[comp_ref] = {}
            net_name = pad.net if pad.net else ""
            input_net_assignments[comp_ref][pad.number] = net_name

    # Strip routing
    result = strip_routing(input_pcb, output_pcb, keep_zones=True, keep_fills=False)

    # Verify net assignments in output
    out_content = Path(output_pcb).read_text(encoding="utf-8")
    out_parse = _tdb.parse_engine.parse_kicad_pcb(out_content, normalize=False)

    for pad in out_parse.pads:
        comp_ref = pad.component_ref if pad.component_ref else None
        if comp_ref and comp_ref in input_net_assignments:
            pad_num = pad.number
            expected_net = input_net_assignments[comp_ref].get(pad_num)
            actual_net = pad.net if pad.net else None
            if expected_net == actual_net:
                continue
            if expected_net and actual_net != expected_net:
                result.warnings.append(
                    f"Net assignment mismatch for {comp_ref} pad {pad_num}: expected {expected_net}, got {actual_net}"
                )

    return result


def write_routes_to_pcb(
    template_pcb: Path,
    output_pcb: Path,
    routes: frozenset,
    vias: frozenset | None = None,
    net_name_to_index: dict[str, int] | None = None,
    clear_existing: bool = False,
) -> WriteResult:
    """
    Add deterministic routes (traces) and vias to a KiCad PCB file.

    See the pre-migration docstring for the emission-order rationale
    (sorted by total keys; PYTHONHASHSEED-independent).

    Args:
        template_pcb: Path to the template .kicad_pcb file.
        output_pcb: Path for the output .kicad_pcb file.
        routes: Unordered set of Trace objects from BoardState.routes.
        vias: Unordered set of Via objects from BoardState.vias.
        net_name_to_index: Optional map of net name → net index.
        clear_existing: If True, remove all existing traces before adding new ones.
    """
    warnings: list[str] = []
    traces_added = 0
    traces_skipped = 0
    vias_added = 0

    content = Path(template_pcb).read_text(encoding="utf-8")

    if net_name_to_index is None:
        net_name_to_index = _tdb.parse_engine.extract_net_map_from_text_py(content)

    if clear_existing:
        content, _, _, _ = _tdb.parse_engine.strip_trace_items_py(content, True, True)
        warnings.append("Cleared existing trace items")

    item_sexprs: list = []

    # Add routes as Segment objects, in canonical order
    keyed_routes = sorted(
        ((_trace_emission_key(r, net_name_to_index), r) for r in routes),
        key=lambda pair: pair[0],
    )
    for route_key, route in keyed_routes:
        net_index = _resolve_net_index(route.net, net_name_to_index)
        if route.net and route.net not in net_name_to_index:
            warnings.append(f"Net '{route.net}' not found in board, using index 0")

        try:
            item_sexprs.append(
                _GEOM.segment_sexpr_py(
                    route.start[0],
                    route.start[1],
                    route.end[0],
                    route.end[1],
                    route.width,
                    route.layer,
                    net_index,
                    _stable_tstamp("segment", route_key),
                )
            )
            traces_added += 1
        except Exception as e:
            warnings.append(f"Failed to add trace {route.start} → {route.end}: {e}")
            traces_skipped += 1

    # Add vias if provided
    if vias:
        keyed_vias = sorted(
            ((_via_emission_key(v, net_name_to_index), v) for v in vias),
            key=lambda pair: pair[0],
        )
        for via_key, via in keyed_vias:
            net_index = _resolve_net_index(via.net, net_name_to_index)

            try:
                item_sexprs.append(
                    _GEOM.via_sexpr_py(
                        via.position[0],
                        via.position[1],
                        via.width,
                        via.drill,
                        list(via.layers),
                        net_index,
                        _stable_tstamp("via", via_key),
                    )
                )
                vias_added += 1
            except Exception as e:
                warnings.append(f"Failed to add via at {via.position}: {e}")

    result_text = _tdb.parse_engine.append_items_to_board_py(content, item_sexprs)

    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    output_pcb.write_text(result_text, encoding="utf-8")

    return WriteResult(
        output_path=output_pcb,
        components_updated=traces_added,
        components_skipped=traces_skipped,
        warnings=warnings,
    )


def get_routing_statistics(pcb_path: Path) -> dict[str, int]:
    """
    Get statistics about routing in a PCB file.
    """
    content = Path(pcb_path).read_text(encoding="utf-8")
    parse_result = _tdb.parse_engine.parse_kicad_pcb(content, normalize=False)

    trace_count = len(parse_result.traces)
    via_count = len(parse_result.vias)

    # Count zones and components from the raw board. `parse_kicad_document`
    # is pure-Rust (its RawBoard is not FromPyObject), so the extension
    # exposes this counting wrapper instead of the parser itself.
    zones, footprints, nets = _tdb.parse_engine.count_raw_board_items_py(content)

    return {
        "traces": trace_count,
        "vias": via_count,
        "zones": zones,
        "components": footprints,
        "nets": nets,
    }
