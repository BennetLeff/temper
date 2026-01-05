"""Layer assignment stage for multi-layer routing.

Assigns each net to a preferred layer based on net class rules.
This is a 2.5D approach where we pre-assign layers rather than doing full 3D A* search.
"""

from dataclasses import dataclass, replace
from typing import Dict
from ..state import BoardState
from .base import Stage


@dataclass(frozen=True)
class LayerAssignment:
    """Assignment of a net to a preferred routing layer."""
    net_name: str
    layer: int
    allow_layer_change: bool = True  # Can router switch layers via vias?
    is_plane: bool = False  # Is this a power plane net (In1.Cu/In2.Cu)?


class LayerAssignmentStage(Stage):
    """Assign nets to preferred layers based on net class rules."""
    
    def __init__(self, layer_assignments: Dict[str, int] = None, net_classes: Dict[str, str] = None):
        """
        Args:
            layer_assignments: Manual layer assignments {net_name: layer_index}
                              If None, will use net_class rules from design_rules
            net_classes: Mapping of net_name -> net_class from config
                        Used to override Net.net_class from parser
        """
        self.manual_assignments = layer_assignments or {}
        self.net_classes = net_classes or {}
    
    @property
    def name(self) -> str:
        return "layer_assignment"
    
    def run(self, state: BoardState) -> BoardState:
        """Assign each net to a preferred layer."""
        if not state.netlist:
            return state
        
        assignments = []
        
        for net in state.netlist.nets:
            # Check if there's a manual assignment
            if net.name in self.manual_assignments:
                layer = self.manual_assignments[net.name]
                # Infer plane status from layer index (1=In1, 2=In2)
                is_plane = (layer in (1, 2))
                assignments.append(LayerAssignment(
                    net_name=net.name,
                    layer=layer,
                    allow_layer_change=True,
                    is_plane=is_plane
                ))
                continue
            
            # Get net_class from config if available, otherwise use the one from parser
            net_class = self.net_classes.get(net.name, net.net_class)
            
            # Use net class rules to assign layer
            layer, is_plane = self._assign_layer_by_net_class(net_class)
            assignments.append(LayerAssignment(
                net_name=net.name,
                layer=layer,
                allow_layer_change=True,
                is_plane=is_plane
            ))
        
        # Store assignments in BoardState
        return replace(state, layer_assignments=tuple(assignments))
    
    def _assign_layer_by_net_class(self, net_class: str) -> tuple[int, bool]:
        """Determine preferred layer and plane status based on net class.
        
        Layer mapping (4-layer board):
        - L0 (F.Cu/Top): HV, Signal
        - L1 (In1.Cu): Ground plane
        - L2 (In2.Cu): Power plane
        - L3 (B.Cu/Bottom): Signal overflow
        
        Returns:
            (layer_index, is_plane)
        """
        if net_class == "HighVoltage":
            return 0, False  # Top layer for easy inspection
        elif net_class == "Power":
            return 2, True  # Inner power plane
        elif net_class == "Ground":
            return 1, True  # Inner ground plane
        elif net_class == "Signal":
            return 0, False  # Top layer with option to use bottom
        elif net_class == "Differential":
            return 0, False  # Top layer for controlled impedance
        else:
            # Default to top layer
            return 0, False
