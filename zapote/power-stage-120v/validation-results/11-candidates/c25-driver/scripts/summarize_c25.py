#!/usr/bin/env python3
"""c25: fold the D2 runs, the dead-time window and the sourcing numbers into the candidate's metrics.

Rerun: python3 -I summarize_c25.py   (after d2_c25.py edge/dtband and dt_window.py; writes ../results/c25_summary.json)

CMTI: the repo's rule (06-controller-interface/cmti, DECISIONS F6) uses a 95 V/ns modelled hard edge. The D2 deck
here is the as-built native-21 F6 deck; its absolute edge rates are not the 95 V/ns figure (that came from the
unipolar round-17 grid). So the new driver's edge is scaled: edge_new = 95 x (slew_new / slew_asbuilt), with the
20-80 % switch-node slew of the fastest hard edge (S4/S5) over all legs/temperatures/buses/directions/ESLs.
"""
import json
import statistics
from pathlib import Path

R = Path(__file__).resolve().parent.parent / "results"
EDGE_95 = 95.0
CMTI = {"UCC21550": 125.0, "2EDR8259": 150.0}        # SLUSE89C 5.9 p.10; Infineon Rev 1.7 Table 23 p.17


def key(r):
    return (r["leg"], r["temp_C"], r["case"], r["vbus"], r["dir"], r["esl_nH"], r["dt_ns"])


def main():
    edge = json.loads((R / "edge" / "results.json").read_text())
    ref = {key(r): r for r in edge if r["variant"] == "ucc_asbuilt" and r["status"] == "complete"}
    out = {"edge": {}, "dtband": {}}
    for v in sorted({r["variant"] for r in edge}):
        rows = [r for r in edge if r["variant"] == v and r["status"] == "complete"]
        hard = [r for r in rows if r["case"] in ("S4", "S5") and r.get("slew2080_Vns")]
        ratios = [r["slew2080_Vns"] / ref[key(r)]["slew2080_Vns"] for r in hard
                  if key(r) in ref and ref[key(r)].get("slew2080_Vns")]
        worst_new = max((r["slew2080_Vns"] for r in hard), default=None)
        worst_ref = max((r.get("slew2080_Vns", 0) for r in ref.values() if r["case"] in ("S4", "S5")), default=None)
        e = {"cases": len([r for r in edge if r["variant"] == v]), "complete": len(rows),
             "pass": sum(r["pass"] for r in rows), "pass_hot": sum(r["pass_hot"] for r in rows),
             "max_off_V": max(r["off_V"] for r in rows), "max_vds_V": max(r["vds_pk"] for r in rows),
             "s1_zvs": f"{sum(r['zvs'] for r in rows if r['case'] == 'S1')}/{sum(r['case'] == 'S1' for r in rows)}",
             "hard_slew2080_max_Vns": worst_new, "asbuilt_hard_slew2080_max_Vns": worst_ref,
             "slew_ratio_vs_asbuilt": {"max": max(ratios), "median": statistics.median(ratios), "min": min(ratios)}
             if ratios else None,
             "ratio_of_worst": worst_new / worst_ref if worst_new and worst_ref else None}
        drv = "UCC21550" if v.startswith("ucc") else "2EDR8259"
        if ratios:
            # CMTI is set by the fastest edge on the board: scale 95 V/ns by worst(new) / worst(as-built).
            # Pairwise ratios are reported only for information: their extremes are slow, multi-step edges
            # (e.g. 52 vs 20 V/ns in a 198 V S5 case) far below the worst edge, so they do not set CMTI.
            k = e["ratio_of_worst"]
            e["cases_above_asbuilt_worst"] = sum(r["slew2080_Vns"] > worst_ref for r in hard)
            e["edge_equiv_Vns"] = EDGE_95 * k
            e["cmti_gate_ratio_min"] = CMTI[drv] / (EDGE_95 * k)
        out["edge"][v] = e
    dtp = R / "dtband" / "results.json"
    if dtp.exists():
        dt = json.loads(dtp.read_text())
        for v in sorted({r["variant"] for r in dt}):
            for d in sorted({r["dt_ns"] for r in dt if r["variant"] == v}):
                g = [r for r in dt if r["variant"] == v and r["dt_ns"] == d]
                c = [r for r in g if r["status"] == "complete"]
                s1 = [r for r in c if r["case"] == "S1"]
                out["dtband"][f"{v}@{d}"] = {
                    "cases": len(g), "complete": len(c), "pass": sum(r["pass"] for r in c),
                    "pass_hot": sum(r["pass_hot"] for r in c), "max_off_V": max(r["off_V"] for r in c),
                    "max_off_S1S2_V": max((r["off_V"] for r in c if r["case"] in ("S1", "S2")), default=None),
                    "max_vds_V": max(r["vds_pk"] for r in c), "s1_zvs": f"{sum(r['zvs'] for r in s1)}/{len(s1)}",
                    "failures": [{k: r[k] for k in ("leg", "temp_C", "case", "vbus", "dir", "esl_nH", "off_V", "vds_pk",
                                                    "zvs")} for r in c if not r["pass_hot"]][:20],
                    "indeterminate": [{k: r[k] for k in ("leg", "temp_C", "case", "vbus", "dir", "esl_nH")}
                                      for r in g if r["status"] != "complete"]}
    out["dt_window"] = json.loads((R / "dt_window.json").read_text())
    (R / "c25_summary.json").write_text(json.dumps(out, indent=1) + "\n")
    for v, e in out["edge"].items():
        print(v, {k: (round(x, 3) if isinstance(x, float) else x) for k, x in e.items()})
    for k, e in out["dtband"].items():
        print(k, {kk: (round(x, 3) if isinstance(x, float) else x) for kk, x in e.items() if kk not in ("failures",)},
              "fails:", len(e["failures"]))


if __name__ == "__main__":
    main()
