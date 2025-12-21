
import jax.numpy as jnp
import pytest
from temper_placer.losses.aesthetic import PortFacingRotationLoss
from temper_placer.losses.base import LossContext, LossResult

@pytest.fixture
def mock_context():
    # Minimal mock context
    return None 

def test_port_facing_rotation_aligned():
    """Test that aligned pins have zero loss."""
    # Group: Component 0
    # Target: Component 1
    # Pin offset: (1, 0) relative to comp 0
    # Comp 0 at (0, 0), Comp 1 at (10, 0)
    
    positions = jnp.array([
        [0.0, 0.0],   # Comp 0
        [10.0, 0.0]   # Comp 1 (Target)
    ])
    
    # Rotations: Comp 0 is 0 degrees (aligned)
    rotations = jnp.array([
        [1.0, 0.0, 0.0, 0.0], # Comp 0: 0 deg
        [1.0, 0.0, 0.0, 0.0]  # Comp 1: 0 deg
    ])
    
    loss_fn = PortFacingRotationLoss(
        group_indices=jnp.array([[0]]),
        primary_pin_offsets=jnp.array([[1.0, 0.0]]),
        target_indices=jnp.array([[1]])
    )
    
    result = loss_fn(positions, rotations, None)
    
    # Cosine sim should be 1.0, so penalty 0.0
    assert result.value < 1e-4

def test_port_facing_rotation_opposite():
    """Test that opposite pins have high loss."""
    # Comp 0 at (0, 0), Comp 1 at (10, 0)
    positions = jnp.array([
        [0.0, 0.0],
        [10.0, 0.0]
    ])
    
    # Rotations: Comp 0 is 180 degrees (opposite)
    # 180 deg -> pin (1,0) becomes (-1, 0)
    # Vector to target is (10, 0).
    # Pin vector is (-1, 0).
    # Cosine sim is -1.0. Penalty 1.0 - (-1.0) = 2.0
    
    rotations = jnp.array([
        [0.0, 0.0, 1.0, 0.0], # Comp 0: 180 deg
        [1.0, 0.0, 0.0, 0.0]  # Comp 1
    ])
    
    loss_fn = PortFacingRotationLoss(
        group_indices=jnp.array([[0]]),
        primary_pin_offsets=jnp.array([[1.0, 0.0]]),
        target_indices=jnp.array([[1]])
    )
    
    result = loss_fn(positions, rotations, None)
    
    assert abs(result.value - 2.0) < 1e-4

def test_port_facing_dynamic_target():
    """Test that loss responds to moving target."""
    # Comp 0 at (0, 0).
    # Pin offset (1, 0).
    # Rotation 0 (Pin faces +X).
    
    # Case 1: Target at (10, 0) -> Aligned
    pos1 = jnp.array([[0.0, 0.0], [10.0, 0.0]])
    rot = jnp.array([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]])
    
    loss_fn = PortFacingRotationLoss(
        group_indices=jnp.array([[0]]),
        primary_pin_offsets=jnp.array([[1.0, 0.0]]),
        target_indices=jnp.array([[1]])
    )
    
    res1 = loss_fn(pos1, rot, None)
    assert res1.value < 1e-4
    
    # Case 2: Target at (0, 10) -> Orthogonal
    # Pin faces +X, Target is +Y. Cosine sim 0. Penalty 1.0.
    pos2 = jnp.array([[0.0, 0.0], [0.0, 10.0]])
    res2 = loss_fn(pos2, rot, None)
    
    assert abs(res2.value - 1.0) < 1e-4

def test_multiple_groups():
    """Test handling of multiple independent groups."""
    # Group A: Comp 0 -> Target 1 (Aligned)
    # Group B: Comp 2 -> Target 3 (Opposite)
    
    positions = jnp.array([
        [0.0, 0.0], [10.0, 0.0],
        [0.0, 10.0], [10.0, 10.0]
    ])
    
    # Comp 0: 0 deg (Faces +X) -> Aligned with (10, 0)
    # Comp 2: 180 deg (Faces -X) -> Opposite to (10, 10)-(0,10)=(10,0)
    rotations = jnp.array([
        [1.0, 0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [1.0, 0.0, 0.0, 0.0]
    ])
    
    loss_fn = PortFacingRotationLoss(
        group_indices=jnp.array([[0], [2]]),
        primary_pin_offsets=jnp.array([[1.0, 0.0], [1.0, 0.0]]),
        target_indices=jnp.array([[1], [3]])
    )
    
    result = loss_fn(positions, rotations, None)
    
    # Total loss = 0.0 + 2.0 = 2.0
    assert abs(result.value - 2.0) < 1e-4
