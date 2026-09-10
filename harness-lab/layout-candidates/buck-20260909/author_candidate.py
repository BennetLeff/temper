"""Author the isolated buck layout candidate through KiCad's pcbnew API.

The input is the copied buck-dev-a witness.  This script only adds an explicit
ground return shortcut and makes the existing footprint references readable;
it does not alter footprints, pads, nets, terminals, outline, or rules.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pcbnew


BOARD = Path(__file__).with_name("candidate.kicad_pcb")


def mm(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def main() -> None:
    if not BOARD.is_file():
        raise FileNotFoundError(f"candidate board is missing: {BOARD}")
    board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(BOARD), None)
    if board is None:
        raise RuntimeError(f"KiCad could not read candidate board: {BOARD}")
    if pcbnew.GetBuildVersion() != "10.0.4":
        raise RuntimeError("candidate authoring requires KiCad 10.0.4")

    gnd = board.FindNet("gnd")
    if gnd is None:
        raise RuntimeError("candidate board is missing the gnd net")

    # Direct B.Cu shortcut between the input return capacitor and the IC
    # ground pad.  The existing gnd spine remains, preserving one native
    # connected island for every mapped ground pad.
    start, end = mm(16.475, 20.0), mm(20.8625, 19.05)
    if not any(
        t.Type() == pcbnew.PCB_TRACE_T
        and t.GetNetname() == "gnd"
        and {
            (t.GetStart().x, t.GetStart().y),
            (t.GetEnd().x, t.GetEnd().y),
        }
        == {(start.x, start.y), (end.x, end.y)}
        for t in board.GetTracks()
    ):
        segment = pcbnew.PCB_TRACK(board)
        segment.SetStart(start)               # C9.2
        segment.SetEnd(end)                   # U3.1
        segment.SetWidth(pcbnew.FromMM(0.6))
        segment.SetLayer(pcbnew.B_Cu)
        segment.SetNet(gnd)
        board.Add(segment)

    # Reference fields are the native presentation labels consumed by the
    # layout evidence collector.  Keep them on F.SilkS, 1.0 mm high, and use
    # fixed asymmetric positions with no overlap on this 50 x 40 mm witness.
    label_positions = {
        "U3": (22.0, 17.0), "L2": (32.0, 28.0), "C9": (15.0, 17.0),
        "C10": (26.0, 17.0), "C11": (40.0, 11.5), "C12": (40.0, 29.0),
        "C13": (44.0, 20.0), "R16": (25.0, 29.5), "R17": (21.5, 31.0),
        "J1": (3.0, 15.5), "J2": (3.0, 24.0), "J3": (47.0, 15.5),
    }
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    if set(label_positions) != set(footprints):
        raise RuntimeError("unexpected footprint census while authoring labels")
    for reference, fp in footprints.items():
        field = fp.Reference()
        field.SetVisible(True)
        field.SetLayer(pcbnew.F_SilkS)
        field.SetTextSize(mm(1.0, 1.0))
        field.SetTextThickness(pcbnew.FromMM(0.15))
        field.SetPosition(mm(*label_positions[reference]))
        value = fp.Value()
        value.SetVisible(False)

    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(BOARD), board)
    print(f"authored {BOARD}")


if __name__ == "__main__":
    main()
