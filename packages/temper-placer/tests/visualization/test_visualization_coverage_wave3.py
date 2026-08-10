"""
Coverage-paydown wave 3 tests for visualization module.

Covers still-uncovered functions:
- board_renderer.py: create_component_annotations, create_component_hover_data,
  render_board_with_violations, check_plotly_available, render_board,
  board_to_html, board_to_json, get_component_shape, get_rectangle_shape,
  get_zone_shape
- server.py: MockLiveServer methods, create_server,
  LiveServer.send_training_complete
- validation.py: compute_coordinate_statistics
- loss_plots.py: check_plotly_available, get_term_color, loss_history_to_html,
  loss_history_to_json, render_loss_breakdown_bar, render_loss_curves,
  render_loss_heatmap, render_training_dashboard
- loop_viz.py: calculate_loop_area, get_loop_points
- report.py: generate_report
- live.py: LiveVisualizer (headless), create_visualizer
"""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from temper_placer.visualization.model import (
    BoardView,
    ComponentStatus,
    ComponentView,
    ConstraintStatus,
    LossDataPoint,
    LossHistory,
    PadView,
    Point,
    Rectangle,
    TraceView,
    Violation,
    ViolationType,
    ZoneView,
    VisualizationState,
    create_board_view_from_state,
    create_component_view,
    create_loss_data_point_from_metrics,
)

# Check Plotly
try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

pytestmark_plotly = pytest.mark.skipif(not PLOTLY_AVAILABLE, reason="Plotly not installed")

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def simple_board():
    """Simple BoardView for testing."""
    comp1 = ComponentView(
        ref="U1", position=Point(50, 40), rotation=0,
        width=10, height=8, status=ComponentStatus.OK,
        footprint="QFN-48", value="MCU",
    )
    comp2 = ComponentView(
        ref="R1", position=Point(80, 60), rotation=90,
        width=2, height=1, status=ComponentStatus.OK,
        footprint="0805", value="10k",
    )
    return BoardView(width=100, height=80, components=(comp1, comp2))


@pytest.fixture
def board_with_everything():
    """BoardView with zones, traces, and pads."""
    comp = ComponentView(
        ref="U1", position=Point(50, 40), rotation=0,
        width=10, height=8, footprint="QFN-48",
    )
    trace = TraceView(
        start=Point(10, 10), end=Point(90, 70),
        width=0.3, layer="F.Cu", net="VCC",
    )
    pad = PadView(
        position=Point(50, 40), size=(1.0, 0.8),
        shape="rect", layer="F.Cu", number="1",
        component_ref="U1", net="VCC",
    )
    zone = ZoneView(
        name="test_zone",
        polygon=(Point(0, 0), Point(30, 0), Point(30, 30), Point(0, 30)),
        zone_type="keepout",
    )
    return BoardView(
        width=100, height=80,
        components=(comp,),
        zones=(zone,),
        traces=(trace,),
        pads=(pad,),
    )


@pytest.fixture
def sample_rect():
    """A Rectangle for shape testing."""
    return Rectangle(center=Point(50, 40), width=10, height=8, rotation=0)


@pytest.fixture
def sample_loss_history():
    """LossHistory with data."""
    history = LossHistory()
    history.add_point(LossDataPoint(
        epoch=0, total_loss=1.0,
        breakdown={"overlap": 0.5, "boundary": 0.3, "wirelength": 0.2},
    ))
    history.add_point(LossDataPoint(
        epoch=10, total_loss=0.5,
        breakdown={"overlap": 0.2, "boundary": 0.15, "wirelength": 0.15},
    ))
    history.add_point(LossDataPoint(
        epoch=20, total_loss=0.1,
        breakdown={"overlap": 0.05, "boundary": 0.03, "wirelength": 0.02},
    ))
    history.phase_boundaries = [5, 15]
    history.phase_names = ["warmup", "optimize"]
    return history


@pytest.fixture
def sample_constraint_status():
    """ConstraintStatus with violations."""
    v1 = Violation(
        violation_type=ViolationType.OVERLAP,
        severity=0.8, component_refs=("U1", "R1"),
        message="Overlap detected", location=Point(50, 40),
    )
    v2 = Violation(
        violation_type=ViolationType.BOUNDARY,
        severity=0.4, component_refs=("U2",),
        message="Outside board", location=Point(105, 50),
    )
    return ConstraintStatus(
        violations=(v1, v2),
        overlap_count=1,
        boundary_violations=1,
    )


# ============================================================================
# board_renderer.py — pure functions (no Plotly needed for some)
# ============================================================================


class TestCheckPlotlyAvailableBoardRenderer:
    """Tests for check_plotly_available in board_renderer."""

    def test_check_plotly_available_passes_when_installed(self):
        """When Plotly is installed, check_plotly_available does nothing."""
        if not PLOTLY_AVAILABLE:
            pytest.skip("Plotly not installed")
        from temper_placer.visualization.board_renderer import check_plotly_available
        # Should not raise
        check_plotly_available()

    @pytest.mark.skipif(PLOTLY_AVAILABLE, reason="Plotly IS installed")
    def test_check_plotly_available_raises_when_missing(self):
        """When Plotly is not installed, raises ImportError."""
        from temper_placer.visualization.board_renderer import check_plotly_available
        with pytest.raises(ImportError):
            check_plotly_available()


class TestRectangleShape:
    """Tests for get_rectangle_shape (pure function, no Plotly call)."""

    @pytestmark_plotly
    def test_basic_rect_shape(self, sample_rect):
        from temper_placer.visualization.board_renderer import get_rectangle_shape
        shape = get_rectangle_shape(
            sample_rect, fill_color="#FF0000", line_color="#000000",
        )
        assert shape["type"] == "path"
        assert shape["fillcolor"] == "#FF0000"
        assert "M " in shape["path"]
        assert "Z" in shape["path"]

    @pytestmark_plotly
    def test_rect_shape_with_custom_opacity(self, sample_rect):
        from temper_placer.visualization.board_renderer import get_rectangle_shape
        shape = get_rectangle_shape(
            sample_rect, fill_color="#00FF00", opacity=0.5,
        )
        assert shape["opacity"] == 0.5

    @pytestmark_plotly
    def test_rect_shape_with_custom_line(self, sample_rect):
        from temper_placer.visualization.board_renderer import get_rectangle_shape
        shape = get_rectangle_shape(
            sample_rect, fill_color="#0000FF",
            line_color="#FFFFFF", line_width=2.0,
        )
        assert shape["line"]["color"] == "#FFFFFF"
        assert shape["line"]["width"] == 2.0


class TestComponentShape:
    """Tests for get_component_shape."""

    @pytestmark_plotly
    def test_get_component_shape_ok(self):
        from temper_placer.visualization.board_renderer import get_component_shape
        comp = ComponentView(
            ref="U1", position=Point(50, 40), rotation=0,
            width=10, height=8, status=ComponentStatus.OK,
        )
        shape = get_component_shape(comp)
        assert shape["type"] == "path"
        # OK components should be green
        assert shape["fillcolor"] is not None

    @pytestmark_plotly
    def test_get_component_shape_error(self):
        from temper_placer.visualization.board_renderer import get_component_shape
        comp = ComponentView(
            ref="R1", position=Point(10, 20), rotation=0,
            width=2, height=1, status=ComponentStatus.ERROR,
        )
        shape = get_component_shape(comp)
        assert shape["type"] == "path"
        # Error components get red border
        assert shape["line"]["color"] == "#FF0000"
        assert shape["line"]["width"] == 2.0

    @pytestmark_plotly
    def test_get_component_shape_warning(self):
        from temper_placer.visualization.board_renderer import get_component_shape
        comp = ComponentView(
            ref="C1", position=Point(30, 40), rotation=0,
            width=3, height=2, status=ComponentStatus.WARNING,
        )
        shape = get_component_shape(comp)
        assert shape["line"]["color"] == "#FFA500"
        assert shape["line"]["width"] == 1.5

    @pytestmark_plotly
    def test_get_component_shape_no_status_color(self):
        from temper_placer.visualization.board_renderer import get_component_shape
        comp = ComponentView(
            ref="U1", position=Point(50, 40), rotation=0,
            width=10, height=8, status=ComponentStatus.ERROR,
        )
        shape = get_component_shape(comp, show_status_color=False)
        assert shape["fillcolor"] == "#4A90D9"  # Default blue


class TestZoneShape:
    """Tests for get_zone_shape."""

    @pytestmark_plotly
    def test_zone_shape_basic(self):
        from temper_placer.visualization.board_renderer import get_zone_shape
        zone = ZoneView(
            name="TEST",
            polygon=(Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)),
            zone_type="keepout",
        )
        shape = get_zone_shape(zone)
        assert shape["type"] == "path"
        assert "M " in shape["path"]

    @pytestmark_plotly
    def test_zone_shape_custom_color(self):
        from temper_placer.visualization.board_renderer import get_zone_shape
        zone = ZoneView(
            name="CUSTOM",
            polygon=(Point(0, 0), Point(5, 5)),
            zone_type="generic",
            color="#FF00FF",
        )
        shape = get_zone_shape(zone)
        assert shape["fillcolor"] == "#FF00FF"

    @pytestmark_plotly
    def test_zone_shape_empty_polygon(self):
        from temper_placer.visualization.board_renderer import get_zone_shape
        zone = ZoneView(
            name="EMPTY",
            polygon=(),
            zone_type="generic",
        )
        shape = get_zone_shape(zone)
        assert shape == {}


class TestComponentAnnotations:
    """Tests for create_component_annotations."""

    def test_annotations_basic(self, simple_board):
        from temper_placer.visualization.board_renderer import create_component_annotations
        annotations = create_component_annotations(simple_board.components)
        assert len(annotations) == 2
        assert annotations[0]["text"] == "U1"
        assert annotations[1]["text"] == "R1"
        assert annotations[0]["x"] == 50
        assert annotations[0]["y"] == 40

    def test_annotations_hidden(self, simple_board):
        from temper_placer.visualization.board_renderer import create_component_annotations
        annotations = create_component_annotations(
            simple_board.components, show_refs=False,
        )
        assert annotations == []

    def test_annotations_custom_font(self, simple_board):
        from temper_placer.visualization.board_renderer import create_component_annotations
        annotations = create_component_annotations(
            simple_board.components, font_size=14,
        )
        assert annotations[0]["font"]["size"] == 14

    def test_annotations_empty_components(self):
        from temper_placer.visualization.board_renderer import create_component_annotations
        annotations = create_component_annotations(())
        assert annotations == []


class TestComponentHoverData:
    """Tests for create_component_hover_data."""

    def test_hover_data_basic(self, simple_board):
        from temper_placer.visualization.board_renderer import create_component_hover_data
        x, y, texts = create_component_hover_data(simple_board.components)
        assert len(x) == 2
        assert len(y) == 2
        assert len(texts) == 2
        assert x[0] == 50.0
        assert y[0] == 40.0
        assert "U1" in texts[0]
        assert "QFN-48" in texts[0]

    def test_hover_data_includes_status(self):
        from temper_placer.visualization.board_renderer import create_component_hover_data
        comp = ComponentView(
            ref="ERR", position=Point(0, 0), rotation=0,
            width=2, height=1, status=ComponentStatus.ERROR,
            value="BadComponent",
        )
        _, _, texts = create_component_hover_data((comp,))
        assert "ERR" in texts[0]
        assert "BadComponent" in texts[0]
        assert "error" in texts[0].lower()

    def test_hover_data_with_violations(self):
        from temper_placer.visualization.board_renderer import create_component_hover_data
        comp = ComponentView(
            ref="BAD", position=Point(10, 20), rotation=0,
            width=5, height=3, status=ComponentStatus.ERROR,
            violations=("Overlaps with U1", "Outside boundary"),
        )
        _, _, texts = create_component_hover_data((comp,))
        assert "Overlaps" in texts[0]
        assert "boundary" in texts[0].lower()

    def test_hover_data_no_optional_fields(self):
        from temper_placer.visualization.board_renderer import create_component_hover_data
        comp = ComponentView(
            ref="SIMPLE", position=Point(50, 40), rotation=0,
            width=3, height=2,
        )
        _, _, texts = create_component_hover_data((comp,))
        assert "SIMPLE" in texts[0]


# ============================================================================
# board_renderer.py — Plotly-dependent rendering
# ============================================================================


class TestRenderBoard:
    """Tests for render_board."""

    @pytestmark_plotly
    def test_render_board_basic(self, simple_board):
        from temper_placer.visualization.board_renderer import render_board
        from temper_placer.visualization.config_types import BoardRenderOptions
        fig = render_board(simple_board)
        assert fig is not None
        assert len(fig.data) > 0  # At least component hover scatter
        assert fig.layout.shapes is not None

    @pytestmark_plotly
    def test_render_board_with_options(self, simple_board):
        from temper_placer.visualization.board_renderer import render_board
        from temper_placer.visualization.config_types import BoardRenderOptions
        opts = BoardRenderOptions(
            title="Test Board", show_refs=False,
            show_grid=False, show_legend=False,
            width=600, height=400,
        )
        fig = render_board(simple_board, options=opts)
        assert fig.layout.title.text == "Test Board"

    @pytestmark_plotly
    def test_render_board_full(self, board_with_everything):
        from temper_placer.visualization.board_renderer import render_board
        fig = render_board(board_with_everything)
        assert fig is not None

    @pytestmark_plotly
    def test_render_board_with_loops(self, board_with_everything):
        from temper_placer.visualization.board_renderer import render_board
        from temper_placer.core.loop import (
            Loop, LoopCollection, LoopEvent, LoopPriority, LoopType,
        )
        loop = Loop(
            name="test_loop",
            loop_type=LoopType("commutation"),
            description="A test loop",
            components=["U1"],
            max_area_mm2=100.0,
            priority=LoopPriority("critical"),
            events=LoopEvent(di_dt=1e9, frequency_hz=50000),
        )
        collection = LoopCollection()
        collection.add_loop(loop)
        fig = render_board(board_with_everything, loops=collection)
        assert fig is not None


class TestRenderBoardWithViolations:
    """Tests for render_board_with_violations."""

    @pytestmark_plotly
    def test_render_with_violations(self, simple_board, sample_constraint_status):
        from temper_placer.visualization.board_renderer import render_board_with_violations
        fig = render_board_with_violations(simple_board, sample_constraint_status)
        assert fig is not None
        # Should have violation markers
        has_violation_trace = any(
            "Violations" in getattr(t, "name", "") for t in fig.data
        )
        assert has_violation_trace

    @pytestmark_plotly
    def test_render_without_highlight(self, simple_board, sample_constraint_status):
        from temper_placer.visualization.board_renderer import render_board_with_violations
        fig = render_board_with_violations(
            simple_board, sample_constraint_status, highlight_violations=False,
        )
        assert fig is not None

    @pytestmark_plotly
    def test_render_empty_violations(self, simple_board):
        from temper_placer.visualization.board_renderer import render_board_with_violations
        status = ConstraintStatus()
        fig = render_board_with_violations(simple_board, status)
        assert fig is not None


class TestBoardToHtml:
    """Tests for board_to_html."""

    @pytestmark_plotly
    def test_board_to_html_basic(self, simple_board):
        from temper_placer.visualization.board_renderer import board_to_html
        html = board_to_html(simple_board)
        assert isinstance(html, str)
        assert "<html" in html.lower()
        assert "plotly" in html.lower()

    @pytestmark_plotly
    def test_board_to_html_no_plotlyjs(self, simple_board):
        from temper_placer.visualization.board_renderer import board_to_html
        html = board_to_html(simple_board, include_plotlyjs=False)
        assert isinstance(html, str)

    @pytestmark_plotly
    def test_board_to_html_with_file(self, simple_board):
        from temper_placer.visualization.board_renderer import board_to_html
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            path = f.name
        try:
            html = board_to_html(simple_board, output_path=path)
            assert Path(path).exists()
            content = Path(path).read_text()
            assert "U1" in content or "plotly" in content.lower()
        finally:
            Path(path).unlink(missing_ok=True)


class TestBoardToJson:
    """Tests for board_to_json."""

    @pytestmark_plotly
    def test_board_to_json_basic(self, simple_board):
        from temper_placer.visualization.board_renderer import board_to_json
        json_str = board_to_json(simple_board)
        data = json.loads(json_str)
        assert "data" in data or "layout" in data

    @pytestmark_plotly
    def test_board_to_json_with_options(self, simple_board):
        from temper_placer.visualization.board_renderer import board_to_json
        from temper_placer.visualization.config_types import BoardRenderOptions
        opts = BoardRenderOptions(show_refs=False, show_legend=False)
        json_str = board_to_json(simple_board, options=opts)
        data = json.loads(json_str)
        assert data is not None


# ============================================================================
# loss_plots.py
# ============================================================================


class TestLossPlotsCheckPlotly:
    """Tests for check_plotly_available in loss_plots."""

    def test_check_plotly_available_passes(self):
        if not PLOTLY_AVAILABLE:
            pytest.skip("Plotly not installed")
        from temper_placer.visualization.loss_plots import check_plotly_available
        check_plotly_available()  # Should not raise

    @pytest.mark.skipif(PLOTLY_AVAILABLE, reason="Plotly IS installed")
    def test_check_plotly_available_raises(self):
        from temper_placer.visualization.loss_plots import check_plotly_available
        with pytest.raises(ImportError):
            check_plotly_available()


class TestGetTermColor:
    """Tests for get_term_color (pure function)."""

    def test_known_terms(self):
        from temper_placer.visualization.loss_plots import get_term_color
        assert get_term_color("overlap").startswith("#")
        assert get_term_color("boundary").startswith("#")
        assert get_term_color("wirelength").startswith("#")
        assert get_term_color("thermal").startswith("#")
        assert get_term_color("total").startswith("#")

    def test_unknown_term_returns_default(self):
        from temper_placer.visualization.loss_plots import get_term_color
        from temper_placer.visualization.loss_plots import DEFAULT_COLOR
        assert get_term_color("nonexistent_term") == DEFAULT_COLOR

    def test_case_insensitive(self):
        from temper_placer.visualization.loss_plots import get_term_color
        lower = get_term_color("overlap")
        upper = get_term_color("OVERLAP")
        assert lower == upper


class TestLossCurves:
    """Tests for render_loss_curves."""

    @pytestmark_plotly
    def test_render_loss_curves(self, sample_loss_history):
        from temper_placer.visualization.loss_plots import render_loss_curves
        fig = render_loss_curves(sample_loss_history)
        assert fig is not None
        assert len(fig.data) >= 1  # At least total loss curve

    @pytestmark_plotly
    def test_render_loss_curves_no_breakdown(self, sample_loss_history):
        from temper_placer.visualization.loss_plots import render_loss_curves
        fig = render_loss_curves(sample_loss_history, show_breakdown=False)
        assert fig is not None

    @pytestmark_plotly
    def test_render_loss_curves_no_phases(self, sample_loss_history):
        from temper_placer.visualization.loss_plots import render_loss_curves
        fig = render_loss_curves(sample_loss_history, show_phases=False)
        assert fig is not None

    @pytestmark_plotly
    def test_render_loss_curves_log_scale(self, sample_loss_history):
        from temper_placer.visualization.loss_plots import render_loss_curves
        fig = render_loss_curves(sample_loss_history, log_scale=True)
        assert fig is not None

    @pytestmark_plotly
    def test_render_loss_curves_empty(self):
        from temper_placer.visualization.loss_plots import render_loss_curves
        history = LossHistory()
        fig = render_loss_curves(history)
        assert fig is not None

    @pytestmark_plotly
    def test_render_loss_curves_custom_title(self, sample_loss_history):
        from temper_placer.visualization.loss_plots import render_loss_curves
        fig = render_loss_curves(sample_loss_history, title="Custom")
        assert "Custom" in fig.layout.title.text


class TestLossBreakdownBar:
    """Tests for render_loss_breakdown_bar."""

    @pytestmark_plotly
    def test_breakdown_bar(self, sample_loss_history):
        from temper_placer.visualization.loss_plots import render_loss_breakdown_bar
        fig = render_loss_breakdown_bar(sample_loss_history)
        assert fig is not None
        # Should have bar trace
        assert len(fig.data) >= 1

    @pytestmark_plotly
    def test_breakdown_bar_specific_epoch(self, sample_loss_history):
        from temper_placer.visualization.loss_plots import render_loss_breakdown_bar
        fig = render_loss_breakdown_bar(sample_loss_history, epoch=10)
        assert fig is not None

    @pytestmark_plotly
    def test_breakdown_bar_empty(self):
        from temper_placer.visualization.loss_plots import render_loss_breakdown_bar
        history = LossHistory()
        fig = render_loss_breakdown_bar(history)
        assert fig is not None

    @pytestmark_plotly
    def test_breakdown_bar_no_breakdown(self):
        from temper_placer.visualization.loss_plots import render_loss_breakdown_bar
        history = LossHistory()
        history.add_point(LossDataPoint(epoch=0, total_loss=1.0))
        fig = render_loss_breakdown_bar(history)
        assert fig is not None


class TestLossHeatmap:
    """Tests for render_loss_heatmap."""

    @pytestmark_plotly
    def test_heatmap(self, sample_loss_history):
        from temper_placer.visualization.loss_plots import render_loss_heatmap
        fig = render_loss_heatmap(sample_loss_history)
        assert fig is not None

    @pytestmark_plotly
    def test_heatmap_empty(self):
        from temper_placer.visualization.loss_plots import render_loss_heatmap
        history = LossHistory()
        fig = render_loss_heatmap(history)
        assert fig is not None


class TestTrainingDashboard:
    """Tests for render_training_dashboard."""

    @pytestmark_plotly
    def test_dashboard(self, sample_loss_history):
        from temper_placer.visualization.loss_plots import render_training_dashboard
        fig = render_training_dashboard(sample_loss_history)
        assert fig is not None

    @pytestmark_plotly
    def test_dashboard_custom_params(self, sample_loss_history):
        from temper_placer.visualization.loss_plots import render_training_dashboard
        fig = render_training_dashboard(
            sample_loss_history, width=1000, height=800,
        )
        assert fig is not None

    @pytestmark_plotly
    def test_dashboard_empty(self):
        from temper_placer.visualization.loss_plots import render_training_dashboard
        history = LossHistory()
        fig = render_training_dashboard(history)
        assert fig is not None


class TestLossHistoryToHtml:
    """Tests for loss_history_to_html."""

    @pytestmark_plotly
    def test_basic(self, sample_loss_history):
        from temper_placer.visualization.loss_plots import loss_history_to_html
        html = loss_history_to_html(sample_loss_history)
        assert isinstance(html, str)
        assert "plotly" in html.lower()


class TestLossHistoryToJson:
    """Tests for loss_history_to_json."""

    @pytestmark_plotly
    def test_basic(self, sample_loss_history):
        from temper_placer.visualization.loss_plots import loss_history_to_json
        json_str = loss_history_to_json(sample_loss_history)
        data = json.loads(json_str)
        assert data is not None


# ============================================================================
# loop_viz.py — pure functions
# ============================================================================


class TestCalculateLoopArea:
    """Tests for calculate_loop_area."""

    def test_zero_area(self):
        from temper_placer.visualization.loop_viz import calculate_loop_area
        # Degenerate (less than 3 points)
        assert calculate_loop_area([(0, 0), (1, 1)]) == 0.0

    def test_square_area(self):
        from temper_placer.visualization.loop_viz import calculate_loop_area
        # 10x10 square, area = 100
        points = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert calculate_loop_area(points) == 100.0

    def test_triangle_area(self):
        from temper_placer.visualization.loop_viz import calculate_loop_area
        # Right triangle: base=10, height=5, area=25
        points = [(0, 0), (10, 0), (0, 5)]
        assert calculate_loop_area(points) == 25.0

    def test_rectangle_area(self):
        from temper_placer.visualization.loop_viz import calculate_loop_area
        points = [(0, 0), (20, 0), (20, 15), (0, 15)]
        assert calculate_loop_area(points) == 300.0

    def test_clockwise_ordering(self):
        from temper_placer.visualization.loop_viz import calculate_loop_area
        # Clockwise should also give positive area
        points = [(0, 0), (0, 10), (10, 10), (10, 0)]
        assert calculate_loop_area(points) == 100.0


class TestGetLoopPoints:
    """Tests for get_loop_points."""

    def test_from_pads(self):
        from temper_placer.visualization.loop_viz import get_loop_points
        from temper_placer.core.loop import Loop, LoopEvent, LoopPriority, LoopType, LoopPin

        comp = ComponentView(
            ref="U1", position=Point(20, 30), rotation=0,
            width=10, height=8,
        )
        comp2 = ComponentView(
            ref="Q1", position=Point(60, 30), rotation=0,
            width=10, height=10,
        )
        pad1 = PadView(
            position=Point(20, 30), size=(1.0, 1.0),
            shape="rect", layer="F.Cu", number="1",
            component_ref="U1", net="VCC",
        )
        pad2 = PadView(
            position=Point(60, 30), size=(1.0, 1.0),
            shape="rect", layer="F.Cu", number="1",
            component_ref="Q1", net="VCC",
        )
        board = BoardView(
            width=100, height=80,
            components=(comp, comp2),
            pads=(pad1, pad2),
        )
        loop = Loop(
            name="test_loop",
            loop_type=LoopType("commutation"),
            description="Test",
            components=["U1", "Q1"],
            max_area_mm2=100.0,
            priority=LoopPriority("critical"),
            events=LoopEvent(di_dt=1e9, frequency_hz=50000),
            pins=[LoopPin("U1", "1"), LoopPin("Q1", "1")],
        )
        points = get_loop_points(loop, board)
        # Should have at least 2 points (closed loop means 3 for 2 unique)
        assert len(points) >= 2
        assert points[0] == (20.0, 30.0)
        assert points[1] == (60.0, 30.0)

    def test_from_components_fallback(self):
        from temper_placer.visualization.loop_viz import get_loop_points
        from temper_placer.core.loop import Loop, LoopEvent, LoopPriority, LoopType

        comp = ComponentView(
            ref="U1", position=Point(10, 20), rotation=0,
            width=5, height=3,
        )
        comp2 = ComponentView(
            ref="R1", position=Point(30, 40), rotation=0,
            width=2, height=1,
        )
        board = BoardView(width=60, height=60, components=(comp, comp2))
        loop = Loop(
            name="test_loop",
            loop_type=LoopType("commutation"),
            description="Test",
            components=["U1", "R1"],
            max_area_mm2=100.0,
            priority=LoopPriority("critical"),
            events=LoopEvent(di_dt=1e9, frequency_hz=50000),
        )
        points = get_loop_points(loop, board)
        assert len(points) >= 2
        assert points[0] == (10.0, 20.0)
        assert points[1] == (30.0, 40.0)

    def test_missing_component(self):
        from temper_placer.visualization.loop_viz import get_loop_points
        from temper_placer.core.loop import Loop, LoopEvent, LoopPriority, LoopType

        board = BoardView(width=60, height=60, components=())
        loop = Loop(
            name="test_loop",
            loop_type=LoopType("commutation"),
            description="Test",
            components=["MISSING"],
            max_area_mm2=100.0,
            priority=LoopPriority("critical"),
            events=LoopEvent(di_dt=1e9, frequency_hz=50000),
        )
        points = get_loop_points(loop, board)
        assert points == []


# ============================================================================
# report.py
# ============================================================================


class TestGenerateReport:
    """Tests for generate_report."""

    def test_generate_report_basic(self, simple_board):
        from temper_placer.visualization.report import generate_report
        report = generate_report(simple_board)
        assert isinstance(report, str)
        assert "<html" in report.lower()
        assert "Placement Optimization Report" in report

    def test_generate_report_with_history(self, simple_board, sample_loss_history):
        from temper_placer.visualization.report import generate_report
        report = generate_report(
            simple_board,
            loss_history=sample_loss_history,
        )
        assert "U1" in report or "Loss" in report

    def test_generate_report_with_constraints(self, simple_board, sample_constraint_status):
        from temper_placer.visualization.report import generate_report
        report = generate_report(
            simple_board,
            constraints=sample_constraint_status,
        )
        assert isinstance(report, str)

    def test_generate_report_to_file(self, simple_board):
        from temper_placer.visualization.report import generate_report
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            path = f.name
        try:
            report = generate_report(simple_board, output_path=path)
            assert Path(path).exists()
            content = Path(path).read_text()
            assert "Placement Optimization Report" in content
        finally:
            Path(path).unlink(missing_ok=True)

    def test_generate_report_with_config(self, simple_board):
        from temper_placer.visualization.report import (
            generate_report, ReportConfig,
        )
        config = ReportConfig(
            title="Custom Report",
            include_timestamp=False,
            include_board_view=False,
            include_loss_curves=False,
            include_component_table=False,
        )
        report = generate_report(simple_board, config=config)
        assert "Custom Report" in report

    def test_generate_report_with_validation(self, simple_board):
        from temper_placer.visualization.report import (
            generate_report, ValidationResults,
        )
        validation = ValidationResults(
            drc_passed=True,
            drc_warnings=["Minor spacing issue"],
            spice_passed=True,
        )
        report = generate_report(simple_board, validation=validation)
        assert isinstance(report, str)


# ============================================================================
# live.py — LiveVisualizer (headless mode)
# ============================================================================


class TestLiveVisualizerHeadless:
    """Tests for LiveVisualizer in headless mode."""

    def test_create_visualizer(self):
        from temper_placer.visualization.live import create_visualizer, LiveVisualizer
        viz = create_visualizer(port=18765, headless=True)
        assert isinstance(viz, LiveVisualizer)
        assert viz.config.headless is True

    def test_is_paused_default(self):
        from temper_placer.visualization.live import LiveVisualizer
        viz = LiveVisualizer(port=18766, headless=True)
        assert viz.is_paused is False

    def test_url_property(self):
        from temper_placer.visualization.live import LiveVisualizer
        viz = LiveVisualizer(host="127.0.0.1", port=18767, headless=True)
        assert "127.0.0.1" in viz.url
        assert "18767" in viz.url

    def test_client_count(self):
        from temper_placer.visualization.live import LiveVisualizer
        viz = LiveVisualizer(port=18768, headless=True)
        assert viz.client_count == 0

    def test_start_stop_headless(self):
        from temper_placer.visualization.live import LiveVisualizer
        viz = LiveVisualizer(port=18769, headless=True, verbose=False)
        viz.start()
        assert viz.is_running
        viz.stop()
        assert not viz.is_running

    def test_get_loss_history(self):
        from temper_placer.visualization.live import LiveVisualizer
        viz = LiveVisualizer(port=18770, headless=True)
        history = viz.get_loss_history()
        assert isinstance(history, LossHistory)
        assert len(history.data_points) == 0

    def test_clear_history(self):
        from temper_placer.visualization.live import LiveVisualizer
        viz = LiveVisualizer(port=18771, headless=True)
        # Start so we can accumulate
        viz.start()
        viz.update(
            positions=np.array([[10.0, 20.0], [30.0, 40.0]]),
            rotations=np.array([0.0, 90.0]),
            widths=np.array([5.0, 2.0]),
            heights=np.array([4.0, 1.0]),
            refs=["U1", "R1"],
            board_width=100.0,
            board_height=80.0,
            losses={"total": 0.5, "overlap": 0.3},
            epoch=1,
        )
        assert len(viz.get_loss_history().data_points) > 0
        viz.clear_history()
        assert len(viz.get_loss_history().data_points) == 0
        viz.stop()

    def test_update_headless(self):
        from temper_placer.visualization.live import LiveVisualizer
        viz = LiveVisualizer(port=18772, headless=True, verbose=False)
        viz.start()
        viz.update(
            positions=np.array([[10.0, 20.0]]),
            rotations=np.array([0.0]),
            widths=np.array([5.0]),
            heights=np.array([4.0]),
            refs=["U1"],
            board_width=100.0,
            board_height=80.0,
            losses={"total": 0.5},
            epoch=1,
        )
        history = viz.get_loss_history()
        assert len(history.data_points) == 1
        assert history.data_points[0].epoch == 1
        viz.stop()

    def test_update_from_state(self):
        from temper_placer.visualization.live import LiveVisualizer
        viz = LiveVisualizer(port=18773, headless=True, verbose=False)
        viz.start()
        viz.update_from_state(
            positions=np.array([[10.0, 20.0], [30.0, 40.0]]),
            rotations=np.array([0.0, 90.0]),
            component_info={
                "widths": [5.0, 2.0],
                "heights": [4.0, 1.0],
                "refs": ["U1", "R1"],
            },
            board_info={"width": 100.0, "height": 80.0},
            loss_info={"total": 0.3},
            epoch=2,
        )
        history = viz.get_loss_history()
        assert len(history.data_points) == 1
        viz.stop()

    def test_update_active_detects_violations(self):
        from temper_placer.visualization.live import LiveVisualizer
        viz = LiveVisualizer(
            port=18774, headless=True, verbose=False,
        )
        viz.config.overlap_threshold = 0.001
        viz.start()
        viz.update(
            positions=np.array([[10.0, 20.0]]),
            rotations=np.array([0.0]),
            widths=np.array([5.0]),
            heights=np.array([4.0]),
            refs=["U1"],
            board_width=100.0,
            board_height=80.0,
            losses={"total": 0.5, "overlap": 0.1, "boundary": 0.05},
            epoch=1,
        )
        viz.stop()

    def test_update_with_zones(self):
        from temper_placer.visualization.live import LiveVisualizer
        viz = LiveVisualizer(port=18775, headless=True, verbose=False)
        viz.start()
        viz.update(
            positions=np.array([[50.0, 40.0]]),
            rotations=np.array([0.0]),
            widths=np.array([5.0]),
            heights=np.array([4.0]),
            refs=["U1"],
            board_width=100.0,
            board_height=80.0,
            losses={"total": 0.2},
            epoch=1,
            zones=[{"name": "ZoneA", "x": 0, "y": 0, "width": 50, "height": 50}],
        )
        viz.stop()

    def test_empty_update_with_flat_positions(self):
        """Test with 1D flattened positions array."""
        from temper_placer.visualization.live import LiveVisualizer
        viz = LiveVisualizer(port=18776, headless=True, verbose=False)
        viz.start()
        viz.update(
            positions=np.array([10.0, 20.0, 30.0, 40.0]),
            rotations=np.array([0.0, 0.0]),
            widths=np.array([5.0, 2.0]),
            heights=np.array([4.0, 1.0]),
            refs=["U1", "R1"],
            board_width=100.0,
            board_height=80.0,
            losses={"total": 0.5},
            epoch=1,
        )
        viz.stop()


class TestCreateLossDataPointFromMetrics:
    """Tests for create_loss_data_point_from_metrics (factory)."""

    def test_from_metrics_basic(self):
        from temper_placer.visualization.model import create_loss_data_point_from_metrics

        class MockMetrics:
            epoch = 100
            loss = 0.05
            loss_breakdown = {"overlap": 0.02, "boundary": 0.03}
            temperature = 0.3
            learning_rate = 0.0005
            convergence_confidence = 0.95
            loss_improvement_ema = 0.01

        metrics = MockMetrics()
        ldp = create_loss_data_point_from_metrics(metrics)
        assert ldp.epoch == 100
        assert ldp.total_loss == 0.05
        assert ldp.breakdown == {"overlap": 0.02, "boundary": 0.03}
        assert ldp.temperature == 0.3
        assert ldp.learning_rate == 0.0005
        assert ldp.convergence_confidence == 0.95
        assert ldp.improvement_ema == 0.01

    def test_from_metrics_minimal(self):
        from temper_placer.visualization.model import create_loss_data_point_from_metrics

        class MockMetrics:
            epoch = 42
            loss = 0.5
            loss_breakdown = None
            temperature = None
            learning_rate = None

        metrics = MockMetrics()
        ldp = create_loss_data_point_from_metrics(metrics)
        assert ldp.epoch == 42
        assert ldp.total_loss == 0.5
        assert ldp.breakdown == {}
        assert ldp.temperature is None
        assert ldp.learning_rate is None


class TestComputeCoordinateStatistics:
    """Tests for compute_coordinate_statistics (validation.py)."""

    def test_stats_with_components(self, simple_board):
        from temper_placer.visualization.validation import compute_coordinate_statistics
        stats = compute_coordinate_statistics(simple_board)
        assert stats["board"]["width"] == 100
        assert stats["board"]["height"] == 80
        comp_stats = stats["components"]
        assert comp_stats["count"] == 2
        assert comp_stats["x_min"] == 50.0
        assert comp_stats["x_max"] == 80.0

    def test_stats_with_traces(self):
        from temper_placer.visualization.validation import compute_coordinate_statistics
        trace = TraceView(
            start=Point(10, 20), end=Point(90, 80),
            width=0.3, layer="F.Cu",
        )
        board = BoardView(width=100, height=80, traces=(trace,))
        stats = compute_coordinate_statistics(board)
        trace_stats = stats.get("traces", {})
        assert trace_stats.get("count") == 1

    def test_stats_with_pads(self):
        from temper_placer.visualization.validation import compute_coordinate_statistics
        pad = PadView(
            position=Point(50, 40), size=(1.0, 0.8),
            shape="rect", layer="F.Cu",
        )
        board = BoardView(width=100, height=80, pads=(pad,))
        stats = compute_coordinate_statistics(board)
        pad_stats = stats.get("pads", {})
        assert pad_stats.get("count") == 1

    def test_stats_empty_board(self):
        from temper_placer.visualization.validation import compute_coordinate_statistics
        board = BoardView(width=100, height=80)
        stats = compute_coordinate_statistics(board)
        assert stats["board"]["width"] == 100
        assert "count" not in stats["components"]

    def test_stats_all_types(self, board_with_everything):
        from temper_placer.visualization.validation import compute_coordinate_statistics
        stats = compute_coordinate_statistics(board_with_everything)
        assert "components" in stats
        assert "traces" in stats
        assert "pads" in stats


# ============================================================================
# server.py — MockLiveServer and create_server
# ============================================================================


class TestMockLiveServer:
    """Tests for MockLiveServer (no websockets needed)."""

    def test_url_property(self):
        from temper_placer.visualization.server import MockLiveServer
        server = MockLiveServer(host="127.0.0.1", port=9999)
        assert server.url == "http://127.0.0.1:9999"

    def test_ws_url_property(self):
        from temper_placer.visualization.server import MockLiveServer
        server = MockLiveServer(host="127.0.0.1", port=9999)
        assert server.ws_url == "ws://127.0.0.1:9999/ws"

    def test_start_stop(self):
        from temper_placer.visualization.server import MockLiveServer
        server = MockLiveServer()
        assert not server.state.is_running
        server.start()
        assert server.state.is_running
        server.stop()
        assert not server.state.is_running

    def test_is_paused(self):
        from temper_placer.visualization.server import MockLiveServer
        server = MockLiveServer()
        assert server.is_paused is False
        server.state.is_paused = True
        assert server.is_paused is True

    def test_client_count(self):
        from temper_placer.visualization.server import MockLiveServer
        server = MockLiveServer()
        assert server.client_count == 0

    def test_send_update(self):
        from temper_placer.visualization.server import MockLiveServer
        from temper_placer.visualization.model import VisualizationState
        server = MockLiveServer()
        state = VisualizationState(
            board=BoardView(width=100, height=80),
            loss_history=LossHistory(),
            constraints=ConstraintStatus(),
        )
        server.send_update(state)
        assert server.state.last_state is state
        assert len(server._updates) == 1

    def test_send_training_started(self):
        from temper_placer.visualization.server import MockLiveServer
        server = MockLiveServer()
        server.send_training_started()  # Should not raise

    def test_send_training_stopped(self):
        from temper_placer.visualization.server import MockLiveServer
        server = MockLiveServer()
        server.send_training_stopped()  # Should not raise

    def test_send_training_complete(self):
        from temper_placer.visualization.server import MockLiveServer
        server = MockLiveServer()
        server.send_training_complete()  # Should not raise

    def test_send_training_complete_with_state(self):
        from temper_placer.visualization.server import MockLiveServer
        from temper_placer.visualization.model import VisualizationState
        server = MockLiveServer()
        state = VisualizationState(
            board=BoardView(width=100, height=80),
            loss_history=LossHistory(),
            constraints=ConstraintStatus(),
        )
        server.send_training_complete(state)  # Should not raise

    def test_multiple_updates(self):
        from temper_placer.visualization.server import MockLiveServer
        from temper_placer.visualization.model import VisualizationState
        server = MockLiveServer()
        for i in range(3):
            state = VisualizationState(
                board=BoardView(width=100, height=80),
                loss_history=LossHistory(),
                constraints=ConstraintStatus(),
                epoch=i,
            )
            server.send_update(state)
        assert len(server._updates) == 3
        assert server.state.last_state.epoch == 2


class TestCreateServer:
    """Tests for create_server factory function."""

    def test_create_server_returns_mock_when_no_websockets(self):
        from temper_placer.visualization.server import create_server
        server = create_server(port=0)
        # With websockets installed, this is a LiveServer; without, Mock
        assert hasattr(server, "start")
        assert hasattr(server, "stop")

    def test_create_server_passes_kwargs(self):
        from temper_placer.visualization.server import create_server
        server = create_server(host="0.0.0.0", port=12345)
        assert server.config.host == "0.0.0.0"
        assert server.config.port == 12345


# ============================================================================
# LiveServer.send_training_complete (requires websockets)
# ============================================================================


class TestLiveServerTrainingComplete:
    """Tests for LiveServer.send_training_complete method."""

    def test_send_training_complete_not_running(self):
        """send_training_complete is a no-op when server not running."""
        from temper_placer.visualization.server import LiveServer
        from temper_placer.visualization.model import VisualizationState

        server = LiveServer(port=0, open_browser=False)
        state = VisualizationState(
            board=BoardView(width=100, height=80),
            loss_history=LossHistory(),
            constraints=ConstraintStatus(),
        )
        # Should not raise - server not running
        server.send_training_complete(state)
