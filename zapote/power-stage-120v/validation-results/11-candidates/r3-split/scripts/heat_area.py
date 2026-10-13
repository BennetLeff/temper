#!/usr/bin/env python3 -I
"""Board heat (B3, 28 A basis, board_fraction x watts_worst) that leaves / stays on each resulting board, and the heat density
on the drive board. Reads results/partition.json and the repo's B3 heat-source JSON. -> ../results/heat_area.json"""
import json, sys
sys.dont_write_bytecode = True
from pathlib import Path
HERE = Path(__file__).resolve().parent; OUT = HERE.parent; PS = HERE.parents[3]
H = json.load(open(PS/"validation-results/04-board-current-thermal/round5-native21/b3/inputs/native21-board-heat-sources-c28.json"))
W = {p["ref"]: p["watts_worst"]*p["board_fraction"] for p in H["parts"]}
P = json.load(open(OUT/"results/partition.json")); C = json.load(open(OUT/"results/cost_model.json"))
out = {"total_board_W": round(sum(W.values()), 3)}
for opt, sides in (("S1", "IM"), ("S2A", "PD"), ("S2B", "PD"), ("S2L", "PD")):
    o = {}
    for s in sides:
        refs = P[opt]["refs"][s]; o[s] = dict(W=round(sum(W.get(r, 0) for r in refs), 3),
            top=sorted(((r, round(W[r], 3)) for r in refs if r in W), key=lambda x: -x[1])[:6])
    out[opt] = o
d = C["S2B_dims"]["drive_area_mm2"]; out["S2B_drive_W_per_cm2"] = round(out["S2B"]["D"]["W"]/(d/100), 4)
json.dump(out, open(OUT/"results/heat_area.json", "w"), indent=1); print(json.dumps(out, indent=1))
