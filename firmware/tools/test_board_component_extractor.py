"""Tests for firmware/tools/board_component_extractor.py (plan 2026-08-02-027, U2).

Synthetic ``.kicad_pcb`` fixtures under ``tmp_path`` (the repo convention:
real files are exercised by running the tool itself, not by tests that
would silently rot with board churn). The synthetic boards mirror the
current board's structure -- one ``gr_poly`` rectangle outline, footprints
keyed by their ``Sheetpath`` property with ``Value`` placeholders -- so a
test failure means the extractor logic is wrong, not that the board
changed.

The one real-board fact pinned here is the outline rectangle the current
board uses (20,20)-(172,254) and the off-outline ``tank.c_tank3``
position (20.0, 272.75) -- the exact defect class this extractor exists
to make visible (a plain refdes/value lookup would PASS it).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from board_component_extractor import BoardParseError, extract_board

# The current board's outline and the staged-off capacitor position --
# reproduced as a fixture so the defect class is a test, not a claim.
OUTLINE = [(20.0, 20.0), (172.0, 20.0), (172.0, 254.0), (20.0, 254.0)]
TANK_CAP_FOOTPRINT = "temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal"
R_REF_FOOTPRINT = "Resistor_SMD:R_0805_2012Metric"

FOOTPRINT_VALUES = {
    TANK_CAP_FOOTPRINT: 100e-9,
    R_REF_FOOTPRINT: 430.0,
}


def _write_board(
    path: Path,
    components: list[tuple[str, str, str, tuple[float, float]]],
    *,
    outline: list[tuple[float, float]] | None = None,
    edge_cuts: bool = True,
    value_props: dict[str, str] | None = None,
) -> Path:
    """Write a synthetic kicad_pcb.

    *components*: list of (sheetpath, refdes, footprint, (x, y)).
    ``Value`` properties default to the board's ``"?"`` placeholder.
    """
    value_props = value_props or {}
    pts = " ".join(f"(xy {x} {y})" for x, y in (outline or OUTLINE))
    gr_poly = f"    (gr_poly (pts {pts}) (layer \"Edge.Cuts\") (width 0.1))\n" if edge_cuts else ""

    lines = [
        "(kicad_pcb (version 20211014) (generator test)",
        "  (layers (44 \"Edge.Cuts\" user))",
        gr_poly,
    ]
    for sheetpath, refdes, footprint, (x, y) in components:
        value = value_props.get(sheetpath, "?")
        lines.append(
            f'  (footprint "{footprint}" (version 20231120) (layer "F.Cu")\n'
            f"    (at {x} {y} 0)\n"
            f'    (property "Reference" "{refdes}")\n'
            f'    (property "Value" "{value}")\n'
            f'    (property "Footprint" "{footprint}")\n'
            f'    (property "Sheetpath" "{sheetpath}")\n'
            "    (attr through_hole)\n"
            "  )"
        )
    lines.append(")")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class TestHappyPath:
    def test_extracts_placed_tank_caps_with_values_via_footprint_decode(
        self, tmp_path: Path
    ) -> None:
        """U2 test scenario 1: the tank capacitors come back placed, with
        their values (footprint decode -- the board's Value fields are the
        '?' placeholder)."""
        board = _write_board(
            tmp_path / "board.kicad_pcb",
            [
                ("tank.c_tank1", "C25", TANK_CAP_FOOTPRINT, (73.42, 52.00)),
                ("tank.c_tank2", "C26", TANK_CAP_FOOTPRINT, (59.38, 28.75)),
                ("tank.c_tank3", "C27", TANK_CAP_FOOTPRINT, (20.0, 254.0)),
            ],
        )
        report = extract_board(board, footprint_values=FOOTPRINT_VALUES)

        assert report.disposition("tank.c_tank1") == "placed"
        assert report.disposition("tank.c_tank2") == "placed"
        assert report.disposition("tank.c_tank3") == "placed"  # exactly on the edge

        comp = report.components["tank.c_tank1"]
        assert comp.refdes == "C25"
        assert comp.footprint == TANK_CAP_FOOTPRINT

        state, value = report.value_state("tank.c_tank1")
        assert state == "value"
        assert value == pytest.approx(100e-9)

    def test_value_property_is_read_directly_when_populated(self, tmp_path: Path) -> None:
        """A netlist-populated board (Value = '100nF') is read directly --
        footprint decode is only the fallback for '?' placeholders."""
        board = _write_board(
            tmp_path / "board.kicad_pcb",
            [("tank.c_tank1", "C25", TANK_CAP_FOOTPRINT, (73.42, 52.00))],
            value_props={"tank.c_tank1": "100nF"},
        )
        report = extract_board(board, footprint_values=FOOTPRINT_VALUES)
        state, value = report.value_state("tank.c_tank1")
        assert state == "value"
        assert value == pytest.approx(100e-9)

    def test_components_are_keyed_by_sheetpath_not_refdes(self, tmp_path: Path) -> None:
        """Keying by Sheetpath (NOT refdes) is the whole point: refdes
        renumber, the Sheetpath is the stable identity. A footprint with
        no Sheetpath (e.g. a mounting hole) is ignored."""
        board = _write_board(
            tmp_path / "board.kicad_pcb",
            [
                ("tank.c_tank1", "C25", TANK_CAP_FOOTPRINT, (73.42, 52.00)),
                ("rtd_pan.r_ref", "R34", R_REF_FOOTPRINT, (52.6, 250.51)),
            ],
        )
        report = extract_board(board, footprint_values=FOOTPRINT_VALUES)
        assert set(report.components) == {"tank.c_tank1", "rtd_pan.r_ref"}
        assert report.components["rtd_pan.r_ref"].refdes == "R34"
        # A refdes lookup for a non-existent refdes is irrelevant: the
        # oracle asks by sheetpath, and an unknown sheetpath is 'absent'.
        assert report.disposition("tank.c_tank2") == "absent"


class TestDefectClass:
    def test_off_outline_component_is_not_placed(self, tmp_path: Path) -> None:
        """THE defect class (U2 test scenario 2 / the plan's motivating
        incident): tank.c_tank3 IS present in the file but staged at
        (20.0, 272.75) -- y > 254, outside the outline. A plain refdes /
        value lookup would PASS it; the extractor must classify it
        off-outline, i.e. not on the board."""
        board = _write_board(
            tmp_path / "board.kicad_pcb",
            [
                ("tank.c_tank1", "C25", TANK_CAP_FOOTPRINT, (73.42, 52.00)),
                ("tank.c_tank2", "C26", TANK_CAP_FOOTPRINT, (59.38, 28.75)),
                ("tank.c_tank3", "C27", TANK_CAP_FOOTPRINT, (20.0, 272.75)),
            ],
        )
        report = extract_board(board, footprint_values=FOOTPRINT_VALUES)
        assert report.disposition("tank.c_tank1") == "placed"
        assert report.disposition("tank.c_tank2") == "placed"
        assert report.disposition("tank.c_tank3") == "off_outline"

    def test_absent_component_is_reported_absent_not_zero(self, tmp_path: Path) -> None:
        """A registered component missing from the board file entirely is
        'absent' -- never a zero-value, never a pass."""
        board = _write_board(
            tmp_path / "board.kicad_pcb",
            [("tank.c_tank1", "C25", TANK_CAP_FOOTPRINT, (73.42, 52.00))],
        )
        report = extract_board(board, footprint_values=FOOTPRINT_VALUES)
        assert report.disposition("tank.c_tank2") == "absent"
        state, value = report.value_state("tank.c_tank2")
        assert state == "value_unknown"
        assert value is None

    def test_value_unknown_when_no_decode_possible(self, tmp_path: Path) -> None:
        """Placed, Value='?', and the footprint not in the decode table ->
        value_unknown (the oracle reports UNMEASURED, never a silent
        pass)."""
        board = _write_board(
            tmp_path / "board.kicad_pcb",
            [("tank.c_tank1", "C25", "Some:Other_Footprint", (73.42, 52.00))],
        )
        report = extract_board(board, footprint_values=FOOTPRINT_VALUES)
        state, value = report.value_state("tank.c_tank1")
        assert state == "value_unknown"
        assert value is None


class TestErrorPaths:
    def test_unparseable_board_raises(self, tmp_path: Path) -> None:
        """U2 test scenario 3: a board that cannot be parsed fails the
        extractor with the parse error -- never an empty success."""
        board = tmp_path / "board.kicad_pcb"
        board.write_text("(kicad_pcb (version 20211014) (unclosed", encoding="utf-8")
        with pytest.raises(BoardParseError, match="unbalanced"):
            extract_board(board)

    def test_non_board_sexpr_raises(self, tmp_path: Path) -> None:
        board = tmp_path / "board.kicad_pcb"
        board.write_text("(kicad_sch (version 20211123))", encoding="utf-8")
        with pytest.raises(BoardParseError, match="not a kicad_pcb"):
            extract_board(board)

    def test_missing_board_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(BoardParseError, match="cannot read"):
            extract_board(tmp_path / "does_not_exist.kicad_pcb")

    def test_missing_edge_cuts_raises(self, tmp_path: Path) -> None:
        """No Edge.Cuts -> outline unknown -> component presence cannot be
        determined -> fail closed, never a pass."""
        board = _write_board(
            tmp_path / "board.kicad_pcb",
            [("tank.c_tank1", "C25", TANK_CAP_FOOTPRINT, (73.42, 52.00))],
            edge_cuts=False,
        )
        with pytest.raises(BoardParseError, match="Edge.Cuts"):
            extract_board(board)


class TestOutlineRobustness:
    def test_point_in_polygon_handles_edge_membership(self, tmp_path: Path) -> None:
        """A component exactly ON the outline edge counts as inside -- the
        outline's corners and edges belong to the board."""
        board = _write_board(
            tmp_path / "board.kicad_pcb",
            [("on_edge", "X1", TANK_CAP_FOOTPRINT, (20.0, 100.0))],
        )
        report = extract_board(board, footprint_values=FOOTPRINT_VALUES)
        assert report.disposition("on_edge") == "placed"

    def test_gr_line_outline_is_supported(self, tmp_path: Path) -> None:
        """An outline defined by gr_line segments (not one gr_poly) still
        yields a membership test -- bounding-box fallback."""
        lines = "\n".join(
            [
                '    (gr_line (start 20 20) (end 172 20) (layer "Edge.Cuts") (width 0.1))',
                '    (gr_line (start 172 20) (end 172 254) (layer "Edge.Cuts") (width 0.1))',
                '    (gr_line (start 172 254) (end 20 254) (layer "Edge.Cuts") (width 0.1))',
                '    (gr_line (start 20 254) (end 20 20) (layer "Edge.Cuts") (width 0.1))',
            ]
        )
        body = (
            '(kicad_pcb (version 20211014) (generator test)\n'
            '  (layers (44 "Edge.Cuts" user))\n'
            f"{lines}\n"
            '  (footprint "X" (version 20231120) (layer "F.Cu")\n'
            "    (at 20 272.75 0)\n"
            '    (property "Reference" "C27")\n'
            '    (property "Value" "?")\n'
            '    (property "Sheetpath" "tank.c_tank3")\n'
            "  )\n"
            ")"
        )
        board = tmp_path / "board.kicad_pcb"
        board.write_text(body, encoding="utf-8")
        report = extract_board(board, footprint_values=FOOTPRINT_VALUES)
        # Off-outline in both representations.
        assert report.disposition("tank.c_tank3") == "off_outline"
