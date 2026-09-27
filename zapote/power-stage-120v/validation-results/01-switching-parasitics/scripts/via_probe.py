#!/usr/bin/env python3
"""Extract native KiCad via drills and pad positions for task 01 evidence."""

import hashlib
import json
import sys
from pathlib import Path

import pcbnew


def main() -> None:
    board_path, output_path = map(Path, sys.argv[1:3])
    board = pcbnew.LoadBoard(str(board_path))
    mm = pcbnew.ToMM
    selected_nets = {"bus_p", "hv_ret", "leg_ret", "sw_a", "sw_b"}
    vias = []
    for item in board.GetTracks():
        if item.Type() != pcbnew.PCB_VIA_T or item.GetNetname() not in selected_nets:
            continue
        via = pcbnew.Cast_to_PCB_VIA(item)
        pos = via.GetPosition()
        vias.append({"net": via.GetNetname(), "centre_mm": [mm(pos.x), mm(pos.y)],
                     "drill_mm": mm(via.GetDrillValue()),
                     "diameter_mm": mm(via.GetWidth(pcbnew.F_Cu))})
    pads = []
    selected_refs = {"C38", "C39", "C40", "C41", "Q2", "Q3", "Q5", "Q6", "R5", "U1", "U2", "R10", "R12", "R18", "R20"}
    for fp in board.GetFootprints():
        if fp.GetReference() not in selected_refs:
            continue
        for pad in fp.Pads():
            pos = pad.GetPosition()
            pads.append({"ref": f"{fp.GetReference()}.{pad.GetNumber()}",
                         "net": pad.GetNetname(), "centre_mm": [mm(pos.x), mm(pos.y)]})
    out = {"board_sha256": hashlib.sha256(board_path.read_bytes()).hexdigest(),
           "vias": sorted(vias, key=lambda x: (x["net"], x["centre_mm"])),
           "pads": sorted(pads, key=lambda x: x["ref"])}
    output_path.write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main()
