#!/usr/bin/env python3
"""C34: resonant-bank margin at the 28 A tank ceiling, 35-50 kHz, 85 C, worst-case current sharing.

    python3 -I scripts/bank_margin.py      -> results/bank_margin.json, results/bank_table.csv  (exit 1 on a failed control)

Figure of merit (fixed before the candidates were scored):
  ratio(f) = max over parts i of  I_tank * s_i / I_allow,i(f, 85 C)
  s_i = C_i (1 + t_i) / (C_i (1 + t_i) + sum_j!=i C_j (1 - t_j))     (part i at its + tolerance, every other part at -)
  I_tank = 28 A line-cycle RMS (DECISIONS 10 hardware ceiling); f over the firmware window 35-50 kHz
  (round 6: f >= max(35 kHz, 1.05 f_res)); the governing value is the worst f in the window.
  Go if ratio <= 0.85 at every f in 35-50 kHz. Vendor curves are taken at their own basis (TDK: T_A <= 85 C,
  self-heating dT <= 20 K, p.57; F_T = 1.0 below 85 C, p.64, so no current is credited for a cooler location).
Voltage checks (line-cycle RMS, carrier sinusoidal):
  V_rms bound at 28 A = 28 / (2 pi 35 kHz C_min)  (I <= ceiling, f >= floor, C >= C_nom (1 - t): a bound)
  V_pk = V_rms * 2.113 (round 6 board-side-protection.csv pk/rms at 28 A, ngspice fit; an estimate)
  no-pan fault 409 V rms / 818 V pk at bank 0.45 uF (DECISIONS 2026-10-08 28 A update), scaled by 0.45 / C_min
  triple fault 1683 V pk (DECISIONS 23, F3) against V_dc: below 1600 V DC reopens F3 (flag, not a reject).
Fit: the slot scan (results/slot_geometry.json, run slot_geometry.py first): pin rows y 53.2-111.5 on the stage-32
copper without moving anything (53.2 = today's row 1, RES_A >= 5 mm below the sw_b band); R22-R25 courtyards above (y 42.17), J6 below (y 131.66); a pitch other than 27.5 mm
needs the RES_A / SW_B strips moved (pins may go to x >= 155.5 and <= 199.0 at every row); height <= 52.5 mm (R43).
Yield for C != 0.50 uF: round 6 fstrat-b-bank-sweep.csv (70 uH, 220 mm pans, 28 A), linear in C.
Controls (exit 1 if any fails):
  C1  5 x 100 nF K reproduces round 6 board-side-bank.csv 24.8 / 25.3 / 26.1 / 27.3 A (35/40/45/50 kHz)
  C2  5 x 100 nF K and J reproduce bank_options.json ratio_to_curve_28A_40k 1.105 / 1.022 (the scorecard metric)
  C3  round 6's "1.12x at 28 A" = board-side-protection.csv cap_part_over_TDK85C_max 1.117, recomputed from the
      28 A, 0.50 uF grid cases (gap84, L 70/80/90, all pans) at each case's own frequency with the K share
  C4  the TDK 100 nF curve at 99 kHz is within 2 % of the p.23 table (7.3 A)
"""
import csv
import glob
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
C34 = HERE.parent
VR = HERE.parents[2]                                         # validation-results
R6 = VR / "05-resonant-tank-envelope/round6-full-power/outputs"
I_TANK = 28.0
FREQS = (35e3, 40e3, 45e3, 50e3)
GO = 0.85
PK_RMS_28A = None                                            # read below
fails = []


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---- curves -------------------------------------------------------------------------------------------
rows = list(csv.DictReader(open(R6 / "tdk-p57-1600v.csv")))
TDK = {int(k[2:-2]): [(float(r["f_hz"]), float(r[k])) for r in rows] for k in rows[0] if k.startswith("I_")}


def loglog(pts, f):
    for (f0, i0), (f1, i1) in zip(pts, pts[1:]):
        if f0 <= f <= f1:
            t = (math.log(f) - math.log(f0)) / (math.log(f1) - math.log(f0))
            return math.exp(math.log(i0) + t * (math.log(i1) - math.log(i0)))
    raise ValueError(f)


def tdk_interp(c_nf, i100k, f):
    """ESTIMATE for a 1600 V B32654 value that p.57 does not plot: shape I(f)/I(99k) interpolated in log C between the
    neighbouring plotted curves, scaled to the p.23 100 kHz table value."""
    lo = max(c for c in TDK if c <= c_nf)
    hi = min(c for c in TDK if c >= c_nf)
    sl = loglog(TDK[lo], f) / TDK[lo][-1][1]
    sh = loglog(TDK[hi], f) / TDK[hi][-1][1]
    t = 0 if hi == lo else (math.log(c_nf) - math.log(lo)) / (math.log(hi) - math.log(lo))
    return i100k * math.exp(math.log(sl) + t * (math.log(sh) - math.log(sl)))


parts = {}
srcs = {}
for f in sorted((C34 / "raw").glob("parts_*.json")):
    d = json.loads(f.read_text())
    srcs[f.name] = sha(f)
    for p in d["parts"]:
        parts[p["id"]] = p


C34C = json.loads((C34 / "results/tdk_curves_c34.json").read_text())["charts"]   # digitize_tdk.py (run first)
B43 = json.loads((C34 / "results/b32643b_curves.json").read_text())["rows"]        # digitize_b32643b.py
KEM = json.loads((C34 / "results/kemet_r76_curves.json").read_text())["charts"]    # digitize_kemet_r76.py


def kem_curve(pn):
    for ch in KEM.values():
        if pn in ch["curves"]:
            return [(float(f), v) for f, v in ch["curves"][pn]["I_A"].items()]
    raise KeyError(pn)


def kem_D(pn, c_nf, esr100):
    """dielectric term D of ESR(f) = ESR_100k + D (1/(w C) - 1/(w_100k C)), fitted at 35 kHz to a plotted R76 curve
    (I proportional to 1/sqrt(ESR) at fixed Rth and dT_lim)"""
    pts = kem_curve(pn)
    r = loglog(pts, 35e3) / loglog(pts, 100e3)
    w35, w100 = 2 * math.pi * 35e3 * c_nf * 1e-9, 2 * math.pi * 100e3 * c_nf * 1e-9
    return esr100 * 1e-3 * (1 / r ** 2 - 1) / (1 / w35 - 1 / w100)


KEM_D = {"kemet_esr_1600": kem_D("R76TR3220", 220, 11), "kemet_esr_2000": kem_D("R76UR3100", 100, 11)}


def allow(p, f):
    c = p.get("I_curve")
    if c and c.startswith("b32643b_"):
        lab = c.split("_")[1]
        return loglog([(r["f_hz"], r[f"I_{lab}"]) for r in B43], f)
    if c and c.startswith("kemet_esr_"):
        esr = p["ESR_max_100k_mOhm"] * 1e-3
        cf = p["C_nF"] * 1e-9
        e = esr + KEM_D[c] * (1 / (2 * math.pi * f * cf) - 1 / (2 * math.pi * 100e3 * cf))
        return p["I100k_table_A"] * math.sqrt(esr / e)
    if c and c.startswith("kemet_"):
        return loglog(kem_curve(c.split("_", 1)[1]), f)
    if c and c.startswith("c34_"):                                        # c34_<chart>_<label>
        _, ch, lab = c.split("_")
        return loglog([(r["f_hz"], r[f"I_{lab}"]) for r in C34C[ch]["rows"]], f)
    if c and c.startswith("tdk_p57_interp_"):
        return tdk_interp(p["C_nF"], p["I100k_table_A"], f)
    if c and c.startswith("tdk_p57_"):
        return loglog(TDK[int(c.split("_")[-1])], f)
    pts = sorted((float(k), v) for k, v in p["I85_A"].items())          # {"35000": A, ...} cited points
    if f <= pts[0][0]:
        return pts[0][1] if f == pts[0][0] else None
    return loglog(pts, f) if f <= pts[-1][0] else None


def shares(cs, ts):
    out = []
    for i, (c, t) in enumerate(zip(cs, ts)):
        oth = sum(cj * (1 - tj) for j, (cj, tj) in enumerate(zip(cs, ts)) if j != i)
        out.append(c * (1 + t) / (c * (1 + t) + oth))
    return out


# ---- inputs from round 6 ------------------------------------------------------------------------------
prot = {float(r["I_max_A"]): r for r in csv.DictReader(open(R6 / "board-side-protection.csv"))}
PK_RMS_28A = float(prot[28.0]["pk_over_rms"])
sweep = [r for r in csv.DictReader(open(R6 / "fstrat-b-bank-sweep.csv")) if r["L_free_uH"] == "70"]
sweep = sorted(((float(r["C_bank_uF"]), float(r["yield_28A"]), float(r["f_op_med_kHz"])) for r in sweep))


def yield_at(c_uf):
    for (c0, y0, f0), (c1, y1, f1) in zip(sweep, sweep[1:]):
        if c0 <= c_uf <= c1:
            t = (c_uf - c0) / (c1 - c0)
            return round(y0 + t * (y1 - y0), 3), round(f0 + t * (f1 - f0), 1)
    return None, None


slot = json.loads((C34 / "results/slot_geometry.json").read_text())
PIN_Y = (53.2, 111.5)   # top: RES_A pin 1 >= 5 mm below the sw_b band (place.py; row 1 today), the pin scan's 48.0
                        # needs that band re-laid; bottom: SW_B pin vs the B.Cu SELV lane (slot_geometry)
ABOVE_Y, BELOW_Y = 42.17, 131.66            # R22-R25 courtyard bottom, J6 courtyard top (neighbours)
X_LEFT_MAX = 155.5                          # RES_A pin may move left to here at every row (pitch_scan)
X_RIGHT_MAX = 199.0                         # SW_B pin may move right to here at every row
HEADROOM = slot["height"]["headroom_with_1mm_gap_mm"]
ss = slot["column_scan_summary"]
assert ss["sw_b_x190.5"]["last_clear_pin_y_below"] == PIN_Y[1] and ss["res_a_x163.0"]["last_clear_pin_y_above"] <= PIN_Y[0]
ps = slot["pitch_scan"]
assert max(v["last_clear_x"] for k, v in ps.items() if k.startswith("res_a")) == X_LEFT_MAX
assert min(v["last_clear_x"] for k, v in ps.items() if k.startswith("sw_b")) == X_RIGHT_MAX


def fit(items):
    """column of radial parts, one per row, pins on two strips. Returns a dict with the verdict and what must move."""
    ws = [parts[i]["w"] for i in items]
    pitch = {parts[i]["pitch"] for i in items}
    h = max(parts[i]["h"] for i in items)
    span = sum(w + 0.5 for w in ws) - 0.5                          # body row, 0.5 mm between bodies (today 0.4-0.8)
    pin_span = span - ws[0] / 2 - ws[-1] / 2
    lo = max(PIN_Y[0], ABOVE_Y + 0.2 + ws[0] / 2)
    hi = min(PIN_Y[1], BELOW_Y - 0.2 - ws[-1] / 2)
    need_move = []
    if pin_span > hi - lo:
        short = pin_span - (hi - lo)
        need_move.append(f"pin rows need {pin_span:.1f} mm, {hi - lo:.1f} mm free (y {lo:.1f}-{hi:.1f}): "
                         f"{short:.1f} mm more: re-lay the sw_b band edge (y 46.8) and R22-R25 above, or the B.Cu SELV lane "
                         f"(line_zc_raw, v15_selv, y 127.5-128.6) and J6 below")
    pmax = max(pitch)
    if len(pitch) > 1:
        need_move.append(f"mixed pitches {sorted(pitch)}: a third strip")
    if pmax > 27.5:
        grow = pmax - 27.5
        room = (163.0 - X_LEFT_MAX) + (X_RIGHT_MAX - 190.5)
        need_move.append(f"pitch {pmax} mm: RES_A / SW_B strips move apart by {grow:.1f} mm "
                         f"({'inside' if grow <= room else 'beyond'} the {room:.1f} mm the pin scan allows)")
    elif pmax < 27.5:
        need_move.append(f"pitch {pmax} mm: new footprint; RES_A strip to x {163.0 + 27.5 - pmax:.1f} or SW_B strip to "
                         f"x {190.5 - 27.5 + pmax:.1f} (both columns scanned in slot_geometry.json: same y limits)")
    if h > HEADROOM:
        need_move.append(f"height {h} mm > {HEADROOM} mm headroom")
    return {"body_row_mm": round(span, 1), "pin_span_mm": round(pin_span, 1), "free_pin_span_mm": round(hi - lo, 1),
            "height_mm": h, "fits_today_copper": not need_move, "changes": need_move}


def evaluate(label, spec, note=""):
    items = [pid for pid, n in spec for _ in range(n)]
    cs = [parts[i]["C_nF"] for i in items]
    ts = [parts[i]["tol"] for i in items]
    sh = shares(cs, ts)
    cnom = sum(cs) / 1000
    cmin = sum(c * (1 - t) for c, t in zip(cs, ts)) / 1000
    r = {"bank": label, "parts": [f"{n} x {parts[p]['mpn']}" for p, n in spec], "n": len(items), "C_nom_uF": round(cnom, 4),
         "C_min_uF": round(cmin, 4), "worst_share": round(max(sh), 4), "note": note}
    worst = 0.0
    for f in FREQS:
        al = [allow(parts[i], f) for i in items]
        if any(a is None for a in al):
            r[f"ratio_{int(f / 1e3)}k"] = None
            r[f"tank_A_at_curve_{int(f / 1e3)}k"] = None
            worst = None if worst is not None else None
            continue
        rat = max(I_TANK * s / a for s, a in zip(sh, al))
        r[f"ratio_{int(f / 1e3)}k"] = round(rat, 3)
        r[f"tank_A_at_curve_{int(f / 1e3)}k"] = round(min(a / s for s, a in zip(sh, al)), 1)
        r[f"tank_A_at_0.85_{int(f / 1e3)}k"] = round(GO * min(a / s for s, a in zip(sh, al)), 1)
        if worst is not None:
            worst = max(worst, rat)
    r["ratio_worst_35_50k"] = round(worst, 3) if worst is not None else None
    # the vendor's own self-heating criterion, scaled: dT = ratio^2 x dT_basis (TDK B3265x and KEMET R76: 20 K;
    # TDK B3264*B: 15 K). Same physics as the ratio, on a common scale across families.
    if worst is not None:
        dtb = max(15.0 if parts[i]["family"].startswith("B32643B") else 20.0 for i in items)
        r["vendor_dT_basis_K"] = dtb
        r["self_heating_at_28A_35k_K"] = round(r["ratio_35k"] ** 2 * dtb, 1)
    # SENSITIVITY (estimate, not a bound): the vendor curve is one part in free air. In the column the 0.5 mm gaps
    # shadow the large h x l faces; if those faces shed nothing, dT per W of a part with two neighbours scales by
    # A / (A - 2 h l), so its allowed current by sqrt((A - 2 h l) / A). Gap convection and radiation are ignored.
    if worst is not None and len(items) >= 2:
        fr = []
        for k_, i in enumerate(items):
            p = parts[i]
            a = 2 * (p["w"] * p["h"] + p["w"] * p["l"] + p["h"] * p["l"])
            nshade = (k_ > 0) + (k_ < len(items) - 1)
            fr.append(math.sqrt((a - nshade * p["h"] * p["l"]) / a))
        r["ratio_35k_faces_shadowed_est"] = round(max(I_TANK * s / (allow(parts[i], 35e3) * q)
                                                      for s, i, q in zip(sh, items, fr)), 3)
    # KEMET R76 only (p.6): the permissible rise is dT_lim(Th) = min(40, 0.8 (110 - Th)) K against 20 K at 85 C, with
    # Th = the hotter of the air round the part and its hottest contact point (tracks). B3 (04-.../b3-convergence,
    # 28 A, h25, 50 C air) puts the bank pads at 77 / 78 C (mean / max): Th = 78 C. Model temperature, not a bound.
    if worst is not None and all(parts[i].get("kemet_th_rule") for i in items):
        th = 78.0
        fac = math.sqrt(min(40.0, 0.8 * (110.0 - th)) / 20.0)
        r["kemet_Th78_factor"] = round(fac, 3)
        r["ratio_worst_35_50k_at_Th78_kemet_rule"] = round(worst / fac, 3)
        r["Th_max_for_0.85_C"] = round(110 - 20 * (worst / GO) ** 2 / 0.8, 1) if worst > GO else None
    vr = I_TANK / (2 * math.pi * 35e3 * cmin * 1e-6)
    r["V_rms_bound_28A_35k"] = round(vr, 1)
    r["V_pk_est_28A_35k"] = round(vr * PK_RMS_28A, 1)
    r["V_nopan_fault_rms_pk"] = [round(409 * 0.45 / cmin, 1), round(818 * 0.45 / cmin, 1)]
    vdc = min(parts[i]["Vdc"] for i in items)
    vac = min(parts[i].get("Vac_1k") or 0 for i in items)
    r["Vdc_min"] = vdc
    r["Vac_1k_min"] = vac
    r["V_checks"] = {"normal_pk_over_Vdc": round(vr * PK_RMS_28A / vdc, 3),
                     "nopan_pk_over_Vdc": round(818 * 0.45 / cmin / vdc, 3),
                     "triple_fault_1683_over_Vdc": round(1683 / vdc, 3),
                     "F3_reopens": vdc < 1600}
    dv = [parts[i].get("dvdt_V_us") for i in items]
    if all(dv):
        vpk = vr * PK_RMS_28A
        r["dvdt_used_over_rated"] = round(2 * math.pi * 50e3 * vpk * 1e-6 / min(dv), 5)
    r["fit"] = fit(items)
    r["f_res_scale"] = round(math.sqrt(0.5 / cnom), 3)
    y, fmed = yield_at(cnom)
    r["yield_28A_70uH_220mm"] = y
    r["f_op_median_kHz"] = fmed
    pr = [parts[i].get("price_500_usd") for i in items]
    r["parts_cost_500_usd"] = round(sum(pr), 2) if all(p is not None for p in pr) else None
    r["go"] = bool(r["ratio_worst_35_50k"] is not None and r["ratio_worst_35_50k"] <= GO)
    return r


out = {"inputs": {"tdk-p57-1600v.csv": sha(R6 / "tdk-p57-1600v.csv"), "board-side-protection.csv": sha(R6 / "board-side-protection.csv"),
                  "fstrat-b-bank-sweep.csv": sha(R6 / "fstrat-b-bank-sweep.csv"), "board-side-bank.csv": sha(R6 / "board-side-bank.csv"),
                  "bank_options.json": sha(VR / "11-candidates/g04-g09-tank-detect/results/bank_options.json"),
                  "slot_geometry.json": sha(C34 / "results/slot_geometry.json"),
                  "tdk_curves_c34.json": sha(C34 / "results/tdk_curves_c34.json"),
                  "b32643b_curves.json": sha(C34 / "results/b32643b_curves.json"),
                  "kemet_r76_curves.json": sha(C34 / "results/kemet_r76_curves.json"), **srcs},
       "kemet_esr_D": {k: round(v, 7) for k, v in KEM_D.items()},
       "basis": {"I_tank_A": I_TANK, "freqs_Hz": FREQS, "go_ratio": GO, "pk_over_rms_28A": PK_RMS_28A}}

# ---- controls -----------------------------------------------------------------------------------------
k = evaluate("5 x B32654A1104K000 (K, control)", [("tdk_a1104k", 5)])
j = evaluate("5 x B32654A1104J000 (J, fitted today)", [("tdk_a1104j", 5)])
r6 = {r["bank"]: r for r in csv.DictReader(open(R6 / "board-side-bank.csv"))}["5 x B32654A1104 (0.50 uF, today)"]
c1 = {f"{int(f / 1e3)}k": (k[f"tank_A_at_curve_{int(f / 1e3)}k"], float(r6[f"tank_A_85C_{int(f / 1e3)}k"])) for f in FREQS}
if any(abs(a - b) > 0.05 for a, b in c1.values()):
    fails.append(f"C1 round-6 bank table not reproduced {c1}")
bo = json.loads((VR / "11-candidates/g04-g09-tank-detect/results/bank_options.json").read_text())["baseline"]
c2 = {"K": (k["ratio_40k"], bo["5x100nF_K(+-10%)"]["ratio_to_curve_28A_40k"]),
      "J": (j["ratio_40k"], bo["5x100nF_J(+-5%)"]["ratio_to_curve_28A_40k"])}
if any(abs(a - b) > 0.0015 for a, b in c2.values()):
    fails.append(f"C2 bank_options ratios not reproduced {c2}")
grid = []
for fn in sorted(glob.glob(str(R6 / "grid6-d228_gap84-L*-C050-I28-pan*-cases.csv"))):
    for row in csv.DictReader(open(fn)):
        grid.append((float(row["i_tank_rms_a"]), float(row["freq_hz"]), row["config"]))
sk = shares([100] * 5, [0.10] * 5)[0]
sj = shares([100] * 5, [0.05] * 5)[0]
gk = max(i * sk / loglog(TDK[100], f) for i, f, _ in grid)
gj = max(i * sj / loglog(TDK[100], f) for i, f, _ in grid)
g70k = max(i * sk / loglog(TDK[100], f) for i, f, c in grid if "-L70-" in c)
g70j = max(i * sj / loglog(TDK[100], f) for i, f, c in grid if "-L70-" in c)
c3 = (round(gk, 3), float(prot[28.0]["cap_part_over_TDK85C_max"]))
if abs(c3[0] - c3[1]) > 0.0015:
    fails.append(f"C3 round-6 1.117 not reproduced {c3}")
c4 = TDK[100][-1][1] / 7.3
if abs(c4 - 1) > 0.02:
    fails.append(f"C4 curve end {c4}")
out["controls"] = {
    "C1_round6_bank_table_K": c1, "C2_bank_options_40k": c2,
    "C3_round6_grid_max_28A": {"recomputed_K": c3[0], "round6": c3[1], "cases": len(grid),
                               "f_min_kHz": round(min(f for _, f, _ in grid) / 1e3, 2),
                               "same_cases_J": round(gj, 3), "L70_only_K": round(g70k, 3), "L70_only_J": round(g70j, 3)},
    "C4_curve_99k_over_table": round(c4, 3), "failed": fails, "passed": not fails}
out["basis_comparison"] = {
    "round6_1.12x": "K (+-10 %) share 0.234, each grid case at its own operating frequency, max over the 28 A / 0.50 uF "
                    "configs on L 70/80/90 uH (80/90 uH sit on the 35 kHz floor); 70 uH alone gives the L70 value",
    "scorecard_1.022": "J (+-5 %) share 0.2165 at a fixed 40 kHz (bank_options.py baseline J)",
    "this_study": "J share, worst f over the whole 35-50 kHz window = the 35 kHz floor for every TDK 1600 V curve",
    "J_at_35k": j["ratio_35k"], "J_at_40k": j["ratio_40k"], "K_at_35k": k["ratio_35k"]}

# ---- per-part view: permissible voltage at 35 kHz and capacitance per mm of column -------------------------
# Parallel parts share one voltage, so ratio_i = V (1 + t_i) / V_allow,i with V_allow = I_allow / (2 pi f C_nom).
# A 0.50 uF J bank at 28 A / 35 kHz sits at 268 V rms (C_min), so a part needs V_allow(35 kHz) >= 268 x 1.05 / 0.85
# = 331 V; and the slot's ~72 mm body row then caps the bank at (nF per mm of row) x 72 mm.
dens = []
for pid, p in sorted(parts.items()):
    a = allow(p, 35e3)
    if a is None:
        continue
    dens.append({"id": pid, "mpn": p["mpn"], "C_nF": p["C_nF"], "w_mm": p["w"], "pitch": p["pitch"],
                 "I_allow_35k_A": round(a, 2), "V_allow_35k_Vrms": round(a / (2 * math.pi * 35e3 * p["C_nF"] * 1e-9), 1),
                 "nF_per_mm_of_column": round(p["C_nF"] / (p["w"] + 0.5), 2),
                 "uF_in_72mm_row": round(p["C_nF"] * int((72.0 + 0.5) // (p["w"] + 0.5)) / 1000, 3)})
out["per_part_35k"] = sorted(dens, key=lambda d: -d["V_allow_35k_Vrms"])
out["per_part_rule"] = "pass needs V_allow(35 kHz) >= V_bank(C_min) (1 + t) / 0.85; 0.50 uF J: 268.1 x 1.05 / 0.85 = 331 V"

# ---- candidate banks ----------------------------------------------------------------------------------
BANKS = json.loads((C34 / "raw/banks.json").read_text())["banks"]
res = [j, k]
for b in BANKS:
    if all(pid in parts for pid, _ in b["spec"]):
        res.append(evaluate(b["label"], [tuple(s) for s in b["spec"]], b.get("note", "")))
    else:
        res.append({"bank": b["label"], "error": "part data missing", "missing": [p for p, _ in b["spec"] if p not in parts]})
out["banks"] = res
OUT = C34 / "results"
(OUT / "bank_margin.json").write_text(json.dumps(out, indent=1) + "\n")
cols = ["bank", "n", "C_nom_uF", "worst_share", "ratio_35k", "ratio_40k", "ratio_45k", "ratio_50k", "ratio_worst_35_50k",
        "tank_A_at_curve_35k", "tank_A_at_0.85_35k", "V_rms_bound_28A_35k", "V_pk_est_28A_35k", "Vdc_min", "go",
        "fits", "yield_28A_70uH_220mm", "parts_cost_500_usd"]
with open(OUT / "bank_table.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(cols)
    for r in res:
        if "error" in r:
            continue
        w.writerow([r.get(c) if c != "fits" else r["fit"]["fits_today_copper"] for c in cols])
print(json.dumps(out["controls"], indent=1))
print(json.dumps(out["basis_comparison"], indent=1))
for r in res:
    if "error" in r:
        print("!!", r)
        continue
    print(f"{r['bank'][:60]:60s} C {r['C_nom_uF']:.3f} r35 {r['ratio_35k']} r50 {r['ratio_50k']} worst {r['ratio_worst_35_50k']} "
          f"I@1.0 {r['tank_A_at_curve_35k']} go {r['go']} fit {r['fit']['fits_today_copper']} y {r['yield_28A_70uH_220mm']} $ {r['parts_cost_500_usd']}")
sys.exit(1 if fails else 0)
