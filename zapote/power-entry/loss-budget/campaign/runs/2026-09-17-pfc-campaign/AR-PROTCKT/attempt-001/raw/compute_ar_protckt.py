#!/usr/bin/env python3
"""AR-PROTCKT arithmetic record -- concrete protection circuit sizing (illustrative only).

This script performs CLOSED-FORM ARITHMETIC ONLY. It is not a solver, not a
maintained model, and not a claim of physical correctness. It exists so every
number in REPORT.md/result.json has a retained, re-runnable derivation and so
the assumed inputs are explicit.

Two fault classes, kept separate:
  (i)  line-fed switch short  -- AC mains fed, ms class, interrupter F1
  (ii) internal cap discharge -- DC bank fed, us class, interrupter candidate F2

For (ii) the internal loop is modelled as a series R-C discharge:
    i(t) = (V0/R) exp(-t/(R C))
This model ASSUMES an overdamped, non-inductive loop with a single lumped R.
AR-PROTECT's coordinator receipt explicitly warns the normal-device resistance
does not describe a destructive fault. The model is retained ONLY to show the
conditional structure; the prospective current is NOT established, so every
value derived from R_loop is labelled illustrative/assumed and kept null in
the ledger.

Outputs: raw/compute_result.json
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent

# --- frozen circuit constants (sourced) -------------------------------------
C_BANK_F = 2240.47e-6  # U36-U39 4x560uF + U40 470nF ; AR-FAULT netlist evidence
V_BUS_V = 400.0  # contract-C1.1 bus setpoint
P_NOMINAL_W = 1796.31003212911  # contract-C1.1 requested nominal input power

# --- candidate series interrupter: Eaton/Cooper Bussmann FWP-50A14F ----------
FWP_MELT_I2T_A2S = 200.0       # "Minimum Melting I2t", datasheet 720025
FWP_CLEAR_I2T_A2S = 1800.0     # "Clearing At Rated Voltage", datasheet 720025
FWP_DC_V_RATING = 800.0        # Vdc (5-50 A, non-striker)
FWP_DC_BREAKING_A = 50_000.0   # 50 kA at 800 Vdc
FWP_CONT_A = 50.0

# --- MOV: Littelfuse V150LA10AP (existing U7) -------------------------------
MOV_VC_MAX_50A = 395.0   # max clamping voltage at IPK=50A, 8/20us, 25C
MOV_ITM_8_20 = 4500.0    # A, 8/20us transient peak current
MOV_WTM_J = 45.0         # J, 10/1000us
FET_BLOCKING_V = 600.0   # active-bridge / boost FET class
CTRL_OP_LIMIT_V = 440.0  # TEA2209T operating limit
CTRL_TRANSIENT_V = 700.0

# --- existing line-side element F1 ------------------------------------------
F1_BREAKING_A = 160.0    # at 250 VAC (AR-FAULT coordinator receipt)
F1_MELT_I2T_A2S = 1638.0 # typical melting I2t at 10x rated (same source)


def main() -> None:
    E = 0.5 * C_BANK_F * V_BUS_V**2

    # Series R-C discharge, assumed. Compute per-R table for sensitivity.
    rows = []
    for R in (0.008, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 0.8962, 1.0, 2.0):
        i_pk = V_BUS_V / R
        tau = R * C_BANK_F
        action = E / R
        rows.append(
            {
                "r_loop_ohm": R,
                "prospective_peak_a": i_pk,
                "time_constant_s": tau,
                "time_constant_us": tau * 1e6,
                "action_i2t_a2s": action,
                "melts_fwp50": action >= FWP_MELT_I2T_A2S,
                "peak_within_fwp_breaking": i_pk <= FWP_DC_BREAKING_A,
            }
        )

    r_melt_max = E / FWP_MELT_I2T_A2S  # fuse melts iff R_loop <= this
    r_break_min = V_BUS_V / FWP_DC_BREAKING_A  # peak <= 50 kA iff R_loop >= this

    i_avg = P_NOMINAL_W / V_BUS_V
    i_peak_rect = (math.pi / 2.0) * i_avg

    out = {
        "schema": "pfc-campaign-AR-PROTCKT-compute/v1",
        "note": (
            "Illustrative closed-form arithmetic only. The series R-C model is "
            "NOT validated for a destructive fault and the loop resistance is "
            "NOT established; every R_loop-derived number is assumed/illustrative."
        ),
        "stored_energy": {
            "c_bank_f": C_BANK_F,
            "v_bus_v": V_BUS_V,
            "energy_j": E,
            "basis": "0.5*C*V^2, equal voltage across the parallel bank",
        },
        "pulse_model": {
            "waveform": "unidirectional decaying exponential i(t)=(V0/R)exp(-t/(R C))",
            "validity": "assumes an overdamped non-inductive loop with a single lumped R; unproven for a destructive short",
            "prospective_peak_formula": "V0/R",
            "action_i2t_formula": "(1/2) C V0^2 / R = E/R",
            "model_kind": "assumed_illustrative",
        },
        "series_rc_table": rows,
        "conditions": {
            "r_loop_for_melting_ohm_max": r_melt_max,
            "r_loop_for_breaking_ohm_min": r_break_min,
            "coordinated_window_ohm": [r_break_min, r_melt_max],
            "coordinated_window_note": (
                "IF r_break_min <= R_loop <= r_melt_max the fuse melts AND the "
                "prospective peak is within the fuse's DC breaking capacity. The "
                "window's EXISTENCE does not show R_loop lies in it, and does not "
                "show clearing at 400 Vdc for a capacitor-discharge waveshape."
            ),
        },
        "normal_operation": {
            "bus_current_avg_a": i_avg,
            "bus_current_peak_rectified_a": i_peak_rect,
            "fuse_continuous_rating_a": FWP_CONT_A,
            "fuse_continuous_margin": FWP_CONT_A / i_peak_rect,
            "note": "sizing basis for CONTINUOUS duty only; the fault pulse is the binding case",
        },
        "fuse_candidate": {
            "part": "FWP-50A14F",
            "manufacturer": "Eaton / Cooper Bussmann (Bussmann series)",
            "dc_voltage_rating_v": FWP_DC_V_RATING,
            "dc_breaking_capacity_a_at_800vdc": FWP_DC_BREAKING_A,
            "min_melting_i2t_a2s": FWP_MELT_I2T_A2S,
            "clearing_i2t_at_rated_voltage_a2s": FWP_CLEAR_I2T_A2S,
            "clearing_i2t_source_condition": (
                "tested at rated voltage and power factor 0.15 (AC/inductive); "
                "NOT a 400 Vdc capacitor-discharge condition"
            ),
            "coordination": "NOT_DEMONSTRATED",
            "coordination_reasons": [
                "prospective internal-loop peak current and action I2t are not established (loop impedance unknown)",
                "clearing I2t is published for an AC/inductive test, not a 400 Vdc capacitor discharge",
                "the let-through I2t is compared against no sourced withstand I2t for the capacitor bank or PCB copper",
            ],
        },
        "mov_candidate": {
            "part": "V150LA10AP",
            "manufacturer": "Littelfuse",
            "vc_max_at_50a_8_20us_v": MOV_VC_MAX_50A,
            "vc_at_50a_bound_direction": "upper bound at 50 A only; bounds no other current in either direction",
            "itm_8_20us_a": MOV_ITM_8_20,
            "wtm_10_1000us_j": MOV_WTM_J,
            "required_clamp_at_operating_surge_v": None,
            "required_clamp_resolution": (
                "read the LA Series Transient V-I curve at the actual MOV surge "
                "current; that current is not established, so the required clamp is null"
            ),
            "device_limits_to_respect_v": {
                "fet_blocking": FET_BLOCKING_V,
                "controller_operating": CTRL_OP_LIMIT_V,
                "controller_transient": CTRL_TRANSIENT_V,
            },
            "lpe_common_mode_clamped": False,
            "internal_discharge_loop_helped": False,
        },
        "line_side": {
            "existing_part": "F1, Schurter 0034.3129, 16 A time-lag, 250 VAC",
            "breaking_capacity_a_at_250vac": F1_BREAKING_A,
            "melting_i2t_at_10x_a2s": F1_MELT_I2T_A2S,
            "prospective_line_current_a": None,
            "coordination": "NOT_DEMONSTRATED",
        },
        "nulls": {
            "internal_loop_resistance_ohm": None,
            "internal_loop_peak_current_a": None,
            "internal_loop_action_i2t_a2s": None,
            "fuse_clearing_at_400vdc_cap_discharge": None,
            "line_fed_peak_current_a": None,
            "f1_total_clearing_at_matching_conditions": None,
            "mov_current_at_operating_surge_a": None,
            "mov_required_clamp_v": None,
        },
    }
    (HERE / "compute_result.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("stored_energy", "conditions")}, indent=2))


if __name__ == "__main__":
    main()
