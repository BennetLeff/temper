"""
Via specifications and placement model.

This module provides the foundation for via-aware routing:
- ViaSpec: Physical via specifications and clearance calculations
- ViaType: Enumeration of via types (through-hole, blind, buried, microvia)
- Via placement validation functions

Design Principles:
1. Vias are first-class routing primitives, not post-processing hacks
2. All via placement must respect clearance rules
3. Via keepout zones prevent collisions
"""

from dataclasses import dataclass
from enum import Enum
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shapely.geometry import Polygon, Point

try:
    from shapely.geometry import Point
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


class ViaType(Enum):
    """Types of vias in PCB design"""
    THROUGH_HOLE = "through"  # Connects all layers (F.Cu to B.Cu)
    BLIND = "blind"           # Connects outer layer to inner layer
    BURIED = "buried"         # Connects inner layers only
    MICROVIA = "micro"        # Small laser-drilled via (typically 1 layer)
    
    def spans_all_layers(self) -> bool:
        """Check if via type connects all layers"""
        return self == ViaType.THROUGH_HOLE


@dataclass
class ViaSpec:
    """
    Physical specifications for a via.
    
    Attributes:
        diameter: Outer diameter of via annular ring (mm)
        drill: Drill hole diameter (mm)
        clearance: Minimum clearance to copper (mm)
        type: Via type (through-hole, blind, buried, microvia)
        margin: Safety margin beyond clearance (mm)
    """
    diameter: float
    drill: float
    clearance: float
    type: ViaType
    margin: float = 0.1  # Safety margin
    
    @classmethod
    def standard(cls) -> "ViaSpec":
        """Standard via for 4-layer board (most common)"""
        return cls(
            diameter=0.8,
            drill=0.4,
            clearance=0.2,
            type=ViaType.THROUGH_HOLE,
            margin=0.1
        )
    
    @classmethod
    def microvia(cls) -> "ViaSpec":
        """Microvia for high-density routing (laser drilled)"""
        return cls(
            diameter=0.4,
            drill=0.2,
            clearance=0.15,
            type=ViaType.MICROVIA,
            margin=0.05
        )
    
    @classmethod
    def large(cls) -> "ViaSpec":
        """Large via for high-current applications"""
        return cls(
            diameter=1.2,
            drill=0.6,
            clearance=0.25,
            type=ViaType.THROUGH_HOLE,
            margin=0.15
        )
    
    @property
    def keepout_radius(self) -> float:
        """
        Total exclusion radius for via placement.
        
        This is the minimum distance from via center to any obstacle.
        Includes: annular ring radius + clearance + safety margin
        """
        return (self.diameter / 2) + self.clearance + self.margin
    
    @property
    def min_spacing(self) -> float:
        """
        Minimum center-to-center spacing between two vias.
        
        Two vias of this type must be at least this far apart
        to avoid keepout zone overlap.
        """
        return 2 * self.keepout_radius
    
    @property
    def annular_area(self) -> float:
        """
        Area of the annular ring (copper donut around hole).
        
        Used for current capacity calculations.
        """
        outer_radius = self.diameter / 2
        hole_radius = self.drill / 2
        return math.pi * (outer_radius**2 - hole_radius**2)
    
    def holes_overlap(
        self,
        pos1: tuple[float, float],
        pos2: tuple[float, float],
        other: "ViaSpec"
    ) -> bool:
        """
        Check if drill holes would physically overlap.
        
        Args:
            pos1: Position of this via (x, y)
            pos2: Position of other via (x, y)
            other: Specification of other via
        
        Returns:
            True if holes overlap (manufacturing error)
        """
        distance = math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)
        min_hole_spacing = (self.drill / 2) + (other.drill / 2)
        return distance < min_hole_spacing
    
    def keepouts_overlap(
        self,
        pos1: tuple[float, float],
        pos2: tuple[float, float],
        other: "ViaSpec"
    ) -> bool:
        """
        Check if keepout zones would overlap.
        
        Args:
            pos1: Position of this via (x, y)
            pos2: Position of other via (x, y)
            other: Specification of other via
        
        Returns:
            True if keepout zones overlap (DRC violation)
        """
        distance = math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)
        min_keepout_spacing = self.keepout_radius + other.keepout_radius
        return distance < min_keepout_spacing
    
    def is_within_bounds(
        self,
        position: tuple[float, float],
        board_area: "Polygon"
    ) -> bool:
        """
        Check if via can be placed within board boundaries.
        
        Args:
            position: Via position (x, y)
            board_area: Board outline polygon
        
        Returns:
            True if via (including keepout) fits within board
        """
        if not SHAPELY_AVAILABLE:
            return True  # Can't check without shapely
        
        via_point = Point(position)
        
        # Check if center is inside board
        if not board_area.contains(via_point):
            return False
        
        # Check if keepout zone fits (distance from edge)
        distance_to_edge = via_point.distance(board_area.boundary)
        return distance_to_edge >= self.keepout_radius


def can_place_via(
    position: tuple[float, float],
    via_spec: ViaSpec,
    obstacles: list["Polygon"]
) -> bool:
    """
    Check if via can be legally placed at position.
    
    Args:
        position: Desired via position (x, y)
        via_spec: Via specifications
        obstacles: List of obstacle polygons (pads, tracks, other vias)
    
    Returns:
        True if via can be placed without violations
    """
    if not SHAPELY_AVAILABLE:
        return True
    
    # Create via keepout zone
    via_keepout = Point(position).buffer(via_spec.keepout_radius)
    
    # Check clearance to all obstacles
    for obstacle in obstacles:
        if via_keepout.intersects(obstacle):
            return False
    
    return True
