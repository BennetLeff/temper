#!/usr/bin/env python3
"""Body-diode recovery charge of each model in the round-17 D3 datasheet fixture (400 V clamped inductive), so every
S4 result can be placed on the part's datasheet typical / maximum Qrr.

Reuses the gate-network study's qrr.py (deck(), metrics(), one()) read-only; its C8 library path and output folder
are redirected here. Wrapped vendor models (SiC / IGBT) use the same fixture with the wrapper substituted (wrappers.py).
Controls: CFD7 TT 50 / 125 ns = 1.739 / 2.356 uC (D-24), C8 TT 25 / 80 ns at RG 400 / 730 = the committed gn qrr.json rows.
CM8 (C8 600 V vendor model = proxy B): the transit time that reaches the IPW65R018CM8 maximum Qrr, 2.31 uC at 400 V,
29.7 A, 100 A/us (Rev 2.1 Table 7), is found by interpolation at 100 A/us.

    python3 -I c05_qrr.py [--workers 8]   -> ../results/qrr.json
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C55, C8_LIB, GN_DIR, SIMS, _load  # noqa: E402

Q = _load("gn_qrr", GN_DIR / "scripts/qrr.py")
Q.gn.C8LIB = C8_LIB
Q.OUT = SIMS / "_qrr"
import wrappers  # noqa: E402


def wrap_deck(name: str) -> str:
    """The D3 fixture with a wrapped vendor model as both switch and DUT (wrappers.get). The fixture's .save of the
    CFD7-internal v_sense2 is dropped (not used by metrics()); the switch's gate step is 0 -> 13 V as in D3."""
    t = (Q.D3 / "recovery.cir").read_text()
    w = wrappers.get(name)
    nm, text, _ = w["wrapper"]
    assert t.count("IPW65R018CFD7_L1") == 2 and t.count(" i(v.xqd.x1.v_sense2)") == 1
    t = t.replace(" i(v.xqd.x1.v_sense2)", "").replace("IPW65R018CFD7_L1", nm)
    t = t.replace(".include params.inc", ".include params.inc\n.param TJDECK={TJ}", 1)
    return t.replace(".include IFX_CFD7_650V.lib", ".include IFX_CFD7_650V.lib\n" + text, 1)


def one_wrap(job):
    tag, name, ifwd, rg, tj = job
    out = Q.OUT / tag
    out.mkdir(parents=True, exist_ok=True)
    p = out / "recovery.cir"
    p.write_text(wrap_deck(name))
    r = Q.gn.run_d2.run(p, {"RG": str(rg), "TJ": str(tj), "STEP": "0.2n", "IFWD": str(ifwd)}, keep=out, raw=True)
    row = {"tag": tag, "model": name, "tt": name.partition("_tt")[2] or None, "IF_A": ifwd, "RG": rg, "TJ": tj,
           "aborted": r["aborted"]}
    if not r["aborted"]:
        sys.path.insert(0, str(Q.gn.run_d2.KIT / "common"))
        from run_ngspice import read_raw
        row.update(Q.metrics(read_raw(out / "waves.raw")))
        (out / "waves.raw").unlink(missing_ok=True)
    return row


def interp_100(rows):
    """Qrr at 100 A/us from the two RG points bracketing it (linear in slew)."""
    r = sorted(rows, key=lambda x: x["slew_A_per_us"])
    for a, b in zip(r, r[1:]):
        if a["slew_A_per_us"] <= 100 <= b["slew_A_per_us"]:
            f = (100 - a["slew_A_per_us"]) / (b["slew_A_per_us"] - a["slew_A_per_us"])
            return a["Qrr_uC"] + f * (b["Qrr_uC"] - a["Qrr_uC"]), a["trr_ns"] + f * (b["trr_ns"] - a["trr_ns"])
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    jobs = [("cfd7_018_tt50_cal730", "IPW65R018CFD7_L1", None, 58.2, 730, 25),
            ("cfd7_018_tt125_cal730", "IPW65R018CFD7_L1", "125e-9", 58.2, 730, 25),
            ("c8_016_rg400", "IPW60R016CM8_L1", None, 29.7, 400, 25),
            ("c8_016_rg730", "IPW60R016CM8_L1", None, 29.7, 730, 25)]
    for tt in (80, 160, 200, 240, 280):
        for rg in (400, 730):
            jobs.append((f"c8_016_tt{tt}_rg{rg}", "IPW60R016CM8_L1", f"{tt}e-9", 29.7, rg, 25))
    wjobs = []
    for tt in ("", "_tt90", "_tt150", "_tt200", "_tt250"):
        for rg in (400, 730):
            wjobs.append((f"cm8_650{tt}_rg{rg}", f"cm8_r39{tt}", 29.7, rg, 25))
    # SiC G2 (datasheet Qfr at 400 V, 34.5 A, 1000 A/us) and RC-H5 / RC-H6 (400 V, 40 A, 1000 A/us), 25 and 150 C
    for nm, tag, ifw in (("sic26_15_r8p2", "sic26", 34.5), ("rch5_r8p2", "rch5", 40.0), ("rch6_r8p2", "rch6", 40.0)):
        for rg in (20, 40, 80):
            for tj in (25, 150):
                wjobs.append((f"{tag}_rg{rg}_T{tj}", nm, ifw, rg, tj))
    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(Q.one, jobs))
        wrows = list(ex.map(one_wrap, wjobs))
    ref = {r["tag"]: r for r in json.loads((GN_DIR / "results/qrr.json").read_text())["rows"]}
    ctrl = {}
    for r in rows:
        k = r["tag"].replace("_tt80_", "_tt80_")
        if k in ref:
            ctrl[k] = {"Qrr_uC": (round(r["Qrr_uC"], 4), round(ref[k]["Qrr_uC"], 4)),
                       "match": abs(r["Qrr_uC"] - ref[k]["Qrr_uC"]) < 1e-3}
    c8 = {}
    for tt in ("25", "80", "160", "200", "240", "280"):
        rr = [r for r in rows if r["model"] == "IPW60R016CM8_L1" and (r["tt"] or "25e-9").startswith(tt)]
        q, t = interp_100(rr)
        c8[tt] = {"Qrr_at_100Apus_uC": q, "trr_ns": t}
    pts = sorted((int(k), v["Qrr_at_100Apus_uC"]) for k, v in c8.items() if v["Qrr_at_100Apus_uC"])
    tt_max = None
    for (t0, q0), (t1, q1) in zip(pts, pts[1:]):
        if q0 <= 2.31 <= q1:
            tt_max = t0 + (2.31 - q0) * (t1 - t0) / (q1 - q0)
    tt_typ = None
    for (t0, q0), (t1, q1) in zip(pts, pts[1:]):
        if q0 <= 1.54 <= q1:
            tt_typ = t0 + (1.54 - q0) * (t1 - t0) / (q1 - q0)
    cm8 = {}
    for tt in ("25", "90", "150", "200", "250"):
        rr = [r for r in wrows if r["model"].startswith("cm8_") and not r["aborted"] and (r["tt"] or "25") == tt]
        q, t = interp_100(rr)
        cm8[tt] = {"Qrr_at_100Apus_uC": q, "trr_ns": t}
    pts = sorted((int(k), v["Qrr_at_100Apus_uC"]) for k, v in cm8.items() if v["Qrr_at_100Apus_uC"])
    cm8_tt = {}
    for target in (1.54, 2.31):
        for (t0, q0), (t1, q1) in zip(pts, pts[1:]):
            if q0 <= target <= q1:
                cm8_tt[str(target)] = t0 + (target - q0) * (t1 - t0) / (q1 - q0)
    out = {"controls_vs_gn_qrr_json": ctrl, "cm8_650_qrr_vs_tt": cm8, "cm8_650_tt_for_typ_max_ns": cm8_tt,
           "wrapped_rows": wrows, "controls_pass": all(v["match"] for v in ctrl.values()),
           "c8_qrr_vs_tt": c8, "c8_tt_for_typ_1p54uC_ns": tt_typ, "c8_tt_for_max_2p31uC_ns": tt_max,
           "datasheet": "IPW65R018CM8 Rev 2.1 Table 7: Qrr 1.54 / 2.31 uC typ / max, trr 180 / 225 ns (400 V, 29.7 A, 100 A/us, 25 C)",
           "rows": rows}
    (C55 / "results").mkdir(exist_ok=True)
    (C55 / "results/qrr.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()
