"""
Core training loop for placement optimization.

This module implements the main training function that orchestrates:
- Position and rotation initialization
- Adam optimizer setup via optax
- Gumbel-Softmax rotation sampling
- Loss computation and gradient updates
- Temperature and learning rate annealing
- Checkpointing and early stopping
- Metrics logging

The training loop is designed to be:
- JAX-compatible with JIT compilation for performance
- Resumable from checkpoints
- Observable via callbacks for visualization
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

import jax
import jax.numpy as jnp
from jax import Array
import optax

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.geometry.transform import sample_rotation_batch
from temper_placer.losses.base import (
    CompositeLoss,
    LossContext,
    WeightedLoss,
    create_value_and_grad_fn,
)
from temper_placer.optimizer.config import OptimizerConfig
from temper_placer.optimizer.scheduler import (
    get_temperature,
    get_learning_rate,
    ScheduleState,
)
from temper_placer.optimizer.validation_callback import (
    ValidationCallback,
    ValidationResult,
)


class TrainingMetrics(NamedTuple):
    """Metrics from a single training epoch."""

    epoch: int
    loss: float
    temperature: float
    learning_rate: float
    loss_breakdown: Dict[str, float]
    grad_norm_pos: float
    grad_norm_rot: float
    elapsed_ms: float


@dataclass
class TrainingResult:
    """
    Result from training run.

    Attributes:
        final_state: Final placement state after optimization.
        final_loss: Final loss value.
        best_state: Best placement state by loss (if early stopping enabled).
        best_loss: Best loss value achieved.
        history: List of TrainingMetrics for each logged epoch.
        total_epochs: Number of epochs run.
        converged: Whether training converged (early stopping triggered).
        elapsed_seconds: Total training time.
        validation_history: List of ValidationResult from validation runs.
        stopped_by_validation: Whether training stopped due to validation failure.
    """

    final_state: PlacementState
    final_loss: float
    best_state: Optional[PlacementState] = None
    best_loss: float = float("inf")
    history: List[TrainingMetrics] = field(default_factory=list)
    total_epochs: int = 0
    converged: bool = False
    elapsed_seconds: float = 0.0
    validation_history: List[ValidationResult] = field(default_factory=list)
    stopped_by_validation: bool = False


@dataclass
class TrainingState:
    """
    Internal state during training.

    This is separate from PlacementState to track optimizer state,
    rotation logits (for Gumbel-Softmax), and training progress.
    """

    positions: Array  # (N, 2)
    rotation_logits: Array  # (N, 4) - learnable parameters
    opt_state_pos: Any  # optax optimizer state for positions
    opt_state_rot: Any  # optax optimizer state for rotations
    rng_key: Array  # JAX random key
    epoch: int = 0
    best_loss: float = float("inf")
    best_positions: Optional[Array] = None
    best_rotations: Optional[Array] = None
    epochs_without_improvement: int = 0


def create_optimizer(
    config: OptimizerConfig,
    initial_lr: float,
) -> Tuple[optax.GradientTransformation, optax.GradientTransformation]:
    """
    Create optax optimizers for positions and rotations.

    Uses Adam by default with optional gradient clipping.

    Args:
        config: Optimizer configuration.
        initial_lr: Initial learning rate.

    Returns:
        Tuple of (position_optimizer, rotation_optimizer).
    """
    # Build optimizer chain
    transforms = []

    # Gradient clipping (if enabled)
    if config.gradient_clip_norm is not None:
        transforms.append(optax.clip_by_global_norm(config.gradient_clip_norm))

    # Adam or SGD
    if config.use_adam:
        transforms.append(
            optax.adam(
                learning_rate=initial_lr,
                b1=config.adam_beta1,
                b2=config.adam_beta2,
            )
        )
    else:
        transforms.append(optax.sgd(learning_rate=initial_lr))

    optimizer = optax.chain(*transforms)

    # Use same optimizer for both, but they could be different
    return optimizer, optimizer


def initialize_training_state(
    netlist: Netlist,
    board: Board,
    config: OptimizerConfig,
    initial_state: Optional[PlacementState] = None,
) -> TrainingState:
    """
    Initialize training state with positions and rotation logits.

    Args:
        netlist: Component netlist.
        board: Board definition.
        config: Optimizer configuration.
        initial_state: Optional initial placement to start from.

    Returns:
        Initialized TrainingState.
    """
    rng_key = jax.random.PRNGKey(config.seed)

    if initial_state is not None:
        # Start from provided initial state
        positions = initial_state.positions
        rotation_logits = initial_state.rotation_logits
    else:
        # Random initialization
        rng_key, init_key = jax.random.split(rng_key)
        state = PlacementState.random_init(
            n_components=netlist.n_components,
            board_width=board.width,
            board_height=board.height,
            key=init_key,
        )
        positions = state.positions
        # Start with uniform logits (equal probability for all rotations)
        rotation_logits = jnp.zeros((netlist.n_components, 4))

    # Create optimizers
    initial_lr = config.learning_rate.initial
    opt_pos, opt_rot = create_optimizer(config, initial_lr)

    # Initialize optimizer states
    opt_state_pos = opt_pos.init(positions)
    opt_state_rot = opt_rot.init(rotation_logits)

    return TrainingState(
        positions=positions,
        rotation_logits=rotation_logits,
        opt_state_pos=opt_state_pos,
        opt_state_rot=opt_state_rot,
        rng_key=rng_key,
        epoch=0,
    )


def make_train_step(
    value_and_grad_fn: Callable,
    opt_pos: optax.GradientTransformation,
    opt_rot: optax.GradientTransformation,
    total_epochs: int,
):
    """
    Create a JIT-compiled training step function.

    Args:
        value_and_grad_fn: Function returning (loss, (grad_pos, grad_rot)).
        opt_pos: Position optimizer.
        opt_rot: Rotation optimizer.
        total_epochs: Total training epochs (for curriculum).

    Returns:
        JIT-compiled train_step function.
    """

    @jax.jit
    def train_step(
        positions: Array,
        rotation_logits: Array,
        rotations: Array,
        opt_state_pos: Any,
        opt_state_rot: Any,
        epoch: int,
    ) -> Tuple[Array, Array, Array, Any, Any, Array, Array]:
        """
        Single training step.

        Args:
            positions: Current positions (N, 2).
            rotation_logits: Current rotation logits (N, 4).
            rotations: Sampled rotations (N, 4) one-hot.
            opt_state_pos: Position optimizer state.
            opt_state_rot: Rotation optimizer state.
            epoch: Current epoch.

        Returns:
            Tuple of (new_positions, new_logits, loss, new_opt_state_pos,
                     new_opt_state_rot, grad_pos, grad_rot).
        """
        # Compute loss and gradients
        loss, (grad_pos, grad_rot) = value_and_grad_fn(positions, rotations, epoch, total_epochs)

        # Update positions
        updates_pos, new_opt_state_pos = opt_pos.update(grad_pos, opt_state_pos, positions)
        new_positions = optax.apply_updates(positions, updates_pos)

        # Update rotation logits
        updates_rot, new_opt_state_rot = opt_rot.update(grad_rot, opt_state_rot, rotation_logits)
        new_rotation_logits = optax.apply_updates(rotation_logits, updates_rot)

        return (
            new_positions,
            new_rotation_logits,
            loss,
            new_opt_state_pos,
            new_opt_state_rot,
            grad_pos,
            grad_rot,
        )

    return train_step


def train(
    netlist: Netlist,
    board: Board,
    composite_loss: CompositeLoss,
    context: LossContext,
    config: Optional[OptimizerConfig] = None,
    initial_state: Optional[PlacementState] = None,
    callback: Optional[Callable[[TrainingMetrics], None]] = None,
    validation_callback: Optional[ValidationCallback] = None,
) -> TrainingResult:
    """
    Run placement optimization training loop.

    This is the main entry point for training. It:
    1. Initializes positions and rotation logits
    2. Creates Adam optimizers
    3. Runs the training loop with Gumbel-Softmax rotation sampling
    4. Anneals temperature and learning rate
    5. Tracks best solution and handles early stopping
    6. Optionally runs validation (DRC) at configured intervals
    7. Returns final and best placement states

    Args:
        netlist: Component netlist to place.
        board: Board definition with dimensions and zones.
        composite_loss: CompositeLoss with weighted loss functions.
        context: LossContext with pre-computed arrays.
        config: Optimizer configuration (uses defaults if None).
        initial_state: Optional initial placement to refine.
        callback: Optional function called after each logged epoch.
        validation_callback: Optional ValidationCallback for DRC/SPICE validation.

    Returns:
        TrainingResult with final placement and training history.

    Example:
        >>> config = OptimizerConfig.fast_test()
        >>> composite = CompositeLoss([
        ...     WeightedLoss(OverlapLoss(), weight=100.0),
        ...     WeightedLoss(BoundaryLoss(), weight=50.0),
        ... ])
        >>> context = LossContext.from_netlist_and_board(netlist, board)
        >>> result = train(netlist, board, composite, context, config)
        >>> print(f"Final loss: {result.final_loss:.4f}")
    """
    if config is None:
        config = OptimizerConfig()

    start_time = time.time()

    # Initialize training state
    state = initialize_training_state(netlist, board, config, initial_state)

    # Create value_and_grad function
    value_and_grad_fn = create_value_and_grad_fn(composite_loss, context)

    # Create optimizers
    initial_lr = config.learning_rate.initial
    opt_pos, opt_rot = create_optimizer(config, initial_lr)

    # Re-initialize optimizer states (in case lr changed)
    state.opt_state_pos = opt_pos.init(state.positions)
    state.opt_state_rot = opt_rot.init(state.rotation_logits)

    # Create JIT-compiled train step
    train_step = make_train_step(value_and_grad_fn, opt_pos, opt_rot, config.epochs)

    # Training history
    history: List[TrainingMetrics] = []

    # Validation tracking
    validation_history: List[ValidationResult] = []
    stopped_by_validation = False

    # Best tracking
    best_loss = float("inf")
    best_positions = state.positions
    best_rotations = jnp.eye(4)[jnp.zeros(netlist.n_components, dtype=jnp.int32)]
    epochs_without_improvement = 0

    # Main training loop
    for epoch in range(config.epochs):
        epoch_start = time.time()

        # Get current temperature
        temperature = get_temperature(epoch, config.epochs, config.temperature)

        # Sample rotations using Gumbel-Softmax
        state.rng_key, sample_key = jax.random.split(state.rng_key)
        rotations = sample_rotation_batch(state.rotation_logits, sample_key, temperature)

        # Run training step
        (
            new_positions,
            new_rotation_logits,
            loss,
            new_opt_state_pos,
            new_opt_state_rot,
            grad_pos,
            grad_rot,
        ) = train_step(
            state.positions,
            state.rotation_logits,
            rotations,
            state.opt_state_pos,
            state.opt_state_rot,
            epoch,
        )

        # Update state
        state.positions = new_positions
        state.rotation_logits = new_rotation_logits
        state.opt_state_pos = new_opt_state_pos
        state.opt_state_rot = new_opt_state_rot

        loss_value = float(loss)

        # Track best
        if loss_value < best_loss - config.early_stopping.min_delta:
            best_loss = loss_value
            best_positions = state.positions
            best_rotations = rotations
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        # Log metrics at intervals
        if epoch % config.log_interval == 0 or epoch == config.epochs - 1:
            lr = get_learning_rate(epoch, config.epochs, config.learning_rate)

            # Compute gradient norms
            grad_norm_pos = float(jnp.linalg.norm(grad_pos))
            grad_norm_rot = float(jnp.linalg.norm(grad_rot))

            # Get loss breakdown
            result = composite_loss(state.positions, rotations, context, epoch, config.epochs)
            breakdown = {k: float(v) for k, v in (result.breakdown or {}).items()}

            epoch_time_ms = (time.time() - epoch_start) * 1000

            metrics = TrainingMetrics(
                epoch=epoch,
                loss=loss_value,
                temperature=temperature,
                learning_rate=lr,
                loss_breakdown=breakdown,
                grad_norm_pos=grad_norm_pos,
                grad_norm_rot=grad_norm_rot,
                elapsed_ms=epoch_time_ms,
            )
            history.append(metrics)

            if callback is not None:
                callback(metrics)

        # Run validation callback (if configured)
        if validation_callback is not None:
            validation_result = validation_callback(
                epoch=epoch,
                positions=state.positions,
                rotations=rotations,
                context=context,
            )
            if validation_result is not None:
                validation_history.append(validation_result)
                # Check if validation failed and we should stop
                if not validation_result.passed:
                    stopped_by_validation = True
                    break

        # Early stopping check
        if (
            config.early_stopping.enabled
            and epochs_without_improvement >= config.early_stopping.patience
        ):
            break

    # Create final placement state
    final_state = PlacementState(
        positions=state.positions,
        rotation_logits=state.rotation_logits,
    )

    # Create best placement state - convert best_rotations (one-hot) back to logits
    # Use high values for the selected rotation
    best_rotation_logits = jnp.where(
        best_rotations > 0.5,
        jnp.ones_like(best_rotations) * 5.0,  # High logit for selected
        jnp.zeros_like(best_rotations),  # Zero for others
    )
    best_state = PlacementState(
        positions=best_positions,
        rotation_logits=best_rotation_logits,
    )

    elapsed = time.time() - start_time

    return TrainingResult(
        final_state=final_state,
        final_loss=float(loss),
        best_state=best_state,
        best_loss=best_loss,
        history=history,
        total_epochs=epoch + 1,
        converged=epochs_without_improvement >= config.early_stopping.patience,
        elapsed_seconds=elapsed,
        validation_history=validation_history,
        stopped_by_validation=stopped_by_validation,
    )


def train_multiphase(
    netlist: Netlist,
    board: Board,
    loss_factory: Callable[[Dict[str, float]], CompositeLoss],
    context: LossContext,
    config: Optional[OptimizerConfig] = None,
    initial_state: Optional[PlacementState] = None,
    callback: Optional[Callable[[TrainingMetrics], None]] = None,
    validation_callback: Optional[ValidationCallback] = None,
) -> TrainingResult:
    """
    Run multi-phase training with curriculum learning.

    This variant supports changing loss weights during training based on
    curriculum phases. It re-creates the CompositeLoss at phase transitions.

    Args:
        netlist: Component netlist.
        board: Board definition.
        loss_factory: Function that creates CompositeLoss from weight dict.
        context: LossContext with pre-computed arrays.
        config: Optimizer configuration with curriculum_phases.
        initial_state: Optional initial placement.
        callback: Optional callback for metrics.
        validation_callback: Optional ValidationCallback for DRC/SPICE validation.

    Returns:
        TrainingResult with final placement.

    Example:
        >>> def make_loss(weights):
        ...     return CompositeLoss([
        ...         WeightedLoss(OverlapLoss(), weight=weights.get("overlap", 100.0)),
        ...         WeightedLoss(BoundaryLoss(), weight=weights.get("boundary", 50.0)),
        ...     ])
        >>> config = OptimizerConfig.default_curriculum()
        >>> result = train_multiphase(netlist, board, make_loss, context, config)
    """
    if config is None:
        config = OptimizerConfig.default_curriculum()

    from temper_placer.optimizer.scheduler import get_curriculum_weights
    from temper_placer.optimizer.config import get_default_loss_weights

    default_weights = get_default_loss_weights()

    start_time = time.time()

    # Initialize training state
    state = initialize_training_state(netlist, board, config, initial_state)

    # Training history
    history: List[TrainingMetrics] = []

    # Validation tracking
    validation_history: List[ValidationResult] = []
    stopped_by_validation = False

    # Best tracking
    best_loss = float("inf")
    best_positions = state.positions
    best_rotations = jnp.eye(4)[jnp.zeros(netlist.n_components, dtype=jnp.int32)]
    epochs_without_improvement = 0

    # Track current phase for re-creating loss function
    current_phase_idx = -1

    # Main training loop
    for epoch in range(config.epochs):
        epoch_start = time.time()

        # Check if we need to update loss weights (phase change)
        new_phase_idx = -1
        for i, phase in enumerate(config.curriculum_phases):
            if phase.start_epoch <= epoch < phase.end_epoch:
                new_phase_idx = i
                break

        # Recreate loss and optimizer if phase changed
        if new_phase_idx != current_phase_idx:
            current_phase_idx = new_phase_idx

            # Get current weights
            weights = get_curriculum_weights(epoch, config.curriculum_phases, default_weights)

            # Create new composite loss
            composite_loss = loss_factory(weights)

            # Create new value_and_grad function
            value_and_grad_fn = create_value_and_grad_fn(composite_loss, context)

            # Create optimizers with current learning rate
            lr = get_learning_rate(epoch, config.epochs, config.learning_rate)
            opt_pos, opt_rot = create_optimizer(config, lr)

            # Create new train step
            train_step = make_train_step(value_and_grad_fn, opt_pos, opt_rot, config.epochs)

            # Re-initialize optimizer states
            state.opt_state_pos = opt_pos.init(state.positions)
            state.opt_state_rot = opt_rot.init(state.rotation_logits)

        # Get current temperature
        temperature = get_temperature(epoch, config.epochs, config.temperature)

        # Sample rotations
        state.rng_key, sample_key = jax.random.split(state.rng_key)
        rotations = sample_rotation_batch(state.rotation_logits, sample_key, temperature)

        # Run training step
        (
            new_positions,
            new_rotation_logits,
            loss,
            new_opt_state_pos,
            new_opt_state_rot,
            grad_pos,
            grad_rot,
        ) = train_step(
            state.positions,
            state.rotation_logits,
            rotations,
            state.opt_state_pos,
            state.opt_state_rot,
            epoch,
        )

        # Update state
        state.positions = new_positions
        state.rotation_logits = new_rotation_logits
        state.opt_state_pos = new_opt_state_pos
        state.opt_state_rot = new_opt_state_rot

        loss_value = float(loss)

        # Track best
        if loss_value < best_loss - config.early_stopping.min_delta:
            best_loss = loss_value
            best_positions = state.positions
            best_rotations = rotations
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        # Log metrics
        if epoch % config.log_interval == 0 or epoch == config.epochs - 1:
            lr = get_learning_rate(epoch, config.epochs, config.learning_rate)
            grad_norm_pos = float(jnp.linalg.norm(grad_pos))
            grad_norm_rot = float(jnp.linalg.norm(grad_rot))

            result = composite_loss(state.positions, rotations, context, epoch, config.epochs)
            breakdown = {k: float(v) for k, v in (result.breakdown or {}).items()}

            epoch_time_ms = (time.time() - epoch_start) * 1000

            metrics = TrainingMetrics(
                epoch=epoch,
                loss=loss_value,
                temperature=temperature,
                learning_rate=lr,
                loss_breakdown=breakdown,
                grad_norm_pos=grad_norm_pos,
                grad_norm_rot=grad_norm_rot,
                elapsed_ms=epoch_time_ms,
            )
            history.append(metrics)

            if callback is not None:
                callback(metrics)

        # Run validation callback (if configured)
        if validation_callback is not None:
            validation_result = validation_callback(
                epoch=epoch,
                positions=state.positions,
                rotations=rotations,
                context=context,
            )
            if validation_result is not None:
                validation_history.append(validation_result)
                # Check if validation failed and we should stop
                if not validation_result.passed:
                    stopped_by_validation = True
                    break

        # Early stopping
        if (
            config.early_stopping.enabled
            and epochs_without_improvement >= config.early_stopping.patience
        ):
            break

    # Create final states
    final_state = PlacementState(
        positions=state.positions,
        rotation_logits=state.rotation_logits,
    )

    # Convert best_rotations (one-hot) back to logits
    best_rotation_logits = jnp.where(
        best_rotations > 0.5,
        jnp.ones_like(best_rotations) * 5.0,
        jnp.zeros_like(best_rotations),
    )
    best_state = PlacementState(
        positions=best_positions,
        rotation_logits=best_rotation_logits,
    )

    elapsed = time.time() - start_time

    return TrainingResult(
        final_state=final_state,
        final_loss=float(loss),
        best_state=best_state,
        best_loss=best_loss,
        history=history,
        total_epochs=epoch + 1,
        converged=epochs_without_improvement >= config.early_stopping.patience,
        elapsed_seconds=elapsed,
        validation_history=validation_history,
        stopped_by_validation=stopped_by_validation,
    )
