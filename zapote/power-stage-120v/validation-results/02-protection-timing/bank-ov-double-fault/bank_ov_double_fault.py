#!/usr/bin/env python3
"""Bank over-voltage in a CT-failed double fault (DECISIONS item 13, open item).

usage: python3 bank_ov_double_fault.py      (no arguments; writes results.json next to this file)

Deterministic: closed-form series-RLC segments, fixed grids, no randomness. numpy only.

Inputs, all committed (paths relative to the unit):
  validation-results/02-protection-timing/stage15-28A/out/ocp_bands.json   shunt band, envelope peak
  validation-results/02-protection-timing/stage15-28A/out/fault_check.json  committed bound to reproduce
  validation-results/05-resonant-tank-envelope/round6-full-power/outputs/board-side-protection.csv
Constants copied from stage15-28A/fault_check.py (named there; asserted below against its output):
  L 66.5 uH +/-10 %, bank 0.50 uF +/-10 %, delay chain T_D.
Datasheet (not committed; TDK MKP_B32651_658.pdf, SHA-256 c32e3754...): see README.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[2]
S15 = UNIT / "validation-results/02-protection-timing/stage15-28A/out"
R6 = UNIT / "validation-results/05-resonant-tank-envelope/round6-full-power/outputs"

# ----------------------------------------------------------------------------- inputs
ocp = json.loads((S15 / "ocp_bands.json").read_text())
fc = json.loads((S15 / "fault_check.json").read_text())
prot = {float(r["I_max_A"]): r for r in csv.DictReader(open(R6 / "board-side-protection.csv"))}

BAND = next(r["band_after_bound_A"] for r in ocp["shunt_candidates"] if round(r["R34"]) == 12600 and round(r["R35"]) == 11700)
I_LO, I_HI = BAND                                  # 66.30 / 118.74 A (R34 12.6 k, after the Kelvin bound)

# ----------------------------------------------------------------------------- constants (fault_check.py)
L_NOM, C_NOM = 66.5e-6, 0.50e-6
L_MIN, L_MAX, C_MIN, C_MAX = L_NOM * 0.9, L_NOM * 1.1, C_NOM * 0.9, C_NOM * 1.1
T_FRONT, T_CHAIN = 555e-9, 573.2e-9
T_Q_EXTRA = 1.17e-6 - 181.6e-9
T_GATE = 150e-9
T_D = T_FRONT + T_CHAIN + T_Q_EXTRA + T_GATE
BUS = {"198 V": 198.0, "280 V": 280.0}            # 140 V line crest; OVP screen (D-31)
BANK_VR_DC = 1600.0                                # TDK B32654A1104K000, p.22 / DECISIONS 2026-10-09
BANK_VRMS_1K = 500.0                               # f <= 1 kHz, same page
BANK_PROOF = 1.6 * BANK_VR_DC                      # p.35 "DC test voltage between terminals 1.6 VR, 2 s" (factory test)
DVDT_LIM_V_PER_US = 1000.0                         # p.36, 27.5 mm, 1600 V DC / 500 V AC, non-sinusoidal dV/dt
F_FLOOR_FW = 35e3                                  # firmware f_min (PLAN s4)
R_LEVELS = {"0.05": 0.05, "0.15": 0.15, "0.60": 0.60, "1.60": 1.60}   # see README (R basis)


def pk_fund(v):                                    # square-wave fundamental peak
    return 4.0 / math.pi * v


# ----------------------------------------------------------------------------- controls (committed numbers)
def controls():
    out = {}
    pk28 = float(prot[28.0]["tank_pk_max_A"])
    assert pk28 == 59.17, pk28
    out["envelope_peak_28A"] = pk28
    assert (I_LO, I_HI) == (66.3, 118.74), BAND
    out["shunt_band_R34_12k6_A"] = [I_LO, I_HI]
    vc = float(prot[28.0]["vc_pk_max_V"])
    assert vc == 483.72, vc
    out["bank_vc_pk_max_28A_V"] = vc
    # fault_check.py recomputation
    f_res_min = 1 / (2 * math.pi * math.sqrt(L_MAX * C_NOM * 1.1))
    z0_max = math.sqrt(L_MAX / C_MIN)
    assert abs(T_D * 1e6 - fc["t_d_us"]) < 1e-3, (T_D, fc["t_d_us"])
    assert round(f_res_min) == fc["f_res_min_hz"], f_res_min
    assert round(z0_max, 3) == fc["z0_max_ohm"], z0_max
    rows = {}
    for r in fc["shunt"]:
        if r["divider"].startswith("R34 12.6k"):
            rows[r["bus"]] = r
    for name, v in (("198 V (140 V line crest)", 198.0), ("280 V (OVP screen, D-31)", 280.0)):
        dA = v / (math.pi * L_MIN * f_res_min)
        didt = (v + z0_max * (I_HI + dA)) / L_MIN
        i_off = I_HI + min(dA, didt * T_D)
        assert round(i_off, 1) == rows[name]["I_off_max_A"], (i_off, rows[name])
        assert round(z0_max * I_HI) == rows[name]["bank_Vpk_no_growth_V"]
        assert round(z0_max * (I_HI + dA)) == rows[name]["bank_Vpk_with_growth_V"]
        out[f"committed_bound_{name[:5].strip()}"] = {
            "I_off_max_A": round(i_off, 1), "bank_Vpk_no_growth_V": round(z0_max * I_HI),
            "bank_Vpk_with_growth_V": round(z0_max * (I_HI + dA)), "matches_fault_check_json": True}
    out["t_d_us"] = round(T_D * 1e6, 3)
    out["z0_max_ohm"] = round(z0_max, 3)
    out["f_res_min_hz"] = round(f_res_min)
    return out, z0_max, f_res_min


# ----------------------------------------------------------------------------- time-domain model
def seg(L, C, R, state, u, tau):
    """Exact series-RLC response to a constant source u for times tau (array). state=(i0,v0). Returns i, v."""
    i0, v0 = state
    a = R / (2 * L)
    w0sq = 1 / (L * C)
    w = math.sqrt(w0sq - a * a)
    y0, yd0 = v0 - u, i0 / C
    e = np.exp(-a * tau)
    cs, sn = np.cos(w * tau), np.sin(w * tau)
    y = e * (y0 * cs + (yd0 + a * y0) / w * sn)
    yd = e * (yd0 * cs - (a * yd0 + w0sq * y0) / w * sn)
    return C * yd, y + u


def run_trip(L, C, R, V, f, itrip, td, nmax=900, ngrid=240):
    """Open-loop bridge at f from rest; shunt trips when |i| >= itrip; bridge off td later; diode free-wheel until i=0.
    Returns dict or None when the trip is never reached in nmax half-cycles."""
    T2 = 0.5 / f
    st = (0.0, 0.0)
    s = 1.0
    tau = np.linspace(0.0, T2, ngrid + 1)
    vmax = 0.0
    for k in range(nmax):
        i, v = seg(L, C, R, st, s * V, tau)
        hit = np.nonzero(np.abs(i) >= itrip)[0]
        if hit.size == 0:
            vmax = max(vmax, float(np.max(np.abs(v))))
            st = (float(i[-1]), float(v[-1]))
            s = -s
            continue
        j = hit[0]
        i_a, i_b = abs(i[j - 1]), abs(i[j])
        tc = tau[j - 1] + (tau[j] - tau[j - 1]) * (itrip - i_a) / (i_b - i_a)
        vmax = max(vmax, float(np.max(np.abs(v[:j]))))
        toff = tc + td
        # propagate to toff (td < T2: at most one source reversal)
        if toff <= T2:
            tt = np.linspace(0.0, toff, 120)
            ii, vv = seg(L, C, R, st, s * V, tt)
        else:
            ii1, vv1 = seg(L, C, R, st, s * V, np.linspace(0.0, T2, 240))
            st2 = (float(ii1[-1]), float(vv1[-1]))
            vmax = max(vmax, float(np.max(np.abs(vv1))))
            tt = np.linspace(0.0, toff - T2, 120)
            ii, vv = seg(L, C, R, st2, -s * V, tt)
        vmax = max(vmax, float(np.max(np.abs(vv))))
        i_off, v_off = float(ii[-1]), float(vv[-1])
        # diode free-wheel: v_AB = -V*sign(i); stop at first i = 0 (V_C peak there)
        sg = 1.0 if i_off > 0 else -1.0
        st3 = (i_off, v_off)
        tfw = np.linspace(0.0, 1.2 * math.pi / math.sqrt(1 / (L * C) - (R / (2 * L)) ** 2), 4000)
        ii, vv = seg(L, C, R, st3, -sg * V, tfw)
        z = np.nonzero(ii * sg <= 0)[0]
        n = z[0] if z.size else len(tfw) - 1
        vmax = max(vmax, float(np.max(np.abs(vv[: n + 1]))))
        return {"tripped": True, "half_cycles": k + 1, "I_off_A": abs(i_off), "V_off_V": abs(v_off), "Vc_peak_V": vmax}
    return None


def fund_amp(L, C, R, V, f):
    w = 2 * math.pi * f
    X = w * L - 1 / (w * C)
    return pk_fund(V) / math.hypot(R, X)


def steady_edge(L, C, R, V, ihi, fmin, f0):
    """Highest bank voltage with the shunt NOT tripping (quasi-steady): max over f in [fmin, 80 kHz] of
    I_fund*X_C subject to I_fund <= ihi (V_C = I*X_C, sine, at drive f)."""
    fs = np.concatenate([np.linspace(fmin, 80e3, 40001), f0 * (1 - np.logspace(-6, -1, 400)),
                         f0 * (1 + np.logspace(-6, -1, 400))])
    fs = fs[(fs >= fmin) & (fs <= 80e3)]
    w = 2 * np.pi * fs
    X = w * L - 1 / (w * C)
    I = pk_fund(V) / np.hypot(R, X)
    Xc = 1 / (w * C)
    ok = I <= ihi
    if not ok.any():
        return None
    vc = np.where(ok, I * Xc, -1.0)
    k = int(np.argmax(vc))
    return {"f_hz": float(fs[k]), "I_pk_A": float(I[k]), "Xc_ohm": float(Xc[k]), "Vc_pk_V": float(vc[k])}


# ----------------------------------------------------------------------------- main study
DELTAS = [0.0] + [s * d for d in (2e-4, 5e-4, 1e-3, 2e-3, 3e-3, 5e-3, 7.5e-3, 1e-2, 1.5e-2, 2e-2, 3e-2, 4e-2, 5e-2,
                                   7e-2, 0.10, 0.15, 0.20) for s in (-1, 1)]
CORNERS = {"Lmax_Cmin (max Z0)": (L_MAX, C_MIN), "Lmax_Cmax": (L_MAX, C_MAX), "nominal": (L_NOM, C_NOM),
           "Lmin_Cmin": (L_MIN, C_MIN), "Lmin_Cmax": (L_MIN, C_MAX)}


def study():
    ctl, z0_max, f_res_min = controls()
    res = {"controls": ctl, "inputs": {
        "shunt_band_A": [I_LO, I_HI], "t_d_us": ctl["t_d_us"], "L_uH": [L_MIN * 1e6, L_NOM * 1e6, L_MAX * 1e6],
        "C_uF_bank": [C_MIN * 1e6, C_NOM * 1e6, C_MAX * 1e6], "R_levels_ohm": R_LEVELS, "bus_V": BUS,
        "bank_VR_dc_V": BANK_VR_DC, "bank_proof_1p6VR_V": BANK_PROOF,
        "bank_AC_peak_equiv_500Vrms_V": round(BANK_VRMS_1K * math.sqrt(2), 1)}}
    runs = []
    worst = {"F1_runaway": {"Vc_peak_V": 0}, "F2_pan_removal": {"Vc_peak_V": 0}}
    steady_worst = {"fw_floor_35k": {"Vc_pk_V": 0}, "no_floor": {"Vc_pk_V": 0}}
    for cname, (L, C) in CORNERS.items():
        f0 = 1 / (2 * math.pi * math.sqrt(L * C))
        for rname, R in R_LEVELS.items():
            for bname, V in BUS.items():
                # ---- quasi-steady, trip never reached (just under the upper band edge)
                for fl_name, fmin in (("fw_floor_35k", F_FLOOR_FW), ("no_floor", 15e3)):
                    se = steady_edge(L, C, R, V, I_HI, fmin, f0)
                    if se and se["Vc_pk_V"] > steady_worst[fl_name]["Vc_pk_V"]:
                        steady_worst[fl_name] = dict(se, corner=cname, R_ohm=R, bus=bname)
                # ---- time-domain trip
                for d in DELTAS:
                    f = f0 * (1 + d)
                    if f < 15e3 or f > 80e3:
                        continue
                    r = run_trip(L, C, R, V, f, I_HI, T_D)
                    if r is None:
                        continue
                    rec = dict(r, corner=cname, R_ohm=R, bus=bname, f_hz=round(f), f_over_f0=round(1 + d, 4),
                               Xc_ohm=1 / (2 * math.pi * f * C))
                    rec["dVdt_V_per_us"] = r["I_off_A"] / C * 1e-6
                    runs.append(rec)
                    # F1: frequency-loop runaway, any f. F2: pan-removal step with loop intact: f >= max(35 k, 1.05 f0)
                    if rec["Vc_peak_V"] > worst["F1_runaway"]["Vc_peak_V"]:
                        worst["F1_runaway"] = rec
                    if f >= max(F_FLOOR_FW, 1.05 * f0) - 1e-9 and rec["Vc_peak_V"] > worst["F2_pan_removal"]["Vc_peak_V"]:
                        worst["F2_pan_removal"] = rec
    res["time_domain_worst"] = worst
    res["quasi_steady_just_under_trip_worst"] = steady_worst
    res["n_tripped_runs"] = len(runs)
    res["max_I_off_A_any_run"] = max(r["I_off_A"] for r in runs)
    # sensitivity matrix: worst bank peak by (bus, R) for the loop-runaway time-domain case, the loop-intact
    # (f >= max(35 kHz, 1.05 f0)) time-domain case, and the quasi-steady just-under-trip case (no floor / 35 kHz floor)
    mat = {}
    for r in runs:
        key = f"{r['bus']} | R {r['R_ohm']:.2f}"
        m = mat.setdefault(key, {"F1_runaway_V": 0.0, "F2_loop_intact_V": 0.0, "steady_no_floor_V": 0.0,
                                 "steady_35k_floor_V": 0.0, "I_off_max_A": 0.0})
        m["F1_runaway_V"] = max(m["F1_runaway_V"], r["Vc_peak_V"])
        m["I_off_max_A"] = max(m["I_off_max_A"], r["I_off_A"])
        f0 = 1 / (2 * math.pi * math.sqrt(CORNERS[r["corner"]][0] * CORNERS[r["corner"]][1]))
        if r["f_hz"] >= max(F_FLOOR_FW, 1.05 * f0) - 1e-9:
            m["F2_loop_intact_V"] = max(m["F2_loop_intact_V"], r["Vc_peak_V"])
    for cname, (L, C) in CORNERS.items():
        f0 = 1 / (2 * math.pi * math.sqrt(L * C))
        for rname, R in R_LEVELS.items():
            for bname, V in BUS.items():
                key = f"{bname} | R {R:.2f}"
                m = mat.setdefault(key, {"F1_runaway_V": 0.0, "F2_loop_intact_V": 0.0, "steady_no_floor_V": 0.0,
                                         "steady_35k_floor_V": 0.0, "I_off_max_A": 0.0})
                for nm, fmin in (("steady_no_floor_V", 15e3), ("steady_35k_floor_V", F_FLOOR_FW)):
                    se = steady_edge(L, C, R, V, I_HI, fmin, f0)
                    if se:
                        m[nm] = max(m[nm], se["Vc_pk_V"])
    res["matrix_by_bus_and_R"] = {k: {a: round(b, 1) for a, b in v.items()} for k, v in sorted(mat.items())}
    # lowest drive frequency that would keep the double fault under V_R (all corners, both buses, all R)
    fl = {}
    for floor in (15e3, 20e3, 25e3, 30e3, 35e3):
        tdv = max([r["Vc_peak_V"] for r in runs if r["f_hz"] >= floor] or [0.0])
        sv = 0.0
        for cname, (L, C) in CORNERS.items():
            f0 = 1 / (2 * math.pi * math.sqrt(L * C))
            for R in R_LEVELS.values():
                for V in BUS.values():
                    se = steady_edge(L, C, R, V, I_HI, floor, f0)
                    if se:
                        sv = max(sv, se["Vc_pk_V"])
        fl[f"{floor / 1e3:.0f} kHz"] = {"time_domain_max_V": round(tdv, 1), "steady_max_V": round(sv, 1)}
    res["f_floor_sensitivity"] = fl
    # context: same quasi-steady bound if a lower trip level were still alive (62 A firmware peak trip, PLAN s4;
    # 76.09 A CT band high corner, DECISIONS 13). Not part of the double fault; shows what the CT trip is worth.
    ctx = {}
    for name, ihi in (("fw_peak_trip_62A", 62.0), ("ct_band_high_76.09A", 76.09), ("shunt_band_high_118.74A", I_HI)):
        sv = 0.0
        for cname, (L, C) in CORNERS.items():
            f0 = 1 / (2 * math.pi * math.sqrt(L * C))
            for R in R_LEVELS.values():
                for V in BUS.values():
                    se = steady_edge(L, C, R, V, ihi, 15e3, f0)
                    if se:
                        sv = max(sv, se["Vc_pk_V"])
        ctx[name] = round(sv, 1)
    res["context_quasi_steady_no_floor_by_trip_level_V"] = ctx
    # model sanity: sim overshoot stays inside the committed bound (fault_check I_off, 198 V and 280 V)
    bound = {"198 V": ctl["committed_bound_198 V"]["I_off_max_A"], "280 V": ctl["committed_bound_280 V"]["I_off_max_A"]}
    for r in runs:
        assert r["I_off_A"] <= bound[r["bus"]] + 1e-6, (r, bound)
    res["control_sim_inside_committed_I_off_bound"] = True
    # model cross-check: long run of the time-domain model vs the quasi-steady fundamental (no trip; itrip huge)
    xchk = []
    for (L, C, R, V, rel) in ((L_NOM, C_NOM, 0.6, 198.0, 0.10), (L_MAX, C_MIN, 1.6, 198.0, 0.05), (L_NOM, C_NOM, 0.6, 280.0, -0.10)):
        f = (1 / (2 * math.pi * math.sqrt(L * C))) * (1 + rel)
        T2 = 0.5 / f
        st = (0.0, 0.0)
        s = 1.0
        tau = np.linspace(0, T2, 400)
        ipk = vpk = 0.0
        for k in range(4000):
            i, v = seg(L, C, R, st, s * V, tau)
            st = (float(i[-1]), float(v[-1]))
            s = -s
            if k > 3500:
                ipk, vpk = max(ipk, float(np.max(np.abs(i)))), max(vpk, float(np.max(np.abs(v))))
        ia = fund_amp(L, C, R, V, f)
        xc = 1 / (2 * math.pi * f * C)
        rel_err = abs(ipk - ia) / ia
        assert rel_err < 0.06, (ipk, ia)
        xchk.append({"R": R, "bus_V": V, "f_over_f0": 1 + rel, "I_time_domain_A": round(ipk, 2),
                     "I_fundamental_A": round(ia, 2), "rel_err": round(rel_err, 4),
                     "Vc_time_domain_V": round(vpk, 1), "Vc_I_times_Xc_V": round(ia * xc, 1)})
    res["control_model_vs_fundamental"] = xchk

    # ---- verdict basis (criterion in README, written before this ran)
    cand = {
        "F1 runaway, trip + overshoot (time-domain)": worst["F1_runaway"]["Vc_peak_V"],
        "F2 pan removal, loop intact, trip + overshoot (time-domain)": worst["F2_pan_removal"]["Vc_peak_V"],
        "quasi-steady just under the upper band edge, f >= 35 kHz": steady_worst["fw_floor_35k"]["Vc_pk_V"],
        "quasi-steady just under the upper band edge, no f floor": steady_worst["no_floor"]["Vc_pk_V"],
    }
    gov_name = max(cand, key=cand.get)
    gov = cand[gov_name]
    res["candidates_V"] = {k: round(v, 1) for k, v in cand.items()}
    res["governing_case"] = gov_name
    res["governing_Vc_pk_V"] = round(gov, 1)
    res["ratio_to_VR_dc"] = round(gov / BANK_VR_DC, 3)
    res["ratio_to_proof_1p6VR"] = round(gov / BANK_PROOF, 3)
    res["ratio_to_AC_peak_equiv"] = round(gov / (BANK_VRMS_1K * math.sqrt(2)), 3)
    res["x_normal_operating_peak"] = round(gov / ctl["bank_vc_pk_max_28A_V"], 2)
    if gov <= BANK_VR_DC:
        v = "PASS"
    elif gov <= BANK_PROOF:
        v = "INCONCLUSIVE"
    else:
        v = "FAIL"
    res["verdict"] = v
    # unconditional, committed-bound view of the same double fault
    res["committed_bound_Vc_pk_V"] = {"no_growth_198V": ctl["committed_bound_198 V"]["bank_Vpk_no_growth_V"],
                                      "with_growth_198V": ctl["committed_bound_198 V"]["bank_Vpk_with_growth_V"],
                                      "with_growth_280V": ctl["committed_bound_280 V"]["bank_Vpk_with_growth_V"]}
    # clamp-study sizing at the governing point
    i_gov = worst["F1_runaway"]["I_off_A"] if gov_name.startswith("F1") else max(r["I_off_A"] for r in runs)
    res["clamp_sizing"] = {
        "I_off_A_governing_or_max": round(i_gov, 1),
        "energy_in_bank_at_peak_mJ": round(0.5 * C_MIN * gov ** 2 * 1e3, 1),
        "energy_in_coil_at_I_off_mJ": round(0.5 * L_MAX * (i_gov) ** 2 * 1e3, 1),
        "dVdt_at_I_off_V_per_us": round(i_gov / C_MIN * 1e-6, 1),
        "dVdt_limit_p36_V_per_us": DVDT_LIM_V_PER_US,
    }
    # top 5 worst tripped runs for the table
    top = sorted(runs, key=lambda r: -r["Vc_peak_V"])[:6]
    res["top_tripped_runs"] = [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()} for r in top]
    return res


def main():
    res = study()
    for k in ("time_domain_worst", "quasi_steady_just_under_trip_worst"):
        def rnd(o):
            if isinstance(o, dict):
                return {a: rnd(b) for a, b in o.items()}
            if isinstance(o, float):
                return round(o, 3)
            return o
        res[k] = rnd(res[k])
    out = HERE / "results.json"
    out.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: res[k] for k in ("candidates_V", "governing_case", "governing_Vc_pk_V", "ratio_to_VR_dc",
                                          "verdict", "max_I_off_A_any_run")}, indent=1))


if __name__ == "__main__":
    main()
