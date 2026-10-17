#!/usr/bin/env python3
"""B3 c28 (29.4 A tank RMS = 1.05 x 28 A, 11.1 A line, c28 part heat) on a candidate's copper, h 25 and h 10.

    python3 b3_eval.py <name> <all-copper.json.gz> <A4_DIR> <power_copper.json.gz> [pitches "1.0 0.5"]
    -> out/b3_<name>.json: board peak, FET-row max (x 0-80, y 0-12.5) and the hottest FET-row cells, per h / pitch.
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

name, geom, a4, copper = sys.argv[1:5]
pitches = (sys.argv[5] if len(sys.argv) > 5 else "1.0").split()
env = {**os.environ, "A4_DIR": a4, "A4_COPPER": copper}
runs = HERE / "runs" / name
runs.mkdir(parents=True, exist_ok=True)
res = {"name": name, "geometry": geom, "a4": json.loads((Path(a4) / "a4_summary.json").read_text()), "runs": {}}
for p in pitches:
    for h in (25, 10):
        out = runs / f"c28_h{h}_p{p.replace('.', 'p')}.json"
        subprocess.run([sys.executable, str(HERE / "model/b3/thermal.py"), "--geometry", geom, "--case", rs.cases("c28"),
                        "--pitch-mm", p, "--h", str(h), "--a6-heat", str(HERE / "model/b3/inputs/native21-board-heat-sources-c28.json"),
                        "--a6-mode", "nominal", "--output", str(out)], check=True, stdout=subprocess.DEVNULL, env=env)
        r = json.loads(out.read_text())
        z = np.load(out.with_suffix(".npz"))
        x, y, rise = z["x_mm"], z["y_mm"], z["rise_k"]
        ix, iy = x <= 80, y <= 12.5
        sub = rise[:, ix][:, :, iy]
        k = np.unravel_index(np.argsort(sub.max(axis=0), axis=None)[::-1][:5], sub.shape[1:])
        cells = [{"x": float(x[ix][i]), "y": float(y[iy][j]), "c": round(50 + float(sub[:, i, j].max()), 2)} for i, j in zip(*k)]
        parts = sorted(r["a6_parts_applied"], key=lambda q: -q["conditional_pad_cell_max_c"])[:3]
        res["runs"][f"h{h}_p{p}"] = {"peak": r["peak"], "fet_row_max_c": cells[0]["c"], "fet_row_hottest": cells,
                                    "hottest_parts": [(q["ref"], round(q["conditional_pad_cell_max_c"], 1)) for q in parts],
                                    "balance_w": r["balance"]["balance_w"]}
        os.remove(out.with_suffix(".npz")) if p == "0.5" else None
        print(f"{name} h{h} p{p}: peak {r['peak']['temperature_c']:.1f} at ({r['peak']['x_mm']}, {r['peak']['y_mm']}) {r['peak']['layer']};"
              f" FET row max {cells[0]['c']:.1f} at ({cells[0]['x']}, {cells[0]['y']})", flush=True)
(HERE / "out").mkdir(exist_ok=True)
(HERE / "out" / f"b3_{name}.json").write_text(json.dumps(res, indent=1) + "\n")
