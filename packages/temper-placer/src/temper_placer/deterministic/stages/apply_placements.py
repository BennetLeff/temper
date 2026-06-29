from dataclasses import replace

from ..state import BoardState
from .base import Stage


class ApplyPlacementsStage(Stage):
    """Apply placements from BoardState to Component.initial_position."""

    @property
    def name(self) -> str:
        return "apply_placements"

    def run(self, state: BoardState) -> BoardState:
        if not state.netlist or not state.placements:
            return state

        placements_dict = dict(state.placements)

        # Create new component list with updated positions
        updated_components = []
        for component in state.netlist.components:
            if component.ref in placements_dict:
                # Create new component with updated position
                new_comp = replace(component, initial_position=placements_dict[component.ref])
                updated_components.append(new_comp)
            else:
                updated_components.append(component)

        # Create new netlist with updated components
        new_netlist = replace(state.netlist, components=tuple(updated_components))

        return replace(state, netlist=new_netlist)
