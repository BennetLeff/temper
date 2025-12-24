import jax
import jax.numpy as jnp
import pytest

from temper_placer.geometry.overlap import box_box_distance
from temper_placer.geometry.sdf import sdf_circle, sdf_rectangle
from temper_placer.geometry.smooth import smooth_max
from temper_placer.geometry.transform import get_rotated_bounds

# =============================================================================
# temper-t76y.1: AABB overlap: Conservative bounds oracles
# =============================================================================

def test_rotated_bounds_oracle():
    """Rotated bounds >= unrotated bounds (always)."""
    width, height = 10.0, 5.0

    # Test all 4 discrete rotations
    for i in range(4):
        rot = jnp.eye(4)[i]
        rw, rh = get_rotated_bounds(width, height, rot)

        # In discrete case, it's either (10,5) or (5,10)
        assert rw >= min(width, height)
        assert rh >= min(width, height)
        assert (rw == width and rh == height) or (rw == height and rh == width)

    # Test soft rotation (e.g., 0.5 * 0deg + 0.5 * 90deg)
    # This should be a "blended" bound
    soft_rot = jnp.array([0.5, 0.5, 0.0, 0.0])
    rw, rh = get_rotated_bounds(width, height, soft_rot)
    # width * 0.5 + height * 0.5 = 7.5
    assert float(rw) == pytest.approx(7.5)
    assert float(rh) == pytest.approx(7.5)

def test_aabb_overlap_oracle():
    """Overlap detected when rectangles truly overlap."""
    # Two 10x10 squares
    w, h = 10.0, 10.0
    rot = jnp.array([1.0, 0.0, 0.0, 0.0])

    # Overlapping
    pos1 = jnp.array([0.0, 0.0])
    pos2 = jnp.array([5.0, 0.0])
    dist = box_box_distance(pos1, rot, w, h, pos2, rot, w, h)
    assert float(dist) < 0  # Negative distance means overlap

    # Touching
    pos3 = jnp.array([10.0, 0.0])
    dist_touch = box_box_distance(pos1, rot, w, h, pos3, rot, w, h)
    assert float(dist_touch) == pytest.approx(0.0, abs=1e-6)

    # Separated
    pos4 = jnp.array([15.0, 0.0])
    dist_sep = box_box_distance(pos1, rot, w, h, pos4, rot, w, h)
    assert float(dist_sep) == pytest.approx(5.0)

def test_distance_symmetry_oracle():
    """Distance symmetric: d(A,B) == d(B,A)."""
    pos1 = jnp.array([1.2, 3.4])
    pos2 = jnp.array([10.5, -2.1])
    rot1 = jnp.array([0.0, 1.0, 0.0, 0.0])
    rot2 = jnp.array([0.0, 0.0, 1.0, 0.0])
    w1, h1 = 8.0, 4.0
    w2, h2 = 2.0, 12.0

    d12 = box_box_distance(pos1, rot1, w1, h1, pos2, rot2, w2, h2)
    d21 = box_box_distance(pos2, rot2, w2, h2, pos1, rot1, w1, h1)

    assert float(d12) == pytest.approx(float(d21))

# =============================================================================
# temper-t76y.2: Smooth approximations: Max/min oracles
# =============================================================================

def test_smooth_max_oracle():
    """smooth_max >= true_max (always) and error bounds."""
    x = jnp.array([1.0, 5.0, 2.0, 4.0])
    true_max = 5.0

    # alpha=1.0 (very smooth)
    s_max_low = smooth_max(x, alpha=1.0)
    assert float(s_max_low) > true_max

    # alpha=10.0 (sharper)
    s_max_high = smooth_max(x, alpha=10.0)
    assert float(s_max_high) > true_max
    assert float(s_max_high) < float(s_max_low)

    # As alpha increases, it should approach true_max
    s_max_very_high = smooth_max(x, alpha=100.0)
    assert float(s_max_very_high) == pytest.approx(true_max, rel=1e-3)

def test_smooth_max_gradient_oracle():
    """Gradient is bounded and continuous."""
    def func(val):
        x = jnp.array([1.0, val])
        return smooth_max(x, alpha=10.0)

    grad_fn = jax.grad(func)

    # Test gradients at different points
    # When val is far below 1.0, grad should be near 0
    g_low = grad_fn(-10.0)
    assert abs(g_low) < 1e-3

    # When val is exactly 1.0, grad should be 0.5 (balanced)
    g_mid = grad_fn(1.0)
    assert float(g_mid) == pytest.approx(0.5)

    # When val is far above 1.0, grad should be near 1
    g_high = grad_fn(10.0)
    assert float(g_high) == pytest.approx(1.0)

    # Check continuity: no big jumps
    vals = jnp.linspace(0.0, 2.0, 100)
    grads = jax.vmap(grad_fn)(vals)
    max_diff = jnp.max(jnp.abs(jnp.diff(grads)))
    assert max_diff < 0.1

# =============================================================================
# temper-t76y.3: SDF collision: Signed distance oracles
# =============================================================================

def test_sdf_circle_oracle():
    """SDF negative inside, zero at boundary, gradient points away."""
    center = jnp.array([10.0, 10.0])
    radius = 5.0

    # Inside
    assert sdf_circle(jnp.array([10.0, 10.0]), center, radius) == pytest.approx(-5.0)
    assert sdf_circle(jnp.array([13.0, 10.0]), center, radius) == pytest.approx(-2.0)

    # Boundary
    assert sdf_circle(jnp.array([15.0, 10.0]), center, radius) == pytest.approx(0.0)

    # Outside
    assert sdf_circle(jnp.array([20.0, 10.0]), center, radius) == pytest.approx(5.0)

    # Gradient
    grad_fn = jax.grad(lambda p: sdf_circle(p, center, radius))
    g = grad_fn(jnp.array([20.0, 10.0]))
    # Normal at [20, 10] for circle at [10, 10] is [1, 0]
    assert jnp.allclose(g, jnp.array([1.0, 0.0]))

def test_sdf_rectangle_oracle():
    """SDF rectangle signed distance and boundary."""
    center = jnp.array([0.0, 0.0])
    width, height = 10.0, 10.0 # 5x5 half-extents

    # Inside
    assert sdf_rectangle(jnp.array([0.0, 0.0]), center, width, height) == pytest.approx(-5.0)

    # Boundary
    assert sdf_rectangle(jnp.array([5.0, 0.0]), center, width, height) == pytest.approx(0.0, abs=1e-4)
    assert sdf_rectangle(jnp.array([0.0, 5.0]), center, width, height) == pytest.approx(0.0, abs=1e-4)

    # Outside (face)
    assert sdf_rectangle(jnp.array([7.0, 0.0]), center, width, height) == pytest.approx(2.0)

    # Outside (corner)
    # dist to [5, 5] from [8, 9] is sqrt(3^2 + 4^2) = 5
    dist_corner = sdf_rectangle(jnp.array([8.0, 9.0]), center, width, height)
    assert float(dist_corner) == pytest.approx(5.0)

# =============================================================================
# temper-t76y.4: Geometry: AABB approximation error bounds
# =============================================================================

def test_aabb_over_approximation_bounds():
    """Quantify AABB over-approximation for rotated components."""
    # 1mm x 100mm box
    w, h = 1.0, 100.0
    # Rotate 45 degrees
    # 45 deg is not a valid discrete rotation for components,
    # but the transform code handles it if we pass soft one-hots.
    # [cos(45), sin(45)] = [0.707, 0.707]
    # We can't easily represent 45 deg with 4-way one-hots unless we use custom rot matrix.

    # Let's test with 90 deg instead - it should be exact swap
    rot_90 = jnp.array([0.0, 1.0, 0.0, 0.0])
    rw, rh = get_rotated_bounds(w, h, rot_90)
    assert float(rw) == 100.0
    assert float(rh) == 1.0

    # Test a "soft" 45 deg (even distribution between 0 and 90)
    rot_45 = jnp.array([0.5, 0.5, 0.0, 0.0])
    rw, rh = get_rotated_bounds(w, h, rot_45)
    # Expected: 0.5 * 1 + 0.5 * 100 = 50.5
    assert float(rw) == 50.5
    assert float(rh) == 50.5

# =============================================================================
# temper-t76y.5: Geometry: Smooth function gradient behavior at extremes
# =============================================================================

def test_smooth_function_extremes():
    """Test smooth functions at extreme values for numerical stability."""
    from temper_placer.geometry.smooth import smooth_relu

    # 1. smooth_relu at extremes
    # x = -100
    assert float(jax.grad(smooth_relu)(-100.0)) == pytest.approx(0.0, abs=1e-6)
    # x = +100
    assert float(jax.grad(smooth_relu)(100.0)) == pytest.approx(1.0, abs=1e-6)

    # 2. smooth_max no overflow (already tested in test_losses.py, but re-verifying)
    # alpha=10, x=100 -> exp(1000) would overflow.
    # JAX logsumexp uses subtraction of max for stability.
    x_large = jnp.array([100.0, 101.0])
    res = smooth_max(x_large, alpha=10.0)
    assert jnp.isfinite(res)
    assert float(res) >= 101.0

# =============================================================================
# temper-t76y.6: Geometry: Overlap distance at zero separation
# =============================================================================

def test_overlap_distance_zero_separation():
    """Test overlap_distance when components are identical or touching."""
    # Two identical components
    pos = jnp.array([50.0, 50.0])
    rot = jnp.array([1.0, 0.0, 0.0, 0.0])
    w, h = 10.0, 10.0

    dist = box_box_distance(pos, rot, w, h, pos, rot, w, h)
    # Identical position -> max possible overlap.
    # Gap_x = 0 - (5+5) = -10. Gap_y = -10.
    # Distance = -10.
    assert float(dist) == pytest.approx(-10.0)

    # Touching
    pos2 = jnp.array([60.0, 50.0])
    dist_touch = box_box_distance(pos, rot, w, h, pos2, rot, w, h)
    assert float(dist_touch) == pytest.approx(0.0, abs=1e-6)

    # Gradient at touching
    def total_dist(p):
        return box_box_distance(pos, rot, w, h, p, rot, w, h)

    grad_fn = jax.grad(total_dist)
    g = grad_fn(pos2)
    # Pushing pos2 away from pos (pos is (50,50), pos2 is (60,50))
    # Increasing pos2[0] increases distance. So grad should be [1, 0]
    assert g[0] > 0
    assert g[1] == 0
    assert jnp.all(jnp.isfinite(g))
