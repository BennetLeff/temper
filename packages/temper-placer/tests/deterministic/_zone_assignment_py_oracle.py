# ORACLE COPY -- DO NOT EDIT, DO NOT "FIX".
#
# Verbatim copy of the pre-migration source of
#   packages/temper-placer/src/temper_placer/deterministic/stages/zone_assignment.py
# at the D2 dispatch base (origin/main, bd85d76e). Relative imports are
# adapted to absolute paths so the oracle imports from the test tree; every
# other line is the verbatim pre-migration source.
#
# This is the R1a behavioural oracle for the D2 Rust Stage-engine port in
# packages/temper-orchestration (plan 2026-08-09-001, Phase D batch D2). It
# must keep the ORIGINAL pure-Python semantics forever, including any warts.
# If a differential test fails, the Rust side is wrong until proven
# otherwise -- never edit this file to make a test pass.
#
# test_deterministic_d2_rust_differential.py recomputes the sha256 of
# everything below the marker and fails if this file drifts.
# --- BEGIN PINNED BODY ---
from dataclasses import replace

import temper_design_bundle_python as _tdb

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage


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
