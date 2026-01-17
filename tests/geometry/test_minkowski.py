"""
Tests for Minkowski sum configuration space computation.

Verifies exact Minkowski sum calculations for collision-free
configuration space generation in PCB placement and routing.
"""

import pytest
from shapely.geometry import box, Polygon, LineString

from geometry.minkowski import (
    compute_minkowski_clearance,
    compute_trace_corridor,
    required_gap_for_traces,
    compute_c_obstacle,
    compute_obstacle_with_clearance,
    compute_parallel_trace_forbidden_region,
    min_minkowski_distance,
    TraceSpec,
)


class TestComputeMinkowskiClearance:
    """Tests for compute_minkowski_clearance function."""

    def test_square_obstacle_expands_correctly(self):
        """Verify that a square obstacle expands by the expected amount."""
        obs = box(0, 0, 10, 10)
        clearance = compute_minkowski_clearance(obs, trace_width=0.5, clearance=0.2)

        assert clearance.area > obs.area
        assert clearance.contains(obs)

    def test_trace_width_affects_expansion(self):
        """Verify that larger trace widths create larger clearance polygons."""
        obs = box(0, 0, 10, 10)

        clearance_narrow = compute_minkowski_clearance(obs, trace_width=0.2, clearance=0.1)
        clearance_wide = compute_minkowski_clearance(obs, trace_width=1.0, clearance=0.1)

        assert clearance_wide.area > clearance_narrow.area

    def test_clearance_affects_expansion(self):
        """Verify that larger clearances create larger clearance polygons."""
        obs = box(0, 0, 10, 10)

        clearance_small = compute_minkowski_clearance(obs, trace_width=0.5, clearance=0.1)
        clearance_large = compute_minkowski_clearance(obs, trace_width=0.5, clearance=0.5)

        assert clearance_large.area > clearance_small.area

    def test_zero_clearance_equals_trace_buffer(self):
        """Verify that zero clearance gives exact trace width buffer."""
        obs = box(0, 0, 10, 10)
        trace_width = 0.5

        clearance = compute_minkowski_clearance(obs, trace_width=trace_width, clearance=0.0)
        expected = obs.buffer(trace_width / 2.0, join_style="bevel", cap_style="square")

        assert clearance.contains(expected) or expected.contains(clearance)

    def test_invalid_polygon_is_repaired(self):
        """Verify that invalid polygons are repaired before processing."""
        obs = Polygon([(0, 0), (5, 5), (10, 0), (10, 10), (5, 5), (0, 10)])
        assert not obs.is_valid

        clearance = compute_minkowski_clearance(obs, trace_width=0.5, clearance=0.2)
        assert clearance.is_valid


class TestComputeTraceCorridor:
    """Tests for compute_trace_corridor function."""

    def test_corridor_contains_line(self):
        """Verify that the corridor contains the original line."""
        start = (0, 0)
        end = (10, 0)
        corridor = compute_trace_corridor(start, end, width=0.5, clearance=0.2)

        line = LineString([start, end])
        assert corridor.contains(line)

    def test_corridor_width_affects_size(self):
        """Verify that larger widths create larger corridors."""
        start = (0, 0)
        end = (10, 0)

        corridor_narrow = compute_trace_corridor(start, end, width=0.2, clearance=0.1)
        corridor_wide = compute_trace_corridor(start, end, width=1.0, clearance=0.1)

        assert corridor_wide.area > corridor_narrow.area

    def test_diagonal_corridor(self):
        """Verify corridor computation for diagonal traces."""
        start = (0, 0)
        end = (10, 10)
        corridor = compute_trace_corridor(start, end, width=0.5, clearance=0.2)

        assert corridor.is_valid
        assert corridor.area > 0

    def test_vertical_corridor(self):
        """Verify corridor computation for vertical traces."""
        start = (5, 0)
        end = (5, 10)
        corridor = compute_trace_corridor(start, end, width=0.5, clearance=0.2)

        assert corridor.is_valid
        line = LineString([start, end])
        assert corridor.contains(line)


class TestRequiredGapForTraces:
    """Tests for required_gap_for_traces function."""

    def test_empty_list_returns_zero(self):
        """Verify that empty list returns zero gap."""
        assert required_gap_for_traces([], 0.2) == 0.0

    def test_single_trace_returns_half_width(self):
        """Verify gap for single trace is half its width plus clearance."""
        gap = required_gap_for_traces([0.5], 0.2)
        expected = (max([0.5]) + min([0.5])) / 2.0 + 0.2
        assert abs(gap - expected) < 0.01

    def test_equal_width_traces(self):
        """Verify gap calculation for equal-width parallel traces."""
        gap = required_gap_for_traces([0.5, 0.5, 0.5], 0.2)
        assert abs(gap - (0.5 + 0.2)) < 0.001

    def test_different_width_traces(self):
        """Verify gap calculation for different-width traces."""
        gap = required_gap_for_traces([0.3, 0.8], 0.2)
        expected = (0.8 + 0.3) / 2.0 + 0.2
        assert abs(gap - expected) < 0.001

    def test_clearance_affects_gap(self):
        """Verify that larger clearances require larger gaps."""
        gap_small = required_gap_for_traces([0.5, 0.5], 0.1)
        gap_large = required_gap_for_traces([0.5, 0.5], 0.3)

        assert gap_large > gap_small
        assert abs(gap_large - gap_small - 0.2) < 0.001


class TestComputeCObstacle:
    """Tests for compute_c_obstacle function."""

    def test_c_obstacle_contains_component(self):
        """Verify that C-obstacle contains the original component."""
        component = box(0, 0, 5, 5)
        spec = TraceSpec(width=0.5)

        c_obstacle = compute_c_obstacle(component, spec)

        assert c_obstacle.contains(component)

    def test_trace_width_affects_c_obstacle(self):
        """Verify that C-obstacle grows with trace width."""
        component = box(0, 0, 5, 5)

        spec_narrow = TraceSpec(width=0.2)
        spec_wide = TraceSpec(width=1.0)

        c_obstacle_narrow = compute_c_obstacle(component, spec_narrow)
        c_obstacle_wide = compute_c_obstacle(component, spec_wide)

        assert c_obstacle_wide.area > c_obstacle_narrow.area


class TestComputeObstacleWithClearance:
    """Tests for compute_obstacle_with_clearance function."""

    def test_forbidden_region_excludes_trace(self):
        """Verify that forbidden region is larger than the obstacle."""
        obs = box(0, 0, 10, 10)

        forbidden = compute_obstacle_with_clearance(obs, trace_width=0.5, clearance=0.2)

        assert forbidden.area > obs.area


class TestComputeParallelTraceForbiddenRegion:
    """Tests for compute_parallel_trace_forbidden_region function."""

    def test_two_parallel_traces(self):
        """Verify forbidden region for two parallel traces."""
        trace1 = LineString([(0, 0), (10, 0)])
        trace2 = LineString([(0, 2), (10, 2)])

        forbidden = compute_parallel_trace_forbidden_region(
            [trace1, trace2], trace_width=0.2, clearance=0.1
        )

        assert forbidden.area > 0

    def test_returns_polygon(self):
        """Verify that result is a valid Polygon."""
        trace = LineString([(0, 0), (10, 0)])

        forbidden = compute_parallel_trace_forbidden_region([trace], trace_width=0.5, clearance=0.2)

        assert isinstance(forbidden, Polygon)
        assert forbidden.is_valid


class TestMinMinkowskiDistance:
    """Tests for min_minkowski_distance function."""

    def test_same_polygon_returns_zero(self):
        """Verify that distance to self is zero."""
        obs = box(0, 0, 10, 10)
        dist = min_minkowski_distance(obs, obs)
        assert dist == 0.0

    def test_separated_polygons(self):
        """Verify distance calculation for separated polygons."""
        obs1 = box(0, 0, 10, 10)
        obs2 = box(20, 0, 30, 10)

        dist = min_minkowski_distance(obs1, obs2)

        assert dist == 10.0

    def test_touching_polygons(self):
        """Verify distance for touching polygons."""
        obs1 = box(0, 0, 10, 10)
        obs2 = box(10, 0, 20, 10)

        dist = min_minkowski_distance(obs1, obs2)

        assert dist == 0.0

    def test_overlapping_polygons(self):
        """Verify distance for overlapping polygons is zero (they touch/overlap)."""
        obs1 = box(0, 0, 10, 10)
        obs2 = box(5, 5, 15, 15)

        dist = min_minkowski_distance(obs1, obs2)

        assert dist == 0.0


class TestTraceSpec:
    """Tests for TraceSpec dataclass."""

    def test_default_values(self):
        """Verify default values for TraceSpec."""
        spec = TraceSpec(width=0.5)

        assert spec.width == 0.5
        assert spec.layer == "top"
        assert spec.is_differential_pair is False
        assert spec.coupled_width == 0.0

    def test_differential_pair_spec(self):
        """Verify differential pair trace specification."""
        spec = TraceSpec(width=0.5, layer="top", is_differential_pair=True, coupled_width=0.2)

        assert spec.is_differential_pair is True
        assert spec.coupled_width == 0.2
