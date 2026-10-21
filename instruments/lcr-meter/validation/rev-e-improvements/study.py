#!/usr/bin/env python3
"""Rev E improvements study: how far four planned changes close the accuracy gap to a bench LCR meter.

Phasor-level Monte Carlo of the whole measurement (calibration standards, fixture insertions, lead
geometry, drift between calibration and measurement, codec noise) through the host's three-standard
calibration, using the verified replica of the host fit/calibration (../virtual-instrument/vi_model.py
cal_coeffs / correct, which agrees with the binary to ~1e-11) and the Temper targets, DUT library and
error metrics of ../virtual-instrument/summarize.py.  E = |bias| + 2 sigma, worst test frequency.

Configurations (Cfg): baseline Rev E as committed; 1 characterized kit (1a DMM only, 1b C0G check
only, 1 both); 2 four-terminal (Kelvin) coax leads; 3 internal 1 kOhm reference check; 4 375 kHz
codec rate; all combined.  Realism: 'typical' (random draws) and 'corner' (deterministic worst
patterns), as in the VI README.  Every assumption marked ESTIMATE in README.md is a constant below.

    study.py            -> results/*.csv, results/summary.json, table on stdout (~1 min)
"""
from __future__ import annotations

import csv
import json
import math
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
VI = HERE.parent / "virtual-instrument"
sys.path.insert(0, str(VI))
sys.path.insert(0, str(HERE))
import vi_model as vm  # noqa: E402
from summarize import TARGETS, error  # noqa: E402
import revE_front as fe  # noqa: E402

RES = HERE / "results"
SOURCES = ("standards", "contact", "leads", "drift_ratio", "drift_leg", "noise")
ALL = frozenset(SOURCES)

# ------------------------------------------------------------------ assumptions (README section 3)
STD1, STD2 = 20.0, 100.0
MARK_TOL = 1e-3                 # marking-only standards: 0.1 % tolerance
DMM_RATIO_SIGMA = 1e-4          # ESTIMATE (given): 6.5-digit DMM 4-wire ratio, sigma 0.01 % typical ...
DMM_RATIO_CORNER = 4e-4         # ... 0.02 % sigma -> 2 sigma = 0.04 % opposite-sign ratio error at the corner
C0G_C = 10e-9                   # C0G reactive check standard (10 nF: X = 265-455 Ohm at 35-60 kHz)
C0G_TAND_ASSUMED = 5e-5         # ESTIMATE: entered tan d; true tan d ~ U(0, 1e-4) typical, 1e-4 corner
C0G_TAND_MAX = 1e-4
CONTACT = (2e-3, 6e-3)          # ESTIMATE (VI): per-insertion contact U(0, x), typical / corner
SHORT_2T = ((0.3e-3, 2e-9), (2e-3, 5e-9))     # ESTIMATE (VI): short residual R, L typ / corner
SHORT_4T = ((0.05e-3, 2e-9), (0.3e-3, 5e-9))  # ESTIMATE: Kelvin shorting bar
C_LEAD_2T = (100e-12, 200e-12)  # ESTIMATE (VI): loose-wire lead C per terminal, typ / corner
MOVE_2T = (0.20, 0.20)          # ESTIMATE (VI): loose leads move +/-20 % (typ random, corner +20 % after cal)
C_COAX = 100e-12                # ESTIMATE: 1 m coax at 100 pF/m, each of four leads
MOVE_COAX = (0.01, 0.03)        # ESTIMATE: coax C moves +/-1 % typ (random), +3 % corner (after cal)
L_LOOP_2T = (400e-9, 10e-9, 20e-9)   # ESTIMATE: 2T loop L, typ movement +/-, corner shift
M_4T = (20e-9, 2e-9, 5e-9)           # ESTIMATE: 4T current-loop -> pot-loop mutual L, movement
RREF = 1e3                      # internal reference, 0.1 % thin film
RREF_TCR = 25e-6                # ESTIMATE: /degC
RELAY_RC = 75e-3                # TQ2SA initial contact resistance max 75 mOhm (typ 28-38, Fig. 10)
RELAY_REPEAT = (1e-3, 10e-3)    # ESTIMATE: repeatability, typ U(+/-) / corner shift (life band 30-48 mOhm, Fig.)
DT = (5.0, 15.0)                # ESTIMATE: temperature change between calibration and measurement, degC
TC = dict(RF=25e-6, Riso=100e-6, R12=25e-6, Caa=30e-6, CF=30e-6, C100=30e-6)  # ESTIMATE TCs, /degC
RIN_COMMON = 0.20               # (given) codec input-impedance drift, common to all legs
RIN_LEG = (0.004, (0.02, -0.02, -0.02, 0.02))  # ESTIMATE: leg-to-leg mismatch = 2 % (typ sigma) / 10 % (corner)
                                                # of the 20 % common drift
CC_COMMON = (0.05, -0.15)       # ESTIMATE: X7R 1 uF drift (temperature + aging), typ U(+/-) / corner
CC_LEG = (0.01, (0.0, 0.0, 0.0, -0.15))   # ESTIMATE: leg mismatch, sigma / corner (front-end doc case)
NOISE_MULT = (1.0, 1.41)        # ESTIMATE: corner = CM_TOL penalty 6 dB instead of 3 dB
NOISE_375 = (1.0, 1.41)         # ESTIMATE: extra in-band noise at 375 kHz (unpublished), typ / corner
SIZES = dict(typ=(20, 5, 4), corner=(8, 5, 4))   # kits x calibrations x repeats
SEED = 7


@dataclass(frozen=True)
class Cfg:
    name: str
    label: str
    kelvin: bool = False
    kit: str = "marking"        # 'marking' | 'dmm'
    c0g: bool = False
    ref: bool = False
    fs375: bool = False
    bypass: bool = False        # reference check with Hcur->Hpot shorted by the relay's 2nd pole
    rezero: bool = False        # re-measure the (Kelvin) short at the start of each measurement session
    ref_unplug: bool = False    # run the reference check with the leads unplugged (no open coax on the inputs)
    capture_mult: float = 1.0   # capture time relative to the Rev D capture (on-device averaging allows more)


CFGS = [
    Cfg("base", "Baseline Rev E (2T, marked standards)"),
    Cfg("i1a", "1a DMM-characterized standards only", kit="dmm"),
    Cfg("i1b", "1b C0G check standard only", c0g=True),
    Cfg("i1", "1 Characterized kit (DMM + C0G check)", kit="dmm", c0g=True),
    Cfg("i2", "2 Four-terminal coax leads", kelvin=True),
    Cfg("i3", "3 Internal 1 kOhm reference check", ref=True),
    Cfg("i4", "4 375 kHz codec rate", fs375=True),
    Cfg("all", "All four combined", kelvin=True, kit="dmm", c0g=True, ref=True, fs375=True),
    Cfg("all_bp", "All four + Hcur-Hpot bypass during check", kelvin=True, kit="dmm", c0g=True, ref=True,
        fs375=True, bypass=True),
    Cfg("rec", "All four, check with leads unplugged, + short re-zero per session", kelvin=True, kit="dmm",
        c0g=True, ref=True, fs375=True, ref_unplug=True, rezero=True),
    Cfg("rec10", "As rec, captures 10x longer (0.16-3.3 s per point)", kelvin=True, kit="dmm", c0g=True, ref=True,
        fs375=True, ref_unplug=True, rezero=True, capture_mult=10.0),
]


def capture_s(f):
    """Rev D capture time (16384 samples at 1 MSPS / divider), as in ../rev-e-codec."""
    return vm.DEFAULT_COUNT * vm.divider_for(f) / vm.SAMPLE_BASE_HZ


def z_resistor(r, l, f, c=0.2e-12):
    w = 2 * math.pi * f
    zs = r + 1j * w * l
    return zs / (1 + 1j * w * c * zs)


# ------------------------------------------------------------------ draws
def draw_standards(cfg, corner, rng, k, en):
    u = rng.uniform(-1, 1, (k, 2))
    g = rng.standard_normal((k, 2))
    ul = rng.standard_normal((k, 2))
    ut = rng.uniform(0, 1, k)
    if cfg.kit == "marking":
        e = np.tile([MARK_TOL, -MARK_TOL], (k, 1)) if corner else MARK_TOL * u
    else:
        e = np.tile([DMM_RATIO_CORNER / 2, -DMM_RATIO_CORNER / 2], (k, 1)) if corner else \
            DMM_RATIO_SIGMA / math.sqrt(2) * g
    lv = np.tile([5e-9, 0.0], (k, 1)) if corner else np.maximum(0, 1.5e-9 + 1e-9 * ul)
    sr, sl = (SHORT_4T if cfg.kelvin else SHORT_2T)[int(corner)]
    tand = np.full(k, C0G_TAND_MAX) if corner else C0G_TAND_MAX * ut
    if "standards" not in en:
        e, lv, sr, sl, tand = 0 * e, 0 * lv, 0.0, 0.0, np.full(k, C0G_TAND_ASSUMED)
    return dict(e=e, l=lv, short=(sr, sl), tand=tand)


def draw_fixture(cfg, corner, rng, n, phase, en):
    u_rc = rng.uniform(0, 1, (n, 4))
    u_c2 = rng.uniform(-1, 1, (n, 2))
    u_cx = rng.uniform(-1, 1, (n, 4))
    u_l = rng.uniform(-1, 1, n)
    meas = phase == "meas"
    rc = CONTACT[int(corner)] * u_rc if "contact" in en else 0 * u_rc
    c0 = C_LEAD_2T[int(corner)]
    if "leads" not in en:
        c2 = np.full((n, 2), c0)
        cx = np.full((n, 4), C_COAX)
        l0 = (M_4T if cfg.kelvin else L_LOOP_2T)[0]
        ls = np.full(n, l0)
    elif corner:
        c2 = np.full((n, 2), c0 * (1 + (MOVE_2T[1] if meas else 0)))
        cx = np.full((n, 4), C_COAX * (1 + (MOVE_COAX[1] if meas else 0)))
        l0, _, lsh = M_4T if cfg.kelvin else L_LOOP_2T
        ls = np.full(n, l0 + (lsh if meas else 0))
    else:
        c2 = c0 * (1 + MOVE_2T[0] * u_c2)
        cx = C_COAX * (1 + MOVE_COAX[0] * u_cx)
        l0, lm, _ = M_4T if cfg.kelvin else L_LOOP_2T
        ls = l0 + lm * u_l
    return dict(rc=rc, c2t=c2, cx=cx, lser=ls)


def draw_drift(corner, rng, n, en):
    d = fe.nominal_drift(n)
    s = rng.choice([-1.0, 1.0], (n, 15))
    u = rng.uniform(-1, 1, (n, 15))
    g = rng.standard_normal((n, 8))
    urin = rng.uniform(-1, 1, n)
    ucc = rng.uniform(-1, 1, n)
    ratio, leg = "drift_ratio" in en, "drift_leg" in en
    if not (ratio or leg):
        return d
    if corner:
        dt = np.full(n, DT[1])
        t = lambda i, k: TC[k] * s[:, i]
        rin = (1 + RIN_COMMON) * (1 + np.tile(RIN_LEG[1], (n, 1)))
        cc = (1 + CC_COMMON[1]) * (1 + np.tile(CC_LEG[1], (n, 1)))
        rref_tc = RREF_TCR * s[:, 14]
    else:
        dt = DT[0] * u[:, 0]
        t = lambda i, k: TC[k] * u[:, i]
        rin = (1 + RIN_COMMON * urin)[:, None] * (1 + RIN_LEG[0] * g[:, :4])
        cc = (1 + CC_COMMON[0] * ucc)[:, None] * (1 + CC_LEG[0] * g[:, 4:])
        rref_tc = RREF_TCR * u[:, 14]
    # ratio-type: common to all legs (cancels in A/B or scales A/B); leg-type: leg-to-leg mismatch
    rin_c = (1 + RIN_COMMON) if corner else (1 + RIN_COMMON * urin)[:, None]
    rin_l = rin / rin_c
    cc_c = (1 + CC_COMMON[1]) if corner else (1 + CC_COMMON[0] * ucc)[:, None]
    cc_l = cc / cc_c
    if not ratio:
        dt_r = 0 * dt
        rin_c, cc_c, rref_tc = 1.0, 1.0, 0 * rref_tc
    else:
        dt_r = dt
    if not leg:
        rin_l, cc_l = 1.0, 1.0
    rin, cc = rin_c * rin_l, cc_c * cc_l
    dt_l = dt if leg else 0 * dt
    d["RF"] = d["RF"] * (1 + t(1, "RF") * dt_r)
    d["Riso"] = d["Riso"] * (1 + t(2, "Riso") * dt_r)
    d["CF"] = d["CF"] * (1 + t(3, "CF") * dt_r)
    d["C100"] = d["C100"] * (1 + t(4, "C100") * dt_r)
    for k in range(4):
        d["R1"][:, k] *= 1 + t(5 + k, "R12") * dt_l
        d["R2"][:, k] *= 1 + t(9 + k, "R12") * dt_l
        d["Caa"][:, k] *= 1 + t(13, "Caa") * dt_r
    d["Rin"] = d["Rin"] * rin
    d["Cc"] = d["Cc"] * cc
    d["rref_scale"] = 1 + rref_tc * dt
    return d


def expand(x, r):
    return np.repeat(x, r, axis=0)


def take(d, idx):
    return {k: v[idx] for k, v in d.items()}


# ------------------------------------------------------------------ one configuration
def dut_freqs():
    out = {}
    for t in TARGETS:
        out.setdefault(t[1], set()).update(t[2])
    return {k: sorted(v) for k, v in out.items()}


def c0g_epsilon(ms, m1, m2, mc, z1, z2, w):
    """Real ratio correction eps on standard 2 so the C0G check reads its assumed tan d."""
    def resid(eps):
        zc = vm.correct(mc, vm.cal_coeffs(ms, m1, z1, m2, z2 * (1 + eps)))
        return zc.real / -zc.imag - C0G_TAND_ASSUMED
    eps = np.zeros(ms.shape)
    for _ in range(5):
        r0 = resid(eps)
        dr = (resid(eps + 1e-6) - r0) / 1e-6
        eps = eps - r0 / dr
    return eps


def run(cfg, corner=False, en=ALL, phi_cc=0.0, rcp=fe.R_CP, sizes=None, seed=SEED, rsrc=fe.R_SRC):
    """Return {(dut, f): (zm array, zt)} for one configuration and realism level."""
    K, C, R = sizes or SIZES["corner" if corner else "typ"]
    nc, nm = K * C, K * C * R
    mult = NOISE_MULT[int(corner)] * (NOISE_375[int(corner)] if cfg.fs375 else 1.0)
    out = {}
    for fi, f in enumerate(sorted({x for v in dut_freqs().values() for x in v})):
        rng = np.random.default_rng([seed, fi, int(corner)])
        w = 2 * math.pi * f
        sig = fe.phasor_sigma(capture_s(f) * cfg.capture_mult, mult) if "noise" in en else 0.0
        st = draw_standards(cfg, corner, rng, K, en)
        kc = np.repeat(np.arange(K), C)
        nom = fe.nominal_drift(nc)

        def unplug(p):
            if cfg.ref_unplug:
                p["cx"] = 0 * p["cx"]
                p["c2t"] = 0 * p["c2t"]
            return p

        def cal_meas(z, ref=None):
            p = draw_fixture(cfg, corner, rng, nc, "cal", en)
            if ref is not None:
                p = unplug(p)
            a, b = fe.measure(f, cfg.kelvin, z, p, nom, rsrc=rsrc, ref=ref, rcp=rcp,
                              bypass=cfg.bypass and ref is not None)
            return fe.raw(a, b, rng, sig)

        sr, sl = st["short"]
        ms = cal_meas(np.full(nc, z_resistor(sr, sl, f, 0.0)))
        m1 = cal_meas(z_resistor(STD1, st["l"][kc, 0], f))
        m2 = cal_meas(z_resistor(STD2, st["l"][kc, 1], f))
        z1 = STD1 * (1 + st["e"][kc, 0])
        z2 = STD2 * (1 + st["e"][kc, 1])
        if cfg.c0g:
            zc = st["tand"][kc] / (w * C0G_C) - 1j / (w * C0G_C)
            mc = cal_meas(zc)
            z2 = z2 * (1 + c0g_epsilon(ms, m1, m2, mc, z1, z2, w))
        abc = vm.cal_coeffs(ms, m1, z1, m2, z2)
        abc_m = tuple(expand(x, R) for x in abc)
        drift = draw_drift(corner, rng, nc, en)
        drift["phi_cc"] = drift["phi_cc"] + phi_cc
        drift_m = {k: expand(v, R) for k, v in drift.items()}
        u_rel = rng.uniform(-1, 1, (nc, 2))
        if cfg.ref:
            rep = RELAY_REPEAT[int(corner)]
            if "drift_ratio" in en:
                rc0 = RELAY_RC + (0.0 if corner else rep * u_rel[:, 0])
                rc1 = RELAY_RC + (rep if corner else rep * u_rel[:, 1])
            else:
                rc0 = rc1 = np.full(nc, RELAY_RC)
            mr0 = cal_meas(None, ref=RREF + rc0)
            p = unplug(draw_fixture(cfg, corner, rng, nc, "meas", en))   # one check per measurement session
            a, b = fe.measure(f, cfg.kelvin, None, p, drift, rsrc=rsrc,
                              ref=RREF * drift["rref_scale"] + rc1, rcp=rcp, bypass=cfg.bypass)
            k_ref_s = mr0 / fe.raw(a, b, rng, sig)
            k_ref = expand(k_ref_s, R)
        if cfg.rezero:   # short re-measured at session start (after the check), replaces the offset b
            p = draw_fixture(cfg, corner, rng, nc, "meas", en)
            a, b = fe.measure(f, cfg.kelvin, np.full(nc, z_resistor(sr, sl, f, 0.0)), p, drift, rsrc=rsrc, rcp=rcp)
            ms1 = fe.raw(a, b, rng, sig) * (k_ref_s if cfg.ref else 1.0)
            abc_m = (abc_m[0], expand(ms1, R), abc_m[2])
        for dn, fl in dut_freqs().items():
            if f not in fl:
                continue
            d = vm.DUTS[dn]
            zt = complex(d.z(f))
            p = draw_fixture(cfg, corner, rng, nm, "meas", en)
            a, b = fe.measure(f, cfg.kelvin, np.full(nm, zt), p, drift_m, rsrc=rsrc, rcp=rcp)
            m = fe.raw(a, b, rng, sig)
            if cfg.ref:
                m = m * k_ref
            out[(dn, f)] = (vm.correct(m, abc_m), zt)
    return out


def evaluate(data):
    """Per target: worst-frequency E = |bias| + 2 sigma, with bias and sigma there."""
    res = {}
    for tid, dn, freqs, q, tol, unit, _ in TARGETS:
        best = None
        for f in freqs:
            zm, zt = data[(dn, f)]
            e = np.asarray(error(q, unit, zm, zt, f, dn))
            bias, sd = float(e.mean()), float(e.std(ddof=1))
            E = abs(bias) + 2 * sd
            if best is None or E > best["E"]:
                best = dict(E=E, bias=bias, sd=sd, f=f, ratio=E / tol)
        res[tid] = best
    return res


# ------------------------------------------------------------------ formatting
def fmt(tid, v):
    t = next(x for x in TARGETS if x[0] == tid)
    q, unit = t[3], t[5]
    if unit == "ohm":
        return f"{v * 1e3:.2f} mΩ"
    if q == "tand":
        return f"{v:.1e}"
    return f"{v * 100:.3f} %"


def tol_str(tid):
    t = next(x for x in TARGETS if x[0] == tid)
    return fmt(tid, t[4]).replace("1.0e-03", "1e-3")


def main():
    RES.mkdir(exist_ok=True)
    summary = dict(configs={}, attribution={}, assumptions={k: v for k, v in globals().items()
                                                           if k.isupper() and isinstance(v, (int, float, tuple, dict))})
    rows = []
    for cfg in CFGS:
        ev_t = evaluate(run(cfg, corner=False))
        ev_c = evaluate(run(cfg, corner=True))
        summary["configs"][cfg.name] = dict(label=cfg.label, typical=ev_t, corner=ev_c)
        for tid in ev_t:
            rows.append(dict(config=cfg.name, target=tid, E_typ=ev_t[tid]["E"], E_corner=ev_c[tid]["E"],
                             ratio_typ=ev_t[tid]["ratio"], ratio_corner=ev_c[tid]["ratio"],
                             worst_f_typ=ev_t[tid]["f"], worst_f_corner=ev_c[tid]["f"],
                             bias_corner=ev_c[tid]["bias"], sd_corner=ev_c[tid]["sd"]))
        print(f"done {cfg.name}", file=sys.stderr)
    with open(RES / "targets_E.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.4g}" if isinstance(v, float) else v) for k, v in r.items()})
    # attribution: one error source at a time (typical and corner), baseline and all-combined
    for cname in ("base", "all", "rec"):
        cfg = next(c for c in CFGS if c.name == cname)
        att = {}
        for corner in (False, True):
            for s in SOURCES:
                ev = evaluate(run(cfg, corner=corner, en=frozenset([s])))
                for tid, v in ev.items():
                    att.setdefault(tid, {})[f"{s}_{'corner' if corner else 'typ'}"] = v["E"]
        summary["attribution"][cname] = att
        print(f"attribution {cname}", file=sys.stderr)
    (RES / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print_tables(summary)


def print_tables(summary):
    cols = ["base", "i1", "i2", "i3", "i4", "all", "rec", "rec10"]
    head = "| Target | T | " + " | ".join(f"{c} typ / corner" for c in cols) + " |"
    print(head)
    print("|" + "---|" * (len(cols) + 2))
    for t in TARGETS:
        tid = t[0]
        cells = [f"{fmt(tid, summary['configs'][c]['typical'][tid]['E'])} / "
                 f"{fmt(tid, summary['configs'][c]['corner'][tid]['E'])}" for c in cols]
        print(f"| {tid} | {tol_str(tid)} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--table":
        print_tables(json.loads((RES / "summary.json").read_text()))
    else:
        main()
