"""Metrics aggregation for ablation study experiments."""

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from scipy import stats

from temper_placer.ablation.runner import ExperimentRun


@dataclass
class AggregatedMetrics:
    """Metrics aggregated across seeds for one experiment + test case."""

    # Identifiers
    experiment_name: str
    """Name of the experiment configuration"""

    test_case: str
    """Name of the test case"""

    n_seeds: int
    """Number of seeds aggregated"""

    # Loss metrics
    final_loss_mean: float
    """Mean final loss across seeds"""

    final_loss_std: float
    """Standard deviation of final loss"""

    final_loss_ci95: tuple[float, float]
    """95% confidence interval for final loss"""

    best_loss_mean: float
    """Mean best loss achieved"""

    best_loss_std: float
    """Standard deviation of best loss"""

    # Convergence metrics
    convergence_epoch_mean: float
    """Mean epoch at convergence"""

    convergence_epoch_std: float
    """Standard deviation of convergence epoch"""

    converged_count: int
    """Number of seeds that converged"""

    # DRC metrics
    drc_pass_rate: float
    """Fraction of seeds with zero DRC errors (0.0 to 1.0)"""

    drc_error_mean: float
    """Mean DRC error count"""

    drc_error_std: float
    """Standard deviation of DRC errors"""

    drc_warning_mean: float
    """Mean DRC warning count"""

    # Quality metrics
    wirelength_mean: float
    """Mean total wirelength"""

    wirelength_std: float
    """Standard deviation of wirelength"""

    wirelength_ci95: tuple[float, float]
    """95% confidence interval for wirelength"""

    loop_area_compliance_mean: float
    """Mean fraction meeting loop area constraints (0.0 to 1.0)"""

    loop_area_violation_mean: float
    """Mean loop area violation amount"""

    # Timing metrics
    elapsed_time_mean: float
    """Mean elapsed time in seconds"""

    elapsed_time_std: float
    """Standard deviation of elapsed time"""

    # Raw seed values for detailed analysis
    seed_values: dict[str, list[float]] = field(default_factory=dict)
    """Dictionary of metric names to lists of seed values"""


class MetricAggregator:
    """Aggregates experiment results across seeds with statistical analysis."""

    def aggregate(
        self,
        runs: list[ExperimentRun],
        _group_by: tuple[str, str] = ("experiment_name", "test_case"),
    ) -> list[AggregatedMetrics]:
        """Aggregate runs by experiment and test case.

        Args:
            runs: List of ExperimentRun results
            group_by: Tuple of field names to group by

        Returns:
            List of AggregatedMetrics, one per group
        """
        # Group runs by experiment and test case
        grouped = defaultdict(list)
        for run in runs:
            key = (run.experiment_name, run.test_case)
            grouped[key].append(run)

        # Compute aggregated metrics for each group
        results = []
        for (exp_name, test_case), group_runs in grouped.items():
            metrics = self._compute_aggregated_metrics(
                exp_name, test_case, group_runs
            )
            results.append(metrics)

        return results

    def _compute_aggregated_metrics(
        self,
        exp_name: str,
        test_case: str,
        runs: list[ExperimentRun],
    ) -> AggregatedMetrics:
        """Compute statistics across seeds.

        Args:
            exp_name: Experiment name
            test_case: Test case name
            runs: List of ExperimentRun results for this configuration

        Returns:
            AggregatedMetrics with all computed statistics
        """
        # Extract loss values
        final_losses = np.array([r.final_loss for r in runs])
        best_losses = np.array([r.best_loss for r in runs])

        # Extract convergence epochs (handle None values)
        convergence_epochs = np.array(
            [r.convergence_epoch or r.epochs_completed for r in runs]
        )
        converged_count = sum(1 for r in runs if r.convergence_epoch is not None)

        # Extract DRC metrics
        drc_errors = np.array([r.drc_error_count for r in runs])
        drc_warnings = np.array([r.drc_warning_count for r in runs])
        drc_passes = np.array(
            [1.0 if r.drc_error_count == 0 else 0.0 for r in runs]
        )

        # Extract timing
        elapsed_times = np.array([r.elapsed_seconds for r in runs])

        # Extract quality metrics
        wirelengths = np.array(
            [r.quality_metrics.get("total_wirelength", 0.0) for r in runs]
        )
        loop_compliance = np.array(
            [r.quality_metrics.get("loop_area_compliance", 0.0) for r in runs]
        )
        loop_violations = np.array(
            [r.quality_metrics.get("loop_area_violation", 0.0) for r in runs]
        )

        # Compute confidence intervals
        final_loss_ci = self._confidence_interval(final_losses)
        wirelength_ci = self._confidence_interval(wirelengths)

        # Store raw seed values
        seed_values = {
            "final_loss": final_losses.tolist(),
            "best_loss": best_losses.tolist(),
            "convergence_epoch": convergence_epochs.tolist(),
            "drc_error": drc_errors.tolist(),
            "drc_warning": drc_warnings.tolist(),
            "elapsed_time": elapsed_times.tolist(),
            "wirelength": wirelengths.tolist(),
        }

        return AggregatedMetrics(
            experiment_name=exp_name,
            test_case=test_case,
            n_seeds=len(runs),
            final_loss_mean=float(np.mean(final_losses)),
            final_loss_std=float(np.std(final_losses, ddof=1) if len(runs) > 1 else 0.0),
            final_loss_ci95=final_loss_ci,
            best_loss_mean=float(np.mean(best_losses)),
            best_loss_std=float(np.std(best_losses, ddof=1) if len(runs) > 1 else 0.0),
            convergence_epoch_mean=float(np.mean(convergence_epochs)),
            convergence_epoch_std=float(
                np.std(convergence_epochs, ddof=1) if len(runs) > 1 else 0.0
            ),
            converged_count=converged_count,
            drc_pass_rate=float(np.mean(drc_passes)),
            drc_error_mean=float(np.mean(drc_errors)),
            drc_error_std=float(np.std(drc_errors, ddof=1) if len(runs) > 1 else 0.0),
            drc_warning_mean=float(np.mean(drc_warnings)),
            wirelength_mean=float(np.mean(wirelengths)),
            wirelength_std=float(np.std(wirelengths, ddof=1) if len(runs) > 1 else 0.0),
            wirelength_ci95=wirelength_ci,
            loop_area_compliance_mean=float(np.mean(loop_compliance)),
            loop_area_violation_mean=float(np.mean(loop_violations)),
            elapsed_time_mean=float(np.mean(elapsed_times)),
            elapsed_time_std=float(np.std(elapsed_times, ddof=1) if len(runs) > 1 else 0.0),
            seed_values=seed_values,
        )

    def _confidence_interval(
        self, values: np.ndarray, confidence: float = 0.95
    ) -> tuple[float, float]:
        """Compute confidence interval using t-distribution.

        For small samples (n < 30), uses t-distribution instead of z.
        This is more accurate for sample statistics.

        Args:
            values: Array of values
            confidence: Confidence level (default 0.95 for 95% CI)

        Returns:
            Tuple of (lower_bound, upper_bound)
        """
        values = np.asarray(values)
        n = len(values)

        if n == 0:
            return (0.0, 0.0)

        if n == 1:
            # Cannot compute CI for single value
            return (float(values[0]), float(values[0]))

        mean = np.mean(values)
        std_err = np.std(values, ddof=1) / np.sqrt(n)

        # Use t-distribution
        alpha = 1 - confidence
        df = n - 1
        t_crit = stats.t.ppf(1 - alpha / 2, df)

        margin = t_crit * std_err
        return (float(mean - margin), float(mean + margin))
