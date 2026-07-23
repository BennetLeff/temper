"""Placement-phase methods for phased component assignment.

Contains the :class:`_PhasePlacementMixin` with _place_template,
_place_proximity, _place_optimize, slot scoring, wirelength, and
fallback greedy placement.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from ..channels import routability_penalty

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
