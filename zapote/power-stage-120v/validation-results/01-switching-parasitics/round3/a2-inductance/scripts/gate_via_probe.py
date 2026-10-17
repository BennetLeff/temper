#!/usr/bin/env python3
"""Export actual gate-output via drills and layers with KiCad pcbnew."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pcbnew  # type: ignore[import-not-found]

NETS = {"leg_a-out_h", "leg_a-out_l", "leg_b-out_h", "leg_b-out_l",
        "leg_a-gate_h", "leg_a-gate_l", "leg_b-gate_h", "leg_b-gate_l"}


def main() -> None:
    board_path, output_path = map(Path, sys.argv[1:3])
    board = pcbnew.LoadBoard(str(board_path))
    mm = pcbnew.ToMM
    vias = []
    for track in board.GetTracks():
        if track.Type() != pcbnew.PCB_VIA_T or track.GetNetname() not in NETS:
            continue
        via = pcbnew.Cast_to_PCB_VIA(track)
        pos = via.GetPosition()
        vias.append({"net": via.GetNetname(), "centre_mm": [mm(pos.x), mm(pos.y)],
                     "drill_mm": mm(via.GetDrillValue()),
                     "diameter_mm": mm(via.GetWidth(pcbnew.F_Cu)),
                     "through": via.GetViaType() == pcbnew.VIATYPE_THROUGH})
    output = {"board_sha256": hashlib.sha256(board_path.read_bytes()).hexdigest(),
              "vias": sorted(vias, key=lambda v: (v["net"], v["centre_mm"]))}
    output_path.write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
