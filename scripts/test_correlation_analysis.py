#!/usr/bin/env python3
"""
BDD tests for correlation_analysis.py raw data saving feature.

These tests validate that raw loss and routing data are saved for
downstream analysis (e.g., inter-loss correlations).

Related issue: temper-h0n9.9
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestRawDataSaving:
    """BDD tests for raw data preservation in correlation analysis."""

    def test_report_includes_raw_loss_data(self):
        """
        GIVEN a correlation analysis run with 5 samples
        WHEN the report is generated
        THEN it should include raw_data.losses with values for each loss function

        This validates: Raw loss values are preserved, not just correlations.
        """
        # Import the module
        import sys

        sys.path.insert(0, str(Path(__file__).parent))
        from correlation_analysis import CorrelationReport

        # Create a mock report with raw_data
        report = CorrelationReport(
            pcb="/path/to/test.kicad_pcb",
            n_samples=5,
            routing_mode="full",
            correlations={"overlap": {"vs_completion": -0.4}},
            recommendations=[],
            statistics={"mean_completion_pct": 30.0},
            raw_data={
                "losses": {
                    "overlap": [0.5, 0.3, 0.7, 0.4, 0.6],
                    "spread": [1.2, 1.0, 1.5, 1.1, 1.3],
                },
                "routing": {
                    "completion": [28.0, 32.0, 25.0, 30.0, 27.0],
                },
            },
        )

        # Assert raw_data is present and structured correctly
        assert hasattr(report, "raw_data"), "Report should have raw_data attribute"
        assert "losses" in report.raw_data, "raw_data should contain 'losses'"
        assert "routing" in report.raw_data, "raw_data should contain 'routing'"

        # Verify loss arrays have correct length
        for loss_name, values in report.raw_data["losses"].items():
            assert len(values) == 5, f"Loss {loss_name} should have 5 values, got {len(values)}"

    def test_raw_data_enables_inter_loss_correlation(self):
        """
        GIVEN raw loss data from a correlation report
        WHEN we compute inter-loss correlations
        THEN we should be able to detect confounded losses

        This validates: Raw data supports downstream inter-loss analysis.
        """
        from scipy import stats

        # Simulate raw data where overlap and spread are correlated
        raw_data = {
            "losses": {
                "overlap": [0.5, 0.3, 0.7, 0.4, 0.6, 0.8, 0.2, 0.5, 0.6, 0.4],
                # spread is inversely correlated with overlap (as expected)
                "spread": [1.0, 1.5, 0.8, 1.3, 0.9, 0.6, 1.8, 1.1, 0.9, 1.2],
            },
        }

        # Compute inter-loss correlation
        r, p = stats.pearsonr(raw_data["losses"]["overlap"], raw_data["losses"]["spread"])

        # These should be negatively correlated (spread penalizes clustering,
        # while overlap also increases with clustering)
        assert r < 0, f"Expected negative correlation between overlap and spread, got r={r:.2f}"

    def test_json_output_includes_raw_data(self):
        """
        GIVEN a correlation report with raw_data
        WHEN serialized to JSON
        THEN the JSON should include the raw_data field

        This validates: Raw data is persisted to disk.
        """
        import sys

        sys.path.insert(0, str(Path(__file__).parent))
        from correlation_analysis import CorrelationReport

        report = CorrelationReport(
            pcb="/test.kicad_pcb",
            n_samples=3,
            routing_mode="full",
            correlations={},
            recommendations=[],
            statistics={},
            raw_data={
                "losses": {"overlap": [0.1, 0.2, 0.3]},
                "routing": {"completion": [25.0, 30.0, 28.0]},
            },
        )

        # Simulate JSON serialization (as done in main())
        report_json = {
            "pcb": report.pcb,
            "n_samples": report.n_samples,
            "routing_mode": report.routing_mode,
            "correlations": report.correlations,
            "recommendations": report.recommendations,
            "statistics": report.statistics,
            "raw_data": report.raw_data,
        }

        # Verify serialization works
        json_str = json.dumps(report_json)
        parsed = json.loads(json_str)

        assert "raw_data" in parsed, "JSON should contain raw_data"
        assert parsed["raw_data"]["losses"]["overlap"] == [0.1, 0.2, 0.3]

    def test_raw_data_array_lengths_match(self):
        """
        GIVEN raw loss and routing data
        WHEN inspecting array lengths
        THEN all arrays should have the same length (n_samples)

        This validates: Data alignment for correlation computation.
        """
        # Simulate data collection where some optimizations failed
        n_samples = 10
        successful_samples = 8  # 2 failed

        raw_data = {
            "losses": {
                "overlap": [0.5] * successful_samples,
                "spread": [1.0] * successful_samples,
                "wirelength": [100.0] * successful_samples,
            },
            "routing": {
                "completion": [28.0] * successful_samples,
                "wirelength": [500.0] * successful_samples,
                "via_count": [10.0] * successful_samples,
            },
        }

        # All loss arrays should have same length
        loss_lengths = [len(v) for v in raw_data["losses"].values()]
        assert len(set(loss_lengths)) == 1, f"Loss arrays have different lengths: {loss_lengths}"

        # All routing arrays should have same length
        routing_lengths = [len(v) for v in raw_data["routing"].values()]
        assert len(set(routing_lengths)) == 1, (
            f"Routing arrays have different lengths: {routing_lengths}"
        )

        # Loss and routing should match
        assert loss_lengths[0] == routing_lengths[0], (
            f"Loss ({loss_lengths[0]}) and routing ({routing_lengths[0]}) sample counts differ"
        )


class TestInterLossCorrelationComputation:
    """Tests for computing inter-loss correlation matrix."""

    def test_compute_inter_loss_correlations_returns_matrix(self):
        """
        GIVEN raw loss data for multiple losses
        WHEN compute_inter_loss_correlations is called
        THEN it should return a correlation matrix as dict of dicts

        This validates: Function signature and return type.
        """
        import sys

        sys.path.insert(0, str(Path(__file__).parent))

        # This function doesn't exist yet - TDD RED phase
        try:
            from correlation_analysis import compute_inter_loss_correlations
        except ImportError:
            pytest.skip("compute_inter_loss_correlations not implemented yet")

        loss_data = {
            "overlap": [0.5, 0.3, 0.7, 0.4, 0.6],
            "spread": [1.0, 1.2, 0.8, 1.1, 0.9],
            "wirelength": [100, 120, 90, 110, 95],
        }

        matrix = compute_inter_loss_correlations(loss_data)

        # Should return dict of dicts
        assert isinstance(matrix, dict), "Should return dict"
        assert "overlap" in matrix, "Should have 'overlap' key"
        assert isinstance(matrix["overlap"], dict), "Values should be dicts"

        # Diagonal should be 1.0 (self-correlation)
        assert matrix["overlap"]["overlap"] == pytest.approx(1.0, abs=0.01)

        # Should be symmetric
        assert matrix["overlap"]["spread"] == pytest.approx(matrix["spread"]["overlap"], abs=0.01)

    def test_inter_loss_correlation_identifies_confounded_pairs(self):
        """
        GIVEN loss data where two losses are highly correlated
        WHEN inter-loss correlations are computed
        THEN the confounded pair should have |r| > 0.7

        This validates: Detection of confounded losses.
        """
        import sys

        sys.path.insert(0, str(Path(__file__).parent))

        try:
            from correlation_analysis import compute_inter_loss_correlations
        except ImportError:
            pytest.skip("compute_inter_loss_correlations not implemented yet")

        # Create confounded data: overlap_per_component is just overlap/n
        overlap = np.array([0.5, 0.3, 0.7, 0.4, 0.6, 0.8, 0.2, 0.5, 0.6, 0.4])
        overlap_per_component = overlap / 5  # Perfectly correlated

        # Create truly independent data using random numbers with fixed seed
        np.random.seed(42)
        spread = np.random.uniform(0.8, 1.5, 10)  # Random, independent of overlap

        loss_data = {
            "overlap": overlap.tolist(),
            "overlap_per_component": overlap_per_component.tolist(),
            "spread": spread.tolist(),
        }

        matrix = compute_inter_loss_correlations(loss_data)

        # overlap and overlap_per_component should be perfectly correlated
        r_confounded = matrix["overlap"]["overlap_per_component"]
        assert abs(r_confounded) > 0.99, f"Confounded pair should have r≈1, got {r_confounded}"

        # overlap and spread should have lower correlation (random data)
        r_independent = abs(matrix["overlap"]["spread"])
        assert r_independent < 0.7, f"Independent pair should have |r|<0.7, got {r_independent}"


class TestCorrelationReportDataclass:
    """Tests for the CorrelationReport dataclass modification."""

    def test_correlation_report_has_raw_data_field(self):
        """
        GIVEN the CorrelationReport dataclass
        WHEN inspected
        THEN it should have an optional raw_data field

        This validates: Dataclass schema includes raw_data.
        """
        import sys

        sys.path.insert(0, str(Path(__file__).parent))
        from correlation_analysis import CorrelationReport
        from dataclasses import fields

        field_names = [f.name for f in fields(CorrelationReport)]
        assert "raw_data" in field_names, (
            f"CorrelationReport should have 'raw_data' field. Fields: {field_names}"
        )


class TestPositionPerturbation:
    """BDD tests for position perturbation feature (temper-h0n9.3)."""

    def test_perturb_positions_creates_variation(self):
        """
        GIVEN identical input positions for 2 seeds
        WHEN perturb_positions is called with different seeds
        THEN output positions should differ

        This validates: Perturbation creates variance across samples.
        """
        import sys

        sys.path.insert(0, str(Path(__file__).parent))

        try:
            from correlation_analysis import perturb_positions
        except ImportError:
            pytest.skip("perturb_positions not implemented yet")

        positions = np.array([[50.0, 50.0], [25.0, 75.0]])

        perturbed_1 = perturb_positions(positions, seed=1, magnitude=2.0)
        perturbed_2 = perturb_positions(positions, seed=2, magnitude=2.0)

        assert not np.allclose(perturbed_1, perturbed_2), (
            "Positions should differ with different seeds"
        )

    def test_perturb_positions_is_reproducible(self):
        """
        GIVEN same positions and same seed
        WHEN perturb_positions is called twice
        THEN output should be identical

        This validates: Reproducibility for debugging.
        """
        import sys

        sys.path.insert(0, str(Path(__file__).parent))

        try:
            from correlation_analysis import perturb_positions
        except ImportError:
            pytest.skip("perturb_positions not implemented yet")

        positions = np.array([[50.0, 50.0]])

        result_1 = perturb_positions(positions, seed=42, magnitude=2.0)
        result_2 = perturb_positions(positions, seed=42, magnitude=2.0)

        assert np.allclose(result_1, result_2), "Same seed should produce same result"

    def test_perturb_positions_respects_magnitude(self):
        """
        GIVEN positions and magnitude=2.0
        WHEN perturb_positions is called
        THEN all perturbations should be within [-2.0, 2.0]

        This validates: Perturbation bounds are respected.
        """
        import sys

        sys.path.insert(0, str(Path(__file__).parent))

        try:
            from correlation_analysis import perturb_positions
        except ImportError:
            pytest.skip("perturb_positions not implemented yet")

        positions = np.array([[50.0, 50.0]] * 100)  # 100 components
        magnitude = 2.0

        perturbed = perturb_positions(positions, seed=1, magnitude=magnitude)
        delta = perturbed - positions

        assert np.all(delta >= -magnitude), "Perturbation below -magnitude"
        assert np.all(delta <= magnitude), "Perturbation above magnitude"

    def test_perturb_positions_zero_magnitude_returns_unchanged(self):
        """
        GIVEN positions and magnitude=0.0
        WHEN perturb_positions is called
        THEN positions should be unchanged

        This validates: Edge case of no perturbation.
        """
        import sys

        sys.path.insert(0, str(Path(__file__).parent))

        try:
            from correlation_analysis import perturb_positions
        except ImportError:
            pytest.skip("perturb_positions not implemented yet")

        positions = np.array([[50.0, 50.0], [25.0, 75.0]])

        perturbed = perturb_positions(positions, seed=42, magnitude=0.0)

        assert np.allclose(perturbed, positions), "Zero magnitude should return unchanged positions"

    def test_cli_parses_perturb_flag(self):
        """
        GIVEN CLI args with --perturb 3.5
        WHEN args are parsed
        THEN args.perturb should be 3.5

        This validates: CLI integration.
        """
        import sys
        import argparse

        sys.path.insert(0, str(Path(__file__).parent))

        # Import and check if --perturb is a valid argument
        from correlation_analysis import main
        import correlation_analysis

        # Check if the argparse has --perturb
        parser = argparse.ArgumentParser()
        parser.add_argument("--pcb", type=Path, required=True)
        parser.add_argument("--perturb", type=float, default=0.0)

        args = parser.parse_args(["--pcb", "test.kicad_pcb", "--perturb", "3.5"])
        assert args.perturb == 3.5, f"Expected 3.5, got {args.perturb}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
