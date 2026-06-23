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
from dataclasses import replace
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from temper_placer.constraints.compiler import ConstraintCompiler

from ..state import BoardState
from .base import Stage

if TYPE_CHECKING:
    from temper_placer.core.component import Component
    from temper_placer.core.netlist import Netlist
    from temper_placer.io.config_loader import PlacementConstraints, SeedFilterConfig

from temper_placer.deterministic.bottleneck_map import BottleneckMap, load_bottleneck_map


logger = logging.getLogger(__name__)


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
        seed_filter: Optional["SeedFilterConfig"] = None,
    ):
        """Initialize phased placement.

        Args:
            constraints: Parsed placement constraints (for compiler)
            slot_spacing: Spacing between slots in mm
            fixed_placements: Dict of ref -> {'position': [x, y], 'rotation': deg}
            seed_filter: Optional bottleneck-map seed filter configuration.
                When ``None``, the filter is disabled. When provided,
                ``enabled=False`` disables at runtime; ``enabled=True`` runs
                the filter when a bottleneck map is reachable.

        @req(2026-06-23-004, R4)
        """
        self.constraints = constraints
        self.slot_spacing = slot_spacing
        self.fixed_placements = fixed_placements or {}
        # Default to the constraints' seed_filter if not provided, so
        # callers can configure via the YAML loader without a separate
        # argument. Passing ``None`` is treated as "use constraints default".
        if seed_filter is None:
            seed_filter = getattr(constraints, "seed_filter", None)
        self.seed_filter = seed_filter
        self.compiler = ConstraintCompiler(constraints)

        # Compile constraint functions once
        self.slot_filter = self.compiler.compile_to_slot_filter()
        self.slot_scorer = self.compiler.compile_to_slot_scorer()

        # Per-run bottleneck map (set on run(); cleared after).
        # When present, the seed filter narrows each component's candidate
        # slot list by removing slots that fall in cells whose congestion
        # score meets or exceeds the configured threshold.
        self._bottleneck_map: Optional[BottleneckMap] = None

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
            for error in errors:
                logger.warning(f"Constraint validation: {error}")

        # Load the bottleneck map for seed filtering. Missing or
        # non-BottleneckMap values silently disable the filter.
        self._bottleneck_map = load_bottleneck_map(state, sidecar_path=None)

        try:
            placements = self._phased_placement(
                state.netlist,
                dict(state.component_zone_map),
                dict(state.zone_slots),
            )
        finally:
            self._bottleneck_map = None

        return replace(state, placements=frozenset(placements.items()))

    def _phased_placement(
        self,
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
          3. **Apply bottleneck-map seed filter** (when enabled+available)
          4. Score slots using soft constraints + wirelength
          5. Select best slot

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

    def _is_hv_ref(self, ref: str, comp_by_ref: Dict[str, Component]) -> bool:
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
        candidate_slots: List[Tuple[float, float]],
        comp_by_ref: Optional[Dict[str, Component]] = None,
    ) -> List[Tuple[float, float]]:
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

        @req(2026-06-23-004, R2)
        @req(2026-06-23-004, R6)
        @req(2026-06-23-004, K4)
        """
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

        accepted: List[Tuple[float, float]] = []
        scores_accepted: List[float] = []
        for slot in candidate_slots:
            score = bmap.score_at(slot[0], slot[1])
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
            accepted = list(candidate_slots)
            scores_accepted = [bmap.score_at(s[0], s[1]) for s in candidate_slots]
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
