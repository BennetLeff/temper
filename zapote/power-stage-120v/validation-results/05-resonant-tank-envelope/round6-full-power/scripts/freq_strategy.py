#!/usr/bin/env python3
"""Round 6, question 3: operating-frequency strategy at the tank ceiling. ASSUMED.

(a) P(f), I(f) for one pan at 120 V: the round-4/5 solver's 'lowest legal frequency' IS the maximum-power point
    under the RMS ceiling; any higher constant frequency delivers less. Also the bus voltage that a higher
    frequency would need to hold the ceiling current.
(b) The frequency lever that does work: a smaller bank (higher f_res -> the ceiling is met at a higher f,
    where pan R ~ f^0.6 is larger). FHA MC yield vs C_bank at 70/80/90 uH, 220 mm, 120 V; bank current
    capability on TDK p.57 for the arrangements that fit the slot.
(c) Line-synchronous frequency modulation (crest clipping): quasi-static FHA over the line half-cycle. The
    frequency is raised near the crest so that the tank PEAK stays at a target, and lowered elsewhere, so the
    line-cycle RMS rises toward the ceiling under a fixed peak limit (the 45 A firmware trip today). Costs:
    inlet power factor (the unsmoothed bus takes p(theta)/v(theta)) and a firmware feature. Validated against
    ngspice with a frequency-modulated deck (scripts/tank_fm.cir) on three cases.
(d) The firmware as written: one commissioned fixed frequency for every pan, RMS > 23.1 A and peak > 45 A
    latch faults. Best single frequency and its yield.

Writes outputs/fstrat-*.csv / .json.
"""
from __future__ import annotations

import csv
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

import common6 as M
import fha6 as F

OUT = M.OUT
CAL = json.loads((OUT / "calibration6.json").read_text())
KP, KI = CAL["kp_median"], CAL["ki_median"]
KA, KB, KR = CAL["kpk_fit"]["a"], CAL["kpk_fit"]["b_per_Q"], CAL["kpk_fit"]["resid_max"]
NTH = 96                                   # line-phase points over the half cycle (midpoint rule)
TH = (np.arange(NTH) + 0.5) / NTH * np.pi
S = np.sin(TH)


def write(name, rows):
    with open(OUT / name, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def nominal(pan_name, lfree=70, c_uf=0.50, pan_d=220, which="nom"):
    fk, fr = M.coupling(M.GEOM, pan_d)
    p = M.pan_params(M.B4.PANS[pan_name], which, M.L_INSTALLED[lfree], fk, fr)
    return {"L0": np.array([p["L0U"]]), "kl": np.array([p["KL40"]]), "r40": np.array([p["R40"]]),
            "alpha": np.array([p["ALPHA"]]), "rac": np.array([p["Q40"] * p["L0U"]]), "C": np.array([c_uf * 1e-6])}


# ------------------------------------------------------------------ (a)
def part_a():
    rows = []
    for pan, which in (("enamelled_steel", "low"), ("enamelled_steel", "nom"), ("cast_iron", "nom")):
        d = nominal(pan, which=which)
        fr = float(F.fres(d)[0])
        p0, i0, f0, _ = F.power_at_ceiling(d, 120.0, 1239.0, 22.0, KP, KI)
        for f in np.arange(max(35e3, 1.05 * fr), 60.01e3, 1e3):
            P, i = F.pi_at(d, 120.0, np.array([f]), KP, KI)
            L, R = F.lr(d, np.array([f]))
            X = 2 * np.pi * f * L - 1 / (2 * np.pi * f * d["C"])
            z = float(np.hypot(R, X)[0])
            rows.append({"pan": f"{pan}-{which}", "f_kHz": round(f / 1e3, 1), "f_over_fres": round(f / fr, 3),
                         "P_W": round(float(P[0]), 1), "I_rms_A": round(float(i[0]), 2), "R_eq_ohm": round(float(R[0]), 3),
                         "P_if_held_at_22A_W": round(22 ** 2 * float(R[0]), 1),
                         "line_V_needed_for_22A": round(22 * z / 0.9003, 1),
                         "chosen_f_kHz_at_22A_ceiling": round(float(f0[0]) / 1e3, 2), "P_at_ceiling_W": round(float(p0[0]), 1)})
    write("fstrat-a-power-vs-f.csv", rows)
    return rows


# ------------------------------------------------------------------ (b)
BANK_OPTIONS = [  # (label, n parts, nF, C uF, fits the C21-C23 slot?)
    ("3 x 100 nF", 3, 100, 0.30, "yes"), ("7 x 47 nF", 7, 47, 0.33, "yes (7 x 11 mm = 80.5 mm, slot max ~81.8)"),
    ("4 x 100 nF", 4, 100, 0.40, "yes"), ("3 x 150 nF", 3, 150, 0.45, "yes"),
    ("5 x 100 nF (today)", 5, 100, 0.50, "yes (75 mm)"), ("4 x 150 nF", 4, 150, 0.60, "yes (4 x 19 = 76 mm)"),
    ("6 x 100 nF", 6, 100, 0.60, "no (90 mm > ~81.8 mm)"),
]


def bank_capability(n, nf, f):
    """Tank RMS at which the worst-share part reaches TDK's 85 C / dT 20 K curve, and the estimate at a 60 C
    local ambient (I^2 ~ (105 - T_amb), round 4's hot-spot rule: an ESTIMATE)."""
    share = M.worst_share(n, 1.0)
    i85 = M.tdk_limit(nf, f) / share
    return i85, i85 * math.sqrt((105 - 60) / 20)


def part_b():
    rows, caps = [], []
    for lfree in (70, 80, 90):
        for c_uf in (0.30, 0.35, 0.40, 0.45, 0.50, 0.60):
            fk, fr = M.coupling(M.GEOM, 220)
            rng = np.random.default_rng([20261010, lfree, int(c_uf * 100)])
            I, Fo, FL, VC = [], [], [], []
            for name, pan in M.B4.PANS.items():
                d = F.draws(pan, 3000, rng, M.L_INSTALLED[lfree], fk, fr, c_uf * 1e-6)
                i, f, st, fres = F.required_current(d, 120.0, 0.99 * 1239.0, KP, KI)
                I.append(i)
                Fo.append(f)
                FL.append(st == 2)
                VC.append(np.where(np.isfinite(i), i / (2 * np.pi * f * d["C"]), np.nan))
            I, Fo, FL, VC = map(np.concatenate, (I, Fo, FL, VC))
            row = {"L_free_uH": lfree, "C_bank_uF": c_uf, "floor_limited": round(float(FL.mean()), 3),
                   "f_op_med_kHz": round(float(np.median(Fo)) / 1e3, 1), "f_op_p95_kHz": round(float(np.percentile(Fo, 95)) / 1e3, 1)}
            for imax in M.CEILINGS:
                row[f"yield_{int(imax)}A"] = round(float((I <= imax).mean()), 3)
            row["vc_line_rms_max_V_at_I_req"] = round(float(np.nanmax(np.where(I <= 30, VC, np.nan))), 0)
            rows.append(row)
    write("fstrat-b-bank-sweep.csv", rows)
    for label, n, nf, c_uf, fits in BANK_OPTIONS:
        for f in (35e3, 40e3, 45e3, 50e3, 55e3, 60e3):
            i85, i60 = bank_capability(n, nf, f)
            caps.append({"bank": label, "C_uF": c_uf, "fits_slot": fits, "f_kHz": f / 1e3,
                         "worst_share": round(M.worst_share(n, 1.0), 3), "part_limit_85C_A": round(M.tdk_limit(nf, f), 2),
                         "tank_limit_85C_A": round(i85, 1), "tank_limit_60C_est_A": round(i60, 1)})
    write("fstrat-b-bank-capability.csv", caps)
    return rows, caps


# ------------------------------------------------------------------ (c) quasi-static FM
def _z(d, f):
    L, R = F.lr(d, f)
    X = 2 * np.pi * f * L - 1 / (2 * np.pi * f * d["C"])
    return np.hypot(R, X), R, L


def _kr(d, f):
    z, R, L = _z(d, f)
    return (KA + KB * (2 * np.pi * f * L / R) + KR) / 2      # peak ripple factor k_r = kpk / 2


def profile(d, V, f_b, f_c):
    """Per-draw (rows) x line-phase (cols) quasi-static solution for f(theta) = max(f_b, f_c(theta))."""
    f = np.maximum(f_b[:, None], f_c)
    dd = {k: v[:, None] for k, v in d.items()}
    z, R, L = _z(dd, f)
    vb = V * math.sqrt(2) * S[None, :]
    i_hf = 0.9003163 * vb / z * KI                       # HF RMS at theta
    p = (0.9003163 * vb / z) ** 2 * R * KP              # local tank power (kp-calibrated)
    ipk = math.sqrt(2) * i_hf * _kr(dd, f)
    i_line = np.sqrt((i_hf ** 2).mean(1))
    P = p.mean(1)
    i_in = p / (M.ETA * vb)                              # inlet current of the power stage (unsmoothed bus)
    i_in_rms = np.sqrt((i_in ** 2).mean(1))
    return {"f": f, "i_hf": i_hf, "i_line": i_line, "P": P, "ipk": ipk.max(1), "i_in_rms": i_in_rms, "pf": P / (M.ETA * V * i_in_rms)}


def clip_freq(d, V, ipk_t, f_floor):
    """f_c(theta): lowest f >= floor at which the local tank peak is <= ipk_t (bisection; 60 kHz cap)."""
    n = len(d["kl"])
    dd = {k: v[:, None] for k, v in d.items()}
    vb = V * math.sqrt(2) * S[None, :]
    lo = np.repeat(f_floor[:, None], NTH, 1)
    hi = np.full_like(lo, M.F_MAX)

    def pk(f):
        z, R, L = _z(dd, f)
        return math.sqrt(2) * 0.9003163 * vb / z * KI * _kr(dd, f)

    ok_lo = pk(lo) <= ipk_t
    for _ in range(18):
        mid = 0.5 * (lo + hi)
        g = pk(mid) <= ipk_t
        hi = np.where(g, mid, hi)
        lo = np.where(g, lo, mid)
    fc = np.where(ok_lo, f_floor[:, None], hi)
    unclippable = pk(np.full_like(lo, M.F_MAX)) > ipk_t
    return fc, unclippable.any(1)


def solve_fm(d, V, imax, ipk_t, clip=True, inlet_hold=M.I_PS_HOLD):
    """Max power s.t. line RMS <= imax, inlet RMS <= hold, P <= 1710 W, tank peak <= ipk_t, f >= floor.
    clip=False: constant frequency per pan (today's rule) with the same peak limit."""
    fr = F.fres(d)
    floor = np.maximum(M.F_MIN, M.ZVS * fr)
    if clip:
        fc, bad = clip_freq(d, V, ipk_t, floor)
    else:
        fc, bad = np.repeat(floor[:, None], NTH, 1), np.zeros(len(fr), bool)

    def ok(fb):
        r = profile(d, V, fb, fc)
        return ((r["i_line"] <= imax) & (r["i_in_rms"] <= inlet_hold * 1.0005) & (r["P"] <= M.P_REQ * 1.0005)
                & (r["ipk"] <= ipk_t * 1.0005)), r

    lo, hi = floor.copy(), np.full_like(floor, M.F_MAX)
    g0, _ = ok(lo)
    for _ in range(18):
        mid = 0.5 * (lo + hi)
        g, _ = ok(mid)
        hi = np.where(g, mid, hi)
        lo = np.where(g, lo, mid)
    fb = np.where(g0, floor, hi)
    g, r = ok(fb)
    r["feasible"] = g & ~bad
    r["f_b"] = fb
    r["full"] = r["feasible"] & ((r["i_in_rms"] >= 0.99 * inlet_hold) | (r["P"] >= 0.99 * M.P_REQ))
    r["full_1239"] = r["feasible"] & (r["P"] >= 0.99 * min(M.P_REQ, inlet_hold * M.ETA * V))
    return r


def part_c(n_draw=800):
    """Yield to the input hold, constant f vs crest-clip FM, under the 45 A firmware peak trip; constant f with no
    peak limit (OCP raised) as the reference. 'full' = P >= 99 % of min(1710, 11.1 A x 0.93 x V);
    'near' = P >= 95 % of it (FM can reach the 11.1 A inlet hold at PF < 1, i.e. below the PF-1 power)."""
    rows = []
    for lfree, c_uf in ((70, 0.50), (80, 0.40), (90, 0.40)):
        fk, fr = M.coupling(M.GEOM, 220)
        for V in (108.0, 120.0):
            rng = np.random.default_rng([7, lfree, int(c_uf * 100), int(V)])
            ds = [F.draws(pan, n_draw, rng, M.L_INSTALLED[lfree], fk, fr, c_uf * 1e-6) for pan in M.B4.PANS.values()]
            d = {k: np.concatenate([x[k] for x in ds]) for k in ds[0]}
            tgt = min(M.P_REQ, M.I_PS_HOLD * M.ETA * V)
            for ipk_t, clip, label in ((1e9, False, "constant f, no peak limit (OCP raised)"),
                                       (45.0, False, "constant f, 45 A peak trip"),
                                       (45.0, True, "crest-clip FM, 45 A peak")):
                for imax in M.CEILINGS:
                    r = solve_fm(d, V, imax, ipk_t, clip)
                    fe = r["feasible"]
                    full = fe & (r["P"] >= 0.99 * tgt)
                    near = fe & (r["P"] >= 0.95 * tgt)
                    rows.append({"L_free_uH": lfree, "C_bank_uF": c_uf, "pan_d_mm": 220, "line_vrms": V,
                                 "strategy": label, "I_max_A": imax,
                                 "yield_full": round(float(full.mean()), 3), "yield_95pct": round(float(near.mean()), 3),
                                 "P_median_W": round(float(np.median(r["P"][fe])), 0),
                                 "PF_min_near_full": round(float(r["pf"][near].min()), 4) if near.any() else "",
                                 "PF_median_near_full": round(float(np.median(r["pf"][near])), 4) if near.any() else "",
                                 "I_pk_max_A": round(float(r["ipk"][fe].max()), 1),
                                 "f_swing_max_kHz": round(float((r["f"].max(1) - r["f"].min(1))[fe].max()) / 1e3, 1),
                                 "unclippable": int((~fe).sum())})
    write("fstrat-c-fm.csv", rows)
    return rows


FM_DECK = r"""* Round 6: series tank over one line half-cycle with a line-synchronous frequency profile (ASSUMED basis).
* As round 4's tank_basis.cir, but the drive phase (cycles) follows PWL source ph (piecewise-constant frequency per
* line-phase segment, integrated in Python), and the load R follows the frequency PWL fq (behavioural). L is held
* at L(f_w), f_w the current-squared-weighted mean frequency of the profile (a behavioural d(L(f) i)/dt source did
* not converge); L(f) moves <= 1.5 % over the profiles checked, f^-0.13.
.include ../common/options.inc
.param VRMS=120 L0U=66.5 KL40=0.6 BETA=-0.13 Q40=0.003 GAMMA=0.55 R40=0.03 ALPHA=0.62 CRES=0.5u FW=40k
.include params.inc
.param VPK={VRMS*1.41421356}
Vfq fq 0 PWL({PWL})
Vph ph 0 PWL({PHPWL})
Bdrv drv 0 V={VPK}*abs(sin(6.283185307*60*time))*tanh(sin(6.283185307*V(ph))/0.02)
Br drv a V={L0U}*({Q40}*pwr(V(fq)/40k,{GAMMA}) + {R40}*pwr(V(fq)/40k,{ALPHA}))*i(Vim)
Lt a b {L0U*1e-6*KL40*pwr(FW/40k,BETA)}
Vim b c 0
Cr c 0 {CRES}
.param VW=1
* DC-link (bridge input) current = tank current x bridge polarity; its HF average (RC 30 us, the role of the
* bus film capacitor) is what the unsmoothed bus draws from the line.
Bib ib 0 V=i(Vim)*tanh(sin(6.283185307*V(ph))/0.02)
Rf ib ibf 1
Cf ibf 0 30u
.tran 50n 16.6667m 0 50n
.meas tran i_rms RMS i(Vim) from=8.3333m to=16.6667m
.meas tran i_pk MAX par('abs(i(Vim))') from=8.3333m to=16.6667m
.meas tran p_avg AVG par('v(drv)*i(Vim)') from=8.3333m to=16.6667m
.meas tran iin_rms RMS v(ibf) from=8.3333m to=16.6667m
.end
"""


def fm_spice_check():
    """Three cases: one pan at 120 V, (constant f) and (crest clip at 45 A), plus one 108 V clip case."""
    sys.path.insert(0, str(M.RG.KIT / "common"))
    import run_ngspice
    out = []
    for pan, which, V, clip in (("enamelled_steel", "nom", 120.0, False), ("enamelled_steel", "nom", 120.0, True),
                                ("aluminium_clad_multiply", "low", 108.0, True)):
        d = nominal(pan, which=which)
        r = solve_fm(d, V, 30.0, 45.0, clip)
        fprof = r["f"][0]
        # PWL over the half cycle (theta midpoints + ends)
        # two half cycles (the first settles the inlet filter); measures use the second
        f2 = np.concatenate([fprof, fprof])
        tb = np.arange(2 * NTH + 1) / (120.0 * NTH)             # segment boundaries
        ph = np.concatenate([[0.0], np.cumsum(f2 / (120.0 * NTH))])
        tm = np.concatenate([[0.0], TH / (2 * np.pi * 60), 1 / 120 + TH / (2 * np.pi * 60), [1 / 60]])
        fv = np.concatenate([[fprof[0]], f2, [fprof[-1]]])
        pwl = " ".join(f"{a:.9e} {b:.2f}" for a, b in zip(tm, fv))
        phpwl = " ".join(f"{a:.9e} {b:.6f}" for a, b in zip(tb, ph))
        work = Path(tempfile.mkdtemp(prefix="t05r6fm-"))
        try:
            deck = work / "tank_fm.cir"
            deck.write_text(FM_DECK.replace("{PWL}", pwl).replace("{PHPWL}", phpwl))
            params = {"VRMS": f"{V:g}", "L0U": f"{float(d['L0'][0]):.6g}", "KL40": f"{float(d['kl'][0]):.6g}",
                      "BETA": f"{F.BETA}", "Q40": f"{float(d['rac'][0] / d['L0'][0]):.6g}", "GAMMA": f"{F.GAMMA}",
                      "R40": f"{float(d['r40'][0]):.6g}", "ALPHA": f"{float(d['alpha'][0]):.6g}",
                      "CRES": f"{float(d['C'][0]):.6e}",
                      "FW": f"{float((r['i_hf'][0] ** 2 * fprof).sum() / (r['i_hf'][0] ** 2).sum()):.2f}"}
            res = run_ngspice.run(deck, params, keep=work / "run")
        finally:
            shutil.rmtree(work, ignore_errors=True)
        m = res["meas"]
        out.append({"case": f"{pan}-{which}-{int(V)}V-{'clip45' if clip else 'constf'}", "aborted": res["aborted"],
                    "qs_I_line_A": round(float(r["i_line"][0]), 2), "spice_I_line_A": round(m.get("i_rms", float("nan")), 2),
                    "qs_I_pk_A": round(float(r["ipk"][0]), 2), "spice_I_pk_A": round(m.get("i_pk", float("nan")), 2),
                    "qs_P_W": round(float(r["P"][0]), 1), "spice_P_W": round(m.get("p_avg", float("nan")), 1),
                    "qs_PF": round(float(r["pf"][0]), 4),
                    "spice_PF_ideal_bridge": round(m.get("p_avg", float("nan")) / (V * m.get("iin_rms", float("nan"))), 4), "f_min_kHz": round(float(fprof.min()) / 1e3, 2),
                    "f_max_kHz": round(float(fprof.max()) / 1e3, 2)})
    write("fstrat-c-fm-spice-check.csv", out)
    return out


# ------------------------------------------------------------------ (d) firmware as written: one fixed frequency
def part_d(n_draw=3000):
    rows = []
    for lfree, c_uf in ((70, 0.50),):
        fk, fr = M.coupling(M.GEOM, 220)
        rng = np.random.default_rng([11, lfree])
        ds = [F.draws(pan, n_draw, rng, M.L_INSTALLED[lfree], fk, fr, c_uf * 1e-6) for pan in M.B4.PANS.values()]
        d = {k: np.concatenate([x[k] for x in ds]) for k in ds[0]}
        fres = F.fres(d)
        for V in (108.0, 120.0, 127.0):
            best = None
            for f in np.arange(35e3, 60.01e3, 250.0):
                P, i = F.pi_at(d, V, np.full_like(fres, f), KP, KI)
                L, R = F.lr(d, np.full_like(fres, f))
                kpk = KA + KB * (2 * np.pi * f * L / R) + KR
                zvs = f >= M.ZVS * fres
                trip = (i > 23.1) | (kpk * i > 45.0) | ~zvs | (P > M.I_PS_HOLD * M.ETA * V * 1.0005)
                full = ~trip & (P >= 0.99 * min(M.P_REQ, M.I_PS_HOLD * M.ETA * V))
                cand = (float(full.mean()), f, float(trip.mean()), float(np.median(np.where(trip, 0, P))))
                if best is None or cand[0] > best[0]:
                    best = cand
            rows.append({"L_free_uH": lfree, "C_bank_uF": c_uf, "line_vrms": V, "best_fixed_f_kHz": best[1] / 1e3,
                         "yield_full_power": round(best[0], 3), "fraction_tripping": round(best[2], 3),
                         "P_median_W_non_tripping": round(best[3], 0)})
    write("fstrat-d-fixed-frequency.csv", rows)
    return rows


def main():
    a = part_a()
    b, caps = part_b()
    c = part_c()
    s = fm_spice_check()
    d = part_d()
    for r in s:
        print(r)
    for r in c:
        print({k: r[k] for k in ("L_free_uH", "C_bank_uF", "line_vrms", "strategy", "I_max_A", "yield_full",
                                 "yield_95pct", "P_median_W", "PF_min_near_full", "I_pk_max_A")})
    for r in d:
        print(r)


if __name__ == "__main__":
    main()
