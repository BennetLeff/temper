"""
Tests for coordinate transformation and validation.

These tests verify that:
1. Board origin transformations are correct
2. Component rotation transforms are applied correctly
3. Trace coordinates are transformed properly
4. Round-trip parsing -> visualization maintains coordinate accuracy
"""

import math
from pathlib import Path

import pytest

from temper_placer.visualization.model import (
    BoardView,
    ComponentView,
    PadView,
    Point,
    TraceView,
)
from temper_placer.visualization.validation import (
    CoordinateDiscrepancy,
    ValidationResult,
    check_components_in_bounds,
    check_trace_connectivity,
    compute_coordinate_statistics,
    export_coordinates_csv,
    validate_coordinates,
)


class TestBoardOriginTransform:
    """Test coordinate transformation with board origin offset."""

    def test_basic_origin_transform(self):
        """Component at (82, 74.5) with origin (77.5, 71) -> relative (4.5, 3.5)."""
        # Create a board view with relative coordinates
        board = BoardView(
            width=20.0,
            height=15.0,
            components=(
                ComponentView(
                    ref="D1",
                    position=Point(4.5, 3.5),  # Board-relative
                    rotation=0.0,
                    width=3.36,
                    height=1.9,
                ),
            ),
        )

        # Original KiCad coordinates
        original_components = [("D1", 82.0, 74.5, 0.0)]
        origin = (77.5, 71.0)

        result = validate_coordinates(
            board,
            original_components,
            origin=origin,
            tolerance=0.01,
        )

        assert result.is_valid
        assert result.components_checked == 1
        assert len(result.discrepancies) == 0

    def test_multiple_components(self):
        """Test multiple components with different positions."""
        board = BoardView(
            width=20.0,
            height=15.0,
            components=(
                ComponentView(
                    ref="D1",
                    position=Point(4.5, 3.5),
                    rotation=0.0,
                    width=3.36,
                    height=1.9,
                ),
                ComponentView(
                    ref="R1",
                    position=Point(10.9, 3.5),
                    rotation=180.0,
                    width=3.36,
                    height=1.9,
                ),
                ComponentView(
                    ref="J1",
                    position=Point(10.5, 10.5),
                    rotation=270.0,
                    width=3.54,
                    height=6.09,
                ),
            ),
        )

        original_components = [
            ("D1", 82.0, 74.5, 0.0),
            ("R1", 88.4, 74.5, 180.0),
            ("J1", 88.0, 81.5, 270.0),
        ]
        origin = (77.5, 71.0)

        result = validate_coordinates(
            board,
            original_components,
            origin=origin,
            tolerance=0.1,  # Allow some tolerance for floating point
        )

        assert result.is_valid
        assert result.components_checked == 3

    def test_detects_wrong_x_coordinate(self):
        """Test that wrong X coordinate is detected."""
        board = BoardView(
            width=20.0,
            height=15.0,
            components=(
                ComponentView(
                    ref="D1",
                    position=Point(5.0, 3.5),  # Wrong - should be 4.5
                    rotation=0.0,
                    width=3.36,
                    height=1.9,
                ),
            ),
        )

        original_components = [("D1", 82.0, 74.5, 0.0)]
        origin = (77.5, 71.0)

        result = validate_coordinates(
            board,
            original_components,
            origin=origin,
            tolerance=0.01,
        )

        assert not result.is_valid
        assert len(result.discrepancies) >= 1
        x_disc = next(d for d in result.discrepancies if d.field == "x")
        assert abs(x_disc.difference - 0.5) < 0.01

    def test_detects_wrong_y_coordinate(self):
        """Test that wrong Y coordinate is detected."""
        board = BoardView(
            width=20.0,
            height=15.0,
            components=(
                ComponentView(
                    ref="D1",
                    position=Point(4.5, 4.0),  # Wrong - should be 3.5
                    rotation=0.0,
                    width=3.36,
                    height=1.9,
                ),
            ),
        )

        original_components = [("D1", 82.0, 74.5, 0.0)]
        origin = (77.5, 71.0)

        result = validate_coordinates(
            board,
            original_components,
            origin=origin,
            tolerance=0.01,
        )

        assert not result.is_valid
        y_disc = next(d for d in result.discrepancies if d.field == "y")
        assert abs(y_disc.difference - 0.5) < 0.01

    def test_zero_origin(self):
        """Test with zero origin (no offset)."""
        board = BoardView(
            width=100.0,
            height=100.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(50.0, 50.0),
                    rotation=0.0,
                    width=10.0,
                    height=10.0,
                ),
            ),
        )

        original_components = [("U1", 50.0, 50.0, 0.0)]
        origin = (0.0, 0.0)

        result = validate_coordinates(
            board,
            original_components,
            origin=origin,
            tolerance=0.01,
        )

        assert result.is_valid


class TestRotationTransform:
    """Test rotation handling in validation."""

    def test_rotation_0_degrees(self):
        """Test component with 0° rotation."""
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

        original_components = [("U1", 10.0, 10.0, 0.0)]

        result = validate_coordinates(board, original_components, tolerance=0.01)
        assert result.is_valid

    def test_rotation_90_degrees(self):
        """Test component with 90° rotation."""
        board = BoardView(
            width=20.0,
            height=20.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(10.0, 10.0),
                    rotation=90.0,
                    width=5.0,
                    height=5.0,
                ),
            ),
        )

        original_components = [("U1", 10.0, 10.0, 90.0)]

        result = validate_coordinates(board, original_components, tolerance=0.01)
        assert result.is_valid

    def test_rotation_180_degrees(self):
        """Test component with 180° rotation."""
        board = BoardView(
            width=20.0,
            height=20.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(10.0, 10.0),
                    rotation=180.0,
                    width=5.0,
                    height=5.0,
                ),
            ),
        )

        original_components = [("U1", 10.0, 10.0, 180.0)]

        result = validate_coordinates(board, original_components, tolerance=0.01)
        assert result.is_valid

    def test_rotation_270_degrees(self):
        """Test component with 270° rotation."""
        board = BoardView(
            width=20.0,
            height=20.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(10.0, 10.0),
                    rotation=270.0,
                    width=5.0,
                    height=5.0,
                ),
            ),
        )

        original_components = [("U1", 10.0, 10.0, 270.0)]

        result = validate_coordinates(board, original_components, tolerance=0.01)
        assert result.is_valid

    def test_rotation_mismatch_detected(self):
        """Test that rotation mismatch is detected."""
        board = BoardView(
            width=20.0,
            height=20.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(10.0, 10.0),
                    rotation=90.0,  # Wrong - should be 0
                    width=5.0,
                    height=5.0,
                ),
            ),
        )

        original_components = [("U1", 10.0, 10.0, 0.0)]

        result = validate_coordinates(board, original_components, tolerance=0.01)
        assert not result.is_valid
        rot_disc = next(d for d in result.discrepancies if d.field == "rotation")
        assert abs(rot_disc.difference - 90.0) < 0.01

    def test_rotation_360_equivalent_to_0(self):
        """Test that 360° is treated as equivalent to 0°."""
        board = BoardView(
            width=20.0,
            height=20.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(10.0, 10.0),
                    rotation=360.0,
                    width=5.0,
                    height=5.0,
                ),
            ),
        )

        original_components = [("U1", 10.0, 10.0, 0.0)]

        result = validate_coordinates(board, original_components, tolerance=0.01)
        assert result.is_valid


class TestTraceTransform:
    """Test trace coordinate transformation."""

    def test_trace_endpoints_transform(self):
        """Test that trace endpoints are correctly transformed."""
        board = BoardView(
            width=20.0,
            height=15.0,
            traces=(
                TraceView(
                    start=Point(5.4, 3.5),  # Relative to origin
                    end=Point(10.0, 3.5),
                    width=0.2,
                    layer="F.Cu",
                ),
            ),
        )

        # Original absolute coordinates
        original_traces = [(82.9, 74.5, 87.5, 74.5)]  # (x1, y1, x2, y2)
        origin = (77.5, 71.0)

        result = validate_coordinates(
            board,
            original_components=[],
            original_traces=original_traces,
            origin=origin,
            tolerance=0.1,
        )

        assert result.is_valid
        assert result.traces_checked == 1


class TestExportCoordinatesCsv:
    """Test CSV export functionality."""

    def test_export_components(self):
        """Test that components are exported correctly."""
        board = BoardView(
            width=20.0,
            height=15.0,
            components=(
                ComponentView(
                    ref="D1",
                    position=Point(4.5, 3.5),
                    rotation=0.0,
                    width=3.36,
                    height=1.9,
                ),
            ),
        )

        csv_content = export_coordinates_csv(board, origin=(77.5, 71.0))

        assert "component,D1" in csv_content
        assert "4.5000" in csv_content  # x_rel
        assert "82.0000" in csv_content  # x_abs

    def test_export_traces(self):
        """Test that traces are exported correctly."""
        board = BoardView(
            width=20.0,
            height=15.0,
            traces=(
                TraceView(
                    start=Point(5.0, 3.0),
                    end=Point(10.0, 3.0),
                    width=0.25,
                    layer="F.Cu",
                    net="GND",
                ),
            ),
        )

        csv_content = export_coordinates_csv(board, origin=(0.0, 0.0))

        assert "trace_start,trace_0" in csv_content
        assert "trace_end,trace_0" in csv_content
        assert "F.Cu" in csv_content
        assert "GND" in csv_content

    def test_export_pads(self):
        """Test that pads are exported correctly."""
        board = BoardView(
            width=20.0,
            height=15.0,
            pads=(
                PadView(
                    position=Point(5.0, 3.0),
                    size=(1.0, 1.0),
                    shape="rect",
                    layer="F.Cu",
                    number="1",
                    net="VCC",
                    component_ref="U1",
                ),
            ),
        )

        csv_content = export_coordinates_csv(board, origin=(0.0, 0.0))

        assert "pad,U1-1" in csv_content
        assert "VCC" in csv_content

    def test_export_to_file(self, tmp_path):
        """Test exporting to a file."""
        board = BoardView(
            width=20.0,
            height=15.0,
            components=(
                ComponentView(
                    ref="R1",
                    position=Point(5.0, 5.0),
                    rotation=0.0,
                    width=2.0,
                    height=1.0,
                ),
            ),
        )

        output_file = tmp_path / "coords.csv"
        csv_content = export_coordinates_csv(board, output_path=output_file)

        assert output_file.exists()
        # Normalize line endings for comparison
        file_content = output_file.read_text().replace("\r\n", "\n")
        normalized_csv = csv_content.replace("\r\n", "\n")
        assert file_content == normalized_csv


class TestCheckComponentsInBounds:
    """Test bounds checking functionality."""

    def test_component_inside_bounds(self):
        """Test that component inside bounds passes."""
        board = BoardView(
            width=20.0,
            height=15.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(10.0, 7.5),  # Center of board
                    rotation=0.0,
                    width=4.0,
                    height=4.0,
                ),
            ),
        )

        out_of_bounds = check_components_in_bounds(board)
        assert len(out_of_bounds) == 0

    def test_component_outside_left(self):
        """Test that component outside left boundary is detected."""
        board = BoardView(
            width=20.0,
            height=15.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(1.0, 7.5),  # Too close to left edge
                    rotation=0.0,
                    width=4.0,  # Extends past x=0
                    height=4.0,
                ),
            ),
        )

        out_of_bounds = check_components_in_bounds(board)
        assert "U1" in out_of_bounds

    def test_component_outside_right(self):
        """Test that component outside right boundary is detected."""
        board = BoardView(
            width=20.0,
            height=15.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(19.0, 7.5),  # Too close to right edge
                    rotation=0.0,
                    width=4.0,  # Extends past x=20
                    height=4.0,
                ),
            ),
        )

        out_of_bounds = check_components_in_bounds(board)
        assert "U1" in out_of_bounds

    def test_rotated_component_bounds(self):
        """Test bounds checking with rotated component."""
        # A 6x2 component at 90° becomes 2x6
        board = BoardView(
            width=20.0,
            height=15.0,
            components=(
                ComponentView(
                    ref="U1",
                    position=Point(10.0, 2.0),  # Center near bottom
                    rotation=90.0,
                    width=6.0,  # After rotation: height becomes 6
                    height=2.0,
                ),
            ),
        )

        out_of_bounds = check_components_in_bounds(board)
        # After 90° rotation, the 6-unit dimension is now vertical
        # With center at y=2, it extends from y=-1 to y=5, so y=-1 is out of bounds
        assert "U1" in out_of_bounds


class TestCheckTraceConnectivity:
    """Test trace connectivity checking."""

    def test_connected_trace(self):
        """Test that connected trace passes."""
        board = BoardView(
            width=20.0,
            height=15.0,
            traces=(
                TraceView(
                    start=Point(5.0, 5.0),
                    end=Point(10.0, 5.0),
                    width=0.25,
                ),
            ),
            pads=(
                PadView(
                    position=Point(5.0, 5.0),  # At trace start
                    size=(1.0, 1.0),
                    shape="rect",
                ),
                PadView(
                    position=Point(10.0, 5.0),  # At trace end
                    size=(1.0, 1.0),
                    shape="rect",
                ),
            ),
        )

        disconnected = check_trace_connectivity(board, tolerance=0.1)
        assert len(disconnected) == 0

    def test_disconnected_trace(self):
        """Test that disconnected trace is detected."""
        board = BoardView(
            width=20.0,
            height=15.0,
            traces=(
                TraceView(
                    start=Point(5.0, 5.0),
                    end=Point(10.0, 5.0),
                    width=0.25,
                ),
            ),
            pads=(
                PadView(
                    position=Point(0.0, 0.0),  # Far from trace
                    size=(1.0, 1.0),
                    shape="rect",
                ),
            ),
        )

        disconnected = check_trace_connectivity(board, tolerance=0.5)
        assert len(disconnected) >= 1


class TestComputeCoordinateStatistics:
    """Test coordinate statistics computation."""

    def test_basic_statistics(self):
        """Test that statistics are computed correctly."""
        board = BoardView(
            width=20.0,
            height=15.0,
            components=(
                ComponentView(
                    ref="C1",
                    position=Point(5.0, 5.0),
                    rotation=0.0,
                    width=2.0,
                    height=2.0,
                ),
                ComponentView(
                    ref="C2",
                    position=Point(15.0, 10.0),
                    rotation=0.0,
                    width=2.0,
                    height=2.0,
                ),
            ),
        )

        stats = compute_coordinate_statistics(board)

        assert stats["board"]["width"] == 20.0
        assert stats["board"]["height"] == 15.0
        assert stats["components"]["count"] == 2
        assert stats["components"]["x_min"] == 5.0
        assert stats["components"]["x_max"] == 15.0
        assert stats["components"]["x_mean"] == 10.0
        assert stats["components"]["y_min"] == 5.0
        assert stats["components"]["y_max"] == 10.0
        assert stats["components"]["y_mean"] == 7.5

    def test_empty_board_statistics(self):
        """Test statistics for empty board."""
        board = BoardView(width=20.0, height=15.0)

        stats = compute_coordinate_statistics(board)

        assert stats["board"]["width"] == 20.0
        assert stats["components"] == {}
        assert stats["traces"] == {}
        assert stats["pads"] == {}


class TestValidationResult:
    """Test ValidationResult string representation."""

    def test_valid_result_str(self):
        """Test string representation of valid result."""
        result = ValidationResult(
            is_valid=True,
            discrepancies=[],
            tolerance=0.01,
            components_checked=5,
            traces_checked=10,
            pads_checked=15,
        )

        result_str = str(result)
        assert "PASSED" in result_str
        assert "5 components" in result_str
        assert "10 traces" in result_str
        assert "15 pads" in result_str

    def test_invalid_result_str(self):
        """Test string representation of invalid result."""
        result = ValidationResult(
            is_valid=False,
            discrepancies=[
                CoordinateDiscrepancy(
                    element_type="component",
                    ref="U1",
                    field="x",
                    expected=10.0,
                    actual=11.0,
                    difference=1.0,
                ),
            ],
            tolerance=0.01,
            components_checked=5,
            traces_checked=0,
            pads_checked=0,
        )

        result_str = str(result)
        assert "FAILED" in result_str
        assert "1 discrepancies" in result_str
        assert "U1" in result_str
