#!/usr/bin/env python3
"""Mesh study of the FET-row result with the stray-heat fix (model/b3/thermal_snap.py).

For base (c0_refill) and the recommended candidate: FET-row max (x 0-80, y 0-12.5, all layers), its location,
the board peak, at pitch 1.0 / 0.5 / 0.25 mm; plus the base at the nominal operating point and at the
26 A ceiling (27.3 A), the gate's references at the same mesh.

    python3 mesh_study.py <candidate>   -> out/mesh_study.json
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "model/b3"))
import run_study as rs  # noqa: E402

CAND = sys.argv[1]
rs.OPS["c26"] = {"I_t": 27.3, "I_line": 11.1, "parts": "nominal", "heat": "c28"}
HEAT = {"c28": "native21-board-heat-sources-c28.json", "c26": "native21-board-heat-sources-c28.json",
        "nominal": "native21-board-heat-sources.json"}
JOBS = [(c, op, p, h) for c in ("c0_refill", CAND) for op, p, h in
        [("c28", 1.0, 25), ("c28", 0.5, 25), ("c28", 0.25, 25), ("c28", 1.0, 10), ("c28", 0.5, 10)]] + \
       [("c0_refill", op, p, 25) for op in ("nominal", "c26") for p in (1.0, 0.5, 0.25)] + \
       [("c0_refill", op, p, 10) for op in ("nominal", "c26") for p in (1.0, 0.5)]
outp = HERE / "out/mesh_study.json"
res = json.loads(outp.read_text()) if outp.exists() else {}
for c, op, p, h in JOBS:
    key = f"{c}|{op}|p{p}|h{h}"
    if key in res:
        continue
    k = HERE / "kicad" / c
    env = {**os.environ, "A4_DIR": str(HERE / "a4" / c), "A4_COPPER": str(k / "power_copper.json.gz")}
    o = HERE / "runs" / c / f"mesh_{op}_h{h}_p{str(p).replace('.', 'p')}.json"
    subprocess.run([sys.executable, str(HERE / "model/b3/thermal_snap.py"), "--geometry", str(k / "all-copper.json.gz"),
                    "--case", rs.cases(op), "--pitch-mm", str(p), "--h", str(h), "--a6-heat", str(HERE / "model/b3/inputs" / HEAT[op]),
                    "--a6-mode", rs.OPS[op]["parts"], "--output", str(o)], check=True, stdout=subprocess.DEVNULL, env=env)
    r = json.loads(o.read_text())
    z = np.load(o.with_suffix(".npz"))
    x, y, t = z["x_mm"], z["y_mm"], 50 + z["rise_k"]
    ix, iy = x <= 80, y <= 12.5
    sub = t[:, ix][:, :, iy]
    zz, i, j = np.unravel_index(np.argmax(sub), sub.shape)
    lanes = t[:, x <= 110][:, :, (y > 12.5) & (y <= 35)].max()
    res[key] = {"board_peak": {k_: r["peak"][k_] for k_ in ("temperature_c", "x_mm", "y_mm", "layer")},
                "fet_row_max_c": round(float(sub.max()), 2), "fet_row_at": [float(x[ix][i]), float(y[iy][j]), ["F.Cu", "d1", "In1.Cu", "d2", "In2.Cu", "d3", "B.Cu"][zz]],
                "lanes_max_c": round(float(lanes), 2),
                "hottest_parts": [(q["ref"], round(q["conditional_pad_cell_max_c"], 1)) for q in sorted(r["a6_parts_applied"], key=lambda q: -q["conditional_pad_cell_max_c"])[:3]],
                "snapped": r["a4_heat_snapped_to_copper"]}
    print(key, res[key]["fet_row_max_c"], res[key]["fet_row_at"], "lanes", res[key]["lanes_max_c"], "peak",
          round(r["peak"]["temperature_c"], 1), r["peak"]["x_mm"], r["peak"]["y_mm"], res[key]["hottest_parts"], flush=True)
    o.with_suffix(".npz").unlink(); o.with_suffix(".png").unlink()
    outp.write_text(json.dumps(res, indent=1) + "\n")
