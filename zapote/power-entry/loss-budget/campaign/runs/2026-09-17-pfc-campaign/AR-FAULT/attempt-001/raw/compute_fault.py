#!/usr/bin/env python3
"""AR-FAULT attempt-001: boost-switch-short fault assessment on the ACTUAL board.

Board: zapote/power-entry/shunt-repair/candidate/section.kicad_sch / .kicad_pcb
Task: verify the AR-VERIFY ~586.7 V claim and bound V/I/E for the boost switch
      short (and the boost-diode short), from the traced circuit, not by adding
      two node voltages.

This script:
  1. Re-reads the bus-capacitance values from the candidate source manifest
     (not hand-copied) and computes the stored energy.
  2. Recomputes the AR-VERIFY 586.7 V arithmetic and shows it is an explicit
     sum of two node potentials (their own line 415).
  3. Computes the boost-switch-short line-fed fault current parametrically,
     because the AC source/line impedance is NOT established on this board.
  4. Computes the boost-diode-short standing voltage and the bus-capacitor
     discharge if the switch conducts.

Everything that is assumed is labelled ASSUMED and kept out of the sourced set.
"""
import json
import math
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ATTEMPT = HERE.parent
REPO = Path("/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan")

MANIFEST = REPO / "zapote/power-entry/shunt-repair/candidate/source-manifest.json"
SCH = REPO / "zapote/power-entry/shunt-repair/candidate/section.kicad_sch"

out = {"schema": "pfc-campaign-AR-FAULT-compute/v1", "task_id": "AR-FAULT",
       "attempt_id": "attempt-001"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- sourced facts
# Sourced from the candidate source-manifest.json (component values) and
# elec/src/power_entry_unit.ato (ratings); regressions in the repo.
man = json.loads(MANIFEST.read_text())
comp = {c["reference"]: c for c in man["components"]}
nets = {n["name"]: n["nodes"] for n in man["bridge"]["nets"]}

out["board_identity"] = {
    "schematic_sha256": sha256(SCH),
    "pcb_sha256": man["board_sha256"],
    "source_manifest_sha256": sha256(MANIFEST),
    "footprints": man["board"]["footprints"],
    "nets": man["board"]["nets"],
    "entry": man["entry"],
}

# Bus bank: c1..c4 = 560 uF 450 V (LGX2W561MELC50), c_hf = 470 nF 630 V
# (B32672P6474K000). Values read from the manifest; ratings from the ato
# (voltage_rating fields). Datasheet captures for LGX not present in this tree.
bus_caps = {}
for ref, key in [("U36", "c1"), ("U37", "c2"), ("U38", "c3"), ("U39", "c4")]:
    v = comp[ref]["value"]
    bus_caps[ref] = {"instance": key, "value": v, "rating_v": 450,
                     "mpn": comp[ref]["mpn"]}
bus_caps["U40"] = {"instance": "c_hf", "value": comp["U40"]["value"],
                   "rating_v": 630, "mpn": comp["U40"]["mpn"]}
out["bus_capacitors"] = bus_caps

def uf(s):
    t = s.strip().lower().replace("f", "")
    mult = 1e-6
    if t.endswith("u"):
        t, mult = t[:-1], 1e-6
    elif t.endswith("n"):
        t, mult = t[:-1], 1e-9
    elif t.endswith("p"):
        t, mult = t[:-1], 1e-12
    return float(t) * mult

C_bulk = sum(uf(bus_caps[r]["value"]) for r in ("U36", "U37", "U38", "U39"))
C_hf = uf(bus_caps["U40"]["value"])
C_bus = C_bulk + C_hf
out["bus_capacitance"] = {
    "C_bulk_f": C_bulk, "C_hf_f": C_hf, "C_total_f": C_bus,
    "note": "4x560uF bulk in parallel + 470nF film, all from PFC_BUS_PLUS_390V "
            "to PFC_BUS_MINUS (netlist).",
}

V_BUS = 400.0        # contract bus_setpoint_v; net is named ..._390V
V_BUS_NAMEPLATE = 390.0
V_LINE_PEAK_132 = 132.0 * math.sqrt(2)

def half_c_v2(c, v):
    return 0.5 * c * v * v

out["stored_energy"] = {
    "at_400v_j": half_c_v2(C_bus, V_BUS),
    "at_390v_j": half_c_v2(C_bus, V_BUS_NAMEPLATE),
    "bulk_only_at_400v_j": half_c_v2(C_bulk, V_BUS),
    "hf_film_at_400v_j": half_c_v2(C_hf, V_BUS),
    "at_450v_rating_j": half_c_v2(C_bus, 450.0),
}
# Bleeder: R_bleed = 150k + 150k in series (U53+U54) across the bus
R_BLEED = 300_000.0
E_bus_400 = half_c_v2(C_bus, V_BUS)
out["bus_discharge_natural"] = {
    "bleeder_ohm": R_BLEED,
    "tau_s": R_BLEED * C_bus,
    "p_bleed_at_400v_w": V_BUS ** 2 / R_BLEED,
    "time_to_34v_s": R_BLEED * C_bus * math.log(V_BUS / 34.0),
    "note": "passive bleed path hv_plus->bleeder1->bleeder2->control_gnd. "
            "No active bus-discharge part is present on this candidate netlist.",
}

# ------------------------------------------------- the 586.7 V claim, recomputed
V_peak_132 = V_LINE_PEAK_132
claim = V_BUS + V_peak_132
out["claim_586_7"] = {
    "recomputed_v": claim,
    "construction": "V_BUS(400) + V_line_peak(132 Vrms=186.676) = 586.676",
    "proof_it_is_a_sum": "AR-VERIFY raw/compute_ar_verify.py:415 computes "
        "round(v_bus + v_peak_132, 2); margin line 422 computes 600/(v_bus+v_peak_132).",
    "verdict": "NOT A SINGLE-FAULT DEVICE STRESS (see result.json).",
}

# ------------------------------------------- boost-switch-short (U9 D-S short)
# After the short, a1 == PFC_BUS_MINUS. L (180uH, Isat 43A typ, DCR 20mOhm max)
# is placed across the bridge DC output. D10 anode=a1, cathode=hv_plus, so the
# bus capacitor is reverse-biased across D10 and does NOT discharge into U9.
L = 180e-6
L_tol = 0.20
I_SAT = 43.0          # typ, |dL/L|<30%
R_L_DCR = 0.020       # max @20C
R_SHUNT = 0.010
V_F_BRIDGE = 1.05     # per diode, GBJ2510 VF typ @12.5A/25C; two in series
R_KNOWN = R_L_DCR + R_SHUNT
V_head = V_LINE_PEAK_132 - 2 * V_F_BRIDGE

switch_short = {
    "fault_node_map": "a1 = l_boost.2 = q_boost.D(2) = d_boost.A1/A2(1,3)",
    "loop": "mains L -> F1 -> CMC L1-L2 -> NTC(U4, bypassed by U5 when running) "
            "-> bridge U1 AC1 -> upper diode -> PLUS -> L(U8) -> a1 -> shorted "
            "U9 -> PFC_BUS_MINUS(control_gnd) -> shunt U12 -> bridge MINUS -> "
            "lower diode -> AC2 -> CMC N2-N1 -> mains N",
    "bus_cap_in_loop": False,
    "bus_cap_reason": "D10 (a1->hv_plus) is reverse-biased by the full bus "
        "voltage; there is no path from hv_plus to the shorted switch.",
    "diode_reverse_voltage_v": V_BUS,
    "pre_saturation": {
        "di_dt_a_per_s_at_132v": V_LINE_PEAK_132 / L,
        "time_to_isat_s": I_SAT / (V_LINE_PEAK_132 / L),
        "note": "L limits di/dt only until Isat(43 A typ, 30% drop).",
    },
    "bridge_sees": {
        "max_reverse_v": V_LINE_PEAK_132,
        "note": "bridge output tracks the rectified line (inductor averages ~0 V).",
    },
}
# Parametric post-saturation peak current: I = (V_peak - 2*VF)/(R_known + R_unknown)
rows = []
for R_unk in (0.0, 0.01, 0.02, 0.05, 0.10, 0.30, 1.00, 10.0):
    R_tot = R_KNOWN + R_unk
    I = V_head / R_tot if R_tot > 0 else float("inf")
    rows.append({"R_unknown_ohm": R_unk, "R_total_ohm": R_tot, "I_peak_a": I,
                 "label": "UNKNOWN-input proxy" if R_unk > 0 else
                          "board-only absolute upper bound (source=ideal short)"})
switch_short["post_saturation_parametric"] = rows
switch_short["known_board_resistance_ohm"] = R_KNOWN
switch_short["v_head_v"] = V_head
out["boost_switch_short"] = switch_short

# --------------------------------------------- boost-diode-short (U10 K-A short)
# a1 == hv_plus. L DC-couples hv_plus to bridge.PLUS. Bus negative sits on
# bridge.MINUS through the shunt. Bridge diodes clamp the AC terminals to
# [MINUS, PLUS]; max single-diode reverse ~ V_BUS. No V_BUS+V_line series node.
R_DS_ON_TYP = 0.042
R_DS_ON_MAX = 0.050
diode_short = {
    "fault_node_map": "d_boost.K(2)=hv_plus shorted to d_boost.A1/A2(1,3)=a1; "
                      "a1 DC-couples through L to bridge PLUS",
    "standing_voltage": {
        "bridge_plus_v": V_BUS,
        "bridge_minus_v": 0.0,
        "boost_switch_vds_v": V_BUS,
        "bridge_diode_max_reverse_v": V_BUS,
        "why_not_586_7": "the bridge's own low-side diode clamps each AC "
            "terminal to >= MINUS-Vf, so the line cannot pull an AC node to "
            "the opposite peak; max reverse across a bridge diode is ~V_BUS.",
    },
    "if_switch_conducts": {
        "label": "bus-cap discharge (internal loop; AC fuse F1 does NOT see it)",
        "R_on_typ": R_DS_ON_TYP, "R_on_max": R_DS_ON_MAX, "R_shunt": R_SHUNT,
        "I_peak_typ_a": V_BUS / (R_DS_ON_TYP + R_SHUNT),
        "I_peak_max_a": V_BUS / (R_DS_ON_MAX + R_SHUNT),
        "tau_s_typ": (R_DS_ON_TYP + R_SHUNT) * C_bus,
        "energy_total_j": E_bus_400,
        "energy_into_switch_typ_j": E_bus_400 * R_DS_ON_TYP / (R_DS_ON_TYP + R_SHUNT),
        "energy_into_shunt_typ_j": E_bus_400 * R_SHUNT / (R_DS_ON_TYP + R_SHUNT),
        "peak_switch_power_typ_w": (V_BUS / (R_DS_ON_TYP + R_SHUNT)) ** 2 * R_DS_ON_TYP,
        "caveat": "requires the controller to keep U9 on after D10 shorts; if "
            "the 400 V bus is fed back on VSENSE the controller has no signal "
            "to stop, but its response is not established here.",
    },
}
out["boost_diode_short"] = diode_short

# ------------------------------------------------ interruption / protection
out["interruption"] = {
    "fuse_F1": {
        "designator": "F1", "holder": "U2 (Schurter FUP 0031.2510)",
        "mpn": "0034.3129", "family": "Schurter FST 5x20 mm",
        "rating": "16 A / 250 V, time-lag (T)",
        "source": "docs/hardware/BOM.md:44, docs/hardware/"
                  "IEC60335_CRITICAL_COMPONENTS.md:77, elec/src/modules.ato:662",
        "pre_arcing_i2t": None,
        "pre_arcing_i2t_note": "NOT captured anywhere in this tree; no "
            "I2t/time-current coordination analysis exists (BOM.md:77).",
        "in_switch_short_loop": True,
        "in_bus_cap_discharge_loop": False,
        "breaking_capacity_v": 250,
    },
    "line_vs_cap_timescale": {
        "line_frequency_fault": "rectified 120 Hz current fed through F1; "
            "interrupted by the 16 A time-lag fuse (timescale ms..10s of ms, "
            "not established).",
        "cap_discharge": "2240 uF through ~50 mohm: tau ~= 116 us; the AC fuse "
            "is not in this loop, so nothing on the board interrupts it.",
    },
    "mov_in_loop": {
        "designator": "U7 (V150LA10AP)",
        "connection": "l1 (line after F1) to AC_N_RECTIFIED_INPUT (neutral) - "
            "line-to-neutral, downstream of the fuse",
        "netlist_evidence": "nets 'l1': [U7.1, U6.1, U3.1, U2.2]; "
            "'AC_N_RECTIFIED_INPUT': [U42.2, U6.2, U7.2, U3.2]",
        "in_switch_short_loop": False,
        "in_diode_short_loop": False,
        "reason": "neither bus rail reaches the MOV's terminals; it clamps the "
            "line only. It is therefore NOT automatically (and here, not at "
            "all) in either internal fault loop.",
    },
}

# ---------------------------------------------- device withstand summary
out["device_ratings"] = {
    "U9_switch": {"mpn": "STW65N65DM2AG", "vds_v": 650, "id_a": 65,
                  "idm_a": 240, "rds_on_typ_ohm": R_DS_ON_TYP,
                  "rds_on_max_ohm": R_DS_ON_MAX, "eas_single_pulse_mj": 1100,
                  "source": "captured STW65N65DM2AG datasheet"},
    "U10_diode": {"mpn": "C3D20065D", "v_rating": 650,
                  "source": "ato voltage_rating=650V; datasheet NOT captured here"},
    "U1_bridge": {"mpn": "GBJ2510-F", "vrrm_v": 1000, "if_a": 25,
                  "ifsm_a": 350, "i2t_a2s": 510,
                  "source": "Diodes-GBJ2510.pdf"},
    "U8_inductor": {"mpn": "760800301", "L_h": L, "isat_typ_a": I_SAT,
                    "rdc_max_ohm": R_L_DCR, "ir_a": 24.5,
                    "source": "captured WE-TORPFC 760800301 datasheet"},
}

out["unresolved_assumptions"] = [
    "AC source/line impedance at the fault (R and X) - NOT established, and "
    "the single largest factor in the peak switch-short current.",
    "F1 pre-arcing I2t / time-current curve - NOT captured.",
    "NTC U4 state at the fault instant (bypassed by U5 when running vs cold "
    "10 ohm).",
    "Controller (U11) response after a diode short - whether U9 keeps switching.",
    "Bus setpoint tolerance and any overshoot above 400 V.",
    "U10 C3D20065D surge/energy ratings - datasheet not captured here.",
    "c1..c4 datasheet voltage rating (450 V from ato only; LGX capture absent).",
    "Whether an external load is attached to U52 at the fault (affects bus discharge).",
]

HERE.joinpath("compute_result.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps({k: out[k] for k in
      ("bus_capacitance", "stored_energy", "claim_586_7", "bus_discharge_natural")},
      indent=2))
print("\nswitch-short parametric I_peak:")
for r in rows:
    print(f"  R_unknown={r['R_unknown_ohm']:>6} ohm -> I_peak={r['I_peak_a']:.1f} A")
