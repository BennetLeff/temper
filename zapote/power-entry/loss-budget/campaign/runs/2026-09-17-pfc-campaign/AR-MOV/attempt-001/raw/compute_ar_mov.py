#!/usr/bin/env python3
"""AR-MOV computation: derive MOSFET required rating and controller node
stresses from the CAPTURED MOV clamp.

Source-and-arithmetic only.  No solver, no maintained model, no CAD/BOM edit.
Every input carries an evidence class.  Nothing here is a physical
qualification.

Sources
-------
MOV:  Littelfuse "Metal-Oxide Varistors Datasheet - LA Series Radial Lead
      Varistors", Revised VL 16/9/2024, (c) 2024 Littelfuse, Inc.,
      13 pages.  Captured at raw/littelfuse_LA_series_datasheet.pdf
      (sha256 8e6c56a7901cc2748a4a58685ccdc7228b13ee07dc5442c411824172e00a7ecc).
      Page 2, table "LA Series Ratings & Specifications" row V150LA10AP:
      VM(AC)=150 V, VM(DC)=200 V, WTM=45 J (10/1000us), ITM=4500 A (8/20us),
      VNOM 216..264 V (1 mA DC), VC=395 V max at IPK=50 A (8/20us), C=800 pF.

Controller: NXP TEA2209T "Active bridge rectifier controller", Rev. 1.1,
      14 April 2021, Product data sheet.  Absolute maximum ratings:
      pins L, R, VR, VCCHL, VCCHR, GATEHR, GATEHL and the differentials
      dV(VR-L), dV(VR-R): 440 V operating / 700 V mains-transient max.
      Note (p.12): "Mains transients or surges must be limited to voltages
      below 700 V."

Contract: contract-C1.1.json (bus 400 V, 108/120/132 Vrms lines).  The
      surge test level is a PROVISIONAL, ASSUMED product contract (IEC
      61000-4-5, 1 kV L-L / 2 kV L-PE), not adopted here.
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---- captured MOV data (guaranteed maxima, 25 C unless stated) -------------
V150LA10AP = {
    "mpn": "V150LA10AP",
    "branding": "P150L10",
    "disc_dia_mm": 14,
    "vm_ac_v": 150.0,
    "vm_dc_v": 200.0,
    "wtm_j_10_1000us": 45.0,
    "itm_a_8_20us": 4500.0,
    "vnom_min_v_1ma": 216.0,
    "vnom_max_v_1ma": 264.0,
    "vc_max_v_8_20us": 395.0,          # <-- the captured clamp
    "ipk_a_for_vc": 50.0,              # <-- its datasheet surge current
    "capacitance_pf": 800.0,
    "source": "Littelfuse LA Series datasheet Rev VL 16/9/2024, p.2",
}

# ---- controller own limits (captured) --------------------------------------
TEA2209T = {
    "part": "TEA2209T",
    "operating_node_limit_v": 440.0,   # pins L, R, VR, VCCHL, VCCHR, gates, diffs
    "mains_transient_node_limit_v": 700.0,
    "note_p12": "Mains transients or surges must be limited below 700 V.",
    "source": "NXP TEA2209T Rev. 1.1 (2021-04-14), p.8 + p.12",
}

# ---- contract (maintained) -------------------------------------------------
LINE_RMS_MAX_V = 132.0
BUS_V = 400.0

# ---- PROVISIONAL, ASSUMED surge contract (NOT adopted) ---------------------
# IEC 61000-4-5 combination-wave generator: effective source impedance 2 ohm,
# so the 8/20us short-circuit current is Voc / 2 ohm.
SURGE_CONTRACT_ASSUMED = {
    "standard": "IEC 61000-4-5",
    "line_to_line_open_circuit_v": 1000.0,
    "line_to_pe_open_circuit_v": 2000.0,
    "waveform": "1.2/50 us voltage / 8/20 us current combination wave",
    "generator_effective_z_ohm": 2.0,   # standard definition, not captured here
    "status": "PROVISIONAL_ASSUMED_NOT_ADOPTED",
}


def main():
    out = {"schema": "pfc-campaign-AR-MOV-compute/v1"}

    v_peak = LINE_RMS_MAX_V * math.sqrt(2.0)

    # ------ provisional surge currents (derived from the assumed contract)
    z = SURGE_CONTRACT_ASSUMED["generator_effective_z_ohm"]
    i_ll_prospective = SURGE_CONTRACT_ASSUMED["line_to_line_open_circuit_v"] / z
    i_lpe_prospective = SURGE_CONTRACT_ASSUMED["line_to_pe_open_circuit_v"] / z

    out["captured_mov"] = V150LA10AP
    out["controller_limits"] = TEA2209T

    out["surge_contract"] = {
        **SURGE_CONTRACT_ASSUMED,
        "prospective_8_20us_current_ll_a": i_ll_prospective,
        "prospective_8_20us_current_lpe_a": i_lpe_prospective,
        "applies_to_ln_mov": "LL differential only; the L-N MOV does not clamp the L-PE common-mode surge",
        "would_settle_it": [
            "a committed product requirement document naming the surge test level (and whether an L-PE clamp is fitted)",
            "a captured/measured V150LA10AP V-I curve so the clamp at the actual MOV current can be read",
        ],
    }

    # ------ the clamp at the product surge current is NOT tabulated
    out["clamp_at_specified_surge"] = {
        "captured_clamp_v": V150LA10AP["vc_max_v_8_20us"],
        "at_datasheet_surge_current_a": V150LA10AP["ipk_a_for_vc"],
        "waveform": "8/20 us",
        "evidence_class": "MANUFACTURER_DATASHEET_GUARANTEED_MAX",
        "clamp_at_provisional_product_surge_v": None,
        "reason_null": (
            "The datasheet guarantees the clamp ONLY at IPK=50 A. The provisional "
            "contract's prospective 8/20us current is 500 A (L-L). At that current "
            "the MOV clamps higher (p.7 Figure 10 shows the 14mm family V-I rising "
            "with current); the datasheet tabulates no guaranteed clamp there, and "
            "the actual MOV current under the combination wave is itself set by the "
            "(unknown) clamp. Figure digitisation was attempted and rejected as "
            "unreliable across the adjacent curves, so no digitised value is used."
        ),
        "direction": "395 V is a LOWER BOUND on the terminal clamp at any current > 50 A.",
    }

    # ------ MOSFET required rating (active-bridge devices off-blocking the line)
    out["mosfet_required_rating"] = {
        "device_class_assumed_v": 600.0,
        "basis": (
            "the active-bridge MOSFET that is off blocks the line terminal voltage; "
            "the L-N MOV clamps that terminal voltage. The required rating therefore "
            "follows from the clamped TERMINAL voltage, NOT from the controller's "
            "700 V limit and NOT from the PFC bus."
        ),
        "steady_line_peak_v": round(v_peak, 2),
        "surge_clamped_v_sourced": V150LA10AP["vc_max_v_8_20us"],
        "margin_vs_steady": round(600.0 / v_peak, 3),
        "margin_vs_sourced_clamp": round(600.0 / V150LA10AP["vc_max_v_8_20us"], 3),
        "sensitivity_margin_if_clamp_v": {
            str(c): round(600.0 / c, 3)
            for c in [395.0, 440.0, 500.0, 600.0]
        },
        "statement": (
            "600 V gives 1.52x against the SOURCED guarantee point (395 V @ 50 A). "
            "Because the clamp rises with current and is untabulated above 50 A, "
            "the margin at the product surge current is unknown and strictly smaller."
        ),
    }

    # ------ controller node stresses (its own limits)
    def ratios(v):
        return {
            "node_v": round(v, 2),
            "fraction_of_440_operating": round(v / 440.0, 3),
            "fraction_of_700_transient": round(v / 700.0, 3),
        }

    out["controller_node_stresses"] = {
        "nodes": ["L", "R", "VR", "VCCHL", "VCCHR", "GATEHR", "GATEHL", "dV(VR-L)", "dV(VR-R)"],
        "operating_limit_v": 440.0,
        "transient_limit_v": 700.0,
        "steady": ratios(v_peak),
        "surge_sourced_clamp": ratios(V150LA10AP["vc_max_v_8_20us"]),
        "sensitivity_if_clamp_v": {str(c): ratios(c) for c in [395.0, 440.0, 500.0, 600.0]},
        "statement": (
            "At the sourced clamp (395 V @ 50 A) the nodes sit at 0.898 of the 440 V "
            "operating limit and 0.564 of the 700 V transient limit. If the surge "
            "current drives the clamp above 440 V (untabulated), the nodes exceed "
            "their OPERATING limit during the surge while remaining under the 700 V "
            "transient limit. The node voltage is set by the circuit clamp, NOT by "
            "the MOSFET rating: a higher-rated MOSFET does not lower it, and the "
            "controller's 700 V transient limit does not require an 800/1000 V device."
        ),
    }

    # ------ the internal-fault boundary (explicit, deferred)
    out["internal_fault_boundary"] = {
        "statement": (
            "A line-surge MOV across L-N does not resolve an internally powered "
            "fault. The boost-switch-short capacitor-discharge loop (179.24 J in "
            "2240.47 uF) never passes through the MOV's terminals; it is AR-PROTECT's "
            "question, not this task's. No MOV clamp figure is admissible as a bound "
            "on that loop."
        ),
        "source": "AR-FAULT/attempt-001/raw + coordinator receipt (corrected)",
    }

    out["boost_switch_note"] = {
        "device": "IPW65R045C7 (contract baseline) / IPW60R017C7 (AR-VERIFY candidate)",
        "statement": (
            "Separate case: the boost switch blocks the PFC bus (~400 V steady), not "
            "the MOV-clamped line. The L-N MOV clamp does not set its rating. Bus "
            "excursion under line surge is controlled by the PFC loop and bus "
            "capacitance and is not derived from the MOV here."
        ),
        "required_rating_v": None,
        "reason_null": "bus surge excursion is not established from the captured sources",
    }

    (HERE / "compute_result.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({
        "clamp": out["clamp_at_specified_surge"]["captured_clamp_v"],
        "at_a": out["clamp_at_specified_surge"]["at_datasheet_surge_current_a"],
        "mosfet_margin": out["mosfet_required_rating"]["margin_vs_sourced_clamp"],
        "ctrl_frac_operating": out["controller_node_stresses"]["surge_sourced_clamp"]["fraction_of_440_operating"],
        "ctrl_frac_transient": out["controller_node_stresses"]["surge_sourced_clamp"]["fraction_of_700_transient"],
        "i_ll_a": i_ll_prospective,
    }, indent=2))


if __name__ == "__main__":
    main()
