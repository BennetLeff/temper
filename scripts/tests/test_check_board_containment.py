"""Unit tests for the board-containment gate (R26 invariant, R38 corpus).

Both halves of R9 are asserted here: the gate must be SILENT on the
committed board and must FIRE on a seeded off-board defect. A gate that
only ever passes certifies nothing, and a gate that fires on everything is
not a measurement -- so neither half is optional.

The synthetic-board tests build minimal boards in a tmp dir rather than
mutating any committed artifact; ``pcb/temper.kicad_pcb`` is read-only to
this suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_board_containment as gate  # noqa: E402
from board_defect_mutator import apply_mutation  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"

# The off-board seed from scripts/board_defect_corpus.yaml.
OFF_BOARD_REF = "C26"
OFF_BOARD_POSITION = [59.38, 256.0]


@pytest.mark.skipif(not BOARD.exists(), reason="committed board not present")
class TestAgainstTheCommittedBoard:
    def test_clean_board_has_no_copper_outside_the_outline(self):
        """R9 half 1: the gate is silent on the clean board."""
        report = gate.analyze_board(BOARD)
        assert report.ok, [v.detail for v in report.violations]
        assert report.violations == []
        assert report.footprints_checked > 0
        assert report.pads_checked > 0

    def test_clean_board_exits_zero(self):
        assert gate.main(["--board", str(BOARD)]) == gate.EXIT_OK

    def test_outline_is_the_boards_real_extent(self):
        report = gate.analyze_board(BOARD)
        x0, y0, x1, y1 = report.outline_bounds_mm
        assert (x1 - x0) > 1.0 and (y1 - y0) > 1.0

    def test_fires_on_the_seeded_off_board_defect(self, tmp_path):
        """R9 half 2: the gate fires on the corpus's off-board seed, and
        names the exact ref the mutator moved."""
        mutated = tmp_path / "off_board.kicad_pcb"
        apply_mutation(
            BOARD,
            "off-board",
            {"ref": OFF_BOARD_REF, "position_mm": OFF_BOARD_POSITION},
            1,
            mutated,
        )
        report = gate.analyze_board(mutated)
        assert not report.ok
        assert OFF_BOARD_REF in report.refs_outside()
        assert all(v.fully_outside for v in report.violations if v.ref == OFF_BOARD_REF)

    def test_seeded_defect_exits_one(self, tmp_path):
        mutated = tmp_path / "off_board.kicad_pcb"
        apply_mutation(
            BOARD,
            "off-board",
            {"ref": OFF_BOARD_REF, "position_mm": OFF_BOARD_POSITION},
            1,
            mutated,
        )
        assert gate.main(["--board", str(mutated)]) == gate.EXIT_VIOLATION

    def test_only_the_mutated_ref_is_reported(self, tmp_path):
        """The seeded defect must not drag unrelated refs into the finding
        -- otherwise the gate is not localising anything."""
        mutated = tmp_path / "off_board.kicad_pcb"
        apply_mutation(
            BOARD,
            "off-board",
            {"ref": OFF_BOARD_REF, "position_mm": OFF_BOARD_POSITION},
            1,
            mutated,
        )
        assert gate.analyze_board(mutated).refs_outside() == {OFF_BOARD_REF}


class TestFailsClosed:
    def test_missing_board_is_gate_error_not_pass(self, tmp_path):
        assert gate.main(["--board", str(tmp_path / "nope.kicad_pcb")]) == gate.EXIT_GATE_ERROR

    def test_board_without_edge_cuts_is_gate_error(self, tmp_path):
        """A board whose outline cannot be determined must never be
        reported as 'everything is inside it'."""
        board = tmp_path / "no_outline.kicad_pcb"
        board.write_text(_MINIMAL_BOARD_NO_OUTLINE, encoding="utf-8")
        with pytest.raises(gate.GateError, match="Edge.Cuts"):
            gate.analyze_board(board)
        assert gate.main(["--board", str(board)]) == gate.EXIT_GATE_ERROR

    def test_unparseable_board_is_gate_error(self, tmp_path):
        board = tmp_path / "garbage.kicad_pcb"
        board.write_text("this is not an s-expression", encoding="utf-8")
        assert gate.main(["--board", str(board)]) == gate.EXIT_GATE_ERROR


class TestSyntheticGeometry:
    """Directional checks on a board small enough to reason about by hand."""

    def _write(self, tmp_path, pad_x, pad_y, angle=0):
        board = tmp_path / "synthetic.kicad_pcb"
        board.write_text(
            _MINIMAL_BOARD_TEMPLATE.format(x=pad_x, y=pad_y, angle=angle),
            encoding="utf-8",
        )
        return board

    def test_pad_well_inside_passes(self, tmp_path):
        report = gate.analyze_board(self._write(tmp_path, 50, 50))
        assert report.ok

    def test_pad_beyond_the_edge_fails_as_fully_outside(self, tmp_path):
        report = gate.analyze_board(self._write(tmp_path, 150, 50))
        assert not report.ok
        assert report.violations[0].fully_outside
        assert report.violations[0].ref == "R1"

    def test_pad_straddling_the_edge_fails_as_straddling(self, tmp_path):
        # Outline is 0..100; a 2x1mm pad centred at x=99.9 hangs over it.
        report = gate.analyze_board(self._write(tmp_path, 99.9, 50))
        assert not report.ok
        assert not report.violations[0].fully_outside
        assert report.violations[0].outside_area_mm2 > 0

    def test_rotation_is_honoured(self, tmp_path):
        # A 2x1mm pad centred 0.6mm inside the edge fits when its long axis
        # is parallel to the edge (rot 90) and hangs over it at rot 0.
        assert not gate.analyze_board(self._write(tmp_path, 99.4, 50, angle=0)).ok
        assert gate.analyze_board(self._write(tmp_path, 99.4, 50, angle=90)).ok


_MINIMAL_BOARD_NO_OUTLINE = """(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
)
"""

# One 2.0 x 1.0 mm pad on one footprint, inside a 0,0 - 100,100 outline.
_MINIMAL_BOARD_TEMPLATE = """(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  (gr_poly (pts (xy 0 0) (xy 100 0) (xy 100 100) (xy 0 100))
    (layer "Edge.Cuts") (width 0.1))
  (footprint "test:R" (layer "F.Cu")
    (at {x} {y} {angle})
    (property "Reference" "R1")
    (property "Sheetpath" "test.r1")
    (pad "1" smd rect (at 0 0 {angle}) (size 2.0 1.0) (layers "F.Cu"))
  )
)
"""
