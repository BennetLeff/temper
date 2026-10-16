#!/usr/bin/env python3
"""Back out the board-face film coefficient h, in B3's own form, from a bench DC copper-heating run on native-21.

    python3 -I bench_h_fit.py sites                       # TC site table resolved on the board (-> results/sites.json)
    python3 -I bench_h_fit.py plan    --run RUN.json      # predicted TC temperatures at a few h (sizing the current)
    python3 -I bench_h_fit.py fit     --run RUN.json      # fit h from measured TCs -> results/fit-<run_id>-C1.json
    python3 -I bench_h_fit.py fit2    --run RUN.json      # diagnostic: h_top and h_bottom separately (after fit)
    python3 -I bench_h_fit.py verdict --fits A.json,B.json --air-op 61 [--route face|jetmix]
    python3 -I bench_h_fit.py selftest [--only ID]        # synthetic bench days with known truth -> results/selftest*.json

Model: the B3 body-level hot-copper solve (b3-convergence/thermal_body.py + body_runs.run_case), imported from SNAP, a
byte copy of PS HEAD (snapshot.py, SNAP/SNAPSHOT.txt). Nothing is written to PS.

What a bench case is (procedure method b1, "jumpered diagonal"): the board, fully assembled, sits in the enclosure with
the airflow under test running. No mains, no bias, no switching. A DC bench supply drives a known current I from BR1.1
to BR1.4 through ONE diagonal of the bridge, whose two TO-247s are bridged drain-to-source on the solder side, through
T1's primary, J2 -> a strap -> J5 (in place of the coil), and the five bank positions bridged C.1 -> C.2:
  diag1  BR1.1 -> Q2.2|Q2.3 -> sw_a -> T1.1|T1.2 -> J2 -> strap -> J5 -> res_a -> C*.1|C*.2 -> sw_b -> Q6.2|Q6.3 -> R5
  diag2  BR1.1 -> Q5.2|Q5.3 -> sw_b -> C*.2|C*.1 -> res_a -> J5 -> strap -> J2 -> T1.2|T1.1 -> sw_a -> Q3.2|Q3.3 -> R5
  alt    an external commutator alternates diag1 / diag2 at <= 1 Hz, 50 % each (B3's own half-path weighting)
Every board-copper segment of those paths is an A4 DC case (round5-native21/outputs, solved from the same source and
sink pads), so the bench heat is B3's copper heat at (I / I_ref)^2 with no new field: see A4_PATHS.
Part heat: R5 at its measured Kelvin power; every other heat row at EPS_W (1 uW), so that every package network and
body-to-air path B3 has in operation is also present in the bench model (zero would drop the node and its air path).
Bench hardware is modelled explicitly ("attachments" in RUN.json): each D-S jumper and bank link is a node carrying its
own I^2 R and tied to both pads by its Wiedemann-Franz thermal conductance L0 T / R; each supply-cable joint is a
fixed-temperature tie at the cable TC. FET tabs are ties at their measured temperatures (B3's drain-lead path,
fet_case's role in run_basis). The air is the measured hot-corner leading-edge air (B3's "bay"), at its absolute
temperature (hot copper is solved at absolute T).

Fit: rise ~ 1/h, so each TC's model temperature is interpolated in x = 1/h (quadratic through the solved points). h
is the weighted least-squares zero over the fit cluster (sigma per TC = instrument + placement x the model's own
gradient at the TC); the search re-solves at the current estimate until it is bracketed and stable, at 0.5 mm, then
re-fits on 0.25 mm solves. Systematics are re-fits on one perturbed solve each (lead g at the drawing extremes,
attachment g x0 / x2, copper loss +/- its measured uncertainty, film/module air rise, tab offset), plus the shifts
(air reference, TC common offset) and the mesh (0.25 vs 0.5 mm).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SNAP = Path(os.environ.get("BH_SNAP", ROOT / "snap"))
R5DIR = SNAP / "zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21"
WORK = Path(os.environ.get("BH_WORK", ROOT / "work"))
OUT = ROOT / "results"
sys.path[:0] = [str(R5DIR / "b3-convergence"), str(R5DIR / "b3-ratings")]

EPS_W = 1e-6
L0 = 2.44e-8            # Lorenz number, W Ohm / K^2 (Wiedemann-Franz; copper at 300-400 K is within 3 %)
T_LINK_K = 330.0

# A4 DC cases per bench configuration: (case, reference current A, weight). weight 1 = carries I the whole time,
# 0.5 = half the time (alt). Directions are irrelevant (I^2 heat); terminals are the A4 cases' own source/sink pads.
A4_DIAG1 = [("bus_dc_q2-p0125-pl18", 15.0), ("sw_a-p00625-pl18", 18.7), ("coil_feed-p0125-pl18", 18.7),
            ("res_a-p0125-pl18", 18.7), ("sw_b_low-p00625-pl18", 18.7), ("leg_b_18p7-p00625-pl18", 18.7),
            ("hv_dc-p00625-pl18", 15.0)]
A4_DIAG2 = [("bus_dc_q5-p0125-pl18", 15.0), ("sw_b_high-p00625-pl18", 18.7), ("res_a-p0125-pl18", 18.7),
            ("coil_feed-p0125-pl18", 18.7), ("sw_a_low-p00625-pl18", 18.7), ("leg_a_18p7-p00625-pl18", 18.7),
            ("hv_dc-p00625-pl18", 15.0)]


def a4_paths(config):
    if config == "diag1":
        return [(c, i, 1.0) for c, i in A4_DIAG1]
    if config == "diag2":
        return [(c, i, 1.0) for c, i in A4_DIAG2]
    if config == "alt":
        both = {}
        for c, i in A4_DIAG1 + A4_DIAG2:
            both[(c, i)] = both.get((c, i), 0.0) + 0.5
        return [(c, i, w) for (c, i), w in both.items()]
    raise SystemExit(f"config {config!r}: diag1 | diag2 | alt")


# Default bench attachments per configuration (procedure section 3.2); RUN.json "attachments" replaces them.
def default_attachments(config, i_a):
    jump = {"diag1": ["Q2", "Q6"], "diag2": ["Q5", "Q3"], "alt": ["Q2", "Q6", "Q5", "Q3"]}[config]
    duty = 1.0 if config != "alt" else 0.5
    att = [{"kind": "link", "name": f"J{q}", "pads": [f"{q}.2", f"{q}.3"], "layer": "B.Cu", "r_ohm": 1.0e-4,
            "i_rms_a": i_a * math.sqrt(duty), "g_air_w_k": 0.002} for q in jump]
    att += [{"kind": "link", "name": f"L{c}", "pads": [f"{c}.1", f"{c}.2"], "layer": "B.Cu", "r_ohm": 1.5e-3,
             "i_rms_a": i_a / 5.0, "g_air_w_k": 0.004} for c in ("C21", "C22", "C23", "C151", "C152")]
    return att


# TC sites. cluster C1 = FET-row / R5 strip (the binding rows of every ladder step), C2 = tank path, D = diagnostic,
# G = guard (drain pads, read against the tab TCs). pt = (x, y, layer) mean over a 0.75 mm radius bead footprint;
# pad = (ref, pad, layer) area mean over the pad copper.
SITES = [
    ("LAM_R5.4", "C1", "pt", (38.5, 15.5, "F.Cu"), "laminate 1 mm block at R5.4 (binding at 22 / 28 A)"),
    ("R12.1", "C1", "pad", ("R12", "1", "F.Cu"), "R12 2512 terminal (binding at 24 / 26 / 28 A)"),
    ("R12.2", "C1", "pad", ("R12", "2", "F.Cu"), "R12 2512 terminal"),
    ("R10.1", "C1", "pad", ("R10", "1", "F.Cu"), "R10 2512 terminal (binding at 18 / 20 A)"),
    ("R10.2", "C1", "pad", ("R10", "2", "F.Cu"), "R10 2512 terminal"),
    ("R20.1", "C1", "pad", ("R20", "1", "F.Cu"), "R20 2512 terminal"),
    ("R20.2", "C1", "pad", ("R20", "2", "F.Cu"), "R20 2512 terminal"),
    ("R18.2", "C1", "pad", ("R18", "2", "F.Cu"), "R18 2512 terminal"),
    ("R5.1", "C1", "pad", ("R5", "1", "F.Cu"), "R5 current terminal (leg_ret side)"),
    ("FETROW_B", "C1", "pt", (44.5, 19.5, "B.Cu"), "FET-row copper under R12 / Q3, solder side (binds top-only flow)"),
    ("Q2S_F", "C1", "pt", (73.5, 7.5, "F.Cu"), "bus / BR1 edge, component side, 3 mm off the Q2.3 pad (In2 hot spot at 73.5, 4.5)"),
    ("Q2S_B", "C1", "pt", (73.5, 7.5, "B.Cu"), "bus / BR1 edge, solder side"),
    ("TANK_T1.1", "C2", "pad", ("T1", "1", "F.Cu"), "T1.1 pad, tank path (binds at 61 C when only the corner is cooled)"),
    ("J2.1", "C2", "pad", ("J2", "1", "F.Cu"), "coil terminal J2 ring land"),
    ("J5.1", "C2", "pad", ("J5", "1", "F.Cu"), "coil terminal J5 ring land"),
    ("BANK_C152.1", "C2", "pad", ("C152", "1", "F.Cu"), "bank column, top end"),
    ("BANK_C21.2", "C2", "pad", ("C21", "2", "F.Cu"), "bank column, bottom end"),
    ("C40.2", "D", "pad", ("C40", "2", "F.Cu"), "HF film cap C40 lead pad"),
    ("U26.21", "D", "pad", ("U26", "21", "F.Cu"), "U26 exposed pad (TC on the body top in practice)"),
    ("Q2.2", "G", "pad", ("Q2", "2", "B.Cu"), "drain pad fillet (guard pair with the Q2 tab TC)"),
    ("Q3.2", "G", "pad", ("Q3", "2", "B.Cu"), "drain pad fillet"),
    ("Q5.2", "G", "pad", ("Q5", "2", "B.Cu"), "drain pad fillet"),
    ("Q6.2", "G", "pad", ("Q6", "2", "B.Cu"), "drain pad fillet"),
]
SITE = {s[0]: s for s in SITES}
FIT_CLUSTERS = ("C1", "C2")


# ---------------------------------------------------------------------------------------------------- model glue
def _model():
    import run_basis as rb
    return rb, rb.br, rb.tb


def lead_g_bounds():
    _, _, tb = _model()
    lo = tb.drain_lead_conductance(2.57, 0.38, 4.50, 7.91, 262.0, 1.0)
    hi = tb.drain_lead_conductance(3.43, 0.89, 3.85, 0.0, 390.0, 3.0)
    return lo, tb.drain_lead_conductance(), hi


def _pad_cells(brd, tb, ref, pad, layer, pitch, nx, ny):
    for lay, poly in brd.pads_of(ref)[pad]:
        if lay == layer:
            return tb.pad_overlap(poly, brd.xmin, brd.ymin, pitch, 0, 0, nx, ny)
    raise KeyError(f"{ref}.{pad} has no {layer} copper")


def bench_heat_json(run, path):
    rb, _, _ = _model()
    heat = json.loads(rb.rs.HEAT_C28.read_text())
    over = run.get("part_watts", {})
    for p in heat["parts"]:
        w = run["p_r5_w"] if p["ref"] == "R5" else over.get(p["ref"], EPS_W)
        p["watts_nominal"] = p["watts_worst"] = w
    heat["status"] = f"bench case {run['run_id']}: R5 {run['p_r5_w']:.4f} W, others {EPS_W} W unless part_watts"
    path.write_text(json.dumps(heat))


def _patch_attachments(tb, attachments, t_air):
    """Wrap tb.build_network_parts / tb.build_lead_links so the bench hardware joins the solve."""
    links = [a for a in attachments if a["kind"] == "link"]
    ties = [a for a in attachments if a["kind"] == "tie"]
    if not hasattr(tb, "_bh_orig"):
        tb._bh_orig = (tb.build_network_parts, tb.build_lead_links)
    bnp0, bll0 = tb._bh_orig

    def bnp(board_obj, heat_json, mode, nz, nx, ny, xmin, ymin, pitch, i0, j0, h, fps, sens, inside, region=None):
        parts, omitted = bnp0(board_obj, heat_json, mode, nz, nx, ny, xmin, ymin, pitch, i0, j0, h, fps, sens, inside,
                              region)
        nxy = nx * ny
        for a in links:
            g_th = a.get("g_th_w_k") or L0 * T_LINK_K / a["r_ohm"]
            g_th *= sens.get("attach_g_scale", 1.0)
            w = a["i_rms_a"] ** 2 * a["r_ohm"]
            np_ = tb.NetPart(a["name"], w, "bench_link")
            for pr in a["pads"]:
                ref, _, n = pr.partition(".")
                for lay, poly in board_obj.pads_of(ref)[n]:
                    if lay != a["layer"]:
                        continue
                    ii, jj, ar = tb.pad_overlap(poly, xmin, ymin, pitch, i0, j0, nx, ny)
                    z = tb.CU_INDEX[lay]
                    np_.groups.append((z * nxy + ii * ny + jj, ar / ar.sum(), 2.0 * g_th, f"{pr}.{lay}"))
            np_.g_air = a.get("g_air_w_k", 0.0)
            np_.t_air = 0.0
            np_.meta.update(label=f"bench link {a['name']}", r_pad=1 / (4 * g_th), spec="bench_link", watts=w)
            parts.append(np_)
        return parts, omitted

    def bll(board_obj, leads, nx, ny, xmin, ymin, pitch, i0, j0):
        out = bll0(board_obj, leads, nx, ny, xmin, ymin, pitch, i0, j0)
        nxy = nx * ny
        for a in ties:
            ref, _, n = a["pad"].partition(".")
            lk = tb.LeadLink(ref, n, a["g_w_k"], a["t_c"] - t_air)
            for lay, poly in board_obj.pads_of(ref)[n]:
                if lay != a["layer"]:
                    continue
                ii, jj, ar = tb.pad_overlap(poly, xmin, ymin, pitch, i0, j0, nx, ny)
                lk.groups.append((tb.CU_INDEX[lay] * nxy + ii * ny + jj, ar / ar.sum(), a["g_w_k"], f"tie.{lay}"))
                lk.shares.append(1.0)
            out.append(lk)
        return out
    tb.build_network_parts, tb.build_lead_links = bnp, bll


def site_xy(run):
    """Measured bead positions for pt sites: tc entries carrying x_mm / y_mm (photo with a scale) move the sample."""
    return {t["site"]: [t["x_mm"], t["y_mm"]] for t in run.get("tc", []) if "x_mm" in t and SITE.get(t["site"], ("",) * 3)[2] == "pt"}


def _sample(rise, brd, tb, pitch, t_air, moved=None):
    moved = moved or {}
    nz, nx, ny = rise.shape
    xc = brd.xmin + (np.arange(nx) + 0.5) * pitch
    yc = brd.ymin + (np.arange(ny) + 0.5) * pitch

    def pt(x0, y0, z, r=0.75):
        sel = ((xc[:, None] - x0) ** 2 + (yc[None, :] - y0) ** 2 <= r * r) & (rise[z] != 0.0)
        return float(rise[z][sel].mean()) if sel.any() else float("nan")
    out = {}
    for name, cl, kind, arg, _ in SITES:
        if kind == "pt":
            x0, y0, lay = arg
            if name in moved:
                x0, y0 = moved[name]
            z = tb.CU_INDEX[lay]
            v = pt(x0, y0, z)
            shifts = [pt(x0 + dx, y0 + dy, z) for dx, dy in ((0.5, 0), (-0.5, 0), (0, 0.5), (0, -0.5))]
        else:
            ref, n, lay = arg
            ii, jj, a = _pad_cells(brd, tb, ref, n, lay, pitch, nx, ny)
            z = tb.CU_INDEX[lay]
            v = float((rise[z][ii, jj] * a).sum() / a.sum())
            # placement on a pad: the bead sits somewhere on it; the spread of the pad's cells is the term
            vals = rise[z][ii, jj]
            shifts = [float(np.percentile(vals, 10)), float(np.percentile(vals, 90))]
        out[name] = {"t_c": t_air + v, "place_k": float(np.nanmax(np.abs(np.array(shifts) - v)))}
    return out


def solve(job):
    """job: dict(run, h, pitch, var) -> per-site model temperatures (absolute C) and the run's balance."""
    sys.dont_write_bytecode = True
    rb, br, tb = _model()
    run, h, pitch, var = job["run"], float(job["h"]), float(job["pitch"]), job.get("var", {})
    t_air = run["t_air_ref_c"]
    d = WORK / run["run_id"]
    d.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps([run_core(run), h, pitch, var], sort_keys=True).encode()).hexdigest()[:16]
    cache = d / f"solve_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    t0 = time.time()
    heat_path = d / f"heat_{key}.json"
    bench_heat_json(run, heat_path)
    cu = 1.0 + var.get("cu_scale", 0.0) + run.get("cu_scale", 0.0)
    case_str = ",".join(f"{c}:{w * (run['i_dc_a'] / i_ref) ** 2 * cu:.8g}" for c, i_ref, w in a4_paths(run["config"]))
    br.op_inputs = lambda _op, _c=(case_str, heat_path, "nominal"): _c
    attachments = run.get("attachments") or default_attachments(run["config"], run["i_dc_a"])
    _patch_attachments(tb, attachments, t_air)
    brd = tb.Board(rb.rs.GEOM, rb.RUNS / "cache")
    g = var.get("lead_g", run.get("lead_g", rb.LEAD_G))
    tabs = {q: run["t_tab_c"][q] + var.get("tab_offset_k", 0.0) - t_air for q in ("Q2", "Q3", "Q5", "Q6")}
    leads = {"pad": "2", "g": g, "t_rise": tabs}
    sens = {"film_air_rise": run.get("film_air_rise_k", 0.0) + var.get("film_air_dk", 0.0),
            "module_air_rise": run.get("module_air_rise_k", 0.0) + var.get("film_air_dk", 0.0),
            "attach_g_scale": var.get("attach_g_scale", 1.0)}
    region = None
    h_top = var.get("h_top", run.get("h_top"))
    if run.get("mode", "uniform") == "jetmix":
        region = tb.TopRegion(rb.JET_REGION, h_top, 0.0, name="jet")
    elif run.get("mode") == "jetfit":         # the swept h is the jets' h_top on JET_REGION; the base is fixed
        region = tb.TopRegion(rb.JET_REGION, h, 0.0, name="jet")
        h = float(run["h_base"])
    elif run.get("mode") == "top":
        region = tb.TopRegion((brd.xmin - 1, brd.xmax + 1, brd.ymin - 1, brd.ymax + 1), h, 0.0, name="top")
        h = float(var.get("h_bottom", run.get("h_bottom", 10.0)))
    res, rise = br.run_case(brd, "bench", h, pitch, "fraction", "network", sens, None, None, True, True,
                            label=f"{run['run_id']} h{h:g} p{pitch:g}", return_rise=True, leads=leads, region=region,
                            copper_tcr={"alpha": tb.ALPHA_CU, "air_c": t_air}, probes=False)
    sites = _sample(rise, brd, tb, pitch, t_air, run.get("site_xy") or site_xy(run))
    pk = res["peak_1mm_block"]
    out = {"h": job["h"], "pitch": pitch, "var": var, "sites": sites, "balance": res["balance"],
           "copper": res.get("copper_temp_model"), "leads": res.get("leads"),
           "peak_1mm_block": {**pk, "temperature_c": t_air + pk["temperature_c"] - tb.TAMB_C},
           "link_w": sum(a["i_rms_a"] ** 2 * a["r_ohm"] for a in attachments if a["kind"] == "link"),
           "board_sha256": brd.data["board_sha256"], "case_str": case_str, "runtime_s": round(time.time() - t0, 1)}
    cache.write_text(json.dumps(out, indent=1) + "\n")
    return out


def run_core(run):
    """The inputs that define the forward model (not the measured TCs)."""
    keys = ("run_id", "config", "i_dc_a", "p_r5_w", "t_air_ref_c", "t_tab_c", "film_air_rise_k", "module_air_rise_k",
            "attachments", "part_watts", "mode", "h_top", "h_bottom", "h_base", "lead_g", "cu_scale")
    out = {k: run.get(k) for k in keys}
    xy = site_xy(run)
    if xy:
        out["site_xy"] = xy
    return out


def solve_many(jobs, workers):
    jobs = [j for j in jobs]
    if not jobs:
        return []
    with ProcessPoolExecutor(max_workers=max(1, min(workers, 4, len(jobs)))) as ex:
        return list(ex.map(solve, jobs))


# ---------------------------------------------------------------------------------------------------------- fit
def site_sigma(run, name, place_k):
    tc = {t["site"]: t for t in run["tc"]}[name]
    s_inst = tc.get("sigma_k", run.get("sigma_tc_k", 0.3))
    return math.hypot(s_inst, place_k * run.get("place_frac", 1.0))


def interp_site(points, name, near=None):
    """points {h: solve}; returns (f, f') of x = 1/h: a quadratic through the 3 solved points nearest h = near (all
    points when near is None), linear with 2."""
    hs = sorted(points)
    if near is not None and len(hs) > 3:
        hs = sorted(sorted(hs, key=lambda q: abs(1 / q - 1 / near))[:3])
    xs = np.array([1 / h for h in hs])
    ys = np.array([points[h]["sites"][name]["t_c"] for h in hs])
    c = np.polyfit(xs, ys, 2 if len(hs) >= 3 else 1)
    return lambda x: float(np.polyval(c, x)), lambda x: float(np.polyval(np.polyder(c), x))


def ls_fit(run, points, names, shifts=None, tshift=0.0, _near=None):
    """Weighted LS zero in x = 1/h. shifts: {site: K} added to the model; tshift: K added to every measurement.
    Two passes: all points, then the local quadratic through the 3 points nearest the first estimate."""
    if _near is None and len(points) > 3:
        h1 = ls_fit(run, points, names, shifts, tshift, _near=0.0)["h"]
        return ls_fit(run, points, names, shifts, tshift, _near=h1)
    near = _near if _near else None
    meas = {t["site"]: t["t_c"] + tshift for t in run["tc"] if t["site"] in names}
    names = [n for n in names if n in meas]
    hs = sorted(points)
    hmid = hs[len(hs) // 2]
    fs = {n: interp_site(points, n, near) for n in names}
    sig = {n: site_sigma(run, n, points[hmid]["sites"][n]["place_k"]) for n in names}
    sh = shifts or {}

    def chi2(x):
        return sum(((meas[n] - fs[n][0](x) - sh.get(n, 0.0)) / sig[n]) ** 2 for n in names)
    xa, xb = 1 / (hs[-1] * 1.3), 1 / (hs[0] / 1.3)
    grid = np.linspace(xa, xb, 801)
    v = [chi2(x) for x in grid]
    k = int(np.argmin(v))
    lo, hi = grid[max(k - 1, 0)], grid[min(k + 1, len(grid) - 1)]
    for _ in range(60):                    # golden section on the bracket
        m1, m2 = lo + 0.382 * (hi - lo), lo + 0.618 * (hi - lo)
        lo, hi = (lo, m2) if chi2(m1) < chi2(m2) else (m1, hi)
    x = 0.5 * (lo + hi)
    h = 1 / x
    dof = max(len(names) - 1, 1)
    c2 = chi2(x)
    # 1-sigma of x from the curvature of chi2 (linearised): sum (dT/dx / sigma)^2
    info = sum((fs[n][1](x) / sig[n]) ** 2 for n in names)
    sx = 1 / math.sqrt(info) if info > 0 else float("inf")
    birge = max(1.0, math.sqrt(c2 / dof))
    per = {}
    for n in names:                         # per-site h: root of T_n(x) = meas
        f = fs[n][0]
        g0 = [f(xx) - sh.get(n, 0.0) - meas[n] for xx in grid]
        roots = [1 / (grid[i] - g0[i] * (grid[i + 1] - grid[i]) / (g0[i + 1] - g0[i]))
                 for i in range(len(grid) - 1) if g0[i] == 0 or g0[i] * g0[i + 1] < 0]
        dTdh = -fs[n][1](x) * x * x
        per[n] = {"h": round(roots[0], 2) if roots else None, "meas_c": round(meas[n], 2),
                  "model_c": round(fs[n][0](x) + sh.get(n, 0.0), 2), "sigma_k": round(sig[n], 3),
                  "dT_dh_k_per_w_m2k": round(dTdh, 3), "rise_over_air_k": round(meas[n] - run["t_air_ref_c"], 1)}
    return {"h": h, "sigma_stat": h * h * sx * birge, "chi2": c2, "dof": dof, "birge": birge, "sites": per,
            "bracketed": hs[0] <= h <= hs[-1]}


def fit_run(run, workers=3, pitch_search=0.5, final_fine=True, systematics=True, cluster="C1", verbose=True):
    names = [s[0] for s in SITES if s[1] == cluster and s[0] in {t["site"] for t in run["tc"]}]
    if len(names) < 2:
        raise SystemExit(f"cluster {cluster}: fewer than 2 TCs")
    hg = float(run.get("h_guess", 20.0))
    pts = {r["h"]: r for r in solve_many([dict(run=run, h=round(hg * f, 2), pitch=pitch_search)
                                          for f in (0.7, 1.0, 1.4)], workers)}
    hist = []
    for _ in range(8):
        f = ls_fit(run, pts, names)
        hist.append(round(f["h"], 3))
        if verbose:
            print(f"  [{run['run_id']} {cluster} p{pitch_search}] h = {f['h']:.2f} (points {sorted(pts)})", flush=True)
        near = min(pts, key=lambda q: abs(q - f["h"]))
        if f["bracketed"] and abs(near - f["h"]) / f["h"] < 0.03:
            break
        hn = round(f["h"], 2)
        pts[hn] = solve(dict(run=run, h=hn, pitch=pitch_search))
    fit05 = ls_fit(run, pts, names)
    res = {"cluster": cluster, "sites_used": names, "search_pitch": pitch_search, "h_p0p5": fit05["h"],
           "search_history": hist, "fit_p0p5": fit05, "points_p0p5": sorted(pts)}
    best, best_pts = fit05, pts
    if final_fine:
        h0 = fit05["h"]
        fine = {r["h"]: r for r in solve_many([dict(run=run, h=round(h0 * f, 2), pitch=0.25) for f in (0.88, 1.0, 1.14)],
                                              workers)}
        fit25 = ls_fit(run, fine, names)
        res.update(h_p0p25=fit25["h"], fit_p0p25=fit25, points_p0p25=sorted(fine))
        best, best_pts = fit25, fine
    res["h"] = best["h"]
    terms = {"statistical (TC + placement, Birge-inflated)": best["sigma_stat"]}
    if final_fine:
        terms["mesh (0.25 vs 0.5 mm fit)"] = abs(res["h_p0p25"] - res["h_p0p5"])
    if systematics:
        hb = round(fit05["h"], 2)
        base = pts[min(pts, key=lambda q: abs(q - hb))]
        hb = base["h"]
        g_lo, _, g_hi = lead_g_bounds()
        u_q = run.get("sigma_cu_rel", 0.015 if run.get("v_loop_v") is not None else 0.03)
        s_fa = run.get("sigma_film_air_k", 1.5)
        perts = {"drain-lead g at drawing minimum": {"lead_g": g_lo},
                 "drain-lead g at drawing maximum": {"lead_g": g_hi},
                 "attachment thermal g x 0.5": {"attach_g_scale": 0.5},
                 "attachment thermal g x 1.5": {"attach_g_scale": 1.5},
                 f"copper loss +{u_q:.0%}": {"cu_scale": u_q},
                 f"film / module air rise +{s_fa} K": {"film_air_dk": s_fa},
                 f"tab TCs +{run.get('sigma_tab_k', 0.5)} K": {"tab_offset_k": run.get("sigma_tab_k", 0.5)}}
        sols = solve_many([dict(run=run, h=hb, pitch=pitch_search, var=v) for v in perts.values()], workers)
        for (lab, _), s in zip(perts.items(), sols):
            shifts = {n: s["sites"][n]["t_c"] - base["sites"][n]["t_c"] for n in names}
            f2 = ls_fit(run, best_pts, names, shifts=shifts)
            terms[lab] = abs(f2["h"] - best["h"])
        # the two drain-lead extremes are one term (take the larger), as are the two attachment extremes
        for a, b, lab in (("drain-lead g at drawing minimum", "drain-lead g at drawing maximum", "drain-lead g (drawing range)"),
                          ("attachment thermal g x 0.5", "attachment thermal g x 1.5", "bench attachments (g x 0.5 .. x 1.5)")):
            terms[lab] = max(terms.pop(a), terms.pop(b))
        s_air = run.get("sigma_air_k", 0.3)
        terms[f"air reference +/-{s_air} K"] = abs(ls_fit(run, best_pts, names, tshift=-s_air)["h"] - best["h"])
        s_cm = run.get("sigma_tc_common_k", 0.2)
        terms[f"TC common offset +/-{s_cm} K"] = abs(ls_fit(run, best_pts, names, tshift=s_cm)["h"] - best["h"])
    u1 = math.sqrt(sum(v * v for v in terms.values()))
    res.update(u_terms_1sigma=terms, u_1sigma=u1, U95=2 * u1, h_L95=best["h"] - 2 * u1,
               chi2_dof=best["chi2"] / best["dof"], birge=best["birge"], site_fit=best["sites"])
    # loss check: model board loss (hot A4 + R5 + links) vs the measured loop power
    s0 = best_pts[min(best_pts, key=lambda q: abs(q - best["h"]))]
    model_w = (s0["copper"] or {}).get("loss_w_hot", 0.0) + run["p_r5_w"] + s0["link_w"]
    res["loss_check"] = {"model_board_w": round(model_w, 3)}
    if run.get("v_loop_v") is not None:
        meas_w = run["v_loop_v"] * run["i_dc_a"] - run.get("r_offboard_ohm", 0.0) * run["i_dc_a"] ** 2
        res["loss_check"].update(measured_w=round(meas_w, 3), ratio=round(meas_w / model_w, 4),
                                 action="if |ratio - 1| > 2 sigma_cu_rel, re-fit with cu_scale = ratio - 1 and say so")
    res["peak_model"] = s0["peak_1mm_block"]
    res["leads"] = s0["leads"]
    return res


def fit_two_face(run, h_uniform, workers=3, pitch=0.25, cluster="C1", step=1.15):
    """Diagnostic: h_top (whole top face + every body) and h_bottom fitted together, linearised about the uniform fit.
    Three solves on the release mesh: uniform at h_u, and mode 'top' (thermal_body.TopRegion on the whole outline) at
    (step x h_u, h_u) and (h_u, step x h_u). T_i = T_i0 + a_i dx_top + b_i dx_bot, x = 1/h; weighted LS for (dx_top,
    dx_bot) with its covariance. The uniform fit is the special case dx_top = dx_bot."""
    names = [s_[0] for s_ in SITES if s_[1] == cluster and s_[0] in {t["site"] for t in run["tc"]}]
    hu = round(h_uniform, 2)
    r2 = dict(run, mode="top")
    s0, st, sb = solve_many([dict(run=run, h=hu, pitch=pitch),
                             dict(run={**r2, "h_bottom": hu}, h=round(hu * step, 2), pitch=pitch, var={"h_bottom": hu}),
                             dict(run={**r2, "h_bottom": round(hu * step, 2)}, h=hu, pitch=pitch,
                                  var={"h_bottom": round(hu * step, 2)})], workers)
    dx = 1 / (hu * step) - 1 / hu
    meas = {t["site"]: t["t_c"] for t in run["tc"]}
    A, y, w = [], [], []
    for n in names:
        a = (st["sites"][n]["t_c"] - s0["sites"][n]["t_c"]) / dx
        b = (sb["sites"][n]["t_c"] - s0["sites"][n]["t_c"]) / dx
        sg = site_sigma(run, n, s0["sites"][n]["place_k"])
        A.append([a / sg, b / sg])
        y.append((meas[n] - s0["sites"][n]["t_c"]) / sg)
    A, y = np.array(A), np.array(y)
    sol, *_ = np.linalg.lstsq(A, y, rcond=None)
    cov = np.linalg.inv(A.T @ A)
    chi2 = float(((A @ sol - y) ** 2).sum())
    dof = max(len(names) - 2, 1)
    cov = cov * max(1.0, chi2 / dof)
    xt, xb = 1 / hu + sol[0], 1 / hu + sol[1]
    ht, hb = 1 / xt, 1 / xb
    st_, sb_ = math.sqrt(cov[0, 0]) * ht * ht, math.sqrt(cov[1, 1]) * hb * hb
    sd = math.sqrt(cov[0, 0] + cov[1, 1] - 2 * cov[0, 1])
    corr = cov[0, 1] / math.sqrt(cov[0, 0] * cov[1, 1])
    return {"h_top": ht, "h_bottom": hb, "sigma_top": st_, "sigma_bottom": sb_, "corr": corr,
            "split_sigma_x": abs(sol[0] - sol[1]) / sd, "chi2": chi2, "dof": dof,
            "significant": abs(sol[0] - sol[1]) > 2 * sd,
            "note": "diagnostic; if 'significant', judge the step with the gate on c<N>_h<h_bottom>_jet<h_top> in "
                    "airflow_search 'top' mode (region = whole outline) instead of the uniform ladder"}


def transfer_to_operation(h_bench, t_film_bench_c, t_film_op_c, regime="turbulent"):
    """Forced-convection property transfer at fixed velocity: h ~ k nu^-n Pr^1/3 (n 0.8 turbulent, 0.5 laminar), air
    from Incropera Table A.4. Applied to the whole fitted h (radiation included), which is conservative: radiation
    rises with temperature."""
    tab = np.array([[250, 11.44, 22.3, 0.720], [300, 15.89, 26.3, 0.707], [350, 20.92, 30.0, 0.700],
                    [400, 26.41, 33.8, 0.690]])

    def prop(tc):
        tk = tc + 273.15
        return [float(np.interp(tk, tab[:, 0], tab[:, i])) for i in (1, 2, 3)]
    n = 0.8 if regime == "turbulent" else 0.5
    nb, kb, pb = prop(t_film_bench_c)
    no, ko, po = prop(t_film_op_c)
    f = (ko / kb) * (no / nb) ** (-n) * (po / pb) ** (1 / 3)
    return h_bench * f, f


# ------------------------------------------------------------------------------------------------------ ladder
# airflow28 README section 3 (s47 board 83355da5, both faces, whole board, release rule): the solved passing integer h
# per step and air. s48 spot checks of the c28 points: results/ladder-s48-check.json (s48_check.py).
LADDER = {18: {55: 10, 61: 11}, 20: {55: 11, 61: 13}, 22: {55: 14, 61: 17}, 24: {55: 17, 61: 20},
          26: {55: 22, 61: 25}, 28: {50: 24, 55: 27, 61: 31}}
JETMIX_BASE_28 = {55: 12, 61: 16}          # jets at h_top 100 on JET_REGION + both-face base flow (airflow28 4.4)
MARGIN = {"face": 1.2, "jetmix": 1.25}


def h_req(step, air_c, route="face"):
    tab = JETMIX_BASE_28 if (route == "jetmix" and step == 28) else LADDER[step]
    if air_c > 61.0 + 1e-9:
        return None                          # not solved above 61 C: no ceiling above 17.5 A without a new B3 basis
    ks = sorted(tab)
    if air_c <= ks[0]:
        return float(tab[ks[0]])            # below the lowest solved air: hold the lowest column (conservative)
    return float(np.interp(air_c, ks, [tab[k] for k in ks]))


def verdict(h_nom, h_l95_worst, air_c, route="face"):
    """Highest step whose gates A and B pass, no step skipped. Jets route: the jets + base requirement is solved at 28 A
    only; B3 is monotone in the tank current at fixed airflow and air, so a jets + base set that passes 28 A passes every
    lower step (the no-jet column is then not needed)."""
    rows, allowed = [], 17.5
    jet28 = None
    if route == "jetmix" and air_c <= 61.0 + 1e-9:
        hr28 = h_req(28, air_c, "jetmix")
        jet28 = h_l95_worst >= hr28 and h_nom >= MARGIN["jetmix"] * hr28
    for step in (18, 20, 22, 24, 26, 28):
        if jet28:
            hr = h_req(28, air_c, "jetmix")
            rows.append({"step_a": step, "h_req": round(hr, 2), "margin": MARGIN["jetmix"],
                         "h_design": round(MARGIN["jetmix"] * hr, 2), "basis": "jets + base at 28 A (monotone)",
                         "pass": True})
            allowed = step
            continue
        hr = h_req(step, air_c, "face" if step < 28 else route)
        if hr is None:
            rows.append({"step_a": step, "pass": False, "why": f"air {air_c} C is above the solved 61 C"})
            break
        m = MARGIN["jetmix" if (route == "jetmix" and step == 28) else "face"]
        a_ok, b_ok = h_l95_worst >= hr, h_nom >= m * hr
        rows.append({"step_a": step, "h_req": round(hr, 2), "margin": m, "h_design": round(m * hr, 2),
                     "gate_A_L95_worst_ge_req": a_ok, "gate_B_nominal_ge_margin_x_req": b_ok, "pass": a_ok and b_ok})
        if not (a_ok and b_ok):
            break
        allowed = step
    return {"air_c": air_c, "route": route, "h_nominal": h_nom, "h_L95_worst": h_l95_worst, "steps": rows,
            "ceiling_allowed_a": allowed,
            "then": "COMMISSIONING gate 0: run_basis.py --cases c<N>_h<floor(h_L95_worst)>@<air> on the board of record "
                    "(or airflow_search.py point --mode jetmix for the jet route) must PASS before TANK_CEILING_DA = 10 N"}


# ---------------------------------------------------------------------------------------------------- selftest
def synth_run(run_id, config, h_true, i_a, t_air, seed, truth_var, tab_guard_err_k=0.0, pitch=0.25):
    """Truth: solve at h_true (0.25 mm) with truth_var, tabs at the drain-pad temperature + tab_guard_err_k (the guard
    null, iterated once). Measurements: truth + bead placement (uniform within the model's own placement term) + TC
    noise N(0, 0.3) + a common offset N(0, 0.1) + an air-reference error N(0, 0.2)."""
    rng = random.Random(seed)
    base = {"run_id": run_id, "config": config, "i_dc_a": i_a, "p_r5_w": i_a ** 2 * 1.0e-3 * 1.12,
            "t_air_ref_c": t_air, "t_tab_c": {q: t_air + 35.0 for q in ("Q2", "Q3", "Q5", "Q6")},
            "film_air_rise_k": 0.0, "module_air_rise_k": 0.0, "h_guess": h_true * 0.8, "tc": []}
    pads = {"Q2": "Q2.2", "Q3": "Q3.2", "Q5": "Q5.2", "Q6": "Q6.2"}
    for it in range(5):                    # the bench's guard loop: tabs -> drain-pad temperature, at 0.5 mm
        t1 = solve(dict(run={**base, "run_id": run_id + f"_guard{it}"}, h=h_true, pitch=0.5, var=truth_var))
        new = {q: round(t1["sites"][p]["t_c"], 2) for q, p in pads.items()}
        err = max(abs(new[q] - base["t_tab_c"][q]) for q in pads)
        base["t_tab_c"] = new
        if err < 0.2:
            break
    base["t_tab_c"] = {q: v + tab_guard_err_k for q, v in base["t_tab_c"].items()}
    tr = solve(dict(run={**base, "run_id": run_id + "_truth"}, h=h_true, pitch=pitch, var=truth_var))
    cm, air_err = rng.gauss(0, 0.1), rng.gauss(0, 0.2)
    tcs = []
    for name, cl, *_ in SITES:
        s = tr["sites"][name]
        t = s["t_c"] + rng.uniform(-1, 1) * s["place_k"] + rng.gauss(0, 0.3) + cm
        tcs.append({"site": name, "t_c": round(t, 2), "sigma_k": 0.3})
    loss = tr["copper"]["loss_w_hot"] + base["p_r5_w"] + tr["link_w"]       # the Kelvin loop reading, 0.3 % (1 sigma)
    run = {**base, "t_air_ref_c": round(t_air + air_err, 2), "tc": tcs,
           "v_loop_v": round(loss / i_a * (1 + rng.gauss(0, 0.003)), 6), "r_offboard_ohm": 0.0,
           "t_tab_c": {q: round(v + rng.gauss(0, 0.3), 2) for q, v in base["t_tab_c"].items()}}
    # the fit is told the air it measured (with its error) and the tabs it measured; truth_var stays unknown to it
    return run, tr


def selftest(workers, only=()):
    OUT.mkdir(parents=True, exist_ok=True)
    g_lo, g_mid, g_hi = lead_g_bounds()
    cases = [("st2_face31_diag1", "diag1", 31.0, 28.0, 25.0, 1, {"lead_g": g_hi, "attach_g_scale": 1.3}, 0.5),
             ("st2_base16_diag2", "diag2", 16.0, 20.0, 25.0, 2, {"lead_g": g_lo, "film_air_dk": 1.0}, -0.5)]
    if only:
        cases = [c for c in cases if c[0] in only]
    out = {"snapshot": (SNAP / "SNAPSHOT.txt").read_text().strip(), "lead_g_bounds_w_k": [g_lo, g_mid, g_hi],
           "cases": []}
    for rid, cfg, h_true, i_a, t_air, seed, tv, guard in cases:
        print(f"selftest {rid}: truth h {h_true}, {cfg}, {i_a} A, air {t_air} C, truth_var {tv}, guard {guard:+} K",
              flush=True)
        run, tr = synth_run(rid, cfg, h_true, i_a, t_air, seed, tv, tab_guard_err_k=guard)
        (WORK / rid).mkdir(parents=True, exist_ok=True)
        (WORK / rid / "run.json").write_text(json.dumps(run, indent=1) + "\n")
        f = fit_run(run, workers=workers)
        c2 = fit_run(run, workers=workers, cluster="C2", final_fine=False, systematics=False, verbose=False)
        inside = abs(f["h"] - h_true) <= f["U95"]
        out["cases"].append({"run_id": rid, "config": cfg, "h_true": h_true, "i_dc_a": i_a, "t_air_true_c": t_air,
                             "truth_var_unknown_to_fit": tv, "tab_guard_error_k": guard,
                             "truth_peak": tr["peak_1mm_block"], "truth_leads": tr["leads"],
                             "truth_rises_k": {n: round(s["t_c"] - t_air, 2) for n, s in tr["sites"].items()},
                             "fit": f, "fit_C2_p0p5": {"h": c2["h"], "sigma_stat": c2["fit_p0p5"]["sigma_stat"],
                                                       "sites": c2["site_fit"]},
                             "recovered_within_U95": inside})
        print(f"  -> h {f['h']:.2f} +/- {f['U95']:.2f} (95 %), truth {h_true}: {'OK' if inside else 'OUTSIDE'}; "
              f"C2 h {c2['h']:.1f}", flush=True)
    name = "selftest.json" if not only else f"selftest-{'-'.join(only)}.json"
    (OUT / name).write_text(json.dumps(out, indent=1, default=float) + "\n")
    print("->", OUT / name)
    return out


def sites_table():
    rb, _, tb = _model()
    brd = tb.Board(rb.rs.GEOM, rb.RUNS / "cache")
    rows = []
    for name, cl, kind, arg, note in SITES:
        if kind == "pt":
            x, y, lay = arg
        else:
            ref, n, lay = arg
            poly = next(p for l, p in brd.pads_of(ref)[n] if l == lay)
            x, y = poly.centroid.coords[0]
        rows.append({"site": name, "cluster": cl, "x_mm": round(x, 2), "y_mm": round(y, 2), "layer": lay,
                     "kind": kind, "note": note})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sites.json").write_text(json.dumps({"board_sha256": brd.data["board_sha256"], "frame": "model / KiCad, mm, y down",
                                               "sites": rows}, indent=1) + "\n")
    for r in rows:
        print(f"{r['site']:12s} {r['cluster']:2s} {r['x_mm']:7.2f} {r['y_mm']:7.2f} {r['layer']:5s} {r['note']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("sites", "plan", "fit", "fit2", "verdict", "selftest"))
    ap.add_argument("--run")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--cluster", default="C1")
    ap.add_argument("--no-fine", action="store_true")
    ap.add_argument("--fits", default="")
    ap.add_argument("--air-op", type=float)
    ap.add_argument("--route", default="face", choices=("face", "jetmix"))
    ap.add_argument("--h-nominal", type=float)
    ap.add_argument("--h-l95-worst", type=float)
    ap.add_argument("--only", default="", help="selftest: comma list of case ids")
    a = ap.parse_args()
    sys.path.insert(0, str(R5DIR))
    import a4_fields
    if a.cmd in ("plan", "fit", "fit2", "selftest", "sites") and not a4_fields.check(R5DIR / "outputs"):
        raise SystemExit(2)
    if a.cmd == "sites":
        sites_table()
    elif a.cmd == "plan":
        run = json.loads(Path(a.run).read_text())
        rs_ = solve_many([dict(run=run, h=h, pitch=0.5) for h in run.get("plan_h", [12, 16, 24, 31, 40])], a.workers)
        for r in rs_:
            print(f"h {r['h']:5.1f}: peak {r['peak_1mm_block']['temperature_c']:.1f} C at "
                  f"({r['peak_1mm_block']['x_mm']}, {r['peak_1mm_block']['y_mm']}) {r['peak_1mm_block']['layer']}; "
                  + ", ".join(f"{n} {r['sites'][n]['t_c']:.1f}" for n in ("LAM_R5.4", "R12.2", "R10.2", "FETROW_B")))
    elif a.cmd == "fit":
        run = json.loads(Path(a.run).read_text())
        f = fit_run(run, workers=a.workers, cluster=a.cluster, final_fine=not a.no_fine)
        OUT.mkdir(parents=True, exist_ok=True)
        p = OUT / f"fit-{run['run_id']}-{a.cluster}.json"
        p.write_text(json.dumps(f, indent=1, default=float) + "\n")
        print(f"h = {f['h']:.2f} W/m2K, U95 {f['U95']:.2f}, L95 {f['h_L95']:.2f}, chi2/dof {f['chi2_dof']:.2f} -> {p}")
    elif a.cmd == "fit2":
        run = json.loads(Path(a.run).read_text())
        f1 = json.loads((OUT / f"fit-{run['run_id']}-{a.cluster}.json").read_text())
        f2 = fit_two_face(run, f1["h"], a.workers, cluster=a.cluster)
        f2["uniform"] = {"h": f1["h"], "U95": f1["U95"], "chi2_dof": f1["chi2_dof"]}
        p = OUT / f"fit2-{run['run_id']}-{a.cluster}.json"
        p.write_text(json.dumps(f2, indent=1, default=float) + "\n")
        print(f"h_top {f2['h_top']:.1f}, h_bottom {f2['h_bottom']:.1f} (uniform {f1['h']:.1f}) -> {p}")
    elif a.cmd == "verdict":
        if a.h_nominal is not None:
            hn, hl = a.h_nominal, a.h_l95_worst
        else:
            fits = [json.loads(Path(p).read_text()) for p in a.fits.split(",") if p]
            hn = fits[0]["h"]                           # nominal condition = the clean-filter, new-fan fit (first)
            hl = min(f["h_L95"] for f in fits)          # worst condition over the sample plan
        print(json.dumps(verdict(hn, hl, a.air_op, a.route), indent=1))
    else:
        selftest(a.workers, tuple(x for x in a.only.split(",") if x))


if __name__ == "__main__":
    main()
