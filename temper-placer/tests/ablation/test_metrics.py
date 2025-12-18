"""Tests for ablation study metrics aggregation."""

import pytest
import numpy as np
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock

from temper_placer.ablation.config import ExperimentConfig
from temper_placer.ablation.runner import ExperimentRun
from temper_placer.ablation.metrics import AggregatedMetrics, MetricAggregator


class TestAggregatedMetrics:
    """Tests for AggregatedMetrics dataclass."""

    def test_aggregated_metrics_creation(self):
        """Should create AggregatedMetrics with all fields."""
        now = datetime.now()

        metrics = AggregatedMetrics(
            experiment_name="baseline",
            test_case="test.kicad_pcb",
            n_seeds=5,
            final_loss_mean=1.5,
            final_loss_std=0.2,
            final_loss_ci95=(1.3, 1.7),
            best_loss_mean=1.2,
            best_loss_std=0.15,
            convergence_epoch_mean=150.0,
            convergence_epoch_std=20.0,
            converged_count=5,
            drc_pass_rate=1.0,
            drc_error_mean=0.0,
            drc_error_std=0.0,
            drc_warning_mean=0.5,
            wirelength_mean=100.0,
            wirelength_std=5.0,
            wirelength_ci95=(95.0, 105.0),
            loop_area_compliance_mean=0.95,
            loop_area_violation_mean=0.05,
            elapsed_time_mean=30.0,
            elapsed_time_std=2.0,
            seed_values={
                "final_loss": [1.4, 1.5, 1.6, 1.5, 1.4],
                "wirelength": [98, 100, 102, 100, 98],
            },
        )

        assert metrics.experiment_name == "baseline"
        assert metrics.n_seeds == 5
        assert metrics.final_loss_mean == 1.5
        assert metrics.drc_pass_rate == 1.0


class TestMetricAggregator:
    """Tests for MetricAggregator class."""

    @pytest.fixture
    def sample_runs(self):
        """Create sample ExperimentRun results."""
        runs = []
        for seed in [42, 123, 456, 789, 1024]:
            run = ExperimentRun(
                experiment_name="baseline",
                seed=seed,
                test_case="test.kicad_pcb",
                final_loss=1.0 + np.random.randn() * 0.1,
                best_loss=0.9 + np.random.randn() * 0.1,
                convergence_epoch=100 + int(np.random.randn() * 10),
                epochs_completed=200,
                quality_metrics={
                    "total_wirelength": 100.0 + np.random.randn() * 5,
                    "loop_area_compliance": 0.95 + np.random.randn() * 0.02,
                    "loop_area_violation": 0.05 + np.abs(np.random.randn() * 0.01),
                },
                drc_error_count=0,
                drc_warning_count=int(np.random.poisson(1)),
                elapsed_seconds=30.0 + np.random.randn() * 2,
                final_state=Mock(),
                checkpoint_path=None,
                timestamp=datetime.now(),
                config_hash="test",
            )
            runs.append(run)
        return runs

    def test_aggregator_creation(self):
        """Should create MetricAggregator."""
        aggregator = MetricAggregator()
        assert aggregator is not None

    def test_aggregate_basic(self, sample_runs):
        """Should aggregate runs by experiment and test case."""
        aggregator = MetricAggregator()
        results = aggregator.aggregate(sample_runs)

        assert len(results) == 1
        metrics = results[0]
        assert metrics.experiment_name == "baseline"
        assert metrics.test_case == "test.kicad_pcb"
        assert metrics.n_seeds == 5

    def test_aggregate_multiple_experiments(self):
        """Should aggregate multiple experiments separately."""
        runs = []
        for exp_name in ["exp1", "exp2"]:
            for seed in [42, 123]:
                run = ExperimentRun(
                    experiment_name=exp_name,
                    seed=seed,
                    test_case="test.kicad_pcb",
                    final_loss=1.0,
                    best_loss=0.9,
                    convergence_epoch=100,
                    epochs_completed=200,
                    quality_metrics={},
                    drc_error_count=0,
                    drc_warning_count=0,
                    elapsed_seconds=30.0,
                    final_state=Mock(),
                    checkpoint_path=None,
                    timestamp=datetime.now(),
                    config_hash="test",
                )
                runs.append(run)

        aggregator = MetricAggregator()
        results = aggregator.aggregate(runs)

        assert len(results) == 2
        assert set(r.experiment_name for r in results) == {"exp1", "exp2"}

    def test_aggregate_multiple_test_cases(self):
        """Should aggregate multiple test cases separately."""
        runs = []
        for test_case in ["test1.kicad_pcb", "test2.kicad_pcb"]:
            for seed in [42, 123]:
                run = ExperimentRun(
                    experiment_name="exp1",
                    seed=seed,
                    test_case=test_case,
                    final_loss=1.0,
                    best_loss=0.9,
                    convergence_epoch=100,
                    epochs_completed=200,
                    quality_metrics={},
                    drc_error_count=0,
                    drc_warning_count=0,
                    elapsed_seconds=30.0,
                    final_state=Mock(),
                    checkpoint_path=None,
                    timestamp=datetime.now(),
                    config_hash="test",
                )
                runs.append(run)

        aggregator = MetricAggregator()
        results = aggregator.aggregate(runs)

        assert len(results) == 2
        assert set(r.test_case for r in results) == {"test1.kicad_pcb", "test2.kicad_pcb"}

    def test_compute_mean_std(self, sample_runs):
        """Should correctly compute mean and standard deviation."""
        aggregator = MetricAggregator()
        results = aggregator.aggregate(sample_runs)
        metrics = results[0]

        # Compare computed mean to numpy
        expected_mean = np.mean([r.final_loss for r in sample_runs])
        assert abs(metrics.final_loss_mean - expected_mean) < 1e-6

        # Compare computed std
        expected_std = np.std([r.final_loss for r in sample_runs], ddof=1)
        assert abs(metrics.final_loss_std - expected_std) < 1e-6

    def test_confidence_interval_computation(self, sample_runs):
        """Should compute 95% CI using t-distribution."""
        aggregator = MetricAggregator()
        results = aggregator.aggregate(sample_runs)
        metrics = results[0]

        # CI should be (mean - margin, mean + margin)
        assert len(metrics.final_loss_ci95) == 2
        assert metrics.final_loss_ci95[0] < metrics.final_loss_mean
        assert metrics.final_loss_mean < metrics.final_loss_ci95[1]

    def test_confidence_interval_uses_t_distribution(self):
        """Should use t-distribution for small samples (not z)."""
        from scipy import stats

        # Create small sample
        runs = []
        values = [1.0, 1.1, 1.2]  # n=3
        for i, val in enumerate(values):
            run = ExperimentRun(
                experiment_name="test",
                seed=i,
                test_case="test.kicad_pcb",
                final_loss=val,
                best_loss=val - 0.1,
                convergence_epoch=100,
                epochs_completed=200,
                quality_metrics={},
                drc_error_count=0,
                drc_warning_count=0,
                elapsed_seconds=30.0,
                final_state=Mock(),
                checkpoint_path=None,
                timestamp=datetime.now(),
                config_hash="test",
            )
            runs.append(run)

        aggregator = MetricAggregator()
        results = aggregator.aggregate(runs)
        metrics = results[0]

        # Manually compute CI using t-distribution
        mean = np.mean(values)
        std = np.std(values, ddof=1)
        sem = std / np.sqrt(len(values))
        df = len(values) - 1
        t_crit = stats.t.ppf(0.975, df)
        expected_ci = (mean - t_crit * sem, mean + t_crit * sem)

        assert abs(metrics.final_loss_ci95[0] - expected_ci[0]) < 1e-6
        assert abs(metrics.final_loss_ci95[1] - expected_ci[1]) < 1e-6

    def test_single_seed_aggregation(self):
        """Should handle n=1 seed gracefully."""
        run = ExperimentRun(
            experiment_name="test",
            seed=42,
            test_case="test.kicad_pcb",
            final_loss=1.0,
            best_loss=0.9,
            convergence_epoch=100,
            epochs_completed=200,
            quality_metrics={},
            drc_error_count=0,
            drc_warning_count=0,
            elapsed_seconds=30.0,
            final_state=Mock(),
            checkpoint_path=None,
            timestamp=datetime.now(),
            config_hash="test",
        )

        aggregator = MetricAggregator()
        results = aggregator.aggregate([run])
        metrics = results[0]

        assert metrics.n_seeds == 1
        assert metrics.final_loss_mean == 1.0
        # Std should be 0 or nan for single value
        assert metrics.final_loss_std == 0.0 or np.isnan(metrics.final_loss_std)

    def test_zero_variance_metrics(self):
        """Should handle metrics with zero variance."""
        runs = []
        for seed in [42, 123, 456]:
            run = ExperimentRun(
                experiment_name="test",
                seed=seed,
                test_case="test.kicad_pcb",
                final_loss=1.0,  # All same
                best_loss=0.9,
                convergence_epoch=100,
                epochs_completed=200,
                quality_metrics={"total_wirelength": 100.0},  # All same
                drc_error_count=0,  # All same
                drc_warning_count=0,
                elapsed_seconds=30.0,
                final_state=Mock(),
                checkpoint_path=None,
                timestamp=datetime.now(),
                config_hash="test",
            )
            runs.append(run)

        aggregator = MetricAggregator()
        results = aggregator.aggregate(runs)
        metrics = results[0]

        assert metrics.final_loss_std == 0.0
        assert metrics.drc_error_std == 0.0

    def test_drc_pass_rate_computation(self):
        """Should compute DRC pass rate correctly."""
        runs = []
        # 3 passing, 2 failing
        for i, error_count in enumerate([0, 0, 0, 1, 2]):
            run = ExperimentRun(
                experiment_name="test",
                seed=i,
                test_case="test.kicad_pcb",
                final_loss=1.0,
                best_loss=0.9,
                convergence_epoch=100,
                epochs_completed=200,
                quality_metrics={},
                drc_error_count=error_count,
                drc_warning_count=0,
                elapsed_seconds=30.0,
                final_state=Mock(),
                checkpoint_path=None,
                timestamp=datetime.now(),
                config_hash="test",
            )
            runs.append(run)

        aggregator = MetricAggregator()
        results = aggregator.aggregate(runs)
        metrics = results[0]

        # 3/5 = 0.6 pass rate
        assert metrics.drc_pass_rate == 0.6

    def test_converged_count_tracking(self):
        """Should track number of converged seeds."""
        runs = []
        for i, conv_epoch in enumerate([100, 150, None, 120, None]):
            run = ExperimentRun(
                experiment_name="test",
                seed=i,
                test_case="test.kicad_pcb",
                final_loss=1.0,
                best_loss=0.9,
                convergence_epoch=conv_epoch,
                epochs_completed=200,
                quality_metrics={},
                drc_error_count=0,
                drc_warning_count=0,
                elapsed_seconds=30.0,
                final_state=Mock(),
                checkpoint_path=None,
                timestamp=datetime.now(),
                config_hash="test",
            )
            runs.append(run)

        aggregator = MetricAggregator()
        results = aggregator.aggregate(runs)
        metrics = results[0]

        # 3 converged (non-None convergence_epoch)
        assert metrics.converged_count == 3

    def test_quality_metrics_extraction(self, sample_runs):
        """Should extract and aggregate quality metrics."""
        aggregator = MetricAggregator()
        results = aggregator.aggregate(sample_runs)
        metrics = results[0]

        # Should have wirelength metrics
        assert metrics.wirelength_mean > 0
        assert metrics.wirelength_std >= 0

        # Should have loop area metrics
        assert 0 <= metrics.loop_area_compliance_mean <= 1
        assert 0 <= metrics.loop_area_violation_mean

    def test_seed_values_stored(self, sample_runs):
        """Should store raw seed values for detailed analysis."""
        aggregator = MetricAggregator()
        results = aggregator.aggregate(sample_runs)
        metrics = results[0]

        assert "final_loss" in metrics.seed_values
        assert "best_loss" in metrics.seed_values
        assert len(metrics.seed_values["final_loss"]) == 5

    def test_drc_warning_aggregation(self):
        """Should aggregate DRC warning counts."""
        runs = []
        for i, warnings in enumerate([0, 1, 2, 1, 0]):
            run = ExperimentRun(
                experiment_name="test",
                seed=i,
                test_case="test.kicad_pcb",
                final_loss=1.0,
                best_loss=0.9,
                convergence_epoch=100,
                epochs_completed=200,
                quality_metrics={},
                drc_error_count=0,
                drc_warning_count=warnings,
                elapsed_seconds=30.0,
                final_state=Mock(),
                checkpoint_path=None,
                timestamp=datetime.now(),
                config_hash="test",
            )
            runs.append(run)

        aggregator = MetricAggregator()
        results = aggregator.aggregate(runs)
        metrics = results[0]

        # Mean should be (0+1+2+1+0)/5 = 0.8
        assert metrics.drc_warning_mean == 0.8

    def test_empty_runs_list(self):
        """Should handle empty runs list."""
        aggregator = MetricAggregator()
        results = aggregator.aggregate([])

        assert len(results) == 0

    def test_timing_aggregation(self):
        """Should aggregate elapsed time metrics."""
        runs = []
        times = [25.0, 30.0, 28.0, 32.0, 29.0]
        for i, elapsed in enumerate(times):
            run = ExperimentRun(
                experiment_name="test",
                seed=i,
                test_case="test.kicad_pcb",
                final_loss=1.0,
                best_loss=0.9,
                convergence_epoch=100,
                epochs_completed=200,
                quality_metrics={},
                drc_error_count=0,
                drc_warning_count=0,
                elapsed_seconds=elapsed,
                final_state=Mock(),
                checkpoint_path=None,
                timestamp=datetime.now(),
                config_hash="test",
            )
            runs.append(run)

        aggregator = MetricAggregator()
        results = aggregator.aggregate(runs)
        metrics = results[0]

        assert abs(metrics.elapsed_time_mean - np.mean(times)) < 1e-6
        assert abs(metrics.elapsed_time_std - np.std(times, ddof=1)) < 1e-6

    def test_missing_quality_metrics_handled(self):
        """Should handle runs with missing quality metrics gracefully."""
        runs = []
        for i in range(3):
            # Some runs have metrics, some don't
            quality = {"total_wirelength": 100.0} if i > 0 else {}
            run = ExperimentRun(
                experiment_name="test",
                seed=i,
                test_case="test.kicad_pcb",
                final_loss=1.0,
                best_loss=0.9,
                convergence_epoch=100,
                epochs_completed=200,
                quality_metrics=quality,
                drc_error_count=0,
                drc_warning_count=0,
                elapsed_seconds=30.0,
                final_state=Mock(),
                checkpoint_path=None,
                timestamp=datetime.now(),
                config_hash="test",
            )
            runs.append(run)

        aggregator = MetricAggregator()
        results = aggregator.aggregate(runs)
        metrics = results[0]

        # Should still compute without error
        assert metrics.wirelength_mean >= 0
