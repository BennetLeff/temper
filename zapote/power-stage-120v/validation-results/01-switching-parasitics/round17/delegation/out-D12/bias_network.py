"""D12 sizing and sensitivity, not a switching simulation or production bound.

TI Fig8-4: capacitor/Zener between OUT and Rg, cathode at OUT. Existing
10kohm Rgs charges the blocking capacitor over many cycles. Approximate
cycle-average startup neglects gate-charge asymmetry and Zener knee shape.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    supply = 15.0
    cgs = 1e-9
    cz = 10e-6
    rgs = 10e3
    q_reference = 234e-9  # Infineon Rev2.0 p5 table6: typical, 0->10V,400V,58.2A
    q_sizing = 400e-9  # engineering scenario, deliberately NOT a worst-case bound
    results = {
        "status": "analytical estimates, circuit-specific transient validation pending",
        "assumptions": {
            "VDD_V": supply,
            "Cgs_F": cgs,
            "Cz_nom_F": cz,
            "Cz_sizing_effective_F": 5e-6,
            "Rgs_ohm": rgs,
            "Qg_reference_C": q_reference,
            "Qg_sizing_scenario_C": q_sizing,
            "frequency_scenarios_Hz": [20000, 40000, 80000],
            "bootstrap_effective_scenario_F": 5e-6,
            "bootstrap_start_V_scenario": 13.0,
            "bootstrap_refresh_target_V": 9.2,
            "driver_quiescent_sizing_A": 0.0044,
            "bootstrap_diode_drop_scenario_V": 1.0,
        },
        "variants": {},
        "capacitor_only_drive": [],
    }
    for bias, zmin, zmax, zz in [(2.0, 1.91, 2.09, 100), (3.9, 3.7, 4.1, 90)]:
        pos = supply - bias
        on_current = pos / rgs
        net_charge_current = 0.5 * on_current - 0.5 * bias / rgs
        row = {
            "gate_on_nominal_est_V": pos,
            "gate_off_nominal_est_V": -bias,
            "positive_reduction_vs_D6_V": bias,
            "zener_25C_at_5mA_range_V": [zmin, zmax],
            "zener_small_signal_ZZT_max_ohm_at_5mA": zz,
            "zener_Tcoeff_mV_C_at_5mA": [-3.5, 0],
            "zener_125C_shift_est_V": [-0.35, 0],
            "on_Rgs_current_est_A": on_current,
            "average_available_zener_current_est_A_50pct": net_charge_current,
            "zener_power_est_W_50pct": bias * max(0, net_charge_current),
            "Rgs_power_est_W_50pct": (0.5 * pos**2 + 0.5 * bias**2) / rgs,
            "bias_cap_ripple_Qg_reference_est_V": (q_reference + cgs * supply) / cz,
            "bias_cap_ripple_sizing_est_V": (q_sizing + cgs * supply) / 5e-6,
            "minimum_duty_for_nominal_bias_in_ideal_average_model": bias / supply,
            "startup_time_to_nominal_bias_est_ms": -rgs
            * cz
            * math.log(1 - bias / (0.5 * supply))
            * 1000,
            "disabled_decay_time_constant_nom_ms": rgs * cz * 1000,
            "disabled_bias_after_100ms_est_V": -bias * math.exp(-0.1 / (rgs * cz)),
            "nominal_off_before_first_switch_V": 0,
            "duty_sensitivity": [
                {"duty": duty, "ideal_average_bias_V": min(bias, duty * supply)}
                for duty in (0.1, 0.2, 0.3, 0.5)
            ],
            "high_side_on_est_with_1V_boot_diode_drop_V": pos - 1,
        }
        results["variants"][str(bias)] = row
    for swing in (15, 17, 19):
        results["capacitor_only_drive"].append(
            {
                "swing_V": swing,
                "added_charge_C": cgs * swing,
                "energy_per_gate_cycle_J": cgs * swing**2,
                "whole_bridge_added_W": {
                    str(f): 4 * cgs * swing**2 * f for f in (20000, 40000, 80000)
                },
                "approx_driver_share_single_3p9_path_J_per_gate_cycle": 0.5
                * cgs
                * swing**2
                * (5 / (5 + 3.9) + 0.55 / (0.55 + 3.9)),
            }
        )
    q_total = q_sizing + cgs * supply
    results["bootstrap_sizing"] = {
        "charge_per_switch_scenario_C": q_total,
        "Q_over_C_droop_scenario_V": q_total / 5e-6,
        "high_hold_limit_to_9p2V_scenario_ms": (5e-6 * (13 - 9.2) - q_total) / 0.0044 * 1000,
        "minimum_refresh_charge_scenario_C": q_total + 0.0044 / 20000,
        "required_avg_refresh_current_for_1us_A": (q_total + 0.0044 / 20000) / 1e-6,
    }
    results["split_off_path"] = {
        "external_parallel_incremental_R_ohm": 3.9 / (3.9 + 1),
        "plus_model_driver_sink_R_ohm": 0.55 + 3.9 / (3.9 + 1),
        "note": "Only when Schottky conducts; Vf, package inductance and capacitance remain",
    }
    (HERE / "bias_network.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
