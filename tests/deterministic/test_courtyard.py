import pytest
from temper_placer.deterministic.geometry.courtyard import Courtyard, check_overlap


def test_courtyard_creation():
    points = [(0, 0), (10, 0), (10, 10), (0, 10)]
    c = Courtyard("Test", points)
    assert c._polygon.area == 100.0


def test_courtyard_overlap():
    # Two 10x10 squares
    # c1 centered at 0,0 (points relative to center)
    p1 = [(-5, -5), (5, -5), (5, 5), (-5, 5)]
    c1 = Courtyard("C1", p1)

    # c2 identical
    c2 = Courtyard("C2", p1)

    # Case 1: Massive overlap (same pos)
    assert check_overlap(c1, (0, 0), 0, c2, (0, 0), 0) == True

    # Case 2: No overlap (far away)
    assert check_overlap(c1, (0, 0), 0, c2, (20, 20), 0) == False

    # Case 3: Partial overlap
    # C1 at 0,0, C2 at 8,0 (width 10, so edges are at +/-5)
    # C1 x-range: [-5, 5]
    # C2 x-range: [3, 13] (8-5, 8+5)
    # Overlap interval [3, 5] -> YES
    assert check_overlap(c1, (0, 0), 0, c2, (8, 0), 0) == True

    # Case 4: Touching (should not be overlap)
    # C2 at 10,0 -> Edge at 5 vs Edge at 5
    # check_overlap returns False for touches by default in implementation
    assert check_overlap(c1, (0, 0), 0, c2, (10, 0), 0) == False


def test_courtyard_rotation():
    # Rectangle 10x2
    points = [(-5, -1), (5, -1), (5, 1), (-5, 1)]
    c = Courtyard("R1", points)

    # At 0 rotation: Width 10, Height 2
    # At 90 rotation: Width 2, Height 10

    # Check bounds of rotated polygon
    poly_0 = c.get_global_polygon(0, 0, 0)
    b0 = poly_0.bounds  # minx, miny, maxx, maxy
    assert b0[2] - b0[0] == 10.0
    assert b0[3] - b0[1] == 2.0

    poly_90 = c.get_global_polygon(0, 0, 1)
    b90 = poly_90.bounds
    assert abs((b90[2] - b90[0]) - 2.0) < 1e-6
    assert abs((b90[3] - b90[1]) - 10.0) < 1e-6


# =============================================================================
# DRC-FIX-4: Board boundary clamping tests
# =============================================================================

from temper_placer.deterministic.stages.courtyard_check import CourtyardCheckStage
from temper_placer.deterministic.state import BoardState
from temper_placer.core.board import Board


class TestBoardBoundaryClamping:
    """Tests for DRC-FIX-4: Board boundary clamping in CourtyardCheckStage."""

    @pytest.fixture
    def small_courtyards(self):
        """Create small 2x2 courtyards for testing."""
        points = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        return {
            "C1": Courtyard("C1", points),
            "C2": Courtyard("C2", points),
        }

    @pytest.fixture
    def stage_100x150(self, small_courtyards):
        """Create a CourtyardCheckStage with 100x150mm board."""
        return CourtyardCheckStage(
            courtyards=small_courtyards,
            board_width=100.0,
            board_height=150.0,
            margin=5.0,
        )

    def test_clamp_position_within_bounds(self, stage_100x150):
        """Position within bounds should not be modified."""
        pos = (50.0, 75.0)
        clamped = stage_100x150._clamp_position(pos)
        assert clamped == pos

    def test_clamp_position_left_edge(self, stage_100x150):
        """Position past left edge should be clamped to margin."""
        pos = (-10.0, 75.0)
        clamped = stage_100x150._clamp_position(pos)
        assert clamped == (5.0, 75.0)  # margin = 5.0

    def test_clamp_position_right_edge(self, stage_100x150):
        """Position past right edge should be clamped to board_width - margin."""
        pos = (110.0, 75.0)
        clamped = stage_100x150._clamp_position(pos)
        assert clamped == (95.0, 75.0)  # 100 - 5 = 95

    def test_clamp_position_top_edge(self, stage_100x150):
        """Position past top edge should be clamped to margin."""
        pos = (50.0, -5.0)
        clamped = stage_100x150._clamp_position(pos)
        assert clamped == (50.0, 5.0)

    def test_clamp_position_bottom_edge(self, stage_100x150):
        """Position past bottom edge should be clamped to board_height - margin."""
        pos = (50.0, 200.0)
        clamped = stage_100x150._clamp_position(pos)
        assert clamped == (50.0, 145.0)  # 150 - 5 = 145

    def test_clamp_position_corner(self, stage_100x150):
        """Position past corner should be clamped on both axes."""
        pos = (200.0, 300.0)
        clamped = stage_100x150._clamp_position(pos)
        assert clamped == (95.0, 145.0)

    def test_clamp_position_negative_corner(self, stage_100x150):
        """Position past negative corner should be clamped on both axes."""
        pos = (-100.0, -100.0)
        clamped = stage_100x150._clamp_position(pos)
        assert clamped == (5.0, 5.0)

    def test_nudge_clamps_to_bounds(self, small_courtyards):
        """After nudging overlapping components near edge, positions stay in bounds."""
        # Create stage with small board to force edge clamping
        stage = CourtyardCheckStage(
            courtyards=small_courtyards,
            board_width=20.0,
            board_height=20.0,
            margin=2.0,
            max_iterations=100,
            nudge_step=1.0,  # Aggressive nudging
        )

        # Place two overlapping components near the right edge
        # They should be nudged apart but not pushed outside the board
        board = Board(width=20.0, height=20.0, zones=[])
        initial_state = BoardState(
            board=board,
            netlist=None,
            placements=(("C1", (16.0, 10.0)), ("C2", (16.0, 10.0))),  # Overlapping at edge
        )

        result_state = stage.run(initial_state)
        placements = dict(result_state.placements)

        # Check that both components are within bounds
        for ref, (x, y) in placements.items():
            assert 2.0 <= x <= 18.0, f"{ref} x={x} outside bounds [2, 18]"
            assert 2.0 <= y <= 18.0, f"{ref} y={y} outside bounds [2, 18]"

    def test_overlapping_at_edge_resolves_inward(self, small_courtyards):
        """Overlapping components at edge should be pushed inward, not out of bounds."""
        stage = CourtyardCheckStage(
            courtyards=small_courtyards,
            board_width=30.0,
            board_height=30.0,
            margin=3.0,
            max_iterations=500,
            nudge_step=0.5,
        )

        # Place overlapping components at the corner
        board = Board(width=30.0, height=30.0, zones=[])
        initial_state = BoardState(
            board=board,
            netlist=None,
            placements=(("C1", (25.0, 25.0)), ("C2", (25.0, 25.0))),
        )

        result_state = stage.run(initial_state)
        placements = dict(result_state.placements)

        # Both should be within valid bounds [3, 27]
        for ref, (x, y) in placements.items():
            assert 3.0 <= x <= 27.0, f"{ref} x={x} outside bounds [3, 27]"
            assert 3.0 <= y <= 27.0, f"{ref} y={y} outside bounds [3, 27]"

        # They should also be separated (not overlapping)
        p1 = placements["C1"]
        p2 = placements["C2"]
        dist = ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5
        assert dist > 1.0, f"Components still too close: dist={dist}"

    def test_custom_margin_respected(self, small_courtyards):
        """Custom margin value should be respected in clamping."""
        stage = CourtyardCheckStage(
            courtyards=small_courtyards,
            board_width=100.0,
            board_height=100.0,
            margin=10.0,  # Larger margin
        )

        # Position at margin edge should not change
        pos_at_margin = (10.0, 50.0)
        assert stage._clamp_position(pos_at_margin) == pos_at_margin

        # Position inside margin should be clamped
        pos_inside_margin = (5.0, 50.0)
        assert stage._clamp_position(pos_inside_margin) == (10.0, 50.0)

        # Position at far edge
        pos_at_far_edge = (90.0, 90.0)
        assert stage._clamp_position(pos_at_far_edge) == pos_at_far_edge

        pos_past_far_edge = (95.0, 95.0)
        assert stage._clamp_position(pos_past_far_edge) == (90.0, 90.0)
