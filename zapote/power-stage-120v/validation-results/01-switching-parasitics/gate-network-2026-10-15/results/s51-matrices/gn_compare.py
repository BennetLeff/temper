#!/usr/bin/env python3
"""Compare two gn.py 'full' results.json files (as-built gate network, 640 rows) row by row.

    python3 -I gn_compare.py LABEL_OLD=OLD/results.json LABEL_NEW=NEW/results.json [--json OUT]

Pass count as gate-network-2026-10-15/results/full.md's "all pass / hot": row 'pass' (die VDS, |VGS|, off-gate 3.0 V
and model threshold, ZVS for S1) and 'pass_hot' (adds 1.9 V). The S4 diode-slew (56 V/ns) and diF/dt (1,040 A/us)
screens are reported as maxima over the rows where they are measured (gn.py's pass_diode56 is False when no slew is
measured, 17 S4 rows on the committed grid, so it is not counted as a row flag).
"""
import json
import sys
from pathlib import Path

KEY = ("case", "drv", "leg", "temp_C", "vbus", "il", "dir", "dt_ns", "esl_nH")
FLAGS = ("pass", "pass_hot")   # full.md's "all pass / hot"; slew and diF/dt are reported as maxima against 56 V/ns and 1,040 A/us
MET = ("vds_pk", "off_V", "vgs_abs", "slew2080_Vns", "difdt_75_25_Apus", "t_trans_ns")


def ok(r):
    return r["status"] == "complete" and all(r.get(f, True) for f in FLAGS)


def summ(rows):
    c = [r for r in rows if r["status"] == "complete"]
    s = {"rows": len(rows), "complete": len(c), "all_screens": sum(ok(r) for r in rows), "by_case": {}}
    for case in sorted({r["case"] for r in rows}):
        g = [r for r in c if r["case"] == case]
        d = {"n": len(g), "all_screens": sum(ok(r) for r in g)}
        for m in MET:
            v = [r[m] for r in g if r.get(m) is not None]
            if v:
                d[f"max_{m}"] = round(max(v), 4)
        if case == "S1":
            d["zvs"] = sum(bool(r.get("zvs")) for r in g)
        s["by_case"][case] = d
    return s


def main():
    argv = sys.argv[1:]
    js = None
    if "--json" in argv:
        i = argv.index("--json"); js = argv[i + 1]; del argv[i:i + 2]
    runs = [a.split("=", 1) for a in argv]
    data = {lab: json.loads(Path(p).read_text())["rows"] for lab, p in runs}
    res = {"runs": {lab: {"path": p, **summ(data[lab])} for lab, p in runs}}
    if len(runs) == 2:
        (la, _), (lb, _) = runs
        A = {tuple(r[k] for k in KEY): r for r in data[la]}
        B = {tuple(r[k] for k in KEY): r for r in data[lb]}
        assert set(A) == set(B), "row sets differ"
        both = [k for k in A if A[k]["status"] == B[k]["status"] == "complete"]
        res["delta"] = {"rows": len(both)}
        for m in MET:
            dv = [B[k][m] - A[k][m] for k in both if A[k].get(m) is not None and B[k].get(m) is not None]
            if dv:
                res["delta"][m] = [round(min(dv), 4), round(max(dv), 4)]
        res["delta"]["flips"] = [dict(zip(KEY, k)) | {"old": ok(A[k]), "new": ok(B[k])} for k in A if ok(A[k]) != ok(B[k])]
    if js:
        Path(js).write_text(json.dumps(res, indent=1) + "\n")
    for lab, s in res["runs"].items():
        print(f"{lab}: all screens {s['all_screens']}/{s['rows']} ({s['complete']} complete)")
        for case, d in s["by_case"].items():
            print("   ", case, {k: v for k, v in d.items()})
    if "delta" in res:
        print("delta", json.dumps(res["delta"]))


if __name__ == "__main__":
    main()
