"""Fine-pitch IC escape routing stage.

This stage automatically detects fine-pitch components (components with pins
closer than a threshold) and places escape vias at their pins to enable
inner-layer routing. This solves the problem of overlapping clearance zones
on the surface layer that block routing.

Professional PCB designers handle fine-pitch ICs by "fanning out" or "escaping"
from the dense pin field to less congested areas or inner layers before main
routing. This stage implements that pattern automatically.
"""

from dataclasses import dataclass
import math
from ..state import BoardState
from .base import Stage


@dataclass
class FinePitchEscapeStage(Stage):
    """Place escape vias for fine-pitch IC pins to enable inner-layer routing.

    This stage:
    1. Auto-detects fine-pitch components by calculating minimum pin-to-pin distance
    2. Places via-under-pad at each netted pin on fine-pitch components
    3. Vias connect from surface layer (F.Cu/Layer 0) to escape layer (In1.Cu/Layer 1)
    4. Main router can then start routing from escape layer where clearances don't conflict

    Args:
        pin_pitch_threshold_mm: Minimum pin spacing to qualify as fine-pitch (default: 0.65mm)
        escape_layer: Target inner layer for escape routing (default: 1 = In1.Cu)
        via_drill_mm: Via drill diameter (default: 0.3mm)
        via_diameter_mm: Via copper diameter (default: 0.6mm)
    """

    pin_pitch_threshold_mm: float = 0.65  # Pins closer than this = fine-pitch
    escape_layer: int = 1  # In1.Cu
    via_drill_mm: float = 0.3
    via_diameter_mm: float = 0.6

    @property
    def name(self) -> str:
        return "fine_pitch_escape"

    def run(self, state: BoardState) -> BoardState:
        """Detect fine-pitch components and place escape vias."""
        if not state.netlist:
            return state

        from dataclasses import replace
        from ...core.board import Via

        placements = dict(state.placements) if state.placements else {}
        vias = list(state.vias) if state.vias else []

        # Track fine-pitch components for debug output
        fine_pitch_components = []
        total_escape_vias = 0

        # Analyze each component
        for component in state.netlist.components:
            # Get component position
            comp_pos = placements.get(component.ref, component.initial_position)
            if comp_pos is None:
                continue

            # Calculate minimum pin-to-pin distance
            min_pitch = self._calculate_min_pin_pitch(component)

            if min_pitch is None or min_pitch >= self.pin_pitch_threshold_mm:
                continue  # Not fine-pitch or no pins

            # This is a fine-pitch component
            fine_pitch_components.append((component.ref, min_pitch, len(component.pins)))

            # Place escape vias at each netted pin
            for pin in component.pins:
                if not pin.net:
                    continue  # Skip NC pins

                # Calculate absolute pin position
                pin_x = comp_pos[0] + pin.position[0]
                pin_y = comp_pos[1] + pin.position[1]

                # Create escape via (F.Cu to escape layer)
                via = Via(
                    position=(pin_x, pin_y),
                    drill=self.via_drill_mm,
                    width=self.via_diameter_mm,
                    layers=("F.Cu", "In1.Cu"),  # Surface to first inner layer
                    net=pin.net,
                )
                vias.append(via)
                total_escape_vias += 1

        # Debug output
        if fine_pitch_components:
            print(f"  Fine-pitch components detected: {len(fine_pitch_components)}")
            for ref, pitch, pin_count in fine_pitch_components:
                # Count netted pins correctly
                comp = next((c for c in state.netlist.components if c.ref == ref), None)
                if comp:
                    netted_pins = sum(1 for pin in comp.pins if pin.net)
                    print(
                        f"    {ref}: min_pitch={pitch:.2f}mm, {netted_pins}/{pin_count} pins with nets"
                    )
            print(f"  Placed {total_escape_vias} escape vias to Layer {self.escape_layer} (In1.Cu)")
        else:
            print(
                f"  No fine-pitch components detected (threshold: {self.pin_pitch_threshold_mm}mm)"
            )

        return replace(state, vias=vias)

    def _calculate_min_pin_pitch(self, component):
        """Calculate minimum pin-to-pin distance for a component.

        Args:
            component: Component to analyze

        Returns:
            Minimum distance between any two pins in mm, or None if < 2 pins
        """
        pins = component.pins
        if len(pins) < 2:
            return None

        min_dist = float("inf")

        # Check all pin pairs
        for i, pin1 in enumerate(pins):
            for pin2 in pins[i + 1 :]:
                dx = pin1.position[0] - pin2.position[0]
                dy = pin1.position[1] - pin2.position[1]
                dist = math.sqrt(dx * dx + dy * dy)
                min_dist = min(min_dist, dist)

        return min_dist if min_dist != float("inf") else None
