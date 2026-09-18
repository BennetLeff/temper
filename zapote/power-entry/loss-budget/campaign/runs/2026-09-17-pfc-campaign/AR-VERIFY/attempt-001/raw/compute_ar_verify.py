#!/usr/bin/env python3
"""AR-VERIFY computation: corrected claims, bootstrap corners, per-point Rds, surge.

This is a *correction and extension* of AR-DESIGN's retained script, not a new
design.  It reads the retained digitisation of the IPW60R017C7 datasheet figures
(`reused_sources/digitized_ipw60r017c7.json`) and re-derives:

  1. the four downgraded claims, re-labelled (fail loud if a superseded number is
     reintroduced);
  2. the bootstrap capacitor corners (charge / discharge / leakage / droop) with
     Rds(on) derived PER POINT from the digitised Rds(VGS) family, not one factor;
  3. the surge / protection contract and the terminal voltages from which BOTH
     the MOSFET's required rating and the controller's node stresses follow;
  4. the revised P_saved across the 23 / 28.30 / 35 W bracket.

Evidence classes are attached to every input.  No bench work, no procurement,
no solver.  Every figure is labelled typical / sensitivity / bound.

Writes `compute_result.json` beside this file.
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIGITISED = json.loads((HERE / "reused_sources" / "digitized_ipw60r017c7.json").read_text())

# ------------------------------------------------------------------ inputs
I_RMS = 15.0
I2 = I_RMS ** 2                                     # 225 A^2
P_BRIDGE = {"low": 23.0, "nominal": 28.3035, "high": 35.0}
F_LINE = 60.0
T_ON = 1.0 / (2.0 * F_LINE)                         # 8.333 ms, one conduction half-cycle

# TEA2209T Rev 1.1 (captured, sha256 fb611299...).  Table 8 / Table 6 / Sec 12.
VCC = {"min": 10.2, "typ": 10.7, "max": 11.2}       # Vregd, Table 8 p.10
VDBS = {"min": 0.8, "typ": 1.0, "max": 1.3}         # table, guaranteed min/max
ILEAK_200V = {"min": 4e-6, "typ": 7e-6, "max": 12e-6}   # II(VCCHL) @VL=200V
ILEAK_0V = {"min": 1.4e-6, "typ": 1.8e-6, "max": 2.5e-6}  # @VL=0V
VDD_FLOAT_UVLO_MAX = 5.0                            # V, guaranteed max, Table 8
CVCC = {"nominal": 2.2e-6, "min_allowed": 1.0e-6}   # Sec 12 typical range 1..2.2 uF
CBS_CANDIDATES = {"100nF": 100e-9, "200nF": 200e-9, "220nF": 220e-9}

# IPW60R017C7 Rev 2.0 (captured, sha256 2c5a60a2...).
R25_10V_TYP = 0.015                                 # Table 4 p.5
R25_10V_MAX = 0.017                                 # Table 4 p.5 guaranteed max
QG_TOT = 240e-9                                     # Table 6 p.6, 0..10 V
QG_PLATEAU = 130e-9                                 # Diagram 10 digitised, at Vplateau
QG_SLOPE = (QG_TOT - QG_PLATEAU) / 5.0              # C per V above the plateau
IGSS_MAX = 100e-9                                   # Table 4 p.5, 100 nA
V_BR_DSS_MIN = 600.0                                # Table 4 p.5

# Assembly (design requirement + assumed contact), unchanged from AR-DESIGN so
# the correction is isolated to the four claims and the gate derivation.
TA = 40.0
RSA = 0.50
RJC = 0.28
RCS = 0.50

D8_TYP = {int(k): v for k, v in DIGITISED["diagram_8_typ_ohm_vs_Tj"].items()}
D8_P98 = {int(k): v for k, v in DIGITISED["diagram_8_p98_ohm_vs_Tj"].items()}
D7_ALL = {int(k): list(v) for k, v in DIGITISED["diagram_7_rds_family_vs_ID_at_125C_ohm"].items()}
# Rows with <5 stroke runs are digitisation artefacts (merged curves at ID 45/120),
# not a VGS family; excluded rather than mis-labelled.
D7 = {k: v for k, v in D7_ALL.items() if len(v) >= 5}
# Diagram 7 caption labels the VGS family 5.5, 6, 6.5, 7, 10, 20 V.  Some ID
# columns digitised only 5 stroke runs because adjacent curves merge; AR-DESIGN
# read those as [6, 6.5, 7, 10, 20].  The 5-value rows are treated as a
# sensitivity only; ID=30 A carries the full family and is the primary.
VG_LADDER_6 = [5.5, 6.0, 6.5, 7.0, 10.0, 20.0]
VG_LADDER_5 = [6.0, 6.5, 7.0, 10.0, 20.0]


def interp(x, series):
    xs = sorted(series)
    if x <= xs[0]:
        return series[xs[0]]
    if x >= xs[-1]:
        return series[xs[-1]]
    for a, b in zip(xs, xs[1:]):
        if a <= x <= b:
            return series[a] + (series[b] - series[a]) * (x - a) / (b - a)
    raise AssertionError


def k_of(tj, series):
    return interp(tj, series) / series[25]


# --------------------------------------------------- Diagram 7 VGS family
def family_ratios(id_key):
    """Rds(VGS)/Rds(10 V) at Tj=125 C, ID=id_key, from the digitised family."""
    # Stored order is DESCENDING R over ASCENDING VGS (captured JSON note:
    # "list is descending R; VGS order 5.5,6,6.5,7,10,20 V").
    vals = D7[id_key]
    ladder = VG_LADDER_6 if len(vals) == 6 else VG_LADDER_5
    raw = dict(zip(ladder, vals))
    assert raw[ladder[0]] > raw[ladder[-1]], "unexpected Diagram 7 ordering"
    r10 = raw[10.0]
    return {v: raw[v] / r10 for v in raw}


D7_PRIMARY = family_ratios(30)
D7_SENS = {k: family_ratios(k) for k in D7}


def ratio_at(vgs, ratios):
    return interp(vgs, ratios)


# --------------------------------------------------- bootstrap gate supply
def qg(vgs):
    if vgs <= 5.0:
        return QG_PLATEAU
    return QG_PLATEAU + QG_SLOPE * (vgs - 5.0)


def solve_hs_vgs(vcc, vd, cbs, ileak, qg_scale=1.0):
    """VGS = (VCC-Vd) - Qg(VGS)/Cbs - (I_leak + I_gss)*T_on/Cbs, self-consistent."""
    base = vcc - vd - (ileak + IGSS_MAX) * T_ON / cbs
    x = 9.0
    for _ in range(1000):
        xn = base - qg_scale * qg(x) / cbs
        if abs(xn - x) < 1e-12:
            return xn
        x = 0.5 * (x + xn)
    return x


def solve_ls_vgs(vcc, cvcc, qg_scale=1.0):
    """LS gate sits at VCC minus the CVCC droop of one LS gate charge plus the
    recharge of one HS bootstrap cap over one half-cycle (2 * Qg), plus bias."""
    droop = (2.0 * qg_scale * QG_TOT + 20e-6 * T_ON) / cvcc
    return vcc - droop


# --------------------------------------------------- coupled thermal
def solve_thermal(series, r25, f_hs, f_ls, rcs=RCS, rsa=RSA):
    tj_hs = tj_ls = 45.0
    t_sink = TA
    r_hs = r_ls = 0.0
    for _ in range(500):
        r_hs = r25 * k_of(tj_hs, series) * f_hs
        r_ls = r25 * k_of(tj_ls, series) * f_ls
        p_hs = 0.5 * r_hs * I2
        p_ls = 0.5 * r_ls * I2
        p_tot = 2.0 * (p_hs + p_ls)
        t_sink = TA + p_tot * rsa
        n_hs = t_sink + p_hs * (RJC + rcs)
        n_ls = t_sink + p_ls * (RJC + rcs)
        if abs(n_hs - tj_hs) < 1e-9 and abs(n_ls - tj_ls) < 1e-9:
            tj_hs, tj_ls = n_hs, n_ls
            break
        tj_hs, tj_ls = n_hs, n_ls
    return {
        "T_sink_c": round(t_sink, 2), "Tj_hs_c": round(tj_hs, 2), "Tj_ls_c": round(tj_ls, 2),
        "R_hs_ohm": round(r_hs, 6), "R_ls_ohm": round(r_ls, 6),
        "P_hs_w": round(0.5 * r_hs * I2, 4), "P_ls_w": round(0.5 * r_ls * I2, 4),
        "P_total_w": round(I2 * (r_hs + r_ls), 4),
        "k_T_hs": round(k_of(tj_hs, series), 4),
    }


def main():
    out = {"schema": "pfc-campaign-AR-VERIFY-compute/v1"}

    # ------------------------------------------------ 1. corrected claims
    p_dev_typ = 0.5 * R25_10V_TYP * I2              # 25 C, VGS 10 V: 0.5*R*I^2
    out["corrected_claims"] = {
        "a_per_device_thermal_power": {
            "correct_value_w": round(p_dev_typ, 4),
            "statement": ("Per-device line-cycle-average conduction is 0.5*R*I_rms^2 "
                          "(each of four devices conducts half the line cycle), "
                          "= 0.5*0.015*225 = 1.6875 W at Rds(25C,10V) typ; at the "
                          "computed hot Rds it is ~1.96-2.28 W. The superseded 3.91 W "
                          "divided a two-device instantaneous total by two."),
            "superseded_value_w": 3.91,
            "superseded_source": "AR-DESIGN coordinator-receipt v1 (withdrawn)",
        },
        "b_worst_bracket_98pct_saving": {
            "worst_bracket_w": 23.0,
            "note": "98% curve saving at the WORST bracket point; see savings rows",
            "superseded_value_w": 26.0,
            "superseded_source": ("~26 W quoted the 35 W bracket point as if it were "
                                  "the worst; 25.98 W is the BEST bracket point"),
        },
        "c_gate_correction": {
            "f_vgs_hs": {
                "status": "ASSUMED constant in AR-DESIGN, now DERIVED per point",
                "superseded_value": 1.020,
                "basis": "digitised Diagram 7 family at ID=30 A, Tj=125 C",
            },
            "f_vgs_ls": {
                "status": ("INVALID as 1.000 at AR-DESIGN's own 9.91 V LS minimum; "
                           "now derived per point from the same family"),
                "superseded_value": 1.00,
                "ls_min_v": 9.906,
            },
        },
        "d_recovery": {
            "superseded_label": "E_RR_UB (upper bound)",
            "correct_label": "SENSITIVITY",
            "statement": ("typical Qrr (18 uC) times an ASSUMED 20 V residual, "
                          "x 2 events/line-cycle; not a guaranteed maximum, so not a bound"),
        },
        "e_voltage_table": {
            "superseded": ("mixed the controller's 700 V node limit (a component "
                           "limit) with the MOSFET's required rating (both directions: "
                           "'700 V requires 800 V device' AND 'higher-V device protects "
                           "controller')"),
            "correct": ("the MOSFET rating follows from the surge-clamped terminal "
                        "voltage it must block; the controller's node stress follows "
                        "from the same terminal voltages compared against its OWN "
                        "440 V operating / 700 V transient limits; neither dictates "
                        "the other"),
        },
    }

    # ------------------------------------------------ 2. bootstrap corners
    hs = {}
    for cname, cbs in CBS_CANDIDATES.items():
        hs[cname] = {
            "typ": solve_hs_vgs(VCC["typ"], VDBS["typ"], cbs, ILEAK_200V["typ"]),
            "guaranteed_min_vcc_vd_leak_typ_qg": solve_hs_vgs(
                VCC["min"], VDBS["max"], cbs, ILEAK_200V["max"]),
            "qg_sensitivity_x1.3": solve_hs_vgs(
                VCC["min"], VDBS["max"], cbs, ILEAK_200V["max"], qg_scale=1.3),
            "qg_sensitivity_x1.5": solve_hs_vgs(
                VCC["min"], VDBS["max"], cbs, ILEAK_200V["max"], qg_scale=1.5),
            "leakage_droop_guaranteed_v": round(ILEAK_200V["max"] * T_ON / cbs, 4),
            "charge_time_constant_note": (
                "recharge is over the 8.33 ms off half-cycle; with any plausible "
                "internal bootstrap impedance (<<30 kohm) the RC is <1 ms, so charge "
                "completeness is not the binding constraint"),
        }
    ls = {}
    for cvcc_name, cvcc in CVCC.items():
        for vcc_name, vcc in VCC.items():
            ls[f"{cvcc_name}_cvcc_{vcc_name}_vcc"] = round(solve_ls_vgs(vcc, cvcc), 4)
    out["bootstrap"] = {
        "method": ("HS: solve VGS = (VCC-Vd) - Qg(VGS)/Cbs - (I_leak+I_gss)*T_on/Cbs "
                   "self-consistently. LS: VCC - (2*Qg + I_bias*T_on)/Cvcc."),
        "T_on_s": T_ON,
        "discharge_terms": ["Qg(VGS)", "II(VCCHL) quiescent over T_on", "IGSS (100 nA max)",
                            "reverse leakage of the internal bootstrap diode while it "
                            "blocks the line (NOT SPECIFIED in the captured datasheet)"],
        "hs_vgs_v": {k: {kk: (round(vv, 3) if isinstance(vv, float) else vv)
                         for kk, vv in v.items()} for k, v in hs.items()},
        "ls_vgs_v": ls,
        "worst_case_gate_voltage": {
            "value_v": round(hs["220nF"]["guaranteed_min_vcc_vd_leak_typ_qg"], 3),
            "capacitor": "220 nF",
            "basis": ("VCC>=10.2 V, Vd(bs)<=1.3 V and II(VCCHL)<=12 uA are guaranteed "
                      "maxima from TEA2209T Table 8; Qg is TYPICAL only, so this is a "
                      "CONDITIONAL worst case, NOT a guaranteed bound"),
            "boundable_part": ("leakage droop >= 12 uA*8.333 ms/220 nF = 0.455 V, "
                               "Vd <= 1.3 V, VCC >= 10.2 V; the Qg/Cbs term cannot be "
                               "bounded from a typical Qg"),
            "functional_floor_v": VDD_FLOAT_UVLO_MAX,
        },
        "chosen_capacitor": "220 nF",
        "justification": (
            "220 nF is at the top of NXP's own 100-220 nF range (Sec 12) and is "
            "essentially the 200 nF value NXP shows in its typical configuration. "
            "Relative to 100 nF it cuts the guaranteed leakage droop from 1.000 V to "
            "0.455 V and lifts the typical-Qg conditional worst case from 6.31 V to "
            "7.59 V, which is above the ~7 V near-full-enhancement knee of Diagram 7 "
            "(3.0% vs 1.4% Rds penalty). The recharge cost is nil (RC < 1 ms in an "
            "8.33 ms half-cycle). This is a ROBUSTNESS choice, not a proof that 100 nF "
            "fails: from typical Qg it takes ~2.2x Qg to reach the 5.0 V floating "
            "UVLO with 100 nF and ~5.8x with 220 nF, because Qg has no published "
            "maximum. The datasheet's own warning against low bootstrap values "
            "(Sec 12) plus NXP's own 200 nF configuration is the basis for the top of "
            "the range."),
        "evidence_class": ("guaranteed_limits_plus_typical_Qg; Qg-bound is ASSUMED/"
                           "sensitivity, not a guaranteed bound"),
    }

    # ------------------------------------------------ 3. per-point Rds
    vgs_points = {
        "hs_typ_220nF": hs["220nF"]["typ"],
        "hs_conditional_worst_220nF": hs["220nF"]["guaranteed_min_vcc_vd_leak_typ_qg"],
        "hs_min_datasheet_100nF": hs["100nF"]["typ"],
        "hs_conditional_worst_100nF": hs["100nF"]["guaranteed_min_vcc_vd_leak_typ_qg"],
        "ls_typ_2.2uF": solve_ls_vgs(VCC["typ"], CVCC["nominal"]),
        "ls_min_2.2uF": solve_ls_vgs(VCC["min"], CVCC["nominal"]),
        "ls_min_1.0uF": solve_ls_vgs(VCC["min"], CVCC["min_allowed"]),
    }
    per_point = {
        name: {"vgs_v": round(v, 3), "ratio_vs_10v": round(ratio_at(v, D7_PRIMARY), 5)}
        for name, v in vgs_points.items()
    }
    per_point_sensitivity = {
        name: {f"ID_{k}A": round(ratio_at(v, fam), 5) for k, fam in D7_SENS.items()}
        for name, v in vgs_points.items()
    }
    out["per_point_rds"] = {
        "primary_family": {"ID_a": 30, "Tj_c": 125, "ratios_vs_10v": D7_PRIMARY},
        "method": ("Rds(Tj, VGS) = Rds10(Tj) * [Rds(VGS)/Rds(10 V)] where Rds10(Tj) is "
                   "the digitised Diagram 8 curve and the ratio is the digitised "
                   "Diagram 7 family. ASSUMPTION: the VGS ratio is temperature-"
                   "independent over the 45-51 C range (Diagram 7 is only at 125 C)."),
        "points": per_point,
        "id_current_sensitivity": per_point_sensitivity,
    }

    f_hs_t = per_point["hs_typ_220nF"]["ratio_vs_10v"]
    f_ls_t = per_point["ls_typ_2.2uF"]["ratio_vs_10v"]
    f_hs_w = per_point["hs_conditional_worst_220nF"]["ratio_vs_10v"]
    f_ls_w = per_point["ls_min_2.2uF"]["ratio_vs_10v"]
    f_hs_100 = per_point["hs_min_datasheet_100nF"]["ratio_vs_10v"]
    f_ls_1u = per_point["ls_min_1.0uF"]["ratio_vs_10v"]

    # ------------------------------------------------ 4. thermal + savings
    rows_basis = {
        "typical": (D8_TYP, R25_10V_TYP, f_hs_t, f_ls_t, RCS, RSA),
        "p98_percentile_VGS_typ": (D8_P98, 0.0172, f_hs_t, f_ls_t, RCS, RSA),
        "typical_VGS_worst_conditional": (D8_TYP, R25_10V_TYP, f_hs_w, f_ls_w, RCS, RSA),
        "p98_VGS_worst_conditional": (D8_P98, 0.0172, f_hs_w, f_ls_w, RCS, RSA),
        "typical_100nF_worst_conditional": (D8_TYP, R25_10V_TYP, f_hs_100, f_ls_1u, RCS, RSA),
        "typical_rcs1.0_rsa1.0": (D8_TYP, R25_10V_TYP, f_hs_t, f_ls_t, 1.0, 1.0),
    }
    thermal = {}
    for name, (series, r25, fh, fl, rcs, rsa) in rows_basis.items():
        thermal[name] = solve_thermal(series, r25, fh, fl, rcs=rcs, rsa=rsa)

    # additional losses (line-frequency gate drive) with per-point gate voltages
    p_gate = (2 * QG_TOT * vgs_points["hs_typ_220nF"] * F_LINE
              + 2 * QG_TOT * solve_ls_vgs(VCC["typ"], CVCC["nominal"]) * F_LINE)
    p_ic = 2e-3
    v_sd = 0.9
    i_pk = I_RMS * math.sqrt(2)
    w = 2 * math.pi * F_LINE
    td = 2.5e-6
    p_dt = v_sd * i_pk * w * td ** 2 / 2.0 * 2 * F_LINE
    qrr_typ = 18e-6
    residual_assumed_v = 20.0
    p_rr_sensitivity = qrr_typ * residual_assumed_v * 2 * F_LINE
    p_additional = p_ic + p_gate + p_dt

    out["additional_losses"] = {
        "controller_ic_w": p_ic,
        "gate_network_w": round(p_gate, 6),
        "dead_time_body_diode_bound_w": round(p_dt, 8),
        "quantified_p_additional_w": round(p_additional, 6),
        "recovery_sensitivity_w": round(p_rr_sensitivity, 4),
        "recovery_label": ("SENSITIVITY: typical Qrr 18 uC x ASSUMED 20 V residual x 2 "
                           "events/line-cycle; the real commutation is at the zero "
                           "crossing, so neither factor is a guaranteed maximum"),
        "unknowns_not_subtracted": ["line-commutation reverse recovery (sensitivity only)",
                                    "start-up/inrush body-diode energy", "added EMI filter loss"],
    }

    savings_rows = []
    for name, res in thermal.items():
        for b, pbr in P_BRIDGE.items():
            p_cond = I2 * (res["R_hs_ohm"] + res["R_ls_ohm"])
            savings_rows.append({
                "basis": name, "bridge_w": round(pbr, 3),
                "p_cond_w": round(p_cond, 3),
                "p_saved_w": round(pbr - p_cond - p_additional, 3),
            })
    out["thermal"] = thermal
    out["savings"] = {
        "formula": "P_saved = P_bridge - 225*(R_HS + R_LS) - P_additional",
        "p_additional_w": round(p_additional, 6),
        "note": ("P_saved is an upper-side estimate: unknown losses (recovery, inrush, "
                 "EMI) are NOT subtracted because they are unknown, not zero"),
        "rows": savings_rows,
        "worst_bracket_98pct_w": next(r["p_saved_w"] for r in savings_rows
                                      if r["basis"] == "p98_percentile_VGS_typ"
                                      and r["bridge_w"] == 23.0),
    }

    # ------------------------------------------------ 5. surge / protection
    v_peak_132 = 132.0 * math.sqrt(2)
    # MOV clamp is UNCAPTURED (Littelfuse 403 twice).  Assumed here, labelled.
    v_clamp_mov_assumed = 400.0
    v_bus = 400.0
    out["surge_contract"] = {
        "test_level": {
            "standard": "IEC 61000-4-5",
            "line_to_line_v": 1000.0,
            "line_to_pe_v": 2000.0,
            "waveform": "1.2/50 us voltage, 8/20 us current (combination wave)",
            "source": "docs/architecture/induction_curriculum.md:2112 (project checklist)",
            "second_source": ("IEC 60335-1 OVC II rated impulse 1500 V on a 120 V "
                              "mains-derived board: docs/evidence/2026-08-13-mains-selv-"
                              "barrier-derivation.md:15-20"),
            "evidence_class": "project_requirement_not_measured_not_datasheet",
            "assumption_flag": ("the released product's real test level is not a "
                                "committed requirement document; the curriculum line is "
                                "a checklist item.  Treat as the ASSUMED contract."),
        },
        "protection_circuit": {
            "specified": ["fuse -> MOV across L-N -> X2 (L-N) -> CMC -> Y caps (L-PE, N-PE)",
                          "MOV: Littelfuse V150LA10AP, 150 V rms MCOV, line-to-neutral "
                          "(the main board carries it; the power-entry candidate BOM does NOT)"],
            "required_addition": ("the power-entry candidate BOM lists no MOV; the surge "
                                  "derivation is therefore conditional on adding the "
                                  "L-N MOV shown in docs/hardware/BOM.md:46"),
            "mov_clamp_assumed_v": v_clamp_mov_assumed,
            "mov_clamp_status": ("ASSUMED - no primary datasheet captured (two 403s "
                                 "retained in raw/capture_failures.json); the repo's own "
                                 "IEC60335 critical-components audit also marks this part "
                                 "UNVERIFIED (secondary-source only)"),
            "would_settle_it": ("a captured Littelfuse LA-series V-I / clamp-voltage "
                                "characteristic at 8/20 us, or a measured clamp"),
        },
        "terminal_voltages": {
            "steady_off_device_blocks_v": round(v_peak_132, 2),
            "surge_with_mov_terminal_v": v_clamp_mov_assumed,
            "surge_without_mov": ("INDETERMINATE - the surge source impedance and the "
                                  "bus-capacitor clamp are not captured; no rating derivable"),
            "bus_fault_boost_switch_short_v": round(v_bus + v_peak_132, 2),
        },
        "mosfet_required_rating": {
            "from_surge_with_mov_v": v_clamp_mov_assumed,
            "chosen_class_v": 600,
            "margin": {"steady": round(600 / v_peak_132, 2),
                       "surge": round(600 / v_clamp_mov_assumed, 2),
                       "bus_fault": round(600 / (v_bus + v_peak_132), 2)},
            "statement": ("the required rating follows from the TERMINAL voltage the off "
                          "device must block (surge-clamped L-N ~400 V assumed), NOT from "
                          "the controller's 700 V node limit"),
        },
        "controller_node_stresses": {
            "operating_limit_v": 440.0,
            "transient_limit_v": 700.0,
            "surge_clamped_node_v": v_clamp_mov_assumed,
            "statement": ("L/R/VR see the same MOV-clamped line voltage (~400 V assumed) "
                          "against their OWN 440 V operating limit; a higher-rated MOSFET "
                          "does NOT lower this node voltage, and the controller's 700 V "
                          "transient allowance does NOT require an 800/1000 V device"),
        },
        "line_to_pe_common_mode": ("not clamped by the L-N MOV; the controller and bridge "
                                   "common-mode stress depends on the Y-cap / PE / "
                                   "dc-return network, which is NOT captured - "
                                   "INDETERMINATE"),
    }

    # ------------------------------------------------ 6. disagreements
    out["conflicts_found"] = {
        "mov_part": ("docs/specs/REQUIREMENTS.md:511 says 'MOV: 275V, 10kA' but the "
                     "committed BOM is V150LA10AP (150 V rms MCOV) and the board is "
                     "120 V single-market (docs/evidence/2026-08-13-...:22).  A 275 V "
                     "MOV would not clamp at the 186.7 V line peak; a 150 V MCOV part "
                     "is the plausible one."),
        "surge_level": ("the curriculum checklist (1 kV L-L / 2 kV L-PE) is not repeated "
                        "in docs/specs/REQUIREMENTS.md, whose EMC section lists filter "
                        "parts but no surge test level."),
    }

    (HERE / "compute_result.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out["corrected_claims"], indent=2))
    print(json.dumps(out["bootstrap"]["worst_case_gate_voltage"], indent=2))
    print(json.dumps(out["per_point_rds"]["points"], indent=2))
    for r in out["savings"]["rows"]:
        print(r)
    print("worst_bracket_98pct_W:", out["savings"]["worst_bracket_98pct_w"])
    print("p_additional_W:", out["additional_losses"]["quantified_p_additional_w"])


if __name__ == "__main__":
    main()
