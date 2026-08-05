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

        # Create new component list with updated positions.
        # Wave-4 adaptation (R12): the migrated Component/Netlist are pyo3
        # pyclasses, not dataclasses — `dataclasses.replace` does not apply.
        updated_components = []
        for component in state.netlist.components:
            if component.ref in placements_dict:
                # Create new component with updated position
                new_comp = type(component)(  # noqa: E721 — pyclass ctor
                    component.ref,
                    component.footprint,
                    component.bounds,
                    pins=component.pins,
                    net_class=component.net_class,
                    zone=component.zone,
                    fixed=component.fixed,
                    initial_position=placements_dict[component.ref],
                    initial_rotation=component.initial_rotation,
                    initial_side=component.initial_side,
                    attributes=component.attributes,
                    tags=component.tags,
                    sheetpath=component.sheetpath,
                )
                updated_components.append(new_comp)
            else:
                updated_components.append(component)

        # Create new netlist with updated components
        new_netlist = type(state.netlist)(  # noqa: E721 — pyclass ctor
            components=list(updated_components),
            nets=state.netlist.nets,
        )

        return replace(state, netlist=new_netlist)
