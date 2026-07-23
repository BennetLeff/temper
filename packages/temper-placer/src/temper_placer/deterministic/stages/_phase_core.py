"""Core orchestration for phased component assignment.

Contains the :class:`_PhaseCoreMixin` with __init__, name, invariants, run,
phase dispatch (_phased_placement), domain lookups, and shared utility methods.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from temper_placer.constraints.compiler import ConstraintCompiler
from temper_placer.io.config_loader import IsolationSlot, PlacementConstraints

from ..channels import ChannelMap
from ..state import BoardState

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
