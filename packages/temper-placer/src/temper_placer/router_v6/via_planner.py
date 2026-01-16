"""
Via placement and management during routing.

ViaPlanner places vias during routing (not post-process) with:
- Collision detection (via-via, via-pad, via-track)
- Via reuse for same net
- Obstacle tracking (vias become obstacles)
- Search for legal placement positions
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING
import math

from .via_model import ViaSpec, can_place_via

if TYPE_CHECKING:
    from shapely.geometry import Polygon

try:
    from shapely.geometry import Point, Polygon as ShapelyPolygon
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


@dataclass
class PlacedVia:
    """
    A via that has been placed on the board.
    
    Attributes:
        position: (x, y) coordinates in mm
        spec: Via specifications
        layers: List of layers via connects
        net: Net name this via belongs to
    """
    position: tuple[float, float]
    spec: ViaSpec
    layers: list[str]
    net: str
    
    def keepout_zone(self) -> "Polygon":
        """Get the keepout zone polygon for this via"""
        if not SHAPELY_AVAILABLE:
            raise ImportError("Shapely required for keepout zones")
        return Point(self.position).buffer(self.spec.keepout_radius)
    
    def distance_to(self, position: tuple[float, float]) -> float:
        """Calculate distance from this via to a position"""
        return math.sqrt(
            (self.position[0] - position[0])**2 + 
            (self.position[1] - position[1])**2
        )


class ViaPlanner:
    """
    Intelligent via placement manager.
    
    Responsibilities:
    1. Check via placement legality (clearance, board bounds)
    2. Track placed vias as obstacles
    3. Reuse vias when possible (same net, close position)
    4. Search for legal via locations near desired position
    """
    
    def __init__(self, board_area: "Polygon", via_spec: ViaSpec, copper_layers: list[str] | None = None):
        """
        Initialize via planner.
        
        Args:
            board_area: Board outline polygon
            via_spec: Via specifications to use
            copper_layers: List of copper layer names (default: 2-layer F.Cu, B.Cu)
        """
        if not SHAPELY_AVAILABLE:
            raise ImportError("Shapely required for via planning")
        
        self.board_area = board_area
        self.via_spec = via_spec
        
        # Track placed vias
        self.placed_vias: list[PlacedVia] = []
        
        # Copper layers (default 4-layer board for Temper)
        self.copper_layers = copper_layers or ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']
        
        # Obstacles per layer
        self.obstacles: dict[str, list[ShapelyPolygon]] = {
            layer: [] for layer in self.copper_layers
        }
        
        # Track pad positions for hole clearance checking
        # List of (position, drill_size) tuples
        self.pad_holes: list[tuple[tuple[float, float], float]] = []
    
    @property
    def via_count(self) -> int:
        """Total number of placed vias"""
        return len(self.placed_vias)
    
    def add_obstacle(self, obstacle: "Polygon", layer: str):
        """
        Add an obstacle on a specific layer.
        
        Args:
            obstacle: Obstacle polygon
            layer: Layer name
        """
        if layer in self.obstacles:
            self.obstacles[layer].append(obstacle)
    
    def register_pad(self, position: tuple[float, float], pad_size: float = 0.8):
        """
        Register a pad position for hole clearance checking.
        
        Via drill holes must maintain clearance from ALL pads (SMD and THT).
        
        Args:
            position: Pad center (x, y)
            pad_size: Pad copper size/diameter (mm) - for SMD or THT annular ring
        """
        self.pad_holes.append((position, pad_size))
    
    def place_via(
        self,
        position: tuple[float, float],
        from_layer: str,
        to_layer: str,
        net: str
    ) -> PlacedVia | None:
        """
        Place a via at specified position.
        
        Args:
            position: Desired (x, y) position
            from_layer: Source layer
            to_layer: Destination layer
            net: Net name
        
        Returns:
            PlacedVia if successful, None if placement illegal
        """
        # Check for via reuse (same net, close position)
        for existing_via in self.placed_vias:
            if existing_via.net == net:
                dist = existing_via.distance_to(position)
                # If within 0.2mm, reuse existing via
                if dist < 0.2:
                    return existing_via
        
        # Check if position is within board bounds
        if not self.via_spec.is_within_bounds(position, self.board_area):
            return None
        
        # Check clearance to ALL obstacles on ALL layers
        # (Vias are through-hole, affect all layers)
        for layer, layer_obstacles in self.obstacles.items():
            if not can_place_via(position, self.via_spec, layer_obstacles):
                return None
        
        # Check clearance to existing vias
        for existing_via in self.placed_vias:
            if existing_via.spec.keepouts_overlap(
                existing_via.position,
                position,
                self.via_spec
            ):
                return None
        
        # Check hole clearance with pads (CRITICAL for DRC)
        # Via drill hole must be > hole_clearance from ALL pad copper
        for pad_pos, pad_size in self.pad_holes:
            if not self.via_spec.has_hole_clearance_to_pad(
                via_pos=position,
                pad_pos=pad_pos,
                pad_size=pad_size
            ):
                return None  # DRC violation: via hole too close to pad copper
        
        # Create via
        # For through-hole, connect all copper layers
        if self.via_spec.type.spans_all_layers():
            layers = self.copper_layers
        else:
            layers = [from_layer, to_layer]
        
        via = PlacedVia(
            position=position,
            spec=self.via_spec,
            layers=layers,
            net=net
        )
        
        # Add via to placed list
        self.placed_vias.append(via)
        
        # Add via keepout as obstacle on all layers
        via_keepout = via.keepout_zone()
        for layer in self.obstacles.keys():
            self.obstacles[layer].append(via_keepout)
        
        return via
    
    def get_via_at(
        self,
        position: tuple[float, float],
        tolerance: float = 0.1
    ) -> PlacedVia | None:
        """
        Get via at or near position.
        
        Args:
            position: Position to check
            tolerance: Distance tolerance (mm)
        
        Returns:
            PlacedVia if found within tolerance, None otherwise
        """
        for via in self.placed_vias:
            if via.distance_to(position) < tolerance:
                return via
        return None
    
    def get_vias_for_net(self, net: str) -> list[PlacedVia]:
        """Get all vias for a specific net"""
        return [v for v in self.placed_vias if v.net == net]
    
    def find_via_location_near(
        self,
        target: tuple[float, float],
        search_radius: float = 5.0,
        grid_step: float = 0.5
    ) -> tuple[float, float] | None:
        """
        Find legal via location near target position.
        
        Searches in expanding circles around target position.
        
        Args:
            target: Desired position
            search_radius: Maximum search distance (mm)
            grid_step: Grid resolution for search (mm)
        
        Returns:
            Legal position if found, None otherwise
        """
        # Try target position first
        if self._is_position_legal(target):
            return target
        
        # Search in expanding squares
        for radius in range(1, int(search_radius / grid_step) + 1):
            r = radius * grid_step
            
            # Try positions at this radius
            angles = [i * (2 * math.pi / 8) for i in range(8)]  # 8 directions
            for angle in angles:
                x = target[0] + r * math.cos(angle)
                y = target[1] + r * math.sin(angle)
                pos = (x, y)
                
                if self._is_position_legal(pos):
                    return pos
        
        return None
    
    def _is_position_legal(self, position: tuple[float, float]) -> bool:
        """Check if position is legal for via placement"""
        # Check board bounds
        if not self.via_spec.is_within_bounds(position, self.board_area):
            return False
        
        # Check clearance to obstacles
        for layer_obstacles in self.obstacles.values():
            if not can_place_via(position, self.via_spec, layer_obstacles):
                return False
        
        # Check clearance to existing vias
        for existing_via in self.placed_vias:
            if existing_via.spec.keepouts_overlap(
                existing_via.position,
                position,
                self.via_spec
            ):
                return False
        
        return True
