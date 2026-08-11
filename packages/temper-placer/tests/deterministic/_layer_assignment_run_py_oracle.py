"""
D7 run-orchestration oracle for `deterministic/stages/layer_assignment.py`.

Verbatim pre-D7 snapshot of the module at the D7 dispatch base (origin/main
`3a7dd1d9`), with ONLY the documented relative-import rewrites below. The body
below `# --- BEGIN PINNED BODY ---` is byte-identical to the module except for
the two relative imports (`from ..state` / `from .base`) rewritten to their
absolute forms so the oracle imports from the test tree; the D7 Rust port
(`temper-orchestration::LayerAssignmentStage`) is the differential subject,
pinned by `test_deterministic_d7_rust_differential.py`. The assignment kernels
(`assign_layers` / `assign_layer_by_net_class_py`) and the `LayerAssignment`
pyclass stay single-source in `temper_design_bundle_python.deterministic_leaves`.
"""

from dataclasses import dataclass, replace

import temper_design_bundle_python as _tdb

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage

# --- BEGIN PINNED BODY ---

LayerAssignment = _tdb.LayerAssignment


class LayerAssignmentStage(Stage):
    """Assign nets to preferred layers based on net class rules."""

    def __init__(
        self,
        layer_assignments: dict[str, int] | None = None,
        net_classes: dict[str, str] | None = None,
    ):
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

        assignments = _tdb.deterministic_leaves.assign_layers(
            state.netlist.nets, self.manual_assignments, self.net_classes
        )

        # Store assignments in BoardState
        return replace(state, layer_assignments=frozenset(assignments))

    def _assign_layer_by_net_class(self, net_class: str) -> tuple[int, bool]:
        """Determine preferred layer and plane status based on net class.

        Layer mapping (4-layer board):
        - L0 (F.Cu/Top): HV, Signal, PowerTrace
        - L1 (In1.Cu): Ground plane
        - L2 (In2.Cu): Power plane
        - L3 (B.Cu/Bottom): Signal overflow

        Returns:
            (layer_index, is_plane)
        """
        return _tdb.deterministic_leaves.assign_layer_by_net_class_py(net_class)
