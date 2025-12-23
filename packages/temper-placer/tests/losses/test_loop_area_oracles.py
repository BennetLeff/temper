import jax
import jax.numpy as jnp
import pytest
from temper_placer.losses.loop_area import (
    LoopAreaLoss,
    compute_loop_area_penalty,
    validate_loop_ordering,
)

def test_rectangle_area_oracle():
    """Rectangle area = width * height."""
    width = 20.0
    height = 10.0
    # Correct CW order
    pins = jnp.array([
        [0.0, 0.0],
        [width, 0.0],
        [width, height],
        [0.0, height]
    ])
    
    # We want to check the actual area, not the penalty.
    # LoopAreaLoss._compute_single_loop_area is private, but we can test via compute_loop_area_penalty
    # by setting max_area to 0 and scale to 1.0, and then taking sqrt.
    # Actually, compute_loop_area_penalty returns violation**2 * scale.
    
    max_area = 0.0
    scale = 1.0
    penalty = compute_loop_area_penalty(pins, max_area=max_area, scale=scale)
    computed_area = jnp.sqrt(penalty / scale)
    
    assert float(computed_area) == pytest.approx(width * height)

def test_triangle_area_oracle():
    """Triangle area = 0.5 * base * height."""
    base = 15.0
    height = 8.0
    # Triangle (0,0), (base, 0), (base/2, height)
    pins = jnp.array([
        [0.0, 0.0],
        [base, 0.0],
        [base / 2.0, height]
    ])
    
    max_area = 0.0
    scale = 1.0
    penalty = compute_loop_area_penalty(pins, max_area=max_area, scale=scale)
    computed_area = jnp.sqrt(penalty / scale)
    
    assert float(computed_area) == pytest.approx(0.5 * base * height)

def test_area_cyclic_permutation_invariance():
    """Area invariant to starting vertex (cyclic permutation)."""
    pins = jnp.array([
        [0.0, 0.0],
        [20.0, 0.0],
        [20.0, 10.0],
        [0.0, 10.0]
    ])
    
    max_area = 0.0
    scale = 1.0
    
    areas = []
    for i in range(len(pins)):
        permuted_pins = jnp.roll(pins, i, axis=0)
        penalty = compute_loop_area_penalty(permuted_pins, max_area=max_area, scale=scale)
        areas.append(float(jnp.sqrt(penalty / scale)))
    
    for area in areas:
        assert area == pytest.approx(areas[0])

def test_self_intersecting_polygon_detection():
    """Self-intersecting polygon detection (figure-8)."""
    # Figure-8: (0,0), (10,10), (10,0), (0,10)
    # This crosses itself at (5,5). 
    # It forms two triangles: (0,0)-(5,5)-(0,10) and (10,10)-(5,5)-(10,0)
    # Each triangle has area 0.5 * 10 * 5 = 25.
    # Algebraic area is sum of signed areas. One will be +25, other -25 -> total 0?
    pins = jnp.array([
        [0.0, 0.0],
        [10.0, 10.0],
        [10.0, 0.0],
        [0.0, 10.0]
    ])
    
    # validate_loop_ordering should catch this
    warnings = validate_loop_ordering(pins, "self_intersecting")
    assert any("much smaller than convex hull" in w for w in warnings)
    
    # Check the computed area (shoelace)
    # (0*10 - 10*0) + (10*0 - 10*10) + (10*10 - 0*0) + (0*0 - 0*10) = 0 + (-100) + 100 + 0 = 0
    max_area = 0.0
    scale = 1.0
    penalty = compute_loop_area_penalty(pins, max_area=max_area, scale=scale)
    computed_area = float(jnp.sqrt(penalty / scale))
    assert computed_area == pytest.approx(0.0, abs=1e-6)

def test_pin_shuffling_detection():
    """Shuffled pins should be detected as invalid orderings."""
    # Correct order: square (0,0), (10,0), (10,10), (0,10)
    pins = jnp.array([
        [0.0, 0.0],
        [10.0, 0.0],
        [10.0, 10.0],
        [0.0, 10.0]
    ])
    
    # Correct ordering should have no warnings (or at least no 'self-intersecting' ones)
    warnings_correct = validate_loop_ordering(pins, "correct")
    assert not any("much smaller than convex hull" in w for w in warnings_correct)
    
    # Shuffled: (0,0), (10,10), (10,0), (0,10) - this is the figure-8
    pins_shuffled = jnp.array([
        [0.0, 0.0],
        [10.0, 10.0],
        [10.0, 0.0],
        [0.0, 10.0]
    ])
    warnings_shuffled = validate_loop_ordering(pins_shuffled, "shuffled")
    assert any("much smaller than convex hull" in w for w in warnings_shuffled)

def test_area_gradient_correctness():
    """Gradient of area w.r.t pin position is correct."""
    def area_fn(p):
        # We need a function that returns the area itself
        vertices_next = jnp.roll(p, -1, axis=0)
        cross = p[:, 0] * vertices_next[:, 1] - vertices_next[:, 0] * p[:, 1]
        return jnp.abs(jnp.sum(cross) / 2.0)
    
    pins = jnp.array([
        [0.0, 0.0],
        [20.0, 0.0],
        [20.0, 10.0],
        [0.0, 10.0]
    ])
    
    grad_fn = jax.grad(area_fn)
    grads = grad_fn(pins)
    
    # For a rectangle at origin (0,0) to (W, H):
    # Pin 0: (0,0). Changing x0 affects x0*y1 - x1*y0. 
    # Since y0=0, x0*y1 is the only part. dArea/dx0 = 0.5 * y1 = 0.5 * 0 = 0.
    # Wait, let's look at shoelace more carefully.
    # 2*Area = |(x0*y1 - x1*y0) + (x1*y2 - x2*y1) + (x2*y3 - x3*y2) + (x3*y0 - x0*y3)|
    # d(2*Area)/dx0 = y1 - y3
    # d(2*Area)/dy0 = x3 - x1
    
    # For our pins: (0,0), (20,0), (20,10), (0,10)
    # d(2*Area)/dx0 = y1 - y3 = 0 - 10 = -10. So dArea/dx0 = -5.
    # d(2*Area)/dy0 = x3 - x1 = 0 - 20 = -20. So dArea/dy0 = -10.
    
    expected_grad0 = jnp.array([-5.0, -10.0])
    assert jnp.allclose(grads[0], expected_grad0)
    
    # Pin 1: (20,0)
    # d(2*Area)/dx1 = y2 - y0 = 10 - 0 = 10. dArea/dx1 = 5.
    # d(2*Area)/dy1 = x0 - x2 = 0 - 20 = -20. dArea/dy1 = -10.
    expected_grad1 = jnp.array([5.0, -10.0])
    assert jnp.allclose(grads[1], expected_grad1)

def test_loop_area_loss_vectorized_oracles():
    """Test LoopAreaLoss class with simple oracles in context."""
    from temper_placer.losses.base import LossContext, LoopConstraint
    
    # 2 components, each with 2 pins
    # Loop 1: Rectangle using 4 pins from these components
    # We'll just mock the context to make it easier
    
    positions = jnp.array([
        [0.0, 0.0],   # Comp 0
        [20.0, 10.0]  # Comp 1
    ])
    # No rotations
    rotations = jnp.zeros((2, 4))
    rotations = rotations.at[:, 0].set(1.0)
    
    # Loop 1: (Comp 0, Pin A), (Comp 1, Pin A), (Comp 1, Pin B), (Comp 0, Pin B)
    # Define pin offsets to form a 10x10 square
    # Comp 0: Pin A at (-5, -5), Pin B at (-5, 5)
    # Comp 1: Pin A at (5, -5), Pin B at (5, 5)
    # Total square: (-5,-5), (25, 5), (25, 15), (-5, 15) -> 30x20 rectangle
    
    # Actually, let's keep it simple.
    # Comp 0 center (0,0), Pin A (0,0), Pin B (0,10)
    # Comp 1 center (20,0), Pin A (20,0), Pin B (20,10)
    # Loop: (0,0), (20,0), (20,10), (0,10)
    
    loop_constraints = [
        LoopConstraint(name="test_loop", pins=[("C0", "PA"), ("C1", "PA"), ("C1", "PB"), ("C0", "PB")], max_area=100.0, weight=1.0)
    ]
    
    # Mocking the pre-computed arrays that would be in LossContext
    loop_pin_indices = jnp.array([[0, 1, 1, 0]]) # (L, Q)
    loop_pin_offsets = jnp.array([[[0, 0], [0, 0], [0, 10], [0, 10]]], dtype=jnp.float32) # (L, Q, 2)
    loop_pin_mask = jnp.array([[True, True, True, True]])
    loop_max_areas = jnp.array([100.0])
    loop_weights = jnp.array([1.0])
    
    class MockContext(LossContext):
        def __init__(self):
            self.loop_pin_indices = loop_pin_indices
            self.loop_pin_offsets = loop_pin_offsets
            self.loop_pin_mask = loop_pin_mask
            self.loop_max_areas = loop_max_areas
            self.loop_weights = loop_weights
            self.loop_constraints = loop_constraints
            self.component_names = ["C0", "C1"]
            self.pin_map = {} # Not used by LoopAreaLoss directly
    
    context = MockContext()
    loss_fn = LoopAreaLoss(area_penalty_scale=1.0)
    
    # Expected area = 20 * 10 = 200.
    # Violation = 200 - 100 = 100.
    # Penalty = weight * violation^2 * scale = 1.0 * 100^2 * 1.0 = 10000.
    
    # Weight schedule: LoopAreaLoss returns 0 if progress < 0.4
    # Set epoch so progress > 0.6
    result = loss_fn(positions, rotations, context, epoch=70, total_epochs=100)
    
    assert float(result.value) == pytest.approx(10000.0)
    assert result.breakdown["test_loop"] == pytest.approx(200.0)
