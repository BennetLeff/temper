#!/usr/bin/env python3
"""Tank-to-SELV/PE working voltage of the coil winding at the 28 A ceiling (row 12b of COIL-SPEC-ELECTRICAL.md).

usage: python3 coil_selv_28a.py        (stdlib only, deterministic, ~20 s) -> results.json beside this file

ASSUMED / bounded calculation: fundamental-harmonic tank current, ideal 0/Vbus switch nodes, no ringing, no bench data.

What 242 V rms / 640 V pk (DECISIONS item 7, ORACLE-ANSWER Q2) is
  The node "RES_A (old T1)" of tools/bus_voltage_sim.py::node_rms, i.e. the voltage of the resonant junction RES_A to
  EARTH (N at earth, SELV return bonded to PE, bus following the rectified line: HV_RET = min(v_line, 0),
  BUS_P = HV_RET + |v_line|, SW_B = HV_RET or BUS_P at the carrier, RES_A = SW_B + v_Cr), evaluated over a whole line
  cycle (rms) and for its peak.  The inputs are hand-entered in that script: line 127 V +10 % = 139.7 V, bank-capacitor
  crest 442 V (48 uH loaded coil) and tank current IN PHASE with the drive (v_Cr = -Vcr*cos(carrier phase)).
  Control C1 reproduces 165/220/242 V rms and 457/582/640 V pk from those inputs.  Control C2 shows 442 V is what a 22 A
  ceiling gives (44 A crest x Xc at 35 kHz, 0.45 uF = 444.6 V).  Control C3 reproduces the RES_A rows of
  ../coil-voltage-28a/results.json (22 A and 28 A, no-pan design worst).
"""
import csv
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UNIT = os.path.abspath(os.path.join(HERE, "../../../../../.."))
R6 = os.path.join(UNIT, "validation-results/05-resonant-tank-envelope/round6-full-power/outputs")
PRIOR = os.path.join(HERE, "../coil-voltage-28a/results.json")
SQ2 = math.sqrt(2.0)


def rnd(x, n=1):
    return round(x + 0.0, n)


# ------------------------------------------------------------------ node model (earth-referenced, repo convention)
def carrier_nodes(vb, amp, phi, sign, n=1024):
    """One carrier cycle. vb = instantaneous bus (>0), amp = v_Cr amplitude, phi = tank phase lag (rad, 0 = in phase with
    the drive), sign=+1 positive half cycle (HV_RET = earth), -1 negative half (BUS_P = earth).
    Returns {node: (sum_sq, peak)} over n samples for SW_A, SW_B, RES_A, all relative to EARTH."""
    ret = 0.0 if sign > 0 else -vb
    busp = vb if sign > 0 else 0.0
    acc = {"SW_A": [0.0, 0.0], "SW_B": [0.0, 0.0], "RES_A": [0.0, 0.0]}
    for k in range(n):
        t = 2 * math.pi * (k + 0.5) / n
        hi = math.sin(t) >= 0
        swa = busp if hi else ret
        swb = ret if hi else busp
        resa = swb - amp * math.cos(t - phi)
        for key, v in (("SW_A", swa), ("SW_B", swb), ("RES_A", resa)):
            acc[key][0] += v * v
            acc[key][1] = max(acc[key][1], abs(v))
    return {k: (a[0], a[1]) for k, a in acc.items()}


def line_cycle(vline_rms, amp_crest, phi, nl=48, n=512):
    """Explicit line-cycle integration (60 Hz envelope: bus = |v_line|, v_Cr amplitude proportional to the bus)."""
    vpk = vline_rms * SQ2
    tot = {"SW_A": 0.0, "SW_B": 0.0, "RES_A": 0.0}
    pk = {"SW_A": 0.0, "SW_B": 0.0, "RES_A": 0.0}
    for j in range(nl):
        th = 2 * math.pi * j / nl      # j = nl/4 hits the crest; j = 0, nl/2 have vb = 0 and are skipped
        vl = vpk * math.sin(th)
        vb = abs(vl)
        if vb < 1e-9:
            continue
        r = carrier_nodes(vb, amp_crest * vb / vpk, phi, 1 if vl >= 0 else -1, n)
        for key, (ss, p) in r.items():
            tot[key] += ss
            pk[key] = max(pk[key], p)
    return {k: (math.sqrt(tot[k] / (nl * n)), pk[k]) for k in tot}      # (line-cycle rms, peak)


def crest_nodes(vline_rms, amp_crest, phi, n=1024):
    """Shortcut: every term scales with |sin(line)|, so line rms = carrier-crest rms / sqrt2 and peak = crest peak.
    Equal to line_cycle() (asserted in C1b)."""
    r = carrier_nodes(vline_rms * SQ2, amp_crest, phi, +1, n)
    return {k: (math.sqrt(ss / n) / SQ2, p) for k, (ss, p) in r.items()}


# ------------------------------------------------------------------ controls
res = {"controls": {}}

# C1: the ORACLE Q2 table, from the oracle's own inputs (in-phase current, hand-entered bank crest)
c1 = {}
for label, vrms, vcr, exp_rms, exp_pk in (("127 V, 70 uH", 127.0, 277.0, 165.0, 457.0),
                                           ("127 V, 48 uH", 127.0, 402.0, 220.0, 582.0),
                                           ("127 V +10 %, 48 uH", 139.7, 442.0, 242.0, 640.0)):
    r = line_cycle(vrms, vcr, 0.0)["RES_A"]
    assert abs(r[0] - exp_rms) < 0.6 and abs(r[1] - exp_pk) < 1.0, (label, r)
    c1[label] = {"RES_A_rms": rnd(r[0]), "RES_A_pk": rnd(r[1]), "oracle": [exp_rms, exp_pk]}
res["controls"]["C1_oracle_Q2_reproduced_from_its_inputs"] = {**c1, "PASS": True,
    "basis": "RES_A to earth, N at earth, bus = |v_line|, in-phase tank current (phi = 0), line-cycle rms"}
# C1b: shortcut == explicit line-cycle integral (and == the oracle's own script when it is present)
a = line_cycle(139.7, 442.0, math.radians(88.0))["RES_A"]
b = crest_nodes(139.7, 442.0, math.radians(88.0))["RES_A"]
assert abs(a[0] - b[0]) < 0.3 and abs(a[1] - b[1]) < 0.6, (a, b)
res["controls"]["C1b_crest_shortcut_equals_line_cycle_integral"] = {"line_cycle": [rnd(a[0], 2), rnd(a[1], 2)],
                                                                   "shortcut": [rnd(b[0], 2), rnd(b[1], 2)], "PASS": True}
sim = os.path.join(UNIT, "tools")
if os.path.isdir(sim):
    sys.path.insert(0, sim)
    try:
        import bus_voltage_sim as bvs
        o = bvs.node_rms(139.7, 442.0)["RES_A (old T1)"]
        assert abs(o[0] - 242.1) < 0.1 and abs(o[1] - 639.6) < 0.1, o
        res["controls"]["C1c_oracle_script_tools_bus_voltage_sim"] = {"RES_A_rms": rnd(o[0], 2), "RES_A_pk": rnd(o[1], 2), "PASS": True}
    except ImportError:
        res["controls"]["C1c_oracle_script_tools_bus_voltage_sim"] = "not importable, skipped"


def xc(f, c):
    return 1.0 / (2 * math.pi * f * c)


# C2: 442 V is the 22 A ceiling (44 A crest = 2 x 22 A line-cycle rms) at the 35 kHz floor, 0.45 uF bank
vcr22 = 2 * 22.0 * xc(35e3, 0.45e-6)
assert abs(vcr22 - 442.0) / 442.0 < 0.01, vcr22
res["controls"]["C2_442V_is_the_22A_ceiling"] = {"I_crest_A": 44.0, "Xc_ohm_35kHz_0p45uF": rnd(xc(35e3, 0.45e-6), 3),
                                                  "V_Cr_crest": rnd(vcr22, 1), "oracle_input": 442.0, "PASS": True}

# ------------------------------------------------------------------ tank solver (same as ../coil-voltage-28a, FHA)
F_FLOOR, F_TOP, ZVS = 35e3, 60e3, 1.05
LINES = (108.0, 120.0, 132.0, 140.0)
CAPS = (0.45e-6, 0.50e-6, 0.55e-6)
L_UNLOADED = tuple(66.5e-6 * k for k in (0.9, 1.0, 1.1))
L_LOADED = tuple(x * 1e-6 for x in range(30, 74, 3))
R_SET = (0.168, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0)
RHO = 2.0       # I_crest / I_rms(line cycle), repo convention


def solve(vfund, L, R, C, ipk_target, f_floor=F_FLOOR):
    fres = 1 / (2 * math.pi * math.sqrt(L * C))
    f_lo = max(f_floor, ZVS * fres)
    if f_lo > F_TOP:
        return None

    def ip(f):
        w = 2 * math.pi * f
        return vfund / math.hypot(R, w * L - 1 / (w * C))
    if ip(f_lo) <= ipk_target:
        f = f_lo
    elif ip(F_TOP) > ipk_target:
        return None
    else:
        lo, hi = f_lo, F_TOP
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if ip(mid) > ipk_target else (lo, mid)
        f = hi
    w = 2 * math.pi * f
    return f, ip(f), math.atan2(w * L - 1 / (w * C), R)


def sweep(ceiling, subset):
    """subset 'unloaded' (no pan) or 'loaded' (pan equivalent circuits).  Returns worst-case records per metric."""
    pairs = ([(L, (0.168, 0.25)) for L in L_UNLOADED] if subset == "unloaded" else [(L, R_SET) for L in L_LOADED])
    best = {}
    n = 0
    for vl in LINES:
        vfund = 4 / math.pi * SQ2 * vl
        for C in CAPS:
            for L, Rs in pairs:
                for R in Rs:
                    s = solve(vfund, L, R, C, RHO * ceiling)
                    if s is None:
                        continue
                    f, ip, phi = s
                    n += 1
                    w = 2 * math.pi * f
                    nd = crest_nodes(vl, ip / (w * C), phi)
                    rec = {"f_kHz": rnd(f / 1e3, 2), "L_uH": rnd(L * 1e6, 1), "R_ohm": R, "C_uF": rnd(C * 1e6, 2), "line_V": vl,
                           "phase_deg": rnd(math.degrees(phi), 1), "I_crest_A": rnd(ip, 1)}
                    for node, (rms, pk) in nd.items():
                        for metric, val in (("rms", rms), ("pk", pk)):
                            key = f"{node}.{metric}"
                            if key not in best or val > best[key][0]:
                                best[key] = (val, rec, rms, pk)
    return best, n


def pack(best, node):
    r, p = best[f"{node}.rms"], best[f"{node}.pk"]
    return {"rms_max": rnd(r[0]), "rms_max_corner": r[1], "pk_max": rnd(p[0]), "pk_max_corner": p[1],
            "rms_and_pk_at_pk_corner": [rnd(p[2]), rnd(p[3])]}


# C3: reproduce the RES_A rows of the earlier study (selected there by max peak; rms is the rms at that corner)
prior = json.load(open(PRIOR))
unl, n_unl = {}, {}
for ceil in (22.0, 28.0, 29.4):
    b_unl, n_unl[ceil] = sweep(ceil, "unloaded")
    b_ld, _ = sweep(ceil, "loaded")
    unl[ceil] = (b_unl, b_ld)
c3 = {}
for row in prior["sweep"]:
    if row["rho_pk_over_rms"] != 2.0 or row["corners"] != "design":
        continue
    ceil = row["ceiling_A"]
    b_unl, b_ld = unl[ceil]
    best_pk = max(b_unl["RES_A.pk"], b_ld["RES_A.pk"], key=lambda x: x[0])
    got = (rnd(best_pk[2]), rnd(best_pk[3]))
    want = (row["nodes"]["RES_A"]["line_rms"], row["nodes"]["RES_A"]["pk"])
    assert abs(got[0] - want[0]) < 0.3 and abs(got[1] - want[1]) < 0.3, (ceil, got, want)
    c3[str(ceil)] = {"this_script_line_rms_pk": got, "prior_results_json": want}
res["controls"]["C3_prior_study_RES_A_rows"] = {**c3, "PASS": True,
    "note": "RES_A to HV_RET at the line crest equals RES_A to earth (HV_RET is earth there); line rms = crest rms / sqrt 2"}

# ------------------------------------------------------------------ pan cases: round-6 grid rows
def grid(i):
    out = []
    for p in sorted(glob.glob(os.path.join(R6, f"grid6-*-I{i}-*cases.csv"))):
        cfg = os.path.basename(p)[len("grid6-"):-len("-cases.csv")]
        for r in csv.DictReader(open(p)):
            f, L, R, C = float(r["freq_hz"]), float(r["L_eq_uH"]) * 1e-6, float(r["R_eq_ohm"]), float(r["C_bank_uF"]) * 1e-6
            w = 2 * math.pi * f
            phi = math.atan2(w * L - 1 / (w * C), R)
            ip = float(r["i_tank_pk_a"])
            nd = crest_nodes(float(r["line_vrms"]), ip / (w * C), phi)
            out.append({"cfg": cfg, "case": r["case"], "status": r["status"], "line_V": float(r["line_vrms"]), "f_kHz": rnd(f / 1e3, 2),
                        "L_uH": rnd(L * 1e6, 1), "R_ohm": rnd(R, 3), "I_rms_A": float(r["i_tank_rms_a"]), "I_crest_A": ip,
                        "phase_deg": rnd(math.degrees(phi), 1), "phase_csv_deg": float(r["fha_phase_deg"]),
                        "RES_A_rms": nd["RES_A"][0], "RES_A_pk": nd["RES_A"][1], "SW_A_rms": nd["SW_A"][0], "SW_A_pk": nd["SW_A"][1]})
    return out


def worst(rows):
    r = max(rows, key=lambda x: x["RES_A_rms"])
    p = max(rows, key=lambda x: x["RES_A_pk"])
    short = lambda x: {k: x[k] for k in ("case", "status", "line_V", "f_kHz", "L_uH", "R_ohm", "I_rms_A", "phase_deg", "RES_A_rms", "RES_A_pk")}
    return {"n": len(rows), "rms_max": rnd(r["RES_A_rms"]), "rms_max_case": short(r), "pk_max": rnd(p["RES_A_pk"]), "pk_max_case": short(p)}


g28, g22 = grid(28), grid(22)
assert g28 and g22
for r in g28:
    assert abs(r["phase_deg"] - r["phase_csv_deg"]) < 3.0, r
res["pan_grid"] = {
    "28A_design_tank_L70_C050": worst([r for r in g28 if "-L70-C050-" in r["cfg"]]),
    "28A_L70_any_C_and_gap": worst([r for r in g28 if "-L70-" in r["cfg"]]),
    "28A_all_configs": worst(g28),
    "22A_design_tank_L70_C050": worst([r for r in g22 if "-L70-C050-" in r["cfg"]]),
    "22A_all_configs": worst(g22),
}

# ------------------------------------------------------------------ scenarios (worst RES_A to earth; winding bound by it)
def scen(ceil):
    b_unl, b_ld = unl[ceil]
    return {"no_pan": {n: pack(b_unl, n) for n in ("RES_A", "SW_A")},
            "pan_equivalent_circuit": {n: pack(b_ld, n) for n in ("RES_A", "SW_A")}}


res["sweep"] = {"22.0": scen(22.0), "28.0": scen(28.0), "29.4": scen(29.4)}
res["sweep_points"] = {str(k): v for k, v in n_unl.items()}

# ------------------------------------------------------------------ headline numbers
# "With a pan (normal use)" = the round-6 grid rows at 28 A for the L70 coil (any bank / gap variant), as in the earlier
# study.  The analytic 'loaded' sweep reaches R_eq = 0.5 ohm (nearly unloaded), so it is NOT a pan case and is reported
# only as a sensitivity.
PANKEY = "28A_L70_any_C_and_gap"
pan28 = res["pan_grid"][PANKEY]["rms_max"]
pan28_pk = res["pan_grid"][PANKEY]["pk_max"]
head = {
    "pan_28A": {"rms": pan28, "pk": pan28_pk, "basis": "round-6 grid, L70, all C / gap variants, 108-140 V lines",
                "grid_L70_C050": [res["pan_grid"]["28A_design_tank_L70_C050"]["rms_max"], res["pan_grid"]["28A_design_tank_L70_C050"]["pk_max"]],
                "grid_all_L_70_80_90": [res["pan_grid"]["28A_all_configs"]["rms_max"], res["pan_grid"]["28A_all_configs"]["pk_max"]],
                "sensitivity_loaded_sweep_R0p5_to_5": [res["sweep"]["28.0"]["pan_equivalent_circuit"]["RES_A"]["rms_max"], res["sweep"]["28.0"]["pan_equivalent_circuit"]["RES_A"]["pk_max"]]},
    "no_pan_22A_clamp": {"rms": res["sweep"]["22.0"]["no_pan"]["RES_A"]["rms_max"], "pk": res["sweep"]["22.0"]["no_pan"]["RES_A"]["pk_max"]},
    "no_pan_28A_fault": {"rms": max(res["sweep"]["28.0"]["no_pan"]["RES_A"]["rms_max"], res["sweep"]["28.0"]["pan_equivalent_circuit"]["RES_A"]["rms_max"]),
                          "pk": max(res["sweep"]["28.0"]["no_pan"]["RES_A"]["pk_max"], res["sweep"]["28.0"]["pan_equivalent_circuit"]["RES_A"]["pk_max"]),
                          "basis": "worst over the unloaded and loaded equivalent-circuit sweeps (R_eq 0.168-5 ohm), as the earlier study's design-worst RES_A row"},
    "no_pan_29p4A_trip": {"rms": max(res["sweep"]["29.4"]["no_pan"]["RES_A"]["rms_max"], res["sweep"]["29.4"]["pan_equivalent_circuit"]["RES_A"]["rms_max"]),
                          "pk": max(res["sweep"]["29.4"]["no_pan"]["RES_A"]["pk_max"], res["sweep"]["29.4"]["pan_equivalent_circuit"]["RES_A"]["pk_max"]),
                          "basis": "worst over the unloaded and loaded equivalent-circuit sweeps (R_eq 0.168-5 ohm), as the earlier study's design-worst RES_A row"},
    "pan_22A_for_reference": {"rms": res["pan_grid"]["22A_all_configs"]["rms_max"], "pk": res["pan_grid"]["22A_all_configs"]["pk_max"]},
    "oracle_242_640_control": {"rms": 242.1, "pk": 639.6},
}
head["normal_use_envelope"] = {"rms": max(head["pan_28A"]["rms"], head["no_pan_22A_clamp"]["rms"]),
                               "pk": max(head["pan_28A"]["pk"], head["no_pan_22A_clamp"]["pk"])}
head["normal_use_envelope"]["governed_by"] = ("no-pan 22 A clamp" if head["no_pan_22A_clamp"]["rms"] >= head["pan_28A"]["rms"]
                                              else "pan 28 A")
res["headline"] = head

# ------------------------------------------------------------------ criteria
# Table 17 basic creepage, PD3, material group IIIa, working-voltage bands (packages/temper-design-bundle/src/safety_value.rs
# TABLE_17, the repo's transcription; the IEC text is not readable here).  Reinforced = 2 x basic (cl. 29.2.3).
T17_PD3 = [(50, 1.9), (125, 2.4), (250, 4.0), (400, 6.3), (500, 8.0), (800, 10.0), (1000, 12.5)]
T17_PD2 = [(50, 1.2), (125, 1.5), (250, 2.5), (400, 4.0), (500, 5.0), (800, 6.3), (1000, 8.0)]


def reinforced(v, table):
    for upper, basic in table:
        if v <= upper:
            return 2 * basic, upper
    return None, None


BOARD_MM = 8.0          # D5 provisional HOT <-> SELV/PE floor, = row 12b creepage
ROW12B = {"vrms": 242.0, "vpk": 640.0, "creepage_mm": 8.0, "clearance_mm": 3.0, "hipot_vrms": 3000.0,
          "pd_test_x_urp": 1.5, "pd_test_V_pk": 960.0, "pd_raised_V_pk": 1200.0, "pd_pC": 10.0}
HIPOT_PK = ROW12B["hipot_vrms"] * SQ2
IMPULSE_REINFORCED_V = 4000.0     # Table 16 step the 3.0 mm clearance rests on (ORACLE-ANSWER Q3, "verify")


def assess(label, v):
    rms, pk = v["rms"], v["pk"]
    crest = pk / SQ2
    need3, band3 = reinforced(rms, T17_PD3)
    need2, _ = reinforced(rms, T17_PD2)
    needc, bandc = reinforced(crest, T17_PD3)
    return {"label": label, "rms_V": rms, "pk_V": pk, "crest_rms_V": rnd(crest),
            "reinforced_creepage_PD3_mm_line_rms": need3, "band_upper_V": band3,
            "reinforced_creepage_PD2_mm_line_rms": need2,
            "reinforced_creepage_PD3_mm_crest_rms": needc,
            "a_board_8mm": "PASS" if need3 is not None and need3 <= BOARD_MM else "FAIL",
            "b_creepage_row12b": "PASS" if need3 is not None and need3 <= ROW12B["creepage_mm"] else "FAIL",
            "b_pd_test_1p5_urp_V_pk": rnd(1.5 * pk, 0), "b_pd_test_1p875_urp_V_pk": rnd(1.875 * pk, 0),
            "b_pd_level_in_row12b": "PASS" if ROW12B["pd_test_V_pk"] >= 1.5 * pk else "FAIL (row 12b level below 1.5 x U_rp)",
            "b_clearance_3mm": "PASS (impulse-set; recurring peak below the 2.5 kV step)" if pk < 2500.0 else "FAIL",
            "c_hipot_3000V": "PASS" if HIPOT_PK >= IMPULSE_REINFORCED_V and ROW12B["hipot_vrms"] >= 3000.0 else "FAIL",
            "c_hipot_pk_over_urp": rnd(HIPOT_PK / pk, 2)}


res["assessment"] = [
    assess("22 A control: ORACLE/DECISIONS item 7 as recorded", head["oracle_242_640_control"]),
    assess("22 A no-pan clamp (normal use), this model", head["no_pan_22A_clamp"]),
    assess("28 A with a pan (normal use)", head["pan_28A"]),
    assess("NORMAL-USE ENVELOPE (max of the two above)", head["normal_use_envelope"]),
    assess("28 A envelope of all tank states (clamp failed, fault)", head["no_pan_28A_fault"]),
    assess("29.4 A envelope of all tank states (RMS trip, fault)", head["no_pan_29p4A_trip"]),
]
# what the row would have to say
env = head["normal_use_envelope"]
flt = head["no_pan_29p4A_trip"]
res["recommended_row_12b"] = {
    "working_voltage_normal_use_rms_V": env["rms"], "working_voltage_normal_use_pk_V": env["pk"],
    "reinforced_creepage_mm_PD3_IIIa": reinforced(env["rms"], T17_PD3)[0],
    "reinforced_creepage_mm_PD2_IIIa": reinforced(env["rms"], T17_PD2)[0],
    "pd_test_1p5_urp_V_pk": rnd(1.5 * env["pk"], 0), "pd_test_raised_1p875_urp_V_pk": rnd(1.875 * env["pk"], 0),
    "fault_no_pan_29p4A_rms_V": flt["rms"], "fault_no_pan_29p4A_pk_V": flt["pk"],
    "fault_pd_1p5_urp_V_pk": rnd(1.5 * flt["pk"], 0),
}
res["constants"] = {"table17_PD3_IIIa_basic_V_mm": T17_PD3, "table17_PD2_IIIa_basic_V_mm": T17_PD2, "board_floor_mm": BOARD_MM,
                    "row12b": ROW12B, "lines_V": list(LINES), "caps_uF": [0.45, 0.50, 0.55], "f_floor_kHz": 35.0,
                    "L_unloaded_uH": [rnd(x * 1e6, 2) for x in L_UNLOADED], "rho_crest_over_rms": RHO}

with open(os.path.join(HERE, "results.json"), "w") as fh:
    json.dump(res, fh, indent=1, sort_keys=True)
    fh.write("\n")

print("controls: C1 242/640 (and 165/457, 220/582), C1b, C2 442 V, C3 prior RES_A rows: all asserted OK")
for k, v in head.items():
    print(f"{k:28s} {v}")
for a in res["assessment"]:
    print(f"{a['label'][:52]:52s} {a['rms_V']:6.1f} Vrms {a['pk_V']:6.1f} Vpk  reinf PD3 {a['reinforced_creepage_PD3_mm_line_rms']} mm "
          f"(PD2 {a['reinforced_creepage_PD2_mm_line_rms']})  a:{a['a_board_8mm']}  PD1.5x {a['b_pd_test_1p5_urp_V_pk']:.0f}")
print(res["recommended_row_12b"])
