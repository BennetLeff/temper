#!/usr/bin/env python3
"""ASSUMED coil/pan electrical basis for the native-21 tank (pre-measurement).

Every number is either (a) a digitized published chart value (outputs/digitized-*.csv),
(b) a value transcribed elsewhere in this repo with its source, or (c) an engineering
ESTIMATE, flagged as such in the `basis` field. Nothing here is a measurement of
Temper's coil or pans.

Model, per 40 kHz reference (turns-independent ratios, as coil_mc.rs uses):
  L_eq(f)   = L0 * kl40 * (f/40k)^beta                  (loaded series inductance)
  R_eq(f)   = L0 * q40 * (f/40k)^gamma                 (coil winding AC resistance)
            + L0 * r40 * (f/40k)^alpha                 (pan reflected resistance)
  L0 = no-pan coil inductance; kl40 = L_loaded/L0; r40, q40 in ohm per uH of L0.
For a fixed winding geometry L0, R_coil and R_reflected all scale as N^2, so the
ratios transfer between coils of the same geometry with different turn counts; they do
NOT transfer exactly between different geometries (diameter, ferrite, gap).

Writes outputs/basis.json, outputs/basis-table.csv, outputs/anchors.csv,
outputs/basis-vs-repo.csv.
"""
import csv
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "outputs")


def load(name):
    with open(os.path.join(OUT, name)) as fh:
        return list(csv.DictReader(fh))


def val(rows, series, f, key):
    for r in rows:
        if r["series"] == series and float(r["f_khz"]) == f and r[key] not in ("", "None"):
            return float(r[key])
    return None


def slope(y1, y2, f1, f2):
    return math.log(y2 / y1) / math.log(f2 / f1)


def anchors():
    ifx = load("digitized-infineon-fig16.csv")
    ons = load("digitized-onsemi-and9201.csv")
    a = []
    # Infineon EVAL-IHW25N140R5L kit coil + unnamed vessel (UG-2023-15 p.21 Fig. 16)
    L0 = val(ifx, "no_vessel", 40, "L_uH")
    Rno = val(ifx, "no_vessel", 40, "R_ohm")
    a.append({
        "anchor": "infineon_kit_vessel", "L0_uH": L0, "f_khz": 40,
        "kl40": val(ifx, "with_vessel", 40, "L_uH") / L0,
        "r40": (val(ifx, "with_vessel", 40, "R_ohm") - Rno) / L0, "q40": Rno / L0,
        "alpha_pan_30_50": slope(val(ifx, "with_vessel", 30, "R_ohm") - val(ifx, "no_vessel", 30, "R_ohm"),
                                 val(ifx, "with_vessel", 50, "R_ohm") - val(ifx, "no_vessel", 50, "R_ohm"), 30, 50),
        "gamma_coil_30_50": slope(val(ifx, "no_vessel", 30, "R_ohm"), val(ifx, "no_vessel", 50, "R_ohm"), 30, 50),
        "beta_kl_30_45": slope(val(ifx, "with_vessel", 30, "L_uH"), val(ifx, "with_vessel", 45, "L_uH"), 30, 45),
        "source": "Infineon UG-2023-15, EVAL-IHW25N140R5L user guide Rev 1.0 (2023-08-04), p.21 Fig. 16; digitized",
    })
    # onsemi AND9201/D (Rev 0, Jan 2015) p.7 Figs. 9-10, HP bridge, small signal
    L0 = val(ons, "no_pan", 40, "L_uH")
    Rno = {f: val(ons, "no_pan", f, "R_ohm") for f in (30, 40, 50)}
    for series, label in (("cast_iron", "onsemi_cast_iron"), ("five_ply_430_clad", "onsemi_5ply_430_clad"),
                          ("ss430_midea", "onsemi_430_ss"), ("ss304_duxtop", "onsemi_304_ss_duxtop"),
                          ("aluminium", "onsemi_aluminium")):
        L = val(ons, series, 40, "L_uH")
        R40 = val(ons, series, 40, "R_ohm")
        R30, R50 = val(ons, series, 30, "R_ohm"), val(ons, series, 50, "R_ohm")
        L30, L50 = val(ons, series, 30, "L_uH"), val(ons, series, 50, "L_uH")
        a.append({
            "anchor": label, "L0_uH": L0, "f_khz": 40,
            "kl40": None if L is None else L / L0,
            "r40": None if R40 is None else (R40 - Rno[40]) / L0, "q40": Rno[40] / L0,
            "alpha_pan_30_50": None if R30 is None or R50 is None else
            slope(R30 - Rno[30], R50 - Rno[50], 30, 50),
            "gamma_coil_30_50": slope(Rno[30], Rno[50], 30, 50),
            "beta_kl_30_45": None if L30 is None or L50 is None else slope(L30, L50, 30, 50),
            "source": "onsemi AND9201/D 'The Effect of Pan Material in an Induction Cooker', Rev 0 (Jan 2015), p.7 Figs. 9-10; digitized",
        })
    # 25 kHz values for the pans whose traces are hidden at 40 kHz (visible separation)
    for series, label in (("ss304_duxtop", "onsemi_304_ss_duxtop_25k"), ("ss430_midea", "onsemi_430_ss_20k")):
        f = 25 if "304" in series else 20
        L = val(ons, series, f, "L_uH")
        R = val(ons, series, f, "R_ohm")
        Rn, Ln = val(ons, "no_pan", f, "R_ohm"), val(ons, "no_pan", f, "L_uH")
        a.append({"anchor": label, "L0_uH": Ln, "f_khz": f, "kl40": None if L is None else L / Ln,
                  "r40": None if R is None else (R - Rn) / Ln * (40 / f) ** 0.62, "q40": Rn / Ln,
                  "alpha_pan_30_50": None, "gamma_coil_30_50": None, "beta_kl_30_45": None,
                  "source": f"onsemi AND9201/D p.7, read at {f} kHz where the trace is visible; "
                            "r scaled to 40 kHz with alpha=0.62 (calculation)"})
    # MDPI 180 mm study, Table 3, as transcribed in zapote/inverter/evidence/provisional-coil-pan-model.md
    # (not re-fetched: mdpi.com returned HTTP 403 on 2026-10-09). No-load L = 110 uH; the
    # study's own no-load coil R is not transcribed, so r is bracketed with the other coils' q.
    for name, L, R in (("mdpi_cast_iron", 89.76, 4.21), ("mdpi_stainless", 81.81, 3.36),
                       ("mdpi_silargan", 69.07, 2.48)):
        for qtag, q in (("qlo", 0.0024), ("qhi", 0.0041)):
            a.append({"anchor": f"{name}_{qtag}", "L0_uH": 110.0, "f_khz": None,
                      "kl40": L / 110.0, "r40": (R - q * 110.0) / 110.0, "q40": q,
                      "alpha_pan_30_50": None, "gamma_coil_30_50": None, "beta_kl_30_45": None,
                      "source": "MDPI Electronics 12(19):4145 (2023) Table 3, transcribed in repo; "
                                "frequency not transcribed; coil R bracketed by q (calculation)"})
    return a


# ---------------- the assumed basis ----------------
# (nominal, min, max). basis: "ANCHOR" = set from the anchors listed; "ESTIMATE" = judgement.
COIL = {
    "L0_uH": (70.0, 63.0, 77.0,
              "ESTIMATE: 70 uH is the native-21 design value (power-stage README; coil_mc.rs selected design); "
              "+/-10 % is the tolerance TANK_COIL_SPECIFICATION.md s.1 row 1 imposes on its 88 uH coil. No 70 uH "
              "coil is specified or measured."),
    "q40_ohm_per_uH": (0.0035, 0.0024, 0.0058,
                       "ANCHOR+ESTIMATE: onsemi no-pan coil 0.0024, Infineon kit coil 0.0041 (digitized, 40 kHz, "
                       "~25 C); max = TANK_COIL_SPECIFICATION row 5 ceiling 0.40 ohm/88 uH = 0.0045 x 1.29 for a "
                       "100 C winding (Cu +0.393 %/K x 75 K, calculation)"),
    "gamma_coil": (0.55, 0.52, 0.59, "ANCHOR: R_coil ~ f^gamma, onsemi 0.52, Infineon 0.59 over 30-50 kHz"),
    "beta_kl": (-0.13, -0.15, -0.11,
                "ANCHOR: L_loaded ~ f^beta, onsemi cast iron -0.15 (30-50 kHz), Infineon vessel -0.11 (30-45 kHz)"),
}

PANS = {
    "cast_iron": {
        "kl40": (0.69, 0.62, 0.84), "r40": (0.034, 0.029, 0.045), "alpha": 0.62,
        "basis": "ANCHOR kl: onsemi 0.66, Infineon vessel 0.68, MDPI 0.82; r: onsemi 0.035, Infineon 0.033, "
                 "MDPI 0.034-0.036. ESTIMATE: min r = lowest anchor -12 % (cold, small-signal, part spread); "
                 "max r = +30 % for a hot pan (iron resistivity rises with temperature; R_sheet ~ sqrt(rho*mu)); "
                 "kl min = lowest anchor -6 % for gap/centring."},
    "enamelled_steel": {
        "kl40": (0.66, 0.58, 0.78), "r40": (0.026, 0.018, 0.036), "alpha": 0.62,
        "basis": "ANCHOR: MDPI Silit Silargan (enamelled steel) kl 0.63, r 0.018-0.020; onsemi 430 kl 0.65. "
                 "ESTIMATE: nominal between the Silargan point and the ferritic-steel points; max r hot +30 %."},
    "ss1810_ferromagnetic_base": {
        "kl40": (0.71, 0.62, 0.80), "r40": (0.030, 0.024, 0.038), "alpha": 0.62,
        "basis": "ANCHOR: MDPI stainless kl 0.74, r 0.027-0.029; onsemi Duxtop 18/10 with magnetic base: R within "
                 "line width of cast iron at >=30 kHz, kl 0.73 at 25 kHz. ESTIMATE: ranges +/-15-25 %."},
    "thin_stainless_single_ply": {
        "kl40": (0.67, 0.58, 0.80), "r40": (0.030, 0.020, 0.040), "alpha": 0.62,
        "basis": "ANCHOR: onsemi Midea 430 kl 0.65, R within line width of cast iron at >=30 kHz. CALCULATION: "
                 "skin depth in ferritic 430 at 40 kHz is 0.07-0.2 mm for mu_r 100-700 (rho 0.6 uOhm.m), so a "
                 "0.5-1 mm base is electrically thick. ESTIMATE: low kl/r for warped or lifted thin bases. "
                 "Non-magnetic single-ply 18/10 is NOT in this class (treated as a detection/fault load)."},
    "aluminium_clad_multiply": {
        "kl40": (0.68, 0.60, 0.80), "r40": (0.027, 0.018, 0.034), "alpha": 0.80,
        "basis": "ANCHOR: onsemi 5-ply (430 exterior, Al core) r 0.030 at 40 kHz, alpha 0.80 (thin ferritic "
                 "layer); kl hidden under the ferrous traces (taken as ferrous). coil_mc.rs tri-ply GUESS "
                 "0.018-0.032 agrees. ESTIMATE: ranges."},
}
SUPPLEMENTAL = {
    "offset_or_small_pan_SYNTHETIC": {
        "kl40": (0.85, 0.80, 0.90), "r40": (0.017, 0.012, 0.022), "alpha": 0.62,
        "basis": "Carried unchanged from coil_mc.rs (synthetic half-coupling construction, no measured anchor)."},
}
FAULT_LOADS = {
    "no_pan": {"kl40": 1.0, "r40": 0.0, "alpha": 0.62,
               "basis": "Coil alone (definition)."},
    "aluminium_or_nonmagnetic_ss": {
        "kl40": 0.485, "r40": 0.0007, "alpha": 0.62,
        "basis": "ANCHOR: onsemi aluminium pan (kl 0.49, reflected R 0.08 ohm on 110 uH). Non-magnetic "
                 "single-ply 18/10 has no anchor; ESTIMATE: treated as this low-R, low-L load. Must be "
                 "rejected by pan detection, not heated."},
}

REPO_COIL_MC = {  # docs/hardware/power-section-120v/coil_mc.rs PANS (kl, r40) and the round-3/4 grid
    "cast_iron": ((0.74, 0.86), (0.036, 0.052)),
    "carbon_or_430_steel": ((0.66, 0.80), (0.029, 0.041)),
    "triply_clad_GUESS": ((0.66, 0.82), (0.018, 0.032)),
    "low_R_silargan_like": ((0.58, 0.68), (0.020, 0.029)),
    "offset_or_small_pan": ((0.80, 0.90), (0.012, 0.022)),
}
REPO_MAP = {"cast_iron": "cast_iron", "enamelled_steel": "low_R_silargan_like",
            "ss1810_ferromagnetic_base": "carbon_or_430_steel", "thin_stainless_single_ply": "carbon_or_430_steel",
            "aluminium_clad_multiply": "triply_clad_GUESS",
            "offset_or_small_pan_SYNTHETIC": "offset_or_small_pan"}

C_BANK_F = 0.54e-6


def corner(pan, which):
    i = {"nom": 0, "low": 1, "high": 2}[which]
    q = COIL["q40_ohm_per_uH"][i]
    return {"kl40": pan["kl40"][i], "r40": pan["r40"][i], "q40": q, "alpha": pan["alpha"]}


def eq(L0_uH, c, f):
    L = L0_uH * 1e-6 * c["kl40"] * (f / 40e3) ** COIL["beta_kl"][0]
    R = L0_uH * (c["q40"] * (f / 40e3) ** COIL["gamma_coil"][0] + c["r40"] * (f / 40e3) ** c["alpha"])
    return L, R


def fres(L0, c, C):
    f = 30e3
    for _ in range(60):
        L, _ = eq(L0, c, f)
        f = 1 / (2 * math.pi * math.sqrt(L * C))
    return f


def main():
    os.makedirs(OUT, exist_ok=True)
    anc = anchors()
    with open(os.path.join(OUT, "anchors.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(anc[0].keys()))
        w.writeheader()
        for r in anc:
            w.writerow({k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()})
    rows = []
    allpans = {**PANS, **SUPPLEMENTAL}
    for name, p in allpans.items():
        for which in ("nom", "low", "high"):
            c = corner(p, which)
            L40, R40 = eq(70, c, 40e3)
            L30, R30 = eq(70, c, 30e3)
            L60, R60 = eq(70, c, 60e3)
            rows.append({
                "pan_class": name, "corner": which, "kl40": c["kl40"], "r40_ohm_per_uH": c["r40"],
                "q40_ohm_per_uH": c["q40"], "alpha_pan": c["alpha"],
                "L_eq_40k_uH": round(L40 * 1e6, 2), "R_pan_40k_ohm": round(70 * c["r40"], 3),
                "R_eq_30k_ohm": round(R30, 3), "R_eq_40k_ohm": round(R40, 3), "R_eq_60k_ohm": round(R60, 3),
                "L_eq_30k_uH": round(L30 * 1e6, 2), "L_eq_60k_uH": round(L60 * 1e6, 2),
                "f_res_0.54uF_kHz": round(fres(70, c, C_BANK_F) / 1e3, 2),
                "Q_at_fres": round(2 * math.pi * fres(70, c, C_BANK_F) *
                                   eq(70, c, fres(70, c, C_BANK_F))[0] /
                                   eq(70, c, fres(70, c, C_BANK_F))[1], 1),
            })
    with open(os.path.join(OUT, "basis-table.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    # resonance extremes including coil L0 and capacitor tolerance (+/-10 %, 942C 'K')
    ext = []
    for name, p in allpans.items():
        lo = {"kl40": p["kl40"][1], "r40": p["r40"][1], "q40": COIL["q40_ohm_per_uH"][1], "alpha": p["alpha"]}
        hi = {"kl40": p["kl40"][2], "r40": p["r40"][2], "q40": COIL["q40_ohm_per_uH"][2], "alpha": p["alpha"]}
        ext.append({"pan_class": name,
                    "f_res_max_kHz (L0-10%, kl min, C-10%)": round(fres(63, lo, 0.9 * C_BANK_F) / 1e3, 2),
                    "f_res_nom_kHz": round(fres(70, corner(p, "nom"), C_BANK_F) / 1e3, 2),
                    "f_res_min_kHz (L0+10%, kl max, C+10%)": round(fres(77, hi, 1.1 * C_BANK_F) / 1e3, 2)})
    for name, p in FAULT_LOADS.items():
        c = {"kl40": p["kl40"], "r40": p["r40"], "q40": COIL["q40_ohm_per_uH"][0], "alpha": p["alpha"]}
        ext.append({"pan_class": name + " (fault/detection)",
                    "f_res_max_kHz (L0-10%, kl min, C-10%)": round(fres(63, c, 0.9 * C_BANK_F) / 1e3, 2),
                    "f_res_nom_kHz": round(fres(70, c, C_BANK_F) / 1e3, 2),
                    "f_res_min_kHz (L0+10%, kl max, C+10%)": round(fres(77, c, 1.1 * C_BANK_F) / 1e3, 2)})
    cmp_rows = []
    for name, p in allpans.items():
        rk = REPO_MAP[name]
        (klo, khi), (rlo, rhi) = REPO_COIL_MC[rk]
        cmp_rows.append({"basis_class": name, "repo_class": rk,
                         "basis_kl40": f"{p['kl40'][1]}-{p['kl40'][2]} (nom {p['kl40'][0]})",
                         "repo_kl": f"{klo}-{khi}",
                         "basis_r40": f"{p['r40'][1]}-{p['r40'][2]} (nom {p['r40'][0]})",
                         "repo_r40": f"{rlo}-{rhi}", "basis_alpha": p["alpha"], "repo_alpha": 0.5})
    with open(os.path.join(OUT, "basis-vs-repo.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cmp_rows[0].keys()))
        w.writeheader()
        w.writerows(cmp_rows)
    out = {"status": "ASSUMED / pre-measurement. No Temper coil or pan has been measured.",
           "model": __doc__.split("Model, per 40 kHz reference")[1].split("Writes")[0].strip(),
           "coil": {k: {"nom": v[0], "min": v[1], "max": v[2], "basis": v[3]} for k, v in COIL.items()},
           "pans": {k: {"kl40": dict(zip(("nom", "min", "max"), v["kl40"])),
                        "r40_ohm_per_uH": dict(zip(("nom", "min", "max"), v["r40"])),
                        "alpha": v["alpha"], "basis": v["basis"]} for k, v in allpans.items()},
           "fault_loads": FAULT_LOADS, "resonance_extremes_0.54uF": ext}
    with open(os.path.join(OUT, "basis.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    for r in anc:
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k != "source"})
    for r in rows:
        print(r)
    for e in ext:
        print(e)


if __name__ == "__main__":
    main()
