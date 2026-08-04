"""Internal: trace/via route writing and stripping functions.

Wave 4, Phase 3, candidate 4: the trace-item classification, zone handling
and net-index resolution delegate to the ``temper-io-types`` ``kicad_write``
kernels; this shim keeps the kiutils board I/O and item construction.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from kiutils.board import Board as KiBoard
from kiutils.items.brditems import Segment, Via
from kiutils.items.common import Position

from temper_io_types import (
    get_routing_statistics as _rs_get_routing_statistics,
    strip_routing_plan,
    write_routes_plan,
)

from temper_placer.io._write_types import StrippingResult, WriteResult, _get_footprint_reference
from temper_placer.io.kicad_exporter import _validate_4_layer_output


def strip_routing(
    input_pcb: Path,
    output_pcb: Path,
    keep_zones: bool = True,
    keep_fills: bool = False,
) -> StrippingResult:
    """
    Remove traces and vias from a KiCad PCB file while preserving components and netlist.
    """
    warnings: list[str] = []
    traces_removed = 0
    vias_removed = 0
    zones_removed = 0

    # Load the input PCB
    try:
        ki_board = KiBoard.from_file(str(input_pcb))
    except Exception as e:
        raise ValueError(f"Failed to load input PCB: {e}") from e

    # Count components for verification
    components_preserved = len(ki_board.footprints)

    # Classification + zone decisions run in the temper-io-types kernel.
    traces_removed, vias_removed, zones_removed, keep_indices, clear_fills, warnings = (
        strip_routing_plan(ki_board.traceItems, ki_board.zones, keep_zones, keep_fills)
    )

    # Apply the plan (thin list plumbing).
    if ki_board.traceItems:
        items = ki_board.traceItems
        ki_board.traceItems = [items[i] for i in keep_indices]

    if ki_board.zones:
        if not keep_zones:
            ki_board.zones = []
        elif clear_fills:
            for zone in ki_board.zones:
                # Clear filled polygons (the copper pour)
                if hasattr(zone, "filledPolygons"):
                    zone.filledPolygons = []

    # Ensure output directory exists
    output_pcb.parent.mkdir(parents=True, exist_ok=True)

    # Write the stripped PCB
    try:
        _validate_4_layer_output(ki_board)
        ki_board.to_file(str(output_pcb))
    except Exception as e:
        raise ValueError(f"Failed to write output PCB: {e}") from e

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

    Composition + verification over the kiutils board objects (a
    kiutils-read surface) — kept in the shim; the classification kernel it
    wraps is ``strip_routing_plan`` in Rust.
    """
    # First, capture net assignments from input
    try:
        ki_input = KiBoard.from_file(str(input_pcb))
    except Exception as e:
        raise ValueError(f"Failed to load input PCB: {e}") from e

    input_net_assignments: dict[str, dict[str, str]] = {}  # ref -> {pad_num -> net_name}
    for fp in ki_input.footprints:
        ref = _get_footprint_reference(fp)
        if ref:
            input_net_assignments[ref] = {}
            for pad in fp.pads:
                if pad.net and pad.net.name:
                    input_net_assignments[ref][pad.number or ""] = pad.net.name

    # Strip routing
    result = strip_routing(input_pcb, output_pcb, keep_zones=True, keep_fills=False)

    # Verify net assignments in output
    try:
        ki_output = KiBoard.from_file(str(output_pcb))
    except Exception as e:
        result.warnings.append(f"Failed to verify output: {e}")
        return result

    for fp in ki_output.footprints:
        ref = _get_footprint_reference(fp)
        if ref and ref in input_net_assignments:
            for pad in fp.pads:
                pad_num = pad.number or ""
                expected_net = input_net_assignments[ref].get(pad_num)
                actual_net = pad.net.name if pad.net else None
                if expected_net == actual_net:
                    continue
                if expected_net and actual_net != expected_net:
                    result.warnings.append(
                        f"Net assignment mismatch for {ref} pad {pad_num}: expected {expected_net}, got {actual_net}"
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

    Net-index resolution, per-route warnings and the Segment/Via specs run in
    the ``temper-io-types`` ``write_routes_plan`` kernel; this shim keeps the
    kiutils board I/O and item construction (including the per-item
    try/except that reports construction failures).
    """
    warnings: list[str] = []
    traces_added = 0
    traces_skipped = 0
    vias_added = 0

    # Load the template PCB
    try:
        ki_board = KiBoard.from_file(str(template_pcb))
    except Exception as e:
        raise ValueError(f"Failed to load template PCB: {e}") from e

    original_trace_count = len(ki_board.traceItems) if ki_board.traceItems else 0

    net_map, segment_specs, via_specs, warnings = write_routes_plan(
        ki_board.nets,
        list(routes),
        list(vias) if vias is not None else None,
        net_name_to_index,
        clear_existing,
        original_trace_count,
    )

    # Clear existing traces if requested
    if clear_existing and hasattr(ki_board, "traceItems"):
        ki_board.traceItems = []

    # Initialize traceItems if it doesn't exist
    if not hasattr(ki_board, "traceItems") or ki_board.traceItems is None:
        ki_board.traceItems = []

    # Add routes as Segment objects
    for net, x1, y1, x2, y2, width, layer, net_index in segment_specs:
        try:
            segment = Segment(
                start=Position(X=x1, Y=y1),
                end=Position(X=x2, Y=y2),
                width=width,
                layer=layer,
                net=net_index,
                tstamp=str(uuid.uuid4()),  # Required: unique timestamp ID
            )
            ki_board.traceItems.append(segment)
            traces_added += 1
        except Exception as e:
            warnings.append(f"Failed to add trace ({x1}, {y1}) → ({x2}, {y2}): {e}")
            traces_skipped += 1

    # Add vias if provided
    for net, vx, vy, width, drill, layers, net_index in via_specs:
        try:
            kicad_via = Via(
                position=Position(X=vx, Y=vy),
                size=width,
                drill=drill,
                layers=layers,
                net=net_index,
                tstamp=str(uuid.uuid4()),
            )
            ki_board.traceItems.append(kicad_via)
            vias_added += 1
        except Exception as e:
            warnings.append(f"Failed to add via at ({vx}, {vy}): {e}")

    # Ensure output directory exists
    output_pcb.parent.mkdir(parents=True, exist_ok=True)

    # Write the modified PCB
    try:
        _validate_4_layer_output(ki_board)
        ki_board.to_file(str(output_pcb))
    except Exception as e:
        raise ValueError(f"Failed to write output PCB: {e}") from e

    return WriteResult(
        output_path=output_pcb,
        components_updated=traces_added,  # Reusing field for trace count
        components_skipped=traces_skipped,
        warnings=warnings,
    )


def get_routing_statistics(pcb_path: Path) -> dict[str, int]:
    """
    Get statistics about routing in a PCB file.
    """
    try:
        ki_board = KiBoard.from_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}") from e

    return _rs_get_routing_statistics(ki_board)
