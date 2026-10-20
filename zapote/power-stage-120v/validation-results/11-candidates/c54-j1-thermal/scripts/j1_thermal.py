#!/usr/bin/env python3
"""J1 (Phoenix 1714971, MKDS 5/ 2-9,5) with the real cord: a two-node terminal model, bounded, and the fixes.

    python3 -I scripts/j1_thermal.py        -> results/j1_thermal.json, results/j1_thermal.md

Reads results/j1_buildup.json (scripts/j1_buildup.py: the B3 pad estimate of the hot pole on the s53 board of record)
and results/phoenix_1714971_p6.json (scripts/digitize_p6.py: the p.6 derating trace). Nothing else; stdlib only.

MODEL (one pole; both poles carry the same current, so by symmetry no heat crosses between them)
  node C  the clamp (current bar + tension sleeve + conductor end); its temperature is the terminal-point temperature
          that both the terminal's 105 C upper limiting temperature (p.5) and the lead's 105 C insulation see.
  node P  the board pad. B3 gives its temperature with nothing attached, T_P0 (the S21 'pad'); a heat Q pushed into the
          board raises it by R_b Q (driving-point resistance of the pad's copper, a Thevenin source).
  heat    P_pole = I^2 R_pole, all of it put on node C (conservative for C: part of it is made in the pin, nearer P).
  paths   C-P  the solder pin, 0.9 x 0.9 mm (p.4), length L, Cu alloy (p.3) k: G_pin = k A / L, in series with R_b;
          C-cord  the lead as a semi-infinite insulated fin with Joule heat q'(T) = I^2 r'20 (1 + alpha (T - 20)):
                  H' = 1 / (ln(r_o/r_c) / (2 pi k_ins) + 1 / (h pi D_o)) per metre, b = I^2 r'20 alpha,
                  theta_inf = q'(T_air) / (H' - b), G_cord = sqrt(k_cu A_cu (H' - b)); heat into the lead
                  G_cord (T_C - T_air - theta_inf) (negative: the lead heats the clamp);
          C-air  the PA housing share, G_h, to the board-heated air around the body, T_hous.
  solve   P_pole = G_pb (T_C - T_P0) + G_cord (T_C - T_inf) + G_h (T_C - T_hous),  G_pb = 1 / (1/G_pin + R_b)
          T_P = T_P0 + R_b G_pb (T_C - T_P0).
  Linear in the temperatures (copper TCR enters q'(T_air) and b exactly; R_pole is taken at its stated value).

BOUNDS: every uncertain input takes its low and high value (grid below) and the bound is the min / max of T_C over the
whole grid; no direction is assumed (whether a stiffer pin or board helps depends on whether the clamp is hotter or
colder than the pad).
"""
import itertools
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RES = ROOT / "results"

# ---------------------------------------------------------------- fixed inputs (sources in README section 2)
I_REL, I_TRIP = 13.5, 15.0          # A: inlet regulated (DECISIONS 56, B3 basis) / trip (ledger stress, DECISIONS 168-182)
LIMIT_C = 105.0                     # Phoenix 1714971 p.5 operating ambient -40..105 C 'depending on ... derating curve';
                                    # p.4 IEC 60947-7-4 rise test: ambient + rise <= upper limiting temperature
LEAD_LIMIT_C = 105.0                # inlet-to-J1 leads >= 14 AWG, >= 105 C (F1-RECOMMENDATION.md:179)
ALPHA = 0.00393                     # copper TCR, 1/K (b3_ratings_gate margins basis alpha_per_k)
K_CU = 390.0                        # W/m/K, annealed conductor copper
K_PVC = 0.19                        # W/m/K, PVC insulation
PIN_A = 0.9e-3 * 0.9e-3             # m^2, solder pin 0.9 x 0.9 mm (p.4 'Pin dimensions')
# lead: copper area, r'20, conductor OD, insulated OD (UL 1015-class 105 C AWM, 0.79 mm wall)
WIRES = {
    "14 AWG": {"a_m2": 2.081e-6, "r20": 8.286e-3, "dc": 1.85e-3, "do": 3.43e-3},   # r'20 8.286 mohm/m: repo cord value
    "12 AWG": {"a_m2": 3.309e-6, "r20": 5.211e-3, "dc": 2.35e-3, "do": 3.93e-3},   # (02-protection-timing/f2-coordination)
    "6 mm2":  {"a_m2": 6.0e-6,   "r20": 3.08e-3,  "dc": 2.76e-3, "do": 4.36e-3},   # Phoenix's curve conductor (p.6)
}
# ---------------------------------------------------------------- uncertain inputs: (low, high) and the central value
GRID = {
    "r_pole_mohm": (0.4, 1.0),      # clamp contact + bar + pin. High 1.0 = the IEC voltage-drop limit, 3.2 mV at 0.1 x
                                    # the rated section's current (4 mm2 nominal, p.1: 32 A -> 3.2 A), which applies
                                    # before AND after the test sequence (Phoenix electrical-tests page). Low 0.4 =
                                    # Phoenix: 'up to 60 % below the limit values'. The p.6 calibration (results) lands
                                    # inside this range for test-board ties 0.01-0.03 W/K. Not covered: 14 AWG is below
                                    # the rated section (bench item 1).
    "pin_k": (120.0, 380.0),        # W/m/K, 'Cu alloy' (p.3): brass ... high-copper alloy
    "pin_l_mm": (5.0, 8.0),         # clamp-to-pad pin length from the p.6 section (3.4 mm seat + jog + bar)
    "r_b_kw": (20.0, 180.0),        # K/W, pad driving point: 5.88 mm x 70 um B.Cu edge strip (task-04 ac_n_main field),
                                    # fin estimate 85-180 K/W, 20 K/W if inner-layer copper couples under it
    "cord_h": (8.0, 18.0),          # W/m2/K on the lead surface: laced / jacketed pair ... single lead in free air
    "lead_air_rise_k": (0.0, 5.0),  # lead air over the bay: the wire enters at J1's rear face (y 4.6) and leaves the board
                                    # over the y = 0 edge within 5 mm (DECISIONS 29 placement), so its decay length
                                    # (6-10 cm, results) is off-board, in bay air (+5 K allowance for the edge plume)
    "housing_air_rise_k": (5.0, 15.0),  # J1's 21.5 mm body sits in the board-heated layer: up to the gate's 15 K
                                    # board-heated-air rule (thermal_body.MODULE_AIR_RISE_K)
    "g_h": (0.005, 0.010),          # W/K per pole, bar -> PA wall (k 0.25, 1.5-2 mm over 2.5-3.5 cm2) -> ~7.8 cm2 of
                                    # housing (p.4: 19.04 x 12.05 x 21.5 mm, two poles) at h 10-14 incl. radiation
}
CENTRAL = {"r_pole_mohm": 0.6, "pin_k": 250.0, "pin_l_mm": 6.5, "r_b_kw": 80.0, "cord_h": 12.0, "lead_air_rise_k": 2.0,
           "housing_air_rise_k": 10.0, "g_h": 0.0075}
BAY_REL = 61.0


def cord(wire, i_a, t_air, h):
    w = WIRES[wire]
    r_ins = math.log(w["do"] / w["dc"]) / (2 * math.pi * K_PVC)
    r_surf = 1.0 / (h * math.pi * w["do"])
    hp = 1.0 / (r_ins + r_surf)
    b = i_a ** 2 * w["r20"] * ALPHA
    qa = i_a ** 2 * w["r20"] * (1 + ALPHA * (t_air - 20.0))
    he = hp - b
    if he <= 0:
        raise SystemExit(f"{wire} at {i_a} A: thermal runaway in the lead (H' {hp:.4f} <= b {b:.4f})")
    th = qa / he
    return {"h_per_m": hp, "theta_inf_k": th, "t_inf_c": t_air + th, "g_cord": math.sqrt(K_CU * w["a_m2"] * he),
            "decay_m": math.sqrt(K_CU * w["a_m2"] / he), "q_w_per_m": qa}


def solve(t_p0, bay, i_a, wire, p):
    t_air = bay + p["lead_air_rise_k"]
    t_hous = bay + p["housing_air_rise_k"]
    c = cord(wire, i_a, t_air, p["cord_h"])
    g_pin = p["pin_k"] * PIN_A / (p["pin_l_mm"] * 1e-3)
    g_pb = 1.0 / (1.0 / g_pin + p["r_b_kw"])
    pw = i_a ** 2 * p["r_pole_mohm"] * 1e-3
    g_tot = g_pb + c["g_cord"] + p["g_h"]
    t_c = (pw + g_pb * t_p0 + c["g_cord"] * c["t_inf_c"] + p["g_h"] * t_hous) / g_tot
    t_p = t_p0 + p["r_b_kw"] * g_pb * (t_c - t_p0)
    return {"t_c": t_c, "t_p": t_p, "p_pole_w": pw, "q_to_board_w": g_pb * (t_c - t_p0),
            "q_to_lead_w": c["g_cord"] * (t_c - c["t_inf_c"]), "lead_far_c": c["t_inf_c"], "g_pb": g_pb, **c}


def bounds(t_p0, bay, i_a, wire, grid=GRID, t_p0_hi=None):
    """min / max of T_C over the grid; t_p0 may itself be a (low, high) pair."""
    keys = list(grid)
    lo, hi = None, None
    tp_set = (t_p0,) if t_p0_hi is None else (t_p0, t_p0_hi)
    for tp in tp_set:
        for vals in itertools.product(*(grid[k] for k in keys)):
            p = dict(zip(keys, vals))
            r = solve(tp, bay, i_a, wire, p)
            if lo is None or r["t_c"] < lo[0]["t_c"]:
                lo = (r, p, tp)
            if hi is None or r["t_c"] > hi[0]["t_c"]:
                hi = (r, p, tp)
    tp_c = t_p0 if t_p0_hi is None else 0.5 * (t_p0 + t_p0_hi)
    mid = solve(tp_c, bay, i_a, wire, CENTRAL)
    pack = lambda x: {"t_c": round(x[0]["t_c"], 2), "t_pad_c": round(x[0]["t_p"], 2), "t_p0": round(x[2], 2),
                      "lead_far_c": round(x[0]["lead_far_c"], 2), "p_pole_w": round(x[0]["p_pole_w"], 4),
                      "q_to_board_w": round(x[0]["q_to_board_w"], 4), "q_to_lead_w": round(x[0]["q_to_lead_w"], 4),
                      "inputs": x[1]}
    return {"low": pack(lo), "high": pack(hi),
            "central": {"t_c": round(mid["t_c"], 2), "t_pad_c": round(mid["t_p"], 2), "t_p0": round(tp_c, 2),
                        "lead_far_c": round(mid["lead_far_c"], 2), "p_pole_w": round(mid["p_pole_w"], 4),
                        "q_to_board_w": round(mid["q_to_board_w"], 4), "q_to_lead_w": round(mid["q_to_lead_w"], 4),
                        "inputs": CENTRAL}}


def sensitivity(t_p0, bay, i_a, wire):
    """One-at-a-time swing of T_C about CENTRAL (tornado), K."""
    base = solve(t_p0, bay, i_a, wire, CENTRAL)["t_c"]
    out = {}
    for k, (a, b) in GRID.items():
        ta = solve(t_p0, bay, i_a, wire, {**CENTRAL, k: a})["t_c"]
        tb = solve(t_p0, bay, i_a, wire, {**CENTRAL, k: b})["t_c"]
        out[k] = {"at_low": round(ta - base, 2), "at_high": round(tb - base, 2)}
    return dict(sorted(out.items(), key=lambda kv: -max(abs(kv[1]["at_low"]), abs(kv[1]["at_high"]))))


# ---------------------------------------------------------------- the p.6 curve
def curve_rise(cur, curve_json):
    """Own rise (105 C - ambient) at current cur from the digitized trace (solid falling branch + dashed branch),
    linear interpolation in I."""
    pts = [(105.0 - t, i) for t, i in curve_json["solid_falling_branch"]] + \
          [(105.0 - t, i) for t, i in curve_json["dashed_branch_above_32A"]] + [(0.0, 0.0)]
    pts.sort(key=lambda x: x[1])
    for (r0, i0), (r1, i1) in zip(pts, pts[1:]):
        if i0 <= cur <= i1 and i1 > i0:
            return r0 + (cur - i0) * (r1 - r0) / (i1 - i0)
    raise ValueError(cur)


def fit_power(curve_json, imin=9.0):
    """Least-squares ln(rise) = ln c + n ln I over the trace points with I >= imin."""
    pts = [(105.0 - t, i) for t, i in curve_json["solid_falling_branch"] + curve_json["dashed_branch_above_32A"]
           if i >= imin and 105.0 - t > 0]
    xs = [math.log(i) for _, i in pts]
    ys = [math.log(r) for r, _ in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return math.exp(my - slope * mx), slope, n


def calibrate(target_k, i_a=32.0, t_air=20.0):
    """R_pole that makes the model's clamp rise equal target_k with 6 mm2 leads in a ~20 C room (the curve's test), over
    test-PCB pin+board conductances 0.01-0.06 W/K and lead h 12-17 W/m2/K."""
    rows = []
    for g_pb, h in itertools.product((0.01, 0.03, 0.06), (12.0, 17.0)):
        c = cord("6 mm2", i_a, t_air, h)
        # rise = (P + g_cord theta_inf) / (g_pb + g_cord)  (board side at the room temperature: unknown test PCB)
        p_need = target_k * (g_pb + c["g_cord"]) - c["g_cord"] * c["theta_inf_k"]
        rows.append({"g_pb_w_k": g_pb, "h": h, "lead_theta_inf_k": round(c["theta_inf_k"], 2),
                     "r_pole_mohm": round(max(p_need, 0.0) / i_a ** 2 * 1e3, 3)})
    return rows


def md_bounds(b):
    return (f"{b['low']['t_c']:.1f} / {b['central']['t_c']:.1f} / **{b['high']['t_c']:.1f}** C "
            f"(margin {LIMIT_C - b['high']['t_c']:+.1f} K at high, {LIMIT_C - b['central']['t_c']:+.1f} K central)")


def main():
    bu = json.loads((RES / "j1_buildup.json").read_text())
    cj = json.loads((RES / "phoenix_1714971_p6.json").read_text())
    rel = bu["cases"]["c17.5_h10"]
    t_p0 = rel["pad_est_c"]                                  # 99.03 C, the hot pole (J1.2, neutral; README 3.2)
    hot_cool = rel["hot_minus_cool_pad_k"]                   # 26.9 K: hot pad over the line pad
    pad_rise = rel["pad_rise_over_model_ambient_k"] + rel["mesh_allowance_k"]
    out = {"inputs": {"t_p0_release_c": t_p0, "bay_c": BAY_REL, "hot_minus_cool_pad_k": hot_cool,
                      "pad_rise_k": round(pad_rise, 2), "grid": GRID, "central": CENTRAL}}

    # 1. the p.6 curve itself
    c, n, npts = fit_power(cj)
    out["curve"] = {
        "rise_32A_knee_k": round(curve_rise(32.0, cj), 2),
        "rise_13p5A_read_k": round(curve_rise(I_REL, cj), 2),
        "rise_15A_read_k": round(curve_rise(I_TRIP, cj), 2),
        "rise_13p5A_s21_scaled_k": round(bu["own_rise_k_s21"], 2),
        "power_fit": {"c": round(c, 4), "n": round(n, 3), "points": npts,
                      "rise_13p5A_k": round(c * I_REL ** n, 2), "rise_15A_k": round(c * I_TRIP ** n, 2)},
        "if_reduction_factor_0p8": {"rise_32A_k": round(curve_rise(0.8 * 32.0, cj), 2),
                                    "rise_13p5A_k": round(curve_rise(0.8 * I_REL, cj), 2)},
    }
    out["calibration"] = {"rise_23K_at_32A": calibrate(out["curve"]["rise_32A_knee_k"]),
                          "rise_if_0p8_at_32A": calibrate(out["curve"]["if_reduction_factor_0p8"]["rise_32A_k"])}

    # 2. the release case with the real lead (14 AWG)
    rel14 = bounds(t_p0, BAY_REL, I_REL, "14 AWG")
    out["release_14awg_13p5A"] = rel14
    c28 = bu["cases"]["c28_h10"]
    out["c28_14awg_13p5A"] = bounds(c28["pad_est_c"], c28["bay_c"], I_REL, "14 AWG")
    out["sensitivity_14awg_13p5A"] = sensitivity(t_p0, BAY_REL, I_REL, "14 AWG")
    out["lead_alone_14awg"] = {f"h{h:g}_air+{ar:g}": round(cord("14 AWG", I_REL, BAY_REL + ar, h)["t_inf_c"], 2)
                               for h in GRID["cord_h"] for ar in GRID["lead_air_rise_k"]}
    # 15 A: the pad's line-driven share scales with I^2: between the hot-minus-cool excess and the whole pad rise
    f = (I_TRIP / I_REL) ** 2 - 1.0
    tp15 = (t_p0 + f * hot_cool, t_p0 + f * pad_rise)
    out["trip_14awg_15A"] = bounds(tp15[0], BAY_REL, I_TRIP, "14 AWG", t_p0_hi=tp15[1])
    out["trip_14awg_15A"]["t_p0_range_c"] = [round(x, 2) for x in tp15]

    # 3. fixes
    fixes = {}
    fixes["a_limit"] = {"what": "105 C is Phoenix's upper limiting temperature for 1714971 (p.5); the PA housing's ball-"
                                "pressure temperature is 125 C (p.3), which is a material test, not a use limit; no "
                                "higher-limit MKDS 5 variant in this footprint was found and the UL RTI of the housing "
                                "is unpublished (Product iQ needs a login). The lead's 105 C insulation co-binds at "
                                "the clamp.", "credit_k": 0.0}
    # (b) neutral copper: the hot pole's excess over the line pole is the ac_n_in feed's own heat (5.88 mm B.Cu edge
    # strip, 2.54 mohm vs 0.29 mohm for ac_l_in, plus the J1.2 barrel hop); a mirrored F.Cu strip landed on J1.2's
    # F.Cu pad halves the feed's resistance and bypasses the barrel: the self-heated excess falls by 1/2 if all of it
    # is self-heat, by 1/3 if a third of it is the board-edge geometry
    red = (hot_cool / 3.0, hot_cool / 2.0)
    tpb = (t_p0 - red[1], t_p0 - red[0])
    fixes["b_neutral_copper"] = {"what": "ac_n_in F.Cu strip mirroring the B.Cu strip x 283.6-289.4, y 3.5-26.5 into "
                                         "J1.2's F.Cu pad, stitched to B.Cu (layout change; B3 re-solve to confirm)",
                                 "pad_reduction_k": [round(r, 2) for r in red],
                                 "t_p0_range_c": [round(x, 2) for x in tpb],
                                 "release_13p5A": bounds(tpb[0], BAY_REL, I_REL, "14 AWG", t_p0_hi=tpb[1])}
    fixes["c_other_terminal"] = {"what": "a terminal with a higher limit gains nothing while the 105 C lead sits in its "
                                         "clamp; with a 125 C lead as well, the margin becomes 125 - T_C(high)",
                                 "credit_k": 0.0,
                                 "with_125C_terminal_and_lead_margin_k": round(125.0 - rel14["high"]["t_c"], 2)}
    fixes["d_12awg"] = {"what": "12 AWG cord and inlet leads (product spec)",
                        "release_13p5A": bounds(t_p0, BAY_REL, I_REL, "12 AWG"),
                        "lead_alone": {f"h{h:g}_air+{ar:g}": round(cord("12 AWG", I_REL, BAY_REL + ar, h)["t_inf_c"], 2)
                                       for h in GRID["cord_h"] for ar in GRID["lead_air_rise_k"]}}
    fixes["d_12awg"]["trip_15A"] = bounds(tp15[0], BAY_REL, I_TRIP, "12 AWG", t_p0_hi=tp15[1])
    fixes["b_plus_d"] = {"release_13p5A": bounds(tpb[0], BAY_REL, I_REL, "12 AWG", t_p0_hi=tpb[1])}
    # (b) at the 15 A trip
    tpb15 = (tpb[0] + f * (hot_cool - red[1]), tpb[1] + f * (pad_rise - red[0]))
    fixes["b_neutral_copper"]["trip_15A"] = bounds(tpb15[0], BAY_REL, I_TRIP, "14 AWG", t_p0_hi=tpb15[1])
    out["fixes"] = fixes

    # gate constants: the high corner of the grid, for the proposed B3 row (patches/)
    hi = rel14["high"]["inputs"]
    out["gate_row_constants_high_corner"] = hi
    (RES / "j1_thermal.json").write_text(json.dumps(out, indent=1) + "\n")

    L = ["# J1 thermal model results (generated by scripts/j1_thermal.py; do not edit)", ""]
    L.append(f"Release case c17.5_h10 at bay {BAY_REL:g} C, hot pole pad (B3, nothing attached) T_P0 = {t_p0} C. "
             "Bounds are low / central / high clamp temperature over the input grid.")
    L += ["", "## Phoenix p.6 curve (6 mm2)", ""]
    cu = out["curve"]
    L.append(f"- knee: {cu['rise_32A_knee_k']} K at 32 A; read at 13.5 A: {cu['rise_13p5A_read_k']} K, at 15 A: "
             f"{cu['rise_15A_read_k']} K (S21 scaled I^2 from the knee: {cu['rise_13p5A_s21_scaled_k']} K)")
    pf = cu["power_fit"]
    L.append(f"- power fit over {pf['points']} points (I >= 9 A): rise = {pf['c']} I^{pf['n']}: "
             f"{pf['rise_13p5A_k']} K at 13.5 A, {pf['rise_15A_k']} K at 15 A")
    L.append(f"- if the drawn curve is 0.8 x the base curve (IEC 60512-5-2): true rise {cu['if_reduction_factor_0p8']['rise_32A_k']} K "
             f"at 32 A, {cu['if_reduction_factor_0p8']['rise_13p5A_k']} K at 13.5 A")
    L += ["", "Calibration (R_pole that reproduces the curve with 6 mm2 leads in a 20 C room):", "",
          "| test pin+board G (W/K) | lead h | lead theta_inf (K) | R_pole for 23 K (mohm) | R_pole if 0.8 (mohm) |",
          "|---|---|---|---|---|"]
    for a, b in zip(out["calibration"]["rise_23K_at_32A"], out["calibration"]["rise_if_0p8_at_32A"]):
        L.append(f"| {a['g_pb_w_k']} | {a['h']:g} | {a['lead_theta_inf_k']} | {a['r_pole_mohm']} | {b['r_pole_mohm']} |")
    L += ["", "## J1 with the 14 AWG lead", ""]
    L.append(f"- 13.5 A (release): {md_bounds(rel14)}")
    L.append(f"- c28_h10 at bay 55 C (ratchet; pad {bu['cases']['c28_h10']['pad_est_c']} C): {md_bounds(out['c28_14awg_13p5A'])}")
    L.append(f"- 15 A (trip; pad {out['trip_14awg_15A']['t_p0_range_c']} C): {md_bounds(out['trip_14awg_15A'])}")
    L.append(f"- the lead alone (far field) at 13.5 A: {out['lead_alone_14awg']} C (limit 105)")
    for k in ("low", "high"):
        b = rel14[k]
        L.append(f"- {k} corner: P_pole {b['p_pole_w']} W, to board {b['q_to_board_w']:+.4f} W, to lead "
                 f"{b['q_to_lead_w']:+.4f} W, pad {b['t_pad_c']} C; inputs {b['inputs']}")
    L += ["", "Sensitivity about the central point (K at the input's low / high):", ""]
    for k, v in out["sensitivity_14awg_13p5A"].items():
        L.append(f"- {k}: {v['at_low']:+.2f} / {v['at_high']:+.2f}")
    L += ["", "## Fixes (13.5 A release case)", ""]
    L.append(f"- (a) limit: credit 0 K. {fixes['a_limit']['what']}")
    fb = fixes["b_neutral_copper"]
    L.append(f"- (b) neutral F.Cu mirror: pad -{fb['pad_reduction_k'][0]} ... -{fb['pad_reduction_k'][1]} K "
             f"(T_P0 {fb['t_p0_range_c']} C): {md_bounds(fb['release_13p5A'])}; at 15 A {md_bounds(fb['trip_15A'])}")
    L.append(f"- (c) other terminal: credit 0 K with the 105 C lead; with a 125 C terminal and lead the margin is "
             f"{fixes['c_other_terminal']['with_125C_terminal_and_lead_margin_k']:+.1f} K")
    L.append(f"- (d) 12 AWG: {md_bounds(fixes['d_12awg']['release_13p5A'])}; at 15 A {md_bounds(fixes['d_12awg']['trip_15A'])}; lead alone {fixes['d_12awg']['lead_alone']} C")
    L.append(f"- (b)+(d): {md_bounds(fixes['b_plus_d']['release_13p5A'])}")
    (RES / "j1_thermal.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
