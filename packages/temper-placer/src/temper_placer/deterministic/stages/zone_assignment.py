"""Zone assignment for the deterministic placement pipeline.

The pure compute is implemented in Rust in the ``temper-design-bundle`` crate
(Wave 4 **Phase 5, first slice** — deterministic leaf stages). This module
keeps the pre-migration public API unchanged and delegates
``_assign_components_to_zones`` to
``temper_design_bundle_python.deterministic_stages.assign_component_zones``;
the ``run`` orchestration (the ``state.netlist`` guard and the ``frozenset``
wrap) stays Python.

Bit-exactness: the Rust kernel reads the same ``Netlist`` pyclass attribute
surface the oracle reads (``nets`` / ``components`` / ``net.name`` /
``net.net_class`` / ``net.pins`` / ``component.ref``) and reproduces the five
priority-ordered rules (``U_MCU`` prefix, SPI/I2C/UART protocol substrings on
the uppercased net name, ``HighVoltage`` net class, ``Power`` net class,
``Signal`` default). ``(ref, zone)`` pairs are returned in
``netlist.components`` order so the dict insertion order is pinned. Verified
by ``tests/deterministic/stages/test_zone_assignment_rust_differential.py``
(oracle: ``tests/deterministic/stages/_zone_assignment_py_oracle.py``) and
the PBT suite ``test_zone_assignment_pbt.py``; the structural proof lives in
``packages/temper-design-bundle/VERIFICATION.md``.
"""

from dataclasses import replace

import temper_design_bundle_python as _tdb

from ..state import BoardState
from .base import Stage


class ZoneAssignmentStage(Stage):
    @property
    def name(self) -> str:
        return "zone_assignment"

    def run(self, state: BoardState) -> BoardState:
        if not state.netlist:
            return state

        component_zone_map = self._assign_components_to_zones(state.netlist)
        return replace(state, component_zone_map=frozenset(component_zone_map.items()))

    def _assign_components_to_zones(self, netlist) -> dict[str, str]:
        """
        Assign components to zones based on net classes and component types.

        Rules (in priority order):
        1. MCU Zone: Components with ref prefix "U_MCU" or connected to SPI/I2C/UART nets
        2. HV Zone: Components connected to "HighVoltage" net class
        3. Power Zone: Components connected to "Power" net class
        4. Signal Zone: Default for all other components
        """
        return dict(_tdb.deterministic_stages.assign_component_zones(netlist))
