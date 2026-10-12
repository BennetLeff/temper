#!/usr/bin/env python3
"""Re-run the M6 coil-terminal working-voltage bound at the 28 A tank ceiling.

usage: python3 coil_voltage_28a.py   (stdlib only, deterministic) -> results.json next to this file

ASSUMED / bounded calculation (fundamental-harmonic model, no bench data).

Controls (asserted):
  C1  the m6m10/coil_voltage.py envelope bound at 22 A -> 326 V rms / 653 V pk (132 V line), 333 V rms / 667 V pk (140 V).
  C2  the nine task-05 retained cases -> 304.7..320.5 V rms, 636.2 V pk max (m6m10/coil_voltage.py, same formula).
  C3  stage-15 bank peak: round6 board-side-protection.csv 483.72 V pk / 243.11 V rms at 28 A (470.7 / 235.54 at 22 A),
      recomputed here from the 28 A grid case rows as I_pk/(w C).
"""
import csv, glob, json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
UNIT = os.path.abspath(os.path.join(HERE, "../../../../../.."))
R6 = os.path.join(UNIT, "validation-results/05-resonant-tank-envelope/round6-full-power/outputs")
T5 = os.path.join(UNIT, "validation-results/05-resonant-tank-envelope/outputs/cases.csv")

# ---- Table 18, IEC 60335-1:2020, PD3, material group IIIa, rows as cited in the repo
# (m6m10/RECOMMENDATION.md, DECISIONS 2026-10-08; NOTE 3 permits linear interpolation).  The standard itself is not
# readable here (the sample PDF text under m6m10/src/ is not committed).  Rows above 500 V are NOT cited in the repo:
# beyond 500 V the function returns a labelled linear extrapolation of the 400-500 V slope (indicative, not the standard).
T18 = [(250.0, 3.2), (400.0, 5.0), (500.0, 6.3)]


def t18(v):
    if v <= 250.0:
        return 3.2          # repo: 3.2 mm is the HOT functional floor (<= 250 V)
    for (v0, d0), (v1, d1) in zip(T18, T18[1:]):
        if v0 <= v <= v1:
            return d0 + (v - v0) / (v1 - v0) * (d1 - d0)
    (v0, d0), (v1, d1) = T18[-2], T18[-1]
    return d1 + (v - v1) / (v1 - v0) * (d1 - d0)      # extrapolation, flagged by caller


def t18_extrapolated(v):
    return v > T18[-1][0]


CLEARANCE_MM = 0.8 + 0.5     # repo: Table 16 PD3 floor (0.8 mm, footnote c) + 0.5 mm assembled parts


def rnd(x, n=2):
    return round(x + 0.0, n)


# ------------------------------------------------------------------ analytic envelope bound (the repo's formula)
def bound(i_rms, xc, vl, rho=2.0):
    """|V_coil| <= |V_drive,1| + |V_C| ; time (line-cycle) RMS and carrier-crest peak.  rho = I_pk / I_rms(line)."""
    vrms = i_rms * xc + 0.9 * vl
    vpk = rho * i_rms * xc + 4 / math.pi * math.sqrt(2) * vl
    return vrms, vpk


def xc_of(f, c):
    return 1 / (2 * math.pi * f * c)


F_RES_ORIG = 1 / (2 * math.pi * math.sqrt(48e-6 * 0.54e-6))   # 31.3 kHz, ORACLE-ANSWER S4 (48 uH lowest loaded L)
XC_ORIG = xc_of(F_RES_ORIG, 0.54e-6)                           # = 9.43 ohm
res = {"controls": {}}

# ---- C1
c1 = {}
for vl in (132, 140):
    vr, vp = bound(22, XC_ORIG, vl)
    c1[str(vl)] = {"vrms": rnd(vr, 1), "vpk": rnd(vp, 1), "t18_mm": rnd(t18(vr))}
assert abs(c1["132"]["vrms"] - 326) < 0.5 and abs(c1["132"]["vpk"] - 653) < 0.6, c1
assert abs(c1["140"]["vrms"] - 333) < 0.5 and abs(c1["140"]["vpk"] - 667) < 0.6, c1
assert abs(c1["140"]["t18_mm"] - 4.20) < 0.005, c1
res["controls"]["C1_original_bound_22A"] = {"f_res_kHz": rnd(F_RES_ORIG / 1e3, 2), "Xc_ohm": rnd(XC_ORIG, 3), **c1, "PASS": True}

# ---- C2 (task-05 retained cases, same formula as m6m10/coil_voltage.py)
rows = list(csv.DictReader(open(T5)))
vr_l, vp_l = [], []
for r in rows:
    f = float(r["frequency_hz"]); L = float(r["l_load_h"])
    z = math.hypot(float(r["r_pan_40_ohm"]) * math.sqrt(f / 40e3) + float(r["r_coil_ohm"]), 2 * math.pi * f * L)
    vp_l.append(float(r["i_pk_a"]) * z)
    if r["run_id"].endswith("1710w"):
        vr_l.append(float(r["i_rms_a"]) * z)       # M6 quoted the 1710 W cases (305-321 V rms)
assert len(rows) == 9 and len(vr_l) == 3
assert abs(min(vr_l) - 304.7) < 0.06 and abs(max(vr_l) - 320.5) < 0.06 and abs(max(vp_l) - 636.2) < 0.06, (min(vr_l), max(vr_l), max(vp_l))
res["controls"]["C2_retained_cases"] = {"vrms_min": rnd(min(vr_l), 1), "vrms_max": rnd(max(vr_l), 1), "vpk_max": rnd(max(vp_l), 1),
                                        "crest_rms_of_vpk_max": rnd(max(vp_l) / math.sqrt(2), 1),
                                        "t18_crest_mm": rnd(t18(max(vp_l) / math.sqrt(2))), "PASS": True}
assert abs(t18(max(vp_l) / math.sqrt(2)) - 5.65) < 0.01

# ---- C3 stage-15 bank (cap) voltage from the round6 grid rows
def grid_rows(i):
    out = []
    for p in sorted(glob.glob(os.path.join(R6, f"grid6-*-I{i}-*cases.csv"))):
        for r in csv.DictReader(open(p)):
            r["_cfg"] = os.path.basename(p)[len("grid6-"):-len("-cases.csv")]
            out.append(r)
    return out


def case_calc(r):
    f = float(r["freq_hz"]); L = float(r["L_eq_uH"]) * 1e-6; R = float(r["R_eq_ohm"]); C = float(r["C_bank_uF"]) * 1e-6
    ir = float(r["i_tank_rms_a"]); ip = float(r["i_tank_pk_a"]); w = 2 * math.pi * f
    zc = math.hypot(R, w * L)
    return {"cfg": r["_cfg"], "case": r["case"], "status": r["status"], "pan": r["pan_class"], "line": float(r["line_vrms"]),
            "f": f, "L": L, "R": R, "C": C, "ir": ir, "ip": ip, "w": w, "zc": zc, "vcoil_rms": ir * zc, "vcoil_pk": ip * zc,
            "vc_rms": ir / (w * C), "vc_pk": ip / (w * C), "vc_pk_csv": float(r["vc_pk_v"]), "vc_rms_csv": float(r["vc_rms_v"]),
            "phi": math.atan2(w * L - 1 / (w * C), R)}


grids = {i: [case_calc(r) for r in grid_rows(i)] for i in (22, 28, 30)}
for i, g in grids.items():
    assert g, i
bsp = {float(r["I_max_A"]): r for r in csv.DictReader(open(os.path.join(R6, "board-side-protection.csv")))}
c3 = {}
for i in (22, 28):
    vcpk_csv = max(c["vc_pk_csv"] for c in grids[i]); vcrms_csv = max(c["vc_rms_csv"] for c in grids[i])
    vcpk_re = max(c["vc_pk"] for c in grids[i])
    assert abs(vcpk_csv - float(bsp[float(i)]["vc_pk_max_V"])) < 0.01, (i, vcpk_csv)
    assert abs(vcrms_csv - float(bsp[float(i)]["vc_rms_max_V"])) < 0.01
    assert abs(vcpk_re - vcpk_csv) / vcpk_csv < 0.03, (vcpk_re, vcpk_csv)     # FHA I_pk/(wC) is within 3 % of the ngspice column (conservative side)
    c3[str(i)] = {"bank_vpk_csv": vcpk_csv, "bank_vpk_recomputed": rnd(vcpk_re, 2), "bank_vrms_csv": vcrms_csv, "n_cases": len(grids[i])}
assert c3["28"]["bank_vpk_csv"] == 483.72 and c3["22"]["bank_vpk_csv"] == 470.7
res["controls"]["C3_stage15_bank_peak"] = {**c3, "PASS": True,
    "note": "483.72 V is the C21-C23 BANK voltage (RES_A to SW_B), not the coil voltage; fault_check.py's 'bank_Vpk' columns "
            "(1247-2038 V) are the OCP-fault bank peaks, a different quantity. Same round6 FHA case model as used below."}
# model self-consistency: the drive fundamental implied by each case is (4/pi)*sqrt2*line (crest bus), i.e. the model is
# a fixed-180-degree full bridge on a line-following bus
resid = 0.0
for c in grids[28]:
    zt = math.hypot(c["R"], c["w"] * c["L"] - 1 / (c["w"] * c["C"]))
    resid = max(resid, abs(c["ip"] * zt - 4 / math.pi * math.sqrt(2) * c["line"]) / (4 / math.pi * math.sqrt(2) * c["line"]))
res["controls"]["model_drive_residual_max_rel"] = rnd(resid, 4)
assert resid < 0.08   # ngspice peaks run up to ~6 % above the FHA fundamental (harmonic content)

# ---- time-domain node voltages over one carrier cycle at the line crest (FHA current, ideal 0/Vb switch nodes)
N = 1024


def nodes(vb, ip, w, c, phi):
    """vb = bus crest voltage; returns peak and carrier-crest RMS of each pair voltage (vs HV_RET unless a pair)."""
    acc = {k: [0.0, 0.0] for k in ("SW_A", "SW_B", "RES_A", "BUS_P_RES_A", "SW_A_RES_A", "RES_A_SW_B", "SW_A_SW_B")}
    for k in range(N):
        t = 2 * math.pi * (k + 0.5) / N
        sa = vb if math.sin(t) > 0 else 0.0
        sb = vb - sa
        vcap = -ip / (w * c) * math.cos(t - phi)
        resa = sb + vcap
        v = {"SW_A": sa, "SW_B": sb, "RES_A": resa, "BUS_P_RES_A": vb - resa, "SW_A_RES_A": sa - resa,
             "RES_A_SW_B": vcap, "SW_A_SW_B": sa - sb}
        for key, x in v.items():
            acc[key][0] = max(acc[key][0], abs(x)); acc[key][1] += x * x
    return {k: (a[0], math.sqrt(a[1] / N)) for k, a in acc.items()}


# ---- the board gaps that sit under the tank rule (stage-11 measured, m6m10/evidence.txt tank_pairs.py / stud_copper.py /
#      lug_rotation.py; the 5.0 mm rule is enforced in the DRC rules, native-21/layout/write_rules21.py).  No newer copper
#      dump is committed, so these are the figures of record.
GAPS = [
    {"gap": "RES_A-COIL_FEED (J5/J2 copper, F/B.Cu plan view)", "actual_mm": 5.000, "pair": "SW_A_RES_A"},
    {"gap": "RES_A-SW_A (F.Cu lane, 74 mm of edge; incl. T1 1-turn drop, neglected)", "actual_mm": 5.000, "pair": "SW_A_RES_A"},
    {"gap": "J2-J5 insulated ring to ring (any rotation)", "actual_mm": 5.000, "pair": "SW_A_RES_A"},
    {"gap": "J2-J5 REDCUBE body to body (15 mm pitch)", "actual_mm": 8.000, "pair": "SW_A_RES_A"},
    {"gap": "RES_A-SW_B (B.Cu, resonant-capacitor voltage)", "actual_mm": 5.002, "pair": "RES_A_SW_B"},
    {"gap": "RES_A-N_LS (In1; LOW group, LEG_RET-referenced)", "actual_mm": 5.002, "pair": "RES_A"},
    {"gap": "RES_A-HV_RET (In1)", "actual_mm": 5.900, "pair": "RES_A"},
    {"gap": "RES_A-BUS_P (In2)", "actual_mm": 5.900, "pair": "BUS_P_RES_A"},
    {"gap": "COIL_FEED-SW_B (bridge output, B.Cu)", "actual_mm": 30.000, "pair": "SW_A_SW_B"},
]

# ---- corner sweep: every (ceiling, bus, C, L_eq, R_eq), f solved so the line-cycle RMS equals the ceiling
F_FLOOR = 35e3        # firmware: tank_freq rejects f_min < 35 kHz; n21_binding refuses retime below it (DECISIONS item 14)
F_TOP = 60e3
ZVS = 1.05            # f >= 1.05 f_res (round6 rule)
LINES = (108.0, 120.0, 132.0, 140.0)
CAPS = (0.45e-6, 0.50e-6, 0.55e-6)                   # bank 5 x 0.1 uF +/-10 %
L_UNLOADED = tuple(66.5e-6 * k for k in (0.9, 1.0, 1.1))   # 70 uH free = 66.5 uH installed, +/-10 % (round6 MC basis)
L_LOADED = tuple(x * 1e-6 for x in range(30, 74, 3))
R_SET = (0.168, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0)


def solve(vb_pk_fund, L, R, C, ipk_target, f_floor):
    """Return (f, ipk, phi) or None.  Lowest legal f with I_pk <= target (input-limited at the floor if the drive is too weak)."""
    fres = 1 / (2 * math.pi * math.sqrt(L * C))
    f_lo = max(f_floor, ZVS * fres)
    if f_lo > F_TOP:
        return None

    def ip(f):
        w = 2 * math.pi * f
        return vb_pk_fund / math.hypot(R, w * L - 1 / (w * C))
    if ip(f_lo) <= ipk_target:
        f = f_lo
    elif ip(F_TOP) > ipk_target:
        return None                                   # ceiling cannot be met at any legal f -> not an operating point
    else:
        lo, hi = f_lo, F_TOP
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if ip(mid) > ipk_target else (lo, mid)
        f = hi
    w = 2 * math.pi * f
    return f, ip(f), math.atan2(w * L - 1 / (w * C), R)


def sweep(ceiling, rho, f_floor, caps, lines, with_nodes=True):
    best = {}
    n = 0
    for vl in lines:
        vb = math.sqrt(2) * vl
        vfund = 4 / math.pi * vb
        for C in caps:
            for L, Rs in [(L, (0.168, 0.25)) for L in L_UNLOADED] + [(L, R_SET) for L in L_LOADED]:
                for R in Rs:
                    s = solve(vfund, L, R, C, rho * ceiling, f_floor)
                    if s is None:
                        continue
                    f, ip, phi = s
                    n += 1
                    w = 2 * math.pi * f
                    zc = math.hypot(R, w * L)
                    rec = {"vcoil_pk": ip * zc, "vc_pk": ip / (w * C), "ip": ip, "f": f, "L": L, "R": R, "C": C, "vl": vl, "phi": phi}
                    cand = {"vcoil_pk": rec["vcoil_pk"], "vc_pk": rec["vc_pk"]}
                    if with_nodes:
                        nd = nodes(vb, ip, w, C, phi)
                        for k, (pk, rms) in nd.items():
                            cand["nd_" + k] = pk
                            rec["rms_" + k] = rms
                            rec["pk_" + k] = pk
                    for key, val in cand.items():
                        if key not in best or val > best[key][0]:
                            best[key] = (val, dict(rec))
    return best, n


def pack(best, key, rho):
    """Worst-case record for a quantity: pk, crest-RMS (pk/sqrt2 for sinusoids; true crest RMS for nodes), line-cycle RMS."""
    val, rec = best[key]
    return val, rec


def fmt_corner(rec):
    return {"f_kHz": rnd(rec["f"] / 1e3, 2), "L_eq_uH": rnd(rec["L"] * 1e6, 1), "R_eq_ohm": rec["R"], "C_uF": rnd(rec["C"] * 1e6, 2),
            "line_V": rec["vl"], "phase_deg": rnd(math.degrees(rec["phi"]), 1), "I_pk_A": rnd(rec["ip"], 1)}


# ---- 1. analytic bound table
bound_tab = []
corner_sets = [("orig: C 0.54 uF, f>=31.3 kHz (as M6)", 0.54e-6, F_RES_ORIG),
               ("design: C 0.50 uF nominal, f>=35 kHz floor", 0.50e-6, 35e3),
               ("design worst: C 0.45 uF (-10 %), f>=35 kHz floor", 0.45e-6, 35e3),
               ("below-floor fault corner: C 0.45 uF, f>=31.3 kHz", 0.45e-6, F_RES_ORIG)]
for name, c, fmin in corner_sets:
    xc = xc_of(fmin, c)
    for ceiling in (22.0, 27.2, 28.0, 29.4):
        for vl in (108, 120, 132, 140):
            vr, vp = bound(ceiling, xc, vl)
            vp2 = bound(ceiling, xc, vl, rho=2.113)[1]
            bound_tab.append({"corners": name, "Xc_ohm": rnd(xc, 3), "ceiling_A": ceiling, "line_V": vl,
                              "vrms_line": rnd(vr, 1), "vpk_rho2": rnd(vp, 1), "crest_rms": rnd(vp / math.sqrt(2), 1),
                              "vpk_rho2.113": rnd(vp2, 1),
                              "t18_line_mm": rnd(t18(vr)), "t18_crest_mm": rnd(t18(vp / math.sqrt(2))),
                              "t18_crest_extrapolated": t18_extrapolated(vp / math.sqrt(2))})
res["analytic_bound"] = bound_tab
# largest ceiling that keeps the bound at or below 400 V rms (the 5.0 mm Table 18 row), per corner set and line voltage
res["ceiling_for_400V_rms"] = {name: {str(vl): rnd((400.0 - 0.9 * vl) / xc_of(fmin, c), 2) for vl in (108, 120, 132, 140)}
                               for name, c, fmin in corner_sets}
# highest line voltage that keeps the bound at or below 400 V rms at a given ceiling (design worst corner)
_x = xc_of(35e3, 0.45e-6)
res["line_for_400V_rms_design_worst"] = {str(a): rnd((400.0 - a * _x) / 0.9, 1) for a in (22.0, 27.2, 28.0, 29.4)}
# frequency floor that restores 400 V rms at 28 A / 140 V line, C -10 %
res["f_floor_for_400V_28A_140V_C0p45_kHz"] = rnd(1 / (2 * math.pi * 0.45e-6 * ((400.0 - 0.9 * 140) / 28.0)) / 1e3, 2)
# 280 V-class sensitivity: the repo's only 280 V use is the D-31 OVP screen (stage15 fault_check.py BUS), a fault condition;
# M6's original bound did not include it.  Shown for completeness with the same formula, drive = (4/pi)*280 flat.
res["bus280_screen"] = {}
for ceiling in (22.0, 28.0):
    xc = xc_of(35e3, 0.45e-6)
    vpk = 2.0 * ceiling * xc + 4 / math.pi * 280.0
    res["bus280_screen"][str(ceiling)] = {"vpk": rnd(vpk, 1), "vrms_line_if_pk_over_2": rnd(vpk / 2, 1),
                                           "note": "D-31 OVP fault screen (bus 280 V, flat); not a working voltage, flagged only"}

# ---- 2. corner sweep (FHA, ZVS and floor constraints), design corners, three ceilings, two pk/rms ratios
sweeps = {}
for ceiling in (22.0, 28.0, 29.4):
    for rho in (2.0, 2.113):
        for tag, fl, caps in (("design", F_FLOOR, CAPS), ("orig-corner", F_RES_ORIG, (0.54e-6,))):
            best, n = sweep(ceiling, rho, fl, caps, LINES)
            vcoil_pk, rec = best["vcoil_pk"]
            vc_pk, rec_c = best["vc_pk"]
            row = {"ceiling_A": ceiling, "rho_pk_over_rms": rho, "corners": tag, "n_points": n,
                   "vcoil_pk": rnd(vcoil_pk, 1), "vcoil_line_rms": rnd(vcoil_pk / rho, 1), "vcoil_crest_rms": rnd(vcoil_pk / math.sqrt(2), 1),
                   "vcoil_corner": fmt_corner(rec),
                   "vcap_pk": rnd(vc_pk, 1), "vcap_line_rms": rnd(vc_pk / rho, 1), "vcap_crest_rms": rnd(vc_pk / math.sqrt(2), 1),
                   "vcap_corner": fmt_corner(rec_c)}
            nodes_out = {}
            for k in ("SW_A", "SW_B", "RES_A", "BUS_P_RES_A", "SW_A_RES_A", "RES_A_SW_B", "SW_A_SW_B"):
                val, r_ = best["nd_" + k]
                nodes_out[k] = {"pk": rnd(val, 1), "crest_rms": rnd(r_["rms_" + k], 1), "line_rms": rnd(r_["rms_" + k] / math.sqrt(2), 1),
                                "corner": fmt_corner(r_)}
            row["nodes"] = nodes_out
            sweeps[f"{ceiling}|{rho}|{tag}"] = row
res["sweep"] = list(sweeps.values())
# the sweep must sit at or below the analytic triangle bound of the same corners, and the 22 A orig-corner sweep must not
# exceed the M6 numbers (the M6 bound is an upper bound)
for key, row in sweeps.items():
    if row["rho_pk_over_rms"] != 2.0:
        continue
    cset = (0.54e-6, F_RES_ORIG) if row["corners"] == "orig-corner" else (0.45e-6, 35e3)
    bnd = bound(row["ceiling_A"], xc_of(cset[1], cset[0]), 140)
    assert row["vcoil_pk"] <= bnd[1] + 0.2, (key, row["vcoil_pk"], bnd)
assert sweeps["22.0|2.0|orig-corner"]["vcoil_pk"] <= 667.0 + 0.2

# ---- 3. round6 deterministic pan cases (loaded L_eq/R_eq from the task-05 pan models)
pan = {}
for i in (22, 28, 30):
    g = grids[i]
    des = [c for c in g if "-L70-C050-" in c["cfg"]]
    for label, sel in (("L70 design tank", des), ("all L (70/80/90 uH)", g)):
        w = max(sel, key=lambda c: c["vcoil_pk"])
        nd = nodes(math.sqrt(2) * w["line"], w["ip"], w["w"], w["C"], w["phi"])
        pan[f"{i}A | {label}"] = {
            "n_cases": len(sel), "case": w["case"], "status": w["status"], "f_kHz": rnd(w["f"] / 1e3, 2), "L_eq_uH": rnd(w["L"] * 1e6, 1),
            "R_eq_ohm": rnd(w["R"], 3), "I_rms_A": rnd(w["ir"], 2), "I_pk_A": rnd(w["ip"], 2),
            "vcoil_line_rms": rnd(w["vcoil_rms"], 1), "vcoil_pk": rnd(w["vcoil_pk"], 1), "vcoil_crest_rms": rnd(w["vcoil_pk"] / math.sqrt(2), 1),
            "vcap_line_rms": rnd(w["vc_rms"], 1), "vcap_pk": rnd(w["vc_pk"], 1),
            "vcoil_max_over_cases_line_rms": rnd(max(c["vcoil_rms"] for c in sel), 1),
            "res_a_to_hv_ret_pk": rnd(nd["RES_A"][0], 1), "res_a_to_hv_ret_crest_rms": rnd(nd["RES_A"][1], 1),
            "res_a_to_hv_ret_line_rms": rnd(nd["RES_A"][1] / math.sqrt(2), 1),
            "sw_pk": rnd(nd["SW_A"][0], 1), "sw_line_rms": rnd(nd["SW_A"][1] / math.sqrt(2), 1),
            "nodes": {k: {"pk": rnd(v[0], 1), "crest_rms": rnd(v[1], 1), "line_rms": rnd(v[1] / math.sqrt(2), 1)} for k, v in nd.items()}}
res["pan_cases"] = pan
# 29.4 A sensitivity from the 28 A pan result: V scales with I at fixed f, L, R (tank-limited cases)
p28 = pan["28A | L70 design tank"]
res["pan_29p4A_linear_scale"] = {k: rnd(p28[k] * 29.4 / 28.0, 1) for k in ("vcoil_line_rms", "vcoil_pk", "vcoil_crest_rms")}

# ---- 4. per-gap verdicts.  Governing figure = sweep at design corners, 28 A, rho 2.0 (repo convention: line-cycle time RMS
#      ~ carrier-crest peak / 2), compared against actual copper/lug distance.  The crest-RMS convention is reported in parallel.
verdicts = {}
for ceil_key in ("28.0", "29.4"):
    ceiling = float(ceil_key)
    row = sweeps[f"{ceiling}|2.0|design"]
    orow = sweeps[f"{ceiling}|2.0|orig-corner"]
    vlist = []
    for g in GAPS:
        k = g["pair"]
        if k in ("SW_A_RES_A", "RES_A_SW_B"):
            nd = row["nodes"][k]; ond = orow["nodes"][k]
        else:
            nd = row["nodes"][k]; ond = orow["nodes"][k]
        v_line, v_crest, v_pk = nd["line_rms"], nd["crest_rms"], nd["pk"]
        req_line, req_crest = t18(v_line), t18(v_crest)
        req_line_o = t18(ond["line_rms"])
        entry = {"gap": g["gap"], "actual_mm": g["actual_mm"], "pair": k,
                 "pk_V": v_pk, "crest_rms_V": v_crest, "line_rms_V": v_line,
                 "req_line_mm": rnd(req_line, 2), "req_crest_mm": rnd(req_crest, 2),
                 "req_crest_extrapolated": t18_extrapolated(v_crest),
                 "orig_corner_line_rms_V": ond["line_rms"], "orig_corner_req_line_mm": rnd(req_line_o, 2),
                 "verdict_line_rms": "PASS" if req_line <= g["actual_mm"] + 1e-9 else "FAIL",
                 "verdict_crest_rms": "PASS" if req_crest <= g["actual_mm"] + 1e-9 else "FAIL",
                 "clearance_ok": g["actual_mm"] >= CLEARANCE_MM}
        pn = res["pan_cases"]["28A | L70 design tank" if ceil_key == "28.0" else "28A | L70 design tank"]["nodes"][k]
        scale = 1.0 if ceil_key == "28.0" else 29.4 / 28.0
        entry["pan_model_L70_line_rms_V"] = rnd(pn["line_rms"] * scale, 1)
        entry["pan_model_L70_req_line_mm"] = rnd(t18(pn["line_rms"] * scale), 2)
        entry["pan_model_L70_verdict"] = "PASS" if t18(pn["line_rms"] * scale) <= g["actual_mm"] + 1e-9 else "FAIL"
        vlist.append(entry)
    verdicts[ceil_key] = vlist
res["gap_verdicts"] = verdicts
# the analytic-bound verdict for the 5.0 mm rule (the number M6 used), at 28 A
b = {(t["corners"], t["ceiling_A"], t["line_V"]): t for t in bound_tab}
res["rule_5mm_check_analytic_bound"] = {
    f"{c}|{a}": {"vrms_line": b[(c, a, 140)]["vrms_line"], "t18_line_mm": b[(c, a, 140)]["t18_line_mm"],
                 "within_400V_rms_rule": b[(c, a, 140)]["vrms_line"] <= 400.0}
    for c in (s[0] for s in corner_sets) for a in (22.0, 28.0, 29.4)}
res["requirement_if_fail"] = {}
for ceil_key in ("28.0", "29.4"):
    row = sweeps[f"{float(ceil_key)}|2.0|design"]
    v_line = row["nodes"]["SW_A_RES_A"]["line_rms"]
    v_crest = row["nodes"]["SW_A_RES_A"]["crest_rms"]
    res["requirement_if_fail"][ceil_key] = {"coil_line_rms_V": v_line, "needs_mm_line": rnd(t18(v_line), 2),
                                            "coil_crest_rms_V": v_crest, "needs_mm_crest": rnd(t18(v_crest), 2),
                                            "crest_extrapolated": t18_extrapolated(v_crest)}
res["constants"] = {"table18_rows_V_mm": T18, "clearance_mm_repo": CLEARANCE_MM, "f_floor_kHz": 35.0, "zvs_ratio": ZVS,
                    "bank_C_uF": [0.45, 0.50, 0.55], "L_installed_uH": [rnd(x * 1e6, 2) for x in L_UNLOADED], "lines_V": list(LINES)}

with open(os.path.join(HERE, "results.json"), "w") as fh:
    json.dump(res, fh, indent=1, sort_keys=True)
    fh.write("\n")

# ---- human-readable summary
print("controls: C1 333/667 V @22 A OK; C2 304.7-320.5 V / 636.2 V OK; C3 bank 483.72 V pk @28 A OK")
print("\nanalytic bound (140 V line)")
for t in bound_tab:
    if t["line_V"] == 140:
        print(f"  {t['corners'][:48]:48s} {t['ceiling_A']:5.1f} A  {t['vrms_line']:6.1f} Vrms  {t['vpk_rho2']:6.1f} Vpk  crest {t['crest_rms']:6.1f}  T18 {t['t18_line_mm']:.2f}/{t['t18_crest_mm']:.2f} mm")
print("\nsweep (rho 2.0, design corners)")
for ceiling in (22.0, 28.0, 29.4):
    r = sweeps[f"{ceiling}|2.0|design"]
    print(f"  {ceiling:4.1f} A coil {r['vcoil_line_rms']:6.1f} Vrms {r['vcoil_pk']:6.1f} Vpk crest {r['vcoil_crest_rms']:6.1f}; cap {r['vcap_line_rms']:6.1f} / {r['vcap_pk']:6.1f}; corner {r['vcoil_corner']}")
print("\npan cases")
for k, v in pan.items():
    print(f"  {k}: coil {v['vcoil_line_rms']} Vrms / {v['vcoil_pk']} Vpk (max-rms {v['vcoil_max_over_cases_line_rms']}); cap {v['vcap_line_rms']}/{v['vcap_pk']}; RES_A-HV_RET {v['res_a_to_hv_ret_line_rms']} Vrms/{v['res_a_to_hv_ret_pk']} pk")
for ck, vl in verdicts.items():
    print(f"\nverdicts {ck} A")
    for e in vl:
        print(f"  {e['gap'][:62]:62s} act {e['actual_mm']:6.3f}  V {e['line_rms_V']:6.1f}/{e['crest_rms_V']:6.1f}/{e['pk_V']:6.1f}  req {e['req_line_mm']:.2f}/{e['req_crest_mm']:.2f}  {e['verdict_line_rms']}/{e['verdict_crest_rms']}")
