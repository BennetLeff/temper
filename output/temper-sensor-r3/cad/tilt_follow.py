"""G5 tilt follow, spring range and wiper friction (hand calculations on the as-drawn C1 geometry).

1. Wiper lip load N (FFKM, no metal energiser). The installed lip is treated as the free edge of a thin cylinder
   on an elastic foundation (Timoshenko): line load P = w k_f / (2 beta), k_f = E t / r^2,
   beta^4 = 3 (1 - nu^2) / (r^2 t^2); N = 2 pi r P. A stiffer bound than a conical lip, so conservative for friction.
   E from Shore A by Gent's relation (Kalrez 6230 hardness 75 A: ASSUMED from the grade family, to confirm).
   Interference w from the drawing tolerances (lip ID 7.80 +/-0.04, neck OD 8.00 +/-0.01).
   Friction = mu N with mu 0.3 (HANDOFF) and, as a sensitivity, mu 1.0 (dry elastomer).
2. Spring: two-point load spec with tolerances, installed-length stack, stress, solid height.
3. Tilt follow: the pan, tilted 5 mrad to the glass, must rotate the post 5 mrad about the guide-pad pivot.
   Resisting moments about the pivot at 5 mrad (upper bounds): wiper friction mu N r (HANDOFF form), wiper radial
   stiffness, spring lateral stiffness at the seat (fixed-parallel-end formula, stiffer than the free cup), spring
   end tilt, pad friction, PTFE lead-sleeve bending, and pan friction at the face times the pivot depth (the face
   centre slides h*theta). The destabilising spring-follower moment (-F L theta) is ignored (conservative).
   The pan supplies this moment by shifting the contact pressure; the residual relative tilt is found from the
   same Yovanovich light-load law that contact_model.py uses: P(u) = (H/3.132) exp(-(u/(1.184 sigma))^(1/0.547))
   for local mean-plane separation u = Y0 + theta_r x, solving sum P = F and sum P x = M for (Y0, theta_r).
Run: python tilt_follow.py -> tilt-follow.json
"""
from __future__ import annotations

import json
import sys
from math import exp, log, pi, sqrt
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cartridge_r3 as C  # noqa: E402

D = C.DIM
PANS = json.loads((HERE.parent / "contact-model.json").read_text())["pans"]
FACE_RA = 0.1
PAN_TILT = 0.005
MU_HANDOFF, MU_DRY = 0.3, 1.0
MU_PAN = 0.3

# lip
SHORE_A, NU_LIP = 75.0, 0.49
LIP_T = D["wiper_lip_t"]
LIP_ID = (7.80, 0.04)
NECK_OD = (8.00, 0.01)
# spring (custom, A-286 wire): two-load spec
SPRING = dict(P1=1.30, P1_tol=0.08, P2=1.70, P2_tol=0.08, L1=D["spring_L1"], stroke=D["stroke_hard"],
              d=D["spring_d"], Dm=D["spring_D"], G=72e3, UTS=1400.0, L1_stack=0.05)


def gent_E(shore):
    return 0.0981 * (56 + 7.62336 * shore) / (0.137505 * (254 - 2.54 * shore))     # MPa


def lip_load(w_mm):
    E = gent_E(SHORE_A) * 1e6
    r, t = D["neck_ro"] * 1e-3, LIP_T * 1e-3
    beta = (3 * (1 - NU_LIP ** 2) / (r ** 2 * t ** 2)) ** 0.25
    kf = E * t / r ** 2
    P = w_mm * 1e-3 * kf / (2 * beta)
    return 2 * pi * r * P, (pi * r * kf / (2 * beta))                            # N, lateral stiffness N/m


def spring():
    s = SPRING
    k = (s["P2"] - s["P1"]) / s["stroke"]
    n = s["G"] * s["d"] ** 4 / (8 * s["Dm"] ** 3) / k
    L0 = s["L1"] + s["P1"] / k
    Fmin = s["P1"] - s["P1_tol"] - k * s["L1_stack"]
    Fmax = s["P2"] + s["P2_tol"] + k * s["L1_stack"]
    C_ = s["Dm"] / s["d"]
    Kw = (4 * C_ - 1) / (4 * C_ - 4) + 0.615 / C_
    tau = 8 * Fmax * s["Dm"] * Kw / (pi * s["d"] ** 3)
    solid = (n + 1) * s["d"]
    return dict(rate_N_mm=round(k, 4), active_coils=round(n, 2), free_length_mm=round(L0, 2), F_min_N=round(Fmin, 3),
                F_max_at_hard_stop_N=round(Fmax, 3), F_nominal_at_flush_N=round(s["P1"] + k * D["proud"], 3),
                shear_stress_MPa_at_Fmax=round(tau, 1), allowable_MPa_35pct_UTS=round(0.35 * s["UTS"], 1),
                solid_height_mm=round(solid, 2), length_at_hard_stop_mm=round(s["L1"] - s["stroke"], 2),
                L0_over_D=round(L0 / s["Dm"], 2), pass_force=(Fmin >= 1.2 and Fmax <= 1.8),
                pass_stress=tau <= 0.35 * s["UTS"], pass_solid=solid < s["L1"] - s["stroke"] - 1.0,
                basis="P1 at L1 (rest) and P2 at L1 - 2.2 (hard stop), each +/-0.08 N (100 % load-tested), L1 stack +/-0.05 mm; "
                      "G 72 GPa and UTS 1400 MPa for aged A-286 0.5 mm wire (typical; supplier to confirm)")


def contact_moment(pan, F, theta_r, n=60):
    """Return (force, moment) for separation Y0 solved so that force = F, at relative tilt theta_r."""
    sigma = 1.25e-6 * sqrt(FACE_RA ** 2 + pan["Ra"] ** 2)
    H = pan["H"] * 1e9
    R = (D["disc_r"] - D["disc_chamfer"]) * 1e-3
    xs = np.linspace(-R, R, n)
    X, Y = np.meshgrid(xs, xs)
    inside = X ** 2 + Y ** 2 <= R ** 2
    dA = (xs[1] - xs[0]) ** 2

    def press(Y0):
        u = Y0 + theta_r * (X + R)                       # touching edge at x = -R carries the smallest gap
        u = np.maximum(u, 1e-9)
        return H / 3.132 * np.exp(-(u / (1.184 * sigma)) ** (1 / 0.547)) * inside

    lo, hi = 0.0, 50 * sigma
    for _ in range(80):
        mid = (lo + hi) / 2
        f = press(mid).sum() * dA
        lo, hi = (mid, hi) if f > F else (lo, mid)
    p = press((lo + hi) / 2)
    return p.sum() * dA, -(p * X).sum() * dA


def residual_tilt(pan, F, M):
    lo, hi = 0.0, 0.01
    for _ in range(50):
        mid = (lo + hi) / 2
        _, m = contact_moment(pan, F, mid)
        lo, hi = (mid, hi) if m < M else (lo, mid)
    return (lo + hi) / 2


def main():
    sp = spring()
    w_min = (NECK_OD[0] - NECK_OD[1] - (LIP_ID[0] + LIP_ID[1])) / 2
    w_max = (NECK_OD[0] + NECK_OD[1] - (LIP_ID[0] - LIP_ID[1])) / 2
    N_min, _ = lip_load(w_min)
    N_max, k_lat_lip = lip_load(w_max)
    fric = {"mu_0.3": MU_HANDOFF * N_max, "mu_1.0_dry_sensitivity": MU_DRY * N_max}
    theta = PAN_TILT
    h_pivot = D["glass_top"] - D["z_pivot"]                # pivot depth under the face when the pan holds it flush
    d_lip = D["z_pivot"] - sum(D["wiper_lip"]) / 2
    z_seat = D["nose_zc"] - D["nose_R"] / sqrt(2) - D["proud"]
    L_seat = D["z_pivot"] - z_seat
    k_ax = sp["rate_N_mm"]
    k_lat_spring = k_ax / (0.204 * (D["spring_L1"] / D["spring_D"]) ** 2 + 0.265)     # fixed-parallel ends
    k_tilt_spring = k_ax * D["spring_D"] ** 2 / 8
    F_max, F_min = sp["F_max_at_hard_stop_N"], sp["F_min_N"]
    EI_sleeve = 0.5e3 * pi * (0.9 ** 4 - 0.5 ** 4) / 64     # N mm2, PTFE E 0.5 GPa
    L_sleeve = z_seat - 81.0
    M = {
        "wiper_friction_mu_N_r": MU_HANDOFF * N_max * D["neck_ro"],
        "wiper_radial": k_lat_lip * 1e-3 * (d_lip * theta) * d_lip,
        "spring_lateral_at_seat": k_lat_spring * (L_seat * theta) * L_seat,
        "spring_end_tilt": k_tilt_spring * theta,
        "pad_friction": MU_HANDOFF * (k_lat_spring * L_seat * theta) * D["neck_ro"],
        "lead_sleeve_bending": 6 * EI_sleeve * (L_seat * theta) / L_sleeve ** 2 + 4 * EI_sleeve * theta / L_sleeve,
        "pan_friction_x_pivot_depth": MU_PAN * F_max * h_pivot,
    }
    M_total = sum(M.values())
    M_dry = M_total - M["wiper_friction_mu_N_r"] + MU_DRY * N_max * D["neck_ro"]
    F_contact_min = F_min - MU_DRY * N_max                  # spring minus the largest friction
    rows = {}
    for name, pan in PANS.items():
        rows[name] = {"theta_r_mrad_handoff_mu": round(residual_tilt(pan, F_contact_min, M_total * 1e-3) * 1e3, 3),
                      "theta_r_mrad_dry_mu_1.0": round(residual_tilt(pan, F_contact_min, M_dry * 1e-3) * 1e3, 3)}
    worst = max(max(v.values()) for v in rows.values())
    out = {
        "scope": __doc__.strip(),
        "lip": {"E_MPa_gent": round(gent_E(SHORE_A), 2), "t_mm": LIP_T, "interference_mm": [round(w_min, 3), round(w_max, 3)],
                "N_N": [round(N_min, 3), round(N_max, 3)], "friction_N": {k: round(v, 3) for k, v in fric.items()},
                "pass_friction_le_0.3N": all(v <= 0.3 for v in fric.values()), "pass_contact_positive": w_min > 0},
        "spring": sp,
        "geometry_mm": {"pivot_depth_under_face": round(h_pivot, 3), "pivot_to_lip": round(d_lip, 3), "pivot_to_seat": round(L_seat, 3),
                        "pivot_within_1mm": h_pivot <= 1.0},
        "resisting_moments_Nmm_at_5mrad": {k: round(v, 4) for k, v in M.items()},
        "M_total_Nmm": round(M_total, 3), "M_total_dry_mu_Nmm": round(M_dry, 3),
        "righting_capacity_Nmm_F_min_x_r_contact": round(F_contact_min * (D["disc_r"] - D["disc_chamfer"]), 3),
        "F_contact_min_N": round(F_contact_min, 3),
        "residual_relative_tilt_by_pan": rows, "worst_residual_tilt_mrad": worst,
        "pass_G5": worst <= 2.0 and h_pivot <= 1.0,
    }
    (HERE / "tilt-follow.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("lip", "geometry_mm", "resisting_moments_Nmm_at_5mrad", "M_total_Nmm",
                                          "righting_capacity_Nmm_F_min_x_r_contact", "residual_relative_tilt_by_pan",
                                          "pass_G5")}, indent=1))
    print(json.dumps(sp, indent=1))
    return out


if __name__ == "__main__":
    main()
