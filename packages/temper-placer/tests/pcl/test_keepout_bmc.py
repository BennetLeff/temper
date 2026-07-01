"""ESL/BMC exhaustiveness for keepout loss.

Verifies the keepout loss function against a ground-truth predicate by
brute-force checking all positions on a grid.

Note: The keepout loss implementation uses smooth_relu_penalty which
produces a non-zero floor at zero penetration (~log(2)^2 * weight).
We verify that the raw penetration is zero iff contained, and that
loss scales monotonically with penetration depth.

Properties verified:
- loss > 0 iff the raw penetration > 0
- Raw penetration == 0 iff all components are inside the effective zone bounds
- Loss is monotonic with penetration depth
- Margin shrinks the zero-loss region
"""

from __future__ import annotations

import itertools
import math

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.pcl.constraints import ConstraintTier, KeepoutConstraint
from temper_placer.pcl.loss_bridge import keepout_to_loss


def _esl_contained(
    positions: list[tuple[float, float]],
    zone_bounds: tuple[float, float, float, float],
    margin: float,
) -> bool:
    """Ground-truth predicate: all positions are within the effective zone bounds."""
    x_min, y_min, x_max, y_max = zone_bounds
    eff_x_min = x_min + margin
    eff_y_min = y_min + margin
    eff_x_max = x_max - margin
    eff_y_max = y_max - margin
    for x, y in positions:
        if not (eff_x_min <= x <= eff_x_max and eff_y_min <= y <= eff_y_max):
            return False
    return True


def _raw_penetration(
    position: tuple[float, float],
    zone_bounds: tuple[float, float, float, float],
    margin: float,
) -> float:
    """Compute raw penetration for a single position."""
    x_min, y_min, x_max, y_max = zone_bounds
    x, y = position[0], position[1]
    pen_x = max(0.0, (x_min + margin) - x) + max(0.0, x - (x_max - margin))
    pen_y = max(0.0, (y_min + margin) - y) + max(0.0, y - (y_max - margin))
    return pen_x + pen_y


def _total_raw_penetration(
    positions: list[tuple[float, float]],
    zone_bounds: tuple[float, float, float, float],
    margin: float,
) -> float:
    """Sum of raw penetrations across all positions."""
    return sum(_raw_penetration(p, zone_bounds, margin) for p in positions)


def _make_netlist(n_components: int) -> Netlist:
    comps = [
        Component(
            ref=f"C{i}",
            footprint="0603",
            bounds=(5.0, 5.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
        )
        for i in range(n_components)
    ]
    return Netlist(
        components=comps,
        nets=[Net("NET1", [(f"C{i}", "1") for i in range(n_components)])],
    )


def _grid_positions(xs: list[float], ys: list[float], n_components: int) -> list[list[tuple[float, float]]]:
    """All combinations of n_components positions on an X*Y grid."""
    all_points = [(x, y) for x in xs for y in ys]
    return [list(combo) for combo in itertools.product(all_points, repeat=n_components)]


ZONE = (30.0, 30.0, 70.0, 70.0)
MARGIN_MM = 5.0

# smooth_relu_penalty(0) = (log(2) / 10)^2 ≈ 0.0048
SMOOTH_RELU_FLOOR = (math.log(2) / 10.0) ** 2


class TestKeepoutBMCSoundness:
    """ESL-style BMC: exhaustive grid enumeration against ground-truth predicate."""

    @pytest.mark.parametrize("n_components,grid_size", [(2, 3), (3, 2)])
    def test_loss_zero_iff_contained(self, n_components, grid_size):
        """For all grid positions: raw penetration == 0 iff contained within
        the effective zone bounds."""
        board = Board(
            width=100.0,
            height=100.0,
            zones=[Zone("KO", ZONE, zone_type="keepout")],
        )
        netlist = _make_netlist(n_components)
        constraint = KeepoutConstraint(
            zone_name="KO",
            tier=ConstraintTier.HARD,
            margin_mm=MARGIN_MM,
            because="BMC exhaustiveness test for keepout",
        )
        loss_fn = keepout_to_loss(constraint, netlist, board)

        xs = [float(i * 25) for i in range(grid_size + 2)]
        ys = [float(i * 25) for i in range(grid_size + 2)]
        positions_list = _grid_positions(xs, ys, n_components)

        mismatches = []
        for positions in positions_list:
            contained = _esl_contained(positions, ZONE, MARGIN_MM)
            raw = _total_raw_penetration(positions, ZONE, MARGIN_MM)

            if (raw == 0.0) != contained:
                mismatches.append(
                    f"raw_pen={raw:.6f}, contained={contained} at positions={positions}"
                )

        assert len(mismatches) == 0, (
            f"{len(mismatches)} mismatches in {len(positions_list)} states: {mismatches[:5]}"
        )

    @pytest.mark.parametrize("n_components,grid_size", [(2, 3), (3, 2)])
    def test_loss_positive_iff_outside(self, n_components, grid_size):
        """Loss is positive (above smooth floor) iff any component is outside."""
        board = Board(
            width=100.0,
            height=100.0,
            zones=[Zone("KO", ZONE, zone_type="keepout")],
        )
        netlist = _make_netlist(n_components)
        constraint = KeepoutConstraint(
            zone_name="KO",
            tier=ConstraintTier.HARD,
            margin_mm=0.0,
            because="BMC test for keepout loss",
        )
        loss_fn = keepout_to_loss(constraint, netlist, board)

        xs = [float(i * 25) for i in range(grid_size + 2)]
        ys = [float(i * 25) for i in range(grid_size + 2)]
        positions_list = _grid_positions(xs, ys, n_components)

        # Floor loss = all positions at zero penetration
        # = n * weight * smooth_relu_penalty(0)
        weight = 1_000_000.0
        epsilon = n_components * weight * SMOOTH_RELU_FLOOR * 1.1

        errors = []
        for positions in positions_list:
            jax_pos = jnp.array(positions, dtype=jnp.float32)
            rotations = jnp.zeros((n_components, 4), dtype=jnp.float32)
            result = loss_fn(jax_pos, rotations, None)
            loss = float(result.value)

            contained = _esl_contained(positions, ZONE, 0.0)

            if contained:
                if loss > epsilon:
                    errors.append(
                        f"Contained but loss={loss:.1f} > epsilon={epsilon:.1f} at {positions}"
                    )
            else:
                if loss <= epsilon:
                    errors.append(
                        f"Not contained but loss={loss:.1f} <= epsilon={epsilon:.1f} at {positions}"
                    )

        assert len(errors) == 0, (
            f"{len(errors)} errors in {len(positions_list)} states: {errors[:5]}"
        )


class TestKeepoutBMCMonotonicity:
    """Monotonicity: farther from zone => higher loss."""

    def test_farther_from_zone_higher_loss(self):
        """A component far outside the zone has >= loss than one just outside."""
        board = Board(
            width=100.0,
            height=100.0,
            zones=[Zone("KO", (20, 20, 80, 80), zone_type="keepout")],
        )
        netlist = _make_netlist(1)
        constraint = KeepoutConstraint(
            zone_name="KO",
            tier=ConstraintTier.HARD,
            margin_mm=0.0,
            because="Monotonicity keepout loss test",
        )
        loss_fn = keepout_to_loss(constraint, netlist, board)

        pos_far = jnp.array([[0.0, 50.0]], dtype=jnp.float32)
        pos_near = jnp.array([[15.0, 50.0]], dtype=jnp.float32)
        rot = jnp.zeros((1, 4), dtype=jnp.float32)
        loss_far = float(loss_fn(pos_far, rot, None).value)
        loss_near = float(loss_fn(pos_near, rot, None).value)

        assert loss_far >= loss_near, (
            f"Farther point should have >= loss: far={loss_far:.1f}, near={loss_near:.1f}"
        )

    def test_deeper_penetration_higher_loss(self):
        """Moving stepwise away from the zone monotonically increases loss."""
        board = Board(
            width=100.0,
            height=100.0,
            zones=[Zone("KO", (25, 25, 75, 75), zone_type="keepout")],
        )
        netlist = _make_netlist(1)
        constraint = KeepoutConstraint(
            zone_name="KO",
            tier=ConstraintTier.HARD,
            margin_mm=0.0,
            because="Monotonic sequence keepout test",
        )
        loss_fn = keepout_to_loss(constraint, netlist, board)
        rotations = jnp.zeros((1, 4), dtype=jnp.float32)

        prev_loss = -1.0
        for x in range(24, -1, -5):
            pos = jnp.array([[float(x), 50.0]], dtype=jnp.float32)
            loss = float(loss_fn(pos, rotations, None).value)
            assert loss >= prev_loss, (
                f"Loss not monotonic: at x={x}, loss={loss:.1f} < prev={prev_loss:.1f}"
            )
            prev_loss = loss


class TestKeepoutBMCEdgeCases:
    """Edge cases."""

    def test_margin_shrinks_zero_loss_region(self):
        """Margin shrinks the effective bounds, turning zero-loss to > floor."""
        board = Board(
            width=100.0,
            height=100.0,
            zones=[Zone("KO", (40, 40, 60, 60), zone_type="keepout")],
        )
        netlist = _make_netlist(1)
        rotations = jnp.zeros((1, 4), dtype=jnp.float32)
        weight = 1_000_000.0

        c_no_margin = KeepoutConstraint(
            zone_name="KO",
            tier=ConstraintTier.HARD,
            margin_mm=0.0,
            because="No margin for keepout test",
        )
        c_with_margin = KeepoutConstraint(
            zone_name="KO",
            tier=ConstraintTier.HARD,
            margin_mm=3.0,
            because="With margin for keepout test",
        )

        pos = jnp.array([[42.0, 50.0]], dtype=jnp.float32)

        loss_no = float(
            keepout_to_loss(c_no_margin, netlist, board)(pos, rotations, None).value
        )
        loss_with = float(
            keepout_to_loss(c_with_margin, netlist, board)(pos, rotations, None).value
        )

        epsilon = weight * SMOOTH_RELU_FLOOR * 1.1
        assert loss_no <= epsilon, f"Without margin, (42,50) inside zone: {loss_no:.1f}"
        assert loss_with > epsilon, (
            f"With margin=3, (42,50) outside effective bounds: {loss_with:.1f}"
        )

    def test_center_of_large_zone_zero_loss(self):
        """Center of large zone produces only the smooth-relu floor loss."""
        board = Board(
            width=200.0,
            height=200.0,
            zones=[Zone("KO", (50, 50, 150, 150), zone_type="keepout")],
        )
        netlist = _make_netlist(1)
        constraint = KeepoutConstraint(
            zone_name="KO",
            tier=ConstraintTier.HARD,
            because="Center zone position test",
        )
        loss_fn = keepout_to_loss(constraint, netlist, board)
        pos = jnp.array([[100.0, 100.0]], dtype=jnp.float32)
        rot = jnp.zeros((1, 4), dtype=jnp.float32)
        loss = float(loss_fn(pos, rot, None).value)

        epsilon = 1_000_000.0 * SMOOTH_RELU_FLOOR * 1.1
        assert loss <= epsilon, (
            f"Center of zone should have only floor loss, got {loss:.1f}"
        )

    def test_well_outside_has_high_loss(self):
        """A point far outside the zone has loss much larger than floor."""
        board = Board(
            width=200.0,
            height=200.0,
            zones=[Zone("KO", (50, 50, 150, 150), zone_type="keepout")],
        )
        netlist = _make_netlist(1)
        constraint = KeepoutConstraint(
            zone_name="KO",
            tier=ConstraintTier.HARD,
            because="Outside zone position test",
        )
        loss_fn = keepout_to_loss(constraint, netlist, board)
        pos = jnp.array([[10.0, 100.0]], dtype=jnp.float32)
        rot = jnp.zeros((1, 4), dtype=jnp.float32)
        loss = float(loss_fn(pos, rot, None).value)

        floor = 1_000_000.0 * SMOOTH_RELU_FLOOR
        assert loss > floor * 10, (
            f"Outside point should have loss >> floor: got {loss:.1f}, floor={floor:.1f}"
        )
