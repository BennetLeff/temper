#!/usr/bin/env python3
"""Summarise the switching grids per candidate (trade.py full / s4b / s2q), against each part's own ratings.

Per device (sims/<dev>/<grid>/results.json):
  S1  ZVS count, worst t_trans (first crossing of the incoming die VDS to 5 % VBUS after T1) and its margin against the
      dead-time window: 2EDR8259X at R9/R17 49.9 k = 408.3-569.0 ns (c25 dt_window.json), audit lower edge 340 ns.
  S2  worst die VDS (585 V screen), S4 worst die VDS (520 V), 20-80 % switch-node slew (= the commutated diode's
      dv/dt), diF/dt 75-25 %, Irr peak; S5 slew; worst off-gate (die VGS of the off device after the partner's on
      command) against 3.0 V / 1.9 V hot (c25) and against the part's own VGS(th),min at Tj max (device_data.json).
  Gate charge per edge (S2 worst, 'q' variants) for the B3 gate-heat estimate (c40).
Diode dv/dt check: S4 max slew <= 0.8 x the part's reverse-diode dv/dt rating (ledger rule); where a part states no
diode rating the MOSFET dv/dt rating (or 'not rated') is used and said so.

    python3 -I c20_switching.py   -> ../results/switching.json, ../results/switching.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C55, SIMS  # noqa: E402

DATA = json.loads((Path(__file__).resolve().parent / "device_data.json").read_text())
DT_WIN = {"340": 340.0, "408": 408.3, "569": 569.0}


def load(dev, grid):
    p = SIMS / dev / grid / "results.json"
    return json.loads(p.read_text()) if p.is_file() else None


def summ(rows):
    ok = [r for r in rows if r["status"] == "complete"]
    s = {"runs": len(rows), "complete": len(ok)}
    for case in ("S1", "S2", "S4", "S5"):
        c = [r for r in ok if r["case"] == case]
        if not c:
            continue
        d = {"n": len(c), "max_vds_V": round(max(r["vds_pk"] for r in c), 1),
             "max_off_V": round(max(r["off_V"] for r in c), 3),
             "max_vgs_abs_V": round(max(r["vgs_abs"] for r in c), 2)}
        for e in (10, 1.06):
            ce = [r.get("slew2080_Vns") or 0 for r in c if r["esl_nH"] == e]
            if ce:
                d[f"max_slew2080_esl{e:g}_Vns"] = round(max(ce), 2)
        if case == "S1":
            d["zvs"] = f"{sum(bool(r['zvs']) for r in c)}/{len(c)}"
            tt = [r["t_trans_ns"] for r in c if r.get("t_trans_ns") is not None]
            d["worst_t_trans_ns"] = round(max(tt), 1) if tt else None
            if tt:
                d["margin_ns"] = {k: round(v - max(tt), 1) for k, v in DT_WIN.items() if k != "569"}
            d["max_turn_on_gate4_ns"] = round(max((r.get("t_on_gate4_ns") or 0) for r in c), 1)
            # long-window grids: incoming die gate voltage 1 / 2 / 3 us after its on command (gn 'slowgate' measure;
            # the gate-network study's turn-on-delay criterion: the current zero is >= 2.08 us away at 60 kHz, 45 deg)
            for k in ("1u", "2u", "3u"):
                v = [r[f"vgs_inc_{k}_V"] for r in c if r.get(f"vgs_inc_{k}_V") is not None]
                if v:
                    d[f"min_gate_at_{k}s_V"] = round(min(v), 2)
                    sub = [r[f"vgs_inc_{k}_V"] for r in c if r.get(f"vgs_inc_{k}_V") is not None and r["drv"] == "nom"
                           and r["temp_C"] in (100, 150) and r["vbus"] == 198 and r["dt_ns"] == 408 and r["esl_nH"] == 10]
                    if sub:
                        d[f"min_gate_at_{k}s_V_gn_slowgate_rows"] = round(min(sub), 2)
        if case == "S4":
            d["max_difdt_75_25_Apus"] = round(max(r.get("difdt_75_25_Apus") or 0 for r in c), 0)
            d["max_irr_A"] = round(max(r.get("i_rr_pk_A") or 0 for r in c), 1)
            # no 20-80 % edge inside the window = the turn-on is too slow for the case to commutate: not evaluable
            d["no_edge_rows"] = sum(r.get("slew2080_Vns") is None for r in c)
            d["max_turn_on_gate4_ns"] = round(max((r.get("t_on_gate4_ns") or 0) for r in c), 1)
            w = max(c, key=lambda r: r.get("slew2080_Vns") or 0)
            d["worst_slew_row"] = {k: w[k] for k in ("drv", "leg", "temp_C", "vbus", "dir", "dt_ns", "esl_nH")}
        if case == "S2":
            q = [max(abs(r["q_gate_hs_C"] or 0), abs(r["q_gate_ls_C"] or 0)) for r in c if r.get("q_gate_hs_C") is not None]
            if q:
                d["max_gate_charge_nC"] = round(max(q) * 1e9, 1)
        s[case] = d
    s["screens_c25_pass"] = sum(bool(r.get("pass")) for r in ok if r["case"] in ("S1", "S2", "S4", "S5"))
    s["screens_c25_pass_hot"] = sum(bool(r.get("pass_hot")) for r in ok if r["case"] in ("S1", "S2", "S4", "S5"))
    s["not_complete"] = [{k: r[k] for k in ("case", "drv", "leg", "temp_C", "vbus", "il", "dir", "dt_ns", "esl_nH")}
                         for r in rows if r["status"] != "complete"]
    return s


def rate(s, d):
    """Checks against the part's own ratings (device_data.json 'ratings')."""
    rt = d.get("ratings", {})
    out = {}
    s4 = s.get("S4")
    if s4:
        slew = max(v for k, v in s4.items() if k.startswith("max_slew2080"))
        dv = rt.get("diode_dvdt_Vns")
        out["S4_slew_Vns"] = slew
        if dv:
            out["diode_dvdt_rating_Vns"] = dv
            out["diode_dvdt_ratio"] = round(slew / dv, 3)
            out["diode_dvdt_pass_80pct"] = slew <= 0.8 * dv
        else:
            out["diode_dvdt_rating_Vns"] = "not stated"
        if rt.get("diode_difdt_Apus"):
            out["difdt_ratio"] = round(s4["max_difdt_75_25_Apus"] / rt["diode_difdt_Apus"], 3)
            out["difdt_pass_80pct"] = s4["max_difdt_75_25_Apus"] <= 0.8 * rt["diode_difdt_Apus"]
        if rt.get("mosfet_dvdt_Vns"):
            out["mosfet_dvdt_ratio"] = round(slew / rt["mosfet_dvdt_Vns"], 3)
        out["S4_vds_pass_520"] = s4["max_vds_V"] <= 520
    offs = [s[c]["max_off_V"] for c in ("S1", "S2", "S4", "S5") if c in s]
    if offs:
        out["max_off_gate_V"] = max(offs)
        vth = rt.get("vth_min_hot_V")
        if vth:
            out["vth_min_hot_V"] = vth
            out["off_gate_margin_to_vth_min_hot_V"] = round(vth - max(offs), 3)
    if s.get("S2"):
        out["S2_vds_pass_585"] = s["S2"]["max_vds_V"] <= 585
    return out


def main():
    res = {}
    md = ["| config | grid | complete | S1 ZVS | S1 worst t_trans ns (margin 340 / 408) | S2 VDS V | S4 VDS V | S4 slew V/ns (ESL 10 / 1.06) "
          "| diode dv/dt rating, ratio | S4 diF/dt A/us | S5 slew V/ns | max off-gate V | c25 screens pass (hot) | gate Q nC (S2) |",
          "|" + "---|" * 14]
    for dev_dir in sorted(p for p in SIMS.iterdir() if p.is_dir() and p.name not in ("control", "gn", "_qrr")):
        dev = dev_dir.name
        dkey = next((k for k, v in DATA["devices"].items() if any(dev.startswith(c) for c in v.get("configs", []))), None)
        d = DATA["devices"].get(dkey, {})
        for grid in ("full", "fullL", "s4L", "s4b", "s4bL", "s2q", "slowgate", "zvs170"):
            r = load(dev, grid)
            if not r:
                continue
            s = summ(r["rows"])
            s["ratings_check"] = rate(s, d)
            s["device_data_key"] = dkey
            res.setdefault(dev, {})[grid] = s
            s1, s2, s4, s5 = (s.get(k, {}) for k in ("S1", "S2", "S4", "S5"))
            rc = s["ratings_check"]
            md.append(
                f"| {dev} | {grid} | {s['complete']}/{s['runs']} | {s1.get('zvs', '')} | "
                + (f"{s1.get('worst_t_trans_ns')} ({s1['margin_ns']['340']} / {s1['margin_ns']['408']})" if s1.get("margin_ns") else "")
                + f" | {s2.get('max_vds_V', '')} | {s4.get('max_vds_V', '')} | "
                + (f"{s4.get('max_slew2080_esl10_Vns', '')} / {s4.get('max_slew2080_esl1.06_Vns', '')}" if s4 else "")
                + f" | {rc.get('diode_dvdt_rating_Vns', '')}, {rc.get('diode_dvdt_ratio', '')} | {s4.get('max_difdt_75_25_Apus', '')} | "
                + (f"{s5.get('max_slew2080_esl10_Vns', '')}" if s5 else "")
                + f" | {rc.get('max_off_gate_V', '')} | {s['screens_c25_pass']} ({s['screens_c25_pass_hot']}) | {s2.get('max_gate_charge_nC', '')} |")
    (C55 / "results").mkdir(exist_ok=True)
    (C55 / "results/switching.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    (C55 / "results/switching.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
