"""
Optimizer module for temper-placer.

This module implements the JAX-based gradient descent optimizer with:
- Adam optimizer via optax with learning rate scheduling
- Gumbel-Softmax temperature annealing for rotation
- Curriculum learning with progressive constraint introduction
- Checkpoint saving and resumption
- Early stopping and convergence detection

The optimizer coordinates:
1. Forward pass: compute placement state → losses
2. Backward pass: compute gradients via JAX autodiff
3. Update step: apply optimizer (optax.adam)
4. Logging: emit metrics for visualization

Training Phases (Curriculum):
1. Spread only - distribute components
2. Add overlap/boundary - enforce hard constraints
3. Add design rules - clearance, thermal
4. Add performance - wirelength, loops
5. Refinement - all losses, fine-tuning

Example:
    >>> from temper_placer.optimizer import train, OptimizerConfig
    >>> from temper_placer.losses import OverlapLoss, BoundaryLoss, CompositeLoss, WeightedLoss
    >>>
    >>> config = OptimizerConfig.fast_test()
    >>> composite = CompositeLoss([
    ...     WeightedLoss(OverlapLoss(), weight=100.0),
    ...     WeightedLoss(BoundaryLoss(), weight=50.0),
    ... ])
    >>> result = train(netlist, board, composite, context, config)
    >>> print(f"Final loss: {result.final_loss:.4f}")
"""

from temper_placer.optimizer.config import (
    OptimizerConfig,
    TemperatureSchedule,
    LearningRateSchedule,
    CurriculumPhase,
    CheckpointConfig,
    EarlyStoppingConfig,
    get_default_loss_weights,
)

from temper_placer.optimizer.scheduler import (
    get_temperature,
    get_learning_rate,
    get_temperature_jax,
    get_learning_rate_jax,
    get_curriculum_weights,
    ScheduleState,
)

from temper_placer.optimizer.curriculum import (
    create_default_phases,
    create_fast_phases,
    get_active_phase,
    get_phase_progress,
    smooth_transition_weights,
    CurriculumState,
)

from temper_placer.optimizer.train import (
    train,
    train_multiphase,
    TrainingResult,
    TrainingMetrics,
    TrainingState,
    initialize_training_state,
)

__all__ = [
    # Config
    "OptimizerConfig",
    "TemperatureSchedule",
    "LearningRateSchedule",
    "CurriculumPhase",
    "CheckpointConfig",
    "EarlyStoppingConfig",
    "get_default_loss_weights",
    # Scheduler
    "get_temperature",
    "get_learning_rate",
    "get_temperature_jax",
    "get_learning_rate_jax",
    "get_curriculum_weights",
    "ScheduleState",
    # Curriculum
    "create_default_phases",
    "create_fast_phases",
    "get_active_phase",
    "get_phase_progress",
    "smooth_transition_weights",
    "CurriculumState",
    # Training
    "train",
    "train_multiphase",
    "TrainingResult",
    "TrainingMetrics",
    "TrainingState",
    "initialize_training_state",
]
