"""
Pad-to-layer connection management.

Handles transitions between pad layers and routing layers via vias.

Key Concepts:
- Pads exist on specific layers (F.Cu, B.Cu, or both for THT)
- Routing may occur on different layers (In1.Cu, In2.Cu)
- Vias bridge the gap between pad layer and routing layer
- Dense ICs require "fanout" - via placed away from pad
"""

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .via_planner import ViaPlanner, PlacedVia


@dataclass
class Pad:
    """
    Pad representation for layer connection logic.
    
    Attributes:
        position: (x, y) coordinates in mm
        layers: List of copper layers pad exists on
        net: Net name
        ref: Component reference (e.g., 'U1')
        number: Pad number (e.g., '1', 'A6')
    """
    position: tuple[float, float]
    layers: list[str]
    net: str
    ref: str
    number: str
    
    def is_on_layer(self, layer: str) -> bool:
        """Check if pad exists on specified layer"""
        return layer in self.layers
    
    def is_tht(self) -> bool:
        """Check if pad is through-hole (exists on multiple layers)"""
        # THT pads have at least F.Cu and B.Cu
        return 'F.Cu' in self.layers and 'B.Cu' in self.layers
    
    def distance_to(self, other: "Pad") -> float:
        """Calculate distance to another pad"""
        return math.sqrt(
            (self.position[0] - other.position[0])**2 + 
            (self.position[1] - other.position[1])**2
        )


@dataclass
class ConnectionPoint:
    """
    Connection point for routing.
    
    Represents where router should connect to reach this pad.
    May include via if layer transition required.
    
    Attributes:
        position: Where router should connect (x, y)
        layer: Layer for routing connection
        via: Via object if transition required, None otherwise
        requires_escape: True if escape routing needed (dense IC)
    """
    position: tuple[float, float]
    layer: str
    via: "PlacedVia | None"
    requires_escape: bool = False


class PadLayerConnector:
    """
    Manages pad-to-layer connections via intelligent via placement.
    
    Strategies:
    1. Direct connection: Pad on routing layer → no via
    2. THT pad: Connects to all layers → no via
    3. Simple SMD: Via near pad (0.5-1mm)
    4. Dense IC: Via in fanout zone (2-5mm from pad)
    """
    
    def __init__(self, via_planner: "ViaPlanner"):
        """
        Initialize connector.
        
        Args:
            via_planner: ViaPlanner for placing vias
        """
        self.via_planner = via_planner
    
    def get_connection_point(
        self,
        pad: Pad,
        routing_layer: str
    ) -> ConnectionPoint | None:
        """
        Get connection point for pad on specified routing layer.
        
        Args:
            pad: Pad to connect
            routing_layer: Layer where routing will occur
        
        Returns:
            ConnectionPoint with via if needed, None if impossible
        """
        # Case 1: Pad on routing layer - direct connection
        if pad.is_on_layer(routing_layer):
            return ConnectionPoint(
                position=pad.position,
                layer=routing_layer,
                via=None,
                requires_escape=False
            )
        
        # Case 2: THT pad - connects to all layers
        if pad.is_tht():
            return ConnectionPoint(
                position=pad.position,
                layer=routing_layer,
                via=None,
                requires_escape=False
            )
        
        # Case 3: SMD pad needs via
        # Determine via placement strategy based on density
        via_position = self._find_via_position_for_pad(pad)
        
        if via_position is None:
            return None  # Can't place via
        
        # Place via
        pad_layer = self._get_primary_copper_layer(pad)
        via = self.via_planner.place_via(
            position=via_position,
            from_layer=pad_layer,
            to_layer=routing_layer,
            net=pad.net
        )
        
        if via is None:
            return None  # Via placement failed
        
        # Check if escape routing required
        dist = math.sqrt(
            (via_position[0] - pad.position[0])**2 + 
            (via_position[1] - pad.position[1])**2
        )
        requires_escape = dist > 0.5  # >0.5mm from pad = fanout
        
        return ConnectionPoint(
            position=via_position,
            layer=routing_layer,
            via=via,
            requires_escape=requires_escape
        )
    
    def _find_via_position_for_pad(self, pad: Pad) -> tuple[float, float] | None:
        """
        Find legal via position for pad.
        
        Strategy (adjusted for DRC compliance):
        1. Skip "near pad" - hole clearance makes it impossible
        2. Use fanout zone (1.5-5mm) - maintains proper clearances
        3. Give up if no space
        
        Note: With via drill=0.4mm and hole_clearance=0.25mm, vias must be
        at least ~1.0mm from IC pad centers to maintain clearance.
        """
        # First try: Medium distance (1.5-2.5mm) for normal fanout
        for radius in [1.5, 2.0, 2.5]:
            # Try 8 directions at this radius
            for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
                angle = math.radians(angle_deg)
                x = pad.position[0] + radius * math.cos(angle)
                y = pad.position[1] + radius * math.sin(angle)
                
                # Check if this position is legal
                if self.via_planner._is_position_legal((x, y)):
                    return (x, y)
        
        # Second try: Larger fanout zone (3-5mm) for dense ICs
        for radius in [3.0, 3.5, 4.0, 4.5, 5.0]:
            # Try 8 directions at this radius
            for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
                angle = math.radians(angle_deg)
                x = pad.position[0] + radius * math.cos(angle)
                y = pad.position[1] + radius * math.sin(angle)
                
                # Check if this position is legal
                if self.via_planner._is_position_legal((x, y)):
                    return (x, y)
        
        return None  # No legal position found
    
    def _get_primary_copper_layer(self, pad: Pad) -> str:
        """Get primary copper layer for pad"""
        # Prefer F.Cu, then B.Cu
        # Filter out wildcards (*.Cu) - only use specific layers
        copper_layers = [l for l in pad.layers if '.Cu' in l and not l.startswith('*')]
        
        if 'F.Cu' in copper_layers:
            return 'F.Cu'
        elif 'B.Cu' in copper_layers:
            return 'B.Cu'
        elif copper_layers:
            return copper_layers[0]
        else:
            # THT pads have *.Cu - default to F.Cu
            return 'F.Cu'
