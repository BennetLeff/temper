#!/usr/bin/env python3
"""
ANALYZE phase implementation for GPBM workflow.

Compares measured results against pre-registered predictions and hypotheses.
Produces statistical analysis with:
- Confidence intervals (bootstrap)
- Effect sizes
- Multiple comparison corrections
- Verdict on H0/H1

This phase sits after MEASURE for experimental work.

Usage:
    # As CLI
    python analyze.py --task temper-xxx  # Analyze measurements for task
    python analyze.py --compare baseline treatment  # Compare two conditions

    # As library
    from gpbm.analyze import AnalyzePhase
    analyzer = AnalyzePhase()
    result = analyzer.analyze_task("temper-xxx")
"""

import argparse
import json
import math
import os
import random

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from ..utils import CommandRunner
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "packages" / "temper-workflow" / "src"))
    from temper_workflow.utils import CommandRunner



@dataclass
class ConfidenceInterval:
    """A confidence interval for a statistic."""

    lower: float
    upper: float
    level: float = 0.95
    method: str = "bootstrap"

    def contains(self, value: float) -> bool:
        """Check if value is within CI."""
        return self.lower <= value <= self.upper

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "lower": self.lower,
            "upper": self.upper,
            "level": self.level,
            "method": self.method,
        }


@dataclass
class EffectSize:
    """Effect size calculation."""

    value: float
    interpretation: str  # "negligible", "small", "medium", "large"
    type: str = "cohens_d"  # or "percentage_change", "ratio"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "value": self.value,
            "interpretation": self.interpretation,
            "type": self.type,
        }


@dataclass
class StatisticalTest:
    """Result of a statistical test."""

    test_name: str
    statistic: float
    p_value: float
    significant: bool
    alpha: float = 0.05
    corrected_alpha: Optional[float] = None  # After multiple comparison correction

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "test_name": self.test_name,
            "statistic": self.statistic,
            "p_value": self.p_value,
            "significant": self.significant,
            "alpha": self.alpha,
            "corrected_alpha": self.corrected_alpha,
        }


@dataclass
class PredictionComparison:
    """Comparison of a prediction to observed result."""

    prediction: str
    expected: str
    observed: str
    match: str  # "yes", "no", "partial"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "prediction": self.prediction,
            "expected": self.expected,
            "observed": self.observed,
            "match": self.match,
            "notes": self.notes,
        }


@dataclass
class AnalysisResult:
    """Complete analysis result."""

    task_id: str
    timestamp: str

    # Summary statistics
    n_samples: int
    mean: float
    std: float
    confidence_interval: Optional[ConfidenceInterval] = None

    # Comparisons
    baseline_mean: Optional[float] = None
    baseline_std: Optional[float] = None
    effect_size: Optional[EffectSize] = None
    statistical_test: Optional[StatisticalTest] = None

    # Prediction comparisons
    prediction_comparisons: list[PredictionComparison] = field(default_factory=list)

    # Verdict
    verdict: str = "inconclusive"  # "accept_h0", "accept_h1", "inconclusive"
    verdict_rationale: str = ""

    # Threats to validity
    threats: list[str] = field(default_factory=list)

    # Recommendations
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "timestamp": self.timestamp,
            "summary_statistics": {
                "n": self.n_samples,
                "mean": self.mean,
                "std": self.std,
                "ci": self.confidence_interval.to_dict() if self.confidence_interval else None,
            },
            "comparison": {
                "baseline_mean": self.baseline_mean,
                "baseline_std": self.baseline_std,
                "effect_size": self.effect_size.to_dict() if self.effect_size else None,
                "test": self.statistical_test.to_dict() if self.statistical_test else None,
            },
            "predictions": [p.to_dict() for p in self.prediction_comparisons],
            "verdict": {
                "decision": self.verdict,
                "rationale": self.verdict_rationale,
            },
            "threats_to_validity": self.threats,
            "recommendations": self.recommendations,
        }

    def to_markdown(self) -> str:
        """Format as markdown report."""
        lines = [
            f"# Analysis Report: {self.task_id}",
            "",
            f"**Generated:** {self.timestamp}",
            "",
            "## Summary Statistics",
            "",
            f"- **N:** {self.n_samples}",
            f"- **Mean:** {self.mean:.4f}",
            f"- **Std Dev:** {self.std:.4f}",
        ]

        if self.confidence_interval:
            lines.append(
                f"- **95% CI:** [{self.confidence_interval.lower:.4f}, {self.confidence_interval.upper:.4f}]"
            )

        lines.append("")

        if self.baseline_mean is not None:
            lines.extend(
                [
                    "## Comparison to Baseline",
                    "",
                    f"- **Baseline Mean:** {self.baseline_mean:.4f}",
                    f"- **Baseline Std:** {self.baseline_std:.4f}" if self.baseline_std else "",
                ]
            )

            if self.effect_size:
                lines.append(
                    f"- **Effect Size:** {self.effect_size.value:.4f} ({self.effect_size.interpretation})"
                )

            if self.statistical_test:
                sig = "Yes" if self.statistical_test.significant else "No"
                lines.extend(
                    [
                        "",
                        f"### Statistical Test: {self.statistical_test.test_name}",
                        f"- **Statistic:** {self.statistical_test.statistic:.4f}",
                        f"- **p-value:** {self.statistical_test.p_value:.4f}",
                        f"- **Significant (α={self.statistical_test.alpha}):** {sig}",
                    ]
                )
                if self.statistical_test.corrected_alpha:
                    lines.append(f"- **Corrected α:** {self.statistical_test.corrected_alpha:.4f}")

            lines.append("")

        if self.prediction_comparisons:
            lines.extend(
                [
                    "## Prediction Comparisons",
                    "",
                    "| Prediction | Expected | Observed | Match |",
                    "|------------|----------|----------|-------|",
                ]
            )
            for p in self.prediction_comparisons:
                lines.append(f"| {p.prediction} | {p.expected} | {p.observed} | {p.match} |")
            lines.append("")

        lines.extend(
            [
                "## Verdict",
                "",
                f"**Decision:** {self.verdict.upper().replace('_', ' ')}",
                "",
                f"**Rationale:** {self.verdict_rationale}",
                "",
            ]
        )

        if self.threats:
            lines.extend(
                [
                    "## Threats to Validity",
                    "",
                ]
            )
            for t in self.threats:
                lines.append(f"- {t}")
            lines.append("")

        if self.recommendations:
            lines.extend(
                [
                    "## Recommendations",
                    "",
                ]
            )
            for r in self.recommendations:
                lines.append(f"- {r}")
            lines.append("")

        return "\n".join(lines)


class AnalyzePhase:
    """ANALYZE phase of GPBM workflow."""

    def __init__(self, repo_root: Optional[Path] = None):
        """Initialize analyze phase."""
        self.repo_root = repo_root or CommandRunner._find_project_root()
        self.measurements_file = self.repo_root / "metrics" / "measurements.jsonl"

    def bootstrap_ci(
        self,
        data: list[float],
        n_bootstrap: int = 1000,
        confidence: float = 0.95,
    ) -> ConfidenceInterval:
        """Calculate confidence interval using bootstrap method."""
        if not data:
            return ConfidenceInterval(lower=0.0, upper=0.0, level=confidence)

        n = len(data)
        bootstrap_means = []

        for _ in range(n_bootstrap):
            sample = [random.choice(data) for _ in range(n)]
            bootstrap_means.append(sum(sample) / n)

        bootstrap_means.sort()
        alpha = 1 - confidence
        lower_idx = int(n_bootstrap * alpha / 2)
        upper_idx = int(n_bootstrap * (1 - alpha / 2))

        return ConfidenceInterval(
            lower=bootstrap_means[lower_idx],
            upper=bootstrap_means[upper_idx],
            level=confidence,
            method="bootstrap",
        )

    def cohens_d(self, group1: list[float], group2: list[float]) -> EffectSize:
        """Calculate Cohen's d effect size."""
        n1, n2 = len(group1), len(group2)
        if n1 == 0 or n2 == 0:
            return EffectSize(value=0.0, interpretation="undefined", type="cohens_d")

        mean1 = sum(group1) / n1
        mean2 = sum(group2) / n2

        var1 = sum((x - mean1) ** 2 for x in group1) / max(n1 - 1, 1)
        var2 = sum((x - mean2) ** 2 for x in group2) / max(n2 - 1, 1)

        # Pooled standard deviation
        pooled_std = math.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / max(n1 + n2 - 2, 1))

        if pooled_std == 0:
            d = 0.0
        else:
            d = (mean1 - mean2) / pooled_std

        # Interpret effect size
        abs_d = abs(d)
        if abs_d < 0.2:
            interpretation = "negligible"
        elif abs_d < 0.5:
            interpretation = "small"
        elif abs_d < 0.8:
            interpretation = "medium"
        else:
            interpretation = "large"

        return EffectSize(value=d, interpretation=interpretation, type="cohens_d")

    def welch_t_test(
        self, group1: list[float], group2: list[float], alpha: float = 0.05
    ) -> StatisticalTest:
        """Perform Welch's t-test (unequal variances)."""
        n1, n2 = len(group1), len(group2)
        if n1 < 2 or n2 < 2:
            return StatisticalTest(
                test_name="welch_t",
                statistic=0.0,
                p_value=1.0,
                significant=False,
                alpha=alpha,
            )

        mean1 = sum(group1) / n1
        mean2 = sum(group2) / n2

        var1 = sum((x - mean1) ** 2 for x in group1) / (n1 - 1)
        var2 = sum((x - mean2) ** 2 for x in group2) / (n2 - 1)

        se = math.sqrt(var1 / n1 + var2 / n2)
        if se == 0:
            t_stat = 0.0
        else:
            t_stat = (mean1 - mean2) / se

        # Welch-Satterthwaite degrees of freedom
        num = (var1 / n1 + var2 / n2) ** 2
        denom = (var1 / n1) ** 2 / (n1 - 1) + (var2 / n2) ** 2 / (n2 - 1)
        df = num / denom if denom > 0 else 1

        # Approximate p-value using normal distribution for large df
        # For small df, this is an approximation
        p_value = 2 * (1 - self._normal_cdf(abs(t_stat)))

        return StatisticalTest(
            test_name="welch_t",
            statistic=t_stat,
            p_value=p_value,
            significant=p_value < alpha,
            alpha=alpha,
        )

    def _normal_cdf(self, x: float) -> float:
        """Approximate normal CDF using error function approximation."""
        # Approximation of the standard normal CDF
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def bonferroni_correction(
        self, p_values: list[float], alpha: float = 0.05
    ) -> list[tuple[float, bool, float]]:
        """Apply Bonferroni correction for multiple comparisons.

        Returns list of (p_value, significant, corrected_alpha) tuples.
        """
        m = len(p_values)
        corrected_alpha = alpha / m
        return [(p, p < corrected_alpha, corrected_alpha) for p in p_values]

    def holm_bonferroni_correction(
        self, p_values: list[float], alpha: float = 0.05
    ) -> list[tuple[float, bool, float]]:
        """Apply Holm-Bonferroni correction (step-down procedure).

        Returns list of (p_value, significant, adjusted_alpha) tuples.
        """
        m = len(p_values)
        indexed = [(p, i) for i, p in enumerate(p_values)]
        indexed.sort()

        results: list[tuple[float, bool, float]] = [(0.0, False, 0.0)] * m
        rejected = True  # Track if we should continue rejecting

        for rank, (p, orig_idx) in enumerate(indexed, 1):
            adjusted_alpha = alpha / (m - rank + 1)
            if rejected and p < adjusted_alpha:
                results[orig_idx] = (p, True, adjusted_alpha)
            else:
                rejected = False
                results[orig_idx] = (p, False, adjusted_alpha)

        return results

    def load_measurements(self, task_id: Optional[str] = None) -> list[dict]:
        """Load measurements from JSONL file."""
        if not self.measurements_file.exists():
            return []

        measurements = []
        with open(self.measurements_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(line)
                    if task_id is None or m.get("task") == task_id:
                        measurements.append(m)
                except json.JSONDecodeError:
                    continue

        return measurements

    def analyze_task(
        self,
        task_id: str,
        metric: Optional[str] = None,
        baseline_task: Optional[str] = None,
    ) -> AnalysisResult:
        """Analyze measurements for a task."""
        timestamp = datetime.now().isoformat()

        # Load measurements
        measurements = self.load_measurements(task_id)

        if metric:
            measurements = [m for m in measurements if m.get("metric") == metric]

        if not measurements:
            return AnalysisResult(
                task_id=task_id,
                timestamp=timestamp,
                n_samples=0,
                mean=0.0,
                std=0.0,
                verdict="inconclusive",
                verdict_rationale="No measurements found",
            )

        # Extract values
        values = [m["value"] for m in measurements if "value" in m]
        n = len(values)

        if n == 0:
            return AnalysisResult(
                task_id=task_id,
                timestamp=timestamp,
                n_samples=0,
                mean=0.0,
                std=0.0,
                verdict="inconclusive",
                verdict_rationale="No numeric values found",
            )

        # Calculate summary statistics
        mean_val = sum(values) / n
        variance = sum((x - mean_val) ** 2 for x in values) / max(n - 1, 1)
        std_val = math.sqrt(variance)

        # Calculate CI
        ci = self.bootstrap_ci(values) if n >= 3 else None

        result = AnalysisResult(
            task_id=task_id,
            timestamp=timestamp,
            n_samples=n,
            mean=mean_val,
            std=std_val,
            confidence_interval=ci,
        )

        # Compare to baseline if provided
        if baseline_task:
            baseline_measurements = self.load_measurements(baseline_task)
            if metric:
                baseline_measurements = [
                    m for m in baseline_measurements if m.get("metric") == metric
                ]

            baseline_values = [m["value"] for m in baseline_measurements if "value" in m]

            if baseline_values:
                result.baseline_mean = sum(baseline_values) / len(baseline_values)
                if len(baseline_values) > 1:
                    bl_var = sum((x - result.baseline_mean) ** 2 for x in baseline_values) / (
                        len(baseline_values) - 1
                    )
                    result.baseline_std = math.sqrt(bl_var)

                # Effect size
                result.effect_size = self.cohens_d(values, baseline_values)

                # Statistical test
                result.statistical_test = self.welch_t_test(values, baseline_values)

                # Determine verdict based on test
                if result.statistical_test.significant:
                    if mean_val > result.baseline_mean:
                        result.verdict = "accept_h1"
                        result.verdict_rationale = (
                            f"Significant improvement detected "
                            f"(p={result.statistical_test.p_value:.4f}, "
                            f"d={result.effect_size.value:.2f})"
                        )
                    else:
                        result.verdict = "accept_h1"
                        result.verdict_rationale = (
                            f"Significant change detected (decrease) "
                            f"(p={result.statistical_test.p_value:.4f}, "
                            f"d={result.effect_size.value:.2f})"
                        )
                else:
                    result.verdict = "accept_h0"
                    result.verdict_rationale = (
                        f"No significant difference detected "
                        f"(p={result.statistical_test.p_value:.4f})"
                    )

        # Add threats to validity
        if n < 10:
            result.threats.append(f"Small sample size (n={n}) may reduce statistical power")
        if std_val > mean_val * 0.5:
            result.threats.append("High variability (CV > 50%) suggests noisy measurements")

        # Add recommendations
        if n < 10:
            result.recommendations.append(
                "Increase sample size to at least 10 for more reliable results"
            )
        if result.verdict == "inconclusive":
            result.recommendations.append("Collect baseline measurements for comparison")

        return result

    def compare_conditions(
        self,
        condition_data: dict[str, list[float]],
        alpha: float = 0.05,
        correction: str = "holm",
    ) -> dict[str, Any]:
        """Compare multiple conditions with multiple comparison correction.

        Args:
            condition_data: Dict mapping condition names to lists of values
            alpha: Significance level
            correction: "bonferroni" or "holm"

        Returns:
            Dict with pairwise comparisons and corrected p-values
        """
        conditions = list(condition_data.keys())
        comparisons = []

        # Generate all pairwise comparisons
        for i, c1 in enumerate(conditions):
            for c2 in conditions[i + 1 :]:
                test = self.welch_t_test(condition_data[c1], condition_data[c2], alpha)
                effect = self.cohens_d(condition_data[c1], condition_data[c2])
                comparisons.append(
                    {
                        "condition1": c1,
                        "condition2": c2,
                        "p_value": test.p_value,
                        "t_statistic": test.statistic,
                        "effect_size": effect.value,
                        "effect_interpretation": effect.interpretation,
                    }
                )

        # Apply multiple comparison correction
        p_values = [c["p_value"] for c in comparisons]

        if correction == "bonferroni":
            corrections = self.bonferroni_correction(p_values, alpha)
        else:
            corrections = self.holm_bonferroni_correction(p_values, alpha)

        for i, (p, sig, adj_alpha) in enumerate(corrections):
            comparisons[i]["significant"] = sig
            comparisons[i]["corrected_alpha"] = adj_alpha

        return {
            "n_comparisons": len(comparisons),
            "correction_method": correction,
            "alpha": alpha,
            "comparisons": comparisons,
        }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="ANALYZE phase - Compare measurements to predictions"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Task analysis
    task_parser = subparsers.add_parser("task", help="Analyze task measurements")
    task_parser.add_argument("task_id", help="Task ID to analyze")
    task_parser.add_argument("--metric", help="Filter by metric name")
    task_parser.add_argument("--baseline", help="Baseline task ID for comparison")
    task_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Compare conditions
    compare_parser = subparsers.add_parser("compare", help="Compare multiple conditions")
    compare_parser.add_argument(
        "conditions",
        nargs="+",
        help="Condition data as name:val1,val2,val3",
    )
    compare_parser.add_argument("--alpha", type=float, default=0.05, help="Significance level")
    compare_parser.add_argument(
        "--correction",
        choices=["bonferroni", "holm"],
        default="holm",
        help="Multiple comparison correction",
    )
    compare_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Bootstrap CI
    ci_parser = subparsers.add_parser("ci", help="Calculate bootstrap CI")
    ci_parser.add_argument("values", nargs="+", type=float, help="Data values")
    ci_parser.add_argument("--confidence", type=float, default=0.95, help="Confidence level")
    ci_parser.add_argument("--n-bootstrap", type=int, default=1000, help="Bootstrap samples")

    args = parser.parse_args()

    analyzer = AnalyzePhase()

    if args.command == "task":
        result = analyzer.analyze_task(
            args.task_id,
            metric=args.metric,
            baseline_task=args.baseline,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(result.to_markdown())

    elif args.command == "compare":
        # Parse condition data
        condition_data = {}
        for cond in args.conditions:
            name, values_str = cond.split(":", 1)
            values = [float(v) for v in values_str.split(",")]
            condition_data[name] = values

        result = analyzer.compare_conditions(
            condition_data,
            alpha=args.alpha,
            correction=args.correction,
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n=== Multiple Comparison Results ===")
            print(f"Correction: {result['correction_method']}")
            print(f"α = {result['alpha']}")
            print()
            for comp in result["comparisons"]:
                sig = "*" if comp["significant"] else ""
                print(
                    f"  {comp['condition1']} vs {comp['condition2']}: "
                    f"p={comp['p_value']:.4f}{sig}, "
                    f"d={comp['effect_size']:.2f} ({comp['effect_interpretation']})"
                )

    elif args.command == "ci":
        ci = analyzer.bootstrap_ci(
            args.values,
            n_bootstrap=args.n_bootstrap,
            confidence=args.confidence,
        )
        mean_val = sum(args.values) / len(args.values)
        print(f"Mean: {mean_val:.4f}")
        print(f"{ci.level:.0%} CI: [{ci.lower:.4f}, {ci.upper:.4f}]")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
