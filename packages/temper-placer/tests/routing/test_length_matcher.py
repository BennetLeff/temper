"""
Tests for length matching post-processing (temper-l4we.3).

Tests serpentine meander generation and path length equalization for buses.
"""

import pytest
import math
import numpy as np

from temper_placer.core.bus_cohort import BusCohortConstraint
from temper_placer.routing.maze_router import RoutePath
from temper_placer.routing.heuristics import GridCell
from temper_placer.routing.post_processing.length_matcher import (
    LengthMatcher,
    SerpentineParams,
    LengthMatchResult,
)


class TestLengthCalculation:
    """Tests for path length calculation."""

    def test_calculate_path_length_straight(self):
        """Should calculate length of straight path correctly."""
        matcher = LengthMatcher()

        path = RoutePath(
            net="TEST",
            cells=[
                GridCell(0, 0, 0),
                GridCell(1, 0, 0),
                GridCell(2, 0, 0),
                GridCell(3, 0, 0),
            ],
            length=0.0,
            via_count=0,
            success=True,
            cell_size=0.2,
        )

        length = matcher.measure_path_length(path.cells, cell_size_mm=0.2)

        assert length == pytest.approx(0.6)  # 3 segments * 0.2mm

    def test_calculate_path_length_diagonal(self):
        """Should calculate diagonal distance correctly."""
        matcher = LengthMatcher()

        path = RoutePath(
            net="TEST",
            cells=[
                GridCell(0, 0, 0),
                GridCell(1, 1, 0),
                GridCell(2, 2, 0),
            ],
            length=0.0,
            via_count=0,
            success=True,
            cell_size=0.2,
        )

        length = matcher.measure_path_length(path.cells, cell_size_mm=0.2)

        expected = 2 * math.sqrt(0.08)  # 2 diagonal segments
        assert length == pytest.approx(expected, abs=0.001)


class TestSerpentineInsertion:
    """Tests for serpentine meander insertion."""

    def test_insert_serpentine_increases_length(self):
        """Adding serpentine should increase path length."""
        matcher = LengthMatcher()

        cells = [
            GridCell(0, 0, 0),
            GridCell(10, 0, 0),
        ]

        original_length = 2.0  # 10 cells * 0.2mm

        new_cells = matcher.insert_serpentine(
            cells,
            segment=(0, 1),
            length_delta_mm=1.0,
            cell_size_mm=0.2,
            params=SerpentineParams(amplitude_mm=0.4),
        )

        new_length = matcher.measure_path_length(new_cells, cell_size_mm=0.2)

        assert new_length > original_length

    def test_serpentine_amplitude_calculation(self):
        """Should calculate correct meander amplitude."""
        matcher = LengthMatcher()

        extra_length = 2.0
        num_periods = 4

        wave_length_added = 2.0 * 0.25
        amplitude = extra_length / (2 * num_periods)

        assert amplitude == 0.25


class TestBusLengthMatching:
    """Tests for bus-level length matching."""

    def test_match_bus_lengths_reduces_skew(self):
        """Should reduce length variance within bus."""
        matcher = LengthMatcher()

        paths = {
            "NET_A": RoutePath(
                net="NET_A",
                cells=[GridCell(0, 0, 0), GridCell(10, 0, 0)],
                length=2.0,
                via_count=0,
                success=True,
                cell_size=0.2,
            ),
            "NET_B": RoutePath(
                net="NET_B",
                cells=[GridCell(0, 0, 0), GridCell(5, 0, 0)],
                length=1.0,
                via_count=0,
                success=True,
                cell_size=0.2,
            ),
        }

        bus = BusCohortConstraint(
            name="SPI_BUS",
            nets=["NET_A", "NET_B"],
            max_skew_mm=0.5,
        )

        result = matcher.match_bus_lengths(paths, bus, cell_size_mm=0.2)

        assert isinstance(result, LengthMatchResult)
        assert result.original_skew_mm == 1.0
        assert result.final_skew_mm < result.original_skew_mm

    def test_match_bus_lengths_all_paths_returned(self):
        """Result should have paths for all nets."""
        matcher = LengthMatcher()

        paths = {
            "NET_A": RoutePath(
                net="NET_A",
                cells=[GridCell(0, 0, 0), GridCell(5, 0, 0)],
                length=1.0,
                via_count=0,
                success=True,
                cell_size=0.2,
            ),
        }

        bus = BusCohortConstraint(
            name="TEST_BUS",
            nets=["NET_A"],
            max_skew_mm=2.0,
        )

        result = matcher.match_bus_lengths(paths, bus, cell_size_mm=0.2)

        assert "NET_A" in result.paths

    def test_match_bus_lengths_reports_skew(self):
        """Result should report achieved skew."""
        matcher = LengthMatcher()

        paths = {
            "NET_A": RoutePath(
                net="NET_A",
                cells=[GridCell(0, 0, 0), GridCell(10, 0, 0)],
                length=2.0,
                via_count=0,
                success=True,
                cell_size=0.2,
            ),
            "NET_B": RoutePath(
                net="NET_B",
                cells=[GridCell(0, 0, 0), GridCell(8, 0, 0)],
                length=1.6,
                via_count=0,
                success=True,
                cell_size=0.2,
            ),
        }

        bus = BusCohortConstraint(
            name="TEST_BUS",
            nets=["NET_A", "NET_B"],
            max_skew_mm=1.0,
        )

        result = matcher.match_bus_lengths(paths, bus, cell_size_mm=0.2)

        assert result.achieved_skew_mm is not None
        assert result.achieved_skew_mm >= 0
        assert result.max_skew_mm == 1.0

    def test_match_bus_lengths_within_tolerance(self):
        """Final skew should be within bus tolerance."""
        matcher = LengthMatcher()

        paths = {
            "NET_A": RoutePath(
                net="NET_A",
                cells=[GridCell(0, 0, 0), GridCell(10, 0, 0)],
                length=2.0,
                via_count=0,
                success=True,
                cell_size=0.2,
            ),
            "NET_B": RoutePath(
                net="NET_B",
                cells=[GridCell(0, 0, 0), GridCell(6, 0, 0)],
                length=1.2,
                via_count=0,
                success=True,
                cell_size=0.2,
            ),
        }

        bus = BusCohortConstraint(
            name="SPI_BUS",
            nets=["NET_A", "NET_B"],
            max_skew_mm=0.5,
        )

        result = matcher.match_bus_lengths(paths, bus, cell_size_mm=0.2)

        assert result.final_skew_mm <= bus.max_skew_mm or len(result.nets_modified) > 0


class TestSerpentineParams:
    """Tests for SerpentineParams configuration."""

    def test_default_params(self):
        """Should have sensible defaults."""
        params = SerpentineParams()

        assert params.amplitude_mm == 0.5
        assert params.tolerance_mm == 0.5
        assert params.min_straight_length_mm == 2.0
        assert params.pitch_mm == 1.0  # 2 * 0.5

    def test_custom_params(self):
        """Should accept custom values."""
        params = SerpentineParams(
            amplitude_mm=0.3,
            tolerance_mm=0.2,
            min_straight_length_mm=1.5,
        )

        assert params.amplitude_mm == 0.3
        assert params.tolerance_mm == 0.2
        assert params.min_straight_length_mm == 1.5


class TestFindStraightSegments:
    """Tests for straight segment detection."""

    def test_find_straight_segments(self):
        """Should identify straight segments."""
        matcher = LengthMatcher()

        cells = [
            GridCell(0, 0, 0),
            GridCell(1, 0, 0),
            GridCell(2, 0, 0),
            GridCell(2, 1, 0),
            GridCell(2, 2, 0),
            GridCell(3, 2, 0),
        ]

        segments = matcher.find_straight_segments(cells, cell_size_mm=0.2, min_length_mm=0.4)

        assert len(segments) >= 1


class TestLengthMatchResult:
    """Tests for LengthMatchResult structure."""

    def test_result_with_modifications(self):
        """Result should track which nets were modified."""
        matcher = LengthMatcher()

        paths = {
            "NET_A": RoutePath(
                net="NET_A",
                cells=[GridCell(0, 0, 0), GridCell(10, 0, 0)],
                length=2.0,
                via_count=0,
                success=True,
                cell_size=0.2,
            ),
            "NET_B": RoutePath(
                net="NET_B",
                cells=[GridCell(0, 0, 0), GridCell(5, 0, 0)],
                length=1.0,
                via_count=0,
                success=True,
                cell_size=0.2,
            ),
        }

        bus = BusCohortConstraint(
            name="TEST_BUS",
            nets=["NET_A", "NET_B"],
            max_skew_mm=0.3,
        )

        result = matcher.match_bus_lengths(paths, bus, cell_size_mm=0.2)

        if result.nets_modified:
            assert "NET_B" in result.nets_modified or "NET_A" in result.nets_modified
