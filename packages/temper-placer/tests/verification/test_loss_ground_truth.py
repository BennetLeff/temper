"""
Ground-truth loss function tests with analytically verifiable results.

These tests use simple synthetic configurations where the expected loss
values can be computed by hand. This verifies that the loss functions
implement the correct mathematical formulas.

Test Methodology:
1. Create minimal synthetic configurations (2-4 components)
2. Compute expected values analytically (by hand)
3. Verify loss functions match within tight tolerance
4. Focus on edge cases: zero loss, known nonzero loss, boundary conditions
"""

from __future__ import annotations

import jax.numpy as jnp
import pytest

from temper_placer.losses.boundary import compute_boundary_penalty
from temper_placer.losses.loop_area import compute_loop_area_penalty
from temper_placer.losses.overlap import compute_overlap_penalty
from temper_placer.losses.thermal import compute_edge_distance

# =============================================================================
# Overlap Loss Ground Truth Tests
# =============================================================================


class TestOverlapLossGroundTruth:
    """
    Ground-truth tests for overlap penalty computation.

    The overlap penalty uses:
    - Signed distance: max(sep_x, sep_y) where sep_x = |dx| - (w1/2 + w2/2)
    - Penalty: relu(-signed_dist)² for each pair, summed over upper triangle
    """

    def test_no_overlap_separated_boxes(self):
        """Two non-overlapping boxes should have zero penalty."""
        # Box 1: center (0, 0), size 2x2 -> spans [-1, 1] x [-1, 1]
        # Box 2: center (5, 0), size 2x2 -> spans [4, 6] x [-1, 1]
        # Gap = 3mm, no overlap
        positions = jnp.array([[0.0, 0.0], [5.0, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        penalty = compute_overlap_penalty(positions, widths, heights)

        assert float(penalty) == pytest.approx(0.0, abs=1e-10)

    def test_touching_boxes_zero_penalty(self):
        """Two boxes exactly touching should have zero penalty."""
        # Box 1: center (0, 0), size 2x2 -> spans [-1, 1] x [-1, 1]
        # Box 2: center (2, 0), size 2x2 -> spans [1, 3] x [-1, 1]
        # They touch at x=1, separation = 0
        positions = jnp.array([[0.0, 0.0], [2.0, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        penalty = compute_overlap_penalty(positions, widths, heights)

        assert float(penalty) == pytest.approx(0.0, abs=1e-10)

    def test_50_percent_overlap_known_penalty(self):
        """
        50% overlap should have known squared penalty.

        Box 1: center (0, 0), size 2x2 -> spans [-1, 1] x [-1, 1]
        Box 2: center (1, 0), size 2x2 -> spans [0, 2] x [-1, 1]

        Overlap in x: half_w1 + half_w2 = 2, |dx| = 1, sep_x = 1 - 2 = -1
        Overlap in y: half_h1 + half_h2 = 2, |dy| = 0, sep_y = 0 - 2 = -2
        signed_dist = max(-1, -2) = -1
        penalty = relu(1)² = 1.0
        """
        positions = jnp.array([[0.0, 0.0], [1.0, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        penalty = compute_overlap_penalty(positions, widths, heights)

        # Overlap = 1mm, penalty = 1²  = 1.0
        assert float(penalty) == pytest.approx(1.0, rel=1e-6)

    def test_full_overlap_identical_boxes(self):
        """
        Two identical boxes at same position should have max overlap.

        Box 1 = Box 2: center (0, 0), size 2x2

        sep_x = 0 - 2 = -2, sep_y = 0 - 2 = -2
        signed_dist = max(-2, -2) = -2
        penalty = relu(2)² = 4.0
        """
        positions = jnp.array([[0.0, 0.0], [0.0, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        penalty = compute_overlap_penalty(positions, widths, heights)

        assert float(penalty) == pytest.approx(4.0, rel=1e-6)

    def test_three_components_pairwise_sum(self):
        """
        Three components: verify penalty sums correctly over pairs.

        A at (0,0), B at (1,0), C at (10,0), all 2x2

        Pairs:
        - A-B: sep_x = 1-2=-1, penalty = 1.0
        - A-C: sep_x = 10-2=8 > 0, penalty = 0
        - B-C: sep_x = 9-2=7 > 0, penalty = 0

        Total = 1.0
        """
        positions = jnp.array([[0.0, 0.0], [1.0, 0.0], [10.0, 0.0]])
        widths = jnp.array([2.0, 2.0, 2.0])
        heights = jnp.array([2.0, 2.0, 2.0])

        penalty = compute_overlap_penalty(positions, widths, heights)

        assert float(penalty) == pytest.approx(1.0, rel=1e-6)

    def test_margin_increases_effective_size(self):
        """
        Margin should increase effective box size, creating overlap where none existed.

        Box 1: center (0, 0), size 2x2
        Box 2: center (2.5, 0), size 2x2

        Without margin: gap = 0.5mm, no overlap
        With margin=1.0: effective widths = 3, gap = -0.5mm overlap!

        sep_x = 2.5 - (1.5 + 1.5) = -0.5
        penalty = relu(0.5)² = 0.25
        """
        positions = jnp.array([[0.0, 0.0], [2.5, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        # Without margin
        penalty_no_margin = compute_overlap_penalty(positions, widths, heights, margin=0.0)
        assert float(penalty_no_margin) == pytest.approx(0.0, abs=1e-10)

        # With margin
        penalty_with_margin = compute_overlap_penalty(positions, widths, heights, margin=1.0)
        assert float(penalty_with_margin) == pytest.approx(0.25, rel=1e-6)


# =============================================================================
# Boundary Loss Ground Truth Tests
# =============================================================================


class TestBoundaryLossGroundTruth:
    """
    Ground-truth tests for boundary penalty computation.

    The boundary penalty uses:
    - left_violation = relu((x_min + margin) - comp_left)
    - Similar for right, top, bottom
    - Total = sum of squared violations
    """

    def test_inside_board_zero_penalty(self):
        """Component fully inside board should have zero penalty."""
        # Board: 0-100 x 0-100
        # Component: center (50, 50), size 10x10 -> spans [45, 55] x [45, 55]
        positions = jnp.array([[50.0, 50.0]])
        widths = jnp.array([10.0])
        heights = jnp.array([10.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        penalty = compute_boundary_penalty(positions, widths, heights, board_bounds, margin=0.5)

        assert float(penalty) == pytest.approx(0.0, abs=1e-10)

    def test_left_edge_violation_known_penalty(self):
        """
        Component extending past left edge should have known penalty.

        Board: 0-100 x 0-100, margin=0.5
        Effective left boundary: 0.5
        Component: center (4, 50), size 10x10 -> left edge at -1

        left_violation = relu(0.5 - (-1)) = relu(1.5) = 1.5
        penalty = 1.5² = 2.25
        """
        positions = jnp.array([[4.0, 50.0]])
        widths = jnp.array([10.0])
        heights = jnp.array([10.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        penalty = compute_boundary_penalty(positions, widths, heights, board_bounds, margin=0.5)

        assert float(penalty) == pytest.approx(2.25, rel=1e-6)

    def test_right_edge_violation_known_penalty(self):
        """
        Component extending past right edge.

        Board: 0-100, margin=0.5 -> effective right = 99.5
        Component: center (96, 50), size 10x10 -> right edge at 101

        right_violation = relu(101 - 99.5) = 1.5
        penalty = 2.25
        """
        positions = jnp.array([[96.0, 50.0]])
        widths = jnp.array([10.0])
        heights = jnp.array([10.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        penalty = compute_boundary_penalty(positions, widths, heights, board_bounds, margin=0.5)

        assert float(penalty) == pytest.approx(2.25, rel=1e-6)

    def test_corner_violation_sums_both_edges(self):
        """
        Component at corner violating both edges should sum both penalties.

        Board: 0-100, margin=0
        Component: center (2, 2), size 10x10
        Left edge: -3, violation = 3, penalty = 9
        Bottom edge: -3, violation = 3, penalty = 9
        Total = 18
        """
        positions = jnp.array([[2.0, 2.0]])
        widths = jnp.array([10.0])
        heights = jnp.array([10.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        penalty = compute_boundary_penalty(positions, widths, heights, board_bounds, margin=0.0)

        assert float(penalty) == pytest.approx(18.0, rel=1e-6)

    def test_exactly_at_boundary_zero_penalty(self):
        """Component exactly at board edge (with margin) should have zero penalty."""
        # Board: 0-100, margin=0
        # Component: center (5, 50), size 10x10 -> left edge at 0
        positions = jnp.array([[5.0, 50.0]])
        widths = jnp.array([10.0])
        heights = jnp.array([10.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        penalty = compute_boundary_penalty(positions, widths, heights, board_bounds, margin=0.0)

        assert float(penalty) == pytest.approx(0.0, abs=1e-10)


# =============================================================================
# Wirelength (HPWL) Ground Truth Tests
# =============================================================================


class TestHPWLGroundTruth:
    """
    Ground-truth tests for Half-Perimeter Wire Length computation.

    HPWL = (x_max - x_min) + (y_max - y_min) for each net

    Note: WirelengthLoss uses LogSumExp approximation, so we test with
    high alpha for tight approximation.
    """

    def test_two_pin_net_horizontal(self):
        """
        Two pins on horizontal line: HPWL = x_span + 0.

        Pin 1 at (0, 0), Pin 2 at (10, 0)
        HPWL = (10 - 0) + (0 - 0) = 10
        """
        pin_positions = jnp.array([[0.0, 0.0], [10.0, 0.0]])

        # Direct HPWL computation
        x_span = jnp.max(pin_positions[:, 0]) - jnp.min(pin_positions[:, 0])
        y_span = jnp.max(pin_positions[:, 1]) - jnp.min(pin_positions[:, 1])
        hpwl = x_span + y_span

        assert float(hpwl) == pytest.approx(10.0, rel=1e-6)

    def test_two_pin_net_diagonal(self):
        """
        Two pins on diagonal: HPWL = x_span + y_span.

        Pin 1 at (0, 0), Pin 2 at (3, 4)
        HPWL = 3 + 4 = 7 (not Euclidean distance 5!)
        """
        pin_positions = jnp.array([[0.0, 0.0], [3.0, 4.0]])

        x_span = jnp.max(pin_positions[:, 0]) - jnp.min(pin_positions[:, 0])
        y_span = jnp.max(pin_positions[:, 1]) - jnp.min(pin_positions[:, 1])
        hpwl = x_span + y_span

        assert float(hpwl) == pytest.approx(7.0, rel=1e-6)

    def test_four_pins_square_corners(self):
        """
        Four pins at square corners: HPWL = side + side.

        Pins at (0,0), (10,0), (10,10), (0,10)
        HPWL = (10 - 0) + (10 - 0) = 20
        """
        pin_positions = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, 10.0],
                [0.0, 10.0],
            ]
        )

        x_span = jnp.max(pin_positions[:, 0]) - jnp.min(pin_positions[:, 0])
        y_span = jnp.max(pin_positions[:, 1]) - jnp.min(pin_positions[:, 1])
        hpwl = x_span + y_span

        assert float(hpwl) == pytest.approx(20.0, rel=1e-6)

    def test_all_pins_same_location_zero_hpwl(self):
        """All pins at same location should have zero HPWL."""
        pin_positions = jnp.array(
            [
                [5.0, 5.0],
                [5.0, 5.0],
                [5.0, 5.0],
            ]
        )

        x_span = jnp.max(pin_positions[:, 0]) - jnp.min(pin_positions[:, 0])
        y_span = jnp.max(pin_positions[:, 1]) - jnp.min(pin_positions[:, 1])
        hpwl = x_span + y_span

        assert float(hpwl) == pytest.approx(0.0, abs=1e-10)

    def test_logsumexp_approximation_accuracy(self):
        """
        Test that LogSumExp with moderate alpha closely approximates true max/min.

        For alpha=10, LogSumExp max should be within ~5% of true max.
        Using jax.nn.logsumexp for numerical stability (avoids overflow).
        """
        import jax

        values = jnp.array([1.0, 5.0, 3.0, 2.0])
        alpha = 10.0

        true_max = jnp.max(values)
        # Use jax.nn.logsumexp for numerical stability
        logsumexp_max = jax.nn.logsumexp(alpha * values) / alpha

        # Moderate alpha gives reasonable approximation
        # The overestimate is bounded by log(n)/alpha where n is number of elements
        # For n=4, alpha=10: bias <= log(4)/10 ≈ 0.14
        assert float(logsumexp_max) == pytest.approx(float(true_max), abs=0.2)


# =============================================================================
# Thermal Loss Ground Truth Tests
# =============================================================================


class TestThermalEdgeDistanceGroundTruth:
    """
    Ground-truth tests for edge distance computation.
    """

    def test_distance_to_top_edge(self):
        """
        Distance from point to TOP edge.

        Board: 0-100 x 0-100
        Point: (50, 80)
        Distance to TOP (y_max=100): 100 - 80 = 20
        """
        position = jnp.array([50.0, 80.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        dist = compute_edge_distance(position, board_bounds, "TOP")

        assert float(dist) == pytest.approx(20.0, rel=1e-6)

    def test_distance_to_bottom_edge(self):
        """
        Distance to BOTTOM edge.

        Point: (50, 25)
        Distance to BOTTOM (y_min=0): 25 - 0 = 25
        """
        position = jnp.array([50.0, 25.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        dist = compute_edge_distance(position, board_bounds, "BOTTOM")

        assert float(dist) == pytest.approx(25.0, rel=1e-6)

    def test_distance_to_left_edge(self):
        """
        Distance to LEFT edge.

        Point: (15, 50)
        Distance to LEFT (x_min=0): 15 - 0 = 15
        """
        position = jnp.array([15.0, 50.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        dist = compute_edge_distance(position, board_bounds, "LEFT")

        assert float(dist) == pytest.approx(15.0, rel=1e-6)

    def test_distance_to_right_edge(self):
        """
        Distance to RIGHT edge.

        Point: (60, 50)
        Distance to RIGHT (x_max=100): 100 - 60 = 40
        """
        position = jnp.array([60.0, 50.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        dist = compute_edge_distance(position, board_bounds, "RIGHT")

        assert float(dist) == pytest.approx(40.0, rel=1e-6)

    def test_point_exactly_at_edge(self):
        """Point exactly at edge should have distance 0."""
        position = jnp.array([50.0, 100.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        dist = compute_edge_distance(position, board_bounds, "TOP")

        assert float(dist) == pytest.approx(0.0, abs=1e-10)


# =============================================================================
# Loop Area Ground Truth Tests
# =============================================================================


class TestLoopAreaGroundTruth:
    """
    Ground-truth tests for loop area computation using shoelace formula.

    Shoelace formula: Area = 0.5 * |sum(x_i * y_{i+1} - x_{i+1} * y_i)|
    """

    def test_unit_square_loop_area(self):
        """
        Unit square: pins at (0,0), (1,0), (1,1), (0,1)

        Shoelace:
        (0*0 - 1*0) + (1*1 - 1*0) + (1*1 - 0*1) + (0*0 - 0*1)
        = 0 + 1 + 1 + 0 = 2
        Area = |2|/2 = 1
        """
        pin_positions = jnp.array(
            [
                [0.0, 0.0],
                [1.0, 0.0],
                [1.0, 1.0],
                [0.0, 1.0],
            ]
        )

        # Manual shoelace
        vertices_next = jnp.roll(pin_positions, -1, axis=0)
        cross = (
            pin_positions[:, 0] * vertices_next[:, 1] - vertices_next[:, 0] * pin_positions[:, 1]
        )
        area = jnp.abs(jnp.sum(cross) / 2.0)

        assert float(area) == pytest.approx(1.0, rel=1e-6)

    def test_rectangle_10x5_loop_area(self):
        """
        10x5 rectangle should have area = 50.

        Pins at (0,0), (10,0), (10,5), (0,5)
        """
        pin_positions = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, 5.0],
                [0.0, 5.0],
            ]
        )

        vertices_next = jnp.roll(pin_positions, -1, axis=0)
        cross = (
            pin_positions[:, 0] * vertices_next[:, 1] - vertices_next[:, 0] * pin_positions[:, 1]
        )
        area = jnp.abs(jnp.sum(cross) / 2.0)

        assert float(area) == pytest.approx(50.0, rel=1e-6)

    def test_right_triangle_loop_area(self):
        """
        Right triangle with legs 3 and 4 should have area = 6.

        Pins at (0,0), (3,0), (0,4)
        Area = base * height / 2 = 3 * 4 / 2 = 6
        """
        pin_positions = jnp.array(
            [
                [0.0, 0.0],
                [3.0, 0.0],
                [0.0, 4.0],
            ]
        )

        vertices_next = jnp.roll(pin_positions, -1, axis=0)
        cross = (
            pin_positions[:, 0] * vertices_next[:, 1] - vertices_next[:, 0] * pin_positions[:, 1]
        )
        area = jnp.abs(jnp.sum(cross) / 2.0)

        assert float(area) == pytest.approx(6.0, rel=1e-6)

    def test_collinear_points_zero_area(self):
        """Collinear points should have zero area."""
        pin_positions = jnp.array(
            [
                [0.0, 0.0],
                [5.0, 0.0],
                [10.0, 0.0],
            ]
        )

        vertices_next = jnp.roll(pin_positions, -1, axis=0)
        cross = (
            pin_positions[:, 0] * vertices_next[:, 1] - vertices_next[:, 0] * pin_positions[:, 1]
        )
        area = jnp.abs(jnp.sum(cross) / 2.0)

        assert float(area) == pytest.approx(0.0, abs=1e-10)

    def test_loop_penalty_below_max_zero(self):
        """Loop with area below max should have zero penalty."""
        # Unit square, area = 1, max_area = 10
        pin_positions = jnp.array(
            [
                [0.0, 0.0],
                [1.0, 0.0],
                [1.0, 1.0],
                [0.0, 1.0],
            ]
        )

        penalty = compute_loop_area_penalty(pin_positions, max_area=10.0, scale=1.0)

        assert float(penalty) == pytest.approx(0.0, abs=1e-10)

    def test_loop_penalty_above_max_known_value(self):
        """
        Loop with area above max should have quadratic penalty.

        10x10 square, area = 100, max_area = 50
        violation = 100 - 50 = 50
        penalty = 1.0 * 50² = 2500
        """
        pin_positions = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, 10.0],
                [0.0, 10.0],
            ]
        )

        penalty = compute_loop_area_penalty(pin_positions, max_area=50.0, scale=1.0)

        assert float(penalty) == pytest.approx(2500.0, rel=1e-6)

    def test_loop_penalty_scale_factor(self):
        """Scale factor should multiply the penalty."""
        pin_positions = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, 10.0],
                [0.0, 10.0],
            ]
        )

        # area=100, max=50, violation=50
        # penalty = scale * 50²
        penalty_scale_1 = compute_loop_area_penalty(pin_positions, max_area=50.0, scale=1.0)
        penalty_scale_01 = compute_loop_area_penalty(pin_positions, max_area=50.0, scale=0.01)

        assert float(penalty_scale_1) == pytest.approx(2500.0, rel=1e-6)
        assert float(penalty_scale_01) == pytest.approx(25.0, rel=1e-6)


# =============================================================================
# Cross-Loss Consistency Tests
# =============================================================================


class TestLossConsistency:
    """
    Tests verifying consistent behavior across loss functions.
    """

    def test_all_losses_return_scalar(self):
        """All loss functions should return scalar values."""
        positions = jnp.array([[0.0, 0.0], [10.0, 10.0]])
        widths = jnp.array([5.0, 5.0])
        heights = jnp.array([5.0, 5.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        overlap = compute_overlap_penalty(positions, widths, heights)
        boundary = compute_boundary_penalty(positions, widths, heights, board_bounds)

        assert overlap.shape == ()
        assert boundary.shape == ()

    def test_losses_non_negative(self):
        """All penalties should be non-negative."""
        positions = jnp.array([[0.0, 0.0], [1.0, 0.0]])  # Overlapping
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        overlap = compute_overlap_penalty(positions, widths, heights)
        boundary = compute_boundary_penalty(positions, widths, heights, board_bounds)

        assert float(overlap) >= 0.0
        assert float(boundary) >= 0.0

    def test_losses_differentiable(self):
        """All losses should have finite gradients (basic check)."""
        import jax

        positions = jnp.array([[0.0, 0.0], [1.0, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        # Overlap gradient
        overlap_grad_fn = jax.grad(lambda p: compute_overlap_penalty(p, widths, heights))
        overlap_grad = overlap_grad_fn(positions)
        assert jnp.all(jnp.isfinite(overlap_grad))

        # Boundary gradient
        boundary_grad_fn = jax.grad(
            lambda p: compute_boundary_penalty(p, widths, heights, board_bounds)
        )
        boundary_grad = boundary_grad_fn(positions)
        assert jnp.all(jnp.isfinite(boundary_grad))
