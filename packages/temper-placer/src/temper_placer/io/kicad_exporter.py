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
from temper_placer.router_v6.grid_converter import grid_to_world
from temper_placer.router_v6 import _AdapterRoutePath as RoutePath
from temper_placer.router_v6.path_simplify import simplify_path
from temper_placer.core.board import STANDARD_LAYER_ORDER
from temper_placer.io.via_dedup import deduplicate_vias


# Layer mapping from grid layer index to KiCad layer name
DEFAULT_LAYER_MAP = {
    0: "F.Cu",    # Top copper (L1)
    1: "In1.Cu",  # Inner layer 1 (L2)
    2: "In2.Cu",  # Inner layer 2 (L3)
    3: "B.Cu",    # Bottom copper (L4)
}

# Standard 2-layer fallback
TWO_LAYER_MAP = {
    0: "F.Cu",
    1: "B.Cu",
}

# Endpoint snapping tolerance in mm (increased to handle grid alignment)
SNAP_TOLERANCE_MM = 0.5   # 0.5mm handles typical grid cell sizes (0.5mm spacing)

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
    tolerance: float = 0.15  # Sufficient for 0.25mm grid half-cell
) -> tuple[float, float]:
    """Snap coordinate to nearest pad center if within tolerance.
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
    """Convert path to trace segments."""
    segments = []

    # Prefer RoutePath.cells (the pathfinding result); fall back to
    # .segments or .coordinates for compatibility with RoutePath3D and
    # V6 router paths that have already converted to world coords.
    coords = []
    if hasattr(path, "cells") and getattr(path, "cells", None):
        path_cell_size = getattr(path, "cell_size", cell_size)
        layer_map = layer_map or DEFAULT_LAYER_MAP
        simplified = simplify_path(path.cells)
        for c in simplified:
            x, y = grid_to_world(c, origin, path_cell_size)
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
                net=net,
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
        layer_map = layer_map or DEFAULT_LAYER_MAP
        for c in path.cells:
            x, y = grid_to_world(c, origin, path_cell_size)
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
                    net=net,
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
    max_dist: float = 2.0
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
    """
    connectors = []
    
    # Organize segments by net for faster lookup
    segs_by_net = {}
    for seg in segments:
        if seg.net not in segs_by_net:
            segs_by_net[seg.net] = []
        segs_by_net[seg.net].append(seg)
        
    for net, pads in pad_centers.items():
        if net not in segs_by_net:
            continue
            
        net_segs = segs_by_net[net]
        
        # Collect all unique endpoints of existing segments
        endpoints = set()
        for seg in net_segs:
            endpoints.add(seg.start)
            endpoints.add(seg.end)
            
        # Check each pad
        for px, py in pads:
            # Is this pad already connected? (Exact match)
            is_connected = False
            for ex, ey in endpoints:
                if abs(ex - px) < 0.01 and abs(ey - py) < 0.01:
                    is_connected = True
                    break
            
            if is_connected:
                continue
                
            # Find nearest endpoint
            nearest_ep = None
            min_dist = float('inf')
            
            for ex, ey in endpoints:
                dist = math.sqrt((ex - px)**2 + (ey - py)**2)
                if dist < min_dist:
                    min_dist = dist
                    nearest_ep = (ex, ey)
            
            # If nearest endpoint is close enough, bridge it!
            if nearest_ep and min_dist < max_dist:
                # Use attributes from nearest segment to match width/layer
                # Need to find which segment has this endpoint
                ref_seg = None
                for seg in net_segs:
                    if seg.start == nearest_ep or seg.end == nearest_ep:
                        ref_seg = seg
                        break
                
                if ref_seg:
                    connectors.append(TraceSegment(
                        net=net,
                        start=nearest_ep,
                        end=(px, py),
                        width=ref_seg.width,
                        layer=ref_seg.layer
                    ))
                    # Add to endpoints so we don't try to connect again
                    endpoints.add((px, py))
                    
    return connectors



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
    auto_fill_zones: bool = True,
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

    # Determine layer map based on presence of inner layers
    has_inner_layers = False
    if hasattr(board, 'layers'):
        layer_names = [l.name for l in board.layers]
        if "In1.Cu" in layer_names or "In2.Cu" in layer_names:
            has_inner_layers = True
    
    layer_map_to_use = layer_map or (DEFAULT_LAYER_MAP if has_inner_layers else TWO_LAYER_MAP)
    
    # FIX: Clean up corrupt drills from kiutils import of template
    # kiutils < 1.4.9 has a bug parsing (drill (offset...)) which results in garbage data
    # that crashes export. We must strip this from SMD pads.
    if hasattr(board, 'footprints'):
        for fp in board.footprints:
            for pad in fp.pads:
                if pad.type == 'smd' and pad.drill is not None:
                    # If parse failed, it might have garbage in diameter or be a DrillDefinition object
                    # Safe bet: SMD pads shouldn't have drills in this context.
                    pad.drill = None

    for net_name, path in routes.items():
        # Check success if attribute exists (legacy), otherwise assume success if in dict
        if hasattr(path, 'success') and not path.success:
            nets_failed += 1
            warnings.append(f"Net {net_name} routing failed: {getattr(path, 'failure_reason', 'unknown')}")
            continue

        # Determine trace width for this net
        trace_width = trace_widths.get(net_name, default_trace_width) if trace_widths else default_trace_width

        # Determine cell size (use path's if available, else function arg)
        current_cell_size = getattr(path, 'cell_size', cell_size)

        # Convert path to geometry
        segments = path_to_segments(path, origin, current_cell_size, trace_width, layer_map_to_use)
        
        # Use explicit vias (e.g. via arrays) if present, otherwise infer from layer transitions
        if hasattr(path, 'explicit_vias') and path.explicit_vias:
            vias = path.explicit_vias
        else:
            vias = path_to_vias(path, origin, current_cell_size, via_size, via_drill, layer_map_to_use)

        all_segments.extend(segments)
        all_vias.extend(vias)
        nets_exported += 1

    # Deduplicate vias to avoid holes_co_located violations
    # Convert to hashable tuples first
    via_list = [tuple((v.position[0], v.position[1], tuple(sorted(v.layers)))) for v in all_vias]
    unique_vias_set = set(via_list)
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
    pad_centers = extract_pad_centers(board)
    connectors = _generate_connector_segments(all_segments, pad_centers, max_dist=2.0)
    if connectors:
        print(f"  INFO: Generated {len(connectors)} connector segments to bridge gaps")
        all_segments.extend(connectors)

    # Add geometry to board
    segments_added = add_segments_to_board(board, all_segments)
    vias_added = add_vias_to_board(board, unique_vias)
    # Write output file
    output_pcb = Path(output_pcb)
    output_pcb.parent.mkdir(parents=True, exist_ok=True)
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

from temper_placer.router_v6.constraints_spatial_index import Track as GeoTrack, Via as GeoVia

def export_board_state(
    template_pcb: Path,
    state: "BoardState",
    output_pcb: Path,
    auto_fill_zones: bool = True,
) -> ExportResult:
    """Export board state directly to KiCad PCB.
    
    This is the preferred high-level export function for the deterministic pipeline.
    It takes a BoardState and performs pad-center snapping to ensure DRC clean connectivity.
    
    Args:
        template_pcb: Input PCB path
        state: BoardState containing traces and vias
        output_pcb: Output PCB path
        auto_fill_zones: Whether to trigger zone filling
        
    Returns:
        ExportResult stats
    """
    # Load PCB
    board = KiBoard.from_file(str(template_pcb))
    
    # Clear existing traces/vias
    board.traceItems = []
    
    all_traces = list(state.routes)
    all_vias = list(state.vias)
    
    # Extract pad centers for endpoint snapping
    pad_centers = extract_pad_centers(board)
    
    # Clean up segments and snap
    # 1. Reject zero-length segments
    valid_traces = [t for t in all_traces if math.sqrt((t.start[0]-t.end[0])**2 + (t.start[1]-t.end[1])**2) > 0.001]
    
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
                
        clean_traces.append(TraceSegment(
            net=t.net,
            start=new_start,
            end=new_end,
            width=t.width,
            layer=t.layer
        ))

    if snapped_count > 0:
        print(f"  INFO: Snapped {snapped_count} traces to pad centers")

    # Add geometry to board
    segments_added = add_segments_to_board(board, clean_traces)
    
    # Deduplicate vias
    via_list = [TraceVia(
        net=v.net,
        position=v.position,
        size=v.width,
        drill=v.drill,
        layers=list(v.layers)
    ) for v in all_vias]
    unique_vias = deduplicate_vias(via_list)
    vias_added = add_vias_to_board(board, unique_vias)
    
    # Write output
    output_pcb = Path(output_pcb)
    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    board.to_file(str(output_pcb))
    
    # Automatically fill zones if requested
    if auto_fill_zones:
        from temper_placer.io.zone_filler import fill_zones_if_present
        fill_zones_if_present(output_pcb, verbose=True)

    return ExportResult(
        output_path=output_pcb,
        segments_added=segments_added,
        vias_added=vias_added,
        nets_exported=len(set(t.net for t in clean_traces)),
        nets_failed=0,
        warnings=[]
    )

import math

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
    board.traceItems = []
    
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
    
    return ExportResult(
        output_path=output_pcb,
        segments_added=total_segments,
        vias_added=total_vias,
        nets_exported=len(set(t.net for t in tracks)),
        nets_failed=0,
        warnings=[]
    )
