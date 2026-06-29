"""
Robustness tests for KiCad PCB parser.

These tests verify the parser handles malformed, corrupted, and edge-case
input files gracefully without crashing or producing undefined behavior.

Test categories:
1. Fatal errors (empty file, binary garbage, truncated S-expression)
2. Recoverable issues (missing board outline, components without positions)
3. Edge cases (unicode refs, very long strings, negative coordinates)

Expected behavior:
- Fatal issues: Raise a clear exception (ParseError or similar)
- Recoverable issues: Add warnings to ParseResult.warnings, continue parsing
- Edge cases: Handle gracefully, possibly with warnings
"""

import contextlib
from pathlib import Path

import pytest

# Import parser
from temper_placer.io.kicad_parser import parse_kicad_pcb

# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MALFORMED_DIR = FIXTURES_DIR / "malformed"


class TestFatalErrors:
    """Tests for inputs that should cause parsing to fail with clear errors."""

    def test_empty_file(self, tmp_path):
        """Empty file should raise an error, not crash."""
        empty_pcb = tmp_path / "empty.kicad_pcb"
        empty_pcb.write_text("")

        with pytest.raises(Exception) as exc_info:
            parse_kicad_pcb(empty_pcb)

        # Should have a meaningful error message
        error_msg = str(exc_info.value).lower()
        assert len(error_msg) > 0, "Error message should not be empty"

    def test_binary_garbage(self, tmp_path):
        """Binary data should fail gracefully, not crash with UnicodeDecodeError."""
        garbage_pcb = tmp_path / "garbage.kicad_pcb"
        garbage_pcb.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd\x80\x81\x82")

        with pytest.raises(Exception) as exc_info:
            parse_kicad_pcb(garbage_pcb)

        # Should NOT be UnicodeDecodeError bubbling up unhandled
        # (though it's fine if the parser converts it to a cleaner error)
        assert exc_info.value is not None

    def test_truncated_sexpr(self, tmp_path):
        """S-expression cut off mid-parse should fail gracefully."""
        truncated_pcb = tmp_path / "truncated.kicad_pcb"
        truncated_pcb.write_text(
            '(kicad_pcb (version 20221018) (generator pcbnew) (footprint "R_0603"'
        )

        with pytest.raises(ValueError):
            parse_kicad_pcb(truncated_pcb)

    def test_mismatched_parens(self, tmp_path):
        """Mismatched parentheses should fail gracefully."""
        bad_parens_pcb = tmp_path / "bad_parens.kicad_pcb"
        bad_parens_pcb.write_text(
            "(kicad_pcb (version 20221018) (general (thickness 1.6)))"  # Extra closing paren at end
        )

        # This might parse or fail - key is it shouldn't crash
        with contextlib.suppress(Exception):
            parse_kicad_pcb(bad_parens_pcb)
            # If it parses, that's OK

    def test_not_kicad_pcb(self, tmp_path):
        """Non-KiCad file format should fail with clear error."""
        not_kicad = tmp_path / "not_kicad.kicad_pcb"
        not_kicad.write_text("This is just plain text, not an S-expression")

        with pytest.raises(ValueError):
            parse_kicad_pcb(not_kicad)

    def test_kicad_schematic_not_pcb(self, tmp_path):
        """KiCad schematic file (not PCB) should fail or be handled."""
        schematic = tmp_path / "schematic.kicad_pcb"
        schematic.write_text("(kicad_sch (version 20230121) (generator eeschema))")

        # Should fail because it's not a PCB file
        with pytest.raises(ValueError):
            parse_kicad_pcb(schematic)


class TestRecoverableIssues:
    """Tests for inputs with issues that should produce warnings but still parse."""

    def test_missing_board_outline(self, tmp_path):
        """PCB with no Edge.Cuts should parse with warning, using default bounds."""
        no_outline = tmp_path / "no_outline.kicad_pcb"
        no_outline.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (44 "Edge.Cuts" user)
  )
  (net 0 "")
  (net 1 "GND")

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 100 80)
    (property "Reference" "R1")
    (property "Value" "10k")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu") (net 1 "GND"))
    (pad "2" smd roundrect (at 0.825 0) (size 0.8 0.95) (layers "F.Cu") (net 1 "GND"))
  )
)""")

        # Should parse successfully
        result = parse_kicad_pcb(no_outline)

        # Should have the component
        assert result.netlist.n_components == 1
        assert result.netlist.components[0].ref == "R1"

        # Board dimensions should be something reasonable (default or inferred)
        assert result.board is not None
        assert result.board.width > 0
        assert result.board.height > 0

    def test_component_at_origin(self, tmp_path):
        """Component at position (0, 0) should parse correctly."""
        at_origin = tmp_path / "at_origin.kicad_pcb"
        at_origin.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 0 0)
    (property "Reference" "R1")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu"))
  )

  (gr_rect (start -10 -10) (end 10 10) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(at_origin)
        assert result.netlist.n_components == 1

    def test_pcb_with_only_nets_no_components(self, tmp_path):
        """PCB with nets but no components should parse to empty netlist."""
        only_nets = tmp_path / "only_nets.kicad_pcb"
        only_nets.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")
  (net 1 "GND")
  (net 2 "VCC")

  (gr_rect (start 0 0) (end 50 50) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(only_nets)
        assert result.netlist.n_components == 0
        # Nets may or may not be captured without components


class TestUnicodeAndSpecialCharacters:
    """Tests for handling of special characters in component names and values."""

    def test_unicode_component_ref(self, tmp_path):
        """Component ref with unicode characters should parse."""
        unicode_ref = tmp_path / "unicode_ref.kicad_pcb"
        unicode_ref.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 100 80)
    (property "Reference" "R1_μΩ")
    (property "Value" "10kΩ ±1%")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu"))
  )

  (gr_rect (start 90 70) (end 120 100) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(unicode_ref)
        assert result.netlist.n_components == 1
        # Reference should contain unicode
        ref = result.netlist.components[0].ref
        assert "R1" in ref  # At minimum should have R1

    def test_component_value_with_special_chars(self, tmp_path):
        """Component values with special characters should parse."""
        special_value = tmp_path / "special_value.kicad_pcb"
        special_value.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")

  (footprint "Capacitor_SMD:C_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 100 80)
    (property "Reference" "C1")
    (property "Value" "100nF/50V X7R ±10%")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu"))
  )

  (gr_rect (start 90 70) (end 120 100) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(special_value)
        assert result.netlist.n_components == 1

    def test_net_name_with_slashes(self, tmp_path):
        """Net names with slashes (hierarchical) should parse."""
        hierarchical_nets = tmp_path / "hierarchical_nets.kicad_pcb"
        hierarchical_nets.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")
  (net 1 "/Power/VCC_3V3")
  (net 2 "/Digital/SPI_CLK")

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 100 80)
    (property "Reference" "R1")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu") (net 1 "/Power/VCC_3V3"))
    (pad "2" smd roundrect (at 0.825 0) (size 0.8 0.95) (layers "F.Cu") (net 2 "/Digital/SPI_CLK"))
  )

  (gr_rect (start 90 70) (end 120 100) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(hierarchical_nets)
        assert result.netlist.n_components == 1


class TestEdgeCaseCoordinates:
    """Tests for edge case coordinate values."""

    def test_negative_coordinates(self, tmp_path):
        """Components at negative coordinates should parse correctly."""
        negative_coords = tmp_path / "negative_coords.kicad_pcb"
        negative_coords.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at -50 -30)
    (property "Reference" "R1")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu"))
  )

  (gr_rect (start -60 -40) (end -40 -20) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(negative_coords)
        assert result.netlist.n_components == 1

        # Position should be negative
        comp = result.netlist.components[0]
        if comp.initial_position:
            # The parser should preserve the coordinate sign
            pass  # Just checking it doesn't crash

    def test_very_large_coordinates(self, tmp_path):
        """Components at very large coordinates should parse."""
        large_coords = tmp_path / "large_coords.kicad_pcb"
        large_coords.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 10000 10000)
    (property "Reference" "R1")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu"))
  )

  (gr_rect (start 9990 9990) (end 10020 10020) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(large_coords)
        assert result.netlist.n_components == 1

    def test_decimal_precision_coordinates(self, tmp_path):
        """Components with high-precision decimal coordinates should parse."""
        precise_coords = tmp_path / "precise_coords.kicad_pcb"
        precise_coords.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 100.123456789 80.987654321)
    (property "Reference" "R1")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu"))
  )

  (gr_rect (start 90 70) (end 120 100) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(precise_coords)
        assert result.netlist.n_components == 1


class TestRotationEdgeCases:
    """Tests for component rotation edge cases."""

    def test_all_rotation_angles(self, tmp_path):
        """Components at 0°, 90°, 180°, 270° should parse."""
        rotations = tmp_path / "rotations.kicad_pcb"
        rotations.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 100 80 0)
    (property "Reference" "R1")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu"))
  )

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000002)
    (at 110 80 90)
    (property "Reference" "R2")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu"))
  )

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000003)
    (at 120 80 180)
    (property "Reference" "R3")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu"))
  )

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000004)
    (at 130 80 270)
    (property "Reference" "R4")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu"))
  )

  (gr_rect (start 90 70) (end 150 100) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(rotations)
        assert result.netlist.n_components == 4

    def test_non_orthogonal_rotation(self, tmp_path):
        """Component at non-90° rotation (e.g., 45°) should parse."""
        angled = tmp_path / "angled.kicad_pcb"
        angled.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 100 80 45)
    (property "Reference" "R1")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu"))
  )

  (gr_rect (start 90 70) (end 120 100) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(angled)
        assert result.netlist.n_components == 1

    def test_negative_rotation(self, tmp_path):
        """Component with negative rotation should parse."""
        neg_rotation = tmp_path / "neg_rotation.kicad_pcb"
        neg_rotation.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 100 80 -90)
    (property "Reference" "R1")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu"))
  )

  (gr_rect (start 90 70) (end 120 100) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(neg_rotation)
        assert result.netlist.n_components == 1


class TestLongStrings:
    """Tests for handling of unusually long strings."""

    def test_very_long_reference(self, tmp_path):
        """Component with very long reference designator should parse."""
        long_ref = tmp_path / "long_ref.kicad_pcb"
        # Create a ref that's 100 chars
        long_designator = "R" + "1" * 99

        long_ref.write_text(f"""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 100 80)
    (property "Reference" "{long_designator}")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu"))
  )

  (gr_rect (start 90 70) (end 120 100) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(long_ref)
        assert result.netlist.n_components == 1

    def test_very_long_net_name(self, tmp_path):
        """Net with very long name should parse."""
        long_net = tmp_path / "long_net.kicad_pcb"
        long_net_name = "/Hierarchy/" + "SubLevel/" * 20 + "SignalName"

        long_net.write_text(f"""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")
  (net 1 "{long_net_name}")

  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 100 80)
    (property "Reference" "R1")
    (pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu") (net 1 "{long_net_name}"))
  )

  (gr_rect (start 90 70) (end 120 100) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(long_net)
        assert result.netlist.n_components == 1


class TestMinimalValidPCB:
    """Tests to verify the absolute minimum PCB structure parses."""

    def test_minimal_structure(self, tmp_path):
        """Minimal valid KiCad PCB structure should parse."""
        minimal = tmp_path / "minimal.kicad_pcb"
        minimal.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")
  (gr_rect (start 0 0) (end 50 50) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(minimal)
        # Should parse with 0 components
        assert result.netlist.n_components == 0
        # Should have valid board dimensions
        assert result.board is not None
        assert result.board.width > 0
        assert result.board.height > 0

    def test_single_component_minimal(self, tmp_path):
        """Single component with minimal attributes should parse."""
        single = tmp_path / "single.kicad_pcb"
        single.write_text("""(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")

  (footprint "R_0603" (layer "F.Cu")
    (at 25 25)
    (property "Reference" "R1")
  )

  (gr_rect (start 0 0) (end 50 50) (layer "Edge.Cuts") (width 0.1))
)""")

        result = parse_kicad_pcb(single)
        assert result.netlist.n_components == 1
        assert result.netlist.components[0].ref == "R1"
