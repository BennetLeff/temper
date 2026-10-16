#!/usr/bin/env python3
"""PS2 (MEAN WELL MPM-20-24) rating arithmetic -> results/ps2.json.

    python3 -I ps2_calc.py ROOT     (ROOT = the ps2-thermal scratch dir)

Every input carries its source; anything marked "estimate" is a hand estimate made here.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])

# ---------------------------------------------------------------- datasheet (MPM-20-SPEC 2024-10-30)
P_RATED = 21.6                      # p.2 RATED POWER, MPM-20-24
ETA_TYP = 0.87                      # p.2 EFFICIENCY (Typ.), 230 VAC, rated load, 25 C (Note 1)
CURVE = [(55.0, 100.0), (60.0, 70.0), (70.0, 50.0), (85.0, 30.0)]   # p.3 Derating Curve, 12V~24V, (HORIZONTAL); 0 above 85
T_WORK_MAX = 85.0                   # p.2 WORKING TEMP. -35 ~ +85 C (Refer to "Derating Curve"); p.3 x-axis "AMBIENT TEMPERATURE"
BODY = (52.4, 27.2, 24.0)           # p.2 DIMENSION / p.4 Case No.219A, mm


def t_amb_limit(load_pct):
    """Highest ambient at which load_pct is on/under the p.3 curve (linear between the printed points)."""
    if load_pct <= CURVE[-1][1]:
        return CURVE[-1][0]
    for (t0, l0), (t1, l1) in zip(CURVE, CURVE[1:]):
        if l1 <= load_pct <= l0:
            return t0 + (l0 - load_pct) * (t1 - t0) / (l0 - l1)
    return CURVE[0][0]


def curve_load(t):
    if t <= CURVE[0][0]:
        return 100.0
    if t > CURVE[-1][0]:
        return 0.0
    for (t0, l0), (t1, l1) in zip(CURVE, CURVE[1:]):
        if t0 <= t <= t1:
            return l0 + (t - t0) * (l1 - l0) / (t1 - t0)


# ---------------------------------------------------------------- PS2 load (design records)
I_CH = (382.6e-9 + 61e-9) * 60e3 + 0.0044 + 0.003 + 0.0015 + 0.014   # make_heat_sources.py C28_F (60 kHz, 2EDR / 68 ohm, Cgs 4.7 nF)
P_OUT_MODEL = 2 * 17.0 * I_CH / 0.45 + 24 * (2 * I_CH + 0.030) + 24 * 0.010   # same formula (RECOM at the 45 % allocation)
P_OUT_RECOM_TYP = 2 * 17.0 * I_CH / 0.53 + 24 * (2 * I_CH + 0.030) + 24 * 0.010  # ALT-BIAS R13: RECOM 53 % typ
LOADS = {
    "model_60kHz_as_built": (P_OUT_MODEL, "B3 c28 heat file (make_heat_sources.py C28_F; = 1.348 W loss / (1/0.84-1)), used in every BASIS case"),
    "recom_typ_53pct": (P_OUT_RECOM_TYP, "same, RECOM at 53 % typ (ALT-BIAS.md R13) - estimate"),
    "ledger_allocation_80kHz_740nC": (9.59, "ledger stress 'P bias allocation' (ALT-BIAS.md:52), bias-sizing allowance, not a physical charge"),
    "alt_bias_80kHz": (11.10, "ALT-BIAS.md R13 sim/budget.py at 80 kHz, outside the 35-60 kHz window (ledger: not used)"),
}
loads = {}
for k, (p, src) in LOADS.items():
    pct = 100 * p / P_RATED
    loads[k] = {"p_out_w": round(p, 3), "load_pct": round(pct, 1), "source": src,
                "t_amb_limit_c": round(t_amb_limit(pct), 1),
                "t_amb_limit_90pct_rule_c": round(t_amb_limit(pct / 0.9), 1)}

# ---------------------------------------------------------------- B3 field (s42, hot copper, ps-selv run files + this study's solves)
runs = ROOT / "runs-copy"
bays = {"c18_h10": 61.0, "c22_h10": 55.0, "c28_h10": 55.0}
b3 = {}
for c, bay in bays.items():
    r25 = json.loads((runs / f"{c}_p0p25.json").read_text())
    r05 = json.loads((runs / f"{c}_p0p5.json").read_text())
    s = bay - 50.0
    p25, p05 = r25["probes"]["PS2"], r05["probes"]["PS2"]
    part = [p for p in r25["parts"] if p["ref"] == "PS2"][0]
    est = p25["pad_max_cell_c"] + 3 * abs(p25["pad_max_cell_c"] - p05["pad_max_cell_c"]) + s
    b3[c] = {"bay_c": bay, "pad_max_c": round(p25["pad_max_cell_c"] + s, 1), "pad_mean_c": round(p25["pad_mean_c"] + s, 1),
             "gate_estimator_c": round(est, 1), "model_body_node_c": round(part["tj_c"] + s, 1),
             "watts_into_board_w": round(part["watts_into_model"], 3)}

field = {}
for tag in ("base", "zero"):
    f = ROOT / "field" / f"ps2-field-{tag}.json"
    if f.exists():
        field[tag] = json.loads(f.read_text())

# ---------------------------------------------------------------- module network (estimate)
L, W, H = (v * 1e-3 for v in BODY)
A_TOP = L * W
A_SIDES = 2 * (L + W) * H
A_BOTTOM = L * W
H_STILL = 10.0                       # B3 still-air h (b3_ratings_gate BASIS; audit README: physical 7.5-15 incl. radiation)
G_TOP = H_STILL * A_TOP
G_SIDES = H_STILL * A_SIDES
# air-layer rise on a vertical face of height H over hot board: thermal_body.py:245-251 method (k/h ~ 4.3 mm layer,
# exponential profile; face average = (d/H)(1 - exp(-H/d)) x board excess over the bay)
D_LAYER = 4.3e-3
F_SIDE = (D_LAYER / H) * (1 - math.exp(-H / D_LAYER))
F_FILM = (D_LAYER / 17.5e-3) * (1 - math.exp(-17.5e-3 / D_LAYER))     # control: thermal_body's 0.24 for 17.5 mm
# module-to-board: pins (B3's ASSUMED r_pad 15 K/W, thermal_body.py 'meanwell') || bottom-face air gap (estimate)
R_PINS = {"low": 5.0, "mid": 15.0, "high": 40.0}      # K/W total; low = 4 Cu pins 3 mm, high = brass pins + potting
GAP_MM = {"low": 0.5, "mid": 1.0, "high": 2.0}        # bottom face to board (thermal_body standoff 1.0 mm); k_air 0.030
K_AIR = 0.030


def case_temp(p_loss, t_bay, t_board, board_excess_k, g_spread, corner="mid"):
    """Steady case node: P = G_top (Tc - T_bay) + G_sides (Tc - T_layer) + G_cb (Tc - T_board0).
    T_layer = bay + F_SIDE x board excess; G_cb = pins || gap, in series with the board's spreading conductance."""
    g_pin = 1.0 / R_PINS[corner]
    g_gap = K_AIR * A_BOTTOM / (GAP_MM[corner] * 1e-3)
    g_mb = g_pin + g_gap
    g_cb = 1.0 / (1.0 / g_mb + 1.0 / g_spread)
    t_layer = t_bay + F_SIDE * board_excess_k
    tc = (p_loss + G_TOP * t_bay + G_SIDES * t_layer + g_cb * t_board) / (G_TOP + G_SIDES + g_cb)
    q_board = g_cb * (tc - t_board)
    return {"case_c": round(tc, 1), "local_air_side_layer_c": round(t_layer, 1), "g_module_board_w_k": round(g_mb, 4),
            "g_case_to_board0_w_k": round(g_cb, 4), "heat_case_to_board_w": round(q_board, 3),
            "heat_case_to_air_w": round(p_loss - q_board, 3)}


out = {"part": {"ref": "PS2", "mpn": "MPM-20-24", "maker": "MEAN WELL",
                "bom": "native-21/frozen/default.csv (s42 BOM, via monitor-sweep.json) and ledger.json entry MPM-20-24",
                "datasheet": "MPM-20-SPEC 2024-10-30, sha256 24d3a6bb642d74ea..., dl/MANIFEST.json"},
       "rating_basis": {
           "working_temp": {"value_c": T_WORK_MAX, "kind": "AMBIENT (surrounding air), with load derating",
                            "quote": "p.2 'WORKING TEMP. -35 ~ +85℃ (Refer to \"Derating Curve\")'; p.3 curve x-axis 'AMBIENT TEMPERATURE (℃)', '(HORIZONTAL)'"},
           "derating_curve_12_24V": {"points_c_pct": CURVE, "source": "p.3 Derating Curve, read from a 300 dpi render (dl/../render/mpm20-derating2/3.png)"},
           "case_temperature_limit": None,
           "case_temperature_note": "No Tc limit and no Tc measurement point in MPM-20-SPEC (4 pp.) or in the MEAN WELL PCB-type installation manual (PCB_EN.pdf, families incl. MPM). Only OTP: p.2 'OVER TEMPERATURE Protection type : Shut down o/p voltage, recovers automatically after temperature goes down' (no threshold).",
           "installation_condition": "PCB_EN.pdf p.1 Installation (4): 'Allow good ventilation ... a 10-15 cm clearance must be kept when the adjacent device is a heat source'; (5) high ambient requires de-rating per the spec; Warning (3) p.2 'refer to the specifications about the maximum ambient temperature limitations'.",
           "test_conditions": "p.2 Note 1: all parameters at 230VAC input, rated load and 25 C ambient unless stated",
           "safety_standards": "p.2 'IEC 60601-1:2005+A1, TUV BS EN/EN 60601-1:2006+A1+A12+A2, ANSI/AAMI ES60601-1:2005/A2:2021, CAN/CSA C22.2 No. 60601-1:2014+A2, IEC 60335-1:2010/AMD2:2016, Dekra BS EN/EN 60335-1:2012+A11+A13+A1+A14+A2+A15, EAC TP TC 004 approved'; 2xMOPP; I/P-O/P 4KVAC; touch current <80 uA/264VAC (Note 7). No IEC/UL 62368-1, no UL file number, and no temperature (Tma) printed for the approvals.",
       },
       "loads": loads,
       "b3_pad_proxy": b3,
       "field_study": field,
       "network_constants": {"A_top_m2": A_TOP, "A_sides_m2": A_SIDES, "A_bottom_m2": A_BOTTOM, "h_w_m2k": H_STILL,
                             "side_layer_factor": round(F_SIDE, 3), "control_film_factor_17p5mm": round(F_FILM, 3),
                             "R_pins_k_w": R_PINS, "gap_mm": GAP_MM, "k_air": K_AIR},
       }
(ROOT / "results").mkdir(exist_ok=True)
if __name__ == "__main__" and "--print" in sys.argv:
    print(json.dumps(out, indent=1)[:4000])
globals()["OUT"] = out


# ================================================================ analysis (appended)
P_LOSS = {   # module loss = Pout (1/eta - 1)
    "model_7p08W_eta0p84": P_OUT_MODEL * (1 / 0.84 - 1),          # = the B3 heat row 1.348 W (make_heat_sources eta 0.84)
    "model_7p08W_eta0p80": P_OUT_MODEL * (1 / 0.80 - 1),          # make_heat_sources worst eta
    "model_7p08W_eta0p87": P_OUT_MODEL * (1 / ETA_TYP - 1),       # datasheet typ (230 VAC, full load: optimistic here)
    "alloc_9p59W_eta0p84": 9.59 * (1 / 0.84 - 1),
}
fb, fz = field["base"], field["zero"]
pad0_mean = fz["ps2_probe_c"]["pad_mean_c"]
pad_mean = fb["ps2_probe_c"]["pad_mean_c"]
g_spread = fb["ps2_watts_into_model"] / (pad_mean - pad0_mean)        # board spreading at PS2's pads (pad-mean basis)
self_heat_k = pad_mean - pad0_mean
under0 = fz["board_under_body"]["F.Cu"]["body_mean_c"]
ring0 = fz["board_under_body"]["F.Cu"]["ring_mean_c"]
pin_max0 = max(v["F.Cu"]["mean_c"] for v in fz["per_pad_c"].values())

# c22 / c28: no zero-PS2 solve (2-solve budget). Superpose: PS2's own pad rise is the c18 value (same 0.674 W, same copper;
# hot-copper loop gain 0.06 / 0.12 changes it by a few %); the board around PS2 scales with the nearby unheated probes.
NEAR = ["R22", "R23", "R24", "R25", "J3", "R1", "R2"]
near_ex = {}
for c, bay in bays.items():
    r = json.loads((runs / f"{c}_p0p25.json").read_text())
    near_ex[c] = sum(r["probes"][q]["pad_mean_c"] + bay - 50 - bay for q in NEAR) / len(NEAR)
cases = {}
for c, bay in bays.items():
    k = near_ex[c] / near_ex["c18_h10"]
    if c == "c18_h10":
        t_pad0, t_under0, t_ring0, t_pin0 = pad0_mean, under0, ring0, pin_max0
        basis = "zero-PS2 solve (this study, 0.5 mm)"
    else:
        t_pad0 = b3[c]["pad_mean_c"] - self_heat_k
        t_under0 = bay + (under0 - 61.0) * k
        t_ring0 = bay + (ring0 - 61.0) * k
        t_pin0 = bay + (pin_max0 - 61.0) * k
        basis = f"estimate: B3 pad mean - c18 self-heat {self_heat_k:.1f} K; under/ring/pin2 scaled x{k:.2f} by nearby probes {NEAR}"
    ring_ex = t_ring0 - bay
    corners = {}
    for corner in ("low", "mid", "high"):
        # air: top face to bay air, sides to the board's warm layer (thermal_body film method)
        t_layer = bay + F_SIDE * ring_ex
        g_air = G_TOP + G_SIDES
        t_air_eff = (G_TOP * bay + G_SIDES * t_layer) / g_air
        g_pin = 1.0 / (R_PINS[corner] + 1.0 / g_spread)                       # pins + board spreading at the pads
        g_gap_raw = K_AIR * A_BOTTOM / (GAP_MM[corner] * 1e-3)
        g_under = 2 * H_STILL * A_BOTTOM                                       # board patch under the body to air, both faces (estimate)
        g_gap = 1.0 / (1.0 / g_gap_raw + 1.0 / g_under)
        g_b = g_pin + g_gap
        t_b = (g_pin * t_pad0 + g_gap * t_under0) / g_b
        t_eq = (g_air * t_air_eff + g_b * t_b) / (g_air + g_b)               # equivalent ambient: P-independent
        r_free = 1.0 / (g_air + g_b)
        row = {"local_air_side_layer_c": round(t_layer, 1), "board_seen_c": round(t_b, 1), "t_equivalent_ambient_c": round(t_eq, 1),
               "g_air_w_k": round(g_air, 4), "g_board_w_k": round(g_b, 4)}
        for pk, pl in P_LOSS.items():
            tc = t_eq + pl * r_free
            q_pin = g_pin * (tc - t_pad0)
            row[pk] = {"p_loss_w": round(pl, 3), "case_c": round(tc, 1),
                       "pad_mean_c": round(t_pad0 + q_pin / g_spread, 1), "heat_to_board_w": round(g_b * (tc - t_b), 3),
                       "heat_to_air_w": round(g_air * (tc - t_air_eff), 3)}
        corners[corner] = row
    # pessimistic bound: the module's whole surroundings at max(bay + 15 K repo cap-air convention, hottest PS2 pad without PS2 heat)
    t_bound = max(bay + 15.0, t_pin0)
    lim = {k: v["t_amb_limit_c"] for k, v in loads.items()}
    lim90 = {k: v["t_amb_limit_90pct_rule_c"] for k, v in loads.items()}
    cases[c] = {"bay_c": bay, "basis": basis, "pad_mean_no_ps2_c": round(t_pad0, 1), "board_under_body_no_ps2_c": round(t_under0, 1),
                "ring_10mm_no_ps2_c": round(t_ring0, 1), "hottest_pad_no_ps2_c": round(t_pin0, 1), "corners": corners,
                "bound_surroundings_c": round(t_bound, 1),
                "margin_k_central": {k: round(lim[k] - corners["mid"]["t_equivalent_ambient_c"], 1) for k in lim},
                "margin_k_central_90pct_rule": {k: round(lim90[k] - corners["mid"]["t_equivalent_ambient_c"], 1) for k in lim90},
                "margin_k_bound": {k: round(lim[k] - t_bound, 1) for k in lim},
                "b3_gate_margin_k_pad_vs_85": round(85.0 - b3[c]["gate_estimator_c"], 1)}

out["analysis"] = {
    "ps2_self_heat_on_own_pads_k": round(self_heat_k, 1),
    "board_spreading_at_pads_k_per_w": round(1 / g_spread, 1),
    "per_pad_c18": {n: {"with_ps2_c": round(fb["per_pad_c"][n]["F.Cu"]["mean_c"], 1), "without_ps2_c": round(fz["per_pad_c"][n]["F.Cu"]["mean_c"], 1)}
                    for n in fb["per_pad_c"]},
    "pad_nets": {"1": "tco_l (0.4 mm F.Cu track, 53.8 mm to J3)", "2": "n_filt (F.Cu pour 1823 mm2, mains neutral after L1)",
                 "3": "n_ls (0.4 mm In1 track)", "4": "v24_raw (0.4 mm In1 track)"},
    "control": "base solve reproduces the ps-selv c18_h10_p0p5 PS2 probe: pad max 108.81 C, mean 104.87 C (= run file)",
    "nearby_probe_excess_k": {c: round(v, 1) for c, v in near_ex.items()},
    "cases": cases,
}
(ROOT / "results" / "ps2.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out["analysis"], indent=1))
