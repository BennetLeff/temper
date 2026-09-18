#!/usr/bin/env python3
"""AR-COORD arithmetic record -- fuse coordination envelope (illustrative only).

Closed-form + quadrature arithmetic for ONE question: does a candidate fuse's
rating cover (1) the normal pulsed boost-diode current on an RMS basis, and
(2) a defensible internal-capacitor-discharge fault-impedance envelope?

This is NOT a solver and NOT a qualified prediction. It computes, for a series
R-L-C discharge of the retained bus bank:

    L di/dt + R i + (1/C) int i dt = 0,  i(0)=0, v_c(0)=V0

  * peak current  i_pk(R, L)
  * total action  integral_0^inf i^2 dt = E / R   (exact energy balance,
    E = 1/2 C V0^2, *given* a single lumped R and no arc / no other loss)
  * damping regime, and the discharge timescale
  * whether a candidate reaches its published PRE-ARCING I2t (melt screen)
  * whether the prospective peak sits inside a published DC breaking capacity

The model ASSUMES a constant single lumped resistance, a fixed inductance, no
arc and no evolving short residual. Those assumptions are the reason every
R-derived value is illustrative and the reason clearing is NOT concluded.

Outputs: raw/compute_result.json
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent

# --- frozen, sourced constants ---------------------------------------------
C_BANK_F = 2240.47e-6        # 4x560uF (U36-U39) + 470nF (U40); AR-FAULT netlist
V_BUS_V = 400.0              # contract-C1.1 bus setpoint
E_J = 0.5 * C_BANK_F * V_BUS_V**2  # 179.2376 J

# Diode RMS from the retained maintained model (R0 report.json), worst line first.
DIODE_RMS_A = {
    "108": 8.538992639857435,
    "120": 9.000670972612259,
    "132": 8.586780852007614,
}
P_NOMINAL_W = 1796.31003212911
I_BUS_AVG_A = P_NOMINAL_W / V_BUS_V

# --- candidates (<=3, dispatch max_candidate_parts) -------------------------
# Datasheet-derived. FWP ratings identical between the retained 2011-2014 rev
# and the 2023 Eaton spec-sheet capture EXCEPT the DC voltage/breaking pair.
CANDIDATES = {
    "FWP-50A14F": {
        "manufacturer": "Eaton / Bussmann",
        "rated_current_a": 50.0,
        "min_melting_i2t_a2s": 200.0,      # retained + current rev agree
        "clearing_i2t_a2s": 1800.0,        # AC/inductive, rated voltage, pf 0.15
        "dc_voltage_current_rev_v": 700.0,  # 2023 Eaton spec sheet
        "dc_voltage_retained_rev_v": 800.0, # 2011-2014 catalogue page
        "dc_breaking_a_current_rev": 50_000.0,   # 50 kA @ 700 Vdc
        "dc_breaking_a_retained_rev": 50_000.0,  # 50 kA @ 800 Vdc
        "watts_loss_rated_w": 9.0,
        "capacitor_discharge_rating": None,  # NOT published in either capture
    },
    "FWP-25A14F": {
        "manufacturer": "Eaton / Bussmann",
        "rated_current_a": 25.0,
        "min_melting_i2t_a2s": 46.5,
        "clearing_i2t_a2s": 375.0,
        "dc_voltage_current_rev_v": 700.0,
        "dc_voltage_retained_rev_v": 800.0,
        "dc_breaking_a_current_rev": 50_000.0,
        "dc_breaking_a_retained_rev": 50_000.0,
        "watts_loss_rated_w": 7.0,
        "capacitor_discharge_rating": None,
    },
    "A70QS50-14F": {
        "manufacturer": "Mersen / Ferraz Shawmut",
        "rated_current_a": 50.0,
        "min_melting_i2t_a2s": 280.0,      # 0.28 x 10^3 A2s, Advisor 2017
        "clearing_i2t_a2s": 1500.0,        # 1.50 x 10^3 @ 700 VAC
        "dc_voltage_current_rev_v": 700.0,
        "dc_voltage_retained_rev_v": None,
        "dc_breaking_a_current_rev": 100_000.0,  # 100 kA DC, L/R <= 10-11.6 ms
        "dc_breaking_a_retained_rev": None,
        "watts_loss_rated_w": 11.6,
        "capacitor_discharge_rating": {
            "dc_voltage_v": 890.0,
            "max_time_constant_ms": 2.5,
            "source": "Mersen High Speed Fuses catalogue, A70QS French Cylindrical",
        },
    },
}

# --- assumed (NOT measured) envelope axes -----------------------------------
R_SWEEP_OHM = [0.005 * (10 ** (i / 4.0)) for i in range(0, 25)]   # 5 mOhm .. 5 Ohm
L_SWEEP_H = [2.0e-8 * (10 ** (i / 5.0)) for i in range(0, 16)]    # 20 nH .. ~6.3 uH

TWO_PI = 2.0 * math.pi


def discharge_current(t: float, r: float, l: float) -> float:
    """i(t) for a series R-L-C discharge from v_c(0)=V0, i(0)=0."""
    alpha = r / (2.0 * l)
    w0sq = 1.0 / (l * C_BANK_F)
    disc = alpha * alpha - w0sq
    if disc > 0.0:  # overdamped
        beta = math.sqrt(disc)
        return (V_BUS_V / (beta * l)) * math.exp(-alpha * t) * math.sinh(beta * t)
    if disc < 0.0:  # underdamped
        w = math.sqrt(-disc)
        return (V_BUS_V / (w * l)) * math.exp(-alpha * t) * math.sin(w * t)
    return (V_BUS_V / l) * t * math.exp(-alpha * t)  # critical


def peak_current(r: float, l: float) -> tuple[float, float, str]:
    alpha = r / (2.0 * l)
    w0sq = 1.0 / (l * C_BANK_F)
    disc = alpha * alpha - w0sq
    if disc > 0.0:
        beta = math.sqrt(disc)
        t_pk = math.atanh(beta / alpha) / beta
        return discharge_current(t_pk, r, l), t_pk, "overdamped"
    if disc < 0.0:
        w = math.sqrt(-disc)
        t_pk = math.atan(w / alpha) / w
        return discharge_current(t_pk, r, l), t_pk, "underdamped"
    t_pk = 1.0 / alpha
    return discharge_current(t_pk, r, l), t_pk, "critical"


def cumulative_action_time(r: float, l: float, target_a2s: float) -> float | None:
    """First time the running integral of i^2 reaches target (Simpson)."""
    alpha = r / (2.0 * l)
    # Cover the slower of the R*C and 2L/R timescales with margin.
    tau_rc = r * C_BANK_F
    tau_rl = 2.0 * l / r
    t_max = 20.0 * max(tau_rc, tau_rl, 1.0e-7)
    n = 20000
    if n % 2:
        n += 1
    dt = t_max / n
    total = 0.0
    prev = discharge_current(0.0, r, l)
    for k in range(1, n + 1, 2):
        f1 = discharge_current(k * dt, r, l)
        f2 = discharge_current((k + 1) * dt, r, l)
        total += (dt / 3.0) * (prev * prev + 4.0 * f1 * f1 + f2 * f2)
        if total >= target_a2s:
            # linear refinement within this pair of intervals
            frac = target_a2s / total if total > 0 else 0.0
            return (k + 1) * dt * frac
        prev = f2
    return None


def main() -> None:
    env = []
    for r in R_SWEEP_OHM:
        for l in L_SWEEP_H:
            ipk, tpk, regime = peak_current(r, l)
            env.append(
                {
                    "r_ohm": r,
                    "l_h": l,
                    "regime": regime,
                    "peak_a": ipk,
                    "t_peak_s": tpk,
                    "total_action_a2s": E_J / r,   # exact: E/R
                    "tau_rc_s": r * C_BANK_F,
                }
            )

    # melt screen per candidate: R <= E / I2t_melt  (L-independent, adiabatic)
    melt = {}
    for name, c in CANDIDATES.items():
        rm = E_J / c["min_melting_i2t_a2s"]
        melt[name] = {
            "min_melting_i2t_a2s": c["min_melting_i2t_a2s"],
            "r_melt_max_ohm": rm,
            "melts_for_all_r_below_ohm": rm,
            "time_to_melt_at_r06_ohm_s": cumulative_action_time(0.6, 5.0e-6, c["min_melting_i2t_a2s"]),
        }

    # clearing screen: only A70QS carries a published capacitor-discharge rating.
    cap_env = []
    if (cd := CANDIDATES["A70QS50-14F"]["capacitor_discharge_rating"]) is not None:
        r_tau = cd["max_time_constant_ms"] * 1e-3 / C_BANK_F
        for r in R_SWEEP_OHM:
            for l in L_SWEEP_H:
                ipk, _, _ = peak_current(r, l)
                cap_env.append(
                    {
                        "r_ohm": r,
                        "l_h": l,
                        "peak_a": ipk,
                        "melts": r <= E_J / CANDIDATES["A70QS50-14F"]["min_melting_i2t_a2s"],
                        "tau_rc_within_rating": r * C_BANK_F <= cd["max_time_constant_ms"] * 1e-3,
                        "voltage_within_rating": V_BUS_V <= cd["dc_voltage_v"],
                        "peak_within_100ka": ipk <= CANDIDATES["A70QS50-14F"]["dc_breaking_a_current_rev"],
                    }
                )

    # independent limits as oracles for the model itself
    oracle = {}
    r0, l0 = 1.0e-4, 1.0e-7  # zero-ish R probe
    ipk, _, _ = peak_current(r0, l0)
    z0 = math.sqrt(l0 / C_BANK_F)
    oracle["lossless_peak_should_approach_V0_over_Z0"] = {
        "computed_peak_a": ipk,
        "V0_over_Z0_a": V_BUS_V / z0,
        "rel_err": abs(ipk - V_BUS_V / z0) / (V_BUS_V / z0),
    }
    ipk2, _, _ = peak_current(2.0, 1.0e-12)
    oracle["large_R_small_L_peak_should_approach_V0_over_R"] = {
        "computed_peak_a": ipk2,
        "V0_over_R_a": V_BUS_V / 2.0,
        "rel_err": abs(ipk2 - V_BUS_V / 2.0) / (V_BUS_V / 2.0),
    }
    # energy balance numeric check at one point
    r_c, l_c = 0.05, 5.0e-6
    t_end = 20.0 * max(r_c * C_BANK_F, 2.0 * l_c / r_c)
    n = 40000
    dt = t_end / n
    acc = 0.0
    prev = discharge_current(0.0, r_c, l_c)
    for k in range(1, n + 1, 2):
        f1 = discharge_current(k * dt, r_c, l_c)
        f2 = discharge_current((k + 1) * dt, r_c, l_c)
        acc += (dt / 3.0) * (prev * prev + 4.0 * f1 * f1 + f2 * f2)
        prev = f2
    oracle["action_integral_should_equal_E_over_R"] = {
        "r_ohm": r_c,
        "numeric_action_a2s": acc,
        "E_over_R_a2s": E_J / r_c,
        "rel_err": abs(acc - E_J / r_c) / (E_J / r_c),
    }

    # normal-current RMS basis
    normal = {}
    for name, c in CANDIDATES.items():
        worst_line = max(DIODE_RMS_A, key=lambda k: DIODE_RMS_A[k])
        rms = DIODE_RMS_A[worst_line]
        normal[name] = {
            "worst_line_v": float(worst_line),
            "diode_rms_a": rms,
            "rated_current_a": c["rated_current_a"],
            "percent_of_rated": 100.0 * rms / c["rated_current_a"],
            "continuous_margin_ratio": c["rated_current_a"] / rms,
        }

    out = {
        "schema": "pfc-campaign-AR-COORD-compute/v1",
        "note": (
            "Illustrative closed-form/quadrature arithmetic only. The series R-L-C "
            "model assumes one constant lumped R, a fixed L, no arc and no evolving "
            "short residual. Loop R and L are NOT measured, so peak/action are "
            "illustrative; clearing is NOT concluded."
        ),
        "stored_energy": {"c_bank_f": C_BANK_F, "v_bus_v": V_BUS_V, "energy_j": E_J},
        "normal_current_rms_basis": {
            "basis": "RMS of the boost-diode current; Eaton's own loss correction Kp is a function of RMS load current (retained FWP sheet, p.207)",
            "diode_rms_by_line_a": DIODE_RMS_A,
            "bus_average_a": I_BUS_AVG_A,
            "average_is_not_a_sizing_basis": True,
            "per_candidate": normal,
            "startup_inrush": None,
            "temperature_derating_factor": None,
            "repetitive_pulse_note": (
                "switching period 1/129107 Hz = 7.75 us << fuse element thermal "
                "time constant, so the repetitive pulses merge thermally; RMS is the "
                "correct heating basis and the average (4.49 A) is not."
            ),
        },
        "fault_impedance_envelope": {
            "assumed_r_ohm": [R_SWEEP_OHM[0], R_SWEEP_OHM[-1]],
            "assumed_l_h": [L_SWEEP_H[0], L_SWEEP_H[-1]],
            "assumption_note": (
                "R envelope spans U10/U9 short residual + bank ESR + fuse R (~3.6 mOhm "
                "from 9 W/50^2) + layout; none measured at multi-kA. L envelope spans a "
                "compact bus loop to long bank leads. No arcing, no evolving R."
            ),
            "grid": env,
            "melt_screen": melt,
            "capacitor_discharge_screen_a70qs": cap_env,
            "clearing_screen": {
                "FWP-50A14F": None,
                "FWP-25A14F": None,
                "A70QS50-14F": "manufacturer capacitor-discharge rating 890 Vdc at time constant <= 2.5 ms; board coordination (let-through vs bank/copper withstand) still not established",
            },
        },
        "model_oracles": oracle,
        "nulls": {
            "internal_loop_resistance_ohm": None,
            "internal_loop_inductance_h": None,
            "internal_loop_peak_current_a": None,
            "fwp_capacitor_discharge_clearing": None,
            "a70qs_melting_and_clearing_demonstrated_for_board": None,
            "bank_copper_withstand_i2t_a2s": None,
            "startup_inrush_current_a": None,
            "temperature_derated_ampacity_a": None,
        },
    }
    (HERE / "compute_result.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(
        {
            "energy_j": E_J,
            "normal": normal,
            "melt": melt,
            "oracles": oracle,
            "envelope_points": len(env),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
