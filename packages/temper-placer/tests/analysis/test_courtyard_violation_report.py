"""Tests for courtyard violation report — U1 decision-support report."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from temper_placer.analysis._violation_report import (
    _generate_report_rows,
    _render_report,
    generate_violation_report,
)
from temper_placer.validation._drc_api import DrcError, is_kicad_cli_available

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _write_pcb(tmp_path: Path, name: str, content: str) -> Path:
    pcb_path = tmp_path / name
    pcb_path.write_text(content)
    return pcb_path


# --- Unit: _generate_report_rows filtering ---


class _FakeCourtyard:
    def __init__(self, area: float = 10.0):
        self._polygon = MagicMock(area=area)

    def get_global_polygon(self, x: float, y: float, rotation_idx: int):
        from shapely.geometry import Point

        return Point(x, y).buffer(5.0)


class _FakeMeta:
    def __init__(self):
        self.courtyards = {
            "D3": _FakeCourtyard(),
            "C4": _FakeCourtyard(),
            "R7": _FakeCourtyard(),
        }


def test_filters_to_target_rules_only():
    errors = [
        DrcError(
            rule="courtyards_overlap",
            severity="error",
            location=(10.0, 20.0),
            message="Courtyards overlap",
            components=["D3", "C4"],
        ),
        DrcError(
            rule="clearance",
            severity="error",
            location=(5.0, 5.0),
            message="Clearance violation",
            components=["R1"],
        ),
        DrcError(
            rule="pth_inside_courtyard",
            severity="error",
            location=(30.0, 40.0),
            message="PTH inside courtyard",
            components=["R7"],
        ),
    ]
    meta = _FakeMeta()
    rows = _generate_report_rows(errors, meta, {})
    assert len(rows) == 2
    rules = {r["rule"] for r in rows}
    assert rules == {"courtyards_overlap", "pth_inside_courtyard"}


def test_courtyard_overlap_with_two_refs_has_overlap_area():
    errors = [
        DrcError(
            rule="courtyards_overlap",
            severity="error",
            location=(10.0, 20.0),
            message="overlap",
            components=["D3", "C4"],
        ),
    ]
    meta = _FakeMeta()
    positions = {"D3": (50.0, 50.0, 0), "C4": (50.0, 50.0, 0)}
    rows = _generate_report_rows(errors, meta, positions)
    assert len(rows) == 1
    assert rows[0]["overlap_area_mm2"] > 0


def test_pth_with_single_ref_reported_without_overlap_area():
    errors = [
        DrcError(
            rule="pth_inside_courtyard",
            severity="error",
            location=(30.0, 40.0),
            message="PTH inside",
            components=["R7"],
        ),
    ]
    meta = _FakeMeta()
    rows = _generate_report_rows(errors, meta, {})
    assert len(rows) == 1
    assert rows[0]["overlap_area_mm2"] == 0.0
    assert rows[0]["n_components"] == 1


# --- Unit: _render_report ---


def test_render_report_includes_sections():
    rows = [
        {
            "rule": "courtyards_overlap",
            "refs_sorted": ["D3", "C4"],
            "location_x": 10.0,
            "location_y": 20.0,
            "overlap_area_mm2": 5.5,
            "message": "Courtyards overlap D3 and C4",
            "n_components": 2,
            "components": ["D3", "C4"],
        },
        {
            "rule": "pth_inside_courtyard",
            "refs_sorted": ["R7"],
            "location_x": 30.0,
            "location_y": 40.0,
            "overlap_area_mm2": 0.0,
            "message": "PTH inside R7 courtyard",
            "n_components": 1,
            "components": ["R7"],
        },
    ]
    report = _render_report(rows)
    assert "Courtyard / PTH Violation-Pair Decision-Support Report" in report
    assert "courtyards_overlap" in report
    assert "pth_inside_courtyard" in report
    assert "D3, C4" in report
    assert "R7" in report
    assert "does **not** judge" in report
    assert "Summary" in report


# --- Integration: synthetic fixture (requires kicad-cli) ---


@pytest.mark.integration
def test_synthetic_fixture_yields_expected_violation(tmp_path):
    if not is_kicad_cli_available():
        pytest.skip("kicad-cli not available")

    content = """(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (39 "F.CrtYd" user))
  (net 0 "")
  (net 1 "N1")
  (footprint "Resistor_SMD:R_0805_2012Metric" (layer "F.Cu")
    (tedit "0") (tstamp "00000000-0000-0000-0000-000000000001")
    (at 50 50 0)
    (property "Reference" "R1") (property "Value" "10k")
    (fp_rect (start -1.5 -1.0) (end 1.5 1.0) (layer "F.CrtYd") (width 0.05))
    (pad "1" smd rect (at -0.9 0) (size 1.0 1.2) (layers "F.Cu") (net 1 "N1"))
    (pad "2" smd rect (at 0.9 0) (size 1.0 1.2) (layers "F.Cu") (net 1 "N1"))
  )
  (footprint "Resistor_SMD:R_0805_2012Metric" (layer "F.Cu")
    (tedit "0") (tstamp "00000000-0000-0000-0000-000000000002")
    (at 50 50 0)
    (property "Reference" "R2") (property "Value" "10k")
    (fp_rect (start -1.5 -1.0) (end 1.5 1.0) (layer "F.CrtYd") (width 0.05))
    (pad "1" smd rect (at -0.9 0) (size 1.0 1.2) (layers "F.Cu") (net 1 "N1"))
    (pad "2" smd rect (at 0.9 0) (size 1.0 1.2) (layers "F.Cu") (net 1 "N1"))
  )
  (gr_poly
    (pts (xy 0 0) (xy 100 0) (xy 100 100) (xy 0 100))
    (layer "Edge.Cuts") (width 0.1)
  )
)
"""
    pcb = _write_pcb(tmp_path, "overlap.kicad_pcb", content)
    report, counts = generate_violation_report(pcb)
    assert counts["courtyards_overlap"] >= 1
    assert "R1" in report
    assert "R2" in report
    assert "Summary" in report


# --- Integration: production board smoke test ---


@pytest.mark.integration
def test_real_board_violation_count_in_expected_range():
    pcb_path = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
    if not pcb_path.exists():
        pytest.skip("Production PCB not available")
    if not is_kicad_cli_available():
        pytest.skip("kicad-cli not available")

    report, counts = generate_violation_report(pcb_path)

    courtyard_count = counts["courtyards_overlap"]
    pth_count = counts["pth_inside_courtyard"]

    # Re-baselined 2026-07-31 against pcb/temper.kicad_pcb @
    # 54372bbf (2026-07-29, "separate C25/C26 tank capacitor courtyards"):
    # measured courtyards_overlap=14, pth_inside_courtyard=9, report 2190
    # chars. Previous range (27-29 / 16-18) predates that board change
    # (the tank-cap courtyard split removed the overlap). Bands leave
    # headroom for run-to-run DRC noise without hiding a real regression.
    assert 12 <= courtyard_count <= 18, f"Expected ~14 courtyards_overlap, got {courtyard_count}"
    assert 7 <= pth_count <= 12, f"Expected ~9 pth_inside_courtyard, got {pth_count}"
    assert len(report) > 100

    print(
        f"\n  Production board violation report:"
        f"\n    courtyards_overlap:    {courtyard_count}"
        f"\n    pth_inside_courtyard:  {pth_count}"
        f"\n    Total filtered:        {courtyard_count + pth_count}"
        "\n  Anti-false-zero verification:"
        f"\n    - Report non-empty:    {len(report) > 100}"
        f"\n    - Has Summary section: {'Summary' in report}"
    )
