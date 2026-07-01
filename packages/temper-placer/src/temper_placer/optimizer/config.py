"""
Configuration dataclasses for the optimizer.

This module defines all configuration options for the placement optimizer,
including learning rates, temperature schedules, curriculum phases, and
checkpointing settings.
"""

import logging

from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TemperatureSchedule:
    """
    Temperature annealing schedule for Gumbel-Softmax.

    The temperature controls how "soft" the rotation selection is:
    - High temperature (e.g., 5.0): More exploration, softer distributions
    - Low temperature (e.g., 0.1): More exploitation, nearly hard one-hot

    Attributes:
        start: Initial temperature (high for exploration).
        end: Final temperature (low for exploitation).
        warmup_epochs: Epochs to hold at start temperature before annealing.
        anneal_type: "linear", "exponential", or "cosine".
    """

    start: float = 5.0
    end: float = 0.1
    warmup_epochs: int = 100
    anneal_type: str = "exponential"  # "linear", "exponential", "cosine"


@dataclass
class LearningRateSchedule:
    """
    Learning rate schedule configuration.

    Attributes:
        initial: Initial learning rate.
        warmup_epochs: Epochs to ramp up from 0 to initial.
        decay_type: "none", "linear", "exponential", "cosine".
        decay_start_epoch: Epoch to start decay (after warmup).
        final: Final learning rate (for decay schedules).
    """

    initial: float = 0.1
    warmup_epochs: int = 100
    decay_type: str = "cosine"  # "none", "linear", "exponential", "cosine"
    decay_start_epoch: int = 1000
    final: float = 0.001


@dataclass
class CurriculumPhase:
    """
    A single phase in curriculum learning.

    Attributes:
        name: Human-readable name for logging.
        start_epoch: Epoch when this phase starts.
        end_epoch: Epoch when this phase ends.
        loss_weights: Dict mapping loss name to weight multiplier.
        temperature_override: Optional temperature to use during this phase.
        learning_rate_override: Optional LR to use during this phase.
    """

    name: str
    start_epoch: int
    end_epoch: int
    loss_weights: dict[str, float] = field(default_factory=dict)
    temperature_override: float | None = None
    learning_rate_override: float | None = None


@dataclass
class CheckpointConfig:
    """
    Checkpoint saving configuration.

    Attributes:
        enabled: Whether to save checkpoints.
        directory: Directory to save checkpoints (None = temp dir).
        interval: Save checkpoint every N epochs.
        keep_last_n: Number of recent checkpoints to keep.
        save_best: Also save best checkpoint by validation loss.
    """

    enabled: bool = True
    directory: str | None = None
    interval: int = 500
    keep_last_n: int = 3
    save_best: bool = True


@dataclass
class EarlyStoppingConfig:
    """
    Early stopping configuration.

    Attributes:
        enabled: Whether to enable early stopping.
        patience: Epochs without improvement before stopping.
        min_delta: Minimum change to qualify as improvement.
        monitor: Metric to monitor ("loss", "overlap", "wirelength").
        use_convergence: If True, also stop when convergence confidence hits threshold.
        confidence_threshold: Confidence (0-1) to trigger stopping.
        stagnation_threshold: Relative improvement threshold for stagnation (default 1e-4).
        stagnation_epochs: Number of epochs of low improvement before stagnation (default 50).
    """

    enabled: bool = True
    patience: int = 2000  # Increased from 500 for PowerSynth multi-phase strategy
    min_delta: float = 1e-6
    monitor: str = "loss"
    use_convergence: bool = True
    confidence_threshold: float = 0.95
    stagnation_threshold: float = 1e-4
    stagnation_epochs: int = 50
    improvement_threshold: float = 1e-5  # Keep for backward compatibility


@dataclass
class GradNormConfig:
    """
    Configuration for GradNorm-based adaptive loss weighting.

    GradNorm automatically balances multiple loss terms by adjusting their
    weights so that their gradient norms are balanced.

    Attributes:
        alpha: Asymmetry parameter (higher = stronger balancing).
        learning_rate: Learning rate for weight updates.
        update_interval: Update weights every N epochs.
    """

    alpha: float = 1.5
    learning_rate: float = 0.025
    update_interval: int = 1


@dataclass
class ForceDirectedConfig:
    """
    Configuration for force-directed pre-optimization.

    Attributes:
        enabled: Whether to run force-directed unfolding.
        iterations: Number of physics steps.
        learning_rate: Step size for updates.
    """

    enabled: bool = False
    iterations: int = 500
    learning_rate: float = 0.5


@dataclass
class ZoneAwareConfig:
    """
    Configuration for zone-aware initialization.

    Components are biased away from copper zones (GND/VCC planes) to create
    better routing channels and reduce congestion.

    Attributes:
        zone_penalty: Cost multiplier for zone-covered cells (higher = stronger avoidance).
        boundary_margin: Buffer distance around zones in mm.
        adjustment_iters: Number of gradient descent steps for zone avoidance.
        grid_resolution: Resolution of zone cost field in mm.
    """

    zone_penalty: float = 10.0
    boundary_margin: float = 3.0
    adjustment_iters: int = 50
    grid_resolution: float = 0.5


@dataclass
class InitializationConfig:
    """
    Component placement initialization configuration.

    Attributes:
        method: Initialization method ("random", "spectral", "zone_aware_spectral", or "learned").
        spectral_normalized: If True, use normalized Laplacian for spectral.
        spectral_margin: Fraction of board to leave as margin for spectral.
        learned_model_path: Path to pre-trained model for 'learned' init.
        force_directed: Force-directed unfolding configuration.
        zone_aware: Zone avoidance configuration (used when method="zone_aware_spectral").
    """

    method: str = "random"  # "random", "spectral", "zone_aware_spectral", "learned"
    spectral_normalized: bool = True
    spectral_margin: float = 0.1
    learned_model_path: str | None = "models/learned_init.pkl"
    force_directed: ForceDirectedConfig = field(default_factory=ForceDirectedConfig)
    zone_aware: ZoneAwareConfig = field(default_factory=ZoneAwareConfig)


@dataclass
class AdaptiveOverlapConfig:
    """
    Configuration for adaptive overlap weight ramping.

    Helps resolve deadlocks by selectively increasing weights for
    components that are persistent in collision.

    Attributes:
        enabled: Whether to use adaptive weighting.
        ramp_rate: Multiplier for weight increase (e.g., 1.05 = 5%).
        update_interval: Epochs between weight updates.
        max_cap: Maximum weight multiplier allowed.
        decay_rate: Multiplier for weight reduction when no collision.
        collision_threshold: Overlap amount (mm) to trigger ramping.
    """

    enabled: bool = True
    ramp_rate: float = 1.10
    update_interval: int = 10
    max_cap: float = 20.0
    decay_rate: float = 0.95
    collision_threshold: float = 0.1


@dataclass
class JiggleConfig:
    """
    Configuration for stochastic perturbation (jiggling).

    Helps escape local minima by adding noise when training stalls.

    Attributes:
        enabled: Whether to use jiggling.
        ema_threshold: Trigger jiggle when movement EMA falls below this.
        sigma_fraction: Noise magnitude as fraction of board size (e.g. 0.05).
        min_epoch: Don't jiggle before this epoch.
    """

    enabled: bool = True
    ema_threshold: float = 5e-4
    sigma_fraction: float = 0.10
    min_epoch: int = 100


@dataclass
class ReduceLROnPlateauConfig:
    """
    Adaptive learning rate reduction on plateau.
    """

    enabled: bool = True
    factor: float = 0.5
    patience: int = 200
    min_lr: float = 1e-4


@dataclass
class ElectrostaticCongestionConfig:
    """
    Configuration for Electrostatic Congestion model.
    """

    enabled: bool = True
    grid_size: int = 64
    update_interval: int = 100
    potential_weight: float = 1.0


@dataclass
class MultiSeedConfig:
    """
    Configuration for DPP-diversified multi-seed placement.

    When enabled, the optimizer generates a diverse pool of initial placements
    by varying initialization hyperparameters, selects a maximally-diverse subset
    via DPP (Determinantal Point Process), evaluates them through a cheap triage
    pass, and promotes the best seed to full optimization.

    Attributes:
        enabled: Master switch; when False, single-seed behavior is unchanged.
        n_generate: Total seeds to generate (capped at 50).
        n_select: DPP subset size promoted to triage evaluation (2-10).
        n_triage_iters: Triage evaluation iterations per seed.
        dpp_quality_enabled: Whether to use constraint-violation quality scores in DPP.
    """

    enabled: bool = False
    n_generate: int = 50
    n_select: int = 4
    n_triage_iters: int = 30
    dpp_quality_enabled: bool = False

    def __post_init__(self):
        if self.n_generate > 50:
            logger.info(
                "n_generate capped from %d to 50 (maximum).", self.n_generate
            )
            self.n_generate = 50
        if self.n_generate < self.n_select:
            logger.info(
                "n_generate raised from %d to %d (minimum to satisfy n_select).",
                self.n_generate,
                self.n_select,
            )
            self.n_generate = self.n_select
        if self.n_select < 2 or self.n_select > 10:
            raise ValueError(
                f"n_select must be in [2, 10], got {self.n_select}"
            )


@dataclass
class OptimizerConfig:
    """
    Complete optimizer configuration.

    This is the main configuration object passed to the training loop.
    It aggregates all sub-configurations for learning rate, temperature,
    curriculum, checkpointing, and early stopping.

    Attributes:
        epochs: Total number of training epochs.
        seed: Random seed for reproducibility.
        batch_size: Not used for placement (always full batch), reserved for future.
        initialization: Initialization configuration.
        temperature: Gumbel-Softmax temperature schedule.
        learning_rate: Learning rate schedule.
        curriculum_phases: List of curriculum phases (optional).
        checkpoint: Checkpoint configuration.
        early_stopping: Early Stopping configuration.
        log_interval: Log metrics every N epochs.
        validate_interval: Run validation every N epochs.
        gradient_clip_norm: Max gradient norm (None = no clipping).
        use_adam: Use Adam optimizer (True) or SGD (False).
        adam_beta1: Adam beta1 parameter.
        adam_beta2: Adam beta2 parameter.
    """

    # Core training parameters
    epochs: int = 8000
    seed: int = 42
    batch_size: int = 1  # Full batch for placement

    # Initialization
    initialization: InitializationConfig = field(default_factory=InitializationConfig)

    # Schedules
    temperature: TemperatureSchedule = field(default_factory=TemperatureSchedule)
    learning_rate: LearningRateSchedule = field(default_factory=LearningRateSchedule)

    # Curriculum (optional - if empty, uses constant weights)
    curriculum_phases: list[CurriculumPhase] = field(default_factory=list)

    # Checkpointing
    checkpoint: CheckpointConfig = field(default_factory=CheckpointConfig)

    # Early stopping
    early_stopping: EarlyStoppingConfig = field(default_factory=EarlyStoppingConfig)

    # Logging and validation
    log_interval: int = 100
    validate_interval: int = 500

    # Optimizer settings
    gradient_clip_norm: float | None = 1.0
    use_adam: bool = True
    adam_beta1: float = 0.9
    adam_beta2: float = 0.999

    # Advanced optimization techniques (ablation support)
    use_gumbel_rotation: bool = True
    adaptive_overlap_enabled: bool = True  # Keep for backward compat
    adaptive_overlap: AdaptiveOverlapConfig = field(default_factory=AdaptiveOverlapConfig)
    jiggle_enabled: bool = True  # Keep for backward compat
    jiggle: JiggleConfig = field(default_factory=JiggleConfig)
    use_grad_norm: bool = False
    grad_norm: GradNormConfig = field(default_factory=GradNormConfig)

    # Adaptive Learning Rate (ALR)
    reduce_lr_on_plateau: ReduceLROnPlateauConfig = field(default_factory=ReduceLROnPlateauConfig)

    # Electrostatic Congestion
    electrostatic: ElectrostaticCongestionConfig = field(
        default_factory=ElectrostaticCongestionConfig
    )

    # Centrality-driven optimization (temper-s7g)
    use_centrality_weighting: bool = True
    centrality_priority_scale: float = 2.0  # Max boost for hub components

    # Soft-body inflation (temper-gcp.2)
    inflation_ramp: float = 0.3  # Fraction of epochs to ramp component size 5%→100%

    # DPP multi-seed diversification
    multi_seed: MultiSeedConfig = field(default_factory=MultiSeedConfig)

    @classmethod
    def fast_test(cls) -> "OptimizerConfig":
        """
        Create a fast configuration for testing.

        Returns config with reduced epochs and intervals suitable for
        unit tests and quick experiments.
        """
        return cls(
            epochs=100,
            seed=42,
            temperature=TemperatureSchedule(start=2.0, end=0.5, warmup_epochs=10),
            learning_rate=LearningRateSchedule(
                initial=0.1,
                warmup_epochs=10,
                decay_type="none",
            ),
            checkpoint=CheckpointConfig(enabled=False),
            early_stopping=EarlyStoppingConfig(enabled=False),
            log_interval=10,
            validate_interval=50,
        )

    @classmethod
    def default_curriculum(cls) -> "OptimizerConfig":
        """
        Create configuration with default curriculum phases.

        This implements the recommended multi-phase training:
        1. Spread (0-1000): Exploration and distribution
        2. Feasibility (1000-3000): Overlap and boundary
        3. Design Rules (3000-5000): Clearance and thermal
        4. Performance (5000-7000): Wirelength and loops
        5. Refinement (7000-8000): All losses, fine-tuning
        """
        phases = [
            CurriculumPhase(
                name="spread",
                start_epoch=0,
                end_epoch=1000,
                loss_weights={
                    "spread": 10.0,
                    "rotation_entropy": 5.0,
                    "boundary": 20.0,
                    "zone": 30.0,
                    "overlap": 5.0,
                },
                temperature_override=5.0,
            ),
            CurriculumPhase(
                name="feasibility",
                start_epoch=1000,
                end_epoch=3000,
                loss_weights={
                    "spread": 2.0,
                    "overlap": 200.0,
                    "boundary": 100.0,
                    "clearance": 100.0,
                    "zone": 50.0,
                    "wirelength": 10.0,
                },
                temperature_override=3.0,
            ),
            CurriculumPhase(
                name="design_rules",
                start_epoch=3000,
                end_epoch=5000,
                loss_weights={
                    "overlap": 200.0,
                    "boundary": 100.0,
                    "clearance": 100.0,
                    "loop_area": 100.0,
                    "thermal_spread": 25.0,
                    "grouping": 50.0,
                    "decoupling": 20.0,
                    "wirelength": 20.0,
                },
                temperature_override=1.0,
            ),
            CurriculumPhase(
                name="performance",
                start_epoch=5000,
                end_epoch=7000,
                loss_weights={
                    "overlap": 250.0,
                    "boundary": 100.0,
                    "clearance": 100.0,
                    "loop_area": 150.0,
                    "power_path": 80.0,
                    "wirelength": 40.0,
                    "congestion": 20.0,
                    "alignment": 10.0,
                },
                temperature_override=0.5,
            ),
            CurriculumPhase(
                name="refinement",
                start_epoch=7000,
                end_epoch=8000,
                loss_weights={
                    "overlap": 250.0,
                    "loop_area": 150.0,
                    "power_path": 80.0,
                    "wirelength": 40.0,
                    "ground_crossing": 30.0,
                },
                temperature_override=0.1,
            ),
        ]

        return cls(
            epochs=8000,
            curriculum_phases=phases,
            temperature=TemperatureSchedule(start=5.0, end=0.1),
            learning_rate=LearningRateSchedule(
                initial=0.1,
                warmup_epochs=200,
                decay_type="cosine",
                decay_start_epoch=6000,
                final=0.01,
            ),
        )


def get_default_loss_weights() -> dict[str, float]:
    """
    Get default loss weights for placement optimization.

    These weights are tuned for the Temper induction cooker PCB
    with ~100 components and emphasis on HV/LV isolation.

    Returns:
        Dict mapping loss name to default weight.
    """
    return {
        # Hard constraints (high weights)
        "overlap": 100.0,
        "boundary": 50.0,
        "clearance": 80.0,  # HV-LV safety critical
        "drc_proxy": 60.0,  # Width-inflated DRC proxy (manufacturability)
        # Medium constraints
        "thermal": 30.0,  # IGBT heatsink placement
        "loop_area": 40.0,  # Gate drive loop EMI
        "zone": 20.0,  # Component zones
        "ground_crossing": 20.0,  # Ground domain splits
        # Soft objectives
        "wirelength": 10.0,
        "congestion": 5.0,
        # Regularization
        "spread": 5.0,
        "rotation_entropy": 1.0,
        "center_of_mass": 1.0,
        "edge_avoidance": 0.0,  # Disabled by default (experimental, see temper-a98v)
    }
