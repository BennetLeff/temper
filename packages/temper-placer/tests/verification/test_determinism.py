import jax
import jax.numpy as jnp
import pytest

from temper_placer.losses.base import LoopConstraint, LossContext
from temper_placer.losses.loop_area import LoopAreaLoss
from temper_placer.optimizer.initialization import SpectralInitializer


def test_spectral_init_determinism(simple_netlist, simple_board):
    """Spectral init with fixed netlist should produce identical positions (10 runs)."""
    initializer = SpectralInitializer()

    positions_list = []
    for _ in range(10):
        pos = initializer.initialize(simple_netlist, simple_board)
        positions_list.append(pos)

    for i in range(1, 10):
        assert jnp.allclose(positions_list[0], positions_list[i], atol=1e-6)

def test_loss_function_determinism(simple_netlist, simple_board, simple_placement_state):
    """Loss functions with fixed positions should produce identical values."""
    # Create a real context with loop constraints
    loop_constraints = [
        LoopConstraint(name="L1", pins=[("U1", "VCC"), ("C1", "1"), ("C1", "2")], max_area=10.0, weight=1.0)
    ]
    context = LossContext.from_netlist_and_board(
        simple_netlist,
        simple_board,
        loop_constraints=loop_constraints
    )

    loss_fn = LoopAreaLoss()

    # Convert rotation_logits to soft one-hot rotations (just use 0 degrees for simplicity)
    n_comp = simple_placement_state.positions.shape[0]
    rotations = jnp.zeros((n_comp, 4))
    rotations = rotations.at[:, 0].set(1.0)

    res1 = loss_fn(simple_placement_state.positions, rotations, context)
    res2 = loss_fn(simple_placement_state.positions, rotations, context)

    assert float(res1.value) == pytest.approx(float(res2.value))
    assert res1.breakdown == res2.breakdown

def test_jax_parallelism_determinism(simple_netlist, simple_board, simple_placement_state):
    """Test that JAX JIT and potential parallelism doesn't break determinism."""
    loop_constraints = [
        LoopConstraint(name="L1", pins=[("U1", "VCC"), ("C1", "1"), ("C1", "2")], max_area=10.0, weight=1.0)
    ]
    context = LossContext.from_netlist_and_board(
        simple_netlist,
        simple_board,
        loop_constraints=loop_constraints
    )

    loss_fn = LoopAreaLoss()

    @jax.jit
    def jitted_loss(pos, rot):
        return loss_fn(pos, rot, context)

    # Convert rotation_logits to soft one-hot rotations
    n_comp = simple_placement_state.positions.shape[0]
    rotations = jnp.zeros((n_comp, 4))
    rotations = rotations.at[:, 0].set(1.0)

    res1 = jitted_loss(simple_placement_state.positions, rotations)
    res2 = jitted_loss(simple_placement_state.positions, rotations)

    assert jnp.allclose(res1.value, res2.value)

@pytest.mark.skip(reason="MazeRouter implementation might not be fully deterministic or ready for this test")
def test_maze_router_determinism(simple_netlist, simple_board):
    """Maze router with fixed netlist should produce identical paths."""
    # This requires more setup (grid, pins, etc.)
    pass

def test_nsga2_determinism(simple_netlist, simple_board):
    """NSGA-II with fixed seed should produce identical fronts."""
    from temper_placer.losses.base import LossContext
    from temper_placer.losses.loop_area import LoopAreaLoss
    from temper_placer.optimizer.nsga2 import NSGAOptimizer

    context = LossContext.from_netlist_and_board(simple_netlist, simple_board)
    optimizer = NSGAOptimizer(population_size=10)

    # Define simple objectives
    def obj1(pos, rot, ctx, ep, tot):
        return LoopAreaLoss()(pos, rot, ctx, ep, tot)

    # Run twice with same seed
    res1 = optimizer.evolve(simple_netlist, simple_board, [obj1], context, generations=2, seed=42)
    res2 = optimizer.evolve(simple_netlist, simple_board, [obj1], context, generations=2, seed=42)

    assert jnp.allclose(res1.population_positions, res2.population_positions)
    assert jnp.allclose(res1.objectives, res2.objectives)
    assert res1.fronts == res2.fronts

