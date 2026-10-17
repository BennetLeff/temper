#!/usr/bin/env python3
"""Summarise the harness runs per device: repro control, edge screens (S1/S2/S4/S5), ZVS margins, gate charge.

    python3 -I analyze.py   -> ../results/switching.json, ../results/switching.md
ZVS method = c33 adoption zvs_node_c.py run(): t_trans = first crossing of the incoming die VDS to 5 % VBUS after T1;
margin(DT) = DT - t_trans; current threshold at a dead time interpolated linearly in 1/IL.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
DT_LOW = {"2EDR_window_min_408": 408.3, "audit_window_min_340": 340.0}


def load(dev, mode):
    p = ROOT / "sims" / dev / mode / "results.json"
    return json.loads(p.read_text()) if p.is_file() else None


def threshold(points, dt_ns):
    pts = sorted((p for p in points if p[1] is not None), key=lambda p: p[0])
    for (i0, t0), (i1, t1) in zip(pts, pts[1:]):
        if (t0 - dt_ns) * (t1 - dt_ns) <= 0 and t0 != t1:
            x0, x1 = 1 / i0, 1 / i1
            return 1 / (x0 + (dt_ns - t0) * (x1 - x0) / (t1 - t0))
    if pts and all(t <= dt_ns for _, t in pts):
        return f"< {pts[0][0]}"
    return None


def edge_summary(rows):
    out = {}
    for case in ("S1", "S2", "S4", "S5"):
        g = [r for r in rows if r.get("case") == case or (r["status"] != "complete" and False)]
        allc = [r for r in rows if r.get("case") == case]
        c = [r for r in allc if r["status"] == "complete"]
        out[case] = {"complete": f"{len(c)}", "pass": sum(bool(r["pass"]) for r in c),
                     "pass_hot_1p9": sum(bool(r["pass_hot"]) for r in c),
                     "max_off_gate_V": round(max(r["off_V"] for r in c), 3) if c else None,
                     "max_die_VDS_V": round(max(r["vds_pk"] for r in c), 1) if c else None,
                     "max_slew2080_Vns": round(max(r.get("slew2080_Vns", 0) for r in c), 1) if c else None,
                     "max_abs_VGS_V": round(max(r["vgs_abs"] for r in c), 2) if c else None}
        if case == "S1":
            out[case]["zvs"] = f"{sum(r['zvs'] for r in c)}/{len(c)}"
    inc = [r for r in rows if r["status"] != "complete"]
    out["not_complete"] = [{k: r[k] for k in ("variant", "leg", "temp_C", "vbus", "il", "dir", "dt_ns")} for r in inc]
    out["total"] = len(rows)
    return out


def zvs_summary(rows):
    ok = [r for r in rows if r["status"] == "complete"]
    out = {}
    for leg in "AB":
        g = [r for r in ok if r["leg"] == leg]
        s37 = [r for r in g if r["il"] == 37]
        w = max(s37, key=lambda r: r["t_trans_ns"])
        e = {"S1_37A_worst_t_trans_ns": round(w["t_trans_ns"], 2),
             "S1_37A_worst_corner": {k: w[k] for k in ("variant", "temp_C", "vbus", "dir")},
             "S1_37A_margin_ns": {k: round(v - w["t_trans_ns"], 1) for k, v in DT_LOW.items()},
             "S1_37A_zvs_at_600": f"{sum(r['zvs'] for r in s37)}/{len(s37)}"}
        thr = {}
        for key in {(r["variant"], r["temp_C"], r["vbus"], r["dir"]) for r in g}:
            pts = [(r["il"], r["t_trans_ns"]) for r in g if (r["variant"], r["temp_C"], r["vbus"], r["dir"]) == key]
            thr["|".join(map(str, key))] = {k: threshold(pts, v) for k, v in DT_LOW.items()}
        worst = {}
        for k in DT_LOW:
            vals = [(t[k], c) for c, t in thr.items() if isinstance(t[k], float)]
            if vals:
                v, c = max(vals)
                worst[k] = {"il_threshold_A": round(v, 2), "corner": c, "margin_vs_37A_A": round(37 - v, 2),
                            "unbracketed": [c2 for c2, t in thr.items() if t[k] is None]}
        e["zvs_threshold_worst"] = worst
        out[leg] = e
    out["incomplete"] = len(rows) - len(ok)
    return out


def gate_charge(rows):
    """|gate-loop charge| per edge: incoming device (turn-on) and outgoing (turn-off) in S1 ZVS rows."""
    res = {}
    for case in ("S1", "S2", "S4", "S5"):
        c = [r for r in rows if r.get("case") == case and r["status"] == "complete" and r.get("q_gate_hs_C") is not None]
        if not c:
            continue
        q = [max(abs(r["q_gate_hs_C"]), abs(r["q_gate_ls_C"])) for r in c]
        res[case] = {"max_nC": round(max(q) * 1e9, 1), "min_nC": round(min(q) * 1e9, 1), "n": len(c)}
    return res


def main():
    devs = sorted(p.name for p in (ROOT / "sims").iterdir() if p.is_dir() and (p / "edge").exists() or
                  (p / "zvs").exists() or (p / "repro").exists())
    res = {}
    for dev in devs:
        d = {}
        rp = load(dev, "repro")
        if rp:
            d["repro"] = {"complete": rp.get("repro_complete"), "max_abs_delta": rp.get("repro_max_abs_delta")}
        ed = load(dev, "edge")
        if ed:
            d["edge"] = edge_summary(ed["rows"])
            d["gate_charge"] = gate_charge(ed["rows"])
        e2 = load(dev, "edge2")
        if e2:
            d["edge_esl1p06"] = edge_summary(e2["rows"])
        cr = load(dev, "cm8rg")
        if cr:
            # CM8 proxy: 029 model with deck RG = R_ext + 1.0 (CM8 Rg,int) - 3.8 (model Rg,int); per R_ext and ESL
            d["cm8_gate_r_proxy"] = {}
            for rext in ("8p2", "10"):
                for esl in (10, 1.06):
                    rows = [r for r in cr["rows"] if r["variant"].startswith(f"cm8ext{rext}") and
                            (r.get("esl_nH", 10) == esl)]
                    if rows:
                        d["cm8_gate_r_proxy"][f"Rext{rext}_ESL{esl}"] = edge_summary(rows)
        cr2 = load(dev, "cm8rg2")
        if cr2:
            for rext in ("12", "15"):
                for esl in (10, 1.06):
                    rows = [r for r in cr2["rows"] if r["variant"].startswith(f"cm8ext{rext}") and r.get("esl_nH", 10) == esl]
                    if rows:
                        d.setdefault("cm8_gate_r_proxy", {})[f"Rext{rext}_ESL{esl}"] = edge_summary(rows)
        zv = load(dev, "zvs")
        if zv:
            d["zvs"] = zvs_summary(zv["rows"])
            d["gate_charge_zvs_sweep"] = gate_charge([dict(r, case="S1") for r in zv["rows"]])
        en = load(dev, "energy")
        if en:
            rows = en["rows"]
            d["energy"] = {"complete": f"{sum(r['status'] == 'complete' for r in rows)}/{len(rows)}"}
        res[dev] = d
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "switching.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
