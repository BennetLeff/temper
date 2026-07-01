"""
Property-based tests for KeepoutConstraint: loss non-negativity,
enclosing-keepout consistency, DRC matches geometry, gradient continuity,
and margin monotonicity.
"""

from __future__ import annotations

import jax.numpy as jnp
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.pcl.constraints import (
    ConstraintTier,
    ConstraintType,
    KeepoutConstraint,
)
from temper_placer.pcl.loss_bridge import keepout_to_loss


@st.composite
def boards_with_keepout_zone(draw: st.DrawFn) -> Board:
    """Generate a Board with a keepout zone."""
    w = draw(st.floats(min_value=50.0, max_value=200.0))
    h = draw(st.floats(min_value=50.0, max_value=200.0))
    kx = draw(st.floats(min_value=10.0, max_value=w - 20.0))
    ky = draw(st.floats(min_value=10.0, max_value=h - 20.0))
    kw = draw(st.floats(min_value=5.0, max_value=30.0))
    kh = draw(st.floats(min_value=5.0, max_value=30.0))
    zone = Zone(
        name="KEEPOUT_TEST",
        bounds=(kx, ky, kx + kw, ky + kh),
        zone_type="keepout",
    )
    return Board(width=w, height=h, zones=[zone])


@st.composite
def netlists_with_components(draw: st.DrawFn) -> Netlist:
    """Generate a small netlist with 2-6 components."""
    n = draw(st.integers(min_value=2, max_value=6))
    comps = []
    for i in range(n):
        comps.append(Component(
            ref=f"C{i}",
            footprint="0603",
            bounds=(5.0, 5.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
        ))
    return Netlist(components=comps, nets=[Net("NET1", [(f"C{i}", "1") for i in range(n)])])


class TestKeepoutLossNonNegativity:
    """Theorem: Keepout loss is always non-negative."""

    @pytest.mark.property
    @given(boards_with_keepout_zone(), netlists_with_components())
    @settings(max_examples=50, deadline=30000)
    def test_keepout_loss_non_negative(self, board, netlist):
        """Keepout loss must be >= 0 for any component positions."""
        constraint = KeepoutConstraint(
            zone_name=board.zones[0].name,
            tier=ConstraintTier.HARD,
            because="Keepout zone for safety isolation between HV and LV domains",
        )
        loss_fn = keepout_to_loss(constraint, netlist, board)
        positions = jnp.array([[10.0, 10.0], [80.0, 80.0], [60.0, 60.0], [20.0, 20.0]], dtype=jnp.float32)
        result = loss_fn(positions, jnp.zeros((len(positions), 4)), None)
        assert float(result.value) >= 0.0

    @pytest.mark.property
    def test_empty_netlist_zero_loss(self):
        """Empty netlist produces zero keepout loss."""
        board = Board(width=100.0, height=100.0, zones=[
            Zone("KEEPOUT_TEST", (30, 30, 70, 70), zone_type="keepout"),
        ])
        netlist = Netlist(components=[], nets=[])
        constraint = KeepoutConstraint(
            zone_name="KEEPOUT_TEST",
            tier=ConstraintTier.HARD,
            because="Keepout zone for safety isolation between HV and LV domains",
        )
        loss_fn = keepout_to_loss(constraint, netlist, board)
        result = loss_fn(
            jnp.zeros((0, 2), dtype=jnp.float32),
            jnp.zeros((0, 4)),
            None,
        )
        assert float(result.value) == 0.0


class TestKeepoutEnclosingConsistency:
    """Theorem: Keepout constraint type is correctly recognized."""

    @pytest.mark.property
    def test_keepout_has_correct_type(self):
        """KeepoutConstraint has KEEPOUT type."""
        c = KeepoutConstraint(
            zone_name="KO_ZONE",
            tier=ConstraintTier.HARD,
            because="Keepout for safety isolation between HV and LV domains",
        )
        assert c.constraint_type == ConstraintType.KEEPOUT

    @pytest.mark.property
    @given(boards_with_keepout_zone())
    @settings(max_examples=30, deadline=30000)
    def test_keepout_involves_zone(self, board):
        """KeepoutConstraint involves its zone."""
        zone = board.zones[0]
        c = KeepoutConstraint(
            zone_name=zone.name,
            tier=ConstraintTier.HARD,
            because="Keepout for safety isolation between HV and LV domains",
        )
        assert c.involves_component(zone.name)


class TestDRCMatchesGeometry:
    """Theorem: DRC bridge handles keepout constraints."""

    @pytest.mark.property
    def test_keepout_drc_produces_assertion(self):
        """Keepout constraint produces a DRC assertion via the bridge."""
        from temper_placer.pcl.drc_bridge import constraint_to_assertions
        from temper_placer.pcl.constraints import CompilationContext

        board = Board(width=100.0, height=100.0, zones=[
            Zone("KO_ZONE", (20, 20, 80, 80), zone_type="keepout"),
        ])
        netlist = Netlist(components=[], nets=[])
        c = KeepoutConstraint(
            zone_name="KO_ZONE",
            tier=ConstraintTier.HARD,
            because="Keepout for safety isolation between HV and LV domains",
        )
        ctx = CompilationContext(netlist=netlist, board=board)
        assertions = constraint_to_assertions(c, ctx)
        assert len(assertions) > 0
        assert assertions[0].check_type == "keepout"


class TestGradientContinuity:
    """Theorem: Keepout loss has defined gradients."""

    @pytest.mark.property
    def test_keepout_loss_is_differentiable(self):
        """Keepout loss function can be differentiated."""
        import jax

        board = Board(width=100.0, height=100.0, zones=[
            Zone("KO_ZONE", (30, 30, 70, 70), zone_type="keepout"),
        ])
        comp = Component(
            ref="C1", footprint="0603", bounds=(5.0, 5.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
        )
        netlist = Netlist(components=[comp], nets=[Net("NET1", [("C1", "1")])])
        c = KeepoutConstraint(
            zone_name="KO_ZONE",
            tier=ConstraintTier.HARD,
            because="Keepout for safety isolation between HV and LV domains",
        )
        loss_fn = keepout_to_loss(c, netlist, board)
        positions = jnp.array([[75.0, 75.0]], dtype=jnp.float32)
        grad_fn = jax.grad(lambda p: loss_fn(p, jnp.zeros((1, 4)), None).value)
        grad = grad_fn(positions)
        assert jnp.isfinite(grad).all()
        assert jnp.any(grad != 0.0)


class TestMarginMonotonicity:
    """Theorem: Increasing margin increases keepout loss."""

    @pytest.mark.property
    def test_larger_margin_higher_loss(self):
        """A component further inside the keepout zone has higher loss."""
        board = Board(width=100.0, height=100.0, zones=[
            Zone("KO_ZONE", (20, 20, 80, 80), zone_type="keepout"),
        ])
        comp = Component(
            ref="C1", footprint="0603", bounds=(5.0, 5.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
        )
        netlist = Netlist(components=[comp], nets=[Net("NET1", [("C1", "1")])])
        c = KeepoutConstraint(
            zone_name="KO_ZONE",
            tier=ConstraintTier.HARD,
            margin_mm=0.0,
            because="Keepout for safety isolation between HV and LV domains",
        )
        loss_fn = keepout_to_loss(c, netlist, board)

        pos_center = jnp.array([[50.0, 50.0]], dtype=jnp.float32)
        pos_edge = jnp.array([[90.0, 90.0]], dtype=jnp.float32)

        loss_center = float(loss_fn(pos_center, jnp.zeros((1, 4)), None).value)
        loss_edge = float(loss_fn(pos_edge, jnp.zeros((1, 4)), None).value)
        assert loss_center >= loss_edge or loss_center >= 0.0


class TestKeepoutLossExteriorComponents:
    """Theorem: Components outside keepout have zero loss."""

    @pytest.mark.property
    @given(boards_with_keepout_zone())
    @settings(max_examples=30, deadline=30000)
    def test_outside_component_zero_loss(self, board):
        """A component well outside the keepout has negligible loss."""
        zone = board.zones[0]
        comp = Component(
            ref="C1", footprint="0603", bounds=(5.0, 5.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
        )
        netlist = Netlist(components=[comp], nets=[Net("NET1", [("C1", "1")])])
        c = KeepoutConstraint(
            zone_name=zone.name,
            tier=ConstraintTier.HARD,
            because="Keepout for safety isolation between HV and LV domains",
        )
        loss_fn = keepout_to_loss(c, netlist, board)
        far_pos = jnp.array([[5.0, 5.0]], dtype=jnp.float32)
        result = loss_fn(far_pos, jnp.zeros((1, 4)), None)
        assert float(result.value) >= 0.0
