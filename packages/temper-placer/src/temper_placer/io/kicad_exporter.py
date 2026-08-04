"""
KiCad PCB route exporter (temper-wnyn).

Exports router RoutePath objects to KiCad PCB files with trace segments and vias.

Wave 4, Phase 3, candidate 4 (``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``):
the transformation/decision layer delegates to ``temper-io-types``'s
``kicad_write`` kernels (plan D5/Q1: duck-typed ``from_py_object`` boundary —
the unmigrated kiutils ``Board`` and router_v6 ``RoutePath`` inputs are read
inside Rust). This shim keeps only the kiutils object I/O
(``KiBoard.from_file`` / ``board.to_file``), the kiutils item construction
(``Segment`` / ``Via`` / ``Position``), and the zone-fill / provenance calls —
the R3-style boundary notes are recorded in
``packages/temper-io-types/VERIFICATION.md``.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from kiutils.board import Board as KiBoard
from kiutils.items.brditems import Segment, Via
from kiutils.items.common import Position

from temper_io_types import (
    export_board_state_plan,
    export_from_geometry_plan,
    export_route_plan,
    extract_pad_centers as _rs_extract_pad_centers,
    generate_connector_segments as _rs_generate_connector_segments,
    path_to_segments as _rs_path_to_segments,
    path_to_vias as _rs_path_to_vias,
    snap_to_nearest_pad as _rs_snap_to_nearest_pad,
    validate_4_layer_output as _rs_validate_4_layer_output,
)

from temper_placer.core.geometry_types import Track as GeoTrack
from temper_placer.core.geometry_types import Via as GeoVia
from temper_placer.io.export_types import ExportResult, TraceSegment, TraceVia
from temper_placer.router_v6 import _AdapterRoutePath as RoutePath

# Layer mapping from grid layer index to KiCad layer name.
# The canonical Temper board is 4-layer. 2-layer is not a production
# path and has been removed.
LAYER_MAP = {
    0: "F.Cu",  # Top copper (L1)
    1: "In1.Cu",  # Inner layer 1 (L2, GND plane)
    2: "In2.Cu",  # Inner layer 2 (L3, PWR plane)
    3: "B.Cu",  # Bottom copper (L4)
}

# Endpoint snapping tolerance in mm (increased to handle grid alignment)
SNAP_TOLERANCE_MM = 0.5  # 0.5mm handles typical grid cell sizes (0.5mm spacing)


def _validate_4_layer_output(board: object) -> None:
    """Validate that a KiCad board has exactly 4 copper layers with canonical names.

    The decision (warn vs raise) and the message are computed by the
    ``temper-io-types`` kernel; this shim performs the Python-side logging and
    ``RuntimeError`` raising, matching the pinned pre-migration behavior.
    """
    import logging

    from temper_placer.core.board import CANONICAL_4LAYER_LAYER_NAMES

    logger = logging.getLogger(__name__)

    decision, message = _rs_validate_4_layer_output(board)
    if decision == "warn":
        logger.warning("%s", message)
        return
    if decision == "raise":
        raise RuntimeError(message)


def extract_pad_centers(board: KiBoard) -> dict[str, list[tuple[float, float]]]:
    """Extract pad center coordinates grouped by net name.

    Returns:
        Dictionary mapping net_name -> list of (x, y) pad centers
    """
    return _rs_extract_pad_centers(board)  # temper_io_types kernel (duck-typed)


def snap_to_nearest_pad(
    x: float,
    y: float,
    pad_centers: list[tuple[float, float]],
    tolerance: float = 0.15,  # Sufficient for 0.25mm grid half-cell
) -> tuple[float, float]:
    """Snap coordinate to nearest pad center if within tolerance."""
    return _rs_snap_to_nearest_pad(x, y, pad_centers, tolerance)


def path_to_segments(
    path: RoutePath,
    origin: tuple[float, float],
    cell_size: float,
    trace_width: float,
    layer_map: dict[int, str] | None = None,
) -> list[TraceSegment]:
    """Convert path to trace segments."""
    return _rs_path_to_segments(path, origin, cell_size, trace_width, layer_map)


def path_to_vias(
    path: RoutePath,
    origin: tuple[float, float],
    cell_size: float,
    via_size: float = 0.8,
    via_drill: float = 0.4,
    layer_map: dict[int, str] | None = None,
) -> list[TraceVia]:
    """Extract vias from layer transitions in path."""
    return _rs_path_to_vias(path, origin, cell_size, via_size, via_drill, layer_map)


def _generate_connector_segments(
    segments: list[TraceSegment],
    pad_centers: dict[str, list[tuple[float, float]]],
    max_dist: float = 2.0,
) -> list[TraceSegment]:
    """
    Generate connector segments to bridge gaps between track endpoints and pads.
    """
    return _rs_generate_connector_segments(segments, pad_centers, max_dist)


def add_segments_to_board(
    board: KiBoard,
    segments: list[TraceSegment],
) -> int:
    """Add trace segments to KiCad board object.

    kiutils item construction — kept across the boundary (the plan's
    ``yaml.safe_load`` judgement: constructing ``kiutils.items.brditems``
    objects is boundary plumbing, not engine logic).
    """
    added_count = 0

    for seg in segments:
        # Find net code (KiCad uses numeric net IDs)
        net_code = 0  # Default to unconnected
        for net in board.nets:
            if net.name == seg.net:
                net_code = net.number
                break

        # Create segment using kiutils
        kicad_seg = Segment(
            start=Position(X=seg.start[0], Y=seg.start[1]),
            end=Position(X=seg.end[0], Y=seg.end[1]),
            width=seg.width,
            layer=seg.layer,
            net=net_code,
            tstamp=str(uuid.uuid4()),
        )

        board.traceItems.append(kicad_seg)
        added_count += 1

    return added_count


def add_vias_to_board(
    board: KiBoard,
    vias: list[TraceVia],
) -> int:
    """Add vias to KiCad board object.

    kiutils item construction — kept across the boundary (see
    ``add_segments_to_board``).
    """
    added_count = 0

    for via in vias:
        # Find net code
        net_code = 0
        for net in board.nets:
            if net.name == via.net:
                net_code = net.number
                break

        # Create via using kiutils
        kicad_via = Via(
            position=Position(X=via.position[0], Y=via.position[1]),
            size=via.size,
            drill=via.drill,
            layers=via.layers,
            net=net_code,
            tstamp=str(uuid.uuid4()),
        )

        board.traceItems.append(kicad_via)
        added_count += 1

    return added_count


def export_routed_pcb(
    template_pcb: Path,
    routes: dict[str, RoutePath],
    output_pcb: Path,
    trace_widths: dict[str, float] | None = None,
    default_trace_width: float = 0.25,
    via_size: float = 0.8,
    via_drill: float = 0.4,
    origin: tuple[float, float] = (0.0, 0.0),
    cell_size: float = 1.0,
    layer_map: dict[int, str] | None = None,
    auto_fill_zones: bool = True,
) -> ExportResult:
    """Export routed paths to KiCad PCB file.

    The per-net segment/via generation, via dedup
    (``(round(x,3), round(y,3), sorted(layers))`` first-wins), pad-center
    extraction and connector generation run in the ``temper-io-types``
    ``export_route_plan`` kernel; this shim keeps the kiutils board I/O, item
    construction and zone filling.
    """
    # Load template PCB
    board = KiBoard.from_file(str(template_pcb))

    # FIX: Clean up corrupt drills from kiutils import of template
    # kiutils < 1.4.9 has a bug parsing (drill (offset...)) which results in garbage data
    # that crashes export. We must strip this from SMD pads.
    if hasattr(board, "footprints"):
        for fp in board.footprints:
            for pad in fp.pads:
                if pad.type == "smd" and pad.drill is not None:
                    # If parse failed, it might have garbage in diameter or be a DrillDefinition object
                    # Safe bet: SMD pads shouldn't have drills in this context.
                    pad.drill = None

    all_segments, unique_vias, connectors, nets_exported, nets_failed, warnings = (
        export_route_plan(
            board,
            routes,
            trace_widths,
            default_trace_width,
            via_size,
            via_drill,
            origin,
            cell_size,
            layer_map,
        )
    )

    # OPTION G+H: GENERATE CONNECTOR SEGMENTS
    if connectors:
        print(f"  INFO: Generated {len(connectors)} connector segments to bridge gaps")
        all_segments = list(all_segments) + list(connectors)

    # Add geometry to board
    segments_added = add_segments_to_board(board, all_segments)
    vias_added = add_vias_to_board(board, unique_vias)
    # Write output file
    output_pcb = Path(output_pcb)
    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    _validate_4_layer_output(board)
    board.to_file(str(output_pcb))

    # Automatically fill zones if requested (temper-x8jz)
    if auto_fill_zones:
        from temper_placer.io.zone_filler import fill_zones_if_present

        fill_zones_if_present(output_pcb, verbose=True)

    return ExportResult(
        output_path=output_pcb,
        segments_added=segments_added,
        vias_added=vias_added,
        nets_exported=nets_exported,
        nets_failed=nets_failed,
        warnings=warnings,
    )


def export_board_state(
    template_pcb: Path,
    state: BoardState,  # noqa: F821
    output_pcb: Path,
    auto_fill_zones: bool = True,
    netlist_path: Path | None = None,
    config_path: Path | None = None,
) -> ExportResult:
    """Export board state directly to KiCad PCB.

    Zero-length-trace rejection, pad-center snapping and the via_dedup
    (``round(x/0.001)*0.001``) dedup run in the ``temper-io-types``
    ``export_board_state_plan`` kernel.
    """
    # Load PCB
    board = KiBoard.from_file(str(template_pcb))

    # Clear existing traces/vias
    board.traceItems = []

    all_traces = list(state.routes)
    all_vias = list(state.vias)

    clean_traces, snapped_count, unique_vias, nets_exported = export_board_state_plan(
        board, all_traces, all_vias
    )

    if snapped_count > 0:
        print(f"  INFO: Snapped {snapped_count} traces to pad centers")

    # Add geometry to board
    segments_added = add_segments_to_board(board, clean_traces)
    vias_added = add_vias_to_board(board, unique_vias)

    # Write output
    output_pcb = Path(output_pcb)
    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    _validate_4_layer_output(board)

    # Provenance header (plan 2026-07-15-001, unit U5). Skipped, not faked,
    # when the netlist isn't available -- this export path also runs against
    # boards/fixtures unrelated to this project's real netlist.
    resolved_netlist_path = netlist_path or Path("elec/build/default.net")
    if resolved_netlist_path.exists():
        from temper_placer.io.provenance import compute_provenance, embed_provenance

        provenance = compute_provenance(template_pcb, resolved_netlist_path, config_path)
        embed_provenance(board, provenance)

    board.to_file(str(output_pcb))

    # Automatically fill zones if requested
    if auto_fill_zones:
        from temper_placer.io.zone_filler import fill_zones_if_present

        fill_zones_if_present(output_pcb, verbose=True)

    return ExportResult(
        output_path=output_pcb,
        segments_added=segments_added,
        vias_added=vias_added,
        nets_exported=nets_exported,
        nets_failed=0,
        warnings=[],
    )


def export_from_geometry(
    template_pcb: Path,
    output_pcb: Path,
    tracks: list[GeoTrack],
    vias: list[GeoVia],
    layer_map: dict[int, str] | None = None,
) -> ExportResult:
    """Export geometry directly to KiCad PCB.

    Net-code resolution and the layer map run in the ``temper-io-types``
    ``export_from_geometry_plan`` kernel; the shim constructs the kiutils
    items.
    """
    layer_map = layer_map or LAYER_MAP

    # Load PCB
    board = KiBoard.from_file(str(template_pcb))

    # Clear existing traces/vias
    board.traceItems = []

    segment_specs, via_specs, nets_exported = export_from_geometry_plan(
        board.nets, tracks, vias, layer_map
    )

    total_segments = 0
    total_vias = 0

    # Add tracks
    for spec in segment_specs:
        net, x1, y1, x2, y2, width, layer_name, net_code = spec
        segment = Segment(
            start=Position(X=x1, Y=y1),
            end=Position(X=x2, Y=y2),
            width=width,
            layer=layer_name,
            net=net_code,
            tstamp=str(uuid.uuid4()),
        )
        board.traceItems.append(segment)
        total_segments += 1

    # Add vias
    for spec in via_specs:
        net, cx, cy, diameter, drill, layers, net_code = spec
        kicad_via = Via(
            position=Position(X=cx, Y=cy),
            size=diameter,
            drill=drill,
            layers=layers,
            net=net_code,
            tstamp=str(uuid.uuid4()),
        )
        board.traceItems.append(kicad_via)
        total_vias += 1

    # Write output
    _validate_4_layer_output(board)
    board.to_file(str(output_pcb))

    return ExportResult(
        output_path=output_pcb,
        segments_added=total_segments,
        vias_added=total_vias,
        nets_exported=nets_exported,
        nets_failed=0,
        warnings=[],
    )
