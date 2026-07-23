from pathlib import Path

import pytest

from temper_placer.io.kicad_metadata import extract_kicad_metadata


def _write_pcb(tmp_path: Path, name: str, content: str) -> Path:
    """Write a synthetic .kicad_pcb fixture to tmp_path."""
    pcb_path = tmp_path / name
    pcb_path.write_text(content)
    return pcb_path


# --- Regression: real production board ---

_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_real_board_dimensions_match_hardcoded_legacy_values():
    """extract_kicad_metadata on the production board returns 100x150mm,
    identical to the old hardcoded default — proves the new Edge.Cuts
    parser does not change today's behavior."""
    pcb_path = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
    if not pcb_path.exists():
        pytest.skip("Production PCB not available")
    meta = extract_kicad_metadata(pcb_path)
    assert meta.board_width == 100.0
    assert meta.board_height == 150.0


# --- Synthetic: non-default dimensions ---


def test_non_default_dimensions_from_gr_poly(tmp_path):
    pcb = _write_pcb(
        tmp_path,
        "test.kicad_pcb",
        """(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal))
  (net 0 "")
  (footprint "Resistor_SMD:R_0805_2012Metric" (layer "F.Cu")
    (property "Reference" "R1") (property "Value" "10k")
    (at 100 100 0)
  )
  (gr_poly
    (pts (xy 0 0) (xy 120 0) (xy 120 170) (xy 0 170))
    (layer "Edge.Cuts") (width 0.1)
  )
)
""",
    )
    meta = extract_kicad_metadata(pcb)
    assert meta.board_width == 120.0
    assert meta.board_height == 170.0


def test_dimensions_from_gr_line_rectangle(tmp_path):
    pcb = _write_pcb(
        tmp_path,
        "test.kicad_pcb",
        """(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal))
  (net 0 "")
  (footprint "Resistor_SMD:R_0805_2012Metric" (layer "F.Cu")
    (property "Reference" "R1") (property "Value" "10k")
    (at 100 100 0)
  )
  (gr_line (start 0 0) (end 80 0) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 80 0) (end 80 60) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 80 60) (end 0 60) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 0 60) (end 0 0) (layer "Edge.Cuts") (width 0.1))
)
""",
    )
    meta = extract_kicad_metadata(pcb)
    assert meta.board_width == 80.0
    assert meta.board_height == 60.0


def test_dimensions_from_gr_rect(tmp_path):
    pcb = _write_pcb(
        tmp_path,
        "test.kicad_pcb",
        """(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal))
  (net 0 "")
  (gr_rect (start 0 0) (end 90 140) (layer "Edge.Cuts") (width 0.1))
)
""",
    )
    meta = extract_kicad_metadata(pcb)
    assert meta.board_width == 90.0
    assert meta.board_height == 140.0


def test_dimensions_from_gr_circle(tmp_path):
    pcb = _write_pcb(
        tmp_path,
        "test.kicad_pcb",
        """(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal))
  (net 0 "")
  (gr_circle (center 50 50) (end 75 50) (layer "Edge.Cuts") (width 0.1))
)
""",
    )
    meta = extract_kicad_metadata(pcb)
    # Circle of radius 25 centered at (50,50): bounding box 25..75
    assert meta.board_width == 50.0
    assert meta.board_height == 50.0


def test_dimensions_from_gr_arc(tmp_path):
    pcb = _write_pcb(
        tmp_path,
        "test.kicad_pcb",
        """(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal))
  (net 0 "")
  (gr_arc (start 10 20) (mid 15 35) (end 30 20) (layer "Edge.Cuts") (width 0.1))
)
""",
    )
    meta = extract_kicad_metadata(pcb)
    # Bounding box of the 3 defining points
    assert meta.board_width == 20.0  # 30 - 10
    assert meta.board_height == 15.0  # 35 - 20


# --- Error path ---


def test_no_edge_cuts_raises_clear_exception(tmp_path):
    pcb = _write_pcb(
        tmp_path,
        "test.kicad_pcb",
        """(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal))
  (net 0 "")
)
""",
    )
    with pytest.raises(ValueError, match="No Edge.Cuts geometry found"):
        extract_kicad_metadata(pcb)


def test_zero_area_edge_cuts_raises_clear_exception(tmp_path):
    pcb = _write_pcb(
        tmp_path,
        "test.kicad_pcb",
        """(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal))
  (net 0 "")
  (gr_line (start 50 50) (end 50 50) (layer "Edge.Cuts") (width 0.1))
)
""",
    )
    with pytest.raises(ValueError, match="degenerates to zero area"):
        extract_kicad_metadata(pcb)
