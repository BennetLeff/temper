#!/usr/bin/env python3
"""Re-stamp the Value / MPN fields of pcb/controller.kicad_pcb from frozen/ without touching copper.

Used when only sourcing (MPN) changes after the board is placed and routed (DECISIONS C35/C36): the
full layout/make.py would re-run the router, which is the slow step and not needed for a field change.
Placement, tracks, vias and zones are not read or written beyond the two text fields.

    KiCad python:  layout/refresh_parts.py            # then layout/build_schematic.py, DRC, fab.py
"""
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_board  # noqa: E402

BOARD = HERE.parent / "pcb/controller.kicad_pcb"


def main():
    comps, _nets = build_board.parse_netlist()
    b = pcbnew.LoadBoard(str(BOARD))
    changed = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        mpn = comps[ref]["mpn"]
        if fp.GetValue() != mpn or fp.GetFieldText("MPN") != mpn:
            changed.append((ref, fp.GetValue(), mpn))
            fp.SetValue(mpn)
            fp.SetField("MPN", mpn)
            fp.GetField("MPN").SetVisible(False)
    pcbnew.SaveBoard(str(BOARD), b)
    for c in changed:
        print("refreshed %s: %s -> %s" % c)
    print(len(changed), "footprints refreshed")


if __name__ == "__main__":
    main()
