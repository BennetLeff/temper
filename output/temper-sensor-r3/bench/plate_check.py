"""Does the plate under the pan matter for the dry h_c measurement? -> plate-check.json

The plate (the cooktop "glass" stand-in) does not enter the contact the survey measures:
h_c is set by the disc face, the pan base, the spring force and the tilt-following mount.
The plate acts only through a gradient. The pan base resting on a cold plate cools there,
while the pan over the Ø18 bore (the contact point) does not. The reference thermocouple is
15 mm from the contact, so it sits over the plate. fit.py uses the reference's slope and
leaves its offset free, so a slope mismatch Δs between the reference and the contact point
biases the fitted h_c.

1. The slope mismatch, from a radial finite-difference model of the pan base (lateral
   conduction kt, heat capacity rho·c·t). The plate draws q(t) only where the pan rests on
   it (r > 9 mm, outside the bore): q(t) = h ΔT exp(b²) erfc(b), b = h sqrt(t) / e,
   e = sqrt(k rho c), contact conductance h_pp in series with a semi-infinite plate
   (Carslaw & Jaeger). Slopes are least-squares over 1-9 s after set-down at the contact
   centre (r = 0), at the old reference position (r = 15 mm, over the plate) and at a
   reference inside the bore (r = 6.5 mm, outside the Ø7.6 contact, inside the Ø18 bore).
2. The τ63_C1 error each mismatch causes, from fit.py's own synthetic generator
   (synth_log ref_extra_cool) and fit, at h = 888 and 1300 W/m²K (the bar region).

Material values are handbook values. ΔT is 125 K (150 °C pan on a room-temperature plate)
or 40 K (plate preheated to about 110 °C). Run: python plate_check.py
"""
from __future__ import annotations

import json
from math import erfc, exp, sqrt
from pathlib import Path

import numpy as np

import fit

HERE = Path(__file__).parent
PLATES = {  # k W/mK, rho kg/m3, c J/kgK
    "glass-ceramic 4 mm (product material)": (1.6, 2550, 800),
    "porcelain tile": (1.5, 2400, 850),
    "calcium-silicate board": (0.12, 750, 1000),
    "aluminium 6061 (don't)": (167.0, 2700, 896),
}
PANS = {  # (rho*c*t J/m2K, k*t W/K) of the base
    "carbon steel 2 mm": (7850 * 470 * 2e-3, 50 * 2e-3),
    "tri-ply clad 2.6 mm": (4.0e6 * 1.0e-3 + 2.43e6 * 1.6e-3, 16 * 1.0e-3 + 200 * 1.6e-3),
    "cast iron 5 mm": (7200 * 460 * 5e-3, 50 * 5e-3),
}
R_BORE, R_REF_OLD, R_REF_IN = 9e-3, 15e-3, 6.5e-3
DT_CASES = (125.0, 40.0)
H_PP = (300.0, 1500.0)   # pan-to-plate dry contact, W/m2K (light pressure over a large area)
WIN_S = 9.0


def flux(h, e, dT, t):
    b = h * sqrt(max(t, 1e-6)) / e
    # exp(b^2) erfc(b) overflows for large b; use the asymptote 1/(b sqrt(pi)) there
    return h * dT * (exp(b * b) * erfc(b) if b < 25 else 1 / (b * sqrt(np.pi)))


def radial_slopes(rct, kt, h, e, dT, R=0.08, dr=0.5e-3):
    """Pan base as rings; plate flux on r > R_BORE. Returns {r: slope K/s} over 1-9 s."""
    n = int(R / dr)
    r_lo = np.arange(n) * dr
    r_hi = r_lo + dr
    area = np.pi * (r_hi**2 - r_lo**2)
    C = rct * area
    G = 2 * np.pi * kt * r_hi[:-1] / dr
    on_plate = (0.5 * (r_lo + r_hi)) > R_BORE
    alpha = kt / rct
    dt = 0.2 * dr * dr / alpha
    T = np.zeros(n)      # temperature drop relative to the initial pan temperature
    probes = {0.0: 0, R_REF_IN: int(R_REF_IN / dr), R_REF_OLD: int(R_REF_OLD / dr)}
    ts, rec = [], {k: [] for k in probes}
    t = 0.0
    while t < WIN_S:
        q = flux(h, e, dT, t + 0.5 * dt)
        flow = G * (T[1:] - T[:-1])
        div = np.zeros(n)
        div[:-1] += flow
        div[1:] -= flow
        T = T + dt * (div - q * area * on_plate) / C
        t += dt
        if not ts or t - ts[-1] >= 0.05:
            ts.append(t)
            for k, i in probes.items():
                rec[k].append(T[i])
    ts = np.array(ts)
    m = ts >= 1.0
    return {k: float(np.polyfit(ts[m], np.array(v)[m], 1)[0]) for k, v in rec.items()}


def tau_error(ds_list):
    """τ63_C1 fit error vs truth for each reference slope mismatch, with selftest-style truth."""
    rng = np.random.default_rng(7)
    tmp = HERE / "_platecheck_logs"
    tmp.mkdir(exist_ok=True)
    probe = fit.load_probe(HERE / "probe.example.json")
    truth = {"A_s": probe["A_s"], "C_disc_true": probe["C_cap_s"] - probe["bond"]["C_extra_J_K"],
             "C_bond_true": probe["bond"]["C_extra_J_K"], "k_disc": probe["disc"]["k_W_mK"],
             "t_disc_m": probe["disc"]["t_mm"] * 1e-3, "disc_d_m": probe["disc"]["d_mm"] * 1e-3,
             "C_el_true": probe["C_el"] * 1.3, "G_bond_true": 0.07, "G_leak_true": probe["G_leak_W_K"] * 1.5}
    cal_path = tmp / "cal.csv"
    fit.synth_log(cal_path, truth, 8.0e4, rng, paste=True, settle_s=0.01)
    L = fit.read_log(cal_path, 430.0)
    cal = fit.fit_calibration(L["t_r"], L["y"], L["t_tc"], L["tc"])
    pc = {**probe, "tau_int_s": cal["tau_int_s"]}
    out = {}
    for ds in ds_list:
        row = {}
        for h in (888.0, 1300.0):
            errs = []
            for rep in range(3):
                p = tmp / f"h{h:.0f}_{rep}.csv"
                fit.synth_log(p, truth, h, rng, settle_s=0.08, ref_extra_cool=ds)
                L = fit.read_log(p, 430.0)
                r = fit.fit_setdown(L["t_r"], L["y"], L["t_tc"], L["tc"], pc)
                errs.append(r["tau63_C1_s"] - fit.c1_tau63(h))
            row[f"h{h:.0f}_err_s"] = round(float(np.mean(errs)), 4)
        out[f"{ds:.3f}"] = row
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    return out


def main():
    rows, mism = {}, {}
    for pl, (k, rho, c) in PLATES.items():
        e = sqrt(k * rho * c)
        rows[pl] = {"effusivity_Ws05_m2K": round(e)}
        for dT in DT_CASES:
            worst_old = worst_in = 0.0
            for pan, (rct, kt) in PANS.items():
                for h in H_PP:
                    sl = radial_slopes(rct, kt, h, e, dT)
                    ds_old = sl[0.0] - sl[R_REF_OLD]   # reference cools faster -> positive
                    ds_in = sl[0.0] - sl[R_REF_IN]
                    rows[pl][f"dT{dT:.0f} | {pan} | h_pp {h:.0f}"] = {
                        "slope_contact_K_s": round(sl[0.0], 3), "ds_ref15mm_K_s": round(ds_old, 3),
                        "ds_ref6p5mm_K_s": round(ds_in, 3)}
                    worst_old = max(worst_old, abs(ds_old))
                    worst_in = max(worst_in, abs(ds_in))
            mism[(pl, dT)] = (round(worst_old, 3), round(worst_in, 3))
    ds_list = sorted({v for pair in mism.values() for v in pair} | {0.0})
    errs = tau_error(ds_list)
    verdict = {}
    for (pl, dT), (d_old, d_in) in mism.items():
        e_old = max(abs(v) for v in errs[f"{d_old:.3f}"].values())
        e_in = max(abs(v) for v in errs[f"{d_in:.3f}"].values())
        verdict[f"{pl} | dT {dT:.0f} K"] = {
            "ref_15mm": {"worst_ds_K_s": d_old, "worst_tau63_err_s": round(e_old, 4), "ok": e_old <= 0.05},
            "ref_6p5mm_in_bore": {"worst_ds_K_s": d_in, "worst_tau63_err_s": round(e_in, 4), "ok": e_in <= 0.05}}
    out = {"scope": __doc__.strip(), "plates": rows, "tau63_error_by_slope_mismatch": errs, "verdict": verdict,
           "acceptance": "worst |tau63_C1 error| from the plate gradient <= 0.05 s (the self-test tolerance)"}
    (HERE / "plate-check.json").write_text(json.dumps(out, indent=1) + "\n")
    for key, v in verdict.items():
        a, b = v["ref_15mm"], v["ref_6p5mm_in_bore"]
        print(f"{key:48s} ref 15 mm: ds {a['worst_ds_K_s']:6.3f} err {a['worst_tau63_err_s']:6.3f} "
              f"{'ok' if a['ok'] else 'NO'} | ref 6.5 mm: ds {b['worst_ds_K_s']:6.3f} "
              f"err {b['worst_tau63_err_s']:6.3f} {'ok' if b['ok'] else 'NO'}")


if __name__ == "__main__":
    main()
