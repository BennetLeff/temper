"""
D7 run-orchestration oracle for `deterministic/stages/apply_placements.py`.

Verbatim pre-D7 snapshot of the module at the D7 dispatch base (origin/main
`3a7dd1d9`), with ONLY the documented relative-import rewrites below. The body
below `# --- BEGIN PINNED BODY ---` is byte-identical to the module except for
the two relative imports (`from ..state` / `from .base`) rewritten to their
absolute forms so the oracle imports from the test tree; the D7 Rust port
(`temper-orchestration::ApplyPlacementsStage`) is the differential subject,
pinned by `test_deterministic_d7_rust_differential.py`. This stage is pure
orchestration -- it has no design-bundle leaf kernel; the ``dataclasses.replace``
component/netlist reconstruction is transcribed directly.
"""

from dataclasses import replace

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage

# --- BEGIN PINNED BODY ---


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
        new_netlist = replace(state.netlist, components=list(updated_components))

        return replace(state, netlist=new_netlist)
