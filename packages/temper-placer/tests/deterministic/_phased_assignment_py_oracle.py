# ORACLE COPY -- DO NOT EDIT, DO NOT "FIX".
#
# Verbatim copy of the pre-migration source of the phased-component-assignment
# orchestration (the D5 `_phase_*` mixins):
#   packages/temper-placer/src/temper_placer/deterministic/stages/_phase_core.py
#   packages/temper-placer/src/temper_placer/deterministic/stages/_phase_zones.py
#   packages/temper-placer/src/temper_placer/deterministic/stages/_phase_rotation.py
#   packages/temper-placer/src/temper_placer/deterministic/stages/_phase_validation.py
#   packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py (aggregation)
# at the D5 dispatch base (origin/main 66f84b87), concatenated into one module.
# Relative imports are adapted to absolute paths so the oracle imports from
# the test tree; cross-mixin imports collapse to the same-module definitions;
# every other line is the verbatim pre-migration source.
#
# This is the R1a behavioural oracle for the D5 Rust Stage-engine port in
# packages/temper-orchestration (plan 2026-08-09-001, Phase D batch D5). It
# must keep the ORIGINAL pure-Python semantics forever, including any warts.
# If a differential test fails, the Rust side is wrong until proven
# otherwise -- never edit this file to make a test pass.
#
# test_deterministic_d5_rust_differential.py recomputes the sha256 of
# everything below the marker and fails if this file drifts.
# --- BEGIN PINNED BODY ---
from __future__ import annotations
# ===================================================================
# [1/5] _phase_core.py (verbatim)
"""Core orchestration for phased component assignment.

Contains the :class:`_PhaseCoreMixin` with __init__, name, invariants, run,
phase dispatch (_phased_placement), domain lookups, and shared utility methods.
"""


import logging
import math
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from temper_placer.constraints.compiler import ConstraintCompiler
from temper_placer.io.config_loader import IsolationSlot, PlacementConstraints

from temper_placer.deterministic.channels import ChannelMap
from temper_placer.deterministic.state import BoardState

if TYPE_CHECKING:
    from shapely.geometry import Polygon

    from temper_placer.core.component import Component
    from temper_placer.core.netlist import Netlist


CRITICAL_BOTTLENECK_INVARIANT: str = "no_component_center_in_critical_bottleneck"


class PhasedComponentAssignmentError(Exception):
    """Raised when a phased-placement stage invariant hard-fails.

    Used by the U6 DRC fence flip. The message includes the offending
    component ref and bottleneck severity so the failure is actionable
    from a CI log.
    """


class _PhaseCoreMixin:
    """Core orchestration mixin for phased component placement.

    Provides __init__, name, invariants, run, phase dispatch,
    and shared utility methods.
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
        """Execute phased placement."""
        if not state.netlist or not state.component_zone_map or not state.zone_slots:
            return state
        assert state.netlist is not None
        assert state.component_zone_map is not None
        assert state.zone_slots is not None
        logger = logging.getLogger(__name__)

        errors = self.compiler.validate(state.board, state.netlist)
        if errors:
            for error in errors:
                logger.warning(f"Constraint validation: {error}")

        if self.design_rules is not None and getattr(state, "design_rules", None) is None:
            state = replace(state, design_rules=self.design_rules)

        domain_for_ref, domain_regions = self._domain_lookups(state)

        assert state.netlist is not None, "Netlist must be set in BoardState"
        placements, used_slots = self._phased_placement(
            state,
            state.netlist,
            dict(state.component_zone_map),
            dict(state.zone_slots),
            domain_for_ref,
            domain_regions,
        )

        new_state = replace(
            state,
            placements=frozenset(placements.items()),
            used_slots=frozenset(used_slots),
        )

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

        return new_state

    @staticmethod
    def _domain_lookups(
        state: BoardState,
    ) -> tuple[dict[str, str], dict[str, Polygon]]:
        domain_for_ref: dict[str, str] = {}
        domain_regions: dict[str, Polygon] = {}
        if not state.component_domain_map or not state.domain_regions:
            return domain_for_ref, domain_regions
        for ref, domain in state.component_domain_map:
            domain_for_ref[ref] = domain
        regions = state.domain_regions
        if len(regions) >= 2:
            domain_regions["HV_edge"] = regions[0]
            domain_regions["LV_interior"] = regions[1]
        elif len(regions) == 1:
            domain_regions["LV_interior"] = regions[0]
        return domain_for_ref, domain_regions

    def _phased_placement(
        self,
        _state: BoardState,
        netlist: Netlist,
        component_zone_map: dict[str, str],
        zone_slots: dict[str, tuple],
        domain_for_ref: Mapping[str, str] | None = None,
        domain_regions: Mapping[str, Polygon] | None = None,
    ) -> tuple[dict[str, tuple[float, float]], set[tuple[float, float]]]:
        """Execute placement in priority-defined phases.

        Returns:
            Tuple of (placements dict, used_slots set)
        """
        placements: dict[str, tuple[float, float]] = {}
        used_slots: set[tuple[float, float]] = set()

        comp_by_ref = {c.ref: c for c in netlist.components}
        net_pins = self._build_net_pins(netlist)
        all_slots = self._flatten_slots(zone_slots)

        phases = self.constraints.placement_priority

        if not phases:
            return self._simple_greedy_placement(netlist, component_zone_map, zone_slots)

        placed_refs: set[str] = set()

        for phase_name, phase_config in phases.items():
            method = phase_config.get("method", "optimize")
            components = phase_config.get("components", [])

            if method == "auto" or not components:
                components = [c.ref for c in netlist.components if c.ref not in placed_refs]

            components = [
                ref for ref in components if ref in comp_by_ref and ref not in placed_refs
            ]

            if not components:
                continue

            if method == "template":
                phase_placements = self._place_template(
                    components,
                    phase_config,
                    comp_by_ref,
                    all_slots,
                    used_slots,
                    current_placements=placements,
                    netlist=netlist,
                )
            elif method == "proximity":
                phase_placements = self._place_proximity(
                    components,
                    phase_config,
                    comp_by_ref,
                    placements,
                    zone_slots,
                    used_slots,
                    all_slots,
                    net_pins,
                    netlist=netlist,
                )
            elif method == "optimize" or method == "auto":
                phase_placements = self._place_optimize(
                    components,
                    comp_by_ref,
                    component_zone_map,
                    zone_slots,
                    placements,
                    used_slots,
                    all_slots,
                    net_pins,
                    netlist=netlist,
                    domain_for_ref=domain_for_ref,
                    domain_regions=domain_regions,
                )
            else:
                logging.getLogger(__name__).warning(
                    f"Unknown placement method '{method}' in phase '{phase_name}'"
                )
                continue

            placements.update(phase_placements)
            placed_refs.update(phase_placements.keys())

        return placements, used_slots

    def _build_net_pins(self, netlist: Netlist) -> dict[str, list]:
        """Build net_name -> [(comp_ref, pin_name), ...] map."""
        net_pins = {}
        for net in netlist.nets:
            net_pins[net.name] = list(net.pins)
        return net_pins

    def _flatten_slots(self, zone_slots: dict[str, tuple]) -> list[tuple[float, float]]:
        """Flatten zone_slots to single list of all slots."""
        all_slots: list[tuple[float, float]] = []
        for slots in zone_slots.values():
            all_slots.extend(slots)
        return all_slots

    def _get_footprint_radius(self, component: Component) -> float:
        """Get minimum radius to enclose component footprint."""
        if hasattr(component, "bounds") and component.bounds:
            w, h = component.bounds
            return math.sqrt(w**2 + h**2) / 2 + 1.0
        return self.slot_spacing / 2.0

    def _reserve_slots(
        self,
        center: tuple[float, float],
        radius: float,
        all_slots: list[tuple[float, float]],
        used_slots: set[tuple[float, float]],
    ) -> None:
        """Reserve all slots within radius of center."""
        cx, cy = center
        for slot in all_slots:
            sx, sy = slot
            dist = math.sqrt((sx - cx) ** 2 + (sy - cy) ** 2)
            if dist <= radius:
                used_slots.add(slot)

    def _distance(self, p1: tuple[float, float], p2: tuple[float, float]) -> float:
        """Euclidean distance between two points."""
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
# ===================================================================
# [2/5] _phase_zones.py (verbatim)
"""Placement-phase methods for phased component assignment.

Contains the :class:`_PhasePlacementMixin` with _place_template,
_place_proximity, _place_optimize, slot scoring, wirelength, and
fallback greedy placement.

Wave 4, **Phase 5, final leaves**: the HPWL wirelength kernel
(``_compute_wirelength``) is implemented in Rust in the ``temper-design-bundle``
crate (``temper_design_bundle_python.deterministic_phase``). This module keeps
the pre-migration public API unchanged and delegates; the constraint-bound
surfaces (``self.slot_filter`` / ``self.slot_scorer`` from the
ConstraintCompiler), the shapely ``_filter_by_domain`` and the placement
orchestration stay Python.

Bit-exactness: the Rust kernel replicates the oracle's
``[candidate_slot]`` + placed-other-net-members position list (pin order
preserved, duplicates kept), the ``len(positions) > 1`` gate and the
``(max(xs) - min(xs)) + (max(ys) - min(ys))`` HPWL with CPython
``min``/``max`` (first-argument-on-ties) folds. Verified by
``tests/deterministic/stages/test_phase_zones_rust_differential.py``
(oracle: ``tests/deterministic/stages/_phase_zones_py_oracle.py``); the
structural proof lives in ``packages/temper-design-bundle/VERIFICATION.md``.
"""


from collections.abc import Mapping
from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb

from temper_placer.deterministic.channels import routability_penalty

if TYPE_CHECKING:
    from shapely.geometry import Polygon

    from temper_placer.core.component import Component
    from temper_placer.core.netlist import Netlist


class _PhasePlacementMixin:
    """Placement-phase methods for phased component assignment.

    Provides _place_template, _place_proximity, _place_optimize,
    slot selection/scoring, wirelength computation, domain filtering,
    and fallback greedy placement.
    """

    def _place_template(
        self,
        components: list[str],
        phase_config: dict,
        comp_by_ref: dict[str, Component],
        all_slots: list[tuple[float, float]],
        used_slots: set[tuple[float, float]],
        current_placements: dict[str, tuple[float, float]] | None = None,
        netlist: Netlist | None = None,
    ) -> dict[str, tuple[float, float]]:
        """Place components using a template (e.g., half-bridge layout).

        Template defines relative positions. Anchor defines absolute position.

        Args:
            components: Component refs to place
            phase_config: Template config with 'template' and 'anchor'
            comp_by_ref: Component lookup
            all_slots: All available slots
            used_slots: Already-used slots
            current_placements: Already-placed components (cumulative, for U2)
            netlist: Full netlist (for U2 nearest-HV-pin lookup)

        Returns:
            Dict of ref -> (x, y) for this phase
        """
        phase_config.get("template")
        anchor = phase_config.get("anchor", [0, 0])

        placements: dict[str, tuple[float, float]] = {}

        for i, ref in enumerate(components):
            if ref not in comp_by_ref:
                continue

            offset_y = i * 10.0
            pos = (float(anchor[0]), float(anchor[1]) + offset_y)

            placements[ref] = pos

            cumulative = {**(current_placements or {}), **placements}
            self._reserve_slots_with_hv(
                comp_by_ref[ref],
                pos,
                all_slots,
                used_slots,
                placements=cumulative,
                netlist=netlist,
            )

        return placements

    def _place_proximity(
        self,
        components: list[str],
        phase_config: dict,
        comp_by_ref: dict[str, Component],
        current_placements: dict[str, tuple[float, float]],
        zone_slots: dict[str, tuple],
        used_slots: set[tuple[float, float]],
        all_slots: list[tuple[float, float]],
        net_pins: dict[str, list],
        netlist: Netlist | None = None,
    ) -> dict[str, tuple[float, float]]:
        """Place components near a reference component.

        Uses constraint-aware slot selection within max_distance of reference.

        Args:
            components: Component refs to place
            phase_config: Proximity config with 'reference' and 'max_distance_mm'
            comp_by_ref: Component lookup
            current_placements: Already-placed components
            zone_slots: Slots by zone
            used_slots: Already-used slots
            all_slots: All available slots
            net_pins: Net connectivity

        Returns:
            Dict of ref -> (x, y) for this phase
        """
        reference_ref = phase_config.get("reference")
        max_distance_mm = phase_config.get("max_distance_mm", 20.0)

        if not reference_ref or reference_ref not in current_placements:
            return self._place_optimize(
                components,
                comp_by_ref,
                {},
                zone_slots,
                current_placements,
                used_slots,
                all_slots,
                net_pins,
            )

        reference_pos = current_placements[reference_ref]
        placements: dict[str, tuple[float, float]] = {}

        for ref in components:
            if ref not in comp_by_ref:
                continue

            component = comp_by_ref[ref]

            all_zone_slots: list[tuple[float, float]] = []
            for slots in zone_slots.values():
                all_zone_slots.extend(slots)

            nearby_slots = [
                slot
                for slot in all_zone_slots
                if slot not in used_slots and self._distance(slot, reference_pos) <= max_distance_mm
            ]

            if not nearby_slots:
                continue

            best_slot = self._select_best_slot(
                ref, nearby_slots, current_placements, placements, net_pins
            )

            if best_slot:
                placements[ref] = best_slot
                cumulative = {**current_placements, **placements}
                self._reserve_slots_with_hv(
                    component,
                    best_slot,
                    all_slots,
                    used_slots,
                    placements=cumulative,
                    netlist=netlist,
                )

        return placements

    def _place_optimize(
        self,
        components: list[str],
        comp_by_ref: dict[str, Component],
        component_zone_map: dict[str, str],
        zone_slots: dict[str, tuple],
        current_placements: dict[str, tuple[float, float]],
        used_slots: set[tuple[float, float]],
        all_slots: list[tuple[float, float]],
        net_pins: dict[str, list],
        netlist=None,
        domain_for_ref: Mapping[str, str] | None = None,
        domain_regions: Mapping[str, Polygon] | None = None,
    ) -> dict[str, tuple[float, float]]:
        """Place components using constraint-aware greedy optimization.

        This is the core placement algorithm:
          1. Sort by footprint size (largest first)
          2. Filter slots using hard constraints
          3. **Apply bottleneck-map seed filter** (when enabled+available)
          4. Score slots using soft constraints + wirelength
          5. Select best slot

        Args:
            components: Components to place
            comp_by_ref: Component lookup
            component_zone_map: Component -> zone assignments
            zone_slots: Slots by zone
            current_placements: Already-placed components
            used_slots: Already-used slots
            all_slots: All available slots
            net_pins: Net connectivity
            domain_for_ref: feat/hv-lv-guard-strip per-ref domain assignments.
            domain_regions: Polygon lookup keyed by domain name.

        Returns:
            Dict of ref -> (x, y) for this phase
        """
        placements: dict[str, tuple[float, float]] = {}

        def get_size(ref: str) -> float:
            comp = comp_by_ref.get(ref)
            if comp and hasattr(comp, "bounds") and comp.bounds:
                return max(comp.bounds)
            return 0

        sorted_components = sorted(components, key=lambda r: (-get_size(r), r))

        for ref in sorted_components:
            if ref not in comp_by_ref:
                continue

            component = comp_by_ref[ref]
            zone_name = component_zone_map.get(ref, "Signal")

            zone_slot_list = list(zone_slots.get(zone_name, ()))
            available_slots = [s for s in zone_slot_list if s not in used_slots]

            if not available_slots:
                for slots in zone_slots.values():
                    available_slots = [s for s in slots if s not in used_slots]
                    if available_slots:
                        break

            if not available_slots:
                continue

            available_slots = self._apply_bottleneck_filter(ref, available_slots, comp_by_ref)

            if not available_slots:
                continue

            available_slots = self._filter_by_domain(
                ref, available_slots, domain_for_ref, domain_regions
            )

            if not available_slots:
                continue

            best_slot = self._select_best_slot(
                ref, available_slots, current_placements, placements, net_pins
            )

            if best_slot:
                placements[ref] = best_slot
                cumulative = {**current_placements, **placements}
                self._reserve_slots_with_hv(
                    component,
                    best_slot,
                    all_slots,
                    used_slots,
                    placements=cumulative,
                    netlist=netlist,
                )

        return placements

    @staticmethod
    def _filter_by_domain(
        ref: str,
        slots: list[tuple[float, float]],
        domain_for_ref: Mapping[str, str] | None,
        domain_regions: Mapping[str, Polygon] | None,
    ) -> list[tuple[float, float]]:
        if not domain_for_ref or not domain_regions:
            return slots
        domain = domain_for_ref.get(ref)
        if not domain:
            return slots
        region = domain_regions.get(domain)
        if region is None or region.is_empty:
            return slots
        from shapely.geometry import Point

        return [s for s in slots if region.covers(Point(s[0], s[1]))]

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
        """
        all_placements = {**current_placements, **phase_placements}

        valid_slots = [
            slot
            for slot in candidate_slots
            if self.slot_filter(slot, component_ref, all_placements)
        ]

        if not valid_slots:
            valid_slots = candidate_slots

        def score_slot(slot: tuple[float, float]) -> float:
            constraint_penalty = self.slot_scorer(slot, component_ref, all_placements)
            wirelength = self._compute_wirelength(component_ref, slot, net_pins, all_placements)
            cm = self.channel_map
            if cm is not None and self.w_r > 0.0:
                routability = routability_penalty(slot, cm) * self.w_r
            else:
                routability = 0.0
            return constraint_penalty + wirelength * 0.1 + routability

        best_slot = min(valid_slots, key=score_slot)
        return best_slot

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

    def _simple_greedy_placement(
        self,
        netlist: Netlist,
        component_zone_map: dict[str, str],
        zone_slots: dict[str, tuple],
    ) -> tuple[dict[str, tuple[float, float]], set[tuple[float, float]]]:
        """Fallback: simple greedy placement (same as ComponentAssignmentStage).

        Returns a ``(placements, used_slots)`` tuple mirroring the
        phase-based path.  HV creepage rings are NOT added in the
        fallback (NFR4 parity — the fallback predates U1 and is only
        used when ``placement_priority`` is empty).
        """
        placements: dict[str, tuple[float, float]] = {}
        used_slots: set[tuple[float, float]] = set()

        net_pins = self._build_net_pins(netlist)
        all_slots = self._flatten_slots(zone_slots)
        {c.ref: c for c in netlist.components}

        def get_size(comp):
            if hasattr(comp, "bounds") and comp.bounds:
                return max(comp.bounds)
            return 0

        sorted_components = sorted(netlist.components, key=lambda c: (-get_size(c), c.ref))

        for component in sorted_components:
            ref = component.ref
            zone_name = component_zone_map.get(ref, "Signal")

            zone_slot_list = list(zone_slots.get(zone_name, ()))
            available = [s for s in zone_slot_list if s not in used_slots]

            if not available:
                continue

            best_slot = min(
                available,
                key=lambda s: self._compute_wirelength(ref, s, net_pins, placements),
            )

            placements[ref] = best_slot
            radius = self._get_footprint_radius(component)
            self._reserve_slots(best_slot, radius, all_slots, used_slots)

        return placements, used_slots
# ===================================================================
# [3/5] _phase_rotation.py (verbatim)
"""HV creepage and isolation-slot reduction for phased component assignment.

Contains the :class:`_PhaseHVMixin` with ghost-pad injection (U1),
isolation-slot reduction (U2), and HV-pin position collection.

Wave 4, **Phase 5, final leaves**: the U2 isolation-slot reduction kernel
(``_effective_ghost_pad_radius``) is implemented in Rust in the
``temper-design-bundle`` crate (``temper_design_bundle_python.deterministic_phase``).
This module keeps the pre-migration public API unchanged and delegates; the
NFR4 ``use_isolation_slots`` toggle and the per-ref slot lookup stay Python.

Bit-exactness: the Rust kernel replicates the oracle's ``math.hypot`` (Dekker
vector_norm, NOT libm hypot), the ``d_len <= 0.0`` early-out, the strict
``projection > 0.0`` accumulation and the ``max(0.0, ...)`` clamp. Verified by
``tests/deterministic/stages/test_phase_rotation_rust_differential.py``
(oracle: ``tests/deterministic/stages/_phase_rotation_py_oracle.py``); the
structural proof lives in ``packages/temper-design-bundle/VERIFICATION.md``.
"""


from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb

if TYPE_CHECKING:
    from temper_placer.core.component import Component
    from temper_placer.core.netlist import Netlist


class _PhaseHVMixin:
    """HV creepage / ghost-pad injection and isolation-slot reduction.

    Provides _collect_hv_pin_positions, _effective_ghost_pad_radius,
    _reserve_slots_with_hv, and _is_hv_ref.
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

    def _reserve_slots_with_hv(
        self,
        component: Component,
        placed_pos: tuple[float, float],
        all_slots: list[tuple[float, float]],
        used_slots: set[tuple[float, float]],
        placements: dict[str, tuple[float, float]] | None = None,
        netlist: Netlist | None = None,
    ) -> None:
        """Reserve the footprint ring AND any HV-pin creepage ring for a placed component.

        Wraps ``_reserve_slots`` (footprint ring) and, when the placer
        has design_rules available, adds a creepage-radius reservation
        around every HV pin's ABSOLUTE position (placed + pin-relative
        offset).  This is the per-placement hook for the U1
        ghost-pad injection: doing it at placement time, with the
        actual placed coordinates, is the only physically correct
        semantic — pin-relative injection would reserve slots at the
        wrong absolute location.

        HV ring reservation respects U2 isolation-slot reductions
        (``_effective_ghost_pad_radius``) and never expands beyond
        the FR4 base radius.

        ``placements`` and ``netlist`` are the cumulative placement
        view and the full netlist, used to find the nearest HV pin on
        a different component for the U2 projection.  When either is
        missing, the placer falls back to the full base radius (no
        isolation-slot reduction) — this preserves the NFR4 parity
        for callers that don't thread the full context.
        """
        radius = self._get_footprint_radius(component)
        self._reserve_slots(placed_pos, radius, all_slots, used_slots)

        if self.design_rules is None or component.pins is None:
            return

        base_radius = 0.0
        for rules in getattr(self.design_rules, "net_classes", {}).values():
            safety = getattr(rules, "safety_category", None)
            if safety in self._HV_SAFETY_CATEGORIES:
                base_radius = max(base_radius, float(getattr(rules, "creepage_mm", 0.0)))
        if base_radius <= 0.0:
            return

        other_hv_pins: list[tuple[float, float]] = []
        if placements is not None and netlist is not None:
            net_class_assignments_other = (
                getattr(self.design_rules, "net_class_assignments", {}) or {}
            )
            net_classes_other = getattr(self.design_rules, "net_classes", {}) or {}
            for other_ref, other_pos in placements.items():
                if other_ref == component.ref:
                    continue
                other_comp = next((c for c in netlist.components if c.ref == other_ref), None)
                if other_comp is None or other_comp.pins is None:
                    continue
                ox, oy = other_pos
                for op in other_comp.pins:
                    if op.net is None:
                        continue
                    other_class = net_class_assignments_other.get(op.net)
                    if other_class is None or other_class not in net_classes_other:
                        continue
                    other_safety = getattr(net_classes_other[other_class], "safety_category", None)
                    if other_safety not in self._HV_SAFETY_CATEGORIES:
                        continue
                    opx, opy = op.position
                    other_hv_pins.append((ox + float(opx), oy + float(opy)))

        net_class_assignments = getattr(self.design_rules, "net_class_assignments", {}) or {}
        net_classes = getattr(self.design_rules, "net_classes", {}) or {}
        cx, cy = placed_pos
        for pin in component.pins:
            if pin.net is None:
                continue
            class_name = net_class_assignments.get(pin.net)
            if class_name is None or class_name not in net_classes:
                continue
            safety = getattr(net_classes[class_name], "safety_category", None)
            if safety not in self._HV_SAFETY_CATEGORIES:
                continue
            px, py = pin.position
            abs_x = cx + float(px)
            abs_y = cy + float(py)
            nearest_other = (0.0, 0.0)
            if other_hv_pins:
                nearest_other = min(
                    other_hv_pins,
                    key=lambda p: (p[0] - abs_x) ** 2 + (p[1] - abs_y) ** 2,
                )
            ring_radius = self._effective_ghost_pad_radius(
                component.ref,
                pin.name,
                base_radius,
                (abs_x, abs_y),
                nearest_other,
            )
            if ring_radius <= 0.0:
                continue
            self._reserve_slots((abs_x, abs_y), ring_radius, all_slots, used_slots)

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
# ===================================================================
# [4/5] _phase_validation.py (verbatim)
"""Validation methods for phased component assignment.

Contains the :class:`_PhaseValidationMixin` with bottleneck-map seed
filtering, critical-bottleneck violation detection, and the invariant
check.

Wave 4, **Phase 5, final leaves**: the critical-bottleneck violation kernel
(``find_critical_bottleneck_violations``) is implemented in Rust in the
``temper-design-bundle`` crate (``temper_design_bundle_python.deterministic_phase``).
This module keeps the pre-migration public API unchanged and delegates; the
``self.channel_map`` guard, the seed-filter orchestration and the DRC-fence
raise/opt-out logic stay Python.

Bit-exactness: the Rust kernel replicates the oracle's floor-to-cell grid
indexing (``int(math.floor((float(x_mm) * 1000.0) / cell_um))``), the
per-cell first-wins-on-score-ties critical map, and the VERBATIM quirk that
the violation ``severity`` reads the LAST bottleneck's severity (the first
loop's trailing ``bn``), not the matched cell's. Verified by
``tests/deterministic/stages/test_phase_validation_rust_differential.py``
(oracle: ``tests/deterministic/stages/_phase_validation_py_oracle.py``); the
structural proof lives in ``packages/temper-design-bundle/VERIFICATION.md``.
"""


import logging

import temper_design_bundle_python as _tdb

from temper_placer.deterministic.flags import is_drc_fence_fail_enabled
from temper_placer.deterministic.stages._phase_core import PhasedComponentAssignmentError

_LOGGER = logging.getLogger(__name__)


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

# ===================================================================
# [5/5] phased_component_assignment.py aggregation (verbatim)
"""Phased component assignment using priority-based placement.

Implementation decomposed across internal mixin modules:
- _phase_core.py — orchestration (_PhaseCoreMixin)
- _phase_zones.py — placement methods (_PhasePlacementMixin)
- _phase_rotation.py — HV creepage (_PhaseHVMixin)
- _phase_validation.py — bottleneck validation (_PhaseValidationMixin)
"""


from temper_placer.deterministic.stages.base import Stage


class PhasedComponentAssignmentStage(
    _PhaseCoreMixin,
    _PhasePlacementMixin,
    _PhaseHVMixin,
    _PhaseValidationMixin,
    Stage,
):
    """Phased component placement using placement_priority configuration.

    Phases are executed in order:
      1. Fixed/Template - Use explicit positions or templates
      2. Proximity - Place near reference components
      3. Optimize - Constraint-aware greedy placement
      4. Auto - Fill remaining components

    Each phase uses:
      - ConstraintCompiler.filter for hard constraints
      - ConstraintCompiler.scorer for soft constraints
      - HPWL wirelength minimization
    """


__all__ = [
    "CRITICAL_BOTTLENECK_INVARIANT",
    "PhasedComponentAssignmentError",
    "PhasedComponentAssignmentStage",
]
