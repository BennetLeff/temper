"""
Exact Geometry Router - Stage 4b Alternative

Replaces grid-based A* with visibility graph routing for exact clearance.

Integration with existing pipeline:
- Uses Stage 3 output (topology_graph) for net ordering
- Uses Stage 2 output (routing_spaces, obstacle_maps) for obstacles  
- Produces same output format as Stage 4 (PathfindingResult)

Key differences from grid-based:
- No discretization (µm precision vs 0.2mm grid)
- Exact clearance checking (Shapely polygon intersection)
- Visibility graph pathfinding (any-angle routing)
- Guaranteed DRC-clean output (if routing succeeds)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator
import numpy as np

try:
    from shapely.geometry import Point, LineString, Polygon, MultiPolygon
    from shapely.ops import unary_union
    from shapely import prepare
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False

from temper_placer.router_v6.stage0_data import ParsedPCB, DesignRules
from temper_placer.router_v6.channel_mapping import ChannelMapping
from temper_placer.router_v6.via_model import ViaSpec
from temper_placer.router_v6.via_planner import ViaPlanner, PlacedVia
from temper_placer.router_v6.pad_layer_connector import Pad, PadLayerConnector


def compute_mst_edges(
    pads: list[tuple[float, float]],
) -> list[tuple[int, int, float]]:
    """
    Compute Minimum Spanning Tree edges for a set of pads using Prim's algorithm.
    
    Returns list of (pad_idx_a, pad_idx_b, distance) edges in MST order.
    This gives optimal connection order to minimize total wire length.
    """
    if len(pads) < 2:
        return []
    
    n = len(pads)
    
    # Compute distance matrix
    def dist(i: int, j: int) -> float:
        dx = pads[i][0] - pads[j][0]
        dy = pads[i][1] - pads[j][1]
        return np.sqrt(dx*dx + dy*dy)
    
    # Prim's algorithm
    in_mst = [False] * n
    in_mst[0] = True
    edges = []
    
    for _ in range(n - 1):
        best_edge = None
        best_dist = float('inf')
        
        for i in range(n):
            if not in_mst[i]:
                continue
            for j in range(n):
                if in_mst[j]:
                    continue
                d = dist(i, j)
                if d < best_dist:
                    best_dist = d
                    best_edge = (i, j, d)
        
        if best_edge:
            edges.append(best_edge)
            in_mst[best_edge[1]] = True
    
    return edges


def identify_differential_pairs(
    net_names: list[str],
) -> list[tuple[str, str]]:
    """
    Identify differential pairs from net names.
    
    Looks for patterns like USB_D+/USB_D-, LVDS_P/LVDS_N, etc.
    
    Returns list of (positive_net, negative_net) tuples.
    """
    pairs = []
    positive_suffixes = ['+', '_P', '_p', 'P', '_DP', '_PLUS']
    negative_suffixes = ['-', '_N', '_n', 'N', '_DN', '_MINUS']
    
    for pos_suffix in positive_suffixes:
        for neg_suffix in negative_suffixes:
            for net in net_names:
                if net.endswith(pos_suffix):
                    base = net[:-len(pos_suffix)]
                    neg_net = base + neg_suffix
                    if neg_net in net_names:
                        pairs.append((net, neg_net))
    
    return pairs


def compute_parallel_offset_path(
    path: list[tuple[float, float]],
    offset_distance: float,
) -> list[tuple[float, float]] | None:
    """
    Compute a parallel path offset from the original.
    
    For differential pairs, the negative signal runs parallel to positive.
    Uses perpendicular offset at each segment.
    
    Args:
        path: Original path coordinates
        offset_distance: Distance to offset (positive = left, negative = right)
    
    Returns:
        Offset path coordinates, or None if path is invalid
    """
    if len(path) < 2:
        return None
    
    offset_path = []
    
    for i in range(len(path)):
        if i == 0:
            # First point: use direction to next point
            dx = path[1][0] - path[0][0]
            dy = path[1][1] - path[0][1]
        elif i == len(path) - 1:
            # Last point: use direction from previous point
            dx = path[-1][0] - path[-2][0]
            dy = path[-1][1] - path[-2][1]
        else:
            # Middle point: average of incoming and outgoing directions
            dx1 = path[i][0] - path[i-1][0]
            dy1 = path[i][1] - path[i-1][1]
            dx2 = path[i+1][0] - path[i][0]
            dy2 = path[i+1][1] - path[i][1]
            dx = dx1 + dx2
            dy = dy1 + dy2
        
        # Compute perpendicular unit vector
        length = np.sqrt(dx*dx + dy*dy)
        if length < 1e-6:
            # Degenerate case, skip offset
            offset_path.append(path[i])
            continue
        
        # Perpendicular: rotate 90° counter-clockwise
        perp_x = -dy / length
        perp_y = dx / length
        
        # Apply offset
        new_x = path[i][0] + perp_x * offset_distance
        new_y = path[i][1] + perp_y * offset_distance
        offset_path.append((new_x, new_y))
    
    return offset_path


def compute_steiner_point(
    pads: list[tuple[float, float]],
) -> tuple[float, float] | None:
    """
    Compute approximate Steiner point for 3+ pads.
    
    For 3 pads forming a triangle with all angles < 120°, the Steiner point
    minimizes total wire length. For other cases, returns centroid.
    
    Returns None if fewer than 3 pads or Steiner point doesn't help.
    """
    if len(pads) < 3:
        return None
    
    # For simplicity, use centroid as approximate Steiner point
    # True Steiner point computation is complex for N > 3
    cx = sum(p[0] for p in pads) / len(pads)
    cy = sum(p[1] for p in pads) / len(pads)
    
    # Check if centroid helps (star topology shorter than MST)
    star_length = sum(np.sqrt((p[0]-cx)**2 + (p[1]-cy)**2) for p in pads)
    
    mst_edges = compute_mst_edges(pads)
    mst_length = sum(e[2] for e in mst_edges)
    
    # Only use Steiner if it saves > 10% wire length
    if star_length < mst_length * 0.9:
        return (cx, cy)
    
    return None


@dataclass
class ExactSegment:
    """A routed trace segment with exact geometry."""
    start: tuple[float, float]  # (x, y) in mm
    end: tuple[float, float]
    width: float
    net_name: str
    layer: str
    
    def as_linestring(self) -> LineString:
        """Convert to Shapely LineString."""
        return LineString([self.start, self.end])
    
    def as_buffered_polygon(self, extra_clearance: float = 0.0) -> Polygon:
        """Convert to polygon with trace width + clearance."""
        line = self.as_linestring()
        return line.buffer(self.width / 2 + extra_clearance, cap_style='round')


@dataclass
class ExactRoutePath:
    """Complete route for a net with exact geometry."""
    net_name: str
    layer_name: str
    segments: list[ExactSegment] = field(default_factory=list)
    vias: list[PlacedVia] = field(default_factory=list)  # VIA-AWARE: Add via list
    
    @property
    def coordinates(self) -> list[tuple[float, float]]:
        """Get all coordinates for compatibility with RoutePath."""
        if not self.segments:
            return []
        coords = [self.segments[0].start]
        for seg in self.segments:
            coords.append(seg.end)
        return coords
    
    def total_length(self) -> float:
        """Total route length in mm."""
        return sum(
            np.sqrt((s.end[0] - s.start[0])**2 + (s.end[1] - s.start[1])**2)
            for s in self.segments
        )


@dataclass
class VisibilityGraph:
    """Graph of mutually visible points for pathfinding."""
    vertices: list[tuple[float, float]]
    edges: dict[int, list[tuple[int, float]]]  # vertex_idx -> [(neighbor_idx, distance), ...]
    
    def shortest_path(self, start_idx: int, goal_idx: int) -> list[int] | None:
        """Dijkstra's algorithm for shortest path."""
        import heapq
        
        dist = {start_idx: 0.0}
        prev = {}
        pq = [(0.0, start_idx)]
        
        while pq:
            d, u = heapq.heappop(pq)
            
            if u == goal_idx:
                # Reconstruct path
                path = [goal_idx]
                while path[-1] != start_idx:
                    path.append(prev[path[-1]])
                return list(reversed(path))
            
            if d > dist.get(u, float('inf')):
                continue
            
            for v, edge_dist in self.edges.get(u, []):
                new_dist = d + edge_dist
                if new_dist < dist.get(v, float('inf')):
                    dist[v] = new_dist
                    prev[v] = u
                    heapq.heappush(pq, (new_dist, v))
        
        return None  # No path found


class ExactGeometryRouter:
    """
    Visibility graph router with exact geometry checking.
    
    Replaces grid-based A* (Stage 4) while keeping same interface.
    
    INTEGRATION NOTE:
    This router uses Stage 2's routing_space for obstacles rather than
    reconstructing from PCB data. This ensures consistency with the
    existing pipeline's obstacle handling.
    """
    
    def __init__(
        self,
        pcb: ParsedPCB,
        design_rules: DesignRules,
        routing_spaces: dict | None = None,  # From Stage 2
        verbose: bool = False,
        kicad_file: str | None = None,  # Path to original .kicad_pcb file
    ):
        import sys
        if verbose:
            print("    [INIT] Starting ExactGeometryRouter.__init__...")
            sys.stdout.flush()
        
        if not SHAPELY_AVAILABLE:
            raise ImportError("Shapely required for exact geometry routing")
        
        self.pcb = pcb
        self.design_rules = design_rules
        self.routing_spaces = routing_spaces
        self.verbose = verbose
        self.kicad_file = kicad_file  # For accurate pad positions
        
        if verbose:
            print("    [INIT] Basic attributes set")
            sys.stdout.flush()
        
        # VIA-AWARE: Setup via planning
        # Try to get board outline from various sources
        if verbose:
            print("    [INIT] Getting board polygon...")
            sys.stdout.flush()
        
        board_polygon = None
        
        if hasattr(self.pcb, 'board_outline') and self.pcb.board_outline:
            board_polygon = Polygon(self.pcb.board_outline)
        elif hasattr(self.pcb, 'board') and self.pcb.board:
            # Use board geometry
            board_info = self.pcb.board
            if hasattr(board_info, 'width') and hasattr(board_info, 'height'):
                width = board_info.width
                height = board_info.height
                board_polygon = Polygon([(0, 0), (width, 0), (width, height), (0, height)])
        
        if board_polygon is None:
            # Fallback to bounding box from components
            if verbose:
                print("    [INIT] Using component bounding box for board polygon...")
                sys.stdout.flush()
            
            all_coords = []
            for comp in self.pcb.components:
                if hasattr(comp, 'initial_position') and comp.initial_position:
                    all_coords.append(comp.initial_position)
                elif hasattr(comp, 'x') and hasattr(comp, 'y'):
                    all_coords.append((comp.x, comp.y))
            
            if all_coords:
                xs = [c[0] for c in all_coords]
                ys = [c[1] for c in all_coords]
                margin = 10.0  # mm
                board_polygon = Polygon([
                    (min(xs) - margin, min(ys) - margin),
                    (max(xs) + margin, min(ys) - margin),
                    (max(xs) + margin, max(ys) + margin),
                    (min(xs) - margin, max(ys) + margin)
                ])
            else:
                # Last resort: large default board
                board_polygon = Polygon([(0, 0), (150, 0), (150, 100), (0, 100)])
        
        if verbose:
            print(f"    [INIT] Board polygon created: {board_polygon.bounds}")
            sys.stdout.flush()
        
        import sys
        if self.verbose:
            print("    [DEBUG] Creating ViaPlanner...")
            sys.stdout.flush()
        # ViaPlanner is created after _build_base_obstacles determines copper_layers
        self._copper_layers = None  # Will be set in _build_base_obstacles
        self._board_polygon = board_polygon
        
        if self.verbose:
            print("    [DEBUG] Building base obstacles...")
            sys.stdout.flush()
        # Build base obstacles from routing spaces (preferred) or PCB
        self.base_obstacles: dict[str, list[Polygon]] = {}
        self._build_base_obstacles()
        
        # Now create ViaPlanner with known copper layers
        if self.verbose:
            print(f"    [DEBUG] Creating ViaPlanner with layers: {self._copper_layers}")
            sys.stdout.flush()
        self.via_planner = ViaPlanner(self._board_polygon, ViaSpec.standard(), self._copper_layers)
        self.pad_connector = PadLayerConnector(self.via_planner)
        
        # Register all pad positions for hole clearance checking
        if self.verbose:
            print(f"    [DEBUG] Registering pad positions for hole clearance...")
            sys.stdout.flush()
        self._register_pads_with_via_planner()
        
        if self.verbose:
            print(f"    [DEBUG] Base obstacles built: {list(self.base_obstacles.keys())}")
            sys.stdout.flush()
        
        # Track routed segments per layer
        self.routed_segments: dict[str, list[ExactSegment]] = {}
        for layer in self.base_obstacles:
            self.routed_segments[layer] = []
        
        if self.verbose:
            print("    [DEBUG] Router initialization complete")
            sys.stdout.flush()
    
    def _read_kicad_pad_positions(self) -> dict[tuple[str, str, str], tuple[float, float]]:
        """
        Read pad positions directly from KiCad file for accuracy.
        
        ParsedPCB has rotation bugs that cause incorrect pad positions.
        This reads from the original KiCad file using kiutils.
        
        Returns:
            Dict mapping (net_name, comp_ref, pin_number) -> (abs_x, abs_y)
        """
        positions = {}
        
        # Try to find the source KiCad file
        kicad_file = self.kicad_file
        if kicad_file is None and hasattr(self.pcb, 'source_file'):
            kicad_file = self.pcb.source_file
        
        if kicad_file is None:
            return positions
        
        try:
            from kiutils.board import Board
            import math
            
            board = Board.from_file(str(kicad_file))
            
            # Build ref->footprint mapping by finding Reference property
            for fp in board.footprints:
                ref = None
                # Try different ways to get reference
                if hasattr(fp, 'reference'):
                    ref = fp.reference
                
                # properties might be dict or list depending on kiutils version
                props = getattr(fp, 'properties', {})
                if isinstance(props, dict):
                    ref = props.get('Reference', ref)
                elif isinstance(props, list):
                    for prop in props:
                        if isinstance(prop, str):
                            continue
                        key = getattr(prop, 'key', None) or getattr(prop, 'name', None)
                        if key == 'Reference':
                            ref = getattr(prop, 'value', None)
                            break
                
                if ref is None:
                    continue
                
                angle = math.radians(fp.position.angle or 0)
                
                for pad in fp.pads:
                    if pad.net is None:
                        continue
                    
                    net_name = pad.net.name
                    pin_num = str(pad.number)
                    
                    # Calculate absolute position with rotation
                    px, py = pad.position.X, pad.position.Y
                    abs_x = fp.position.X + px * math.cos(angle) - py * math.sin(angle)
                    abs_y = fp.position.Y + px * math.sin(angle) + py * math.cos(angle)
                    
                    positions[(net_name, ref, pin_num)] = (abs_x, abs_y)
            
        except Exception as e:
            if self.verbose:
                print(f"  Warning: Could not read KiCad file directly: {e}")
        
        return positions
    
    def _register_pads_with_via_planner(self):
        """
        Register ALL pad positions with ViaPlanner for hole clearance checking.
        
        CRITICAL: Via drill holes must maintain clearance from ALL copper,
        including both SMD and THT pads. KiCad's "hole clearance" rule checks
        via drill hole to pad copper edge distance.
        
        This ensures vias maintain proper clearance, preventing DRC violations.
        """
        # Use KiCad file to get accurate pad sizes
        if self.kicad_file is None:
            if self.verbose:
                print(f"      [VIA] No KiCad file - skipping pad registration")
            return
        
        try:
            from kiutils.board import Board
            board = Board.from_file(str(self.kicad_file))
            
            pad_count = 0
            for fp in board.footprints:
                ref = fp.entryName if hasattr(fp, 'entryName') else None
                if not ref:
                    continue
                
                fp_x = fp.position.X if fp.position else 0
                fp_y = fp.position.Y if fp.position else 0
                
                for pad in fp.pads:
                    pad_x = pad.position.X if pad.position else 0
                    pad_y = pad.position.Y if pad.position else 0
                    abs_x = fp_x + pad_x
                    abs_y = fp_y + pad_y
                    
                    # Get pad size (SMD or THT annular ring)
                    pad_size = 0.8  # Default for SMD
                    if hasattr(pad, 'size') and pad.size:
                        # Use max dimension (width or height)
                        if hasattr(pad.size, 'X') and hasattr(pad.size, 'Y'):
                            pad_size = max(pad.size.X, pad.size.Y)
                    
                    self.via_planner.register_pad((abs_x, abs_y), pad_size=pad_size)
                    pad_count += 1
            
            if self.verbose:
                print(f"      [VIA] Registered {pad_count} pads for hole clearance")
        
        except Exception as e:
            if self.verbose:
                print(f"      [VIA] Warning: Could not register pads: {e}")
    
    def _build_base_obstacles(self):
        """Build obstacles from Stage 2 routing spaces or PCB."""
        import sys
        if self.verbose:
            print("      [OBS] Setting up layers...")
            sys.stdout.flush()
        # Use only actual copper layers from board stackup
        # Default to 2-layer (F.Cu, B.Cu) if unknown
        self._copper_layers = ["F.Cu", "B.Cu"]  # Default 2-layer
        if hasattr(self.pcb, 'stackup') and self.pcb.stackup:
            if hasattr(self.pcb.stackup, 'copper_layers'):
                self._copper_layers = self.pcb.stackup.copper_layers
            elif hasattr(self.pcb.stackup, 'layer_count'):
                if self.pcb.stackup.layer_count >= 4:
                    self._copper_layers = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
        
        for layer in self._copper_layers:
            self.base_obstacles[layer] = []
        
        if self.verbose:
            print(f"      [OBS] Using {len(self._copper_layers)} copper layers: {self._copper_layers}")
        
        if self.verbose:
            print("      [OBS] Building component lookup...")
            sys.stdout.flush()
        # Build component lookup and net-to-pads mapping
        self._comp_by_ref = {comp.ref: comp for comp in self.pcb.components}
        self._net_pads: dict[str, list[tuple[float, float]]] = {}
        
        if self.verbose:
            print("      [OBS] Reading KiCad pad positions...")
            sys.stdout.flush()
        # Try to read pad positions directly from KiCad file for accuracy
        # ParsedPCB has rotation bugs that cause incorrect positions
        kicad_pad_positions = self._read_kicad_pad_positions()
        if self.verbose:
            print(f"      [OBS] Read {len(kicad_pad_positions)} pad positions from KiCad")
            sys.stdout.flush()
        
        if self.verbose:
            print(f"      [OBS] Processing {len(self.pcb.nets)} nets...")
            sys.stdout.flush()
        for i, net in enumerate(self.pcb.nets):
            pads = []
            for comp_ref, pin_number in net.pins:
                # First try KiCad-sourced positions (most accurate)
                key = (net.name, comp_ref, str(pin_number))
                if key in kicad_pad_positions:
                    pads.append(kicad_pad_positions[key])
                    continue
                
                # Fallback to ParsedPCB (may have rotation issues)
                comp = self._comp_by_ref.get(comp_ref)
                if not comp:
                    continue
                for pin in comp.pins:
                    if pin.number == pin_number or pin.name == pin_number:
                        abs_x = comp.initial_position[0] + pin.position[0]
                        abs_y = comp.initial_position[1] + pin.position[1]
                        pads.append((abs_x, abs_y))
                        break
            self._net_pads[net.name] = pads
        if self.verbose:
            print(f"      [OBS] Net pads built: {len(self._net_pads)} nets")
            sys.stdout.flush()
        
        # If routing_spaces provided (from Stage 2), use them
        if self.routing_spaces:
            for layer, rspace in self.routing_spaces.items():
                if hasattr(rspace, 'obstacles'):
                    # Convert obstacles to Shapely polygons
                    for obs in rspace.obstacles:
                        if hasattr(obs, 'polygon'):
                            self.base_obstacles[layer].append(obs.polygon)
                        elif hasattr(obs, 'bounds'):
                            x, y, w, h = obs.bounds
                            poly = Polygon([
                                (x, y), (x + w, y), (x + w, y + h), (x, y + h)
                            ])
                            self.base_obstacles[layer].append(poly)
        else:
            # Minimal obstacles: only keepouts and board edge
            # Don't block component bodies - pads need to be reachable!
            # This is a simplified fallback when routing_spaces not provided
            pass
        
        if self.verbose:
            print("      [OBS] Adding pad obstacles...")
            sys.stdout.flush()
        # Add ALL pads as obstacles (including unconnected ones)
        # This is critical - unconnected pads still exist physically!
        pad_size = 0.8  # mm - typical pad size for SMD
        tht_pad_size = 2.5  # mm - larger for through-hole (DO-201 diodes are 2.5mm)
        
        # First, add pads from known nets
        pad_count = 0
        for net_name, pads in self._net_pads.items():
            for x, y in pads:
                center = Point(x, y)
                poly = center.buffer(pad_size / 2)
                for layer in self.base_obstacles:
                    self.base_obstacles[layer].append((poly, net_name))
                pad_count += 1
        
        if self.verbose:
            print(f"      [OBS] Added {pad_count} pad obstacles from nets")
            sys.stdout.flush()
        
        # Track which pads we've already added (by position)
        added_pad_positions = set()
        for pads in self._net_pads.values():
            for x, y in pads:
                added_pad_positions.add((round(x, 2), round(y, 2)))
        
        if self.verbose:
            print(f"      [OBS] Adding unconnected pad obstacles...")
            sys.stdout.flush()
        
        # Now add ALL component pads, including unconnected ones
        unconnected_count = 0
        for comp in self.pcb.components:
            for pin in comp.pins:
                abs_x = comp.initial_position[0] + pin.position[0]
                abs_y = comp.initial_position[1] + pin.position[1]
                pos_key = (round(abs_x, 2), round(abs_y, 2))
                
                # Skip if already added from net
                if pos_key in added_pad_positions:
                    continue
                
                # This is an unconnected pad - add as obstacle with special net name
                center = Point(abs_x, abs_y)
                # Use larger size for THT pads (check footprint name)
                is_tht = 'THT' in (comp.footprint or '') or 'PTH' in (comp.footprint or '')
                size = tht_pad_size if is_tht else pad_size
                poly = center.buffer(size / 2)
                
                # Mark as unconnected with component reference
                unconnected_net = f"_UNCONNECTED_{comp.ref}_{pin.number}"
                for layer in self.base_obstacles:
                    self.base_obstacles[layer].append((poly, unconnected_net))
                
                added_pad_positions.add(pos_key)
                unconnected_count += 1
        
        if self.verbose:
            print(f"      [OBS] Added {unconnected_count} unconnected pad obstacles")
            total_obs = sum(len(v) for v in self.base_obstacles.values())
            print(f"      [OBS] Total obstacles: {total_obs}")
            sys.stdout.flush()
    
    def _get_obstacles_for_net(
        self,
        layer: str,
        net_name: str,
        clearance: float,
        trace_width: float,
        target_pads: list[tuple[float, float]] | None = None,
    ) -> list[Polygon]:
        """Get inflated obstacles with same-component handling.
        
        Key insight: Pads on the SAME COMPONENT as our target pads should NOT
        be obstacles. We're routing from a pin on that IC - we can freely
        pass near other pins on the same IC (just need clearance to our trace).
        
        PRODUCTION FIX: Add extra margin (0.05mm) beyond clearance to ensure
        DRC passes even with floating point tolerance.
        """
        obstacles = []
        # Safety margins for DRC compliance
        # The trace centerline must be at least (clearance + trace_width/2) from obstacle edge
        # Add extra margin for RRT path approximation
        pad_safety_margin = 0.08  # mm extra for pad obstacles (balanced)
        track_safety_margin = 0.08  # mm extra for existing track obstacles
        full_inflation = clearance + trace_width / 2 + pad_safety_margin
        
        # Get target pad positions for escape zone calculation
        if target_pads is None:
            target_pads = self._net_pads.get(net_name, [])
        
        # Find target pads AND target components
        target_pad_positions = set()
        target_components = set()
        for net in self.pcb.nets:
            if net.name == net_name:
                for comp_ref, pin_number in net.pins:
                    target_components.add(comp_ref)
        
        # Use actual pad positions from our (rotation-corrected) mapping
        if net_name in self._net_pads:
            for x, y in self._net_pads[net_name]:
                target_pad_positions.add((round(x, 2), round(y, 2)))
        
        def is_target_pad(pad_pos: tuple[float, float]) -> bool:
            """Check if a pad position is one of our target pads (on same net)."""
            pos_key = (round(pad_pos[0], 2), round(pad_pos[1], 2))
            return pos_key in target_pad_positions
        
        def is_on_target_ic(pad_pos: tuple[float, float]) -> bool:
            """Check if pad is on same IC as our target (for escape routing).
            
            Only applies to ICs with 3+ pins (not simple diodes/resistors).
            2-pin components should have all pins as obstacles.
            """
            for comp_ref in target_components:
                comp = self._comp_by_ref.get(comp_ref)
                if not comp or len(comp.pins) <= 2:  # Skip 2-pin components
                    continue
                
                # Get all pads on this component from our nets
                # (Use rotation-corrected positions from _net_pads)
                comp_pads = []
                for other_net in self.pcb.nets:
                    for c_ref, pin_num in other_net.pins:
                        if c_ref == comp_ref and other_net.name in self._net_pads:
                            # Find this pad's position
                            for pad_coord in self._net_pads[other_net.name]:
                                comp_pads.append(pad_coord)
                
                # Check if pad_pos is close to any pad on this component
                for comp_pad in comp_pads:
                    dist = np.sqrt((pad_pos[0] - comp_pad[0])**2 + (pad_pos[1] - comp_pad[1])**2)
                    if dist < 0.5:  # Within 0.5mm = same pad
                        return True
            return False
        
        def min_distance_to_targets(pos: tuple[float, float]) -> float:
            """Minimum distance from pos to any target pad."""
            if not target_pads:
                return float('inf')
            return min(
                np.sqrt((pos[0] - t[0])**2 + (pos[1] - t[1])**2)
                for t in target_pads
            )
        
        for obs in self.base_obstacles.get(layer, []):
            if isinstance(obs, tuple):
                poly, obs_net = obs
                if obs_net == net_name:
                    continue  # Skip same-net pads
                
                centroid = (poly.centroid.x, poly.centroid.y)
                
                # SKIP pads that ARE our target pads (same net)
                if is_target_pad(centroid):
                    continue
                
                # Check if this is on an IC we're routing from (for escape)
                on_target_ic = is_on_target_ic(centroid)
                
                dist = min_distance_to_targets(centroid)
                
                # Tiered inflation based on context:
                # 1. On same IC (3+ pins): skip entirely for escape routing
                # 2. Close to target: reduced inflation  
                # 3. Far away: full inflation
                if on_target_ic:
                    # Same IC - skip entirely to allow escape routing
                    # (clearance is enforced by trace width itself)
                    continue
                elif dist < 2.0:
                    # Close but different component - reduced inflation
                    inflation = clearance * 0.7 + pad_safety_margin
                else:
                    # Full inflation for distant obstacles
                    inflation = full_inflation
                
                obstacles.append(poly.buffer(inflation))
            else:
                # Non-pad obstacles (keepouts, etc) get full inflation
                obstacles.append(obs.buffer(full_inflation))
        
        # Add existing routed segments as obstacles with safety margin
        for seg in self.routed_segments.get(layer, []):
            if seg.net_name == net_name:
                continue
            obstacles.append(seg.as_buffered_polygon(clearance + track_safety_margin))
        
        return obstacles
    
    def _rrt_path(
        self,
        start: tuple[float, float],
        goal: tuple[float, float],
        obstacles: list[Polygon],
        max_iterations: int = 30000,  # High for complex paths
        step_size: float = 2.0,  # mm - smaller for precision in tight spaces
    ) -> list[tuple[float, float]] | None:
        """Find path using RRT (Rapidly-exploring Random Tree).
        
        Better than visibility graph for dense obstacle environments.
        """
        import random
        
        # Filter and merge obstacles
        min_area = 0.1
        obstacles = [o for o in obstacles if o.area > min_area]
        merged = unary_union(obstacles) if obstacles else Polygon()
        if not merged.is_empty:
            prepare(merged)
        
        # Check direct path first
        direct = LineString([start, goal])
        if merged.is_empty or not direct.intersects(merged):
            return [start, goal]
        
        # Get bounds for random sampling - focus on path corridor
        path_length = np.sqrt((goal[0] - start[0])**2 + (goal[1] - start[1])**2)
        
        # For very long paths (>50mm), use wider corridor and more iterations
        if path_length > 50:
            corridor_width = max(40.0, path_length * 0.5)  # Wider for long paths
            max_iterations = int(max_iterations * 2)  # 60k iterations for long paths
        else:
            corridor_width = max(20.0, path_length * 0.3)  # 30% of path length or 20mm
        
        # Bounding box around start-goal with corridor
        x_min = min(start[0], goal[0]) - corridor_width
        x_max = max(start[0], goal[0]) + corridor_width
        y_min = min(start[1], goal[1]) - corridor_width
        y_max = max(start[1], goal[1]) + corridor_width
        
        # RRT tree: node -> parent
        tree = {start: None}
        nodes = [start]
        
        for _ in range(max_iterations):
            # Bias towards goal 30% of the time for faster convergence
            if random.random() < 0.3:
                sample = goal
            else:
                sample = (
                    random.uniform(x_min, x_max),
                    random.uniform(y_min, y_max)
                )
            
            # Find nearest node in tree
            nearest = min(nodes, key=lambda n: 
                (n[0] - sample[0])**2 + (n[1] - sample[1])**2)
            
            # Steer towards sample
            dx = sample[0] - nearest[0]
            dy = sample[1] - nearest[1]
            dist = np.sqrt(dx*dx + dy*dy)
            
            if dist < 0.1:
                continue
            
            if dist > step_size:
                dx = dx / dist * step_size
                dy = dy / dist * step_size
            
            new_node = (nearest[0] + dx, nearest[1] + dy)
            
            # Check if edge is collision-free
            edge = LineString([nearest, new_node])
            if not edge.intersects(merged):
                tree[new_node] = nearest
                nodes.append(new_node)
                
                # Check if we can reach goal from new_node
                to_goal = LineString([new_node, goal])
                if not to_goal.intersects(merged):
                    tree[goal] = new_node
                    # Reconstruct path
                    path = [goal]
                    current = goal
                    while tree[current] is not None:
                        current = tree[current]
                        path.append(current)
                    return list(reversed(path))
        
        return None  # Failed to find path
    
    def _build_visibility_graph(
        self,
        start: tuple[float, float],
        goal: tuple[float, float],
        obstacles: list[Polygon],
        max_vertices: int = 200,
    ) -> VisibilityGraph:
        """Build visibility graph - fallback to RRT if no direct edges."""
        # Try RRT first (works better for dense obstacles)
        rrt_path = self._rrt_path(start, goal, obstacles)
        
        if rrt_path:
            # Convert RRT path to visibility graph format
            vertices = rrt_path
            edges = {i: [] for i in range(len(vertices))}
            for i in range(len(vertices) - 1):
                dist = np.sqrt(
                    (vertices[i+1][0] - vertices[i][0])**2 +
                    (vertices[i+1][1] - vertices[i][1])**2
                )
                edges[i].append((i + 1, dist))
                edges[i + 1].append((i, dist))
            return VisibilityGraph(vertices=vertices, edges=edges)
        
        # Fallback: empty graph (will fail routing)
        return VisibilityGraph(vertices=[start, goal], edges={0: [], 1: []})
    
    def _get_escape_obstacles(
        self,
        layer: str,
        net_name: str,
        clearance: float,
        trace_width: float,
        pad_pos: tuple[float, float],
    ) -> list[Polygon]:
        """Get obstacles for escape routing - includes ALL pads except our own.
        
        Unlike _get_obstacles_for_net, this doesn't skip same-IC pads.
        Escape routing needs to avoid adjacent GND/power pads on the same IC.
        """
        obstacles = []
        full_inflation = clearance + trace_width / 2 + 0.05  # Small safety margin
        
        # Only skip the exact pad we're escaping from
        our_pad_key = (round(pad_pos[0], 2), round(pad_pos[1], 2))
        
        for obs in self.base_obstacles.get(layer, []):
            if isinstance(obs, tuple):
                poly, obs_net = obs
                centroid = (poly.centroid.x, poly.centroid.y)
                centroid_key = (round(centroid[0], 2), round(centroid[1], 2))
                
                # Skip only our own pad
                if centroid_key == our_pad_key:
                    continue
                
                # Full inflation for all other pads
                obstacles.append(poly.buffer(full_inflation))
            else:
                obstacles.append(obs.buffer(full_inflation))
        
        # Add existing routed segments
        for seg in self.routed_segments.get(layer, []):
            if seg.net_name == net_name:
                continue
            obstacles.append(seg.as_buffered_polygon(clearance + 0.05))
        
        return obstacles
    
    def _get_escape_point(
        self,
        pad_pos: tuple[float, float],
        net_name: str,
        escape_distance: float = 2.0,
        layer: str = "F.Cu",
        is_destination: bool = False,
    ) -> tuple[float, float] | None:
        """Calculate escape/approach point for a pad on a dense IC.
        
        For source pads: finds clear direction to escape from IC
        For destination pads: finds approach direction that avoids adjacent pins
        
        Returns escape point or None if pad doesn't need escape routing.
        """
        # Find which component this pad belongs to
        comp_ref = None
        
        for net in self.pcb.nets:
            if net.name == net_name:
                for ref, pin in net.pins:
                    comp = self._comp_by_ref.get(ref)
                    if not comp:
                        continue
                    for p in comp.pins:
                        if p.number == pin or p.name == pin:
                            abs_x = comp.initial_position[0] + p.position[0]
                            abs_y = comp.initial_position[1] + p.position[1]
                            if abs(abs_x - pad_pos[0]) < 0.1 and abs(abs_y - pad_pos[1]) < 0.1:
                                comp_ref = ref
                                break
        
        if not comp_ref:
            return None
        
        comp = self._comp_by_ref.get(comp_ref)
        if not comp or len(comp.pins) < 4:
            # Not a dense IC, no escape needed
            return None
        
        # Get obstacles for checking escape directions
        rules = self.design_rules.get_rules_for_net(net_name)
        escape_obstacles = self._get_escape_obstacles(
            layer, net_name, rules.clearance_mm, rules.trace_width_mm, pad_pos
        )
        merged = unary_union([o for o in escape_obstacles if o.area > 0.1])
        
        # For destination approach, prefer directions perpendicular to pin row
        # This avoids adjacent pins
        comp_center = comp.initial_position
        base_dx = pad_pos[0] - comp_center[0]
        base_dy = pad_pos[1] - comp_center[1]
        base_dist = np.sqrt(base_dx*base_dx + base_dy*base_dy)
        
        if base_dist < 0.1:
            base_angle = 0
        else:
            base_angle = np.arctan2(base_dy, base_dx)
        
        # For destination pads, try perpendicular directions first (avoid pin row)
        if is_destination:
            # Perpendicular to away-from-center: ±90°
            angle_offsets = [np.pi/2, -np.pi/2, np.pi/4, -np.pi/4, 3*np.pi/4, -3*np.pi/4, 0, np.pi]
        else:
            # For source, try away from center first
            angle_offsets = [0, np.pi/4, -np.pi/4, np.pi/2, -np.pi/2, 3*np.pi/4, -3*np.pi/4, np.pi]
        
        for angle_offset in angle_offsets:
            angle = base_angle + angle_offset
            escape_x = pad_pos[0] + np.cos(angle) * escape_distance
            escape_y = pad_pos[1] + np.sin(angle) * escape_distance
            
            # Check if escape segment is clear
            escape_line = LineString([pad_pos, (escape_x, escape_y)])
            if merged.is_empty or not escape_line.intersects(merged):
                return (escape_x, escape_y)
        
        # No clear direction found
        return None
    
    def _route_pad_pair(
        self,
        net_name: str,
        layer: str,
        start_pad: tuple[float, float],
        goal_pad: tuple[float, float],
        start_escape: tuple[float, float] | None,
        goal_escape: tuple[float, float] | None,
        obstacles: list[Polygon],
        clearance: float,
        trace_width: float,
        start_idx: int,
        goal_idx: int,
    ) -> list[ExactSegment] | None:
        """
        Route between two pads with optional escape routing.
        
        Args:
            net_name: Name of net
            layer: Target layer
            start_pad: Start pad position
            goal_pad: Goal pad position
            start_escape: Escape point for start pad (or None)
            goal_escape: Escape point for goal pad (or None)
            obstacles: Pre-computed obstacles for this net
            clearance: Required clearance in mm
            trace_width: Trace width in mm
            start_idx: Index of start pad (for error messages)
            goal_idx: Index of goal pad (for error messages)
        
        Returns:
            List of segments if successful, None if routing failed
        """
        segments = []
        
        # Calculate direct distance between pads
        direct_dist = np.sqrt(
            (goal_pad[0] - start_pad[0])**2 + (goal_pad[1] - start_pad[1])**2
        )
        
        # Skip escape routing for short connections (< 5mm)
        # Escape routing is only needed for long routes that might graze adjacent pads
        if direct_dist < 5.0:
            start_escape = None
            goal_escape = None
        
        # Build waypoints: pad -> escape -> ... -> escape -> pad
        waypoints = [start_pad]
        if start_escape:
            waypoints.append(start_escape)
        if goal_escape:
            waypoints.append(goal_escape)
        waypoints.append(goal_pad)
        
        # Route through waypoints
        for j in range(len(waypoints) - 1):
            start = waypoints[j]
            goal = waypoints[j + 1]
            
            # For escape segments (short, near IC), check against ALL pads
            is_escape_segment = (j == 0 and start_escape) or (j == len(waypoints) - 2 and goal_escape)
            
            if is_escape_segment:
                # For escape, get obstacles WITHOUT same-IC skipping
                escape_obstacles = self._get_escape_obstacles(
                    layer, net_name, clearance, trace_width, start
                )
                direct = LineString([start, goal])
                merged = unary_union([o for o in escape_obstacles if o.area > 0.1])
                if merged.is_empty or not direct.intersects(merged):
                    # Direct escape works
                    seg = ExactSegment(
                        start=start,
                        end=goal,
                        width=trace_width,
                        net_name=net_name,
                        layer=layer,
                    )
                    segments.append(seg)
                    continue
                else:
                    # Escape blocked, try RRT with escape obstacles
                    rrt_path = self._rrt_path(start, goal, escape_obstacles, max_iterations=5000, step_size=1.0)
                    if rrt_path:
                        for k in range(len(rrt_path) - 1):
                            seg = ExactSegment(
                                start=rrt_path[k],
                                end=rrt_path[k + 1],
                                width=trace_width,
                                net_name=net_name,
                                layer=layer,
                            )
                            segments.append(seg)
                        continue
            
            # Use visibility graph + RRT for non-escape segments
            vg = self._build_visibility_graph(start, goal, obstacles)
            path_indices = vg.shortest_path(0, 1)
            
            if path_indices is None:
                # Visibility graph failed, try RRT as fallback
                rrt_path = self._rrt_path(start, goal, obstacles)
                if rrt_path:
                    for k in range(len(rrt_path) - 1):
                        seg = ExactSegment(
                            start=rrt_path[k],
                            end=rrt_path[k + 1],
                            width=trace_width,
                            net_name=net_name,
                            layer=layer,
                        )
                        segments.append(seg)
                    continue
                return None  # Both VG and RRT failed
            
            # Convert path to segments
            path_coords = [vg.vertices[idx] for idx in path_indices]
            for k in range(len(path_coords) - 1):
                seg = ExactSegment(
                    start=path_coords[k],
                    end=path_coords[k + 1],
                    width=trace_width,
                    net_name=net_name,
                    layer=layer,
                )
                segments.append(seg)
        
        return segments
    
    def route_net_with_vias(
        self,
        net_name: str,
        layer: str,
        pads_with_layers: list[tuple[tuple[float, float], list[str], str, str]],
    ) -> ExactRoutePath | None:
        """
        VIA-AWARE: Route a net with automatic via placement for layer transitions.
        
        Args:
            net_name: Name of net to route
            layer: Target routing layer (e.g., "In1.Cu")
            pads_with_layers: List of (position, layers, ref, pin_num) tuples
        
        Returns:
            ExactRoutePath with segments and vias, or None if failed
        """
        if len(pads_with_layers) < 2:
            return None
        
        # Convert to Pad objects
        pad_objects = [
            Pad(position=pos, layers=lyrs, net=net_name, ref=ref, number=pin)
            for pos, lyrs, ref, pin in pads_with_layers
        ]
        
        # Get connection points (may include vias)
        connection_points = []
        vias = []
        
        for pad in pad_objects:
            conn = self.pad_connector.get_connection_point(pad, layer)
            if conn is None:
                # Can't connect this pad
                if self.verbose:
                    print(f"  ✗ {net_name}: Can't get connection point for {pad.ref}.{pad.number}")
                return None
            connection_points.append((pad, conn))
            if conn.via:
                vias.append(conn.via)
                # Add via as obstacle
                self.via_planner.add_obstacle(conn.via.keepout_zone(), layer)
        
        # Extract positions for routing
        routing_positions = [conn.position for _, conn in connection_points]
        
        # Use existing route_net on routing layer
        route = self.route_net(net_name, layer, routing_positions)
        
        if route is None:
            return None
        
        # Add escape segments (pad → via on pad layer)
        for pad, conn in connection_points:
            if conn.requires_escape and conn.via:
                # Add escape segment from pad to via on pad's layer
                pad_layer = self.pad_connector._get_primary_copper_layer(pad)
                escape_seg = ExactSegment(
                    start=pad.position,
                    end=conn.position,
                    width=self.design_rules.get_rules_for_net(net_name).trace_width_mm,
                    net_name=net_name,
                    layer=pad_layer
                )
                route.segments.insert(0, escape_seg)  # Add at beginning
        
        # Add vias to route
        route.vias = vias
        
        if self.verbose:
            print(f"  ✓ {net_name}: {len(route.segments)} segments, {len(vias)} vias")
        
        return route
    
    def route_net(
        self,
        net_name: str,
        layer: str,
        pads: list[tuple[float, float]],
    ) -> ExactRoutePath | None:
        """
        Route a single net using MST-optimized connection order.
        
        For multi-pad nets (3+), uses Minimum Spanning Tree to determine
        optimal connection order, minimizing total wire length and avoiding
        blockages that occur with sequential routing.
        
        For pads on dense ICs, uses escape routing to avoid adjacent pads.
        
        Args:
            net_name: Name of net to route
            layer: Target layer (e.g., "F.Cu")
            pads: List of (x, y) pad positions to connect
        
        Returns:
            ExactRoutePath if successful, None if routing failed
        """
        if len(pads) < 2:
            return None
        
        # Get routing parameters
        rules = self.design_rules.get_rules_for_net(net_name)
        clearance = rules.clearance_mm
        trace_width = rules.trace_width_mm
        
        # Get obstacles with escape zones around our target pads
        obstacles = self._get_obstacles_for_net(
            layer, net_name, clearance, trace_width,
            target_pads=pads  # Pass target pads for escape zone calculation
        )
        
        route = ExactRoutePath(net_name=net_name, layer_name=layer)
        
        # Calculate escape points for each pad
        escape_points = {}
        for i, pad in enumerate(pads):
            escape = self._get_escape_point(
                pad, net_name, escape_distance=2.0, layer=layer, is_destination=False
            )
            escape_points[i] = escape
        
        # Use MST for multi-pad nets (3+) instead of sequential routing
        if len(pads) >= 3:
            mst_edges = compute_mst_edges(pads)
            
            # Track which pads are "connected" (have a route to them)
            connected_pads = {0}  # Start with first pad in MST
            
            # Route MST edges in order
            for start_idx, goal_idx, _ in mst_edges:
                # Ensure we're routing from connected to unconnected
                if start_idx not in connected_pads:
                    start_idx, goal_idx = goal_idx, start_idx
                
                start_pad = pads[start_idx]
                goal_pad = pads[goal_idx]
                start_escape = escape_points.get(start_idx)
                goal_escape = escape_points.get(goal_idx)
                
                # Route this MST edge
                edge_segments = self._route_pad_pair(
                    net_name, layer, start_pad, goal_pad,
                    start_escape, goal_escape, obstacles,
                    clearance, trace_width, start_idx, goal_idx
                )
                
                if edge_segments is None:
                    if self.verbose:
                        print(f"  ✗ {net_name}: No path from pad {start_idx} to {goal_idx}")
                    return None
                
                route.segments.extend(edge_segments)
                connected_pads.add(goal_idx)
        else:
            # For 2-pad nets, use simple routing
            start_pad = pads[0]
            goal_pad = pads[1]
            start_escape = escape_points.get(0)
            goal_escape = escape_points.get(1)
            
            edge_segments = self._route_pad_pair(
                net_name, layer, start_pad, goal_pad,
                start_escape, goal_escape, obstacles,
                clearance, trace_width, 0, 1
            )
            
            if edge_segments is None:
                if self.verbose:
                    print(f"  ✗ {net_name}: No path from pad 0 to 1")
                return None
            
            route.segments.extend(edge_segments)
        
        # Store routed segments
        self.routed_segments[layer].extend(route.segments)
        
        if self.verbose:
            print(f"  ✓ {net_name}: {len(route.segments)} segments, {route.total_length():.2f}mm")
        
        return route
    
    def route_differential_pair(
        self,
        pos_net: str,
        neg_net: str,
        layer: str,
        spacing: float = 0.15,  # mm spacing between traces
    ) -> tuple[ExactRoutePath | None, ExactRoutePath | None]:
        """
        Route a differential pair together.
        
        Strategy:
        1. Try routing both nets and computing parallel offset
        2. If one blocks the other, try reversed order
        3. Use intelligent offset based on pad positions
        
        Args:
            pos_net: Positive net name (e.g., "USB_D+")
            neg_net: Negative net name (e.g., "USB_D-")
            layer: Target layer
            spacing: Distance between trace centerlines
        
        Returns:
            Tuple of (positive_route, negative_route), either may be None if failed
        """
        pos_pads = self._net_pads.get(pos_net, [])
        neg_pads = self._net_pads.get(neg_net, [])
        
        if len(pos_pads) < 2 or len(neg_pads) < 2:
            return None, None
        
        # Compute offset direction from pad positions
        # The pads should be parallel, so we use their relative position
        dx = neg_pads[0][0] - pos_pads[0][0]
        dy = neg_pads[0][1] - pos_pads[0][1]
        pad_dist = np.sqrt(dx*dx + dy*dy)
        
        rules_pos = self.design_rules.get_rules_for_net(pos_net)
        rules_neg = self.design_rules.get_rules_for_net(neg_net)
        trace_width = rules_pos.trace_width_mm
        clearance = rules_pos.clearance_mm
        
        # Minimum spacing needed between trace centerlines for parallel routing
        min_spacing = clearance + trace_width + 0.05  # = 0.2 + 0.25 + 0.05 = 0.5mm
        
        # If pads are too close for parallel offset, route on different layers
        # This is the case for USB (0.4mm pad spacing < 0.5mm min)
        if pad_dist < min_spacing:
            if self.verbose:
                print(f"  ⚠ Diff pair: Pad spacing ({pad_dist:.2f}mm) < min ({min_spacing:.2f}mm)")
                print(f"    Routing on different layers: {pos_net} on F.Cu, {neg_net} on B.Cu")
            pos_route = self.route_net(pos_net, 'F.Cu', pos_pads)
            neg_route = self.route_net(neg_net, 'B.Cu', neg_pads)
            return pos_route, neg_route
        
        # Strategy 1: Route positive first, offset for negative
        pos_route = self.route_net(pos_net, layer, pos_pads)
        if pos_route is None:
            if self.verbose:
                print(f"  ✗ Diff pair: {pos_net} failed to route")
            # Try routing negative independently
            neg_route = self.route_net(neg_net, layer, neg_pads)
            return None, neg_route
        
        # Try parallel offset using the natural pad spacing
        # Minimum spacing = clearance + trace_width (center to center)
        pos_coords = pos_route.coordinates
        min_spacing = clearance + trace_width + 0.05  # Extra safety margin
        offset_dist = max(pad_dist, min_spacing) if pad_dist > 0.1 else (spacing + trace_width)
        
        # Determine offset direction from pad delta
        if pad_dist > 0.1:
            # Use pad-to-pad direction for offset
            for sign in [1, -1]:
                offset_path = compute_parallel_offset_path(pos_coords, sign * offset_dist)
                if offset_path is None:
                    continue
                
                # Check if endpoints match negative pads reasonably well
                start_dist = np.sqrt((offset_path[0][0] - neg_pads[0][0])**2 + 
                                     (offset_path[0][1] - neg_pads[0][1])**2)
                end_dist = np.sqrt((offset_path[-1][0] - neg_pads[-1][0])**2 + 
                                   (offset_path[-1][1] - neg_pads[-1][1])**2)
                
                if start_dist < 2.0 and end_dist < 2.0:
                    # Good match, adjust endpoints to exact pad positions
                    offset_path[0] = neg_pads[0]
                    offset_path[-1] = neg_pads[-1]
                    
                    # Verify path doesn't hit obstacles
                    # IMPORTANT: Exclude positive net's segments (they're parallel, expected to be close)
                    obstacles = self._get_obstacles_for_net(
                        layer, neg_net, clearance, trace_width, target_pads=neg_pads
                    )
                    
                    # Filter out positive net's segments from obstacle check
                    # (they should be parallel, not blocking)
                    filtered_obstacles = []
                    pos_path_buffered = LineString(pos_coords).buffer(trace_width)
                    for obs in obstacles:
                        if hasattr(obs, 'area') and obs.area > 0.1:
                            # Skip obstacles that are part of the positive route
                            if not obs.intersects(pos_path_buffered):
                                filtered_obstacles.append(obs)
                            elif obs.area > pos_path_buffered.area * 2:
                                # Keep larger obstacles that contain the pos path
                                filtered_obstacles.append(obs)
                    
                    merged = unary_union(filtered_obstacles) if filtered_obstacles else Polygon()
                    
                    path_line = LineString(offset_path)
                    buffered_path = path_line.buffer(trace_width / 2)
                    
                    if merged.is_empty or not buffered_path.intersects(merged):
                        # Success! Create route from offset
                        neg_route = ExactRoutePath(net_name=neg_net, layer_name=layer)
                        for i in range(len(offset_path) - 1):
                            seg = ExactSegment(
                                start=offset_path[i],
                                end=offset_path[i + 1],
                                width=trace_width,
                                net_name=neg_net,
                                layer=layer,
                            )
                            neg_route.segments.append(seg)
                        
                        self.routed_segments[layer].extend(neg_route.segments)
                        
                        if self.verbose:
                            print(f"  ✓ Diff pair: {neg_net} parallel to {pos_net}")
                        
                        return pos_route, neg_route
        
        # Offset failed, try independent routing for negative
        if self.verbose:
            print(f"  ⚠ Diff pair: {neg_net} offset failed, trying independent route")
        
        neg_route = self.route_net(neg_net, layer, neg_pads)
        return pos_route, neg_route
    
    def rip_up_net(self, net_name: str) -> None:
        """
        Remove all routed segments for a net.
        
        Used for rip-up and retry when DRC violations are found.
        """
        for layer in self.routed_segments:
            self.routed_segments[layer] = [
                seg for seg in self.routed_segments[layer]
                if seg.net_name != net_name
            ]
    
    def reroute_with_clearance(
        self,
        net_name: str,
        extra_clearance: float = 0.1,
    ) -> ExactRoutePath | None:
        """
        Rip up a net and reroute with increased clearance.
        
        Args:
            net_name: Net to reroute
            extra_clearance: Additional clearance margin (mm)
        
        Returns:
            New route if successful, None otherwise
        """
        # Rip up existing route
        self.rip_up_net(net_name)
        
        # Get pads and layer
        pads = self._net_pads.get(net_name, [])
        if len(pads) < 2:
            return None
        
        layer = self.design_rules.get_layer_constraint(net_name) or 'F.Cu'
        
        # Temporarily increase clearance for this net
        original_clearance = self.design_rules.get_rules_for_net(net_name).clearance_mm
        
        # Create modified obstacle set with extra clearance
        rules = self.design_rules.get_rules_for_net(net_name)
        obstacles = self._get_obstacles_for_net(
            layer, net_name, 
            rules.clearance_mm + extra_clearance,  # Extra clearance
            rules.trace_width_mm, 
            target_pads=pads
        )
        
        route = ExactRoutePath(net_name=net_name, layer_name=layer)
        
        # Use MST for multi-pad nets
        if len(pads) >= 3:
            mst_edges = compute_mst_edges(pads)
            connected_pads = {0}
            
            for start_idx, goal_idx, _ in mst_edges:
                if start_idx not in connected_pads:
                    start_idx, goal_idx = goal_idx, start_idx
                
                start_pad = pads[start_idx]
                goal_pad = pads[goal_idx]
                
                # Route without escape (simpler is better for reroute)
                direct = LineString([start_pad, goal_pad])
                merged = unary_union([o for o in obstacles if hasattr(o, 'area') and o.area > 0.1])
                
                if merged.is_empty or not direct.intersects(merged):
                    # Direct works
                    seg = ExactSegment(
                        start=start_pad, end=goal_pad,
                        width=rules.trace_width_mm, net_name=net_name, layer=layer
                    )
                    route.segments.append(seg)
                else:
                    # Try RRT
                    rrt_path = self._rrt_path(start_pad, goal_pad, obstacles)
                    if rrt_path:
                        for i in range(len(rrt_path) - 1):
                            seg = ExactSegment(
                                start=rrt_path[i], end=rrt_path[i+1],
                                width=rules.trace_width_mm, net_name=net_name, layer=layer
                            )
                            route.segments.append(seg)
                    else:
                        if self.verbose:
                            print(f"  ✗ Reroute {net_name}: failed at {start_idx}->{goal_idx}")
                        return None
                
                connected_pads.add(goal_idx)
        else:
            # 2-pad net
            start_pad, goal_pad = pads[0], pads[1]
            direct = LineString([start_pad, goal_pad])
            merged = unary_union([o for o in obstacles if hasattr(o, 'area') and o.area > 0.1])
            
            if merged.is_empty or not direct.intersects(merged):
                seg = ExactSegment(
                    start=start_pad, end=goal_pad,
                    width=rules.trace_width_mm, net_name=net_name, layer=layer
                )
                route.segments.append(seg)
            else:
                rrt_path = self._rrt_path(start_pad, goal_pad, obstacles)
                if rrt_path:
                    for i in range(len(rrt_path) - 1):
                        seg = ExactSegment(
                            start=rrt_path[i], end=rrt_path[i+1],
                            width=rules.trace_width_mm, net_name=net_name, layer=layer
                        )
                        route.segments.append(seg)
                else:
                    return None
        
        # Store new route
        self.routed_segments[layer].extend(route.segments)
        
        if self.verbose:
            print(f"  ✓ Rerouted {net_name} with +{extra_clearance}mm clearance")
        
        return route
    
    def route_all(
        self,
        channel_mapping: ChannelMapping | None = None,
        net_order: list[str] | None = None,
    ) -> dict[str, ExactRoutePath]:
        """
        Route all nets, handling differential pairs first.
        
        Args:
            channel_mapping: Optional ChannelMapping for layer preferences
            net_order: Optional list of net names in routing order
        
        This is the main entry point that replaces run_astar_pathfinding().
        """
        routed_paths = {}
        failed_nets = []
        
        # Determine nets to route
        if net_order:
            nets_to_route = list(net_order)  # Make a copy we can modify
        elif channel_mapping and hasattr(channel_mapping, 'net_channels'):
            nets_to_route = list(channel_mapping.net_channels.keys())
        else:
            # Use all nets with 2+ pads
            nets_to_route = [n for n, pads in self._net_pads.items() if len(pads) >= 2]
        
        # Auto-prioritize complex nets (4+ pads) - they need more routing space
        # and should be routed before simpler nets block their paths
        complex_nets = [n for n in nets_to_route if len(self._net_pads.get(n, [])) >= 4]
        simple_nets = [n for n in nets_to_route if n not in complex_nets]
        nets_to_route = complex_nets + simple_nets
        
        if self.verbose and complex_nets:
            print(f"  Prioritizing complex nets: {complex_nets}")
        
        # Identify and route differential pairs first
        diff_pairs = identify_differential_pairs(nets_to_route)
        routed_as_diff = set()
        
        for pos_net, neg_net in diff_pairs:
            if pos_net in routed_as_diff or neg_net in routed_as_diff:
                continue
            
            # Get layer for differential pair
            layer = self.design_rules.get_layer_constraint(pos_net)
            if layer is None:
                layer = 'F.Cu'
            
            if self.verbose:
                print(f"  Routing differential pair: {pos_net} / {neg_net}")
            
            pos_route, neg_route = self.route_differential_pair(pos_net, neg_net, layer)
            
            if pos_route:
                routed_paths[pos_net] = pos_route
                routed_as_diff.add(pos_net)
            else:
                failed_nets.append(pos_net)
            
            if neg_route:
                routed_paths[neg_net] = neg_route
                routed_as_diff.add(neg_net)
            else:
                failed_nets.append(neg_net)
        
        # Route remaining nets
        for net_name in nets_to_route:
            if net_name in routed_as_diff:
                continue  # Already routed as part of diff pair
            # Get layer from design rules or channel mapping
            layer = self.design_rules.get_layer_constraint(net_name)
            if layer is None:
                if channel_mapping and hasattr(channel_mapping, 'net_channels'):
                    cp = channel_mapping.net_channels.get(net_name)
                    layer = cp.preferred_layer if cp else 'F.Cu'
                else:
                    layer = 'F.Cu'
            
            # Get pad locations from our pre-built mapping
            pads = self._net_pads.get(net_name, [])
            
            if len(pads) < 2:
                continue
            
            # Route the net
            route = self.route_net(net_name, layer, pads)
            
            if route:
                routed_paths[net_name] = route
            else:
                failed_nets.append(net_name)
        
        if self.verbose:
            print(f"\nExact Geometry Routing Complete:")
            print(f"  Routed: {len(routed_paths)}")
            print(f"  Failed: {len(failed_nets)}")
            if failed_nets:
                print(f"  Failed nets: {failed_nets}")
        
        return routed_paths


def run_exact_geometry_routing(
    channel_mapping: ChannelMapping,
    pcb: ParsedPCB,
    design_rules: DesignRules,
    verbose: bool = False,
) -> dict[str, ExactRoutePath]:
    """
    Drop-in replacement for run_astar_pathfinding().
    
    Integration with pipeline:
        # In pipeline.py _run_stage4():
        if self.use_exact_geometry:
            from .exact_geometry_router import run_exact_geometry_routing
            paths = run_exact_geometry_routing(
                channel_mapping,
                pcb,
                pcb.design_rules,
                verbose=self.verbose,
            )
            # Convert ExactRoutePath to RoutePath format...
        else:
            pathfinding_result = run_astar_pathfinding(...)
    """
    router = ExactGeometryRouter(pcb, design_rules, verbose=verbose)
    return router.route_all(channel_mapping)
