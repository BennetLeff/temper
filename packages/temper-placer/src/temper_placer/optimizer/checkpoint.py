"""
Checkpointing for training state.

This module provides functions to save and load training checkpoints,
enabling resume from interrupted training and preservation of best models.

Uses msgpack for serialization with JAX array support via numpy conversion.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jax.numpy as jnp
import numpy as np
from jax import Array

from temper_placer.optimizer.config import CheckpointConfig
from temper_placer.optimizer.validation_callback import ValidationResult


@dataclass
class Checkpoint:
    """
    Training checkpoint containing all state needed to resume.

    Attributes:
        epoch: Training epoch when checkpoint was saved.
        positions: Component positions (N, 2).
        rotation_logits: Rotation logits (N, 4).
        optimizer_state_pos: Serialized optimizer state for positions.
        optimizer_state_rot: Serialized optimizer state for rotations.
        rng_key: JAX random key state.
        best_loss: Best loss achieved so far.
        best_positions: Positions at best loss (optional).
        best_rotation_logits: Rotation logits at best loss (optional).
        validation_history: List of validation results.
        config_hash: Hash of config for compatibility checking.
    """

    epoch: int
    positions: Array
    rotation_logits: Array
    optimizer_state_pos: Any
    optimizer_state_rot: Any
    rng_key: Array
    best_loss: float
    best_positions: Array | None = None
    best_rotation_logits: Array | None = None
    validation_history: list[ValidationResult] | None = None
    config_hash: str | None = None

    def __post_init__(self):
        if self.validation_history is None:
            self.validation_history = []


class CheckpointManager:
    """
    Manages checkpoint saving, loading, and cleanup.

    Handles:
    - Saving checkpoints at configured intervals
    - Keeping only the last N checkpoints
    - Saving best checkpoint separately
    - Loading checkpoints for resume
    """

    def __init__(self, config: CheckpointConfig):
        """
        Initialize checkpoint manager.

        Args:
            config: Checkpoint configuration.
        """
        self.config = config
        self._checkpoint_dir: Path | None = None
        self._checkpoints: list[Path] = []
        self._best_checkpoint: Path | None = None
        self._best_loss: float = float("inf")

        if config.enabled:
            self._setup_directory()

    def __enter__(self) -> CheckpointManager:
        """Enable context manager support."""
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        """Cleanup on exit."""
        self.cleanup()

    def _setup_directory(self):
        """Set up checkpoint directory."""
        if self.config.directory is not None:
            self._checkpoint_dir = Path(self.config.directory)
            self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        else:
            # Use temp directory
            self._checkpoint_dir = Path(tempfile.mkdtemp(prefix="temper_placer_"))

    @property
    def checkpoint_dir(self) -> Path | None:
        """Get checkpoint directory path."""
        return self._checkpoint_dir

    def should_save(self, epoch: int) -> bool:
        """
        Check if a checkpoint should be saved at this epoch.

        Args:
            epoch: Current training epoch.

        Returns:
            True if checkpoint should be saved.
        """
        if not self.config.enabled:
            return False
        return epoch % self.config.interval == 0

    def save(
        self,
        checkpoint: Checkpoint,
        is_best: bool = False,
    ) -> Path | None:
        """
        Save a checkpoint to disk.

        Args:
            checkpoint: Checkpoint to save.
            is_best: Whether this is the best checkpoint so far.

        Returns:
            Path to saved checkpoint, or None if saving disabled.
        """
        if not self.config.enabled or self._checkpoint_dir is None:
            return None

        # Save regular checkpoint
        checkpoint_path = self._checkpoint_dir / f"checkpoint_epoch_{checkpoint.epoch:06d}.npz"
        self._save_to_file(checkpoint, checkpoint_path)

        # Track checkpoints
        self._checkpoints.append(checkpoint_path)

        # Clean up old checkpoints
        self._cleanup_old_checkpoints()

        # Save best checkpoint if requested
        if is_best and self.config.save_best:
            best_path = self._checkpoint_dir / "best_checkpoint.npz"
            self._save_to_file(checkpoint, best_path)
            self._best_checkpoint = best_path
            self._best_loss = checkpoint.best_loss

        return checkpoint_path

    def _save_to_file(self, checkpoint: Checkpoint, path: Path):
        """
        Save checkpoint to file using numpy's npz format.

        Args:
            checkpoint: Checkpoint to save.
            path: Path to save to.
        """
        # Convert JAX arrays to numpy for serialization
        save_dict = {
            "epoch": np.array(checkpoint.epoch),
            "positions": np.asarray(checkpoint.positions),
            "rotation_logits": np.asarray(checkpoint.rotation_logits),
            "rng_key": np.asarray(checkpoint.rng_key),
            "best_loss": np.array(checkpoint.best_loss),
        }

        # Handle optional arrays
        if checkpoint.best_positions is not None:
            save_dict["best_positions"] = np.asarray(checkpoint.best_positions)
        if checkpoint.best_rotation_logits is not None:
            save_dict["best_rotation_logits"] = np.asarray(checkpoint.best_rotation_logits)

        # Serialize optimizer states using numpy structured arrays
        # This is a simplified approach - full optax state serialization is complex
        save_dict["opt_state_pos"] = _serialize_opt_state(checkpoint.optimizer_state_pos)
        save_dict["opt_state_rot"] = _serialize_opt_state(checkpoint.optimizer_state_rot)

        # Save validation history as JSON string
        if checkpoint.validation_history:
            val_history_dicts = []
            for vr in checkpoint.validation_history:
                val_history_dicts.append(
                    {
                        "epoch": vr.epoch,
                        "drc_errors": vr.drc_errors,
                        "drc_penalty": vr.drc_penalty,
                        "drc_warnings": vr.drc_warnings,
                        "elapsed_ms": vr.elapsed_ms,
                        "spice_results": vr.spice_results,
                        "passed": vr.passed,
                        "messages": vr.messages,
                    }
                )
            save_dict["validation_history_json"] = np.array(json.dumps(val_history_dicts))
        else:
            save_dict["validation_history_json"] = np.array("[]")

        if checkpoint.config_hash:
            save_dict["config_hash"] = np.array(checkpoint.config_hash)

        np.savez_compressed(path, **save_dict)  # type: ignore[arg-type]

    def _cleanup_old_checkpoints(self):
        """Remove old checkpoints, keeping only the last N."""
        while len(self._checkpoints) > self.config.keep_last_n:
            old_checkpoint = self._checkpoints.pop(0)
            if old_checkpoint.exists():
                old_checkpoint.unlink()

    def load(self, path: Path | None = None) -> Checkpoint | None:
        """
        Load a checkpoint from disk.

        Args:
            path: Path to checkpoint. If None, loads the latest checkpoint.

        Returns:
            Loaded Checkpoint, or None if not found.
        """
        if path is None:
            path = self.get_latest_checkpoint()

        if path is None or not path.exists():
            return None

        return self._load_from_file(path)

    def load_best(self) -> Checkpoint | None:
        """
        Load the best checkpoint.

        Returns:
            Best checkpoint, or None if not found.
        """
        if self._checkpoint_dir is None:
            return None

        best_path = self._checkpoint_dir / "best_checkpoint.npz"
        if best_path.exists():
            return self._load_from_file(best_path)
        return None

    def _load_from_file(self, path: Path) -> Checkpoint:
        """
        Load checkpoint from file.

        Args:
            path: Path to checkpoint file.

        Returns:
            Loaded Checkpoint.
        """
        data = np.load(path, allow_pickle=True)

        # Convert numpy arrays back to JAX arrays
        positions = jnp.array(data["positions"])
        rotation_logits = jnp.array(data["rotation_logits"])
        rng_key = jnp.array(data["rng_key"])

        # Handle optional arrays
        best_positions = None
        if "best_positions" in data:
            best_positions = jnp.array(data["best_positions"])

        best_rotation_logits = None
        if "best_rotation_logits" in data:
            best_rotation_logits = jnp.array(data["best_rotation_logits"])

        # Deserialize optimizer states
        opt_state_pos = _deserialize_opt_state(data["opt_state_pos"])
        opt_state_rot = _deserialize_opt_state(data["opt_state_rot"])

        # Load validation history
        validation_history = []
        if "validation_history_json" in data:
            val_history_str = str(data["validation_history_json"])
            val_history_dicts = json.loads(val_history_str)
            for vd in val_history_dicts:
                validation_history.append(
                    ValidationResult(
                        epoch=vd["epoch"],
                        drc_errors=vd.get("drc_errors", 0),
                        drc_penalty=vd.get("drc_penalty", 0.0),
                        drc_warnings=vd.get("drc_warnings", 0),
                        elapsed_ms=vd.get("elapsed_ms", 0.0),
                        spice_results=vd.get("spice_results", {}),
                        passed=vd.get("passed", True),
                        messages=vd.get("messages", []),
                    )
                )

        config_hash = None
        if "config_hash" in data:
            config_hash = str(data["config_hash"])

        return Checkpoint(
            epoch=int(data["epoch"]),
            positions=positions,
            rotation_logits=rotation_logits,
            optimizer_state_pos=opt_state_pos,
            optimizer_state_rot=opt_state_rot,
            rng_key=rng_key,
            best_loss=float(data["best_loss"]),
            best_positions=best_positions,
            best_rotation_logits=best_rotation_logits,
            validation_history=validation_history,
            config_hash=config_hash,
        )

    def get_latest_checkpoint(self) -> Path | None:
        """
        Get path to the latest checkpoint.

        Returns:
            Path to latest checkpoint, or None if none exist.
        """
        if self._checkpoint_dir is None:
            return None

        checkpoints = sorted(self._checkpoint_dir.glob("checkpoint_epoch_*.npz"))
        if checkpoints:
            return checkpoints[-1]
        return None

    def list_checkpoints(self) -> list[Path]:
        """
        List all available checkpoints.

        Returns:
            List of checkpoint paths, sorted by epoch.
        """
        if self._checkpoint_dir is None:
            return []
        return sorted(self._checkpoint_dir.glob("checkpoint_epoch_*.npz"))

    def cleanup(self):
        """Remove all checkpoints and the checkpoint directory if it was auto-created."""
        if self._checkpoint_dir is None:
            return

        # Only remove if it was auto-created (temp directory)
        if self.config.directory is None and self._checkpoint_dir.exists():
            shutil.rmtree(self._checkpoint_dir)
            self._checkpoint_dir = None


def _serialize_opt_state(opt_state: Any) -> np.ndarray:
    """
    Serialize optax optimizer state to numpy array.

    This is a simplified serialization that extracts the core arrays.
    For full serialization, consider using orbax-checkpoint.

    Args:
        opt_state: Optax optimizer state.

    Returns:
        Serialized state as numpy array (pickled).
    """
    import pickle

    return np.frombuffer(pickle.dumps(opt_state), dtype=np.uint8)


def _deserialize_opt_state(data: np.ndarray) -> Any:
    """
    Deserialize optax optimizer state from numpy array.

    Args:
        data: Serialized state as numpy array.

    Returns:
        Deserialized optax optimizer state.
    """
    import pickle

    return pickle.loads(data.tobytes())


def create_checkpoint_from_training_state(
    training_state: Any,  # TrainingState from train.py
    validation_history: list[ValidationResult],
    config_hash: str | None = None,
) -> Checkpoint:
    """
    Create a Checkpoint from current training state.

    Args:
        training_state: TrainingState object from train.py.
        validation_history: List of validation results so far.
        config_hash: Optional hash of configuration.

    Returns:
        Checkpoint object ready for saving.
    """
    return Checkpoint(
        epoch=training_state.epoch,
        positions=training_state.positions,
        rotation_logits=training_state.rotation_logits,
        optimizer_state_pos=training_state.opt_state_pos,
        optimizer_state_rot=training_state.opt_state_rot,
        rng_key=training_state.rng_key,
        best_loss=training_state.best_loss,
        best_positions=training_state.best_positions,
        best_rotation_logits=training_state.best_rotations
        if hasattr(training_state, "best_rotations")
        else None,
        validation_history=validation_history,
        config_hash=config_hash,
    )


def restore_training_state_from_checkpoint(
    checkpoint: Checkpoint,
    training_state: Any,  # TrainingState from train.py
) -> tuple[Any, list[ValidationResult]]:
    """
    Restore training state from a checkpoint.

    Args:
        checkpoint: Checkpoint to restore from.
        training_state: TrainingState to update.

    Returns:
        Tuple of (updated training_state, validation_history).
    """
    training_state.epoch = checkpoint.epoch
    training_state.positions = checkpoint.positions
    training_state.rotation_logits = checkpoint.rotation_logits
    training_state.opt_state_pos = checkpoint.optimizer_state_pos
    training_state.opt_state_rot = checkpoint.optimizer_state_rot
    training_state.rng_key = checkpoint.rng_key
    training_state.best_loss = checkpoint.best_loss

    if checkpoint.best_positions is not None:
        training_state.best_positions = checkpoint.best_positions

    return training_state, checkpoint.validation_history
