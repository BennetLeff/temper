"""Layer assignment stage for multi-layer routing.

Assigns each net to a preferred layer based on net class rules.
This is a 2.5D approach where we pre-assign layers rather than doing full 3D A* search.

The pure compute is implemented in Rust in the ``temper-design-bundle`` crate
(Wave 4 **Phase 5, batch 2** — deterministic leaf stages): the net-class →
(layer, is_plane) mapping table and the per-net assignment loop delegate to
``temper_design_bundle_python.deterministic_leaves``. ``LayerAssignment`` is
a pyo3 pyclass re-exported here under the pre-migration name; the ``run``
orchestration (the ``state.netlist`` guard and the ``frozenset`` wrap) stays
Python.

Bit-exactness: the net-class table, the manual-assignment branch (plane
status inferred from ``layer in (1, 2)``), the ``or "Signal"`` fallback and
netlist-order iteration are reproduced identically. Verified by
``tests/deterministic/stages/test_layer_assignment_rust_differential.py``
(oracle: ``tests/deterministic/stages/_layer_assignment_py_oracle.py``) and
the PBT suite ``test_layer_assignment_pbt.py``; the structural proof lives
in ``packages/temper-design-bundle/VERIFICATION.md``.
"""

from dataclasses import dataclass, replace

import temper_design_bundle_python as _tdb

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
