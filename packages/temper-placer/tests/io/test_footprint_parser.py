"""
Tests for KiCad footprint parser - extract courtyard bounds from .kicad_mod files.

TDD Task: temper-1my.1.1
"""

from pathlib import Path

import pytest

# Module under test - will be implemented
from temper_placer.io.footprint_parser import (
    FootprintBounds,
    FootprintParseError,
    parse_footprint_courtyard,
)


class TestFootprintParser:
    """Test courtyard extraction from KiCad footprint files."""

    def test_parse_to247_courtyard(self, tmp_path: Path) -> None:
        """TO-247 footprint should have courtyard ~16x21mm."""
        # Create a minimal TO-247 footprint file
        footprint_content = """
(footprint "Package_TO_SOT_THT:TO-247-3_Horizontal_TabDown"
  (layer "F.Cu")
  (fp_line (start -8.0 -10.5) (end 8.0 -10.5) (layer "F.CrtYd") (width 0.05))
  (fp_line (start 8.0 -10.5) (end 8.0 10.5) (layer "F.CrtYd") (width 0.05))
  (fp_line (start 8.0 10.5) (end -8.0 10.5) (layer "F.CrtYd") (width 0.05))
  (fp_line (start -8.0 10.5) (end -8.0 -10.5) (layer "F.CrtYd") (width 0.05))
  (pad "1" thru_hole rect (at -5.46 0) (size 2.0 2.0) (drill 1.0))
  (pad "2" thru_hole circle (at 0 0) (size 2.0 2.0) (drill 1.0))
  (pad "3" thru_hole circle (at 5.46 0) (size 2.0 2.0) (drill 1.0))
)
"""
        fp_file = tmp_path / "TO-247.kicad_mod"
        fp_file.write_text(footprint_content)

        bounds = parse_footprint_courtyard(fp_file)

        assert isinstance(bounds, FootprintBounds)
        assert bounds.width == pytest.approx(16.0, abs=0.5)  # 2 * 8.0
        assert bounds.height == pytest.approx(21.0, abs=0.5)  # 2 * 10.5

    def test_parse_sot223_courtyard(self, tmp_path: Path) -> None:
        """SOT-223 with tab should have asymmetric courtyard ~6.5x7mm."""
        footprint_content = """
(footprint "Package_TO_SOT_SMD:SOT-223-3_TabPin2"
  (layer "F.Cu")
  (fp_line (start -3.25 -3.5) (end 3.25 -3.5) (layer "F.CrtYd") (width 0.05))
  (fp_line (start 3.25 -3.5) (end 3.25 3.5) (layer "F.CrtYd") (width 0.05))
  (fp_line (start 3.25 3.5) (end -3.25 3.5) (layer "F.CrtYd") (width 0.05))
  (fp_line (start -3.25 3.5) (end -3.25 -3.5) (layer "F.CrtYd") (width 0.05))
  (pad "1" smd rect (at -2.3 3.2) (size 1.0 2.0))
  (pad "2" smd rect (at 0 3.2) (size 1.0 2.0))
  (pad "3" smd rect (at 2.3 3.2) (size 1.0 2.0))
  (pad "2" smd rect (at 0 -3.2) (size 3.0 2.0))
)
"""
        fp_file = tmp_path / "SOT-223.kicad_mod"
        fp_file.write_text(footprint_content)

        bounds = parse_footprint_courtyard(fp_file)

        assert bounds.width == pytest.approx(6.5, abs=0.5)  # 2 * 3.25
        assert bounds.height == pytest.approx(7.0, abs=0.5)  # 2 * 3.5

    def test_parse_0805_courtyard(self, tmp_path: Path) -> None:
        """Standard 0805 should have courtyard ~2x1.25mm."""
        footprint_content = """
(footprint "Capacitor_SMD:C_0805_2012Metric"
  (layer "F.Cu")
  (fp_line (start -1.0 -0.625) (end 1.0 -0.625) (layer "F.CrtYd") (width 0.05))
  (fp_line (start 1.0 -0.625) (end 1.0 0.625) (layer "F.CrtYd") (width 0.05))
  (fp_line (start 1.0 0.625) (end -1.0 0.625) (layer "F.CrtYd") (width 0.05))
  (fp_line (start -1.0 0.625) (end -1.0 -0.625) (layer "F.CrtYd") (width 0.05))
  (pad "1" smd roundrect (at -0.9 0) (size 1.0 1.2) (roundrect_rratio 0.25))
  (pad "2" smd roundrect (at 0.9 0) (size 1.0 1.2) (roundrect_rratio 0.25))
)
"""
        fp_file = tmp_path / "C_0805.kicad_mod"
        fp_file.write_text(footprint_content)

        bounds = parse_footprint_courtyard(fp_file)

        assert bounds.width == pytest.approx(2.0, abs=0.2)
        assert bounds.height == pytest.approx(1.25, abs=0.2)

    def test_courtyard_includes_margin(self, tmp_path: Path) -> None:
        """Extracted bounds should include fab margin from courtyard."""
        # Create a footprint where pads extend beyond silkscreen but courtyard includes margin
        footprint_content = """
(footprint "Test:TestPart"
  (layer "F.Cu")
  (fp_line (start -2.5 -1.5) (end 2.5 -1.5) (layer "F.CrtYd") (width 0.05))
  (fp_line (start 2.5 -1.5) (end 2.5 1.5) (layer "F.CrtYd") (width 0.05))
  (fp_line (start 2.5 1.5) (end -2.5 1.5) (layer "F.CrtYd") (width 0.05))
  (fp_line (start -2.5 1.5) (end -2.5 -1.5) (layer "F.CrtYd") (width 0.05))
  (fp_line (start -2.0 -1.0) (end 2.0 -1.0) (layer "F.SilkS") (width 0.12))
  (fp_line (start 2.0 -1.0) (end 2.0 1.0) (layer "F.SilkS") (width 0.12))
  (fp_line (start 2.0 1.0) (end -2.0 1.0) (layer "F.SilkS") (width 0.12))
  (fp_line (start -2.0 1.0) (end -2.0 -1.0) (layer "F.SilkS") (width 0.12))
  (pad "1" smd rect (at -1.5 0) (size 1.0 2.0))
  (pad "2" smd rect (at 1.5 0) (size 1.0 2.0))
)
"""
        fp_file = tmp_path / "TestPart.kicad_mod"
        fp_file.write_text(footprint_content)

        bounds = parse_footprint_courtyard(fp_file)

        # Bounds should be from courtyard (5x3), not silkscreen (4x2)
        assert bounds.width == pytest.approx(5.0, abs=0.1)
        assert bounds.height == pytest.approx(3.0, abs=0.1)

    def test_parse_back_courtyard(self, tmp_path: Path) -> None:
        """Should also parse B.CrtYd (back courtyard) layer."""
        footprint_content = """
(footprint "Test:BackSide"
  (layer "B.Cu")
  (fp_line (start -3.0 -2.0) (end 3.0 -2.0) (layer "B.CrtYd") (width 0.05))
  (fp_line (start 3.0 -2.0) (end 3.0 2.0) (layer "B.CrtYd") (width 0.05))
  (fp_line (start 3.0 2.0) (end -3.0 2.0) (layer "B.CrtYd") (width 0.05))
  (fp_line (start -3.0 2.0) (end -3.0 -2.0) (layer "B.CrtYd") (width 0.05))
)
"""
        fp_file = tmp_path / "BackSide.kicad_mod"
        fp_file.write_text(footprint_content)

        bounds = parse_footprint_courtyard(fp_file)

        assert bounds.width == pytest.approx(6.0, abs=0.1)
        assert bounds.height == pytest.approx(4.0, abs=0.1)

    def test_no_courtyard_raises_error(self, tmp_path: Path) -> None:
        """Footprint without courtyard should raise descriptive error."""
        footprint_content = """
(footprint "Test:NoCourt"
  (layer "F.Cu")
  (pad "1" smd rect (at 0 0) (size 1.0 1.0))
)
"""
        fp_file = tmp_path / "NoCourt.kicad_mod"
        fp_file.write_text(footprint_content)

        with pytest.raises(FootprintParseError) as exc_info:
            parse_footprint_courtyard(fp_file)

        assert "courtyard" in str(exc_info.value).lower()

    def test_invalid_file_raises_error(self, tmp_path: Path) -> None:
        """Invalid file should raise descriptive error."""
        fp_file = tmp_path / "invalid.kicad_mod"
        fp_file.write_text("not valid s-expression content")

        with pytest.raises(FootprintParseError):
            parse_footprint_courtyard(fp_file)

    def test_nonexistent_file_raises_error(self, tmp_path: Path) -> None:
        """Non-existent file should raise FileNotFoundError."""
        fp_file = tmp_path / "nonexistent.kicad_mod"

        with pytest.raises(FileNotFoundError):
            parse_footprint_courtyard(fp_file)

    def test_footprint_bounds_dataclass(self) -> None:
        """FootprintBounds should have width, height, and optional center offset."""
        bounds = FootprintBounds(width=10.0, height=5.0)
        assert bounds.width == 10.0
        assert bounds.height == 5.0
        assert bounds.center_offset == (0.0, 0.0)

        bounds_with_offset = FootprintBounds(width=10.0, height=5.0, center_offset=(1.0, -0.5))
        assert bounds_with_offset.center_offset == (1.0, -0.5)

    def test_fp_rect_courtyard(self, tmp_path: Path) -> None:
        """Handle fp_rect elements for courtyard (newer KiCad format)."""
        footprint_content = """
(footprint "Test:RectCourt"
  (layer "F.Cu")
  (fp_rect (start -2.0 -1.0) (end 2.0 1.0) (layer "F.CrtYd") (width 0.05))
  (pad "1" smd rect (at 0 0) (size 1.0 1.0))
)
"""
        fp_file = tmp_path / "RectCourt.kicad_mod"
        fp_file.write_text(footprint_content)

        bounds = parse_footprint_courtyard(fp_file)

        assert bounds.width == pytest.approx(4.0, abs=0.1)
        assert bounds.height == pytest.approx(2.0, abs=0.1)


class TestFootprintDirectory:
    """Test parsing multiple footprints from a directory."""

    def test_parse_footprint_directory(self, tmp_path: Path) -> None:
        """Should parse all .kicad_mod files in a directory."""
        from temper_placer.io.footprint_parser import parse_footprint_directory

        # Create multiple footprint files
        for name, width, height in [
            ("R_0805", 2.0, 1.25),
            ("C_0603", 1.6, 0.8),
            ("U_SOIC8", 5.0, 4.0),
        ]:
            content = f"""
(footprint "Test:{name}"
  (layer "F.Cu")
  (fp_line (start -{width / 2} -{height / 2}) (end {width / 2} -{height / 2}) (layer "F.CrtYd") (width 0.05))
  (fp_line (start {width / 2} -{height / 2}) (end {width / 2} {height / 2}) (layer "F.CrtYd") (width 0.05))
  (fp_line (start {width / 2} {height / 2}) (end -{width / 2} {height / 2}) (layer "F.CrtYd") (width 0.05))
  (fp_line (start -{width / 2} {height / 2}) (end -{width / 2} -{height / 2}) (layer "F.CrtYd") (width 0.05))
)
"""
            (tmp_path / f"{name}.kicad_mod").write_text(content)

        results = parse_footprint_directory(tmp_path)

        assert len(results) == 3
        assert "R_0805" in results
        assert results["R_0805"].width == pytest.approx(2.0, abs=0.1)
        assert results["C_0603"].height == pytest.approx(0.8, abs=0.1)
