#!/usr/bin/env python3
"""AR-DESIGN computation: gate supply, bias-corrected Rds(on), coupled Tj, savings.

Method is explicit so a reviewer can re-derive every number.  Evidence classes
are attached to each input.  No bench work; no solver; pure arithmetic.

Governing relation (from the retained net-savings note, SECTION 3):
    P_saved = P_bridge - 225*(R_HS + R_LS) - P_additional
where 225 = I_rms^2 with I_rms = 15 A, and (R_HS + R_LS) are the two
conducting devices of the diagonal pair (one high side, one low side).

Outputs compute_result.json in the same directory.
"""
import json
import math

# ---------------------------------------------------------------- inputs
I_RMS = 15.0                     # A, contract (true RMS incl. ripple)
I2 = I_RMS ** 2                  # 225 A^2
P_BRIDGE = {"low": 23.0, "nominal": 28.3035, "high": 35.0}   # W, retained bracket

# TEA2209T (NXP, Rev 1.1, 2021-04-14) gate-supply constants
VCC_TYP, VCC_MIN, VCC_MAX = 10.7, 10.2, 11.2     # V, Vregd Table 8 p.10
VDBS_TYP, VDBS_MIN, VDBS_MAX = 1.0, 0.8, 1.3     # V, bootstrap diode Vd(bs) @1mA
ILEAK_TYP, ILEAK_MAX = 7e-6, 12e-6               # A, II(VCCHL) @VL=200V
T_ON = 8.333e-3                                  # s, half of a 60 Hz line cycle
CVCC = 2.2e-6                                    # F, datasheet typical config

# IPW60R017C7 (Infineon, Rev 2.0, 2016-03-01)
R25_10V_TYP = 0.015              # ohm, table p.5 (VGS=10V, ID=58.2A, Tj=25C)
R25_10V_MAX = 0.017              # ohm, table p.5 (guaranteed 25C maximum)
QG_TOT = 240e-9                  # C, table p.6 (0..10V, VDD=400V, ID=58.2A)
QG_PLATEAU_Q = 130e-9            # C at Vplateau=5.0V (Diagram 10, digitised)
QG_SLOPE = (QG_TOT - QG_PLATEAU_Q) / 5.0   # C per V above plateau

# Digitised Diagram 8 typ/98% (ID=58.2A, VGS=10V).  Calibrated against the
# p.5 table rows (25C 0.015, 150C 0.033).
D8_TYP = {25: 0.01517, 50: 0.01791, 75: 0.02115, 100: 0.02496,
          125: 0.02945, 145: 0.03363, 150: 0.0338}
D8_98 = {25: 0.0172, 50: 0.02031, 75: 0.02397, 100: 0.02737,
         125: 0.03339, 145: 0.0380, 150: 0.0387}
D8_TYP_25 = D8_TYP[25]

# Diagram 7 (Tj=125C) family ratio: Rds(8.5V)/Rds(10V) read at ID~21A.
# Digitised family at ID=21: [0.0339,0.0334,0.0330,0.0323,0.0320] for
# VGS = [6,6.5,7,10,20] -> Rds(7V)/Rds(10V)=1.020; 10V=0.0323.
# The IPW60R017C7 is near fully enhanced above ~7V, so the correction at the
# HS bias (typ 8.5V) is small; carry it as a factor with a stated bound.
F_VGS_HS = 1.020
F_VGS_HS_LO, F_VGS_HS_HI = 1.00, 1.07
F_VGS_LS = 1.00                  # LS VGS ~ VCC (>=10.2V): 10V data applies

# Proposed thermal assembly (bridge-cooling.md selected concept, TO-247 variant)
TA = 40.0                        # degC, design inlet air (contract 2026-09-14)
RSA = 0.50                       # K/W sink-to-air, total (catalog @500 LFM, typical)
RJC = 0.28                       # K/W junction-to-case MAX (IPW60R017C7 p.4)
RCS = 0.50                       # K/W case-to-sink per device (assumed; 0.25..1.0)
P_ADD_CONTROLLER = 0.003         # W controller + gate-drive (datasheet prose)


def interp(Tj, series):
    Ts = sorted(series)
    if Tj <= Ts[0]:
        return series[Ts[0]]
    if Tj >= Ts[-1]:
        return series[Ts[-1]]
    for a, b in zip(Ts, Ts[1:]):
        if a <= Tj <= b:
            return series[a] + (series[b] - series[a]) * (Tj - a) / (b - a)
    raise AssertionError


def k_of(Tj, series, t25):
    """Normalised temperature factor k_T(Tj) = Rds(Tj)/Rds(25C) for a series."""
    return interp(Tj, series) / t25


def vgs_high_side(vcc, vd, cbs, ileak):
    """Self-consistent HS gate-source voltage.

    The bootstrap cap is charged to (VCC - Vd) during the off half cycle; at
    turn-on it delivers Qg(VGS) and then leaks II(VCCHL) over the on-time.
    Solve  VGS = (VCC - Vd) - Qg(VGS)/Cbs - ileak*T_ON/Cbs.
    Qg(V) = QG_PLATEAU_Q + QG_SLOPE*(V - 5) for V > 5 V.
    """
    base = vcc - vd - ileak * T_ON / cbs
    x = 9.0
    for _ in range(200):
        qg = QG_PLATEAU_Q + QG_SLOPE * (x - 5.0)
        xn = base - qg / cbs
        if abs(xn - x) < 1e-9:
            x = xn
            break
        x = 0.5 * (x + xn)
    return x


def ls_vgs(vcc, n_gates_per_halfcycle=2):
    """LS gate sits at VCC minus the droop of CVCC over a half cycle."""
    q_per_half = n_gates_per_halfcycle * QG_TOT + 20e-6 * T_ON
    return vcc - q_per_half / CVCC


def solve_thermal(r_series, r25_ohm, f_hs, f_ls, rcs=RCS, rsa=RSA, p_add_dev=0.0):
    """Iterate Tj to convergence.  Returns dict with per-device detail.

    r_series is the digitised Rds(Tj) shape; r25_ohm is the absolute 25C anchor
    (table value for typ, 98% curve for the distributional upper case).
    """
    # seed
    Tj_hs = Tj_ls = 45.0
    for _ in range(200):
        k_hs = k_of(Tj_hs, r_series, r_series[25])
        k_ls = k_of(Tj_ls, r_series, r_series[25])
        R_hs = r25_ohm * k_hs * f_hs
        R_ls = r25_ohm * k_ls * f_ls
        P_hs = 0.5 * R_hs * I2 + p_add_dev / 2.0
        P_ls = 0.5 * R_ls * I2 + p_add_dev / 2.0
        P_tot = 2.0 * (P_hs + P_ls)          # both diagonals, line-cycle average
        T_sink = TA + P_tot * rsa
        n_hs = T_sink + P_hs * (RJC + rcs)
        n_ls = T_sink + P_ls * (RJC + rcs)
        if abs(n_hs - Tj_hs) < 1e-6 and abs(n_ls - Tj_ls) < 1e-6:
            Tj_hs, Tj_ls = n_hs, n_ls
            break
        Tj_hs, Tj_ls = n_hs, n_ls
    return {
        "Tj_hs_c": round(Tj_hs, 2), "Tj_ls_c": round(Tj_ls, 2),
        "T_sink_c": round(T_sink, 2), "R_hs_ohm": round(R_hs, 6),
        "R_ls_ohm": round(R_ls, 6), "P_hs_w": round(P_hs, 4),
        "P_ls_w": round(P_ls, 4), "P_total_w": round(P_tot, 4),
        "k_T_hs": round(k_hs, 4), "k_T_ls": round(k_ls, 4),
    }


def main():
    out = {"schema": "pfc-campaign-AR-DESIGN-compute/v1"}

    # ---- 1. gate supply -------------------------------------------------
    hs_vgs = {name: round(vgs_high_side(vcc, vd, cbs, il)
                         , 3)
              for name, (vcc, vd, cbs, il) in {
        "typ_220nF": (VCC_TYP, VDBS_TYP, 220e-9, ILEAK_TYP),
        "typ_200nF": (VCC_TYP, VDBS_TYP, 200e-9, ILEAK_TYP),
        "datasheet_min_100nF": (VCC_TYP, VDBS_TYP, 100e-9, ILEAK_TYP),
        "worstcase_100nF": (VCC_MIN, VDBS_MAX, 100e-9, ILEAK_MAX),
    }.items()}
    ls = {name: round(ls_vgs(vcc), 3) for name, vcc in
          {"typ": VCC_TYP, "min": VCC_MIN, "max": VCC_MAX}.items()}
    out["gate_supply"] = {
        "method": "VGS_HS solved self-consistently: (VCC-Vd) - Qg(VGS)/Cbs - I_leak*T_on/Cbs",
        "VCC_Vregd_v": {"typ": VCC_TYP, "min": VCC_MIN, "max": VCC_MAX},
        "Vd_bs_v": {"typ": VDBS_TYP, "min": VDBS_MIN, "max": VDBS_MAX},
        "Qg_total_c": QG_TOT,
        "hs_vgs_v": hs_vgs, "ls_vgs_v": ls,
        "conclusion": ("Vregd is the regulated VCC rail, NOT the MOSFET VGS. "
                       "Low side VGS ~ VCC (10.4-10.7V typ) so VGS=10V data applies; "
                       "high side VGS ~8.5V typ (bootstrap Vd + Qg/Cbs droop) so the "
                       "10V Rds(on) does NOT directly apply and is corrected by f_VGS_HS."),
        "f_vgs_hs": F_VGS_HS, "f_vgs_hs_bound": [F_VGS_HS_LO, F_VGS_HS_HI],
        "f_vgs_ls": F_VGS_LS,
        "evidence_class": "derived_from_manufacturer_datasheet_conditions",
    }

    # ---- 2. coupled thermal / hot Rds, typical ---------------------------
    typ = solve_thermal(D8_TYP, R25_10V_TYP, F_VGS_HS, F_VGS_LS)
    p98 = solve_thermal(D8_98, 0.0172, F_VGS_HS, F_VGS_LS)
    out["thermal_typical"] = {
        "assembly": {
            "Ta_c": TA, "Rjc_K_per_W": RJC, "Rcs_K_per_W": RCS,
            "Rsa_K_per_W_total": RSA,
            "basis": ("Ta and Rsa from the selected bridge cooling concept "
                      "(thermal/bridge-cooling.md, 2026-09-14); Rjc is the "
                      "IPW60R017C7 MAX; Rcs is an ASSUMED TO-247 contact/spreader "
                      "budget (0.25..1.0 K/W sensitivity)."),
            "evidence_class": "design_requirement_plus_assumed_contact",
        },
        "result": typ,
    }
    out["thermal_p98_sensitivity"] = {
        "note": "Diagram 8 98% curve; a distributional percentile, NOT a guaranteed maximum",
        "result": p98,
    }
    # Rcs / Rsa sensitivity
    out["thermal_sensitivity"] = {
        f"rcs_{r}_rsa_{s}": solve_thermal(D8_TYP, R25_10V_TYP, F_VGS_HS, F_VGS_LS,
                                          rcs=r, rsa=s)
        for r in (0.25, 1.0) for s in (0.50, 1.00)
    }

    # ---- 2b. commutation / start-up terms (step 4) ----------------------
    VSD = 0.9                     # V body-diode forward, typ @58.2A 25C (p.6)
    TD_MAX = 2.5e-6               # s zero-crossing comparator delay, max (Table 8 p.11)
    QRR_TYP = 18e-6               # C, @IF=58.2A, VR=400V, diF/dt=100A/us (p.6)
    F_LINE = 60.0
    P_GATE = (2 * QG_TOT * hs_vgs["typ_220nF"] * F_LINE
              + 2 * QG_TOT * ls["typ"] * F_LINE)
    # dead-time body-diode energy about a zero crossing, i_pk*sin(wt)~0:
    #   E = VSD * I_pk * w * td^2 / 2  per event, 2 events per line cycle
    I_PK = I_RMS * math.sqrt(2)
    W = 2 * math.pi * F_LINE
    E_DT = VSD * I_PK * W * TD_MAX ** 2 / 2.0
    P_DT = E_DT * 2 * F_LINE
    # recovery bound: worst case apply the full rated Qrr at a low residual
    # voltage (the commutation happens at the zero crossing): upper bound only
    E_RR_UB = QRR_TYP * 20.0      # J, assuming 20 V residual (generous)
    P_RR_UB = E_RR_UB * 2 * F_LINE
    out["additional_losses"] = {
        "controller_and_gate_drive": {
            "value_w": round(2e-3 + P_GATE, 5),
            "gate_component_w": round(P_GATE, 5),
            "evidence_class": "manufacturer_datasheet_prose_and_calculated",
            "basis": "TEA2209T 2 mW IC (Sec 2.1) + 4 gate charges/line cycle at line frequency",
        },
        "dead_time_body_diode": {
            "value_w": None, "upper_bound_w": round(P_DT, 8),
            "evidence_class": "derived_bound_from_datasheet_conditions",
            "basis": "TEA2209T td<=2.5us about a zero crossing; body diode VSD typ 0.9V",
        },
        "line_commutation_reverse_recovery": {
            "value_w": None, "upper_bound_w": round(P_RR_UB, 8),
            "evidence_class": "unknown_bounded_by_rated_Qrr",
            "basis": "IPW60R017C7 Qrr typ 18uC at IF=58.2A/VR=400V only; the real "
                     "commutation is at the line zero crossing (low i, low v), so the "
                     "18uC figure is an over-bound not the operating value",
        },
        "startup_inrush_body_diode": {
            "value_w": None, "evidence_class": "unknown",
            "basis": "NTC-limited inrush through the body diodes before VCC charges; "
                     "no inrush waveform or energy captured; no bench work permitted",
        },
        "emi_filter_obligation": {
            "value_w": None, "evidence_class": "unknown",
            "basis": "line-frequency MOSFET commutation changes the EMI picture; added "
                     "filter/snubber loss is not sourceable from the captured documents",
        },
        "quantified_p_additional_w": round(2e-3 + P_GATE + P_DT, 6),
    }

    # ---- 4. voltage contract / derived rating ---------------------------
    V_PEAK_132 = 132.0 * math.sqrt(2)      # 186.68 V
    out["voltage_contract"] = {
        "sourced": {
            "line_rms_v": [108.0, 120.0, 132.0],
            "line_peak_at_132vrms_v": round(V_PEAK_132, 2),
            "retained_bridge_vrrm_v": 1000,
            "retained_bridge_source": "GBU2510A (BOM.md: '1000 V / 25 A'); GBJ2510-F VRRM 1000 V (semiconductor-research.md)",
            "controller_node_limit_v": {"operating_max": 440, "transient_max": 700,
                                        "source": "TEA2209T Table 6/12: VR,L,R -0.4..440 V operating; "
                                                  "700 V mains transient, max 10 min over lifetime"},
            "declared_surge_clamp_in_bom": None,
        },
        "derived_rating_by_contract_variant": {
            "A_line_only_with_2x_margin": {"required_v_class": 400,
                "note": "186.7 V peak * 2 = 373 V"},
            "B_nxp_700V_transient_limit_binding": {"required_v_class": 800,
                "note": "device must block the node voltage the controller permits (<=700 V)"},
            "C_added_clamp_limits_node_to_500V": {"required_v_class": 600, "note": "requires a clamp not in the retained BOM"},
            "D_retained_bridge_equivalent_no_clamp": {"required_v_class": 1000,
                "note": "match the retained 1000 V bridge's implied design point"},
        },
        "reference_candidate_satisfies": ["C only (with an added clamp)"],
        "lower_voltage_alternative_status": "NOT SUPPORTED - a 500 V-class device satisfies only variant A (line-only), and fails the surge/transient variants B, C and D that the retained design implies",
    }

    # ---- 5. savings -----------------------------------------------------
    # rebuild absolute R from each solved case (already stored) and subtract
    p_add = out["additional_losses"]["quantified_p_additional_w"]

    def savings2(P_bridge, res, f_hs, f_ls):
        R_hs = res["R_hs_ohm"]
        R_ls = res["R_ls_ohm"]
        p_cond = I2 * (R_hs + R_ls)
        return p_cond, P_bridge - p_cond - p_add

    rows = []
    for label, res in (
        ("typical", typ),
        ("98pct", p98),
        ("typical_rcs1.0_rsa1.0", out["thermal_sensitivity"]["rcs_1.0_rsa_1.0"]),
    ):
        for b in ("low", "nominal", "high"):
            pc, ps = savings2(P_BRIDGE[b], res, F_VGS_HS, F_VGS_LS)
            rows.append({"basis": label, "bridge_w": round(P_BRIDGE[b], 3),
                         "p_cond_w": round(pc, 3), "p_saved_w": round(ps, 3)})
    out["savings"] = {
        "formula": "P_saved = P_bridge - 225*(R_HS + R_LS) - P_additional",
        "p_additional_w": p_add,
        "rows": rows,
    }

    with open("compute_result.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out["gate_supply"], indent=2))
    print("TYP:", json.dumps(typ))
    print("P98:", json.dumps(p98))
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
