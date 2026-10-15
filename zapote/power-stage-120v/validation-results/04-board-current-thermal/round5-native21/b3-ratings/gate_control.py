#!/usr/bin/env python3
"""Controls for b3_ratings_gate.py (exit 1 if any fails).

    python3 gate_control.py --runs ../runs/body [--out ../results/gate_control.json]

G1 real s32 runs at the declared basis: report the verdict (the gate's answer for the board of record).
G2 deliberately HOT input: the real c22_h10 files with every temperature +40 K - must FAIL.
G3 deliberately COOL input: every rise above 50 C scaled by 0.3 - must PASS (the gate can pass).
G4 single-part trip: real c28_h25 files (laminate margin positive at bay 50) with only U42's junction raised to 151 C at
   both meshes - must FAIL on U42 alone (a part limit is enforced independently of the laminate).
G5 mesh allowance: 0.25 mm value unchanged, 0.5 mm value lowered by 10 K on R5 only - the R5 estimate must rise by 20 K.
"""
import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import b3_ratings_gate as g  # noqa: E402


def mutate(run, fn):
    r = copy.deepcopy(run)
    r["peak_1mm_block"]["temperature_c"] = fn(r["peak_1mm_block"]["temperature_c"])
    r["fet_row_max_c"] = fn(r["fet_row_max_c"])
    for p in r["parts"]:
        for k in ("tj_c", "pad_max_cell_c", "pad_mean_c"):
            if k in p:
                p[k] = fn(p[k])
    return r


def gate_cli(runs, cases, bay):
    p = subprocess.run([sys.executable, str(HERE / "b3_ratings_gate.py"), "--runs", str(runs), "--cases", cases,
                        "--bay-c", str(bay)], capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    runs = Path(a.runs)
    load = lambda n: json.loads((runs / f"{n}.json").read_text())
    res, ok = {}, True
    rc, msg = gate_cli(runs, "c22_h10,c28_h10", 55.0)
    res["G1_s32_basis"] = {"exit": rc, "output": msg}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for n in ("c22_h10_p0p25", "c22_h10_p0p5"):
            (td / f"{n}.json").write_text(json.dumps(mutate(load(n), lambda t: t + 40.0)))
        rc, msg = gate_cli(td, "c22_h10", 50.0)
        res["G2_hot_must_fail"] = {"exit": rc, "output": msg, "ok": rc == 1}
        for n in ("c22_h10_p0p25", "c22_h10_p0p5"):
            (td / f"{n}.json").write_text(json.dumps(mutate(load(n), lambda t: 50.0 + 0.3 * (t - 50.0))))
        rc, msg = gate_cli(td, "c22_h10", 50.0)
        res["G3_cool_must_pass"] = {"exit": rc, "output": msg, "ok": rc == 0}
        base = g.run(runs, ["c28_h25"], 50.0)
        for n in ("c28_h25_p0p25", "c28_h25_p0p5"):
            r = load(n)
            for p in r["parts"]:
                if p["ref"] == "U42":
                    p["tj_c"] = 151.0
            (td / f"{n}.json").write_text(json.dumps(r))
        trip = g.run(td, ["c28_h25"], 50.0)
        u42 = [r for r in trip["cases"]["c28_h25"] if r["item"].startswith("U42")]
        res["G4_single_part"] = {"laminate_margin_base": base["metrics"]["b3_laminate_margin_K"],
                                 "base_pass": base["pass"], "trip_pass": trip["pass"], "u42_rows": u42,
                                 "ok": base["metrics"]["b3_laminate_margin_K"] >= 0 and not trip["pass"]
                                 and trip["metrics"]["worst_gated"].startswith("U42")}
        r25, r05 = load("c22_h10_p0p25"), load("c22_h10_p0p5")
        e0 = [r for r in g.evaluate(r25, r05, 50.0) if r["item"].startswith("R5: element")][0]["est_c"]
        r05b = copy.deepcopy(r05)
        for p in r05b["parts"]:
            if p["ref"] == "R5":
                p["tj_c"] -= 10.0
        r05b_base = [p for p in r05["parts"] if p["ref"] == "R5"][0]["tj_c"]
        r25_v = [p for p in r25["parts"] if p["ref"] == "R5"][0]["tj_c"]
        e1 = [r for r in g.evaluate(r25, r05b, 50.0) if r["item"].startswith("R5: element")][0]["est_c"]
        expect = g.K_MESH * (abs(r25_v - (r05b_base - 10.0)) - abs(r25_v - r05b_base))
        res["G5_mesh_allowance"] = {"est_before": e0, "est_after": e1, "expected_rise": round(expect, 1),
                                    "ok": abs((e1 - e0) - expect) < 0.11}
    # G6 (information): the gate's estimate against the audit's verdict.py central estimate (19b fine-window increments)
    vf = HERE.parent / "results/verdict.json"
    if vf.exists():
        v = json.loads(vf.read_text())["cases"]
        cmp = {}
        for c in ("c22_h10", "c28_h10", "c28_h25"):
            gr = {r["item"]: r["est_c"] for r in g.run(runs, [c], 50.0)["cases"][c]}
            vr = {(r["ref"], r["quantity"]): r["est_c"] for r in v[c]["rows"]}
            cmp[c] = {"board block: gate / verdict": [gr["laminate: 1 mm-block copper peak"], vr[("board", "1 mm-block copper peak")]],
                      "R5 element: gate / verdict": [[x for k, x in gr.items() if k.startswith("R5: element")][0],
                                                     vr[("R5", "junction / element / body node")]],
                      "U42 Tj: gate / verdict": [[x for k, x in gr.items() if k.startswith("U42")][0],
                                                 vr[("U42", "junction / element / body node")]]}
        res["G6_gate_vs_verdict_info"] = cmp
    for k in ("G2_hot_must_fail", "G3_cool_must_pass", "G4_single_part", "G5_mesh_allowance"):
        ok &= res[k]["ok"]
    res["all_controls_pass"] = ok
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    for k, v in res.items():
        print(k, v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != "u42_rows"})
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
