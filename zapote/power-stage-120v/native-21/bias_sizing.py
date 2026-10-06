"""D-33 HOT-side bias sizing; assumptions are not component limits.

Run before circuit changes. Sources and unresolved qualifications are in
round17/delegation/out-D33/README.md. No PCB or circuit source is generated.
"""
from __future__ import annotations

import json
from pathlib import Path

POWER = Path(__file__).resolve().parents[1]
OUT = POWER / "validation-results/01-switching-parasitics/round17/delegation/out-D33"


def sizing() -> dict:
    # Infineon Rev2.0 table6: 234nC typical at 400V,58.2A,0->10V.
    # D12's 400nC at 15V is an engineering allowance, NOT a datasheet maximum.
    q_typ, q_allow, cgs, span = 234e-9, 400e-9, 1e-9, 17.0
    extracted = json.loads((OUT / 'edge-current/summary.json').read_text())
    measured_charge = max(extracted['maximum_positive_negative_charge_C'], json.loads((OUT/'edge-current-2.4V/summary.json').read_text())['maximum_positive_negative_charge_C'])
    # The extracted physical-1ohm F6 waveform exceeds the old 417nC sizing
    # assumption. 740nC also covers the deeper -2.4V check (661.3nC) +10%.
    q_edge = 740e-9
    assert q_edge >= measured_charge*1.1
    rows = []
    for f in (33000, 40000, 80000):
        gate_i = q_edge * f
        # Per output: 4.4mA driver allowance, 3mA split bleed,
        # 1.5mA Rgs at +15V, 14mA rail monitor allocation (reference bias,
        # LED, comparator); shared LS monitor charged twice conservatively.
        channel_i = gate_i + .0044 + .003 + .0015 + .014
        # Low-side 17V linear span from 24V; two HS 1.2:1 transformers.
        # 20V is the no-loss secondary voltage, conservative for power sizing.
        # 70% conversion efficiency is an allocation, not a guaranteed minimum.
        transformer_output = 2 * 20 * channel_i
        primary_24w = transformer_output / .70
        # HOT5/OCP/input-side loads allocated 30mA at raw 24V; verify netlist later.
        total = 2 * 24 * channel_i + primary_24w + 24 * (.030 + .010)
        rows.append({"frequency_Hz": f, "gate_typ_reference_W_4_at_10V": 4*q_typ*10*f,
                     "gate_allowance_W_4_at_17V": 4*q_edge*span*f,
                     "channel_current_A": channel_i, "transformer_output_W_2": transformer_output,
                     "transformer_driver_input_W_at_70pct": primary_24w,
                     "low_side_span_LDO_heat_W": (24-17)*(2*channel_i+.030),
                     "high_side_span_LDO_heat_W_2": 2*(20-17)*channel_i,
                     "HOT_supply_allocation_W": total, "supply_21p6W_utilization": total/21.6})
    # ESR and ESL here are explicit layout/component scenarios, not measured.
    droop = [{"effective_C_F": c, "charge_step_V": q_edge/c,
              "charge_only_edge_V_from_minus_2": -2 + q_edge/c,
              "with_2A_20mohm_0p5nH_0p1Aperns_V": -2 + q_edge/c + .04 + .05}
             for c in (2.2e-6, 10e-6, 22e-6)]
    return {"status": "source sizing; physical enclosure/transformer qualification remains a bench gate",
            "Qg_typ_datasheet_C": q_typ, "Qg_sizing_assumption_C": q_allow,
            "old_Q_edge_including_1nF_Cgs_C": q_allow+cgs*span,
            "extracted_positive_negative_charge_C": measured_charge,
            "extracted_peak_negative_current_A": extracted['maximum_negative_current_A'],
            "Q_edge_allowance_C": q_edge, "gate_swing_V": span,
            "conversion_efficiency_assumption": .70,
            "candidate": "TCO_L -> IRM-20-24 -> low-side 17V split; direct 24V -> SN6507 -> two WE 750320775 -> 17V splits",
            "supply": {"part": "IRM-20-24", "rating_W": 21.6, "rating_A": .9,
                       "nominal_V": 24, "tolerance_fraction": .025, "ripple_pp_V": .2,
                       "dimensions_mm": [52.4, 27.2, 24],
                       "qualification": "rating is before enclosure temperature derating; HOT load allocation must be reconciled to final netlist"},
            "rows": rows, "negative_rail_droop": droop,
            "shunt": {"candidate": "TLVH431B", "Rtop_ohm": 6120, "Rbottom_ohm": 10000,
                      "nominal_V": 1.24*(1+6120/10000), "bleed_ohm": 4990,
                      "idle_current_A": 15/4990,
                      "local_bank": "2x10uF 50V 1210, 2x1uF 25V 0603, 4x100nF 25V 0402",
                      "minimum_effective_F_by_branch": [10e-6,1e-6,.32e-6],
                      "bulk": "220uF 6SVPC220M through 0.68ohm, per driver VSS; 140.8..316.8uF sensitivity",
                      "stability": "rail_qualification.py: full TI macro plus gm/pole sensitivities; bench loop and ESR/ESL verification required"},
            "transformer": {"candidate": "WE 750320775", "primary_to_secondary_ratio": 1.2,
                            "reinforced_working_Vrms": 500, "working_rating_max_frequency_Hz": 700000,
                            "half_primary_Vus": 60, "full_primary_L_min_H": 300e-6,
                            "Cww_typ_pF": 3, "leakage_typ_H": 9e-6,
                            "Cww_status": "typical, not a maximum; sweep and layout qualification remain required",
                            "primary_full_DCR_max_ohm": .41, "secondary_full_DCR_max_ohm": .29,
                            "RCLK_ohm": 18200, "switching_frequency_curve_estimate_Hz": 600000,
                            "frequency_acceptance_min_Hz": 500000,
                            "frequency_acceptance_max_Hz": 700000,
                            "Vt_required_Vus": (24*1.025+.1)/(2*500000)*1e6,
                            "magnetizing_peak_A_two_cores_estimate": 2*(24*1.025+.1)/(4*500000*(300e-6/4)),
                            "reflected_load_A_two_cores": 2*rows[-1]["channel_current_A"]/1.2,
                            "driver_switch_current_limit_recommended_A": .5,
                            "limits": "transformer_check.py includes recharge, +40% winding DCR and min filter L; core loss, worst leakage, clock limits and startup still need bench verification"}}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    result = sizing()
    (OUT / "bias-sizing.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
