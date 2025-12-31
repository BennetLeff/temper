import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple
from kiutils.board import Board
from kiutils.items.common import Position
from kiutils.items.brditems import Via, Segment
from temper_placer.core.netlist import Netlist

logger = logging.getLogger(__name__)

@dataclass
class FanoutConfig:
    """Configuration for Fanout Generation."""
    pitch: float = 2.54  # Grid pitch in mm
    via_drill: float = 0.3
    via_size: float = 0.6
    trace_width: float = 0.2
    
    # "Grid" strategy: offset by half pitch
    # "Void" strategy: search for nearest empty space
    strategy: str = "grid" 
    
    # Offset factors for Grid strategy (relative to pitch)
    # (0.5, 0.5) puts via in the center of 4 pins
    offset_x: float = 0.5 
    offset_y: float = 0.5

class FanoutGenerator:
    """
    Generates 'dog-bone' fanouts for pins to allow routing from clear areas.
    """
    def __init__(self, board: Board, netlist: Netlist, config: FanoutConfig = None):
        self.board = board
        self.netlist = netlist
        self.config = config or FanoutConfig()
        
    def generate_fanouts(self, target_nets: List[str] = None) -> Dict[str, List[Tuple[float, float]]]:
        """
        Generate fanouts for specified nets (or all if None).
        Returns a map of net_name -> list of NEW start/end positions (the vias).
        Updates self.board with new Vias and Tracks.
        """
        new_positions = {}
        
        # Build map of component pins to absolute positions
        # Simplified: assumes we can calculate it or pass it in. 
        # For now, let's assume we can get it from components + footprints.
        # But we need absolute positions.
        
        # Helper to get pin positions
        # Implementation similar to MazeRouter's extraction
        
        for net in self.netlist.nets:
            if not net.name: continue
            if target_nets and net.name not in target_nets:
                continue
                
            fanout_points = []
            
            # Find all pins for this net
            for comp_ref, pin_name in net.pins:
                # Find the component
                comp = next((c for c in self.netlist.components if c.ref == comp_ref), None)
                if not comp: continue
                
                # Find the pin relative position
                pin_def = next((p for p in comp.pins if p.name == pin_name or p.number == pin_name), None)
                if not pin_def: continue
                
                # Calculate absolute position
                # Assuming no rotation for simplicity in EXP-02-C, 
                # but functionally we should handle it if needed.
                cx, cy = comp.initial_position
                px = cx + pin_def.position[0]
                py = cy + pin_def.position[1]
                
                # Calculate Fanout Position (Escape Point)
                # Strategy: Grid (Offset)
                fx = px + (self.config.pitch * self.config.offset_x)
                fy = py + (self.config.pitch * self.config.offset_y)
                
                # Create Via
                via = Via(
                    position=Position(X=fx, Y=fy),
                    size=self.config.via_size,
                    drill=self.config.via_drill,
                    layers=["F.Cu", "B.Cu"], # Through via
                    net=None # We don't have net index lookup easily here, relying on name matching elsewhere?
                             # kiutils Board uses numeric net IDs usually. 
                             # For now, we leave net unassigned or try to find ID.
                )
                
                # Find Net ID from Board
                # This is O(N) but N is small
                ki_net = next((n for n in self.board.nets if n.name == net.name), None)
                if ki_net:
                    via.net = ki_net
                
                self.board.traceItems.append(via)
                
                # Create Trace (Pin -> Via)
                track = Segment(
                    start=Position(X=px, Y=py),
                    end=Position(X=fx, Y=fy),
                    width=self.config.trace_width,
                    layer="F.Cu", # Assume pins are accessible on Top (SMD or TH)
                    net=ki_net
                )
                self.board.traceItems.append(track)
                
                # Record the Via position as the new "Routing Point"
                fanout_points.append((fx, fy))
                
            if fanout_points:
                new_positions[net.name] = fanout_points
                
        return new_positions
