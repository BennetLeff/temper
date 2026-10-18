"""Dry contact conductance h_c between a sprung sensor face and a pan base.

At sensor spring loads (~1-2 N on ~50-65 mm2, P/H ~ 1e-5) solid-spot conduction
is negligible next to conduction across the air gap, so h_c is gap conductance:

    h(r, theta) = k_gas / (Y + M + g(r, theta))
    Y / sigma   = 1.184 * (-ln(3.132 P / H))**0.547     (Yovanovich light-load
                  mean-plane separation correlation, Song & Yovanovich 1987)
    M           = gas rarefaction parameter, air at ~150 C ~ 0.38 um
    g           = wedge gap from relative tilt phi between face and pan, zero at
                  the touching edge: g = phi * (R_face + r cos theta)
    sigma       = sqrt(sigma_face^2 + sigma_pan^2), sigma = 1.25 Ra

h_c is the area mean over the contact face (plus linearised radiation).
Inputs that are ASSUMPTIONS (bench survey replaces them): pan Ra and hardness by
cookware class, and the relative tilt. They are stated in PANS / TILTS below.

Run: python contact_model.py  -> contact-model.json
"""
from __future__ import annotations

import json
from math import cos, log, pi
from pathlib import Path

K_AIR_150C = 0.0241 * ((150 + 273.15) / 273.15) ** 0.81   # W/mK, air at 150 C
M_GAS = 0.38e-6
EPS_RAD = 0.5                     # face/pan effective emissivity pair (low effect)
T_RAD = 150 + 273.15

# Cookware classes (Ra in um, microhardness of the softer surface in GPa).
PANS = {
    "clad_polished_ss":  dict(Ra=0.2, H=2.5, thermal="triply_clad_24"),
    "disc_base_brushed": dict(Ra=0.6, H=2.5, thermal="disc_pot_water_1l5"),
    "carbon_steel":      dict(Ra=1.2, H=2.5, thermal="carbon_steel_28"),
    "cast_iron_machined": dict(Ra=1.6, H=2.0, thermal="cast_iron_26"),
    "cast_iron_as_cast": dict(Ra=6.0, H=2.0, thermal="cast_iron_26"),
    "enamel_cast_iron":  dict(Ra=0.4, H=5.0, thermal="cast_iron_26"),
}
# Relative tilt between face and pan base at the contact (rad). A pan resting on
# the glass is parallel to it at its centre unless warped; a rigid axial guide
# adds its own clearance tilt. 0 = ideal, 0.002 = typical, 0.005 = worst case.
TILTS = (0.0, 0.002, 0.005)

# Sensor faces. R_face = radius of the flat contact; Ra_face; F = spring force
# range at working compression (N); max_tilt = worst relative tilt the mount
# allows (R16: rigid plunger in a boot, so the full 5 mrad; sensor-r3: the post
# rocks about the face centre on its guide, so friction-limited 2 mrad: CAD gate G5).
FACES = {
    "R16 alumina cap (ground)": dict(R_face=4.5e-3, Ra=0.4, F=(0.79, 0.96), max_tilt=0.005),
    "sensor-r3 Si3N4 disc (lapped)": dict(R_face=3.8e-3, Ra=0.1, F=(1.2, 1.8), max_tilt=0.002),
}


def h_contact(face, pan, tilt, force, n_r=40, n_t=72):
    sigma = 1.25e-6 * (face["Ra"] ** 2 + pan["Ra"] ** 2) ** 0.5
    area = pi * face["R_face"] ** 2
    p_over_h = force / area / (pan["H"] * 1e9)
    Y = sigma * 1.184 * (-log(3.132 * p_over_h)) ** 0.547
    h_rad = 4 * EPS_RAD * 5.67e-8 * T_RAD ** 3
    tot = 0.0
    for i in range(n_r):
        r = (i + 0.5) / n_r * face["R_face"]
        dA = 2 * pi * r * face["R_face"] / n_r / n_t
        for j in range(n_t):
            th = 2 * pi * (j + 0.5) / n_t
            g = tilt * (face["R_face"] + r * cos(th))
            tot += K_AIR_150C / (Y + M_GAS + g) * dA * n_t
    return tot / area / n_t * 1.0 + h_rad, Y


def table():
    out = {}
    for fname, face in FACES.items():
        rows = {}
        for pname, pan in PANS.items():
            hs = {}
            for tilt in (t for t in TILTS if t <= face["max_tilt"]):
                lo = h_contact(face, pan, tilt, face["F"][0])[0]
                hs[f"{tilt:g}"] = round(lo, 0)
            rows[pname] = {"thermal_pan": pan["thermal"], "h_c_by_tilt": hs,
                           "Y_um_at_Fmin": round(h_contact(face, pan, 0.0, face["F"][0])[1] * 1e6, 2)}
        out[fname] = rows
    return out


def main():
    res = {"scope": __doc__.strip(), "k_air_W_mK": round(K_AIR_150C, 4), "M_um": M_GAS * 1e6,
           "pans": PANS, "tilts_rad": TILTS, "faces": FACES, "h_c_W_m2K": table()}
    Path(__file__).with_name("contact-model.json").write_text(json.dumps(res, indent=1) + "\n")
    for fname, rows in res["h_c_W_m2K"].items():
        print(fname)
        for p, r in rows.items():
            print(f"  {p:20s} Y={r['Y_um_at_Fmin']:6.2f} um  h_c by tilt {r['h_c_by_tilt']}")


if __name__ == "__main__":
    main()
