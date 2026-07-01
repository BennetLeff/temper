"""
Reproduction tests for PCL constraint stubs.
"""

import jax.numpy as jnp

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Netlist
from temper_placer.losses.base import LossContext
from temper_placer.pcl.constraints import (
    ConstraintTier,
    EnclosingConstraint,
    SeparatedConstraint,
)
from temper_placer.pcl.loss_bridge import (
    enclosing_to_zone_loss,
    separated_to_separation_loss,
)


def _create_simple_netlist(component_refs: list[str]) -> Netlist:
    """Create a minimal netlist for testing."""
    components = [
        Component(
            ref=ref,
            footprint="TestFootprint",
            bounds=(5.0, 5.0),
            pins=[],
            net_class="Signal",
        )
        for ref in component_refs
    ]
    return Netlist(components=components, nets=[])

def _create_simple_board(width: float, height: float, zones: list[Zone] = None) -> Board:
    """Create a minimal board for testing."""
    return Board(
        width=width,
        height=height,
        zones=zones or [],
        keepouts=[],
    )

def test_separated_constraint_is_implemented():
    """Verify that SeparatedConstraint now returns non-zero loss when violated."""
    constraint = SeparatedConstraint(
        a="Q1",
        b="U1",
        min_distance_mm=20.0,
        tier=ConstraintTier.HARD,
        because="Test separation",
    )

    netlist = _create_simple_netlist(["Q1", "U1"])
    board = _create_simple_board(100, 100)
    context = LossContext.from_netlist_and_board(netlist, board)

    # Q1 at (10, 10), U1 at (15, 15) -> distance = sqrt(5^2 + 5^2) = 7.07 < 20.0
    positions = jnp.array([[10.0, 10.0], [15.0, 15.0]])
    rotations = jnp.zeros((2, 4))

    # Pass board instead of zones
    loss_fn = separated_to_separation_loss(constraint, netlist, board)
    result = loss_fn(positions, rotations, context)

    # Should be positive now
    assert result.value > 0.0

def test_enclosing_constraint_is_implemented():
    """Verify that EnclosingConstraint now returns non-zero loss when violated."""
    constraint = EnclosingConstraint(
        outer="HV_ZONE",
        inner=["Q1"],
        tier=ConstraintTier.HARD,
        because="Test enclosing",
    )

    netlist = _create_simple_netlist(["Q1"])
    # Zone at (50, 50) to (100, 100)
    hv_zone = Zone(name="HV_ZONE", bounds=(50.0, 50.0, 100.0, 100.0), components=["Q1"])
    board = _create_simple_board(100, 100, zones=[hv_zone])
    context = LossContext.from_netlist_and_board(netlist, board)

    # enclosing_to_zone_loss no longer takes zones dict
    loss_fn = enclosing_to_zone_loss(constraint, netlist)

    # Q1 at (10, 10), which is OUTSIDE HV_ZONE
    positions = jnp.array([[10.0, 10.0]])
    rotations = jnp.zeros((1, 4))

    result = loss_fn(positions, rotations, context)

    # Should be positive now
    assert result.value > 0.0
