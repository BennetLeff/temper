from dataclasses import replace
from typing import Dict, Tuple, Set
from ..state import BoardState
from .base import Stage

class ComponentAssignmentStage(Stage):
    @property
    def name(self) -> str:
        return "component_assignment"
    
    def run(self, state: BoardState) -> BoardState:
        if not state.netlist or not state.component_zone_map or not state.zone_slots:
            return state
        
        placements = self._assign_components_to_slots(
            state.netlist,
            dict(state.component_zone_map),
            dict(state.zone_slots)
        )
        
        return replace(state, placements=frozenset(placements.items()))
    
    def _assign_components_to_slots(
        self,
        netlist,
        component_zone_map: Dict[str, str],
        zone_slots: Dict[str, Tuple]
    ) -> Dict[str, Tuple[float, float]]:
        """
        Assign components to slots using greedy wirelength minimization.
        
        For each component (in sorted order for determinism):
        1. Get its assigned zone
        2. Find available slots in that zone
        3. Score each slot by HPWL to connected nets
        4. Assign to best slot
        """
        placements = {}
        used_slots: Set[Tuple[float, float]] = set()
        
        # Build net connectivity map
        net_pins = {}  # net_name -> [(comp_ref, pin_name), ...]
        for net in netlist.nets:
            net_pins[net.name] = list(net.pins)
        
        # Assign in sorted order for determinism
        for component in sorted(netlist.components, key=lambda c: c.ref):
            ref = component.ref
            zone_name = component_zone_map.get(ref, "Signal")
            
            # Get available slots in this zone
            all_zone_slots = list(zone_slots.get(zone_name, ()))
            available_slots = [s for s in all_zone_slots if s not in used_slots]
            
            if not available_slots:
                # Fallback: use any available slot from other zones
                for other_zone, slots in zone_slots.items():
                    available_slots = [s for s in slots if s not in used_slots]
                    if available_slots:
                        break
            
            if not available_slots:
                continue  # Skip if no slots available
            
            # Score each slot by wirelength
            best_slot = min(
                available_slots,
                key=lambda slot: self._compute_wirelength(ref, slot, net_pins, placements)
            )
            
            placements[ref] = best_slot
            used_slots.add(best_slot)
        
        return placements
    
    def _compute_wirelength(
        self,
        component_ref: str,
        candidate_slot: Tuple[float, float],
        net_pins: Dict[str, list],
        current_placements: Dict[str, Tuple[float, float]]
    ) -> float:
        """Compute HPWL (Half-Perimeter Wirelength) for placing component at slot."""
        total_hpwl = 0.0
        
        # Find all nets this component is on
        for net_name, pins in net_pins.items():
            component_on_net = any(ref == component_ref for ref, _ in pins)
            if not component_on_net:
                continue
            
            # Collect positions of all pins on this net
            positions = [candidate_slot]  # Include candidate position
            for ref, _ in pins:
                if ref != component_ref and ref in current_placements:
                    positions.append(current_placements[ref])
            
            # Compute HPWL: (max_x - min_x) + (max_y - min_y)
            if len(positions) > 1:
                xs = [p[0] for p in positions]
                ys = [p[1] for p in positions]
                hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))
                total_hpwl += hpwl
        
        return total_hpwl
