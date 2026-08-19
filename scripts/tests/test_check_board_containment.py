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


class TestEdgeCutsShapeCoverage:
    """Every Edge.Cuts primitive that can carry an outline must be read.

    Each test here FAILS on the pre-2026-08-18 parser, which understood
    only ``gr_poly`` and "anything with start/end, as a straight segment".
    That blind spot is why ``check_corpus_specificity.py`` was red: the
    corpus's ``temper`` and ``minimal`` boards state their entire outline
    as one ``gr_rect``, which became a single diagonal segment and could
    never close.
    """

    def _board(self, tmp_path, outline, pad_x, pad_y, name="shape.kicad_pcb"):
        board = tmp_path / name
        board.write_text(
            _SHAPE_BOARD_TEMPLATE.format(outline=outline, x=pad_x, y=pad_y),
            encoding="utf-8",
        )
        return board

    def test_gr_rect_outline_is_a_rectangle_not_its_diagonal(self, tmp_path):
        outline = '(gr_rect (start 0 0) (end 100 100) (layer "Edge.Cuts") (width 0.1))'
        report = gate.analyze_board(self._board(tmp_path, outline, 50, 50))
        assert report.ok, [v.detail for v in report.violations]
        assert report.outline_bounds_mm == (0.0, 0.0, 100.0, 100.0)

    def test_gr_rect_outline_still_catches_copper_outside_it(self, tmp_path):
        """Anti-vacuity: reading gr_rect must not mean accepting anything."""
        outline = '(gr_rect (start 0 0) (end 100 100) (layer "Edge.Cuts") (width 0.1))'
        report = gate.analyze_board(self._board(tmp_path, outline, 150, 50))
        assert not report.ok
        assert report.violations[0].fully_outside

    def test_gr_circle_outline_is_read(self, tmp_path):
        outline = '(gr_circle (center 50 50) (end 90 50) (layer "Edge.Cuts") (width 0.1))'
        report = gate.analyze_board(self._board(tmp_path, outline, 50, 50))
        assert report.ok, [v.detail for v in report.violations]

    def test_gr_circle_outline_still_catches_copper_outside_it(self, tmp_path):
        outline = '(gr_circle (center 50 50) (end 90 50) (layer "Edge.Cuts") (width 0.1))'
        report = gate.analyze_board(self._board(tmp_path, outline, 95, 50))
        assert not report.ok

    def test_unhandled_edge_cuts_primitive_is_a_gate_error(self):
        """A shape this gate does not understand must stop it, not be
        skipped -- silently dropping one is how an outline reads smaller
        than the board."""

        class _UnknownEdgeItem:
            layer = "Edge.Cuts"

        class _FakeBoard:
            graphicItems = [_UnknownEdgeItem()]

        with pytest.raises(gate.GateError, match="unhandled"):
            gate.extract_outline(_FakeBoard())


class TestOutlineAssemblyFailsClosed:
    """An outline that will not close is a gate error, never a smaller board."""

    def _board(self, tmp_path, outline, pad_x, pad_y):
        board = tmp_path / "assembly.kicad_pcb"
        board.write_text(
            _SHAPE_BOARD_TEMPLATE.format(outline=outline, x=pad_x, y=pad_y),
            encoding="utf-8",
        )
        return board

    def test_open_outline_is_not_silently_replaced_by_a_closed_slot(self, tmp_path):
        """The piantor_right shape, minimised.

        A 100x100 outline with a 5 mm gap, plus a closed 5x5 internal slot.
        The pre-fix assembler kept "the largest ring that closed" and raised
        only when nothing closed, so the SLOT became the board and a pad at
        the board's centre was reported outside it. Now the open contour
        itself is the error.
        """
        outline = (
            '(gr_line (start 0 0) (end 100 0) (layer "Edge.Cuts") (width 0.1))\n'
            '  (gr_line (start 100 0) (end 100 100) (layer "Edge.Cuts") (width 0.1))\n'
            '  (gr_line (start 100 100) (end 5 100) (layer "Edge.Cuts") (width 0.1))\n'
            '  (gr_line (start 0 100) (end 0 0) (layer "Edge.Cuts") (width 0.1))\n'
            '  (gr_line (start 40 40) (end 45 40) (layer "Edge.Cuts") (width 0.1))\n'
            '  (gr_line (start 45 40) (end 45 45) (layer "Edge.Cuts") (width 0.1))\n'
            '  (gr_line (start 45 45) (end 40 45) (layer "Edge.Cuts") (width 0.1))\n'
            '  (gr_line (start 40 45) (end 40 40) (layer "Edge.Cuts") (width 0.1))'
        )
        with pytest.raises(gate.GateError, match="open contour"):
            gate.analyze_board(self._board(tmp_path, outline, 50, 50))

    def test_one_nanometre_seam_still_closes(self, tmp_path):
        """KiCad's internal unit IS 1 nm, so a 1 nm seam is a real file
        shape, not corruption. The pre-fix tolerance was exactly 1e-6 mm,
        i.e. exactly that quantum, so whether a seam closed came down to
        float64 rounding AT THE COORDINATE'S OWN MAGNITUDE:

            abs(100.000001 - 100.0)   == 9.999999974752427e-07  -> closed
            abs(113.600001 - 113.6)   == 1.0000000116860974e-06 -> REJECTED

        The literal 113.6 here is not arbitrary: it is the y coordinate at
        which power_pcb_dataset/corpus/piantor_right/keyboard_pcb.kicad_pcb
        joins, and the reason that board's entire 40-segment outline was
        rejected. A test written at 100.0 would pass against the pre-fix
        code and prove nothing.
        """
        outline = (
            '(gr_line (start 0 0) (end 113.6 0) (layer "Edge.Cuts") (width 0.1))\n'
            '  (gr_line (start 113.6 0) (end 113.6 113.6) (layer "Edge.Cuts") (width 0.1))\n'
            '  (gr_line (start 113.6 113.6) (end 0 113.600001) (layer "Edge.Cuts") (width 0.1))\n'
            '  (gr_line (start 0 113.6) (end 0 0) (layer "Edge.Cuts") (width 0.1))'
        )
        report = gate.analyze_board(self._board(tmp_path, outline, 50, 50))
        assert report.ok, [v.detail for v in report.violations]
        assert report.outline_bounds_mm[2] == 113.6

    def test_a_real_gap_is_still_rejected(self, tmp_path):
        """Anti-vacuity for the tolerance: 1 um admits a seam, not a gap."""
        outline = (
            '(gr_line (start 0 0) (end 100 0) (layer "Edge.Cuts") (width 0.1))\n'
            '  (gr_line (start 100 0) (end 100 100) (layer "Edge.Cuts") (width 0.1))\n'
            '  (gr_line (start 100 100) (end 0 101) (layer "Edge.Cuts") (width 0.1))\n'
            '  (gr_line (start 0 100) (end 0 0) (layer "Edge.Cuts") (width 0.1))'
        )
        with pytest.raises(gate.GateError, match="closed outline"):
            gate.analyze_board(self._board(tmp_path, outline, 50, 50))


class TestPadShapeIsNotAlwaysARectangle:
    """A circular pad is a circle, not its circumscribing square.

    The bitaxe_ultra shape, minimised: a pad tucked into a chamfered board
    corner. Its bounding-box corner crosses the chamfer; its real copper
    does not. Modelling every pad as a box produced 4 false positives on
    that board and left them recorded as possibly-real annular-ring
    overhang.
    """

    def _board(self, tmp_path, shape):
        # 100x100 with the (100,100) corner cut on the line x + y = 195.
        outline = (
            '(gr_poly (pts (xy 0 0) (xy 100 0) (xy 100 95) (xy 95 100) (xy 0 100))\n'
            '    (layer "Edge.Cuts") (width 0.1))'
        )
        board = tmp_path / f"pad_{shape}.kicad_pcb"
        board.write_text(
            _PAD_SHAPE_BOARD_TEMPLATE.format(outline=outline, shape=shape),
            encoding="utf-8",
        )
        return board

    def test_circle_pad_inside_the_chamfer_is_clean(self, tmp_path):
        # Centre (96,96), diameter 4: distance to the chamfer is
        # |96+96-195|/sqrt(2) = 2.121 mm > the 2 mm radius.
        report = gate.analyze_board(self._board(tmp_path, "circle"))
        assert report.ok, [v.detail for v in report.violations]

    def test_the_same_pad_as_a_rect_does_cross_the_chamfer(self, tmp_path):
        """Anti-vacuity: the geometry really is tight enough to bite, so
        the circle test above is passing on shape and not on slack. The
        square's (98,98) corner sums to 196 > 195."""
        report = gate.analyze_board(self._board(tmp_path, "rect"))
        assert not report.ok
        assert report.violations[0].outside_area_mm2 > 0

    def test_oval_pad_is_a_stadium_not_a_box(self, tmp_path):
        report = gate.analyze_board(self._board(tmp_path, "oval"))
        assert report.ok, [v.detail for v in report.violations]


class TestReferenceDesignatorResolution:
    """KiCad <= 8 stores the designator as ``fp_text reference``.

    Reading only ``property "Reference"`` made every footprint on such a
    board anonymous, and ``refs_outside()`` is a set -- so 310 violations
    on piantor_right collapsed to one ``<no Reference>`` entry.
    """

    def test_fp_text_reference_is_used_when_no_property_exists(self, tmp_path):
        board = tmp_path / "legacy_ref.kicad_pcb"
        board.write_text(_LEGACY_REF_BOARD, encoding="utf-8")
        report = gate.analyze_board(board)
        assert not report.ok
        assert report.refs_outside() == {"R9"}
        assert "<no Reference>" not in report.refs_outside()


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


# Outline is parameterised so one template covers gr_rect/gr_circle/gr_line
# cases; the pad is a 2.0 x 1.0 mm rect, as in _MINIMAL_BOARD_TEMPLATE.
_SHAPE_BOARD_TEMPLATE = """(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  {outline}
  (footprint "test:R" (layer "F.Cu")
    (at {x} {y} 0)
    (property "Reference" "R1")
    (property "Sheetpath" "test.r1")
    (pad "1" smd rect (at 0 0 0) (size 2.0 1.0) (layers "F.Cu"))
  )
)
"""

# One 4.0 x 4.0 mm pad at (96, 96), shape parameterised.
_PAD_SHAPE_BOARD_TEMPLATE = """(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  {outline}
  (footprint "test:H" (layer "F.Cu")
    (at 96 96 0)
    (property "Reference" "H1")
    (property "Sheetpath" "test.h1")
    (pad "1" thru_hole {shape} (at 0 0 0) (size 4.0 4.0) (layers "*.Cu"))
  )
)
"""

# KiCad <= 8 encoding: no (property "Reference"), only (fp_text reference).
# The pad is placed off the outline so the violation carries a name.
_LEGACY_REF_BOARD = """(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  (gr_poly (pts (xy 0 0) (xy 100 0) (xy 100 100) (xy 0 100))
    (layer "Edge.Cuts") (width 0.1))
  (footprint "test:R" (layer "F.Cu")
    (at 150 50 0)
    (fp_text reference "R9" (at 0 0) (layer "F.SilkS")
      (effects (font (size 1 1) (thickness 0.15))))
    (pad "1" smd rect (at 0 0 0) (size 2.0 1.0) (layers "F.Cu"))
  )
)
"""
