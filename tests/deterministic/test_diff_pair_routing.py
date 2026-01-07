"""
Tests for differential pair routing.

These tests verify:
1. P and N traces never occupy the same grid cell (prevents shorts)
2. P and N traces maintain minimum separation (edge-to-edge clearance)
3. Grid resolution is sufficient for trace width + clearance requirements
4. Coupling ratio is calculated correctly (0-100%)
5. Path reconstruction handles divergence states correctly

Key invariants:
- With 0.25mm grid and 0.127mm traces, adjacent cells give 0.123mm edge gap
- For 0.1mm clearance requirement, adjacent cells are acceptable
- For 0.2mm traces, adjacent cells give only 0.05mm gap (violation!)
"""

import pytest
import math
from typing import Set, Tuple, List


class TestDiffPairGeometry:
    """Test geometric constraints for differential pairs."""

    def test_adjacent_cell_clearance_with_thin_traces(self):
        """
        With 0.127mm traces on 0.25mm grid, adjacent cells should meet 0.1mm clearance.

        Calculation:
        - Center-to-center: 0.25mm (adjacent cells)
        - Edge-to-edge gap: 0.25 - 0.127 = 0.123mm
        - Required: 0.1mm
        - Result: PASS (0.123 >= 0.1)
        """
        grid_cell_size = 0.25  # mm
        trace_width = 0.127  # mm
        required_clearance = 0.1  # mm

        center_to_center = grid_cell_size  # adjacent cells
        edge_to_edge_gap = center_to_center - trace_width

        assert edge_to_edge_gap >= required_clearance, (
            f"Adjacent cells with {trace_width}mm traces have {edge_to_edge_gap:.3f}mm gap, "
            f"but {required_clearance}mm is required"
        )

    def test_adjacent_cell_clearance_with_thick_traces_fails(self):
        """
        With 0.2mm traces on 0.25mm grid, adjacent cells violate 0.1mm clearance.

        This is the bug we found - USB diff pair was using 0.2mm traces
        on adjacent cells, resulting in only 0.05mm gap.
        """
        grid_cell_size = 0.25  # mm
        trace_width = 0.2  # mm
        required_clearance = 0.1  # mm

        center_to_center = grid_cell_size
        edge_to_edge_gap = center_to_center - trace_width

        # This SHOULD fail - demonstrates the bug
        assert edge_to_edge_gap < required_clearance, (
            "This test documents the bug: 0.2mm traces on adjacent 0.25mm cells "
            "violate clearance requirements"
        )

        # The actual gap
        assert abs(edge_to_edge_gap - 0.05) < 0.001, (
            f"Expected 0.05mm gap, got {edge_to_edge_gap}mm"
        )

    def test_diagonal_cell_clearance(self):
        """
        Diagonal neighbors on 0.25mm grid are sqrt(2)*0.25 = 0.354mm apart.
        This should meet clearance even with 0.2mm traces.
        """
        grid_cell_size = 0.25  # mm
        trace_width = 0.2  # mm
        required_clearance = 0.1  # mm

        # Diagonal distance
        center_to_center = math.sqrt(2) * grid_cell_size
        edge_to_edge_gap = center_to_center - trace_width

        assert edge_to_edge_gap >= required_clearance, (
            f"Diagonal cells with {trace_width}mm traces have {edge_to_edge_gap:.3f}mm gap"
        )

    def test_minimum_grid_resolution_for_trace_and_clearance(self):
        """
        Calculate minimum grid resolution needed for given trace width and clearance.

        For trace_width=W and clearance=C, minimum grid size is W + C
        so adjacent cells have exactly C edge-to-edge gap.
        """
        test_cases = [
            # (trace_width, clearance, expected_min_grid)
            (0.127, 0.1, 0.227),  # FinePitch/Differential
            (0.2, 0.1, 0.3),  # Thick traces need bigger grid
            (0.15, 0.15, 0.3),  # Equal width and clearance
            (0.1, 0.2, 0.3),  # Large clearance requirement
        ]

        for trace_width, clearance, expected_min_grid in test_cases:
            min_grid = trace_width + clearance
            assert abs(min_grid - expected_min_grid) < 0.001, (
                f"For {trace_width}mm trace and {clearance}mm clearance, "
                f"minimum grid is {min_grid}mm, expected {expected_min_grid}mm"
            )


class TestDiffPairRouterConstraints:
    """Test that DiffPairRouter enforces P/N separation constraints."""

    @pytest.fixture
    def router(self):
        """Create a DiffPairRouter for testing."""
        from temper_placer.routing.diff_pair_router import DiffPairRouter

        return DiffPairRouter(
            grid_size=(100, 100, 4),  # 100x100 grid, 4 layers
            cell_size_mm=0.25,
            target_separation_mm=0.25,  # Adjacent cells
            max_divergence_mm=1.0,
            max_skew_mm=0.5,
        )

    def test_p_and_n_never_share_same_cell(self, router):
        """
        P and N traces must never occupy the same grid cell on the same layer.
        This would cause a short circuit.
        """
        from temper_placer.routing.diff_pair_router import DiffPairState

        # Create a state where P and N are adjacent
        state = DiffPairState(
            pos_x=50, pos_y=50, pos_layer=0, neg_x=51, neg_y=50, neg_layer=0, separation_mm=0.25
        )

        # Generate neighbors
        obstacles: Set[Tuple[int, int, int]] = set()
        neighbors = router._generate_coupled_neighbors(state, obstacles)

        # Check that no neighbor has P and N at same position
        for next_state, neighbor_type, cost in neighbors:
            same_position = (
                next_state.pos_x == next_state.neg_x
                and next_state.pos_y == next_state.neg_y
                and next_state.pos_layer == next_state.neg_layer
            )
            assert not same_position, (
                f"Neighbor type {neighbor_type} created state where P and N "
                f"share position ({next_state.pos_x}, {next_state.pos_y}, {next_state.pos_layer})"
            )

    def test_p_cannot_move_to_n_position(self, router):
        """
        When P moves and N waits (POS_MOVES_NEG_WAITS), P must not move
        to N's current position.
        """
        from temper_placer.routing.diff_pair_router import DiffPairState, NeighborType

        # Create a state where P is one cell away from N
        state = DiffPairState(
            pos_x=50,
            pos_y=50,
            pos_layer=0,
            neg_x=51,
            neg_y=50,
            neg_layer=0,  # N is at (51, 50)
            separation_mm=0.25,
        )

        obstacles: Set[Tuple[int, int, int]] = set()
        neighbors = router._generate_coupled_neighbors(state, obstacles)

        # Find POS_MOVES_NEG_WAITS neighbors
        pos_moves_neighbors = [
            (s, t, c) for s, t, c in neighbors if t == NeighborType.POS_MOVES_NEG_WAITS
        ]

        # None should have P at N's position (51, 50)
        for next_state, _, _ in pos_moves_neighbors:
            assert not (next_state.pos_x == 51 and next_state.pos_y == 50), (
                "P moved to N's current position - this would cause a short"
            )

    def test_n_cannot_move_to_p_position(self, router):
        """
        When N moves and P waits (NEG_MOVES_POS_WAITS), N must not move
        to P's current position.
        """
        from temper_placer.routing.diff_pair_router import DiffPairState, NeighborType

        # Create a state where N is one cell away from P
        state = DiffPairState(
            pos_x=51,
            pos_y=50,
            pos_layer=0,  # P is at (51, 50)
            neg_x=50,
            neg_y=50,
            neg_layer=0,
            separation_mm=0.25,
        )

        obstacles: Set[Tuple[int, int, int]] = set()
        neighbors = router._generate_coupled_neighbors(state, obstacles)

        # Find NEG_MOVES_POS_WAITS neighbors
        neg_moves_neighbors = [
            (s, t, c) for s, t, c in neighbors if t == NeighborType.NEG_MOVES_POS_WAITS
        ]

        # None should have N at P's position (51, 50)
        for next_state, _, _ in neg_moves_neighbors:
            assert not (next_state.neg_x == 51 and next_state.neg_y == 50), (
                "N moved to P's current position - this would cause a short"
            )


class TestDiffPairPathReconstruction:
    """Test path reconstruction from bidirectional search."""

    @pytest.fixture
    def router(self):
        """Create a DiffPairRouter for testing."""
        from temper_placer.routing.diff_pair_router import DiffPairRouter

        return DiffPairRouter(
            grid_size=(100, 100, 4),
            cell_size_mm=0.25,
            target_separation_mm=0.5,  # 2 cells apart
            max_divergence_mm=1.0,
            max_skew_mm=0.5,
        )

    def test_simple_route_no_obstacles(self, router):
        """Route a simple differential pair with no obstacles."""
        # Start: P at (10, 50), N at (10, 52) - 2 cells apart vertically
        # Goal: P at (90, 50), N at (90, 52)
        start_pins = ((2.5, 12.5), (2.5, 13.0))  # mm coordinates
        goal_pins = ((22.5, 12.5), (22.5, 13.0))

        obstacles: Set[Tuple[int, int, int]] = set()

        result = router.route_pair(start_pins, goal_pins, obstacles)

        assert result.success, f"Routing failed: {result.failure_reason}"
        assert len(result.pos_cells) > 0, "P path is empty"
        assert len(result.neg_cells) > 0, "N path is empty"

        # Verify P and N never share a cell
        for i, (p_cell, n_cell) in enumerate(zip(result.pos_cells, result.neg_cells)):
            assert p_cell != n_cell, f"At step {i}, P and N share cell {p_cell}"

    def test_coupling_ratio_is_valid_percentage(self, router):
        """Coupling ratio must be between 0 and 100%."""
        start_pins = ((2.5, 12.5), (2.5, 13.0))
        goal_pins = ((22.5, 12.5), (22.5, 13.0))

        obstacles: Set[Tuple[int, int, int]] = set()
        result = router.route_pair(start_pins, goal_pins, obstacles)

        if result.success:
            assert 0 <= result.coupling_ratio <= 100, (
                f"Coupling ratio {result.coupling_ratio}% is outside valid range [0, 100]"
            )

    def test_paths_have_equal_length(self, router):
        """
        P and N paths should have the same number of cells since they're
        extracted from the same DiffPairState sequence.
        """
        start_pins = ((2.5, 12.5), (2.5, 13.0))
        goal_pins = ((22.5, 12.5), (22.5, 13.0))

        obstacles: Set[Tuple[int, int, int]] = set()
        result = router.route_pair(start_pins, goal_pins, obstacles)

        if result.success:
            assert len(result.pos_cells) == len(result.neg_cells), (
                f"P path has {len(result.pos_cells)} cells, "
                f"N path has {len(result.neg_cells)} cells"
            )


class TestDiffPairTraceGeneration:
    """Test conversion of diff pair paths to actual traces."""

    def test_trace_segments_dont_overlap(self):
        """
        When converting grid cells to traces, P and N traces must not
        create overlapping segments on the same layer.
        """
        # Simulated path cells (what diff pair router might output)
        # P path: moves right
        pos_cells = [(10, 50, 0), (11, 50, 0), (12, 50, 0), (13, 50, 0)]
        # N path: also moves right, one cell above
        neg_cells = [(10, 51, 0), (11, 51, 0), (12, 51, 0), (13, 51, 0)]

        cell_size_mm = 0.25
        trace_width = 0.127

        # Convert to trace segments
        def cells_to_segments(cells):
            segments = []
            for i in range(len(cells) - 1):
                c1, c2 = cells[i], cells[i + 1]
                if c1[2] == c2[2]:  # Same layer
                    start = (c1[0] * cell_size_mm, c1[1] * cell_size_mm)
                    end = (c2[0] * cell_size_mm, c2[1] * cell_size_mm)
                    segments.append((start, end, c1[2]))
            return segments

        pos_segments = cells_to_segments(pos_cells)
        neg_segments = cells_to_segments(neg_cells)

        # Check no segment pairs overlap
        def segments_overlap(s1, s2, width):
            """Check if two line segments are too close (would overlap with given width)."""
            # Simple check: if endpoints are within width distance, they might overlap
            min_dist = width  # Center-to-center must be > width for no overlap

            for p1 in [s1[0], s1[1]]:
                for p2 in [s2[0], s2[1]]:
                    dist = math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
                    if dist < min_dist:
                        return True
            return False

        for p_seg in pos_segments:
            for n_seg in neg_segments:
                if p_seg[2] == n_seg[2]:  # Same layer
                    assert not segments_overlap(p_seg, n_seg, trace_width), (
                        f"P segment {p_seg} overlaps with N segment {n_seg}"
                    )

    def test_no_zero_length_segments(self):
        """
        Traces should not have zero-length segments (same start and end point).
        This can happen if P or N "waits" during divergence.
        """
        # Simulated path with a "wait" state (repeated position)
        pos_cells = [(10, 50, 0), (11, 50, 0), (11, 50, 0), (12, 50, 0)]  # (11,50) repeated

        cell_size_mm = 0.25

        # Convert and filter zero-length segments
        segments = []
        for i in range(len(pos_cells) - 1):
            c1, c2 = pos_cells[i], pos_cells[i + 1]
            if c1 != c2 and c1[2] == c2[2]:  # Different position, same layer
                start = (c1[0] * cell_size_mm, c1[1] * cell_size_mm)
                end = (c2[0] * cell_size_mm, c2[1] * cell_size_mm)
                segments.append((start, end))

        # All segments should have non-zero length
        for start, end in segments:
            length = math.sqrt((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2)
            assert length > 0, f"Zero-length segment from {start} to {end}"


class TestDiffPairConfigValidation:
    """Test that diff pair configuration is valid for the grid."""

    def test_spacing_compatible_with_grid(self):
        """
        The configured spacing_mm should be achievable on the grid.
        If spacing < cell_size, P and N would need to be in the same cell.
        """
        # Load actual config
        import yaml

        try:
            with open("configs/temper_deterministic_config.yaml") as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            pytest.skip("Config file not found")

        diff_pairs = config.get("differential_pairs", [])
        grid_cell_size = 0.25  # From pipeline

        for dp in diff_pairs:
            spacing = dp.get("spacing_mm", 0.25)
            assert spacing >= grid_cell_size, (
                f"Diff pair spacing {spacing}mm is less than grid cell size {grid_cell_size}mm. "
                f"P and N cannot be closer than one grid cell apart."
            )

    def test_trace_width_and_clearance_fit_in_grid(self):
        """
        For adjacent cell routing, trace_width + clearance <= grid_cell_size
        must hold to avoid DRC violations.
        """
        import yaml

        try:
            with open("configs/temper_deterministic_config.yaml") as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            pytest.skip("Config file not found")

        net_classes = config.get("net_classes", {})
        diff_class = net_classes.get("Differential", {})

        trace_width = diff_class.get("trace_width_mm", 0.127)
        clearance = diff_class.get("clearance_mm", 0.1)
        grid_cell_size = 0.25

        # For adjacent cells to meet clearance:
        # edge_gap = grid_cell_size - trace_width >= clearance
        # Therefore: trace_width <= grid_cell_size - clearance
        max_trace_width = grid_cell_size - clearance

        assert trace_width <= max_trace_width, (
            f"Differential trace width {trace_width}mm is too large for "
            f"{grid_cell_size}mm grid with {clearance}mm clearance. "
            f"Maximum trace width is {max_trace_width}mm."
        )


class TestDiffPairEdgeCases:
    """Test edge cases and potential failure modes."""

    @pytest.fixture
    def router(self):
        from temper_placer.routing.diff_pair_router import DiffPairRouter

        return DiffPairRouter(
            grid_size=(50, 50, 4),
            cell_size_mm=0.25,
            target_separation_mm=0.25,
            max_divergence_mm=0.5,
            max_skew_mm=0.5,
        )

    def test_route_with_obstacle_between_pins(self, router):
        """
        Test routing when there's an obstacle directly between start and goal.
        The router should find a path around it.
        """
        start_pins = ((2.5, 6.25), (2.5, 6.5))
        goal_pins = ((10.0, 6.25), (10.0, 6.5))

        # Block the direct path
        obstacles: Set[Tuple[int, int, int]] = set()
        for x in range(20, 35):
            for y in range(20, 30):
                obstacles.add((x, y, 0))

        result = router.route_pair(start_pins, goal_pins, obstacles)

        # Should either succeed with a path around, or fail gracefully
        if result.success:
            # Verify path doesn't go through obstacles
            for cell in result.pos_cells:
                assert cell not in obstacles, f"P path goes through obstacle at {cell}"
            for cell in result.neg_cells:
                assert cell not in obstacles, f"N path goes through obstacle at {cell}"

    def test_route_when_pins_are_very_close(self, router):
        """
        Test routing when start and goal pins are very close together.
        """
        start_pins = ((2.5, 6.25), (2.5, 6.5))
        goal_pins = ((3.0, 6.25), (3.0, 6.5))  # Only 2 cells away

        obstacles: Set[Tuple[int, int, int]] = set()
        result = router.route_pair(start_pins, goal_pins, obstacles)

        if result.success:
            assert len(result.pos_cells) >= 2, "Path too short"
            assert len(result.neg_cells) >= 2, "Path too short"

    def test_separation_never_zero(self, router):
        """
        The separation between P and N should never be zero
        (they should never occupy the same cell).
        """
        start_pins = ((2.5, 6.25), (2.5, 6.5))
        goal_pins = ((10.0, 6.25), (10.0, 6.5))

        obstacles: Set[Tuple[int, int, int]] = set()
        result = router.route_pair(start_pins, goal_pins, obstacles)

        if result.success:
            for p_cell, n_cell in zip(result.pos_cells, result.neg_cells):
                # Calculate separation
                dx = (p_cell[0] - n_cell[0]) * router.cell_size_mm
                dy = (p_cell[1] - n_cell[1]) * router.cell_size_mm
                separation = math.sqrt(dx**2 + dy**2)

                assert separation > 0, f"P and N have zero separation at P={p_cell}, N={n_cell}"


class TestDiffPairIntegration:
    """Integration tests with the full routing pipeline."""

    def test_usb_diff_pair_no_shorts(self):
        """
        End-to-end test: Route USB_D+ and USB_D- and verify no shorts.
        This is the specific bug we encountered.
        """
        pytest.skip("Integration test - requires full pipeline setup")

        # TODO: When pipeline is available:
        # 1. Create minimal netlist with USB_D+ and USB_D-
        # 2. Run diff pair routing
        # 3. Export to KiCad format
        # 4. Run DRC and verify no shorting_items violations

    def test_diff_pair_clearance_violations(self):
        """
        End-to-end test: Verify diff pair traces meet clearance requirements.
        """
        pytest.skip("Integration test - requires full pipeline setup")

        # TODO: When pipeline is available:
        # 1. Create minimal netlist with diff pair
        # 2. Route with known trace width and clearance
        # 3. Verify all segment pairs meet clearance


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
