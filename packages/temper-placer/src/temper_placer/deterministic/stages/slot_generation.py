from dataclasses import replace

from ..state import BoardState
from .base import Stage


class SlotGenerationStage(Stage):
    def __init__(self, slot_spacing_mm: float = 5.0):
        self.slot_spacing_mm = slot_spacing_mm

    @property
    def name(self) -> str:
        return "slot_generation"

    def run(self, state: BoardState) -> BoardState:
        if not state.zones:
            return state

        # Build list of (zone_name, tuple_of_slots) for storage
        zone_slots_list = []
        for zone in state.zones:
            slots = self._generate_slots_for_zone(zone, self.slot_spacing_mm)
            # Store as (zone_name, tuple_of_slot_tuples)
            zone_slots_list.append((zone.name, tuple(slots)))

        return replace(state, zone_slots=frozenset(zone_slots_list))

    def _generate_slots_for_zone(self, zone, spacing: float) -> list[tuple[float, float]]:
        """Generate a regular grid of placement slots within a zone."""
        (x_min, y_min), (x_max, y_max) = zone.bounds

        slots = []

        # Start from minimum + half spacing to center slots in cells
        x = x_min + spacing / 2
        while x < x_max:
            y = y_min + spacing / 2
            while y < y_max:
                slots.append((x, y))
                y += spacing
            x += spacing

        return slots
