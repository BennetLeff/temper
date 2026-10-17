"""Pin the reviewed REDCUBE drawing through native serialization."""

from pathlib import Path

import pytest
from kiutils.board import Board
from kiutils.footprint import Footprint

UNIT = Path(__file__).resolve().parents[1]
PATTERN = (
    UNIT / "libraries/TerminalBlock_Wuerth.pretty"
    / "Wuerth_REDCUBE-THR_WP-THRBU_74650074_THR.kicad_mod"
)
TERMINALS = {"J2", "J5", "J7", "J8", "J9", "J10"}
LANDINGS = {(-2.935, -2.935), (-2.935, 2.935), (2.935, -2.935), (2.935, 2.935)}


def assert_reviewed_landings(footprint):
    legs = [pad for pad in footprint.pads if pad.number == "1" and pad.type == "thru_hole"]
    assert len(legs) == 4
    assert {(pad.position.X, pad.position.Y) for pad in legs} == LANDINGS
    assert all((pad.size.X, pad.size.Y, pad.drill.diameter) == (3.2, 3.2, 1.85) for pad in legs)
    paste = [pad for pad in footprint.pads if pad.layers == ["F.Paste"]]
    assert len(paste) == 4
    assert {(pad.position.X, pad.position.Y) for pad in paste} == LANDINGS


def test_reviewed_terminal_geometry_survives_in_every_native_instance():
    assert_reviewed_landings(Footprint.from_file(str(PATTERN)))
    board = Board.from_file(str(UNIT / "native-02/section.kicad_pcb"))
    checked = set()
    for footprint in board.footprints:
        reference = footprint.properties["Reference"]
        if reference in TERMINALS:
            assert_reviewed_landings(footprint)
            checked.add(reference)
    assert checked == TERMINALS


def test_deleted_same_number_leg_is_rejected():
    footprint = Footprint.from_file(str(PATTERN))
    victim = next(pad for pad in footprint.pads if pad.number == "1")
    footprint.pads.remove(victim)
    with pytest.raises(AssertionError):
        assert_reviewed_landings(footprint)
