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

import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import jax
import jax.numpy as jnp
import optax
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.geometry.transform import sample_rotation_batch
from temper_placer.losses.base import (
    CompositeLoss,
    LossContext,
    create_value_and_grad_fn_with_breakdown,
)
from temper_placer.optimizer.config import OptimizerConfig
from temper_placer.optimizer.initialization import SpectralInitializer
from temper_placer.optimizer.scheduler import (
    get_learning_rate,
    get_temperature,
)
from temper_placer.optimizer.validation_callback import (
    ValidationCallback,
    ValidationResult,
)


class NumericalInstabilityError(RuntimeError):
    """Raised when training encounters NaN or Inf values.

    This indicates a numerical instability in the loss function or gradients,
    often caused by:
    - Learning rate too high
    - Temperature too low (Gumbel-Softmax overflow)
    - Invalid input data (e.g., zero-size components)
    - Loss function overflow (e.g., large_val in wirelength)

    Attributes:
        epoch: The epoch where instability was detected.
        loss_value: The problematic loss value (may be NaN or Inf).
        loss_breakdown: Per-loss values to identify the source.
        grad_norms: Gradient norms if available.
    """

    def __init__(
        self,
        message: str,
        epoch: int = -1,
        loss_value: float = float("nan"),
        loss_breakdown: dict[str, float] | None = None,
        grad_norms: dict[str, float] | None = None,
    ):
        super().__init__(message)
        self.epoch = epoch
        self.loss_value = loss_value
        self.loss_breakdown = loss_breakdown or {}
        self.grad_norms = grad_norms or {}


def _check_numerical_stability(
    loss_value: float,
    loss_breakdown: dict[str, Any],
    grad_pos: Array,
    grad_rot: Array,
    epoch: int,
) -> None:
    """Check for NaN/Inf in loss and gradients, raise if found.

    Args:
        loss_value: Total loss value.
        loss_breakdown: Per-loss component values (may contain arrays).
        grad_pos: Position gradients.
        grad_rot: Rotation gradients.
        epoch: Current epoch for error reporting.

    Raises:
        NumericalInstabilityError: If any value is NaN or Inf.
    """
    import math

    # Check total loss
    if not math.isfinite(loss_value):
        # Find which loss component caused the issue
        bad_components = []
        for name, val in loss_breakdown.items():
            if not jnp.all(jnp.isfinite(val)):
                bad_components.append(name)

        raise NumericalInstabilityError(
            f"Non-finite loss at epoch {epoch}: {loss_value}. "
            f"Problematic components: {bad_components if bad_components else 'unknown (overflow in combination)'}",
            epoch=epoch,
            loss_value=loss_value,
            loss_breakdown={k: float(jnp.sum(v)) if hasattr(v, "shape") and v.shape else float(v)
                           for k, v in loss_breakdown.items()},
            grad_norms={"position": float(jnp.linalg.norm(grad_pos)),
                        "rotation": float(jnp.linalg.norm(grad_rot))},
        )

    # Check gradients
    grad_norm_pos = float(jnp.linalg.norm(grad_pos))
    grad_norm_rot = float(jnp.linalg.norm(grad_rot))

    if not math.isfinite(grad_norm_pos) or not math.isfinite(grad_norm_rot):
        raise NumericalInstabilityError(
            f"Non-finite gradients at epoch {epoch}: "
            f"grad_pos_norm={grad_norm_pos}, grad_rot_norm={grad_norm_rot}",
            epoch=epoch,
            loss_value=loss_value,
            loss_breakdown={k: float(jnp.sum(v)) if hasattr(v, "shape") and v.shape else float(v)
                           for k, v in loss_breakdown.items()},
            grad_norms={"position": grad_norm_pos, "rotation": grad_norm_rot},
        )


class TrainingMetrics(NamedTuple):
    """Metrics from a single training epoch."""

    epoch: int
    loss: float
    temperature: float
    learning_rate: float
    loss_breakdown: dict[str, float]
    grad_norm_pos: float
    grad_norm_rot: float
    elapsed_ms: float
    loss_weights: dict[str, float] | None = None


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
    best_state: PlacementState | None = None
    best_loss: float = float("inf")
    history: list[TrainingMetrics] = field(default_factory=list)
    total_epochs: int = 0
    converged: bool = False
    elapsed_seconds: float = 0.0
    validation_history: list[ValidationResult] = field(default_factory=list)
    stopped_by_validation: bool = False
    final_overlap_weights: Array | None = None


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
    best_positions: Array | None = None
    best_rotations: Array | None = None
    epochs_without_improvement: int = 0
    position_delta_ema: float = 1.0  # EMA of component movement norm
    overlap_weights: Array | None = None  # (N,) adaptive multipliers
    loss_weights: Array | None = None  # (L,) dynamic loss weights
    initial_grad_norms: Array | None = None  # (L,) initial gradient norms for GradNorm


def create_optimizer(
    config: OptimizerConfig,
    initial_lr: float,
) -> tuple[optax.GradientTransformation, optax.GradientTransformation]:
    """
    Create optax optimizers for positions and rotations.

    Uses Adam by default with optional gradient clipping. Learning rate is
    injected as a hyperparameter so it can be updated during training.

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

    # Make learning rate injectable
    # We must wrap the chain to ensure it's a simple GradientTransformation
    # that inject_hyperparams can handle.
    # Note: inject_hyperparams passes params as keyword args.
    optimizer = optax.inject_hyperparams(lambda **kwargs: optax.chain(*transforms))()

    # Use same optimizer for both, but they could be different
    return optimizer, optimizer


def initialize_training_state(
    netlist: Netlist,
    board: Board,
    config: OptimizerConfig,
    initial_state: PlacementState | None = None,
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

    Note:
        When initial_state is None, random positions are generated in ABSOLUTE
        coordinates using board.origin. This ensures compatibility with KiCad
        PCB files where the board is not at (0, 0).
    """
    rng_key = jax.random.PRNGKey(config.seed)

    if initial_state is not None:
        # Start from provided initial state
        positions = initial_state.positions
        rotation_logits = initial_state.rotation_logits
    else:
        # Use configured initialization method
        if config.initialization.method == "spectral":
            initializer = SpectralInitializer(
                normalized_laplacian=config.initialization.spectral_normalized,
                margin_fraction=config.initialization.spectral_margin,
            )
            positions = initializer.initialize(netlist, board)
        else:
            # Default: Random initialization in absolute coordinates
            rng_key, init_key = jax.random.split(rng_key)
            state = PlacementState.random_init(
                n_components=netlist.n_components,
                board_width=board.width,
                board_height=board.height,
                key=init_key,
                origin=board.origin,  # Use board origin for absolute coordinates
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
        overlap_weights=jnp.ones((netlist.n_components,), dtype=jnp.float32),
        loss_weights=jnp.ones((1,), dtype=jnp.float32),  # Placeholder, will be resized if needed
        initial_grad_norms=jnp.ones((1,), dtype=jnp.float32),
    )


def make_train_step(
    value_and_grad_fn: Callable,
    opt_pos: optax.GradientTransformation,
    opt_rot: optax.GradientTransformation,
    total_epochs: int,
    centrality: Array | None = None,
    priority_scale: float = 1.0,
    use_grad_norm: bool = False,
    grad_norm_alpha: float = 1.5,
    grad_norm_lr: float = 0.025,
    composite_loss: CompositeLoss | None = None,
    loss_context: LossContext | None = None,
):
    """
    Create a JIT-compiled training step function.

    Args:
        value_and_grad_fn: Function returning ((loss, breakdown), (grad_pos, grad_rot)).
        opt_pos: Position optimizer.
        opt_rot: Rotation optimizer.
        total_epochs: Total training epochs (for curriculum).
        centrality: Optional (N,) array of component centralities.
        priority_scale: Max boost for hub components (1.0 = none).
        use_grad_norm: Whether to use GradNorm adaptive weighting.
        grad_norm_alpha: Asymmetry parameter for GradNorm.
        grad_norm_lr: Learning rate for weight updates.
        composite_loss: Required if use_grad_norm is True.
        loss_context: Required if use_grad_norm is True.

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
        learning_rate: float,
        position_delta_ema: float,
        overlap_weights: Array,
        loss_weights: Array,
        initial_grad_norms: Array,
    ) -> tuple[Array, Array, Array, dict[str, Array], Any, Any, Array, Array, float, Array, Array]:
        """
        Single training step.

        Args:
            positions: Current positions (N, 2).
            rotation_logits: Current rotation logits (N, 4).
            rotations: Sampled rotations (N, 4) one-hot.
            opt_state_pos: Position optimizer state.
            opt_state_rot: Rotation optimizer state.
            epoch: Current epoch.
            learning_rate: Current learning rate to apply.
            position_delta_ema: Current EMA of position updates.
            overlap_weights: Per-component adaptive overlap weights.
            loss_weights: Current (L,) dynamic loss weights.
            initial_grad_norms: (L,) initial gradient norms for GradNorm.

        Returns:
            Tuple of (new_positions, new_logits, loss, breakdown,
                     new_opt_state_pos, new_opt_state_rot, grad_pos, grad_rot,
                     new_ema, new_loss_weights, new_initial_grad_norms).
        """
        # Update learning rate in optimizer state
        new_opt_state_pos = opt_state_pos._replace(
            hyperparams={**opt_state_pos.hyperparams, "learning_rate": learning_rate}
        )
        new_opt_state_rot = opt_state_rot._replace(
            hyperparams={**opt_state_rot.hyperparams, "learning_rate": learning_rate}
        )

        # Compute loss and gradients
        if use_grad_norm and composite_loss is not None and loss_context is not None:
            # GradNorm requires gradients of individual loss terms
            # We compute gradients for each loss i: w_i * L_i

            def get_individual_loss(i, pos, rot):
                # Use jax.lax.switch to handle traced index i
                def make_loss_thunk(wloss_idx):
                    def thunk(p_r):
                        pos_in, rot_in = p_r
                        wloss = composite_loss.losses[wloss_idx]
                        res = wloss.loss_fn(pos_in, rot_in, loss_context, epoch, total_epochs)
                        return res.value / wloss.get_normalizer(loss_context)
                    return thunk

                thunks = [make_loss_thunk(idx) for idx in range(len(composite_loss.losses))]
                return jax.lax.switch(i, thunks, (pos, rot))

            # Compute individual gradients and their norms
            # Note: This is computationally expensive, but needed for GradNorm
            n_losses = len(composite_loss.losses)

            def get_grad_norm(i):
                # Gradient w.r.t. positions (index 1 of get_individual_loss call)
                # We use argnums=1 to differentiate w.r.t pos
                # But rotations also matter, so we use jax.grad(..., argnums=(1, 2))
                # or just (1,) if we only care about position gradients for balancing.
                # Standard GradNorm usually uses the norm of the gradient w.r.t shared parameters.
                grad_fn = jax.grad(get_individual_loss, argnums=1)
                g = grad_fn(i, positions, rotations)
                # Apply fixed mask to match total gradient behavior
                g = jnp.where(loss_context.fixed_mask[:, None], 0.0, g)
                return jnp.linalg.norm(g)

            curr_grad_norms = jax.vmap(get_grad_norm)(jnp.arange(n_losses))

            # Update initial norms at epoch 0
            new_initial_grad_norms = jnp.where(
                epoch == 0,
                curr_grad_norms,
                initial_grad_norms
            )
            # Avoid division by zero
            new_initial_grad_norms = jnp.maximum(new_initial_grad_norms, 1e-6)

            # Compute total loss and breakdown using current dynamic weights
            (loss, breakdown), (grad_pos, grad_rot) = value_and_grad_fn(
                positions, rotations, epoch, total_epochs, loss_weights
            )

            # GradNorm weight update
            # 1. Compute relative losses: r_i(t) = L_i(t) / L_i(0)
            # We use moving average or initial loss. For simplicity, we'll use a fixed baseline.
            # But since L_i is dynamic, we'll track initial losses.
            # Actually, standard GradNorm uses L_i(t) / E[L_i(0)]
            # We'll simplify: use relative improvement if possible, or just raw loss ratios.

            loss_values = jnp.array([breakdown.get(f"{name}_normalized", 0.0)
                                   for name in composite_loss.loss_names])

            # 2. Compute target norms: G_avg(t) * [r_i(t)]^alpha
            # where G_avg is mean of weighted gradient norms
            gw_norms = loss_weights * curr_grad_norms
            g_avg = jnp.mean(gw_norms)

            # For relative losses, we need a baseline. Let's use epoch 0 losses.
            # Since we don't track initial losses in state yet, we'll use a constant or simplified ratio.
            # Standard GradNorm: r_i = L_i / L_i_init
            # We'll use relative loss magnitudes for now.
            relative_losses = loss_values / jnp.maximum(jnp.mean(loss_values), 1e-6)
            inv_relative_losses = relative_losses / jnp.maximum(jnp.mean(relative_losses), 1e-6)

            target_norms = g_avg * jnp.power(inv_relative_losses, grad_norm_alpha)

            # 3. Update weights via gradient descent on L_grad = sum |w_i * G_i - target_i|
            # We'll do a simple step here
            jnp.abs(gw_norms - target_norms)

            # Update weights: w = w - lr * grad_L_grad(w)
            # grad(L_grad) w.r.t w_i is sign(w_i * G_i - target_i) * G_i
            weight_grads = jnp.sign(gw_norms - target_norms) * curr_grad_norms
            new_loss_weights = loss_weights - grad_norm_lr * weight_grads

            # Post-update: Normalize weights to sum to n_losses (keep overall scale)
            new_loss_weights = jnp.maximum(new_loss_weights, 1e-3)
            new_loss_weights = new_loss_weights * (n_losses / jnp.sum(new_loss_weights))

        else:
            # Standard training
            (loss, breakdown), (grad_pos, grad_rot) = value_and_grad_fn(
                positions, rotations, epoch, total_epochs
            )
            new_loss_weights = loss_weights
            new_initial_grad_norms = initial_grad_norms

        # Apply adaptive overlap weighting to gradients
        grad_pos = grad_pos * overlap_weights[:, None]
        grad_rot = grad_rot * overlap_weights[:, None]

        # Apply centrality-based gradient scaling (Inertia/Priority)
        if centrality is not None and centrality.shape[0] > 0 and priority_scale > 1.0:
            c_min = jnp.min(centrality)
            c_max = jnp.max(centrality)
            c_range = jnp.where(c_max - c_min < 1e-10, 1.0, c_max - c_min)
            normalized_c = (centrality - c_min) / c_range
            grad_scale = 1.0 + (priority_scale - 1.0) * normalized_c

            grad_pos = grad_pos * grad_scale[:, None]
            grad_rot = grad_rot * grad_scale[:, None]

        # Update positions and rotations
        updates_pos, next_opt_state_pos = opt_pos.update(grad_pos, new_opt_state_pos, positions)
        new_positions = optax.apply_updates(positions, updates_pos)

        updates_rot, next_opt_state_rot = opt_rot.update(grad_rot, new_opt_state_rot, rotation_logits)
        new_rotation_logits = optax.apply_updates(rotation_logits, updates_rot)

        # Compute movement norm and update EMA
        update_norm = jnp.linalg.norm(new_positions - positions)
        new_ema = 0.9 * position_delta_ema + 0.1 * update_norm

        return (
            new_positions,
            new_rotation_logits,
            loss,
            breakdown,
            next_opt_state_pos,
            next_opt_state_rot,
            grad_pos,
            grad_rot,
            new_ema,
            new_loss_weights,
            new_initial_grad_norms,
        )

    return train_step

    return train_step


def train(
    netlist: Netlist,
    board: Board,
    composite_loss: CompositeLoss,
    context: LossContext,
    config: OptimizerConfig | None = None,
    initial_state: PlacementState | None = None,
    callback: Callable[[TrainingMetrics], None] | None = None,
    validation_callback: ValidationCallback | None = None,
    profile_dir: str | None = None,
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
        profile_dir: If provided, save JAX profiler trace to this directory.

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

    # Initialize dynamic loss weights for GradNorm
    n_losses = len(composite_loss.losses)
    state.loss_weights = jnp.ones((n_losses,), dtype=jnp.float32)
    state.initial_grad_norms = jnp.zeros((n_losses,), dtype=jnp.float32)

    # Create value_and_grad function with breakdown
    value_and_grad_fn = create_value_and_grad_fn_with_breakdown(composite_loss, context)

    # Create optimizers
    initial_lr = config.learning_rate.initial
    opt_pos, opt_rot = create_optimizer(config, initial_lr)

    # Re-initialize optimizer states (in case lr changed)
    state.opt_state_pos = opt_pos.init(state.positions)
    state.opt_state_rot = opt_rot.init(state.rotation_logits)

    # Create JIT-compiled train step
    centrality = context.centrality if config.use_centrality_weighting else None
    train_step = make_train_step(
        value_and_grad_fn,
        opt_pos,
        opt_rot,
        config.epochs,
        centrality=centrality,
        priority_scale=config.centrality_priority_scale,
        use_grad_norm=config.use_grad_norm,
        grad_norm_alpha=config.grad_norm.alpha,
        grad_norm_lr=config.grad_norm.learning_rate,
        composite_loss=composite_loss,
        loss_context=context,
    )

    # Optional: Enable JAX profiler
    profile_ctx = (
        jax.profiler.trace(profile_dir) if profile_dir else contextlib.nullcontext()
    )

    # Training history
    history: list[TrainingMetrics] = []

    # Validation tracking
    validation_history: list[ValidationResult] = []
    stopped_by_validation = False

    # Best tracking
    best_loss = float("inf")
    best_positions = state.positions
    best_rotations = jnp.eye(4)[jnp.zeros(netlist.n_components, dtype=jnp.int32)]
    epochs_without_improvement = 0

    # Main training loop
    with profile_ctx:
        for epoch in range(config.epochs):
            epoch_start = time.time()

            # Get current temperature and learning rate
            temperature = get_temperature(epoch, config.epochs, config.temperature)
            lr = get_learning_rate(epoch, config.epochs, config.learning_rate)

            # Sample rotations using Gumbel-Softmax
            state.rng_key, sample_key = jax.random.split(state.rng_key)
            if config.use_gumbel_rotation:
                rotations = sample_rotation_batch(state.rotation_logits, sample_key, temperature)
            else:
                # Use hard rotations (argmax of logits)
                rotations = sample_rotation_batch(state.rotation_logits, sample_key, 1e-5)

            # Run training step (returns breakdown alongside loss to avoid recomputation)
            (
                new_positions,
                new_rotation_logits,
                loss,
                loss_breakdown_arrays,
                new_opt_state_pos,
                new_opt_state_rot,
                grad_pos,
                grad_rot,
                new_ema,
                new_loss_weights,
                new_initial_grad_norms,
            ) = train_step(
                state.positions,
                state.rotation_logits,
                rotations,
                state.opt_state_pos,
                state.opt_state_rot,
                epoch,
                lr,
                state.position_delta_ema,
                state.overlap_weights,
                state.loss_weights,
                state.initial_grad_norms,
            )

            # Update state
            state.positions = new_positions
            state.rotation_logits = new_rotation_logits
            state.opt_state_pos = new_opt_state_pos
            state.opt_state_rot = new_opt_state_rot
            state.position_delta_ema = float(new_ema)
            state.loss_weights = new_loss_weights
            state.initial_grad_norms = new_initial_grad_norms

            # Adaptive Overlap Weighting Logic
            # Every 10 epochs, check for persistent collisions and ramp weights
            if config.adaptive_overlap_enabled and epoch % 10 == 0:
                per_comp_overlap = loss_breakdown_arrays.get("overlap_per_component")
                per_comp_boundary = loss_breakdown_arrays.get("boundary_per_component")
                per_comp_group = loss_breakdown_arrays.get("group_cluster_per_component")
                
                if per_comp_overlap is not None or per_comp_boundary is not None or per_comp_group is not None:
                    # Initialize mask
                    violation_mask = jnp.zeros(state.overlap_weights.shape, dtype=jnp.bool_)
                    
                    if per_comp_overlap is not None:
                        violation_mask = jnp.logical_or(violation_mask, per_comp_overlap > 0.1)
                    
                    if per_comp_boundary is not None:
                        violation_mask = jnp.logical_or(violation_mask, per_comp_boundary > 0.1)

                    if per_comp_group is not None:
                        violation_mask = jnp.logical_or(violation_mask, per_comp_group > 0.1)
                        
                    # Increment weight by 10% for any violation
                    state.overlap_weights = jnp.where(
                        violation_mask,
                        state.overlap_weights * 1.10,
                        state.overlap_weights
                    )
                    # Cap at 50x
                    state.overlap_weights = jnp.minimum(state.overlap_weights, 50.0)

                    # Decouple cleared components?
                    # Optionally slowly decay weights for non-violating components
                    state.overlap_weights = jnp.where(
                        ~violation_mask,
                        jnp.maximum(1.0, state.overlap_weights * 0.99),
                        state.overlap_weights
                    )

            # Stochastic Perturbation (Jiggle) Logic
            if config.jiggle_enabled and state.position_delta_ema < 1e-4 and epoch > 100:
                state.rng_key, jiggle_key = jax.random.split(state.rng_key)
                sigma = 0.05 * max(board.width, board.height)
                noise_scale = sigma * (temperature / config.temperature.start)

                jiggle = jax.random.normal(jiggle_key, state.positions.shape) * noise_scale
                state.positions = state.positions + jiggle
                state.position_delta_ema = 1.0

            loss_value = float(loss)

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
                    # Add non-differentiable penalties to total loss
                    loss_value += validation_result.drc_penalty
                    loss_value += validation_result.routing_penalty
                    
                    # Check if validation failed and we should stop
                    if not validation_result.passed:
                        stopped_by_validation = True
                        break

            # Check for numerical instability (NaN/Inf)
            _check_numerical_stability(loss_value, loss_breakdown_arrays, grad_pos, grad_rot, epoch)

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

                # Use breakdown from train_step (no recomputation needed!)
                # Convert arrays to scalars for logging, keeping only the totals
                breakdown = {k: float(jnp.sum(v)) if hasattr(v, "shape") and v.shape else float(v)
                           for k, v in loss_breakdown_arrays.items()}

                # Extract current loss weights for logging
                logged_weights = None
                if config.use_grad_norm and state.loss_weights is not None:
                    logged_weights = {
                        name: float(state.loss_weights[i])
                        for i, name in enumerate(composite_loss.loss_names)
                    }

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
                    loss_weights=logged_weights,
                )
                history.append(metrics)

                if callback is not None:
                    callback(metrics)

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
        final_overlap_weights=state.overlap_weights,
    )


def train_multiphase(
    netlist: Netlist,
    board: Board,
    loss_factory: Callable[[dict[str, float]], CompositeLoss],
    context: LossContext,
    config: OptimizerConfig | None = None,
    initial_state: PlacementState | None = None,
    callback: Callable[[TrainingMetrics], None] | None = None,
    validation_callback: ValidationCallback | None = None,
    profile_dir: str | None = None,
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
        profile_dir: If provided, save JAX profiler trace to this directory.

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

    from temper_placer.optimizer.config import get_default_loss_weights
    from temper_placer.optimizer.scheduler import get_curriculum_weights

    default_weights = get_default_loss_weights()

    start_time = time.time()

    # Initialize training state
    state = initialize_training_state(netlist, board, config, initial_state)

    # Initialize dynamic loss weights for GradNorm
    # We initialize with ones, but we'll resize if composite_loss size changes
    state.loss_weights = jnp.ones((1,), dtype=jnp.float32)
    state.initial_grad_norms = jnp.zeros((1,), dtype=jnp.float32)

    # Training history
    history: list[TrainingMetrics] = []

    # Validation tracking
    validation_history: list[ValidationResult] = []
    stopped_by_validation = False

    # Best tracking
    best_loss = float("inf")
    best_positions = state.positions
    best_rotations = jnp.eye(4)[jnp.zeros(netlist.n_components, dtype=jnp.int32)]
    epochs_without_improvement = 0

    # Track current phase for re-creating loss function
    current_phase_idx = -1
    composite_loss: CompositeLoss | None = None
    train_step = None

    # Optional: Enable JAX profiler
    profile_ctx = (
        jax.profiler.trace(profile_dir) if profile_dir else contextlib.nullcontext()
    )

    # Main training loop
    with profile_ctx:
        for epoch in range(config.epochs):
            epoch_start = time.time()

            # Check if we need to update loss weights (phase change)
            new_phase_idx = -1
            for i, phase in enumerate(config.curriculum_phases):
                if phase.start_epoch <= epoch < phase.end_epoch:
                    new_phase_idx = i
                    break
            
            # Special case: if we aren't in any phase, use default weights or the first phase
            if new_phase_idx == -1 and config.curriculum_phases:
                new_phase_idx = 0

            # Recreate loss and optimizer if phase changed or not yet initialized
            if new_phase_idx != current_phase_idx or composite_loss is None:
                current_phase_idx = new_phase_idx

                # Get current weights
                if config.curriculum_phases:
                    weights = get_curriculum_weights(epoch, config.curriculum_phases, default_weights)
                else:
                    weights = default_weights

                # Create new composite loss
                composite_loss = loss_factory(weights)
                n_losses = len(composite_loss.losses)

                # Update state weights if size changed
                if state.loss_weights.shape[0] != n_losses:
                    state.loss_weights = jnp.ones((n_losses,), dtype=jnp.float32)
                    state.initial_grad_norms = jnp.zeros((n_losses,), dtype=jnp.float32)

                # Create new value_and_grad function with breakdown
                value_and_grad_fn = create_value_and_grad_fn_with_breakdown(composite_loss, context)

                # Create optimizers with current learning rate
                lr = get_learning_rate(epoch, config.epochs, config.learning_rate)
                opt_pos, opt_rot = create_optimizer(config, lr)

                # Create new train step
                centrality = context.centrality if config.use_centrality_weighting else None
                train_step = make_train_step(
                    value_and_grad_fn,
                    opt_pos,
                    opt_rot,
                    config.epochs,
                    centrality=centrality,
                    priority_scale=config.centrality_priority_scale,
                    use_grad_norm=config.use_grad_norm,
                    grad_norm_alpha=config.grad_norm.alpha,
                    grad_norm_lr=config.grad_norm.learning_rate,
                    composite_loss=composite_loss,
                    loss_context=context,
                )

                # Re-initialize optimizer states
                state.opt_state_pos = opt_pos.init(state.positions)
                state.opt_state_rot = opt_rot.init(state.rotation_logits)

            # Get current temperature and learning rate
            temperature = get_temperature(epoch, config.epochs, config.temperature)
            lr = get_learning_rate(epoch, config.epochs, config.learning_rate)

            # Sample rotations
            state.rng_key, sample_key = jax.random.split(state.rng_key)
            if config.use_gumbel_rotation:
                rotations = sample_rotation_batch(state.rotation_logits, sample_key, temperature)
            else:
                rotations = sample_rotation_batch(state.rotation_logits, sample_key, 1e-5)

            # Run training step (returns breakdown alongside loss to avoid recomputation)
            if train_step is None:
                raise RuntimeError(f"train_step not initialized at epoch {epoch}. Check curriculum phases.")

            (
                new_positions,
                new_rotation_logits,
                loss,
                loss_breakdown_arrays,
                new_opt_state_pos,
                new_opt_state_rot,
                grad_pos,
                grad_rot,
                new_ema,
                new_loss_weights,
                new_initial_grad_norms,
            ) = train_step(
                state.positions,
                state.rotation_logits,
                rotations,
                state.opt_state_pos,
                state.opt_state_rot,
                epoch,
                lr,
                state.position_delta_ema,
                state.overlap_weights,
                state.loss_weights,
                state.initial_grad_norms,
            )

            # Update state
            state.positions = new_positions
            state.rotation_logits = new_rotation_logits
            state.opt_state_pos = new_opt_state_pos
            state.opt_state_rot = new_opt_state_rot
            state.position_delta_ema = float(new_ema)
            state.loss_weights = new_loss_weights
            state.initial_grad_norms = new_initial_grad_norms

            # Adaptive Overlap Weighting Logic
            if config.adaptive_overlap_enabled and epoch % 10 == 0:
                per_comp_overlap = loss_breakdown_arrays.get("overlap_per_component")
                if per_comp_overlap is not None:
                    collision_mask = per_comp_overlap > 0.1
                    state.overlap_weights = jnp.where(
                        collision_mask,
                        state.overlap_weights * 1.05,
                        state.overlap_weights
                    )
                    state.overlap_weights = jnp.minimum(state.overlap_weights, 20.0)
                    state.overlap_weights = jnp.where(
                        ~collision_mask,
                        jnp.maximum(1.0, state.overlap_weights * 0.99),
                        state.overlap_weights
                    )

            # Stochastic Perturbation (Jiggle) Logic
            if config.jiggle_enabled and state.position_delta_ema < 1e-4 and epoch > 100:
                state.rng_key, jiggle_key = jax.random.split(state.rng_key)
                sigma = 0.05 * max(board.width, board.height)
                noise_scale = sigma * (temperature / config.temperature.start)

                jiggle = jax.random.normal(jiggle_key, state.positions.shape) * noise_scale
                state.positions = state.positions + jiggle
                state.position_delta_ema = 1.0

            loss_value = float(loss)

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
                    # Add non-differentiable penalties to total loss
                    loss_value += validation_result.drc_penalty
                    loss_value += validation_result.routing_penalty
                    
                    # Check if validation failed and we should stop
                    if not validation_result.passed:
                        stopped_by_validation = True
                        break

            # Check for numerical instability (NaN/Inf)
            _check_numerical_stability(loss_value, loss_breakdown_arrays, grad_pos, grad_rot, epoch)

            # Track best
            if loss_value < best_loss - config.early_stopping.min_delta:
                best_loss = loss_value
                best_positions = state.positions
                best_rotations = rotations
                epochs_without_improvement = 0
            else:
                epochs_without_improvement += 1

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
        final_overlap_weights=state.overlap_weights,
    )
