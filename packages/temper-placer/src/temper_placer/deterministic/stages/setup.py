from typing import TYPE_CHECKING
from dataclasses import dataclass, replace
import math

from ..state import BoardState
from .base import Stage
from temper_placer.routing.constraints.drc_oracle import DRCOracle
from temper_placer.routing.constraints.design_rules import ClearanceMatrix, DesignRulesParser
from temper_placer.routing.constraints.spatial_index import Pad
from temper_placer.routing.constraints.geometry import Point

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.core.design_rules import DesignRules

@dataclass
class DRCOracleSetupStage(Stage):
    """Setup stage for initializing DRCOracle and other common utilities."""
    design_rules: 'DesignRules | None' = None
    
    @property
    def name(self) -> str:
        return "drc_oracle_setup"

    def _rotate_point(self, point: tuple[float, float], angle_degrees: float) -> tuple[float, float]:
        """Rotate a point by angle_degrees around (0,0)."""
        angle_rad = math.radians(angle_degrees)
        x, y = point
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        return (
            x * cos_a - y * sin_a,
            x * sin_a + y * cos_a
        )

    def run(self, state: BoardState) -> BoardState:
        # Initialize ClearanceMatrix
        if self.design_rules:
            # Use provided design rules if available
            matrix = ClearanceMatrix()
            for name, rules in self.design_rules.net_classes.items():
                matrix.add_net_class_rules(rules)
            for net, class_name in self.design_rules.net_class_assignments.items():
                matrix.set_net_class(net, class_name)
        elif state.board:
            # Try to parse from board (handles zones)
            matrix = ClearanceMatrix.parse(state.board)
        else:
            matrix = DesignRulesParser.create_default()
            
        # Create DRCOracle
        oracle = DRCOracle(rules=matrix)
        
        # Register pads from board if available
        if state.board and state.netlist:
            placements_dict = dict(state.placements) if state.placements else {}
            
            for component in state.netlist.components:
                # Use placement from BoardState if available, otherwise initial
                pos = placements_dict.get(component.ref, component.initial_position)
                if pos is None:
                    continue
                
                # Component rotation: index to degrees (0=0, 1=90, 2=180, 3=270)
                rot_idx = component.initial_rotation or 0
                rotation = rot_idx * 90.0
                    
                for pin in component.pins:
                    # Pad position is relative to component center, must be rotated
                    rel_pos = self._rotate_point(pin.position, rotation)
                    pin_pos = (pos[0] + rel_pos[0], pos[1] + rel_pos[1])
                    
                    # Map layer name to index
                    layer_idx = 0
                    pin_layer = getattr(pin, 'layer', 'F.Cu')
                    is_pth = pin_layer == 'all' or pin.is_pth
                    
                    if pin_layer == 'B.Cu':
                        layer_idx = 3
                    elif pin_layer == 'In1.Cu':
                        layer_idx = 1
                    elif pin_layer == 'In2.Cu':
                        layer_idx = 2
                    else:
                        layer_idx = 0
                        
                    # Create Pad object for DRCOracle
                    # Use sentinel net for unconnected pads so Oracle still validates
                    # against them (fixes J_DEBUG pin 6 vs DC_BUS+ shorting)
                    pad_net = pin.net if pin.net else "__UNCONNECTED__"
                    oracle.register_pad(Pad(
                        center=Point(pin_pos[0], pin_pos[1]),
                        shape=getattr(pin, 'shape', 'rect') if getattr(pin, 'shape', 'rect') in ["circle", "rect", "oval"] else "rect",
                        size=(getattr(pin, 'width', 1.0), getattr(pin, 'height', 1.0)),
                        net=pad_net,
                        layer=layer_idx,
                        id=f"{component.ref}.{pin.number}",
                        rotation=rotation, # Pad rotation follows component rotation
                        mask_expansion=getattr(pin, 'mask_expansion', 0.1),
                        is_pth=is_pth
                    ))
            
            oracle.geometry.rebuild_index()

        return replace(state, drc_oracle=oracle)

# Alias for backward compatibility
SetupStage = DRCOracleSetupStage
