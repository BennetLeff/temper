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

from temper_placer.optimizer.checkpoint import (
    Checkpoint,
    CheckpointManager,
    create_checkpoint_from_training_state,
    restore_training_state_from_checkpoint,
)
from temper_placer.optimizer.config import (
    AdaptiveOverlapConfig,
    CheckpointConfig,
    CurriculumPhase,
    EarlyStoppingConfig,
    InitializationConfig,
    LearningRateSchedule,
    MultiSeedConfig,
    OptimizerConfig,
    TemperatureSchedule,
    ZoneAwareConfig,
    get_default_loss_weights,
)
from temper_placer.optimizer.convergence_analytics import (
    ConvergenceAnalyzer,
    ConvergenceConfidence,
    ConvergenceConfidenceScorer,
    ImprovementMetrics,
    LossImprovementTracker,
    PlateauEvent,
)
from temper_placer.optimizer.curriculum import (
    CurriculumState,
    create_default_phases,
    create_fast_phases,
    get_active_phase,
    get_phase_progress,
    smooth_transition_weights,
)
from temper_placer.optimizer.initialization import (
    HierarchicalGroupInitializer,
)
from temper_placer.optimizer.postprocess import (
    DEFAULT_GRID_SIZE,
    PostProcessConfig,
    PostProcessResult,
    detailed_local_search,
    discrete_rotation_refinement,
    discrete_rotation_refinement_beam,
    discrete_rotation_refinement_greedy,
    finalize_placement,
    get_rotation_index,
    postprocess,
    set_rotation_index,
    snap_to_grid,
    snap_to_grid_with_overlap_check,
)
from temper_placer.optimizer.scheduler import (
    ScheduleState,
    get_curriculum_weights,
    get_learning_rate,
    get_learning_rate_jax,
    get_temperature,
    get_temperature_jax,
)
from temper_placer.optimizer.train import (
    NumericalInstabilityError,
    ParallelTrainingResult,
    TrainingMetrics,
    TrainingResult,
    TrainingState,
    initialize_training_state,
    train,
    train_dpp_multiseed,
    train_multiphase,
)
from temper_placer.optimizer.validation_callback import (
    ValidationCallback,
    ValidationConfig,
    ValidationResult,
    create_validation_callback,
)
from temper_placer.optimizer.zone_aware_init import (
    ZoneAwareSpectralInitializer,
    adjust_positions_for_zones,
    create_zone_cost_field,
)

__all__ = [
    # Config
    "OptimizerConfig",
    "MultiSeedConfig",
    "InitializationConfig",
    "TemperatureSchedule",
    "LearningRateSchedule",
    "CurriculumPhase",
    "CheckpointConfig",
    "EarlyStoppingConfig",
    "AdaptiveOverlapConfig",
    "ZoneAwareConfig",
    "get_default_loss_weights",
    # Convergence Analytics
    "LossImprovementTracker",
    "ImprovementMetrics",
    "ConvergenceAnalyzer",
    "PlateauEvent",
    "ConvergenceConfidence",
    "ConvergenceConfidenceScorer",
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
    "train_dpp_multiseed",
    "ParallelTrainingResult",
    "TrainingResult",
    "TrainingMetrics",
    "TrainingState",
    "initialize_training_state",
    "NumericalInstabilityError",
    # Initialization
    "HierarchicalGroupInitializer",
    # Zone-aware initialization
    "ZoneAwareSpectralInitializer",
    "create_zone_cost_field",
    "adjust_positions_for_zones",
    # Validation
    "ValidationConfig",
    "ValidationResult",
    "ValidationCallback",
    "create_validation_callback",
    # Postprocessing
    "PostProcessConfig",
    "PostProcessResult",
    "snap_to_grid",
    "snap_to_grid_with_overlap_check",
    "detailed_local_search",
    "discrete_rotation_refinement",
    "discrete_rotation_refinement_greedy",
    "discrete_rotation_refinement_beam",
    "postprocess",
    "finalize_placement",
    "get_rotation_index",
    "set_rotation_index",
    "DEFAULT_GRID_SIZE",
    # Checkpointing
    "Checkpoint",
    "CheckpointManager",
    "create_checkpoint_from_training_state",
    "restore_training_state_from_checkpoint",
]
