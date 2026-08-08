"""
Coverage-paydown tests for visualization module functions.

Covers allowlisted public functions from:
- validation.py (pure computation, no Plotly needed)
- status.py (pure functions, no Plotly needed)
"""

import json

import pytest

from temper_placer.visualization.model import (
    BoardView,
    ComponentStatus,
    ComponentView,
    ConstraintStatus,
    PadView,
    Point,
    TraceView,
    Violation,
    ViolationType,
)
from temper_placer.visualization.status import (
    constraint_status_to_json,
    get_affected_component_refs,
    get_severity_color,
    get_severity_level,
    get_violations_by_component,
    get_violations_by_type,
)
from temper_placer.visualization.validation import (
    ValidationResult,
    check_components_in_bounds,
    check_trace_connectivity,
    compute_coordinate_statistics,
    export_coordinates_csv,
    validate_coordinates,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_board() -> BoardView:
    """A simple board with two components."""
    comp1 = ComponentView(
        ref="U1", position=Point(50, 40), rotation=0,
        width=10, height=8, status=ComponentStatus.OK,
    )
    comp2 = ComponentView(
        ref="R1", position=Point(80, 60), rotation=90,
        width=2, height=1, status=ComponentStatus.OK,
    )
    return BoardView(width=100, height=80, components=(comp1, comp2))


@pytest.fixture
def board_with_traces() -> BoardView:
    """Board with components, traces, and pads at BOTH trace endpoints."""
    comp = ComponentView(
        ref="U1", position=Point(50, 40), rotation=0,
        width=10, height=8,
    )
    trace = TraceView(
        start=Point(50, 40), end=Point(80, 60),
        width=0.25, layer="F.Cu", net="VCC",
    )
    pad_start = PadView(
        position=Point(50, 40), size=(1.0, 1.0),
        shape="rect", layer="F.Cu", number="1",
        component_ref="U1", net="VCC",
    )
    pad_end = PadView(
        position=Point(80, 60), size=(1.0, 1.0),
        shape="rect", layer="F.Cu", number="2",
        component_ref="U1", net="VCC",
    )
    return BoardView(
        width=100, height=80,
        components=(comp,),
        traces=(trace,),
        pads=(pad_start, pad_end),
    )


@pytest.fixture
def sample_constraint_status() -> ConstraintStatus:
    """A constraint status with violations."""
    v1 = Violation(
        violation_type=ViolationType.OVERLAP,
        severity=0.8,
        component_refs=("U1", "R1"),
        message="Components overlap by 2.3mm",
    )
    v2 = Violation(
        violation_type=ViolationType.BOUNDARY,
        severity=0.4,
        component_refs=("U2",),
        message="Component outside board boundary",
    )
    return ConstraintStatus(
        violations=(v1, v2),
        overlap_count=1,
        boundary_violations=1,
        clearance_violations=0,
        thermal_warnings=0,
        drc_errors=0,
    )


# ---------------------------------------------------------------------------
# validation.py
# ---------------------------------------------------------------------------


class TestValidateCoordinates:
    """Tests for validate_coordinates."""

    def test_passing_validation(self, simple_board):
        """Matching coordinates pass validation."""
        result = validate_coordinates(
            board_view=simple_board,
            original_components=[("U1", 50.0, 40.0, 0.0), ("R1", 80.0, 60.0, 90.0)],
            tolerance=0.01,
        )
        assert result.is_valid
        assert len(result.discrepancies) == 0

    def test_failing_validation(self, simple_board):
        """Mismatched coordinates produce discrepancies."""
        result = validate_coordinates(
            board_view=simple_board,
            original_components=[("U1", 99.0, 99.0, 0.0)],
            tolerance=0.01,
        )
        assert not result.is_valid
        assert len(result.discrepancies) > 0

    def test_missing_component(self, simple_board):
        """Component in original but not in board view."""
        result = validate_coordinates(
            board_view=simple_board,
            original_components=[("MISSING", 10.0, 10.0, 0.0)],
            tolerance=0.01,
        )
        assert not result.is_valid

    def test_with_traces_and_pads(self, board_with_traces):
        """Validation with trace and pad data."""
        result = validate_coordinates(
            board_view=board_with_traces,
            original_components=[("U1", 50.0, 40.0, 0.0)],
            original_traces=[(50.0, 40.0, 80.0, 60.0)],
            original_pads=[("U1-1", 50.0, 40.0), ("U1-2", 80.0, 60.0)],
            tolerance=0.01,
        )
        assert result.is_valid


class TestExportCoordinatesCSV:
    """Tests for export_coordinates_csv."""

    def test_export_components(self, simple_board):
        """CSV export includes components."""
        csv_str = export_coordinates_csv(simple_board)
        assert "component" in csv_str
        assert "U1" in csv_str
        assert "R1" in csv_str

    def test_export_with_traces(self, board_with_traces):
        """CSV export includes traces."""
        csv_str = export_coordinates_csv(board_with_traces)
        assert "trace_0" in csv_str
        assert "VCC" in csv_str
        assert "pad" in csv_str
        assert "U1-1" in csv_str
        assert "U1-2" in csv_str

    def test_export_empty_board(self):
        """CSV export of empty board."""
        board = BoardView(width=100, height=80)
        csv_str = export_coordinates_csv(board)
        assert "type,ref" in csv_str  # Header still emitted


class TestCheckComponentsInBounds:
    """Tests for check_components_in_bounds."""

    def test_all_in_bounds(self, simple_board):
        """Components inside board return empty list."""
        out = check_components_in_bounds(simple_board)
        assert out == []

    def test_component_out_of_bounds(self):
        """Component extending beyond board is flagged."""
        comp = ComponentView(
            ref="BAD", position=Point(-5, 50), rotation=0,
            width=10, height=8,
        )
        board = BoardView(width=100, height=80, components=(comp,))
        out = check_components_in_bounds(board)
        assert "BAD" in out


class TestCheckTraceConnectivity:
    """Tests for check_trace_connectivity."""

    def test_connected_traces(self, board_with_traces):
        """Trace endpoints at pad positions are connected."""
        disconnected = check_trace_connectivity(board_with_traces, tolerance=0.5)
        assert len(disconnected) == 0

    def test_disconnected_trace(self):
        """Trace far from any pad is flagged."""
        trace = TraceView(
            start=Point(0, 0), end=Point(10, 10),
            width=0.25, layer="F.Cu",
        )
        pad = PadView(
            position=Point(50, 50), size=(1.0, 1.0), shape="rect",
        )
        board = BoardView(
            width=100, height=80,
            traces=(trace,), pads=(pad,),
        )
        disconnected = check_trace_connectivity(board, tolerance=1.0)
        assert len(disconnected) > 0

    def test_no_pads(self, simple_board):
        """No pads means no disconnected traces."""
        disconnected = check_trace_connectivity(simple_board)
        assert disconnected == []


class TestComputeCoordinateStatistics:
    """Tests for compute_coordinate_statistics."""

    def test_statistics_with_components(self, simple_board):
        """Statistics computed for components."""
        stats = compute_coordinate_statistics(simple_board)
        assert stats["board"]["width"] == 100
        assert stats["board"]["height"] == 80
        comp_stats = stats["components"]
        assert comp_stats["count"] == 2
        assert comp_stats["x_min"] == 50.0
        assert comp_stats["x_max"] == 80.0

    def test_statistics_empty(self):
        """Empty board returns empty stats."""
        board = BoardView(width=100, height=80)
        stats = compute_coordinate_statistics(board)
        assert stats["board"]["width"] == 100
        assert "count" not in stats["components"]


# ---------------------------------------------------------------------------
# status.py — pure functions (no Plotly)
# ---------------------------------------------------------------------------


class TestSeverityLevels:
    """Tests for get_severity_level and get_severity_color."""

    def test_severity_low(self):
        assert get_severity_level(0.1) == "low"

    def test_severity_medium(self):
        assert get_severity_level(0.3) == "medium"

    def test_severity_high(self):
        assert get_severity_level(0.6) == "high"

    def test_severity_critical(self):
        assert get_severity_level(0.9) == "critical"

    def test_get_severity_color(self):
        color = get_severity_color(0.9)
        assert color.startswith("#")
        assert len(color) == 7


class TestViolationGrouping:
    """Tests for get_violations_by_type and get_violations_by_component."""

    def test_get_violations_by_type(self, sample_constraint_status):
        grouped = get_violations_by_type(sample_constraint_status)
        assert ViolationType.OVERLAP in grouped
        assert ViolationType.BOUNDARY in grouped
        assert len(grouped[ViolationType.OVERLAP]) == 1

    def test_get_violations_by_component(self, sample_constraint_status):
        grouped = get_violations_by_component(sample_constraint_status)
        assert "U1" in grouped
        assert "R1" in grouped
        assert "U2" in grouped

    def test_get_affected_component_refs(self, sample_constraint_status):
        refs = get_affected_component_refs(sample_constraint_status)
        assert "R1" in refs
        assert "U1" in refs
        assert "U2" in refs
        assert refs == sorted(refs)  # Returns sorted list


class TestConstraintStatusToJSON:
    """Tests for constraint_status_to_json."""

    def test_basic_conversion(self, sample_constraint_status):
        json_str = constraint_status_to_json(sample_constraint_status)
        data = json.loads(json_str)
        assert "violations" in data
        assert "summary" in data
        assert "affected_components" in data
        assert "violations_by_type" in data
        assert "R1" in data["affected_components"]
        assert "overlap" in data["violations_by_type"]

    def test_empty_status(self):
        status = ConstraintStatus()
        json_str = constraint_status_to_json(status)
        data = json.loads(json_str)
        assert data["affected_components"] == []
        assert data["violations_by_type"] == {}
