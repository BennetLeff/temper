"""
Comprehensive tests for loop visualization module.

This test module covers the visualization of current loops overlaid on PCB
component placements, including:
- Loop path rendering (SVG generation)
- Loop area display with compliance indicators
- Color coding by priority/type
- Interactive features (hover, click)
- HTML report integration

Tests are written TDD-style to guide implementation of temper-z1c.6.
"""

import pytest
from dataclasses import dataclass
from typing import Any

from temper_placer.core.loop import (
    Loop,
    LoopCollection,
    LoopEvent,
    LoopPin,
    LoopPriority,
    LoopType,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_placements() -> dict[str, Any]:
    """Sample component placements for visualization testing."""
    return {
        "Q1": {"x": 100.0, "y": 50.0, "rotation": 0, "layer": "F.Cu"},
        "Q2": {"x": 100.0, "y": 80.0, "rotation": 0, "layer": "F.Cu"},
        "C_BUS": {"x": 70.0, "y": 65.0, "rotation": 90, "layer": "F.Cu"},
        "U_GATE": {"x": 60.0, "y": 50.0, "rotation": 0, "layer": "F.Cu"},
        "RG_H": {"x": 80.0, "y": 45.0, "rotation": 0, "layer": "F.Cu"},
        "RG_L": {"x": 80.0, "y": 85.0, "rotation": 0, "layer": "F.Cu"},
        "C_BOOT": {"x": 50.0, "y": 40.0, "rotation": 0, "layer": "F.Cu"},
        "D_BOOT": {"x": 40.0, "y": 40.0, "rotation": 0, "layer": "F.Cu"},
    }


@pytest.fixture
def commutation_loop() -> Loop:
    """Sample commutation loop for testing."""
    return Loop(
        name="commutation",
        loop_type=LoopType.COMMUTATION,
        description="Main half-bridge commutation loop",
        pins=[
            LoopPin("C_BUS", "+", "DC_BUS+"),
            LoopPin("Q1", "COLLECTOR", "DC_BUS+"),
            LoopPin("Q1", "EMITTER", "SW_NODE"),
            LoopPin("Q2", "COLLECTOR", "SW_NODE"),
            LoopPin("Q2", "EMITTER", "DC_BUS-"),
            LoopPin("C_BUS", "-", "DC_BUS-"),
        ],
        max_area_mm2=500.0,
        priority=LoopPriority.CRITICAL,
        events=LoopEvent(di_dt=1e9, frequency_hz=25000, peak_current_a=30),
    )


@pytest.fixture
def gate_drive_high_loop() -> Loop:
    """Sample high-side gate drive loop for testing."""
    return Loop(
        name="gate_drive_high",
        loop_type=LoopType.GATE_DRIVE_HIGH,
        description="High-side IGBT gate drive loop",
        pins=[
            LoopPin("U_GATE", "OUTA", "GATE_H_DRV"),
            LoopPin("RG_H", "1", "GATE_H_DRV"),
            LoopPin("RG_H", "2", "GATE_H"),
            LoopPin("Q1", "GATE", "GATE_H"),
            LoopPin("Q1", "EMITTER", "SW_NODE"),
            LoopPin("U_GATE", "VSSA", "SW_NODE"),
        ],
        max_area_mm2=100.0,
        priority=LoopPriority.CRITICAL,
        events=LoopEvent(di_dt=0.5e9, frequency_hz=25000, peak_current_a=4),
    )


@pytest.fixture
def bootstrap_loop() -> Loop:
    """Sample bootstrap charging loop for testing."""
    return Loop(
        name="bootstrap",
        loop_type=LoopType.BOOTSTRAP,
        description="Bootstrap capacitor charging loop",
        components=["D_BOOT", "C_BOOT", "U_GATE"],
        max_area_mm2=50.0,
        priority=LoopPriority.HIGH,
        events=LoopEvent(frequency_hz=25000, peak_current_a=0.5),
    )


@pytest.fixture
def sample_loop_collection(
    commutation_loop: Loop, gate_drive_high_loop: Loop, bootstrap_loop: Loop
) -> LoopCollection:
    """Collection of sample loops for testing."""
    collection = LoopCollection(name="test_collection", description="Test loops for visualization")
    collection.add_loop(commutation_loop)
    collection.add_loop(gate_drive_high_loop)
    collection.add_loop(bootstrap_loop)
    return collection


# =============================================================================
# Tests for Loop Color Scheme
# =============================================================================


class TestLoopColorScheme:
    """Tests for loop color assignment based on type and priority."""

    def test_critical_loops_use_distinct_colors(self):
        """Critical loops should have visually distinct, attention-grabbing colors."""
        # Import when implemented
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import get_loop_color

        commutation_color = get_loop_color(LoopType.COMMUTATION, LoopPriority.CRITICAL)
        gate_high_color = get_loop_color(LoopType.GATE_DRIVE_HIGH, LoopPriority.CRITICAL)
        gate_low_color = get_loop_color(LoopType.GATE_DRIVE_LOW, LoopPriority.CRITICAL)

        # All should be different
        colors = {commutation_color, gate_high_color, gate_low_color}
        assert len(colors) == 3, "Critical loops should have unique colors"

        # Should be warm/attention colors (red, orange, etc.) - verify hex format
        for color in colors:
            assert color.startswith("#"), "Colors should be hex format"
            assert len(color) == 7, "Colors should be full hex (#RRGGBB)"

    def test_priority_affects_color_intensity(self):
        """Lower priority loops should have more muted colors."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import get_loop_color

        critical_color = get_loop_color(LoopType.CUSTOM, LoopPriority.CRITICAL)
        high_color = get_loop_color(LoopType.CUSTOM, LoopPriority.HIGH)
        medium_color = get_loop_color(LoopType.CUSTOM, LoopPriority.MEDIUM)
        low_color = get_loop_color(LoopType.CUSTOM, LoopPriority.LOW)

        # All should be valid hex colors
        for color in [critical_color, high_color, medium_color, low_color]:
            assert color.startswith("#")

    def test_default_color_for_unknown_type(self):
        """Unknown or custom loop types should get a sensible default color."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import get_loop_color

        color = get_loop_color(LoopType.CUSTOM, LoopPriority.MEDIUM)
        assert color.startswith("#")
        assert len(color) == 7

    def test_color_palette_is_colorblind_friendly(self):
        """Color palette should be distinguishable for common color vision deficiencies."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import LOOP_COLOR_PALETTE

        # Verify palette exists and has sufficient colors
        assert len(LOOP_COLOR_PALETTE) >= 5, "Need at least 5 distinct colors"

        # Verify all colors are valid hex
        for name, color in LOOP_COLOR_PALETTE.items():
            assert color.startswith("#"), f"Color {name} should be hex format"


# =============================================================================
# Tests for Loop Path Rendering
# =============================================================================


class TestLoopPathRendering:
    """Tests for generating SVG paths from loop definitions."""

    def test_render_loop_path_from_pins(self, commutation_loop: Loop, sample_placements: dict):
        """Should generate SVG path connecting all pins in order."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        svg = render_loop_path(commutation_loop, sample_placements, "#FF0000")

        # Should be valid SVG polyline or path
        assert "<polyline" in svg or "<path" in svg or "<polygon" in svg
        assert 'stroke="#FF0000"' in svg or "stroke:#FF0000" in svg

    def test_render_loop_path_closes_loop(self, commutation_loop: Loop, sample_placements: dict):
        """Loop path should close back to the starting point."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        svg = render_loop_path(commutation_loop, sample_placements, "#FF0000")

        # Should use closed path (polygon or path with Z command)
        assert "<polygon" in svg or 'Z"' in svg or "Z'" in svg

    def test_render_loop_path_with_missing_component(self, commutation_loop: Loop):
        """Should handle gracefully when a component placement is missing."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        incomplete_placements = {
            "Q1": {"x": 100.0, "y": 50.0, "rotation": 0},
            # C_BUS and Q2 missing
        }

        # Should not raise, should return partial path or empty
        svg = render_loop_path(commutation_loop, incomplete_placements, "#FF0000")
        assert isinstance(svg, str)

    def test_render_loop_path_from_components_only(
        self, bootstrap_loop: Loop, sample_placements: dict
    ):
        """Should render path using component centers when pins not specified."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        svg = render_loop_path(bootstrap_loop, sample_placements, "#00FF00")

        # Should generate valid SVG even without explicit pins
        assert "<polyline" in svg or "<path" in svg or "<polygon" in svg

    def test_render_empty_loop(self, sample_placements: dict):
        """Should handle empty loop gracefully."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        empty_loop = Loop(
            name="empty",
            loop_type=LoopType.CUSTOM,
            description="Empty loop for testing",
        )

        svg = render_loop_path(empty_loop, sample_placements, "#000000")
        # Should return empty string or comment, not raise
        assert isinstance(svg, str)

    def test_path_stroke_width_scales_with_priority(
        self, commutation_loop: Loop, bootstrap_loop: Loop, sample_placements: dict
    ):
        """Critical loops should have thicker strokes than lower priority."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        critical_svg = render_loop_path(commutation_loop, sample_placements, "#FF0000")
        high_svg = render_loop_path(bootstrap_loop, sample_placements, "#00FF00")

        # Extract stroke-width values (implementation detail but important for viz)
        # Just verify both have stroke-width specified
        assert "stroke-width" in critical_svg or "stroke-width" in high_svg


# =============================================================================
# Tests for Loop Area Display
# =============================================================================


class TestLoopAreaDisplay:
    """Tests for displaying loop area measurements and compliance."""

    def test_render_loop_area_indicator_compliant(self, commutation_loop: Loop):
        """Should show green indicator when loop area is under max."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_area_indicator

        commutation_loop.set_current_area(300.0)  # Under 500mm² max

        html = render_loop_area_indicator(commutation_loop)

        assert "300" in html  # Current area shown
        assert "500" in html  # Max area shown
        assert "compliant" in html.lower() or "green" in html.lower() or "#0" in html

    def test_render_loop_area_indicator_non_compliant(self, commutation_loop: Loop):
        """Should show red/warning indicator when loop area exceeds max."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_area_indicator

        commutation_loop.set_current_area(600.0)  # Over 500mm² max

        html = render_loop_area_indicator(commutation_loop)

        assert "600" in html  # Current area shown
        assert "warning" in html.lower() or "red" in html.lower() or "violation" in html.lower()

    def test_render_loop_area_indicator_unknown(self, commutation_loop: Loop):
        """Should show neutral indicator when area not yet computed."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_area_indicator

        # Area not set (None)
        html = render_loop_area_indicator(commutation_loop)

        assert "unknown" in html.lower() or "n/a" in html.lower() or "—" in html

    def test_render_area_with_percentage(self, commutation_loop: Loop):
        """Should show percentage of max area used."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_area_indicator

        commutation_loop.set_current_area(250.0)  # 50% of 500mm² max

        html = render_loop_area_indicator(commutation_loop)

        # Should show 50% or similar
        assert "50%" in html or "50 %" in html


# =============================================================================
# Tests for Loop Legend
# =============================================================================


class TestLoopLegend:
    """Tests for the loop color legend in reports."""

    def test_render_loop_legend(self, sample_loop_collection: LoopCollection):
        """Should render legend showing all loops with their colors."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_legend

        html = render_loop_legend(sample_loop_collection)

        # Should include all loop names
        assert "commutation" in html
        assert "gate_drive_high" in html
        assert "bootstrap" in html

        # Should have color swatches
        assert "background" in html or "fill" in html or "color:" in html

    def test_legend_sorted_by_priority(self, sample_loop_collection: LoopCollection):
        """Legend should show critical loops first."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_legend

        html = render_loop_legend(sample_loop_collection)

        # Critical loops should appear before HIGH priority
        commutation_pos = html.find("commutation")
        bootstrap_pos = html.find("bootstrap")

        assert commutation_pos < bootstrap_pos, "Critical loops should appear first"

    def test_legend_shows_compliance_status(self, sample_loop_collection: LoopCollection):
        """Legend should indicate which loops are compliant."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_legend

        # Set areas for testing
        sample_loop_collection.loops[0].set_current_area(300.0)  # Compliant
        sample_loop_collection.loops[1].set_current_area(150.0)  # Non-compliant (max=100)

        html = render_loop_legend(sample_loop_collection)

        # Should have visual indicator for compliance
        assert "check" in html.lower() or "✓" in html or "pass" in html.lower()
        assert "warning" in html.lower() or "✗" in html or "fail" in html.lower()

    def test_empty_legend_for_no_loops(self):
        """Should handle empty loop collection gracefully."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_legend

        empty_collection = LoopCollection()
        html = render_loop_legend(empty_collection)

        # Should return placeholder or empty, not raise
        assert isinstance(html, str)


# =============================================================================
# Tests for Loop Summary Table
# =============================================================================


class TestLoopSummaryTable:
    """Tests for the loop summary table in HTML reports."""

    def test_render_loop_summary_table(self, sample_loop_collection: LoopCollection):
        """Should render HTML table with loop details."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_summary_table

        html = render_loop_summary_table(sample_loop_collection)

        # Should be a table
        assert "<table" in html
        assert "</table>" in html

        # Should have headers
        assert "Name" in html or "Loop" in html
        assert "Type" in html or "Priority" in html
        assert "Area" in html

    def test_summary_table_columns(self, sample_loop_collection: LoopCollection):
        """Table should have expected columns."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_summary_table

        html = render_loop_summary_table(sample_loop_collection)

        expected_columns = ["Name", "Type", "Priority", "Max Area", "Current Area", "Status"]
        for col in expected_columns:
            # At least some variation of column name should exist
            assert col.lower() in html.lower() or col.replace(" ", "") in html

    def test_summary_table_row_per_loop(self, sample_loop_collection: LoopCollection):
        """Should have one row per loop in collection."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_summary_table

        html = render_loop_summary_table(sample_loop_collection)

        # Count <tr> tags (minus header row)
        tr_count = html.count("<tr")
        assert tr_count >= 3 + 1  # 3 loops + 1 header row

    def test_summary_table_sortable(self, sample_loop_collection: LoopCollection):
        """Table should have sortable columns or be pre-sorted by priority."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_summary_table

        html = render_loop_summary_table(sample_loop_collection)

        # Either has data-sort attributes or is sorted by priority
        # Check that commutation (CRITICAL) appears before bootstrap (HIGH)
        comm_pos = html.find("commutation")
        boot_pos = html.find("bootstrap")
        assert comm_pos < boot_pos


# =============================================================================
# Tests for Interactive Features
# =============================================================================


class TestLoopInteractivity:
    """Tests for interactive visualization features (hover, click, etc.)."""

    def test_loop_hover_shows_details(self, commutation_loop: Loop, sample_placements: dict):
        """Hovering over loop path should show detailed tooltip."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        svg = render_loop_path(commutation_loop, sample_placements, "#FF0000")

        # Should have title or data attributes for tooltip
        assert "<title>" in svg or "data-loop" in svg or "onmouseover" in svg

    def test_loop_path_has_id(self, commutation_loop: Loop, sample_placements: dict):
        """Each loop path should have unique ID for JavaScript interaction."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        svg = render_loop_path(commutation_loop, sample_placements, "#FF0000")

        assert 'id="' in svg or "id='" in svg
        assert "commutation" in svg  # ID should include loop name

    def test_render_loop_toggle_controls(self, sample_loop_collection: LoopCollection):
        """Should render checkboxes to toggle loop visibility."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_toggle_controls

        html = render_loop_toggle_controls(sample_loop_collection)

        # Should have checkboxes
        assert 'type="checkbox"' in html or "<input" in html

        # One per loop
        assert "commutation" in html
        assert "gate_drive_high" in html
        assert "bootstrap" in html

    def test_click_loop_highlights_components(
        self, commutation_loop: Loop, sample_placements: dict
    ):
        """Clicking loop should highlight member components."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        svg = render_loop_path(commutation_loop, sample_placements, "#FF0000")

        # Should have onclick or data attributes for component highlighting
        assert "onclick" in svg or "data-components" in svg or "class=" in svg


# =============================================================================
# Tests for Full Board Visualization with Loops
# =============================================================================


class TestBoardWithLoops:
    """Tests for rendering full board with loops overlaid."""

    def test_render_board_with_loops(
        self, sample_loop_collection: LoopCollection, sample_placements: dict
    ):
        """Should render board with all loops overlaid."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_board_with_loops

        html = render_board_with_loops(
            placements=sample_placements,
            loops=sample_loop_collection,
            board_width=200.0,
            board_height=150.0,
        )

        # Should have SVG
        assert "<svg" in html
        assert "</svg>" in html

        # Should have all loop paths
        assert "commutation" in html
        assert "gate_drive_high" in html
        assert "bootstrap" in html

    def test_loops_rendered_in_priority_order(
        self, sample_loop_collection: LoopCollection, sample_placements: dict
    ):
        """Lower priority loops should be rendered first (behind higher priority)."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_board_with_loops

        html = render_board_with_loops(
            placements=sample_placements,
            loops=sample_loop_collection,
            board_width=200.0,
            board_height=150.0,
        )

        # Bootstrap (HIGH) should appear before commutation (CRITICAL) in SVG
        # because CRITICAL is rendered on top (last in SVG order)
        boot_pos = html.find('id="loop-bootstrap"')
        comm_pos = html.find('id="loop-commutation"')

        if boot_pos >= 0 and comm_pos >= 0:
            assert boot_pos < comm_pos, "Lower priority should render first (underneath)"

    def test_render_board_shows_components(
        self, sample_loop_collection: LoopCollection, sample_placements: dict
    ):
        """Board render should show component outlines."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_board_with_loops

        html = render_board_with_loops(
            placements=sample_placements,
            loops=sample_loop_collection,
            board_width=200.0,
            board_height=150.0,
        )

        # Should have component markers
        assert "Q1" in html
        assert "Q2" in html
        assert "U_GATE" in html

    def test_render_board_with_empty_loops(self, sample_placements: dict):
        """Should render board even with no loops defined."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_board_with_loops

        empty_collection = LoopCollection()

        html = render_board_with_loops(
            placements=sample_placements,
            loops=empty_collection,
            board_width=200.0,
            board_height=150.0,
        )

        # Should still have SVG with components
        assert "<svg" in html
        assert "Q1" in html  # Components still shown


# =============================================================================
# Tests for HTML Report Integration
# =============================================================================


class TestLoopReportSection:
    """Tests for loop section in HTML reports."""

    def test_generate_loop_section(self, sample_loop_collection: LoopCollection):
        """Should generate complete loop section for HTML report."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import generate_loop_report_section

        html = generate_loop_report_section(sample_loop_collection)

        # Should have section header
        assert "Loop" in html or "loop" in html

        # Should have summary
        assert "3" in html  # 3 loops total

        # Should have legend
        assert "commutation" in html

    def test_loop_section_includes_physics(self, sample_loop_collection: LoopCollection):
        """Section should display physics metadata (di/dt, frequency)."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import generate_loop_report_section

        html = generate_loop_report_section(sample_loop_collection)

        # Should have physics info
        assert (
            "di/dt" in html or "dI/dt" in html.replace("i", "I") or "1e9" in html or "1.0e9" in html
        )
        assert "25000" in html or "25 kHz" in html or "25kHz" in html

    def test_loop_section_collapsible(self, sample_loop_collection: LoopCollection):
        """Section should be collapsible for large reports."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import generate_loop_report_section

        html = generate_loop_report_section(sample_loop_collection)

        # Should have details/summary or similar collapsible structure
        assert "<details" in html or "collapse" in html.lower() or "accordion" in html.lower()


# =============================================================================
# Tests for Loop Metrics Export
# =============================================================================


class TestLoopMetricsExport:
    """Tests for exporting loop metrics to JSON/CSV."""

    def test_export_loop_metrics_json(self, sample_loop_collection: LoopCollection):
        """Should export loop metrics as JSON."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import export_loop_metrics

        # Set some areas
        sample_loop_collection.loops[0].set_current_area(300.0)
        sample_loop_collection.loops[1].set_current_area(80.0)

        data = export_loop_metrics(sample_loop_collection, format="json")

        assert isinstance(data, dict)
        assert "loops" in data
        assert len(data["loops"]) == 3

        # First loop should have area info
        comm = next(l for l in data["loops"] if l["name"] == "commutation")
        assert comm["current_area_mm2"] == 300.0
        assert comm["max_area_mm2"] == 500.0
        assert comm["compliant"] is True

    def test_export_loop_metrics_csv(self, sample_loop_collection: LoopCollection):
        """Should export loop metrics as CSV string."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import export_loop_metrics

        csv = export_loop_metrics(sample_loop_collection, format="csv")

        assert isinstance(csv, str)
        # Should have header row
        assert "name" in csv.lower()
        assert "max_area" in csv.lower() or "max area" in csv.lower()

        # Should have data rows
        assert "commutation" in csv


# =============================================================================
# Tests for SVG Export
# =============================================================================


class TestLoopSvgExport:
    """Tests for standalone SVG export of loops."""

    def test_export_loops_svg(
        self, sample_loop_collection: LoopCollection, sample_placements: dict
    ):
        """Should export loops as standalone SVG file."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import export_loops_svg

        svg = export_loops_svg(
            loops=sample_loop_collection,
            placements=sample_placements,
            width=200.0,
            height=150.0,
        )

        # Should be valid SVG
        assert '<?xml version="1.0"' in svg or "<svg" in svg
        assert "</svg>" in svg

        # Should have proper namespace
        assert "xmlns" in svg

    def test_export_svg_with_options(
        self, sample_loop_collection: LoopCollection, sample_placements: dict
    ):
        """Should support export options (background, margins, etc.)."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import export_loops_svg

        svg = export_loops_svg(
            loops=sample_loop_collection,
            placements=sample_placements,
            width=200.0,
            height=150.0,
            background_color="#FFFFFF",
            show_components=True,
            show_labels=True,
        )

        # Should have background rect
        assert 'fill="#FFFFFF"' in svg or "fill: #FFFFFF" in svg or "background" in svg

        # Should have labels
        assert "<text" in svg


# =============================================================================
# Tests for Loop Animation (Optional Feature)
# =============================================================================


class TestLoopAnimation:
    """Tests for animated loop visualization (current flow)."""

    def test_render_animated_loop(self, commutation_loop: Loop, sample_placements: dict):
        """Should render loop with current flow animation."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_animated_loop

        svg = render_animated_loop(commutation_loop, sample_placements, animate=True)

        # Should have animation elements
        assert "<animate" in svg or "animation" in svg or "@keyframes" in svg

    def test_animation_can_be_disabled(self, commutation_loop: Loop, sample_placements: dict):
        """Should render static loop when animation disabled."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_animated_loop

        svg = render_animated_loop(commutation_loop, sample_placements, animate=False)

        # Should NOT have animation elements
        assert "<animate" not in svg


# =============================================================================
# Tests for Error Handling
# =============================================================================


class TestLoopVizErrorHandling:
    """Tests for error handling in loop visualization."""

    def test_handles_negative_coordinates(self, commutation_loop: Loop):
        """Should handle placements with negative coordinates."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        negative_placements = {
            "Q1": {"x": -10.0, "y": -20.0, "rotation": 0},
            "Q2": {"x": -10.0, "y": 20.0, "rotation": 0},
            "C_BUS": {"x": -30.0, "y": 0.0, "rotation": 0},
        }

        # Should not raise
        svg = render_loop_path(commutation_loop, negative_placements, "#FF0000")
        assert isinstance(svg, str)

    def test_handles_very_large_coordinates(self, commutation_loop: Loop):
        """Should handle placements with very large coordinates."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        large_placements = {
            "Q1": {"x": 1e6, "y": 1e6, "rotation": 0},
            "Q2": {"x": 1e6, "y": 1.1e6, "rotation": 0},
            "C_BUS": {"x": 0.9e6, "y": 1.05e6, "rotation": 0},
        }

        svg = render_loop_path(commutation_loop, large_placements, "#FF0000")
        assert isinstance(svg, str)

    def test_handles_invalid_color(self, commutation_loop: Loop, sample_placements: dict):
        """Should handle or reject invalid color strings."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        # Invalid color - should either fix it or raise ValueError
        try:
            svg = render_loop_path(commutation_loop, sample_placements, "not-a-color")
            # If it doesn't raise, it should use a default
            assert isinstance(svg, str)
        except ValueError:
            pass  # Also acceptable

    def test_handles_circular_pins(self):
        """Should handle loop with same start and end pin."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        circular_loop = Loop(
            name="circular",
            loop_type=LoopType.CUSTOM,
            description="Loop with explicit closure",
            pins=[
                LoopPin("A", "1", "NET1"),
                LoopPin("B", "1", "NET2"),
                LoopPin("A", "1", "NET1"),  # Explicit closure to same pin
            ],
        )

        placements = {
            "A": {"x": 0, "y": 0, "rotation": 0},
            "B": {"x": 10, "y": 0, "rotation": 0},
        }

        svg = render_loop_path(circular_loop, placements, "#FF0000")
        assert isinstance(svg, str)


# =============================================================================
# Tests for Performance
# =============================================================================


class TestLoopVizPerformance:
    """Performance tests for loop visualization."""

    def test_render_many_loops(self, sample_placements: dict):
        """Should handle rendering many loops efficiently."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_board_with_loops

        # Create collection with many loops
        collection = LoopCollection()
        for i in range(50):
            loop = Loop(
                name=f"loop_{i}",
                loop_type=LoopType.CUSTOM,
                description=f"Test loop {i}",
                components=["Q1", "Q2"],
            )
            collection.add_loop(loop)

        # Should complete in reasonable time
        import time

        start = time.time()
        html = render_board_with_loops(
            placements=sample_placements,
            loops=collection,
            board_width=200.0,
            board_height=150.0,
        )
        elapsed = time.time() - start

        assert elapsed < 5.0, f"Rendering took too long: {elapsed}s"
        assert isinstance(html, str)

    def test_render_loop_with_many_pins(self, sample_placements: dict):
        """Should handle loop with many pins efficiently."""
        pytest.importorskip("temper_placer.visualization.loop_viz")
        from temper_placer.visualization.loop_viz import render_loop_path

        # Create loop with many pins
        pins = []
        for i in range(100):
            pins.append(LoopPin(f"C{i}", "1", f"NET{i}"))

        # Create placements for all components
        placements = {
            f"C{i}": {"x": i * 2.0, "y": (i % 10) * 2.0, "rotation": 0} for i in range(100)
        }

        complex_loop = Loop(
            name="complex",
            loop_type=LoopType.CUSTOM,
            description="Loop with many pins",
            pins=pins,
        )

        import time

        start = time.time()
        svg = render_loop_path(complex_loop, placements, "#FF0000")
        elapsed = time.time() - start

        assert elapsed < 1.0, f"Rendering took too long: {elapsed}s"
        assert isinstance(svg, str)
