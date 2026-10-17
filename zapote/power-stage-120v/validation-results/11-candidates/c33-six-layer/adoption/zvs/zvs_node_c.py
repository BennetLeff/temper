#!/usr/bin/env python3
"""DECISIONS 39 adoption item 2: switch-node capacitance against the ZVS dead-time margin, s32 vs s33, per leg.

Method (the project's ZVS check, round17/d2 grid.py and c25-driver/d2_c25.py): the as-built D2 single-transition
deck (F6 + PMEG + -1.6 V off level + 2EDR8259 output resistances, Rg 8.2 ohm; c25 `results/dtband/F6.cir`, sha
55a2058f...) on the native-21 leg matrices (legA21 / legB21 -h0-s9b2-n21). ZVS criterion: the incoming device's die
VDS is <= 5 % of VBUS at its own on command.

That deck has no board switch-node capacitance (only 1 nF snubber per device, C12/C13/C19/C20, and the vendor
model's Coss). This script adds the plane-pair screen's sw-node capacitance (c33-six-layer/loop_screen.py,
screens/loop-screen-b2.json), split by the plane it faces:
    Cbrd_ret  sw -> 0    (hv_ret / leg_ret planes: deck node 0 is the bus-capacitor / shunt return)
    Cbrd_bus  sw -> bus  (bus_p planes)
and measures, per case, t_zvs = the first time after the outgoing off command T1 at which the incoming die VDS falls
to 5 % VBUS. The transition before the on command does not depend on the dead time, so one run per case (DT 600 ns,
the window's top) gives the margin at any dead time:   margin_ns(DT) = DT - (t_zvs - T1).
The ZVS current threshold at a dead time is interpolated from an IL sweep (in 1/IL, where t_zvs is near linear).

Dead time: the 2EDR8259 window at R9/R17 49.9 kOhm 0.1 % is 408.3-569.0 ns (c25 dt_window.json); the audit window's
lower edge is 340 ns (DECISIONS: DT_WINDOW_NS (340, 600)). Both lower edges are reported; the lower is the worst case.

    python3 -I zvs_node_c.py repro              # CBRD = 0 against committed c25 dtband rows
    python3 -I zvs_node_c.py run [--workers 8]  # the sweep -> results.json, summary.json
    python3 -I zvs_node_c.py rerun              # aborted sweep rows again at a 0.1 ns step -> rerun.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import math
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
POWER = HERE.parents[4]  # zapote/power-stage-120v
C25 = POWER / "validation-results/11-candidates/c25-driver"
C33 = HERE.parents[1]
spec = importlib.util.spec_from_file_location("d2_c25", C25 / "scripts/d2_c25.py")
d2c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d2c)  # read-only reuse: VARIANTS, MATRICES, SCREEN, run_d2
run_d2 = d2c.run_d2

REF_DECK = C25 / "results/dtband/F6.cir"
REF_SHA = "55a2058f05c366b046ea1d1b2e8b8d0101f81ffeb5a0ed23cde5c8348e3fc342"
REF_PMEG = "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v/validation-plan/sim-kit/models/vendor/PMEG6030EP.txt"
VENDOR_SHA = {"PMEG6030EP.txt": "0c2892521c7933b99f405d803cef84240050b71c9e1f412088bd7a6c6352b983",
              "IFX_CFD7_650V.lib": "02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b"}

DT_LOW = {"2EDR_window_min_408": 408.3, "audit_window_min_340": 340.0}
DT_RUN = 600  # ns: the transition is measured before the on command, so it is DT-independent

ADD = """
* ---- c33 adoption: board switch-node capacitance (plane-pair screen) and the ZVS crossing time
Cbrd_ret sw 0 {CBRD_RET}
Cbrd_bus sw bus {CBRD_BUS}
.meas tran t_hs_zvs WHEN par('v(xqh.dd)-v(xqh.s)')={0.05*VBUS} FALL=1 TD={T1}
.meas tran t_ls_zvs WHEN par('v(xql.dd)-v(xql.s)')={0.05*VBUS} FALL=1 TD={T1}
"""


def node_caps():
    """Per board and leg: (to-return pF, to-bus pF) from the committed plane-pair screen (fills, plan view)."""
    scr = json.loads((C33 / "screens/loop-screen-b2.json").read_text())["plans"]
    out = {"none": {"A": (0.0, 0.0), "B": (0.0, 0.0)}}
    for board, plan in (("s32", "4L-s32"), ("s33", "6L-A")):
        ov = scr[plan]["switch_node_overlap"]
        out[board] = {}
        for leg, sw in (("A", "sw_a"), ("B", "sw_b")):
            ret = sum(v["pF"] for k, v in ov.items() if k.startswith(sw + " ") and ("hv_ret" in k or "leg_ret" in k))
            bus = sum(v["pF"] for k, v in ov.items() if k.startswith(sw + " ") and "bus_p" in k)
            tot = scr[plan]["switch_node_pF_total"][sw]
            assert abs(ret + bus - tot) < 0.02, (board, leg, ret, bus, tot)
            out[board][leg] = (round(ret, 2), round(bus, 2))
    return out


def deck_text() -> str:
    """The committed as-built c25 deck, with only its PMEG include path pointed at this checkout's sim-kit copy."""
    ref = REF_DECK.read_text()
    assert hashlib.sha256(ref.encode()).hexdigest() == REF_SHA
    vend = run_d2.KIT / "models" / "vendor"
    for name, sha in VENDOR_SHA.items():
        assert hashlib.sha256((vend / name).read_bytes()).hexdigest() == sha, name
    assert ref.count(REF_PMEG) == 1
    deck = ref.replace(REF_PMEG, str(vend / "PMEG6030EP.txt"))
    assert deck.count("\n.end") == 1
    return deck.replace("\n.end", "\n" + ADD + ".end")


def one(job, deck: Path, out: Path, caps, trmax="0.2n"):
    board, variant, leg, temp, vbus, il, d, esl, dt = job
    roh, rol, rg = d2c.VARIANTS[variant]
    cret, cbus = caps[board][leg]
    name = f"{board}_{variant}_{leg}_T{temp}_v{vbus}_i{il}_d{d}_esl{esl}_dt{dt}"
    p = run_d2.matrix_params(run_d2.read_L(str(d2c.MATRICES[leg])))
    p.update(TJ=str(temp), VBUS=str(vbus), IL=str(il), DIR=str(d), DT=f"{dt}n", LESL=f"{esl}n", LSHUNT="2n",
             TRMAX=trmax, ROH=str(roh), ROL=str(rol), RG=str(rg),
             CBRD_RET=f"{max(cret, 1e-6)}p", CBRD_BUS=f"{max(cbus, 1e-6)}p")  # 1e-6 pF = "none"
    keep = out / "runs" / name
    r = run_d2.run(deck, p, keep=keep)
    m = r["meas"]
    inc = "hs" if d == 0 else "ls"
    row = {"board": board, "variant": variant, "leg": leg, "temp_C": temp, "vbus": vbus, "il": il, "dir": d,
           "esl_nH": esl, "dt_run_ns": dt, "cbrd_ret_pF": cret, "cbrd_bus_pF": cbus, "trmax": trmax}
    t1 = 2e-6  # deck T1
    tz = m.get(f"t_{inc}_zvs")
    if r["aborted"]:
        row["status"] = "aborted"
        return row
    shutil.rmtree(keep, ignore_errors=True)
    row.update(status="complete", incoming_V_at_on=m.get(f"vds_{inc}_at_on"),
               vds_pk=max(m.get("vds_ls_die_pk", float("nan")), m.get("vds_hs_die_pk", float("nan"))),
               t_trans_ns=(tz - t1) * 1e9 if tz is not None else None)
    row["zvs_at_dt_run"] = row["incoming_V_at_on"] is not None and row["incoming_V_at_on"] <= 0.05 * vbus
    return row


def repro(workers):
    """CBRD ~ 0 must reproduce committed c25 dtband rows (S1, both legs/directions, three temperatures)."""
    ref = json.loads((C25 / "results/dtband/results.json").read_text())
    want = [r for r in ref if r["case"] == "S1" and r["variant"] == "edr_rg8p2" and r["dt_ns"] == 408 and r["esl_nH"] == 10
            and r["status"] == "complete"]
    out = HERE / "repro"
    out.mkdir(parents=True, exist_ok=True)
    deck = out / "F6zvs.cir"
    deck.write_text(deck_text())
    caps = node_caps()
    jobs = [("none", w["variant"], w["leg"], w["temp_C"], w["vbus"], w["il"], w["dir"], w["esl_nH"], w["dt_ns"]) for w in want]
    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(lambda j: one(j, deck, out, caps), jobs))
    worst = 0.0
    for w, r in zip(want, rows):
        r["committed_incoming_V"], r["committed_vds_pk"] = w["incoming_V"], w["vds_pk"]
        worst = max(worst, abs(r["incoming_V_at_on"] - w["incoming_V"]), abs(r["vds_pk"] - w["vds_pk"]))
    res = {"cases": len(rows), "max_abs_delta_V": worst, "rows": rows}
    (out / "repro.json").write_text(json.dumps(res, indent=1) + "\n")
    print(f"repro: {len(rows)} cases, max |delta| incoming / VDS {worst:.4g} V")


def threshold(points, dt_ns):
    """IL at which t_trans = dt_ns, linear in 1/IL between bracketing sweep points (None if not bracketed)."""
    pts = sorted((p for p in points if p[1] is not None), key=lambda p: p[0])
    for (i0, t0), (i1, t1) in zip(pts, pts[1:]):
        if (t0 - dt_ns) * (t1 - dt_ns) <= 0 and t0 != t1:
            x0, x1 = 1 / i0, 1 / i1
            x = x0 + (dt_ns - t0) * (x1 - x0) / (t1 - t0)
            return 1 / x
    if pts and all(t <= dt_ns for _, t in pts):
        return f"< {pts[0][0]}"
    return None


def run(workers):
    out = HERE
    deck = out / "F6zvs.cir"
    deck.write_text(deck_text())
    caps = node_caps()
    ils = (37, 25, 20, 15, 10, 7, 5, 3)
    corners = [("edr_rg8p2", t) for t in (27, 100, 150)] + [(v, t) for v in ("edr_rg8p2_weak", "edr_rg8p2_strong") for t in (27, 150)]
    jobs = [(b, v, leg, t, vb, il, d, 10, DT_RUN) for b in ("none", "s32", "s33") for (v, t) in corners for leg in "AB"
            for vb in (170, 198, 280) for il in ils for d in (0, 1)]
    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(lambda j: one(j, deck, out, caps), jobs))
    (out / "results.json").write_text(json.dumps(rows, indent=1) + "\n")

    # summary: per board / leg, the worst (longest) transition at 37 A and margins at the low dead-time edges;
    # ZVS current thresholds per corner, worst (highest) per board / leg
    summ = {"node_caps_pF_ret_bus": caps, "dt_low_edges_ns": DT_LOW, "il_sweep_A": ils, "boards": {}}
    ok = [r for r in rows if r["status"] == "complete"]
    summ["incomplete"] = [r for r in rows if r["status"] != "complete"]
    for b in ("none", "s32", "s33"):
        for leg in "AB":
            g = [r for r in ok if r["board"] == b and r["leg"] == leg]
            s37 = [r for r in g if r["il"] == 37]
            w = max(s37, key=lambda r: r["t_trans_ns"])
            e = {"cbrd_pF_ret_bus": caps[b][leg], "S1_37A_cases": len(s37),
                 "S1_37A_zvs_at_600ns": f"{sum(r['zvs_at_dt_run'] for r in s37)}/{len(s37)}",
                 "S1_37A_worst_t_trans_ns": round(w["t_trans_ns"], 2),
                 "S1_37A_worst_corner": {k: w[k] for k in ("variant", "temp_C", "vbus", "dir")},
                 "S1_37A_margin_ns": {k: round(v - w["t_trans_ns"], 1) for k, v in DT_LOW.items()}}
            thr = {}
            for key in {(r["variant"], r["temp_C"], r["vbus"], r["dir"]) for r in g}:
                pts = [(r["il"], r["t_trans_ns"]) for r in g if (r["variant"], r["temp_C"], r["vbus"], r["dir"]) == key]
                thr["|".join(map(str, key))] = {k: threshold(pts, v) for k, v in DT_LOW.items()}
            worst = {}
            for k in DT_LOW:
                vals = [(t[k], c) for c, t in thr.items() if isinstance(t[k], float)]
                unb = [c for c, t in thr.items() if t[k] is None]
                if vals:
                    v, c = max(vals)
                    worst[k] = {"il_threshold_A": round(v, 2), "corner": c, "margin_vs_37A_A": round(37 - v, 2),
                                "unbracketed_corners": unb}
            e["zvs_threshold_worst"] = worst
            e["zvs_threshold_by_corner"] = thr
            summ["boards"].setdefault(b, {})[leg] = e
    for leg in "AB":
        a, c = summ["boards"]["s32"][leg], summ["boards"]["s33"][leg]
        summ[f"delta_s33_minus_s32_leg{leg}"] = {
            "S1_37A_worst_t_trans_ns": round(c["S1_37A_worst_t_trans_ns"] - a["S1_37A_worst_t_trans_ns"], 2),
            **{f"il_threshold_A@{k}": round(c["zvs_threshold_worst"][k]["il_threshold_A"]
                                             - a["zvs_threshold_worst"][k]["il_threshold_A"], 2)
               for k in DT_LOW if k in a["zvs_threshold_worst"] and k in c["zvs_threshold_worst"]}}
    files = [d2c.MATRICES["A"], d2c.MATRICES["B"], REF_DECK, deck, Path(__file__), C25 / "scripts/d2_c25.py",
             POWER / "validation-results/01-switching-parasitics/round17/d2/run_d2.py", C33 / "screens/loop-screen-b2.json"]
    summ["identity"] = {str(p.relative_to(POWER)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    summ["identity"]["vendor"] = VENDOR_SHA
    (out / "summary.json").write_text(json.dumps(summ, indent=1, default=str) + "\n")
    for b in ("none", "s32", "s33"):
        for leg in "AB":
            e = summ["boards"][b][leg]
            print(b, leg, e["cbrd_pF_ret_bus"], "37A worst t", e["S1_37A_worst_t_trans_ns"], "margins", e["S1_37A_margin_ns"],
                  "zvs", e["S1_37A_zvs_at_600ns"], "thr", {k: v["il_threshold_A"] for k, v in e["zvs_threshold_worst"].items()})


def rerun(workers):
    """Aborted rows of results.json again at a 0.1 ns maximum step (c25's treatment of an isolated abort)."""
    rows = json.loads((HERE / "results.json").read_text())
    caps = node_caps()
    deck = HERE / "F6zvs.cir"
    keys = ("board", "variant", "leg", "temp_C", "vbus", "il", "dir", "esl_nH", "dt_run_ns")
    bad = [r for r in rows if r["status"] != "complete"]
    with ThreadPoolExecutor(workers) as ex:
        new = list(ex.map(lambda r: one(tuple(r[k] for k in keys), deck, HERE / "rerun", caps, "0.1n"), bad))
    near = [r for r in rows if r["status"] == "complete" and all(r[k] == b[k] for b in bad for k in keys if k != "il")]
    (HERE / "rerun.json").write_text(json.dumps({"aborted_at_0p2ns": bad, "rerun_0p1ns": new,
                                                 "same_corner_other_currents_0p2ns": near}, indent=1) + "\n")
    for r in new:
        print(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["repro", "run", "rerun"])
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    {"repro": repro, "run": run, "rerun": rerun}[a.mode](a.workers)


if __name__ == "__main__":
    main()
