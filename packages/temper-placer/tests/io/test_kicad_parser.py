"""
Tests for KiCad PCB parser (io/kicad_parser.py).

This module tests the primary input parser that reads KiCad PCB files
and converts them to the internal Netlist representation.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from temper_placer.io.kicad_parser import (
    PadData,
    ParseResult,
    TraceData,
    _calculate_footprint_bounds,
    _extract_board_geometry,
    _get_footprint_reference,
    parse_kicad_pcb,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def minimal_pcb_path(fixtures_dir: Path) -> Path:
    """Return path to minimal test PCB."""
    path = fixtures_dir / "minimal_board.kicad_pcb"
    if not path.exists():
        pytest.skip(f"Test fixture not found: {path}")
    return path


@pytest.fixture
def medium_pcb_path(fixtures_dir: Path) -> Path:
    """Return path to medium test PCB."""
    path = fixtures_dir / "medium_board.kicad_pcb"
    if not path.exists():
        pytest.skip(f"Test fixture not found: {path}")
    return path


@pytest.fixture
def large_pcb_path(fixtures_dir: Path) -> Path:
    """Return path to large test PCB."""
    path = fixtures_dir / "large_board.kicad_pcb"
    if not path.exists():
        pytest.skip(f"Test fixture not found: {path}")
    return path


# =============================================================================
# ParseResult Tests
# =============================================================================


class TestParseResult:
    """Tests for ParseResult dataclass."""

    def test_has_warnings_empty(self):
        """Test has_warnings returns False for empty warnings."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Netlist

        result = ParseResult(
            netlist=Netlist(components=[], nets=[]),
            board=Board(width=100, height=100),
            warnings=[],
        )
        assert not result.has_warnings

    def test_has_warnings_with_warnings(self):
        """Test has_warnings returns True when warnings exist."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Netlist

        result = ParseResult(
            netlist=Netlist(components=[], nets=[]),
            board=Board(width=100, height=100),
            warnings=["Some warning"],
        )
        assert result.has_warnings

    def test_default_traces_and_pads(self):
        """Test traces and pads default to empty lists."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Netlist

        result = ParseResult(
            netlist=Netlist(components=[], nets=[]),
            board=Board(width=100, height=100),
            warnings=[],
        )
        assert result.traces == []
        assert result.pads == []


class TestTraceData:
    """Tests for TraceData dataclass."""

    def test_basic_creation(self):
        """Test creating TraceData."""
        trace = TraceData(
            start=(10.0, 20.0),
            end=(30.0, 40.0),
            width=0.25,
            layer="F.Cu",
            net="GND",
        )
        assert trace.start == (10.0, 20.0)
        assert trace.end == (30.0, 40.0)
        assert trace.width == 0.25
        assert trace.layer == "F.Cu"
        assert trace.net == "GND"

    def test_default_net(self):
        """Test TraceData defaults net to None."""
        trace = TraceData(
            start=(0, 0),
            end=(1, 1),
            width=0.2,
            layer="B.Cu",
        )
        assert trace.net is None


class TestPadData:
    """Tests for PadData dataclass."""

    def test_basic_creation(self):
        """Test creating PadData."""
        pad = PadData(
            position=(5.0, 10.0),
            size=(1.5, 0.8),
            shape="rect",
            rotation=45.0,
            layer="F.Cu",
            number="1",
            net="VCC",
            component_ref="U1",
        )
        assert pad.position == (5.0, 10.0)
        assert pad.size == (1.5, 0.8)
        assert pad.shape == "rect"
        assert pad.rotation == 45.0
        assert pad.net == "VCC"
        assert pad.component_ref == "U1"

    def test_defaults(self):
        """Test PadData default values."""
        pad = PadData(
            position=(0, 0),
            size=(1, 1),
            shape="circle",
        )
        assert pad.rotation == 0.0
        assert pad.layer == "F.Cu"
        assert pad.number == ""
        assert pad.net is None
        assert pad.component_ref is None


# =============================================================================
# parse_kicad_pcb Tests
# =============================================================================


class TestParseKicadPcb:
    """Tests for parse_kicad_pcb function."""

    def test_parse_minimal_board(self, minimal_pcb_path: Path):
        """Test parsing a minimal board extracts basic info."""
        result = parse_kicad_pcb(minimal_pcb_path)

        # Check we got a valid result
        assert isinstance(result, ParseResult)
        assert result.netlist is not None
        assert result.board is not None

        # Check components were extracted
        assert len(result.netlist.components) > 0

        # Check board dimensions are reasonable
        assert result.board.width > 0
        assert result.board.height > 0

    def test_parse_minimal_board_components(self, minimal_pcb_path: Path):
        """Test that expected components are extracted from minimal board."""
        result = parse_kicad_pcb(minimal_pcb_path)

        # Get component refs
        refs = {c.ref for c in result.netlist.components}

        # minimal_board.kicad_pcb has R1, R2, C1, U1
        assert "R1" in refs
        assert "R2" in refs
        assert "C1" in refs
        assert "U1" in refs

    def test_parse_minimal_board_nets(self, minimal_pcb_path: Path):
        """Test that nets are extracted with correct connectivity."""
        result = parse_kicad_pcb(minimal_pcb_path)

        # Get net names
        net_names = {n.name for n in result.netlist.nets}

        # minimal_board.kicad_pcb has GND, VCC, SIG1, SIG2
        assert "GND" in net_names
        assert "VCC" in net_names
        assert "SIG1" in net_names
        assert "SIG2" in net_names

    def test_parse_minimal_board_dimensions(self, minimal_pcb_path: Path):
        """Test board dimensions are correctly extracted."""
        result = parse_kicad_pcb(minimal_pcb_path)

        assert result.board is not None
        # minimal_board.kicad_pcb has Edge.Cuts from (90,70) to (140,100)
        # So width = 50, height = 30
        assert result.board.width == pytest.approx(50.0, abs=0.1)
        assert result.board.height == pytest.approx(30.0, abs=0.1)

    def test_parse_minimal_board_origin(self, minimal_pcb_path: Path):
        """Test board origin is correctly extracted."""
        result = parse_kicad_pcb(minimal_pcb_path)

        assert result.board is not None
        # minimal_board.kicad_pcb has Edge.Cuts starting at (90, 70)
        assert result.board.origin[0] == pytest.approx(90.0, abs=0.1)
        assert result.board.origin[1] == pytest.approx(70.0, abs=0.1)

    def test_parse_minimal_board_component_positions_normalized(self, minimal_pcb_path: Path):
        """Test component positions are normalized to board origin."""
        result = parse_kicad_pcb(minimal_pcb_path)

        # R1 is at (100, 80) in KiCad coords
        # Board origin is (90, 70)
        # So normalized position should be (10, 10)
        r1 = next(c for c in result.netlist.components if c.ref == "R1")
        assert r1.initial_position is not None
        assert r1.initial_position[0] == pytest.approx(10.0, abs=0.1)
        assert r1.initial_position[1] == pytest.approx(10.0, abs=0.1)

    def test_parse_minimal_board_rotations(self, minimal_pcb_path: Path):
        """Test component rotations are correctly extracted."""
        result = parse_kicad_pcb(minimal_pcb_path)

        # R1 has no rotation (0°)
        r1 = next(c for c in result.netlist.components if c.ref == "R1")
        assert r1.initial_rotation == 0

        # R2 has 90° rotation
        r2 = next(c for c in result.netlist.components if c.ref == "R2")
        assert r2.initial_rotation == 1  # 90° = index 1

        # U1 has 180° rotation
        u1 = next(c for c in result.netlist.components if c.ref == "U1")
        assert u1.initial_rotation == 2  # 180° = index 2

    def test_parse_minimal_board_pins(self, minimal_pcb_path: Path):
        """Test component pins are extracted with net connections."""
        result = parse_kicad_pcb(minimal_pcb_path)

        # R1 should have 2 pins connected to SIG1 and SIG2
        r1 = next(c for c in result.netlist.components if c.ref == "R1")
        assert len(r1.pins) == 2

        pin_nets = {p.net for p in r1.pins}
        assert "SIG1" in pin_nets
        assert "SIG2" in pin_nets

    def test_parse_medium_board(self, medium_pcb_path: Path):
        """Test parsing a medium complexity board."""
        result = parse_kicad_pcb(medium_pcb_path)

        # Should have more components than minimal board
        assert len(result.netlist.components) > 4

        # Should have more nets
        assert len(result.netlist.nets) > 4

    def test_parse_large_board(self, large_pcb_path: Path):
        """Test parsing a larger board works efficiently."""
        result = parse_kicad_pcb(large_pcb_path)

        # Large board should have many components
        assert len(result.netlist.components) > 10

        # Verify structure is valid
        assert result.board is not None
        assert result.board.width > 0

    def test_parse_nonexistent_file_raises(self, tmp_path: Path):
        """Test parsing a non-existent file raises an error."""
        fake_path = tmp_path / "nonexistent.kicad_pcb"

        with pytest.raises(Exception):  # kiutils raises various exceptions
            parse_kicad_pcb(fake_path)

    def test_net_filtering(self, minimal_pcb_path: Path):
        """Test that single-pin nets are filtered out."""
        result = parse_kicad_pcb(minimal_pcb_path)

        # All nets should have at least 2 pins
        for net in result.netlist.nets:
            assert len(net.pins) >= 2, f"Net {net.name} has only {len(net.pins)} pins"


# =============================================================================
# Board Geometry Extraction Tests
# =============================================================================


class TestExtractBoardGeometry:
    """Tests for _extract_board_geometry helper."""

    def test_no_edge_cuts_returns_default(self):
        """Test that missing Edge.Cuts returns default board."""
        mock_board = MagicMock()
        mock_board.graphicItems = []
        mock_board.footprints = []
        mock_board.zones = []

        warnings = []
        board = _extract_board_geometry(mock_board, warnings)

        # Should return temper_default dimensions
        assert board.width > 0
        assert board.height > 0
        assert "No Edge.Cuts found" in warnings[0]


# =============================================================================
# Footprint Reference Extraction Tests
# =============================================================================


class TestGetFootprintReference:
    """Tests for _get_footprint_reference helper."""

    def test_reference_from_properties_dict(self):
        """Test extracting ref from properties dict."""
        fp = MagicMock()
        fp.properties = {"Reference": "U1"}
        fp.graphicItems = []

        ref = _get_footprint_reference(fp)
        assert ref == "U1"

    def test_reference_from_properties_list(self):
        """Test extracting ref from properties list (kiutils style)."""
        prop = MagicMock()
        prop.name = "Reference"
        prop.value = "R5"

        fp = MagicMock()
        fp.properties = [prop]
        fp.graphicItems = []

        ref = _get_footprint_reference(fp)
        assert ref == "R5"

    def test_reference_from_graphic_items(self):
        """Test extracting ref from graphic items."""
        item = MagicMock()
        item.type = "reference"
        item.text = "C10"

        fp = MagicMock()
        fp.properties = {}
        fp.graphicItems = [item]

        ref = _get_footprint_reference(fp)
        assert ref == "C10"

    def test_ref_attribute_fallback(self):
        """Test fallback to ref attribute."""
        fp = MagicMock()
        fp.properties = {}
        fp.graphicItems = []
        fp.ref = "D3"

        ref = _get_footprint_reference(fp)
        assert ref == "D3"

    def test_skip_ref_marker(self):
        """Test that REF** markers are skipped."""
        fp = MagicMock()
        fp.properties = {}
        fp.graphicItems = []
        fp.ref = "REF**"
        fp.entryName = "TestPart"

        ref = _get_footprint_reference(fp)
        # Should fall back to entryName since ref is invalid
        assert ref == "TestPart"


# =============================================================================
# Footprint Bounds Calculation Tests
# =============================================================================


class TestCalculateFootprintBounds:
    """Tests for _calculate_footprint_bounds helper."""

    def test_bounds_from_courtyard(self):
        """Test calculating bounds from courtyard layer."""
        # Create mock graphic items on F.CrtYd layer
        item = MagicMock()
        item.layer = "F.CrtYd"
        start_mock = MagicMock()
        start_mock.X = 0.0
        start_mock.Y = 0.0
        end_mock = MagicMock()
        end_mock.X = 10.0
        end_mock.Y = 5.0
        item.start = start_mock
        item.end = end_mock
        # Ensure center/radius attributes don't exist
        del item.center
        del item.radius

        fp = MagicMock()
        fp.graphicItems = [item]
        fp.pads = []

        width, height = _calculate_footprint_bounds(fp)
        assert width == pytest.approx(10.0, abs=0.1)
        assert height == pytest.approx(5.0, abs=0.1)

    def test_bounds_from_pads(self):
        """Test calculating bounds from pads when no courtyard exists."""
        pad1 = MagicMock()
        pad1.position = MagicMock(X=-1.0, Y=0.0)
        pad1.size = MagicMock(X=0.8, Y=0.6)

        pad2 = MagicMock()
        pad2.position = MagicMock(X=1.0, Y=0.0)
        pad2.size = MagicMock(X=0.8, Y=0.6)

        fp = MagicMock()
        fp.graphicItems = []
        fp.pads = [pad1, pad2]

        width, height = _calculate_footprint_bounds(fp)
        # Bounds: from -1.0 - 0.4 to 1.0 + 0.4 = -1.4 to 1.4 = 2.8 width
        # Height: from 0 - 0.3 to 0 + 0.3 = 0.6
        assert width == pytest.approx(2.8, abs=0.1)
        assert height == pytest.approx(0.6, abs=0.1)

    def test_minimum_bounds(self):
        """Test that bounds have a minimum of 0.5mm."""
        fp = MagicMock()
        fp.graphicItems = []
        fp.pads = []

        width, height = _calculate_footprint_bounds(fp)
        # Ultimate fallback should be (2.0, 2.0)
        assert width >= 0.5
        assert height >= 0.5


# =============================================================================
# Round-Trip Consistency Tests
# =============================================================================


class TestRoundTripConsistency:
    """Tests for parse → export → parse consistency."""

    def test_component_count_preserved(self, minimal_pcb_path: Path, tmp_path: Path):
        """Test that component count is preserved through round-trip."""
        from temper_placer.io.kicad_writer import PlacementUpdate, write_placements_to_pcb

        # Parse original
        result1 = parse_kicad_pcb(minimal_pcb_path)
        original_count = len(result1.netlist.components)

        assert result1.board is not None, "Board should not be None"

        # Export to new file (with same positions) - use dict format
        output_path = tmp_path / "roundtrip.kicad_pcb"
        placements: dict[str, PlacementUpdate] = {}
        for comp in result1.netlist.components:
            pos = comp.initial_position or (0, 0)
            rot = comp.initial_rotation or 0
            placements[comp.ref] = PlacementUpdate(
                ref=comp.ref,
                x=pos[0] + result1.board.origin[0],  # Add origin back
                y=pos[1] + result1.board.origin[1],
                rotation=rot * 90.0,
            )

        write_placements_to_pcb(
            template_pcb=minimal_pcb_path,
            output_pcb=output_path,
            placements=placements,
        )

        # Parse round-tripped file
        result2 = parse_kicad_pcb(output_path)

        # Component count should be preserved
        assert len(result2.netlist.components) == original_count

    def test_net_connectivity_preserved(self, minimal_pcb_path: Path, tmp_path: Path):
        """Test that net connectivity is preserved through round-trip."""
        from temper_placer.io.kicad_writer import PlacementUpdate, write_placements_to_pcb

        # Parse original
        result1 = parse_kicad_pcb(minimal_pcb_path)
        original_nets = {n.name: len(n.pins) for n in result1.netlist.nets}

        assert result1.board is not None, "Board should not be None"

        # Export to new file - use dict format
        output_path = tmp_path / "roundtrip_nets.kicad_pcb"
        placements: dict[str, PlacementUpdate] = {}
        for comp in result1.netlist.components:
            pos = comp.initial_position or (0, 0)
            rot = comp.initial_rotation or 0
            placements[comp.ref] = PlacementUpdate(
                ref=comp.ref,
                x=pos[0] + result1.board.origin[0],
                y=pos[1] + result1.board.origin[1],
                rotation=rot * 90.0,
            )

        write_placements_to_pcb(
            template_pcb=minimal_pcb_path,
            output_pcb=output_path,
            placements=placements,
        )

        # Parse round-tripped file
        result2 = parse_kicad_pcb(output_path)
        roundtrip_nets = {n.name: len(n.pins) for n in result2.netlist.nets}

        # Net names and pin counts should match
        assert set(original_nets.keys()) == set(roundtrip_nets.keys())
        for name in original_nets:
            assert original_nets[name] == roundtrip_nets[name], (
                f"Net {name} pin count changed: {original_nets[name]} → {roundtrip_nets[name]}"
            )


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_board_handling(self, tmp_path: Path):
        """Test handling a minimal empty board file."""
        # Create a minimal but valid KiCad PCB file
        empty_pcb = tmp_path / "empty.kicad_pcb"
        empty_pcb.write_text("""(kicad_pcb (version 20221018) (generator test)
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal))
)
""")

        result = parse_kicad_pcb(empty_pcb)

        # Should parse without crashing
        assert result is not None
        assert len(result.netlist.components) == 0
        assert len(result.netlist.nets) == 0
        # Should have warning about missing Edge.Cuts
        assert result.has_warnings

    def test_component_without_pads(self, minimal_pcb_path: Path):
        """Test that components are handled correctly even without pad data."""
        result = parse_kicad_pcb(minimal_pcb_path)

        # All components should have valid bounds even if pads are missing
        for comp in result.netlist.components:
            assert comp.bounds[0] > 0
            assert comp.bounds[1] > 0
