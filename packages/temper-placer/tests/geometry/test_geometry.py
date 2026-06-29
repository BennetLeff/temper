"""
Unit tests for the geometry engine.

Tests cover:
- Rotation correctness at 0°, 90°, 180°, 270°
- SDF signs (negative inside, positive outside, zero on boundary)
- Overlap detection for overlapping and non-overlapping boxes
- Smooth min/max approximation accuracy
- Polygon area for known shapes
- JAX gradient compatibility
"""

import jax
import jax.numpy as jnp
from jax import grad

from temper_placer.geometry.overlap import (
    box_box_distance,
    check_clearance_violation,
    component_overlap_amount,
)
from temper_placer.geometry.polygon import (
    point_in_polygon_soft,
    point_in_polygon_winding,
    polygon_area,
    polygon_centroid,
    polygon_perimeter,
    rotate_polygon,
    scale_polygon,
)

# Import geometry functions
from temper_placer.geometry.primitives import (
    distance_to_rect_edge,
    distance_to_specific_edge,
    point_distance,
    point_distance_squared,
    points_centroid,
    rect_area,
    rect_center,
)
from temper_placer.geometry.sdf import (
    sdf_circle,
    sdf_intersection,
    sdf_rectangle,
    sdf_union,
)
from temper_placer.geometry.smooth import (
    hpwl_smooth,
    smooth_abs,
    smooth_max,
    smooth_max_pair,
    smooth_min,
    smooth_min_pair,
    smooth_relu,
)
from temper_placer.geometry.transform import (
    get_rotation_matrix,
    gumbel_softmax,
    onehot_to_rotation_degrees,
    rotate_point,
    rotation_index_to_onehot,
    sample_rotation,
    sample_rotation_batch,
)

# =============================================================================
# Primitives Tests
# =============================================================================


class TestPrimitives:
    """Tests for basic geometric primitives."""

    def test_point_distance(self):
        """Test Euclidean distance between points."""
        p1 = jnp.array([0.0, 0.0])
        p2 = jnp.array([3.0, 4.0])
        assert jnp.isclose(point_distance(p1, p2), 5.0)

    def test_point_distance_squared(self):
        """Test squared distance (avoids sqrt)."""
        p1 = jnp.array([0.0, 0.0])
        p2 = jnp.array([3.0, 4.0])
        assert jnp.isclose(point_distance_squared(p1, p2), 25.0)

    def test_points_centroid(self):
        """Test centroid of point cloud."""
        points = jnp.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])
        centroid = points_centroid(points)
        assert jnp.allclose(centroid, jnp.array([1.0, 1.0]))

    def test_rect_center(self):
        """Test rectangle center from corners."""
        min_corner = jnp.array([0.0, 0.0])
        max_corner = jnp.array([10.0, 20.0])
        center = rect_center(min_corner, max_corner)
        assert jnp.allclose(center, jnp.array([5.0, 10.0]))

    def test_rect_area(self):
        """Test rectangle area calculation."""
        # rect_area takes width and height, not corners
        assert rect_area(5.0, 10.0) == 50.0

    def test_distance_to_rect_edge_inside(self):
        """Test distance to edge for point inside rectangle."""
        point = jnp.array([5.0, 5.0])
        min_corner = jnp.array([0.0, 0.0])
        max_corner = jnp.array([10.0, 10.0])
        d = distance_to_rect_edge(point, min_corner, max_corner)
        assert jnp.isclose(d, 5.0)  # Center of 10x10 box

    def test_distance_to_specific_edge(self):
        """Test distance to specific edges."""
        point = jnp.array([3.0, 7.0])
        min_corner = jnp.array([0.0, 0.0])
        max_corner = jnp.array([10.0, 10.0])

        assert jnp.isclose(distance_to_specific_edge(point, "LEFT", min_corner, max_corner), 3.0)
        assert jnp.isclose(distance_to_specific_edge(point, "RIGHT", min_corner, max_corner), 7.0)
        assert jnp.isclose(distance_to_specific_edge(point, "BOTTOM", min_corner, max_corner), 7.0)
        assert jnp.isclose(distance_to_specific_edge(point, "TOP", min_corner, max_corner), 3.0)


# =============================================================================
# Rotation Tests
# =============================================================================


class TestRotation:
    """Tests for rotation transforms."""

    def test_rotation_0_degrees(self):
        """Test 0° rotation (identity)."""
        point = jnp.array([1.0, 0.0])
        rot_onehot = rotation_index_to_onehot(0)
        rotated = rotate_point(point, rot_onehot)
        assert jnp.allclose(rotated, jnp.array([1.0, 0.0]), atol=1e-6)

    def test_rotation_90_degrees(self):
        """Test 90° CCW rotation."""
        point = jnp.array([1.0, 0.0])
        rot_onehot = rotation_index_to_onehot(1)
        rotated = rotate_point(point, rot_onehot)
        assert jnp.allclose(rotated, jnp.array([0.0, 1.0]), atol=1e-6)

    def test_rotation_180_degrees(self):
        """Test 180° rotation."""
        point = jnp.array([1.0, 0.0])
        rot_onehot = rotation_index_to_onehot(2)
        rotated = rotate_point(point, rot_onehot)
        assert jnp.allclose(rotated, jnp.array([-1.0, 0.0]), atol=1e-6)

    def test_rotation_270_degrees(self):
        """Test 270° CCW rotation."""
        point = jnp.array([1.0, 0.0])
        rot_onehot = rotation_index_to_onehot(3)
        rotated = rotate_point(point, rot_onehot)
        assert jnp.allclose(rotated, jnp.array([0.0, -1.0]), atol=1e-6)

    def test_rotation_around_center(self):
        """Test rotation around non-origin center."""
        point = jnp.array([2.0, 0.0])
        center = jnp.array([1.0, 0.0])
        rot_onehot = rotation_index_to_onehot(1)  # 90°
        rotated = rotate_point(point, rot_onehot, center)
        # Point is 1 unit right of center, after 90° CCW should be 1 unit above
        assert jnp.allclose(rotated, jnp.array([1.0, 1.0]), atol=1e-6)

    def test_rotation_matrix_orthogonal(self):
        """Verify rotation matrices are orthogonal (R @ R.T = I)."""
        for i in range(4):
            rot_onehot = rotation_index_to_onehot(i)
            R = get_rotation_matrix(rot_onehot)
            assert jnp.allclose(R @ R.T, jnp.eye(2), atol=1e-6)

    def test_onehot_encoding_roundtrip(self):
        """Test one-hot encoding roundtrip."""
        for i in range(4):
            onehot = rotation_index_to_onehot(i)
            degrees = onehot_to_rotation_degrees(onehot)
            expected = i * 90.0
            assert jnp.isclose(degrees, expected, atol=1e-6)

    def test_soft_rotation_gradient(self):
        """Test that soft rotation supports gradients."""

        def loss_fn(rot_logits):
            rot_soft = jax.nn.softmax(rot_logits)
            point = jnp.array([1.0, 0.0])
            rotated = rotate_point(point, rot_soft)
            # Loss: want y-coordinate to be high
            return -rotated[1]

        rot_logits = jnp.array([0.0, 1.0, 0.0, 0.0])  # Favor 90°
        grads = grad(loss_fn)(rot_logits)
        # Gradients should exist and not be NaN
        assert not jnp.any(jnp.isnan(grads))


# =============================================================================
# Gumbel-Softmax Tests
# =============================================================================


class TestGumbelSoftmax:
    """Tests for Gumbel-Softmax sampling functions."""

    def test_sample_rotation_is_one_hot(self):
        """Test that sample_rotation returns one-hot vectors."""
        key = jax.random.PRNGKey(42)
        logits = jnp.array([0.0, 2.0, 0.0, 0.0])  # Prefer 90°
        sample = sample_rotation(logits, key, temperature=1.0)
        # Should sum to 1 and be one-hot
        assert jnp.isclose(sample.sum(), 1.0)
        assert jnp.allclose(sample, jnp.round(sample))  # Is one-hot

    def test_sample_rotation_batch(self):
        """Test batch rotation sampling."""
        key = jax.random.PRNGKey(123)
        batch_logits = jnp.array(
            [
                [0.0, 2.0, 0.0, 0.0],  # Prefer 90°
                [2.0, 0.0, 0.0, 0.0],  # Prefer 0°
                [0.0, 0.0, 0.0, 2.0],  # Prefer 270°
            ]
        )
        samples = sample_rotation_batch(batch_logits, key, temperature=0.5)
        assert samples.shape == (3, 4)
        # Each row should sum to 1
        assert jnp.allclose(samples.sum(axis=1), jnp.ones(3))

    def test_gumbel_softmax_soft_mode(self):
        """Test soft Gumbel-Softmax returns soft probabilities."""
        key = jax.random.PRNGKey(0)
        logits = jnp.array([1.0, 1.0, 1.0, 1.0])  # Equal preference
        soft = gumbel_softmax(logits, key, temperature=5.0, hard=False)
        # Should sum to 1
        assert jnp.isclose(soft.sum(), 1.0)
        # Should NOT be one-hot (soft samples)
        assert not jnp.allclose(soft, jnp.round(soft))

    def test_temperature_effect(self):
        """Test that lower temperature produces sharper distributions."""
        key = jax.random.PRNGKey(0)
        logits = jnp.array([1.0, 1.0, 1.0, 1.0])

        soft_high = gumbel_softmax(logits, key, temperature=10.0, hard=False)
        soft_low = gumbel_softmax(logits, key, temperature=0.1, hard=False)

        # Lower temperature should have higher max value (sharper)
        assert soft_low.max() > soft_high.max()

    def test_gumbel_softmax_gradient_flow(self):
        """Test that gradients flow through Gumbel-Softmax."""

        def loss_fn(logits, key):
            rot = sample_rotation(logits, key, temperature=1.0)
            point = jnp.array([1.0, 0.0])
            rotated = rotate_point(point, rot)
            # Loss: want y-coordinate to be high (prefer 90° rotation)
            return -rotated[1]

        # Average over many keys to get a stable gradient signal.
        # Single samples are too noisy because rotations are stochastic.
        logits = jnp.array([0.0, 0.0, 0.0, 0.0])
        keys = jax.random.split(jax.random.PRNGKey(99), 100)
        per_key_grads = jnp.stack(
            [grad(loss_fn)(logits, k) for k in keys]
        )
        avg_grads = jnp.mean(per_key_grads, axis=0)

        # Gradients should exist and not be NaN
        assert not jnp.any(jnp.isnan(avg_grads))
        # Average gradient for 90° (index 1) should be most negative
        # (we want to increase logits[1] to decrease loss)
        assert jnp.argmin(avg_grads) == 1

    def test_gumbel_softmax_jit_compatible(self):
        """Test that Gumbel-Softmax works with JIT."""

        @jax.jit
        def jitted_sample(logits, key):
            return sample_rotation(logits, key, temperature=0.5)

        key = jax.random.PRNGKey(42)
        logits = jnp.array([0.0, 2.0, 0.0, 0.0])
        result = jitted_sample(logits, key)

        assert result.shape == (4,)
        assert jnp.isclose(result.sum(), 1.0)

    def test_gumbel_softmax_respects_logits(self):
        """Test that higher logits lead to more frequent selection."""
        key = jax.random.PRNGKey(0)
        # Strongly prefer 90° rotation
        logits = jnp.array([0.0, 10.0, 0.0, 0.0])

        # Sample many times and count
        counts = jnp.zeros(4)
        for _i in range(100):
            key, subkey = jax.random.split(key)
            sample = sample_rotation(logits, subkey, temperature=1.0)
            counts = counts + sample

        # Index 1 (90°) should be selected most often
        assert jnp.argmax(counts) == 1
        # Should be selected majority of the time
        assert counts[1] > 80  # At least 80% of samples

    def test_gumbel_softmax_very_low_temperature_no_overflow(self):
        """Test that very low temperatures don't cause NaN/Inf.

        At temperature=0.01, logits are divided by 0.01 (multiplied by 100).
        Combined with Gumbel noise (can reach ~15), values can reach ~1500.
        JAX softmax handles this via max subtraction, so should remain finite.
        """
        key = jax.random.PRNGKey(0)
        logits = jnp.array(
            [
                [0.0, 1.0, 0.0, 0.0],
                [2.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 3.0, 0.0],
            ]
        )

        # Test very low temperatures
        for temp in [0.1, 0.05, 0.01, 0.001]:
            samples = sample_rotation_batch(logits, key, temperature=temp)

            # All values should be finite
            assert jnp.all(jnp.isfinite(samples)), f"Non-finite at temp={temp}"
            # Should sum to 1 for each row
            assert jnp.allclose(samples.sum(axis=1), 1.0), f"Sum != 1 at temp={temp}"
            # Should be valid one-hot vectors (hard mode)
            assert jnp.allclose(samples, jnp.round(samples)), f"Not one-hot at temp={temp}"

    def test_gumbel_softmax_gradient_at_low_temperature(self):
        """Test gradient behavior at low temperatures.

        Gradients should remain finite (though they may be zero/tiny
        due to softmax saturation at very low temperatures).
        """

        def loss_fn(logits, key, temp):
            rot = sample_rotation(logits, key, temperature=temp)
            point = jnp.array([1.0, 0.0])
            rotated = rotate_point(point, rot)
            return -rotated[1]

        key = jax.random.PRNGKey(42)
        logits = jnp.array([0.0, 1.0, 0.0, 0.0])

        for temp in [1.0, 0.5, 0.1, 0.05]:
            grads = grad(loss_fn)(logits, key, temp)
            # Gradients should be finite (may be zero at very low temp)
            assert jnp.all(jnp.isfinite(grads)), f"Non-finite grad at temp={temp}"


# =============================================================================
# SDF Tests
# =============================================================================


class TestSDF:
    """Tests for Signed Distance Functions."""

    def test_sdf_circle_inside(self):
        """Test SDF is negative inside circle."""
        center = jnp.array([0.0, 0.0])
        point = jnp.array([0.3, 0.0])
        d = sdf_circle(point, center, 1.0)
        assert d < 0  # Inside is negative

    def test_sdf_circle_outside(self):
        """Test SDF is positive outside circle."""
        center = jnp.array([0.0, 0.0])
        point = jnp.array([2.0, 0.0])
        d = sdf_circle(point, center, 1.0)
        assert d > 0  # Outside is positive

    def test_sdf_circle_boundary(self):
        """Test SDF is zero on circle boundary."""
        center = jnp.array([0.0, 0.0])
        point = jnp.array([1.0, 0.0])
        d = sdf_circle(point, center, 1.0)
        assert jnp.isclose(d, 0.0, atol=1e-6)

    def test_sdf_circle_distance_correct(self):
        """Test SDF returns correct distance values."""
        center = jnp.array([0.0, 0.0])
        point = jnp.array([3.0, 0.0])
        d = sdf_circle(point, center, 1.0)
        assert jnp.isclose(d, 2.0)  # 3 - 1 = 2

    def test_sdf_rectangle_inside(self):
        """Test rectangle SDF is negative inside."""
        center = jnp.array([0.0, 0.0])
        point = jnp.array([0.5, 0.5])
        # sdf_rectangle takes point, center, width, height
        d = sdf_rectangle(point, center, 4.0, 2.0)  # 4x2 rectangle (half-sizes 2x1)
        assert d < 0

    def test_sdf_rectangle_outside(self):
        """Test rectangle SDF is positive outside."""
        center = jnp.array([0.0, 0.0])
        point = jnp.array([5.0, 0.0])
        d = sdf_rectangle(point, center, 4.0, 2.0)  # 4x2 rectangle
        assert d > 0

    def test_sdf_rectangle_boundary(self):
        """Test rectangle SDF is zero on boundary."""
        center = jnp.array([0.0, 0.0])
        point = jnp.array([2.0, 0.0])  # On right edge of 4-wide rectangle
        d = sdf_rectangle(point, center, 4.0, 2.0)
        assert jnp.isclose(d, 0.0, atol=1e-4)  # Relaxed tolerance for numerical precision

    def test_sdf_union(self):
        """Test SDF union (min of two SDFs)."""
        jnp.array([0.0, 0.0])
        # Point between two circles
        point = jnp.array([1.5, 0.0])
        d1 = sdf_circle(point, jnp.array([0.0, 0.0]), 1.0)
        d2 = sdf_circle(point, jnp.array([3.0, 0.0]), 1.0)
        d_union = sdf_union(d1, d2)
        assert jnp.isclose(d_union, min(d1, d2))

    def test_sdf_intersection(self):
        """Test SDF intersection (max of two SDFs)."""
        jnp.array([0.0, 0.0])
        point = jnp.array([0.0, 0.0])
        d1 = sdf_circle(point, jnp.array([-0.5, 0.0]), 1.0)
        d2 = sdf_circle(point, jnp.array([0.5, 0.0]), 1.0)
        d_intersection = sdf_intersection(d1, d2)
        # Point is inside both circles, intersection should be negative
        assert d_intersection < 0

    def test_sdf_gradient(self):
        """Test that SDF supports gradients."""

        def loss_fn(point):
            center = jnp.array([0.0, 0.0])
            return sdf_circle(point, center, 1.0)

        point = jnp.array([2.0, 0.0])
        grads = grad(loss_fn)(point)
        # Gradient should point away from center (outward normal)
        assert grads[0] > 0  # x-gradient positive (pointing away)
        assert jnp.isclose(grads[1], 0.0, atol=1e-6)  # y-gradient ~0


# =============================================================================
# Smooth Function Tests
# =============================================================================


class TestSmoothFunctions:
    """Tests for smooth (differentiable) approximations."""

    def test_smooth_min_approximation(self):
        """Test smooth_min approximates min."""
        x = jnp.array([1.0, 5.0, 3.0, 2.0])
        # With high alpha, should be close to true min
        s_min = smooth_min(x, alpha=100.0)
        assert jnp.isclose(s_min, 1.0, atol=0.1)

    def test_smooth_max_approximation(self):
        """Test smooth_max approximates max."""
        x = jnp.array([1.0, 5.0, 3.0, 2.0])
        # With high alpha, should be close to true max
        s_max = smooth_max(x, alpha=100.0)
        assert jnp.isclose(s_max, 5.0, atol=0.1)

    def test_smooth_min_pair(self):
        """Test pairwise smooth min."""
        a = jnp.array(3.0)
        b = jnp.array(7.0)
        result = smooth_min_pair(a, b, alpha=100.0)
        assert jnp.isclose(result, 3.0, atol=0.1)

    def test_smooth_max_pair(self):
        """Test pairwise smooth max."""
        a = jnp.array(3.0)
        b = jnp.array(7.0)
        result = smooth_max_pair(a, b, alpha=100.0)
        assert jnp.isclose(result, 7.0, atol=0.1)

    def test_smooth_relu(self):
        """Test smooth ReLU approximation."""
        # smooth_relu uses beta parameter, not alpha
        # Positive value should pass through
        assert smooth_relu(jnp.array(5.0), beta=10.0) > 4.9
        # Negative value should be near zero
        assert smooth_relu(jnp.array(-5.0), beta=10.0) < 0.1

    def test_smooth_abs(self):
        """Test smooth absolute value."""
        # smooth_abs uses beta parameter, not alpha
        # Should return approximate absolute value
        assert jnp.isclose(smooth_abs(jnp.array(5.0), beta=10.0), 5.0, atol=0.1)
        assert jnp.isclose(smooth_abs(jnp.array(-5.0), beta=10.0), 5.0, atol=0.1)

    def test_hpwl_smooth(self):
        """Test Half-Perimeter Wirelength calculation."""
        # Points forming a 4x3 rectangle
        points = jnp.array([[0.0, 0.0], [4.0, 0.0], [4.0, 3.0], [0.0, 3.0]])
        hpwl = hpwl_smooth(points, alpha=100.0)
        # HPWL = (max_x - min_x) + (max_y - min_y) = 4 + 3 = 7
        assert jnp.isclose(hpwl, 7.0, atol=0.2)

    def test_smooth_functions_gradient(self):
        """Test that smooth functions support gradients."""

        def loss_fn(x):
            return smooth_min(x, alpha=10.0)

        x = jnp.array([1.0, 2.0, 3.0])
        grads = grad(loss_fn)(x)
        # Gradients should exist and not be NaN
        assert not jnp.any(jnp.isnan(grads))
        # Gradient should be highest for the minimum element
        assert grads[0] > grads[1] > grads[2]


# =============================================================================
# Overlap Detection Tests
# =============================================================================


class TestOverlap:
    """Tests for overlap detection functions."""

    def test_boxes_overlapping(self):
        """Test overlap detection for overlapping boxes."""
        # Box 1: center (0,0), size 4x4
        c1 = jnp.array([0.0, 0.0])
        r1 = rotation_index_to_onehot(0)

        # Box 2: center (2,2), size 4x4 (overlaps with box 1)
        c2 = jnp.array([2.0, 2.0])
        r2 = rotation_index_to_onehot(0)

        # component_overlap_amount(pos1, rot1, w1, h1, pos2, rot2, w2, h2)
        overlap = component_overlap_amount(c1, r1, 4.0, 4.0, c2, r2, 4.0, 4.0)
        assert overlap > 0  # Should detect overlap

    def test_boxes_separated(self):
        """Test overlap detection for separated boxes."""
        # Box 1: center (0,0), size 2x2
        c1 = jnp.array([0.0, 0.0])
        r1 = rotation_index_to_onehot(0)

        # Box 2: center (10,10), size 2x2 (far from box 1)
        c2 = jnp.array([10.0, 10.0])
        r2 = rotation_index_to_onehot(0)

        overlap = component_overlap_amount(c1, r1, 2.0, 2.0, c2, r2, 2.0, 2.0)
        # Smooth overlap functions may return tiny positive values near zero
        assert overlap < 0.01  # No significant overlap

    def test_clearance_violation(self):
        """Test clearance violation detection."""
        # Box 1: center (0,0), size 2x2
        c1 = jnp.array([0.0, 0.0])
        r1 = rotation_index_to_onehot(0)

        # Box 2: center (3,0), size 2x2 (gap of 1mm)
        c2 = jnp.array([3.0, 0.0])
        r2 = rotation_index_to_onehot(0)

        # check_clearance_violation(pos1, rot1, w1, h1, pos2, rot2, w2, h2, min_clearance)
        # With required clearance of 0.5mm - should pass (gap is 1mm)
        violation = check_clearance_violation(c1, r1, 2.0, 2.0, c2, r2, 2.0, 2.0, 0.5)
        # Smooth functions may have small numerical errors
        assert violation < 0.01  # No significant violation

        # With required clearance of 2mm - should fail
        violation = check_clearance_violation(c1, r1, 2.0, 2.0, c2, r2, 2.0, 2.0, 2.0)
        assert violation > 0

    def test_box_distance_gradient(self):
        """Test that box distance functions support gradients."""

        def loss_fn(c2):
            c1 = jnp.array([0.0, 0.0])
            r1 = rotation_index_to_onehot(0)
            r2 = rotation_index_to_onehot(0)
            # Use box_box_distance which computes signed distance
            return box_box_distance(c1, r1, 2.0, 2.0, c2, r2, 2.0, 2.0)

        c2 = jnp.array([1.0, 1.0])  # Overlapping position
        grads = grad(loss_fn)(c2)
        # Gradients should exist and not be NaN
        assert not jnp.any(jnp.isnan(grads))


# =============================================================================
# Polygon Tests
# =============================================================================


class TestPolygon:
    """Tests for polygon operations."""

    def test_square_area(self):
        """Test area of unit square."""
        square = jnp.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
        assert jnp.isclose(polygon_area(square), 1.0)

    def test_rectangle_area(self):
        """Test area of 3x4 rectangle."""
        rect = jnp.array([[0.0, 0.0], [4.0, 0.0], [4.0, 3.0], [0.0, 3.0]])
        assert jnp.isclose(polygon_area(rect), 12.0)

    def test_triangle_area(self):
        """Test area of right triangle."""
        triangle = jnp.array([[0.0, 0.0], [4.0, 0.0], [0.0, 3.0]])
        assert jnp.isclose(polygon_area(triangle), 6.0)  # 0.5 * 4 * 3

    def test_polygon_centroid(self):
        """Test centroid of square."""
        square = jnp.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])
        centroid = polygon_centroid(square)
        assert jnp.allclose(centroid, jnp.array([1.0, 1.0]), atol=1e-6)

    def test_polygon_perimeter(self):
        """Test perimeter of unit square."""
        square = jnp.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
        assert jnp.isclose(polygon_perimeter(square), 4.0)

    def test_point_in_polygon_inside(self):
        """Test point inside polygon."""
        square = jnp.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])
        point = jnp.array([1.0, 1.0])
        inside = point_in_polygon_soft(point, square)
        assert inside > 0.9  # Should be close to 1

    def test_point_in_polygon_outside(self):
        """Test point outside polygon."""
        square = jnp.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])
        point = jnp.array([5.0, 5.0])
        inside = point_in_polygon_soft(point, square)
        assert inside < 0.1  # Should be close to 0

    def test_winding_number_inside(self):
        """Test winding number for point inside."""
        square = jnp.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])
        point = jnp.array([1.0, 1.0])
        winding = point_in_polygon_winding(point, square)
        assert jnp.abs(winding) >= 0.9  # Non-zero winding number

    def test_rotate_polygon(self):
        """Test polygon rotation preserves area."""
        square = jnp.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
        rotated = rotate_polygon(square, jnp.pi / 4)  # 45 degrees
        # Area should be preserved
        assert jnp.isclose(polygon_area(rotated), polygon_area(square), atol=1e-6)

    def test_scale_polygon(self):
        """Test polygon scaling."""
        square = jnp.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
        scaled = scale_polygon(square, 2.0)
        # Area should increase by factor of 4
        assert jnp.isclose(polygon_area(scaled), 4.0 * polygon_area(square), atol=1e-6)

    def test_polygon_area_gradient(self):
        """Test that polygon area supports gradients."""

        def loss_fn(vertices):
            return polygon_area(vertices)

        square = jnp.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
        grads = grad(loss_fn)(square)
        # Gradients should exist and not be NaN
        assert not jnp.any(jnp.isnan(grads))


# =============================================================================
# JAX Compatibility Tests
# =============================================================================


class TestJAXCompatibility:
    """Tests to ensure JAX jit and grad compatibility."""

    def test_jit_primitives(self):
        """Test JIT compilation of primitive functions."""

        @jax.jit
        def fn(p1, p2):
            return point_distance(p1, p2)

        p1 = jnp.array([0.0, 0.0])
        p2 = jnp.array([3.0, 4.0])
        assert jnp.isclose(fn(p1, p2), 5.0)

    def test_jit_rotation(self):
        """Test JIT compilation of rotation."""

        @jax.jit
        def fn(point, rot_idx):
            rot = rotation_index_to_onehot(rot_idx)
            return rotate_point(point, rot)

        point = jnp.array([1.0, 0.0])
        result = fn(point, 1)
        assert jnp.allclose(result, jnp.array([0.0, 1.0]), atol=1e-6)

    def test_jit_sdf(self):
        """Test JIT compilation of SDF."""

        @jax.jit
        def fn(point):
            center = jnp.array([0.0, 0.0])
            return sdf_circle(point, center, 1.0)

        point = jnp.array([2.0, 0.0])
        assert jnp.isclose(fn(point), 1.0)

    def test_vmap_compatibility(self):
        """Test that functions work with vmap."""

        @jax.vmap
        def batch_fn(point):
            center = jnp.array([0.0, 0.0])
            return sdf_circle(point, center, 1.0)

        points = jnp.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
        results = batch_fn(points)
        expected = jnp.array([-1.0, 0.0, 1.0])
        assert jnp.allclose(results, expected, atol=1e-6)

    def test_grad_composition(self):
        """Test gradient through composed operations."""

        def loss_fn(center):
            point = jnp.array([2.0, 0.0])
            d = sdf_circle(point, center, 1.0)
            return smooth_relu(d, beta=10.0)  # Use beta, not alpha

        center = jnp.array([0.0, 0.0])
        grads = grad(loss_fn)(center)
        # Gradient should point towards the point (to reduce distance)
        assert grads[0] < 0  # Should move center towards point
