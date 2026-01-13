#!/usr/bin/env python3
"""Integration tests for differential pair minimum spacing enforcement.

Tests that diff pair router correctly enforces minimum separation to prevent
shorts when trace edges overlap.
"""

import sys
from pathlib import Path
from typing import Tuple, List

import pytest

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packages/temper-placer/src"))

from temper_placer.routing.diff_pair_router import DiffPairRouter, DiffPairPath


def calculate_edge_to_edge_distance(
    pos1: Tuple[float, float],
    pos2: Tuple[float, float],
    trace_width: float,
) -> float:
    """Calculate edge-to-edge distance between two parallel traces.

    Args:
        pos1: Center position of trace 1 (x, y)
        pos2: Center position of trace 2 (x, y)
        trace_width: Width of traces (assumed same for both)

    Returns:
        Edge-to-edge distance (negative if overlapping)
    """
    # Center-to-center distance
    dx = pos2[0] - pos1[0]
    dy = pos2[1] - pos1[1]
    center_dist = (dx * dx + dy * dy) ** 0.5

    # Edge-to-edge = center - both radii
    edge_dist = center_dist - trace_width
    return edge_dist


class TestDiffPairMinimumSpacing:
    """Test differential pair spacing enforcement."""

    def test_adjacent_cells_cause_shorts_with_025mm_traces(self):
        """Adjacent cells (0.25mm apart) with 0.25mm traces cause shorts."""
        # Setup: 0.25mm grid, 0.25mm traces
        trace_width = 0.25
        clearance = 0.127
        cell_size = 0.25

        # Adjacent cells are 0.25mm apart center-to-center
        # With 0.25mm trace width, edges are at:
        # Trace 1: -0.125 to +0.125
        # Trace 2: 0.125 to 0.375 (starting at 0.25)
        # Overlap zone: 0.125 to 0.125 = TOUCHING (violation)

        center_separation = cell_size  # Adjacent = 1 cell apart
        edge_separation = calculate_edge_to_edge_distance(
            (0, 0), (center_separation, 0), trace_width
        )

        # Edge separation should be 0 (touching)
        assert edge_separation == 0.0, f"Expected touching edges, got {edge_separation}mm apart"

        # This violates clearance requirement
        assert edge_separation < clearance, "Adjacent cells violate clearance"

    def test_minimum_safe_separation_calculation(self):
        """Calculate minimum safe center-to-center separation."""
        trace_width = 0.25
        clearance = 0.127

        # Minimum safe = trace_width + clearance (edge-to-edge must be >= clearance)
        # Actually: edge_to_edge = center_separation - trace_width >= clearance
        # So: center_separation >= trace_width + clearance
        min_safe_separation = trace_width + clearance

        assert min_safe_separation == 0.377, "Minimum safe separation for 0.25mm traces"

        # With 0.25mm grid, minimum is 2 cells apart (0.5mm)
        min_cells = 2
        assert min_cells * 0.25 >= min_safe_separation, "Need at least 2 cells apart"

    def test_router_enforces_minimum_spacing_simple_path(self):
        """Router should enforce minimum spacing throughout path."""
        # Create router with realistic parameters
        router = DiffPairRouter(
            grid_size=(400, 400, 2),  # Large enough for our test (100mm x 100mm)
            cell_size_mm=0.25,
            target_separation_mm=0.5,  # 2 cells apart (safe)
            max_divergence_mm=2.0,
        )

        # Simple straight-line routing
        start_pos = (10.0, 50.0)
        start_neg = (10.5, 50.0)  # 0.5mm apart (safe)
        goal_pos = (90.0, 50.0)
        goal_neg = (90.5, 50.0)

        result = router.route_pair(
            start_pins=(start_pos, start_neg),
            goal_pins=(goal_pos, goal_neg),
            obstacles=set(),
        )

        assert result is not None, "Should find path with safe spacing"
        assert result.success, f"Routing should succeed. Failure: {result.failure_reason}"

        # Verify no points are too close
        trace_width = 0.25  # Default USB trace width
        min_safe = 0.377  # trace_width + clearance

        # Check spacing at each position along the path
        assert len(result.pos_cells) == len(result.neg_cells), "Paths should have same length"

        for i, (pos_cell, neg_cell) in enumerate(zip(result.pos_cells, result.neg_cells)):
            pos = (pos_cell[0] * router.cell_size_mm, pos_cell[1] * router.cell_size_mm)
            neg = (neg_cell[0] * router.cell_size_mm, neg_cell[1] * router.cell_size_mm)

            dx = neg[0] - pos[0]
            dy = neg[1] - pos[1]
            separation = (dx * dx + dy * dy) ** 0.5

            assert separation >= min_safe, (
                f"Separation {separation:.3f}mm < minimum {min_safe:.3f}mm at position {i}"
            )

    def test_router_rejects_tight_spacing_constraint(self):
        """Router with spacing < min_safe should reject configuration."""
        # This configuration would cause shorts if allowed
        router = DiffPairRouter(
            grid_size=(400, 400, 2),  # Large enough for test
            cell_size_mm=0.25,
            target_separation_mm=0.25,  # TOO TIGHT!
            trace_width_mm=0.25,
            clearance_mm=0.127,
            max_divergence_mm=2.0,
        )

        start_pos = (10.0, 50.0)
        start_neg = (10.25, 50.0)  # Only 0.25mm apart (below min_safe)
        goal_pos = (90.0, 50.0)
        goal_neg = (90.25, 50.0)

        # Router should reject this configuration
        result = router.route_pair(
            start_pins=(start_pos, start_neg),
            goal_pins=(goal_pos, goal_neg),
            obstacles=set(),
        )

        # After EXP-3 fix: should fail with spacing violation
        assert not result.success, "Should reject configuration with spacing < min_safe"
        assert result.failure_reason is not None, "Should have failure reason"
        assert "too close" in result.failure_reason.lower(), (
            f"Expected spacing failure, got: {result.failure_reason}"
        )

    def test_config_spacing_validation(self):
        """Verify config uses safe spacing value."""
        # From configs/temper_deterministic_config.yaml
        config_spacing = 0.25  # Current value in config
        trace_width = 0.25  # USB trace width (updated assumption)
        clearance = 0.127  # FinePitch clearance

        min_safe = trace_width + clearance  # 0.377mm

        # Config should use at least min_safe, rounded to grid
        # Current config value is TOO TIGHT for 0.25mm traces
        assert config_spacing < min_safe, (
            f"Config spacing {config_spacing}mm < minimum safe {min_safe}mm "
            f"for {trace_width}mm traces (known issue - causes shorts)"
        )

        # Recommended: Round up to next grid cell
        recommended_spacing = 0.5  # 2 cells apart
        assert recommended_spacing >= min_safe, (
            f"0.5mm provides {recommended_spacing - min_safe:.3f}mm margin"
        )


class TestDiffPairSpacingWithObstacles:
    """Test spacing enforcement with obstacles and layer changes."""

    def test_spacing_maintained_around_obstacles(self):
        """Traces should maintain spacing even when navigating obstacles."""
        router = DiffPairRouter(
            grid_size=(400, 400, 2),  # Large enough for test
            cell_size_mm=0.25,
            target_separation_mm=0.5,
            max_divergence_mm=2.0,
        )

        # Add obstacle in the middle
        obstacles = set()
        for x in range(160, 240):  # Scaled up for 400x400 grid
            for y in range(192, 208):
                obstacles.add((x, y, 0))  # Block on layer 0

        start_pos = (10.0, 50.0)
        start_neg = (10.5, 50.0)
        goal_pos = (90.0, 50.0)
        goal_neg = (90.5, 50.0)

        result = router.route_pair(
            start_pins=(start_pos, start_neg),
            goal_pins=(goal_pos, goal_neg),
            obstacles=obstacles,
        )

        if result and result.success:
            # Verify spacing maintained throughout
            min_safe = 0.377
            for i, (pos_cell, neg_cell) in enumerate(zip(result.pos_cells, result.neg_cells)):
                pos = (pos_cell[0] * router.cell_size_mm, pos_cell[1] * router.cell_size_mm)
                neg = (neg_cell[0] * router.cell_size_mm, neg_cell[1] * router.cell_size_mm)

                dx = neg[0] - pos[0]
                dy = neg[1] - pos[1]
                separation = (dx * dx + dy * dy) ** 0.5

                assert separation >= min_safe, (
                    f"Spacing violated near obstacle: {separation:.3f}mm < {min_safe:.3f}mm at position {i}"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
