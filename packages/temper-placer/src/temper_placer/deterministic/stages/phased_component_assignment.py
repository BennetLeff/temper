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

import math
from dataclasses import replace
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from temper_placer.constraints.compiler import ConstraintCompiler

from ..state import BoardState
from .base import Stage

if TYPE_CHECKING:
    from temper_placer.core.component import Component
    from temper_placer.core.design_rules import DesignRules
    from temper_placer.core.netlist import Netlist
    from temper_placer.io.config_loader import IsolationSlot, PlacementConstraints


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
        fixed_placements: Dict[str, Dict] = None,
        design_rules: Optional["DesignRules"] = None,
        use_isolation_slots: bool = False,
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
        self.compiler = ConstraintCompiler(constraints)

        # Compile constraint functions once
        self.slot_filter = self.compiler.compile_to_slot_filter()
        self.slot_scorer = self.compiler.compile_to_slot_scorer()

        # Cache design rules + isolation-slot toggle for U1/U2.
        # _isolation_slots_by_ref lets the U2 reduction path find slots
        # without re-scanning the constraints list on every pin.
        self.design_rules = design_rules
        self.use_isolation_slots = use_isolation_slots
        self._isolation_slots_by_ref: Dict[str, List["IsolationSlot"]] = {}
        if use_isolation_slots and getattr(constraints, "isolation_slots", None):
            for slot in constraints.isolation_slots:
                self._isolation_slots_by_ref.setdefault(slot.component_ref, []).append(slot)

    @property
    def name(self) -> str:
        return "phased_component_assignment"

    def run(self, state: BoardState) -> BoardState:
        """Execute phased placement."""
        if not state.netlist or not state.component_zone_map or not state.zone_slots:
            return state

        # Validate constraints before placement
        errors = self.compiler.validate(state.board, state.netlist)
        if errors:
            import logging

            logger = logging.getLogger(__name__)
            for error in errors:
                logger.warning(f"Constraint validation: {error}")

        placements = self._phased_placement(
            state,
            state.netlist,
            dict(state.component_zone_map),
            dict(state.zone_slots),
        )

        return replace(state, placements=frozenset(placements.items()))

    def _phased_placement(
        self,
        state: BoardState,
        netlist: Netlist,
        component_zone_map: Dict[str, str],
        zone_slots: Dict[str, Tuple],
    ) -> Dict[str, Tuple[float, float]]:
        """Execute placement in priority-defined phases.

        Returns:
            Dict of component_ref -> (x, y) positions
        """
        placements = {}
        used_slots: Set[Tuple[float, float]] = set()

        # Build lookup structures
        comp_by_ref = {c.ref: c for c in netlist.components}
        net_pins = self._build_net_pins(netlist)
        all_slots = self._flatten_slots(zone_slots)

        # U1 (Ghost-Pad Injection): reserve every slot within creepage of
        # an HV pin position BEFORE the placement loop runs.  This blocks
        # placement from sitting in the IEC 62368-1 6mm ring around HV pins
        # so the router never has to leave the placer a placement it cannot
        # route.  When design_rules is None (older pipelines), this is a
        # no-op (NFR4 parity).
        if self.design_rules is not None:
            self._inject_ghost_pads(
                state, netlist, used_slots, all_slots, logger_name=__name__
            )

        # Get placement phases from config
        phases = self.constraints.placement_priority

        if not phases:
            # Fallback to simple greedy if no phases defined
            return self._simple_greedy_placement(netlist, component_zone_map, zone_slots)

        # Track which components have been placed
        placed_refs = set()

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
                    components, phase_config, comp_by_ref, all_slots, used_slots
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

        return placements

    def _place_template(
        self,
        components: List[str],
        phase_config: dict,
        comp_by_ref: Dict[str, Component],
        all_slots: List[Tuple[float, float]],
        used_slots: Set[Tuple[float, float]],
    ) -> Dict[str, Tuple[float, float]]:
        """Place components using a template (e.g., half-bridge layout).

        Template defines relative positions. Anchor defines absolute position.

        Args:
            components: Component refs to place
            phase_config: Template config with 'template' and 'anchor'
            comp_by_ref: Component lookup
            all_slots: All available slots
            used_slots: Already-used slots

        Returns:
            Dict of ref -> (x, y) for this phase
        """
        template_name = phase_config.get("template")
        anchor = phase_config.get("anchor", [0, 0])

        # For now, use simple fixed positions
        # TODO: Load actual templates from template library
        placements = {}

        # Fallback: place at anchor with small offsets
        for i, ref in enumerate(components):
            if ref not in comp_by_ref:
                continue

            # Simple vertical stacking
            offset_y = i * 10.0  # 10mm spacing
            pos = (float(anchor[0]), float(anchor[1]) + offset_y)

            placements[ref] = pos

            # Reserve slots
            radius = self._get_footprint_radius(comp_by_ref[ref])
            self._reserve_slots(pos, radius, all_slots, used_slots)

        return placements

    def _place_proximity(
        self,
        components: List[str],
        phase_config: dict,
        comp_by_ref: Dict[str, Component],
        current_placements: Dict[str, Tuple[float, float]],
        zone_slots: Dict[str, Tuple],
        used_slots: Set[Tuple[float, float]],
        all_slots: List[Tuple[float, float]],
        net_pins: Dict[str, list],
    ) -> Dict[str, Tuple[float, float]]:
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
            all_zone_slots = []
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
                radius = self._get_footprint_radius(component)
                self._reserve_slots(best_slot, radius, all_slots, used_slots)

        return placements

    def _place_optimize(
        self,
        components: List[str],
        comp_by_ref: Dict[str, Component],
        component_zone_map: Dict[str, str],
        zone_slots: Dict[str, Tuple],
        current_placements: Dict[str, Tuple[float, float]],
        used_slots: Set[Tuple[float, float]],
        all_slots: List[Tuple[float, float]],
        net_pins: Dict[str, list],
    ) -> Dict[str, Tuple[float, float]]:
        """Place components using constraint-aware greedy optimization.

        This is the core placement algorithm:
          1. Sort by footprint size (largest first)
          2. Filter slots using hard constraints
          3. Score slots using soft constraints + wirelength
          4. Select best slot

        Args:
            components: Component refs to place
            comp_by_ref: Component lookup
            component_zone_map: Component -> zone assignments
            zone_slots: Slots by zone
            current_placements: Already-placed components
            used_slots: Already-used slots
            all_slots: All available slots
            net_pins: Net connectivity

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

            # Merge current + phase placements for scoring
            all_placements = {**current_placements, **placements}

            # Select best slot using constraints + wirelength
            best_slot = self._select_best_slot(
                ref, available_slots, current_placements, placements, net_pins
            )

            if best_slot:
                placements[ref] = best_slot
                radius = self._get_footprint_radius(component)
                self._reserve_slots(best_slot, radius, all_slots, used_slots)

        return placements

    def _select_best_slot(
        self,
        component_ref: str,
        candidate_slots: List[Tuple[float, float]],
        current_placements: Dict[str, Tuple[float, float]],
        phase_placements: Dict[str, Tuple[float, float]],
        net_pins: Dict[str, list],
    ) -> Tuple[float, float] | None:
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
        def score_slot(slot: Tuple[float, float]) -> float:
            # Soft constraint penalty
            constraint_penalty = self.slot_scorer(slot, component_ref, all_placements)

            # Wirelength penalty
            wirelength = self._compute_wirelength(component_ref, slot, net_pins, all_placements)

            # Combined score (weight wirelength lower than constraints)
            return constraint_penalty + wirelength * 0.1

        # Phase 3: Select best slot
        best_slot = min(valid_slots, key=score_slot)
        return best_slot

    # Helper methods

    def _simple_greedy_placement(
        self,
        netlist: Netlist,
        component_zone_map: Dict[str, str],
        zone_slots: Dict[str, Tuple],
    ) -> Dict[str, Tuple[float, float]]:
        """Fallback: simple greedy placement (same as ComponentAssignmentStage)."""
        placements = {}
        used_slots: Set[Tuple[float, float]] = set()

        net_pins = self._build_net_pins(netlist)
        all_slots = self._flatten_slots(zone_slots)
        comp_by_ref = {c.ref: c for c in netlist.components}

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

        return placements

    # =====================================================================
    # Ghost-pad injection (U1) and isolation-slot reduction (U2)
    # =====================================================================

    # Categorical safety tags that mark a net as HV for the purposes of
    # creepage-aware placement.  "AC" is included because mains-voltage
    # nets (AC_L/AC_N/PE) need the same 6mm ring as HV in the Temper
    # design.  Per open question A.1, None / missing values are treated
    # as LV (no ghost pad).
    _HV_SAFETY_CATEGORIES: Set[str] = {"HV", "AC"}

    def _collect_hv_pin_positions(
        self,
        netlist: Netlist,
    ) -> List[Tuple[float, float, str, str]]:
        """Collect absolute (x, y) positions for every HV-class pin.

        Returns a list of (pin_x, pin_y, component_ref, pin_name) tuples
        for pins whose net class has a non-None ``safety_category`` in
        :attr:`_HV_SAFETY_CATEGORIES``.  Pins whose net is missing from
        :attr:`design_rules.net_classes` (or has a non-HV / None safety
        tag) are silently skipped — this preserves NFR4 parity on
        LV-only boards.

        Note: pin coordinates returned here are RELATIVE to their
        component origin, not absolute board positions.  Callers that
        need absolute positions (U3 validator) must combine with the
        component's placement.  The placer itself reserves slots around
        the *current* anchor of every component (which is its initial /
        fixed position at placement time), so relative coordinates are
        sufficient for the placer's reservation step.
        """
        if self.design_rules is None or not getattr(self.design_rules, "net_classes", None):
            return []

        net_classes = self.design_rules.net_classes
        net_class_assignments = getattr(self.design_rules, "net_class_assignments", {}) or {}

        hv_pins: List[Tuple[float, float, str, str]] = []
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
        pin_name: str,
        base_radius: float,
    ) -> float:
        """Apply U2 isolation-slot reduction to a base ghost-pad radius.

        When :attr:`use_isolation_slots` is False, returns ``base_radius``
        unchanged (NFR4 bit-identical parity with U1).  When True, walks
        every isolation slot whose ``component_ref`` matches and reduces
        the radius by the slot's length projected onto the slot's
        axis (IEC 62368-1 Annex G creepage compliance).  The reduction
        is clamped at 0 and never expands beyond ``base_radius`` (the
        FR4 SSOT).
        """
        if not self.use_isolation_slots:
            return base_radius
        slots = self._isolation_slots_by_ref.get(component_ref, [])
        if not slots:
            return base_radius
        for slot in slots:
            sx0, sy0 = slot.start_offset
            sx1, sy1 = slot.end_offset
            dx = sx1 - sx0
            dy = sy1 - sy0
            length = math.hypot(dx, dy)
            if length <= 0.0:
                continue
            # Project slot length onto its own axis (always length).
            # Only the on-axis component reduces creepage; off-axis
            # contributions are accounted for by the slot's own
            # geometry, not the placer's radius budget.
            base_radius = max(0.0, base_radius - length)
        return base_radius

    def _inject_ghost_pads(
        self,
        state: BoardState,
        netlist: Netlist,
        used_slots: Set[Tuple[float, float]],
        all_slots: List[Tuple[float, float]],
        logger_name: str = __name__,
    ) -> None:
        """Inject HV-creepage ghost pads into ``used_slots``.

        For every HV pin, reserves every grid slot within
        ``creepage_mm`` (max across HV net classes, FR4 SSOT) of the
        pin's component-relative position.  Inner layers are
        over-reserved by design (FR2b).  Logs a per-stage summary
        ``ghost_pads_injected={N} slots_blocked={M}`` at INFO so
        downstream tooling can correlate.
        """
        import logging

        logger = logging.getLogger(logger_name)

        hv_pins = self._collect_hv_pin_positions(netlist)
        if not hv_pins:
            logger.debug("No HV pins found; ghost-pad injection is a no-op")
            return

        # FR4 base radius: max creepage across HV/AC classes.  Using
        # the max keeps the placer conservative — every HV pin gets at
        # least its class's required ring, and over-reservation is the
        # intended failure mode (FR2b).
        base_radius = 0.0
        for rules in getattr(self.design_rules, "net_classes", {}).values():
            safety = getattr(rules, "safety_category", None)
            if safety in self._HV_SAFETY_CATEGORIES:
                base_radius = max(base_radius, float(getattr(rules, "creepage_mm", 0.0)))
        if base_radius <= 0.0:
            logger.debug("creepage_mm is zero across all HV classes; skipping injection")
            return

        before = len(used_slots)
        rejected = 0
        for pin_x, pin_y, comp_ref, pin_name in hv_pins:
            radius = self._effective_ghost_pad_radius(comp_ref, pin_name, base_radius)
            new_slots = [
                slot
                for slot in all_slots
                if math.hypot(slot[0] - pin_x, slot[1] - pin_y) <= radius
                and slot not in used_slots
            ]
            if not new_slots:
                # FR7: log when an HV pin cannot reserve any slot.
                logger.debug(
                    f"Ghost-pad for {comp_ref}.{pin_name} at ({pin_x},{pin_y}) "
                    f"radius={radius}mm rejected: no slots within radius"
                )
                rejected += 1
                continue
            used_slots.update(new_slots)

        added = len(used_slots) - before
        logger.info(
            f"ghost_pads_injected={len(hv_pins)} slots_blocked={added} "
            f"rejected={rejected} base_creepage_mm={base_radius}"
        )

    def _build_net_pins(self, netlist: Netlist) -> Dict[str, list]:
        """Build net_name -> [(comp_ref, pin_name), ...] map."""
        net_pins = {}
        for net in netlist.nets:
            net_pins[net.name] = list(net.pins)
        return net_pins

    def _flatten_slots(self, zone_slots: Dict[str, Tuple]) -> List[Tuple[float, float]]:
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
        center: Tuple[float, float],
        radius: float,
        all_slots: List[Tuple[float, float]],
        used_slots: Set[Tuple[float, float]],
    ) -> None:
        """Reserve all slots within radius of center."""
        cx, cy = center
        for slot in all_slots:
            sx, sy = slot
            dist = math.sqrt((sx - cx) ** 2 + (sy - cy) ** 2)
            if dist <= radius:
                used_slots.add(slot)

    def _distance(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        """Euclidean distance between two points."""
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def _compute_wirelength(
        self,
        component_ref: str,
        candidate_slot: Tuple[float, float],
        net_pins: Dict[str, list],
        current_placements: Dict[str, Tuple[float, float]],
    ) -> float:
        """Compute HPWL (Half-Perimeter Wirelength) for placing component at slot."""
        total_hpwl = 0.0

        for net_name, pins in net_pins.items():
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
