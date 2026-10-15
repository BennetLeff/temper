#!/usr/bin/env python3
"""Legacy B3 (the committed b3/thermal.py, run in place, read-only) on the s32 board: reproduction control and the
0.25 mm grid point the repo does not have.

    python3 legacy_grid.py            -> ../runs/legacy/<name>.json, ../results/legacy_grid.json

Control L1: the 1.0 mm nominal h10 and c28 h25 runs reproduce b3/outputs/summary.json (the s32 scorecard's
b3_nominal_h10_peak_C 162.1 and b3_c28_h25_peak_C 135.0) to 1e-6 K, else exit 1.
The 1.0 and 0.5 mm values for the other cases are read from the committed b3/outputs/*.json.
"""
import json
import os
import subprocess
import sys

from paths import B3, RESULTS, RUNS

sys.path.insert(0, str(B3))
import run_study as rs  # noqa: E402  (read-only import: OPS, cases(), GEOM, HEAT paths)

OUT = RUNS / "legacy"
CASES = [("nominal", 10), ("c28", 10), ("c28", 25), ("nominal", 25)]


def run(op, h, pitch):
    name = f"{op}_h{h}_p{str(pitch).replace('.', 'p')}"
    path = OUT / f"{name}.json"
    if not path.exists():
        OUT.mkdir(parents=True, exist_ok=True)
        heat = rs.HEAT_C28 if rs.OPS[op].get("heat") == "c28" else rs.HEAT
        subprocess.run([sys.executable, str(B3 / "thermal.py"), "--geometry", str(rs.GEOM), "--case", rs.cases(op),
                        "--pitch-mm", str(pitch), "--h", str(h), "--a6-heat", str(heat), "--a6-mode", rs.OPS[op]["parts"],
                        "--output", str(path)], check=True, stdout=subprocess.DEVNULL,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        for ext in (".npz",):                         # keep the json and png only (disk)
            p = path.with_suffix(ext)
            if p.exists():
                p.unlink()
    return json.loads(path.read_text())


def summarise(r):
    parts = sorted(r["a6_parts_applied"], key=lambda p: -p["conditional_pad_cell_max_c"])
    return {"peak_c": round(r["peak"]["temperature_c"], 2), "peak_at": [r["peak"]["x_mm"], r["peak"]["y_mm"], r["peak"]["layer"]],
            "board_sha256": r["board_sha256"],
            "pad_cell_max_c": {p["ref"]: round(p["conditional_pad_cell_max_c"], 1) for p in parts[:10]},
            "pad_cell_counts": {p["ref"]: p["pad_cell_count"] for p in parts[:10]}}


def main():
    summary = json.loads((B3 / "outputs/summary.json").read_text())
    out = {"control_L1": {}, "cases": {}}
    ok = True
    for op, h in (("nominal", 10), ("c28", 25)):
        r = run(op, h, 1.0)
        ref = summary["runs"][f"{op}_h{h}_p1p0"]["peak"]["temperature_c"]
        d = abs(r["peak"]["temperature_c"] - ref)
        out["control_L1"][f"{op}_h{h}_p1p0"] = {"rerun_c": r["peak"]["temperature_c"], "committed_c": ref, "diff_k": d}
        ok &= d < 1e-6
    for op, h in CASES:
        row = {}
        for p in (1.0, 0.5):
            committed = B3 / "outputs" / f"{op}_h{h}_p{str(p).replace('.', 'p')}.json"
            row[str(p)] = summarise(json.loads(committed.read_text()))
        row["0.25"] = summarise(run(op, h, 0.25))
        out["cases"][f"{op}_h{h}"] = row
    out["control_L1"]["pass"] = ok
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "legacy_grid.json").write_text(json.dumps(out, indent=1) + "\n")
    for k, row in out["cases"].items():
        print(k, " / ".join(f"{p} mm {row[p]['peak_c']} C @ {row[p]['peak_at']}" for p in ("1.0", "0.5", "0.25")))
    print("control L1", "PASS" if ok else "FAIL", out["control_L1"])
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
