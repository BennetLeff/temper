"""Tests for extracting component positions from KiCad PCB footprint sections.

TDD: These tests verify that the KiCad parser extracts component positions from footprints.
"""

import pytest
from pathlib import Path


class TestFootprintPositionExtraction:
    """Test that KiCad parser extracts component positions from footprint (at ...) fields."""

    def test_parser_extracts_component_positions_from_piantor(self):
        """Components should have positions extracted from (at x y) in footprint sections."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        # Use Piantor keyboard as test fixture (if available)
        pcb_path = Path("/tmp/piantor/pcb/right/keyboard_pcb.kicad_pcb")
        if not pcb_path.exists():
            pytest.skip("Piantor benchmark not cloned to /tmp/piantor")

        result = parse_kicad_pcb(pcb_path)

        # Piantor should have 36 components
        assert len(result.netlist.components) == 36, "Expected 36 components"

        # All components should have initial_position set (not (0,0) or None-like)
        components_with_positions = [
            c for c in result.netlist.components
            if c.initial_position and c.initial_position != (0, 0)
        ]
        
        assert len(components_with_positions) == 36, (
            f"Expected 36 components with non-zero positions, got {len(components_with_positions)}. "
            f"Parser should extract (at x y) from footprint sections."
        )

    def test_component_position_values_are_sensible(self):
        """Component positions should be within board bounds after origin normalization."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        pcb_path = Path("/tmp/piantor/pcb/right/keyboard_pcb.kicad_pcb")
        if not pcb_path.exists():
            pytest.skip("Piantor benchmark not cloned")

        result = parse_kicad_pcb(pcb_path)

        # Find K25 component
        k25 = next((c for c in result.netlist.components if c.ref == "K25"), None)
        assert k25 is not None, "K25 component not found"

        # Check position is set and within reasonable board bounds (139x90mm board)
        pos = k25.initial_position
        assert pos is not None, "K25 should have initial_position"
        
        x, y = pos[0], pos[1]
        # After origin normalization, positions should be within [0, board_width/height]
        assert 0 <= x <= 200, f"K25 X ({x}) should be within reasonable bounds"
        assert 0 <= y <= 200, f"K25 Y ({y}) should be within reasonable bounds"

    def test_component_rotation_available(self):
        """Component rotation should be available via initial_rotation attribute."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        pcb_path = Path("/tmp/piantor/pcb/right/keyboard_pcb.kicad_pcb")
        if not pcb_path.exists():
            pytest.skip("Piantor benchmark not cloned")

        result = parse_kicad_pcb(pcb_path)

        # Check that components have rotation data
        components_with_rotation = [
            c for c in result.netlist.components
            if hasattr(c, 'initial_rotation') and c.initial_rotation is not None
        ]
        
        # All components should have rotation (even if 0)
        assert len(components_with_rotation) == 36, (
            f"Expected all 36 components to have initial_rotation, got {len(components_with_rotation)}"
        )


class TestExtractFootprintPositionsHelper:
    """Test the extract_footprint_positions helper function for raw content parsing."""

    def test_extract_footprint_positions_from_content(self):
        """Should extract position dict from raw KiCad PCB content."""
        from temper_placer.io.kicad_parser import extract_footprint_positions

        # Minimal KiCad PCB content with one footprint
        content = '''(kicad_pcb (version 20211014)
  (footprint "Package_SO:SOIC-8" (layer "F.Cu")
    (at 50.5 75.25 90)
    (property "Reference" "U1" (at 0 0 0) (layer "F.Fab"))
    (pad "1" smd rect (at -1.905 -0.975) (size 0.6 1.78) (layers "F.Cu" "F.Paste" "F.Mask"))
  )
)'''

        positions = extract_footprint_positions(content)

        assert "U1" in positions, "U1 should be extracted"
        assert positions["U1"]["x"] == pytest.approx(50.5, rel=0.01)
        assert positions["U1"]["y"] == pytest.approx(75.25, rel=0.01)
        assert positions["U1"]["rotation"] == pytest.approx(90, rel=0.01)

    def test_extract_multiple_footprints(self):
        """Should extract positions for multiple footprints."""
        from temper_placer.io.kicad_parser import extract_footprint_positions

        content = '''(kicad_pcb (version 20211014)
  (footprint "Resistor_SMD:R_0603" (layer "F.Cu")
    (at 10 20)
    (property "Reference" "R1" (at 0 0 0) (layer "F.Fab"))
  )
  (footprint "Resistor_SMD:R_0603" (layer "F.Cu")
    (at 30 40 180)
    (property "Reference" "R2" (at 0 0 0) (layer "F.Fab"))
  )
)'''

        positions = extract_footprint_positions(content)

        assert len(positions) == 2
        assert positions["R1"]["x"] == pytest.approx(10, rel=0.01)
        assert positions["R1"]["y"] == pytest.approx(20, rel=0.01)
        assert positions["R2"]["rotation"] == pytest.approx(180, rel=0.01)

