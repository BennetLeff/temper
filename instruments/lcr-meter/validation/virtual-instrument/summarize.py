#!/usr/bin/env python3
"""Reduce the Monte Carlo CSVs to target quantities, statistics and verdicts.

Proposed targets (README section 1).  Metric per target and frequency:
    E = |bias| + 2 * sigma_total     (all boards, calibrations and repeats)
Verdict: meets   if E(typical) <= T and E(worst-case corner) <= T
         marginal if E(typical) <= T <  E(corner)
         fails   if E(typical) >  T
Spur aliasing (spur_alias.py) is a deterministic bound reported beside the verdict, not inside E.

    summarize.py -> results/summary.json, results/targets.csv, results/whatif.csv, results/leadmove.csv
"""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

import vi_model as vm
from mc import F0_NOPAN, F0_PAN

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
COIL_F = (35000.0, 40000.0, 50000.0, 60000.0)

TARGETS = [
    # id, dut, freqs, quantity, tolerance, unit, basis
    ("coil_nopan_L", "coil_nopan", COIL_F, "L", 0.01, "rel",
     "TANK_COIL_SPECIFICATION §2 equipment: LCR meter >= 1 % at 30-80 uH; row 2 flatness +/-3 % over 20-60 kHz"),
    ("coil_nopan_R", "coil_nopan", COIL_F, "R", 0.020, "ohm",
     "Row 5 curve 0.132/0.193/0.241 ohm at 20/40/60 kHz: +/-10 % of the 40 kHz limit decides accept/reject"),
    ("coil_pan_L", "coil_pan", COIL_F, "L", 0.005, "rel",
     "Row 3 floor 41.5 uH; a nominal coil reads 41.95 uH, 1.1 % above it, so 0.5 % keeps the decision"),
    ("coil_pan_R", "coil_pan", COIL_F, "R", 0.05, "rel",
     "Pan-reflected R sets delivered power; coil_mc.rs pan-class r40 bands are 30-50 % wide"),
    ("coil_pan_lowR_L", "coil_pan_lowR", COIL_F, "L", 0.005, "rel", "As coil_pan_L, low-R pan class"),
    ("coil_pan_lowR_R", "coil_pan_lowR", COIL_F, "R", 0.05, "rel", "As coil_pan_R, lowest-R pan class (worst case)"),
    ("cap100n_C", "cap100n", COIL_F, "C", 0.01, "rel",
     "Measured C replaces the +/-10 % (K) assumption in the f_res floor (C_worst = 0.45 uF); 1 % C = 0.5 % f_res"),
    ("cap100n_tand", "cap100n", COIL_F, "tand", 1e-3, "abs",
     "Gross-fault screen only (PP film <~1e-3, X7R ~2.5e-2); milliohm ESR is not claimed"),
    ("bank500n_C", "bank500n", COIL_F, "C", 0.01, "rel", "As cap100n_C, five-capacitor bank"),
    ("bank500n_tand", "bank500n", COIL_F, "tand", 1e-3, "abs", "As cap100n_tand (1e-3 of 6.4 ohm = 6.4 mohm ESR)"),
    ("bus9u_C", "bus9u", (1000.0,), "C", 0.02, "rel", "Bus capacitance check at 1 kHz (film tolerance 5-10 %)"),
    ("tank_pan_f0", "tank_pan", (float(F0_PAN),), "f0", 0.005, "rel",
     "ZVS guard f >= 1.05 f_res: a 0.5 % f0 error is 10x inside the guard"),
    ("tank_pan_Q", "tank_pan", (float(F0_PAN),), "Q", 0.05, "rel", "Loaded tank Q (~4-14) sets current per volt"),
    ("tank_nopan_f0", "tank_nopan", (float(F0_NOPAN),), "f0", 0.005, "rel", "As tank_pan_f0, no pan"),
    ("tank_nopan_Q", "tank_nopan", (float(F0_NOPAN),), "Q", 0.10, "rel", "Unloaded tank Q (~90): coil/cap loss screen"),
]


def quantity(q, z, f, dut):
    w = 2 * math.pi * f
    if q == "L":
        return z.imag / w
    if q == "R":
        return z.real
    if q == "C":
        return -1 / (w * z.imag)
    if q == "tand":
        return z.real / abs(z.imag)
    raise KeyError(q)


def error(q, unit, zm, zt, f, dut):
    if q in ("f0", "Q"):
        d = vm.DUTS[dut]
        dxdf = (d.z(f * 1.0001).imag - d.z(f * 0.9999).imag) / (f * 0.0002)
        if q == "f0":
            return -(zm.imag - zt.imag) / dxdf / f
        return zt.real / zm.real - 1
    qm, qt = quantity(q, zm, f, dut), quantity(q, zt, f, dut)
    return (qm - qt) / qt if unit == "rel" else qm - qt


def load(name, use_host=True):
    rows = list(csv.DictReader(open(RES / f"mc_{name}.csv")))
    out = defaultdict(list)
    for r in rows:
        f = float(r["freq"])
        fa = vm.frequency_hz(vm.frequency_word(f))
        if use_host and r["host_re"]:
            zm = complex(float(r["host_re"]), float(r["host_im"]))
        else:
            zm = complex(float(r["meas_re"]), float(r["meas_im"]))
        zt = complex(float(r["true_re"]), float(r["true_im"]))
        out[(r["dut"], f)].append((int(r["board"]), int(r["cal"]), int(r["rep"]), zm, zt, fa, int(r["valid"])))
    return out


def stats(errs):
    e = np.array([x[3] for x in errs])
    groups = defaultdict(list)
    for b, c, r, v in errs:
        groups[(b, c)].append(v)
    within = [np.var(g, ddof=1) for g in groups.values() if len(g) > 1]
    cal_means = defaultdict(list)
    for (b, c), g in groups.items():
        cal_means[b].append(np.mean(g))
    between_cal = [np.var(m, ddof=1) for m in cal_means.values() if len(m) > 1]
    board_means = [np.mean(m) for m in cal_means.values()]
    bias = float(e.mean())
    sd = float(e.std(ddof=1)) if e.size > 1 else 0.0
    return dict(n=int(e.size), bias=bias, sd_total=sd,
                sd_repeat=float(math.sqrt(np.mean(within))) if within else None,
                sd_between_cal=float(math.sqrt(np.mean(between_cal))) if between_cal else None,
                sd_between_board=float(np.std(board_means, ddof=1)) if len(board_means) > 1 else None,
                E=abs(bias) + 2 * sd, max_abs=float(np.max(np.abs(e))))


def evaluate(data, tid):
    t = next(x for x in TARGETS if x[0] == tid)
    _, dut, freqs, q, tol, unit, _ = t
    per_f = {}
    for f in freqs:
        rows = data.get((dut, f), [])
        if not rows:
            continue
        errs = [(b, c, r, error(q, unit, zm, zt, fa, dut)) for b, c, r, zm, zt, fa, v in rows]
        s = stats(errs)
        s["invalid"] = sum(1 for x in rows if not x[6])
        per_f[f] = s
    worst_f = max(per_f, key=lambda f: per_f[f]["E"])
    return dict(target=tid, tolerance=tol, unit=unit, per_freq=per_f, worst_freq=worst_f,
                E=per_f[worst_f]["E"], ratio=per_f[worst_f]["E"] / tol)


def main():
    base = load("baseline")
    corner = load("corner")
    spur = json.loads((RES / "spur_alias.json").read_text())
    summary = dict(targets=[], whatif={}, leadmove={})
    with open(RES / "targets.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["target", "tolerance", "unit", "worst_freq_hz", "bias", "sd_repeat", "sd_between_cal",
                    "sd_between_board", "sd_total", "E_typical", "E_corner", "E_over_T_typ", "E_over_T_corner",
                    "spur_bound_60dBc", "spur_bound_80dBc", "verdict"])
        for t in TARGETS:
            ev = evaluate(base, t[0])
            ec = evaluate(corner, t[0])
            tol = t[4]
            verdict = "meets" if ev["E"] <= tol and ec["E"] <= tol else ("marginal" if ev["E"] <= tol else "fails")
            # spur bound in target units (worst over the target's frequencies, worst phase)
            sb = {}
            for lvl in (60, 80):
                worst = 0.0
                for s in spur:
                    if s["dut"] == t[1] and s["hz"] in t[2] and not s["boxcar"]:
                        z = complex(*s["z"])
                        dz = s[f"abs_z_ohm_at_{lvl}dBc"]
                        if t[3] == "L":
                            v = dz / abs(z.imag)
                        elif t[3] == "R":
                            v = dz if t[5] == "ohm" else dz / z.real
                        elif t[3] == "C":
                            v = dz / abs(z.imag)
                        elif t[3] == "tand":
                            v = dz / abs(z.imag)
                        elif t[3] == "f0":
                            d = vm.DUTS[t[1]]
                            f = s["hz"]
                            dxdf = (d.z(f * 1.0001).imag - d.z(f * 0.9999).imag) / (f * 0.0002)
                            v = dz / dxdf / f
                        else:
                            v = dz / z.real
                        worst = max(worst, v)
                sb[lvl] = worst
            pf = ev["per_freq"][ev["worst_freq"]]
            w.writerow([t[0], tol, t[5], ev["worst_freq"], f"{pf['bias']:.4g}", f"{pf['sd_repeat']:.3g}",
                        f"{pf['sd_between_cal']:.3g}", f"{pf['sd_between_board']:.3g}", f"{pf['sd_total']:.3g}",
                        f"{ev['E']:.4g}", f"{ec['E']:.4g}", f"{ev['ratio']:.3f}", f"{ec['ratio']:.3f}",
                        f"{sb[60]:.3g}", f"{sb[80]:.3g}", verdict])
            summary["targets"].append(dict(target=t[0], dut=t[1], quantity=t[3], tolerance=tol, unit=t[5], basis=t[6],
                                           typical=ev, corner=ec, spur_bound={"-60dBc": sb[60], "-80dBc": sb[80]},
                                           verdict=verdict))
    # check standard (host validate) and host-vs-replica agreement
    chk = [abs(complex(*map(float, (r["meas_re"], r["meas_im"]))) - 47) / 47
           for r in csv.DictReader(open(RES / "mc_baseline.csv")) if r["dut"] == "chk_standard"]
    hv = [r["host_validate"] for r in csv.DictReader(open(RES / "mc_baseline.csv")) if r["host_validate"]]
    agree = [abs(complex(float(r["host_re"]), float(r["host_im"])) - complex(float(r["meas_re"]), float(r["meas_im"])))
             / max(abs(complex(float(r["true_re"]), float(r["true_im"]))), 1e-9)
             for r in csv.DictReader(open(RES / "mc_baseline.csv")) if r["host_re"]]
    inval = [r for r in csv.DictReader(open(RES / "mc_baseline.csv")) if r["valid"] == "0"]
    summary["check47"] = dict(max_rel_error=max(chk), host_validate_pass=sum("PASS" in x for x in hv),
                              host_validate_total=len(hv))
    summary["host_vs_replica_max_rel"] = max(agree)
    summary["host_invalid_flags"] = sorted({(r["dut"], r["freq"]) for r in inval})
    # what-ifs: repeatability/noise-only total, perfect standards, nominal board
    wis = ["wi_base", "wi_r33", "wi_r33_20mA", "wi_gain2", "wi_again4", "wi_amp2", "wi_boxcar", "wi_gain2_boxcar",
           "wi_riso22", "wi_base_c200", "wi_riso22_c200"]
    with open(RES / "whatif.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["target", "tolerance"] + [f"{s}_E" for s in wis] + [f"{s}_ratio_vs_base" for s in wis[1:]])
        loaded = {s: load(s, use_host=False) for s in wis if (RES / f"mc_{s}.csv").exists()}
        for t in TARGETS:
            es = {s: evaluate(d, t[0])["E"] for s, d in loaded.items()}
            summary["whatif"][t[0]] = es
            w.writerow([t[0], t[4]] + [f"{es.get(s, float('nan')):.3g}" for s in wis] +
                       [f"{es['wi_base'] / es[s]:.2f}" if s in es else "" for s in wis[1:]])
    # lead move after calibration
    with open(RES / "leadmove.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        names = sorted(p.stem[3:] for p in RES.glob("mc_lm_*.csv"))
        w.writerow(["target", "tolerance"] + [f"{n}_bias" for n in names])
        loaded = {n: load(n, use_host=False) for n in names}
        for t in TARGETS:
            bs = {}
            for n, d in loaded.items():
                ev = evaluate(d, t[0])
                bs[n] = max((abs(v["bias"]) for v in ev["per_freq"].values()))
            summary["leadmove"][t[0]] = bs
            w.writerow([t[0], t[4]] + [f"{bs[n]:.3g}" for n in names])
    # analytic single-capture noise (noise_budget.py) vs MC repeatability (perfect standards, no contact R)
    import noise_budget as nb
    chk = []
    for scen, acq in (("wi_base", vm.Acq()), ("wi_boxcar", vm.Acq(boxcar=True))):
        d = load(scen, use_host=False)
        for t in TARGETS:
            ev = evaluate(d, t[0])
            for f, v in ev["per_freq"].items():
                r = nb.phasor_noise("base", vm.DUTS[t[1]], f, acq=acq)
                chk.append(dict(scenario=scen, target=t[0], freq=f, mc_sd_repeat=v["sd_repeat"],
                                analytic=nb.sigma_in_units(t[3], t[5], r, t[1], f)))
    with open(RES / "analytic_vs_mc.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(chk[0].keys()) + ["ratio"])
        w.writeheader()
        for c in chk:
            c["ratio"] = c["mc_sd_repeat"] / c["analytic"]
            w.writerow({k: (f"{v:.4g}" if isinstance(v, float) else v) for k, v in c.items()})
    rat = np.array([c["ratio"] for c in chk])
    summary["analytic_vs_mc_ratio"] = dict(n=len(rat), median=float(np.median(rat)), p5=float(np.percentile(rat, 5)),
                                           p95=float(np.percentile(rat, 95)))
    (RES / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(open(RES / "targets.csv").read())
    print(json.dumps({k: summary[k] for k in ("check47", "host_vs_replica_max_rel", "host_invalid_flags")}, indent=1))


if __name__ == "__main__":
    main()
