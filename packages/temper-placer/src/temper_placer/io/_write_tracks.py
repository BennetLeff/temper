"""Internal: trace/via route writing and stripping functions."""

from __future__ import annotations

from pathlib import Path

from kiutils.board import Board as KiBoard

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

    This is used to create "unrouted" versions of PCBs for benchmark comparisons,
    where we want to compare optimizer placements against human placements without
    the interference of broken traces (which cause DRC errors when components move).

    What is REMOVED:
    - All trace segments on copper layers (F.Cu, B.Cu, In*.Cu)
    - All vias
    - Zone fills (optionally, if keep_fills=False)

    What is KEPT:
    - Footprints (components) with original positions
    - Pads and their net assignments (connectivity information)
    - Board outline (Edge.Cuts layer)
    - Text, silkscreen, labels
    - Design rules
    - Net definitions
    - Zone outlines (if keep_zones=True)

    Args:
        input_pcb: Path to the input .kicad_pcb file with routing.
        output_pcb: Path for the output .kicad_pcb file without routing.
        keep_zones: If True, keep zone outlines but remove fills.
                   If False, remove zones entirely.
        keep_fills: If True, keep zone copper fills (rarely desired).

    Returns:
        StrippingResult with statistics about what was removed.
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

    # Remove traces and vias from traceItems
    # traceItems contains: Segment (traces), Via, Arc
    len(ki_board.traceItems) if ki_board.traceItems else 0

    # Filter traceItems - keep only non-routing items (there shouldn't be any)
    # In kiutils, traceItems are: Segment, Via, Arc
    if ki_board.traceItems:
        new_trace_items = []
        for item in ki_board.traceItems:
            item_type = type(item).__name__

            if item_type in ("Segment", "Arc"):
                # This is a trace segment - remove it
                traces_removed += 1
            elif item_type == "Via":
                # This is a via - remove it
                vias_removed += 1
            else:
                # Unknown type - keep it with warning
                warnings.append(f"Unknown traceItem type preserved: {item_type}")
                new_trace_items.append(item)

        ki_board.traceItems = new_trace_items

    # Handle zones
    if ki_board.zones:
        if not keep_zones:
            # Remove all zones entirely
            zones_removed = len(ki_board.zones)
            ki_board.zones = []
        elif not keep_fills:
            # Keep zone outlines but clear fills
            for zone in ki_board.zones:
                # Clear filled polygons (the copper pour)
                if hasattr(zone, "filledPolygons"):
                    zone.filledPolygons = []
                # The polygon/polygons attribute is the zone outline, keep it

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

    This is a convenience wrapper around strip_routing that verifies
    net assignments are preserved after stripping.

    Args:
        input_pcb: Path to the input .kicad_pcb file.
        output_pcb: Path for the output .kicad_pcb file.

    Returns:
        StrippingResult with warnings if net assignments differ.
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

    This function takes routes generated by the deterministic pipeline
    (as Trace objects) and adds them to a KiCad board as Segment objects.
    Also adds Vias if provided.

    Args:
        template_pcb: Path to the template .kicad_pcb file.
        output_pcb: Path for the output .kicad_pcb file.
        routes: Frozen set of Trace objects from BoardState.routes.
        vias: Frozen set of Via objects from BoardState.vias.
        net_name_to_index: Optional map of net name → net index.
            If None, will be built from the template PCB.
        clear_existing: If True, remove all existing traces before adding new ones.

    Returns:
        WriteResult with statistics and warnings.
    """
    from kiutils.items.brditems import Segment, Via
    from kiutils.items.common import Position

    warnings: list[str] = []
    traces_added = 0
    traces_skipped = 0
    vias_added = 0

    # Load the template PCB
    try:
        ki_board = KiBoard.from_file(str(template_pcb))
    except Exception as e:
        raise ValueError(f"Failed to load template PCB: {e}") from e

    # Build net name → index mapping if not provided
    if net_name_to_index is None:
        net_name_to_index = {}
        if hasattr(ki_board, "nets") and ki_board.nets:
            for net in ki_board.nets:
                if hasattr(net, "name") and hasattr(net, "number"):
                    net_name_to_index[net.name] = net.number

    # Clear existing traces if requested
    if clear_existing and hasattr(ki_board, "traceItems"):
        original_count = len(ki_board.traceItems) if ki_board.traceItems else 0
        ki_board.traceItems = []
        if original_count > 0:
            warnings.append(f"Cleared {original_count} existing trace items")

    # Initialize traceItems if it doesn't exist
    if not hasattr(ki_board, "traceItems") or ki_board.traceItems is None:
        ki_board.traceItems = []

    # Add routes as Segment objects
    for route in routes:
        # Get net index (default to 0 if not found)
        net_index = 0
        if route.net and route.net in net_name_to_index:
            net_index = net_name_to_index[route.net]
        elif route.net:
            warnings.append(f"Net '{route.net}' not found in board, using index 0")

        try:
            import uuid

            segment = Segment(
                start=Position(X=route.start[0], Y=route.start[1]),
                end=Position(X=route.end[0], Y=route.end[1]),
                width=route.width,
                layer=route.layer,
                net=net_index,
                tstamp=str(uuid.uuid4()),  # Required: unique timestamp ID
            )
            ki_board.traceItems.append(segment)
            traces_added += 1
        except Exception as e:
            warnings.append(f"Failed to add trace {route.start} → {route.end}: {e}")
            traces_skipped += 1

    # Add vias if provided
    if vias:
        for via in vias:
            net_index = 0
            if via.net and via.net in net_name_to_index:
                net_index = net_name_to_index[via.net]

            try:
                import uuid

                kicad_via = Via(
                    position=Position(X=via.position[0], Y=via.position[1]),
                    size=via.width,
                    drill=via.drill,
                    layers=list(via.layers),
                    net=net_index,
                    tstamp=str(uuid.uuid4()),
                )
                ki_board.traceItems.append(kicad_via)
                vias_added += 1
            except Exception as e:
                warnings.append(f"Failed to add via at {via.position}: {e}")

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

    Args:
        pcb_path: Path to the .kicad_pcb file.

    Returns:
        Dictionary with counts of traces, vias, zones, components.
    """
    try:
        ki_board = KiBoard.from_file(str(pcb_path))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}") from e

    trace_count = 0
    via_count = 0

    if ki_board.traceItems:
        for item in ki_board.traceItems:
            item_type = type(item).__name__
            if item_type in ("Segment", "Arc"):
                trace_count += 1
            elif item_type == "Via":
                via_count += 1

    return {
        "traces": trace_count,
        "vias": via_count,
        "zones": len(ki_board.zones) if ki_board.zones else 0,
        "components": len(ki_board.footprints) if ki_board.footprints else 0,
        "nets": len(ki_board.nets) if ki_board.nets else 0,
    }
