
import jax.numpy as jnp
import pytest
from dataclasses import dataclass
from jax import Array
import jax

from temper_placer.losses.manufacturing_margin import ManufacturingMarginLoss
from temper_placer.losses.base import LossResult
from temper_placer.core.board import Board, LayerStackup

@dataclass
class MockNetlist:
    n_components: int
    def get_bounds_array(self) -> Array:
        return jnp.full((self.n_components, 2), 10.0)

@dataclass
class MockContext:
    board: Board
    netlist: MockNetlist

@pytest.fixture
def manufacturing_context():
    board = Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        zones=[],
        ground_domains=[],
        layer_stackup=LayerStackup.default_4layer(),
    )
    netlist = MockNetlist(n_components=2)
    return MockContext(board=board, netlist=netlist)

def test_margin_loss_comfortable(manufacturing_context):
    """Loss should be near zero for comfortable margins."""
    # Two 10x10 components at (20, 20) and (50, 20)
    # Distance center-to-center = 30
    # Edge-to-edge = 30 - 5 - 5 = 20
    # Target margin is typically small (e.g. 0.1mm)
    positions = jnp.array([
        [20.0, 20.0],
        [50.0, 20.0]
    ])
    rotations = jnp.zeros((2, 4))
    
    loss_fn = ManufacturingMarginLoss(target_margin_mm=0.1)
    result = loss_fn(positions, rotations, manufacturing_context)
    
    # Margin 20 >> 0.1, so loss should be very low
    assert float(result.value) < 1e-3

def test_margin_loss_tight(manufacturing_context):
    """Loss should increase as margins approach target."""
    # Edge-to-edge = 0.15 (just above target 0.1)
    # Centers at 20 and 20 + 10 + 0.15 = 30.15
    positions_comfortable = jnp.array([[20.0, 20.0], [50.0, 20.0]])
    positions_tight = jnp.array([[20.0, 20.0], [30.15, 20.0]])
    
    rotations = jnp.zeros((2, 4))
    loss_fn = ManufacturingMarginLoss(target_margin_mm=0.1)
    
    res_comf = loss_fn(positions_comfortable, rotations, manufacturing_context)
    res_tight = loss_fn(positions_tight, rotations, manufacturing_context)
    
    assert float(res_tight.value) > float(res_comf.value)

def test_margin_loss_violation(manufacturing_context):
    """Loss should be very high for violations (overlap)."""
    # Overlap by 1mm
    positions = jnp.array([
        [20.0, 20.0],
        [29.0, 20.0] # Edge-to-edge = -1
    ])
    rotations = jnp.zeros((2, 4))
    
    loss_fn = ManufacturingMarginLoss(target_margin_mm=0.1)
    result = loss_fn(positions, rotations, manufacturing_context)
    
    # Very high penalty for violation
    assert float(result.value) > 10.0

def test_margin_loss_differentiable(manufacturing_context):
    """Gradient should exist and point in direction of increasing margin."""
    def loss_val(pos):
        loss_fn = ManufacturingMarginLoss(target_margin_mm=0.1)
        return loss_fn(pos, jnp.zeros((2, 4)), manufacturing_context).value
        
    positions = jnp.array([[20.0, 20.0], [30.05, 20.0]]) # 0.05 margin
    grad = jax.grad(loss_val)(positions)
    
    # Gradient for second component should be negative in X (minimize loss by increasing X)
    # loss(x) decreases as x increases -> dloss/dx < 0
    assert grad[1, 0] < 0
