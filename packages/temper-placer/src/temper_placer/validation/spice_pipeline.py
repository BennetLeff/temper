"""
Orchestration pipeline for automated SPICE validation of PCB placements.

This module integrates placement-derived parameters (like loop inductance)
with SPICE simulation templates to provide electrical correctness checks
during or after optimization.
"""

from __future__ import annotations

import logging
from typing import Any

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.validation.spice import (
    NgspiceValidator,
    PlacementSpiceResult,
    run_all_placement_validations,
)

logger = logging.getLogger(__name__)

class SpiceValidationPipeline:
    """
    High-level pipeline for running electrical validation simulations.
    """

    def __init__(
        self,
        validator: NgspiceValidator | None = None,
        config: dict[str, Any] | None = None
    ):
        self.validator = validator or NgspiceValidator()
        self.config = config or {}

    def validate_placement(
        self,
        state: PlacementState,
        netlist: Netlist,
        _board: Board
    ) -> dict[str, PlacementSpiceResult]:
        """
        Run all configured SPICE validations for a given placement.

        Args:
            state: Current placement state.
            netlist: Netlist containing component info.
            board: Board dimensions and stackup info.

        Returns:
            Dict mapping simulation name to result.
        """
        if not self.validator.is_available():
            logger.warning("Ngspice not found. Skipping SPICE validation.")
            return {}

        # 1. Convert state to component position dict
        comp_positions = {}
        for i, comp in enumerate(netlist.components):
            comp_positions[comp.ref] = (float(state.positions[i, 0]), float(state.positions[i, 1]))

        # 2. Run validations
        # We reuse the existing run_all_placement_validations from spice.py
        # but we could add more logic here for custom loops.
        results = run_all_placement_validations(
            self.validator,
            comp_positions,
            self.config
        )

        return results

    def print_report(self, results: dict[str, PlacementSpiceResult]):
        """Print a summary of validation results to the log."""
        if not results:
            print("No SPICE results to report.")
            return

        print("\n" + "="*40)
        print(" ELECTRICAL VALIDATION REPORT (SPICE)")
        print("="*40)

        all_passed = True
        for _name, res in results.items():
            print(f"\n{res.summary()}")
            if not res.passed:
                all_passed = False

        print("\n" + "="*40)
        status = "PASSED" if all_passed else "FAILED"
        print(f" OVERALL STATUS: {status}")
        print("="*40 + "\n")
