#!/usr/bin/env python3
"""PS2 field study on the B3 hot-copper body model (s42, c18_h10 @ 61 C, pitch 0.5 mm only).

    python3 ps2_field.py SNAP OUT_DIR [--zero-ps2]

SNAP = a `git archive cb65ce911` extraction of zapote/power-stage-120v/{native-21,validation-results/04-...}
with the s42 task-04 A4 fields (round5-native21/outputs) copied in. Mirrors run_basis.one() exactly (same inputs(),
lead ties, hot copper at the bay) but at 0.5 mm only, and returns the rise field so per-pad / per-layer temperatures
around PS2 can be read. --zero-ps2 sets PS2's heat row to 0 W (everything else identical): the difference is PS2's
own contribution to its pads.
"""
import json
import sys
from pathlib import Path

import numpy as np

snap, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
zero = "--zero-ps2" in sys.argv
R5 = snap / "zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21"
sys.path.insert(0, str(R5 / "b3-ratings"))
sys.dont_write_bytecode = True
import run_basis as rb  # noqa: E402

br, tb, rs, gate = rb.br, rb.tb, rb.rs, rb.gate
CASE, BAY, PITCH = "c18_h10", 61.0, 0.5
ceil, h = gate.case_ceiling_h(CASE)
out_dir.mkdir(parents=True, exist_ok=True)
op = CASE.split("_")[0]
case_str, heat_path, mode = rb.inputs(op, ceil, out_dir)
heat = json.loads(Path(heat_path).read_text())
ps2_row = [p for p in heat["parts"] if p["ref"] == "PS2"][0]
if zero:
    ps2_row["watts_nominal"] = ps2_row["watts_worst"] = 0.0
    Path(heat_path).write_text(json.dumps(heat))
c = (case_str, heat_path, mode)
br.op_inputs = lambda _op, _c=c: _c
brd = tb.Board(rs.GEOM, out_dir / "cache")
leads = {"pad": "2", "g": rb.LEAD_G, "t_rise": {r: t - BAY for r, t in rb.fet_case.t_case(ceil, i_line=rb.I_LINE_A).items()}}
res, rise = br.run_case(brd, op, h, PITCH, "fraction", "network", {}, None, None, True, True, label=CASE,
                        leads=leads, region=None, copper_tcr={"alpha": tb.ALPHA_CU, "air_c": BAY},
                        probes=True, return_rise=True)
shift = BAY - 50.0
T0 = tb.TAMB_C
nx, ny = rise.shape[1], rise.shape[2]
x = brd.xmin + (np.arange(nx) + 0.5) * PITCH
y = brd.ymin + (np.arange(ny) + 0.5) * PITCH
names = tb.T.LAYER_NAMES
cu = tb.T.CU_INDEX
pads = brd.pads_of("PS2")
per_pad = {}
for n, lst in pads.items():
    for layer, poly in lst:
        ii, jj, a = tb.pad_overlap(poly, brd.xmin, brd.ymin, PITCH, 0, 0, nx, ny)
        z = cu[layer]
        v = rise[z][ii, jj]
        per_pad.setdefault(n, {})[layer] = {"mean_c": float((v * a).sum() / a.sum()) + T0 + shift,
                                            "max_c": float(v.max()) + T0 + shift}
# board under the body (fab outline 160.3-212.7 x 0.4-27.6) and a 10 mm ring outside it, per layer
X, Y = np.meshgrid(x, y, indexing="ij")
body = (X >= 160.3) & (X <= 212.7) & (Y >= 0.4) & (Y <= 27.6)
ring = (X >= 150.3) & (X <= 222.7) & (Y >= 0.0) & (Y <= 37.6) & ~body
board_mask = np.isfinite(rise[0])
under = {}
for nm, z in cu.items():
    r = rise[z]
    under[nm] = {"body_mean_c": float(r[body].mean()) + T0 + shift, "body_max_c": float(r[body].max()) + T0 + shift,
                 "body_min_c": float(r[body].min()) + T0 + shift, "ring_mean_c": float(r[ring].mean()) + T0 + shift}
ps2_part = next((p for p in res["parts"] if p["ref"] == "PS2"), {"watts_into_model": 0.0, "note": "0 W row: omitted by body_runs (no network)"})
summary = {"case": CASE, "bay_c": BAY, "pitch_mm": PITCH, "zero_ps2": zero, "board_sha256": brd.data["board_sha256"],
           "ps2_watts_into_model": ps2_part["watts_into_model"],
           "ps2_part_row_c": {k: (v + shift if k.endswith("_c") and isinstance(v, float) else v) for k, v in ps2_part.items()},
           "ps2_probe_c": {k: (v + shift if k.endswith("_c") else v) for k, v in res["probes"]["PS2"].items()},
           "per_pad_c": per_pad, "board_under_body": under, "copper_temp_model": res.get("copper_temp_model"),
           "layers": list(names)}
tag = "zero" if zero else "base"
(out_dir / f"ps2-field-{tag}.json").write_text(json.dumps(summary, indent=1) + "\n")
np.savez_compressed(out_dir / f"ps2-rise-{tag}.npz", rise=rise.astype(np.float32), x=x, y=y)
print(json.dumps({k: summary[k] for k in ("ps2_probe_c", "per_pad_c", "board_under_body")}, indent=1))
