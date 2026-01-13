from dataclasses import replace
from typing import Dict
from ..state import BoardState
from .base import Stage

class ZoneAssignmentStage(Stage):
    @property
    def name(self) -> str:
        return "zone_assignment"
    
    def run(self, state: BoardState) -> BoardState:
        if not state.netlist:
            return state
        
        component_zone_map = self._assign_components_to_zones(state.netlist)
        return replace(state, component_zone_map=frozenset(component_zone_map.items()))
    
    def _assign_components_to_zones(self, netlist) -> Dict[str, str]:
        """
        Assign components to zones based on net classes and component types.
        
        Rules (in priority order):
        1. MCU Zone: Components with ref prefix "U_MCU" or connected to SPI/I2C/UART nets
        2. HV Zone: Components connected to "HighVoltage" net class
        3. Power Zone: Components connected to "Power" net class
        4. Signal Zone: Default for all other components
        """
        zone_map = {}
        
        # Build net-to-class mapping
        net_class_map = {}
        for net in netlist.nets:
            net_class = getattr(net, 'net_class', 'Signal')
            net_class_map[net.name] = net_class
        
        # Build component-to-nets mapping
        comp_nets = {}
        for net in netlist.nets:
            for comp_ref, _ in net.pins:
                if comp_ref not in comp_nets:
                    comp_nets[comp_ref] = []
                comp_nets[comp_ref].append(net.name)
        
        # Assign each component
        for component in netlist.components:
            ref = component.ref
            zone = self._infer_zone_for_component(ref, comp_nets.get(ref, []), net_class_map)
            zone_map[ref] = zone
        
        return zone_map
    
    def _infer_zone_for_component(self, ref: str, nets: list[str], net_class_map: Dict[str, str]) -> str:
        """Infer zone for a single component."""
        # Rule 1: MCU zone by ref prefix
        if ref.startswith("U_MCU"):
            return "MCU"
        
        # Rule 2: MCU zone by SPI/I2C/UART nets
        for net_name in nets:
            if any(proto in net_name.upper() for proto in ["SPI", "I2C", "UART"]):
                return "MCU"
        
        # Rule 3: HV zone by net class
        for net_name in nets:
            if net_class_map.get(net_name) == "HighVoltage":
                return "HV"
        
        # Rule 4: Power zone by net class
        for net_name in nets:
            if net_class_map.get(net_name) == "Power":
                return "Power"
        
        # Rule 5: Signal zone (default)
        return "Signal"
