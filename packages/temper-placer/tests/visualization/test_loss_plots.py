"""
Tests for loss curve plotting.

Tests the Plotly loss curve rendering functions. Tests are skipped if Plotly
is not installed.
"""

import json

import pytest

from temper_placer.visualization.loss_plots import (
    LOSS_TERM_COLORS,
    PLOTLY_AVAILABLE,
    get_term_color,
)
from temper_placer.visualization.model import LossDataPoint, LossHistory

# Skip all tests in this module if Plotly is not available
pytestmark = pytest.mark.skipif(
    not PLOTLY_AVAILABLE,
    reason="Plotly not installed",
)


@pytest.fixture
def empty_history() -> LossHistory:
    """Create an empty loss history."""
    return LossHistory()


@pytest.fixture
def simple_history() -> LossHistory:
    """Create a simple loss history with a few points."""
    history = LossHistory()
    history.add_point(
        LossDataPoint(
            epoch=0,
            total_loss=1.0,
            breakdown={"overlap": 0.6, "boundary": 0.4},
            learning_rate=0.01,
            temperature=1.0,
        )
    )
    history.add_point(
        LossDataPoint(
            epoch=50,
            total_loss=0.5,
            breakdown={"overlap": 0.3, "boundary": 0.2},
            learning_rate=0.005,
            temperature=0.5,
        )
    )
    history.add_point(
        LossDataPoint(
            epoch=100,
            total_loss=0.1,
            breakdown={"overlap": 0.05, "boundary": 0.05},
            learning_rate=0.001,
            temperature=0.1,
        )
    )
    return history


@pytest.fixture
def history_with_phases() -> LossHistory:
    """Create a loss history with phase boundaries."""
    history = LossHistory()
    for i in range(0, 201, 10):
        history.add_point(
            LossDataPoint(
                epoch=i,
                total_loss=1.0 / (1 + i / 50),
                breakdown={"overlap": 0.5 / (1 + i / 50), "boundary": 0.5 / (1 + i / 50)},
            )
        )
    history.phase_boundaries = [50, 150]
    history.phase_names = ["Warmup", "Main Training"]
    return history


class TestLossTermColors:
    """Tests for loss term color mapping."""

    def test_standard_terms_have_colors(self):
        """Test standard loss terms have colors."""
        expected_terms = [
            "overlap",
            "boundary",
            "wirelength",
            "clearance",
            "thermal",
            "total",
        ]
        for term in expected_terms:
            assert term in LOSS_TERM_COLORS
            assert LOSS_TERM_COLORS[term].startswith("#")


class TestGetTermColor:
    """Tests for get_term_color function."""

    def test_known_term(self):
        """Test color for known term."""
        assert get_term_color("overlap") == LOSS_TERM_COLORS["overlap"]
        assert get_term_color("boundary") == LOSS_TERM_COLORS["boundary"]

    def test_unknown_term(self):
        """Test default color for unknown term."""
        color = get_term_color("unknown_term_xyz")
        assert color == "#9E9E9E"  # Default gray

    def test_case_insensitive(self):
        """Test term matching is case insensitive."""
        assert get_term_color("OVERLAP") == LOSS_TERM_COLORS["overlap"]
        assert get_term_color("Boundary") == LOSS_TERM_COLORS["boundary"]


class TestRenderLossCurves:
    """Tests for render_loss_curves function."""

    def test_render_empty_history(self, empty_history):
        """Test rendering empty history shows message."""
        from temper_placer.visualization.loss_plots import render_loss_curves

        fig = render_loss_curves(empty_history)

        # Should have annotation with "No training data"
        assert len(fig.layout.annotations) > 0
        assert "No training data" in fig.layout.annotations[0].text

    def test_render_simple_history(self, simple_history):
        """Test rendering simple history."""
        from temper_placer.visualization.loss_plots import render_loss_curves

        fig = render_loss_curves(simple_history)

        # Should have at least total loss trace
        assert len(fig.data) >= 1
        assert fig.data[0].name == "Total Loss"

    def test_render_with_breakdown(self, simple_history):
        """Test rendering with term breakdown."""
        from temper_placer.visualization.loss_plots import render_loss_curves

        fig = render_loss_curves(simple_history, show_breakdown=True)

        # Should have total + breakdown traces
        trace_names = [t.name for t in fig.data]
        assert "Total Loss" in trace_names
        # Breakdown traces exist but may be hidden
        assert len(fig.data) > 1

    def test_render_without_breakdown(self, simple_history):
        """Test rendering without breakdown."""
        from temper_placer.visualization.loss_plots import render_loss_curves

        fig = render_loss_curves(simple_history, show_breakdown=False)

        # Should only have total loss trace
        assert len(fig.data) == 1
        assert fig.data[0].name == "Total Loss"

    def test_render_with_phases(self, history_with_phases):
        """Test rendering with phase boundaries."""
        from temper_placer.visualization.loss_plots import render_loss_curves

        fig = render_loss_curves(history_with_phases, show_phases=True)

        # Should have vertical lines for phase boundaries
        # Phase lines are added as shapes or annotations
        assert fig.layout is not None

    def test_render_with_title(self, simple_history):
        """Test rendering with custom title."""
        from temper_placer.visualization.loss_plots import render_loss_curves

        fig = render_loss_curves(simple_history, title="Custom Title")

        assert fig.layout.title.text == "Custom Title"

    def test_render_log_scale(self, simple_history):
        """Test rendering with log scale."""
        from temper_placer.visualization.loss_plots import render_loss_curves

        fig = render_loss_curves(simple_history, log_scale=True)

        assert fig.layout.yaxis.type == "log"

    def test_render_dimensions(self, simple_history):
        """Test custom figure dimensions."""
        from temper_placer.visualization.loss_plots import render_loss_curves

        fig = render_loss_curves(simple_history, width=1000, height=500)

        assert fig.layout.width == 1000
        assert fig.layout.height == 500


class TestRenderLossBreakdownBar:
    """Tests for render_loss_breakdown_bar function."""

    def test_render_empty_history(self, empty_history):
        """Test rendering empty history."""
        from temper_placer.visualization.loss_plots import render_loss_breakdown_bar

        fig = render_loss_breakdown_bar(empty_history)

        # Should show "No data" message
        assert len(fig.layout.annotations) > 0

    def test_render_latest_epoch(self, simple_history):
        """Test rendering latest epoch by default."""
        from temper_placer.visualization.loss_plots import render_loss_breakdown_bar

        fig = render_loss_breakdown_bar(simple_history)

        # Should have bar trace
        assert len(fig.data) == 1
        assert fig.data[0].type == "bar"

    def test_render_specific_epoch(self, simple_history):
        """Test rendering specific epoch."""
        from temper_placer.visualization.loss_plots import render_loss_breakdown_bar

        fig = render_loss_breakdown_bar(simple_history, epoch=50)

        # Title should mention epoch 50
        assert "50" in fig.layout.title.text

    def test_render_no_breakdown(self):
        """Test rendering point with no breakdown."""
        from temper_placer.visualization.loss_plots import render_loss_breakdown_bar

        history = LossHistory()
        history.add_point(LossDataPoint(epoch=0, total_loss=1.0))

        fig = render_loss_breakdown_bar(history)

        # Should show "No breakdown data" message
        assert len(fig.layout.annotations) > 0


class TestRenderLossHeatmap:
    """Tests for render_loss_heatmap function."""

    def test_render_empty_history(self, empty_history):
        """Test rendering empty history."""
        from temper_placer.visualization.loss_plots import render_loss_heatmap

        fig = render_loss_heatmap(empty_history)

        # Should show message about no data
        assert len(fig.layout.annotations) > 0

    def test_render_history(self, simple_history):
        """Test rendering heatmap."""
        from temper_placer.visualization.loss_plots import render_loss_heatmap

        fig = render_loss_heatmap(simple_history)

        # Should have heatmap trace
        assert len(fig.data) == 1
        assert fig.data[0].type == "heatmap"


class TestRenderTrainingDashboard:
    """Tests for render_training_dashboard function."""

    def test_render_empty_dashboard(self, empty_history):
        """Test rendering empty dashboard."""
        from temper_placer.visualization.loss_plots import render_training_dashboard

        fig = render_training_dashboard(empty_history)

        # Should show message about no data
        assert len(fig.layout.annotations) > 0

    def test_render_full_dashboard(self, simple_history):
        """Test rendering full dashboard with data."""
        from temper_placer.visualization.loss_plots import render_training_dashboard

        fig = render_training_dashboard(simple_history)

        # Should have multiple traces
        assert len(fig.data) >= 1

    def test_dashboard_dimensions(self, simple_history):
        """Test dashboard dimensions."""
        from temper_placer.visualization.loss_plots import render_training_dashboard

        fig = render_training_dashboard(simple_history, width=1200, height=800)

        assert fig.layout.width == 1200
        assert fig.layout.height == 800


class TestLossHistoryToHtml:
    """Tests for loss_history_to_html function."""

    def test_html_output(self, simple_history):
        """Test HTML generation."""
        from temper_placer.visualization.loss_plots import loss_history_to_html

        html = loss_history_to_html(simple_history)

        assert "<html>" in html.lower()
        assert "plotly" in html.lower()

    def test_dashboard_html(self, simple_history):
        """Test dashboard HTML generation."""
        from temper_placer.visualization.loss_plots import loss_history_to_html

        html = loss_history_to_html(simple_history, dashboard=True)

        assert "<html>" in html.lower()


class TestLossHistoryToJson:
    """Tests for loss_history_to_json function."""

    def test_json_output(self, simple_history):
        """Test JSON generation."""
        from temper_placer.visualization.loss_plots import loss_history_to_json

        json_str = loss_history_to_json(simple_history)

        # Should be valid JSON
        data = json.loads(json_str)
        assert "data" in data
        assert "layout" in data

    def test_dashboard_json(self, simple_history):
        """Test dashboard JSON generation."""
        from temper_placer.visualization.loss_plots import loss_history_to_json

        json_str = loss_history_to_json(simple_history, dashboard=True)

        data = json.loads(json_str)
        assert "data" in data
