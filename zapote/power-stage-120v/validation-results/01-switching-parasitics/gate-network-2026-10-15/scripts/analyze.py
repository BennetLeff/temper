#!/usr/bin/env python3
"""Summaries, controls and the Pareto set from ../sims/<cfg>/<grid>/results.json -> ../results/.

python3 -I analyze.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIMS = HERE.parent / "sims"
OUT = HERE.parent / "results"
PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
DS = PS / "validation-results/01-switching-parasitics/device-study-2026-10-15"
NAN = float("nan")


def load(cfg, grid):
    p = SIMS / cfg / grid / "results.json"
    return json.loads(p.read_text()) if p.is_file() else None


def mx(rows, k, absval=False):
    v = [abs(r[k]) if absval else r[k] for r in rows if r.get(k) is not None]
    return max(v) if v else None


def mn(rows, k):
    v = [r[k] for r in rows if r.get(k) is not None]
    return min(v) if v else None


def rnd(x, n=1):
    return None if x is None else round(x, n)


def summarize(cfg, grid):
    d = load(cfg, grid)
    if d is None:
        return None
    rows = d["rows"]
    ok = [r for r in rows if r["status"] == "complete"]
    s = {"cfg": cfg, "grid": grid, "spec": d["cfg"], "runs": len(rows), "complete": len(ok),
         "pass": sum(bool(r.get("pass")) for r in ok), "pass_hot": sum(bool(r.get("pass_hot")) for r in ok)}
    for case in ("S1", "S2", "S4", "S5"):
        c = [r for r in ok if r["case"] == case]
        if not c:
            continue
        e = {"n": len(c), "pass": sum(bool(r.get("pass")) for r in c), "pass_hot": sum(bool(r.get("pass_hot")) for r in c),
             "max_vds": rnd(mx(c, "vds_pk")), "max_off_V": rnd(mx(c, "off_V"), 3), "max_vgs_abs": rnd(mx(c, "vgs_abs"), 2),
             "max_q_gate_inc_nC": rnd(mx(c, "q_gate_inc_nC"))}
        for esl in (10, 1.06):
            ce = [r for r in c if r["esl_nH"] == esl]
            if ce:
                e[f"max_slew2080_esl{esl:g}"] = rnd(mx(ce, "slew2080_Vns"), 2)
                e[f"max_slew1090_esl{esl:g}"] = rnd(mx(ce, "slew1090_Vns"), 2)
        if case == "S4":
            e["max_difdt_75_25"] = rnd(mx(c, "difdt_75_25_Apus"), 0)
            e["max_difdt_50_0"] = rnd(mx(c, "difdt_50_0_Apus"), 0)
            e["max_irr_A"] = rnd(mx(c, "i_rr_pk_A"), 1)
            e["pass_diode56"] = sum(bool(r.get("pass_diode56")) for r in c)
            e["pass_difdt1040"] = sum(bool(r.get("pass_difdt1040")) for r in c)
            w = max(c, key=lambda r: r.get("slew2080_Vns") or 0)
            e["worst_slew_row"] = {k: w.get(k) for k in ("drv", "leg", "temp_C", "vbus", "dir", "dt_ns", "esl_nH")}
            e["max_turn_on_delay_gate4_ns"] = rnd(mx(c, "t_on_gate4_ns"))
        if case == "S5":
            e["max_partner_i_A"] = rnd(mx(c, "i_rr_pk_A"), 1)
        if case == "S1":
            e["zvs"] = f"{sum(r['zvs'] for r in c)}/{len(c)}"
            e["worst_t_trans_ns"] = rnd(mx(c, "t_trans_ns"))
            e["margin_340_ns"] = rnd(340 - e["worst_t_trans_ns"]) if e["worst_t_trans_ns"] else None
            e["margin_408_ns"] = rnd(408.3 - e["worst_t_trans_ns"]) if e["worst_t_trans_ns"] else None
        s[case] = e
    return s


def loss_summary(cfg):
    d = load(cfg, "loss")
    if d is None:
        return None
    ok = [r for r in d["rows"] if r["status"] == "complete"]
    out = {"complete": f"{len(ok)}/{len(d['rows'])}"}
    for case, il in (("S1", 10), ("S1", 20), ("S1", 37), ("S4", -20)):
        c = [r for r in ok if r["case"] == case and r["il"] == il and (case != "S4" or r["vbus"] == 280)]
        if c:
            out[f"{case}_{il}A"] = {
                "max_e_extra_uJ": rnd(mx(c, "e_extra_J") * 1e6, 2),
                "max_e_off_edge_uJ": rnd(mx(c, "e_off_edge_J") * 1e6, 2),
                "max_e_in_uJ": rnd(mx(c, "e_in_J") * 1e6, 2), "n": len(c)}
    return out


def slowgate_summary(cfg):
    """Long-window S1 rows: incoming die heat over 3.75 us after the on command, gate voltage at 1/2/3 us, and
    the series-resistor (R_on) energy per cycle (turn-on + turn-off edge of the same FET) -> power at 35/60/80 kHz."""
    d = load(cfg, "slowgate")
    if d is None:
        return None
    ok = [r for r in d["rows"] if r["status"] == "complete"]
    out = {"complete": f"{len(ok)}/{len(d['rows'])}"}
    for il in (20, 37):
        c = [r for r in ok if r["il"] == il]
        if not c:
            continue
        out[f"S1_{il}A"] = {
            "max_e_in_uJ": rnd(mx(c, "e_in_J") * 1e6, 2), "max_e_tot_uJ": rnd(mx(c, "e_tot_J") * 1e6, 2),
            "min_vgs_inc_1us_V": rnd(mn(c, "vgs_inc_1u_V"), 2), "min_vgs_inc_2us_V": rnd(mn(c, "vgs_inc_2u_V"), 2),
            "min_vgs_inc_3us_V": rnd(mn(c, "vgs_inc_3u_V"), 2), "max_q_gate_inc_nC": rnd(mx(c, "q_gate_inc_nC"), 1),
            "max_e_ron_cycle_uJ": rnd(max(r["e_ron_inc_J"] + r["e_ron_out_J"] for r in c) * 1e6, 2)}
        e = out[f"S1_{il}A"]["max_e_ron_cycle_uJ"]
        out[f"S1_{il}A"]["P_ron_W_at_35_60_80kHz"] = [rnd(e * f * 1e-3, 3) for f in (35, 60, 80)]
    return out


def repro_controls():
    out = {}
    d = load("asbuilt", "repro")
    if d:
        dm = {}
        for r, w in zip(d["rows"], d["reference"]):
            for k in ("vds_pk", "off_V", "slew2080_Vns", "t_trans_ns", "incoming_V"):
                if r.get(k) is not None and w.get(k) is not None:
                    dm[k] = max(dm.get(k, 0.0), abs(r[k] - w[k]))
        s4 = [r for r in d["rows"] if r["case"] == "S4"]
        out["asbuilt_vs_committed_edge_edge2"] = {
            "rows": len(d["rows"]), "complete": sum(r["status"] == "complete" for r in d["rows"]),
            "max_abs_delta": {k: float(f"{v:.3g}") for k, v in dm.items()},
            "rows_within_1mV_vds": sum(abs(r["vds_pk"] - w["vds_pk"]) < 1e-3 for r, w in zip(d["rows"], d["reference"])),
            "S4_max_slew_esl10": rnd(mx([r for r in s4 if r["esl_nH"] == 10], "slew2080_Vns"), 2),
            "S4_max_slew_esl1.06": rnd(mx([r for r in s4 if r["esl_nH"] == 1.06], "slew2080_Vns"), 2),
            "committed_S4_max_slew_esl10": rnd(mx([w for w in d["reference"] if w["case"] == "S4" and w["esl_nH"] == 10], "slew2080_Vns"), 2),
            "committed_S4_max_slew_esl1.06": rnd(mx([w for w in d["reference"] if w["case"] == "S4" and w["esl_nH"] == 1.06], "slew2080_Vns"), 2)}
    d = load("asbuilt", "erepro")
    if d:
        dm = max(abs(r["e_extra_J"] - w["e_extra_J"]) for r, w in zip(d["rows"], d["reference"]))
        out["asbuilt_energy_vs_committed"] = {"rows": len(d["rows"]), "max_abs_delta_e_extra_J": dm}

    def pair(a, b, grid="s4screen"):
        A, B = load(a, grid), load(b, grid)
        if not (A and B):
            return None
        dm, n = {}, 0
        for r, w in zip(A["rows"], B["rows"]):
            if r["status"] == w["status"] == "complete":
                n += 1
                for k in ("vds_pk", "off_V", "slew2080_Vns", "difdt_75_25_Apus", "q_gate_inc_nC"):
                    if r.get(k) is not None and w.get(k) is not None:
                        dm[k] = max(dm.get(k, 0.0), abs(r[k] - w[k]))
        return {"rows_compared": n, "max_abs_delta": {k: float(f"{v:.3g}") for k, v in dm.items()}}
    # split topology, diode replaced by 1 uohm, R_on = R_off = 2R  ==  symmetric R (turn-off branch deleted)
    out["split_short_2R_vs_sym_R"] = {"R=12": pair("short24_24", "sym12"), "R=22": pair("short44_44", "sym22")}
    # deck ROFF literal (1.345) vs BOM value (1.0 ohm)
    out["asbuilt_deck_roff1p345_vs_bom_1ohm"] = pair("asbuilt", "asbuilt_bom")
    # CM8 proxy conventions: device-study RG correction outside the package vs Rg,int inside (symmetric)
    out["open_1Gohm_vs_deleted_branch"] = {"R=12": pair("open12", "sym12"), "R=22": pair("open22", "sym22")}
    out["tt50_copy_vs_vendor"] = pair("split39_1_tt50", "split39_1")
    # against the committed device-study cm8rg / cm8rg2 rows (same corners)
    vmap = {"nom": "", "strong": "_strong", "weak": "_weak"}
    res = {}
    for r_ext, mode in ((8.2, "cm8rg"), (10, "cm8rg"), (12, "cm8rg2"), (15, "cm8rg2")):
        A = load(f"cm8rgc_rext{r_ext:g}".replace(".", "p"), "s4screen")
        ref = json.loads((DS / f"sims/IPW65R029CFD7_L1/{mode}/results.json").read_text())["rows"]
        idx = {(w["variant"], w["leg"], w["temp_C"], w["vbus"], w["dir"], w["dt_ns"], w["esl_nH"]): w for w in ref
               if w["status"] == "complete" and w.get("case") == "S4"}
        if not A:
            continue
        dm, n = {}, 0
        for r in A["rows"]:
            k = (f"cm8ext{r_ext:g}{vmap[r['drv']]}".replace(".", "p"), r["leg"], r["temp_C"], r["vbus"], r["dir"], r["dt_ns"], r["esl_nH"])
            w = idx.get(k)
            if w and r["status"] == "complete":
                n += 1
                for q in ("vds_pk", "off_V", "slew2080_Vns"):
                    dm[q] = max(dm.get(q, 0.0), abs(r[q] - w[q]))
        res[f"R_ext={r_ext}"] = {"rows_matched": n, "max_abs_delta": {k: float(f"{v:.3g}") for k, v in dm.items()}}
    out["cm8rgc_vs_committed_device_study"] = res
    return out


def pareto(items, keys):
    """items: list of dicts; keys: list of (key, sense) with sense 'min'; returns non-dominated names."""
    nd = []
    for a in items:
        dom = False
        for b in items:
            if b is a:
                continue
            if all(b[k] <= a[k] for k, _ in keys) and any(b[k] < a[k] for k, _ in keys):
                dom = True
                break
        if not dom:
            nd.append(a["cfg"])
    return nd


def main():
    OUT.mkdir(exist_ok=True)
    cfgs = sorted(p.name for p in SIMS.iterdir() if p.is_dir())
    summ = {}
    for c in cfgs:
        summ[c] = {g: summarize(c, g) for g in ("s4screen", "s4b", "full", "repro") if load(c, g)}
        ls = loss_summary(c)
        if ls:
            summ[c]["loss"] = ls
        sg = slowgate_summary(c)
        if sg:
            summ[c]["slowgate"] = sg
    ctrl = repro_controls()
    (OUT / "summary.json").write_text(json.dumps(summ, indent=1) + "\n")
    (OUT / "controls.json").write_text(json.dumps(ctrl, indent=1, default=str) + "\n")
    # screen table
    lines = ["| cfg | model | topo | R_on | R_off | Cgs nF | S4 slew ESL10 / 1.06 V/ns | diF/dt 75-25 / 50-0 A/us | Irr pk A | S4 die VDS max | S4 off-gate max | S4 pass / hot | turn-on delay to 4 V ns |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in cfgs:
        s = summ[c].get("s4screen")
        if not s or "S4" not in s:
            continue
        e, sp = s["S4"], s["spec"]
        lines.append(f"| {c} | {sp['model']} | {sp['topo']} | {sp['ron']} | {sp['roff'] if sp['topo'] != 'sym' else '-'} | "
                     f"{sp['cgs']*1e9:g} | {e.get('max_slew2080_esl10')} / {e.get('max_slew2080_esl1.06')} | "
                     f"{e['max_difdt_75_25']} / {e['max_difdt_50_0']} | {e['max_irr_A']} | {e['max_vds']} | {e['max_off_V']} | "
                     f"{e['pass']}/{e['n']} ({e['pass_hot']}) | {e['max_turn_on_delay_gate4_ns']} |")
    (OUT / "s4screen.md").write_text("\n".join(lines) + "\n")
    lb = [lines[0].replace("| cfg |", "| cfg | diode TT |"), lines[1] + "---|"]
    for c in cfgs:
        s = summ[c].get("s4b")
        if not s or "S4" not in s:
            continue
        e, sp = s["S4"], s["spec"]
        lb.append(f"| {c} | {sp.get('tt', '50e-9 (vendor)')} | {sp['model']} | {sp['topo']} | {sp['ron']} | {sp['roff']} | {sp['cgs']*1e9:g} | "
                  f"{e.get('max_slew2080_esl10')} / {e.get('max_slew2080_esl1.06')} | {e['max_difdt_75_25']} / {e['max_difdt_50_0']} | "
                  f"{e['max_irr_A']} | {e['max_vds']} | {e['max_off_V']} | {e['pass']}/{e['n']} ({e['pass_hot']}) | "
                  f"{e['max_turn_on_delay_gate4_ns']} |")
    (OUT / "s4b.md").write_text("\n".join(lb) + "\n")
    # full-grid table
    fl = ["| cfg | S1 worst t_trans ns (margin 340 / 408) | S1 ZVS | S1 off-gate max | S2 VDS max (ESL10/1.06 all) | S2 off-gate | "
          "S4 slew ESL10 / 1.06 | S4 diF/dt 75-25 max | S4 Irr | S4 VDS max | S4 off-gate | S5 slew ESL10 / 1.06 | S5 VDS | S5 off-gate | "
          "max off-gate all | Q gate on max nC | all pass / hot | E_off S1 37 A uJ | E_extra S1 37 A uJ | E_extra S4 280 V uJ |",
          "|" + "---|" * 20]
    items = []
    for c in cfgs:
        s = summ[c].get("full")
        if not s or not all(k in s for k in ("S1", "S2", "S4", "S5")):
            continue
        a, b, f4, f5 = s["S1"], s["S2"], s["S4"], s["S5"]
        ls = summ[c].get("loss", {})
        e37 = ls.get("S1_37A", {})
        e4 = ls.get("S4_-20A", {})
        offall = max(a["max_off_V"], b["max_off_V"], f4["max_off_V"], f5["max_off_V"])
        qmax = max(x["max_q_gate_inc_nC"] for x in (a, b, f4, f5) if x["max_q_gate_inc_nC"] is not None)
        fl.append(f"| {c} | {a['worst_t_trans_ns']} ({a['margin_340_ns']} / {a['margin_408_ns']}) | {a['zvs']} | {a['max_off_V']} | "
                  f"{b['max_vds']} | {b['max_off_V']} | {f4.get('max_slew2080_esl10')} / {f4.get('max_slew2080_esl1.06')} | "
                  f"{f4['max_difdt_75_25']} | {f4['max_irr_A']} | {f4['max_vds']} | {f4['max_off_V']} | "
                  f"{f5.get('max_slew2080_esl10')} / {f5.get('max_slew2080_esl1.06')} | {f5['max_vds']} | {f5['max_off_V']} | "
                  f"{rnd(offall, 3)} | {qmax} | {s['pass']}/{s['complete']} of {s['runs']} ({s['pass_hot']}) | "
                  f"{e37.get('max_e_off_edge_uJ')} | {e37.get('max_e_extra_uJ')} | {e4.get('max_e_extra_uJ')} |")
        if e37:
            items.append({"cfg": c, "s4": max(f4.get("max_slew2080_esl10") or 0, f4.get("max_slew2080_esl1.06") or 0),
                          "difdt": f4["max_difdt_75_25"], "ttrans": a["worst_t_trans_ns"], "off": offall,
                          "eoff": e37["max_e_off_edge_uJ"], "model": s["spec"]["model"]})
    (OUT / "full.md").write_text("\n".join(fl) + "\n")
    par = {}
    for model in sorted({i["model"] for i in items}):
        it = [i for i in items if i["model"] == model]
        par[model] = {"objectives": "min S4 slew (both ESL), min S4 diF/dt, min S1 worst t_trans, min off-gate, min S1 37 A E_off",
                      "set": pareto(it, [("s4", "min"), ("difdt", "min"), ("ttrans", "min"), ("off", "min"), ("eoff", "min")]),
                      "feasible (S4 <= 56 V/ns and diF/dt <= 1040 A/us, all screens pass)":
                          [i["cfg"] for i in it if i["s4"] <= 56 and i["difdt"] <= 1040 and
                           summ[i["cfg"]]["full"]["pass"] == summ[i["cfg"]]["full"]["complete"]]}
    # series-resistor (R_on) dissipation at 60 kHz and the package derating (Uniroyal/Uniohm JLC-01-010 Ed.1 2016-09-23
    # p.3 / p.8: 1206 1/4 W, 2010 3/4 W, 2512 1 W at 70 C, derated above 70 C, 155 C limit; FH RS-06L the same shape)
    pw = ["| cfg | R_on ohm | Cgs nF | Q gate (sim, nC) | E R_on per cycle uJ (worst S1 corner) | P R_on 60 kHz W (sim Q) | "
          "P at Q 383 nC W (CFD7 basis) | max terminal T for 1206 / 2010 / 2512 C (155 - 85 P / P70) | S1 37 A die heat over 3.75 us uJ (vs as-built) | min gate V at 1 / 2 / 3 us |",
          "|" + "---|" * 10]
    base = (summ.get("asbuilt", {}).get("slowgate") or {}).get("S1_37A", {}).get("max_e_tot_uJ")
    powers = {}
    for c in cfgs:
        sg = summ[c].get("slowgate")
        if not sg:
            continue
        sp = load(c, "slowgate")["cfg"]
        e = max(sg[k]["max_e_ron_cycle_uJ"] for k in ("S1_20A", "S1_37A") if k in sg)
        q = max(sg[k]["max_q_gate_inc_nC"] for k in ("S1_20A", "S1_37A") if k in sg)
        p60 = e * 60e3 * 1e-6
        p383 = p60 * 383 / q if "CFD7" in sp["model"] else None
        pr = p383 or p60
        tm = [round(155 - 85 * pr / r, 1) for r in (0.25, 0.75, 1.0)]
        a = sg.get("S1_37A", {})
        powers[c] = {"E_ron_cycle_uJ": e, "Q_nC": q, "P60_W": round(p60, 3), "P60_at_383nC_W": rnd(p383, 3),
                     "Tmax_1206_2010_2512_C": tm}
        pw.append(f"| {c} | {sp['ron']} | {sp['cgs']*1e9:g} | {q} | {e} | {p60:.3f} | {'' if p383 is None else f'{p383:.3f}'} | "
                  f"{tm[0]} / {tm[1]} / {tm[2]} | {a.get('max_e_tot_uJ')} ({'' if base is None else f'{a.get(chr(109)+'ax_e_tot_uJ', 0) - base:+.2f}'}) | "
                  f"{a.get('min_vgs_inc_1us_V')} / {a.get('min_vgs_inc_2us_V')} / {a.get('min_vgs_inc_3us_V')} |")
    (OUT / "ron_power.md").write_text("\n".join(pw) + "\n")
    (OUT / "ron_power.json").write_text(json.dumps(powers, indent=1) + "\n")
    (OUT / "pareto.json").write_text(json.dumps({"items": items, "pareto": par}, indent=1) + "\n")
    print("\n".join(lines))
    print("\n".join(fl))
    print(json.dumps(par, indent=1))
    print(json.dumps(ctrl, indent=1, default=str))


if __name__ == "__main__":
    main()
