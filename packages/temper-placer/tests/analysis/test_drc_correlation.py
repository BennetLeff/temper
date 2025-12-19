"""Tests for DRC correlation analysis."""

import json
import tempfile
from pathlib import Path
from typing import List, Dict, Any
import sys

# Add src to path so we can import temper_placer modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest

from temper_placer.analysis.drc_correlation import (
    analyze_drc_correlation,
    CorrelationReport,
    PlacementResult,
    DRCResult,
)


class TestPlacementResult:
    """Test PlacementResult dataclass."""

    def test_placement_result_creation(self):
        """Should create PlacementResult with all required fields."""
        result = PlacementResult(
            quality_level="good",
            overlap_loss=0.1,
            boundary_loss=0.05,
            wirelength_loss=25.0,
            total_loss=35.0,
        )
        assert result.quality_level == "good"
        assert result.overlap_loss == 0.1
        assert result.boundary_loss == 0.05
        assert result.wirelength_loss == 25.0
        assert result.total_loss == 35.0


class TestDRCResult:
    """Test DRCResult dataclass."""

    def test_drc_result_creation(self):
        """Should create DRCResult with violation counts."""
        result = DRCResult(
            courtyards_overlap=2,
            edge_clearance=1,
            pad_clearance=3,
            total_errors=6,
        )
        assert result.courtyards_overlap == 2
        assert result.edge_clearance == 1
        assert result.pad_clearance == 3
        assert result.total_errors == 6


class TestCorrelationReport:
    """Test CorrelationReport dataclass."""

    def test_correlation_report_creation(self):
        """Should create CorrelationReport with correlation data."""
        correlations = [
            {
                "loss_component": "overlap_loss",
                "pearson_r": 0.89,
                "spearman_rho": 0.92,
                "p_value": 0.001,
                "drc_type": "courtyards_overlap",
            }
        ]
        report = CorrelationReport(
            correlations=correlations,
            recommendations={
                "clearance": 150,
                "overlap": 100,
                "boundary": 75,
                "wirelength": 10,
            },
        )
        assert len(report.correlations) == 1
        assert report.correlations[0]["loss_component"] == "overlap_loss"
        assert report.recommendations["clearance"] == 150


class TestAnalyzeDRCCorrelation:
    """Test the main analyze_drc_correlation function."""

    def test_analyze_with_empty_data(self):
        """Should handle empty data gracefully."""
        placements: List[PlacementResult] = []
        drc_results: List[DRCResult] = []

        report = analyze_drc_correlation(placements, drc_results)

        assert isinstance(report, CorrelationReport)
        assert len(report.correlations) == 0
        assert "overlap" in report.recommendations
        assert "boundary" in report.recommendations
        assert "wirelength" in report.recommendations

    def test_analyze_with_single_data_point(self):
        """Should handle single data point."""
        placements = [
            PlacementResult(
                quality_level="good",
                overlap_loss=0.1,
                boundary_loss=0.05,
                wirelength_loss=25.0,
                total_loss=35.0,
            )
        ]
        drc_results = [
            DRCResult(
                courtyards_overlap=1,
                edge_clearance=0,
                pad_clearance=2,
                total_errors=3,
            )
        ]

        report = analyze_drc_correlation(placements, drc_results)

        # With single data point, correlation should be undefined (NaN)
        assert len(report.correlations) >= 3  # overlap, boundary, wirelength
        for corr in report.correlations:
            assert "loss_component" in corr
            assert "pearson_r" in corr
            assert "spearman_rho" in corr
            assert "p_value" in corr

    def test_analyze_with_multiple_data_points(self):
        """Should compute correlations with multiple data points."""
        placements = [
            PlacementResult(
                quality_level="perfect",
                overlap_loss=0.0,
                boundary_loss=0.0,
                wirelength_loss=20.0,
                total_loss=20.0,
            ),
            PlacementResult(
                quality_level="good",
                overlap_loss=0.1,
                boundary_loss=0.05,
                wirelength_loss=25.0,
                total_loss=35.0,
            ),
            PlacementResult(
                quality_level="bad",
                overlap_loss=0.5,
                boundary_loss=0.2,
                wirelength_loss=35.0,
                total_loss=55.0,
            ),
        ]
        drc_results = [
            DRCResult(courtyards_overlap=0, edge_clearance=0, pad_clearance=0, total_errors=0),
            DRCResult(courtyards_overlap=1, edge_clearance=0, pad_clearance=1, total_errors=2),
            DRCResult(courtyards_overlap=3, edge_clearance=1, pad_clearance=2, total_errors=6),
        ]

        report = analyze_drc_correlation(placements, drc_results)

        # Should have correlations for all loss components
        assert len(report.correlations) >= 3

        # Find overlap correlation
        overlap_corr = next(
            (c for c in report.correlations if c["loss_component"] == "overlap_loss"), None
        )
        assert overlap_corr is not None
        assert 0 <= overlap_corr["pearson_r"] <= 1  # Should be positive correlation
        assert overlap_corr["p_value"] >= 0
        assert overlap_corr["drc_type"] == "courtyards_overlap"

        # Find boundary correlation
        boundary_corr = next(
            (c for c in report.correlations if c["loss_component"] == "boundary_loss"), None
        )
        assert boundary_corr is not None
        assert boundary_corr["drc_type"] == "edge_clearance"

        # Find wirelength correlation (should be weak)
        wirelength_corr = next(
            (c for c in report.correlations if c["loss_component"] == "wirelength_loss"), None
        )
        assert wirelength_corr is not None
        # Wirelength should have weak or no correlation with DRC errors

    def test_recommendations_generation(self):
        """Should generate reasonable weight recommendations."""
        placements = [
            PlacementResult(
                quality_level="good",
                overlap_loss=0.1,
                boundary_loss=0.05,
                wirelength_loss=25.0,
                total_loss=35.0,
            ),
            PlacementResult(
                quality_level="bad",
                overlap_loss=0.5,
                boundary_loss=0.2,
                wirelength_loss=35.0,
                total_loss=55.0,
            ),
        ]
        drc_results = [
            DRCResult(courtyards_overlap=1, edge_clearance=0, pad_clearance=1, total_errors=2),
            DRCResult(courtyards_overlap=3, edge_clearance=1, pad_clearance=2, total_errors=6),
        ]

        report = analyze_drc_correlation(placements, drc_results)

        # Should have recommendations for all loss types
        assert "overlap" in report.recommendations
        assert "boundary" in report.recommendations
        assert "wirelength" in report.recommendations

        # Recommendations should be positive numbers
        for weight in report.recommendations.values():
            assert isinstance(weight, (int, float))
            assert weight > 0

        # Higher correlation should generally lead to higher weight
        overlap_corr = next(
            c["pearson_r"] for c in report.correlations if c["loss_component"] == "overlap_loss"
        )
        wirelength_corr = next(
            c["pearson_r"] for c in report.correlations if c["loss_component"] == "wirelength_loss"
        )

        if overlap_corr > wirelength_corr:
            assert report.recommendations["overlap"] >= report.recommendations["wirelength"]

    def test_output_format(self):
        """Should produce properly formatted output."""
        placements = [
            PlacementResult(
                quality_level="good",
                overlap_loss=0.1,
                boundary_loss=0.05,
                wirelength_loss=25.0,
                total_loss=35.0,
            )
        ]
        drc_results = [
            DRCResult(
                courtyards_overlap=1,
                edge_clearance=0,
                pad_clearance=1,
                total_errors=2,
            )
        ]

        report = analyze_drc_correlation(placements, drc_results)

        # Should be JSON serializable
        output = {
            "correlations": report.correlations,
            "recommendations": report.recommendations,
        }
        json_str = json.dumps(output)
        assert len(json_str) > 0

        # Should be able to parse back
        parsed = json.loads(json_str)
        assert "correlations" in parsed
        assert "recommendations" in parsed
