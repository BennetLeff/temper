#!/usr/bin/env python3
"""Stage 15b, deliverable 1: where the 28 A FET-row hot spot comes from.

B3's solve is linear in the heat (fixed k, fixed h), so the c28 field is exactly the sum of the
fields of each A4 case (at its c28 scale) and of the A6 part heat alone. This runs thermal.py
(stage15b copy, unchanged physics) once per source and reports:
  - the FET-row profile (x 0-80, y 0-12.5): max-over-layers temperature per 1 mm column;
  - each source's share of the rise at the hot points;
  - each source's heat inside the FET-row box.

    python3 diag_decompose.py [geometry.json.gz] [A4_DIR] [tag]   ->  out/decompose_<tag>.json
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MODEL = HERE / "model"
sys.path.insert(0, str(MODEL / "b3"))
import run_study as rs  # noqa: E402

GEOM = Path(sys.argv[1]) if len(sys.argv) > 1 else MODEL / "native21s15-all-copper.json.gz"
A4 = Path(sys.argv[2]) if len(sys.argv) > 2 else MODEL / "outputs"
TAG = sys.argv[3] if len(sys.argv) > 3 else "base"
HEAT = MODEL / "b3/inputs/native21-board-heat-sources-c28.json"
RUNS = HERE / "runs" / TAG
RUNS.mkdir(parents=True, exist_ok=True)
STRIP = (0.0, 0.0, 80.0, 12.5)
POINTS = {"hot_h25 (76.5, 9.5)": (76.5, 9.5), "hot_h10 (50.5, 4.5)": (50.5, 4.5),
          "Q3.2 sw_a (50.05, 4.2)": (50.05, 4.215), "Q2.3 sw_a (73.5, 4.2)": (73.5, 4.215),
          "link neck Q3.3 (55.5, 9.5)": (55.5, 9.5), "link neck Q2.2 (68.0, 9.5)": (68.05, 9.5),
          "Q5.3 sw_b (15.4, 4.2)": (15.4, 4.215), "Q6.2 sw_b (27.95, 4.2)": (27.95, 4.215)}
env = {**os.environ, "A4_DIR": str(A4), "A4_COPPER": os.environ.get("A4_COPPER", str(MODEL / "inputs/power_copper.json.gz"))}


def run(case, h, a6, name):
    out = RUNS / f"{name}_h{h}.json"
    cmd = [sys.executable, str(MODEL / "b3/thermal.py"), "--geometry", str(GEOM), "--case", case,
           "--pitch-mm", "1.0", "--h", str(h), "--output", str(out)]
    if a6:
        cmd += ["--a6-heat", str(HEAT), "--a6-mode", "nominal"]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, env=env)
    z = np.load(out.with_suffix(".npz"))
    return json.loads(out.read_text()), z["x_mm"], z["y_mm"], z["rise_k"], z["heat_w"]


def main():
    sources = [(c.rsplit(":", 1)[0], c) for c in rs.cases("c28").split(",")] + [("parts (A6 c28)", "none")]
    result = {"geometry": str(GEOM), "a4_dir": str(A4), "op": rs.OPS["c28"], "h": {}}
    for h in (25, 10):
        fields, heats = {}, {}
        full, x, y, rise_full, _ = run(rs.cases("c28"), h, True, "full")
        for label, case in sources:
            _, x, y, rise, heat = run(case, h, case == "none", label.split(" ")[0].replace("-", "_"))
            fields[label], heats[label] = rise, heat
        total = sum(fields.values())
        err = float(np.abs(total - rise_full).max())
        ix = (x >= STRIP[0]) & (x <= STRIP[2])
        iy = (y >= STRIP[1]) & (y <= STRIP[3])
        tmax = 50 + rise_full.max(axis=0)
        prof = [{"x_mm": float(x[i]), "max_c": round(float(tmax[i, iy].max()), 2),
                 "y_at_max": float(y[iy][np.argmax(tmax[i, iy])]),
                 "layer": rs_layer(rise_full[:, i, iy])} for i in np.flatnonzero(ix)]
        pts = {}
        for name, (px, py) in POINTS.items():
            i, j = int(np.argmin(abs(x - px))), int(np.argmin(abs(y - py)))
            z = int(np.argmax(rise_full[:, i, j]))
            contrib = {k: round(float(v[z, i, j]), 2) for k, v in fields.items()}
            pts[name] = {"cell": [float(x[i]), float(y[j])], "layer_index": z,
                         "temperature_c": round(50 + float(rise_full[z, i, j]), 2),
                         "rise_by_source_k": dict(sorted(contrib.items(), key=lambda kv: -kv[1]))}
        strip_heat = {k: round(float(v[:, ix][:, :, iy].sum()), 4) for k, v in heats.items()}
        result["h"][h] = {"peak": full["peak"], "superposition_max_error_k": err,
                          "fet_row_profile": prof, "points": pts,
                          "strip_heat_w": dict(sorted(strip_heat.items(), key=lambda kv: -kv[1])),
                          "strip_heat_total_w": round(sum(strip_heat.values()), 3)}
        print(f"h{h}: peak {full['peak']}, superposition err {err:.2e} K")
        for name, p in pts.items():
            top = list(p["rise_by_source_k"].items())[:5]
            print(f"  {name}: {p['temperature_c']} C  {top}")
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out" / f"decompose_{TAG}.json").write_text(json.dumps(result, indent=1) + "\n")


def rs_layer(col):
    return ["F.Cu", "d1", "In1.Cu", "d2", "In2.Cu", "d3", "B.Cu"][int(np.unravel_index(np.argmax(col), col.shape)[0])]


if __name__ == "__main__":
    main()
