"""
Tests for rendered output validation.

These tests verify that:
1. All rendered components are within board bounds
2. Trace endpoints are near pad positions (connectivity)
3. Roundtrip parsing maintains coordinate integrity
"""


import pytest

from temper_placer.visualization.model import (
    BoardView,
    ComponentView,
    PadView,
    Point,
    TraceView,
)
from temper_placer.visualization.validation import (
    check_components_in_bounds,
    check_trace_connectivity,
    compute_coordinate_statistics,
)


class TestComponentsInBounds:
    """Test that all components render inside board rectangle."""

    def test_all_components_inside(self):
        """All components should be inside board when properly placed."""
        board = BoardView(
            width=100.0,
            height=100.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(25.0, 25.0),
                    rotation=0.0,
                    width=10.0,
                    height=10.0,
                ),
                ComponentView(
                    ref="U2",
                    position=Point(75.0, 75.0),
                    rotation=0.0,
                    width=10.0,
                    height=10.0,
                ),
                ComponentView(
                    ref="R1",
                    position=Point(50.0, 50.0),
                    rotation=45.0,  # Rotated
                    width=4.0,
                    height=2.0,
                ),
            ),
        )

        out_of_bounds = check_components_in_bounds(board)
        assert len(out_of_bounds) == 0

    def test_component_at_edge_inside(self):
        """Component exactly at edge should be inside."""
        board = BoardView(
            width=20.0,
            height=20.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(5.0, 10.0),  # 5 units from left, centered vertically
                    rotation=0.0,
                    width=10.0,  # Extends from x=0 to x=10
                    height=10.0,
                ),
            ),
        )

        out_of_bounds = check_components_in_bounds(board)
        assert len(out_of_bounds) == 0

    def test_component_partially_outside(self):
        """Component partially outside should be detected."""
        board = BoardView(
            width=20.0,
            height=20.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(2.0, 10.0),  # Too close to left edge
                    rotation=0.0,
                    width=10.0,  # Would extend from x=-3 to x=7
                    height=10.0,
                ),
            ),
        )

        out_of_bounds = check_components_in_bounds(board)
        assert "U1" in out_of_bounds

    def test_multiple_out_of_bounds(self):
        """Multiple components out of bounds should all be detected."""
        board = BoardView(
            width=20.0,
            height=20.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(-5.0, 10.0),  # Completely outside left
                    rotation=0.0,
                    width=5.0,
                    height=5.0,
                ),
                ComponentView(
                    ref="U2",
                    position=Point(10.0, 10.0),  # Inside
                    rotation=0.0,
                    width=5.0,
                    height=5.0,
                ),
                ComponentView(
                    ref="U3",
                    position=Point(25.0, 10.0),  # Outside right
                    rotation=0.0,
                    width=5.0,
                    height=5.0,
                ),
            ),
        )

        out_of_bounds = check_components_in_bounds(board)
        assert "U1" in out_of_bounds
        assert "U2" not in out_of_bounds
        assert "U3" in out_of_bounds

    def test_rotated_component_corners_checked(self):
        """Rotated component corners should be checked properly."""
        # A 10x2 component rotated 45° has diagonal ~10.2 units
        # Center at (5, 5) with this diagonal, corners could reach beyond board
        board = BoardView(
            width=15.0,
            height=15.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(2.0, 7.5),  # Near left edge
                    rotation=45.0,
                    width=10.0,  # Long component
                    height=2.0,
                ),
            ),
        )

        out_of_bounds = check_components_in_bounds(board)
        # After 45° rotation, corners extend beyond left boundary
        assert "U1" in out_of_bounds


class TestTraceConnectivity:
    """Test that trace endpoints are near pad positions."""

    def test_all_traces_connected(self):
        """All trace endpoints should be near pads."""
        board = BoardView(
            width=50.0,
            height=50.0,
            traces=(
                TraceView(
                    start=Point(10.0, 10.0),
                    end=Point(20.0, 10.0),
                    width=0.25,
                ),
                TraceView(
                    start=Point(20.0, 10.0),
                    end=Point(20.0, 20.0),
                    width=0.25,
                ),
            ),
            pads=(
                PadView(
                    position=Point(10.0, 10.0),
                    size=(1.0, 1.0),
                    shape="rect",
                ),
                PadView(
                    position=Point(20.0, 10.0),
                    size=(1.0, 1.0),
                    shape="rect",
                ),
                PadView(
                    position=Point(20.0, 20.0),
                    size=(1.0, 1.0),
                    shape="rect",
                ),
            ),
        )

        disconnected = check_trace_connectivity(board, tolerance=0.1)
        assert len(disconnected) == 0

    def test_trace_start_disconnected(self):
        """Trace with disconnected start should be detected."""
        board = BoardView(
            width=50.0,
            height=50.0,
            traces=(
                TraceView(
                    start=Point(5.0, 5.0),  # No pad here
                    end=Point(20.0, 10.0),
                    width=0.25,
                ),
            ),
            pads=(
                PadView(
                    position=Point(20.0, 10.0),  # Only at end
                    size=(1.0, 1.0),
                    shape="rect",
                ),
            ),
        )

        disconnected = check_trace_connectivity(board, tolerance=0.5)
        assert len(disconnected) >= 1
        assert any(d[1] == "start" for d in disconnected)

    def test_trace_end_disconnected(self):
        """Trace with disconnected end should be detected."""
        board = BoardView(
            width=50.0,
            height=50.0,
            traces=(
                TraceView(
                    start=Point(10.0, 10.0),
                    end=Point(30.0, 30.0),  # No pad here
                    width=0.25,
                ),
            ),
            pads=(
                PadView(
                    position=Point(10.0, 10.0),  # Only at start
                    size=(1.0, 1.0),
                    shape="rect",
                ),
            ),
        )

        disconnected = check_trace_connectivity(board, tolerance=0.5)
        assert len(disconnected) >= 1
        assert any(d[1] == "end" for d in disconnected)

    def test_tolerance_respected(self):
        """Traces within tolerance should be considered connected."""
        board = BoardView(
            width=50.0,
            height=50.0,
            traces=(
                TraceView(
                    start=Point(10.0, 10.0),
                    end=Point(20.0, 10.3),  # 0.3mm from pad
                    width=0.25,
                ),
            ),
            pads=(
                PadView(
                    position=Point(10.0, 10.0),
                    size=(1.0, 1.0),
                    shape="rect",
                ),
                PadView(
                    position=Point(20.0, 10.0),
                    size=(1.0, 1.0),
                    shape="rect",
                ),
            ),
        )

        # With tight tolerance, should be disconnected
        disconnected_tight = check_trace_connectivity(board, tolerance=0.1)
        assert len(disconnected_tight) >= 1

        # With loose tolerance, should be connected
        disconnected_loose = check_trace_connectivity(board, tolerance=0.5)
        assert len(disconnected_loose) == 0

    def test_no_pads_returns_empty(self):
        """Board with no pads should return empty list."""
        board = BoardView(
            width=50.0,
            height=50.0,
            traces=(
                TraceView(
                    start=Point(10.0, 10.0),
                    end=Point(20.0, 10.0),
                    width=0.25,
                ),
            ),
        )

        disconnected = check_trace_connectivity(board, tolerance=0.5)
        assert len(disconnected) == 0

    def test_no_traces_returns_empty(self):
        """Board with no traces should return empty list."""
        board = BoardView(
            width=50.0,
            height=50.0,
            pads=(
                PadView(
                    position=Point(10.0, 10.0),
                    size=(1.0, 1.0),
                    shape="rect",
                ),
            ),
        )

        disconnected = check_trace_connectivity(board, tolerance=0.5)
        assert len(disconnected) == 0


class TestRoundtripIntegrity:
    """Test coordinate integrity through parsing and visualization."""

    @pytest.fixture
    def sample_board_view(self):
        """Create a sample board view for testing."""
        return BoardView(
            width=50.0,
            height=40.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(10.0, 10.0),
                    rotation=0.0,
                    width=8.0,
                    height=8.0,
                ),
                ComponentView(
                    ref="R1",
                    position=Point(25.0, 10.0),
                    rotation=90.0,
                    width=3.0,
                    height=1.5,
                ),
                ComponentView(
                    ref="C1",
                    position=Point(40.0, 30.0),
                    rotation=180.0,
                    width=4.0,
                    height=2.0,
                ),
            ),
            traces=(
                TraceView(
                    start=Point(14.0, 10.0),
                    end=Point(24.0, 10.0),
                    width=0.25,
                    layer="F.Cu",
                ),
                TraceView(
                    start=Point(26.0, 10.0),
                    end=Point(38.0, 30.0),
                    width=0.25,
                    layer="F.Cu",
                ),
            ),
            pads=(
                PadView(
                    position=Point(14.0, 10.0),
                    size=(1.0, 1.0),
                    shape="rect",
                    component_ref="U1",
                    number="1",
                ),
                PadView(
                    position=Point(24.0, 10.0),
                    size=(0.8, 0.8),
                    shape="circle",
                    component_ref="R1",
                    number="1",
                ),
                PadView(
                    position=Point(26.0, 10.0),
                    size=(0.8, 0.8),
                    shape="circle",
                    component_ref="R1",
                    number="2",
                ),
                PadView(
                    position=Point(38.0, 30.0),
                    size=(1.2, 1.2),
                    shape="rect",
                    component_ref="C1",
                    number="1",
                ),
            ),
        )

    def test_statistics_match_content(self, sample_board_view):
        """Statistics should accurately reflect board content."""
        stats = compute_coordinate_statistics(sample_board_view)

        # Board dimensions
        assert stats["board"]["width"] == 50.0
        assert stats["board"]["height"] == 40.0

        # Component stats
        assert stats["components"]["count"] == 3
        comp_x = [10.0, 25.0, 40.0]
        assert stats["components"]["x_min"] == min(comp_x)
        assert stats["components"]["x_max"] == max(comp_x)

        # Trace stats
        assert stats["traces"]["count"] == 2

        # Pad stats
        assert stats["pads"]["count"] == 4

    def test_all_elements_in_bounds(self, sample_board_view):
        """All elements should be within board bounds."""
        out_of_bounds = check_components_in_bounds(sample_board_view)
        assert len(out_of_bounds) == 0

    def test_traces_connected_to_pads(self, sample_board_view):
        """All traces should connect to pads."""
        disconnected = check_trace_connectivity(sample_board_view, tolerance=0.5)
        assert len(disconnected) == 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_board(self):
        """Empty board should not cause errors."""
        board = BoardView(width=100.0, height=100.0)

        out_of_bounds = check_components_in_bounds(board)
        assert len(out_of_bounds) == 0

        disconnected = check_trace_connectivity(board, tolerance=0.5)
        assert len(disconnected) == 0

        stats = compute_coordinate_statistics(board)
        assert stats["components"] == {}
        assert stats["traces"] == {}
        assert stats["pads"] == {}

    def test_single_component(self):
        """Single component should work correctly."""
        board = BoardView(
            width=20.0,
            height=20.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(10.0, 10.0),
                    rotation=0.0,
                    width=5.0,
                    height=5.0,
                ),
            ),
        )

        out_of_bounds = check_components_in_bounds(board)
        assert len(out_of_bounds) == 0

        stats = compute_coordinate_statistics(board)
        assert stats["components"]["count"] == 1
        assert stats["components"]["x_min"] == stats["components"]["x_max"] == 10.0

    def test_component_at_origin(self):
        """Component at board origin should be detected if outside."""
        board = BoardView(
            width=20.0,
            height=20.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(0.0, 0.0),  # At origin
                    rotation=0.0,
                    width=4.0,  # Extends into negative x and y
                    height=4.0,
                ),
            ),
        )

        out_of_bounds = check_components_in_bounds(board)
        assert "U1" in out_of_bounds

    def test_very_small_board(self):
        """Very small board should work correctly."""
        board = BoardView(
            width=1.0,
            height=1.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(0.5, 0.5),
                    rotation=0.0,
                    width=0.8,  # Almost fills board
                    height=0.8,
                ),
            ),
        )

        out_of_bounds = check_components_in_bounds(board)
        assert len(out_of_bounds) == 0

    def test_large_board(self):
        """Large board with many components should work correctly."""
        components = tuple(
            ComponentView(
                ref=f"R{i}",
                position=Point(10.0 + i * 10.0, 50.0),  # All at y=50, spread along x
                rotation=float(i * 90 % 360),
                width=2.0,
                height=1.0,
            )
            for i in range(100)
        )

        board = BoardView(
            width=1100.0,  # Wide enough for all components
            height=100.0,
            components=components,
        )

        out_of_bounds = check_components_in_bounds(board)
        assert len(out_of_bounds) == 0

        stats = compute_coordinate_statistics(board)
        assert stats["components"]["count"] == 100
