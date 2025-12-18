"""Tests for initialization integration in train.py."""
import pytest
import jax.numpy as jnp
from temper_placer.optimizer.config import OptimizerConfig, InitializationConfig
from temper_placer.optimizer.train import initialize_training_state
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.board import Board

def test_spectral_initialization_integration():
    """Verify that initialize_training_state uses spectral initialization when configured."""
    components = [
        Component(ref="R1", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0), net="N1")]),
        Component(ref="R2", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0), net="N1")]),
    ]
    nets = [Net(name="N1", pins=[("R1", "1"), ("R2", "1")])]
    netlist = Netlist(components=components, nets=nets)
    board = Board(width=100, height=100)
    
    # Configure spectral initialization
    config = OptimizerConfig(
        initialization=InitializationConfig(method="spectral")
    )
    
    state = initialize_training_state(netlist, board, config)
    
    # Spectral initialization is deterministic, R1 and R2 should be separated
    # For a simple 2-node graph, they should be at some distance from each other
    dist = float(jnp.linalg.norm(state.positions[0] - state.positions[1]))
    assert dist > 1.0
    
    # Default is random, which should also be separated but depends on seed
    config_random = OptimizerConfig(
        initialization=InitializationConfig(method="random"),
        seed=42
    )
    state_random = initialize_training_state(netlist, board, config_random)
    
    # They should be different
    assert not jnp.allclose(state.positions, state_random.positions)
