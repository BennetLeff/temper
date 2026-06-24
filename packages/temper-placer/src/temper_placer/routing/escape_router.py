"""
Escape Router for high-density components.

Generates dog-bone fanouts for pins that are topologically trapped
within dense component grids (e.g., QFN centers, BGA arrays).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Tuple, Dict, Optional

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.routing.fanout import FanoutGenerator, FanoutConfig
from temper_placer.io.kicad_parser import TraceData, ViaData

if TYPE_CHECKING:
    from kiutils.board import Board as KiBoard

@dataclass
class EscapeResult:
    """Result of escape routing for a net.
    
    Attributes:
        success: Whether escape routing succeeded for all pins.
        net_name: Name of the net.
        original_positions: Original pin positions (world coords).
        escape_positions: New routing positions (the vias).
        via_count: Number of vias placed.
        length: Total length of escape traces.
        traces: List of generated trace segments (TraceData).
        vias: List of generated vias (ViaData).
    """
    success: bool
    net_name: str
    original_positions: List[Tuple[float, float]]
    escape_positions: List[Tuple[float, float]]
    via_count: int = 0
    length: float = 0.0
    traces: List[TraceData] = field(default_factory=list)
    vias: List[ViaData] = field(default_factory=list)

class EscapeRouter:
    """
    Specialized router for escaping dense pin grids.
    
    This router doesn't connect pins to each other; instead, it connects
    individual pins to nearby escape points (usually vias to another layer)
    to facilitate routing by the main maze router.
    """

    def __init__(
        self, 
        ki_board: KiBoard, 
        netlist: Netlist, 
        config: FanoutConfig = None
    ):
        """
        Initialize the EscapeRouter.
        
        Args:
            ki_board: The Kiutils board object (to add items to).
            netlist: The internal netlist.
            config: Optional fanout configuration.
        """
        self.ki_board = ki_board
        self.netlist = netlist
        self.config = config or FanoutConfig()
        self.generator = FanoutGenerator(ki_board, netlist, self.config)

    def route_net_escapes(self, net_name: str) -> EscapeResult:
        """
        Generate escape routes for all pins in a net.
        
        Args:
            net_name: Name of the net to escape.
            
        Returns:
            EscapeResult containing new start/end positions for the main router.
        """
        # Record existing items to identify new ones
        existing_count = len(self.ki_board.traceItems)

        # Find original pin positions for this net
        net = next((n for n in self.netlist.nets if n.name == net_name), None)
        if not net:
            return EscapeResult(success=False, net_name=net_name, original_positions=[], escape_positions=[])

        original_positions = []
        for comp_ref, pin_name in net.pins:
            comp = next((c for c in self.netlist.components if c.ref == comp_ref), None)
            if not comp: continue
            pin = comp.get_pin(pin_name)
            if not pin: continue
            
            cx, cy = comp.initial_position
            px, py = pin_world_position(pin, comp)
            original_positions.append((px, py))

        # Generate fanouts
        new_positions_map = self.generator.generate_fanouts(target_nets=[net_name])
        
        if net_name not in new_positions_map:
            return EscapeResult(
                success=True, 
                net_name=net_name, 
                original_positions=original_positions, 
                escape_positions=original_positions
            )

        escape_positions = new_positions_map[net_name]
        via_count = len(escape_positions)
        
        # Identify new items and convert to TraceData/ViaData
        new_items = self.ki_board.traceItems[existing_count:]
        traces = []
        vias = []
        
        from kiutils.items.brditems import Via, Segment
        
        for item in new_items:
            if isinstance(item, Via):
                vias.append(ViaData(
                    position=(item.position.X, item.position.Y),
                    diameter=item.size,
                    drill=item.drill,
                    net=net_name,
                    layers=tuple(item.layers)
                ))
            elif isinstance(item, Segment):
                traces.append(TraceData(
                    start=(item.start.X, item.start.Y),
                    end=(item.end.X, item.end.Y),
                    width=item.width,
                    layer=item.layer,
                    net=net_name
                ))

        # Calculate length
        length = 0.0
        for i in range(min(len(original_positions), len(escape_positions))):
            p = original_positions[i]
            e = escape_positions[i]
            length += math.sqrt((p[0] - e[0])**2 + (p[1] - e[1])**2)
        
        return EscapeResult(
            success=True,
            net_name=net_name,
            original_positions=original_positions,
            escape_positions=escape_positions,
            via_count=via_count,
            length=length,
            traces=traces,
            vias=vias
        )
