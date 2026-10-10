#!/usr/bin/env python3
"""Stage 15: B3 peak vs tank-RMS ceiling at h 25 / 1.0 mm pitch (the forced-air case), to place the
thermally supported commissioned ceiling while the FET-row tank copper is unchanged.

    python3 ceiling_sweep.py  ->  outputs/ceiling_sweep.json

Each point uses run_study.py's c28 copper scaling at the firmware RMS trip (1.05 x ceiling) and the c28 heat
file (parts at the 29.4 A case: conservative below 28 A for R5, R39 and the bank, whose heat falls as I^2).
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_study as rs  # noqa: E402

out = []
for ceiling in (22.0, 24.0, 26.0, 28.0):
    it = round(1.05 * ceiling, 2)
    rs.OPS["sweep"] = {"I_t": it, "I_line": 11.1, "parts": "nominal", "heat": "c28"}
    path = HERE / "outputs" / f"sweep_c{int(ceiling)}_h25_p1p0.json"
    subprocess.run([sys.executable, str(HERE / "thermal.py"), "--geometry", str(rs.GEOM), "--case", rs.cases("sweep"),
                    "--pitch-mm", "1.0", "--h", "25", "--a6-heat", str(rs.HEAT_C28), "--a6-mode", "nominal",
                    "--output", str(path)], check=True, stdout=subprocess.DEVNULL)
    r = json.loads(path.read_text())
    out.append({"ceiling_A": ceiling, "I_t_A": it, "peak": r["peak"]})
    print(ceiling, it, round(r["peak"]["temperature_c"], 1), r["peak"]["x_mm"], r["peak"]["y_mm"], r["peak"]["layer"], flush=True)
(HERE / "outputs" / "ceiling_sweep.json").write_text(json.dumps(out, indent=1) + "\n")
