#!/usr/bin/env python3
"""Write the heatsink solve JSON back to a scratch .kicad_pcb.

Passes board_origin=board.origin (NOT the default (0,0)) -- omitting it writes
every footprint ~20mm off the outline and silently invalidated a prior PR.
Also propagates .kicad_pro/.kicad_dru so a DRC run on the placed board resolves
the project's custom rules instead of silently dropping them.
"""
import json
import sys
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_writer import write_placements_to_pcb
from temper_placer.io._write_types import PlacementUpdate
from temper_placer.validation._drc_api import copy_kicad_project_sidecar

solve_json = Path(sys.argv[1])
template = Path(sys.argv[2])
out = Path(sys.argv[3])

d = json.loads(solve_json.read_text())
assert d["status"] == "optimal", f"solve status={d['status']}"

parsed = parse_kicad_pcb(template)
netlist, board = parsed.netlist, parsed.board
print(f"board.origin = {board.origin}  (solve json recorded {d['board_origin']})")
assert tuple(board.origin) == tuple(d["board_origin"]), "origin mismatch"

placements = {
    ref: PlacementUpdate(ref=ref, x=p[0], y=p[1], rotation=d["rotations"][ref] * 90.0)
    for ref, p in d["positions"].items()
}
print(f"{len(placements)} placements")

res = write_placements_to_pcb(
    template,
    out,
    placements,
    components=netlist.components,
    board_origin=board.origin,      # load-bearing
)
print("WriteResult:", res)

copy_kicad_project_sidecar(out, template)
print("propagated project sidecar ->", out.with_suffix(".kicad_pro").name)
