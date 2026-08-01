"""Tests for area-sufficiency check — courtyard-area vs. usable-board-area tool."""

import math
import subprocess
from pathlib import Path

import pytest

from temper_placer.analysis._area_sufficiency import (
    compute_area_sufficiency,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPT = _REPO_ROOT / "packages/temper-placer/scripts/analysis/area_sufficiency_check.py"


def _write_pcb(tmp_path: Path, name: str, content: str) -> Path:
    pcb_path = tmp_path / name
    pcb_path.write_text(content)
    return pcb_path


def _make_board(
    width: float,
    height: float,
    footprints: str = "",
) -> str:
    return f"""(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (39 "F.CrtYd" user) (41 "B.CrtYd" user))
  (net 0 "")
  (net 1 "N1")
{footprints}
  (gr_poly
    (pts (xy 0 0) (xy {width:.1f} 0) (xy {width:.1f} {height:.1f}) (xy 0 {height:.1f}))
    (layer "Edge.Cuts") (width 0.1)
  )
)
"""


def _footprint(ref: str, at_x: float, at_y: float, rect_w: float, rect_h: float) -> str:
    hw = rect_w / 2.0
    hh = rect_h / 2.0
    return f"""  (footprint "test:{ref}" (layer "F.Cu")
    (property "Reference" "{ref}") (property "Value" "test")
    (at {at_x:.1f} {at_y:.1f} 0)
    (fp_rect (start {-hw:.2f} {-hh:.2f}) (end {hw:.2f} {hh:.2f}) (layer "F.CrtYd") (width 0.1))
    (pad "1" smd rect (at 0 0) (size 1.0 1.0) (layers "F.Cu") (net 1 "N1"))
  )
"""


# --- Synthetic pass case ---


def test_synthetic_pass_raw_ratio_under_100(tmp_path):
    """Board 100x100mm, one 10x10mm courtyard -> raw ratio ~1.2% (well under 100)."""
    content = _make_board(100.0, 100.0, _footprint("R1", 50.0, 50.0, 10.0, 10.0))
    pcb = _write_pcb(tmp_path, "pass.kicad_pcb", content)

    result = compute_area_sufficiency(pcb, margin_mm=5.0)
    assert result.usable_area_mm2 == 8100.0  # (100-10)*(100-10)
    assert math.isclose(result.total_courtyard_area_mm2, 100.0, rel_tol=0.01)
    assert result.raw_ratio_pct < 100.0
    expected_pct = 100.0 / 8100.0 * 100.0
    assert math.isclose(result.raw_ratio_pct, expected_pct, rel_tol=0.01)


# --- Synthetic fail case ---


def test_synthetic_fail_raw_ratio_over_100(tmp_path):
    """Board 20x20mm, one 20x20mm courtyard -> exactly 400%."""
    content = _make_board(20.0, 20.0, _footprint("BIG1", 10.0, 10.0, 20.0, 20.0))
    pcb = _write_pcb(tmp_path, "fail.kicad_pcb", content)

    result = compute_area_sufficiency(pcb, margin_mm=5.0)
    assert result.usable_area_mm2 == 100.0  # (20-10)*(20-10)
    # FpRect from (-10,-10) to (10,10) = 20x20 = 400 mm^2
    assert math.isclose(result.total_courtyard_area_mm2, 400.0, rel_tol=0.01)
    assert result.raw_ratio_pct == 400.0


# --- Margin effect ---


def test_larger_margin_decreases_usable_area(tmp_path):
    content = _make_board(100.0, 100.0, _footprint("R1", 50.0, 50.0, 10.0, 10.0))
    pcb = _write_pcb(tmp_path, "margin.kicad_pcb", content)

    r5 = compute_area_sufficiency(pcb, margin_mm=5.0)
    r10 = compute_area_sufficiency(pcb, margin_mm=10.0)

    assert r5.usable_area_mm2 > r10.usable_area_mm2
    assert r5.raw_ratio_pct < r10.raw_ratio_pct


# --- Zero margin ---


def test_zero_margin_uses_full_board_area(tmp_path):
    content = _make_board(100.0, 100.0)
    pcb = _write_pcb(tmp_path, "zero_margin.kicad_pcb", content)

    result = compute_area_sufficiency(pcb, margin_mm=0.0)
    assert result.usable_area_mm2 == 10000.0


# --- Non-positive usable area raises ---


def test_margin_larger_than_half_board_raises(tmp_path):
    content = _make_board(10.0, 10.0)
    pcb = _write_pcb(tmp_path, "tiny.kicad_pcb", content)

    with pytest.raises(ValueError, match="Usable board area is non-positive"):
        compute_area_sufficiency(pcb, margin_mm=6.0)


# --- CLI exit codes ---


def test_cli_exit_code_zero_on_pass(tmp_path):
    content = _make_board(200.0, 200.0, _footprint("R1", 100.0, 100.0, 10.0, 10.0))
    pcb = _write_pcb(tmp_path, "cli_pass.kicad_pcb", content)

    result = subprocess.run(
        ["uv", "run", "python", str(_SCRIPT), "--pcb", str(pcb)],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, f"stdout={result.stdout} stderr={result.stderr}"


def test_cli_exit_code_nonzero_on_fail(tmp_path):
    content = _make_board(20.0, 20.0, _footprint("BIG1", 10.0, 10.0, 20.0, 20.0))
    pcb = _write_pcb(tmp_path, "cli_fail.kicad_pcb", content)

    result = subprocess.run(
        ["uv", "run", "python", str(_SCRIPT), "--pcb", str(pcb)],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 2, f"stdout={result.stdout} stderr={result.stderr}"


def test_cli_reports_packing_efficiency_ratios(tmp_path):
    content = _make_board(100.0, 100.0, _footprint("R1", 50.0, 50.0, 10.0, 10.0))
    pcb = _write_pcb(tmp_path, "cli_pe.kicad_pcb", content)

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(_SCRIPT),
            "--pcb",
            str(pcb),
            "--packing-efficiency",
            "0.5",
            "0.8",
        ],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0
    assert "At 50%" in result.stdout
    assert "At 80%" in result.stdout


# --- Regression: real production board ---


def test_real_board_reports_approximately_52_7_pct():
    """Running against pcb/temper.kicad_pcb should report ~52.7% raw ratio and
    exit nonzero.

    Re-baselined 2026-07-31 against pcb/temper.kicad_pcb @ 54372bbf
    (2026-07-29, "separate C25/C26 tank capacitor courtyards"): the
    earlier ~108.5% figure and 149-component count predate that board
    change (courtyard area dropped as tank-cap courtyards were split and
    the component count grew to 169). Measured on that commit:
    raw_ratio_pct=52.73, component_count=169.
    """
    pcb_path = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
    if not pcb_path.exists():
        pytest.skip("Production PCB not available")

    result = compute_area_sufficiency(pcb_path, margin_mm=5.0)
    assert 50.0 <= result.raw_ratio_pct <= 56.0, (
        f"Expected ~52.7%, got {result.raw_ratio_pct:.1f}%"
    )
    assert result.raw_ratio_pct < 100.0
    assert result.component_count == 169

    proc = subprocess.run(
        ["uv", "run", "python", str(_SCRIPT), "--pcb", str(pcb_path)],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    # 52.7% < 100%: the board is now area-sufficient, so the CLI must
    # exit 0 and say so (the old "INSUFFICIENT"/exit-2 assertion matched
    # the pre-54372bbf board that sat at ~108.5%).
    assert proc.returncode == 0, f"stdout={proc.stdout} stderr={proc.stderr}"
    assert "area sufficient" in proc.stdout

    total_area = result.total_courtyard_area_mm2
    usable_area = result.usable_area_mm2
    print(
        f"\n  Production board area check:"
        f"\n    Total courtyard: {total_area:.1f} mm^2"
        f"\n    Usable area:     {usable_area:.1f} mm^2"
        f"\n    Raw ratio:       {result.raw_ratio_pct:.1f}%"
        f"\n    Components:      {result.component_count}"
        "\n  Anti-false-zero verification:"
        f"\n    - Courtyard area > 0:   {total_area > 0}"
        f"\n    - Usable area > 0:     {usable_area > 0}"
        f"\n    - Component count > 0: {result.component_count > 0}"
        "\n    All three must be True to rule out degenerate/silent-fallback output."
    )
    assert total_area > 0, "Courtyard area is zero — degenerate run"
    assert usable_area > 0, "Usable area is zero — degenerate run"
    assert result.component_count > 0, "Component count is zero — degenerate run"
