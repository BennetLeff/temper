from dataclasses import dataclass

import jax.numpy as jnp
import pytest
from jax import Array

from temper_placer.core.board import Board, LayerStackup
from temper_placer.losses.aesthetic import WhitespaceLoss


@dataclass
class MockNetlist:
    n_components: int
    bounds: Array # (N, 2) array of (width, height)

    def get_bounds_array(self) -> Array:
        return self.bounds

@dataclass
class MockContext:
    board: Board
    netlist: MockNetlist

@pytest.fixture
def whitespace_context():
    """Create a mock context for whitespace loss tests."""
    board = Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        zones=[],
        ground_domains=[],
        layer_stackup=LayerStackup.default_4layer(),
    )

    # 4 components of 10x10 size
    bounds = jnp.full((4, 2), 10.0)
    netlist = MockNetlist(n_components=4, bounds=bounds)

    return MockContext(board=board, netlist=netlist)

def test_whitespace_loss_uniform(whitespace_context):
    """Test that uniform distribution has low loss."""
    # 4 components spread out: (25,25), (25,75), (75,25), (75,75)
    # Each in center of a quadrant
    positions = jnp.array([
        [25.0, 25.0],
        [25.0, 75.0],
        [75.0, 25.0],
        [75.0, 75.0]
    ])
    rotations = jnp.zeros((4, 4))

    # Grid 2x2. Each cell should have approx equal density.
    # Cell size 50x50 = 2500 area.
    # Component area 10x10 = 100.
    # Density = 100/2500 = 0.04 per cell.
    # Variance should be 0.

    loss_fn = WhitespaceLoss(grid_shape=(2, 2))
    result = loss_fn(positions, rotations, whitespace_context)

    assert float(result.value) < 1e-4

def test_whitespace_loss_clustered(whitespace_context):
    """Test that clustered distribution has high loss."""
    # 4 components all in top-left quadrant
    # All in (0-50, 0-50)
    positions = jnp.array([
        [10.0, 10.0],
        [15.0, 15.0],
        [10.0, 20.0],
        [20.0, 10.0]
    ])
    rotations = jnp.zeros((4, 4))

    loss_fn = WhitespaceLoss(grid_shape=(2, 2))
    result = loss_fn(positions, rotations, whitespace_context)

    # Top-left cell has density 4 * 100 / 2500 = 0.16
    # Others have 0.
    # Variance is high.

    assert float(result.value) > 0.001
