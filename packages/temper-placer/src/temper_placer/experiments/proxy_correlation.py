"""
Proxy-to-Actual Correlation Tracker.

Tracks how well our optimization proxies predict real-world outcomes.
This is essential for understanding whether we're optimizing the right things.

Defined correlations in MEASUREMENT_SPEC.yaml:
- loop_inductance: gate_loop_area vs measured_inductance_nh
- thermal: thermal_junction_estimate vs measured_junction_temp_c
- routing_success: wirelength_hpwl vs routing_completion
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CorrelationSample:
    """A single data point for proxy-actual correlation."""

    run_id: str
    timestamp: str
    proxy_value: float
    actual_value: float
    seed: int | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "proxy_value": self.proxy_value,
            "actual_value": self.actual_value,
            "seed": self.seed,
            "notes": self.notes,
        }


@dataclass
class CorrelationResult:
    """Result of correlation analysis between proxy and actual values."""

    proxy_name: str
    actual_name: str
    expected_correlation: float
    sample_count: int
    pearson_r: float | None = None
    spearman_r: float | None = None
    mean_proxy: float = 0.0
    mean_actual: float = 0.0
    std_proxy: float = 0.0
    std_actual: float = 0.0
    is_tracking: bool = False
    correlation_acceptable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "proxy_name": self.proxy_name,
            "actual_name": self.actual_name,
            "expected_correlation": self.expected_correlation,
            "sample_count": self.sample_count,
            "pearson_r": self.pearson_r,
            "spearman_r": self.spearman_r,
            "mean_proxy": self.mean_proxy,
            "mean_actual": self.mean_actual,
            "std_proxy": self.std_proxy,
            "std_actual": self.std_actual,
            "is_tracking": self.is_tracking,
            "correlation_acceptable": self.correlation_acceptable,
        }


class CorrelationTracker:
    """
    Tracks correlation between optimization proxies and actual outcomes.

    Usage:
        tracker = CorrelationTracker("experiments/correlation")

        # After each run with actual measurements:
        tracker.add_sample(
            proxy_name="gate_loop_area",
            actual_name="measured_inductance_nh",
            run_id="exp1_seed42",
            proxy_value=95.0,
            actual_value=12.5,
        )

        # Periodically analyze:
        results = tracker.analyze_all()
    """

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.samples: list[CorrelationSample] = []
        self.correlations: dict[str, list[CorrelationSample]] = {}

        self._load_existing()

    def _load_existing(self) -> None:
        samples_file = self.output_dir / "correlation_samples.jsonl"
        if samples_file.exists():
            with open(samples_file) as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        sample = CorrelationSample(**data)
                        self.samples.append(sample)
                        key = f"{data['proxy_name']}_vs_{data['actual_name']}"
                        if key not in self.correlations:
                            self.correlations[key] = []
                        self.correlations[key].append(sample)

    def add_sample(
        self,
        proxy_name: str,
        actual_name: str,
        run_id: str,
        proxy_value: float,
        actual_value: float,
        seed: int | None = None,
        notes: str = "",
    ) -> None:
        """
        Add a correlation sample.

        Args:
            proxy_name: Name of the proxy metric (e.g., "gate_loop_area")
            actual_name: Name of the actual measurement (e.g., "measured_inductance_nh")
            run_id: Unique identifier for this run
            proxy_value: Value of the proxy during optimization
            actual_value: Measured actual value after fabrication/testing
            seed: Random seed used (for debugging)
            notes: Additional notes about this sample
        """
        sample = CorrelationSample(
            run_id=run_id,
            timestamp=datetime.now().isoformat(),
            proxy_value=proxy_value,
            actual_value=actual_value,
            seed=seed,
            notes=notes,
        )

        self.samples.append(sample)

        key = f"{proxy_name}_vs_{actual_name}"
        if key not in self.correlations:
            self.correlations[key] = []
        self.correlations[key].append(sample)

        self._save_sample(sample)

    def _save_sample(self, sample: CorrelationSample) -> None:
        samples_file = self.output_dir / "correlation_samples.jsonl"
        with open(samples_file, "a") as f:
            f.write(json.dumps(sample.to_dict()) + "\n")

    def analyze_correlation(
        self,
        proxy_name: str,
        actual_name: str,
        expected_correlation: float = 0.5,
    ) -> CorrelationResult:
        """
        Analyze correlation between a proxy and actual values.

        Args:
            proxy_name: Name of the proxy metric
            actual_name: Name of the actual measurement
            expected_correlation: Minimum acceptable correlation (default 0.5)

        Returns:
            CorrelationResult with analysis
        """
        key = f"{proxy_name}_vs_{actual_name}"
        samples = self.correlations.get(key, [])

        if len(samples) < 3:
            return CorrelationResult(
                proxy_name=proxy_name,
                actual_name=actual_name,
                expected_correlation=expected_correlation,
                sample_count=len(samples),
                is_tracking=len(samples) > 0,
                correlation_acceptable=False,
            )

        proxy_values = [s.proxy_value for s in samples]
        actual_values = [s.actual_value for s in samples]

        mean_proxy = statistics.mean(proxy_values)
        mean_actual = statistics.mean(actual_values)
        std_proxy = statistics.stdev(proxy_values) if len(proxy_values) > 1 else 0.0
        std_actual = statistics.stdev(actual_values) if len(actual_values) > 1 else 0.0

        pearson_r = self._pearson_correlation(proxy_values, actual_values)
        spearman_r = self._spearman_correlation(proxy_values, actual_values)

        correlation_acceptable = (pearson_r is not None and pearson_r >= expected_correlation) or (
            spearman_r is not None and spearman_r >= expected_correlation
        )

        return CorrelationResult(
            proxy_name=proxy_name,
            actual_name=actual_name,
            expected_correlation=expected_correlation,
            sample_count=len(samples),
            pearson_r=pearson_r,
            spearman_r=spearman_r,
            mean_proxy=mean_proxy,
            mean_actual=mean_actual,
            std_proxy=std_proxy,
            std_actual=std_actual,
            is_tracking=True,
            correlation_acceptable=correlation_acceptable,
        )

    def analyze_all(self) -> dict[str, CorrelationResult]:
        """
        Analyze all tracked correlations.

        Returns:
            Dictionary mapping correlation keys to CorrelationResult
        """
        results: dict[str, CorrelationResult] = {}

        for key, samples in self.correlations.items():
            proxy_name, actual_name = key.split("_vs_")
            result = self.analyze_correlation(proxy_name, actual_name)
            results[key] = result

        return results

    def _pearson_correlation(self, x: list[float], y: list[float]) -> float | None:
        """Compute Pearson correlation coefficient."""
        if len(x) < 2 or len(y) < 2:
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

    def get_summary_report(self) -> dict[str, Any]:
        """Generate a summary report of all correlations."""
        results = self.analyze_all()

        summary: dict[str, Any] = {
            "generated_at": datetime.now().isoformat(),
            "total_samples": len(self.samples),
            "correlations": {},
            "alerts": [],
        }

        for key, result in results.items():
            summary["correlations"][key] = result.to_dict()

            if result.is_tracking and not result.correlation_acceptable:
                summary["alerts"].append(
                    {
                        "type": "correlation_degraded",
                        "proxy": result.proxy_name,
                        "actual": result.actual_name,
                        "current_r": result.pearson_r or result.spearman_r,
                        "expected": result.expected_correlation,
                        "message": (
                            f"Correlation between {result.proxy_name} and {result.actual_name} "
                            f"is {result.pearson_r:.3f} (expected ≥{result.expected_correlation})"
                        ),
                    }
                )

        return summary

    def save_summary_report(self, path: Path | None = None) -> Path:
        """Save summary report to file."""
        if path is None:
            path = self.output_dir / "correlation_summary.yaml"

        summary = self.get_summary_report()

        with open(path, "w") as f:
            yaml.dump(summary, f, default_flow_style=False)

        return path


def track_proxy_actual(
    tracker: CorrelationTracker | None,
    proxy_name: str,
    actual_name: str,
    run_id: str,
    proxy_value: float,
    actual_value: float,
    seed: int | None = None,
) -> None:
    """
    Convenience function to add a proxy-actual sample.

    Args:
        tracker: CorrelationTracker or None (if tracking disabled)
        proxy_name: Name of the proxy metric
        actual_name: Name of the actual measurement
        run_id: Unique identifier for this run
        proxy_value: Value of the proxy during optimization
        actual_value: Measured actual value
        seed: Random seed used
    """
    if tracker is None:
        return

    tracker.add_sample(
        proxy_name=proxy_name,
        actual_name=actual_name,
        run_id=run_id,
        proxy_value=proxy_value,
        actual_value=actual_value,
        seed=seed,
    )
