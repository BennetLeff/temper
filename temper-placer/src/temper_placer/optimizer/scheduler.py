"""
Learning rate and temperature scheduling for the optimizer.

This module provides schedule functions for:
- Gumbel-Softmax temperature annealing
- Learning rate warmup and decay
- Curriculum weight transitions

All schedules are designed to be JAX-compatible and can be JIT-compiled.
"""

import jax.numpy as jnp
from jax import Array
from typing import Tuple

from temper_placer.optimizer.config import (
    TemperatureSchedule,
    LearningRateSchedule,
    CurriculumPhase,
)


def get_temperature(
    epoch: int,
    total_epochs: int,
    schedule: TemperatureSchedule,
) -> float:
    """
    Get the Gumbel-Softmax temperature for a given epoch.

    Args:
        epoch: Current epoch (0-indexed).
        total_epochs: Total number of epochs.
        schedule: Temperature schedule configuration.

    Returns:
        Temperature value for the current epoch.
    """
    # During warmup, hold at start temperature
    if epoch < schedule.warmup_epochs:
        return schedule.start

    # Compute progress through annealing phase
    anneal_epochs = total_epochs - schedule.warmup_epochs
    if anneal_epochs <= 0:
        return schedule.end

    progress = (epoch - schedule.warmup_epochs) / anneal_epochs
    progress = min(max(progress, 0.0), 1.0)  # Clamp to [0, 1]

    if schedule.anneal_type == "linear":
        return schedule.start + progress * (schedule.end - schedule.start)

    elif schedule.anneal_type == "exponential":
        # Exponential decay: start * (end/start)^progress
        ratio = schedule.end / schedule.start
        return schedule.start * (ratio**progress)

    elif schedule.anneal_type == "cosine":
        # Cosine annealing: smooth transition
        cos_progress = (1 - jnp.cos(jnp.pi * progress)) / 2
        return schedule.start + float(cos_progress) * (schedule.end - schedule.start)

    else:
        # Default to linear
        return schedule.start + progress * (schedule.end - schedule.start)


def get_learning_rate(
    epoch: int,
    total_epochs: int,
    schedule: LearningRateSchedule,
) -> float:
    """
    Get the learning rate for a given epoch.

    Implements warmup followed by optional decay.

    Args:
        epoch: Current epoch (0-indexed).
        total_epochs: Total number of epochs.
        schedule: Learning rate schedule configuration.

    Returns:
        Learning rate for the current epoch.
    """
    # Warmup phase: linear ramp from 0 to initial
    if epoch < schedule.warmup_epochs:
        warmup_progress = epoch / max(schedule.warmup_epochs, 1)
        return schedule.initial * warmup_progress

    # Before decay starts, hold at initial
    if epoch < schedule.decay_start_epoch:
        return schedule.initial

    # No decay mode
    if schedule.decay_type == "none":
        return schedule.initial

    # Compute decay progress
    decay_epochs = total_epochs - schedule.decay_start_epoch
    if decay_epochs <= 0:
        return schedule.final

    progress = (epoch - schedule.decay_start_epoch) / decay_epochs
    progress = min(max(progress, 0.0), 1.0)

    if schedule.decay_type == "linear":
        return schedule.initial + progress * (schedule.final - schedule.initial)

    elif schedule.decay_type == "exponential":
        ratio = schedule.final / max(schedule.initial, 1e-10)
        return schedule.initial * (ratio**progress)

    elif schedule.decay_type == "cosine":
        cos_progress = (1 - jnp.cos(jnp.pi * progress)) / 2
        return schedule.initial + float(cos_progress) * (schedule.final - schedule.initial)

    else:
        return schedule.initial


def get_temperature_jax(
    epoch: Array,
    total_epochs: int,
    start: float,
    end: float,
    warmup_epochs: int,
) -> Array:
    """
    JAX-compatible temperature schedule (for use in JIT-compiled functions).

    Uses exponential annealing by default.

    Args:
        epoch: Current epoch as JAX array (scalar).
        total_epochs: Total number of epochs.
        start: Start temperature.
        end: End temperature.
        warmup_epochs: Warmup epochs before annealing.

    Returns:
        Temperature as JAX array (scalar).
    """
    # Warmup: hold at start
    warmup_temp = start

    # Annealing: exponential decay
    anneal_epochs = total_epochs - warmup_epochs
    progress = jnp.clip((epoch - warmup_epochs) / jnp.maximum(anneal_epochs, 1), 0.0, 1.0)
    ratio = end / start
    anneal_temp = start * jnp.power(ratio, progress)

    # Select based on epoch
    return jnp.where(epoch < warmup_epochs, warmup_temp, anneal_temp)


def get_learning_rate_jax(
    epoch: Array,
    total_epochs: int,
    initial: float,
    final: float,
    warmup_epochs: int,
    decay_start_epoch: int,
) -> Array:
    """
    JAX-compatible learning rate schedule (for use in JIT-compiled functions).

    Uses cosine annealing by default.

    Args:
        epoch: Current epoch as JAX array (scalar).
        total_epochs: Total number of epochs.
        initial: Initial learning rate.
        final: Final learning rate.
        warmup_epochs: Warmup epochs.
        decay_start_epoch: Epoch to start decay.

    Returns:
        Learning rate as JAX array (scalar).
    """
    # Warmup: linear ramp
    warmup_progress = epoch / jnp.maximum(warmup_epochs, 1)
    warmup_lr = initial * warmup_progress

    # Hold: constant at initial
    hold_lr = initial

    # Decay: cosine annealing
    decay_epochs = total_epochs - decay_start_epoch
    decay_progress = jnp.clip((epoch - decay_start_epoch) / jnp.maximum(decay_epochs, 1), 0.0, 1.0)
    cos_progress = (1 - jnp.cos(jnp.pi * decay_progress)) / 2
    decay_lr = initial + cos_progress * (final - initial)

    # Select based on epoch
    lr = jnp.where(epoch < warmup_epochs, warmup_lr, hold_lr)
    lr = jnp.where(epoch >= decay_start_epoch, decay_lr, lr)
    return lr


def smooth_step(x: float, edge0: float = 0.0, edge1: float = 1.0) -> float:
    """
    Smooth step function for gradual transitions.

    Returns 0 for x <= edge0, 1 for x >= edge1, and smoothly
    interpolates between using Hermite polynomial 3x² - 2x³.

    Args:
        x: Input value.
        edge0: Lower edge (returns 0).
        edge1: Upper edge (returns 1).

    Returns:
        Smoothly interpolated value in [0, 1].
    """
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def get_phase_weight(
    epoch: int,
    phase: CurriculumPhase,
    transition_epochs: int = 100,
) -> float:
    """
    Get the weight multiplier for a curriculum phase.

    Returns 0 before phase starts, smoothly ramps up at start,
    holds at 1 during phase, and smoothly ramps down at end.

    Args:
        epoch: Current epoch.
        phase: Curriculum phase configuration.
        transition_epochs: Epochs for smooth transitions.

    Returns:
        Weight multiplier in [0, 1].
    """
    # Before phase starts
    if epoch < phase.start_epoch:
        return 0.0

    # After phase ends
    if epoch >= phase.end_epoch:
        return 0.0

    # Ramp up at start
    if epoch < phase.start_epoch + transition_epochs:
        progress = (epoch - phase.start_epoch) / transition_epochs
        return smooth_step(progress)

    # Ramp down at end
    if epoch >= phase.end_epoch - transition_epochs:
        progress = (phase.end_epoch - epoch) / transition_epochs
        return smooth_step(progress)

    # Full weight during phase
    return 1.0


def get_curriculum_weights(
    epoch: int,
    phases: list,
    default_weights: dict,
) -> dict:
    """
    Get combined loss weights from all active curriculum phases.

    Blends weights from overlapping phases based on their phase weights.

    Args:
        epoch: Current epoch.
        phases: List of CurriculumPhase instances.
        default_weights: Default loss weights to use when no phase is active.

    Returns:
        Dict mapping loss name to combined weight.
    """
    if not phases:
        return default_weights

    # Start with zeros
    combined = {name: 0.0 for name in default_weights}
    total_phase_weight = 0.0

    for phase in phases:
        phase_weight = get_phase_weight(epoch, phase)
        if phase_weight > 0:
            total_phase_weight += phase_weight
            for loss_name, weight in phase.loss_weights.items():
                if loss_name in combined:
                    combined[loss_name] += phase_weight * weight
                else:
                    combined[loss_name] = phase_weight * weight

    # If no phases active, use defaults
    if total_phase_weight < 1e-6:
        return default_weights

    # Normalize by total phase weight
    return {name: weight / max(total_phase_weight, 1e-6) for name, weight in combined.items()}


class ScheduleState:
    """
    Tracks current schedule values during training.

    This class provides a convenient interface for getting all schedule
    values at a given epoch, handling phase transitions and overrides.

    Attributes:
        config: OptimizerConfig with all schedule settings.
        default_weights: Default loss weights.
    """

    def __init__(self, config, default_weights: dict):
        """
        Initialize schedule state.

        Args:
            config: OptimizerConfig instance.
            default_weights: Default loss weights.
        """
        self.config = config
        self.default_weights = default_weights

    def get_state(self, epoch: int) -> dict:
        """
        Get all schedule values for the current epoch.

        Returns:
            Dict with keys: temperature, learning_rate, loss_weights, phase_name
        """
        # Get temperature (check for phase override first)
        temperature = None
        phase_name = None

        for phase in self.config.curriculum_phases:
            if phase.start_epoch <= epoch < phase.end_epoch:
                if phase.temperature_override is not None:
                    temperature = phase.temperature_override
                phase_name = phase.name
                break

        if temperature is None:
            temperature = get_temperature(
                epoch,
                self.config.epochs,
                self.config.temperature,
            )

        # Get learning rate (check for phase override first)
        learning_rate = None
        for phase in self.config.curriculum_phases:
            if phase.start_epoch <= epoch < phase.end_epoch:
                if phase.learning_rate_override is not None:
                    learning_rate = phase.learning_rate_override
                break

        if learning_rate is None:
            learning_rate = get_learning_rate(
                epoch,
                self.config.epochs,
                self.config.learning_rate,
            )

        # Get loss weights
        loss_weights = get_curriculum_weights(
            epoch,
            self.config.curriculum_phases,
            self.default_weights,
        )

        return {
            "temperature": temperature,
            "learning_rate": learning_rate,
            "loss_weights": loss_weights,
            "phase_name": phase_name,
        }
