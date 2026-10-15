"""G7 field screen: conductive parts of the C1 cartridge in the coil eye, eddy heating at B 5-20 mT.

Methods are those of the R16/R32 screens (read-only):
- output/temper-manufacturing-r43/evidence/sensor-r16/thermal_screen.py: thin-disc low-frequency loss
  P = sigma w^2 B^2 pi t R^4 / 16 (used for the Pt film), skin-depth check.
- output/temper-r32-studies/06-emi-strayfield/ring_and_pickup.py: open helix P = sigma w^2 B^2 pi a^4 / 8 x wire
  length; open gap ring P = sigma w^2 B^2 t w^3 / 24 x 2 pi r; closed ring P = (w B pi r^2)^2 / (2 R).
B is the peak axial field, swept 5 / 10 / 20 mT (R16 sweep); f = 40 kHz (native-21), 60 kHz and 100 kHz (PCB band).
The study-06 FEM field at the eye (loops.json) is quoted for reference.
Also the lead-pair pickup inside the fused-silica capillary (untwisted over its length): only the radial field
B_r ~ (r/2) dBz/dz threads a loop in a plane through the axis; dBz/dz from the study-06 Z95/Z105 eye values.
And the geometric part of the gate: no conductive part inside r < 10 above the coil plane except the sensing
element and its leads (and the spring, which sits below the plane).
Run: python field_screen.py -> field-screen.json
"""
from __future__ import annotations

import json
import sys
from math import pi, sqrt
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cartridge_r3 as C  # noqa: E402
from build123d import Edge  # noqa: E402

D = C.DIM
MU0 = 4e-7 * pi
B_SWEEP = (0.005, 0.010, 0.020)
F_SWEEP = (40e3, 60e3, 100e3)
RHO = {"316": 7.4e-7, "A286": 9.1e-7, "Pt": 1.06e-7, "manganin": 4.8e-7}
STUDY06 = Path(__file__).resolve().parents[2] / "temper-r32-studies/06-emi-strayfield/loops.json"
COIL_PLANE_Z = 99.0 + 2.4 / 2           # r34_world Z_WIND: winding bundle centre plane
CONDUCTIVE = ("spring_A286", "wave_spring_A286", "Pt100_chip", "lead_capillary", "rim_NTC", "pigtail", "ntc_lead")


def helix_open(rho, w, B, a, length):
    return (1 / rho) * w ** 2 * B ** 2 * pi * a ** 4 / 8 * length


def gap_ring(rho, w, B, t, wd, r):
    return (1 / rho) * w ** 2 * B ** 2 * t * wd ** 3 / 24 * 2 * pi * r


def closed_ring(rho, w, B, r, area):
    V = w * B * pi * r ** 2
    R = rho * 2 * pi * r / area
    return V ** 2 / (2 * R)


def thin_disc(rho, w, B, t, R):
    return (1 / rho) * w ** 2 * B ** 2 * pi * t * R ** 4 / 16


def main():
    import tilt_follow
    n_act = tilt_follow.spring()["active_coils"]
    spring_len = (n_act + 1) * pi * D["spring_D"] * 1e-3
    a = D["spring_d"] / 2 * 1e-3
    rows = []
    for f in F_SWEEP:
        w = 2 * pi * f
        for B in B_SWEEP:
            rows.append(dict(f_kHz=f / 1e3, B_mT=B * 1e3,
                             spring_A286_open_helix_W=helix_open(RHO["A286"], w, B, a, spring_len),
                             spring_if_end_turn_closed_W=closed_ring(RHO["A286"], w, B, D["spring_D"] / 2 * 1e-3, pi * a ** 2),
                             wave_spring_A286_gap_ring_W=gap_ring(RHO["A286"], w, B, 0.2e-3, 2.0e-3, 20.35e-3),
                             Pt_film_disc_W=thin_disc(RHO["Pt"], w, B, 1e-6, 1.0e-3),
                             skin_depth_A286_mm=sqrt(2 * RHO["A286"] / (w * MU0)) * 1e3))
    worst = max(rows, key=lambda r: r["spring_A286_open_helix_W"])
    # spring temperature rise: wire surface to the sump air, h 15 W/m2K (enclosed natural convection + radiation,
    # ASSUMED); the end conduction along 85 mm of 0.5 mm wire adds < 0.1 mW/K and is ignored.
    g_spring = 15.0 * pi * D["spring_d"] * 1e-3 * spring_len
    dT = worst["spring_A286_open_helix_W"] / g_spring
    eye06 = json.loads(STUDY06.read_text())["bars|nopan|E_real|60k"]
    b_fem = eye06["B_eye_Z95_uT"] * 1e-6 * sqrt(2)                 # peak, at the spring top (Z95), no pan: worst
    p_fem = helix_open(RHO["A286"], 2 * pi * 60e3, b_fem, a, spring_len)
    p_wave_fem = gap_ring(RHO["A286"], 2 * pi * 60e3, b_fem, 0.2e-3, 2.0e-3, 20.35e-3)
    fem = {"B_peak_mT": round(b_fem * 1e3, 2), "f_kHz": 60, "spring_W": round(p_fem, 5), "spring_dT_K": round(p_fem / g_spring, 3),
           "wave_spring_W": round(p_wave_fem, 4)}
    # lead-pair pickup in the capillary
    eye = json.loads(STUDY06.read_text())
    case = eye["bars|nopan|E_real|60k"]
    dbz_dz = abs(case["B_eye_Z105_uT"] - case["B_eye_Z95_uT"]) * 1e-6 * sqrt(2) / 10e-3      # T/m, peak
    pitch = 0.30e-3
    length = (D["capillary_z"][1] - D["capillary_z"][0]) * 1e-3
    b_r = (pitch / 2 + pitch) / 2 * dbz_dz           # at the outer wire of the pair, r <= 0.45 mm
    emf = 2 * pi * 60e3 * b_r * pitch * length
    # geometric gate
    parts = C.r3_cartridge(D["proud"])
    axis = Edge.make_line((C.SX, C.SY, 50.0), (C.SX, C.SY, 120.0))
    geo = []
    for p in parts:
        if not any(k in p["name"] for k in CONDUCTIVE):
            continue
        bb = p["shape"].bounding_box()
        rin = p["shape"].distance_to(axis)
        above = bb.max.Z > COIL_PLANE_Z
        inside = rin < 10.0
        allowed = ("Pt100_chip" in p["name"]) or ("lead_capillary" in p["name"])
        geo.append(dict(part=p["name"], z_range=[round(bb.min.Z, 2), round(bb.max.Z, 2)], r_min=round(rin, 2),
                        inside_d20_above_coil_plane=inside and above, allowed_exception=allowed))
    geo_pass = all((not g["inside_d20_above_coil_plane"]) or g["allowed_exception"] for g in geo)
    out = {"scope": __doc__.strip(), "coil_plane_z": COIL_PLANE_Z, "rows": rows, "worst_spring_row": worst,
           "spring_G_W_per_K": round(g_spring, 5), "spring_dT_K_at_sweep_extreme": round(dT, 2),
           "at_study06_FEM_field": fem,
           "study06_eye_field_uT_rms": {k: round(case[k], 1) for k in ("B_eye_Z80_uT", "B_eye_Z95_uT", "B_eye_Z105_uT")},
           "capillary_pair_pickup": {"dBz_dz_T_per_m": round(dbz_dz, 4), "B_r_T": b_r, "loop_area_mm2": round(pitch * length * 1e6, 2),
                                     "emf_mV_at_60kHz": round(emf * 1e3, 4),
                                     "emf_mV_scaled_to_20mT_100kHz": round(emf * 1e3 * (0.020 / (case["B_eye_Z95_uT"] * 1e-6 * sqrt(2)))
                                                                           * (100e3 / 60e3), 4),
                                     "PCB_twisted_bound_mV": 6.6,
                                     "note": "straight (untwisted) over the capillary length because each wire has its own bore; "
                                             "the pair loop lies in a plane through the coil axis, so only B_r threads it"},
           "geometry": geo, "pass_geometry": geo_pass,
           "pass_heating": fem["spring_dT_K"] <= 2.0,
           "flag": ("At the 20 mT / 100 kHz sweep corner the spring would run %.1f K above its 192 C FV temperature, far inside "
                    "A-286's 538 C limit (Smalley materials table, R16 parts-research); at the study-06 FEM eye field it is "
                    "%.2f K. 316 was rejected: its 204 C relaxation limit leaves 12 K at the FV temperature." % (dT, p_fem / g_spring)),
           "notes": ["Pt film and manganin/Ni leads are the sensing element itself; listed as exceptions with their screen.",
                     "Spring sits Z81-96.6, below the coil plane (Z100.2); ends open (unground, unclosed) so no closed turn; "
                     "the closed-turn row shows what a touching end turn would cost.",
                     "Wave spring (R16/R32) is outside r10 and below the plane; its gap is held by the PEEK key."]}
    (HERE / "field-screen.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("worst_spring_row", "spring_dT_K_at_sweep_extreme", "at_study06_FEM_field", "capillary_pair_pickup", "pass_geometry",
                                          "pass_heating")}, indent=1))
    return out


if __name__ == "__main__":
    main()
