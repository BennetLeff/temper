#!/usr/bin/env python3
"""Build AR-BOUNDS claims.json with evidence hashes computed from retained bytes."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../attempt-001/raw
ATT = HERE.parent                                # .../attempt-001
BASE = ATT                                       # paths resolve relative to claims.json


def ev(rel):
    p = BASE / rel
    return {"path": rel, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


NICH = [ev("raw/sources/nichicon-e-lgx.pdf"), ev("raw/sources/nichicon-e-lgx.txt")]
C3D = [ev("raw/sources/C3D20065D-promelec.pdf"), ev("raw/sources/C3D20065D-promelec.txt")]
STW = [ev("raw/sources/STW65N65DM2AG.pdf")]
MERSEN = [ev("raw/sources/mersen-hs-high-speed-fuses.pdf"), ev("raw/sources/a70qs-conditions.json")]
GEOM = [ev("raw/geometry.json"), ev("raw/compute_bounds.py"), ev("raw/sources/section.kicad_pcb")]
NETL = [ev("raw/sources/netlist_fault_loop.json")]
CAPFAIL = [ev("raw/capture_failures.json")]

claims = []


def add(**kw):
    kw.setdefault("part", None)
    kw.setdefault("source_condition", None)
    kw.setdefault("evidence", [])
    kw.setdefault("derived_from", None)
    kw.setdefault("part_transformation", None)
    kw.setdefault("condition_transformation", None)
    kw.setdefault("justification", None)
    claims.append(kw)


add(id="assessed-board-identity", quantity="assessed_board",
    value_kind="assumed", bound_kind="point", fault_state="not_applicable",
    assertion="qualified", evidence=GEOM + CAPFAIL,
    justification="Geometry is taken from zapote/power-entry/shunt-repair/candidate/"
                "section.kicad_pcb (sha256 34e6fba9...), the board the delivered AR-FAULT "
                "netlist was extracted from. The dispatch's pcb/temper.kicad_pcb "
                "(sha256 00a27419...) does NOT contain PFC_BUS_PLUS_390V/a1/PFC_BUS_MINUS "
                "and was not used; the substitution is recorded in capture_failures.json.")

add(id="bank-capacitor-identity", quantity="bank_capacitor_part", part="LGX2W561MELC50",
    value_kind="assumed", bound_kind="point", fault_state="not_applicable",
    assertion="qualified", evidence=NICH,
    justification="4 x 560 uF / 450 V Nichicon LGX snap-in (35 x 50 mm), in parallel = "
                "2240 uF, the energy source of the internal discharge.")

add(id="bank-tan-delta-max-120hz", quantity="cap_tan_delta_max", part="LGX2W561MELC50",
    value_kind="maximum", bound_kind="upper",
    source_condition="120 Hz, 20 C, 450-500 V class tan delta max = 0.20 (datasheet table)",
    fault_state="not_applicable", assertion="qualified", evidence=NICH)

add(id="bank-esr-120hz-max", quantity="capacitor_esr_120hz_ohm", part="LGX2W561MELC50",
    value_kind="maximum", bound_kind="upper",
    source_condition="120 Hz, 20 C, 450-500 V class tan delta max = 0.20 (datasheet table)",
    fault_state="not_applicable", assertion="qualified", evidence=NICH,
    derived_from="bank-tan-delta-max-120hz",
    justification="ESR = tan_delta / (2*pi*f*C) = 0.20 / (2*pi*120*560e-6) = 0.4737 ohm per "
                "capacitor at 120 Hz, from the datasheet tan_delta max.")

add(id="bank-esr-bank-max", quantity="bank_esr_120hz_max_ohm", part="LGX2W561MELC50 x4",
    value_kind="maximum", bound_kind="upper",
    source_condition="120 Hz, 20 C, four equal capacitors in parallel",
    fault_state="not_applicable", assertion="qualified", evidence=NICH,
    justification="0.4737 ohm / 4 = 0.11842 ohm for the bank. This is an upper bound for "
                "the discharge frequency too: aluminium-electrolytic ESR falls with frequency, "
                "so the 120 Hz max exceeds the ESR at the ~0.5-300 kHz discharge content.")

add(id="bank-esr-min-null", quantity="bank_esr_min_ohm", part="LGX2W561MELC50",
    value_kind="assumed", bound_kind="unknown", fault_state="not_applicable",
    assertion="illustrative", evidence=NICH,
    justification="NULL. The datasheet publishes tan_delta max only; no minimum or "
                "high-frequency ESR is published, so no lower bound on bank ESR exists. "
                "A fabricated minimum is not supplied.")

add(id="fuse-watts-loss-rated", quantity="fuse_watts_loss_rated_w", part="A70QS50-14F",
    value_kind="typical", bound_kind="unknown",
    source_condition="A70QS50-14F Watts Loss @ Rated Current = 11.6 W at 50 A "
                     "(Mersen HS catalogue 2024, PDF p.21/HS21)",
    fault_state="not_applicable", assertion="qualified", evidence=MERSEN,
    justification="The table gives no min/max on the watts-loss figure, so it is recorded "
                "as the catalogue's nominal (typical) hot value.")

add(id="fuse-resistance-hot", quantity="fuse_resistance_hot_ohm", part="A70QS50-14F",
    value_kind="typical", bound_kind="upper",
    source_condition="derived from 11.6 W at 50 A rated current; thermal-equilibrium (HOT) figure",
    fault_state="not_applicable", assertion="qualified", evidence=MERSEN,
    justification="R = P/I^2 = 11.6/50^2 = 4.64 mOhm. HOT figure (steady state at rated "
                "current). The element has a positive temperature coefficient, so the cold "
                "onset resistance is lower: 4.64 mOhm is an upper bound on the cold/onset "
                "resistance and a typical value for the hot state. It is NOT a resistance "
                "measured at fault current.")

add(id="u9-rds-on-25c-max", quantity="mosfet_rds_on_25c_max_ohm", part="STW65N65DM2AG",
    value_kind="maximum", bound_kind="upper",
    source_condition="VGS = 10 V, ID = 30 A, Tcase = 25 C (datasheet Table 5 Static)",
    fault_state="healthy_on", assertion="qualified", evidence=STW,
    justification="Rds_on max 0.05 ohm, typ 0.042 ohm at 25 C. This is the healthy/on "
                "switch resistance, valid only for the U9-healthy case at 25 C.")

add(id="u9-rds-on-hot-null", quantity="mosfet_rds_on_hot_ohm", part="STW65N65DM2AG",
    value_kind="assumed", bound_kind="unknown", fault_state="healthy_on",
    assertion="illustrative", evidence=STW,
    justification="NULL. No numeric hot Rds_on is published; the normalised on-resistance is "
                "Figure 10 only. Per the worker rules a room-temperature value must not be "
                "promoted to a hot value, so the hot Rds_on stays unknown.")

add(id="u9-short-residual-null", quantity="mosfet_failed_short_residual_ohm", part="STW65N65DM2AG",
    value_kind="assumed", bound_kind="unknown", fault_state="failed_short",
    assertion="illustrative", evidence=STW,
    justification="NULL. No failed-short (drain-source weld/bridge) residual resistance is "
                "published for STW65N65DM2AG. Rds_on is a healthy/on parameter and is not the "
                "short residual.")

add(id="u10-short-residual-null", quantity="diode_failed_short_residual_ohm", part="C3D20065D",
    value_kind="assumed", bound_kind="unknown", fault_state="failed_short",
    assertion="illustrative", evidence=C3D,
    justification="NULL. No failed-short residual is published for the C3D20065D. The "
                "datasheet's only conduction model is the forward VfT = VT + If*RT model, "
                "which is not a short residual.")

add(id="u10-forward-series-r-25c", quantity="diode_forward_series_resistance_25c_ohm", part="C3D20065D",
    value_kind="typical", bound_kind="unknown",
    source_condition="Tj = 25 C, forward-conduction diode model VfT = VT + If*RT",
    fault_state="healthy_on", assertion="qualified", evidence=C3D,
    justification="RT = 0.044 + 4.4e-4*Tj ohm per leg = 0.055 ohm at 25 C (VT = 0.9298 V). "
                "This is the FORWARD conduction slope, provided for completeness only; the "
                "fault loop's U10 element is a failed short, whose residual is the null above.")

add(id="copper-loop-resistance-lower", quantity="copper_loop_resistance_lower_ohm",
    value_kind="assumed", bound_kind="lower", fault_state="failed_short",
    assertion="illustrative", evidence=GEOM,
    justification="10.289 mOhm: least-resistance >=3 mm-wide copper path from the nearest bank "
                "capacitor U38 (cap+ -> U10 -> a1 -> U9 -> cap-) at 20 C, copper 0.07 mm, "
                "rho 1.72e-8 ohm*m. Every other loop element has resistance >= 0, so the total "
                "loop R is >= this value.")

add(id="copper-loop-resistance-upper", quantity="copper_loop_resistance_upper_ohm",
    value_kind="assumed", bound_kind="upper", fault_state="failed_short",
    assertion="illustrative", evidence=GEOM,
    justification="20.494 mOhm: least-resistance path from the farthest bank capacitor U37 at "
                "100 C (rho 2.30e-8). AC copper R is not below this: at 100 kHz the skin depth "
                "is 0.209 mm >> 0.07 mm copper, so the DC figure is a lower bound on AC copper R "
                "and 100 C bounds the temperature rise of the early pulse.")

add(id="copper-loop-inductance-lower", quantity="copper_loop_inductance_lower_h",
    value_kind="assumed", bound_kind="lower", fault_state="failed_short",
    assertion="illustrative", evidence=GEOM,
    justification="75.8 nH: current-sheet model mu0*h*l/w_eff with the return path directly "
                "beneath the forward path, h = the 1.44 mm single-core dielectric, the shortest "
                "geometry (U38). Return-path assumption stated in geometry.json.")

add(id="copper-loop-inductance-upper", quantity="copper_loop_inductance_upper_h",
    value_kind="assumed", bound_kind="upper", fault_state="failed_short",
    assertion="illustrative", evidence=GEOM,
    justification="2815.5 nH: same model with the return path horizontally offset by the "
                "measured worst-case separation (34.5 mm, U37), h = 1.44 + 34.5 mm. This is the "
                "return-path-dominated upper bound; the return-path assumption dominates L.")

add(id="component-internal-inductance-null", quantity="component_internal_inductance_h",
    value_kind="assumed", bound_kind="unknown", fault_state="failed_short",
    assertion="illustrative", evidence=C3D + STW + MERSEN,
    justification="NULL. Bank, fuse and semiconductor-package internal inductances are not "
                "published. They add >= 0 to the copper loop L and are not bounded; the "
                "geometry-derived copper term already dominates at ~0.1-2.8 uH.")

add(id="known-components-loop-r-upper", quantity="known_components_loop_resistance_upper_ohm",
    value_kind="assumed", bound_kind="upper", fault_state="failed_short",
    assertion="illustrative", evidence=NICH + MERSEN + STW + GEOM,
    justification="193.6 mOhm = bank ESR max 118.42 mOhm (120 Hz) + fuse 4.64 mOhm + U9 Rds_on "
                "25 C max 50.0 mOhm + copper 20.49 mOhm (100 C). This EXCLUDES the two null "
                "failed-short residuals, so it is NOT a loop upper bound; it is the sourced "
                "portion only.")

add(id="loop-resistance-upper-null", quantity="loop_resistance_upper_ohm",
    value_kind="assumed", bound_kind="unknown", fault_state="failed_short",
    assertion="illustrative", evidence=STW + C3D,
    justification="NULL / unbounded above by sourced data: the U9 and U10 failed-short "
                "residuals are unpublished and each could in principle exceed 0.45 ohm, which "
                "would move the total R above the 0.64013 ohm action screen. No upper bound "
                "may be fabricated.")

add(id="loop-inductance-bounds", quantity="loop_inductance_bounds_h",
    value_kind="assumed", bound_kind="unknown", fault_state="failed_short",
    assertion="illustrative", evidence=GEOM + STW + C3D + MERSEN,
    justification="Copper term 75.8 nH to 2815.5 nH; unsourced component internal inductances "
                "add >= 0 and are unknown, so the total L is not closed above. Both bounds sit "
                "inside the campaign's swept range [20 nH, 20 uH].")

add(id="fuse-cap-discharge-tau-condition", quantity="fuse_cap_discharge_max_time_constant_s",
    part="A70QS50-14F", value_kind="maximum", bound_kind="upper",
    source_condition="890 VDC capacitor-discharge rating, L/R <= 2.5 ms (Mersen catalogue PDF p.20/HS20)",
    fault_state="not_applicable", assertion="qualified", evidence=MERSEN)

add(id="fuse-action-screen", quantity="action_screen_r_max_ohm", part="A70QS50-14F",
    value_kind="maximum", bound_kind="upper",
    source_condition="pre-arcing I2t max 280 A2s; E = 179.2376 J; ACTION screen, not melting",
    fault_state="failed_short", assertion="qualified", evidence=MERSEN,
    justification="R <= E/280 = 0.64013 ohm. A pre-arcing ACTION screen only; it does not "
                "establish melting across durations, temperatures or tolerances.")

add(id="time-constant-condition-margin", quantity="max_total_inductance_for_R_ge_400L_h",
    value_kind="assumed", bound_kind="unknown", fault_state="failed_short",
    assertion="illustrative", evidence=GEOM + MERSEN,
    justification="R >= 400*L requires total L <= R_lower/400 = 10.289 mOhm / 400 = 25.72 uH. "
                "The geometry-derived copper L is <= 2.82 uH and no component internal "
                "inductance is published, so the time-constant condition holds for any "
                "physically plausible L (it would need > 25.7 uH to fail), but the unpublished "
                "internal inductances keep it from being closed by sourced data alone.")

add(id="frequency-basis", quantity="discharge_frequency_basis",
    value_kind="assumed", bound_kind="unknown", fault_state="failed_short",
    assertion="illustrative", evidence=GEOM + NICH,
    justification="Dominant discharge frequency ~ 1/(2*pi*L/R) = 0.5-300 kHz for the bounded "
                "(L,R). The datasheet tan_delta is quoted at 120 Hz (its lowest-frequency, "
                "highest-ESR point), so the 120 Hz ESR is an upper bound at the discharge "
                "frequency. Skin depth in copper at 100 kHz is 0.209 mm >> the 0.07 mm copper, "
                "so the DC copper resistance is a lower bound on the AC copper resistance.")

add(id="discharge-location-verdict", quantity="discharge_location_verdict",
    value_kind="assumed", bound_kind="unknown", fault_state="failed_short",
    assertion="illustrative", evidence=GEOM + MERSEN,
    justification="INDETERMINATE. The sourced components give R <= 0.1936 ohm and a copper "
                "L in [75.8, 2815.5] nH, both inside the AR-MERSEN screened region "
                "{400L <= R <= 0.64013 ohm} for any plausible residual; but the U9/U10 "
                "failed-short residuals and the bank ESR minimum are null, so neither "
                "R <= 0.64013 nor R >= 400L is closed by bounds. The verdict is not forced.")

protection_claims = [
    {"case_id": "case-a-U10-short-U9-healthy", "fault_case": "failed_short",
     "interrupting_device": "A70QS50-14F (bus-side candidate F2)",
     "interrupting_device_state": "healthy_on", "interrupts": False, "evidence": MERSEN},
    {"case_id": "case-b-U10-short-U9-failed-short", "fault_case": "failed_short",
     "interrupting_device": "A70QS50-14F (bus-side candidate F2)",
     "interrupting_device_state": "healthy_on", "interrupts": False, "evidence": MERSEN},
    {"case_id": "case-c-line-fed-switch-short", "fault_case": "failed_short",
     "interrupting_device": "F1 (Schurter 0034.3129, line)",
     "interrupting_device_state": "healthy_on", "interrupts": False, "evidence": NETL},
    {"case_id": "case-d-line-surge", "fault_case": "not_applicable",
     "interrupting_device": None, "interrupting_device_state": "not_applicable",
     "interrupts": False, "evidence": []},
]

ledger = {
    "schema": "pfc-campaign-claims/v1",
    "task_id": "AR-BOUNDS",
    "attempt_id": "attempt-001",
    "note": "Component-decomposed bounds for the internal discharge loop R and L of "
            "(caps -> shorted U10 -> a1 -> U9 -> caps). Each value carries its source, "
            "condition and bound direction; unsourced values are null. This is a SCREEN "
            "localisation, not coordination, melting or clearing.",
    "claims": claims,
    "protection_claims": protection_claims,
    "promotions": [],
}
(ATT / "claims.json").write_text(json.dumps(ledger, indent=2) + "\n")
print("wrote", ATT / "claims.json", "claims:", len(claims))

# assignments for the fault-loop connectivity check (magnitudes are illustrative fixtures)
assignments = {
    "U9": 3077.0, "U10": 3077.0,
    "U36": 769.25, "U37": 769.25, "U38": 769.25, "U39": 769.25, "U40": 3.0,
}
(ATT / "raw/assignments.json").write_text(json.dumps(assignments, indent=2) + "\n")
print("wrote", ATT / "raw/assignments.json")
