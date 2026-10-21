#!/usr/bin/env python3
"""Rev E accuracy map: E = |bias| + 2 sigma of |Z| and phase over |Z| x frequency, on each range.

Same phasor Monte Carlo as ../rev-e-improvements/study.py (front end, fixture, drift, codec noise,
host three-standard calibration), generalized from the 100 Ohm range to all three:
  - range r: RG = RF = r, source resistance r + 47 Ohm (R40/R41/R42 in series to DUT_HI, R104 47 Ohm),
    C104 100 pF shared; standards short + (20, 100) / (1k, 4.99k) / (20k, 100k) Ohm per range
    (calkit/README.md), DMM-characterized;
  - configuration: the recommended one without the C0G phase check (it exists only for the 100 Ohm
    range's reactive targets) and at the default 187.5 kHz rate: four-terminal coax, reference check on
    the same range with the leads unplugged, short re-measured per session;
  - capture: the host default, the smallest whole number of periods summing >= 0.25 s;
  - new here: a HI-LO stray across the DUT at the clips (C_HL, ESTIMATE), which only matters at high |Z|.
DUTs: |Z| = 10 mOhm .. 10 MOhm in half decades, at three phases: resistive (0 deg), inductive Q = 100,
capacitive D = 1e-3.  Each cell reports the worst of the three phases; 'best' is the range with the lowest
typical |Z| error (the host has no autorange: the operator picks the range).
Frequencies 50 Hz .. 85 kHz: 45.8 Hz is the lowest tone the firmware makes (period <= 4096 at 187.5 kHz)
and 85 kHz the highest.

    accuracy_map.py  -> results/map.json, results/tables.md (~1 min)
"""
from __future__ import annotations

import contextlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "rev-e-improvements"))
import study as s  # noqa: E402
import commercial as com  # noqa: E402

fe, vm = s.fe, s.vm
RES = HERE / "results"

RANGES = (100, 5000, 100000)
R104 = 47.0
STDS = {100: (20.0, 100.0), 5000: (1e3, 4.99e3), 100000: (20e3, 100e3)}
FREQS = (50, 100, 200, 500, 1e3, 2e3, 5e3, 10e3, 20e3, 50e3, 85e3)
ZMAGS = tuple(10 ** (k / 2) for k in range(-4, 15))          # 10 mOhm .. 10 MOhm
PHASES = {"R": 0.0, "L_Q100": math.atan(100.0), "C_D1e-3": -math.atan(1e3)}
CAPTURE_S = 0.25                 # host default summed capture (host/src/rev_e.rs)
STD_C = 0.2e-12                  # ESTIMATE: standard self-capacitance (study.z_resistor default); the host
                                 # takes real-valued standards, so it is uncorrected
C_HL = 0.3e-12                   # ESTIMATE: HI-LO clip stray across the DUT
C_HL_MOVE = (0.05, 0.10)         # ESTIMATE: per insertion +/-5 % (typ, random) / +10 % after cal (corner)
SEED = 11
CFG = s.Cfg("map", "Four-terminal, DMM kit, reference check unplugged, short per session",
            kelvin=True, kit="dmm", ref=True, ref_unplug=True, rezero=True)


@contextlib.contextmanager
def feedback_resistor(r):
    """fe.nominal_drift reads NOM['RF'] at call time; point it at the selected range."""
    old = fe.NOM["RF"]
    fe.NOM["RF"] = float(r)
    try:
        yield
    finally:
        fe.NOM["RF"] = old


def capture_s(f):
    return math.ceil(CAPTURE_S * f) / f


def c_hl(corner, rng, n, phase, en):
    if "leads" not in en:
        return np.full(n, C_HL)
    if corner:
        return np.full(n, C_HL * (1 + (C_HL_MOVE[1] if phase == "meas" else 0.0)))
    return C_HL * (1 + C_HL_MOVE[0] * rng.uniform(-1, 1, n))


def run_point(r, f, zs, corner, seed=SEED, en=None):
    """Corrected readings (nm,) for every DUT impedance in zs, on range r at f."""
    cfg, en = CFG, (s.ALL if en is None else en)
    K, C, R = s.SIZES["corner" if corner else "typ"]
    nc, nm = K * C, K * C * R
    rng = np.random.default_rng([seed, int(f), int(r), int(corner)])
    w = 2 * math.pi * f
    sig = fe.phasor_sigma(capture_s(f), s.NOISE_MULT[int(corner)]) if "noise" in en else 0.0
    rsrc = r + R104
    std1, std2 = STDS[r]
    with feedback_resistor(r):
        st = s.draw_standards(cfg, corner, rng, K, en)
        kc = np.repeat(np.arange(K), C)
        nom = fe.nominal_drift(nc)
        drift = s.draw_drift(corner, rng, nc, en)

    def meas(z, d, phase, n, ref=None):
        p = s.draw_fixture(cfg, corner, rng, n, phase, en)
        if ref is not None:          # reference check: leads unplugged
            p["cx"] = 0 * p["cx"]
            z_eff = None
        else:
            z_eff = z / (1 + 1j * w * c_hl(corner, rng, n, phase, en) * z)
        a, b = fe.measure(f, True, z_eff, p, d, rsrc=rsrc, ref=ref)
        return fe.raw(a, b, rng, sig)

    sr, sl = st["short"]
    zshort = np.full(nc, s.z_resistor(sr, sl, f, 0.0))
    ms = meas(zshort, nom, "cal", nc)
    cs = STD_C if "standards" in en else 0.0
    m1 = meas(s.z_resistor(std1, st["l"][kc, 0], f, cs), nom, "cal", nc)
    m2 = meas(s.z_resistor(std2, st["l"][kc, 1], f, cs), nom, "cal", nc)
    abc = vm.cal_coeffs(ms, m1, std1 * (1 + st["e"][kc, 0]), m2, std2 * (1 + st["e"][kc, 1]))
    # reference check at calibration and at the measurement session (study.py, rec)
    rep = s.RELAY_REPEAT[int(corner)]
    u = rng.uniform(-1, 1, (nc, 2))
    rc0 = s.RELAY_RC + (0.0 if corner else rep * u[:, 0])
    rc1 = s.RELAY_RC + (rep if corner else rep * u[:, 1])
    k_ref_s = np.ones(nc, complex)
    if cfg.ref:
        mr0 = meas(None, nom, "cal", nc, ref=s.RREF + rc0)
        k_ref_s = mr0 / meas(None, drift, "meas", nc, ref=s.RREF * drift["rref_scale"] + rc1)
    ms1 = meas(zshort, drift, "meas", nc) * k_ref_s            # short re-measured per session
    abc_m = (s.expand(abc[0], R), s.expand(ms1, R), s.expand(abc[2], R))
    k_ref = s.expand(k_ref_s, R)
    drift_m = {k: s.expand(v, R) for k, v in drift.items()}
    return [vm.correct(meas(np.full(nm, z), drift_m, "meas", nm) * k_ref, abc_m) for z in zs]


def stats(e):
    return float(abs(e.mean()) + 2 * e.std(ddof=1))


def main():
    RES.mkdir(exist_ok=True)
    duts = [(zm, ph, zm * complex(math.cos(t), math.sin(t))) for zm in ZMAGS for ph, t in PHASES.items()]
    zs = [d[2] for d in duts]
    cells = {}
    for corner in (False, True):
        for r in RANGES:
            for f in FREQS:
                zm_all = run_point(r, f, zs, corner)
                for (zmag, ph, zt), zm in zip(duts, zm_all):
                    ez = stats(np.abs(zm) / abs(zt) - 1)
                    et = stats(np.angle(zm / zt))
                    c = cells.setdefault(f"{zmag:.4g}|{f:g}|{r}", dict(z=zmag, f=f, range=r))
                    k = "corner" if corner else "typ"
                    c[f"z_{k}"] = max(c.get(f"z_{k}", 0.0), ez)
                    c[f"th_{k}"] = max(c.get(f"th_{k}", 0.0), et)
            print(f"range {r} {'corner' if corner else 'typ'} done", file=sys.stderr)
    best = {}
    for c in cells.values():
        key = f"{c['z']:.4g}|{c['f']:g}"
        if key not in best or c["z_typ"] < best[key]["z_typ"]:
            best[key] = c
    for b in best.values():
        b["gw_0m"] = com.gw_ae(b["f"], b["z"], 0.0)
        b["gw_1m"] = com.gw_ae(b["f"], b["z"], 1.0)
        b["bk"] = com.bk_ae(b["f"], b["z"])
    out = dict(config=CFG.label, capture_s=CAPTURE_S, c_hl=C_HL, c_hl_move=C_HL_MOVE, ranges=RANGES,
               freqs=FREQS, zmags=ZMAGS, phases=list(PHASES), seed=SEED,
               cells=list(cells.values()), best=list(best.values()))
    (RES / "map.json").write_text(json.dumps(out, indent=1))
    md = tables(out)
    (RES / "tables.md").write_text(md)
    print(md)


def zlabel(z):
    for unit, k in (("MΩ", 1e6), ("kΩ", 1e3), ("Ω", 1.0), ("mΩ", 1e-3)):
        if z >= k * 0.999:
            v = z / k
            return f"{v:.3g} {unit}"
    return f"{z:.3g} Ω"


def rng_label(r):
    return {100: "100", 5000: "5k", 100000: "100k"}[r]


def flabel(f):
    return f"{f / 1e3:g}k" if f >= 1e3 else f"{f:g}"


def grid(out, fn, title, note=""):
    b = {(c["z"], c["f"]): c for c in out["best"]}
    lines = [f"### {title}", ""]
    if note:
        lines += [note, ""]
    lines.append("| \\|Z\\| | " + " | ".join(flabel(f) for f in out["freqs"]) + " |")
    lines.append("|---" * (len(out["freqs"]) + 1) + "|")
    for z in out["zmags"]:
        lines.append(f"| {zlabel(z)} | " + " | ".join(fn(b[(z, f)]) for f in out["freqs"]) + " |")
    return "\n".join(lines) + "\n"


def pct(x):
    x *= 100
    return f"{x:.2g}" if x < 10 else f"{x:.0f}"


def verdict(c, spec):
    typ = max(c["z_typ"], c["th_typ"])
    if max(typ, c["z_corner"], c["th_corner"]) <= c[spec]:
        return "✓"
    return "~" if typ <= c[spec] else "✗"


def tables(out):
    parts = [
        grid(out, lambda c: f"{pct(c['z_typ'])} / {pct(c['z_corner'])}",
             "|Z| error, % (typical / corner), best range",
             "Worst of resistive, inductive (Q 100) and capacitive (D 1e-3) DUTs."),
        grid(out, lambda c: f"{pct(c['th_typ'])} / {pct(c['th_corner'])}",
             "Phase error, centiradians (typical / corner), best range",
             "1 crad = 0.01 rad = 0.57°; for small D or 1/Q, the phase error is the D (tan δ) error."),
        grid(out, lambda c: rng_label(c["range"]), "Best range (Ω)"),
        grid(out, lambda c: f"{pct(c['gw_1m'])}", "GW Instek LCR-6100 published |Z| accuracy with 1 m leads, %",
             "From ../rev-e-improvements/commercial.py (manual §13, 1 Vrms, slow); 1.7 V peak here. Phase "
             "accuracy is the same number in rad/100."),
        grid(out, lambda c: verdict(c, "gw_1m"), "Rev E against LCR-6100 (1 m leads)",
             "✓ typical and corner, |Z| and phase, all within the LCR-6100 spec; ~ typical within, corner not; "
             "✗ typical outside."),
        grid(out, lambda c: verdict(c, "gw_0m"), "Rev E against LCR-6100 (0 m direct fixture)"),
    ]
    parts.append(bands(out))
    return "\n".join(parts)


def bands(out):
    """Frequency span per |Z| where every error (typical and corner, |Z| and phase) is within a limit."""
    lines = ["### Where every error is within 0.2 % and 1 %", "",
             "Phase in rad against the same number (0.2 % = 2 mrad).", "",
             "| \\|Z\\| | ≤ 0.2 % | ≤ 1 % |", "|---|---|---|"]
    for z in out["zmags"]:
        cells = []
        for lim in (0.002, 0.01):
            fs = [c["f"] for c in out["best"] if c["z"] == z and
                  max(c["z_typ"], c["z_corner"], c["th_typ"], c["th_corner"]) <= lim]
            cells.append(f"{flabel(min(fs))}–{flabel(max(fs))} Hz ({len(fs)}/{len(out['freqs'])})" if fs else "—")
        lines.append(f"| {zlabel(z)} | " + " | ".join(cells) + " |")
    counts = []
    for spec, lab in (("gw_1m", "1 m leads"), ("gw_0m", "0 m fixture")):
        v = [verdict(c, spec) for c in out["best"]]
        counts.append(f"LCR-6100 {lab}: ✓ {v.count('✓')}, ~ {v.count('~')}, ✗ {v.count('✗')} of {len(v)}")
    return "\n".join(lines) + "\n\nVerdict counts: " + "; ".join(counts) + ".\n"


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--tables":
        print(tables(json.loads((RES / "map.json").read_text())))
    else:
        main()
