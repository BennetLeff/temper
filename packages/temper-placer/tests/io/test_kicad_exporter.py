"""
Tests for KiCad exporter (temper-wnyn).

Integration tests for trace and via export to KiCad PCB files.
"""

import tempfile
from pathlib import Path

import pytest

from temper_placer.io.kicad_exporter import (
    add_segments_to_board,
    add_vias_to_board,
    path_to_segments,
    path_to_vias,
    TraceSegment,
    TraceVia,
)
from temper_placer.routing.maze_router import GridCell, RoutePath


class TestPathToSegments:
    """Tests for converting paths to segments."""

    def test_straight_path_creates_one_segment(self):
        """Straight line should simplify to one segment."""
        path = RoutePath(
            net="GND",
            cells=[GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)],
            length=2.0,
            via_count=0,
            success=True,
        )

        segments = path_to_segments(path, origin=(0, 0), cell_size=1.0, trace_width=0.25)

        assert len(segments) == 1
        assert segments[0].net == "GND"
        assert segments[0].width == 0.25
        assert segments[0].layer == "F.Cu"

    def test_l_shaped_path_creates_two_segments(self):
        """L-shaped path should create 2 segments."""
        path = RoutePath(
            net="VCC",
            cells=[GridCell(0, 0, 0), GridCell(2, 0, 0), GridCell(2, 2, 0)],
            length=4.0,
            via_count=0,
            success=True,
        )

        segments = path_to_segments(path, origin=(0, 0), cell_size=1.0, trace_width=0.5)

        assert len(segments) == 2
        # Horizontal segment
        assert segments[0].start[1] == segments[0].end[1]  # Same Y
        # Vertical segment
        assert segments[1].start[0] == segments[1].end[0]  # Same X

    def test_failed_path_creates_no_segments(self):
        """Failed routing should not export segments."""
        path = RoutePath(
            net="FAILED_NET",
            cells=[],
            length=0.0,
            via_count=0,
            success=False,
            failure_reason="No path found",
        )

        segments = path_to_segments(path, origin=(0, 0), cell_size=1.0, trace_width=0.25)

        assert len(segments) == 0

    def test_layer_transition_skipped_in_segments(self):
        """Via location should not create a segment."""
        path = RoutePath(
            net="SIG",
            cells=[
                GridCell(0, 0, 0),  # L0
                GridCell(1, 0, 0),  # L0
                GridCell(1, 0, 1),  # L1 - via
                GridCell(2, 0, 1),  # L1
            ],
            length=2.0,
            via_count=1,
            success=True,
        )

        segments = path_to_segments(path, origin=(0, 0), cell_size=1.0, trace_width=0.25)

        # Should have 2 segments (one per layer), not 3
        assert len(segments) == 2


class TestPathToVias:
    """Tests for extracting vias from paths."""

    def test_single_layer_transition_creates_one_via(self):
        """Path with one layer change should create one via.
        
        Uses default 4-layer map where layer 0=F.Cu, layer 1=In1.Cu.
        Via connects only the layers involved in the transition (partial stack).
        """
        path = RoutePath(
            net="CLK",
            cells=[GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 0, 1)],
            length=1.0,
            via_count=1,
            success=True,
        )

        vias = path_to_vias(path, origin=(0, 0), cell_size=1.0)

        assert len(vias) == 1
        assert vias[0].net == "CLK"
        assert vias[0].size == 0.8  # Default
        assert vias[0].drill == 0.4  # Default
        # With default 4-layer map, layer 0→1 creates F.Cu→In1.Cu via
        assert "F.Cu" in vias[0].layers
        assert "In1.Cu" in vias[0].layers
        assert len(vias[0].layers) == 2  # Partial stack, not through-hole

    def test_multiple_layer_transitions(self):
        """Multiple vias in path."""
        path = RoutePath(
            net="DATA",
            cells=[
                GridCell(0, 0, 0),  # L0
                GridCell(1, 0, 1),  # L1 - via 1
                GridCell(2, 0, 1),  # L1
                GridCell(2, 0, 0),  # L0 - via 2
            ],
            length=2.0,
            via_count=2,
            success=True,
        )

        vias = path_to_vias(path, origin=(0, 0), cell_size=1.0)

        assert len(vias) == 2

    def test_single_layer_path_no_vias(self):
        """Path on single layer should have no vias."""
        path = RoutePath(
            net="PWR",
            cells=[GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)],
            length=2.0,
            via_count=0,
            success=True,
        )

        vias = path_to_vias(path, origin=(0, 0), cell_size=1.0)

        assert len(vias) == 0

    def test_custom_via_size(self):
        """Custom via dimensions should be applied."""
        path = RoutePath(
            net="GND",
            cells=[GridCell(0, 0, 0), GridCell(0, 0, 1)],
            length=0.0,
            via_count=1,
            success=True,
        )

        vias = path_to_vias(path, origin=(0, 0), cell_size=1.0, via_size=1.0, via_drill=0.6)

        assert vias[0].size == 1.0
        assert vias[0].drill == 0.6


# Integration tests with kiutils would require a valid KiCad PCB file
# These are more complex and would be part of end-to-end testing
class TestKicadBoardIntegration:
    """Integration tests with kiutils Board manipulation (temper-wnyn.5)."""

    @pytest.mark.skip(reason="Requires valid KiCad PCB template - integration test")
    def test_add_segments_to_board(self):
        """Should add segments to KiCad board object."""
        # Would load a template PCB and test segment addition
        pass

    @pytest.mark.skip(reason="Requires valid KiCad PCB template - integration test")
    def test_add_vias_to_board(self):
        """Should add vias to KiCad board object."""
        # Would load a template PCB and test via addition
        pass

    @pytest.mark.skip(reason="Requires valid KiCad PCB template - integration test")
    def test_export_routed_pcb_end_to_end(self):
        """End-to-end test of PCB export."""
        # Would:
        # 1. Create mock routes
        # 2. Export to temp file
        # 3. Load and verify output contains traces
        pass
