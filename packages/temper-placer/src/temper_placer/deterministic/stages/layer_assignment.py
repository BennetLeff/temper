"""Layer assignment stage for multi-layer routing.

Assigns each net to a preferred layer based on net class rules.
This is a 2.5D approach where we pre-assign layers rather than doing full 3D A* search.

Phase D batch D7 of the Rust Orchestration Engine plan (2026-08-09-001): the
**run orchestration** (the ``state.netlist`` guard, the design-bundle
``assign_layers`` kernel call and the ``frozenset`` write) is implemented in
Rust (``temper-orchestration``'s ``LayerAssignmentStage`` /
``run_layer_assignment``), crossing the FFI once per stage call. The net-class
→ (layer, is_plane) mapping table and the per-net assignment loop stay
single-source in ``temper_design_bundle_python``; ``LayerAssignment`` is the
pyo3 pyclass re-exported here under the pre-migration name, and
``_assign_layer_by_net_class`` stays as a directly-exercised public method.
The pre-migration implementation is pinned VERBATIM in
``tests/deterministic/_layer_assignment_run_py_oracle.py``.
"""

import temper_design_bundle_python as _tdb
import temper_orchestration as _to

from ..state import BoardState
from .base import Stage

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
        """Run the layer-assignment orchestration in Rust (Phase D D7);
        crosses the FFI once per stage call."""
        return _to.run_layer_assignment(state, self)

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
