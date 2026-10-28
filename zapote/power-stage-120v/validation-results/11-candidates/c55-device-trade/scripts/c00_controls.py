#!/usr/bin/env python3
"""Step 0: reproduce the 2026-10-15 device-study controls (DECISIONS 49) and the gate-network baseline (DECISIONS 54)
before any new number is written.

Controls (each compared with the committed rows, not re-derived):
  K1 DS repro    128 c33 s32 ZVS rows      (device-study harness 'repro'; committed DS sims/IPW65R018CFD7_L1/repro)
  K2 DS zvs      672-run as-built S1 sweep (harness 'zvs'; committed DS sims/.../zvs; summary by DS analyze.zvs_summary)
  K3 DS thermal  C1 (R33 requirement.py) and C2 (round6 board-side-fets.csv) via DS thermal.controls(); every committed
                 thermal.json row recomputed by DS thermal.basis_rows()
  K4 DS bias     DS bias.control()
  K5 DS price    IPW65R018CFD7 $10.17612 @510 in the committed DS market/mosfets.csv
  K6 GN repro    320 as-built edge/edge2 rows (gn 'repro', S4 max slew 85.78 / 81.87 V/ns = S14)
  K7 GN c39      the adopted network (68 ohm 2512 + 4.7 nF, TT 125 ns) on the 640-run full grid against the committed
                 gate-network summary.json row split68_1_cgs4p7_tt125

    python3 -I c00_controls.py [--workers 8] [--only K1,K2,...]  -> ../results/controls.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C55, DS_DIR, GN_DIR, H, G, SIMS, _load, sha

RES = C55 / "results"


def run_ds(mode: str, workers: int):
    out = SIMS / "control" / f"ds_{mode}"
    deck = H.write_deck(H.AS_BUILT, out, energy=(mode == "energy"))
    jobs, want = H.jobs_for(mode)

    def go(j):
        case, v, leg, t, vb, il, d, dt, *esl = j
        r = H.run_one(deck, out, H.AS_BUILT, v, leg, t, vb, il, d, dt, esl=(esl[0] if esl else 10))
        if r["status"] != "complete":
            r = H.run_one(deck, out / "retry", H.AS_BUILT, v, leg, t, vb, il, d, dt, esl=(esl[0] if esl else 10),
                          trmax="0.1n")
        return H.screen(r, case)

    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(go, jobs))
    (out / "results.json").write_text(json.dumps({"mode": mode, "identity": H.identity(H.AS_BUILT, deck),
                                                  "rows": rows}, indent=1, default=str) + "\n")
    return rows, want


def cmp_rows(mine, ref, keys):
    worst = {k: 0.0 for k in keys}
    exact = 0
    status_diff = 0
    for a, b in zip(mine, ref):
        if a["status"] != b["status"]:
            status_diff += 1
            continue
        if a["status"] != "complete":
            continue
        same = True
        for k in keys:
            x, y = a.get(k), b.get(k)
            if x is None and y is None:
                continue
            if x is None or y is None:
                worst[k] = math.inf
                same = False
                continue
            dlt = abs(float(x) - float(y))
            worst[k] = max(worst[k], dlt)
            same &= dlt == 0
        exact += same
    return {"rows": len(mine), "ref_rows": len(ref), "status_diff": status_diff, "bit_identical_rows": exact,
            "max_abs_delta": worst}


def k1(workers):
    rows, want = run_ds("repro", workers)
    ref = json.loads((DS_DIR / "sims/IPW65R018CFD7_L1/repro/results.json").read_text())
    c33 = {"incoming_V": 0.0, "vds_pk": 0.0, "t_trans_ns": 0.0}
    for w, r in zip(want, rows):
        if r["status"] == "complete":
            c33["incoming_V"] = max(c33["incoming_V"], abs(r["incoming_V"] - w["incoming_V_at_on"]))
            c33["vds_pk"] = max(c33["vds_pk"], abs(r["vds_pk"] - w["vds_pk"]))
            c33["t_trans_ns"] = max(c33["t_trans_ns"], abs(r["t_trans_ns"] - w["t_trans_ns"]))
    out = {"vs_committed_c33": {"complete": f"{sum(r['status'] == 'complete' for r in rows)}/{len(rows)}",
                                "max_abs_delta": c33,
                                "DS_reported": "128/128; 2.6 uV incoming, 0.7 mV die VDS, 0 ns"},
           "vs_committed_DS_rows": cmp_rows(rows, ref["rows"], ("incoming_V", "vds_pk", "t_trans_ns", "off_V"))}
    out["pass"] = (out["vs_committed_c33"]["complete"] == "128/128" and c33["vds_pk"] < 1e-3 and
                   c33["incoming_V"] < 1e-4 and c33["t_trans_ns"] < 0.01)
    return out


def k2(workers):
    rows, _ = run_ds("zvs", workers)
    ref = json.loads((DS_DIR / "sims/IPW65R018CFD7_L1/zvs/results.json").read_text())
    A = _load("ds_analyze", DS_DIR / "scripts/analyze.py")
    mine, theirs = A.zvs_summary(rows), A.zvs_summary(ref["rows"])
    pick = lambda s: {leg: {"worst_t_trans_ns": s[leg]["S1_37A_worst_t_trans_ns"], "margin_ns": s[leg]["S1_37A_margin_ns"],
                            "threshold_A": {k: v["il_threshold_A"] for k, v in s[leg]["zvs_threshold_worst"].items()}}
                      for leg in "AB"}
    out = {"summary_mine": pick(mine), "summary_committed": pick(theirs),
           "DS_reported": "leg A 188.9 ns (219.4/151.1), 9.11/11.65 A; leg B 190.36 ns (217.9/149.6), 9.14/11.73 A",
           "vs_committed_DS_rows": cmp_rows(rows, ref["rows"], ("incoming_V", "vds_pk", "t_trans_ns", "off_V"))}
    out["pass"] = pick(mine) == pick(theirs) and out["vs_committed_DS_rows"]["status_diff"] == 0
    return out


def k3():
    T = _load("ds_thermal", DS_DIR / "scripts/thermal.py")
    c = T.controls()
    ref = json.loads((DS_DIR / "results/thermal.json").read_text())
    worst, n = 0.0, 0
    for dev in T.DEVICES:
        mine = T.basis_rows(dev)
        for cn, row in mine.items():
            for basis, b in row.items():
                for sk in T.SINKS:
                    if sk in b:
                        x, y = b[sk]["tj_max"], ref["devices"][dev]["cases"][cn][basis][sk]["tj_max"]
                        if isinstance(x, str) or isinstance(y, str):
                            assert x == y, (dev, cn, basis, sk, x, y)
                        else:
                            worst = max(worst, abs(x - y))
                        n += 1
    return {"C1_C2": c, "thermal_json_rows": n, "thermal_json_max_abs_delta_C": worst,
            "pass": bool(c["pass"]) and worst == 0.0}


def k4():
    B = _load("ds_bias", DS_DIR / "scripts/bias.py")
    c = B.control()
    return {"control": c, "pass": bool(c["pass"])}


def k5():
    rows = list(csv.DictReader((DS_DIR / "market/mosfets.csv").open()))
    r = [x for x in rows if x["orderable_mpn"] == "IPW65R018CFD7XKSA1"][0]
    ok = abs(float(r["break_unit_usd"]) - 10.17612) < 1e-9 and r["break_qty"] == "510"
    return {"row": {k: r[k] for k in ("orderable_mpn", "stock", "break_qty", "break_unit_usd", "fetched_utc")},
            "pass": ok}


# Measures that the committed gn.py added after its 320-row control was run (R_on energy and incoming-gate times).
# They are par() expressions, which ngspice turns into B-sources, so they move rows by up to 0.46 V / 0.17 V/ns.
# 'era' strips them to rebuild the deck the control was run with (probe: one S4 row returns to 422.4335 V exactly).
LATER_MEAS = ("e_rgl", "e_rgh", "tgh4", "tgl4", "tgh10", "tgl10", "v(gdl) v(gdh) v(offl)")


def run_gn(cfg_name: str, grid_name: str, workers: int, era: bool = False):
    cfg = G.configs()[cfg_name]
    out = SIMS / "control" / f"gn_{cfg_name}_{grid_name}{'_era' if era else ''}"
    out.mkdir(parents=True, exist_ok=True)
    jobs = G.grid(grid_name)
    ref = None
    if grid_name in ("repro", "erepro"):
        ref = [r for _, r in jobs]
        jobs = [j for j, _ in jobs]
    decks = {}
    for en in (False, True):
        p = out / ("deck_energy.cir" if en else "deck.cir")
        txt = G.build_deck(cfg, energy=en)
        if era:
            txt = "\n".join(ln for ln in txt.splitlines() if not any(x in ln for x in LATER_MEAS)) + "\n"
        p.write_text(txt)
        decks[en] = p

    def go(j):
        case, drv, leg, t, vb, il, d, dt, esl, *en = j
        en = bool(en and en[0])
        r = G.run_case(decks[en], out, cfg, case, drv, leg, t, vb, il, d, dt, esl)
        if r["status"] != "complete":
            r = G.run_case(decks[en], out / "retry", cfg, case, drv, leg, t, vb, il, d, dt, esl, trmax="0.1n")
        return G.screen(r)

    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(go, jobs))
    (out / "results.json").write_text(json.dumps({"cfg": cfg, "grid": grid_name, "identity":
                                                  {str(p): sha(p) for p in decks.values()}, "rows": rows,
                                                  "reference": ref}, indent=1, default=str) + "\n")
    return rows, ref


def k6(workers):
    """The control-era deck must reproduce gn's 317/320; the current gn.py deck is reported beside it."""
    cur = SIMS / "control" / "gn_asbuilt_repro" / "results.json"
    if cur.is_file():
        d = json.loads(cur.read_text())
        cur_cmp = cmp_rows(d["rows"], d["reference"], ("vds_pk", "off_V", "slew2080_Vns", "t_trans_ns", "incoming_V"))
    else:
        cur_cmp = None
    rows, ref = run_gn("asbuilt", "repro", workers, era=True)
    c = cmp_rows(rows, ref, ("vds_pk", "off_V", "slew2080_Vns", "t_trans_ns", "incoming_V"))
    within = sum(1 for a, b in zip(rows, ref) if a["status"] == "complete" and abs(a["vds_pk"] - b["vds_pk"]) <= 1e-3)
    s4 = {e: round(max(r.get("slew2080_Vns", 0) for r in rows if r["status"] == "complete" and r["case"] == "S4"
                       and r["esl_nH"] == e), 2) for e in (10, 1.06)}
    gn_ctrl = json.loads((GN_DIR / "results/controls.json").read_text())["asbuilt_vs_committed_edge_edge2"]
    out = {"deck": "control-era gn deck (LATER_MEAS stripped)", "current_gn_deck_vs_DS_rows": cur_cmp,
           "vs_committed_DS_edge_edge2": c, "rows_within_1mV_vds": within, "S4_max_slew_Vns": s4,
           "GN_reported": {k: gn_ctrl[k] for k in ("rows_within_1mV_vds", "S4_max_slew_esl10", "S4_max_slew_esl1.06",
                                                  "max_abs_delta")}}
    out["pass"] = (within >= gn_ctrl["rows_within_1mV_vds"] and s4[10] == gn_ctrl["S4_max_slew_esl10"] and
                   s4[1.06] == gn_ctrl["S4_max_slew_esl1.06"])
    return out


def summarize_full(rows):
    """The fields of the gate-network summary.json 'full' block that the trade quotes."""
    ok = [r for r in rows if r["status"] == "complete"]
    s = {"runs": len(rows), "complete": len(ok), "pass": sum(bool(r.get("pass")) for r in ok),
         "pass_hot": sum(bool(r.get("pass_hot")) for r in ok)}
    for case in ("S1", "S2", "S4", "S5"):
        c = [r for r in ok if r["case"] == case]
        if not c:
            continue
        d = {"n": len(c), "max_vds": round(max(r["vds_pk"] for r in c), 1),
             "max_off_V": round(max(r["off_V"] for r in c), 3)}
        for e in (10, 1.06):
            ce = [r.get("slew2080_Vns") or 0 for r in c if r["esl_nH"] == e]
            if ce:
                d[f"max_slew2080_esl{e:g}"] = round(max(ce), 2)
        if case == "S1":
            d["zvs"] = f"{sum(r['zvs'] for r in c)}/{len(c)}"
            d["worst_t_trans_ns"] = round(max(r["t_trans_ns"] for r in c), 1)
        if case == "S4":
            d["max_difdt_75_25"] = round(max(r.get("difdt_75_25_Apus") or 0 for r in c), 0)
            d["max_irr_A"] = round(max(r.get("i_rr_pk_A") or 0 for r in c), 1)
            d["pass_diode56"] = sum(bool(r.get("pass_diode56")) for r in c)
        s[case] = d
    return s


def k7(workers):
    rows, _ = run_gn("split68_1_cgs4p7_tt125", "full", workers)
    mine = summarize_full(rows)
    ref = json.loads((GN_DIR / "results/summary.json").read_text())["split68_1_cgs4p7_tt125"]["full"]
    checks = {"S4_slew10": (mine["S4"]["max_slew2080_esl10"], ref["S4"]["max_slew2080_esl10"]),
              "S4_slew1.06": (mine["S4"]["max_slew2080_esl1.06"], ref["S4"]["max_slew2080_esl1.06"]),
              "S4_difdt": (mine["S4"]["max_difdt_75_25"], ref["S4"]["max_difdt_75_25"]),
              "S4_vds": (mine["S4"]["max_vds"], ref["S4"]["max_vds"]),
              "S2_vds": (mine["S2"]["max_vds"], ref["S2"]["max_vds"]),
              "S1_t_trans": (mine["S1"]["worst_t_trans_ns"], ref["S1"]["worst_t_trans_ns"]),
              "S4_off": (mine["S4"]["max_off_V"], ref["S4"]["max_off_V"]),
              "pass": (mine["pass"], ref["pass"])}
    ok = all(abs(a - b) <= 0.051 for a, b in checks.values())     # equal at the committed rounding
    return {"mine": mine, "checks_mine_vs_committed": checks, "pass": ok}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--only", default="K1,K2,K3,K4,K5,K6,K7")
    a = ap.parse_args()
    RES.mkdir(exist_ok=True)
    p = RES / "controls.json"
    res = json.loads(p.read_text()) if p.is_file() else {}
    fns = {"K1": lambda: k1(a.workers), "K2": lambda: k2(a.workers), "K3": k3, "K4": k4, "K5": k5,
           "K6": lambda: k6(a.workers), "K7": lambda: k7(a.workers)}
    for k in a.only.split(","):
        res[k] = fns[k]()
        print(k, "PASS" if res[k]["pass"] else "FAIL", json.dumps(res[k], default=str)[:600], flush=True)
        p.write_text(json.dumps(res, indent=1, default=str) + "\n")
    print("ALL", all(v["pass"] for v in res.values()))


if __name__ == "__main__":
    main()
