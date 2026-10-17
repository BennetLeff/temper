#!/usr/bin/env python3
"""Task 05 round 4: pan/line/power grid on the ASSUMED coil/pan basis, under the
native-21 operating envelope, with ngspice (sim-kit runner, <= 8 workers).

Envelope applied to every case (sources in the round README):
  - switching frequency 35-60 kHz (firmware/components/power/fullbridge_adapter.c);
  - f >= 1.05 x loaded resonance (ZVS_MARGIN_MIN of scripts/check_pll_range_consistency.py);
  - tank current <= 22 A RMS over the line half-cycle (DECISIONS 2026-10-08 envelope;
    input_limits.c tank_limit_a = 22);
  - power-stage input I_ps,est = P / (eta_min V_line) <= 11.1 A hold (DECISIONS 2026-10-08,
    input_limits.c eta_min = 0.93), i.e. P <= 10.32 W/V x V_line.
The deck's P is total tank resistive dissipation (pan + coil); the ideal deck has no
bridge loss, so the ideal P equals inverter output power.

Search: for each case the smallest feasible frequency in [f_floor, 60 kHz] (power falls
monotonically with frequency above resonance) by bisection to 10 Hz, bracketed by a
first-harmonic estimate. Status:
  MET            requested power delivered (within 1 %);
  TANK_LIMITED   22 A RMS binds;  INPUT_LIMITED  11.1 A hold binds;
  FLOOR_LIMITED  the 35 kHz / 1.05 f_res floor binds (cannot go lower in frequency);
  BURST_REQUIRED even 60 kHz exceeds the request (needs burst/pulse-density control).

Usage:
  run_grid.py [--cres 0.54u] [--tag grid] [--classes all|main|supp] [--workers 8]
              [--l0-scale 1.0] [--c-scale 1.0] [--corners low,nom,high]
"""
import argparse
import csv
import json
import math
import os
import shutil
import sys
import tempfile
import time
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
KIT = HERE.parents[3] / "validation-plan" / "sim-kit"
sys.path.insert(0, str(KIT / "common"))
sys.path.insert(0, str(HERE))
import run_ngspice  # noqa: E402
import basis as B  # noqa: E402

DECK = HERE / "tank_basis.cir"
LINES = [108.0, 120.0, 140.0]
POWERS = [1710.0, 855.0, 300.0]
F_MIN, F_MAX = 35e3, 60e3
ZVS_MARGIN = 1.05
I_TANK_MAX = 22.0
I_PS_HOLD, ETA_MIN = 11.1, 0.93


def corner_params(pan, which, l0):
    c = B.corner(pan, which)
    return {"L0U": l0, "KL40": c["kl40"], "BETA": B.COIL["beta_kl"][0], "Q40": c["q40"],
            "GAMMA": B.COIL["gamma_coil"][0], "R40": c["r40"], "ALPHA": c["alpha"]}


def lr(p, f):
    fr = f / 40e3
    L = p["L0U"] * 1e-6 * p["KL40"] * fr ** p["BETA"]
    R = p["L0U"] * (p["Q40"] * fr ** p["GAMMA"] + p["R40"] * fr ** p["ALPHA"])
    return L, R


def f_res(p, C):
    f = 30e3
    for _ in range(80):
        L, _ = lr(p, f)
        f = 1 / (2 * math.pi * math.sqrt(L * C))
    return f


def fha(p, C, V, f):
    """First-harmonic estimate: line-averaged P and tank RMS for the square-wave drive."""
    L, R = lr(p, f)
    X = 2 * math.pi * f * L - 1 / (2 * math.pi * f * C)
    z2 = R * R + X * X
    i_rms = (2 * math.sqrt(2) / math.pi) * V / math.sqrt(z2)
    return i_rms * i_rms * R, i_rms, math.degrees(math.atan2(X, R))


def sim(p, C, V, f):
    # falling drive edge (inductive current should be > 0 there) nearest the line crest
    k = round(2 * f * 4.16667e-3)
    if k % 2 == 0:
        k += 1
    params = {**{k2: f"{v:.8g}" for k2, v in p.items()}, "VRMS": f"{V:g}", "FREQ": f"{f:.3f}",
              "CRES": f"{C:.6e}", "TEDGE": f"{k / (2 * f):.9e}"}
    work = Path(tempfile.mkdtemp(prefix="t05r4-"))
    try:
        r = run_ngspice.run(DECK, params, keep=work)
    finally:
        shutil.rmtree(work, ignore_errors=True)  # also removes the vendor-lib copy
    need = ("i_rms", "i_pk", "vc_pk", "vc_rms", "p_avg", "i_rms_crest", "i_edge")
    if r["aborted"] or any(n not in r["meas"] for n in need):
        raise RuntimeError(f"ngspice failed {params}: {r['log_tail']}")
    m = dict(r["meas"])
    m["freq"] = f
    return m


def solve(case):
    p, C, V, P_req = case["p"], case["C"], case["V"], case["P_req"]
    P_cap = I_PS_HOLD * ETA_MIN * V
    P_tgt = min(P_req, P_cap)
    fr = f_res(p, C)
    f_floor = max(F_MIN, ZVS_MARGIN * fr)
    nsim = 0

    def feasible(m):
        return m["p_avg"] <= P_tgt * 1.0005 and m["i_rms"] <= I_TANK_MAX

    m_lo = sim(p, C, V, f_floor)
    nsim += 1
    if f_floor > F_MAX:
        status, m = "NO_WINDOW", m_lo
    elif feasible(m_lo):
        m = m_lo
        status = "MET" if m["p_avg"] >= 0.99 * P_req else "FLOOR_LIMITED"
    else:
        m_hi = sim(p, C, V, F_MAX)
        nsim += 1
        if not feasible(m_hi):
            status, m = "BURST_REQUIRED", m_hi
        else:
            lo, hi, m = f_floor, F_MAX, m_hi
            # FHA bracket: smallest f where the FHA estimate meets both limits
            g = f_floor
            while g < F_MAX:
                pf, i_f, _ = fha(p, C, V, g)
                if pf <= P_tgt and i_f <= I_TANK_MAX:
                    break
                g += 100.0
            for cand in (g - 1500.0, g + 1500.0):
                if lo < cand < hi:
                    mc = sim(p, C, V, cand)
                    nsim += 1
                    if feasible(mc):
                        hi, m = cand, mc
                    else:
                        lo = cand
            while hi - lo > 10.0:
                mid = 0.5 * (lo + hi)
                mm = sim(p, C, V, mid)
                nsim += 1
                if feasible(mm):
                    hi, m = mid, mm
                else:
                    lo = mid
            # which limit binds at the solution
            r_p = m["p_avg"] / P_req
            r_cap = m["p_avg"] / P_cap
            r_i = m["i_rms"] / I_TANK_MAX
            if r_p >= 0.99:
                status = "MET"
            elif r_i >= max(r_cap, 0.0) and r_i > 0.99:
                status = "TANK_LIMITED"
            elif r_cap > 0.99:
                status = "INPUT_LIMITED"
            else:
                status = "TANK_LIMITED" if r_i >= r_cap else "INPUT_LIMITED"
    L, R = lr(p, m["freq"])
    _, _, phase = fha(p, C, V, m["freq"])
    out = {
        "case": case["id"], "pan_class": case["pan"], "corner": case["corner"], "line_vrms": V,
        "p_request_w": P_req, "p_input_cap_w": round(P_cap, 1), "status": status,
        "freq_hz": round(m["freq"], 1), "f_res_hz": round(fr, 1), "f_over_fres": round(m["freq"] / fr, 4),
        "f_floor_hz": round(f_floor, 1), "fha_phase_deg": round(phase, 2),
        "L_eq_uH": round(L * 1e6, 3), "R_eq_ohm": round(R, 4), "C_bank_uF": round(C * 1e6, 4),
        "p_tank_w": round(m["p_avg"], 1), "p_pan_w": round(m["p_avg"] * (R - p["L0U"] * p["Q40"] *
                                                                         (m["freq"] / 40e3) ** p["GAMMA"]) / R, 1),
        "i_ps_est_a": round(m["p_avg"] / (ETA_MIN * V), 3),
        "i_tank_rms_a": round(m["i_rms"], 3), "i_tank_rms_crest_a": round(m["i_rms_crest"], 3),
        "i_tank_pk_a": round(m["i_pk"], 3), "i_edge_crest_a": round(m["i_edge"], 3),
        "vc_pk_v": round(m["vc_pk"], 2), "vc_rms_v": round(m["vc_rms"], 2),
        "ct_sec_pk_v": round(m["i_pk"] / 100 * 1.5, 4), "n_sims": nsim,
        **{f"param_{k}": v for k, v in p.items()},
    }
    return out


def build_cases(args):
    pans = {}
    if args.classes in ("all", "main"):
        pans.update(B.PANS)
    if args.classes in ("all", "supp"):
        pans.update(B.SUPPLEMENTAL)
    C = float(args.cres.replace("u", "e-6")) * args.c_scale
    cases = []
    for name, pan in pans.items():
        for which in args.corners.split(","):
            p = corner_params(pan, which, 70.0 * args.l0_scale)
            for V in LINES:
                for P in POWERS:
                    cases.append({"id": f"{name}-{which}-{int(V)}v-{int(P)}w", "pan": name, "corner": which,
                                  "p": p, "C": C, "V": V, "P_req": P})
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cres", default="0.54u")
    ap.add_argument("--c-scale", type=float, default=1.0)
    ap.add_argument("--l0-scale", type=float, default=1.0)
    ap.add_argument("--tag", default="grid")
    ap.add_argument("--classes", default="all")
    ap.add_argument("--corners", default="low,nom,high")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    assert args.workers <= 8
    cases = build_cases(args)
    out_csv = ROOT / "outputs" / f"{args.tag}-cases.csv"
    prog = ROOT / "outputs" / f"{args.tag}-progress.jsonl"
    t0 = time.time()
    rows = []
    with Pool(args.workers) as pool, open(prog, "w") as ph:
        for r in pool.imap_unordered(solve, cases):
            rows.append(r)
            ph.write(json.dumps({"case": r["case"], "status": r["status"], "t_s": round(time.time() - t0, 1)}) + "\n")
            ph.flush()
    order = {c["id"]: i for i, c in enumerate(cases)}
    rows.sort(key=lambda r: order[r["case"]])
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} cases -> {out_csv.relative_to(ROOT)} in {time.time() - t0:.0f} s, "
          f"{sum(r['n_sims'] for r in rows)} ngspice runs")


if __name__ == "__main__":
    main()
