#!/usr/bin/env python3
"""Bench heatsink r1: one common sink + selected shims (revision 2) against one sink per device, and against a thick soft
gap pad on the common sink. Coordinator request 2026-10-18: least hand work at the bench, same limits.

    python3 -I scripts/compare_mounts.py         (from bench-sink-r1/)  -> results/compare.md, results/compare.json

Limits (as for the common sink): Tj <= 125 C target / 150 C rating; the sink carrying the TCO <= 80 C (DF110S Th 86 - 6);
firmware 95 C < hardware 98.3-104.6 C < TCO 105-110 C on that same sink. Ambient 30 C, ZVS loss basis D (bench_thermal).
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
import bench_tolerance as TOL  # noqa: E402

T = P.TO247
T_AMB = 30.0
IN2_M2 = 6.4516e-4


def fet_alone(r_sa, ceil, rcs, f=60e3):
    """One FET on its own sink: worst of the four legs, Tj iterated with the device study's losses."""
    worst = None
    for ref in P.FET_X:
        tj = T_AMB + 40
        for _ in range(300):
            p = BT.p_fet(ref, tj, ceil, f, "D")
            ts = T_AMB + p * r_sa
            tj_new = ts + p * (rcs + P.RTH_JC_FET)
            if tj_new > 400:
                return dict(runaway=True)
            if abs(tj_new - tj) < 1e-9:
                break
            tj = tj_new
        r = dict(ref=ref, p=p, ts=ts, tj=tj)
        if worst is None or r["tj"] > worst["tj"]:
            worst = r
    return worst


def per_device():
    lo_w, hi_w = T["E1"][1], min(18.0, 50.05 - 27.95) - P.SINK_GAP_MIN   # cover the tab metal; fit the 18 mm pitch
    rcs_clip = BT.r_interface(P.PAD_CHOICE, P.CLAMP_ACCEPT_N[0], P.TAB_AREA[0])[0]   # strip at a 45 N clip, small tab
    rows = []
    for c in P.CATALOG_TO247:
        fits = lo_w <= c["w"] <= hi_w
        res = {}
        for label, r in (("natural", c["r_nat"]), (f"{c['r_forced'][1]} LFM" if c["r_forced"] else "forced", c["r_forced"][0] if c["r_forced"] else None)):
            if r is None:
                continue
            for ceil in (17.5, 22.0):
                res[f"{label}|{ceil}"] = fet_alone(r, ceil, rcs_clip)
        rows.append(dict(c, fits_pitch=fits, results=res))
    # BR1 on its own sink: R_SA that keeps that sink <= 80 C (it is the hottest device, so it would carry the TCO)
    p_br1 = BT.p_br1()
    r_need_br1 = (80.0 - T_AMB) / p_br1
    # FET sink R_SA that keeps a FET sink <= 80 C at 22 A (only matters if the TCO sits on a FET sink)
    lo, hi = 0.1, 30.0                 # bisection: the R_SA whose self-consistent FET sink sits at 80 C at 22 A
    for _ in range(60):
        mid = (lo + hi) / 2
        r = fet_alone(mid, 22.0, rcs_clip)
        lo, hi = (mid, hi) if not r.get("runaway") and r["ts"] < 80.0 else (lo, mid)
    r_need_fet22, p22 = lo, fet_alone(lo, 22.0, rcs_clip)["p"]
    # a hanging sink loads the soldered leads: the leads' elastic moment at the weakest corner
    m_el_min = min(P.SIGMA_LEAD_ALLOW * sum(w * k["c"] ** 2 / 6 for w in (k["b1"], k["b2"], k["b1"])) for k in M.corners())
    lever = 4.215 - (-30.0)        # leads at y 4.215 to a sink centre of mass ~30 mm off the board edge (EST)
    m_max_g = m_el_min / lever / 9.81e-3
    return dict(width_window=(lo_w, hi_w), rcs_clip=rcs_clip, rows=rows, p_br1=p_br1, r_need_br1=r_need_br1,
                p_fet22=p22, r_need_fet22=r_need_fet22, lead_moment_el_Nmm=m_el_min, hang_lever_mm=lever, hang_mass_max_g=m_max_g)


def gap_pad():
    g = P.GAP5000
    # interface part of the 0.040 in data = impedance - bulk (t (1 - strain) / k)
    iface = {e: z - (0.040 * 25.4e-3 * (1 - e) / g["k"]) / IN2_M2 for e, z in g["z_040"].items()}
    sp = TOL.spreads()
    out = []
    for t_in in g["t_in"]:
        t = t_in * 25.4
        window = t * (g["strain"][1] - g["strain"][0])       # thickness range inside the data's strain range
        thick = t * (1 - g["strain"][0])                         # the deepest device sits at the least strain
        z = thick * 1e-3 / g["k"] / IN2_M2 + iface[g["strain"][0]]
        r_small = z * 645.16 / P.TAB_AREA[0]
        out.append(dict(t_in=t_in, t_mm=t, window_mm=window, r_small_tab=r_small,
                        covers_R_lot=window >= sp["R_lot"], covers_R_ds=window >= sp["R_datasheet"], covers_U=window >= sp["U_lot"]))
    lean_wedge = TOL.lean_limit(BT.clamp(P.PAD_CHOICE), M.elastic_limits(), TOL.lean_terms())[0] * (TOL.gauge_z()[1] - TOL.gauge_z()[0])
    return dict(rows=out, iface=iface, spreads=sp, lean_wedge_mm=lean_wedge)


def main():
    pdv = per_device()
    gp = gap_pad()
    tol = json.loads((STUDY / "results" / "tolerance.json").read_text())
    th = json.loads((STUDY / "results" / "thermal.json").read_text())
    rows_c = {(r["ceil"], r["t_amb"], r["basis"]): r for r in th["pads"][P.PAD_CHOICE]["rows"]}
    md = ["# Bench sink r1: mount comparison (generated by scripts/compare_mounts.py; do not edit)", "",
          "## A. Common sink + selected shims (revision 2; bench_thermal.py / bench_tolerance.py, bound case)", "",
          f"- 17.5 A: sink {rows_c[(17.5, 30.0, 'D')]['ts']:.1f} C, Tj {rows_c[(17.5, 30.0, 'D')]['tj']:.1f} C; 22 A: sink "
          f"{rows_c[(22.0, 30.0, 'D')]['ts']:.1f} C (fan), Tj {rows_c[(22.0, 30.0, 'D')]['tj']:.1f} C. One NTC and one TCO see all five devices' heat.",
          f"- Hand work: gauge 8 gaps, run shim_select.py, cut and grease up to {P.SHIM_LAYERS_MAX} layers x 4, float and lock the sink.", "",
          "## B. One sink per device", "",
          f"Width window for a per-device sink: >= {pdv['width_window'][0]:.2f} mm (cover E1 max) and <= {pdv['width_window'][1]:.2f} mm "
          f"(18 mm pitch at Q5/Q6 and Q3/Q2, {P.SINK_GAP_MIN} mm fitting gap). Strip at a 45 N clip on the small tab: {pdv['rcs_clip']:.3f} C/W.", "",
          "| catalogue part [DKS] | attach | width mm | fits pitch | R nat | R forced | 17.5 A nat: sink / Tj | 22 A nat: sink / Tj | 22 A forced: sink / Tj | stock | $ |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in pdv["rows"]:
        def cell(key):
            v = r["results"].get(key)
            return "-" if not v else ("runaway" if v.get("runaway") else f"{v['ts']:.0f} / {v['tj']:.0f}")
        fk = f"{r['r_forced'][1]} LFM|22.0" if r["r_forced"] else None
        md.append(f"| {r['pn']} ({r['dk_id']}) | {r['attach']} | {r['w']} | {r['fits_pitch']} | {r['r_nat'] or '-'} | "
                  f"{(str(r['r_forced'][0]) + ' @ ' + str(r['r_forced'][1]) + ' LFM') if r['r_forced'] else '-'} | {cell('natural|17.5')} | "
                  f"{cell('natural|22.0')} | {cell(fk) if fk else '-'} | {r['stock']} | {r['usd']} |")
    md += ["", f"- **No catalogue TO-247 sink in the read fits the pitch** (narrowest {min(r['w'] for r in pdv['rows'])} mm). The ones that would "
           "hold 22 A are 35-42 mm wide. A per-device bench would need custom 17 mm sinks (e.g. slices of an extrusion) and custom clips.",
           f"- A FET sink that carried the TCO would need R_SA <= {pdv['r_need_fet22']:.2f} C/W at 22 A ({pdv['p_fet22']:.2f} W). BR1 alone "
           f"dissipates {pdv['p_br1']:.2f} W: its own sink needs R_SA <= {pdv['r_need_br1']:.2f} C/W to stay <= 80 C, so BR1's sink is the "
           "hottest and the TCO/NTC would sit there, **seeing none of the FETs**. A fan-shadowed or badly clipped FET sink then overheats "
           "with no sink-sensed trip; the common sink's NTC sees every device's heat (not a bad interface, in either design).",
           f"- A sink that hangs on its device loads the soldered leads: elastic moment at the weakest lead corner {pdv['lead_moment_el_Nmm']:.1f} N mm, "
           f"so at a {pdv['hang_lever_mm']:.0f} mm lever (EST centre of mass) the sink must weigh <= {pdv['hang_mass_max_g']:.0f} g "
           "(before any fan or harness pull), or sit on its own support - which brings back a positioning fit per device.",
           "- Insulation: each tab still needs >= 4 mm of pad beyond its metal edge on every side; at the 18 mm pitch the pads overlap, so the "
           "per-device design still needs one continuous strip across the separate sinks, plus five PE bonds (one per sink).", "",
           "## C. Common sink + thick soft gap pad (GAP PAD 5000S35, no shims, no spring clamp)", "",
           f"Usable thickness window = 10-30 % strain (the data range [HNK] p.28). Spread to absorb: R {gp['spreads']['R_lot']:.3f}-"
           f"{gp['spreads']['R_datasheet']:.3f} mm, U {gp['spreads']['U_lot']:.3f}-{gp['spreads']['U_datasheet']:.3f} mm, plus up to "
           f"{gp['lean_wedge_mm']:.3f} mm of lean wedge per device.", "",
           "| sheet in | mm | window mm | Rcs at 10 % strain, small tab C/W | covers R (lot) | covers R (datasheet) | covers U |", "|---|---|---|---|---|---|---|"]
    md += [f"| {r['t_in']} | {r['t_mm']:.2f} | {r['window_mm']:.3f} | {r['r_small_tab']:.2f} | {r['covers_R_lot']} | {r['covers_R_ds']} | {r['covers_U']} |"
           for r in gp["rows"]]
    best = gp["rows"][-1]
    md += ["", f"- Even the 0.125 in sheet's window ({best['window_mm']:.3f} mm) misses the no-remark spread and only covers the remark "
           f"case if lean is small, at Rcs {best['r_small_tab']:.2f} C/W (the shim bound adds {th['shim_stack_C_per_W']['small'][0]:.3f} to the strip's "
           f"{th['pads'][P.PAD_CHOICE]['rcs_range'][1]:.3f}). Whether it fits is known only after gauging the row, i.e. the same hand work as A.", ""]
    res = dict(per_device=pdv, gap_pad=gp)
    (STUDY / "results" / "compare.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
    (STUDY / "results" / "compare.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
