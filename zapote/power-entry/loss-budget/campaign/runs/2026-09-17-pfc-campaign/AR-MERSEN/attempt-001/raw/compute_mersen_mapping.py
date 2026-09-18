#!/usr/bin/env python3
"""AR-MERSEN arithmetic record -- map the AR-COORD fault-impedance envelope onto
Mersen's stated capacitor-discharge conditions, with the time constant defined
as L/R (not R*C).

This is NOT a solver and NOT a qualified prediction. For a series R-L-C discharge
of the retained bus bank,

    L di/dt + R i + (1/C) int i dt = 0,  i(0)=0, v_c(0)=V0

it computes, on the same 400-point (R, L) grid AR-COORD used:

  * peak current i_pk(R, L) and damping factor zeta
  * total action integral  int_0^inf i^2 dt = E / R   (exact energy balance)
  * the circuit time constant L/R   (Mersen's own definition)
  * the pre-arcing ACTION screen (L-independent; E/R >= I2t_pre_arcing)
  * Mersen's capacitor-discharge condition for A70QS50-14F (L-dependent; L/R <= 2.5 ms)
  * the JOINT qualifying region: cells that meet the action screen AND L/R AND
    the voltage/current limits

The model ASSUMES a single constant lumped R, a fixed L, no arc and no evolving
short residual. Those assumptions are why every R-derived value is illustrative
and why clearing is NOT concluded. The oracles below validate the RLC
arithmetic only; they do NOT validate its translation into manufacturer
conditions.

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

# A70QS50-14F, Mersen HS High-Speed Fuses catalogue (2024, captured 2026-09-18).
#   p.20 (HS 20), A70QS French Cylindrical: "an 890 VDC rating for capacitor
#   discharge applications up to 2.5ms time constant"; "700VDC rated for DC
#   protection of equipment with L/R <=10ms"; "100kA interrupting at 10ms time
#   constant".
#   p.21 (HS 21), RATINGS AND APPLICATION DATA:
#   Melting I2t (A2s x 10^3) Max = 0.28 ; Max Clearing I2t @ 700VAC = 1.50 ;
#   Watts Loss @ Rated Current = 11.6 W ; footnote "*100kA, L/R = 11.6ms".
A70QS50 = {
    "rated_current_a": 50.0,
    "pre_arcing_i2t_max_a2s": 0.28e3,     # table header: "Max"
    "clearing_i2t_700vac_a2s": 1.50e3,    # at 700 VAC, not DC
    "watts_loss_rated_w": 11.6,
    "cap_discharge_voltage_v": 890.0,     # p.20
    "cap_discharge_tau_max_s": 2.5e-3,    # p.20
    "dc_interrupting_a": 100e3,           # footnote p.21, L/R = 11.6 ms
    "dc_interrupting_tau_ref_s": 11.6e-3, # footnote p.21
    "general_dc_tau_s": 10e-3,            # highlight p.20 (L/R <= 10 ms)
}

# Same 400-point grid as AR-COORD (raw/compute_coordination.py):
#   R = 5 mOhm .. 5 Ohm (25 log-spaced values, 4 per decade)
#   L = 20 nH .. 20 uH  (16 log-spaced values, 5 per decade)
R_SWEEP_OHM = [0.005 * (10 ** (i / 4.0)) for i in range(0, 25)]
L_SWEEP_H = [2.0e-8 * (10 ** (i / 5.0)) for i in range(0, 16)]


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


def numeric_action(r: float, l: float, n: int = 40000) -> float:
    """Simpson integral of i^2 over the full discharge."""
    t_end = 20.0 * max(r * C_BANK_F, 2.0 * l / r, 1.0e-7)
    dt = t_end / n
    acc = 0.0
    prev = discharge_current(0.0, r, l)
    for k in range(1, n + 1, 2):
        f1 = discharge_current(k * dt, r, l)
        f2 = discharge_current((k + 1) * dt, r, l)
        acc += (dt / 3.0) * (prev * prev + 4.0 * f1 * f1 + f2 * f2)
        prev = f2
    return acc


def main() -> None:
    pre_arcing = A70QS50["pre_arcing_i2t_max_a2s"]
    tau_max = A70QS50["cap_discharge_tau_max_s"]
    v_max = A70QS50["cap_discharge_voltage_v"]
    i_max = A70QS50["dc_interrupting_a"]
    r_action_max = E_J / pre_arcing  # action screen boundary, L-independent

    grid = []
    for r in R_SWEEP_OHM:
        for l in L_SWEEP_H:
            ipk, tpk, regime = peak_current(r, l)
            alpha = r / (2.0 * l)
            w0 = math.sqrt(1.0 / (l * C_BANK_F))
            tau_lr = l / r
            grid.append(
                {
                    "r_ohm": r,
                    "l_h": l,
                    "regime": regime,
                    "peak_a": ipk,
                    "t_peak_s": tpk,
                    "damping_zeta": alpha / w0,
                    "total_action_a2s": E_J / r,
                    "tau_lr_s": tau_lr,
                    "tau_rc_s": r * C_BANK_F,
                    "action_screen_met": (E_J / r) >= pre_arcing,
                    "tau_lr_within_cap_rating": tau_lr <= tau_max,
                    "voltage_within_cap_rating": V_BUS_V <= v_max,
                    "peak_within_dc_ir": ipk <= i_max,
                    "qualifies": (
                        (E_J / r) >= pre_arcing
                        and tau_lr <= tau_max
                        and V_BUS_V <= v_max
                        and ipk <= i_max
                    ),
                }
            )

    qualifying = [c for c in grid if c["qualifies"]]
    action_met = [c for c in grid if c["action_screen_met"]]
    action_tau_fail = [c for c in action_met if not c["tau_lr_within_cap_rating"]]
    rc_would_admit = [c for c in grid if c["action_screen_met"] and c["tau_rc_s"] <= tau_max]

    peak_max = max(grid, key=lambda c: c["peak_a"])
    # most underdamped cell (smallest zeta)
    min_zeta = min(grid, key=lambda c: c["damping_zeta"])

    # R*C vs L/R at the max-L / min-R corner (AR-COORD's comparison corner)
    r_corner, l_corner = R_SWEEP_OHM[0], L_SWEEP_H[-1]
    rc_corner = r_corner * C_BANK_F
    lr_corner = l_corner / r_corner
    zeta_corner = (r_corner / 2.0) * math.sqrt(C_BANK_F / l_corner)

    # independent limits as oracles for the model arithmetic only
    oracle = {}
    r0, l0 = 1.0e-4, 1.0e-7
    ipk0, _, _ = peak_current(r0, l0)
    z0 = math.sqrt(l0 / C_BANK_F)
    oracle["lossless_peak_should_approach_V0_over_Z0"] = {
        "computed_peak_a": ipk0,
        "V0_over_Z0_a": V_BUS_V / z0,
        "rel_err": abs(ipk0 - V_BUS_V / z0) / (V_BUS_V / z0),
    }
    ipk2, _, _ = peak_current(2.0, 1.0e-12)
    oracle["large_R_small_L_peak_should_approach_V0_over_R"] = {
        "computed_peak_a": ipk2,
        "V0_over_R_a": V_BUS_V / 2.0,
        "rel_err": abs(ipk2 - V_BUS_V / 2.0) / (V_BUS_V / 2.0),
    }
    r_c, l_c = 0.05, 5.0e-6
    acc = numeric_action(r_c, l_c)
    oracle["action_integral_should_equal_E_over_R"] = {
        "r_ohm": r_c,
        "numeric_action_a2s": acc,
        "E_over_R_a2s": E_J / r_c,
        "rel_err": abs(acc - E_J / r_c) / (E_J / r_c),
    }

    out = {
        "schema": "pfc-campaign-AR-MERSEN-compute/v1",
        "note": (
            "Illustrative closed-form/quadrature arithmetic only. The series R-L-C "
            "model assumes one constant lumped R, a fixed L, no arc and no evolving "
            "short residual. Loop R and L are NOT measured, so peak/action/time "
            "constants are illustrative; clearing is NOT concluded. The oracles "
            "validate the RLC arithmetic, not its translation into Mersen conditions."
        ),
        "stored_energy": {"c_bank_f": C_BANK_F, "v_bus_v": V_BUS_V, "energy_j": E_J},
        "applicable_candidate": "A70QS50-14F",
        "catalogue_conditions": A70QS50,
        "time_constant_reconciliation": {
            "manufacturer_definition": "L/R (catalogue: '*Time Constant: L/R <=1ms'; A70QS highlights use 'L/R <=10ms' and '10ms time constant' interchangeably)",
            "not_rc": "R*C is not the manufacturer's stated time constant",
            "at_corner": {
                "r_ohm": r_corner,
                "l_h": l_corner,
                "rc_s": rc_corner,
                "lr_s": lr_corner,
                "lr_over_rc": lr_corner / rc_corner,
                "damping_zeta": zeta_corner,
            },
            "applies_to_capacitor_discharge": "the p.20 sentence explicitly scopes 890 VDC / 2.5 ms to capacitor discharge applications; the general DC rating is 700 VDC / L/R <= 10 ms",
        },
        "joint_mapping": {
            "action_screen": {
                "kind": "pre-arcing ACTION screen, not a melting result",
                "pre_arcing_i2t_max_a2s": pre_arcing,
                "r_action_max_ohm": r_action_max,
                "L_independent": True,
            },
            "manufacturer_time_constant": {
                "tau_lr_max_s": tau_max,
                "relation": "R >= L / tau_max = 400 * L",
            },
            "voltage": {"v_bus_v": V_BUS_V, "v_max_v": v_max, "within": V_BUS_V <= v_max},
            "current": {
                "dc_interrupting_a": i_max,
                "peak_max_on_grid_a": peak_max["peak_a"],
                "peak_max_at": {"r_ohm": peak_max["r_ohm"], "l_h": peak_max["l_h"]},
                "within_on_all_cells": peak_max["peak_a"] <= i_max,
                "caveat": "100 kA is the DC I.R. at L/R = 11.6 ms (footnote p.21); no peak limit is published separately for the 890 VDC capacitor-discharge condition",
            },
            "qualifying_cell_count": len(qualifying),
            "grid_cell_count": len(grid),
            "qualifying_r_bounds_ohm": [min(c["r_ohm"] for c in qualifying), max(c["r_ohm"] for c in qualifying)],
            "qualifying_l_bounds_h": [min(c["l_h"] for c in qualifying), max(c["l_h"] for c in qualifying)],
            "region_is_empty": len(qualifying) == 0,
            "action_screen_met_count": len(action_met),
            "action_met_but_tau_fails": [
                {"r_ohm": c["r_ohm"], "l_h": c["l_h"], "tau_lr_s": c["tau_lr_s"]}
                for c in action_tau_fail
            ],
            "rc_would_admit_count": len(rc_would_admit),
            "grid": grid,
        },
        "model_oracles": oracle,
        "most_underdamped_cell": {
            "r_ohm": min_zeta["r_ohm"],
            "l_h": min_zeta["l_h"],
            "damping_zeta": min_zeta["damping_zeta"],
        },
        "nulls": {
            "internal_loop_resistance_ohm": None,
            "internal_loop_inductance_h": None,
            "a70qs50_min_breaking_capacity_a": None,
            "a70qs50_capacitor_discharge_clearing_i2t_a2s": None,
            "bank_copper_withstand_i2t_a2s": None,
            "u9_u10_short_residual_ohm": None,
            "bank_esr_ohm": None,
        },
    }
    (HERE / "compute_result.json").write_text(json.dumps(out, indent=2) + "\n")

    print(json.dumps(
        {
            "energy_j": E_J,
            "action_screen_r_max_ohm": r_action_max,
            "qualifying_cells": len(qualifying),
            "action_met_cells": len(action_met),
            "action_met_but_tau_fails": len(action_tau_fail),
            "rc_would_admit_cells": len(rc_would_admit),
            "peak_max_a": peak_max["peak_a"],
            "min_zeta": min_zeta["damping_zeta"],
            "corner_rc_s": rc_corner,
            "corner_lr_s": lr_corner,
            "oracles": oracle,
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
