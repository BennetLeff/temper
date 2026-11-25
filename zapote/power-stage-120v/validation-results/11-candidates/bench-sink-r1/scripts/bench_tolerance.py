#!/usr/bin/env python3
"""Bench heatsink r1: tab-plane tolerance stack of JLC-soldered TO-247s, and whether the strip + spring clamp closes them.

    python3 -I scripts/bench_tolerance.py        (from bench-sink-r1/)  -> results/tolerance.json, results/tolerance.md

Owner decision 2026-10-18: JLC solders Q2/Q3/Q5/Q6 (wave line, hand-inserted: [JLC]); the sink, strip and clamp are fitted
to the soldered devices afterwards. A soldered device can no longer move to the sink. The tab plane of each device at the
board line (y, at z = Z_PIVOT) is offset from the footprint by
  * hole position              +/- HOLE_POS_TOL                    [JLC]
  * lead free in its hole      +/- (D_fin - c) / 2                  D_fin = 1.8 drill (stage 57) -0.08/+0.13 [JLC], c [IPW]
  * package A1 (back -> leads) +/- 0.20 datasheet, +/- A1_LOT_TOL within one lot (EST)               [IPW]
and leans by
  * board bow / twist          IPC 0.75 % of the diagonal as quoted by [JLCB] (common lean + a small differential)
  * assembly lean              not specified by JLC (no published THT seating or tilt rule was found): an inspection limit.
What can absorb a device's offset once soldered: the strip's compliance (EST) + the leads' elastic translation (bench_mech).
What absorbs lean: the clamp rotates the device about its leads, up to the leads' elastic lean (bench_mech).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(HERE))
import bench_params as P  # noqa: E402
import bench_mech as M  # noqa: E402
import bench_thermal as BT  # noqa: E402

T = P.TO247
K = P.SPRING["k"]


def spreads():
    play = M.lead_play()
    a1_ds = (T["A1"][1] - T["A1"][0]) / 2
    # U: leads anywhere in their holes (no remark, or the remark not honoured)
    u_lot = 2 * (P.HOLE_POS_TOL + play[1] + P.A1_LOT_TOL)
    u_ds = 2 * (P.HOLE_POS_TOL + play[1] + a1_ds)
    # R: remark honoured, every lead bears on the edge-side wall of its hole: only position, local diameter and A1 remain
    r_lot = 2 * (P.HOLE_POS_TOL + P.HOLE_DIA_LOCAL_TOL / 2 + P.A1_LOT_TOL)
    r_ds = 2 * (P.HOLE_POS_TOL + P.HOLE_DIA_LOCAL_TOL / 2 + a1_ds)
    return dict(play=play, U_lot=u_lot, U_datasheet=u_ds, R_lot=r_lot, R_datasheet=r_ds)


def lean_terms():
    diag = math.hypot(*P.BOARD_XY)
    dev = P.BOW_TWIST * diag
    common = 4 * dev / P.BOARD_XY[1]                     # bow across y as an arc: slope at the rear edge
    span = max(P.FET_X.values()) - min(P.FET_X.values())
    diff = dev * span / (P.BOARD_XY[0] * P.BOARD_XY[1])   # twist z = d x y / (Lx Ly): slope change along the row
    return dict(deviation_mm=dev, common_rad=common, differential_rad=diff, row_span_mm=span)


def lean_limit(cl, mech, ln):
    """Lean the clamp may straighten: the leads' elastic limit, and the force it costs must leave >= 45 N on the strip of
    a device set at the 60 N target (bar deflection included). The row's twist differential comes off the inspection limit."""
    theta_force = (P.CLAMP_TARGET_MIN_N - P.CLAMP_ACCEPT_N[0] - cl["force_loss_from_deflection_N"]) * mech["lever_mm"] / mech["k_rot_max"]
    theta_dev = min(mech["theta_el_rad"], theta_force)
    return theta_dev - ln["differential_rad"], theta_force, theta_dev, mech["k_rot_max"] * theta_dev / mech["lever_mm"]


def gauge_z():
    """Feeler-gauge heights on the package back: 2 mm inside the body at the worst seated outline."""
    return T["L1"][1] + 2.0, T["L1"][0] + T["D"][0] - 2.0


def pad_windows(cl):
    """Shim range each FR-4 pad option keeps inside 60-102 N (target) and off solid, at the shimmed device."""
    out = {}
    opts = {"FR-4 1.6": (0.0, 0.0), "FR-4 0.8": (P.FR4_T[0] - P.FR4_THIN_T[1], P.FR4_T[1] - P.FR4_THIN_T[0]),
            "no pad": (P.FR4_T[0], P.FR4_T[1])}
    for name, (dlo, dhi) in opts.items():
        f_lo, f_hi = cl["F_min"] - K * dhi, cl["F_max"] - K * dlo
        s_lo = max(0.0, (P.CLAMP_TARGET_MIN_N - f_lo) / K)
        s_hi = min((P.CLAMP_ACCEPT_N[1] - f_hi) / K, cl["solid_margin_min"] + dlo)
        out[name] = dict(shim_from=round(s_lo, 3), shim_to=round(s_hi, 3), F_at_from=(round(f_lo + K * s_lo, 1), round(f_hi + K * s_lo, 1)))
    return out


def covered(windows, top):
    """Is [0, top] covered by the union of the pad windows?"""
    x = 0.0
    for w in sorted(windows.values(), key=lambda w: w["shim_from"]):
        if w["shim_from"] <= x + 1e-9 < w["shim_to"]:
            x = max(x, w["shim_to"])
    return x >= top, x


def main():
    cl = BT.clamp(P.PAD_CHOICE)
    mech = M.elastic_limits()
    sp = spreads()
    ln = lean_terms()
    budget = P.PAD_COMPLIANCE + mech["delta_el_mm"]
    rounding = P.SHIM_STEP / 2
    win = pad_windows(cl)
    cov_u, reach = covered(win, sp["U_datasheet"])
    theta_acc, theta_force, theta_dev, f_loss = lean_limit(cl, mech, ln)
    z_low, z_up = gauge_z()
    face = M.sink_face_range()
    bar_film = cl["bar_to_film_courtyard_mm"] - (face[2] - face[1])
    # BR1: its strip face must meet BR1's back within its lead play when BR1 is dry-fitted vertical
    play_br1 = ((P.BR1_DRILL_FIN[0] - P.GBJ["lead_t"][1]) / 2, (P.BR1_DRILL_FIN[1] - P.GBJ["lead_t"][0]) / 2)
    t = P.PADS[P.PAD_CHOICE]["t"]
    grease = P.GREASE_BLT
    br1_shim = (P.Y_BR1_BACK - (face[2] + grease + t), P.Y_BR1_BACK - (face[0] + grease + t))
    # a negative BR1 shim beyond its lead play is taken by leaning BR1 back about its holes (leads still unsoldered)
    excess = max(0.0, -br1_shim[0] - play_br1[0])
    br1_lean = excess / P.BR1_HOLE_Z
    br1_cap = math.atan((P.BR1_DRILL_FIN[0] - P.GBJ["lead_t"][1]) / P.BOARD_T)
    assert P.SHIM_MAX_DESIGN >= sp["U_datasheet"], "thermal model's shim must cover the worst spread"
    assert P.SHIM_MAX_DESIGN >= br1_shim[1]
    float_max = (P.STRIP_TOP_Z - P.STRIP_PLACE_TOL) - (T["L1"][1] + T["D"][1] - T["D2"][0]) + t - P.CREEPAGE_BASIC
    res = dict(spread=sp, lean=ln, mech=mech, budget_mm=budget, closes_without_shims=dict(
                   U=sp["U_lot"] <= budget, R=sp["R_lot"] <= budget),
               shim_rounding_mm=rounding, closes_with_shims=rounding <= budget, pad_windows=win,
               pad_options_cover_worst_spread=cov_u, pad_options_reach_mm=reach, theta_accept_rad=theta_acc,
               gauge_z=(z_low, z_up), sink_face_y=face, bar_to_film_min_mm=bar_film, br1_play=play_br1,
               br1_shim_range_mm=br1_shim, br1_lean_needed_rad=br1_lean, br1_lean_capacity_rad=br1_cap,
               br1_fits=br1_lean <= br1_cap,
               float_max_mm=float_max, clamp_base=dict(F_min=cl["F_min"], F_max=cl["F_max"]),
               theta_force_rad=theta_force, f_loss_N=f_loss,
               f_pad_min_after_lean_N=round(P.CLAMP_TARGET_MIN_N - f_loss - cl["force_loss_from_deflection_N"], 1))
    md = ["# Bench sink r1: tab-plane tolerance of JLC-soldered TO-247s (generated by scripts/bench_tolerance.py; do not edit)", "",
          "## 1. Offset of each tab plane at the board line (y)", "",
          "| term | value mm | source |", "|---|---|---|",
          f"| hole position | +/- {P.HOLE_POS_TOL} | [JLC] |",
          f"| finished hole, {P.FET_DRILL} drill | {M.hole_fin()[0]:.2f}-{M.hole_fin()[1]:.2f} | [JLC] {P.PTH_TOL} |",
          f"| lead thickness c | {T['c'][0]}-{T['c'][1]} | [IPW] p.12 |",
          f"| lead free in its hole, (D - c)/2 | +/- {sp['play'][0]:.3f} to +/- {sp['play'][1]:.3f} | from the two rows above |",
          f"| package A1 | +/- {(T['A1'][1] - T['A1'][0]) / 2:.2f} (datasheet), +/- {P.A1_LOT_TOL} within a lot (EST) | [IPW] p.12 |",
          f"| **one device, worst** | **+/- {M.tab_offset_bound():.3f}** | sum |", "",
          "Spread between the four devices (what a single flat sink face must meet):", "",
          "| case | spread mm (lot A1) | spread mm (datasheet A1) |", "|---|---|---|",
          f"| U: leads anywhere in their holes (no remark, or not honoured) | {sp['U_lot']:.3f} | {sp['U_datasheet']:.3f} |",
          f"| R: order remark honoured, leads against the edge-side hole walls | {sp['R_lot']:.3f} | {sp['R_datasheet']:.3f} |", "",
          "## 2. What can close a gap once the device is soldered", "",
          f"- Strip compliance: {P.PAD_COMPLIANCE} mm (EST: no catalogue compression data for SIL PAD 2000).",
          f"- Lead elastic translation at {P.SIGMA_LEAD_ALLOW:.0f} MPa (EST): {mech['delta_el_mm']:.4f} mm at the stiffest corner; "
          f"translation stiffness up to {mech['k_trans_max']:.0f} N/mm, so the clamp cannot move a soldered device.",
          f"- **Budget {budget:.4f} mm.** Without shims the spread is {sp['R_lot']:.3f}-{sp['U_datasheet']:.3f} mm: "
          f"closes? U {res['closes_without_shims']['U']}, R {res['closes_without_shims']['R']}. **The strip + clamp alone does not close every tab.**",
          f"- With a per-device shim selected in {P.SHIM_STEP} mm steps the residual is <= {rounding:.4f} mm: closes = **{res['closes_with_shims']}**.", "",
          "## 3. Lean", "",
          f"- Bow/twist {P.BOW_TWIST*100:.2f} % of the {math.hypot(*P.BOARD_XY):.1f} mm diagonal = {ln['deviation_mm']:.2f} mm: common lean up to "
          f"{ln['common_rad']:.4f} rad ({math.degrees(ln['common_rad']):.2f} deg; the floating sink tilts to it), differential across the "
          f"{ln['row_span_mm']:.1f} mm row {ln['differential_rad']:.5f} rad.",
          f"- Leads' elastic lean {mech['theta_el_rad']:.4f} rad ({math.degrees(mech['theta_el_rad']):.2f} deg). **Inspection limit per device, "
          f"relative to the row mean: {theta_acc:.4f} rad ({math.degrees(theta_acc):.2f} deg)**, i.e. a gap difference <= "
          f"{theta_acc * (z_up - z_low):.3f} mm between the gauge heights z {z_low:.2f} and {z_up:.2f}.",
          f"- The limit is the smaller of the elastic lean and the lean whose straightening moment ({mech['k_rot_max']:.0f} N mm/rad, "
          f"lever {mech['lever_mm']:.1f} mm, EST pivot at the board) still leaves a device set at the 60 N target >= 45 N on its strip: "
          f"{theta_force:.4f} rad. At that lean the clamp spends {f_loss:.1f} N and the strip sees >= {res['f_pad_min_after_lean_N']} N "
          f"(bar deflection included).", "",
          "## 4. Spring force at a shimmed device, per FR-4 pad option", "",
          f"Zero-shim device: {cl['F_min']}-{cl['F_max']} N (bench_thermal.py). A shim s moves the package front s closer to the bar: +{K:.2f} N/mm.", "",
          "| pad | shim range mm (60-102 N, off solid) | force at the range start N |", "|---|---|---|"]
    md += [f"| {k} | {w['shim_from']}-{w['shim_to']} | {w['F_at_from'][0]}-{w['F_at_from'][1]} |" for k, w in win.items()]
    md += ["", f"The options cover 0-{reach:.3f} mm; worst spread {sp['U_datasheet']:.3f} mm: covered = **{cov_u}**. "
           "The 'no pad' option puts the spring end on the package front (the FR-4 pad is credited for nothing; insulation.md).", "",
           "## 5. Sink, bar and BR1 positions", "",
           f"- Sink face y {face[0]:.3f} .. {face[2]:.3f} (nominal {face[1]:.3f}): the floating sink settles on the most-proud tab; "
           f"bracket slots must give at least +/- {M.tab_offset_bound():.2f} mm in y and +/- {math.degrees(ln['common_rad']):.1f} deg of tilt.",
           f"- Bar back face to the C38-C41 courtyard: >= {bar_film:.3f} mm at the deepest sink position.",
           f"- BR1 (fitted later by the owner, seated on the strip by its screw): lead play +/- {play_br1[0]:.3f}..{play_br1[1]:.3f} mm. "
           f"Shim behind the strip at BR1 {br1_shim[0]:.3f} .. {br1_shim[1]:.3f} mm. A positive value is selected at the BR1 dry fit; "
           f"a negative one is taken by the lead play and, beyond it, by leaning BR1 back {br1_lean:.4f} rad about its holes before "
           f"soldering (the 1.6 mm board allows {br1_cap:.3f} rad): fits = **{res['br1_fits']}**.",
           f"- Unseated body float allowed by the strip-top creepage: {float_max:.2f} mm (acceptance set at {P.FET_FLOAT_MAX} mm).", ""]
    (STUDY / "results").mkdir(exist_ok=True)
    (STUDY / "results" / "tolerance.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
    (STUDY / "results" / "tolerance.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0 if res["closes_with_shims"] and cov_u and res["br1_fits"] and res["f_pad_min_after_lean_N"] >= P.CLAMP_ACCEPT_N[0] else 1


if __name__ == "__main__":
    sys.exit(main())
