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
        # THT pads have either:
        # 1. Both F.Cu and B.Cu explicitly
        # 2. Wildcard *.Cu (all copper layers)
        if 'F.Cu' in self.layers and 'B.Cu' in self.layers:
            return True
        # Check for wildcard copper layers
        for layer in self.layers:
            if '*.Cu' in layer or layer == '*.Cu':
                return True
        return False
    
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
        routing_layer: str,
        routed_segments: dict[str, list] | None = None,
        clearance: float = 0.2,
        trace_width: float = 0.25
    ) -> ConnectionPoint | None:
        """
        Get connection point for pad on specified routing layer.
        
        Args:
            pad: Pad to connect
            routing_layer: Layer where routing will occur
            routed_segments: Dict of layer -> list of ExactSegment for escape validation
            clearance: Minimum clearance for escape traces
            trace_width: Trace width for escape traces
        
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
        # Pass routed_segments to check escape trace validity
        via_position = self._find_via_position_for_pad(
            pad, routed_segments, clearance, trace_width
        )
        
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
    
    def _find_via_position_for_pad(
        self, 
        pad: Pad,
        routed_segments: dict[str, list] | None = None,
        clearance: float = 0.2,
        trace_width: float = 0.25
    ) -> tuple[float, float] | None:
        """
        Find legal via position for pad with escape trace validation.
        
        Strategy (adjusted for DRC compliance):
        1. Skip "near pad" - hole clearance makes it impossible
        2. Use fanout zone (1.5-10mm) - maintains proper clearances
        3. Try more angles for dense connectors
        4. Check escape trace doesn't cross existing routes
        5. Give up if no space
        
        Note: With via drill=0.4mm and hole_clearance=0.15mm, vias must be
        at least ~0.85mm from pad centers to maintain clearance.
        """
        from shapely.geometry import LineString
        
        # Try multiple radii with 16 directions for better coverage
        angles = [i * 22.5 for i in range(16)]  # 0, 22.5, 45, ... 337.5
        
        pad_layer = self._get_primary_copper_layer(pad)
        
        def is_escape_clear(via_pos: tuple[float, float]) -> bool:
            """Check if escape trace from pad to via is clear of existing routes."""
            if routed_segments is None:
                return True
            
            escape_line = LineString([pad.position, via_pos])
            # PHASE 1 FIX: Use 50% clearance for escape traces to allow dense fanout
            # Escape traces are short and can use tighter spacing for IC fanout
            escape_clearance = clearance * 0.5
            
            for existing_seg in routed_segments.get(pad_layer, []):
                if existing_seg.net_name == pad.net:
                    continue
                existing_line = existing_seg.as_linestring()
                # Check intersection - this is critical (would cause short)
                if escape_line.intersects(existing_line):
                    return False
                # Check clearance - use reduced clearance for escape traces
                # This allows fanout from dense ICs while staying DRC-compliant
                if escape_line.distance(existing_line) < escape_clearance:
                    return False
            return True
        
        # First try: Medium distance (1.5-3mm) for normal fanout
        for radius in [1.5, 2.0, 2.5, 3.0]:
            for angle_deg in angles:
                angle = math.radians(angle_deg)
                x = pad.position[0] + radius * math.cos(angle)
                y = pad.position[1] + radius * math.sin(angle)
                
                # Check via position AND escape trace
                if self.via_planner._is_position_legal((x, y)) and is_escape_clear((x, y)):
                    return (x, y)
        
        # Second try: Larger fanout zone (3.5-10mm) for dense connectors
        for radius in [3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0]:
            for angle_deg in angles:
                angle = math.radians(angle_deg)
                x = pad.position[0] + radius * math.cos(angle)
                y = pad.position[1] + radius * math.sin(angle)
                
                if self.via_planner._is_position_legal((x, y)) and is_escape_clear((x, y)):
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
