#!/usr/bin/env python3 -I
"""Leakage x conducted-EMI co-design study, native-21 120 V power board.  Regenerates every number in WRITEUP.md.

    python3 -I run_all.py [--procs N] [--reuse]

--reuse: load results/emi_candidates.json instead of re-solving the EMI candidates; the control candidate E00 (s19b
nominal) and every other control are always re-solved.
Full run: ~15-20 min with 5 processes (each EMI candidate = 1 nominal sweep over 6 configs at 0.5 kHz + 19 sensitivities
over 3 configs at 1 kHz + 1 INFO case, ~1,400 MNA solves).
Exit 1 if any control fails.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = "1"

import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
RES = HERE / "results"
RES.mkdir(exist_ok=True)
REPO_VR = Path(__file__).resolve().parents[3]   # validation-results (committed copy, DECISIONS 47)

import candidates as C  # noqa: E402
import leakage_core as L  # noqa: E402

PROCS = int(sys.argv[sys.argv.index("--procs") + 1]) if "--procs" in sys.argv else 5
REUSE = "--reuse" in sys.argv
FAIL = []


def check(name, ok, detail):
    print(f"  [{'OK ' if ok else 'BAD'}] {name}: {detail}")
    if not ok:
        FAIL.append(name)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ===================================================================================== 0. provenance
def manifest():
    pairs = {"leakage_budget.py": REPO_VR / "07-conducted-emi/leakage/leakage_budget.py",
             "leakage_result_committed.json": REPO_VR / "07-conducted-emi/leakage/result.json",
             "emi_s19b.py": REPO_VR / "07-conducted-emi/s19b/emi_s19b.py",
             "s19b_results_committed.json": REPO_VR / "07-conducted-emi/s19b/results.json"}
    out = {}
    print("\n== 0. repo copies (byte-identical to the read-only repo files)")
    for k, src in pairs.items():
        mine = sha(HERE / "repo_copies" / k)
        theirs = sha(src) if src.exists() else None
        out[k] = {"sha256": mine, "repo_path": str(src), "repo_sha256": theirs}
        check(f"copy {k}", theirs is None or mine == theirs, mine[:16] + ("" if theirs else " (repo not reachable)"))
    (HERE / "MANIFEST.json").write_text(json.dumps(out, indent=1) + "\n")
    return out


# ===================================================================================== 1. datasheet rows
def datasheets():
    """Re-read the leakage / value rows from the downloaded datasheets (pdftotext, page by page)."""
    print("\n== 1. datasheet rows (downloads/, pdftotext -layout)")
    dl = HERE / "downloads"
    exe = shutil.which("pdftotext")
    out = {}
    want = {
        "meanwell/IRM-20-SPEC.PDF": ["LEAKAGE CURRENT", "File Name"],
        "meanwell/IRM-60-SPEC.PDF": ["LEAKAGE CURRENT", "File Name", "Case No"],
        "meanwell/MPM-20-SPEC.PDF": ["LEAKAGE CURRENT", "Touch current was measured", "File Name", "Case No", "DIMENSION"],
        "meanwell/MPM-65-SPEC.PDF": ["LEAKAGE CURRENT", "Touch current was measured", "File Name", "Case No", "DIMENSION",
                                    "VOLTAGE RANGE", "SAFETY STANDARDS"],
        "meanwell/IRM-20-SPEC.PDF#case": ["Case No", "DIMENSION"],
        "murata/murata_RA_EGD08G.pdf": ["DE1E3RA102MA4BP01F", "DE1E3RA152MA4BP01F", "DE1E3RA222MA4BP01F", "DE1E3RA332MA4BP01F"],
        "kemet/SC-20-201.pdf": ["Inductance", "Rated Current", "DC Resistance", "Voltage AC", "Generated"],
        "kemet/SCF31X-220-2R1A011JH.pdf": ["Inductance", "Rated Current", "DC Resistance", "Voltage AC", "Generated"],
        "kemet/SCF39XV-200-Z2R1A012JH.pdf": ["Inductance", "Rated Current", "DC Resistance", "Voltage AC", "Generated"],
    }
    if not exe or not dl.exists():
        print("  (skipped: pdftotext or downloads/ missing; values are fixed in leakage_core.py / candidates.py)")
        return {"skipped": True}
    for key, pats in want.items():
        f = dl / key.split("#")[0]
        if not f.exists():
            out[key] = "missing"
            continue
        txt = subprocess.run([exe, "-layout", str(f), "-"], capture_output=True, text=True).stdout
        rows = []
        for pno, page in enumerate(txt.split("\f"), 1):
            for line in page.splitlines():
                s = " ".join(line.split())
                if any(p in s for p in pats):
                    rows.append(f"p.{pno}: {s[:170]}")
        out[key] = {"sha256_16": sha(f)[:16], "rows": rows[:14]}
        print(f"  {key}  sha256 {sha(f)[:16]}")
        for r in rows[:8]:
            print("     ", r)
    # assert the numbers used in leakage_core.SUPPLIES are what the files say
    def has(key, s):
        return isinstance(out.get(key), dict) and any(s in r for r in out[key]["rows"])
    check("IRM-20 < 0.25mA/277Vac", has("meanwell/IRM-20-SPEC.PDF", "< 0.25mA/277Vac"), "p.2")
    check("IRM-60 < 0.25mA/277Vac", has("meanwell/IRM-60-SPEC.PDF", "< 0.25mA/277Vac"), "p.2")
    check("MPM-20 <80uA/264VAC", has("meanwell/MPM-20-SPEC.PDF", "Touch current <80μA/264VAC"), "p.2")
    check("MPM-65 <100uA/264VAC", has("meanwell/MPM-65-SPEC.PDF", "Touch current <100μA/264VAC"), "p.2")
    check("MPM-65 same case as IRM-60 (Case No.IRM60)", has("meanwell/MPM-65-SPEC.PDF", "Case No.IRM60")
          and has("meanwell/IRM-60-SPEC.PDF", "Case No.IRM60"), "mechanical page")
    check("MPM-20 same case as IRM-20 (Case No.219A)", has("meanwell/MPM-20-SPEC.PDF", "Case No.219A")
          and has("meanwell/IRM-20-SPEC.PDF#case", "Case No.219A"), "mechanical page")
    (RES / "datasheet_check.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return out


# ===================================================================================== 2. leakage controls
def leakage_controls():
    print("\n== 2. leakage controls (committed leakage_budget.py rows)")
    lb = L.lb
    committed = json.loads((HERE / "repo_copies/leakage_result_committed.json").read_text())
    want = {r["label"]: r["governing_touch_mA"] for r in committed["results"]}
    design = lb.evaluate("DESIGN (datasheet-max supplies)", lb.build())
    typical = lb.evaluate("INFORMATIONAL (typical-measured supplies)", lb.build(supply_mode="typical"))
    ysplit = lb.evaluate("INFORMATIONAL (no module Y, board Y only, typical supplies)",
                         [i for i in lb.build(supply_mode="typical") if "module" not in i["name"]])
    control = lb.evaluate("CONTROL (+10 nF Y per line; must FAIL)", lb.build(extra_y_per_line_f=10e-9))
    c2 = lb.evaluate("CONTROL 2 (board-only variant + 10 nF Y per line; must FAIL)",
                     [i for i in lb.build(extra_y_per_line_f=10e-9, supply_mode="typical") if "module" not in i["name"]])
    rows = {}
    for r in (design, typical, ysplit, control, c2):
        d = abs(r["governing_touch_mA"] - want[r["label"]])
        rows[r["label"]] = {"repro_mA": r["governing_touch_mA"], "committed_mA": want[r["label"]], "verdict": r["verdict"]}
        check(r["label"], d < 1e-12, f"{r['governing_touch_mA']:.4f} mA (committed {want[r['label']]:.4f}) {r['verdict']}")
    # the parametrised model must give the same DESIGN number, and c29's / c23's published figures
    t0 = L.touch(2.2, 6.9, C.AS_BUILT)
    check("leakage_core DESIGN == committed", abs(t0 - want["DESIGN (datasheet-max supplies)"]) < 1e-12, f"{t0:.4f} mA")
    t1 = L.touch(2.2, 0, ["IRM-20-24", "IRM-60-15ST"])
    check("c23 + D-22 rev B (Y 2.2, PS1 deleted) = 0.419 (CONTROLLER-REQUEST.md)", abs(t1 - 0.419) < 6e-4, f"{t1:.4f}")
    t2 = L.touch(2.2, 0, C.AS_BUILT)
    check("D-22 rev B, PS1 fitted = 0.562 (CONTROLLER-REQUEST.md)", abs(t2 - 0.562) < 6e-4, f"{t2:.4f}")
    return rows


# ===================================================================================== 3. EMI controls + candidates
def _eval(job):
    import emi_core as E
    name, over = job
    cm, nom = E.nominal_inputs()
    t = time.time()
    r = E.evaluate(over, nom, cm, full=True, info=True)
    r["seconds"] = time.time() - t
    return name, r


def emi_all(filters):
    import emi_core as E
    E.nominal_inputs()  # cache cm/nominal (fringe Laplace) before the workers start
    path = RES / "emi_candidates.json"
    if REUSE and path.exists():
        res = json.loads(path.read_text())
        # the control candidate (s19b nominal) is always re-solved, so the EMI controls never run on cached numbers
        missing = [k for k in filters if k not in res or k.startswith("E00")]
    else:
        res, missing = {}, list(filters)
    if missing:
        print(f"\n== 3b. solving {len(missing)} EMI candidates on {PROCS} processes (full s19b compliance set each)")
        jobs = [(k, filters[k]["over"]) for k in missing]
        with Pool(PROCS) as p:
            for name, r in p.imap_unordered(_eval, jobs):
                res[name] = r
                print(f"  {name:78s} nominal {r['nominal']['margin_dB']:6.2f}  min {r['min_dB']:6.2f} "
                      f"[{r['min_case']}]  ({r['seconds']:.0f} s)", flush=True)
                path.write_text(json.dumps(res, indent=1, default=float) + "\n")
    return res


def emi_controls(res_e00):
    print("\n== 3a. EMI controls (committed s19b results.json)")
    s19 = json.loads((HERE / "repo_copies/s19b_results_committed.json").read_text())
    nom_c = s19["verdict"]["nominal_min_margin_dB"]
    check("s19b nominal min margin (scorecard emi_min_margin_dB)", abs(res_e00["nominal"]["margin_dB"] - nom_c) < 1e-9,
          f"{res_e00['nominal']['margin_dB']:.6f} dB (committed {nom_c:.6f})")
    worst = 0.0
    out = {}
    for sname, r in res_e00["sens"].items():
        if sname.startswith("INFO"):
            ref = s19["scenarios"][sname]
        else:
            ref = s19["scenarios"][sname]
        cm = min(v[b]["margin_dB"] for v in ref.values() for b in ("hi_150k_30M", "lo_9k_150k"))
        out[sname] = {"repro": r["margin_dB"], "committed": cm}
        worst = max(worst, abs(r["margin_dB"] - cm))
    check("all 19 compliance sensitivities + INFO pan-earthed reproduce s19b", worst < 1e-6, f"max |delta| {worst:.2e} dB")
    sm = min(v["margin_dB"] for k, v in res_e00["sens"].items() if not k.startswith("INFO"))
    check("s19b sensitivity minimum", abs(sm - s19["verdict"]["sensitivity_min_margin_all_dB"]) < 1e-9, f"{sm:.4f} dB")
    return {"nominal_dB": res_e00["nominal"]["margin_dB"], "sens_min_dB": sm, "per_scenario": out}


# ===================================================================================== 4. joint analysis
def joint(filters, emi, sups):
    rows = []
    for sn, s in sups.items():
        for fn, f in filters.items():
            t = L.touch(f["y_board"], f["y_module"], s["fitted"], s["counted"])
            fu, fp, fitems, coord = C.filter_delta(f)
            su = C.supply_cost(s["fitted"])
            sp = len(s["fitted"]) - len(C.AS_BUILT)
            unpriced = bool(f["shield"]) or bool(f["extra"])
            e = emi[fn]
            changes = list(s["changes"]) + fitems
            co = list(coord)
            if any("c23" in c for c in s["changes"]):
                co.append("controller (c23 J13 rail merge)")
            if any("MPM" in c for c in s["changes"]):
                co.append("certifier (MPM is ES/IEC 60601-1 + CSA 60601-1 listed, not UL 62368-1; '60335-1 by request')")
            if any("PS3" in c for c in s["changes"]):
                co.append("enclosure (PS3 bay: MPM-65 derating curve)")
            if not s["design_basis"]:
                co.append("certifier + bench (non-DESIGN basis)")
            rows.append(dict(supplies=sn, filter=fn, design_basis=s["design_basis"], touch_mA=t,
                             pass_portable_50=t <= 0.25 + 1e-12, pass_stationary_50=t <= 0.375 + 1e-12,
                             pass_portable_100=t <= 0.5 + 1e-12,
                             emi_nominal_dB=e["nominal"]["margin_dB"], emi_min_dB=e["min_dB"], emi_min_case=e["min_case"],
                             emi_pan_earthed_INFO_dB=e["sens"]["INFO_pan_earthed_91pF"]["margin_dB"],
                             emi_ok=e["min_dB"] >= 6.0, usd=fu + su, usd_unpriced_items=unpriced, parts=fp + sp,
                             n_changes=len(changes), changes=changes, coordination=sorted(set(co)),
                             y_total_nF=f["y_board"] + f["y_module"]))
    return rows


def pareto(rows):
    """Non-dominated set on (touch_mA min, emi_min_dB max, usd min), priced rows only."""
    pr = [r for r in rows if not r["usd_unpriced_items"]]
    front = []
    for r in pr:
        dom = False
        for q in pr:
            if q is r:
                continue
            if (q["touch_mA"] <= r["touch_mA"] + 1e-12 and q["emi_min_dB"] >= r["emi_min_dB"] - 1e-9 and q["usd"] <= r["usd"] + 1e-9
                    and (q["touch_mA"] < r["touch_mA"] - 1e-12 or q["emi_min_dB"] > r["emi_min_dB"] + 1e-9 or q["usd"] < r["usd"] - 1e-9)):
                dom = True
                break
        if not dom:
            front.append(r)
    return sorted(front, key=lambda r: (r["touch_mA"], -r["emi_min_dB"]))


def thermal():
    """Max ambient for each supply at the g06 supply_budget loads (supplies/result.json), from the datasheet derating
    curves read off the p.3 graphs (piecewise-linear; the MPM points are my reading of the plotted knees, +-2 C)."""
    curves = {
        "IRM-20 (repo basis)": None,  # repo numbers used as-is
        "MPM-20 12-24V": [(-30, 100), (55, 100), (60, 70), (70, 50), (85, 30)],   # MPM-20-SPEC 2024-10-30 p.3
        "MPM-65 5/12/15V": [(-30, 100), (50, 100), (55, 80), (70, 50), (80, 30)],  # MPM-65-SPEC 2024-10-30 p.3
    }

    def tmax(curve, pct):
        for (t0, p0), (t1, p1) in zip(curve, curve[1:]):
            if p1 <= pct <= p0 and p0 != p1:
                return t0 + (p0 - pct) / (p0 - p1) * (t1 - t0)
        return curve[-1][0] if pct <= curve[-1][1] else None

    sb = json.loads((REPO_VR / "11-candidates/g06-g08-g10-supplies-sense-io/supplies/result.json").read_text())
    out = {}
    for lab, w, rated_irm, mpm, rated_mpm in (
            ("PS2 @80 kHz", sb["PS2 @80 kHz (24 V, 21.6 W)"]["load_W"], 21.6, "MPM-20 12-24V", 21.6),
            ("PS3 now (blower)", sb["PS3 now: 39.7 W blower"]["load_W"], 60.0, "MPM-65 5/12/15V", 65.0),
            ("PS3 after c23 (blower + logic)", sb["PS3 after P1: 39.7 + 4.83 W"]["load_W"], 60.0, "MPM-65 5/12/15V", 65.0),
            ("PS1 (logic) if kept", sb["PS1 now: 4.83 W controller"]["load_W"], 21.0, "MPM-20 12-24V", 21.0)):
        irm_key = {"PS2 @80 kHz": "PS2 @80 kHz (24 V, 21.6 W)", "PS3 now (blower)": "PS3 now: 39.7 W blower",
                   "PS3 after c23 (blower + logic)": "PS3 after P1: 39.7 + 4.83 W",
                   "PS1 (logic) if kept": "PS1 now: 4.83 W controller"}[lab]
        pct = 100 * w / rated_mpm
        out[lab] = {"load_W": w, "IRM_pct": 100 * w / rated_irm, "IRM_max_ambient_C (repo)": sb[irm_key]["max_ambient_C"],
                    "MPM_pct": pct, "MPM_max_ambient_C (curve read)": tmax(curves[mpm], pct)}
    print("\n== 9b. supply thermal check (max ambient at the g06 loads; MPM from the p.3 derating curves)")
    for k, v in out.items():
        print(f"  {k:32s} {v['load_W']:5.2f} W  IRM {v['IRM_pct']:5.1f} % -> {v['IRM_max_ambient_C (repo)']:.1f} C   "
              f"MPM {v['MPM_pct']:5.1f} % -> {v['MPM_max_ambient_C (curve read)']:.1f} C")
    return out


def sanity(best_rows, sups, filters):
    """Assumption sweeps on candidate rows: voltage, frequency factor, Y tolerance, coil C, supply spec basis."""
    import leakage_core as LC
    lb = LC.lb
    out = {}
    for r in best_rows:
        f, s = filters[r["filter"]], sups[r["supplies"]]
        y = f["y_board"] + f["y_module"]
        cases = {}
        for v in (120.0, 127.0, 132.0, 134.6):
            for ff in (1.0, 1.2):
                for tol in (0.10, 0.20):
                    for coil in (31e-12, 51e-12):
                        ty = lb.i_ma(y * 1e-9 * (1 + tol), v) + lb.i_ma(coil * (1 + 0.2), v)
                        ts = sum(LC.SUPPLIES[x][0] * (v / LC.SUPPLIES[x][1]) * ff for x in s["counted"])
                        cases[f"V{v}_ff{ff}_tol{tol}_coil{coil*1e12:.0f}pF"] = ty + ts
        # flip points at the DESIGN basis (132 V, x1.2, +20 %, 31 pF)
        base = r["touch_mA"]
        per_sup = {x: LC.supply_ma(x) for x in s["counted"]}
        out[r["supplies"] + " | " + r["filter"]] = dict(
            touch_design_mA=base, margin_to_0p25_mA=0.25 - base,
            max_extra_Y_nF_before_fail=(0.25 - base) / LC.MA_PER_NF,
            supply_terms_mA=per_sup,
            supply_scale_factor_that_fails=(0.25 - (base - sum(per_sup.values()))) / max(sum(per_sup.values()), 1e-12),
            worst_case_in_sweep_mA=max(cases.values()), worst_case_key=max(cases, key=cases.get),
            sweep=cases)
    return out


# ===================================================================================== main
def main():
    t0 = time.time()
    manifest()
    ds = datasheets()
    lk = leakage_controls()
    filters = C.filters()
    emi = emi_all(filters)
    ec = emi_controls(emi["E00 baseline (board 2.2 + module 4.7+2.2)"])
    sups = C.supply_sets()

    print("\n== 4. Y ceiling per supply set (nominal nF per line, board + module, every Y at +20 %, 132 V, coil 31 pF)")
    ceil = {}
    for sn, s in sups.items():
        ceil[sn] = {k: L.y_ceiling_nF(lim, s["counted"], frac) for k, (lim, frac) in
                    {"portable 0.25 (50 %)": (0.5, 0.5), "stationary 0.375 (50 %)": (0.75, 0.5),
                     "portable 0.5 (100 %)": (0.5, 1.0), "stationary 0.75 (100 %)": (0.75, 1.0)}.items()}
        sup_ma = sum(L.supply_ma(x) for x in s["counted"])
        ceil[sn]["supplies_mA"] = sup_ma
        print(f"  {sn:66s} supplies {sup_ma:.4f} mA  ->  " +
              "  ".join(f"{k.split()[0][:4]}{k.split()[1]}: {v:6.2f}" for k, v in ceil[sn].items() if k != "supplies_mA"))

    rows = joint(filters, emi, sups)
    feas = [r for r in rows if r["pass_portable_50"] and r["emi_ok"]]
    feas_design = sorted([r for r in feas if r["design_basis"]],
                         key=lambda r: (r["n_changes"], r["usd_unpriced_items"], r["usd"], -r["emi_min_dB"]))
    front = pareto([r for r in rows if r["design_basis"]])

    print("\n== 5. EMI per filter (full s19b compliance set; min over nominal + 19 sensitivities)")
    for fn, f in filters.items():
        e = emi[fn]
        print(f"  {fn:84s} Y {f['y_board'] + f['y_module']:4.1f}  nom {e['nominal']['margin_dB']:6.2f}  "
              f"min {e['min_dB']:6.2f} [{e['min_case']}]  panE(INFO) {e['sens']['INFO_pan_earthed_91pF']['margin_dB']:6.2f}")

    print(f"\n== 6. feasible on the DESIGN basis (touch <= 0.25 mA AND EMI min >= 6 dB): {len(feas_design)} of "
          f"{sum(r['design_basis'] for r in rows)}")
    for r in feas_design[:25]:
        print(f"  {r['touch_mA']:.4f} mA  EMI {r['emi_min_dB']:5.2f} dB  ${r['usd']:+7.2f}{'+?' if r['usd_unpriced_items'] else ''} "
              f"parts {r['parts']:+d}  n={r['n_changes']}  {r['supplies']}  ||  {r['filter']}")
    print("\n== 7. non-DESIGN-basis variants that pass (need bench + certifier)")
    for r in sorted([r for r in feas if not r["design_basis"]], key=lambda r: (r["n_changes"], r["usd"]))[:12]:
        print(f"  {r['touch_mA']:.4f} mA  EMI {r['emi_min_dB']:5.2f} dB  ${r['usd']:+7.2f}  n={r['n_changes']}  "
              f"{r['supplies']}  ||  {r['filter']}")
    print("\n== 8. Pareto frontier (DESIGN basis, priced rows; touch mA, EMI min dB, USD)")
    for r in front:
        print(f"  {r['touch_mA']:.4f}  {r['emi_min_dB']:6.2f}  ${r['usd']:+7.2f}  parts {r['parts']:+d}  "
              f"{'P' if r['pass_portable_50'] else '-'}{'S' if r['pass_stationary_50'] else '-'}  {r['supplies']} || {r['filter']}")

    # smallest DESIGN-basis change set per limit criterion (EMI min >= 6 dB in every compliance scenario)
    crit = {"portable 0.5 mA, 50 % rule (0.25)": 0.25, "stationary 0.75 mA, 50 % rule (0.375)": 0.375,
            "portable 0.5 mA, 100 % (0.5)": 0.5, "stationary 0.75 mA, 100 % (0.75)": 0.75}
    per_crit = {}
    print("\n== 8b. smallest DESIGN-basis change set per limit criterion (EMI >= 6 dB everywhere; priced first)")
    for cn, lim in crit.items():
        ok = sorted([r for r in rows if r["design_basis"] and r["emi_ok"] and r["touch_mA"] <= lim + 1e-12],
                    key=lambda r: (r["n_changes"], r["usd_unpriced_items"], r["usd"], r["touch_mA"]))
        per_crit[cn] = ok[:3]
        for r in ok[:3]:
            print(f"  {cn:40s} {r['touch_mA']:.4f} mA  EMI {r['emi_min_dB']:5.2f}  ${r['usd']:+6.2f}  n={r['n_changes']}  "
                  f"{r['supplies']} || {r['filter']}")

    # per-scenario breakdown for the recommended / runner-up sets
    pick = feas_design[:4]
    rec = feas_design[0]
    print(f"\n== 8c. EMI per compliance scenario, recommended set: {rec['filter']}  (vs committed design E00)")
    e_r, e_0 = emi[rec["filter"]], emi["E00 baseline (board 2.2 + module 4.7+2.2)"]
    print(f"  {'nominal (6 configs, 0.5 kHz)':48s} {e_r['nominal']['margin_dB']:7.2f}  (E00 {e_0['nominal']['margin_dB']:6.2f})  "
          f"{e_r['nominal']['band']} {e_r['nominal']['f_hz']/1e3:.0f} kHz {e_r['nominal']['cfg']}")
    for k, v in e_r["sens"].items():
        print(f"  {k:48s} {v['margin_dB']:7.2f}  (E00 {e_0['sens'][k]['margin_dB']:6.2f})  {v['band']} {v['f_hz']/1e3:.0f} kHz {v['cfg']}")
    breakdown = {}
    for r in pick:
        e = emi[r["filter"]]
        breakdown[r["supplies"] + " | " + r["filter"]] = {
            "nominal": e["nominal"], **{k: v for k, v in e["sens"].items()}}
    san = sanity(pick, sups, filters)
    print("\n== 9. sanity sweeps on the top feasible sets")
    for k, v in san.items():
        print(f"  {k}\n     DESIGN {v['touch_design_mA']:.4f} mA, margin {v['margin_to_0p25_mA']*1e3:.1f} uA "
              f"(= {v['max_extra_Y_nF_before_fail']:.2f} nF more Y), supplies fail if x{v['supply_scale_factor_that_fails']:.2f}; "
              f"worst in sweep {v['worst_case_in_sweep_mA']:.4f} mA at {v['worst_case_key']}")

    th = thermal()

    # switching-frequency touch current (estimate outside the committed model), quadrature-added to the 60 Hz DESIGN value
    import emi_core as EC
    import hf_touch as HT
    cmn, nomn = EC.nominal_inputs()
    print("\n== 10. switching-frequency touch current estimate (hf_touch.py; NOT part of the committed rule)")
    mc = HT.control_meter()
    check("meter networks vs closed form", max(abs(list(r.values())[1] - r["closed_form"]) for r in mc) < 1e-9,
          ", ".join(f"{r['f_hz']:.0f} Hz {list(r.keys())[1]} {list(r.values())[1]:.4f}" for r in mc))
    hf = {}
    for fn in dict.fromkeys(["E00 baseline (board 2.2 + module 4.7+2.2)"] + [r["filter"] for r in feas_design[:6]]):
        hf[fn] = HT.hf_touch(filters[fn]["over"], nomn)
        for k, v in hf[fn].items():
            print(f"  {fn[:70]:70s} {k:22s} {v['weighted_mA']:.4f} mA (unweighted {v['unweighted_mA']:.3f}) "
                  f"@ fs {v['fs_hz']/1e3:.0f} kHz {v['cfg']}")
    # tolerance corners of the HF estimate (the s19b sensitivity definitions) on the recommended filter and the
    # robust variant (L1 also -> NC5.68)
    ROBUST = "B2.2 module Y removed, board 2.2 nF, L1 NC5.68, module NC5.68"
    hf_corners = {}
    for tag, fname in (("recommended", rec["filter"]), ("robust", ROBUST)):
        pr = {**EC.m.BASE, **nomn, **filters[fname]["over"]}
        corners = {"none": {}, "chokes -30 % (L1 + module)": {"LCM": pr["LCM"] * 0.7, "LCMADD": pr["LCMADD"] * 0.7},
                   "module choke -30 %": {"LCMADD": pr["LCMADD"] * 0.7},
                   "module choke +50 %": {"LCMADD": pr["LCMADD"] * 1.5},
                   "Y -20 %": {"CY": pr["CY"] * 0.8}, "Y +20 %": {"CY": pr["CY"] * 1.2},
                   "coil + board 51 pF": {"CCOILA": 25.7e-12, "CCOILB": 25.3e-12}}
        hf_corners[tag] = {"filter": fname}
        for cn_, ov in corners.items():
            hf_corners[tag][cn_] = HT.hf_touch({**filters[fname]["over"], **ov}, nomn)
            w = {k: v["weighted_mA"] for k, v in hf_corners[tag][cn_].items()}
            print(f"  {tag:11s} {cn_:28s} IEC60990 {w['lisn_mains_iec60990']:.4f}  UL-style {w['lisn_mains_ul101']:.4f} mA  "
                  f"-> RSS with {rec['touch_mA']:.4f}: {math.hypot(rec['touch_mA'], w['lisn_mains_iec60990']):.4f} / "
                  f"{math.hypot(rec['touch_mA'], w['lisn_mains_ul101']):.4f} mA (crest; x0.71 for a line-cycle RMS: "
                  f"{math.hypot(rec['touch_mA'], 0.7071 * w['lisn_mains_ul101']):.4f})")
    hf["_tolerance_corners"] = hf_corners
    for r in feas_design[:6]:
        w = max(v["weighted_mA"] for v in hf[r["filter"]].values())
        r["touch_with_hf_rss_mA"] = math.hypot(r["touch_mA"], w)
        print(f"  RSS 60 Hz DESIGN {r['touch_mA']:.4f} + worst meter HF {w:.4f} -> {r['touch_with_hf_rss_mA']:.4f} mA  "
              f"[{r['supplies'][:40]} | {r['filter'][:50]}]")
    # ---- 11. temper-8d claim: pan-reflected R inside the winding, coil-end C at the physical coil terminals (RIN)
    print("\n== 11. tank variant RIN (R/2 + L + R/2, coil C at the coil terminals; temper-8d emi_split_cap.py)")
    tr0 = EC._transfers({**EC.m.BASE, **nomn, "CCOILA": 46.2e-12, "CCOILB": 45.2e-12, "RIN": True}, True, EC.REP3, EC.FS_SENS)
    pe_rin = EC._worst(tr0, EC.REP3, EC.FS_SENS)["margin_dB"]
    check("temper-8d T1 reproduced: E00 pan earthed 91 pF with RIN = 8.37 dB", abs(pe_rin - 8.37) < 0.006, f"{pe_rin:.3f} dB")
    rin_set = ["E00 baseline (board 2.2 + module 4.7+2.2)", rec["filter"], ROBUST,
               "B2.2 module Y removed, board 2.2 nF, module choke NC3.6",
               "B2.2 module Y removed, board 2.2 nF, module choke NC5.68lk0.3",
               "B1.5 module Y removed, board 1.5 nF, module choke NC5.68",
               "B1.5 module Y removed, board 1.5 nF, L1 NC5.68, module NC5.68",
               "B2.2 module Y removed, board 2.2 nF, module choke TDK1.6"]
    path = RES / "emi_rin.json"
    emi_rin = json.loads(path.read_text()) if (REUSE and path.exists()) else {}
    todo = [k for k in rin_set if k not in emi_rin]
    if todo:
        with Pool(PROCS) as p:
            for name, r in p.imap_unordered(_eval, [(k, {**filters[k]["over"], "RIN": True}) for k in todo]):
                emi_rin[name] = r
                path.write_text(json.dumps(emi_rin, indent=1, default=float) + "\n")
    for k in rin_set:
        a, b = emi[k], emi_rin[k]
        print(f"  {k[:66]:66s} min {a['min_dB']:6.2f} [{a['min_case'][:28]}] -> RIN {b['min_dB']:6.2f} [{b['min_case'][:28]}]  "
              f"nom {a['nominal']['margin_dB']:5.2f}->{b['nominal']['margin_dB']:5.2f}  panE {a['sens']['INFO_pan_earthed_91pF']['margin_dB']:5.2f}"
              f"->{b['sens']['INFO_pan_earthed_91pF']['margin_dB']:5.2f}")
    hf_rin = {}
    for tag, fname in (("recommended", rec["filter"]), ("robust", ROBUST)):
        pr = {**EC.m.BASE, **nomn, **filters[fname]["over"]}
        for cn_, ov in {"none": {}, "chokes -30 % (L1 + module)": {"LCM": pr["LCM"] * 0.7, "LCMADD": pr["LCMADD"] * 0.7}}.items():
            r = HT.hf_touch({**filters[fname]["over"], **ov, "RIN": True}, nomn)
            hf_rin[f"{tag} | {cn_}"] = r
            w = {k: v["weighted_mA"] for k, v in r.items()}
            print(f"  HF touch RIN {tag:11s} {cn_:28s} IEC60990 {w['lisn_mains_iec60990']:.4f}  UL-style {w['lisn_mains_ul101']:.4f} mA")

    summary = dict(controls=dict(leakage=lk, emi=ec, meter=mc, failed=FAIL), datasheets=ds, y_ceiling_nF=ceil, thermal=th,
                   rin_variant=dict(pan_earthed_E00_dB=pe_rin, emi={k: dict(min=emi_rin[k]["min_dB"], min_case=emi_rin[k]["min_case"],
                                    nominal=emi_rin[k]["nominal"]["margin_dB"],
                                    per_scenario={kk: vv["margin_dB"] for kk, vv in emi_rin[k]["sens"].items()}) for k in rin_set},
                                    hf_touch=hf_rin),
                   hf_touch_estimate=hf,
                   emi_per_filter={fn: dict(y_total_nF=filters[fn]["y_board"] + filters[fn]["y_module"],
                                            nominal=emi[fn]["nominal"]["margin_dB"], min=emi[fn]["min_dB"],
                                            min_case=emi[fn]["min_case"],
                                            per_scenario={"nominal": emi[fn]["nominal"]["margin_dB"],
                                                          **{k: v["margin_dB"] for k, v in emi[fn]["sens"].items()}},
                                            src={"l1": C.CHOKES[filters[fn]["l1"]]["src"], "mod": C.CHOKES[filters[fn]["mod"]]["src"]})
                                    for fn in filters},
                   joint=rows, feasible_design_basis=feas_design, pareto_design_basis=front, smallest_set_per_criterion=per_crit,
                   recommended_breakdown=breakdown, sanity=san, supply_prices=C.SUPPLY_USD, supply_price_src=C.SUPPLY_USD_SRC,
                   choke_prices={k: {"usd": v[0], "src": v[1]} for k, v in C.CHOKE_USD.items()},
                   supplies_db={k: {"max_mA": v[0], "test_V": v[1], "src": v[2], "at_132V_mA": L.supply_ma(k)}
                                for k, v in L.SUPPLIES.items()},
                   runtime_s=time.time() - t0)
    import csv
    with open(RES / "joint.csv", "w", newline="") as fh:
        cols = ["supplies", "filter", "design_basis", "touch_mA", "pass_portable_50", "pass_stationary_50", "pass_portable_100",
                "emi_nominal_dB", "emi_min_dB", "emi_min_case", "emi_pan_earthed_INFO_dB", "usd", "usd_unpriced_items", "parts",
                "n_changes", "y_total_nF"]
        wr = csv.writer(fh)
        wr.writerow(cols)
        for r in rows:
            wr.writerow([round(r[c], 4) if isinstance(r[c], float) else r[c] for c in cols])
    (RES / "summary.json").write_text(json.dumps(summary, indent=1, default=float) + "\n")
    print(f"\nwrote {RES / 'summary.json'}  ({time.time() - t0:.0f} s)")
    print("CONTROLS:", "ALL OK" if not FAIL else f"FAILED {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
