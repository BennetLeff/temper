#!/usr/bin/env python3 -I
"""Touch current and conducted EMI for the as-built stage-38 board (candidate 23), on the co-design study's cores.

    python3 -I s38_leakage_emi.py [--procs 4] [--json OUT]

Re-runs the leakage x EMI co-design evaluation (validation-results/07-conducted-emi/leakage/co-design-2026-10-15:
leakage_core.py, emi_core.py, hf_touch.py, candidates.py, unchanged) for exactly the stage-38 system:
  board:   PS1 deleted; PS2 = MEAN WELL MPM-20-24; L1 = TDK B82726S2203A020 1.6 mH (kept, README section 2);
           C3 / C4 = 2.2 nF Y1 per line (unchanged);
  chassis: PS3 = MEAN WELL MPM-65-15ST (controller request, addendum item 6);
  D-22 inlet module: its four Y caps removed, its CM choke TDK 1.6 mH -> KEMET SCF31X-220-2R1A011JH 5.68 mH
           (DECISIONS 47 items 4 / 5; off-board, modelled here only).
That is the co-design's filter "B2.2 module Y removed, board 2.2 nF, module choke NC5.68" with supply set S4.

Outputs (all solved here, nothing reused from the study's cached results):
  * DESIGN touch current (committed rule: every Y +20 %, coil 31 pF +20 %, 132 V 60 Hz, supplies at datasheet max
    scaled x V/V_test x 60/50), its margin to the 0.25 mA portable 50 % budget, and the study's sanity sweep;
  * EMI: the s19b compliance set (nominal: 6 configs at 0.5 kHz; 19 sensitivities over 3 configs at 1 kHz) and the
    INFO earthed-pan case; the minimum over the 20 compliance scenarios is the "s19b compliance minimum"; plus the
    temper-8d split-R coil variant (RIN) as information;
  * HF (35-60 kHz) touch-current estimate (hf_touch.py) with the study's tolerance corners.
Controls (exit 1 if any fails): the s35 as-built supplies + committed filter reproduce the committed DESIGN row
(0.9741 mA); E00 (committed filter) reproduces the committed s19b nominal minimum (10.479334 dB) and sensitivity
minimum (6.5028 dB); the stage-38 numbers equal the co-design study's committed values for the same candidate.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = "1"

import json
import math
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]                                   # zapote/power-stage-120v
CODESIGN = UNIT / "validation-results/07-conducted-emi/leakage/co-design-2026-10-15"
sys.path.insert(0, str(CODESIGN))

import candidates as C  # noqa: E402
import leakage_core as L  # noqa: E402

S38_FILTER = "B2.2 module Y removed, board 2.2 nF, module choke NC5.68"
S38_SUPPLIES = ["MPM-20-24", "MPM-65-15ST"]          # PS2 (board), PS3 (chassis); PS1 deleted
S35_SUPPLIES = C.AS_BUILT                            # IRM-20-15, IRM-20-24, IRM-60-15ST
E00 = "E00 baseline (board 2.2 + module 4.7+2.2)"
PROCS = int(sys.argv[sys.argv.index("--procs") + 1]) if "--procs" in sys.argv else 4
OUT = Path(sys.argv[sys.argv.index("--json") + 1]) if "--json" in sys.argv else HERE.parent / "results/s38_leakage_emi.json"
FAIL = []


def check(name, ok, detail):
    print(f"  [{'OK ' if ok else 'BAD'}] {name}: {detail}")
    if not ok:
        FAIL.append(name)


def _eval(job):
    import emi_core as E
    name, over = job
    cm, nom = E.nominal_inputs()
    t = time.time()
    r = E.evaluate(over, nom, cm, full=True, info=True)
    r["seconds"] = time.time() - t
    return name, r


def main():
    t0 = time.time()
    filters = C.filters()
    f38 = filters[S38_FILTER]
    assert f38["l1"] == "TDK1.6" and f38["mod"] == "NC5.68" and f38["y_board"] == 2.2 and f38["y_module"] == 0

    print("== 1. touch current (committed DESIGN rule)")
    committed = json.loads((UNIT / "validation-results/07-conducted-emi/leakage/co-design-2026-10-15/repo_copies/"
                                   "leakage_result_committed.json").read_text())
    want = [r for r in committed["results"] if r["label"].startswith("DESIGN")][0]["governing_touch_mA"]
    t35 = L.touch(2.2, 6.9, S35_SUPPLIES)
    check("s35 as built reproduces the committed DESIGN row", abs(t35 - want) < 1e-12, f"{t35:.4f} mA (committed {want:.4f})")
    t38 = L.touch(f38["y_board"], f38["y_module"], S38_SUPPLIES)
    terms = {"Y (board 2.2 nF/line, +20 %)": f38["y_board"] * L.MA_PER_NF, "coil 31 pF (+20 %)": L.COIL_MA,
             **{f"{x} (datasheet max)": L.supply_ma(x) for x in S38_SUPPLIES}}
    for k, v in terms.items():
        print(f"     {k:34s} {v:.4f} mA")
    print(f"  s38 DESIGN touch current {t38:.4f} mA; budget 0.25 mA (portable 0.5 mA, 50 %): margin {(0.25 - t38) * 1e3:+.1f} uA")
    verd = L.verdicts(t38)
    san = {}
    for v in (120.0, 127.0, 132.0, 134.6):
        for ff in (1.0, 1.2):
            for tol in (0.10, 0.20):
                for coil in (31e-12, 51e-12):
                    ty = L.lb.i_ma(2.2e-9 * (1 + tol), v) + L.lb.i_ma(coil * 1.2, v)
                    ts = sum(L.SUPPLIES[x][0] * (v / L.SUPPLIES[x][1]) * ff for x in S38_SUPPLIES)
                    san[f"V{v}_ff{ff}_tol{tol}_coil{coil * 1e12:.0f}pF"] = ty + ts
    worst_key = max(san, key=san.get)
    sup = sum(L.supply_ma(x) for x in S38_SUPPLIES)
    flips = {"extra_Y_nF_per_line_to_fail": (0.25 - t38) / L.MA_PER_NF,
             "supply_scale_factor_to_fail": (0.25 - (t38 - sup)) / sup}
    print(f"  sweep worst {san[worst_key]:.4f} mA at {worst_key}; fails with +{flips['extra_Y_nF_per_line_to_fail']:.2f} nF/line "
          f"or supplies x{flips['supply_scale_factor_to_fail']:.3f}")

    print("\n== 2. EMI (s19b model, full compliance set): E00 control and the s38 filter")
    import emi_core as E
    E.nominal_inputs()
    jobs = [(E00, filters[E00]["over"]), (S38_FILTER, f38["over"]), (S38_FILTER + " | RIN", {**f38["over"], "RIN": True})]
    res = {}
    with Pool(min(PROCS, 4)) as p:
        for name, r in p.imap_unordered(_eval, jobs):
            res[name] = r
            print(f"  {name:70s} nominal {r['nominal']['margin_dB']:6.2f}  min {r['min_dB']:6.2f} [{r['min_case']}]  "
                  f"({r['seconds']:.0f} s)", flush=True)
    s19 = json.loads((CODESIGN / "repo_copies/s19b_results_committed.json").read_text())
    e0 = res[E00]
    check("E00 nominal = committed s19b nominal_min_margin_dB",
          abs(e0["nominal"]["margin_dB"] - s19["verdict"]["nominal_min_margin_dB"]) < 1e-9,
          f"{e0['nominal']['margin_dB']:.6f} dB")
    sm0 = min(v["margin_dB"] for k, v in e0["sens"].items() if not k.startswith("INFO"))
    check("E00 sensitivity minimum = committed s19b", abs(sm0 - s19["verdict"]["sensitivity_min_margin_all_dB"]) < 1e-9,
          f"{sm0:.4f} dB")
    cs = json.loads((CODESIGN / "results/summary.json").read_text())["emi_per_filter"][S38_FILTER]
    r38 = res[S38_FILTER]
    check("s38 filter = the co-design study's committed numbers (same model, solved again here)",
          abs(r38["min_dB"] - cs["min"]) < 1e-9 and abs(r38["nominal"]["margin_dB"] - cs["nominal"]) < 1e-9,
          f"min {r38['min_dB']:.4f} / nominal {r38['nominal']['margin_dB']:.4f} dB (study {cs['min']:.4f} / {cs['nominal']:.4f})")
    per = {"nominal": r38["nominal"]["margin_dB"], **{k: v["margin_dB"] for k, v in r38["sens"].items()}}
    for k, v in per.items():
        e = e0["nominal"]["margin_dB"] if k == "nominal" else e0["sens"][k]["margin_dB"]
        print(f"     {k:48s} {v:7.2f} dB   (s35 / E00 {e:6.2f})")

    print("\n== 3. HF touch-current estimate (hf_touch.py; outside the committed rule)")
    import hf_touch as HT
    cmn, nomn = E.nominal_inputs()
    pr = {**E.m.BASE, **nomn, **f38["over"]}
    corners = {"none": {}, "chokes -30 % (L1 + module)": {"LCM": pr["LCM"] * 0.7, "LCMADD": pr["LCMADD"] * 0.7},
               "module choke -30 %": {"LCMADD": pr["LCMADD"] * 0.7}, "module choke +50 %": {"LCMADD": pr["LCMADD"] * 1.5},
               "Y -20 %": {"CY": pr["CY"] * 0.8}, "Y +20 %": {"CY": pr["CY"] * 1.2},
               "coil + board 51 pF": {"CCOILA": 25.7e-12, "CCOILB": 25.3e-12}}
    hf = {}
    for cn, ov in corners.items():
        r = HT.hf_touch({**f38["over"], **ov}, nomn)
        w = {k: v["weighted_mA"] for k, v in r.items()}
        hf[cn] = {"weighted_mA": w, "rss_iec60990_mA": math.hypot(t38, w["lisn_mains_iec60990"]),
                  "rss_ul_style_mA": math.hypot(t38, w["lisn_mains_ul101"])}
        print(f"  {cn:28s} IEC 60990 {w['lisn_mains_iec60990']:.4f}  UL-style {w['lisn_mains_ul101']:.4f} mA -> RSS "
              f"{hf[cn]['rss_iec60990_mA']:.4f} / {hf[cn]['rss_ul_style_mA']:.4f} mA")

    out = dict(
        system={"board": "PS1 deleted; PS2 MPM-20-24; L1 TDK B82726S2203A020 1.6 mH; C3/C4 2.2 nF",
                "chassis": "PS3 MPM-65-15ST", "d22_module": "Y caps removed; CM choke SCF31X-220-2R1A011JH 5.68 mH (1 % DM leakage assumed)",
                "codesign_filter": S38_FILTER, "supplies_charged": S38_SUPPLIES},
        touch={"design_mA": t38, "terms_mA": terms, "budget_mA": 0.25, "margin_uA": (0.25 - t38) * 1e3, "verdicts": verd,
               "pe_conductor_mA_pe_intact": 2 * t38, "sweep": san, "sweep_worst": {"key": worst_key, "mA": san[worst_key]},
               "flip_points": flips, "s35_design_mA": t35},
        emi={"s38": {"nominal_dB": r38["nominal"]["margin_dB"], "compliance_min_dB": r38["min_dB"], "min_case": r38["min_case"],
                     "nominal_worst": r38["nominal"], "per_scenario_dB": per,
                     "info_pan_earthed_dB": r38["sens"]["INFO_pan_earthed_91pF"]["margin_dB"]},
             "s38_rin": {"nominal_dB": res[S38_FILTER + " | RIN"]["nominal"]["margin_dB"],
                         "compliance_min_dB": res[S38_FILTER + " | RIN"]["min_dB"], "min_case": res[S38_FILTER + " | RIN"]["min_case"]},
             "s35_E00": {"nominal_dB": e0["nominal"]["margin_dB"], "compliance_min_dB": e0["min_dB"], "min_case": e0["min_case"]}},
        hf_touch_estimate=hf,
        sources={"cores": "validation-results/07-conducted-emi/leakage/co-design-2026-10-15/{leakage_core,emi_core,hf_touch,candidates}.py",
                 "supplies": {k: L.SUPPLIES[k][2] for k in S38_SUPPLIES}, "module_choke": C.CHOKES["NC5.68"]["src"],
                 "l1": C.CHOKES["TDK1.6"]["src"]},
        controls_failed=FAIL, runtime_s=round(time.time() - t0, 1))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n")
    print(f"\nwrote {OUT}  ({time.time() - t0:.0f} s); CONTROLS: {'ALL OK' if not FAIL else FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
