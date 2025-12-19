"""
Tests for board renderer.

Tests the Plotly board rendering functions. Tests are skipped if Plotly
is not installed.
"""

import json

import pytest

from temper_placer.visualization.board_renderer import (
    PLOTLY_AVAILABLE,
    STATUS_COLORS,
    ZONE_COLORS,
    create_component_annotations,
    create_component_hover_data,
    get_component_shape,
    get_rectangle_shape,
    get_zone_shape,
)
from temper_placer.visualization.model import (
    BoardView,
    ComponentStatus,
    ComponentView,
    ConstraintStatus,
    Point,
    Violation,
    ViolationType,
    ZoneView,
    create_board_view_from_state,
)

# Skip all tests in this module if Plotly is not available
pytestmark = pytest.mark.skipif(
    not PLOTLY_AVAILABLE,
    reason="Plotly not installed",
)


@pytest.fixture
def simple_board() -> BoardView:
    """Create a simple board for testing."""
    return create_board_view_from_state(
        board_width=100.0,
        board_height=80.0,
        component_refs=["U1", "R1", "C1"],
        positions=[(20, 30), (50, 40), (70, 60)],
        rotations=[0, 90, 180],
        bounds=[(10, 8), (4, 2), (3, 3)],
        footprints=["QFN-48", "0805", "0603"],
        statuses=[ComponentStatus.OK, ComponentStatus.WARNING, ComponentStatus.ERROR],
    )


@pytest.fixture
def board_with_zones() -> BoardView:
    """Create a board with zones for testing."""
    comp = ComponentView(
        ref="U1",
        position=Point(50, 40),
        rotation=0,
        width=10,
        height=8,
    )
    zone1 = ZoneView(
        name="HV_KEEPOUT",
        polygon=(Point(0, 0), Point(30, 0), Point(30, 30), Point(0, 30)),
        zone_type="keepout",
    )
    zone2 = ZoneView(
        name="GROUND",
        polygon=(Point(70, 50), Point(100, 50), Point(100, 80), Point(70, 80)),
        zone_type="ground",
        color="#00FF00",
    )
    return BoardView(
        width=100,
        height=80,
        components=(comp,),
        zones=(zone1, zone2),
        title="Test Board with Zones",
    )


class TestStatusColors:
    """Tests for status color mapping."""

    def test_all_statuses_have_colors(self):
        """Test all ComponentStatus values have colors defined."""
        for status in ComponentStatus:
            assert status in STATUS_COLORS
            assert STATUS_COLORS[status].startswith("#")


class TestZoneColors:
    """Tests for zone color mapping."""

    def test_standard_zones_have_colors(self):
        """Test standard zone types have colors."""
        expected_zones = ["keepout", "copper", "ground", "hv", "generic"]
        for zone_type in expected_zones:
            assert zone_type in ZONE_COLORS


class TestGetRectangleShape:
    """Tests for get_rectangle_shape function."""

    def test_basic_rectangle(self):
        """Test creating a basic rectangle shape."""
        from temper_placer.visualization.model import Rectangle

        rect = Rectangle(center=Point(50, 40), width=10, height=8, rotation=0)
        shape = get_rectangle_shape(rect, fill_color="#FF0000")

        assert shape["type"] == "path"
        assert shape["fillcolor"] == "#FF0000"
        assert "M" in shape["path"]
        assert "L" in shape["path"]
        assert "Z" in shape["path"]

    def test_rectangle_with_rotation(self):
        """Test creating a rotated rectangle shape."""
        from temper_placer.visualization.model import Rectangle

        rect = Rectangle(center=Point(50, 40), width=10, height=8, rotation=45)
        shape = get_rectangle_shape(rect, fill_color="#00FF00", line_width=2.0)

        assert shape["type"] == "path"
        assert shape["line"]["width"] == 2.0


class TestGetComponentShape:
    """Tests for get_component_shape function."""

    def test_ok_component(self):
        """Test shape for OK status component."""
        comp = ComponentView(
            ref="U1",
            position=Point(50, 40),
            rotation=0,
            width=10,
            height=8,
            status=ComponentStatus.OK,
        )
        shape = get_component_shape(comp)

        assert shape["fillcolor"] == STATUS_COLORS[ComponentStatus.OK]
        assert shape["line"]["width"] == 1.0

    def test_error_component(self):
        """Test shape for ERROR status component has thicker border."""
        comp = ComponentView(
            ref="U1",
            position=Point(50, 40),
            rotation=0,
            width=10,
            height=8,
            status=ComponentStatus.ERROR,
        )
        shape = get_component_shape(comp)

        assert shape["fillcolor"] == STATUS_COLORS[ComponentStatus.ERROR]
        assert shape["line"]["width"] == 2.0
        assert shape["line"]["color"] == "#FF0000"

    def test_no_status_color(self):
        """Test shape without status coloring."""
        comp = ComponentView(
            ref="U1",
            position=Point(50, 40),
            rotation=0,
            width=10,
            height=8,
            status=ComponentStatus.ERROR,
        )
        shape = get_component_shape(comp, show_status_color=False)

        # Should use default blue instead of error red
        assert shape["fillcolor"] == "#4A90D9"


class TestGetZoneShape:
    """Tests for get_zone_shape function."""

    def test_keepout_zone(self):
        """Test shape for keepout zone."""
        zone = ZoneView(
            name="KEEPOUT",
            polygon=(Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)),
            zone_type="keepout",
        )
        shape = get_zone_shape(zone)

        assert shape["type"] == "path"
        assert shape["fillcolor"] == ZONE_COLORS["keepout"]
        assert shape["layer"] == "below"

    def test_custom_color_zone(self):
        """Test shape with custom color."""
        zone = ZoneView(
            name="CUSTOM",
            polygon=(Point(0, 0), Point(10, 0), Point(10, 10)),
            zone_type="unknown",
            color="#AABBCC",
        )
        shape = get_zone_shape(zone)

        assert shape["fillcolor"] == "#AABBCC"

    def test_empty_zone(self):
        """Test empty zone returns empty dict."""
        zone = ZoneView(name="EMPTY", polygon=())
        shape = get_zone_shape(zone)

        assert shape == {}


class TestCreateComponentAnnotations:
    """Tests for create_component_annotations function."""

    def test_annotations_created(self, simple_board):
        """Test annotations are created for components."""
        annotations = create_component_annotations(simple_board.components)

        assert len(annotations) == 3
        refs = [a["text"] for a in annotations]
        assert "U1" in refs
        assert "R1" in refs
        assert "C1" in refs

    def test_annotations_positions(self, simple_board):
        """Test annotations are at component positions."""
        annotations = create_component_annotations(simple_board.components)

        # Find U1 annotation
        u1_ann = next(a for a in annotations if a["text"] == "U1")
        assert u1_ann["x"] == 20
        assert u1_ann["y"] == 30

    def test_no_annotations_when_disabled(self, simple_board):
        """Test no annotations when show_refs=False."""
        annotations = create_component_annotations(simple_board.components, show_refs=False)
        assert annotations == []


class TestCreateComponentHoverData:
    """Tests for create_component_hover_data function."""

    def test_hover_data_created(self, simple_board):
        """Test hover data is created for all components."""
        x, y, texts = create_component_hover_data(simple_board.components)

        assert len(x) == 3
        assert len(y) == 3
        assert len(texts) == 3

    def test_hover_text_content(self, simple_board):
        """Test hover text contains expected information."""
        _, _, texts = create_component_hover_data(simple_board.components)

        # First component is U1
        u1_text = texts[0]
        assert "<b>U1</b>" in u1_text
        assert "Position:" in u1_text
        assert "Size:" in u1_text
        assert "Rotation:" in u1_text
        assert "Footprint: QFN-48" in u1_text

    def test_hover_text_with_violations(self):
        """Test hover text includes violations."""
        comp = ComponentView(
            ref="U1",
            position=Point(50, 40),
            rotation=0,
            width=10,
            height=8,
            status=ComponentStatus.ERROR,
            violations=("Overlaps with R1", "Too close to edge"),
        )
        _, _, texts = create_component_hover_data((comp,))

        assert "Violations" in texts[0]
        assert "Overlaps with R1" in texts[0]
        assert "Too close to edge" in texts[0]


class TestRenderBoard:
    """Tests for render_board function."""

    def test_render_simple_board(self, simple_board):
        """Test rendering a simple board."""
        from temper_placer.visualization.board_renderer import render_board

        fig = render_board(simple_board)

        # Check figure has traces and shapes
        assert len(fig.data) >= 1  # At least hover trace
        assert len(fig.layout.shapes) >= 4  # Board + 3 components

    def test_render_with_title(self, simple_board):
        """Test rendering with custom title."""
        from temper_placer.visualization.board_renderer import render_board

        fig = render_board(simple_board, title="Custom Title")

        assert fig.layout.title.text == "Custom Title"

    def test_render_with_zones(self, board_with_zones):
        """Test rendering board with zones."""
        from temper_placer.visualization.board_renderer import render_board

        fig = render_board(board_with_zones, show_zones=True)

        # Should have board outline + 2 zones + 1 component = 4 shapes
        assert len(fig.layout.shapes) >= 4

    def test_render_without_refs(self, simple_board):
        """Test rendering without reference designators."""
        from temper_placer.visualization.board_renderer import render_board

        fig = render_board(simple_board, show_refs=False)

        # Should have no annotations
        assert len(fig.layout.annotations) == 0

    def test_render_dimensions(self, simple_board):
        """Test custom figure dimensions."""
        from temper_placer.visualization.board_renderer import render_board

        fig = render_board(simple_board, width=1200, height=800)

        assert fig.layout.width == 1200
        assert fig.layout.height == 800


class TestRenderBoardWithViolations:
    """Tests for render_board_with_violations function."""

    def test_render_with_violations(self, simple_board):
        """Test rendering with violation markers."""
        from temper_placer.visualization.board_renderer import (
            render_board_with_violations,
        )

        v1 = Violation(
            violation_type=ViolationType.OVERLAP,
            severity=0.8,
            component_refs=("U1", "R1"),
            message="Components overlap",
            location=Point(35, 35),
        )
        constraints = ConstraintStatus(violations=(v1,), overlap_count=1)

        fig = render_board_with_violations(simple_board, constraints, highlight_violations=True)

        # Should have violation marker trace
        traces_with_violations = [t for t in fig.data if t.name == "Violations"]
        assert len(traces_with_violations) == 1

    def test_render_without_highlight(self, simple_board):
        """Test rendering without violation highlights."""
        from temper_placer.visualization.board_renderer import (
            render_board_with_violations,
        )

        constraints = ConstraintStatus(overlap_count=1)

        fig = render_board_with_violations(simple_board, constraints, highlight_violations=False)

        # Should not have violation marker trace
        traces_with_violations = [t for t in fig.data if t.name == "Violations"]
        assert len(traces_with_violations) == 0


class TestBoardToHtml:
    """Tests for board_to_html function."""

    def test_html_output(self, simple_board):
        """Test HTML generation."""
        from temper_placer.visualization.board_renderer import board_to_html

        html = board_to_html(simple_board)

        assert "<html>" in html.lower()
        assert "plotly" in html.lower()

    def test_html_without_plotlyjs(self, simple_board):
        """Test HTML without embedded Plotly.js."""
        from temper_placer.visualization.board_renderer import board_to_html

        html = board_to_html(simple_board, include_plotlyjs=False)

        # Should reference CDN instead of embedded script
        assert len(html) < 100000  # Much smaller without embedded JS


class TestBoardToJson:
    """Tests for board_to_json function."""

    def test_json_output(self, simple_board):
        """Test JSON generation."""
        from temper_placer.visualization.board_renderer import board_to_json

        json_str = board_to_json(simple_board)

        # Should be valid JSON
        data = json.loads(json_str)
        assert "data" in data
        assert "layout" in data


class TestPlotlyNotAvailable:
    """Tests for handling missing Plotly."""

    @pytest.mark.skipif(PLOTLY_AVAILABLE, reason="Test for when Plotly is missing")
    def test_check_plotly_raises(self):
        """Test check_plotly_available raises ImportError."""
        from temper_placer.visualization.board_renderer import check_plotly_available

        with pytest.raises(ImportError, match="Plotly is required"):
            check_plotly_available()
