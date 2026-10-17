#!/usr/bin/env python3
"""Compare two f6_legs.py results.json files case by case (same job list), and summarise each.

    python3 -I f6_compare.py LABEL_OLD=OLD/results.json LABEL_NEW=NEW/results.json [--json OUT]

Per run: complete / pass / pass_hot counts, worst die VDS per case class (limit 520 V S1/S4/S5, 585 V S2), worst
off-gate (limits 1.9 V hot screen, 3.0 V, model threshold), worst |VGS| (30 V), S1 ZVS count. Per pair: max |delta|
of die VDS and off-gate over matching rows, and every row whose pass / pass_hot flipped.
"""
import json
import sys
from pathlib import Path

KEY = ("leg", "temp_C", "case", "vbus", "il", "dir", "dt_ns", "esl_nH")


def summ(rows):
    c = [r for r in rows if r["status"] == "complete"]
    out = {"cases": len(rows), "complete": len(c), "pass": sum(r["pass"] for r in c),
           "pass_hot": sum(r["pass_hot"] for r in c), "by_case": {}}
    for case in sorted({r["case"] for r in rows}):
        g = [r for r in c if r["case"] == case]
        lim = 585 if case == "S2" else 520
        w = max(g, key=lambda r: r["vds_pk"])
        o = max(g, key=lambda r: r["off_V"])
        out["by_case"][case] = {"n": len(g), "pass_hot": sum(r["pass_hot"] for r in g),
                                "max_vds_V": round(w["vds_pk"], 2), "vds_limit_V": lim,
                                "vds_margin_V": round(lim - w["vds_pk"], 2),
                                "worst_vds_row": {k: w[k] for k in KEY},
                                "max_off_V": round(o["off_V"], 4), "off_margin_to_1p9_V": round(1.9 - o["off_V"], 4),
                                "worst_off_row": {k: o[k] for k in KEY},
                                "max_vgs_abs_V": round(max(r["vgs_abs"] for r in g), 3),
                                **({"zvs": sum(r["zvs"] for r in g)} if case == "S1" else {})}
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    js = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    if js:
        args.remove(js)
    runs = [a.split("=", 1) for a in args]
    data = {lab: json.loads(Path(p).read_text()) for lab, p in runs}
    res = {"runs": {lab: {"path": p, **summ(data[lab])} for lab, p in runs}}
    if len(runs) == 2:
        (la, _), (lb, _) = runs
        A = {tuple(r[k] for k in KEY): r for r in data[la]}
        B = {tuple(r[k] for k in KEY): r for r in data[lb]}
        assert set(A) == set(B), "job lists differ"
        both = [k for k in A if A[k]["status"] == B[k]["status"] == "complete"]
        dv = [B[k]["vds_pk"] - A[k]["vds_pk"] for k in both]
        do = [B[k]["off_V"] - A[k]["off_V"] for k in both]
        res["delta"] = {"rows": len(both), "vds_max_up_V": round(max(dv), 3), "vds_max_down_V": round(min(dv), 3),
                        "off_max_up_V": round(max(do), 4), "off_max_down_V": round(min(do), 4),
                        "flips": [{"row": dict(zip(KEY, k)), "old": (A[k].get("pass"), A[k].get("pass_hot")),
                                   "new": (B[k].get("pass"), B[k].get("pass_hot"))}
                                  for k in A if (A[k].get("pass"), A[k].get("pass_hot")) != (B[k].get("pass"), B[k].get("pass_hot"))]}
    txt = json.dumps(res, indent=1)
    if js:
        Path(js).write_text(txt + "\n")
    for lab, s in res["runs"].items():
        print(f"{lab}: {s['pass_hot']}/{s['cases']} pass_hot ({s['complete']} complete)")
        for case, g in s["by_case"].items():
            print(f"   {case}: {g['pass_hot']}/{g['n']}  max VDS {g['max_vds_V']} (margin {g['vds_margin_V']})  "
                  f"max off {g['max_off_V']} (to 1.9 V {g['off_margin_to_1p9_V']})  |VGS| {g['max_vgs_abs_V']}"
                  + (f"  ZVS {g['zvs']}" if "zvs" in g else ""))
    if "delta" in res:
        d = res["delta"]
        print(f"delta over {d['rows']} rows: VDS {d['vds_max_down_V']} .. +{d['vds_max_up_V']} V, off-gate "
              f"{d['off_max_down_V']} .. +{d['off_max_up_V']} V, flips {len(d['flips'])}")


if __name__ == "__main__":
    main()
