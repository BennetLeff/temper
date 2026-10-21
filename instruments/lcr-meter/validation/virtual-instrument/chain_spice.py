#!/usr/bin/env python3
"""Full-chain AC transfer extraction for the Rev C virtual instrument.

The netlist is the validated fixed-local full chain (validation/solver-resolution-fixed-local/
ac-matched100.cir: official TI OPA810/OPA2810/THS4551 models, real FDA bias, 100 nH RF lead,
5 nH local-CF lead, ADC RC loads).  This script adds zero-valued AC injection sources at every
noise location, solves a strict true DC operating point with KLU (declaration-order search and
false-OP rejection reuse ../solver-resolution-rev-c-final/strict_order.rs through op_guard), then
runs one AC analysis per injection source (KLU cannot run .noise; AC injection works).

Every response of a linear network to any source is a bilinear (Moebius) function of one
two-terminal element's impedance, with a source-independent denominator.  So for each
configuration we solve three DUT resistances and fit, per frequency and per source,
    H(Z) = (p + q*Z) / (1 + s*Z)
for ADC channel A (HI-LO path) and B (LO-TIA path).  The fit is exact for three points; a fourth
DUT value and direct capacitor/coil runs check it (validate_transfer.py).

Usage: chain_spice.py CONFIG [--signal-only] [--instance SEED]
Writes work/transfer_<tag>.npz and data/transfer_<tag>.npz (compressed, < 5 MB).
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
WORK = HERE / "work"
DATA = HERE / "data"
MODELS = (HERE / "../../sources/ti/models").resolve()
SEED_INC = (HERE / "../solver-resolution-fixed-local/final-seed.inc").resolve()
NGSPICE = os.environ.get("NGSPICE", "/opt/homebrew/bin/ngspice")
OP_GUARD = WORK / "op_guard"

# AC grid: 50 points/decade, 1 Hz .. 200 MHz (ngspice dec sweep)
AC_CMD = "ac dec 50 1 200meg"

# Physical configurations.  'base' is the Rev C board as ordered.
CONFIGS = {
    "base": dict(rg=100.0, rf=100.0, cf=100e-12, rin_a=1000.0, rin_b=1000.0, rfb=1000.0),
    # what-if (a): low range, matched 33 ohm (needs BUF634A for current; not modelled in AC)
    "r33": dict(rg=33.0, rf=33.0, cf=100e-12, rin_a=1000.0, rin_b=1000.0, rfb=1000.0),
    # what-if (b1): both FDAs at gain 2 (input resistors 499 ohm, feedback unchanged)
    "gain2": dict(rg=100.0, rf=100.0, cf=100e-12, rin_a=499.0, rin_b=499.0, rfb=1000.0),
    # what-if (b3): voltage channel A at gain 4 (input resistors 249 ohm)
    "again4": dict(rg=100.0, rf=100.0, cf=100e-12, rin_a=249.0, rin_b=1000.0, rfb=1000.0),
    # 5 kOhm and 100 kOhm ranges, for completeness of the transfer model
    "r5k": dict(rg=5000.0, rf=5000.0, cf=100e-12, rin_a=1000.0, rin_b=1000.0, rfb=1000.0),
}
# what-if (d), Rev D candidate (validation/stability-full-chain/fixture-envelope.md): R_iso between
# the J3 LO pin (node low: DUT, LOW follower, lead capacitance) and the TIA summing node (sum:
# U7A -IN, RF, C104).  Lead capacitance to ground on each DUT terminal: c<pF> suffix.
for _riso in (0, 22):
    for _c in (0, 80, 100, 120, 160, 200, 240):
        _name = ("riso22" if _riso else "base") + (f"_c{_c}" if _c else "")
        if _name != "base":
            CONFIGS[_name] = dict(CONFIGS["base"], riso=float(_riso), chi=_c * 1e-12, clo=_c * 1e-12)
# Rev E (docs/rev-e-front-end.md): fixed 100 pF from DUT_LO to ground ahead of R_iso, for TIA
# stability with the range relays; no lead capacitance on HI.
CONFIGS["riso22_lo100"] = dict(CONFIGS["base"], riso=22.0, clo=100e-12)

# Noise injection sources: name -> (kind, element line template).  Op-amp voltage noise is
# a series source at the non-inverting pin; current noise is a shunt current source to ground;
# resistor thermal noise is a current source across the resistor.
OPAMP_EN = {  # source name, node it lifts, new node
    "en_x5": ("acin", "x5_p"),
    "en_x6a": ("excite", "x6a_p"),
    "en_x6b": ("hi", "x6b_p"),
    "en_x7b": ("low", "x7b_p"),
    "en_x7a": ("0", "x7a_p"),
    "en_xa": ("aip", "xa_p"),
    "en_xb": ("bip", "xb_p"),
}
CURRENT_SOURCES = {  # name -> (node_from, node_to)
    "in_x7a_m": ("0", "low"),
    "in_xa_p": ("0", "aip"),
    "in_xa_m": ("0", "aim"),
    "in_xb_p": ("0", "bip"),
    "in_xb_m": ("0", "bim"),
    "dut": ("hi", "low"),
}
RESISTORS = ["R30", "R31", "R32", "R33", "R34", "RG", "RF",
             "Rai1", "Rai2", "Raf1", "Raf2", "Raint1", "Raint2", "Raiso1", "Raiso2",
             "Rbi1", "Rbi2", "Rbf1", "Rbf2", "Rbint1", "Rbint2", "Rbiso1", "Rbiso2"]


def netlist(cfg, rdut, tol=None, noise=True):
    """Element lines.  tol: optional dict of multiplicative factors keyed by element name."""
    t = tol or {}

    def v(name, nominal):
        return nominal * t.get(name, 1.0)

    p = {k: (v(k, x) if not isinstance(x, str) else x) for k, x in dict(
        R30=330.0, C34=1e-9, R31=330.0, C35=1e-9, C36=1e-6, R32=100e3, R33=5e3, R34=1e3,
        RG=cfg["rg"], RF=cfg["rf"], CF=cfg["cf"],
        Rai1=cfg["rin_a"], Rai2=cfg["rin_a"], Raf1=cfg["rfb"], Raf2=cfg["rfb"],
        Raint1=22.0, Raint2=22.0, Raiso1=4.32, Raiso2=4.32,
        Caflt1=330e-12, Caflt2=330e-12, Cadiff=3.3e-9,
        Rbi1=cfg["rin_b"], Rbi2=cfg["rin_b"], Rbf1=cfg["rfb"], Rbf2=cfg["rfb"],
        Rbint1=22.0, Rbint2=22.0, Rbiso1=4.32, Rbiso2=4.32,
        Cbflt1=330e-12, Cbflt2=330e-12, Cbdiff=3.3e-9,
        Cfba1=100e-12, Cfba2=100e-12, Cfbb1=100e-12, Cfbb2=100e-12).items()}
    pin = {k: (n_new if noise else n_old) for k, (n_old, n_new) in OPAMP_EN.items()}
    riso = cfg.get("riso", 0.0)
    sm = "sum" if riso else "low"  # TIA summing node
    L = [
        "Vp vp 0 12", "Vn vn 0 -12", "V5 v5 0 5", "Vcm cm 0 2.048",
        "Vdds dds0 0 DC 0.3 AC 0", "Rdds dds0 dds 200",
        f"R30 dds lp1 {p['R30']:.12g}", f"C34 lp1 0 {p['C34']:.12g}",
        f"R31 lp1 lp2 {p['R31']:.12g}", f"C35 lp2 0 {p['C35']:.12g}",
        f"C36 lp2 acin {p['C36']:.12g}", f"R32 acin 0 {p['R32']:.12g}",
        f"X5 {pin['en_x5']} srcfb excite vp vn OPA810",
        f"R33 excite srcfb {p['R33']:.12g}", f"R34 srcfb 0 {p['R34']:.12g}",
        f"X6A {pin['en_x6a']} source source vp vn OPA2810",
        f"RG source hi {p['RG']:.12g}",
        f"RDUT hi low {rdut:.12g}",
        f"RF {sm} rf_end {p['RF']:.12g}",
        f"CF {sm} cf_end {p['CF']:.12g}",
        f"X6B {pin['en_x6b']} highbuf highbuf vp vn OPA2810",
        f"X7B {pin['en_x7b']} lowbuf lowbuf vp vn OPA2810",
        f"X7A {pin['en_x7a']} {sm} tia vp vn OPA2810",
        f"Rai1 highbuf aip {p['Rai1']:.12g}", f"Rai2 lowbuf aim {p['Rai2']:.12g}",
        f"Raf1 afbm aip {p['Raf1']:.12g}", f"Raf2 afbp aim {p['Raf2']:.12g}",
        f"Raint1 aom afbm {p['Raint1']:.12g}", f"Raint2 aop afbp {p['Raint2']:.12g}",
        f"Xa {pin['en_xa']} aim aop aom cm v5 0 THS4551",
        f"Raiso1 afbp aadc_p {p['Raiso1']:.12g}", f"Raiso2 afbm aadc_m {p['Raiso2']:.12g}",
        f"Caflt1 aadc_p 0 {p['Caflt1']:.12g}", f"Caflt2 aadc_m 0 {p['Caflt2']:.12g}",
        f"Cadiff aadc_p aadc_m {p['Cadiff']:.12g}",
        "Caadc1 aadc_p 0 16p", "Caadc2 aadc_m 0 16p",
        f"Rbi1 lowbuf bip {p['Rbi1']:.12g}", f"Rbi2 tia bim {p['Rbi2']:.12g}",
        f"Rbf1 bfbm bip {p['Rbf1']:.12g}", f"Rbf2 bfbp bim {p['Rbf2']:.12g}",
        f"Rbint1 bom bfbm {p['Rbint1']:.12g}", f"Rbint2 bop bfbp {p['Rbint2']:.12g}",
        f"Xb {pin['en_xb']} bim bop bom cm v5 0 THS4551",
        f"Rbiso1 bfbp badc_p {p['Rbiso1']:.12g}", f"Rbiso2 bfbm badc_m {p['Rbiso2']:.12g}",
        f"Cbflt1 badc_p 0 {p['Cbflt1']:.12g}", f"Cbflt2 badc_m 0 {p['Cbflt2']:.12g}",
        f"Cbdiff badc_p badc_m {p['Cbdiff']:.12g}",
        "Cbadc1 badc_p 0 16p", "Cbadc2 badc_m 0 16p",
        f"Cfba1 afbm aip {p['Cfba1']:.12g}", f"Cfba2 afbp aim {p['Cfba2']:.12g}",
        f"Cfbb1 bfbm bip {p['Cfbb1']:.12g}", f"Cfbb2 bfbp bim {p['Cfbb2']:.12g}",
        "Lrf rf_end tia 100n", "Lcf cf_end tia 5n",
        f"Chi hi 0 {cfg.get('chi', 0) or 1e-24:.12g}", f"Clo low 0 {cfg.get('clo', 0) or 1e-24:.12g}",
    ]
    if riso:
        L.append(f"Risolo low sum {riso:.12g}")
    names = ["dds"]
    if noise:
        for name, (old, new) in OPAMP_EN.items():
            L.append(f"V{name} {new} {old} DC 0 AC 0")
            names.append(name)
        for name, (a, b) in CURRENT_SOURCES.items():
            if name == "in_x7a_m":
                b = sm
            L.append(f"I{name} {a} {b} DC 0 AC 0")
            names.append(name)
        nodes = {l.split()[0]: l.split()[1:3] for l in L if l.split()[0] in RESISTORS + ["Risolo"]}
        for r in RESISTORS + (["Risolo"] if riso else []):
            a, b = nodes[r]
            L.append(f"Inr_{r} {a} {b} DC 0 AC 0")
            names.append("nr_" + r)
    return L, names


def source_element(name):
    if name == "dds":
        return "vdds"
    if name in OPAMP_EN:
        return "v" + name
    if name in CURRENT_SOURCES:
        return "i" + name
    return "i" + name  # nr_R..


def deck(stem, cfg, rdut, tol=None, noise=True):
    lines, names = netlist(cfg, rdut, tol, noise)
    head = [
        "RevC virtual instrument full chain; official models; AC injection transfers",
        f".include {MODELS}/opa2810_a.lib",
        f".include {MODELS}/opa810_a.lib",
        f".include {MODELS}/ths4551.lib",
        ".options reltol=1e-5 abstol=1e-12 vntol=1e-7 method=gear",
        f".include {SEED_INC}",
    ]
    ctl = [".control", "set klu", "set wr_singlescale", "set wr_vecnames", "set numdgt=15",
           "set filetype=ascii", "op", f"write {stem}_op.raw all"]
    prev = None
    for n in names:
        el = source_element(n)
        if prev:
            ctl.append(f"alter @{prev}[acmag] = 0")
        ctl.append(f"alter @{el}[acmag] = 1")
        ctl.append(AC_CMD)
        ctl.append(f"wrdata {stem}_{n}.dat real(v(aadc_p)-v(aadc_m)) imag(v(aadc_p)-v(aadc_m)) "
                   f"real(v(badc_p)-v(badc_m)) imag(v(badc_p)-v(badc_m))")
        prev = el
    ctl += ["quit", ".endc", ".end"]
    return "\n".join(head + lines + ctl) + "\n", names


def run_case(tag, cfg, rdut, tol=None, noise=True):
    """Return (freq, {source: (HA, HB)}) for one DUT resistance."""
    stem = f"{tag}_r{rdut:g}z"  # trailing z: no stem is a prefix of another
    d, names = deck(stem, cfg, rdut, tol, noise)
    os.chdir(WORK)
    (WORK / ".spiceinit").write_text((HERE / "spiceinit").read_text())  # PSpice compatibility
    for f in [WORK / f"{stem}_{n}.dat" for n in names] + [WORK / f"{stem}_op.raw"]:
        f.unlink(missing_ok=True)
    Path(f"{stem}.cir").write_text(d)
    # Strict order search on the OP-only variant (the helper strips our control block).
    r = subprocess.run([str(OP_GUARD), "order", stem, f"{stem}.cir", f"{stem}-ordered.cir"],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{stem}: no true OP order: {r.stderr}")
    order = int(r.stdout.split()[1])
    ordered = Path(f"{stem}-ordered.cir").read_text()
    with open(f"{stem}.log", "w") as log:
        st = subprocess.run([NGSPICE, "-b", f"{stem}-ordered.cir"], stdout=log, stderr=log)
    logtxt = Path(f"{stem}.log").read_text()
    if st.returncode or "aborted" in logtxt or re.search(r"\berror\b", logtxt, re.I):
        raise RuntimeError(f"{stem}: ngspice failure, see work/{stem}.log")
    chk = subprocess.run([str(OP_GUARD), "check", f"{stem}_op.raw"], capture_output=True, text=True)
    if chk.returncode:
        raise RuntimeError(f"{stem}: false OP: {chk.stderr}")
    out = {}
    freq = None
    for n in names:
        a = np.loadtxt(f"{stem}_{n}.dat", skiprows=1)
        if freq is None:
            freq = a[:, 0]
        elif not np.array_equal(freq, a[:, 0]):
            raise RuntimeError("frequency grids differ")
        if not np.all(np.isfinite(a)):
            raise RuntimeError(f"{stem}_{n}: non-finite AC data")
        out[n] = (a[:, 1] + 1j * a[:, 2], a[:, 3] + 1j * a[:, 4])
    # Raw vectors are large: keep only the deck, log and OP check.
    for n in names:
        (WORK / f"{stem}_{n}.dat").unlink()
    for f in WORK.glob(f"{stem}-order*.raw"):
        f.unlink()
    meta = dict(order=order, op_check=chk.stdout.strip(), deck_sha256=hashlib.sha256(ordered.encode()).hexdigest())
    return freq, out, meta


def bilinear_fit(zs, hs):
    """Fit H(Z)=(p+qZ)/(1+sZ) per frequency.  zs: 3 real; hs: list of 3 arrays (A) -> p,q,s."""
    z1, z2, z3 = zs
    h1, h2, h3 = hs
    # Linear in (p, q, s): p + q z - s z h = h
    n = len(h1)
    p = np.empty(n, complex); q = np.empty(n, complex); s = np.empty(n, complex)
    for k in range(n):
        M = np.array([[1, z1, -z1 * h1[k]], [1, z2, -z2 * h2[k]], [1, z3, -z3 * h3[k]]], complex)
        p[k], q[k], s[k] = np.linalg.solve(M, [h1[k], h2[k], h3[k]])
    return p, q, s


def fit_pq(zs, hs, s):
    """With the shared denominator s known, least-squares p, q from >=2 points."""
    n = len(hs[0])
    p = np.empty(n, complex); q = np.empty(n, complex)
    for k in range(n):
        M = np.array([[1, z] for z in zs], complex)
        y = np.array([h[k] * (1 + s[k] * z) for h, z in zip(hs, zs)])
        (p[k], q[k]), *_ = np.linalg.lstsq(M, y, rcond=None)
    return p, q


def extract(tag, cfg, zs, tol=None, noise=True, check_z=None):
    WORK.mkdir(exist_ok=True)
    zlist = list(zs) + ([check_z] if check_z else [])
    with ThreadPoolExecutor(max_workers=3) as ex:  # at most 3 concurrent ngspice processes
        res = list(ex.map(lambda z: run_case(tag, cfg, z, tol, noise), zlist))
    freq = res[0][0]
    names = list(res[0][1].keys())
    # Shared denominator from the DDS source on channel A (largest, cleanest response).
    _, _, s = bilinear_fit(zs, [res[i][1]["dds"][0] for i in range(3)])
    coef = {}
    for n in names:
        pa, qa = fit_pq(zs, [res[i][1][n][0] for i in range(3)], s)
        pb, qb = fit_pq(zs, [res[i][1][n][1] for i in range(3)], s)
        coef[n] = np.stack([pa, qa, pb, qb])
    check = None
    if check_z:
        hz = res[3][1]
        err = 0.0
        for n in names:
            pa, qa, pb, qb = coef[n]
            ha = (pa + qa * check_z) / (1 + s * check_z)
            hb = (pb + qb * check_z) / (1 + s * check_z)
            scale = max(np.max(np.abs(hz[n][0])), np.max(np.abs(hz[n][1])), 1e-30)
            err = max(err, np.max(np.abs(ha - hz[n][0])) / scale, np.max(np.abs(hb - hz[n][1])) / scale)
        check = float(err)
    meta = dict(config=tag, params=cfg, tolerance_factors=tol or {}, dut_resistances=list(zs),
                runs=[r[2] for r in res], check_resistance=check_z,
                check_max_normalized_error=check, ac=AC_CMD)
    return freq, s, names, coef, meta


def save(path, freq, s, names, coef, meta):
    arr = np.stack([coef[n] for n in names])  # (src, 4, f)
    np.savez_compressed(path, freq=freq, s=s, names=np.array(names), coef=arr,
                        meta=json.dumps(meta))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config", choices=sorted(CONFIGS))
    ap.add_argument("--signal-only", action="store_true")
    ap.add_argument("--instance", type=int, help="board-instance tolerance draw seed (signal only)")
    a = ap.parse_args()
    cfg = CONFIGS[a.config]
    tol = None
    tag = a.config
    if a.instance is not None:
        tol = instance_tolerances(a.instance)
        tag = f"{a.config}_inst{a.instance}"
    rg = cfg["rg"]
    zs = (rg * 0.03, rg * 1.0, rg * 30.0)
    freq, s, names, coef, meta = extract(tag, cfg, zs, tol, noise=not (a.signal_only or tol),
                                         check_z=rg * 0.3)
    DATA.mkdir(exist_ok=True)
    out = DATA / f"transfer_{tag}.npz"
    save(out, freq, s, names, coef, meta)
    print(json.dumps(dict(out=str(out.relative_to(HERE)), check_max_normalized_error=meta["check_max_normalized_error"],
                          orders=[r["order"] for r in meta["runs"]]), indent=1))


def instance_tolerances(seed):
    """Board-instance component draws from the BOM tolerances (uniform within tolerance).

    RG/RF 0.1 % (RT0603B), CF C104 5 % C0G, FDA 1 k 0.1 %, 22 ohm 5 %, 4.32 ohm 1 %,
    FDA 100 pF / 330 pF / 3.3 nF C0G 5 %, reconstruction 330 ohm 1 % and 1 nF 5 %."""
    rng = np.random.default_rng(10_000 + seed)
    tol = {}
    spec = {"RG": 1e-3, "RF": 1e-3, "CF": 0.05, "R30": 0.01, "R31": 0.01, "C34": 0.05, "C35": 0.05,
            "R33": 1e-3, "R34": 1e-3}
    for ch in "ab":
        spec.update({f"R{ch}i1": 1e-3, f"R{ch}i2": 1e-3, f"R{ch}f1": 1e-3, f"R{ch}f2": 1e-3,
                     f"R{ch}int1": 0.05, f"R{ch}int2": 0.05, f"R{ch}iso1": 0.01, f"R{ch}iso2": 0.01,
                     f"C{ch}flt1": 0.05, f"C{ch}flt2": 0.05, f"C{ch}diff": 0.05,
                     f"Cfb{ch}1": 0.05, f"Cfb{ch}2": 0.05})
    for k, t in sorted(spec.items()):
        tol[k] = float(1 + rng.uniform(-t, t))
    return tol


if __name__ == "__main__":
    sys.exit(main())
