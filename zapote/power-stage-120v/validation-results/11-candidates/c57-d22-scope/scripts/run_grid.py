#!/usr/bin/env python3
"""Run emi_grid.py over the grid, 3 at a time, and collect results/emi-grid.json.   python3 -I run_grid.py RUNDIR"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = Path(sys.argv[1])
G = ["proto:88:1", "proto:88:0.3", "proto:88:0.5", "proto:88:2", "proto:100:0.3", "proto:100:1", "proto:100:2", "proto:110:0.3",
     "proto:49.7:1", "proto:49.7:2", "proto:77:2", "prod:41:0.3", "prod:41:1", "prod:49.7:0.3", "prod:49.7:1", "prod:88:0.3"]


def one(v):
    d = RUN / v.replace(":", "_")
    if not (d / "results.json").exists():
        p = subprocess.run([sys.executable, str(HERE / "emi_grid.py"), v, str(d)], capture_output=True, text=True)
        (RUN / (d.name + ".log")).write_text(p.stdout + p.stderr)
        if p.returncode:
            raise SystemExit(f"{v} failed: see {d.name}.log")
    s = json.loads((d / "results.json").read_text())["verdict"]
    return v, {k: s[k] for k in ("nominal_min_margin_dB", "sensitivity_min_margin_all_dB", "verdict", "controls_ok")}


res = dict(ThreadPoolExecutor(3).map(one, G))
c = res["proto:88:1"]["sensitivity_min_margin_all_dB"]
assert abs(c - 6.118415399102389) < 1e-9, "control: c53 s3 88 uH row not reproduced"
assert all(r["controls_ok"] for r in res.values())
(HERE.parent / "results/emi-grid.json").write_text(json.dumps(res, indent=1) + "\n")
for v, r in res.items():
    print(f"{v:16s} {r['nominal_min_margin_dB']:6.2f} {r['sensitivity_min_margin_all_dB']:6.2f} {r['verdict']}")
