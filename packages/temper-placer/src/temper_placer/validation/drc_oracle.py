"""
DRCOracle: Batch DRC evaluator using temper-drc composable checks.

Provides a DRCOracle class that wraps temper_drc.CheckRunner for batch
placement evaluation. Not to be confused with routing.constraints.drc_oracle.DRCOracle
which serves real-time track/via clearance queries.

This oracle:
- Converts temper-placer Netlist/Board data into temper_drc.input.Placement + ConstraintSet
- Runs the full temper-drc check suite (DRC, Safety, EMC, ERC)
- Returns RunResult with aggregate penalty

Graceful degradation: If temper-drc is not installed, the factory function raises
ImportError with a clear message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import jax.numpy as jnp
from jax import Array

if TYPE_CHECKING:
    from temper_drc.core.result import RunResult
    from temper_drc.input.constraints import ConstraintSet as DrcConstraintSet
    from temper_drc.input.placement import Placement as DrcPlacement
    from temper_placer.losses.base import LossContext


def build_placement_from_netlist(
    positions: Array,
    context: LossContext,
) -> DrcPlacement:
    """Convert temper-placer Netlist + positions into a temper_drc.input.Placement.

    Maps each Component to ComponentPlacement:
    - ref, footprint, width, height, net_class from netlist components
    - x, y from positions array
    - rotation from initial_rotation if available (converted from quantized 0-3 to degrees)
    - layer from initial_side (0=F.Cu, 1=B.Cu)
    - voltage_domain set to None (not present on temper-placer Component)
    """
    from temper_drc.input.placement import ComponentPlacement, Placement

    netlist = context.netlist
    n = netlist.n_components
    components: dict[str, ComponentPlacement] = {}

    for i, c in enumerate(netlist.components):
        x = float(positions[i, 0])
        y = float(positions[i, 1])

        width = c.width
        height = c.height

        rotation = 0.0
        if c.initial_rotation is not None:
            rotation = float(c.initial_rotation * 90)

        layer = "F.Cu"
        if c.initial_side is not None and c.initial_side == 1:
            layer = "B.Cu"

        comp = ComponentPlacement(
            ref=c.ref,
            footprint=c.footprint,
            x=x,
            y=y,
            rotation=rotation,
            layer=layer,
            width=width,
            height=height,
            net_class=c.net_class,
            voltage_domain=None,
        )
        components[c.ref] = comp

    return Placement(
        components=components,
        board_width=context.board.width,
        board_height=context.board.height,
    )


def build_constraint_set(context: LossContext) -> DrcConstraintSet:
    """Convert temper-placer clearance_rules into a temper_drc.input.ConstraintSet.

    Maps temper_placer.losses.types.ClearanceRule (net_class_a, net_class_b,
    min_clearance) to temper_drc.input.constraints.ClearanceRule (from_class,
    to_class, min_mm).
    """
    from temper_drc.input.constraints import ClearanceRule, ConstraintSet

    clearances: list[ClearanceRule] = []
    for rule in context.clearance_rules:
        clearances.append(
            ClearanceRule(
                from_class=rule.net_class_a,
                to_class=rule.net_class_b,
                min_mm=rule.min_clearance,
                description=getattr(rule, "because", ""),
            )
        )

    return ConstraintSet(
        clearances=clearances,
        board_width=context.board.width,
        board_height=context.board.height,
    )


@dataclass
class DRCOracle:
    """Batch DRC evaluator using temper-drc composable checks.

    Not to be confused with routing.constraints.drc_oracle.DRCOracle,
    which serves real-time track/via clearance queries.

    Pre-builds static lookup maps at construction from the netlist.
    The ConstraintSet is built once and cached (net classes and
    clearance rules are static for a design).

    Attributes:
        runner: Configured CheckRunner with all desired checks.
        constraints: Pre-built ConstraintSet (static for the design).
        net_class_map: component_ref → net_class.
        footprint_map: component_ref → footprint_name.
        layer_map: component_ref → layer.
    """

    runner: object  # temper_drc.core.runner.CheckRunner
    constraints: object  # temper_drc.input.constraints.ConstraintSet
    net_class_map: dict[str, str]
    footprint_map: dict[str, str]
    layer_map: dict[str, str]

    def evaluate(
        self,
        positions: Array,
        context: LossContext,
        categories: list[str] | None = None,
    ) -> RunResult:
        """Convert positions to Placement, run checks, return RunResult.

        Args:
            positions: (N, 2) array of component positions in mm.
            context: LossContext with netlist and board.
            categories: Optional list of check categories to run
                (e.g. ["drc", "safety"]). None means all categories.

        Returns:
            RunResult with per-check results and aggregate metrics.
        """
        placement = build_placement_from_netlist(positions, context)
        return self.runner.run(placement, self.constraints, categories=categories)

    def evaluate_placement(
        self,
        placement: DrcPlacement,
        categories: list[str] | None = None,
    ) -> RunResult:
        """Evaluate a pre-built Placement (useful for testing).

        Args:
            placement: Pre-built temper_drc.input.Placement.
            categories: Optional list of check categories.

        Returns:
            RunResult with per-check results and aggregate metrics.
        """
        return self.runner.run(placement, self.constraints, categories=categories)


def create_standard_drc_oracle(context: LossContext) -> DRCOracle:
    """Create a DRCOracle pre-loaded with all 12 standard temper-drc checks.

    The oracle is configured with:
    - All DRC checks: component_overlap, courtyard, clearance, zone_containment
    - All Safety checks: creepage, hv_lv_separation, isolation
    - All EMC checks: noise_coupling, loop_area, ground_plane
    - All ERC checks: floating_pins, net_connectivity, power_domain

    Args:
        context: LossContext with netlist and clearance rules.

    Returns:
        Configured DRCOracle instance.

    Raises:
        ImportError: If temper-drc is not installed.
    """
    try:
        from temper_drc import CheckRunner
        from temper_drc.checks.drc import (
            ClearanceCheck,
            ComponentOverlapCheck,
            CourtyardCheck,
            ZoneContainmentCheck,
        )
        from temper_drc.checks.emc import GroundPlaneCheck, LoopAreaCheck, NoiseCouplingCheck
        from temper_drc.checks.erc import FloatingPinsCheck, NetConnectivityCheck, PowerDomainCheck
        from temper_drc.checks.safety import (
            CreepageCheck,
            HVLVSeparationCheck,
            IsolationCheck,
        )
    except ImportError as e:
        raise ImportError(
            "temper-drc is not installed. Install it with: pip install temper-drc"
        ) from e

    runner = CheckRunner()
    runner.add_checks(
        [
            ComponentOverlapCheck(),
            CourtyardCheck(),
            ClearanceCheck(),
            ZoneContainmentCheck(),
            CreepageCheck(),
            HVLVSeparationCheck(),
            IsolationCheck(),
            NoiseCouplingCheck(),
            LoopAreaCheck(),
            GroundPlaneCheck(),
            FloatingPinsCheck(),
            NetConnectivityCheck(),
            PowerDomainCheck(),
        ]
    )

    constraints = build_constraint_set(context)

    netlist = context.netlist
    net_class_map: dict[str, str] = {}
    footprint_map: dict[str, str] = {}
    layer_map: dict[str, str] = {}

    for c in netlist.components:
        net_class_map[c.ref] = c.net_class
        footprint_map[c.ref] = c.footprint
        layer = "F.Cu"
        if c.initial_side is not None and c.initial_side == 1:
            layer = "B.Cu"
        layer_map[c.ref] = layer

    return DRCOracle(
        runner=runner,
        constraints=constraints,
        net_class_map=net_class_map,
        footprint_map=footprint_map,
        layer_map=layer_map,
    )
