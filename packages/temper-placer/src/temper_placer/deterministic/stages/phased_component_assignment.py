"""
Phased component assignment using priority-based placement.

This module implements deterministic placement in multiple phases:
  1. Fixed/Template - Mechanical constraints and power stages
  2. Proximity - Critical components near references
  3. Optimize - Zone-constrained with constraint-aware selection
  4. Auto - Fill remaining components

Uses ConstraintCompiler for constraint-aware slot selection.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from temper_placer.constraints.compiler import ConstraintCompiler
from temper_placer.io.config_loader import IsolationSlot, PlacementConstraints

from ..channels import Bottleneck, ChannelMap, routability_penalty
from ..flags import is_drc_fence_fail_enabled
from ..state import BoardState
from . import phased_component_assignment_validator  # noqa: F401  (registers U3 validator)
from .base import Stage

if TYPE_CHECKING:
    from shapely.geometry import Polygon

    from temper_placer.core.component import Component
    from temper_placer.core.netlist import Netlist


_LOGGER = logging.getLogger(__name__)


#: Invariant name used by the DRC fence. Declared on
#: :class:`PhasedComponentAssignmentStage` only when a ``channel_map`` is
#: present, so runs without a sidecar never report false positives.
CRITICAL_BOTTLENECK_INVARIANT: str = "no_component_center_in_critical_bottleneck"


class PhasedComponentAssignmentError(Exception):
    """Raised when a phased-placement stage invariant hard-fails.

    Used by the U6 DRC fence flip. The message includes the offending
    component ref and bottleneck severity so the failure is actionable
    from a CI log.
    """


class PhasedComponentAssignmentStage(Stage):
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

    Example config:
        placement_priority:
          power:
            components: ["Q1", "Q2"]
            method: "template"
            template: "half_bridge_vertical"
            anchor: [75, 62]

          driver:
            components: ["U_GATE", "C_BOOT"]
            method: "proximity"
            reference: "Q1"
            max_distance_mm: 20.0

          high_speed:
            components: ["U_MCU"]
            method: "optimize"
            zone: "control_zone"

          auto:
            method: "optimize"
    """

    def __init__(
        self,
        constraints: PlacementConstraints,
        slot_spacing: float = 12.0,
        fixed_placements: dict[str, dict] = None,
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
        # Default to the constraints' seed_filter if not provided, so
        # callers can configure via the YAML loader without a separate
        # argument. Passing ``None`` is treated as "use constraints default".
        if seed_filter is None:
            seed_filter = getattr(constraints, "seed_filter", None)
        self.seed_filter = seed_filter
        self._bottleneck_map = None
        self.compiler = ConstraintCompiler(constraints)

        # Compile constraint functions once
        self.slot_filter = self.compiler.compile_to_slot_filter()
        self.slot_scorer = self.compiler.compile_to_slot_scorer()

        # Cache design rules + isolation-slot toggle for U1/U2.
        # _isolation_slots_by_ref lets the U2 reduction path find slots
        # without re-scanning the constraints list on every pin.
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
        from temper_drc.core.fence import InvariantSpec

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
        import logging
        logger = logging.getLogger(__name__)

        # Validate constraints before placement
        errors = self.compiler.validate(state.board, state.netlist)
        if errors:
            for error in errors:
                logger.warning(f"Constraint validation: {error}")

        # U3: surface design_rules on state so the post-stage DRC fence
        # validator can recompute HV-pin coverage without a side-channel.
        # Additive, optional — older pipelines pass None and the validator
        # degrades to a no-op.
        if self.design_rules is not None and getattr(state, "design_rules", None) is None:
            state = replace(state, design_rules=self.design_rules)

        domain_for_ref, domain_regions = self._domain_lookups(state)

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

        # U3: run any registered DRC fence validators for this stage.
        # Failures are logged but do not abort the pipeline — the
        # validator is a fence, not a hard stop (the closure test is).
        try:
            from temper_placer.router_v6.stage_validators import run_validators

            failures = run_validators("PhasedComponentAssignment", new_state)
            if failures:
                import logging

                logger = logging.getLogger(__name__)
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
    ) -> dict[str, tuple[float, float]]:
        """Execute placement in priority-defined phases.

        Returns:
            Dict of component_ref -> (x, y) positions
        """
        placements = {}
        used_slots: set[tuple[float, float]] = set()

        # Build lookup structures
        comp_by_ref = {c.ref: c for c in netlist.components}
        net_pins = self._build_net_pins(netlist)
        all_slots = self._flatten_slots(zone_slots)

        # U1 (Ghost-Pad Injection): per-placement creepage rings around
        # the absolute HV pin positions of each placed component.  The
        # reservation happens at placement time (not pre-compute) so the
        # ring tracks the actual placed coordinates.  This is the only
        # physically correct semantic — pin-relative injection would
        # reserve slots at the wrong absolute location.  When
        # design_rules is None (older pipelines), no HV ring is added
        # and behavior is bit-identical to pre-U1 (NFR4 parity).
        #
        # We don't pre-compute: the ring is added inside each placement
        # method via ``_reserve_slots_with_hv`` (see _place_template,
        # _place_proximity, _place_optimize).  Cost is O(M*pin) per
        # placed component, dominated by the slot-distance scan which
        # is the same loop the placer was already doing.

        # Get placement phases from config
        phases = self.constraints.placement_priority

        if not phases:
            # Fallback to simple greedy if no phases defined
            return self._simple_greedy_placement(netlist, component_zone_map, zone_slots)

        # Track which components have been placed
        placed_refs: set[str] = set()

        # Execute each phase in order
        for phase_name, phase_config in phases.items():
            method = phase_config.get("method", "optimize")
            components = phase_config.get("components", [])

            # Auto phase places everything remaining
            if method == "auto" or not components:
                components = [c.ref for c in netlist.components if c.ref not in placed_refs]

            # Filter to components that exist and aren't placed yet
            components = [
                ref for ref in components if ref in comp_by_ref and ref not in placed_refs
            ]

            if not components:
                continue

            # Execute phase-specific placement
            if method == "template":
                phase_placements = self._place_template(
                    components, phase_config, comp_by_ref, all_slots, used_slots,
                    current_placements=placements, netlist=netlist,
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
                import logging

                logging.getLogger(__name__).warning(
                    f"Unknown placement method '{method}' in phase '{phase_name}'"
                )
                continue

            # Update global state
            placements.update(phase_placements)
            placed_refs.update(phase_placements.keys())

        return placements, used_slots

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

        # For now, use simple fixed positions
        # TODO: Load actual templates from template library
        placements: dict[str, tuple[float, float]] = {}

        # Fallback: place at anchor with small offsets
        for i, ref in enumerate(components):
            if ref not in comp_by_ref:
                continue

            # Simple vertical stacking
            offset_y = i * 10.0  # 10mm spacing
            pos = (float(anchor[0]), float(anchor[1]) + offset_y)

            placements[ref] = pos

            # Reserve slots (footprint + HV creepage rings, U1).
            # The cumulative placements (current + phase-so-far) is
            # the U2 nearest-HV-pin search space; the placer falls
            # back to no reduction if either is missing.
            cumulative = {**(current_placements or {}), **placements}
            self._reserve_slots_with_hv(
                comp_by_ref[ref], pos, all_slots, used_slots,
                placements=cumulative, netlist=netlist,
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
            # Reference not placed yet - fallback to optimize
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
        placements = {}

        for ref in components:
            if ref not in comp_by_ref:
                continue

            component = comp_by_ref[ref]

            # Filter slots within max_distance of reference
            all_zone_slots: list[Slot] = []
            for slots in zone_slots.values():
                all_zone_slots.extend(slots)

            nearby_slots = [
                slot
                for slot in all_zone_slots
                if slot not in used_slots and self._distance(slot, reference_pos) <= max_distance_mm
            ]

            if not nearby_slots:
                continue

            # Use constraint-aware selection
            best_slot = self._select_best_slot(
                ref, nearby_slots, current_placements, placements, net_pins
            )

            if best_slot:
                placements[ref] = best_slot
                # Reserve slots (footprint + HV creepage rings, U1)
                cumulative = {**current_placements, **placements}
                self._reserve_slots_with_hv(
                    component, best_slot, all_slots, used_slots,
                    placements=cumulative, netlist=netlist,
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
        placements = {}

        # Sort by footprint size (largest first)
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

            # Get available slots in zone
            zone_slot_list = list(zone_slots.get(zone_name, ()))
            available_slots = [s for s in zone_slot_list if s not in used_slots]

            if not available_slots:
                # Fallback: any zone
                for slots in zone_slots.values():
                    available_slots = [s for s in slots if s not in used_slots]
                    if available_slots:
                        break

            if not available_slots:
                continue

            # Apply bottleneck-map seed filter (if enabled and reachable)
            # The filter is per-component: drop slots whose cell score
            # is at or above the (HV-aware) threshold. ``comp_by_ref``
            # is forwarded so the filter can identify HV-class refs
            # and apply the stricter ``hv_threshold``.
            available_slots = self._apply_bottleneck_filter(
                ref, available_slots, comp_by_ref
            )

            if not available_slots:
                continue

            # Apply domain filter (FR4): drop slots outside the
            # component's domain region. Boundary points are kept.
            available_slots = self._filter_by_domain(
                ref, available_slots, domain_for_ref, domain_regions
            )

            if not available_slots:
                continue

            # Merge current + phase placements for scoring

            # Select best slot using constraints + wirelength
            best_slot = self._select_best_slot(
                ref, available_slots, current_placements, placements, net_pins
            )

            if best_slot:
                placements[ref] = best_slot
                # Reserve slots (footprint + HV creepage rings, U1)
                cumulative = {**current_placements, **placements}
                self._reserve_slots_with_hv(
                    component, best_slot, all_slots, used_slots,
                    placements=cumulative, netlist=netlist,
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

        # Use ``covers`` so boundary points are kept; ``contains`` would
        # exclude slots sitting exactly on the corridor edge.
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

        # Phase 1: Apply hard constraint filter
        valid_slots = [
            slot
            for slot in candidate_slots
            if self.slot_filter(slot, component_ref, all_placements)
        ]

        if not valid_slots:
            # No slots pass hard constraints - try without filter (emergency fallback)
            valid_slots = candidate_slots

        # Phase 2: Score each valid slot
        def score_slot(slot: tuple[float, float]) -> float:
            # Soft constraint penalty
            constraint_penalty = self.slot_scorer(slot, component_ref, all_placements)

            # Wirelength penalty
            wirelength = self._compute_wirelength(component_ref, slot, net_pins, all_placements)

            # Routability term (channel-aware). When channel_map is None or
            # w_r is 0, this contributes 0.0 and we get byte-identical output
            # to the pre-change baseline.
            cm = self.channel_map
            if cm is not None and self.w_r > 0.0:
                routability = routability_penalty(slot, cm) * self.w_r
            else:
                routability = 0.0

            # Combined score (weight wirelength lower than constraints)
            return constraint_penalty + wirelength * 0.1 + routability

        # Phase 3: Select best slot
        best_slot = min(valid_slots, key=score_slot)
        return best_slot

    # Helper methods

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
        placements = {}
        used_slots: set[tuple[float, float]] = set()

        net_pins = self._build_net_pins(netlist)
        all_slots = self._flatten_slots(zone_slots)
        {c.ref: c for c in netlist.components}

        # Sort by size
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

    # =====================================================================
    # Ghost-pad injection (U1) and isolation-slot reduction (U2)
    # =====================================================================

    # Categorical safety tags that mark a net as HV for the purposes of
    # creepage-aware placement.  "AC" is included because mains-voltage
    # nets (AC_L/AC_N/PE) need the same 6mm ring as HV in the Temper
    # design.  Per open question A.1, None / missing values are treated
    # as LV (no ghost pad).
    _HV_SAFETY_CATEGORIES: set[str] = {"HV", "AC"}

    def _collect_hv_pin_positions(
        self,
        netlist: Netlist,
    ) -> list[tuple[float, float, str, str]]:
        """Collect component-relative (x, y) positions for every HV-class pin.

        Returns a list of (pin_x, pin_y, component_ref, pin_name) tuples
        for pins whose net class has a non-None ``safety_category`` in
        :attr:`_HV_SAFETY_CATEGORIES``.  Pins whose net is missing from
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
                # Resolve net -> net class via the assignments table, then
                # the net-class rules' safety_category field.
                class_name = net_class_assignments.get(pin.net)
                if class_name is None:
                    # Fall back to scanning net_classes by name (mirrors
                    # the lookup in core.design_rules.get_rules_for_net).
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
        # Unit vector from the current pin to the nearest other HV pin.
        # Both pin positions are absolute; the slot vector is
        # component-relative but the dot product is invariant under
        # translation, so we can mix coordinate systems.
        dx = nearest_other_hv_pin_absolute[0] - current_pin_absolute[0]
        dy = nearest_other_hv_pin_absolute[1] - current_pin_absolute[1]
        d_len = math.hypot(dx, dy)
        if d_len <= 0.0:
            # No other HV pin, or coincident pins: creepage direction
            # undefined, no reduction.  This is a degenerate case
            # (a single-component HV circuit) and the placer should
            # fall back to the full base radius.
            return base_radius
        ux, uy = dx / d_len, dy / d_len

        reduction = 0.0
        for slot in slots:
            sx0, sy0 = slot.start_offset
            sx1, sy1 = slot.end_offset
            sdx = sx1 - sx0
            sdy = sy1 - sy0
            # Projection clamped at 0 — a slot whose vector points
            # away from the other HV pin does not extend creepage.
            projection = sdx * ux + sdy * uy
            if projection > 0.0:
                reduction += projection
        return max(0.0, base_radius - reduction)

    def _build_net_pins(self, netlist: Netlist) -> dict[str, list]:
        """Build net_name -> [(comp_ref, pin_name), ...] map."""
        net_pins = {}
        for net in netlist.nets:
            net_pins[net.name] = list(net.pins)
        return net_pins

    def _flatten_slots(self, zone_slots: dict[str, tuple]) -> list[tuple[float, float]]:
        """Flatten zone_slots to single list of all slots."""
        all_slots = []
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
        # Footprint ring (unchanged from pre-U1 behavior).
        radius = self._get_footprint_radius(component)
        self._reserve_slots(placed_pos, radius, all_slots, used_slots)

        if self.design_rules is None or component.pins is None:
            return

        # FR4 base radius: max creepage across HV/AC classes.
        base_radius = 0.0
        for rules in getattr(self.design_rules, "net_classes", {}).values():
            safety = getattr(rules, "safety_category", None)
            if safety in self._HV_SAFETY_CATEGORIES:
                base_radius = max(
                    base_radius, float(getattr(rules, "creepage_mm", 0.0))
                )
        if base_radius <= 0.0:
            return

        # Pre-compute the absolute positions of all OTHER HV pins so
        # the U2 reduction can find the nearest one for each pin.  We
        # only consider HV pins on different components; pins on the
        # same component don't define a creepage direction for
        # isolation-slot reduction (they share the same placed_pos).
        other_hv_pins: list[tuple[float, float]] = []
        if placements is not None and netlist is not None:
            net_class_assignments_other = (
                getattr(self.design_rules, "net_class_assignments", {}) or {}
            )
            net_classes_other = (
                getattr(self.design_rules, "net_classes", {}) or {}
            )
            for other_ref, other_pos in placements.items():
                if other_ref == component.ref:
                    continue
                other_comp = next(
                    (c for c in netlist.components if c.ref == other_ref), None
                )
                if other_comp is None or other_comp.pins is None:
                    continue
                ox, oy = other_pos
                for op in other_comp.pins:
                    if op.net is None:
                        continue
                    other_class = net_class_assignments_other.get(op.net)
                    if other_class is None or other_class not in net_classes_other:
                        continue
                    other_safety = getattr(
                        net_classes_other[other_class], "safety_category", None
                    )
                    if other_safety not in self._HV_SAFETY_CATEGORIES:
                        continue
                    opx, opy = op.position
                    other_hv_pins.append(
                        (ox + float(opx), oy + float(opy))
                    )

        # Walk this component's pins.  For each HV pin, reserve the
        # creepage ring around its absolute position.
        net_class_assignments = (
            getattr(self.design_rules, "net_class_assignments", {}) or {}
        )
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
            # Find the nearest other HV pin for the U2 reduction.
            nearest_other = (0.0, 0.0)
            if other_hv_pins:
                nearest_other = min(
                    other_hv_pins,
                    key=lambda p: (p[0] - abs_x) ** 2 + (p[1] - abs_y) ** 2,
                )
            ring_radius = self._effective_ghost_pad_radius(
                component.ref, pin.name, base_radius,
                (abs_x, abs_y), nearest_other,
            )
            if ring_radius <= 0.0:
                continue
            self._reserve_slots(
                (abs_x, abs_y), ring_radius, all_slots, used_slots
            )

    def _distance(self, p1: tuple[float, float], p2: tuple[float, float]) -> float:
        """Euclidean distance between two points."""
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

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

    def _apply_bottleneck_filter(
        self,
        component_ref: str,
        candidate_slots: list[tuple[float, float]],
        comp_by_ref: dict[str, Component] | None = None,
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
            # R3 silent-disable when no map is reachable.
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
            # R2: empty pool -> fall back to the unfiltered list with
            # a warning so the placer never silently reduces to zero.
            logger.warning(
                "seed_filter: would reject all %d candidates for %s; "
                "falling back to unfiltered pool",
                candidates_total,
                component_ref,
            )
            fallback_used = True
            # Reuse the per-slot scores already computed in the first
            # loop; avoid re-querying the map for the fallback pool.
            accepted = list(candidate_slots)
            scores_accepted = list(all_scores)
            candidates_accepted = candidates_total
            candidates_rejected = 0

        avg_score = (
            sum(scores_accepted) / len(scores_accepted) if scores_accepted else 0.0
        )
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

    def _compute_wirelength(
        self,
        component_ref: str,
        candidate_slot: tuple[float, float],
        net_pins: dict[str, list],
        current_placements: dict[str, tuple[float, float]],
    ) -> float:
        """Compute HPWL (Half-Perimeter Wirelength) for placing component at slot."""
        total_hpwl = 0.0

        for _net_name, pins in net_pins.items():
            component_on_net = any(ref == component_ref for ref, _ in pins)
            if not component_on_net:
                continue

            positions = [candidate_slot]
            for ref, _ in pins:
                if ref != component_ref and ref in current_placements:
                    positions.append(current_placements[ref])

            if len(positions) > 1:
                xs = [p[0] for p in positions]
                ys = [p[1] for p in positions]
                hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))
                total_hpwl += hpwl

        return total_hpwl

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

        # Pre-index bottlenecks by (gx, gy) for O(1) lookup per placement.
        critical_by_cell: dict[tuple[int, int], Bottleneck] = {}
        for bn in cmap.bottlenecks:
            if bn.severity != "CRITICAL":
                continue
            key = (bn.x, bn.y)
            existing = critical_by_cell.get(key)
            if existing is None or bn.score > existing.score:
                critical_by_cell[key] = bn

        violations: list[dict] = []
        for ref, pos in placements.items():
            if not isinstance(pos, (tuple, list)) or len(pos) < 2:
                continue
            x_mm, y_mm = pos[0], pos[1]
            gx = int(math.floor((float(x_mm) * 1000.0) / cell_um))
            gy = int(math.floor((float(y_mm) * 1000.0) / cell_um))
            if gx < 0 or gx >= width or gy < 0 or gy >= height:
                continue
            bn = critical_by_cell.get((gx, gy))
            if bn is None:
                continue
            violations.append(
                {
                    "ref": ref,
                    "x": gx,
                    "y": gy,
                    "layer": bn.layer,
                    "severity": bn.severity,
                }
            )
        return violations

    def _check_critical_bottlenecks(
        self, placements: dict[str, tuple[float, float]]
    ) -> list[dict]:
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
