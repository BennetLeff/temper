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
import logging
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
from temper_placer.explainability.trace import Trace
from temper_placer.geometry.transform import sample_rotation_batch
from temper_placer.heuristics.force_directed import compute_force_directed_layout
from temper_placer.io.config_loader import PlacementConstraints
from temper_placer.losses.base import (
    CompositeLoss,
    LossContext,
    create_value_and_grad_fn_with_breakdown,
)
from temper_placer.optimizer.config import OptimizerConfig
from temper_placer.optimizer.convergence_analytics import (
    ConvergenceConfidenceScorer,
    LossImprovementTracker,
)
from temper_placer.optimizer.initialization import SpectralInitializer
from temper_placer.optimizer.scheduler import (
    get_learning_rate,
    get_temperature,
)
from temper_placer.optimizer.validation_callback import (
    ValidationCallback,
    ValidationResult,
)
from temper_placer.optimizer.zone_aware_init import ZoneAwareSpectralInitializer

logger = logging.getLogger(__name__)


class NumericalInstabilityError(RuntimeError):
    """Exception raised when training becomes numerically unstable (NaN/Inf)."""

    def __init__(
        self,
        message: str,
        epoch: int,
        loss_value: float | None = None,
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
    loss_breakdown: dict[str, Array],
    grad_pos: Array,
    grad_rot: Array,
    epoch: int,
) -> None:
    """
    Check for NaN/Inf values in loss or gradients.

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
            f"Problematic components: {bad_components if bad_components else 'unknown'}",
            epoch=epoch,
            loss_value=loss_value,
            loss_breakdown={
                k: float(jnp.sum(v)) if hasattr(v, "shape") else float(v)
                for k, v in loss_breakdown.items()
            },
            grad_norms={
                "position": float(jnp.linalg.norm(grad_pos)),
                "rotation": float(jnp.linalg.norm(grad_rot)),
            },
        )

    # Check gradients
    if not (jnp.all(jnp.isfinite(grad_pos)) and jnp.all(jnp.isfinite(grad_rot))):
        raise NumericalInstabilityError(
            f"Non-finite gradients at epoch {epoch}. "
            f"grad_pos_norm: {jnp.linalg.norm(grad_pos)}, grad_rot_norm: {jnp.linalg.norm(grad_rot)}",
            epoch=epoch,
            loss_value=loss_value,
            loss_breakdown={
                k: float(jnp.sum(v)) if hasattr(v, "shape") else float(v)
                for k, v in loss_breakdown.items()
            },
            grad_norms={
                "position": float(jnp.linalg.norm(grad_pos)),
                "rotation": float(jnp.linalg.norm(grad_rot)),
            },
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
    loss_improvement_ema: float = 0.0
    convergence_confidence: float = 0.0
    is_plateau: bool = False
    loss_weights: dict[str, float] | None = None
    positions: Array | None = None
    rotations: Array | None = None


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
        convergence_reached: Whether the convergence confidence reached the threshold.
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
    convergence_reached: bool = False
    trace: Trace | None = None


@dataclass
class ParallelTrainingResult:
    """
    Aggregated result from multiple parallel training seeds.

    Attributes:
        best_result: The TrainingResult with the lowest aesthetic loss.
        aesthetic_tax: The percentage increase in wirelength due to aesthetics.
        confidence_score: 0.0-1.0 score based on how many seeds reached the same state.
        all_results: List of all individual TrainingResult instances.
    """

    best_result: TrainingResult
    aesthetic_tax: float
    confidence_score: float
    all_results: list[TrainingResult]


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
    opt_state_vn: Any | None = None  # optax optimizer state for net_virtual_nodes (optional)
    net_virtual_nodes: Array | None = None  # (M, 2)
    epoch: int = 0
    best_loss: float = float("inf")
    best_positions: Array | None = None
    best_rotations: Array | None = None
    best_net_virtual_nodes: Array | None = None
    epochs_without_improvement: int = 0
    position_delta_ema: float = 1.0  # EMA of component movement norm
    loss_ema: float | None = None  # EMA of the total loss
    improvement_ema: float = 0.0  # EMA of the relative loss improvement
    overlap_weights: Array | None = None  # (N,) adaptive multipliers
    loss_weights: Array | None = None  # (L,) dynamic loss weights
    initial_grad_norms: Array | None = None  # (L,) initial gradient norms for GradNorm
    current_lr: float = 0.1
    plateau_count: int = 0


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
    optimizer = optax.inject_hyperparams(lambda **_kwargs: optax.chain(*transforms))()

    # Use same optimizer for both, but they could be different
    return optimizer, optimizer


def initialize_training_state(
    netlist: Netlist,
    board: Board,
    config: OptimizerConfig,
    initial_state: PlacementState | None = None,
    constraints: PlacementConstraints | None = None,
) -> TrainingState:
    """
    Initialize training state with positions and rotation logits.

    Args:
        netlist: Component netlist.
        board: Board definition.
        config: Optimizer configuration.
        initial_state: Optional initial placement to start from.
        constraints: Optional placement constraints (passed through to
            constraint-aware initializers; ignored by current initializers).

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
        net_virtual_nodes = initial_state.net_virtual_nodes
    else:
        # Use configured initialization method
        if config.initialization.method == "spectral":
            initializer = SpectralInitializer(
                normalized_laplacian=config.initialization.spectral_normalized,
                margin_fraction=config.initialization.spectral_margin,
            )
            positions = initializer.initialize(netlist, board, constraints=constraints)
            net_virtual_nodes = None
        elif config.initialization.method == "zone_aware_spectral":
            # Zone-aware spectral: bias components away from copper zones
            zone_cfg = config.initialization.zone_aware
            initializer = ZoneAwareSpectralInitializer(
                normalized_laplacian=config.initialization.spectral_normalized,
                margin_fraction=config.initialization.spectral_margin,
                zone_penalty=zone_cfg.zone_penalty,
                boundary_margin=zone_cfg.boundary_margin,
                adjustment_iters=zone_cfg.adjustment_iters,
            )
            positions = initializer.initialize(netlist, board, constraints=constraints)
            net_virtual_nodes = None
            logger.info(
                f"Zone-aware spectral init: penalty={zone_cfg.zone_penalty}, "
                f"margin={zone_cfg.boundary_margin}mm, iters={zone_cfg.adjustment_iters}"
            )
        elif config.initialization.method == "learned":
            from temper_placer.optimizer.initialization import LearnedInitializer

            initializer = LearnedInitializer(model_path=config.initialization.learned_model_path)  # type: ignore[assignment]
            positions = initializer.initialize(netlist, board, constraints=constraints)
            net_virtual_nodes = None
        else:
            # Default: Random initialization in relative coordinates
            rng_key, init_key = jax.random.split(rng_key)
            state = PlacementState.random_init(
                n_components=netlist.n_components,
                board_width=board.width,
                board_height=board.height,
                key=init_key,
                n_nets=netlist.n_nets,
            )
            positions = state.positions
            net_virtual_nodes = state.net_virtual_nodes

        # Initialize uniform rotation logits if not starting from existing state
        rotation_logits = jnp.zeros((netlist.n_components, 4))

    # Initialize virtual nodes if not present
    if net_virtual_nodes is None:
        ox, oy = board.origin
        # Use 10mm margin but cap it at 20% of board dimensions to handle small boards
        margin = min(10.0, board.width * 0.2, board.height * 0.2)
        key_vn_x, key_vn_y = jax.random.split(rng_key, 2)
        nx = jax.random.uniform(
            key_vn_x, (netlist.n_nets,), minval=ox + margin, maxval=ox + board.width - margin
        )
        ny = jax.random.uniform(
            key_vn_y, (netlist.n_nets,), minval=oy + margin, maxval=oy + board.height - margin
        )
        net_virtual_nodes = jnp.stack([nx, ny], axis=-1)

    # Apply force-directed unfolding if enabled
    if config.initialization.force_directed.enabled:
        positions = compute_force_directed_layout(
            netlist=netlist,
            initial_positions=positions,
            iterations=config.initialization.force_directed.iterations,
            learning_rate=config.initialization.force_directed.learning_rate,
        )

    # Create optimizers
    initial_lr = config.learning_rate.initial
    opt_pos, opt_rot = create_optimizer(config, initial_lr)

    # Create optimizer for virtual nodes (reuse generic optimizer config)
    opt_vn, _ = create_optimizer(config, initial_lr)

    # Initialize optimizer states
    opt_state_pos = opt_pos.init(positions)
    opt_state_rot = opt_rot.init(rotation_logits)
    opt_state_vn = opt_vn.init(net_virtual_nodes)

    return TrainingState(
        positions=positions,
        rotation_logits=rotation_logits,
        opt_state_pos=opt_state_pos,
        opt_state_rot=opt_state_rot,
        rng_key=rng_key,
        net_virtual_nodes=net_virtual_nodes,
        opt_state_vn=opt_state_vn,
        epoch=0,
        overlap_weights=jnp.ones((netlist.n_components,), dtype=jnp.float32),
        loss_weights=jnp.ones((1,), dtype=jnp.float32),  # Placeholder, will be resized if needed
        initial_grad_norms=jnp.ones((1,), dtype=jnp.float32),
        current_lr=initial_lr,
    )


def make_train_step(
    value_and_grad_fn: Callable,
    opt_pos: optax.GradientTransformation,
    opt_rot: optax.GradientTransformation,
    opt_vn: optax.GradientTransformation,
    total_epochs: int,
    centrality: Array | None = None,
    priority_scale: float = 1.0,
    use_grad_norm: bool = False,
    grad_norm_alpha: float = 1.5,  # noqa: ARG001 (used as kwarg by callers)
    grad_norm_lr: float = 0.025,
    composite_loss: CompositeLoss | None = None,
    loss_context: LossContext | None = None,
    zone_bounds: Array
    | None = None,  # (N, 4) per-component zone bounds [x_min, y_min, x_max, y_max]
):
    """
    Create a JIT-compiled training step function.

    Args:
        value_and_grad_fn: Function returning ((loss, breakdown), (grad_pos, grad_rot)).
        opt_pos: Position optimizer.
        opt_rot: Rotation optimizer.
        opt_vn: Virtual Node optimizer.
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
        net_virtual_nodes: Array,
        opt_state_pos: Any,
        opt_state_rot: Any,
        opt_state_vn: Any,
        epoch: int,
        learning_rate: float,
        position_delta_ema: float,
        overlap_weights: Array,
        loss_weights: Array,
        initial_grad_norms: Array,
    ) -> tuple[
        Array,
        Array,
        Array,
        Array,
        dict[str, Array],
        Any,
        Any,
        Any,
        Array,
        Array,
        Array,
        float,
        Array,
        Array,
    ]:
        """
        Single training step.

        Args:
            positions: Current positions (N, 2).
            rotation_logits: Current rotation logits (N, 4).
            rotations: Sampled rotations (N, 4) one-hot.
            net_virtual_nodes: Current virtual nodes (M, 2).
            opt_state_pos: Position optimizer state.
            opt_state_rot: Rotation optimizer state.
            opt_state_vn: Virtual node optimizer state.
            epoch: Current epoch.
            learning_rate: Current learning rate to apply.
            position_delta_ema: Current EMA of position updates.
            overlap_weights: Per-component adaptive overlap weights.
            loss_weights: Current (L,) dynamic loss weights.
            initial_grad_norms: (L,) initial gradient norms for GradNorm.

        Returns:
            Tuple of (new_positions, new_logits, new_virtual_nodes, loss, breakdown,
                     new_opt_state_pos, new_opt_state_rot, new_opt_state_vn, grad_pos, grad_rot, grad_vn,
                     new_ema, new_loss_weights, new_initial_grad_norms).
        """
        # Update learning rate in optimizer state
        new_opt_state_pos = opt_state_pos._replace(
            hyperparams={**opt_state_pos.hyperparams, "learning_rate": learning_rate}
        )
        new_opt_state_rot = opt_state_rot._replace(
            hyperparams={**opt_state_rot.hyperparams, "learning_rate": learning_rate}
        )
        # Note: opt_state_vn might not have hyperparams if it's not injected, but we assume it is
        new_opt_state_vn = opt_state_vn._replace(
            hyperparams={**opt_state_vn.hyperparams, "learning_rate": learning_rate}
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
            new_initial_grad_norms = jnp.where(epoch == 0, curr_grad_norms, initial_grad_norms)
            # Avoid division by zero
            new_initial_grad_norms = jnp.maximum(new_initial_grad_norms, 1e-6)

            # Compute total loss and breakdown using current dynamic weights
            (loss, breakdown), (grad_pos, grad_rot, grad_vn) = value_and_grad_fn(
                positions, rotations, net_virtual_nodes, epoch, total_epochs, loss_weights
            )

            # GradNorm weight update
            # 1. Compute weighted gradient norms: w_i * ||grad(L_i)||
            gw_norms = loss_weights * curr_grad_norms

            # 2. Compute target norm: mean(gw_i)
            # (Simplified version without inverse training rate for now)
            target_norms = jnp.mean(gw_norms)

            # 3. Compute gradient of GradNorm loss (L_grad = sum |gw_i - target_i|)
            weight_grads = jnp.sign(gw_norms - target_norms) * curr_grad_norms
            new_loss_weights = loss_weights - grad_norm_lr * weight_grads
            new_loss_weights = jnp.maximum(new_loss_weights, 1e-3)
            new_loss_weights = new_loss_weights * (n_losses / jnp.sum(new_loss_weights))

        else:
            # Standard training
            (loss, breakdown), (grad_pos, grad_rot, grad_vn) = value_and_grad_fn(
                positions, rotations, net_virtual_nodes, epoch, total_epochs
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
            # Invert: hubs (normalized_c=1) get scale 1.0, leaves (normalized_c=0) get scale priority_scale
            grad_scale = 1.0 + (priority_scale - 1.0) * (1.0 - normalized_c)

            grad_pos = grad_pos * grad_scale[:, None]
            grad_rot = grad_rot * grad_scale[:, None]

        # Update positions and rotations
        updates_pos, next_opt_state_pos = opt_pos.update(grad_pos, new_opt_state_pos, positions)
        new_positions = optax.apply_updates(positions, updates_pos)

        # Hard clamping to board bounds (temper-p11g.2)
        if loss_context is not None:
            board_bounds = loss_context.board.get_relative_bounds_array()
            new_positions = jnp.clip(new_positions, min=board_bounds[:2], max=board_bounds[2:])

        # Hard clamping to zone bounds (guaranteed zone compliance)
        # zone_bounds is (N, 4) where each row is [x_min, y_min, x_max, y_max]
        # Components without zone assignment have bounds = board bounds (no extra constraint)
        if zone_bounds is not None:
            new_positions = jnp.clip(
                new_positions,
                min=zone_bounds[:, :2],  # x_min, y_min
                max=zone_bounds[:, 2:],  # x_max, y_max
            )

        # Ensure fixed components don't move (temper-p11g.6)
        if loss_context is not None:
            new_positions = jnp.where(loss_context.fixed_mask[:, None], positions, new_positions)  # type: ignore[index]

            # Zero out optimizer state for fixed components to prevent drift (temper-p11g.6)
            # Adam optimizer maintains momentum (mu) and variance (nu) which can accumulate
            if hasattr(next_opt_state_pos, "mu"):
                next_opt_state_pos = next_opt_state_pos._replace(
                    mu=jnp.where(loss_context.fixed_mask[:, None], 0.0, next_opt_state_pos.mu),  # type: ignore[index]
                    nu=jnp.where(loss_context.fixed_mask[:, None], 0.0, next_opt_state_pos.nu),  # type: ignore[index]
                )

        updates_rot, next_opt_state_rot = opt_rot.update(
            grad_rot, new_opt_state_rot, rotation_logits
        )
        new_rotation_logits = optax.apply_updates(rotation_logits, updates_rot)

        # Fixed components don't rotate either
        if loss_context is not None:
            new_rotation_logits = jnp.where(
                loss_context.fixed_mask[:, None], rotation_logits, new_rotation_logits  # type: ignore[index]
            )

            # Zero out optimizer state for fixed components (temper-p11g.6)
            if hasattr(next_opt_state_rot, "mu"):
                next_opt_state_rot = next_opt_state_rot._replace(
                    mu=jnp.where(loss_context.fixed_mask[:, None], 0.0, next_opt_state_rot.mu),  # type: ignore[index]
                    nu=jnp.where(loss_context.fixed_mask[:, None], 0.0, next_opt_state_rot.nu),  # type: ignore[index]
                )

        updates_vn, next_opt_state_vn = opt_vn.update(grad_vn, new_opt_state_vn, net_virtual_nodes)
        new_net_virtual_nodes = optax.apply_updates(net_virtual_nodes, updates_vn)

        # Hard clamping for virtual nodes
        if loss_context is not None:
            board_bounds = loss_context.board.get_relative_bounds_array()
            new_net_virtual_nodes = jnp.clip(
                new_net_virtual_nodes, min=board_bounds[:2], max=board_bounds[2:]
            )

        # Compute movement norm and update EMA
        update_norm = jnp.linalg.norm(new_positions - positions)
        new_ema = 0.9 * position_delta_ema + 0.1 * update_norm

        return (
            new_positions,
            new_rotation_logits,
            new_net_virtual_nodes,
            loss,
            breakdown,
            next_opt_state_pos,
            next_opt_state_rot,
            next_opt_state_vn,
            grad_pos,
            grad_rot,
            grad_vn,
            new_ema,
            new_loss_weights,
            new_initial_grad_norms,
        )

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
    constraints: PlacementConstraints | None = None,
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
        constraints: Optional placement constraints (passed through to
            initialization; ignored by current initializers).

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
    state = initialize_training_state(netlist, board, config, initial_state, constraints=constraints)

    # Initialize dynamic loss weights for GradNorm
    n_losses = len(composite_loss.losses)
    state.loss_weights = jnp.ones((n_losses,), dtype=jnp.float32)
    state.initial_grad_norms = jnp.zeros((n_losses,), dtype=jnp.float32)

    # Create value_and_grad function with breakdown
    value_and_grad_fn = create_value_and_grad_fn_with_breakdown(composite_loss, context)

    # Create optimizers
    initial_lr = config.learning_rate.initial
    opt_pos, opt_rot = create_optimizer(config, initial_lr)
    opt_vn, _ = create_optimizer(config, initial_lr)

    # Re-initialize optimizer states (in case lr changed)
    state.opt_state_pos = opt_pos.init(state.positions)
    state.opt_state_rot = opt_rot.init(state.rotation_logits)
    state.opt_state_vn = opt_vn.init(state.net_virtual_nodes)

    # Create JIT-compiled train step
    centrality = context.centrality if config.use_centrality_weighting else None

    # Compute zone bounds per component for hard zone clamping
    # Each row is [x_min, y_min, x_max, y_max] for component i
    zone_bounds = None
    if context.board.zones:
        # Build ref -> zone lookup
        ref_to_zone = {}
        for zone in context.board.zones:
            for comp_ref in zone.components:
                ref_to_zone[comp_ref] = zone.bounds

        # Build zone_bounds array
        board_bounds = context.board.get_relative_bounds_array()
        zone_bounds_list = []
        for _i, comp in enumerate(netlist.components):
            if comp.ref in ref_to_zone:
                zone_bounds_list.append(ref_to_zone[comp.ref])
            else:
                # No zone assignment - use board bounds
                zone_bounds_list.append(
                    (board_bounds[0], board_bounds[1], board_bounds[2], board_bounds[3])
                )
        zone_bounds = jnp.array(zone_bounds_list, dtype=jnp.float32)

    train_step = make_train_step(
        value_and_grad_fn,
        opt_pos,
        opt_rot,
        opt_vn,
        config.epochs,
        centrality=centrality,
        priority_scale=config.centrality_priority_scale,
        use_grad_norm=config.use_grad_norm,
        grad_norm_alpha=config.grad_norm.alpha,
        grad_norm_lr=config.grad_norm.learning_rate,
        composite_loss=composite_loss,
        loss_context=context,
        zone_bounds=zone_bounds,
    )

    # Optional: Enable JAX profiler
    profile_ctx = jax.profiler.trace(profile_dir) if profile_dir else contextlib.nullcontext()

    # Training history
    history: list[TrainingMetrics] = []

    # Validation tracking
    validation_history: list[ValidationResult] = []
    stopped_by_validation = False
    convergence_reached = False
    is_plateau = False

    # Best tracking
    best_loss = float("inf")
    best_positions = state.positions
    # Initialize best_rotations from initial state (temper-p11g.7)
    best_rotations = jax.nn.one_hot(jnp.argmax(state.rotation_logits, axis=-1), 4)
    epochs_without_improvement = 0

    # Convergence tracking
    tracker = LossImprovementTracker(
        stagnation_threshold=config.early_stopping.stagnation_threshold,
        stagnation_epochs=config.early_stopping.stagnation_epochs,
    )
    scorer = ConvergenceConfidenceScorer(
        convergence_threshold=config.early_stopping.confidence_threshold,
        improvement_threshold=config.early_stopping.stagnation_threshold,
    )

    # Main training loop
    is_plateau = False
    with profile_ctx:
        for epoch in range(config.epochs):
            epoch_start = time.time()

            # Get current temperature and learning rate
            temperature = get_temperature(epoch, config.epochs, config.temperature)

            # Adaptive Learning Rate (ALR) - Reduce on Plateau
            lr_cfg = config.reduce_lr_on_plateau
            if lr_cfg.enabled and is_plateau:
                state.plateau_count += 1
                if state.plateau_count >= lr_cfg.patience:
                    state.current_lr = max(state.current_lr * lr_cfg.factor, lr_cfg.min_lr)
                    state.plateau_count = 0
                    logger.info(
                        f"Epoch {epoch}: Reducing learning rate to {state.current_lr:.6f} due to plateau"
                    )
            else:
                state.plateau_count = 0

            # If not plateauing, follow base schedule (optional: blend them)
            # For now, if ALR has touched the LR, we stay with ALR's value
            # unless the schedule is even lower.
            base_lr = get_learning_rate(epoch, config.epochs, config.learning_rate)
            lr = min(state.current_lr, base_lr)

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
                new_net_virtual_nodes,
                loss,
                loss_breakdown_arrays,
                new_opt_state_pos,
                new_opt_state_rot,
                new_opt_state_vn,
                grad_pos,
                grad_rot,
                grad_vn,
                new_ema,
                new_loss_weights,
                new_initial_grad_norms,
            ) = train_step(
                state.positions,
                state.rotation_logits,
                rotations,
                state.net_virtual_nodes,
                state.opt_state_pos,
                state.opt_state_rot,
                state.opt_state_vn,
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
            state.net_virtual_nodes = new_net_virtual_nodes
            state.opt_state_pos = new_opt_state_pos
            state.opt_state_rot = new_opt_state_rot
            state.opt_state_vn = new_opt_state_vn
            state.position_delta_ema = float(new_ema)
            state.loss_weights = new_loss_weights
            state.initial_grad_norms = new_initial_grad_norms

            # --- Convergence Tracking ---
            loss_value = float(loss)

            # Update specialized trackers
            conv_metrics = tracker.update(loss_value)
            # Use gradient norm for confidence if enabled
            grad_norm = float(jnp.linalg.norm(grad_pos))
            conv_confidence = scorer.update(tracker, grad_norm=grad_norm)

            confidence = conv_confidence.confidence
            is_plateau = conv_metrics.is_stagnating
            state.improvement_ema = (
                conv_metrics.improvement_rate
            )  # Use rate as EMA proxy for backward compat if needed

            # Adaptive Overlap Weighting Logic
            # Adaptive Overlap Weighting
            ao_cfg = config.adaptive_overlap
            if ao_cfg.enabled and epoch % ao_cfg.update_interval == 0:
                assert state.overlap_weights is not None
                per_comp_overlap = loss_breakdown_arrays.get("overlap_per_component")
                per_comp_boundary = loss_breakdown_arrays.get("boundary_per_component")
                per_comp_group = loss_breakdown_arrays.get("group_cluster_per_component")

                if (
                    per_comp_overlap is not None
                    or per_comp_boundary is not None
                    or per_comp_group is not None
                ):
                    # Initialize mask
                    violation_mask = jnp.zeros(state.overlap_weights.shape, dtype=jnp.bool_)

                    if per_comp_overlap is not None:
                        violation_mask = jnp.logical_or(
                            violation_mask, per_comp_overlap > ao_cfg.collision_threshold
                        )

                    if per_comp_boundary is not None:
                        violation_mask = jnp.logical_or(
                            violation_mask, per_comp_boundary > ao_cfg.collision_threshold
                        )

                    if per_comp_group is not None:
                        violation_mask = jnp.logical_or(
                            violation_mask, per_comp_group > ao_cfg.collision_threshold
                        )

                    # Increment weight for any violation
                    state.overlap_weights = jnp.where(
                        violation_mask,
                        state.overlap_weights * ao_cfg.ramp_rate,
                        state.overlap_weights,
                    )
                    # Cap is critical to prevent explosion (temper-taaj.1)
                    state.overlap_weights = jnp.minimum(state.overlap_weights, ao_cfg.max_cap)

                    # Log when weights approach cap for debugging
                    max_weight = float(jnp.max(state.overlap_weights))
                    if max_weight > ao_cfg.max_cap * 0.9:
                        logger.debug(
                            f"Epoch {epoch}: Adaptive weight near cap: {max_weight:.2f}/{ao_cfg.max_cap}"
                        )
            # Stochastic Perturbation (Jiggle) Logic
            j_cfg = config.jiggle
            if (
                j_cfg.enabled
                and state.position_delta_ema < j_cfg.ema_threshold
                and epoch > j_cfg.min_epoch
            ):
                state.rng_key, jiggle_key = jax.random.split(state.rng_key)
                sigma = j_cfg.sigma_fraction * max(board.width, board.height)
                noise_scale = sigma * (temperature / config.temperature.start)

                jiggle = jax.random.normal(jiggle_key, state.positions.shape) * noise_scale
                state.positions = state.positions + jiggle
                # Re-clamp after jiggle to maintain feasibility invariants
                board_bounds = context.board.get_relative_bounds_array()
                state.positions = jnp.clip(
                    state.positions, min=board_bounds[:2], max=board_bounds[2:]
                )
                # We don't reset EMA to 1.0 anymore (temper-p11g.9)
                logger.debug(f"Epoch {epoch}: Jiggle triggered")

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
                breakdown = {
                    k: float(jnp.sum(v)) if hasattr(v, "shape") and v.shape else float(v)
                    for k, v in loss_breakdown_arrays.items()
                }

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
                    loss_improvement_ema=float(state.improvement_ema),
                    convergence_confidence=float(confidence),
                    is_plateau=bool(is_plateau),
                    loss_weights=logged_weights,
                    positions=state.positions,
                    rotations=rotations,
                )
                history.append(metrics)

                if callback is not None:
                    callback(metrics)

            # Early stopping check
            if config.early_stopping.enabled:
                # 1. Traditional patience-based stopping
                if epochs_without_improvement >= config.early_stopping.patience:
                    convergence_reached = True
                    break

                # 2. Convergence-based stopping
                if (
                    config.early_stopping.use_convergence
                    and confidence >= config.early_stopping.confidence_threshold
                    and epoch > config.early_stopping.patience // 2  # Warmup
                ):
                    logger.info(
                        f"Epoch {epoch}: Early stopping due to convergence confidence ({confidence:.4f})"
                    )
                    convergence_reached = True
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
        converged=epochs_without_improvement >= config.early_stopping.patience
        or convergence_reached,
        elapsed_seconds=elapsed,
        validation_history=validation_history,
        stopped_by_validation=stopped_by_validation,
        final_overlap_weights=state.overlap_weights,
        convergence_reached=convergence_reached,
        trace=composite_loss.trace(
            best_positions,
            best_rotations,
            context,
            epoch=epoch,
            total_epochs=config.epochs,
            net_virtual_nodes=state.net_virtual_nodes,
        )[1],
    )


def train_parallel(
    netlist: Netlist,
    board: Board,
    composite_loss: CompositeLoss,
    context: LossContext,
    config: OptimizerConfig,
    n_seeds: int = 4,
    callback: Callable[[TrainingMetrics], None] | None = None,
    constraints: PlacementConstraints | None = None,
) -> ParallelTrainingResult:
    """
    Run optimization across multiple random seeds in parallel (or sequence).

    Identifies the best placement and calculates aesthetic tax.

    Args:
        netlist: Component netlist.
        board: Board definition.
        composite_loss: The full aesthetic loss.
        context: Loss context.
        config: Optimizer configuration.
        n_seeds: Number of seeds to run.
        callback: Optional callback for progress tracking.
        constraints: Optional placement constraints (passed through to
            initialization; ignored by current initializers).

    Returns:
        ParallelTrainingResult.
    """
    results = []
    base_seed = config.seed

    for i in range(n_seeds):
        # Create a new config with a different seed
        seed_config = dataclass_replace(config, seed=base_seed + i)

        # Run training
        res = train(netlist, board, composite_loss, context, seed_config, callback=callback, constraints=constraints)
        results.append(res)

    # 1. Identify best result
    best_result = min(results, key=lambda r: r.best_loss)

    # 2. Calculate Aesthetic Tax
    # We estimate the tax by comparing total wirelength vs a hypothetical minimum
    # Or just looking at the wirelength component of the best result vs the average.
    best_wl = best_result.history[-1].loss_breakdown.get("wirelength", 0.0)
    jnp.mean(
        jnp.array([r.history[-1].loss_breakdown.get("wirelength", 0.0) for r in results])
    )

    # Aesthetic tax is best_wl / minimal_achieved_wl
    min_wl = min([r.history[-1].loss_breakdown.get("wirelength", 1e9) for r in results])
    aesthetic_tax = (best_wl / jnp.maximum(min_wl, 1e-6)) if min_wl > 0 else 1.0

    # 3. Calculate Confidence Score
    # Fraction of seeds that reached within 10% of the best loss
    threshold = best_result.best_loss * 1.10
    confident_seeds = sum(1 for r in results if r.best_loss < threshold)
    confidence_score = confident_seeds / n_seeds

    return ParallelTrainingResult(
        best_result=best_result,
        aesthetic_tax=float(aesthetic_tax),
        confidence_score=float(confidence_score),
        all_results=results,
    )


def dataclass_replace(obj, **kwargs):
    """Simple helper to replace fields in a dataclass."""
    from dataclasses import replace

    return replace(obj, **kwargs)


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
    drc_oracle: Any | None = None,
    constraints: PlacementConstraints | None = None,
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
        drc_oracle: Optional DRC oracle for early stopping.
        constraints: Optional placement constraints (passed through to
            initialization; ignored by current initializers).

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
    state = initialize_training_state(netlist, board, config, initial_state, constraints=constraints)

    # Initialize dynamic loss weights for GradNorm
    # We initialize with ones, but we'll resize if composite_loss size changes
    state.loss_weights = jnp.ones((1,), dtype=jnp.float32)
    state.initial_grad_norms = jnp.zeros((1,), dtype=jnp.float32)

    # Training history
    history: list[TrainingMetrics] = []

    # Validation tracking
    validation_history: list[ValidationResult] = []
    stopped_by_validation = False
    convergence_reached = False
    is_plateau = False

    # Best tracking
    best_loss = float("inf")
    best_positions = state.positions
    # Initialize best_rotations from initial state (temper-p11g.7)
    best_rotations = jax.nn.one_hot(jnp.argmax(state.rotation_logits, axis=-1), 4)
    epochs_without_improvement = 0

    # Convergence tracking
    tracker = LossImprovementTracker(
        stagnation_threshold=config.early_stopping.stagnation_threshold,
        stagnation_epochs=config.early_stopping.stagnation_epochs,
    )
    scorer = ConvergenceConfidenceScorer(
        convergence_threshold=config.early_stopping.confidence_threshold,
        improvement_threshold=config.early_stopping.stagnation_threshold,
    )

    # Track current phase for re-creating loss function
    current_phase_idx = -1
    composite_loss: CompositeLoss | None = None
    train_step = None

    # Compute zone bounds per component for hard zone clamping
    # Each row is [x_min, y_min, x_max, y_max] for component i
    zone_bounds = None
    if board.zones:
        # Build ref -> zone lookup
        ref_to_zone = {}
        for zone in board.zones:
            for comp_ref in zone.components:
                ref_to_zone[comp_ref] = zone.bounds

        # Build zone_bounds array
        board_bounds = board.get_relative_bounds_array()
        zone_bounds_list = []
        for _i, comp in enumerate(netlist.components):
            if comp.ref in ref_to_zone:
                zone_bounds_list.append(ref_to_zone[comp.ref])
            else:
                # No zone assignment - use board bounds
                zone_bounds_list.append(
                    (float(board_bounds[0]), float(board_bounds[1]), float(board_bounds[2]), float(board_bounds[3]))
                )
        zone_bounds = jnp.array(zone_bounds_list, dtype=jnp.float32)

    # Optional: Enable JAX profiler
    profile_ctx = jax.profiler.trace(profile_dir) if profile_dir else contextlib.nullcontext()

    # Main training loop
    is_plateau = False
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
                phase_changed = new_phase_idx != current_phase_idx
                current_phase_idx = new_phase_idx

                # ── DRC fence at phase boundary (U9, K4) ──────────────────
                # Evaluate DRC violations at each curriculum phase transition.
                # This is informational only — violations do NOT block the
                # optimizer. Results are logged for monitoring and tuning.
                if phase_changed and drc_oracle is not None:
                    try:
                        phase_name = (
                            config.curriculum_phases[new_phase_idx].name
                            if new_phase_idx >= 0 and config.curriculum_phases
                            else "unknown"
                        )
                        result = drc_oracle.evaluate(
                            state.positions, context, use_rust=True
                        )
                        logger.info(
                            "DRC fence at phase '%s' (epoch %d): "
                            "%sC/%sE/%sW",
                            phase_name,
                            epoch,
                            getattr(result, "critical_count", "?"),
                            getattr(result, "error_count", "?"),
                            getattr(result, "warning_count", "?"),
                        )
                    except Exception as e:
                        logger.warning(
                            "DRC fence at phase boundary failed: %s", e
                        )

                # Get current weights
                if config.curriculum_phases:
                    weights = get_curriculum_weights(
                        epoch, config.curriculum_phases, default_weights
                    )
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
                opt_vn, _ = create_optimizer(config, lr)

                # Create new train step
                centrality = context.centrality if config.use_centrality_weighting else None
                train_step = make_train_step(
                    value_and_grad_fn,
                    opt_pos,
                    opt_rot,
                    opt_vn,
                    config.epochs,
                    centrality=centrality,
                    priority_scale=config.centrality_priority_scale,
                    use_grad_norm=config.use_grad_norm,
                    grad_norm_alpha=config.grad_norm.alpha,
                    grad_norm_lr=config.grad_norm.learning_rate,
                    composite_loss=composite_loss,
                    loss_context=context,
                    zone_bounds=zone_bounds,
                )

                # Re-initialize optimizer states
                state.opt_state_pos = opt_pos.init(state.positions)
                state.opt_state_rot = opt_rot.init(state.rotation_logits)

            # Get current temperature and learning rate
            temperature = get_temperature(epoch, config.epochs, config.temperature)

            # Adaptive Learning Rate (ALR) - Reduce on Plateau
            lr_cfg = config.reduce_lr_on_plateau
            if lr_cfg.enabled and is_plateau:
                state.plateau_count += 1
                if state.plateau_count >= lr_cfg.patience:
                    state.current_lr = max(state.current_lr * lr_cfg.factor, lr_cfg.min_lr)
                    state.plateau_count = 0
                    logger.info(
                        f"Epoch {epoch}: Reducing learning rate to {state.current_lr:.6f} due to plateau"
                    )
            else:
                state.plateau_count = 0

            base_lr = get_learning_rate(epoch, config.epochs, config.learning_rate)
            lr = min(state.current_lr, base_lr)

            # Sample rotations
            state.rng_key, sample_key = jax.random.split(state.rng_key)
            if config.use_gumbel_rotation:
                rotations = sample_rotation_batch(state.rotation_logits, sample_key, temperature)
            else:
                rotations = sample_rotation_batch(state.rotation_logits, sample_key, 1e-5)

            # Run training step (returns breakdown alongside loss to avoid recomputation)
            if train_step is None:
                raise RuntimeError(
                    f"train_step not initialized at epoch {epoch}. Check curriculum phases."
                )

            (
                new_positions,
                new_rotation_logits,
                new_net_virtual_nodes,
                loss,
                loss_breakdown_arrays,
                new_opt_state_pos,
                new_opt_state_rot,
                new_opt_state_vn,
                grad_pos,
                grad_rot,
                grad_vn,
                new_ema,
                new_loss_weights,
                new_initial_grad_norms,
            ) = train_step(
                state.positions,
                state.rotation_logits,
                rotations,
                state.net_virtual_nodes,
                state.opt_state_pos,
                state.opt_state_rot,
                state.opt_state_vn,
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
            state.net_virtual_nodes = new_net_virtual_nodes
            state.opt_state_pos = new_opt_state_pos
            state.opt_state_rot = new_opt_state_rot
            state.opt_state_vn = new_opt_state_vn
            state.position_delta_ema = float(new_ema)
            state.loss_weights = new_loss_weights
            state.initial_grad_norms = new_initial_grad_norms

            # --- Convergence Tracking ---
            loss_value = float(loss)

            # Update specialized trackers
            conv_metrics = tracker.update(loss_value)
            # Use gradient norm for confidence if enabled
            grad_norm = float(jnp.linalg.norm(grad_pos))
            conv_confidence = scorer.update(tracker, grad_norm=grad_norm)

            confidence = conv_confidence.confidence
            is_plateau = conv_metrics.is_stagnating
            state.improvement_ema = (
                conv_metrics.improvement_rate
            )  # Use rate as EMA proxy for backward compat if needed

            # Adaptive Overlap Weighting Logic
            # Adaptive Overlap Weighting
            ao_cfg = config.adaptive_overlap
            if ao_cfg.enabled and epoch % ao_cfg.update_interval == 0:
                assert state.overlap_weights is not None
                per_comp_overlap = loss_breakdown_arrays.get("overlap_per_component")
                if per_comp_overlap is not None:
                    collision_mask = per_comp_overlap > ao_cfg.collision_threshold
                    state.overlap_weights = jnp.where(
                        collision_mask,
                        state.overlap_weights * ao_cfg.ramp_rate,
                        state.overlap_weights,
                    )
                    state.overlap_weights = jnp.minimum(state.overlap_weights, ao_cfg.max_cap)
                    state.overlap_weights = jnp.where(
                        ~collision_mask,
                        jnp.maximum(1.0, state.overlap_weights * ao_cfg.decay_rate),
                        state.overlap_weights,
                    )

            # Stochastic Perturbation (Jiggle) Logic
            # Stochastic Perturbation (Jiggle) Logic
            j_cfg = config.jiggle
            if (
                j_cfg.enabled
                and state.position_delta_ema < j_cfg.ema_threshold
                and epoch > j_cfg.min_epoch
            ):
                state.rng_key, jiggle_key = jax.random.split(state.rng_key)
                sigma = j_cfg.sigma_fraction * max(board.width, board.height)
                noise_scale = sigma * (temperature / config.temperature.start)

                jiggle = jax.random.normal(jiggle_key, state.positions.shape) * noise_scale

                # Apply mask to jiggle
                jiggle = jnp.where(context.fixed_mask[:, None], 0.0, jiggle)  # type: ignore[index]

                state.positions = state.positions + jiggle
                # Re-clamp after jiggle to maintain feasibility invariants
                board_bounds = context.board.get_relative_bounds_array()
                state.positions = jnp.clip(
                    state.positions, min=board_bounds[:2], max=board_bounds[2:]
                )
                # We don't reset EMA to 1.0 anymore (temper-p11g.9)
                logger.debug(f"Epoch {epoch}: Jiggle triggered")

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
                # Compute gradient norms
                grad_norm_pos = float(jnp.linalg.norm(grad_pos))
                grad_norm_rot = float(jnp.linalg.norm(grad_rot))

                # Use breakdown from train_step (no recomputation needed!)
                # Convert arrays to scalars for logging, keeping only the totals
                breakdown = {
                    k: float(jnp.sum(v)) if hasattr(v, "shape") and v.shape else float(v)
                    for k, v in loss_breakdown_arrays.items()
                }

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
                    loss_improvement_ema=float(state.improvement_ema),
                    convergence_confidence=float(confidence),
                    is_plateau=bool(is_plateau),
                    loss_weights=logged_weights,
                    positions=state.positions,
                    rotations=rotations,
                )
                history.append(metrics)

                if callback is not None:
                    callback(metrics)

            # Early stopping
            if config.early_stopping.enabled:
                # 1. Traditional patience-based stopping
                if epochs_without_improvement >= config.early_stopping.patience:
                    convergence_reached = True
                    break

                # 2. Convergence-based stopping
                if (
                    config.early_stopping.use_convergence
                    and confidence >= config.early_stopping.confidence_threshold
                    and epoch > config.early_stopping.patience // 2  # Warmup
                ):
                    logger.info(
                        f"Epoch {epoch}: Early stopping due to convergence confidence ({confidence:.4f})"
                    )
                    convergence_reached = True
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

    assert composite_loss is not None
    return TrainingResult(
        final_state=final_state,
        final_loss=float(loss),
        best_state=best_state,
        best_loss=best_loss,
        history=history,
        total_epochs=epoch + 1,
        converged=epochs_without_improvement >= config.early_stopping.patience
        or convergence_reached,
        elapsed_seconds=elapsed,
        validation_history=validation_history,
        stopped_by_validation=stopped_by_validation,
        final_overlap_weights=state.overlap_weights,
        convergence_reached=convergence_reached,
        trace=composite_loss.trace(
            best_positions,
            best_rotations,
            context,
            epoch=epoch,
            total_epochs=config.epochs,
            net_virtual_nodes=state.net_virtual_nodes,
        )[1],
    )
