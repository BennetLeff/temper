#!/usr/bin/env python3
"""Gate check per candidate: max temperature by region at c28, p1.0, against the baseline field.

"New hot spot" = any copper-board cell above the gate (133.9 C at h 25, the 26 A ceiling-sweep peak) whose
baseline (c0_refill) c28 value was below the gate, or any cell that got hotter than baseline by > 0.5 K and is
above the gate. Also runs the 26 A reference (27.3 A = 1.05 x 26) on the base copper at h 10 / h 25.

    python3 region_check.py c0_refill c1_f_corner ...   -> out/region_check.json
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

GATE = {25: 133.9, 10: None}
REG = {"fet_row x0-80 y0-12.5": (0, 0, 80, 12.5), "lanes x0-110 y12.5-35": (0, 12.5, 110, 35),
       "board": (0, 0, 400, 400)}


def field(path):
    z = np.load(path)
    return z["x_mm"], z["y_mm"], 50 + z["rise_k"].max(axis=0), z["board_mask"]


ref = HERE / "runs/ref26"
ref.mkdir(parents=True, exist_ok=True)
rs.OPS["c26"] = {"I_t": 27.3, "I_line": 11.1, "parts": "nominal", "heat": "c28"}
env = {**os.environ, "A4_DIR": str(HERE / "a4/c0_refill"), "A4_COPPER": str(HERE / "kicad/c0_refill/power_copper.json.gz")}
out = {"gate_h25_c": GATE[25], "ref26": {}, "cand": {}}
for h in (25, 10):
    o = ref / f"c26_h{h}.json"
    if not o.exists():
        subprocess.run([sys.executable, str(HERE / "model/b3/thermal.py"), "--geometry", str(HERE / "kicad/c0_refill/all-copper.json.gz"),
                        "--case", rs.cases("c26"), "--pitch-mm", "1.0", "--h", str(h), "--a6-heat",
                        str(HERE / "model/b3/inputs/native21-board-heat-sources-c28.json"), "--a6-mode", "nominal", "--output", str(o)],
                       check=True, stdout=subprocess.DEVNULL, env=env)
    x, y, t, b = field(o.with_suffix(".npz"))
    out["ref26"][h] = {k: round(float(t[np.ix_((x >= r[0]) & (x <= r[2]), (y >= r[1]) & (y <= r[3]))].max()), 2) for k, r in REG.items()}
for h in (25, 10):
    x, y, t0, b = field(HERE / f"runs/c0_refill/c28_h{h}_p1p0.npz")
    for n in sys.argv[1:]:
        x, y, t, b = field(HERE / f"runs/{n}/c28_h{h}_p1p0.npz")
        row = {k: round(float(t[np.ix_((x >= r[0]) & (x <= r[2]), (y >= r[1]) & (y <= r[3]))].max()), 2) for k, r in REG.items()}
        g = GATE[25] if h == 25 else out["ref26"][10]["board"]
        worse = (t > g) & b & (t > t0 + 0.5)
        ii, jj = np.nonzero(worse)
        row["cells_above_gate_and_hotter_than_base"] = [(float(x[i]), float(y[j]), round(float(t[i, j]), 1), round(float(t0[i, j]), 1)) for i, j in zip(ii, jj)][:12]
        row["gate_used_c"] = g
        out["cand"].setdefault(n, {})[h] = row
        print(h, n, row["fet_row x0-80 y0-12.5"], row["lanes x0-110 y12.5-35"], row["board"], "new>gate:", len(ii), row["cells_above_gate_and_hotter_than_base"][:4])
print("26 A reference:", out["ref26"])
(HERE / "out/region_check.json").write_text(json.dumps(out, indent=1) + "\n")
