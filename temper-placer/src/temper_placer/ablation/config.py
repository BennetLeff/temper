"""Configuration dataclasses for ablation study experiments."""

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ComponentToggle:
    """Toggle individual pipeline components on/off for ablation experiments.

    All fields default to True (enabled). Set to False to disable a component.
    """

    # ========================
    # HEURISTICS (11 total)
    # ========================

    # Initialization heuristics (Priority -1)
    spectral_init: bool = True
    """Use spectral placement for initial global layout (spectral.py)"""

    force_directed: bool = True
    """Use force-directed layout for refinement (force_directed.py)"""

    # Structural heuristics (Priority 1)
    connector_edge_snap: bool = True
    """Snap connectors to board edges (structural.py)"""

    thermal_edge: bool = True
    """Place thermal components near edges (structural.py)"""

    critical_loop: bool = True
    """Pre-minimize critical current loops (structural.py)"""

    # Organizational heuristics (Priority 2)
    functional_clustering: bool = True
    """Cluster components by functional module (organizational.py)"""

    power_flow_topology: bool = True
    """Arrange components by power flow (organizational.py)"""

    decoupling_cap: bool = True
    """Place decoupling caps near ICs (organizational.py)"""

    domain_separation: bool = True
    """Separate analog/digital domains (organizational.py)"""

    star_ground: bool = True
    """Enforce star ground topology (organizational.py)"""

    # Style heuristics (Priority 3)
    signal_flow: bool = True
    """Preserve signal flow patterns (style.py)"""

    # ========================
    # OPTIMIZATION TECHNIQUES (8 total)
    # ========================

    curriculum_learning: bool = True
    """Use multi-phase curriculum learning with dynamic loss weights"""

    gumbel_softmax_rotation: bool = True
    """Use Gumbel-Softmax for differentiable rotation sampling"""

    adaptive_overlap_weighting: bool = True
    """Dynamically increase weights for stuck overlapping components"""

    stochastic_perturbation: bool = True
    """Apply random 'jiggle' when optimization stalls"""

    centrality_gradient_scaling: bool = True
    """Scale gradients by component centrality (hub prioritization)"""

    temperature_annealing: bool = True
    """Anneal Gumbel-Softmax temperature from high to low"""

    learning_rate_annealing: bool = True
    """Decay learning rate during training"""

    gradient_clipping: bool = True
    """Clip gradient norms to prevent instability"""

    # ========================
    # UTILITY METHODS
    # ========================

    def get_enabled_heuristics(self) -> list[str]:
        """Return list of enabled heuristic names."""
        heuristic_fields = [
            "spectral_init",
            "force_directed",
            "connector_edge_snap",
            "thermal_edge",
            "critical_loop",
            "functional_clustering",
            "power_flow_topology",
            "decoupling_cap",
            "domain_separation",
            "star_ground",
            "signal_flow",
        ]
        return [f for f in heuristic_fields if getattr(self, f)]

    def get_enabled_techniques(self) -> list[str]:
        """Return list of enabled technique names."""
        technique_fields = [
            "curriculum_learning",
            "gumbel_softmax_rotation",
            "adaptive_overlap_weighting",
            "stochastic_perturbation",
            "centrality_gradient_scaling",
            "temperature_annealing",
            "learning_rate_annealing",
            "gradient_clipping",
        ]
        return [f for f in technique_fields if getattr(self, f)]

    def count_enabled(self) -> tuple[int, int]:
        """Return (enabled_heuristics, enabled_techniques) counts."""
        return (len(self.get_enabled_heuristics()), len(self.get_enabled_techniques()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ComponentToggle":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})

    @classmethod
    def all_disabled(cls) -> "ComponentToggle":
        """Create toggle with all components disabled."""
        return cls(**{f.name: False for f in fields(cls)})


@dataclass
class LossToggle:
    """Toggle individual loss functions on/off for ablation experiments.

    All fields default to True (enabled). Set to False to disable a loss.
    """

    # ========================
    # HARD CONSTRAINTS
    # ========================

    overlap: bool = True
    """Penalize overlapping components (overlap.py)"""

    boundary: bool = True
    """Keep components within board boundaries (boundary.py)"""

    clearance: bool = True
    """Enforce HV-LV clearance requirements (clearance.py)"""

    # ========================
    # DESIGN RULES
    # ========================

    thermal: bool = True
    """Place thermal components near edges (thermal.py)"""

    zone: bool = True
    """Enforce zone membership constraints (zone.py)"""

    ground_crossing: bool = True
    """Avoid crossing ground domain splits (ground_crossing.py)"""

    net_class: bool = True
    """Maintain net class separation (net_class.py)"""

    # ========================
    # PERFORMANCE OBJECTIVES
    # ========================

    wirelength: bool = True
    """Minimize half-perimeter wire length (wirelength.py)"""

    loop_area: bool = True
    """Minimize critical current loop areas (loop_area.py)"""

    congestion: bool = True
    """Balance routing demand across board (congestion.py)"""

    power_path: bool = True
    """Minimize power path parasitic inductance (power_path.py)"""

    return_path: bool = True
    """Optimize current return paths (return_path.py)"""

    critical_path: bool = True
    """Minimize critical signal path lengths (critical_path.py)"""

    # ========================
    # REGULARIZATION
    # ========================

    spread: bool = True
    """Prevent component clustering (regularization.py)"""

    rotation_entropy: bool = True
    """Encourage rotation exploration early (regularization.py)"""

    center_of_mass: bool = True
    """Balance component distribution (regularization.py)"""

    # ========================
    # DOMAIN-SPECIFIC
    # ========================

    crystal: bool = True
    """Crystal oscillator placement rules (crystal.py)"""

    mechanical: bool = True
    """Mechanical mounting constraints (mechanical.py)"""

    via_density: bool = True
    """Via placement balance (via_density.py)"""

    coil: bool = True
    """Induction coil constraints (coil.py)"""

    drc: bool = True
    """Non-differentiable DRC penalty (drc_loss.py)"""

    group_cluster: bool = True
    """Cluster functional groups together (grouping.py)"""

    group_separation: bool = True
    """Separate different functional groups (grouping.py)"""

    proximity: bool = True
    """Enforce specific component proximity rules (grouping.py)"""

    # ========================
    # UTILITY METHODS
    # ========================

    def get_enabled_losses(self) -> list[str]:
        """Return list of enabled loss names."""
        return [f.name for f in fields(self) if getattr(self, f.name)]

    def count_enabled(self) -> int:
        """Return count of enabled losses."""
        return len(self.get_enabled_losses())

    def get_by_category(self) -> dict[str, list[str]]:
        """Return enabled losses grouped by category."""
        categories = {
            "hard_constraints": ["overlap", "boundary", "clearance"],
            "design_rules": ["thermal", "zone", "ground_crossing", "net_class"],
            "performance": [
                "wirelength",
                "loop_area",
                "congestion",
                "power_path",
                "return_path",
                "critical_path",
            ],
            "regularization": ["spread", "rotation_entropy", "center_of_mass"],
            "domain_specific": ["crystal", "mechanical", "via_density", "coil"],
        }
        return {
            cat: [loss_name for loss_name in losses if getattr(self, loss_name, False)]
            for cat, losses in categories.items()
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LossToggle":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})

    @classmethod
    def hard_constraints_only(cls) -> "LossToggle":
        """Create toggle with only hard constraints enabled."""
        toggle = cls.all_disabled()
        toggle.overlap = True
        toggle.boundary = True
        return toggle

    @classmethod
    def all_disabled(cls) -> "LossToggle":
        """Create toggle with all losses disabled."""
        return cls(**{f.name: False for f in fields(cls)})


@dataclass
class HyperparameterOverrides:
    """Override specific hyperparameters for an experiment."""

    loss_weights: dict[str, float] | None = None
    """Override default loss weights"""

    learning_rate_initial: float | None = None
    """Override initial learning rate (default: 0.1)"""

    learning_rate_final: float | None = None
    """Override final learning rate (default: 0.01)"""

    temperature_start: float | None = None
    """Override Gumbel-Softmax start temperature (default: 5.0)"""

    temperature_end: float | None = None
    """Override Gumbel-Softmax end temperature (default: 0.1)"""

    epochs: int | None = None
    """Override number of training epochs (default: 8000)"""

    overlap_margin: float | None = None
    """Override overlap loss margin (default: 1.0)"""

    def merge_with_defaults(self, defaults: dict[str, Any]) -> dict[str, Any]:
        """Merge overrides with defaults, preferring overrides."""
        result = defaults.copy()
        for field_name, value in asdict(self).items():
            if value is not None:
                result[field_name] = value
        return result


@dataclass
class ExperimentConfig:
    """Configuration for a single ablation experiment."""

    name: str
    """Unique identifier for this experiment (e.g., 'ablate_spectral')"""

    description: str
    """Human-readable description of what this experiment tests"""

    components: ComponentToggle = field(default_factory=ComponentToggle)
    """Which heuristics and techniques are enabled"""

    losses: LossToggle = field(default_factory=LossToggle)
    """Which loss functions are enabled"""

    hyperparameters: HyperparameterOverrides = field(
        default_factory=HyperparameterOverrides
    )
    """Hyperparameter overrides for this experiment"""

    tags: list[str] = field(default_factory=list)
    """Tags for filtering (e.g., ['single_ablation', 'heuristic'])"""

    def __post_init__(self):
        # Validate name is identifier-safe
        if not self.name.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"Invalid experiment name: {self.name}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "components": self.components.to_dict(),
            "losses": self.losses.to_dict(),
            "hyperparameters": asdict(self.hyperparameters),
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentConfig":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            description=data["description"],
            components=ComponentToggle.from_dict(data.get("components", {})),
            losses=LossToggle.from_dict(data.get("losses", {})),
            hyperparameters=HyperparameterOverrides(
                **data.get("hyperparameters", {})
            ),
            tags=data.get("tags", []),
        )

    def get_config_hash(self) -> str:
        """Return hash of config for deduplication."""
        import hashlib

        config_str = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:12]


@dataclass
class AblationStudyConfig:
    """Top-level configuration for an ablation study."""

    study_name: str
    """Name of the study (used in reports and file paths)"""

    experiments: list[ExperimentConfig]
    """List of experiments to run"""

    seeds: list[int] = field(
        default_factory=lambda: [42, 123, 456, 789, 1024]
    )
    """Random seeds for reproducibility (5 seeds = good statistical power)"""

    test_cases: list[Path] = field(default_factory=list)
    """PCB files to test on"""

    output_dir: Path = field(default_factory=lambda: Path("ablation_results"))
    """Directory for results output"""

    parallel_workers: int = 4
    """Number of parallel workers for execution"""

    checkpoint_interval: int = 10
    """Save checkpoint every N completed runs"""

    metrics_to_collect: list[str] = field(
        default_factory=lambda: [
            "final_loss",
            "best_loss",
            "convergence_epoch",
            "drc_error_count",
            "wirelength",
            "loop_area_compliance",
            "elapsed_time",
        ]
    )
    """Metrics to collect for each run"""

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        self.test_cases = [Path(tc) for tc in self.test_cases]

    def get_total_runs(self) -> int:
        """Return total number of experiment runs."""
        return len(self.experiments) * len(self.seeds) * len(self.test_cases)

    def estimate_runtime_hours(self, minutes_per_run: float = 10) -> float:
        """Estimate total runtime in hours."""
        total_minutes = self.get_total_runs() * minutes_per_run
        parallel_minutes = total_minutes / self.parallel_workers
        return parallel_minutes / 60

    def save(self, path: Path) -> None:
        """Save configuration to YAML file."""
        data = {
            "study_name": self.study_name,
            "experiments": [e.to_dict() for e in self.experiments],
            "seeds": self.seeds,
            "test_cases": [str(tc) for tc in self.test_cases],
            "output_dir": str(self.output_dir),
            "parallel_workers": self.parallel_workers,
            "checkpoint_interval": self.checkpoint_interval,
            "metrics_to_collect": self.metrics_to_collect,
        }
        path.write_text(yaml.dump(data, default_flow_style=False))

    @classmethod
    def load(cls, path: Path) -> "AblationStudyConfig":
        """Load configuration from YAML file."""
        data = yaml.safe_load(path.read_text())
        return cls(
            study_name=data["study_name"],
            experiments=[
                ExperimentConfig.from_dict(e) for e in data["experiments"]
            ],
            seeds=data.get("seeds", [42, 123, 456, 789, 1024]),
            test_cases=[Path(tc) for tc in data.get("test_cases", [])],
            output_dir=Path(data.get("output_dir", "ablation_results")),
            parallel_workers=data.get("parallel_workers", 4),
            checkpoint_interval=data.get("checkpoint_interval", 10),
            metrics_to_collect=data.get("metrics_to_collect", []),
        )

    def filter_experiments(self, tags: list[str]) -> "AblationStudyConfig":
        """Return new config with only experiments matching tags."""
        tag_set = set(tags)
        filtered = [e for e in self.experiments if tag_set & set(e.tags)]
        return AblationStudyConfig(
            study_name=self.study_name,
            experiments=filtered,
            seeds=self.seeds,
            test_cases=self.test_cases,
            output_dir=self.output_dir,
            parallel_workers=self.parallel_workers,
            checkpoint_interval=self.checkpoint_interval,
            metrics_to_collect=self.metrics_to_collect,
        )
