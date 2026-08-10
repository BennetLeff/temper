"""Placement-phase methods for phased component assignment.

Contains the :class:`_PhasePlacementMixin` with slot selection/scoring and
wirelength computation.

Wave 4, **Phase 5, final leaves**: the HPWL wirelength kernel
(``_compute_wirelength``) is implemented in Rust in the ``temper-design-bundle``
crate (``temper_design_bundle_python.deterministic_phase``).

Phase D batch D5 of the Rust Orchestration Engine plan (2026-08-09-001): the
placement orchestration (``_place_template`` / ``_place_proximity`` /
``_place_optimize`` / ``_simple_greedy_placement`` / ``_filter_by_domain`` and
the ``_select_best_slot`` scoring loop) is implemented in Rust
(``temper-orchestration``'s ``PhasedAssignmentStage``) and runs inside the
migrated ``run()``. This module keeps the public helper methods
(``_select_best_slot`` as a thin FFI delegation to the Rust scoring kernel,
``_compute_wirelength`` delegating to the design-bundle kernel) and the
shapely ``_filter_by_domain`` predicate stays single-source (the Rust stage
drives it through the shapely objects at runtime, exactly like the D4 stage).

Bit-exactness: the Rust kernel replicates the oracle's
``[candidate_slot]`` + placed-other-net-members position list (pin order
preserved, duplicates kept), the ``len(positions) > 1`` gate and the
``(max(xs) - min(xs)) + (max(ys) - min(ys))`` HPWL with CPython
``min``/``max`` (first-argument-on-ties) folds. Verified by
``tests/deterministic/stages/test_phase_zones_rust_differential.py``
(oracle: ``tests/deterministic/stages/_phase_zones_py_oracle.py``) and the
D5 stage differential; the structural proof lives in
``packages/temper-design-bundle/VERIFICATION.md`` and
``packages/temper-orchestration/VERIFICATION.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb
import temper_orchestration as _to

if TYPE_CHECKING:
    from temper_placer.core.component import Component
    from temper_placer.core.netlist import Netlist


class _PhasePlacementMixin:
    """Placement-phase methods for phased component assignment.

    Provides _select_best_slot (FFI delegation to the Rust scoring kernel)
    and _compute_wirelength (design-bundle kernel).
    """

    def _select_best_slot(
        self,
        component_ref: str,
        candidate_slots: list[tuple[float, float]],
        current_placements: dict[str, tuple[float, float]],
        phase_placements: dict[str, tuple[float, float]],
        net_pins: dict[str, list],
    ) -> tuple[float, float] | None:
        """Select best slot using filter + scorer + wirelength.

        Algorithm:
          1. Filter out slots that violate hard constraints
          2. Score remaining slots (lower = better):
             - Soft constraint penalties
             - HPWL wirelength
          3. Return slot with lowest score

        Args:
            component_ref: Component to place
            candidate_slots: Available slots to consider
            current_placements: Already-placed components
            phase_placements: Components placed in this phase
            net_pins: Net connectivity

        Returns:
            Best slot or None if no valid slots

        The scoring loop (slot_filter / slot_scorer / wirelength /
        routability with CPython first-minimum-wins ``min`` semantics) is
        implemented in Rust (Phase D D5); this method is a thin FFI
        delegation for public-API parity.
        """
        return _to.run_phase_select_best_slot(
            self,
            component_ref,
            candidate_slots,
            current_placements,
            phase_placements,
            net_pins,
        )

    def _compute_wirelength(
        self,
        component_ref: str,
        candidate_slot: tuple[float, float],
        net_pins: dict[str, list],
        current_placements: dict[str, tuple[float, float]],
    ) -> float:
        """Compute HPWL (Half-Perimeter Wirelength) for placing component at slot."""
        return _tdb.deterministic_phase.compute_wirelength_py(
            component_ref, candidate_slot, net_pins, current_placements
        )
