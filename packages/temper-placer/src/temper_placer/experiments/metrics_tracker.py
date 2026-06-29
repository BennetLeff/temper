"""
Metrics tracking infrastructure for experiment reproducibility.

Provides systematic collection, storage, and analysis of optimization metrics.
All experiments should use this to ensure consistent measurement.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


def create_run_id(
    experiment_name: str,
    seed: int,
    timestamp: datetime | None = None,
) -> str:
    """Create a unique run ID for tracking."""
    ts = timestamp or datetime.now()
    ts_str = ts.strftime("%Y%m%d_%H%M%S")
    return f"{experiment_name}_seed{seed}_{ts_str}"


@dataclass
class RunMetrics:
    """Metrics collected from a single optimization run."""

    # Identification
    run_id: str
    experiment_name: str
    seed: int
    timestamp: str
    config_hash: str

    # Hard constraints
    overlap_loss: float
    boundary_loss: float
    hv_clearance_violations: int = 0
    zone_violations: int = 0

    # Performance metrics
    hpwl_mm: float = 0.0
    gate_loop_area_mm2: float = 0.0
    bootstrap_loop_area_mm2: float = 0.0
    commutation_loop_area_mm2: float = 0.0
    igbt_edge_distance_mm: float = 0.0

    # Optimization metrics
    final_loss: float = 0.0
    best_loss: float = 0.0
    convergence_epoch: int = 0
    epochs_completed: int = 0
    elapsed_seconds: float = 0.0

    # DRC metrics
    drc_errors: int = -1  # -1 means not measured
    drc_warnings: int = -1

    # Routing metrics (optional, requires autorouter)
    routing_completion_percent: float = -1.0
    unrouted_nets: int = -1

    # Additional metrics (flexible)
    extra_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunMetrics":
        """Create from dictionary."""
        return cls(**data)

    def passes_hard_constraints(self, tolerance: float = 0.01) -> bool:
        """Check if run passes all hard constraints."""
        return (
            self.overlap_loss < tolerance
            and self.boundary_loss < tolerance
            and self.hv_clearance_violations == 0
            and self.zone_violations == 0
        )

    def get_summary(self) -> dict[str, Any]:
        """Get summary for quick display."""
        return {
            "run_id": self.run_id,
            "seed": self.seed,
            "passes_hard_constraints": self.passes_hard_constraints(),
            "overlap": self.overlap_loss,
            "hpwl_mm": self.hpwl_mm,
            "drc_errors": self.drc_errors,
            "convergence_epoch": self.convergence_epoch,
        }


class MetricsTracker:
    """
    Tracks metrics across multiple experiment runs.

    Provides:
    - Automatic run ID generation
    - JSON/YAML persistence
    - Baseline comparison
    - Statistical aggregation

    Usage:
        tracker = MetricsTracker("experiments/my_experiment")
        tracker.record_run(metrics)
        tracker.save()
        summary = tracker.get_summary_statistics()
    """

    def __init__(
        self,
        output_dir: str | Path,
        experiment_name: str = "unnamed",
        auto_save: bool = True,
    ):
        self.output_dir = Path(output_dir)
        self.experiment_name = experiment_name
        self.auto_save = auto_save
        self.runs: list[RunMetrics] = []

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load existing runs if present
        self._load_existing()

    def _load_existing(self) -> None:
        """Load existing runs from output directory."""
        runs_file = self.output_dir / "runs.json"
        if runs_file.exists():
            with open(runs_file) as f:
                data = json.load(f)
                self.runs = [RunMetrics.from_dict(r) for r in data.get("runs", [])]

    def record_run(self, metrics: RunMetrics) -> None:
        """Record a completed run."""
        self.runs.append(metrics)
        if self.auto_save:
            self.save()

    def save(self) -> None:
        """Save all runs to disk."""
        runs_file = self.output_dir / "runs.json"
        data = {
            "experiment_name": self.experiment_name,
            "total_runs": len(self.runs),
            "last_updated": datetime.now().isoformat(),
            "runs": [r.to_dict() for r in self.runs],
        }
        with open(runs_file, "w") as f:
            json.dump(data, f, indent=2)

        # Also save summary statistics
        self._save_summary()

    def _save_summary(self) -> None:
        """Save summary statistics as YAML."""
        summary_file = self.output_dir / "summary.yaml"
        summary = self.get_summary_statistics()
        with open(summary_file, "w") as f:
            yaml.dump(summary, f, default_flow_style=False)

    def get_summary_statistics(self) -> dict[str, Any]:
        """Compute summary statistics across all runs."""
        if not self.runs:
            return {"error": "No runs recorded"}

        import statistics

        # Extract metrics
        overlaps = [r.overlap_loss for r in self.runs]
        boundaries = [r.boundary_loss for r in self.runs]
        hpwls = [r.hpwl_mm for r in self.runs]
        convergences = [float(r.convergence_epoch) for r in self.runs]
        final_losses = [r.final_loss for r in self.runs]

        # Count failures
        hard_constraint_passes = sum(1 for r in self.runs if r.passes_hard_constraints())
        failure_rate = 1.0 - (hard_constraint_passes / len(self.runs))

        def safe_stats(values: list[float]) -> dict[str, float]:
            """Compute statistics safely."""
            if not values or all(v == 0 for v in values):
                return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "cv": 0.0}
            mean = statistics.mean(values)
            std = statistics.stdev(values) if len(values) > 1 else 0.0
            cv = std / mean if mean > 0 else 0.0
            return {
                "mean": round(mean, 4),
                "std": round(std, 4),
                "min": round(min(values), 4),
                "max": round(max(values), 4),
                "cv": round(cv, 4),
            }

        return {
            "experiment_name": self.experiment_name,
            "total_runs": len(self.runs),
            "failure_rate": round(failure_rate, 4),
            "hard_constraint_passes": hard_constraint_passes,
            "metrics": {
                "overlap_loss": safe_stats(overlaps),
                "boundary_loss": safe_stats(boundaries),
                "hpwl_mm": safe_stats(hpwls),
                "convergence_epoch": safe_stats(convergences),
                "final_loss": safe_stats(final_losses),
            },
        }

    def compare_to_baseline(
        self, baseline: "MetricsTracker"
    ) -> dict[str, Any]:
        """Compare this experiment to a baseline."""
        if not self.runs or not baseline.runs:
            return {"error": "Insufficient data for comparison"}

        import statistics

        def compare_metric(name: str, higher_is_better: bool = False) -> dict[str, Any]:
            """Compare a single metric."""
            exp_values = [getattr(r, name) for r in self.runs]
            base_values = [getattr(r, name) for r in baseline.runs]

            exp_mean = statistics.mean(exp_values)
            base_mean = statistics.mean(base_values)

            # Compute effect size (Cohen's d)
            pooled_std = (
                (statistics.stdev(exp_values) + statistics.stdev(base_values)) / 2
                if len(exp_values) > 1 and len(base_values) > 1
                else 1.0
            )
            cohens_d = (exp_mean - base_mean) / pooled_std if pooled_std > 0 else 0.0

            # Determine direction
            improvement = exp_mean > base_mean if higher_is_better else exp_mean < base_mean

            return {
                "experiment_mean": round(exp_mean, 4),
                "baseline_mean": round(base_mean, 4),
                "difference": round(exp_mean - base_mean, 4),
                "percent_change": round(
                    (exp_mean - base_mean) / base_mean * 100 if base_mean != 0 else 0, 2
                ),
                "cohens_d": round(cohens_d, 4),
                "improvement": improvement,
            }

        return {
            "experiment": self.experiment_name,
            "baseline": baseline.experiment_name,
            "comparisons": {
                "overlap_loss": compare_metric("overlap_loss", higher_is_better=False),
                "hpwl_mm": compare_metric("hpwl_mm", higher_is_better=False),
                "final_loss": compare_metric("final_loss", higher_is_better=False),
                "convergence_epoch": compare_metric(
                    "convergence_epoch", higher_is_better=False
                ),
            },
        }

    def get_config_hash(self, config: dict[str, Any]) -> str:
        """Generate hash of configuration for reproducibility."""
        config_str = json.dumps(config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()[:12]

    def filter_runs(
        self,
        passes_constraints: bool | None = None,
        min_epochs: int | None = None,
        seed: int | None = None,
    ) -> list[RunMetrics]:
        """Filter runs by criteria."""
        result = self.runs

        if passes_constraints is not None:
            result = [r for r in result if r.passes_hard_constraints() == passes_constraints]

        if min_epochs is not None:
            result = [r for r in result if r.epochs_completed >= min_epochs]

        if seed is not None:
            result = [r for r in result if r.seed == seed]

        return result

    def export_csv(self, path: str | Path | None = None) -> Path:
        """Export runs to CSV for external analysis."""
        import csv

        path = Path(path) if path else self.output_dir / "runs.csv"

        if not self.runs:
            return path

        # Get all field names
        fieldnames = list(asdict(self.runs[0]).keys())

        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for run in self.runs:
                writer.writerow(run.to_dict())

        return path
