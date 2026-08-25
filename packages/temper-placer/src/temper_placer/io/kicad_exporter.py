"""
KiCad PCB route exporter (temper-wnyn).

Exports router RoutePath objects to KiCad PCB files with trace segments and vias.
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import temper_geometry as _tg
from temper_io_types import kicad_write_geometry as _GEOM

from temper_placer.core.geometry_types import Track as GeoTrack
from temper_placer.core.geometry_types import Via as GeoVia
from temper_placer.io.export_types import ExportResult, TraceSegment, TraceVia
from temper_placer.io.via_dedup import deduplicate_vias
from temper_placer.router_v6 import _AdapterRoutePath as RoutePath
from temper_placer.router_v6.path_simplify import simplify_path

if TYPE_CHECKING:
    # Annotation-only (postponed evaluation via `from __future__ import
    # annotations`): guarded to avoid pulling deterministic/state.py's import
    # graph into this module at runtime. Was previously an undefined name
    # (mypy `name-defined`), long ruff-`noqa: F821`-suppressed and therefore
    # invisible to lint -- mypy is the first gate that actually checks it.
    from temper_placer.deterministic.state import BoardState


def _load_board_text(template_pcb: Path) -> str:
    """Load a template board as raw text (the Rust kernels' input format).

    Wave 4 Phase 3 (formats/IO): the entire board I/O path is Rust —
    parse (``parse_engine``), mutate (``sexpr_writer`` tree kernels),
    serialize (``write_board_sexpr_py``). Python only orchestrates; the
    board never materializes as kiutils objects.
    """
    return Path(template_pcb).read_text()


def _validate_4_layer_output(board_text: str) -> None:
    """Validate that a KiCad board has exactly 4 copper layers with canonical names.

    Warns instead of raising for boards with differing layer counts — the
    canonical 4-layer stackup is the production target, but non-production
    boards (test fixtures, 2-layer prototypes) are valid output.
    """
    import logging

    from temper_placer.core.board import CANONICAL_4LAYER_LAYER_NAMES

    logger = logging.getLogger(__name__)

    import temper_design_bundle_python as _tdb

    layer_names = _tdb.parse_engine.extract_copper_layer_names_py(board_text)
    copper_names = [name for name in layer_names if name.endswith(".Cu")]
    if len(copper_names) != 4:
        logger.warning(
            "Board has %d copper layers (canonical 4-layer stackup: %s). "
            "Proceeding — non-4-layer boards are valid for test fixtures and prototypes.",
            len(copper_names),
            sorted(CANONICAL_4LAYER_LAYER_NAMES),
        )
        return
    name_set = set(copper_names)
    if name_set != set(CANONICAL_4LAYER_LAYER_NAMES):
        raise RuntimeError(
            f"Copper layer names must match canonical set {sorted(CANONICAL_4LAYER_LAYER_NAMES)}, "
            f"got {sorted(name_set)}"
        )


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


def extract_pad_centers(board_text: str) -> dict[str, list[tuple[float, float]]]:
    """Extract pad center coordinates grouped by net name.

    Delegates to the Rust kernel (``parse_engine.extract_pad_centers_py``):
    text -> KiNode tree traversal with temper-geometry's canonical
    R(-theta) rotation. Shape matches the pre-migration kiutils traversal
    exactly (first-appearance group order).
    """
    import temper_design_bundle_python as _tdb

    return _tdb.parse_engine.extract_pad_centers_py(board_text)


def _net_map(board_text: str) -> list:
    """Net objects for find_net_code_py — [{name, number}] from the board text."""
    import temper_design_bundle_python as _tdb

    raw = _tdb.parse_engine.extract_net_map_from_text_py(board_text)
    return [SimpleNamespace(name=name, number=number) for name, number in raw.items()]


def _append_items(board_text: str, item_sexprs: list) -> str:
    """Append pre-built s-expression items to the board tree; serialize."""
    import temper_design_bundle_python as _tdb

    return _tdb.parse_engine.append_items_to_board_py(board_text, item_sexprs)


def _clear_traces(board_text: str) -> str:
    """Remove all existing trace items (segments/vias/arcs); keep zones."""
    import temper_design_bundle_python as _tdb

    new_text, _, _, _ = _tdb.parse_engine.strip_trace_items_py(
        board_text, True, True
    )
    return new_text


def _build_segment_items(board_text: str, segments: list[TraceSegment]) -> list:
    """Pre-build segment s-expression items (Rust content kernels)."""
    nets = _net_map(board_text)
    return [
        _GEOM.segment_sexpr_py(
            seg.start[0], seg.start[1], seg.end[0], seg.end[1],
            seg.width, seg.layer, _GEOM.find_net_code_py(nets, seg.net),
            str(uuid.uuid4()),
        )
        for seg in segments
    ]


def _build_via_items(board_text: str, vias: list[TraceVia]) -> list:
    """Pre-build via s-expression items (Rust content kernels)."""
    nets = _net_map(board_text)
    return [
        _GEOM.via_sexpr_py(
            via.position[0], via.position[1],
            via.size, via.drill, list(via.layers), _GEOM.find_net_code_py(nets, via.net),
            str(uuid.uuid4()),
        )
        for via in vias
    ]


def snap_to_nearest_pad(
    x: float,
    y: float,
    pad_centers: list[tuple[float, float]],
    tolerance: float = 0.15,  # Sufficient for 0.25mm grid half-cell
) -> tuple[float, float]:
    """Snap coordinate to nearest pad center if within tolerance.

    Delegates to the Rust kernel (Wave 4 Phase 3, formats/IO migration).
    Pinned oracle: ``tests/io/_kicad_exporter_py_oracle.py``; differential:
    ``tests/io/test_kicad_exporter_geometry_rust_differential.py``.
    """
    from temper_design_bundle_python import kicad_exporter_geometry as _kicad_exporter_geometry

    return _kicad_exporter_geometry.snap_to_nearest_pad_py(x, y, list(pad_centers), tolerance)


def path_to_segments(
    path: RoutePath,
    origin: tuple[float, float],
    cell_size: float,
    trace_width: float,
    layer_map: dict[int, str] | None = None,
) -> list[TraceSegment]:
    """Convert path to trace segments."""
    segments = []

    # Prefer RoutePath.cells (the pathfinding result); fall back to
    # .segments or .coordinates for compatibility with RoutePath3D and
    # V6 router paths that have already converted to world coords.
    coords = []
    if hasattr(path, "cells") and getattr(path, "cells", None):
        path_cell_size = getattr(path, "cell_size", cell_size)
        layer_map = layer_map or LAYER_MAP
        simplified = simplify_path(path.cells)
        for c in simplified:
            x, y = _tg.grid_to_world_py(c.x, c.y, origin[0], origin[1], path_cell_size)
            layer_name = layer_map.get(c.layer, "F.Cu")
            coords.append((x, y, layer_name))
    elif hasattr(path, "segments") and path.segments:
        coords = list(path.segments)
    elif hasattr(path, "coordinates") and path.coordinates:
        coords = list(path.coordinates)
    else:
        return []

    default_layer = getattr(path, "layer_name", "F.Cu")
    net = getattr(path, "net_name", None) or getattr(path, "net", "unknown")

    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]

        if len(p1) == 3:
            x1, y1, l1 = p1
        else:
            x1, y1 = p1
            l1 = default_layer
        if len(p2) == 3:
            x2, y2, l2 = p2
        else:
            x2, y2 = p2
            l2 = default_layer

        if l1 != l2:
            continue

        segments.append(
            TraceSegment(
                net=net or "unknown",
                start=(x1, y1),
                end=(x2, y2),
                width=trace_width,
                layer=l1,
            )
        )

    return segments


def path_to_vias(
    path: RoutePath,
    origin: tuple[float, float],
    cell_size: float,
    via_size: float = 0.8,
    via_drill: float = 0.4,
    layer_map: dict[int, str] | None = None,
) -> list[TraceVia]:
    """Extract vias from layer transitions in path."""
    vias = []

    coords = []
    if hasattr(path, "cells") and getattr(path, "cells", None):
        path_cell_size = getattr(path, "cell_size", cell_size)
        layer_map = layer_map or LAYER_MAP
        for c in path.cells:
            x, y = _tg.grid_to_world_py(c.x, c.y, origin[0], origin[1], path_cell_size)
            layer_name = layer_map.get(c.layer, "F.Cu")
            coords.append((x, y, layer_name))
    elif hasattr(path, "segments") and path.segments:
        coords = list(path.segments)
    elif hasattr(path, "coordinates") and path.coordinates:
        coords = list(path.coordinates)
    else:
        return []

    net = getattr(path, "net_name", None) or getattr(path, "net", "unknown")
    default_layer = getattr(path, "layer_name", "F.Cu")

    for i in range(1, len(coords)):
        p1 = coords[i - 1]
        p2 = coords[i]

        if len(p1) >= 3 and len(p2) >= 3:
            l1 = p1[2]
            l2 = p2[2]
        else:
            l1 = l2 = default_layer

        if l1 != l2:
            pos = (p2[0], p2[1])
            # Use just the two layers being joined (partial stack);
            # through-hole would need ["F.Cu", "B.Cu"] for top↔bottom.
            all_layers = sorted({l1, l2})

            vias.append(
                TraceVia(
                    net=net or "unknown",
                    position=pos,
                    size=via_size,
                    drill=via_drill,
                    layers=all_layers,
                )
            )

    return vias


def _generate_connector_segments(
    segments: list[TraceSegment],
    pad_centers: dict[str, list[tuple[float, float]]],
    max_dist: float = 2.0,
) -> list[TraceSegment]:
    """
    Generate connector segments to bridge gaps between track endpoints and pads.

    The skeleton router stops at the medial axis, which may be 1-2mm away from
    the actual pad center. This function detects 'dangling' track ends near pads
    and adds a straight segment to connect them.

    Args:
        segments: List of existing trace segments
        pad_centers: Dict mapping net name to list of pad coordinates (x, y)
        max_dist: Maximum distance to bridge (mm)

    Returns:
        List of NEW connector segments

    Delegates the nearest-endpoint bridging search to the Rust kernel (Wave 4
    Phase 3, formats/IO migration). Pinned oracle:
    ``tests/io/_kicad_exporter_py_oracle.py``; differential:
    ``tests/io/test_kicad_exporter_geometry_rust_differential.py``.
    """
    from temper_design_bundle_python import kicad_exporter_geometry as _kicad_exporter_geometry

    seg_tuples = [(seg.net, seg.start, seg.end, seg.width, seg.layer) for seg in segments]
    # `dict.items()` preserves insertion order -- NOT a set, so this carries
    # no PYTHONHASHSEED risk across the boundary.
    pad_tuples = list(pad_centers.items())
    result = _kicad_exporter_geometry.generate_connector_segments_py(seg_tuples, pad_tuples, max_dist)
    return [
        TraceSegment(net=net, start=start, end=end, width=width, layer=layer)
        for (net, start, end, width, layer) in result
    ]


def add_segments_to_board(
    board_text: str,
    segments: list[TraceSegment],
) -> int:
    """Add trace segments to a KiCad board (text path).

    The net-code lookup and segment content are built in Rust
    (find_net_code_py / segment_sexpr_py); items are appended to the
    parsed KiNode tree and serialized back by ``append_items_to_board_py``.

    Args:
        board_text: Raw .kicad_pcb text of the board to modify
        segments: List of trace segments to add

    Returns:
        Number of segments added
    """
    if not segments:
        return 0


    item_sexprs = []
    for seg in segments:
        net_code = _GEOM.find_net_code_py(_net_map(board_text), seg.net)
        item_sexprs.append(
            _GEOM.segment_sexpr_py(
                seg.start[0], seg.start[1], seg.end[0], seg.end[1],
                seg.width, seg.layer, net_code, str(uuid.uuid4()),
            )
        )
    return len(item_sexprs)  # caller applies via _append_items; count only


def add_vias_to_board(
    board_text: str,
    vias: list[TraceVia],
) -> int:
    """Add vias to a KiCad board (text path).

    The net-code lookup and via content are built in Rust
    (find_net_code_py / via_sexpr_py); items are appended to the parsed
    KiNode tree and serialized back by ``append_items_to_board_py``.

    Args:
        board_text: Raw .kicad_pcb text of the board to modify
        vias: List of vias to add

    Returns:
        Number of vias added
    """
    if not vias:
        return 0

    item_sexprs = []
    for via in vias:
        net_code = _GEOM.find_net_code_py(_net_map(board_text), via.net)
        item_sexprs.append(
            _GEOM.via_sexpr_py(
                via.position[0], via.position[1],
                via.size, via.drill, list(via.layers), net_code, str(uuid.uuid4()),
            )
        )
    return len(item_sexprs)


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

    Main export function that:
    1. Parses template PCB (has components, no traces)
    2. Converts successful routes to segments and vias
    3. Adds geometry to PCB via the Rust text-path kernels
    4. Writes output file

    Args:
        template_pcb: Path to input .kicad_pcb file with placed components
        routes: Dictionary of net_name → RoutePath from router
        output_pcb: Path to write output .kicad_pcb file
        trace_widths: Optional dict of net_name → trace width (mm)
        default_trace_width: Default trace width in mm
        via_size: Via outer diameter in mm
        via_drill: Via drill diameter in mm
        origin: PCB origin offset (x0, y0)
        cell_size: Router grid cell size in mm
        layer_map: Optional layer index → name mapping

    Returns:
        ExportResult with statistics and warnings

    Example:
        >>> routes = {
        ...     "GND": RoutePath(..., success=True),
        ...     "VCC": RoutePath(..., success=True),
        ...     "SIG1": RoutePath(..., success=False),
        ... }
        >>> result = export_routed_pcb(
        ...     "input.kicad_pcb",
        ...     routes,
        ...     "output.kicad_pcb",
        ... )
        >>> print(result)
        Export complete: 2 nets, 45 segments, 3 vias → output.kicad_pcb
    """
    # Load template PCB as raw text — all board I/O is Rust from here
    board_text = _load_board_text(template_pcb)

    # Strip corrupt SMD drills (kiutils < 1.4.9 mis-parse; the Rust kernel
    # drops the whole (drill ...) sub-list from every SMD pad).
    import temper_design_bundle_python as _tdb

    board_text = _tdb.parse_engine.strip_smd_drills_py(board_text)

    # Collect all segments and vias
    all_segments: list[TraceSegment] = []
    all_vias: list[TraceVia] = []
    nets_exported = 0
    nets_failed = 0
    warnings: list[str] = []

    layer_map_to_use = layer_map or LAYER_MAP

    for net_name, path in routes.items():
        # Check success if attribute exists (legacy), otherwise assume success if in dict
        if hasattr(path, "success") and not path.success:
            nets_failed += 1
            warnings.append(
                f"Net {net_name} routing failed: {getattr(path, 'failure_reason', 'unknown')}"
            )
            continue

        # Determine trace width for this net
        trace_width = (
            trace_widths.get(net_name, default_trace_width) if trace_widths else default_trace_width
        )

        # Determine cell size (use path's if available, else function arg)
        current_cell_size = getattr(path, "cell_size", cell_size)

        # Convert path to geometry
        segments = path_to_segments(path, origin, current_cell_size, trace_width, layer_map_to_use)

        # Use explicit vias (e.g. via arrays) if present, otherwise infer from layer transitions
        if hasattr(path, "explicit_vias") and path.explicit_vias:
            vias = path.explicit_vias
        else:
            vias = path_to_vias(
                path, origin, current_cell_size, via_size, via_drill, layer_map_to_use
            )

        all_segments.extend(segments)
        all_vias.extend(vias)
        nets_exported += 1

    # Deduplicate vias to avoid holes_co_located violations
    # Convert to hashable tuples first
    via_list = [(v.position[0], v.position[1], tuple(sorted(v.layers))) for v in all_vias]
    set(via_list)
    unique_vias = []

    # Reconstruct TraceVia objects
    # We lost size/drill/net info in deduplication if we just use set
    # Better approach: Keep first via for each position+layers key
    via_map = {}
    for v in all_vias:
        key = (round(v.position[0], 3), round(v.position[1], 3), tuple(sorted(v.layers)))
        if key not in via_map:
            via_map[key] = v
            unique_vias.append(v)

    # OPTION G+H: GENERATE CONNECTOR SEGMENTS
    # Bridge small gaps between route ends and pad centers
    # caused by medial axis approximation or coordinate quirks.
    pad_centers = extract_pad_centers(board_text)
    connectors = _generate_connector_segments(all_segments, pad_centers, max_dist=2.0)
    if connectors:
        print(f"  INFO: Generated {len(connectors)} connector segments to bridge gaps")
        all_segments.extend(connectors)

    # Add geometry to board (Rust text path: build sexprs, append to tree)
    segments_added = add_segments_to_board(board_text, all_segments)
    vias_added = add_vias_to_board(board_text, unique_vias)
    seg_items = _build_segment_items(board_text, all_segments)
    via_items = _build_via_items(board_text, unique_vias)
    board_text = _append_items(_clear_traces(board_text), seg_items + via_items)

    # Write output file
    output_pcb = Path(output_pcb)
    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    _validate_4_layer_output(board_text)
    output_pcb.write_text(board_text)

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
    state: BoardState,
    output_pcb: Path,
    auto_fill_zones: bool = True,
    netlist_path: Path | None = None,
    config_path: Path | None = None,
) -> ExportResult:
    """Export board state directly to KiCad PCB.

    This is the preferred high-level export function for the deterministic pipeline.
    It takes a BoardState and performs pad-center snapping to ensure DRC clean connectivity.

    Args:
        template_pcb: Input PCB path
        state: BoardState containing traces and vias
        output_pcb: Output PCB path
        auto_fill_zones: Whether to trigger zone filling
        netlist_path: Atopile netlist export to record in the output's
            provenance header (default: elec/build/default.net if present).
            Provenance is skipped, not faked, if it can't be found.
        config_path: Placement config in effect, if any, also recorded in
            the provenance header.

    Returns:
        ExportResult stats
    """
    # Load PCB as raw text; clear existing traces/vias (Rust text path)
    board_text = _clear_traces(_load_board_text(template_pcb))

    all_traces = list(state.routes)
    all_vias = list(state.vias)

    # Extract pad centers for endpoint snapping
    pad_centers = extract_pad_centers(board_text)

    # Clean up segments and snap
    # 1. Reject zero-length segments
    valid_traces = [
        t
        for t in all_traces
        if math.sqrt((t.start[0] - t.end[0]) ** 2 + (t.start[1] - t.end[1]) ** 2) > 0.001
    ]

    # 2. Snap segment endpoints to pad centers
    # For signal nets, we use a larger tolerance (0.15mm) to bridge grid gaps.
    # For plane nets (GND), we are more careful to preserve stubs.
    snapped_count = 0
    clean_traces = []
    for t in valid_traces:
        new_start = t.start
        new_end = t.end

        if t.net in pad_centers:
            net_pads = pad_centers[t.net]
            new_start = snap_to_nearest_pad(t.start[0], t.start[1], net_pads)
            new_end = snap_to_nearest_pad(t.end[0], t.end[1], net_pads)

            if new_start != t.start or new_end != t.end:
                snapped_count += 1

        clean_traces.append(
            TraceSegment(net=t.net, start=new_start, end=new_end, width=t.width, layer=t.layer)
        )

    if snapped_count > 0:
        print(f"  INFO: Snapped {snapped_count} traces to pad centers")

    # Add geometry to board (Rust text path)
    segments_added = add_segments_to_board(board_text, clean_traces)

    # Deduplicate vias
    via_list = [
        TraceVia(net=v.net, position=v.position, size=v.width, drill=v.drill, layers=list(v.layers))
        for v in all_vias
    ]
    unique_vias = deduplicate_vias(via_list)
    vias_added = add_vias_to_board(board_text, unique_vias)
    board_text = _append_items(
        board_text,
        _build_segment_items(board_text, clean_traces)
        + _build_via_items(board_text, unique_vias),
    )

    # Write output
    output_pcb = Path(output_pcb)
    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    _validate_4_layer_output(board_text)

    # Provenance header (plan 2026-07-15-001, unit U5). Skipped, not faked,
    # when the netlist isn't available -- this export path also runs against
    # boards/fixtures unrelated to this project's real netlist. The embed
    # is the Rust text kernel (provenance.py: parse -> mutate KiNode tree ->
    # serialize), applied to the Rust-serialized board text.
    resolved_netlist_path = netlist_path or Path("elec/build/default.net")
    if resolved_netlist_path.exists():
        from temper_placer.io.provenance import compute_provenance, embed_provenance

        provenance = compute_provenance(template_pcb, resolved_netlist_path, config_path)
        board_text = embed_provenance(board_text, provenance)
    output_pcb.write_text(board_text)

    # Automatically fill zones if requested
    if auto_fill_zones:
        from temper_placer.io.zone_filler import fill_zones_if_present

        fill_zones_if_present(output_pcb, verbose=True)

    return ExportResult(
        output_path=output_pcb,
        segments_added=segments_added,
        vias_added=vias_added,
        nets_exported=len({t.net for t in clean_traces}),
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

    Args:
        template_pcb: Input PCB path
        output_pcb: Output PCB path
        tracks: List of Track objects from PCBGeometry
        vias: List of Via objects from PCBGeometry
        layer_map: Layer index to name map

    Returns:
        ExportResult stats
    """
    layer_map = layer_map or LAYER_MAP

    # Load PCB as raw text; clear existing traces/vias (Rust text path)
    board_text = _clear_traces(_load_board_text(template_pcb))

    total_segments = len(tracks)
    total_vias = len(vias)

    # Build all items — net-code lookup and item content run in Rust
    # (find_net_code_py / segment_sexpr_py / via_sexpr_py).
    nets = _net_map(board_text)
    items: list = []
    for track in tracks:
        layer_name = layer_map.get(track.layer, "F.Cu")
        net_code = _GEOM.find_net_code_py(nets, track.net)
        items.append(
            _GEOM.segment_sexpr_py(
                track.start.x, track.start.y, track.end.x, track.end.y,
                track.width, layer_name, net_code, str(uuid.uuid4()),
            )
        )

    # Add vias
    for via in vias:
        net_code = _GEOM.find_net_code_py(nets, via.net)
        items.append(
            _GEOM.via_sexpr_py(
                via.center.x, via.center.y,
                via.diameter, via.drill, ["F.Cu", "B.Cu"], net_code, str(uuid.uuid4()),
            )
        )

    board_text = _append_items(board_text, items)

    # Write output
    _validate_4_layer_output(board_text)
    output_pcb.write_text(board_text)

    return ExportResult(
        output_path=output_pcb,
        segments_added=total_segments,
        vias_added=total_vias,
        nets_exported=len({t.net for t in tracks}),
        nets_failed=0,
        warnings=[],
    )
