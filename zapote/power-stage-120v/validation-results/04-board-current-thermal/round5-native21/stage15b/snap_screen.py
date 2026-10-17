#!/usr/bin/env python3
"""c28, p1.0, h25 / h10 with the stray-heat fix (thermal_snap.py) for each candidate: FET-row and lane maxima.

    python3 snap_screen.py <cand> ...   -> out/snap_screen.json (merged)
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

outp = HERE / "out/snap_screen.json"
res = json.loads(outp.read_text()) if outp.exists() else {}
for c in sys.argv[1:]:
    k = HERE / "kicad" / c
    env = {**os.environ, "A4_DIR": str(HERE / "a4" / c), "A4_COPPER": str(k / "power_copper.json.gz")}
    for h in (25, 10):
        o = HERE / "runs" / c / f"snap_c28_h{h}_p1p0.json"
        subprocess.run([sys.executable, str(HERE / "model/b3/thermal_snap.py"), "--geometry", str(k / "all-copper.json.gz"),
                        "--case", rs.cases("c28"), "--pitch-mm", "1.0", "--h", str(h), "--a6-heat",
                        str(HERE / "model/b3/inputs/native21-board-heat-sources-c28.json"), "--a6-mode", "nominal",
                        "--output", str(o)], check=True, stdout=subprocess.DEVNULL, env=env)
        r = json.loads(o.read_text())
        z = np.load(o.with_suffix(".npz"))
        x, y, t = z["x_mm"], z["y_mm"], 50 + z["rise_k"]
        sub = t[:, x <= 80][:, :, y <= 12.5]
        zz, i, j = np.unravel_index(np.argmax(sub), sub.shape)
        res[f"{c}|h{h}"] = {"fet_row_max_c": round(float(sub.max()), 2),
                            "at": [float(x[x <= 80][i]), float(y[y <= 12.5][j]), int(zz)],
                            "lanes_max_c": round(float(t[:, x <= 110][:, :, (y > 12.5) & (y <= 35)].max()), 2),
                            "board_peak": round(r["peak"]["temperature_c"], 2), "peak_at": [r["peak"]["x_mm"], r["peak"]["y_mm"], r["peak"]["layer"]]}
        print(c, h, res[f"{c}|h{h}"], flush=True)
outp.write_text(json.dumps(res, indent=1) + "\n")
