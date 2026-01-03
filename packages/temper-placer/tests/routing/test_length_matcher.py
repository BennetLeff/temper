"""
Tests for differential pair length matching.

Verifies serpentine insertion and length equalization for high-speed differential pairs.
"""

import pytest
import math
from temper_placer.routing.maze_router import GridCell, RoutePath
from temper_placer.routing.post_processing.length_matcher import (
    LengthMatcher,
    SerpentineParams,
)


class TestSerpentineParams:
    """Tests for SerpentineParams dataclass."""

    def test_default_parameters(self):
        """Should use sensible defaults for serpentine configuration."""
        params = SerpentineParams()
        assert params.amplitude_mm == 0.5
        assert params.pitch_mm == 1.0  # 2x amplitude
        assert params.tolerance_mm == 0.5
        assert params.min_straight_length_mm == 2.0

    def test_pitch_auto_calculation(self):
        """Should auto-set pitch to 2x amplitude when not specified."""
        params = SerpentineParams(amplitude_mm=0.3)
        # Since pitch has default 1.0, post_init should set it to 2*amplitude
        assert params.pitch_mm == 0.6

    def test_custom_pitch_preserved(self):
        """Should preserve explicitly set pitch value."""
        params = SerpentineParams(amplitude_mm=0.5, pitch_mm=1.5)
        assert params.pitch_mm == 1.5  # Not overridden


class TestMeasurePathLength:
    """Tests for path length measurement."""

    def test_empty_path(self):
        """Should return 0 for empty path."""
        matcher = LengthMatcher()
        assert matcher.measure_path_length([], cell_size_mm=0.1) == 0.0

    def test_single_cell(self):
        """Should return 0 for single-cell path."""
        matcher = LengthMatcher()
        cells = [GridCell(0, 0, 0)]
        assert matcher.measure_path_length(cells, cell_size_mm=0.1) == 0.0

    def test_straight_horizontal_path(self):
        """Should calculate correct length for horizontal path."""
        matcher = LengthMatcher()
        cells = [GridCell(0, 0, 0), GridCell(10, 0, 0)]  # 10 cells = 1mm at 0.1mm/cell
        length = matcher.measure_path_length(cells, cell_size_mm=0.1)
        assert length == pytest.approx(1.0, abs=0.01)

    def test_straight_vertical_path(self):
        """Should calculate correct length for vertical path."""
        matcher = LengthMatcher()
        cells = [GridCell(0, 0, 0), GridCell(0, 20, 0)]  # 20 cells = 2mm
        length = matcher.measure_path_length(cells, cell_size_mm=0.1)
        assert length == pytest.approx(2.0, abs=0.01)

    def test_diagonal_path(self):
        """Should calculate Euclidean distance for diagonal moves."""
        matcher = LengthMatcher()
        cells = [GridCell(0, 0, 0), GridCell(10, 10, 0)]  # sqrt(10^2 + 10^2) * 0.1
        expected = math.sqrt(10 * 10 + 10 * 10) * 0.1
        length = matcher.measure_path_length(cells, cell_size_mm=0.1)
        assert length == pytest.approx(expected, abs=0.01)

    def test_multi_segment_path(self):
        """Should sum all segments for complex paths."""
        matcher = LengthMatcher()
        cells = [
            GridCell(0, 0, 0),
            GridCell(10, 0, 0),  # +1mm horizontal
            GridCell(10, 10, 0),  # +1mm vertical
            GridCell(20, 10, 0),  # +1mm horizontal
        ]
        length = matcher.measure_path_length(cells, cell_size_mm=0.1)
        assert length == pytest.approx(3.0, abs=0.01)


class TestFindStraightSegments:
    """Tests for straight segment identification."""

    def test_no_segments_short_path(self):
        """Should return empty list for paths too short."""
        matcher = LengthMatcher()
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 0)]
        segments = matcher.find_straight_segments(cells, cell_size_mm=0.1, min_length_mm=2.0)
        assert segments == []

    def test_single_straight_segment(self):
        """Should identify a single long straight segment."""
        matcher = LengthMatcher()
        cells = [GridCell(i, 0, 0) for i in range(30)]  # 3mm straight line
        segments = matcher.find_straight_segments(cells, cell_size_mm=0.1, min_length_mm=2.0)
        assert len(segments) == 1
        assert segments[0] == (0, 29)

    def test_filter_short_segments(self):
        """Should filter out segments shorter than min_length."""
        matcher = LengthMatcher()
        # Short segment (10 cells = 1mm)
        cells = [GridCell(i, 0, 0) for i in range(10)]
        segments = matcher.find_straight_segments(cells, cell_size_mm=0.1, min_length_mm=2.0)
        assert len(segments) == 0

    def test_multiple_segments_with_corners(self):
        """Should split at corners and return multiple segments."""
        matcher = LengthMatcher()
        cells = (
            [GridCell(i, 0, 0) for i in range(30)]  # 3mm horizontal
            + [GridCell(29, i, 0) for i in range(1, 30)]  # 3mm vertical
        )
        segments = matcher.find_straight_segments(cells, cell_size_mm=0.1, min_length_mm=2.0)
        assert len(segments) == 2  # Two straight segments separated by corner

    def test_layer_change_breaks_segment(self):
        """Should treat layer change as segment boundary."""
        matcher = LengthMatcher()
        cells = (
            [GridCell(i, 0, 0) for i in range(30)]  # Layer 0
            + [GridCell(29, 0, 1)]  # Via to layer 1
            + [GridCell(29 + i, 0, 1) for i in range(1, 30)]  # Layer 1
        )
        segments = matcher.find_straight_segments(cells, cell_size_mm=0.1, min_length_mm=2.0)
        assert len(segments) == 2  # Split at layer change


class TestInsertSerpentine:
    """Tests for serpentine insertion."""

    def test_serpentine_adds_length(self):
        """Should increase path length after serpentine insertion."""
        matcher = LengthMatcher()
        cells = [GridCell(i, 5, 0) for i in range(50)]  # 5mm straight
        params = SerpentineParams(amplitude_mm=0.5, tolerance_mm=0.5)
        
        original_length = matcher.measure_path_length(cells, cell_size_mm=0.1)
        new_cells = matcher.insert_serpentine(
            cells, segment=(0, 49), length_delta_mm=1.0, cell_size_mm=0.1, params=params
        )
        new_length = matcher.measure_path_length(new_cells, cell_size_mm=0.1)
        
        assert new_length > original_length
        assert new_length >= original_length + 0.5  # Should add at least some length

    def test_serpentine_preserves_endpoints(self):
        """Should maintain same start and end points."""
        matcher = LengthMatcher()
        cells = [GridCell(i, 10, 0) for i in range(50)]
        params = SerpentineParams(amplitude_mm=0.5)
        
        new_cells = matcher.insert_serpentine(
            cells, segment=(5, 45), length_delta_mm=1.0, cell_size_mm=0.1, params=params
        )
        
        # Start and end should be unchanged
        assert new_cells[0] == cells[0]
        assert new_cells[-1] == cells[-1]

    def test_horizontal_serpentine_perpendicular(self):
        """Horizontal trace should get vertical serpentine."""
        matcher = LengthMatcher()
        cells = [GridCell(i, 10, 0) for i in range(50)]  # Horizontal
        params = SerpentineParams(amplitude_mm=0.5)
        
        new_cells = matcher.insert_serpentine(
            cells, segment=(10, 40), length_delta_mm=1.0, cell_size_mm=0.1, params=params
        )
        
        # Check that some cells have different Y coordinates (vertical deviation)
        y_coords = [c.y for c in new_cells]
        assert len(set(y_coords)) > 1  # Multiple Y values means vertical deviation


class TestMatchDifferentialPairLengths:
    """Tests for differential pair length matching integration."""

    def test_no_matching_if_within_tolerance(self):
        """Should not modify paths if length delta is within tolerance."""
        matcher = LengthMatcher()
        params = SerpentineParams(tolerance_mm=1.0)
        
        # Create two paths with similar lengths
        cells_pos = [GridCell(i, 0, 0) for i in range(30)]  # 3mm
        cells_neg = [GridCell(i, 2, 0) for i in range(32)]  # 3.2mm
        
        path_pos = RoutePath(
            net="D+", cells=cells_pos, length=3.0, via_count=0, success=True
        )
        path_neg = RoutePath(
            net="D-", cells=cells_neg, length=3.2, via_count=0, success=True
        )
        
        new_pos, new_neg = matcher.match_differential_pair_lengths(
            path_pos, path_neg, params
        )
        
        # Paths should be unchanged
        assert len(new_pos.cells) == len(path_pos.cells)
        assert len(new_neg.cells) == len(path_neg.cells)

    def test_matching_modifies_shorter_path(self):
        """Should add serpentine to shorter path when delta exceeds tolerance."""
        matcher = LengthMatcher()
        params = SerpentineParams(tolerance_mm=0.3, amplitude_mm=0.5)
        
        # Create paths with significant length difference
        cells_pos = [GridCell(i, 0, 0) for i in range(30)]  # 3mm
        cells_neg = [GridCell(i, 2, 0) for i in range(50)]  # 5mm
        
        path_pos = RoutePath(
            net="D+", cells=cells_pos, length=3.0, via_count=0, success=True
        )
        path_neg = RoutePath(
            net="D-", cells=cells_neg, length=5.0, via_count=0, success=True
        )
        
        new_pos, new_neg = matcher.match_differential_pair_lengths(
            path_pos, path_neg, params
        )
        
        # Shorter path (pos) should be modified
        assert len(new_pos.cells) > len(path_pos.cells)
        # Longer path should be unchanged
        assert len(new_neg.cells) == len(path_neg.cells)

    def test_failed_paths_unchanged(self):
        """Should not modify failed routing paths."""
        matcher = LengthMatcher()
        params = SerpentineParams()
        
        path_pos = RoutePath(
            net="D+", cells=[], length=0, via_count=0, success=False, failure_reason="blocked"
        )
        path_neg = RoutePath(
            net="D-", cells=[], length=0, via_count=0, success=True
        )
        
        new_pos, new_neg = matcher.match_differential_pair_lengths(
            path_pos, path_neg, params
        )
        
        assert new_pos == path_pos
        assert new_neg == path_neg

    def test_no_suitable_segments_returns_unchanged(self):
        """Should return original paths if no suitable straight segments exist."""
        matcher = LengthMatcher()
        params = SerpentineParams(min_straight_length_mm=10.0)  # Very long minimum
        
        # Short paths with no long straights
        cells_pos = [GridCell(i % 2, i // 2, 0) for i in range(20)]  # Zigzag
        cells_neg = [GridCell(i, 2, 0) for i in range(50)]
        
        path_pos = RoutePath(
            net="D+", cells=cells_pos, length=2.0, via_count=0, success=True
        )
        path_neg = RoutePath(
            net="D-", cells=cells_neg, length=5.0, via_count=0, success=True
        )
        
        new_pos, new_neg = matcher.match_differential_pair_lengths(
            path_pos, path_neg, params
        )
        
        # Should be unchanged (no suitable segments for serpentine)
        assert len(new_pos.cells) == len(path_pos.cells)
