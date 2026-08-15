"""Tests for check_stackup_copper_weight_gate.py.

Both the board-stackup parser and the derivation-doc parser are proven
against synthetic scratch fixtures (never mutating real repo files), mirroring
``test_check_layer_plane_emission_coverage.py``'s and
``test_check_netclass_class_param_correspondence.py``'s pattern. A dedicated
class (`TestGateBitesOnDrift`) proves the gate's whole reason for existing:
declaring the board's copper weight at a value that disagrees with
TRACE_WIDTH_CALCULATIONS.md's assumption must flip a clean board to a
VIOLATION -- the exact drift this gate exists to catch (2026-08-13, alongside
the ``(setup (stackup ...))`` block first added to ``pcb/temper.kicad_pcb``).

``TestRealRepoIntegration`` checks the CURRENT, real repository state: as of
this gate's introduction, the board's declared stackup (2oz outer / 1oz
inner) agrees with TRACE_WIDTH_CALCULATIONS.md §1's assumption, so the gate
must report ``clean`` against the live files -- unlike several sibling gates
in this family, which document a still-broken ``origin/main``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_stackup_copper_weight_gate import (  # noqa: E402
    EXIT_VIOLATION,
    GateError,
    Violation,
    compare,
    load_assumed_copper_weight_um,
    load_declared_copper_thickness_um,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
REAL_DERIVATION_DOC = REPO_ROOT / "docs" / "hardware" / "TRACE_WIDTH_CALCULATIONS.md"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _board_text(
    f_cu_mm: float,
    in1_mm: float,
    in2_mm: float,
    b_cu_mm: float,
    *,
    in3_mm: float | None = None,
    in4_mm: float | None = None,
) -> str:
    """A minimal scratch ``.kicad_pcb`` with only a ``(setup (stackup ...))``
    block -- the gate never reads geometry, so nothing else is needed.

    UPDATED 2026-08-13 (layer-architecture SSOT): 6 copper layers, matching
    the real board's post-decision stackup (F.Cu / In3.Cu / In1.Cu / In2.Cu
    / In4.Cu / B.Cu) -- ``INNER_LAYERS`` now requires In3.Cu/In4.Cu to be
    present in any board this gate checks, real or synthetic, so every
    fixture needs them too. ``in3_mm``/``in4_mm`` default to ``in1_mm`` when
    omitted (the common case: "both new inner layers match the existing
    inner assumption"), so single-drift tests that only vary
    ``in1_mm``/``in2_mm`` don't need every call site updated.
    """
    if in3_mm is None:
        in3_mm = in1_mm
    if in4_mm is None:
        in4_mm = in1_mm
    return f"""(kicad_pcb (version 20211014) (generator kiutils)

  (setup
    (stackup
      (layer "F.SilkS" (type "Top Silk Screen"))
      (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
      (layer "F.Cu" (type "copper") (thickness {f_cu_mm}))
      (layer "dielectric 1" (type "prepreg") (thickness 0.15) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
      (layer "In3.Cu" (type "copper") (thickness {in3_mm}))
      (layer "dielectric 2" (type "prepreg") (thickness 0.15) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
      (layer "In1.Cu" (type "copper") (thickness {in1_mm}))
      (layer "dielectric 3" (type "core") (thickness 0.72) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
      (layer "In2.Cu" (type "copper") (thickness {in2_mm}))
      (layer "dielectric 4" (type "prepreg") (thickness 0.15) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
      (layer "In4.Cu" (type "copper") (thickness {in4_mm}))
      (layer "dielectric 5" (type "prepreg") (thickness 0.15) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness {b_cu_mm}))
      (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
      (layer "B.SilkS" (type "Bottom Silk Screen"))
      (copper_finish "ENIG")
      (dielectric_constraints no)
    )
    (pad_to_mask_clearance 0)
  )

  (net 0 "")
)
"""


_DERIVATION_DOC_TEXT = """# Temper PCB Trace Width Calculations

## 1. Design Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Ambient Temperature | 60C | Worst-case kitchen environment |
| Outer Copper Weight | 2 oz (70 µm) | JLCPCB capability |
| Inner Copper Weight | 1 oz (35 µm) | Standard for 4-layer |
| Board Thickness | 1.6mm | Standard FR4 |
"""


# ---------------------------------------------------------------------------
# Board stackup parser
# ---------------------------------------------------------------------------


class TestLoadDeclaredCopperThickness:
    def test_2oz_outer_1oz_inner(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text(0.07, 0.035, 0.035, 0.07))
        declared = load_declared_copper_thickness_um(board)
        assert declared == {
            "F.Cu": 70.0,
            "In3.Cu": 35.0,
            "In1.Cu": 35.0,
            "In2.Cu": 35.0,
            "In4.Cu": 35.0,
            "B.Cu": 70.0,
        }

    def test_missing_stackup_block_fails_closed(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text('(kicad_pcb (version 20211014)\n  (setup\n    (pad_to_mask_clearance 0)\n  )\n)\n')
        with pytest.raises(GateError, match="stackup"):
            load_declared_copper_thickness_um(board)

    def test_missing_setup_block_fails_closed(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text("(kicad_pcb (version 20211014)\n)\n")
        with pytest.raises(GateError, match="setup"):
            load_declared_copper_thickness_um(board)

    def test_missing_board_file_fails_closed(self, tmp_path):
        with pytest.raises(GateError, match="not found"):
            load_declared_copper_thickness_um(tmp_path / "nonexistent.kicad_pcb")


# ---------------------------------------------------------------------------
# Derivation-doc parser
# ---------------------------------------------------------------------------


class TestLoadAssumedCopperWeight:
    def test_parses_outer_and_inner_rows(self, tmp_path):
        doc = tmp_path / "TRACE_WIDTH_CALCULATIONS.md"
        doc.write_text(_DERIVATION_DOC_TEXT)
        assert load_assumed_copper_weight_um(doc) == {"outer": 70.0, "inner": 35.0}

    def test_missing_outer_row_fails_closed(self, tmp_path):
        doc = tmp_path / "TRACE_WIDTH_CALCULATIONS.md"
        doc.write_text("# doc\n\n| Inner Copper Weight | 1 oz (35 µm) | x |\n")
        with pytest.raises(GateError, match="outer"):
            load_assumed_copper_weight_um(doc)

    def test_missing_doc_fails_closed(self, tmp_path):
        with pytest.raises(GateError, match="not found"):
            load_assumed_copper_weight_um(tmp_path / "nonexistent.md")


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


class TestCompare:
    def test_matching_weights_produce_no_violations(self):
        declared = {
            "F.Cu": 70.0,
            "In3.Cu": 35.0,
            "In1.Cu": 35.0,
            "In2.Cu": 35.0,
            "In4.Cu": 35.0,
            "B.Cu": 70.0,
        }
        assumed = {"outer": 70.0, "inner": 35.0}
        assert compare(declared, assumed) == []

    def test_within_tolerance_rounding_produces_no_violations(self):
        # 0.5um tolerance absorbs mm-to-um round-trip rounding.
        declared = {
            "F.Cu": 70.2,
            "In3.Cu": 35.1,
            "In1.Cu": 34.8,
            "In2.Cu": 35.0,
            "In4.Cu": 34.9,
            "B.Cu": 70.0,
        }
        assumed = {"outer": 70.0, "inner": 35.0}
        assert compare(declared, assumed) == []

    def test_missing_layer_fails_closed(self):
        declared = {
            "F.Cu": 70.0,
            "In3.Cu": 35.0,
            "In1.Cu": 35.0,
            "In2.Cu": 35.0,
            "In4.Cu": 35.0,
        }  # B.Cu absent
        assumed = {"outer": 70.0, "inner": 35.0}
        with pytest.raises(GateError, match="B.Cu"):
            compare(declared, assumed)

    def test_missing_new_inner_layer_fails_closed(self):
        """The 2026-08-13 6-layer extension: In3.Cu/In4.Cu are just as
        mandatory as In1.Cu/In2.Cu now -- a board that hasn't declared them
        (e.g. a stale 4-layer board) must fail closed, not silently skip
        the check for layers it doesn't have."""
        declared = {"F.Cu": 70.0, "In1.Cu": 35.0, "In2.Cu": 35.0, "B.Cu": 70.0}  # 4-layer, pre-decision
        assumed = {"outer": 70.0, "inner": 35.0}
        with pytest.raises(GateError, match="In3.Cu"):
            compare(declared, assumed)


# ---------------------------------------------------------------------------
# The gate biting on drift -- this is the property the task requires proven
# ---------------------------------------------------------------------------


class TestGateBitesOnDrift:
    def test_bottom_layer_declared_at_1oz_is_a_violation(self, tmp_path):
        """The exact defect this gate exists to catch: someone (re)declares
        B.Cu at 1oz (0.035mm) while every GateDrive/HighVoltage/Power/ACMains
        derivation in TRACE_WIDTH_CALCULATIONS.md still assumes 2oz outer."""
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text(0.07, 0.035, 0.035, 0.035))  # B.Cu = 1oz
        doc = tmp_path / "TRACE_WIDTH_CALCULATIONS.md"
        doc.write_text(_DERIVATION_DOC_TEXT)  # still assumes 2oz outer

        state, report = run(board, doc)

        assert state == "violation"
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.layer == "B.Cu"
        assert v.role == "outer"
        assert v.declared_um == pytest.approx(35.0)
        assert v.assumed_um == pytest.approx(70.0)

    def test_both_outer_layers_undersized_is_two_violations(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text(0.035, 0.035, 0.035, 0.035))  # F.Cu and B.Cu both 1oz
        doc = tmp_path / "TRACE_WIDTH_CALCULATIONS.md"
        doc.write_text(_DERIVATION_DOC_TEXT)

        state, report = run(board, doc)

        assert state == "violation"
        assert {v.layer for v in report.violations} == {"F.Cu", "B.Cu"}

    def test_inner_layer_drift_is_also_caught(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        # In1.Cu bumped to 2oz; In3.Cu/In4.Cu pinned explicitly to the
        # correct 1oz so this test isolates exactly one drifted layer
        # (relying on _board_text's "defaults to in1_mm" convenience here
        # would silently drift In3.Cu/In4.Cu to 2oz too, producing 3
        # violations instead of the 1 this test's name promises).
        board.write_text(_board_text(0.07, 0.07, 0.035, 0.07, in3_mm=0.035, in4_mm=0.035))
        doc = tmp_path / "TRACE_WIDTH_CALCULATIONS.md"
        doc.write_text(_DERIVATION_DOC_TEXT)

        state, report = run(board, doc)

        assert state == "violation"
        assert len(report.violations) == 1
        assert report.violations[0].layer == "In1.Cu"
        assert report.violations[0].role == "inner"

    def test_fixing_the_drift_clears_the_violation(self, tmp_path):
        """Round-trip: the same board that violates at 1oz B.Cu is clean once
        corrected back to 2oz -- proves the gate is a real comparison, not a
        one-way trap."""
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text(0.07, 0.035, 0.035, 0.035))
        doc = tmp_path / "TRACE_WIDTH_CALCULATIONS.md"
        doc.write_text(_DERIVATION_DOC_TEXT)
        assert run(board, doc)[0] == "violation"

        board.write_text(_board_text(0.07, 0.035, 0.035, 0.07))
        assert run(board, doc)[0] == "clean"

    def test_violation_str_names_the_disagreement(self):
        v = Violation(layer="B.Cu", role="outer", declared_um=35.0, assumed_um=70.0)
        text = str(v)
        assert "B.Cu" in text
        assert "35.000" in text
        assert "70.000" in text


# ---------------------------------------------------------------------------
# Tool-error paths via run()
# ---------------------------------------------------------------------------


class TestRunToolErrors:
    def test_missing_board_is_tool_error(self, tmp_path):
        doc = tmp_path / "TRACE_WIDTH_CALCULATIONS.md"
        doc.write_text(_DERIVATION_DOC_TEXT)
        state, report = run(tmp_path / "nonexistent.kicad_pcb", doc)
        assert state == "tool_error"
        assert report.tool_errors

    def test_missing_doc_is_tool_error(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text(0.07, 0.035, 0.035, 0.07))
        state, report = run(board, tmp_path / "nonexistent.md")
        assert state == "tool_error"
        assert report.tool_errors


# ---------------------------------------------------------------------------
# Exit-code contract
# ---------------------------------------------------------------------------


def test_exit_violation_constant_is_nonzero():
    assert EXIT_VIOLATION == 3


# ---------------------------------------------------------------------------
# Real-repo integration: current committed state must be clean
# ---------------------------------------------------------------------------


class TestRealRepoIntegration:
    def test_real_board_and_doc_agree(self):
        """As of the 2026-08-13 stackup declaration + doc corrections, the
        real pcb/temper.kicad_pcb stackup and the real
        TRACE_WIDTH_CALCULATIONS.md §1 assumption agree: 2oz outer, 1oz
        inner. If this test starts failing, either the stackup drifted or
        the derivation doc's assumption changed without the other -- which
        is exactly the drift this gate exists to catch.

        UPDATED 2026-08-13 (layer-architecture SSOT,
        docs/evidence/2026-08-13-layer-architecture-decision.md): the real
        board now declares 6 copper layers (In3.Cu/In4.Cu added as new
        signal layers, both 1oz -- same inner assumption as the pre-existing
        In1.Cu/In2.Cu planes)."""
        state, report = run(REAL_BOARD, REAL_DERIVATION_DOC)
        assert state == "clean", report.violations
        assert report.assumed_um == {"outer": 70.0, "inner": 35.0}
        assert report.declared_um == {
            "F.Cu": 70.0,
            "In3.Cu": 35.0,
            "In1.Cu": 35.0,
            "In2.Cu": 35.0,
            "In4.Cu": 35.0,
            "B.Cu": 70.0,
        }
