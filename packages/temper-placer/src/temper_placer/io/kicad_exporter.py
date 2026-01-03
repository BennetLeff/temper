"""
KiCad PCB route exporter (temper-wnyn).

Exports router RoutePath objects to KiCad PCB files with trace segments and vias.
"""

from dataclasses import dataclass
from pathlib import Path
import uuid

from kiutils.board import Board as KiBoard
from kiutils.items.brditems import Segment, Via
from kiutils.items.common import Position

from temper_placer.io.export_types import ExportResult, TraceSegment, TraceVia
from temper_placer.routing.grid_converter import grid_to_world
from temper_placer.routing.maze_router import RoutePath
from temper_placer.routing.path_simplify import simplify_path
from temper_placer.io.via_dedup import deduplicate_vias


# Layer mapping from grid layer index to KiCad layer name
DEFAULT_LAYER_MAP = {
    0: "F.Cu",  # Top copper
    1: "B.Cu",  # Bottom copper
    2: "In1.Cu",  # Inner layer 1 (for 4-layer boards)
    3: "In2.Cu",  # Inner layer 2 (for 4-layer boards)
}

# Endpoint snapping tolerance in mm
SNAP_TOLERANCE_MM = 0.2

def extract_pad_centers(board: KiBoard) -> dict[str, list[tuple[float, float]]]:
    """Extract pad center coordinates grouped by net name.
    
    Returns:
        Dictionary mapping net_name -> list of (x, y) pad centers
    """
    import math
    pad_centers: dict[str, list[tuple[float, float]]] = {}
    
    for fp in board.footprints:
        if fp.position:
            fp_x, fp_y = fp.position.X, fp.position.Y
            fp_angle = fp.position.angle if fp.position.angle is not None else 0.0
        else:
            fp_x, fp_y, fp_angle = 0.0, 0.0, 0.0
        
        for pad in fp.pads:
            net_name = pad.net.name if pad.net and hasattr(pad.net, "name") else str(pad.net) if pad.net else ""
            if not net_name:
                continue
            
            # Apply footprint rotation to pad position
            rel_x, rel_y = pad.position.X, pad.position.Y
            rad = math.radians(fp_angle)
            rot_x = rel_x * math.cos(rad) - rel_y * math.sin(rad)
            rot_y = rel_x * math.sin(rad) + rel_y * math.cos(rad)
            abs_x = fp_x + rot_x
            abs_y = fp_y + rot_y
            
            if net_name not in pad_centers:
                pad_centers[net_name] = []
            pad_centers[net_name].append((abs_x, abs_y))
    
    return pad_centers

def snap_to_nearest_pad(
    x: float, y: float, 
    pad_centers: list[tuple[float, float]], 
    tolerance: float = SNAP_TOLERANCE_MM
) -> tuple[float, float]:
    """Snap coordinate to nearest pad center if within tolerance.
    
    Args:
        x, y: Original coordinates
        pad_centers: List of (x, y) pad centers for this net
        tolerance: Maximum distance to snap
    
    Returns:
        Snapped (x, y) or original if no pad within tolerance
    """
    import math
    best_dist = tolerance
    best_pos = (x, y)
    
    for px, py in pad_centers:
        dist = math.sqrt((x - px)**2 + (y - py)**2)
        if dist < best_dist:
            best_dist = dist
            best_pos = (px, py)
    
    return best_pos

def path_to_segments(
    path: RoutePath,
    origin: tuple[float, float],
    cell_size: float,
    trace_width: float,
    layer_map: dict[int, str] | None = None,
) -> list[TraceSegment]:
    """Convert path to trace segments.

    Applies path simplification before conversion to reduce segment count.
    Skips cells where layer transitions occur (via locations).

    Args:
        path: RoutePath from maze router
        origin: PCB origin (x0, y0) in mm
        cell_size: Grid cell size in mm
        trace_width: Trace width in mm
        layer_map: Optional layer index to name mapping

    Returns:
        List of TraceSegment objects

    Example:
        >>> path = RoutePath(
        ...     net="GND",
        ...     cells=[GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)],
        ...     length=2.0,
        ...     via_count=0,
        ...     success=True,
        ... )
        >>> segments = path_to_segments(path,  origin=(0, 0), cell_size=1.0, trace_width=0.25)
        >>> len(segments)
        1  # Simplified to start→end
    """
    if not path.success or len(path.cells) < 2:
        return []

    layer_map = layer_map or DEFAULT_LAYER_MAP
    simplified_cells = simplify_path(path.cells)
    segments = []

    for i in range(1, len(simplified_cells)):
        c1, c2 = simplified_cells[i - 1], simplified_cells[i]

        # Layer transition creates a via, not a segment
        if c1.layer != c2.layer:
            continue

        # Convert grid to world coordinates
        start = grid_to_world(c1, origin, path.cell_size)
        end = grid_to_world(c2, origin, path.cell_size)
        layer_name = layer_map.get(c1.layer, "F.Cu")

        segments.append(
            TraceSegment(
                net=path.net,
                start=start,
                end=end,
                width=trace_width,
                layer=layer_name,
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
    """Extract vias from layer transitions in path.

    Args:
        path: RoutePath from maze router
        origin: PCB origin (x0, y0) in mm
        cell_size: Grid cell size in mm
        via_size: Via outer diameter in mm
        via_drill: Via drill diameter in mm
        layer_map: Optional layer index to name mapping

    Returns:
        List of TraceVia objects

    Example:
        >>> path = RoutePath(
        ...     net="SPI_CLK",
        ...     cells=[GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 0, 1)],
        ...     length=1.0,
        ...     via_count=1,
        ...     success=True,
        ... )
        >>> vias = path_to_vias(path, origin=(0, 0), cell_size=1.0)
        >>> len(vias)
        1
    """
    if not path.success or len(path.cells) < 2:
        return []

    layer_map = layer_map or DEFAULT_LAYER_MAP
    vias = []

    for i in range(1, len(path.cells)):
        c1, c2 = path.cells[i - 1], path.cells[i]

        # Detect layer transition
        if c1.layer != c2.layer:
            # Via is placed at the location where layer changes
            # Use the position of the cell AFTER the transition
            pos = grid_to_world(c2, origin, path.cell_size)

            # For through-hole via, specify all layers
            # For blind/buried via, would need specific layer pair
            all_layers = sorted([layer_map.get(c1.layer, "F.Cu"), layer_map.get(c2.layer, "B.Cu")])

            vias.append(
                TraceVia(
                    net=path.net,
                    position=pos,
                    size=via_size,
                    drill=via_drill,
                    layers=all_layers,
                )
            )

    return vias


def add_segments_to_board(
    board: KiBoard,
    segments: list[TraceSegment],
) -> int:
    """Add trace segments to KiCad board object.

    Uses kiutils.items.brditems.Segment to create PCB trace elements.

    Args:
        board: KiCad board object to modify
        segments: List of trace segments to add

    Returns:
        Number of segments added
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

    Uses kiutils.items.brditems.Via to create PCB via elements.

    Args:
        board: KiCad board object to modify
        vias: List of vias to add

    Returns:
        Number of vias added
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
) -> ExportResult:
    """Export routed paths to KiCad PCB file.

    Main export function that:
    1. Parses template PCB (has components, no traces)
    2. Converts successful routes to segments and vias
    3. Adds geometry to PCB using kiutils
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
    # Load template PCB
    board = KiBoard.from_file(str(template_pcb))

    # Collect all segments and vias
    all_segments: list[TraceSegment] = []
    all_vias: list[TraceVia] = []
    nets_exported = 0
    nets_failed = 0
    warnings: list[str] = []

    for net_name, path in routes.items():
        if not path.success:
            nets_failed += 1
            warnings.append(f"Net {net_name} routing failed: {path.failure_reason}")
            continue

        # Determine trace width for this net
        trace_width = trace_widths.get(net_name, default_trace_width) if trace_widths else default_trace_width

        # Convert path to geometry
        segments = path_to_segments(path, origin, path.cell_size, trace_width, layer_map)
        
        # Use explicit vias (e.g. via arrays) if present, otherwise infer from layer transitions
        if path.explicit_vias:
            vias = path.explicit_vias
        else:
            vias = path_to_vias(path, origin, path.cell_size, via_size, via_drill, layer_map)

        all_segments.extend(segments)
        all_vias.extend(vias)
        nets_exported += 1

    # Deduplicate vias to avoid holes_co_located violations
    unique_vias = deduplicate_vias(all_vias)
    
    # Extract pad centers for endpoint snapping
    pad_centers = extract_pad_centers(board)
    
    # Snap segment endpoints to pad centers to eliminate dangling tracks
    snapped_count = 0
    for seg in all_segments:
        if seg.net in pad_centers:
            net_pads = pad_centers[seg.net]
            # Snap start point
            new_start = snap_to_nearest_pad(seg.start[0], seg.start[1], net_pads)
            if new_start != seg.start:
                seg.start = new_start
                snapped_count += 1
            # Snap end point
            new_end = snap_to_nearest_pad(seg.end[0], seg.end[1], net_pads)
            if new_end != seg.end:
                seg.end = new_end
                snapped_count += 1
    
    if snapped_count > 0:
        print(f"Snapped {snapped_count} segment endpoints to pad centers")

    # Add geometry to board
    segments_added = add_segments_to_board(board, all_segments)
    vias_added = add_vias_to_board(board, unique_vias)

    # Write output file
    output_pcb = Path(output_pcb)
    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    board.to_file(str(output_pcb))

    return ExportResult(
        output_path=output_pcb,
        segments_added=segments_added,
        vias_added=vias_added,
        nets_exported=nets_exported,
        nets_failed=nets_failed,
        warnings=warnings,
    )

from temper_placer.routing.constraints.spatial_index import Track as GeoTrack, Via as GeoVia

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
    layer_map = layer_map or DEFAULT_LAYER_MAP
    
    # Load PCB
    board = KiBoard.from_file(str(template_pcb))
    
    # Clear existing traces/vias
    board.traceItems = [
        item for item in board.traceItems 
        if not isinstance(item, (Segment, Via))
    ]
    
    total_segments = 0
    total_vias = 0
    
    # Helper to find net code
    def get_net_code(net_name: str) -> int:
        for n in board.nets:
            if n.name == net_name:
                return n.number
        return 0

    # Add tracks
    for track in tracks:
        layer_name = layer_map.get(track.layer, "F.Cu")
        net_code = get_net_code(track.net)
        
        segment = Segment(
            start=Position(X=track.start.x, Y=track.start.y),
            end=Position(X=track.end.x, Y=track.end.y),
            width=track.width,
            layer=layer_name,
            net=net_code,
            tstamp=str(uuid.uuid4()),
        )
        board.traceItems.append(segment)
        total_segments += 1
        
    # Add vias
    for via in vias:
        net_code = get_net_code(via.net)
        kicad_via = Via(
            position=Position(X=via.center.x, Y=via.center.y),
            size=via.diameter,
            drill=via.drill,
            layers=["F.Cu", "B.Cu"], # Default through
            net=net_code,
            tstamp=str(uuid.uuid4()),
        )
        board.traceItems.append(kicad_via)
        total_vias += 1
        
    # Write output
    board.to_file(str(output_pcb))
    
    # from temper_placer.routing.maze_router import RoutePath # Ensure type is known if needed
    
    return ExportResult(
        output_path=output_pcb,
        segments_added=total_segments,
        vias_added=total_vias,
        nets_exported=len(set(t.net for t in tracks)),
        nets_failed=0, # Geometric export doesn't track failures directly
        warnings=[]
    )
