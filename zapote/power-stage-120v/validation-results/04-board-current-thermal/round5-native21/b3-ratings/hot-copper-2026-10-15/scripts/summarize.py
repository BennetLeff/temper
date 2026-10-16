#!/usr/bin/env python3
"""Hot-copper B3 (OPEN-ITEMS S17) summary: BASIS hot vs the 20 C copper record, copper loss multipliers, and the bay-61
ceiling by direct solves.

    python3 -I summarize.py   -> ../hot-copper.json   (reads committed margins files and the gitignored run files)

Inputs (b3-ratings/):
  margins.json                          hot-copper BASIS (run_basis.py default)
  hot-copper-2026-10-15/margins-cold-copper.json   the same BASIS on 20 C copper (= ff921e889 margins.json; the
                                        control run_basis.py --copper-tcr 0 reproduced it byte for byte)
  runs/c*_p0p25.json / _p0p5.json       BASIS run files (copper_temp_model)
  hot-copper-2026-10-15/margins-bay61.json   direct solves at bay 61 (c8, c12, c16, c17, c17.25, c17.5, c17.75)
  hot-copper-2026-10-15/margins-bay55.json   direct solves at bay 55 (c19, c20) - the ceilings.py extrapolation check
Ceiling at bay 61 = the highest solved ceiling whose gated rows all pass, with the next solved ceiling failing, for three
row sets: as built (every gated row, monitor ICs at their 85 C TA grades), monitors at the 125 C grades of the same
pinouts (TL431BQDBZR, LM2901BIDR), and without the monitor rows (the S17 copper effect alone, rows as before S16).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAT = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(RAT))
import b3_ratings_gate as gate  # noqa: E402

MON = set(gate.MONITORS)


def worst(rows, mode):
    out = []
    for r in rows:
        if not r["gated"]:
            continue
        ref = r["item"].split(":")[0]
        if ref in MON:
            if mode == "no_monitor":
                continue
            if mode == "grade125" and r["limit_c"] < 125.0:
                r = {**r, "margin_k": round(125.0 - r["est_c"], 1), "item": r["item"] + " [at the 125 C grade]"}
        out.append(r)
    w = min(out, key=lambda r: r["margin_k"])
    return {"margin_k": w["margin_k"], "row": w["item"]}


def main():
    hot = json.loads((RAT / "margins.json").read_text())
    cold = json.loads((HERE.parent / "margins-cold-copper.json").read_text())
    res = {"basis": {}, "metrics": {"cold_20c": cold["metrics"], "hot": hot["metrics"]}, "copper": {}}
    for c in hot["cases"]:
        old = {r["item"]: r["margin_k"] for r in cold["cases"][c]}
        rows = [{"row": r["item"], "cold_k": old.get(r["item"]), "hot_k": r["margin_k"],
                 "delta_k": None if r["item"] not in old else round(r["margin_k"] - old[r["item"]], 1)}
                for r in hot["cases"][c] if r["gated"]][:8]
        res["basis"][c] = {**hot["basis"]["cases"][c], "worst_gated_hot": worst(hot["cases"][c], "all"),
                           "worst_gated_no_monitor": worst(hot["cases"][c], "no_monitor"),
                           "worst_gated_cold": worst(cold["cases"][c], "all"), "top_rows": rows}
        for m in ("p0p25", "p0p5"):
            ctm = json.loads((RAT / f"runs/{c}_{m}.json").read_text())["copper_temp_model"]
            res["copper"][f"{c}_{m}"] = {k: ctm[k] for k in ("air_c", "picard_steps", "max_dT_k", "loop_gain_rayleigh",
                                                              "max_heated_copper_c", "loss_w_20c", "loss_w_hot",
                                                              "loss_multiplier", "loss_multiplier_by_case")}
    pts = {}
    b61 = json.loads((HERE.parent / "margins-bay61.json").read_text())
    for src in (b61, hot):
        for c, rows in src["cases"].items():
            if src["basis"]["cases"][c]["bay_c"] != 61.0:
                continue
            ceil, _ = gate.case_ceiling_h(c)
            pts[ceil] = {"case": c, **{k: worst(rows, k) for k in ("all", "grade125", "no_monitor")}}
    ceil = {}
    xs = sorted(pts)
    for k in ("all", "grade125", "no_monitor"):
        ok = [x for x in xs if pts[x][k]["margin_k"] >= 0]
        bad = [x for x in xs if pts[x][k]["margin_k"] < 0]
        top = max(ok) if ok else None
        nxt = min((x for x in bad if top is None or x > top), default=None)
        ceil[k] = {"ceiling_a": top, "next_solved_failing_a": nxt,
                   "resolved_to_0p25": top is not None and nxt is not None and nxt - top <= 0.25 + 1e-9,
                   "monotone": all(pts[x][k]["margin_k"] >= pts[y][k]["margin_k"] for x, y in zip(xs, xs[1:]))}
    res["bay61_direct"] = {"points": {f"{x:g}": pts[x] for x in xs}, "ceiling": ceil}
    f55 = HERE.parent / "margins-bay55.json"
    if f55.exists():
        b55 = json.loads(f55.read_text())
        res["bay55_direct"] = {c: {k: worst(rows, k) for k in ("all", "grade125", "no_monitor")} for c, rows in b55["cases"].items()}
    (HERE.parent / "hot-copper.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({"metrics": res["metrics"], "bay61": {f"{x:g}": {k: pts[x][k]["margin_k"] for k in pts[x] if k != "case"}
                                                          for x in xs}, "ceiling": ceil,
                      "bay55": res.get("bay55_direct")}, indent=1))


if __name__ == "__main__":
    main()
