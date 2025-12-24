#!/usr/bin/env python3
"""
Verification script for rotation crossover and mutation logic.

Tests the modified nsga2.py functions independently.
"""

import sys

sys.path.insert(0, "src")

import jax
import jax.numpy as jnp


def test_crossover_blx_alpha():
    """Test that crossover_blx_alpha blends values."""
    from temper_placer.optimizer.nsga2 import crossover_blx_alpha

    parent1 = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    parent2 = jnp.array([[0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])

    key = jax.random.PRNGKey(42)
    child = crossover_blx_alpha(parent1, parent2, key, alpha=0.5)

    print("✓ Test 1: Crossover BLX-alpha function works")
    print(f"  Parent1: {parent1}")
    print(f"  Parent2: {parent2}")
    print(f"  Child: {child}")

    # Child should differ from both parents
    assert not jnp.allclose(child, parent1, atol=0.1)
    assert not jnp.allclose(child, parent2, atol=0.1)
    print("  ✓ Child differs from both parents")


def test_mutate_gaussian():
    """Test that mutate_gaussian introduces noise."""
    from temper_placer.optimizer.nsga2 import mutate_gaussian

    initial = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])

    key = jax.random.PRNGKey(42)
    mutated = mutate_gaussian(initial, key, sigma=0.3, rate=0.5)

    print("\n✓ Test 2: Mutation function works")
    print(f"  Initial: {initial}")
    print(f"  Mutated: {mutated}")

    # Some values should have changed
    differences = jnp.abs(mutated - initial)
    max_diff = jnp.max(differences)
    print(f"  Max difference: {max_diff}")
    assert max_diff > 0.01
    print("  ✓ Mutation introduces changes")


def test_rotation_diversity():
    """Test that repeated initialization creates diverse rotations."""
    from temper_placer.optimizer.nsga2 import NSGAOptimizer
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Component, Netlist
    from temper_placer.core.state import PlacementState
    from temper_placer.losses.base import LossContext

    # Simple board
    board = Board(
        width=100,
        height=100,
        origin=(0, 0),
        zones=[],
        ground_domains=[],
        layer_stackup=[0, 1, 2, 3],
    )

    c1 = Component(ref="U1", footprint="S", bounds=(10, 10))
    netlist = Netlist(components=[c1], nets=[])
    context = LossContext.from_netlist_and_board(netlist, board)

    # Initial state with fixed rotation
    initial_rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]])
    initial_state = PlacementState(
        positions=jnp.array([[50.0, 50.0]]), rotation_logits=initial_rotations
    )

    optimizer = NSGAOptimizer(population_size=20)

    # Just run a few generations to see diversity
    class DummyObjective:
        def __call__(self, positions, rotations, context, epoch, total_epochs):
            return type("Result", (), {"value": jnp.zeros(positions.shape[0])})()

    result = optimizer.evolve(
        netlist=netlist,
        board=board,
        objectives=[DummyObjective()],
        context=context,
        generations=5,
        initial_state=initial_state,
        seed=42,
    )

    # Check rotation diversity in final population
    final_rotations = jnp.argmax(result.population_rotations, axis=-1)
    unique_rotations = jnp.unique(final_rotations)
    rotation_variance = jnp.var(final_rotations.flatten())

    print("\n✓ Test 3: Rotation diversity over generations")
    print(f"  Final rotations: {final_rotations}")
    print(f"  Unique rotations: {unique_rotations}")
    print(f"  Rotation variance: {rotation_variance}")

    assert len(unique_rotations) > 1, "Should have multiple unique rotations"
    print("  ✓ Multiple unique rotations found in final population")


if __name__ == "__main__":
    try:
        test_crossover_blx_alpha()
        test_mutate_gaussian()
        test_rotation_diversity()
        print("\n✅ All verification tests passed!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
