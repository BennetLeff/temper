"""Tests for force-directed initialization integration."""
import jax.numpy as jnp

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.optimizer.config import (
    ForceDirectedConfig,
    InitializationConfig,
    OptimizerConfig,
)
from temper_placer.optimizer.train import initialize_training_state


def test_force_directed_integration():
    """Verify that initialize_training_state applies force-directed unfolding when configured."""
    # Create a 3-component chain R1-R2-R3
    components = [
        Component(ref="R1", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0), net="N1")]),
        Component(ref="R2", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0), net="N1"), Pin("2", "2", (1, 0), net="N2")]),
        Component(ref="R3", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0), net="N2")]),
    ]
    nets = [
        Net(name="N1", pins=[("R1", "1"), ("R2", "1")]),
        Net(name="N2", pins=[("R2", "2"), ("R3", "1")])
    ]
    netlist = Netlist(components=components, nets=nets)
    board = Board(width=100, height=100)

    # 1. Run without force-directed (using Spectral)
    config_base = OptimizerConfig(
        initialization=InitializationConfig(
            method="spectral",
            force_directed=ForceDirectedConfig(enabled=False)
        ),
        seed=42
    )
    state_base = initialize_training_state(netlist, board, config_base)

    # 2. Run with force-directed enabled
    config_fd = OptimizerConfig(
        initialization=InitializationConfig(
            method="spectral",
            force_directed=ForceDirectedConfig(enabled=True, iterations=50, learning_rate=0.5)
        ),
        seed=42
    )
    state_fd = initialize_training_state(netlist, board, config_fd)

    # Positions should be different
    assert not jnp.allclose(state_base.positions, state_fd.positions)

    # Check that positions are still valid (not NaN)
    assert jnp.all(jnp.isfinite(state_fd.positions))
