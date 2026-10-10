#!/usr/bin/env python3
"""Sensitivity: FET THT barrels' thermal link with the lead's copper core (LEAD_CORE=1 in thermal_snap.py).

    python3 lead_core.py <cand> ...   -> stdout + out/lead_core.json
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

res = {}
for c in sys.argv[1:]:
    k = HERE / "kicad" / c
    env = {**os.environ, "LEAD_CORE": "1", "A4_DIR": str(HERE / "a4" / c), "A4_COPPER": str(k / "power_copper.json.gz")}
    for h in (25, 10):
        o = HERE / "runs" / c / f"core_c28_h{h}.json"
        subprocess.run([sys.executable, str(HERE / "model/b3/thermal_snap.py"), "--geometry", str(k / "all-copper.json.gz"),
                        "--case", rs.cases("c28"), "--pitch-mm", "1.0", "--h", str(h), "--a6-heat",
                        str(HERE / "model/b3/inputs/native21-board-heat-sources-c28.json"), "--a6-mode", "nominal",
                        "--output", str(o)], check=True, stdout=subprocess.DEVNULL, env=env)
        z = np.load(o.with_suffix(".npz"))
        x, y, t = z["x_mm"], z["y_mm"], 50 + z["rise_k"]
        res[f"{c}|h{h}"] = round(float(t[:, x <= 80][:, :, y <= 12.5].max()), 2)
        print(c, h, res[f"{c}|h{h}"])
(HERE / "out/lead_core.json").write_text(json.dumps(res, indent=1) + "\n")
