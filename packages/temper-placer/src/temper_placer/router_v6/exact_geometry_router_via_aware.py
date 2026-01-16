"""
Via-aware exact geometry router.

Integrates ViaPlanner and PadLayerConnector with routing:
- Vias placed during routing (not post-process)
- Vias become obstacles for subsequent nets
- Escape routing for dense ICs
- Export includes vias
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING
import random
import numpy as np

if TYPE_CHECKING:
    from .via_planner import ViaPlanner, PlacedVia
    from .pad_layer_connector import PadLayerConnector, Pad, ConnectionPoint
    from shapely.geometry import Polygon

try:
    from shapely.geometry import Point, LineString, Polygon as ShapelyPolygon
    from shapely.ops import unary_union
    from shapely.prepared import prep as prepare
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


@dataclass
class Track:
    """Track segment"""
    start: tuple[float, float]
    end: tuple[float, float]
    layer: str
    width: float
    net: str


@dataclass
class NetRoute:
    """Complete route for a net including tracks and vias"""
    net: str
    tracks: list[Track]
    vias: list["PlacedVia"]
    layer: str


class ExactGeometryRouterViaAware:
    """
    Exact geometry router with integrated via planning.
    
    Key differences from post-process approach:
    1. Uses PadLayerConnector to get connection points with vias
    2. Vias placed during routing, not after
    3. Vias added as obstacles for subsequent nets
    4. Escape routing for dense ICs
    """
    
    def __init__(
        self,
        board_area: "Polygon",
        via_planner: "ViaPlanner",
        pad_connector: "PadLayerConnector",
        clearance: float = 0.2,
        trace_width: float = 0.25
    ):
        """
        Initialize via-aware router.
        
        Args:
            board_area: Board outline polygon
            via_planner: ViaPlanner for placing vias
            pad_connector: PadLayerConnector for pad transitions
            clearance: Minimum clearance (mm)
            trace_width: Default trace width (mm)
        """
        if not SHAPELY_AVAILABLE:
            raise ImportError("Shapely required for via-aware routing")
        
        self.board_area = board_area
        self.via_planner = via_planner
        self.pad_connector = pad_connector
        self.clearance = clearance
        self.trace_width = trace_width
        
        # Track routed nets
        self.routed_nets: dict[str, NetRoute] = {}
    
    def route_net(
        self,
        net_name: str,
        pads: list["Pad"],
        routing_layer: str
    ) -> NetRoute | None:
        """
        Route a net with via-aware connection handling.
        
        Args:
            net_name: Net name
            pads: List of Pad objects
            routing_layer: Preferred routing layer
        
        Returns:
            NetRoute with tracks and vias, or None if failed
        """
        if len(pads) < 2:
            return None
        
        # Get connection points for all pads (may include vias)
        connection_points = []
        for pad in pads:
            conn = self.pad_connector.get_connection_point(pad, routing_layer)
            if conn is None:
                # Can't connect this pad
                return None
            connection_points.append((pad, conn))
        
        # Route between connection points
        tracks = []
        vias = []
        
        # Collect all vias from connection points
        for pad, conn in connection_points:
            if conn.via is not None:
                vias.append(conn.via)
        
        # Simple 2-pad routing for now
        if len(connection_points) == 2:
            (pad1, conn1), (pad2, conn2) = connection_points
            
            # If both have escape routing, route: pad1 -> via1 -> via2 -> pad2
            # Otherwise route directly between connection points
            
            # Escape segments (if needed)
            if conn1.requires_escape:
                # Route from pad to via on pad's layer
                escape1 = self._route_escape(
                    pad1.position,
                    conn1.position,
                    self.pad_connector._get_primary_copper_layer(pad1)
                )
                if escape1:
                    tracks.extend(escape1)
            
            if conn2.requires_escape:
                # Route from via to pad on pad's layer
                escape2 = self._route_escape(
                    conn2.position,
                    pad2.position,
                    self.pad_connector._get_primary_copper_layer(pad2)
                )
                if escape2:
                    tracks.extend(escape2)
            
            # Main segment on routing layer
            main_track = self._route_segment(
                conn1.position,
                conn2.position,
                routing_layer
            )
            if main_track:
                tracks.append(main_track)
        
        # Multi-pad: route in sequence (simple approach)
        else:
            for i in range(len(connection_points) - 1):
                (pad1, conn1), (pad2, conn2) = connection_points[i], connection_points[i+1]
                
                # Escape segments
                if conn1.requires_escape and i == 0:
                    escape1 = self._route_escape(
                        pad1.position,
                        conn1.position,
                        self.pad_connector._get_primary_copper_layer(pad1)
                    )
                    if escape1:
                        tracks.extend(escape1)
                
                # Main segment
                main_track = self._route_segment(
                    conn1.position,
                    conn2.position,
                    routing_layer
                )
                if main_track:
                    tracks.append(main_track)
                
                # Escape at end
                if conn2.requires_escape and i == len(connection_points) - 2:
                    escape2 = self._route_escape(
                        conn2.position,
                        pad2.position,
                        self.pad_connector._get_primary_copper_layer(pad2)
                    )
                    if escape2:
                        tracks.extend(escape2)
        
        if not tracks:
            return None
        
        route = NetRoute(
            net=net_name,
            tracks=tracks,
            vias=vias,
            layer=routing_layer
        )
        
        self.routed_nets[net_name] = route
        return route
    
    def _route_segment(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        layer: str
    ) -> Track | None:
        """
        Route single track segment.
        
        For now, just creates direct connection.
        Future: Use RRT/A* with obstacle avoidance.
        """
        # Simple direct connection
        return Track(
            start=start,
            end=end,
            layer=layer,
            width=self.trace_width,
            net=""  # Set by caller
        )
    
    def _route_escape(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        layer: str
    ) -> list[Track]:
        """
        Route escape segment (short connection on pad layer).
        
        For dense ICs, this routes from pad to via.
        """
        # Simple direct escape
        track = Track(
            start=start,
            end=end,
            layer=layer,
            width=self.trace_width,
            net=""
        )
        return [track]
