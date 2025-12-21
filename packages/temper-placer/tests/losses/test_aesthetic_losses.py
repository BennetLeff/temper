
from dataclasses import dataclass
import jax.numpy as jnp
import pytest
from jax import Array
from temper_placer.losses.aesthetic import PortFacingRotationLoss, StackedRowLoss
from temper_placer.losses.base import LossContext, LossResult

@pytest.fixture
def mock_loss_context():
    @dataclass
    class MockContext:
        net_pin_indices: Array
        net_pin_mask: Array
        net_weights: Array
    
    # Setup context with 1 net crossing between Row 0 and Row 1
    # Group components: 0, 1, 2 (Row 0), 3, 4, 5 (Row 1)
    # Net 0 connects component 0 to component 3
    return MockContext(
        net_pin_indices=jnp.array([[0, 3], [1, 2]]),
        net_pin_mask=jnp.array([[True, True], [True, True]]),
        net_weights=jnp.array([1.0, 1.0])
    )

def test_stacked_row_gutter_calculation(mock_loss_context):
    """Test that gutters expand with net crossings."""
    # 6 components in 3 columns -> 2 rows
    # Row 0: 0, 1, 2
    # Row 1: 3, 4, 5
    comp_indices = jnp.arange(6)
    
    # Case 1: No crossing weight
    loss_fn_no_weight = StackedRowLoss(
        component_indices=comp_indices,
        cols=3,
        min_row_pitch=10.0,
        col_pitch=10.0,
        net_crossing_weight=0.0
    )
    
    positions = jnp.zeros((6, 2))
    rotations = jnp.zeros((6, 4))
    
    result_no_weight = loss_fn_no_weight(positions, rotations, mock_loss_context)
    # Breakdown should have crossing_counts
    counts = result_no_weight.breakdown["crossing_counts"]
    # Net 0 (0-3) crosses Row 0-1. Net 1 (1-2) does NOT cross (both in Row 0).
    # So count should be 1.
    assert counts[0] == 1
    
    # Case 2: With crossing weight
    loss_fn_weight = StackedRowLoss(
        component_indices=comp_indices,
        cols=3,
        min_row_pitch=10.0,
        col_pitch=10.0,
        net_crossing_weight=5.0
    )
    
    # We can't easily check internal row_offsets from result.value without math.
    # Row 0 is at y=0. Row 1 is at y = 10 + 5*1 = 15.
    # Target positions: 
    # Row 0: (0,0), (10,0), (20,0)
    # Row 1: (0,15), (10,15), (20,15)
    # Target Centroid: (10, 7.5)
    # Let's check if the penalty is 0 when components are at these positions.
    
    target_pos = jnp.array([
        [0, 0], [10, 0], [20, 0],
        [0, 15], [10, 15], [20, 15]
    ])
    # Center them
    target_pos = target_pos - jnp.mean(target_pos, axis=0)
    
    result = loss_fn_weight(target_pos, rotations, mock_loss_context)
    assert result.value < 1e-4

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
