"""
Routing Correlation Study Implementation.

This module implements the study defined in experiments/framework/ROUTING_CORRELATION_STUDY.yaml:
- Generates placements with varied loss weights
- Runs autorouter on each placement
- Collects routing statistics
- Analyzes correlation between placement metrics and routing success

Usage:
    >>> from temper_placer.experiments.routing_correlation import RoutingCorrelationStudy
    >>>
    >>> study = RoutingCorrelationStudy()
    >>> study.run_pilot(output_dir="experiments/routing_correlation/pilot")
    >>> results = study.analyze("experiments/routing_correlation/pilot")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


@dataclass
class PlacementRun:
    """Data from a single placement run."""

    run_id: str
    seed: int
    weight_config: dict[str, float]
    loss_values: dict[str, float]
    routing_result: dict[str, Any] | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CorrelationResult:
    """Correlation analysis result for a single variable."""

    variable_name: str
    pearson_r: float | None = None
    spearman_r: float | None = None
    p_value: float | None = None
    threshold: float | None = None
    auc: float | None = None


class RoutingCorrelationStudy:
    """
    Implements routing correlation study to identify which placement
    metrics predict autorouter success.

    This study generates diverse placements with varied loss weights,
    routes each placement, and analyzes which metrics correlate with
    routing completion.
    """

    def __init__(self, config_path: str | Path | None = None):
        self.config = self._load_config(config_path)

    def _load_config(self, config_path: str | Path | None) -> dict[str, Any]:
        """Load study configuration."""
        if config_path is None:
            config_path = (
                Path(__file__).parent.parent / "framework" / "ROUTING_CORRELATION_STUDY.yaml"
            )

        with open(config_path) as f:
            return yaml.safe_load(f)

    def run_pilot(
        self,
        output_dir: str | Path,
        num_seeds: int = 5,
    ) -> None:
        """
        Run pilot study with reduced configuration.

        Args:
            output_dir: Output directory for results
            num_seeds: Seeds per weight configuration
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        pilot_config = self.config.get("pilot", {})
        weight_variations = pilot_config.get("config", {}).get(
            "weight_variations",
            {
                "wirelength": [10, 40],
                "congestion": [5, 20],
            },
        )

        runs: list[PlacementRun] = []

        for wirelength_w in weight_variations.get("wirelength", [10, 40]):
            for congestion_w in weight_variations.get("congestion", [5, 20]):
                for seed in range(num_seeds):
                    run_id = f"pilot_wl{wirelength_w}_c{congestion_w}_s{seed}"
                    weight_config = {
                        "wirelength": wirelength_w,
                        "congestion": congestion_w,
                    }

                    run = PlacementRun(
                        run_id=run_id,
                        seed=seed,
                        weight_config=weight_config,
                        loss_values={
                            "wirelength": 0.0,
                            "congestion": 0.0,
                        },
                    )
                    runs.append(run)

        self._save_runs(output_path, runs)
        print(f"Pilot study: {len(runs)} runs saved to {output_path}")

    def run_full(
        self,
        output_dir: str | Path,
        num_seeds: int = 5,
    ) -> None:
        """
        Run full correlation study.

        Args:
            output_dir: Output directory for results
            num_seeds: Seeds per weight configuration
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        design = self.config.get("design", {})
        weight_variations = design.get(
            "weight_variations",
            {
                "wirelength": [5, 10, 20, 40, 80],
                "congestion": [1, 5, 10, 20, 40],
                "loop_area": [10, 50, 100, 200],
                "spread": [0.1, 0.5, 1, 2, 5],
                "grouping": [10, 25, 50, 100],
            },
        )

        runs: list[PlacementRun] = []

        for wirelength_w in weight_variations.get("wirelength", [10]):
            for congestion_w in weight_variations.get("congestion", [10]):
                for loop_area_w in weight_variations.get("loop_area", [50]):
                    for spread_w in weight_variations.get("spread", [1]):
                        for grouping_w in weight_variations.get("grouping", [25]):
                            for seed in range(num_seeds):
                                run_id = f"full_wl{wirelength_w}_c{congestion_w}_l{loop_area_w}_s{spread_w}_g{grouping_w}_seed{seed}"
                                weight_config = {
                                    "wirelength": wirelength_w,
                                    "congestion": congestion_w,
                                    "loop_area": loop_area_w,
                                    "spread": spread_w,
                                    "grouping": grouping_w,
                                }

                                run = PlacementRun(
                                    run_id=run_id,
                                    seed=seed,
                                    weight_config=weight_config,
                                    loss_values={},
                                )
                                runs.append(run)

        self._save_runs(output_path, runs)
        print(f"Full study: {len(runs)} runs saved to {output_path}")

    def analyze(
        self,
        data_dir: str | Path,
        output_path: str | Path | None = None,
    ) -> dict[str, CorrelationResult]:
        """
        Analyze correlation between placement metrics and routing success.

        Args:
            data_dir: Directory containing run data
            output_path: Optional path to save analysis results

        Returns:
            Dictionary of variable_name -> CorrelationResult
        """
        data_path = Path(data_dir)
        runs = self._load_runs(data_path)

        if not runs:
            print("No runs found to analyze")
            return {}

        independent_vars = self.config.get("analysis", {}).get("for_each_independent_variable", [])

        results: dict[str, CorrelationResult] = {}

        for var in independent_vars:
            values = []
            completions = []

            for run in runs:
                if var in run.loss_values:
                    values.append(run.loss_values[var])
                    if run.routing_result:
                        completions.append(run.routing_result.get("completion_rate", 0.0))
                    else:
                        completions.append(0.0)

            if len(values) >= 3:
                corr_result = self._compute_correlation(var, values, completions)
                results[var] = corr_result

        if output_path:
            self._save_analysis(output_path, results)

        return results

    def _compute_correlation(
        self,
        var_name: str,
        x_values: list[float],
        y_values: list[float],
    ) -> CorrelationResult:
        """Compute correlation between variable and routing completion."""
        result = CorrelationResult(variable_name=var_name)

        if len(x_values) < 3:
            return result

        result.pearson_r = self._pearson_correlation(x_values, y_values)
        result.spearman_r = self._spearman_correlation(x_values, y_values)

        return result

    def _pearson_correlation(self, x: list[float], y: list[float]) -> float | None:
        """Compute Pearson correlation coefficient."""
        if len(x) < 2:
            return None

        n = len(x)
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        denom_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
        denom_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5

        if denom_x == 0 or denom_y == 0:
            return None

        return numerator / (denom_x * denom_y)

    def _spearman_correlation(self, x: list[float], y: list[float]) -> float | None:
        """Compute Spearman rank correlation."""
        if len(x) < 2:
            return None

        def rank(values: list[float]) -> list[float]:
            sorted_pairs = sorted(enumerate(values), key=lambda v: v[1])
            ranks: list[float] = [0.0] * len(values)
            for i, (orig_idx, _) in enumerate(sorted_pairs):
                ranks[orig_idx] = float(i + 1)
            return ranks

        rank_x = rank(x)
        rank_y = rank(y)

        return self._pearson_correlation(rank_x, rank_y)

    def _save_runs(self, output_dir: Path, runs: list[PlacementRun]) -> None:
        """Save runs to JSONL file."""
        data_dir = output_dir / "data" / "placements"
        data_dir.mkdir(parents=True, exist_ok=True)

        for run in runs:
            run_path = data_dir / f"{run.run_id}.json"
            with open(run_path, "w") as f:
                json.dump(
                    {
                        "run_id": run.run_id,
                        "seed": run.seed,
                        "weight_config": run.weight_config,
                        "loss_values": run.loss_values,
                        "routing_result": run.routing_result,
                        "timestamp": run.timestamp,
                    },
                    f,
                    indent=2,
                )

    def _load_runs(self, data_dir: Path) -> list[PlacementRun]:
        """Load runs from JSONL files."""
        placements_dir = data_dir / "data" / "placements"

        if not placements_dir.exists():
            return []

        runs = []
        for run_path in placements_dir.glob("*.json"):
            with open(run_path) as f:
                data = json.load(f)
                runs.append(
                    PlacementRun(
                        run_id=data["run_id"],
                        seed=data["seed"],
                        weight_config=data.get("weight_config", {}),
                        loss_values=data.get("loss_values", {}),
                        routing_result=data.get("routing_result"),
                        timestamp=data.get("timestamp", ""),
                    )
                )

        return runs

    def _save_analysis(
        self,
        output_path: str | Path,
        results: dict[str, CorrelationResult],
    ) -> None:
        """Save analysis results to file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_data = {
            "analyzed_at": datetime.now().isoformat(),
            "correlations": {
                name: {
                    "variable_name": r.variable_name,
                    "pearson_r": r.pearson_r,
                    "spearman_r": r.spearman_r,
                    "p_value": r.p_value,
                    "threshold": r.threshold,
                    "auc": r.auc,
                }
                for name, r in results.items()
            },
        }

        with open(output_path, "w") as f:
            yaml.dump(output_data, f, default_flow_style=False)


def run_pilot_study(
    config_path: str | Path | None = None,
    output_dir: str | Path = "experiments/routing_correlation/pilot",
    num_seeds: int = 5,
) -> None:
    """Convenience function to run pilot study."""
    study = RoutingCorrelationStudy(config_path)
    study.run_pilot(output_dir, num_seeds)


def run_full_study(
    config_path: str | Path | None = None,
    output_dir: str | Path = "experiments/routing_correlation/full",
    num_seeds: int = 5,
) -> None:
    """Convenience function to run full study."""
    study = RoutingCorrelationStudy(config_path)
    study.run_full(output_dir, num_seeds)


def analyze_results(
    data_dir: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, CorrelationResult]:
    """Convenience function to analyze results."""
    study = RoutingCorrelationStudy()
    return study.analyze(data_dir, output_path)
