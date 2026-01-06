from dataclasses import replace
from typing import Dict, Tuple, Set, List
import math
from ..state import BoardState
from .base import Stage

class ComponentAssignmentStage(Stage):
    """Assign components to slots with multi-slot reservation for large footprints."""

    def __init__(self, slot_spacing: float = 12.0, fixed_placements: Dict[str, Dict] = None):
        """Initialize with slot spacing and optional fixed placements.
        
        Args:
            slot_spacing: Spacing between slots in mm
            fixed_placements: Dict of ref -> {'position': [x, y], 'rotation': deg}
        """
        self.slot_spacing = slot_spacing
        self.fixed_placements = fixed_placements or {}

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

    def _get_footprint_radius(self, component) -> float:
        """Get the minimum radius needed to enclose the component footprint.

        Uses diagonal of bounding box / 2 with some margin.
        """
        if hasattr(component, 'bounds') and component.bounds:
            w, h = component.bounds
            # Use diagonal/2 + 1mm margin to avoid overlaps
            radius = math.sqrt(w**2 + h**2) / 2 + 1.0
            return radius
        # Default to half slot spacing for unknown components
        return self.slot_spacing / 2.0

    def _reserve_slots(
        self,
        center: Tuple[float, float],
        radius: float,
        all_slots: List[Tuple[float, float]],
        used_slots: Set[Tuple[float, float]]
    ) -> None:
        """Reserve all slots within radius of center."""
        cx, cy = center
        for slot in all_slots:
            sx, sy = slot
            dist = math.sqrt((sx - cx)**2 + (sy - cy)**2)
            if dist <= radius:
                used_slots.add(slot)

    def _assign_components_to_slots(
        self,
        netlist,
        component_zone_map: Dict[str, str],
        zone_slots: Dict[str, Tuple]
    ) -> Dict[str, Tuple[float, float]]:
        """
        Assign components to slots using greedy wirelength minimization.

        Improvements over basic algorithm:
        1. Process fixed placements first
        2. Sort remaining components by footprint size (largest first)
        3. Multi-slot reservation - large footprints block nearby slots
        4. Wirelength-based slot selection
        """
        placements = {}
        used_slots: Set[Tuple[float, float]] = set()

        # Build net connectivity map
        net_pins = {}  # net_name -> [(comp_ref, pin_name), ...]
        for net in netlist.nets:
            net_pins[net.name] = list(net.pins)

        # Build flat list of all slots for reservation checks
        all_slots = []
        for zone_name, slots in zone_slots.items():
            all_slots.extend(slots)

        # 1. Process fixed placements first
        comp_by_ref = {c.ref: c for c in netlist.components}
        for ref, info in self.fixed_placements.items():
            if ref in comp_by_ref:
                # Handle both [x, y] and {'position': [x, y]} formats
                pos = None
                if isinstance(info, (list, tuple)) and len(info) == 2:
                    pos = info
                elif isinstance(info, dict):
                    pos = info.get('position')
                
                if pos and len(pos) == 2:
                    fixed_pos = (float(pos[0]), float(pos[1]))
                    placements[ref] = fixed_pos
                    
                    # Reserve slots near fixed component
                    footprint_radius = self._get_footprint_radius(comp_by_ref[ref])
                    self._reserve_slots(fixed_pos, footprint_radius, all_slots, used_slots)

        # 2. Sort remaining components by footprint size (largest first)
        remaining_components = [c for c in netlist.components if c.ref not in placements]
        
        def get_size(comp):
            if hasattr(comp, 'bounds') and comp.bounds:
                return max(comp.bounds)
            return 0

        sorted_components = sorted(remaining_components, key=lambda c: (-get_size(c), c.ref))

        for component in sorted_components:
            ref = component.ref
            zone_name = component_zone_map.get(ref, "Signal")
            footprint_radius = self._get_footprint_radius(component)

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

            # Reserve this slot AND all slots within footprint radius
            self._reserve_slots(best_slot, footprint_radius, all_slots, used_slots)
        
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
