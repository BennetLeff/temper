#!/usr/bin/env python3
"""MOSFET loss and sink/junction budget per candidate device, at the nominal, c28 and 29.4 A trip points.

Copied and parametrised from (read-only originals):
  * R33 thermal/requirement.py solve()  (/Users/bennet/Desktop/temper/output/temper-r33-studies/09-coil-210-strayfield/
    thermal/requirement.py; itself D-18's power-stage losses.py solve()): common sink, upstream air heating, device order
  * round6-full-power/scripts/board_side.py fets(): basis A (D-18 switching proxy) and basis B (m11 ZVS estimate) at the
    22..30 A ceilings, R_SA 0.29 + pedestal 0.0161, R_cs 0.634 (m11 2 mm AlN, conservative), 13 CFM, 50 C inlet, BR1 0.378
  * m11 stack_calc.py: tab area, Rcs; DECISIONS 2026-10-12 item 15: K1 sink R_SA 0.214 C/W.
Controls (must pass before any candidate row is written):
  C1 this solve() == requirement.py solve() on the round-6 rows (basis A) for the as-built device
  C2 basis A / basis B rows == committed round6 outputs/board-side-fets.csv (28 A, 40/45/50 kHz)
New basis D (this study): conduction with the device's own Rds(T) + switching/dead-time heat from the as-built deck with the
device's vendor model (harness.py energy grid), averaged over the line cycle of the case (bus = Vpk|sin|, turn-off current =
2 Irms |sin| sin(phi), phi = 60 deg FHA phase [round6: >= 50 deg everywhere]).

    python3 -I thermal.py            -> ../results/thermal.json, ../results/thermal.md
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
POWER = Path(__file__).resolve().parents[4]   # zapote/power-stage-120v (committed copy, DECISIONS 49)
R33 = Path(__import__("os").environ.get("TEMPER_R33_REQUIREMENT", "/Users/bennet/Desktop/temper/output/temper-r33-studies/09-coil-210-strayfield/thermal/requirement.py"))   # main checkout output/ (not in this worktree)
R6 = POWER / "validation-results/05-resonant-tank-envelope/round6-full-power/outputs/board-side-fets.csv"

MOS = ("Q5", "Q6", "Q3", "Q2")
ORDER = ("Q5", "Q6", "Q3", "Q2", "BR1")
R_PED = 0.0161
RCS = 0.634          # m11 2 mm AlN + 2x grease, conservative upper (stack-calc.txt)
BR1_RCS = 0.378
FLOW = 13            # CFM, D-18 requirement at R_SA 0.29 (DECISIONS R32 item 2)
TIN = 50.0
SINKS = {"S8": 0.29, "K1": 0.214}   # R_SA C/W: D-18 limit / K1 contingency (DECISIONS 2026-10-12 item 15)
D18_SW_36K = {"Q2": 12.7574, "Q5": 12.7574, "Q3": 13.1537, "Q6": 13.1537}

# Devices. rds_max25 / r150_over_r25 (typ 150 C / typ 25 C) cited in DEVICES.md; vendor model for basis D.
DEVICES = json.loads((HERE / "devices.json").read_text())


def rds(dev, t):
    d = DEVICES[dev]
    return d["rds_max25"] * (1 + (d["r150_over_r25"] - 1) * (t - 25) / 125)


def solve(case, rsa, p_dev_fn, rjc, rcs=RCS, flow=FLOW, order=ORDER, bridge_rcs=BR1_RCS, ambient=TIN):
    """requirement.py solve() with the per-device power as a function of its own Tj."""
    tj = {r: ambient for r in order}
    iin = float(case["target_w"]) / (.95 * float(case["vrms_v"]))
    bridge = 2 * 1.05 * iin * 2 * math.sqrt(2) / math.pi
    cpflow = 1.09 * 1005 * flow * .00047194745
    for _ in range(400):
        powers = {"BR1": bridge}
        for ref in MOS:
            powers[ref] = p_dev_fn(ref, tj[ref])
        psink = sum(powers.values())
        ts = ambient + rsa * psink
        upstream, nxt = 0.0, {}
        for ref in order:
            local = ts + upstream / cpflow
            rpath = .25 + bridge_rcs if ref == "BR1" else rjc + rcs
            nxt[ref] = local + powers[ref] * rpath
            upstream += powers[ref]
        delta = max(abs(nxt[r] - tj[r]) for r in order)
        tj = nxt
        if max(tj.values()) > 400:
            return None
        if delta < 1e-8:
            break
    return {"max_tj": max(tj[r] for r in MOS), "worst": max(MOS, key=tj.get), "psink": psink, "powers": powers,
            "tj": tj, "ts": ts}


# ---------------- switching energy (basis D) from the harness energy grid ----------------
def load_energy(model):
    p = ROOT / "sims" / model / "energy" / "results.json"
    if not p.is_file():
        return None
    rows = [r for r in json.loads(p.read_text())["rows"] if r["status"] == "complete"]
    grid = {}
    for r in rows:
        grid.setdefault((r["leg"], r["temp_C"]), {}).setdefault((r["vbus"], r["il"]), {})[r["dir"]] = r["e_extra_J"]
    return grid


def bilin(tab, v, i):
    vs = sorted({k[0] for k in tab})
    is_ = sorted({k[1] for k in tab})
    v = min(max(v, vs[0]), vs[-1])
    i = min(max(i, is_[0]), is_[-1])

    def br(xs, x):
        for a, b in zip(xs, xs[1:]):
            if a <= x <= b:
                return a, b
        return xs[-2], xs[-1]
    v0, v1 = br(vs, v)
    i0, i1 = br(is_, i)
    fv = (v - v0) / (v1 - v0)
    fi = (i - i0) / (i1 - i0)
    g = lambda a, b: tab[(a, b)]
    return (g(v0, i0) * (1 - fv) * (1 - fi) + g(v1, i0) * fv * (1 - fi) + g(v0, i1) * (1 - fv) * fi + g(v1, i1) * fv * fi)


def p_switch_leg(grid, leg, temp, vpk, irms, f, phi_deg=60.0, n=360):
    """Leg switching/dead-time heat (both devices) averaged over the half line cycle: 2 transitions per period."""
    tab0 = {k: v[0] for k, v in grid[(leg, temp)].items() if 0 in v and 1 in v}
    tab1 = {k: v[1] for k, v in grid[(leg, temp)].items() if 0 in v and 1 in v}
    s = 0.0
    for k in range(n):
        th = (k + 0.5) * math.pi / n
        v = vpk * math.sin(th)
        i = 2 * irms * math.sin(th) * math.sin(math.radians(phi_deg))
        s += bilin(tab0, v, i) + bilin(tab1, v, i)
    return f * s / n


CASES = {  # (I tank RMS line-cycle, f, line V, input W); c28 at the 50 kHz worst of DECISIONS item 15
    "nominal_21p47A_32p8kHz": (21.47, 32773.0, 120.0, 1239.0),   # task 03 example tank; input at the 11.1 A hold
    "c28_28A_45kHz": (28.0, 45e3, 120.0, 1239.0),
    "c28_28A_50kHz": (28.0, 50e3, 120.0, 1239.0),
    "trip_29p4A_50kHz": (29.4, 50e3, 120.0, 1239.0),
}


def basis_rows(dev):
    d = DEVICES[dev]
    grid = load_energy(d["model"]) if d.get("model") else None
    out = {}
    for cname, (i, f, V, P) in CASES.items():
        case = {"frequency_hz": f, "i_rms_a": i, "target_w": P, "vrms_v": V}
        row = {}
        cond = lambda t: i * i / 2 * rds(dev, t)
        # basis B': m11 ZVS form with this device's conduction (+0.33 W covered turn-off, as m11/round6)
        # basis A: D-18's switching proxy (12.7574 W HS / 13.1537 W LS at 36 kHz, derived from the as-built device's deck;
        # applied unchanged to a candidate = no credit for its lower Eoss/Qg) with this device's conduction
        row["A_D18_proxy"] = {}
        for sk, rsa in SINKS.items():
            r = solve(case, rsa + R_PED, lambda ref, t: cond(t) + D18_SW_36K[ref] * f / 36000, d["rjc"])
            row["A_D18_proxy"][sk] = {"tj_max": round(r["max_tj"], 1), "psink": round(r["psink"], 1),
                                      "p_fet": round(r["powers"][r["worst"]], 2)} if r else {"tj_max": "runaway"}
        row["B_cond_plus_0p33"] = {}
        for sk, rsa in SINKS.items():
            r = solve(case, rsa + R_PED, lambda ref, t: cond(t) + 0.33, d["rjc"])
            row["B_cond_plus_0p33"][sk] = {"tj_max": round(r["max_tj"], 1), "psink": round(r["psink"], 1),
                                          "p_fet": round(r["powers"][r["worst"]], 2)}
        if grid:
            psw = {}
            for leg in "AB":
                for t in (100, 150):
                    psw[(leg, t)] = p_switch_leg(grid, leg, t, V * math.sqrt(2), i, f) / 2   # per device
            # interpolate per device in Tj between 100 and 150 C (clamped), leg A = Q2/Q3, leg B = Q5/Q6
            leg_of = {"Q2": "A", "Q3": "A", "Q5": "B", "Q6": "B"}

            def pdev(ref, t, _psw=psw):
                lg = leg_of[ref]
                a, b = _psw[(lg, 100)], _psw[(lg, 150)]
                x = min(max((t - 100) / 50, 0), 1)
                return cond(t) + a + (b - a) * x
            row["D_deck"] = {"p_sw_per_device_W": {f"{k[0]}{k[1]}": round(v, 3) for k, v in psw.items()}}
            for sk, rsa in SINKS.items():
                r = solve(case, rsa + R_PED, pdev, d["rjc"])
                row["D_deck"][sk] = {"tj_max": round(r["max_tj"], 1), "worst": r["worst"], "psink": round(r["psink"], 1),
                                     "p_fet": {k: round(v, 2) for k, v in r["powers"].items()},
                                     "tj": {k: round(v, 1) for k, v in r["tj"].items()}}
        out[cname] = row
    return out


def controls():
    spec = importlib.util.spec_from_file_location("requirement", R33)
    RQ = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(RQ)
    ref = [r for r in csv.DictReader(R6.open()) if r["line_V"] == "120.0"]
    worst = {"C1_tj": 0.0, "C2_A_tj": 0.0, "C2_B_tj": 0.0}
    for r in ref:
        i, f = float(r["I_tank_A"]), float(r["f_kHz"]) * 1e3
        case = {"frequency_hz": f, "i_rms_a": i, "target_w": 1239.0, "vrms_v": 120.0}
        a = RQ.solve(case, 50.0, 0.29 + RQ.R_PED, 0.634, 13, ORDER, 0.378)
        mine = solve(case, 0.29 + R_PED,
                     lambda ref_, t: i * i / 2 * RQ.rds(t) + RQ.SW[ref_] * f / 36000, 0.28)
        worst["C1_tj"] = max(worst["C1_tj"], abs(a["max_tj"] - mine["max_tj"]))
        worst["C2_A_tj"] = max(worst["C2_A_tj"], abs(round(mine["max_tj"], 1) - float(r["A_tj_max_C"])))
        # basis B as round6 board_side.fets() (isothermal sink, LS +0.33, HS +0.26)
        p_fet = 6.78 * (i / 21.47) ** 2 + 0.33
        p_br1 = 2 * 1.05 * 0.9 * (1239.0 / (0.95 * 120.0))
        tj_b = 50.0 + (0.29 + R_PED) * (2 * (p_fet - 0.07) + 2 * p_fet + p_br1) + p_fet * (0.28 + 0.634)
        worst["C2_B_tj"] = max(worst["C2_B_tj"], abs(round(tj_b, 1) - float(r["B_tj_C"])))
    ok = worst["C1_tj"] < 1e-6 and worst["C2_A_tj"] <= 0.05 and worst["C2_B_tj"] <= 0.05
    return {"max_abs_delta_C": worst, "pass": ok, "rows": len(ref)}


def main():
    c = controls()
    print("controls", c)
    assert c["pass"], c
    res = {"controls": c, "assumptions": {"Tin_C": TIN, "R_SA": SINKS, "R_pedestal": R_PED, "Rcs": RCS, "flow_CFM": FLOW,
                                          "BR1_rcs": BR1_RCS, "phi_deg": 60, "cases": CASES},
           "devices": {}}
    for dev in DEVICES:
        res["devices"][dev] = {"meta": DEVICES[dev], "cases": basis_rows(dev)}
    # screen: the largest RDS(on),max at 25 C (SJ typical 150/25 ratio 2.2, RthJC 0.28) that keeps the worst FET at
    # Tj <= 125 C with the ZVS basis (conduction + 0.33 W), per case and sink. Any SJ part above it is excluded on
    # conduction alone, before switching is considered.
    scr = {}
    for cname, (i, f, V, P) in CASES.items():
        case = {"frequency_hz": f, "i_rms_a": i, "target_w": P, "vrms_v": V}
        for sk, rsa in SINKS.items():
            lo, hi = 0.005, 0.1
            for _ in range(50):
                mid = (lo + hi) / 2
                r = solve(case, rsa + R_PED, lambda ref, tt, m=mid: i * i / 2 * m * (1 + 1.2 * (tt - 25) / 125) + 0.33, 0.28)
                lo, hi = (mid, hi) if (r and r["max_tj"] <= 125.0) else (lo, mid)
            scr[f"{cname}|{sk}"] = round(lo * 1e3, 2)
    res["rds_max25_ceiling_mOhm_ZVS_basis"] = scr
    print("RDS(on),max(25C) ceiling for Tj<=125 C, ZVS basis:", scr)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "thermal.json").write_text(json.dumps(res, indent=1) + "\n")
    lines = ["| device | case | basis | sink | worst Tj C | sink W | P worst FET W |", "|---|---|---|---|---|---|---|"]
    for dev, dd in res["devices"].items():
        for cn, row in dd["cases"].items():
            for basis, b in row.items():
                for sk in SINKS:
                    if sk in b:
                        pf = b[sk]["p_fet"]
                        pw = max(v for k, v in pf.items() if k != "BR1") if isinstance(pf, dict) else pf
                        lines.append(f"| {dev} | {cn} | {basis} | {sk} | {b[sk]['tj_max']} | {b[sk]['psink']} | {pw} |")
    (ROOT / "results" / "thermal.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
