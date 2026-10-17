#!/usr/bin/env python3
"""Whole decision + startup case set (both legs, 27/100/150 C) with dL in series with the gate ports.
Reuses gate_sens.one. Usage: python3 -I gate_full.py --dl 10,20 --workers 6 -> ../results/gate_full.json"""
import sys, json, argparse
sys.dont_write_bytecode = True
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_sens as g
ap = argparse.ArgumentParser(); ap.add_argument("--dl", default="10,20"); ap.add_argument("--workers", type=int, default=6); ap.add_argument("--variant", default="port")
a = ap.parse_args(); g.VARIANT = a.variant; dls = [float(x) for x in a.dl.split(",")]
jobs = []
for leg in "AB":
    for suffix in ("", "-startup"):
        p = g.D2/f"results/f6-vneg-m1p6-leg{leg}21-s9b2{suffix}/results.json"
        for r in json.load(open(p)):
            if r.get("status") == "complete":
                for dl in dls: jobs.append((leg, r, dl))
print(len(jobs), "jobs", flush=True)
with ThreadPoolExecutor(a.workers) as ex: rows = list(ex.map(g.one, jobs))
for row, (leg, r, dl) in zip(rows, jobs):
    if row["status"] == "complete":
        lim = 585 if row["case"]["case"] == "S2" else 520
        row["pass_vds"] = row["vds_pk"] <= lim; row["pass_vgs"] = row["vgs_abs"] <= 30; row["pass_1p9"] = row["off_V"] < 1.9
        row["zvs"] = row["incoming_V"] <= 0.05 * row["case"]["vbus"]
        row["base_zvs"] = r.get("zvs")
json.dump(rows, open(g.OUT/("results/gate_full.json" if a.variant == "port" else "results/gate_full_drv.json"), "w"))
print("done", sum(r["status"] != "complete" for r in rows), "indeterminate")
