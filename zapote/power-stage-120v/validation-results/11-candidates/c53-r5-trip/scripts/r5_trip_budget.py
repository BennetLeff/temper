#!/usr/bin/env python3
"""R5 hardware average-current trip: values, trip point and error budget (desk calculation).

    python3 -I validation-results/11-candidates/c53-r5-trip/scripts/r5_trip_budget.py [--json OUT]

Circuit (HOT5 domain, ground = ocp_kelvin_p): OPA333 inverting averager, IN- through RIN from the dedicated sense line to
R5's ocp_kelvin_n pad, RF || CF feedback, IN+ on ocp_kelvin_p. The Kelvin signal is NEGATIVE with respect to ocp_kelvin_p, so
VOUT = +(RF/RIN) x |V_R5|, low-passed at RF x CF. An open-collector LMV331 compares VOUT with a ref25 divider and, on a trip,
pulls HOT5_UV_RAW low (R50 pull-up to HOT5), exactly as U14's outputs do: wired-AND of the "OK" level, no gate in the OCP path.
With the comparator and averager not fitted the board is s52/s53 (nothing else is connected to those nets).
Inputs are the datasheet maxima I could cite from the scope studies (c53-line-current-f1/README.md A4); the op-amp and
comparator limits below are TO BE CONFIRMED against the datasheets in the ledger audit before a build.
"""
import argparse
import json
import math

R5 = 1e-3                  # ohm (CSS2H-2512R-1L00F), 1 % ; 75 ppm/K is in the Kelvin budget, not here
FORM = 0.9003              # mean / RMS for a sine envelope
GAIN_RIN, GAIN_RF = 10e3, 1e6
CF = 1e-6
VREF = 2.5                 # ref25 (LM4050A, 0.1 %)
RT, RB = 100e3, 100e3      # threshold divider (0603WAF1003T5E both)
I_HOLD = 13.5              # A total hold; power-stage share = (13.5 - I_aux) / 1.1
I_AUX = (0.26, 0.887)
TOL = dict(r5=0.01, ref=0.001, div=0.002, rin_rf=0.002)       # 0.1 % thin film pair, 1 % thick film divider pair worst
VOS_OPA = 10e-6            # OPA333 max (to confirm)
VOS_CMP = 7e-3             # LMV331 max (to confirm)
IB_CMP = 250e-9            # LMV331 max input bias (to confirm)
IB_OPA = 200e-12           # OPA333 max input bias (to confirm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    gain = GAIN_RF / GAIN_RIN
    vth = VREF * RB / (RT + RB)
    v_in = vth / gain
    i_mean = v_in / R5
    i_rms_eq = i_mean / FORM
    rth = RT * RB / (RT + RB)
    out = {
        "gain": gain, "tau_s": GAIN_RF * CF, "threshold_V": vth, "threshold_mean_mV_at_R5": v_in * 1e3,
        "trip_mean_A": i_mean, "trip_rms_equiv_A": i_rms_eq,
        "divider_load_uA_from_ref25": VREF / (RT + RB) * 1e6,
    }
    # errors referred to the trip current (relative)
    e_vos_cmp = VOS_CMP / vth
    e_ib_cmp = IB_CMP * rth / vth
    e_vos_opa = VOS_OPA * (1 + gain) / vth                 # noise gain 1 + RF/RIN ; also times (1+...) at DC through RF
    e_ib_opa = IB_OPA * GAIN_RF / vth
    worst = TOL["r5"] + TOL["ref"] + TOL["div"] + TOL["rin_rf"] + e_vos_cmp + e_ib_cmp + e_vos_opa + e_ib_opa
    rss = math.sqrt(sum(x * x for x in (TOL["r5"], TOL["ref"], TOL["div"], TOL["rin_rf"], e_vos_cmp, e_ib_cmp, e_vos_opa, e_ib_opa)))
    out["errors"] = {"R5": TOL["r5"], "ref25": TOL["ref"], "divider": TOL["div"], "RIN/RF": TOL["rin_rf"],
                     "LMV331 offset": e_vos_cmp, "LMV331 bias x Rth": e_ib_cmp, "OPA333 offset": e_vos_opa,
                     "OPA333 bias x RF": e_ib_opa, "sum_worst": worst, "rss": rss}
    # Kelvin loading by the sense line: current drawn from R5's ocp_kelvin_n pad at the trip point
    out["sense_line_current_uA"] = v_in / GAIN_RIN * 1e6
    out["sense_line_drop_uV_per_mohm_of_trace"] = out["sense_line_current_uA"] * 1e-6 * 1e-3 * 1e6
    # power-stage share limits
    # TRUE power-stage current (c53-line-current-f1/README.md A4): regulated maximum 13.5 - I_aux, and the value that makes
    # the 15.0 A plug total, 15.0 - I_aux (the firmware's own estimate carries a further 1.1 e_est factor; not used here)
    hold = [I_HOLD - x for x in I_AUX]
    cap = [15.0 - x for x in I_AUX]
    out["hold_I_ps_A"] = hold
    out["cap15_I_ps_A"] = cap
    out["margin_over_highest_hold_low_corner_pct"] = ((i_rms_eq * (1 - worst)) / max(hold) - 1) * 100
    out["margin_over_highest_hold_rss_pct"] = ((i_rms_eq * (1 - rss)) / max(hold) - 1) * 100
    out["under_15A_cap_high_corner_rss"] = i_rms_eq * (1 + rss) <= min(cap)
    out["under_15A_cap_high_corner_worst"] = i_rms_eq * (1 + worst) <= min(cap)
    for k, v in out.items():
        print(f"{k}: {v}")
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
