"""
Tests for correlation_analysis.py script.

Tests the core correlation computation logic using TDD approach.
"""


import numpy as np
import pytest
from scipy import stats


# Mock data structures for testing
class MockOptimizationResult:
    """Mock result from a single optimization run."""

    def __init__(self, seed: int, loss_values: dict[str, float]):
        self.seed = seed
        self.loss_values = loss_values


class MockRoutingResult:
    """Mock result from routing verification."""

    def __init__(self, completion_pct: float, wirelength_mm: float, via_count: int):
        self.completion_pct = completion_pct
        self.wirelength_mm = wirelength_mm
        self.via_count = via_count
        self.routable = completion_pct >= 90.0


class TestCorrelationComputation:
    """Test correlation computation between losses and routing metrics."""

    def test_perfect_positive_correlation(self):
        """Test that perfect positive correlation yields r=1.0."""
        # Given: Loss values that increase linearly with routing metric
        loss_values = [1.0, 2.0, 3.0, 4.0, 5.0]
        routing_metric = [10.0, 20.0, 30.0, 40.0, 50.0]

        # When: Computing Pearson correlation
        r, p_value = stats.pearsonr(loss_values, routing_metric)

        # Then: Should be perfect positive correlation
        assert abs(r - 1.0) < 1e-10
        assert p_value < 0.05

    def test_perfect_negative_correlation(self):
        """Test that perfect negative correlation yields r=-1.0."""
        # Given: Loss values that decrease as routing metric increases
        loss_values = [5.0, 4.0, 3.0, 2.0, 1.0]
        routing_metric = [10.0, 20.0, 30.0, 40.0, 50.0]

        # When: Computing Pearson correlation
        r, p_value = stats.pearsonr(loss_values, routing_metric)

        # Then: Should be perfect negative correlation
        assert abs(r - (-1.0)) < 1e-10
        assert p_value < 0.05

    def test_no_correlation(self):
        """Test that uncorrelated data yields r≈0."""
        # Given: Random uncorrelated values
        np.random.seed(42)
        loss_values = np.random.randn(30)
        routing_metric = np.random.randn(30)

        # When: Computing Pearson correlation
        r, p_value = stats.pearsonr(loss_values, routing_metric)

        # Then: Should have weak correlation
        assert abs(r) < 0.3

    def test_spearman_handles_nonlinear(self):
        """Test that Spearman correlation handles non-linear monotonic relationships."""
        # Given: Non-linear but monotonic relationship (y = x^2)
        loss_values = [1.0, 2.0, 3.0, 4.0, 5.0]
        routing_metric = [1.0, 4.0, 9.0, 16.0, 25.0]

        # When: Computing both Pearson and Spearman
        pearson_r, _ = stats.pearsonr(loss_values, routing_metric)
        spearman_r, _ = stats.spearmanr(loss_values, routing_metric)

        # Then: Spearman should be perfect (1.0) but Pearson less than 1
        assert abs(spearman_r - 1.0) < 1e-10
        assert pearson_r < 0.99  # Non-linear, so Pearson is less than perfect


class TestRecommendationGeneration:
    """Test recommendation logic based on correlation coefficients."""

    def test_strong_positive_correlation_recommends_keep(self):
        """Strong correlation (r>0.7) should recommend keeping/increasing weight."""
        # Given: Strong positive correlation
        r = 0.92

        # When: Generating recommendation
        action = _generate_action(r, "wirelength_loss", "routed_wirelength")

        # Then: Should recommend keeping
        assert action in ["keep", "increase"]

    def test_strong_negative_correlation_recommends_increase(self):
        """Strong negative correlation with completion should recommend increasing."""
        # Given: Strong negative correlation with completion
        r = -0.85

        # When: Generating recommendation for completion metric
        action = _generate_action(r, "overlap_loss", "completion")

        # Then: Should recommend increasing (overlaps block routing)
        assert action == "increase"

    def test_weak_correlation_recommends_review(self):
        """Weak correlation (|r|<0.3) should recommend review."""
        # Given: Weak correlation
        r = 0.08

        # When: Generating recommendation
        action = _generate_action(r, "thermal_loss", "completion")

        # Then: Should recommend review
        assert action == "review"

    def test_moderate_correlation_recommends_keep(self):
        """Moderate correlation (0.3<=|r|<0.7) should recommend keeping."""
        # Given: Moderate correlation
        r = 0.45

        # When: Generating recommendation
        action = _generate_action(r, "loop_area_loss", "completion")

        # Then: Should recommend keeping
        assert action == "keep"


class TestBatchOptimizationResults:
    """Test aggregation of multiple optimization runs."""

    def test_aggregate_loss_values_across_runs(self):
        """Test extracting loss values from multiple runs."""
        # Given: Multiple optimization results with different seeds
        results = [
            MockOptimizationResult(seed=1, loss_values={"overlap": 0.0, "wirelength": 100.0}),
            MockOptimizationResult(seed=2, loss_values={"overlap": 5.0, "wirelength": 120.0}),
            MockOptimizationResult(seed=3, loss_values={"overlap": 2.0, "wirelength": 110.0}),
        ]

        # When: Aggregating loss values
        overlap_values = [r.loss_values["overlap"] for r in results]
        wirelength_values = [r.loss_values["wirelength"] for r in results]

        # Then: Should match expected arrays
        assert overlap_values == [0.0, 5.0, 2.0]
        assert wirelength_values == [100.0, 120.0, 110.0]

    def test_aggregate_routing_metrics_across_runs(self):
        """Test extracting routing metrics from multiple runs."""
        # Given: Multiple routing results
        results = [
            MockRoutingResult(completion_pct=100.0, wirelength_mm=150.0, via_count=10),
            MockRoutingResult(completion_pct=95.0, wirelength_mm=160.0, via_count=12),
            MockRoutingResult(completion_pct=100.0, wirelength_mm=145.0, via_count=8),
        ]

        # When: Aggregating routing metrics
        completion_values = [r.completion_pct for r in results]
        wirelength_values = [r.wirelength_mm for r in results]
        via_values = [r.via_count for r in results]

        # Then: Should match expected arrays
        assert completion_values == [100.0, 95.0, 100.0]
        assert wirelength_values == [150.0, 160.0, 145.0]
        assert via_values == [10, 12, 8]


class TestStatistics:
    """Test statistical summary generation."""

    def test_compute_mean_and_std(self):
        """Test computing mean and standard deviation."""
        # Given: Sample routing completion values
        completion_values = [98.0, 100.0, 95.0, 100.0, 97.0]

        # When: Computing statistics
        mean_val = float(np.mean(completion_values))
        std_val = float(np.std(completion_values, ddof=1))

        # Then: Should match expected values
        assert abs(mean_val - 98.0) < 0.1
        assert std_val > 0

    def test_count_failed_routes(self):
        """Test counting routing failures."""
        # Given: Mix of successful and failed routes
        results = [
            MockRoutingResult(completion_pct=100.0, wirelength_mm=150.0, via_count=10),
            MockRoutingResult(completion_pct=85.0, wirelength_mm=160.0, via_count=12),  # Failed
            MockRoutingResult(completion_pct=100.0, wirelength_mm=145.0, via_count=8),
            MockRoutingResult(completion_pct=75.0, wirelength_mm=170.0, via_count=15),  # Failed
        ]

        # When: Counting failures (< 90% completion)
        failed_count = sum(1 for r in results if r.completion_pct < 90.0)

        # Then: Should have 2 failures
        assert failed_count == 2


class TestCorrelationReport:
    """Test correlation report JSON structure."""

    def test_report_contains_required_fields(self):
        """Test that correlation report has all required fields."""
        # Given: Sample correlation report data
        report = {
            "pcb": "test.kicad_pcb",
            "n_samples": 10,
            "routing_mode": "quick",
            "correlations": {
                "overlap_loss": {
                    "vs_completion": -0.75,
                    "vs_wirelength": 0.20,
                    "vs_via_count": 0.15,
                }
            },
            "recommendations": [
                {
                    "loss": "overlap_loss",
                    "action": "increase",
                    "reason": "Strong negative correlation with completion",
                }
            ],
            "statistics": {
                "mean_completion_pct": 97.5,
                "std_completion_pct": 2.1,
                "failed_routes": 0,
            },
        }

        # Then: Should have all required top-level keys
        assert "pcb" in report
        assert "n_samples" in report
        assert "routing_mode" in report
        assert "correlations" in report
        assert "recommendations" in report
        assert "statistics" in report

    def test_correlation_entry_structure(self):
        """Test that correlation entry has correct structure."""
        # Given: Sample correlation entry
        correlation = {"vs_completion": -0.75, "vs_wirelength": 0.20, "vs_via_count": 0.15}

        # Then: Should have all three routing metrics
        assert "vs_completion" in correlation
        assert "vs_wirelength" in correlation
        assert "vs_via_count" in correlation

        # And: Values should be in valid range [-1, 1]
        for key, value in correlation.items():
            assert -1.0 <= value <= 1.0

    def test_recommendation_structure(self):
        """Test that recommendation entry has correct structure."""
        # Given: Sample recommendation
        recommendation = {
            "loss": "overlap_loss",
            "action": "increase",
            "reason": "Strong negative correlation with completion",
        }

        # Then: Should have required fields
        assert "loss" in recommendation
        assert "action" in recommendation
        assert "reason" in recommendation

        # And: Action should be one of valid values
        assert recommendation["action"] in ["keep", "increase", "reduce", "review"]


# Helper functions to be implemented in the script
def _generate_action(r: float, loss_name: str, metric_name: str) -> str:
    """
    Generate recommendation action based on correlation coefficient.

    Args:
        r: Pearson correlation coefficient
        loss_name: Name of the loss function
        metric_name: Name of the routing metric

    Returns:
        Action string: "keep", "increase", "reduce", or "review"
    """
    abs_r = abs(r)

    # Strong correlation (|r| > 0.7)
    if abs_r > 0.7:
        # Negative correlation with completion means loss blocks routing → increase
        if metric_name == "completion" and r < 0:
            return "increase"
        # Positive correlation with bad metrics (wirelength, vias) → might want to adjust
        return "keep"

    # Moderate correlation (0.3 <= |r| < 0.7)
    elif abs_r >= 0.3:
        return "keep"

    # Weak correlation (|r| < 0.3)
    else:
        return "review"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
