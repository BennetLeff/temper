"""Core orchestration for phased component assignment.

Contains the :class:`_PhaseCoreMixin` with __init__, name, invariants, run,
and the shared utility methods.

Collapsed (2026-08-20): the four ``_phase_*`` leaf modules that were split
out during the Wave 4 / Phase 5 and Phase D batch D5 migrations are merged
back into this single module. The mixins they defined are used only by
:class:`PhasedComponentAssignmentStage` (``phased_component_assignment.py``),
which combines them through multiple inheritance:

- ``_phase_core.py``    → orchestration (``_PhaseCoreMixin``) — this module
- ``_phase_zones.py``   → placement methods (``_PhasePlacementMixin``)
- ``_phase_rotation.py`` → HV creepage (``_PhaseHVMixin``)
- ``_phase_validation.py`` → bottleneck validation (``_PhaseValidationMixin``)

The pinned VERBATIM oracle ``tests/deterministic/_phased_assignment_py_oracle.py``
imports ``PhasedComponentAssignmentError`` from this module path, so the
module name is part of the oracle contract and is preserved.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb
import temper_orchestration as _to

from temper_placer.constraints.compiler import ConstraintCompiler
from temper_placer.io.config_loader import IsolationSlot, PlacementConstraints

from ..channels import ChannelMap
from ..flags import is_drc_fence_fail_enabled
from ..state import BoardState

if TYPE_CHECKING:
    from temper_placer.core.component import Component
    from temper_placer.core.netlist import Netlist


CRITICAL_BOTTLENECK_INVARIANT: str = "no_component_center_in_critical_bottleneck"

_LOGGER = logging.getLogger(__name__)


class PhasedComponentAssignmentError(Exception):
    """Raised when a phased-placement stage invariant hard-fails.

    Used by the U6 DRC fence flip. The message includes the offending
    component ref and bottleneck severity so the failure is actionable
    from a CI log.
    """


class _PhaseCoreMixin:
    """Core orchestration mixin for phased component placement.

    Provides __init__, name, invariants, run, and shared utility methods.

    The run() orchestration (Phase D batch D5 of the Rust Orchestration
    Engine plan 2026-08-09-001) is implemented in Rust (``temper-orchestration``'s
    ``PhasedAssignmentStage``): the state guards, ``compiler.validate``, the
    design-rules attach, ``_domain_lookups``, the phase dispatch and the
    template/proximity/optimize placement methods, the HV ghost-pad
    reservation and the ``frozenset`` writes all run Rust-side, crossing the
    FFI once per stage call with the stage instance as the config carrier.
    This module keeps the public API (the constructor, ``name`` and
    ``invariants``) and delegates ``run``. The residual phase arithmetic is
    implemented in Rust in the ``temper-design-bundle`` crate
    (``temper_design_bundle_python.deterministic_phase``), which is called
    directly by the Rust orchestration stage. The router_v6 DRC-fence call-back
    (``register_validator`` / ``run_validators``) stays Python (router_v6
    surface -- the D4 ``StageDRCFailure`` convention). The differential oracle
    for the pre-migration implementation is pinned VERBATIM in
    ``tests/deterministic/_phased_assignment_py_oracle.py``.
    """

    _HV_SAFETY_CATEGORIES: set[str] = {"HV", "AC"}

    def __init__(
        self,
        constraints: PlacementConstraints,
        slot_spacing: float = 12.0,
        fixed_placements: dict[str, dict] | None = None,
        channel_map: ChannelMap | None = None,
        w_r: float = 0.05,
        design_rules=None,
        use_isolation_slots: bool = False,
        seed_filter=None,
    ):
        """Initialize phased placement.

        Args:
            constraints: Parsed placement constraints (for compiler)
            slot_spacing: Spacing between slots in mm
            fixed_placements: Dict of ref -> {'position': [x, y], 'rotation': deg}
            design_rules: PCB design rules (SSOT for creepage_mm per net class).
                When provided, ghost-pad injection uses the HV class creepage
                to reserve slots around HV pin positions (U1). When None,
                injection is a no-op.
            use_isolation_slots: When True (U2), reduce each HV pin's
                effective ghost-pad radius by the projection of the
                referenced isolation slot onto the pin-to-other-HV-pin
                vector (IEC 62368-1 Annex G). When False (default),
                behavior is bit-identical to U1.
        """
        self.constraints = constraints
        self.slot_spacing = slot_spacing
        self.fixed_placements = fixed_placements or {}
        self.channel_map = channel_map
        if channel_map is None:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "channel_map is None; channel-aware scoring and seed "
                "filter will be disabled (R4d fallback)"
            )
        self.w_r = w_r
        if seed_filter is None:
            seed_filter = getattr(constraints, "seed_filter", None)
        self.seed_filter = seed_filter
        self._bottleneck_map = None
        self.compiler = ConstraintCompiler(constraints)
        self.slot_filter = self.compiler.compile_to_slot_filter()
        self.slot_scorer = self.compiler.compile_to_slot_scorer()
        self.design_rules = design_rules
        self.use_isolation_slots = use_isolation_slots
        self._isolation_slots_by_ref: dict[str, list[IsolationSlot]] = {}
        if use_isolation_slots and getattr(constraints, "isolation_slots", None):
            for slot in constraints.isolation_slots:
                self._isolation_slots_by_ref.setdefault(slot.component_ref, []).append(slot)

    @property
    def name(self) -> str:
        return "phased_component_assignment"

    @property
    def invariants(self) -> tuple:
        """Per-stage invariants for the DRC fence.

        The :data:`CRITICAL_BOTTLENECK_INVARIANT` is declared only when a
        ``channel_map`` is supplied; runs without a sidecar cannot run the
        check meaningfully, so the invariant is omitted to avoid spurious
        false positives on degraded runs.
        """
        from temper_placer.validation.drc_fence import InvariantSpec

        if self.channel_map is None or not self.channel_map.has_grid():
            return ()
        return (
            InvariantSpec(
                check_name=CRITICAL_BOTTLENECK_INVARIANT,
                guarantees=(
                    "No component center falls inside a CRITICAL-severity "
                    "bottleneck cell of the channel map."
                ),
            ),
        )

    def run(self, state: BoardState) -> BoardState:
        """Execute phased placement.

        The orchestration is implemented in Rust (Phase D D5); this method
        crosses the FFI once, then runs the router_v6 DRC-fence validator
        call-back (which stays Python -- the router_v6 surface).
        """
        new_state = _to.run_phased_assignment(state, self)
        self._run_phased_drc_fence(new_state)
        return new_state

    def _run_phased_drc_fence(self, new_state: BoardState) -> None:
        """The router_v6 DRC-fence call-back (register + run the HV
        validator on the new state). Stays Python: the validator and the
        ``stage_validators`` registry are router_v6 surface (the D4
        ``StageDRCFailure`` convention).

        Fail-closed since 2026-08-18. This used to end ``except
        ImportError: pass`` -- "swallowed exactly like the pre-migration
        run() body" -- which meant that if the HV validator or the
        validator registry could not be imported, the high-voltage DRC
        fence simply did not run and the stage returned as though it had
        passed. Both imports are first-party; failing to import them is a
        bug, and pass destroyed the evidence of it."""
        logger = logging.getLogger(__name__)
        try:
            from temper_placer.deterministic.stages.phased_component_assignment_validator import (
                validate_phased_component_assignment_hv,
            )
            from temper_placer.router_v6.stage_validators import register_validator, run_validators

            register_validator("PhasedComponentAssignment")(validate_phased_component_assignment_hv)

            failures = run_validators("PhasedComponentAssignment", new_state)
            if failures:
                for f in failures:
                    logger.warning(f"DRC fence failure: {f}")
        except ImportError as e:
            raise ImportError(
                "The phased-assignment HV validator and the router_v6 "
                "stage-validator registry are required to run the DRC fence "
                "and could not be imported. This is a broken temper-placer "
                "install, not an optional feature -- reinstall with: uv sync"
            ) from e

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


class _PhaseHVMixin:
    """HV creepage / ghost-pad injection and isolation-slot reduction.

    Provides _collect_hv_pin_positions, _effective_ghost_pad_radius,
    and _is_hv_ref.
    """

    def _collect_hv_pin_positions(
        self,
        netlist: Netlist,
    ) -> list[tuple[float, float, str, str]]:
        """Collect component-relative (x, y) positions for every HV-class pin.

        Returns a list of (pin_x, pin_y, component_ref, pin_name) tuples
        for pins whose net class has a non-None ``safety_category`` in
        :attr:`_HV_SAFETY_CATEGORIES`.  Pins whose net is missing from
        :attr:`design_rules.net_classes` (or has a non-HV / None safety
        tag) are silently skipped — this preserves NFR4 parity on
        LV-only boards.

        Coordinates are component-RELATIVE (i.e. relative to the
        component's local origin).  Callers that need absolute board
        positions must combine them with the component's actual
        placement.  The placer's per-component hook
        ``_reserve_slots_with_hv`` does exactly that and is the
        production path; this helper exists for the post-stage DRC
        fence validator (U3) and for any future analytic consumer that
        needs the pin-relative coordinate set.
        """
        if self.design_rules is None or not getattr(self.design_rules, "net_classes", None):
            return []

        net_classes = self.design_rules.net_classes
        net_class_assignments = getattr(self.design_rules, "net_class_assignments", {}) or {}

        hv_pins: list[tuple[float, float, str, str]] = []
        for component in netlist.components:
            for pin in component.pins:
                if pin.net is None:
                    continue
                class_name = net_class_assignments.get(pin.net)
                if class_name is None:
                    class_name = next(
                        (nc for nc in net_classes if nc == pin.net),
                        None,
                    )
                if class_name is None or class_name not in net_classes:
                    continue
                safety = getattr(net_classes[class_name], "safety_category", None)
                if safety not in self._HV_SAFETY_CATEGORIES:
                    continue
                px, py = pin.position
                hv_pins.append((float(px), float(py), component.ref, pin.name))
        return hv_pins

    def _effective_ghost_pad_radius(
        self,
        component_ref: str,
        _pin_name: str,
        base_radius: float,
        current_pin_absolute: tuple[float, float],
        nearest_other_hv_pin_absolute: tuple[float, float],
    ) -> float:
        """Apply U2 isolation-slot reduction to a base ghost-pad radius.

        The reduction for each isolation slot is the projection of the
        slot's vector onto the unit vector from ``current_pin_absolute``
        to ``nearest_other_hv_pin_absolute`` (the nearest HV pin on a
        different component).  Slots that are perpendicular to the
        creepage direction reclaim 0mm; slots aligned with the
        direction reclaim their full length.  The projection is
        clamped at 0 (a slot that points away from the other HV pin
        does not extend creepage) and the total reduction is clamped
        at ``base_radius`` (the FR4 SSOT).

        When :attr:`use_isolation_slots` is False, returns
        ``base_radius`` unchanged (NFR4 bit-identical parity with U1).
        When True but the component has no isolation slots, the
        reduction is also 0 (the slot list is the source of truth, not
        the toggle alone).
        """
        if not self.use_isolation_slots:
            return base_radius
        slots = self._isolation_slots_by_ref.get(component_ref, [])
        if not slots:
            return base_radius
        flat_slots = []
        for slot in slots:
            sx0, sy0 = slot.start_offset
            sx1, sy1 = slot.end_offset
            flat_slots.append((sx0, sy0, sx1, sy1))
        return _tdb.deterministic_phase.effective_ghost_pad_radius_py(
            base_radius,
            current_pin_absolute,
            nearest_other_hv_pin_absolute,
            flat_slots,
        )

    def _is_hv_ref(self, ref: str, comp_by_ref: dict[str, Component]) -> bool:
        """Return True if ``ref`` participates in any HV-class net.

        "HV" is determined by :meth:`PlacementConstraints.get_net_class`
        (which flags names containing "HV"/"BUS"/"DC_BUS" as
        HighVoltage) and, when available, by the
        ``NetClassRules.safety_category`` field for that class.
        """
        comp = comp_by_ref.get(ref)
        if comp is None or not hasattr(comp, "pins") or not comp.pins:
            return False
        constraints = self.constraints
        get_net_class = getattr(constraints, "get_net_class", None)
        if get_net_class is None:
            return False
        for pin in comp.pins:
            net = getattr(pin, "net", None)
            if not net:
                continue
            try:
                net_class = get_net_class(net)
            except Exception:
                continue
            if net_class == "HighVoltage":
                return True
            rule = constraints.net_class_rules.get(net_class)
            if rule is not None and getattr(rule, "safety_category", None) == "HV":
                return True
        return False


class _PhaseValidationMixin:
    """Validation and bottleneck-filtering methods.

    Provides _apply_bottleneck_filter, find_critical_bottleneck_violations,
    and _check_critical_bottlenecks.
    """

    def _apply_bottleneck_filter(
        self,
        component_ref: str,
        candidate_slots: list[tuple[float, float]],
        comp_by_ref: dict | None = None,
    ) -> list[tuple[float, float]]:
        """Filter ``candidate_slots`` through the bottleneck map.

        Returns the unfiltered list when:

        * the seed filter is disabled at the config level
        * no ``BottleneckMap`` is reachable on the current state
        * the filter would drop every candidate (empty pool fallback
           per R2; a warning is logged and the original pool passes
           through unchanged)

        Otherwise returns the slot list with cells at or above the
        applicable (LV or HV) threshold removed, and emits one
        structured INFO log line per call with the keys required by R6.

        # @req(2026-06-23-004, R2)
        # @req(2026-06-23-004, R6)
        # @req(2026-06-23-004, K4)
        """
        logger = logging.getLogger(__name__)

        config = self.seed_filter
        if config is None or not config.enabled:
            return candidate_slots
        bmap = self._bottleneck_map
        if bmap is None:
            return candidate_slots

        is_hv = False
        if comp_by_ref is not None:
            is_hv = self._is_hv_ref(component_ref, comp_by_ref)
        limit = config.hv_threshold if is_hv else config.threshold

        accepted: list[tuple[float, float]] = []
        scores_accepted: list[float] = []
        all_scores: list[float] = []
        for slot in candidate_slots:
            score = bmap.score_at(slot[0], slot[1])
            all_scores.append(score)
            if score < limit:
                accepted.append(slot)
                scores_accepted.append(score)

        candidates_total = len(candidate_slots)
        candidates_accepted = len(accepted)
        candidates_rejected = candidates_total - candidates_accepted
        fallback_used = False

        if candidates_accepted == 0 and candidates_total > 0:
            logger.warning(
                "seed_filter: would reject all %d candidates for %s; "
                "falling back to unfiltered pool",
                candidates_total,
                component_ref,
            )
            fallback_used = True
            accepted = list(candidate_slots)
            scores_accepted = list(all_scores)
            candidates_accepted = candidates_total
            candidates_rejected = 0

        avg_score = sum(scores_accepted) / len(scores_accepted) if scores_accepted else 0.0
        logger.info(
            "seed_filter event=seed_filter "
            "component=%s "
            "candidates_total=%d "
            "candidates_accepted=%d "
            "candidates_rejected=%d "
            "avg_bottleneck_score_accepted=%.4f "
            "threshold=%.4f "
            "hv_threshold=%.4f "
            "is_hv=%s "
            "fallback_used=%s",
            component_ref,
            candidates_total,
            candidates_accepted,
            candidates_rejected,
            avg_score,
            config.threshold,
            config.hv_threshold,
            is_hv,
            fallback_used,
        )
        return accepted

    def find_critical_bottleneck_violations(
        self, placements: dict[str, tuple[float, float]]
    ) -> list[dict]:
        """Return a list of CRITICAL-severity bottleneck violations.

        Each violation is a dict with keys ``ref``, ``x``, ``y``, ``layer``,
        ``severity``. The center of each placed component is converted to
        grid coordinates (floor semantics, same as
        :func:`routability_penalty`); any cell covered by a CRITICAL
        bottleneck record produces a violation. MEDIUM/HIGH severities are
        not flagged - the invariant name
        (``no_component_center_in_critical_bottleneck``) is part of the
        contract.

        Out-of-grid placements (gx, gy outside the channel map bounds) are
        not flagged, matching the routability penalty 'no penalty at the
        board edge' semantics.
        """
        if self.channel_map is None or not self.channel_map.has_grid():
            return []

        cmap = self.channel_map
        cell_um = cmap.cell_size_um
        width = cmap.width
        height = cmap.height
        bottlenecks = [
            (bn.x, bn.y, bn.layer, bn.severity, bn.score) for bn in cmap.bottlenecks
        ]
        return _tdb.deterministic_phase.find_critical_bottleneck_violations_py(
            placements,
            bottlenecks,
            cell_um,
            width,
            height,
        )

    def _check_critical_bottlenecks(self, placements: dict[str, tuple[float, float]]) -> list[dict]:
        """Run the invariant check; blocking by default.

        When :func:`is_drc_fence_fail_enabled` returns True (the default),
        the first violation raises :class:`PhasedComponentAssignmentError`
        with the offending ref and severity in the message. Opt out by
        setting :envvar:`TEMPER_DRC_FENCE_FAIL` to ``"0"``, ``"false"``,
        ``"no"``, or ``"off"``.
        """
        violations = self.find_critical_bottleneck_violations(placements)
        for v in violations:
            if is_drc_fence_fail_enabled():
                raise PhasedComponentAssignmentError(
                    f"DRC fence violation (hard-fail): {v['ref']} placed in "
                    f"CRITICAL bottleneck cell ({v['x']}, {v['y']}) on "
                    f"layer {v['layer']}; severity={v['severity']}"
                )
            _LOGGER.warning(
                "DRC fence violation: %s placed in CRITICAL bottleneck cell "
                "(%d, %d) on layer %s; severity=%s",
                v["ref"],
                v["x"],
                v["y"],
                v["layer"],
                v["severity"],
            )
        return violations
