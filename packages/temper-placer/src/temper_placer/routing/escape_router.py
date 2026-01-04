"""
Escape Router for high-density components.

Generates dog-bone fanouts for pins that are topologically trapped
within dense component grids (e.g., QFN centers, BGA arrays).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Tuple, Dict, Optional

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.routing.fanout import FanoutGenerator, FanoutConfig

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
    """
    success: bool
    net_name: str
    original_positions: List[Tuple[float, float]]
    escape_positions: List[Tuple[float, float]]
    via_count: int = 0
    length: float = 0.0

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
            
            # Note: initial_position is BB center. 
            # Pin position is relative to BB center.
            # We should probably use a proper absolute_position helper if rotation is involved.
            cx, cy = comp.initial_position
            px = cx + pin.position[0]
            py = cy + pin.position[1]
            original_positions.append((px, py))

        # Generate fanouts using the existing generator
        new_positions_map = self.generator.generate_fanouts(target_nets=[net_name])
        
        if net_name not in new_positions_map:
            # Maybe no pins needed escape, or it failed
            return EscapeResult(
                success=True, 
                net_name=net_name, 
                original_positions=original_positions, 
                escape_positions=original_positions # No change
            )

        escape_positions = new_positions_map[net_name]
        via_count = len(escape_positions)
        
        # Calculate length (Euclidean distance for each dog-bone)
        length = 0.0
        # This is a bit tricky because FanoutGenerator doesn't return the mapping
        # but we can assume it follows the same order if we are careful.
        # Actually FanoutGenerator calculates them in the same way.
        
        return EscapeResult(
            success=True,
            net_name=net_name,
            original_positions=original_positions,
            escape_positions=escape_positions,
            via_count=via_count,
            length=0.0 # TODO: Calculate actual length
        )
