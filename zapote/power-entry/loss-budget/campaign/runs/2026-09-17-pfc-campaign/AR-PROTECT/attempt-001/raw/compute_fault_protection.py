#!/usr/bin/env python3
"""AR-PROTECT attempt-001 computation.

Source-only. Produces the defensible quantities for the corrected fault-loop
and protection assessment and emits the loop-consistency assignment files.

What this script does NOT do, by design:
  * it does not compute a prospective line-fault current (the AC source/line
    impedance is not established);
  * it does not split the stored capacitor energy between U9 and U10 (the
    branch impedances over a multi-kA discharge are not defensible);
  * it does not map the active-bridge MOSFETs onto their SOA (the fault current
    and duration are both unresolved).
Those stay null in the output.

The loop-consistency check itself is Rust (`zapote-erc::fault_loop` via the
`zapote-fault-loop` binary); this script only prepares its inputs.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NETLIST = HERE / "netlist_fault_loop.json"
OUT = HERE / "compute_result.json"
CHECKER_DIR = HERE / "checker"

INTERNAL_LOOP_NETS = ["PFC_BUS_PLUS_390V", "PFC_BUS_MINUS", "a1"]

# Line-fed switch-short loop, from AR-FAULT's traced loop (for the report's
# membership table only; the dispatch fixes the checker to the internal loop).
LINE_LOOP_NETS = [
    "AC_L_RECTIFIED_INPUT",
    "l1",
    "l2",
    "ac1",
    "ac2",
    "plus",
    "a1",
    "PFC_BUS_MINUS",
    "minus",
    "AC_N_RECTIFIED_INPUT",
]

# Frozen stored-energy basis (values, not derived here).
C_BULK_PER_CAP_F = 560e-6
C_HF_F = 0.47e-6
N_BULK = 4
V_BUS_V = 400.0
RDS_BOOST_SWITCH_OHM = 0.042  # STW65N65DM2AG typ (AR-FAULT)
RDS_ACTIVE_BRIDGE_OHM = 0.0174  # IPW60R017C7 hot typ (AR-DESIGN/AR-VERIFY)


def load_netlist() -> dict:
    return json.loads(NETLIST.read_text())


def element_membership(evidence: dict) -> dict[str, list[str]]:
    membership: dict[str, list[str]] = {}
    for net, info in evidence["netlist_evidence"].items():
        for reference, _pin in info["nodes"]:
            membership.setdefault(reference, [])
            if net not in membership[reference]:
                membership[reference].append(net)
    return membership


def on_loop(membership: dict[str, list[str]], loop_nets: list[str]):
    rows = []
    for reference in sorted(membership):
        nets = membership[reference]
        on = sorted(set(nets) & set(loop_nets))
        rows.append(
            {
                "element": reference,
                "nets": sorted(nets),
                "terminals_on_loop": len(on),
                "on_loop_nets": on,
                "can_conduct_in_loop": len(on) >= 2,
            }
        )
    return rows


def main() -> int:
    evidence = load_netlist()
    membership = element_membership(evidence)

    internal_rows = on_loop(membership, INTERNAL_LOOP_NETS)
    line_rows = on_loop(membership, LINE_LOOP_NETS)

    c_bank = N_BULK * C_BULK_PER_CAP_F + C_HF_F
    e_total = 0.5 * c_bank * V_BUS_V**2
    e_per_bulk = 0.5 * C_BULK_PER_CAP_F * V_BUS_V**2
    e_hf = 0.5 * C_HF_F * V_BUS_V**2

    tau_correct = RDS_BOOST_SWITCH_OHM * c_bank
    tau_withdrawn = (RDS_BOOST_SWITCH_OHM + 0.010) * c_bank

    bulk_refs = ["U36", "U37", "U38", "U39"]
    # U40 is the 470 nF B32672P6474K000 film cap (c_hf), per the netlist
    # node_meaning; U52 is the DC output connector (1714971), not a capacitor.
    hf_ref = "U40"

    # --- assignment files -------------------------------------------------
    # (1) corrected: stored energy held by the loop's capacitors (defensible,
    #     equal-voltage 1/2 C V^2); delivered split into U9/U10 and any shunt
    #     term are NULL -> assigned 0.0 (zero is ignored by the checker, which
    #     is exactly the point: a null is not a claim).
    corrected = {ref: round(e_per_bulk, 4) for ref in bulk_refs}
    corrected[hf_ref] = round(e_hf, 4)
    corrected.update({"U9": 0.0, "U10": 0.0, "U12": 0.0})

    # (2) withdrawn AR-FAULT distribution: U12 carries energy though only one of
    #     its terminals is on the loop. Retained as the checker's negative
    #     control; it MUST fail.
    withdrawn = {"U9": 144.77, "U12": 34.46}

    # (3) all-null distribution: no element is assigned delivered energy.
    nulls = {"U9": 0.0, "U10": 0.0, "U12": 0.0, "U36": 0.0, "U37": 0.0,
             "U38": 0.0, "U39": 0.0, "U40": 0.0}

    CHECKER_DIR.mkdir(exist_ok=True)
    (CHECKER_DIR / "assignments_corrected.json").write_text(
        json.dumps(corrected, indent=2) + "\n")
    (CHECKER_DIR / "assignments_withdrawn_negative_control.json").write_text(
        json.dumps(withdrawn, indent=2) + "\n")
    (CHECKER_DIR / "assignments_null_distribution.json").write_text(
        json.dumps(nulls, indent=2) + "\n")

    result = {
        "schema": "pfc-campaign-AR-PROTECT-compute/v1",
        "note": "source-only; no solver, no model, no CAD/BOM edit",
        "internal_loop_nets": INTERNAL_LOOP_NETS,
        "line_loop_nets": LINE_LOOP_NETS,
        "internal_loop_membership": internal_rows,
        "line_loop_membership": line_rows,
        "stored_energy": {
            "c_bank_f": c_bank,
            "v_bus_v": V_BUS_V,
            "e_total_j": round(e_total, 3),
            "e_per_bulk_cap_j": round(e_per_bulk, 3),
            "e_hf_cap_j": round(e_hf, 5),
            "basis": "0.5*C*V^2 at the 400 V bus setpoint, equal voltage across "
                     "the parallel bank",
        },
        "internal_loop_timescale": {
            "tau_corrected_s": tau_correct,
            "tau_corrected_us": round(tau_correct * 1e6, 1),
            "tau_withdrawn_s": tau_withdrawn,
            "tau_withdrawn_us": round(tau_withdrawn * 1e6, 1),
            "basis": "R_loop * C; R_loop taken as the boost switch Rds_on(typ) "
                     "only, because the shunt U12 is NOT in this loop",
            "line_half_cycle_us": round(1.0 / 60.0 / 2.0 * 1e6, 1),
        },
        "defensible_device_ratings": {
            "gbj_passive_bridge_incumbent": {
                "ifsm_a": 350.0,
                "i2t_a2s": 510.0,
                "note": "the INCUMBENT U1's rating; not transferable to a "
                        "replacement",
            },
            "active_bridge_mosfet_ipw60r017c7": {
                "id_pulse_a_tc25": 495.0,
                "id_pulse_note": "pulse width limited by Tj,max; not an IFSM",
                "eas_single_pulse_mj": 582.0,
                "ias_single_pulse_a": 12.6,
                "i2t_a2s": None,
                "i2t_note": "no I2t rating is published for this MOSFET",
                "short_circuit_withstand_s": None,
                "soa": "Diagrams 2 and 3 (Safe operating area) and Diagram 4 "
                       "(max transient thermal impedance) exist in the "
                       "datasheet; their coordinates are not digitised here "
                       "because the fault current and duration are unresolved",
            },
            "tea2209t_controller": {
                "v_operating_max_v": 440.0,
                "v_mains_transient_max_v": 700.0,
                "tj_max_c": 125.0,
                "overcurrent_protection": None,
                "protections": [
                    "gate pull-down on driver-supply UVLO (<2 V at the gate)",
                    "power-MOSFET drain-source protection disables all gate "
                    "drivers; documented purpose is to avoid high dissipation "
                    "and high current peaks during start-up",
                    "charge state entered only when |L| or |R| > 22 V",
                    "external disable only via COMP pin",
                ],
            },
        },
        "nulls_by_design": {
            "ac_source_line_impedance_ohm": None,
            "line_fed_peak_current_a": None,
            "line_fed_fault_duration_s": None,
            "line_fed_fault_energy_j": None,
            "internal_loop_peak_current_a": None,
            "internal_loop_u9_u10_energy_split_j": None,
            "f1_total_clearing_i2t_a2s": None,
            "active_bridge_mosfet_survival_at_fault": None,
            "controller_post_fault_response": None,
        },
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "e_total_j": result["stored_energy"]["e_total_j"],
        "tau_corrected_us": result["internal_loop_timescale"]["tau_corrected_us"],
        "internal_loop_can_conduct": [
            r["element"] for r in internal_rows if r["can_conduct_in_loop"]
        ],
        "internal_loop_cannot_conduct": [
            r["element"] for r in internal_rows if not r["can_conduct_in_loop"]
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
