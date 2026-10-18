#!/usr/bin/env python3
"""Bench heatsink r1: clamp force, per-device Tj and sink temperature at the 17.5 / 22 / 28 A tank ceilings.

    python3 -I scripts/bench_thermal.py          (from bench-sink-r1/)  -> results/thermal.json, results/thermal.md

Losses are not re-derived here. They come from the committed device study
(validation-results/01-switching-parasitics/device-study-2026-10-15/scripts/thermal.py, imported read-only):
  * conduction  I_t^2 / 2 x RDS(on)(Tj), RDS max 18 mOhm at 25 C, x2.2 at 150 C (its rds());
  * basis D     ZVS switching / dead-time heat from the as-built deck's energy grid (its p_switch_leg(), phi 60 deg),
                interpolated in Tj between the 100 and 150 C grids;
  * basis A     D-18's hard-switching proxy (12.76 / 13.15 W per FET at 36 kHz, scaled with f): the LOST-ZVS fault case.
I_t = 1.05 x ceiling (the half-cycle RMS trip, as fet_case.py; 29.4 A at 28 A). Bus = 132 V AC peak (bench maximum).
BR1 = 2 x 1.05 V x 0.9 x I_line with I_line = 13.5 A (b3/run_study.py I_LINE_A, the firmware inlet bound), as stack_calc.py.

Sink: Wakefield 511-3M, 0.90 C/W natural convection at a 50 C rise (catalogue). Below a 50 C rise the natural-convection
resistance is scaled by (50 / rise)^0.25 (EST, laminar natural-convection h ~ dT^0.25); above it the catalogue value is kept.
A fan is NOT credited anywhere: the bench measures R_SA with its fan (README section 7).
Spreading in the 5.6 mm base: Lee, Song, Au & Moran (1995) average-temperature form, source = tab (or BR1) area,
plate = that device's share of the base (EST model).
Interface: Bergquist SIL PAD thermal impedance at the clamp pressure (log-linear interpolation of the catalogue rows),
divided by the tab area (151.2-240.1 mm2). The strip runs behind BR1 too, over a greased shim.

JLC-soldered devices (owner decision 2026-10-18; bench_tolerance.py): each FET sits on a selected shim under the strip.
Every FET is modelled with the thickest design shim (SHIM_MAX_DESIGN, brass, SHIM_LAYERS_MAX greased faces at the
conservative grease value) and at the worst pressure corner: both tab areas against both the lowest strip force the
tolerance tool guarantees (45 N, after straightening the worst accepted lean) and the zero-shim highest force.
This bounds every device; the most-proud device (no shim, no lean) is better.
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
POWER = HERE.parents[3]          # zapote/power-stage-120v
sys.path.insert(0, str(HERE))
import bench_params as P  # noqa: E402

DEV = POWER / "validation-results/01-switching-parasitics/device-study-2026-10-15/scripts/thermal.py"
RUN_STUDY = POWER / "validation-results/04-board-current-thermal/round5-native21/b3/run_study.py"

_spec = importlib.util.spec_from_file_location("device_thermal", DEV)
DT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DT)
# controls: the imported model is the one the repo cites
assert DT.DEVICES["IPW65R018CFD7"]["rds_max25"] == 0.018 and DT.DEVICES["IPW65R018CFD7"]["r150_over_r25"] == 2.2
assert DT.DEVICES["IPW65R018CFD7"]["rjc"] == P.RTH_JC_FET
assert DT.D18_SW_36K == {"Q2": 12.7574, "Q5": 12.7574, "Q3": 13.1537, "Q6": 13.1537}
I_LINE_A = float(re.search(r"^I_LINE_A = ([0-9.]+)", RUN_STUDY.read_text(), re.M).group(1))
assert I_LINE_A == 13.5
GRID = DT.load_energy("IPW65R018CFD7_L1")
assert GRID is not None, "device-study energy grid missing"

IN2 = 645.16
PSI = 6894.757
CEILINGS = (17.5, 22.0, 28.0)
FREQS = (35e3, 50e3, 60e3)       # the per-pan loop starts at F_MAX 60 kHz and settles lower (COMMISSIONING 9a)
AMBIENTS = (30.0, 40.0)          # stated bench ambient 30 C; 40 C sensitivity
V_PK = P.V_LINE_MAX_RMS * math.sqrt(2)


def i_tank(ceil):
    return 29.4 if ceil == 28.0 else 1.05 * ceil


def p_br1():
    return 2 * 1.05 * 0.9 * I_LINE_A


def interp_z(table, psi):
    """log-log interpolation of thermal impedance vs pressure, clamped to the catalogue range."""
    ks = sorted(table)
    psi = min(max(psi, ks[0]), ks[-1])
    for a, b in zip(ks, ks[1:]):
        if a <= psi <= b:
            f = (math.log(psi) - math.log(a)) / (math.log(b) - math.log(a))
            return math.exp(math.log(table[a]) + f * (math.log(table[b]) - math.log(table[a])))
    return table[ks[-1]]


# ------------------------------------------------------------------------------------------------ clamp
def clamp(pad):
    """Spring force per TO-247 over the body-thickness and FR-4 tolerance corners."""
    y_face = P.Y_TAB - P.PADS[pad]["t"]
    y_bar = y_face + P.SPACER_L
    rows = []
    for a in (P.TO247["A"][0], sum(P.TO247["A"]) / 2, P.TO247["A"][1]):
        for t4 in (P.FR4_T[0], sum(P.FR4_T) / 2, P.FR4_T[1]):
            lc = y_bar + P.POCKET_DEPTH - (P.Y_TAB + a + t4)
            f = P.SPRING["k"] * (P.SPRING["L0"] - lc)
            rows.append(dict(A=a, fr4=t4, L_c=round(lc, 3), F_N=round(f, 1), solid_margin=round(lc - P.SPRING["Ls"], 2)))
    fs = [r["F_N"] for r in rows]
    # bar bending: simply supported between the two end screws, the four spring loads at nominal force
    xa, xb = P.BAR_SCREW_X
    span = xb - xa
    f_nom = [r for r in rows if r["A"] == sum(P.TO247["A"]) / 2 and r["fr4"] == sum(P.FR4_T) / 2][0]["F_N"]
    i_bar = P.BAR["h"] * P.BAR["t"] ** 3 / 12
    defl = {}
    for xq in P.FET_X.values():           # deflection at each spring by superposition of point loads
        d = 0.0
        for xp in P.FET_X.values():
            a, b = xp - xa, xb - xp
            x = xq - xa
            if x <= a:
                d += f_nom * b * x * (span ** 2 - b ** 2 - x ** 2) / (6 * span * P.E_6061 * i_bar)
            else:
                d += f_nom * a * (span - x) * (span ** 2 - a ** 2 - (span - x) ** 2) / (6 * span * P.E_6061 * i_bar)
        defl[round(xq, 2)] = d
    dmax = max(defl.values())
    r_left = sum(f_nom * (xb - x) / span for x in P.FET_X.values())
    return dict(rows=rows, F_min=min(fs), F_max=max(fs), F_nom=f_nom,
                within_acceptance=P.CLAMP_ACCEPT_N[0] <= min(fs) and max(fs) <= P.CLAMP_ACCEPT_N[1],
                meets_60N=min(fs) >= P.CLAMP_TARGET_MIN_N, solid_margin_min=min(r["solid_margin"] for r in rows),
                bar_deflection_max_mm=round(dmax, 4), force_loss_from_deflection_N=round(P.SPRING["k"] * dmax, 2),
                screw_loads_N=(round(r_left, 1), round(4 * f_nom - r_left, 1)),
                bar_back_y=round(y_bar + P.BAR["t"], 3), film_row_courtyard_y=round(P.Y_FILM_COURTYARD_FRONT, 3),
                bar_to_film_courtyard_mm=round(P.Y_FILM_COURTYARD_FRONT - (y_bar + P.BAR["t"]), 3))


# ------------------------------------------------------------------------------------------------ resistances
def r_interface(pad, force_n, area_mm2):
    psi = force_n / (area_mm2 * 1e-6) / PSI
    z = interp_z(P.PADS[pad]["z"], psi)
    return z * IN2 / area_mm2, psi


def r_spread(src_mm2, share_mm2, rsa_share):
    """Lee et al. (1995): average-temperature spreading resistance of a circular source on a finite plate (EST)."""
    k = P.K_6063 * 1e-3            # W/mm K
    a = math.sqrt(src_mm2 / math.pi)
    b = math.sqrt(share_mm2 / math.pi)
    h = 1.0 / (rsa_share * share_mm2)  # W/mm2 K from the share of R_SA
    eps, tau, bi = a / b, P.SINK_BASE_T / b, h * b / k
    lam = math.pi + 1.0 / (eps * math.sqrt(math.pi))
    phi = (math.tanh(lam * tau) + lam / bi) / (1 + (lam / bi) * math.tanh(lam * tau))
    return (1 - eps) ** 1.5 * phi / (2 * math.sqrt(math.pi) * k * a)


def rsa_nat(rise):
    return P.RSA_NAT * (P.RSA_NAT_RISE / rise) ** 0.25 if 0 < rise < P.RSA_NAT_RISE else P.RSA_NAT


def shim_stack(area_mm2, t_mm=None):
    """Selected shim under the strip: bulk (brass bound) + SHIM_LAYERS_MAX greased faces (conservative grease)."""
    t_mm = P.SHIM_MAX_DESIGN if t_mm is None else t_mm
    bulk = t_mm * 1e-3 / (P.K_SHIM_FET * area_mm2 * 1e-6)
    grease = P.SHIM_LAYERS_MAX * P.GREASE_CM2[1] / (area_mm2 / 100)
    return bulk + grease, dict(bulk=bulk, grease=grease)


def br1_stack(pad):
    """BR1 case -> sink: strip (at 50 psi: one central M3 screw on a plastic body, EST) + selected shim stack."""
    a = P.BR1_AREA
    z = P.PADS[pad]["z"][50]
    r_pad = z * IN2 / a
    r_sh, parts = shim_stack(P.SHIM_SIZE[0] * P.SHIM_SIZE[1])
    return r_pad + r_sh, dict(pad=r_pad, shim=parts["bulk"], grease_cons=parts["grease"])


# ------------------------------------------------------------------------------------------------ solve
_SW = {}


def p_sw(leg, temp, it, f):
    """Per-device ZVS switching heat from the device study's energy grid (cached: it does not depend on the solve)."""
    key = (leg, temp, it, f)
    if key not in _SW:
        _SW[key] = DT.p_switch_leg(GRID, leg, temp, V_PK, it, f) / 2
    return _SW[key]


def p_fet(ref, tj, ceil, f, basis):
    it = i_tank(ceil)
    cond = it * it / 2 * DT.rds("IPW65R018CFD7", tj)
    if basis == "A":
        return cond + DT.D18_SW_36K[ref] * f / 36000
    leg = P.FET_LEG[ref]
    a = p_sw(leg, 100, it, f)
    b = p_sw(leg, 150, it, f)
    x = min(max((tj - 100) / 50, 0), 1)
    return cond + a + (b - a) * x


CORNERS = [(a, fc) for a in ("small", "large") for fc in ("low", "high")]


def corner(pad, area_case, force_case):
    """(area, force) of a pressure corner: tab area 151.2 / 240.1 mm2; force 45 N (JLC-fit floor) / zero-shim maximum."""
    cl = clamp(pad)
    area = P.TAB_AREA[0] if area_case == "small" else P.TAB_AREA[1]
    force = P.CLAMP_ACCEPT_N[0] if force_case == "low" else cl["F_max"]
    return area, force


def solve(pad, ceil, f, basis, t_amb, area_case, rsa_fixed=None, force_case="low"):
    area, force = corner(pad, area_case, force_case)
    rcs, psi = r_interface(pad, force, area)
    rcs += shim_stack(area)[0]
    rbr1, _ = br1_stack(pad)
    pbr1 = p_br1()
    tj = {r: t_amb + 30 for r in P.FET_X}
    ts = t_amb + 30
    for _ in range(500):
        pw = {r: p_fet(r, tj[r], ceil, f, basis) for r in P.FET_X}
        ptot = sum(pw.values()) + pbr1
        rsa = rsa_fixed if rsa_fixed else rsa_nat(max(ts - t_amb, 1e-3))
        ts_new = t_amb + rsa * ptot
        base_area = P.SINK_WIDTH * P.SINK_LEN
        rsp_fet = r_spread(area, 18.0 * P.SINK_LEN, rsa * base_area / (18.0 * P.SINK_LEN))
        rsp_br1 = r_spread(P.BR1_AREA, 30.0 * P.SINK_LEN, rsa * base_area / (30.0 * P.SINK_LEN))
        new = {r: ts_new + pw[r] * (rsp_fet + rcs + P.RTH_JC_FET) for r in P.FET_X}
        d = max(abs(new[r] - tj[r]) for r in tj) + abs(ts_new - ts)
        tj, ts = new, ts_new
        if max(tj.values()) > 400:
            return None
        if d < 1e-9:
            break
    tc_br1 = ts + pbr1 * (rsp_br1 + rbr1)
    return dict(ts=ts, rsa=rsa, ptot=ptot, p=pw, p_br1=pbr1, tj=tj, rcs=rcs, psi=psi, rsp_fet=rsp_fet,
                tcase={r: ts + pw[r] * (rsp_fet + rcs) for r in P.FET_X},
                tj_br1=tc_br1 + pbr1 / 4 * P.RTH_JC_BR1_ELEM, tc_br1=tc_br1)


def tj_at_sink(pad, ceil, f, basis, t_sink, area_case="small", force_case="low"):
    """Junction temperature with the sink held at a trip temperature (what the sink-sensed trips protect)."""
    area, force = corner(pad, area_case, force_case)
    rcs, _ = r_interface(pad, force, area)
    rcs += shim_stack(area)[0]
    rsp = r_spread(area, 18.0 * P.SINK_LEN, P.RSA_NAT * P.SINK_WIDTH / 18.0)
    tj = {r: t_sink + 20 for r in P.FET_X}
    for _ in range(200):
        tj = {r: t_sink + p_fet(r, tj[r], ceil, f, basis) * (rsp + rcs + P.RTH_JC_FET) for r in P.FET_X}
    return max(tj.values())


def main():
    out = {"inputs": {"I_line_A": I_LINE_A, "V_pk": V_PK, "ceilings": CEILINGS, "freqs_Hz": FREQS, "ambients_C": AMBIENTS,
                      "sink": P.SINK_PN, "RSA_nat": P.RSA_NAT, "pad_choice": P.PAD_CHOICE},
           "clamp": {}, "pads": {}, "trip_ladder": {}, "fan_requirement": {}}
    md = ["# Bench sink r1: thermal results (generated by scripts/bench_thermal.py; do not edit)", ""]
    for pad in P.PADS:
        out["clamp"][pad] = clamp(pad)
    cl = out["clamp"][P.PAD_CHOICE]
    md += [f"## Clamp ({P.SPRING['pn']}, {P.SPACER_L} mm spacers, {P.POCKET_DEPTH} mm pockets, strip {P.PAD_CHOICE})", "",
           f"Force per TO-247 over A 4.70-5.30 mm x FR-4 1.44-1.76 mm: **{cl['F_min']}-{cl['F_max']} N** (nominal {cl['F_nom']} N); "
           f"acceptance 45-102 N: {cl['within_acceptance']}; >= 60 N: {cl['meets_60N']}; spring solid-height margin >= "
           f"{cl['solid_margin_min']} mm. Bar deflection {cl['bar_deflection_max_mm']} mm (-{cl['force_loss_from_deflection_N']} N). "
           f"End-screw loads {cl['screw_loads_N']} N. Bar back face y {cl['bar_back_y']} vs film-row courtyard {cl['film_row_courtyard_y']} "
           f"({cl['bar_to_film_courtyard_mm']} mm).", ""]
    rbr1, rbr1_parts = br1_stack(P.PAD_CHOICE)
    out["br1_stack_C_per_W"] = dict(total=rbr1, **rbr1_parts)
    hdr = "| strip | ceiling A | basis | f kHz | ambient C | sink C | R_SA | P_FET max W | P_sink W | Rcs + shim (corner) | Tj FET max C | Tcase max C | Tj BR1 C | Rcs <= 0.7 (D-36) |"
    md += ["## Steady state, natural convection (no fan credited)", "", hdr, "|" + "---|" * 14]
    for pad in P.PADS:
        rows = []
        for ceil in CEILINGS:
            for basis in ("D", "A"):
                for t_amb in AMBIENTS:
                    worst = None
                    for f in FREQS:
                        for ac, fc in CORNERS:
                            r = solve(pad, ceil, f, basis, t_amb, ac, force_case=fc)
                            if r is None:
                                cand = dict(runaway=True, f=f, area=ac + "/" + fc)
                            else:
                                cand = dict(f=f, area=ac + "/" + fc, ts=r["ts"], rsa=r["rsa"], pmax=max(r["p"].values()), ptot=r["ptot"],
                                            rcs=r["rcs"], psi=r["psi"], rsp=r["rsp_fet"], tj=max(r["tj"].values()),
                                            tc=max(r["tcase"].values()), tj_br1=r["tj_br1"],
                                            tj_each={k: round(v, 1) for k, v in r["tj"].items()},
                                            p_each={k: round(v, 2) for k, v in r["p"].items()})
                            key = 1e9 if cand.get("runaway") else cand["tj"]
                            if worst is None or key > (1e9 if worst.get("runaway") else worst["tj"]):
                                worst = cand
                    rows.append(dict(ceil=ceil, basis=basis, t_amb=t_amb, **worst))
                    if worst.get("runaway"):
                        md.append(f"| {pad} | {ceil} | {basis} | {worst['f']/1e3:.0f} | {t_amb:.0f} | runaway | | | | | | | | |")
                    else:
                        md.append(f"| {pad} | {ceil} | {basis} | {worst['f']/1e3:.0f} | {t_amb:.0f} | {worst['ts']:.1f} | "
                                  f"{worst['rsa']:.3f} | {worst['pmax']:.2f} | {worst['ptot']:.1f} | {worst['rcs']:.3f} ({worst['area']}, "
                                  f"{worst['psi']:.0f} psi) | **{worst['tj']:.1f}** | {worst['tc']:.1f} | {worst['tj_br1']:.1f} | "
                                  f"{worst['rcs'] <= 0.7} |")
        # interface range over both tab corners (for the D-36 line)
        rc = [r_interface(pad, corner(pad, a, fc)[1], corner(pad, a, fc)[0])[0] for a, fc in CORNERS]
        out["pads"][pad] = dict(rows=rows, rcs_range=[min(rc), max(rc)], d36_pass_all=max(rc) <= 0.7)
    md += ["", "Basis D = ZVS operation (deck energy grid). Basis A = D-18 hard-switching proxy = **lost-ZVS fault**, not an operating point.", ""]
    # trip ladder: Tj when the sink sits at each sink-sensed trip
    md += ["## Junction at the sink-sensed trips (sink held at the trip; worst FET, worst pressure corner, design shim)", "",
           "| strip | ceiling A | basis | sink 86 (TCO Th) | sink 95 (firmware) | sink 104.6 (HW band top) | sink 110 (TCO Tf) |",
           "|---|---|---|---|---|---|---|"]
    for pad in P.PADS:
        out["trip_ladder"][pad] = {}
        for ceil in CEILINGS:
            for basis in ("D", "A"):
                vals = [max(tj_at_sink(pad, ceil, f, basis, ts, a, fc) for f in FREQS for a, fc in CORNERS) for ts in (86.0, P.FW_TRIP_C, P.HW_TRIP_BAND_C[1], P.TCO["Tf"])]
                out["trip_ladder"][pad][f"{ceil}|{basis}"] = vals
                md.append(f"| {pad} | {ceil} | {basis} | " + " | ".join(f"{v:.1f}" for v in vals) + " |")
    # fan requirement: R_SA that keeps the sink <= 80 C (6 K under the TCO holding temperature) at 30 / 40 C ambient
    md += ["", "## Forced-air requirement (sink <= 80 C, 6 K under the DF110S holding temperature 86 C), basis D", "",
           "| ceiling A | P_sink W | R_SA needed at 30 C | at 40 C | natural 511-3M (0.90) enough at 30 C? |", "|---|---|---|---|---|"]
    for ceil in CEILINGS:
        need = {}
        for t_amb in (30.0, 40.0):
            lo, hi = 0.01, 3.0          # bisection on R_SA so that the self-consistent sink sits at 80 C
            for _ in range(60):
                mid = (lo + hi) / 2
                r = solve(P.PAD_CHOICE, ceil, 60e3, "D", t_amb, "small", rsa_fixed=mid, force_case="low")
                lo, hi = (mid, hi) if r and r["ts"] < 80.0 else (lo, mid)
            need[t_amb] = (lo, r["ptot"])
        out["fan_requirement"][str(ceil)] = dict(P_sink=need[30.0][1], RSA_need_30=need[30.0][0], RSA_need_40=need[40.0][0])
        md.append(f"| {ceil} | {need[30.0][1]:.1f} | {need[30.0][0]:.3f} | {need[40.0][0]:.3f} | {P.RSA_NAT <= need[30.0][0]} |")
    md += ["", f"BR1 stack (strip at 50 psi + {P.SHIM_MAX_DESIGN} mm design shim, {P.SHIM_LAYERS_MAX} greased faces, conservative grease): {rbr1:.3f} C/W "
           f"(strip {rbr1_parts['pad']:.3f}, shim {rbr1_parts['shim']:.4f}, grease {rbr1_parts['grease_cons']:.3f}); "
           f"P_BR1 {p_br1():.2f} W at {I_LINE_A} A line.", ""]
    md += ["## Interface range per strip over the four pressure corners (D-36 budget <= 0.7 C/W per FET)", "",
           "| strip | Rcs strip only C/W | + design shim stack C/W (small / large tab) | all corners <= 0.7 |", "|---|---|---|---|"]
    for pad, d in out["pads"].items():
        md.append(f"| {pad} | {d['rcs_range'][0]:.3f}-{d['rcs_range'][1]:.3f} | +{shim_stack(P.TAB_AREA[0])[0]:.3f} / "
                  f"+{shim_stack(P.TAB_AREA[1])[0]:.3f} | {d['d36_pass_all']} |")
    out["shim_stack_C_per_W"] = dict(small=shim_stack(P.TAB_AREA[0]), large=shim_stack(P.TAB_AREA[1]))
    (STUDY / "results").mkdir(exist_ok=True)
    (STUDY / "results" / "thermal.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    (STUDY / "results" / "thermal.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
