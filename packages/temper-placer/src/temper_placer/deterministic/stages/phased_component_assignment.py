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
from typing import TYPE_CHECKING, Dict, List, Set, Tuple

from temper_placer.constraints.compiler import ConstraintCompiler

from ..channels import Bottleneck, ChannelMap, routability_penalty
from ..flags import is_drc_fence_fail_enabled
from ..state import BoardState
from .base import Stage

if TYPE_CHECKING:
    from temper_drc.core.fence import InvariantSpec
    from temper_placer.core.component import Component
    from temper_placer.core.netlist import Netlist
    from temper_placer.io.config_loader import PlacementConstraints


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
        fixed_placements: Dict[str, Dict] = None,
        channel_map: ChannelMap | None = None,
        w_r: float = 0.05,
    ):
        """Initialize phased placement.

        Args:
            constraints: Parsed placement constraints (for compiler)
            slot_spacing: Spacing between slots in mm
            fixed_placements: Dict of ref -> {'position': [x, y], 'rotation': deg}
            channel_map: Optional :class:`ChannelMap` snapshot from
                ``placement.channels.json``. When ``None`` the placer falls back
                to wirelength-only scoring and emits a WARNING (under-instrumented
                run). When provided, ``routability_penalty`` contributes to
                ``score_slot`` with weight ``w_r``.
            w_r: Routability weight applied to ``routability_penalty`` in
                ``score_slot``. ``0.0`` produces output identical to
                ``channel_map=None`` and is the explicit escape hatch.
        """
        self.constraints = constraints
        self.slot_spacing = slot_spacing
        self.fixed_placements = fixed_placements or {}
        self.channel_map = channel_map
        self.w_r = float(w_r)
        self.compiler = ConstraintCompiler(constraints)

        # Compile constraint functions once
        self.slot_filter = self.compiler.compile_to_slot_filter()
        self.slot_scorer = self.compiler.compile_to_slot_scorer()

        if self.channel_map is None and self.w_r > 0.0:
            _LOGGER.warning(
                "PhasedComponentAssignmentStage: no channel_map provided; "
                "placement will not use routability-aware scoring "
                "(under-instrumented run)"
            )

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

        # Validate constraints before placement
        errors = self.compiler.validate(state.board, state.netlist)
        if errors:
            import logging

            logger = logging.getLogger(__name__)
            for error in errors:
                logger.warning(f"Constraint validation: {error}")

        placements = self._phased_placement(
            state.netlist,
            dict(state.component_zone_map),
            dict(state.zone_slots),
        )

        # R6: Soft-launch DRC fence invariant check. Currently WARNING-only;
        # U6 wires the hard-fail flip. Center-only sampling in v1; the
        # invariant name reflects that explicit deferral.
        if self.channel_map is not None and self.channel_map.has_grid():
            self._check_critical_bottlenecks(placements)

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

    def find_critical_bottleneck_violations(
        self, placements: Dict[str, Tuple[float, float]]
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
        not flagged, matching the routability penalty's "no penalty at the
        board edge" semantics.
        """
        if self.channel_map is None or not self.channel_map.has_grid():
            return []

        cmap = self.channel_map
        cell_um = cmap.cell_size_um
        width = cmap.width
        height = cmap.height

        # Pre-index bottlenecks by (gx, gy) for O(1) lookup per placement.
        critical_by_cell: Dict[Tuple[int, int], Bottleneck] = {}
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
        self, placements: Dict[str, Tuple[float, float]]
    ) -> list[dict]:
        """Run the invariant check; WARNING-only in soft-launch mode.

        When :func:`is_drc_fence_fail_enabled` returns True, the first
        violation raises :class:`PhasedComponentAssignmentError` with the
        offending ref and severity in the message. The U6 follow-up
        bd issue ``Flip DRC fence invariant to hard-fail`` owns the
        2-week timeline for flipping the env var by default.
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
