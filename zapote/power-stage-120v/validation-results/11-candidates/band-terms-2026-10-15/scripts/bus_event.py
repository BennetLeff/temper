#!/usr/bin/env python3
"""Item 3: stacked bus-overvoltage event inputs for the ledger's 451.6 V rows, on the current tank state.

    python3 -I bus_event.py [PS_DIR]   -> ../results/bus_event.json, ../results/bus_event.md
    (run band_cmrr.py first: the CM-term band tops are read from ../results/band_cmrr.json)

Read-only on PS. Three parts.

A. Tank energy at gate-off (E_t). The committed bank-ov model (02-protection-timing/bank-ov-double-fault/
   bank_ov_double_fault.py; imported, its main() is not called) drives the s47 tank basis (L 66.5 uH +-10 %, bank
   0.50 uF +-10 %, R 0.05..1.6 ohm, 35 frequency offsets) open-loop until |i| reaches the trip level I_HI, turns the
   bridge off T_D = 2.267 us later, and reports I_off. This script repeats its grid with run_trip() copied verbatim
   except that it returns the SIGNED state (i, v_C) at gate-off, so the tank energy 1/2 L i^2 + 1/2 C v^2 is exact
   per run. Control: I_HI = 118.74 A on the 198 / 280 V buses reproduces the committed max I_off 155.4 A.
B. The r2-cost closed form (11-candidates/r2-cost/scripts/bus_peak_no_clamp.py:17-22, imported, run on new inputs):
       V1 = sqrt(V0^2 + 2 E_t / C);  Vpk = Vs + sqrt((V1 - Vs)^2 + (L/C) I0^2)
   C = 14.9 uF (18.4 uF -19 %), Vs 198 V, L 500 uH, I0 30 A. Control: E_t 0.475 J, V0 287.62 V -> 451.6 V (ledger).
C. OVP-delay overshoot: the line ring (L, C, Vs; bridge draw ignored, which only raises dV/dt) through the U7 sense
   filter (R_th = 4 x 470 k || 15.8 k, C27 1 nF C0G +-5 %, C0603C102J5GACTU) with the static trip at the s47 band top;
   gate-off T_D after the filtered crossing. The ring is set to carry I0 = 30 A as it passes the band top (the
   committed stacking basis). Then E_t is added at (V0', I0') and the ring continues (closed form).
D. Time-domain gate-off event with and without the D3 / D17 string (Good-Ark 30KPA150CA x 2): tank free-wheeling
   through the body diodes into the bus, line ring, clamp. The datasheet gives only VBR min 167.6 V @ 5 mA and
   VC max 233.4 V @ IPP 129.8 A, 10/1000 us, per device at 25 C (Doc.US30KPA28A-30KPA320CAxSM5.0, p.3); no V-I curve,
   no VBR max, no tempco. So the clamp bound used is VC <= 466.8 V for I <= 129.8 A (monotone V-I); two straight-line
   V-I models (onset at VBR min 335.2 V, or at 2 x 184.36 V = 368.72 V, the VBR max that the Littelfuse sheet for the
   same 30KPA150CA row prints (Littelfuse 30KPA series, LCSC C19111562 copy, p.2; Good-Ark prints no max), also
   scaled by the Littelfuse typical tempco 0.1 %/K (p.1) to the D3 B3 temperature 73 C) give the clamp current,
   energy and pulse width for the pulse-rating check (p.4 Fig. 4 Ppk vs td, Fig. 1 derating); a near-ideal 323 V
   clamp bounds the clamp current from above.
"""
import sys
sys.dont_write_bytecode = True
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PS = Path(sys.argv[1] if len(sys.argv) > 1 else
          "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
OUT = HERE.parent / "results"
VR = PS / "validation-results"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bo = load("bo", VR / "02-protection-timing/bank-ov-double-fault/bank_ov_double_fault.py")   # top level reads only
# r2-cost closed form: the module runs its table at import and writes its results JSON, so take vpk() from the
# source text instead of executing the file (the formula is lines 17-22 of the docstring and the vpk() body)
src = (VR / "11-candidates/r2-cost/scripts/bus_peak_no_clamp.py").read_text()
ns = {"math": math, "E_T": 0.475}
exec(src[src.index("def vpk("):src.index("rows = []")], ns)          # defines vpk() only
vpk = ns["vpk"]
C_BUS = 14.9e-6
VS, L_LINE, I0 = 198.0, 500e-6, 30.0
Z_LINE = math.sqrt(L_LINE / C_BUS)
V_OVP_TOP = 287.62                 # bands-s47.md:24 (c28), the ledger's static value
E_T_STALE = 0.475                  # ALT-D3 s1.1 (stage-13b band 47.32-97.77 A, 1.5 us, 77 uH)

# ----------------------------------------------------------------------------- ledger rows that use the event peak
ROWS = [  # (entry, check id, limit V, max_ratio, how the stress is formed)
    ("CC1206JKNPOCBN102 (C12, C13, C19, C20)", "bus no-clamp worst", 1000.0, 0.5, 1.0),
    ("B32676G1905K000 (C5, C6)", "Vbus worst", 750.0, 0.8, 1.0),
    ("B32676G1905K000 (C5, C6)", "Vbus worst hot", 570.0, 0.8, 1.0),
    ("B32652A0104K000 (C38-C41)", "V", 1000.0, 0.8, 1.0),
    ("B32652A0104K000 (C38-C41)", "V hot", 687.5, 0.8, 1.0),
    ("GBJ2510-F (BR1)", "V reverse", 1000.0, 0.8, 1.0),
    ("2EDR8259XXUMA1 (U1, U2)", "barrier", 1767.0, 0.5, 1.0),
    ("RC1206FR-07220KL (R3, R4)", "V transient", 400.0, 1.0, 0.5),
]


def ratios(v):
    return [{"entry": e, "check": c, "limit_V": lim, "max_ratio": mx, "stress_V": round(v * f, 1),
             "ratio": round(v * f / lim, 4), "pass": v * f / lim <= mx} for e, c, lim, mx, f in ROWS]


# ----------------------------------------------------------------------------- A. tank state at gate-off
def run_trip_signed(L, C, R, V, f, itrip, td, nmax=900, ngrid=240):
    """bank_ov_double_fault.run_trip, verbatim, returning the signed (i, v_C) at gate-off."""
    seg = bo.seg
    T2 = 0.5 / f
    st = (0.0, 0.0)
    s = 1.0
    tau = np.linspace(0.0, T2, ngrid + 1)
    for k in range(nmax):
        i, v = seg(L, C, R, st, s * V, tau)
        hit = np.nonzero(np.abs(i) >= itrip)[0]
        if hit.size == 0:
            st = (float(i[-1]), float(v[-1]))
            s = -s
            continue
        j = hit[0]
        i_a, i_b = abs(i[j - 1]), abs(i[j])
        tc = tau[j - 1] + (tau[j] - tau[j - 1]) * (itrip - i_a) / (i_b - i_a)
        toff = tc + td
        if toff <= T2:
            ii, vv = seg(L, C, R, st, s * V, np.linspace(0.0, toff, 120))
        else:
            ii1, vv1 = seg(L, C, R, st, s * V, np.linspace(0.0, T2, 240))
            st2 = (float(ii1[-1]), float(vv1[-1]))
            ii, vv = seg(L, C, R, st2, -s * V, np.linspace(0.0, toff - T2, 120))
        return {"I_off": float(ii[-1]), "V_off": float(vv[-1]), "half_cycles": k + 1}
    return None


def tank_grid(i_hi, buses):
    best_e, best_i, runs = None, None, 0
    for cname, (L, C) in bo.CORNERS.items():
        f0 = 1 / (2 * math.pi * math.sqrt(L * C))
        for R in bo.R_LEVELS.values():
            for V in buses:
                for d in bo.DELTAS:
                    f = f0 * (1 + d)
                    if f < 15e3 or f > 80e3:
                        continue
                    r = run_trip_signed(L, C, R, V, f, i_hi, bo.T_D)
                    if r is None:
                        continue
                    runs += 1
                    e = 0.5 * L * r["I_off"] ** 2 + 0.5 * C * r["V_off"] ** 2
                    rec = dict(r, corner=cname, L_uH=L * 1e6, C_uF=C * 1e6, R=R, bus=V, f_hz=round(f),
                               E_tank_J=e, E_coil_J=0.5 * L * r["I_off"] ** 2)
                    if best_e is None or e > best_e["E_tank_J"]:
                        best_e = rec
                    if best_i is None or abs(r["I_off"]) > abs(best_i["I_off"]):
                        best_i = rec
    return {"runs": runs, "max_E": best_e, "max_I": best_i,
            "E_coil_Lmax_at_max_I_J": 0.5 * bo.L_MAX * best_i["I_off"] ** 2}


# ----------------------------------------------------------------------------- C. OVP delay
R_TH_NOM = (4 * 470e3) * 15.8e3 / (4 * 470e3 + 15.8e3)
R_TH_MAX = (4 * 470e3 * 1.01) * (15.8e3 * 1.001) / (4 * 470e3 * 1.01 + 15.8e3 * 1.001)
TAU = {"nominal 15.67 k x 1 nF": R_TH_NOM * 1e-9, "max (R +1 % / +0.1 %, C27 +5 %)": R_TH_MAX * 1.05e-9}


def ovp_delay(tau, td=bo.T_D, v_trip=V_OVP_TOP, i_at_trip=I0, dt=2e-9):
    """Line ring of L_LINE / C_BUS around VS that passes v_trip carrying i_at_trip; first-order filter (time
    constant tau) on the bus, starting in equilibrium at the ring's start (V = VS, maximum current). Returns the bus
    state when the gate goes off td after the filtered crossing."""
    k = math.hypot(v_trip - VS, Z_LINE * i_at_trip)       # ring amplitude (V)
    w = 1 / math.sqrt(L_LINE * C_BUS)
    t = np.arange(0.0, 0.5 * math.pi / w, dt)            # from V = VS (phase 0) to the ring peak
    vb = VS + k * np.sin(w * t)
    il = k / Z_LINE * np.cos(w * t)
    # exact discrete first-order filter
    a = math.exp(-dt / tau)
    y = np.empty_like(vb)
    y[0] = vb[0]
    for n in range(1, len(vb)):
        y[n] = a * y[n - 1] + (1 - a) * vb[n]
    ic = int(np.argmax(vb >= v_trip))
    jf = np.nonzero(y >= v_trip)[0]
    if jf.size == 0:
        return {"filtered_never_crosses": True, "ring_peak_V": round(VS + k, 2)}
    jf = int(jf[0])
    joff = min(jf + int(round(td / dt)), len(vb) - 1)
    return {"tau_us": round(tau * 1e6, 3), "ring_peak_no_tank_V": round(VS + k, 2),
            "dVdt_at_trip_V_per_us": round(il[ic] / C_BUS * 1e-6, 3),
            "filter_lag_us": round((jf - ic) * dt * 1e6, 3), "t_d_us": round(td * 1e6, 3),
            "V0_gate_off_V": round(float(vb[joff]), 2), "I0_gate_off_A": round(float(il[joff]), 3),
            "overshoot_V": round(float(vb[joff]) - v_trip, 2),
            "naive_constant_30A_V": round(I0 * ((jf - ic) * dt + td) / C_BUS, 2)}


# ----------------------------------------------------------------------------- D. time-domain gate-off event
CLAMP = {  # string of two 30KPA150CA; (onset V, V at 129.8 A); straight lines, NOT published curves
    "none": None,
    "onset VBR min 335.2 V (low line)": (335.2, 466.8),
    "onset 368.72 V (Littelfuse VBR max) (high line)": (368.72, 466.8),
    "high line hot, x(1 + 0.1 %/K x 48 K) at 73 C": (368.72 * 1.048, 466.8 * 1.048),
    "near-ideal at VBR min -10 C, 323 V, 129.8 A at 329.5 V (bounds the clamp current)": (323.0, 329.5),
}
IPP, VC_MAX = 129.8, 466.8


def event(state, clamp, v0, i0=I0, dt=2e-9, tmax=400e-6):
    """Bridge off. Tank (L, C, R) free-wheels through the body diodes into the bus; line source VS behind L_LINE
    (rectifier: i_line >= 0); bus C_BUS; clamp i_c(V). Semi-implicit Euler, dt 2 ns. Returns peaks and clamp pulse."""
    L, Cr, R = state["L_uH"] * 1e-6, state["C_uF"] * 1e-6, state["R"]
    it, vr, vb, il = state["I_off"], state["V_off"], v0, i0
    vpk, icpk, ec, t_c, ec_t = vb, 0.0, 0.0, [], []
    n = int(tmax / dt)
    on = True
    for k in range(n):
        # bridge diodes: v_AB = -sign(i) Vb while conducting; restart if |vr| > vb with i = 0
        if it == 0.0:
            if abs(vr) > vb:
                sgn = -1.0 if vr > 0 else 1.0
            else:
                sgn = 0.0
        else:
            sgn = 1.0 if it > 0 else -1.0
        if sgn != 0.0:
            di = (-sgn * vb - vr - R * it) / L * dt
            it_new = it + di
            if it != 0.0 and it_new * it < 0:      # current reached zero this step
                it_new = 0.0
            it = it_new
            vr += it / Cr * dt
        ib = abs(it) if sgn != 0.0 else 0.0
        if clamp is None or vb <= clamp[0]:
            ic = 0.0
        else:
            ic = (vb - clamp[0]) / (clamp[1] - clamp[0]) * IPP
        dil = (VS - vb) / L_LINE * dt
        il = max(0.0, il + dil)
        vb += (ib + il - ic) / C_BUS * dt
        if ic > 0:
            ec += vb * ic * dt
            t_c.append(k * dt)
            ec_t.append(ic)
        if vb > vpk:
            vpk = vb
        icpk = max(icpk, ic)
        if it == 0.0 and il == 0.0 and abs(vr) <= vb and k * dt > 20e-6:
            break
    out = {"Vbus_peak_V": round(vpk, 2), "clamp_I_peak_A": round(icpk, 2), "clamp_energy_J": round(ec, 4)}
    if ec_t:
        arr = np.array(ec_t)
        tt = np.array(t_c)
        half = tt[arr >= 0.5 * arr.max()]
        out["clamp_conduction_us"] = round((tt[-1] - tt[0]) * 1e6, 2)
        out["clamp_t_above_half_peak_us"] = round((half[-1] - half[0]) * 1e6, 2)
    return out


def fig4_ppk_kw(td_us):
    """Good-Ark p.4 Fig. 4, straight on log-log through its two printed end labels, 370 kW at 1 us and 27 kW at
    1000 us (the ALT-D3 digitisation reads 380 / 165 / 65 / 28 kW at 1 / 10 / 100 / 1000 us, the same line)."""
    return 370.0 * (td_us / 1.0) ** (math.log(27 / 370) / math.log(1000))


def main():
    out = {}
    # ---- A
    ctl = tank_grid(118.74, (198.0, 280.0))
    assert abs(abs(ctl["max_I"]["I_off"]) - 155.4) < 0.06, ctl["max_I"]
    out["control_118p74A_198_280V"] = {"max_I_off_A": round(abs(ctl["max_I"]["I_off"]), 2),
                                       "E_coil_Lmax_at_max_I_J": round(ctl["E_coil_Lmax_at_max_I_J"], 4),
                                       "max_E_tank_J": round(ctl["max_E"]["E_tank_J"], 4)}
    cm = json.loads((OUT / "band_cmrr.json").read_text())
    top_r1 = max(r["shunt_a"][1] for r in cm["rows"] if r["reading"] == "R1" and r["psrr"] and r["hot5"].startswith("Q1"))
    top_r1_phys = max(r["shunt_a"][1] for r in cm["rows"] if r["reading"] == "R1" and r["psrr"])
    cases = {"CT band top 76.09 A (CT path alive; single fault)": 76.09,
             "s47 shunt top 119.09 A (bands-s47.md:24)": 119.09,
             f"shunt top + CMRR R1 (Q1 HOT5) {top_r1:.2f} A": top_r1,
             f"shunt top + CMRR R1 (physical HOT5) {top_r1_phys:.2f} A": top_r1_phys}
    tank = {}
    for lab, ihi in cases.items():
        g = tank_grid(ihi, (198.0, 280.0, V_OVP_TOP, 323.04))   # 323.04 V: the OVP-delayed bus (part C)
        tank[lab] = {"I_HI_A": ihi, "runs": g["runs"], "max_I_off_A": round(abs(g["max_I"]["I_off"]), 2),
                     "E_coil_Lmax_at_max_I_J": round(g["E_coil_Lmax_at_max_I_J"], 4),
                     "max_E_tank_J": round(g["max_E"]["E_tank_J"], 4),
                     "max_E_run": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in g["max_E"].items()},
                     "max_I_run": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in g["max_I"].items()}}
    out["tank_at_gate_off"] = tank
    # ---- B: closed form
    assert round(vpk(C_BUS, V_OVP_TOP, L_LINE, I0, VS, E_T_STALE), 1) == 451.6
    et_cases = {"stale E_t 0.475 J (ALT-D3, stage 13b)": E_T_STALE,
                "bank-ov 0.884 J (155.4 A, 73.15 uH)": 0.5 * bo.L_MAX * 155.4 ** 2}
    for lab, t in tank.items():
        et_cases[f"{lab}: max tank energy"] = t["max_E_tank_J"]
    closed = {}
    for lab, et in et_cases.items():
        v = vpk(C_BUS, V_OVP_TOP, L_LINE, I0, VS, et)
        closed[lab] = {"E_t_J": round(et, 4), "Vpk_V": round(v, 2), "rows": ratios(v)}
    out["closed_form_V0_287p62"] = closed
    # ---- C: OVP delay
    od = {lab: ovp_delay(tau) for lab, tau in TAU.items()}
    out["ovp_delay"] = od
    gov_key = f"s47 shunt top 119.09 A (bands-s47.md:24)"
    gov_e = tank[gov_key]["max_E_tank_J"]
    cm_key = next(k for k in tank if "Q1 HOT5" in k)
    stacked = {}
    for lab, d in od.items():
        for elab, et in (("E_t 0.475 J (stale)", E_T_STALE), ("E_t at the CT top 76.09 A", tank[next(iter(tank))]["max_E_tank_J"]),
                         ("E_t at 119.09 A", gov_e),
                         ("E_t at the CMRR top", tank[cm_key]["max_E_tank_J"])):
            v_coh = vpk(C_BUS, d["V0_gate_off_V"], L_LINE, d["I0_gate_off_A"], VS, et)
            v_naive = vpk(C_BUS, V_OVP_TOP + d["naive_constant_30A_V"], L_LINE, I0, VS, et)
            stacked[f"{lab} | {elab}"] = {"E_t_J": round(et, 4), "coherent_ring_Vpk_V": round(v_coh, 2),
                                          "naive_plus_constant_30A_Vpk_V": round(v_naive, 2),
                                          "rows_coherent": ratios(v_coh)}
    out["stacked_with_ovp_delay"] = stacked
    # ---- D: time-domain event, with and without the clamp, from the governing tank states
    td = {}
    v0_delay = od["max (R +1 % / +0.1 %, C27 +5 %)"]["V0_gate_off_V"]
    i0_delay = od["max (R +1 % / +0.1 %, C27 +5 %)"]["I0_gate_off_A"]
    for slab, st in (("max-E run at 119.09 A", tank[gov_key]["max_E_run"]),
                     ("max-E run at the CMRR top", tank[cm_key]["max_E_run"])):
        for v0lab, v0, i0 in (("V0 287.62 V, I0 30 A", V_OVP_TOP, I0),
                              (f"V0 {v0_delay} V, I0 {i0_delay} A (OVP delay)", v0_delay, i0_delay)):
            for clab, cl in CLAMP.items():
                r = event(st, cl, v0, i0)
                key = f"{slab} | {v0lab} | clamp {clab}"
                if cl is not None and r["clamp_I_peak_A"] > 0:
                    p_pk = r["clamp_I_peak_A"] * min(VC_MAX, r["Vbus_peak_V"])
                    tdur = max(r.get("clamp_t_above_half_peak_us", 1.0), 1.0)
                    rating = fig4_ppk_kw(tdur) * 1e3
                    r["pulse_check"] = {"P_peak_W_upper": round(p_pk / 2, 1), "per": "device (string of 2)",
                                        "td_us_to_half": tdur, "Fig4_Ppk_W": round(rating, 0),
                                        "Fig1_derate_at_73C": round(1 - (73 - 25) / 150, 3),
                                        "ratio_exp_pulse": round(p_pk / 2 / (rating * (1 - (73 - 25) / 150)), 4),
                                        "ratio_rect_0p66": round(p_pk / 2 / (0.66 * rating * (1 - (73 - 25) / 150)), 4),
                                        "energy_per_device_J": round(r["clamp_energy_J"] / 2, 4)}
                    r["published_bound_applies"] = r["clamp_I_peak_A"] <= IPP
                r["rows"] = ratios(min(r["Vbus_peak_V"], 1e9))
                td[key] = r
    out["time_domain_event"] = td
    out["clamp_bound_published_25C"] = {"Vc_max_string_V": VC_MAX, "at_I_A": IPP, "rows": ratios(VC_MAX),
                                        "hot_assumed_+0.1%/K_at_73C_V": round(VC_MAX * (1 + 0.001 * 48), 1),
                                        "rows_hot": ratios(VC_MAX * (1 + 0.001 * 48))}
    OUT.mkdir(exist_ok=True)
    (OUT / "bus_event.json").write_text(json.dumps(out, indent=1) + "\n")
    # ---- md
    L = ["## A. Tank state at gate-off (bank-ov grid; buses 198 / 280 / 287.62 / 323.04 V)\n",
         "| trip level | runs | max I_off (A) | 1/2 L_max I_off^2 (J) | max tank energy 1/2 L i^2 + 1/2 C v^2 (J) | run |",
         "|---|---:|---:|---:|---:|---|"]
    L.append(f"| control 118.74 A, 198/280 V | | {out['control_118p74A_198_280V']['max_I_off_A']} | "
             f"{out['control_118p74A_198_280V']['E_coil_Lmax_at_max_I_J']} | {out['control_118p74A_198_280V']['max_E_tank_J']} | |")
    for lab, t in tank.items():
        r = t["max_E_run"]
        L.append(f"| {lab} | {t['runs']} | {t['max_I_off_A']} | {t['E_coil_Lmax_at_max_I_J']} | {t['max_E_tank_J']} | "
                 f"{r['corner']}, R {r['R']}, bus {r['bus']}, {r['f_hz']} Hz, i {r['I_off']:.1f} A, v_C {r['V_off']:.0f} V |")
    L += ["\n## B. Closed form, V0 287.62 V, 500 uH / 30 A, C 14.9 uF, no clamp\n",
          "| E_t basis | E_t (J) | Vpk (V) | C12 fam. /1000 (0.5) | C5C6 /750 (0.8) | C5C6 hot /570 (0.8) | C38-41 hot /687.5 (0.8) | BR1 /1000 (0.8) | 2EDR /1767 (0.5) | R3R4 V/2 /400 (1.0) |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]

    def rowtxt(rows):
        sel = [rows[0], rows[1], rows[2], rows[4], rows[5], rows[6], rows[7]]
        return " | ".join(f"{x['ratio']:.3f}{'' if x['pass'] else ' **X**'}" for x in sel)
    for lab, c in closed.items():
        L.append(f"| {lab} | {c['E_t_J']} | {c['Vpk_V']} | {rowtxt(c['rows'])} |")
    L += ["\n## C. OVP delay (line ring through the U7 filter, gate-off T_D after the filtered crossing)\n",
          "| tau | lag (us) | V0' (V) | I0' (A) | overshoot (V) | naive 30 A x t (V) | ring peak alone (V) |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for lab, d in od.items():
        L.append(f"| {lab} ({d['tau_us']} us) | {d['filter_lag_us']} | {d['V0_gate_off_V']} | {d['I0_gate_off_A']} | "
                 f"{d['overshoot_V']} | {d['naive_constant_30A_V']} | {d['ring_peak_no_tank_V']} |")
    L += ["\n| stacked case | E_t (J) | coherent Vpk (V) | naive Vpk (V) | ratios (coherent) |", "|---|---:|---:|---:|---|"]
    for lab, s in stacked.items():
        L.append(f"| {lab} | {s['E_t_J']} | {s['coherent_ring_Vpk_V']} | {s['naive_plus_constant_30A_Vpk_V']} | "
                 f"{rowtxt(s['rows_coherent'])} |")
    L += ["\n## D. Time-domain gate-off event (clamp V-I lines are assumptions; see docstring)\n",
          "| case | Vbus pk (V) | clamp I pk (A) | clamp E (J) | t>half (us) | pulse ratio exp / rect (per device) | ratios |",
          "|---|---:|---:|---:|---:|---|---|"]
    for lab, r in td.items():
        pc = r.get("pulse_check", {})
        L.append(f"| {lab} | {r['Vbus_peak_V']} | {r['clamp_I_peak_A']} | {r['clamp_energy_J']} | "
                 f"{r.get('clamp_t_above_half_peak_us', '')} | {pc.get('ratio_exp_pulse', '')} / {pc.get('ratio_rect_0p66', '')} | "
                 f"{rowtxt(r['rows'])} |")
    L.append(f"\nPublished clamp bound (VC <= 466.8 V for I <= 129.8 A, 25 C): {rowtxt(out['clamp_bound_published_25C']['rows'])}; "
             f"hot (+0.1 %/K assumed, 73 C) {out['clamp_bound_published_25C']['hot_assumed_+0.1%/K_at_73C_V']} V: "
             f"{rowtxt(out['clamp_bound_published_25C']['rows_hot'])}")
    (OUT / "bus_event.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
