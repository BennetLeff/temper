"""Core orchestration for phased component assignment.

Contains the :class:`_PhaseCoreMixin` with __init__, name, invariants, run,
and the shared utility methods.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb
import temper_orchestration as _to

from temper_placer.constraints.compiler import ConstraintCompiler
from temper_placer.io.config_loader import IsolationSlot, PlacementConstraints

from ..channels import ChannelMap
from ..state import BoardState

if TYPE_CHECKING:
    from temper_placer.core.component import Component


CRITICAL_BOTTLENECK_INVARIANT: str = "no_component_center_in_critical_bottleneck"


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
    This module keeps the public API (the constructor, ``name``,
    ``invariants`` and the ``_get_footprint_radius`` / ``_reserve_slots`` /
    ``_distance`` helpers) and delegates ``run`` and those helpers. The
    residual arithmetic (``_get_footprint_radius``'s
    ``sqrt(w**2 + h**2) / 2 + 1.0``, ``_reserve_slots``'s distance filter and
    ``_distance``'s ``sqrt((p1-p2)**2 + ...)``) is implemented in Rust in the
    ``temper-design-bundle`` crate
    (``temper_design_bundle_python.deterministic_phase``); the Python methods
    are thin delegations. The router_v6 DRC-fence call-back
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
        ``StageDRCFailure`` convention). ImportError is swallowed exactly
        like the pre-migration run() body."""
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
        except ImportError:
            pass

    def _get_footprint_radius(self, component: Component) -> float:
        """Get minimum radius to enclose component footprint.

        The arithmetic (``math.sqrt(w**2 + h**2) / 2 + 1.0`` over the
        component bounds, or ``slot_spacing / 2.0`` on the no-bounds path) is
        implemented in Rust
        (``temper_design_bundle_python.deterministic_phase.footprint_radius_py``);
        the ``hasattr``/truthiness guard stays here.
        """
        bounds = (
            component.bounds
            if (hasattr(component, "bounds") and component.bounds)
            else None
        )
        return _tdb.deterministic_phase.footprint_radius_py(bounds, self.slot_spacing)

    def _reserve_slots(
        self,
        center: tuple[float, float],
        radius: float,
        all_slots: list[tuple[float, float]],
        used_slots: set[tuple[float, float]],
    ) -> None:
        """Reserve all slots within radius of center.

        The distance filter (``math.sqrt((sx-cx)**2 + (sy-cy)**2) <= radius``)
        is implemented in Rust (``reserve_slots_py``); the set mutation stays
        here.
        """
        for slot in _tdb.deterministic_phase.reserve_slots_py(center, radius, all_slots):
            used_slots.add(slot)

    def _distance(self, p1: tuple[float, float], p2: tuple[float, float]) -> float:
        """Euclidean distance between two points.

        Delegates to the Rust kernel
        (``temper_design_bundle_python.deterministic_phase.distance_py``).
        """
        return _tdb.deterministic_phase.distance_py(p1, p2)
