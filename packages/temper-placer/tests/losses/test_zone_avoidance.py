"""
Tests for ZoneAvoidanceLoss - TDD approach for temper-3b1l

These tests verify that the ZoneAvoidanceLoss correctly penalizes components
being placed inside or too close to restricted zones (especially HV zones).
"""

import jax
import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.base import LossContext
from temper_placer.losses.zone_avoidance import (
    ZoneAvoidanceLoss,
    compute_zone_avoidance_penalty,
    signed_distance_to_polygon,
)


@pytest.fixture
def hv_board():
    """Create a board with HV and LV zones for testing zone avoidance."""
    return Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        zones=[
            Zone("HV_ZONE", (0, 0, 40, 100), net_classes=["HighVoltage"]),
            Zone("LV_ZONE", (40, 0, 100, 100), net_classes=["Signal", "LowVoltage"]),
        ],
    )


@pytest.fixture
def hv_components():
    """Create components that should be restricted from HV zone."""
    return [
        Component(
            ref="U_MCU",
            footprint="QFN-48",
            bounds=(7.0, 7.0),
            pins=[
                Pin("VCC", "1", (3.0, 3.0), net="3V3"),
                Pin("GND", "10", (-3.0, -3.0), net="GND"),
            ],
            net_class="LowVoltage",
        ),
        Component(
            ref="R_PULL",
            footprint="0603",
            bounds=(1.6, 0.8),
            pins=[
                Pin("1", "1", (-0.75, 0.0), net="NET_A"),
                Pin("2", "2", (0.75, 0.0), net="3V3"),
            ],
            net_class="LowVoltage",
        ),
    ]


@pytest.fixture
def hv_nets():
    """Create nets for the HV board."""
    return [
        Net("3V3", [("U_MCU", "VCC"), ("R_PULL", "2")], net_class="Power", weight=1.0),
        Net("GND", [("U_MCU", "GND")], net_class="Power", weight=1.0),
        Net("NET_A", [("R_PULL", "1")], net_class="Signal", weight=1.0),
    ]


@pytest.fixture
def hv_netlist(hv_components, hv_nets):
    """Create netlist for HV board tests."""
    return Netlist(components=hv_components, nets=hv_nets)


class TestSignedDistanceToPolygon:
    """Tests for the signed distance computation to polygon boundary."""

    def test_point_inside_rectangle(self):
        """Point inside rectangle should have negative distance."""
        rect = jnp.array([[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]])
        point = jnp.array([5.0, 2.5])
        dist = signed_distance_to_polygon(point, rect)
        assert float(dist) < 0.0, "Point inside should have negative distance"

    def test_point_outside_rectangle(self):
        """Point outside rectangle should have positive distance."""
        rect = jnp.array([[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]])
        point = jnp.array([15.0, 2.5])  # To the right
        dist = signed_distance_to_polygon(point, rect)
        assert float(dist) > 0.0, "Point outside should have positive distance"

    def test_point_on_boundary(self):
        """Point on boundary should have zero distance."""
        rect = jnp.array([[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]])
        point = jnp.array([10.0, 2.5])  # On right edge
        dist = signed_distance_to_polygon(point, rect)
        assert float(dist) == pytest.approx(0.0, abs=1e-5)

    def test_distance_equals_margin_at_boundary(self):
        """Distance should equal margin when point is at margin from boundary."""
        rect = jnp.array([[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]])
        point = jnp.array([12.0, 2.5])  # 2mm to the right of boundary
        dist = signed_distance_to_polygon(point, rect)
        assert float(dist) == pytest.approx(2.0, abs=1e-5)

    def test_corner_outside_distance(self):
        """Corner outside should give Euclidean distance to corner."""
        rect = jnp.array([[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]])
        point = jnp.array([15.0, 10.0])  # Upper right outside
        dist = signed_distance_to_polygon(point, rect)
        expected = jnp.sqrt(5.0**2 + 5.0**2)  # sqrt(25+25) = 7.07
        assert float(dist) == pytest.approx(expected, abs=1e-5)

    def test_batch_computation(self):
        """Test that multiple points can be evaluated."""
        rect = jnp.array([[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]])
        points = jnp.array(
            [
                [5.0, 2.5],  # Inside
                [15.0, 2.5],  # Outside right
                [5.0, -2.5],  # Outside bottom
            ]
        )
        dists = jax.vmap(signed_distance_to_polygon, (0, None))(points, rect)
        assert float(dists[0]) < 0.0
        assert float(dists[1]) > 0.0
        assert float(dists[2]) > 0.0


class TestComputeZoneAvoidancePenalty:
    """Tests for the zone avoidance penalty computation."""

    def test_no_zones_returns_zero(self, simple_netlist, simple_board):
        """Board with no zones should return zero penalty."""
        penalty = compute_zone_avoidance_penalty(
            jnp.zeros((simple_netlist.n_components, 2)),
            LossContext.from_netlist_and_board(simple_netlist, simple_board),
        )
        assert float(penalty) == 0.0

    def test_component_inside_hv_zone_high_penalty(self, hv_netlist, hv_board):
        """Component deep inside HV zone should receive high penalty."""
        context = LossContext.from_netlist_and_board(hv_netlist, hv_board)
        positions = jnp.array(
            [
                [20.0, 50.0],  # U_MCU deep inside HV_ZONE (0-40, 0-100), 20mm from boundary
                [50.0, 50.0],  # R_PULL in LV_ZONE
            ]
        )
        penalty = compute_zone_avoidance_penalty(positions, context, margin=2.0)
        # dist = 20 - 40 = -20, depth_inside = max(0, 20 - 2) = 18, penalty = 18^2 = 324
        assert float(penalty) > 0.0, "Component deep in HV zone should be penalized"

    def test_component_outside_hv_zone_zero_penalty(self, hv_netlist, hv_board):
        """Component outside HV zone should receive zero penalty."""
        context = LossContext.from_netlist_and_board(hv_netlist, hv_board)
        positions = jnp.array(
            [
                [50.0, 50.0],  # U_MCU in LV_ZONE
                [50.0, 50.0],  # R_PULL in LV_ZONE
            ]
        )
        penalty = compute_zone_avoidance_penalty(positions, context)
        # dist = 50 - 40 = 10, depth_inside = max(0, -10 - 2) = 0, penalty = 0
        assert float(penalty) == 0.0

    def test_component_near_boundary_no_penalty(self, hv_netlist, hv_board):
        """Component near HV zone boundary (within margin) should have zero penalty."""
        context = LossContext.from_netlist_and_board(hv_netlist, hv_board)
        positions = jnp.array(
            [
                [38.0, 50.0],  # 2mm inside HV boundary at x=40, margin=2mm
                [50.0, 50.0],
            ]
        )
        penalty = compute_zone_avoidance_penalty(positions, context)
        # dist = 38 - 40 = -2, depth_inside = max(0, 2 - 2) = 0, penalty = 0
        assert float(penalty) == 0.0, "Component within margin of boundary should have zero penalty"

    def test_component_deep_inside_penalty(self, hv_netlist, hv_board):
        """Component deep inside HV zone (beyond margin) should have penalty."""
        context = LossContext.from_netlist_and_board(hv_netlist, hv_board)
        positions = jnp.array(
            [
                [30.0, 50.0],  # 10mm inside HV boundary at x=40, margin=2mm
                [50.0, 50.0],
            ]
        )
        penalty = compute_zone_avoidance_penalty(positions, context)
        # dist = 30 - 40 = -10, depth_inside = max(0, 10 - 2) = 8, penalty = 8^2 = 64
        assert float(penalty) == pytest.approx(64.0, abs=1e-3)


class TestZoneAvoidanceLoss:
    """Tests for the ZoneAvoidanceLoss class."""

    def test_loss_name(self):
        """Loss should have correct name."""
        loss = ZoneAvoidanceLoss()
        assert loss.name == "zone_avoidance"

    def test_loss_with_margin(self):
        """Loss with margin should define exclusion zone around boundaries."""
        loss = ZoneAvoidanceLoss(margin=2.0)
        assert loss.margin == 2.0

    def test_loss_with_zones(self):
        """Loss should accept specific zones to avoid."""
        zones_to_avoid = ["HV_ZONE", "KEEPOUT_ZONE"]
        loss = ZoneAvoidanceLoss(zones_to_avoid=zones_to_avoid)
        assert loss.zones_to_avoid == zones_to_avoid

    def test_gradient_exists(self, hv_netlist, hv_board):
        """Loss should have valid gradients for optimization."""
        context = LossContext.from_netlist_and_board(hv_netlist, hv_board)
        loss_fn = ZoneAvoidanceLoss()

        positions = jnp.array(
            [
                [20.0, 50.0],
                [50.0, 50.0],
            ]
        )

        grad_fn = jax.grad(lambda p: loss_fn(p, None, context).value)
        gradients = grad_fn(positions)

        assert gradients.shape == (2, 2)
        assert jnp.all(jnp.isfinite(gradients)), "Gradients should be finite"

    def test_gradients_push_out_of_zone(self, hv_netlist, hv_board):
        """Gradients should push component toward boundary (negative for gradient descent)."""
        context = LossContext.from_netlist_and_board(hv_netlist, hv_board)
        loss_fn = ZoneAvoidanceLoss(margin=2.0)

        # Component deep inside HV zone (beyond margin)
        positions = jnp.array(
            [
                [30.0, 50.0],  # 10mm inside HV zone, 8mm beyond margin
                [50.0, 50.0],
            ]
        )

        grad_fn = jax.grad(lambda p: loss_fn(p, None, context).value)
        gradients = grad_fn(positions)

        # Gradient is NEGATIVE because gradient descent does: x = x - lr * gradient
        # So negative gradient means x will INCREASE toward the boundary at x=40
        assert float(gradients[0, 0]) < 0.0, (
            "Gradient should be negative (gradient descent increases x)"
        )

    def test_jit_compatible(self, hv_netlist, hv_board):
        """Loss computation should be JIT compatible for inner functions."""
        context = LossContext.from_netlist_and_board(hv_netlist, hv_board)
        loss_fn = ZoneAvoidanceLoss()

        positions = jnp.array(
            [
                [30.0, 50.0],
                [50.0, 50.0],
            ]
        )

        # JIT compile the inner penalty computation
        jit_penalty = jax.jit(lambda p: compute_zone_avoidance_penalty(p, context))
        result = jit_penalty(positions)

        assert jnp.isfinite(result)
        assert float(result) > 0.0  # Component is inside HV zone

    def test_breakdown_includes_zone_avoidance(self, hv_netlist, hv_board):
        """Result breakdown should include zone_avoidance metric."""
        context = LossContext.from_netlist_and_board(hv_netlist, hv_board)
        loss_fn = ZoneAvoidanceLoss()

        positions = jnp.array(
            [
                [20.0, 50.0],
                [50.0, 50.0],
            ]
        )

        result = loss_fn(positions, None, context)
        assert "zone_avoidance" in result.breakdown


class TestZoneAvoidanceIntegration:
    """Integration tests for zone avoidance with full optimization context."""

    def test_placement_moves_away_from_hv_zone(self, hv_netlist, hv_board):
        """Full test: optimization should move components out of HV zone."""
        from temper_placer.losses.base import CompositeLoss, WeightedLoss
        from temper_placer.losses.overlap import OverlapLoss
        from temper_placer.losses.wirelength import WirelengthLoss

        context = LossContext.from_netlist_and_board(hv_netlist, hv_board)

        # Create composite loss with zone avoidance
        composite = CompositeLoss(
            [
                WeightedLoss(ZoneAvoidanceLoss(margin=2.0), weight=10.0),
                WeightedLoss(OverlapLoss(), weight=100.0),
                WeightedLoss(WirelengthLoss(), weight=1.0),
            ]
        )

        # Initial positions: one component deep inside HV zone (beyond margin)
        positions = jnp.array(
            [
                [30.0, 50.0],  # Deep inside HV zone, should be pushed out
                [50.0, 50.0],
            ]
        )
        rotations = jnp.zeros((2, 4)).at[:, 0].set(1.0)  # All 0 degree rotation

        # Compute loss
        initial_loss = composite(positions, rotations, context).value

        # Apply gradient update
        value_and_grad = jax.jit(jax.value_and_grad(lambda p, r: composite(p, r, context).value))
        loss, grads = value_and_grad(positions, rotations)

        # Take gradient step
        learning_rate = 0.1
        new_positions = positions - learning_rate * grads[0]

        # New positions should be closer to LV zone (x > 40)
        assert float(new_positions[0, 0]) > float(positions[0, 0]), (
            "Component should be pushed right (toward LV zone)"
        )

    def test_component_far_from_zone_has_zero_loss(self, hv_netlist, hv_board):
        """Component far from any forbidden zone should have zero loss."""
        context = LossContext.from_netlist_and_board(hv_netlist, hv_board)
        loss_fn = ZoneAvoidanceLoss()

        # Positions far from HV zone (which is 0-40)
        positions = jnp.array(
            [
                [80.0, 50.0],  # Deep in LV zone, outside HV zone
                [90.0, 90.0],
            ]
        )

        result = loss_fn(positions, None, context)
        # dist = 80 - 40 = 40, depth_inside = max(0, -40 - 2) = 0, penalty = 0
        assert float(result.value) == pytest.approx(0.0, abs=1e-6)
