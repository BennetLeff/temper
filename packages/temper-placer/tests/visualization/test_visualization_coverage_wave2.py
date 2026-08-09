"""
Coverage-paydown wave 2 tests for visualization module.

Covers allowlisted public functions that are still zero-coverage:
- model.py: TraceView.to_dict, PadView.to_dict
- board_renderer.py: get_trace_shapes, get_pad_shapes, create_trace_hover_data,
  create_pad_hover_data, render_board_comparison
- loop_viz.py: add_loops_to_plotly, render_loop_summary_table
- server.py: LiveServer.is_paused, send_training_started/stopped/complete
"""

import pytest

from temper_placer.visualization.model import (
    BoardView,
    ComponentView,
    ConstraintStatus,
    PadView,
    Point,
    TraceView,
    ZoneView,
    create_board_view_from_state,
)
from temper_placer.visualization.config_types import BoardRenderOptions


# ============================================================================
# model.py — TraceView.to_dict, PadView.to_dict
# ============================================================================


class TestModelToDict:
    """Cover TraceView.to_dict and PadView.to_dict."""

    def test_trace_view_to_dict(self):
        trace = TraceView(
            start=Point(10, 20),
            end=Point(30, 40),
            width=0.5,
            layer="F.Cu",
            net="VCC",
        )
        d = trace.to_dict()
        assert d["start"]["x"] == 10
        assert d["start"]["y"] == 20
        assert d["end"]["x"] == 30
        assert d["end"]["y"] == 40
        assert d["width"] == 0.5
        assert d["layer"] == "F.Cu"
        assert d["net"] == "VCC"

    def test_pad_view_to_dict(self):
        pad = PadView(
            position=Point(15, 25),
            size=(1.0, 0.8),
            shape="rect",
            rotation=0,
            layer="F.Cu",
            number="1",
            net="GND",
            component_ref="U1",
        )
        d = pad.to_dict()
        assert d["position"]["x"] == 15
        assert d["position"]["y"] == 25
        assert d["size"] == [1.0, 0.8]
        assert d["shape"] == "rect"
        assert d["layer"] == "F.Cu"
        assert d["number"] == "1"
        assert d["net"] == "GND"
        assert d["component_ref"] == "U1"


# ============================================================================
# board_renderer.py — shape and hover-data functions (Plotly-dependent)
# ============================================================================


# Skip if Plotly not installed
try:
    import plotly.graph_objects as go

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

if PLOTLY_AVAILABLE:
    from temper_placer.visualization.board_renderer import (
        get_trace_shapes,
        get_pad_shapes,
        create_trace_hover_data,
        create_pad_hover_data,
        render_board_comparison,
    )

pytestmark_board_renderer = pytest.mark.skipif(
    not PLOTLY_AVAILABLE, reason="Plotly not installed"
)


@pytest.fixture
def sample_traces():
    """Tuple of TraceView for testing."""
    return (
        TraceView(
            start=Point(0, 0), end=Point(50, 50),
            width=0.3, layer="F.Cu", net="VCC",
        ),
        TraceView(
            start=Point(10, 80), end=Point(90, 20),
            width=0.5, layer="B.Cu", net="GND",
        ),
    )


@pytest.fixture
def sample_pads():
    """Tuple of PadView with varied shapes for testing."""
    return (
        PadView(
            position=Point(20, 30), size=(1.2, 0.8),
            shape="rect", layer="F.Cu", number="1",
            component_ref="U1", net="VCC",
        ),
        PadView(
            position=Point(60, 40), size=(0.8, 0.8),
            shape="circle", layer="F.Cu", number="2",
            component_ref="R1", net="GND",
        ),
        PadView(
            position=Point(80, 60), size=(1.0, 0.6),
            shape="oval", layer="B.Cu", number="3",
            component_ref="C1", net="NET1",
        ),
        PadView(
            position=Point(40, 70), size=(1.5, 1.0),
            shape="rect", layer="F.Cu", number="4",
            component_ref="U1", net="VCC", rotation=45,
        ),
        PadView(
            position=Point(10, 90), size=(0.6, 0.6),
            shape="rect", layer="*.Cu", number="5",
            component_ref="J1", net="GND",
        ),
    )


@pytest.fixture
def sample_board():
    """Simple BoardView for render tests."""
    return create_board_view_from_state(
        board_width=100.0,
        board_height=100.0,
        component_refs=["U1", "R1"],
        positions=[(20, 30), (60, 70)],
        rotations=[0, 90],
        bounds=[(10, 8), (4, 2)],
    )


@pytest.fixture
def board_with_everything(sample_traces, sample_pads):
    """BoardView with components, zones, traces, and pads."""
    comp = ComponentView(
        ref="U1", position=Point(50, 40), rotation=0,
        width=10, height=8,
    )
    comp2 = ComponentView(
        ref="R1", position=Point(80, 60), rotation=90,
        width=4, height=2,
    )
    zone = ZoneView(
        name="test_zone",
        polygon=(Point(0, 0), Point(30, 0), Point(30, 30), Point(0, 30)),
        zone_type="keepout",
    )
    return BoardView(
        width=100, height=80,
        components=(comp, comp2),
        zones=(zone,),
        traces=sample_traces,
        pads=sample_pads,
    )


class TestTraceShapes:
    """Tests for get_trace_shapes."""

    @pytestmark_board_renderer
    def test_get_trace_shapes_basic(self, sample_traces):
        shapes = get_trace_shapes(sample_traces)
        assert len(shapes) == 2
        # Each shape is a line dict
        assert shapes[0]["type"] == "line"
        assert shapes[0]["x0"] == 0
        assert shapes[0]["y0"] == 0
        assert shapes[0]["x1"] == 50
        assert shapes[0]["y1"] == 50

    @pytestmark_board_renderer
    def test_get_trace_shapes_layer_filter(self, sample_traces):
        shapes = get_trace_shapes(sample_traces, layer_filter="F.Cu")
        assert len(shapes) == 1
        # "F.Cu" color is gold
        assert shapes[0]["line"]["color"] is not None

    @pytestmark_board_renderer
    def test_get_trace_shapes_empty(self):
        shapes = get_trace_shapes(())
        assert shapes == []


class TestPadShapes:
    """Tests for get_pad_shapes — exercises rect, circle, oval, rotated rect,
    and through-hole pad paths."""

    @pytestmark_board_renderer
    def test_get_pad_shapes_basic(self, sample_pads):
        shapes = get_pad_shapes(sample_pads)
        assert len(shapes) == 5
        # First pad is rect
        assert shapes[0]["type"] == "rect"

    @pytestmark_board_renderer
    def test_get_pad_shapes_circle(self):
        """Circle pad produces a circle shape."""
        pads = (PadView(
            position=Point(50, 50), size=(1.0, 1.0),
            shape="circle", layer="F.Cu", number="1",
        ),)
        shapes = get_pad_shapes(pads)
        assert len(shapes) == 1
        assert shapes[0]["type"] == "circle"

    @pytestmark_board_renderer
    def test_get_pad_shapes_oval(self):
        """Oval pad produces a circle shape (approximation)."""
        pads = (PadView(
            position=Point(50, 50), size=(1.0, 0.5),
            shape="oval", layer="F.Cu", number="1",
        ),)
        shapes = get_pad_shapes(pads)
        assert len(shapes) == 1
        assert shapes[0]["type"] == "circle"

    @pytestmark_board_renderer
    def test_get_pad_shapes_rotated_rect(self):
        """Rotated rect pad produces a path shape."""
        pads = (PadView(
            position=Point(50, 50), size=(2.0, 1.0),
            shape="rect", layer="F.Cu", number="1", rotation=30,
        ),)
        shapes = get_pad_shapes(pads)
        assert len(shapes) == 1
        assert shapes[0]["type"] == "path"

    @pytestmark_board_renderer
    def test_get_pad_shapes_thru_hole(self):
        """Through-hole pad on *.Cu layer."""
        pads = (PadView(
            position=Point(50, 50), size=(0.8, 0.8),
            shape="rect", layer="*.Cu", number="1",
        ),)
        shapes = get_pad_shapes(pads)
        assert len(shapes) == 1

    @pytestmark_board_renderer
    def test_get_pad_shapes_layer_filter(self, sample_pads):
        """Layer filter excludes pads on other layers (through-hole passes all)."""
        shapes = get_pad_shapes(sample_pads, layer_filter="B.Cu")
        # Pad 3 (oval on B.Cu) + pad 5 (through-hole on *.Cu passes all layers)
        assert len(shapes) == 2

    @pytestmark_board_renderer
    def test_get_pad_shapes_empty(self):
        shapes = get_pad_shapes(())
        assert shapes == []


class TestHoverData:
    """Tests for create_trace_hover_data and create_pad_hover_data."""

    @pytestmark_board_renderer
    def test_create_trace_hover_data(self, sample_traces):
        x, y, texts = create_trace_hover_data(sample_traces)
        assert len(x) == 2
        assert len(y) == 2
        assert len(texts) == 2
        # Midpoint of first trace: (25, 25)
        assert x[0] == 25.0
        assert y[0] == 25.0
        assert "VCC" in texts[0]
        assert "GND" in texts[1]

    @pytestmark_board_renderer
    def test_create_pad_hover_data(self, sample_pads):
        x, y, texts = create_pad_hover_data(sample_pads)
        assert len(x) == 5
        assert len(y) == 5
        assert len(texts) == 5
        assert "U1" in texts[0]
        assert "Pad 1" in texts[0] or "Pad" in texts[0]


class TestRenderBoardComparison:
    """Test render_board_comparison."""

    @pytestmark_board_renderer
    def test_render_board_comparison_basic(self, sample_board):
        """Side-by-side comparison of identical boards."""
        fig = render_board_comparison(sample_board, sample_board)
        assert fig is not None
        # Should have 2 subplots
        assert len(fig.data) > 0

    @pytestmark_board_renderer
    def test_render_board_comparison_different(self):
        """Comparison of two different boards."""
        before = create_board_view_from_state(
            board_width=100.0, board_height=80.0,
            component_refs=["U1"],
            positions=[(10, 20)],
            rotations=[0],
            bounds=[(8, 6)],
        )
        after = create_board_view_from_state(
            board_width=100.0, board_height=80.0,
            component_refs=["U1"],
            positions=[(80, 60)],
            rotations=[90],
            bounds=[(8, 6)],
        )
        fig = render_board_comparison(before, after)
        assert fig is not None


# ============================================================================
# loop_viz.py — add_loops_to_plotly, render_loop_summary_table
# ============================================================================


# Skip if Plotly not installed
pytestmark_loop_viz = pytest.mark.skipif(
    not PLOTLY_AVAILABLE, reason="Plotly not installed"
)


@pytest.fixture
def board_for_loop():
    """BoardView with components and pads for loop testing."""
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
    pad3 = PadView(
        position=Point(60, 10), size=(1.0, 1.0),
        shape="rect", layer="F.Cu", number="2",
        component_ref="Q1", net="GND",
    )
    pad4 = PadView(
        position=Point(20, 10), size=(1.0, 1.0),
        shape="rect", layer="F.Cu", number="2",
        component_ref="U1", net="GND",
    )
    return BoardView(
        width=100, height=80,
        components=(comp, comp2),
        pads=(pad1, pad2, pad3, pad4),
    )


class TestLoopViz:
    """Tests for loop visualization functions."""

    @pytestmark_loop_viz
    def test_add_loops_to_plotly(self, board_for_loop):
        """add_loops_to_plotly adds loop traces to a Plotly figure."""
        from temper_placer.core.loop import (
            Loop,
            LoopCollection,
            LoopEvent,
            LoopPriority,
            LoopType,
            LoopPin,
        )
        from temper_placer.visualization.loop_viz import add_loops_to_plotly

        # Create a loop with explicit pins that match pad positions
        loop = Loop(
            name="test_loop",
            loop_type=LoopType("commutation"),
            description="A test commutaton loop",
            components=["U1", "Q1"],
            max_area_mm2=100.0,
            priority=LoopPriority("critical"),
            events=LoopEvent(di_dt=1e9, frequency_hz=50000),
            pins=[
                LoopPin("U1", "1"),
                LoopPin("Q1", "1"),
                LoopPin("Q1", "2"),
                LoopPin("U1", "2"),
            ],
        )
        collection = LoopCollection()
        collection.add_loop(loop)

        fig = go.Figure()
        add_loops_to_plotly(fig, collection, board_for_loop)
        # A trace should have been added
        assert len(fig.data) > 0

    @pytestmark_loop_viz
    def test_render_loop_summary_table(self, board_for_loop):
        """render_loop_summary_table returns an HTML string."""
        from temper_placer.core.loop import (
            Loop,
            LoopCollection,
            LoopEvent,
            LoopPriority,
            LoopType,
        )
        from temper_placer.visualization.loop_viz import render_loop_summary_table

        loop = Loop(
            name="test_loop",
            loop_type=LoopType("commutation"),
            description="Test",
            components=["U1"],
            max_area_mm2=50.0,
            priority=LoopPriority("critical"),
            events=LoopEvent(di_dt=1e9, frequency_hz=50000),
        )
        collection = LoopCollection()
        collection.add_loop(loop)

        html = render_loop_summary_table(collection, board_for_loop)
        assert isinstance(html, str)
        assert "test_loop" in html
        assert "Loop Analysis" in html
        assert "commutation" in html


# ============================================================================
# server.py — LiveServer (require websockets)
# ============================================================================


# Check websockets availability
try:
    import websockets  # noqa: F401

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

pytestmark_server = pytest.mark.skipif(
    not WEBSOCKETS_AVAILABLE, reason="websockets not installed"
)


class TestLiveServer:
    """Tests for LiveServer uncovered methods."""

    @pytestmark_server
    def test_is_paused_default(self):
        """LiveServer.is_paused is False by default."""
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(port=0, open_browser=False)
        assert server.is_paused is False

    @pytestmark_server
    def test_is_paused_after_pause(self):
        """LiveServer.is_paused reflects state."""
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(port=0, open_browser=False)
        server.state.is_paused = True
        assert server.is_paused is True

    @pytestmark_server
    def test_send_training_started_not_running(self):
        """send_training_started is a no-op when server not running."""
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(port=0, open_browser=False)
        # Should not raise; is a no-op when not running
        server.send_training_started()

    @pytestmark_server
    def test_send_training_stopped_not_running(self):
        """send_training_stopped is a no-op when server not running."""
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(port=0, open_browser=False)
        server.send_training_stopped()

    @pytestmark_server
    def test_send_training_complete_not_running(self):
        """send_training_complete is a no-op when server not running."""
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(port=0, open_browser=False)
        server.send_training_complete()

    @pytestmark_server
    def test_client_count(self):
        """client_count returns 0 with no connections."""
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(port=0, open_browser=False)
        assert server.client_count == 0

    @pytestmark_server
    def test_url_property(self):
        """url returns correct HTTP URL."""
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(host="127.0.0.1", port=9999, open_browser=False)
        assert server.url == "http://127.0.0.1:9999"

    @pytestmark_server
    def test_ws_url_property(self):
        """ws_url returns correct WebSocket URL."""
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(host="127.0.0.1", port=9999, open_browser=False)
        assert server.ws_url == "ws://127.0.0.1:9999/ws"
