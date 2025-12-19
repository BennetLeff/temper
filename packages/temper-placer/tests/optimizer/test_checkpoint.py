"""
Tests for checkpoint module.

Tests the Checkpoint dataclass, CheckpointManager, and save/load functionality.
"""

import tempfile

import jax
import jax.numpy as jnp

from temper_placer.optimizer.checkpoint import (
    Checkpoint,
    CheckpointManager,
    create_checkpoint_from_training_state,
)
from temper_placer.optimizer.config import CheckpointConfig
from temper_placer.optimizer.validation_callback import ValidationResult


class TestCheckpoint:
    """Tests for Checkpoint dataclass."""

    def test_checkpoint_creation(self):
        """Test creating a checkpoint with basic data."""
        positions = jnp.array([[1.0, 2.0], [3.0, 4.0]])
        rotation_logits = jnp.zeros((2, 4))
        rng_key = jax.random.PRNGKey(42)

        checkpoint = Checkpoint(
            epoch=100,
            positions=positions,
            rotation_logits=rotation_logits,
            optimizer_state_pos=None,
            optimizer_state_rot=None,
            rng_key=rng_key,
            best_loss=10.5,
        )

        assert checkpoint.epoch == 100
        assert checkpoint.best_loss == 10.5
        assert checkpoint.positions.shape == (2, 2)
        assert checkpoint.rotation_logits.shape == (2, 4)
        assert checkpoint.validation_history == []

    def test_checkpoint_with_validation_history(self):
        """Test checkpoint with validation history."""
        val_result = ValidationResult(epoch=50, drc_errors=0, drc_penalty=0.0, passed=True)

        checkpoint = Checkpoint(
            epoch=100,
            positions=jnp.zeros((2, 2)),
            rotation_logits=jnp.zeros((2, 4)),
            optimizer_state_pos=None,
            optimizer_state_rot=None,
            rng_key=jax.random.PRNGKey(0),
            best_loss=5.0,
            validation_history=[val_result],
        )

        assert len(checkpoint.validation_history) == 1
        assert checkpoint.validation_history[0].epoch == 50


class TestCheckpointManager:
    """Tests for CheckpointManager."""

    def test_manager_disabled(self):
        """Test that disabled manager doesn't save."""
        config = CheckpointConfig(enabled=False)
        manager = CheckpointManager(config)

        assert not manager.should_save(0)
        assert not manager.should_save(100)
        assert manager.checkpoint_dir is None

    def test_manager_with_temp_dir(self):
        """Test manager creates temp directory when none specified."""
        config = CheckpointConfig(enabled=True, directory=None)
        manager = CheckpointManager(config)

        assert manager.checkpoint_dir is not None
        assert manager.checkpoint_dir.exists()

        # Cleanup
        manager.cleanup()

    def test_should_save_interval(self):
        """Test that should_save respects interval."""
        config = CheckpointConfig(enabled=True, interval=100)
        manager = CheckpointManager(config)

        assert manager.should_save(0)
        assert not manager.should_save(50)
        assert manager.should_save(100)
        assert not manager.should_save(150)
        assert manager.should_save(200)

        manager.cleanup()

    def test_save_and_load(self):
        """Test saving and loading checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = CheckpointConfig(enabled=True, directory=tmpdir, interval=100)
            manager = CheckpointManager(config)

            # Create checkpoint
            positions = jnp.array([[1.0, 2.0], [3.0, 4.0]])
            rotation_logits = jnp.array([[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]])
            rng_key = jax.random.PRNGKey(42)

            checkpoint = Checkpoint(
                epoch=100,
                positions=positions,
                rotation_logits=rotation_logits,
                optimizer_state_pos=None,
                optimizer_state_rot=None,
                rng_key=rng_key,
                best_loss=10.5,
            )

            # Save
            path = manager.save(checkpoint)
            assert path is not None
            assert path.exists()

            # Load
            loaded = manager.load(path)
            assert loaded is not None
            assert loaded.epoch == 100
            assert loaded.best_loss == 10.5
            assert jnp.allclose(loaded.positions, positions)
            assert jnp.allclose(loaded.rotation_logits, rotation_logits)

    def test_load_latest(self):
        """Test loading the latest checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = CheckpointConfig(enabled=True, directory=tmpdir, interval=100)
            manager = CheckpointManager(config)

            # Save multiple checkpoints
            for epoch in [100, 200, 300]:
                checkpoint = Checkpoint(
                    epoch=epoch,
                    positions=jnp.zeros((2, 2)),
                    rotation_logits=jnp.zeros((2, 4)),
                    optimizer_state_pos=None,
                    optimizer_state_rot=None,
                    rng_key=jax.random.PRNGKey(0),
                    best_loss=float(epoch),
                )
                manager.save(checkpoint)

            # Load latest
            latest = manager.load()
            assert latest is not None
            assert latest.epoch == 300
            assert latest.best_loss == 300.0

    def test_keep_last_n(self):
        """Test that old checkpoints are cleaned up."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = CheckpointConfig(enabled=True, directory=tmpdir, interval=100, keep_last_n=2)
            manager = CheckpointManager(config)

            # Save 5 checkpoints
            for epoch in [100, 200, 300, 400, 500]:
                checkpoint = Checkpoint(
                    epoch=epoch,
                    positions=jnp.zeros((2, 2)),
                    rotation_logits=jnp.zeros((2, 4)),
                    optimizer_state_pos=None,
                    optimizer_state_rot=None,
                    rng_key=jax.random.PRNGKey(0),
                    best_loss=float(epoch),
                )
                manager.save(checkpoint)

            # Should only have 2 checkpoints
            checkpoints = manager.list_checkpoints()
            assert len(checkpoints) == 2
            # Should be the most recent two
            assert "epoch_000400" in str(checkpoints[0])
            assert "epoch_000500" in str(checkpoints[1])

    def test_save_best(self):
        """Test saving best checkpoint separately."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = CheckpointConfig(enabled=True, directory=tmpdir, interval=100, save_best=True)
            manager = CheckpointManager(config)

            # Save checkpoint marked as best
            checkpoint = Checkpoint(
                epoch=100,
                positions=jnp.zeros((2, 2)),
                rotation_logits=jnp.zeros((2, 4)),
                optimizer_state_pos=None,
                optimizer_state_rot=None,
                rng_key=jax.random.PRNGKey(0),
                best_loss=5.0,
            )
            manager.save(checkpoint, is_best=True)

            # Load best
            best = manager.load_best()
            assert best is not None
            assert best.epoch == 100
            assert best.best_loss == 5.0

    def test_validation_history_roundtrip(self):
        """Test that validation history survives save/load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = CheckpointConfig(enabled=True, directory=tmpdir)
            manager = CheckpointManager(config)

            # Create checkpoint with validation history
            val_results = [
                ValidationResult(epoch=50, drc_errors=2, drc_penalty=0.5, passed=True),
                ValidationResult(epoch=100, drc_errors=0, drc_penalty=0.0, passed=True),
            ]

            checkpoint = Checkpoint(
                epoch=100,
                positions=jnp.zeros((2, 2)),
                rotation_logits=jnp.zeros((2, 4)),
                optimizer_state_pos=None,
                optimizer_state_rot=None,
                rng_key=jax.random.PRNGKey(0),
                best_loss=5.0,
                validation_history=val_results,
            )

            path = manager.save(checkpoint)
            loaded = manager.load(path)

            assert len(loaded.validation_history) == 2
            assert loaded.validation_history[0].epoch == 50
            assert loaded.validation_history[0].drc_errors == 2
            assert loaded.validation_history[1].epoch == 100
            assert loaded.validation_history[1].passed is True


class TestCheckpointWithOptimizerState:
    """Tests for checkpointing with actual optimizer state."""

    def test_optimizer_state_roundtrip(self):
        """Test that optax optimizer state survives save/load."""
        import optax

        with tempfile.TemporaryDirectory() as tmpdir:
            config = CheckpointConfig(enabled=True, directory=tmpdir)
            manager = CheckpointManager(config)

            # Create optimizer and state
            optimizer = optax.adam(0.01)
            params = jnp.array([[1.0, 2.0], [3.0, 4.0]])
            opt_state = optimizer.init(params)

            checkpoint = Checkpoint(
                epoch=100,
                positions=params,
                rotation_logits=jnp.zeros((2, 4)),
                optimizer_state_pos=opt_state,
                optimizer_state_rot=opt_state,
                rng_key=jax.random.PRNGKey(0),
                best_loss=5.0,
            )

            path = manager.save(checkpoint)
            loaded = manager.load(path)

            # Verify optimizer state can be used
            assert loaded.optimizer_state_pos is not None
            grads = jnp.ones_like(params)
            updates, new_state = optimizer.update(grads, loaded.optimizer_state_pos, params)
            # Should not raise


class TestCreateCheckpointFromTrainingState:
    """Tests for checkpoint creation from training state."""

    def test_create_from_training_state(self):
        """Test creating checkpoint from training state object."""
        from dataclasses import dataclass
        from typing import Any

        import jax.numpy as jnp
        from jax import Array

        # Mock TrainingState (simplified version of the real one)
        @dataclass
        class MockTrainingState:
            positions: Array
            rotation_logits: Array
            opt_state_pos: Any
            opt_state_rot: Any
            rng_key: Array
            epoch: int = 0
            best_loss: float = float("inf")
            best_positions: Array | None = None
            best_rotations: Array | None = None

        # Create mock training state
        state = MockTrainingState(
            positions=jnp.array([[1.0, 2.0], [3.0, 4.0]]),
            rotation_logits=jnp.zeros((2, 4)),
            opt_state_pos=None,
            opt_state_rot=None,
            rng_key=jax.random.PRNGKey(42),
            epoch=150,
            best_loss=7.5,
            best_positions=jnp.array([[0.5, 1.5], [2.5, 3.5]]),
        )

        validation_history = [
            ValidationResult(epoch=100, passed=True),
        ]

        checkpoint = create_checkpoint_from_training_state(
            state, validation_history, config_hash="abc123"
        )

        assert checkpoint.epoch == 150
        assert checkpoint.best_loss == 7.5
        assert jnp.allclose(checkpoint.positions, state.positions)
        assert checkpoint.config_hash == "abc123"
        assert len(checkpoint.validation_history) == 1
