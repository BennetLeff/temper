#!/usr/bin/env python3
"""28 A bank options at ~0.50 uF from parts in stock: n x (0.50/n) and mixed banks, vendor row, voltage rows, fit,
bank_air (strict and gap credit) at 28 A under the S24 flow, release, highest strictly-qualified step, BOM cost.

    python3 -I scripts/options28.py   -> results/options28.json + .md (exit 1 on a failed control)

Inputs: data/parts28.json; PS read-only: c34 tdk_curves_c34.json (TDK p.57 2000 V chart); round-6 fstrat-b-bank-sweep.csv (yield vs C, L 70 uH, 220 mm pans, 28 A) and
c34-bank-margin/results/kemet_r76_curves.json (R76 2000 V chart digitisation); bank_air physics from
scripts/bank_air_cand.py (imported unchanged, s49 pads).

Rules
  worst share  s_i = C_i (1 + t) / (C_i (1 + t) + sum_j!=i C_j (1 - t))  (c34 bank_margin.py)
  vendor row   I_tank s_i / I_allow,i(35 kHz) <= 0.85  (and 40 kHz reported)
  C band       yield: round 6 at L 70 uH is monotone falling in C for C >= 0.35 uF (0.45 -> 91.4 %, 0.50 -> 88.6 %,
               0.60 -> 75.9 %), interpolated linearly (as c34). F3 R0/R1 = 1693.2 V at C_min 0.475 uF is 0.996 of the
               0.85 VR rule; voltages are scaled by 0.475 / C_min (1/C, conservative: F3 and Z0 go as C^-1/2 at
               resonance), so C_min >= 0.4731 uF, i.e. C_nom >= 0.498 uF for J parts.
  fit          single column: pin rows y 48.0-113.2 on the s49 / s51 copper (65.2 mm pin span; first-pass slot read,
               KiCad DRC is the authority), 0.5 mm min body gap. Bodies beyond that need a second column.
  bank_air     per part type, its own share, tight column (gap 0.5 mm), s49 jetmix pads; KEMET Th rule
               Th = max(T_A, T_pad), dT_lim 40 K to Th 60 C -> 0 K at 110 C; dT_v 20 K (table footnote).
Controls: (1) bank_air_cand's knscha gate 1.221 reproduced through the share override; (2) the ESR model reproduces the
plotted R76UR2470 curve at 35 kHz within 3 % (the estimate factor is that ratio).
"""
import csv
import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
R6 = PS / "validation-results/05-resonant-tank-envelope/round6-full-power/outputs/fstrat-b-bank-sweep.csv"
KEMC = PS / "validation-results/11-candidates/c34-bank-margin/results/kemet_r76_curves.json"
spec = importlib.util.spec_from_file_location("bac", ROOT / "scripts/bank_air_cand.py")
bac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bac)
J = "/Users/bennet/Desktop/temper/worktrees/runs-native21/s49/c49/b3-bank-air/jetmix"
REL = ("/Users/bennet/Desktop/temper/worktrees/ps-selv/zapote/power-stage-120v/validation-results/04-board-current-thermal/"
       "round5-native21/b3-ratings/runs")
PIN_SPAN, GAP = 65.2, 0.5
V0 = {"V_pk_28A": 566.0, "V_rms_28A": 268.0, "no_pan_pk": 775.0, "F3_R01": 1693.2, "F3_any": 1786.6, "Z0_top": 1607.1, "dVdt": 345.4}
STEPS = (18.0, 20.0, 22.0, 24.0, 26.0, 28.0)

OPTIONS = [
    ("O1", "11 x R76UR2470 (47 nF P27.5)", [("r76ur2470", 11)]),
    ("O2", "11 x R76UN2470 (47 nF P22.5, AEC)", [("r76un2470", 11)]),
    ("O3", "10 x R76UR2470 + 1 x R76UN2390 (39 nF)", [("r76ur2470", 10), ("r76un2390", 1)]),
    ("O4", "2 x R76UR2470 + 6 x R76UR2680 (68 nF)", [("r76ur2470", 2), ("r76ur2680", 6)]),
    ("O5", "5 x R76UR2470 + 4 x R76UR2680", [("r76ur2470", 5), ("r76ur2680", 4)]),
    ("O6", "10 x R76UR2470 + 1 x TDK B32654A2333K000 (33 nF K)", [("r76ur2470", 10), ("tdk_a2333k", 1)]),
    ("R1", "ref: 5 x KNSCHA 104 (s51 as built)", [("knscha104", 5)]),
    ("R2", "ref: 10 x R76UR2470 (0.47 uF)", [("r76ur2470", 10)]),
    ("R3", "ref: 7 x R76UR2680 (0.476 uF)", [("r76ur2680", 7)]),
    ("R4", "ref: 8 x R76UR2680 (0.544 uF)", [("r76ur2680", 8)]),
]


def loglog(pts, f):
    for (f0, i0), (f1, i1) in zip(pts, pts[1:]):
        if f0 <= f <= f1:
            t = (math.log(f) - math.log(f0)) / (math.log(f1) - math.log(f0))
            return math.exp(math.log(i0) + t * (math.log(i1) - math.log(i0)))
    raise ValueError(f)


TDKC = json.loads((PS / "validation-results/11-candidates/c34-bank-margin/results/tdk_curves_c34.json").read_text())["charts"]["p57B"]["rows"]
KC = json.loads(KEMC.read_text())["charts"]["2000V"]["curves"]
CURVE = {k: sorted((float(f), a) for f, a in v["I_A"].items()) for k, v in KC.items()}
_r = loglog(CURVE["R76UR3100"], 35e3) / loglog(CURVE["R76UR3100"], 100e3)
D = 11e-3 * (1 / _r ** 2 - 1) / (1 / (2 * math.pi * 35e3 * 100e-9) - 1 / (2 * math.pi * 100e3 * 100e-9))


def esr_model(p, f):
    c, esr = p["C_nF"] * 1e-9, p["ESR100k_mOhm"] * 1e-3
    e = esr + D * (1 / (2 * math.pi * f * c) - 1 / (2 * math.pi * 100e3 * c))
    return p["I100k_table_A"] * math.sqrt(esr / e)


P28 = json.loads((ROOT / "data/parts28.json").read_text())
CTRL_FACTOR = loglog(CURVE["R76UR2470"], 35e3) / esr_model(P28["parts"]["r76ur2470"], 35e3)


def part(pid):
    p = dict(P28["parts"][pid])
    if p["series"].startswith("KEMET"):
        for k, v in P28["kemet_common"].items():
            p.setdefault(k, v)
    if p["I_basis"] == "curve":
        p["I35"], p["I40"] = loglog(CURVE[p["curve"]], 35e3), loglog(CURVE[p["curve"]], 40e3)
    elif p["I_basis"] == "esr_model":
        p["I35"], p["I40"] = esr_model(p, 35e3) * min(1.0, CTRL_FACTOR), esr_model(p, 40e3) * min(1.0, CTRL_FACTOR)
    elif p["I_basis"] == "tdk_interp":
        def ti(f):
            a = loglog([(r["f_hz"], r["I_22nF"]) for r in TDKC], f)
            b = loglog([(r["f_hz"], r["I_47nF"]) for r in TDKC], f)
            t = math.log(p["C_nF"] / 22.0) / math.log(47.0 / 22.0)
            return math.exp(math.log(a) + t * (math.log(b) - math.log(a)))
        p["I35"], p["I40"] = ti(35e3), ti(40e3)
    p["V35"] = p["I35"] / (2 * math.pi * 35e3 * p["C_nF"] * 1e-9)
    return p


def yield_at(c_uf):
    rows = [(float(r["C_bank_uF"]), float(r["yield_28A"])) for r in csv.DictReader(open(R6)) if r["L_free_uH"] == "70"]
    rows.sort()
    for (c0, y0), (c1, y1) in zip(rows, rows[1:]):
        if c0 <= c_uf <= c1:
            return y0 + (y1 - y0) * (c_uf - c0) / (c1 - c0)
    raise ValueError(c_uf)


def price(pid, qty):
    """allocate qty across distributors by unit price at the tier each one's share reaches, limited to its stock;
    returns (sources, mean unit price) or (sources, None) when stock is short."""
    st = P28["stock"][P28["parts"][pid]["mpn"]]
    offers = []
    for dist, lad in st["ladders"].items():
        have = st.get(dist, 0)
        if have <= 0:
            continue
        take = min(have, qty)
        tiers = [p for q, p in lad if q <= take]
        if tiers:
            offers.append((tiers[-1], dist, have))
    offers.sort()
    left, cost, src = qty, 0.0, []
    for unit, dist, have in offers:
        t = min(have, left)
        cost += t * unit
        src.append((dist, t, unit))
        left -= t
        if left == 0:
            break
    return src, (round(cost / qty, 4) if left == 0 else None)


def fit(items):
    bodies = []
    for pid, n in items:
        bodies += [P28["parts"][pid]["w"]] * n
    bodies.sort(reverse=True)
    cols, cur, span = [], [], 0.0
    for w in bodies:
        add = 0.0 if not cur else cur[-1] / 2 + w / 2 + GAP
        if cur and span + add > PIN_SPAN:
            cols.append((cur, span))
            cur, span = [w], 0.0
        else:
            cur.append(w)
            span += add
    cols.append((cur, span))
    leads = sorted({P28["parts"][pid]["lead_mm"] for pid, _ in items})
    return {"bodies": len(bodies), "column_body_thickness_mm": round(sum(bodies), 1),
            "columns": [{"n": len(c), "pin_span_mm": round(s, 2), "body_envelope_mm": round(s + c[0] / 2 + c[-1] / 2, 2)} for c, s in cols],
            "fits_one_column": len(cols) == 1, "lead_spacings_mm": leads,
            "pin_span_needed_one_column_mm": round(sum(bodies) - bodies[0] / 2 - bodies[-1] / 2 + GAP * (len(bodies) - 1), 1)}


def main():
    enc = json.loads((PS / "validation-results/11-candidates/airflow28-2026-10-16/results/enclosure.json").read_text())
    e20 = enc["jetmix_base"]["h20"][bac.PATH]
    v0, rise0 = e20["v_turbulent_m_s"], e20["bulk_rise_K_gap10"]
    p61, _ = bac.pads_from(f"{J}/bay61/c28_h20_jet100_p0p25.json", f"{J}/bay61/c28_h20_jet100_p0p5.json", 61)
    p55, _ = bac.pads_from(f"{J}/bay55/c28_h15_jet100_p0p25.json", f"{J}/bay55/c28_h15_jet100_p0p5.json", 55)
    prel, srel = bac.pads_from(f"{REL}/c17.5_h10_p0p25.json", f"{REL}/c17.5_h10_p0p5.json", 61)
    pts = [("@61 h20", 61, v0, rise0, p61), ("@55 h15", 55, v0, rise0, p55)]
    orig_share = bac.share
    bac.share = lambda c: c["_share"] if "_share" in c else orig_share(c)

    def thermal(p, s, ncol, i_tank):
        c = {"mpn": p["mpn"], "n": ncol, "tol": p["tol"], "w": p["w"], "h": p["h"], "l": p["l"], "pitch": p["w"] + GAP,
             "gap_mm": GAP, "dT_v": p["dT_v"], "I35": p["I35"], "I40": p["I40"], "rule": p["rule"], "top_max": p["top_max"],
             "_share": s}
        bac.I_TANK = i_tank
        g, _ = bac.run_forced(c, pts, gap_credit=False, pad_heat=False, k_pad=0.0, p_ref=0.0)
        gg, _ = bac.run_forced(c, pts, gap_credit=True, pad_heat=False, k_pad=0.0, p_ref=0.0)
        bac.I_TANK = 28.0
        return g, gg, c

    out = {"inputs": {"D_kemet_esr": D, "esr_model_control_factor_R76UR2470_35k": round(CTRL_FACTOR, 4),
                      "flow": {"v_m_s": v0, "bulk_rise_K": rise0}, "release_pads_board": srel["p0p25"][1][:8],
                      "pin_span_mm": PIN_SPAN, "gap_mm": GAP}, "parts": {}, "options": {}}
    for pid in P28["parts"]:
        p = part(pid)
        out["parts"][pid] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in p.items() if k not in ("rule",)}
    fails = []
    if abs(CTRL_FACTOR - 1) > 0.03:
        fails.append(f"ESR model vs plotted R76UR2470 at 35 kHz: {CTRL_FACTOR:.3f}")
    for oid, label, items in OPTIONS:
        ps = {pid: part(pid) for pid, _ in items}
        c_nom = sum(ps[pid]["C_nF"] * n for pid, n in items) / 1e3
        c_min = sum(ps[pid]["C_nF"] * (1 - ps[pid]["tol"]) * n for pid, n in items) / 1e3
        k = 0.475 / c_min
        per = {}
        for pid, n in items:
            p = ps[pid]
            ci = p["C_nF"] * (1 + p["tol"])
            rest = sum(ps[q]["C_nF"] * (1 - ps[q]["tol"]) * m for q, m in items) - p["C_nF"] * (1 - p["tol"])
            s = ci / (ci + rest)
            per[pid] = {"mpn": p["mpn"], "n": n, "share": round(s, 4), "I_part_28A_A": round(28 * s, 3),
                        "I35_A": round(p["I35"], 3), "I40_A": round(p["I40"], 3), "I_basis": p["I_basis"],
                        "vendor_35k": round(28 * s / p["I35"], 3), "vendor_40k": round(28 * s / p["I40"], 3),
                        "tank_A_at_vendor_0.85": round(0.85 * p["I35"] / s, 2)}
        vrows = {}
        for pid in ps:
            p = ps[pid]
            vrows[pid] = {"V 28 A <= 0.8 VR": V0["V_pk_28A"] * k / (0.8 * p.get("VR", 2000)),
                          "no-pan <= 0.8 VC(Top)": V0["no_pan_pk"] * k / (0.8 * p.get("VC_top", 1375)),
                          "Vrms <= 0.8 VRMS": V0["V_rms_28A"] * k / (0.8 * p.get("VRMS", 700)),
                          "F3 R0/R1 <= 0.85 VR": V0["F3_R01"] * k / (0.85 * p.get("VR", 2000)),
                          "F3 any <= VR": V0["F3_any"] * k / p.get("VR", 2000),
                          "Z0 x top <= VR": V0["Z0_top"] * k / p.get("VR", 2000),
                          "dV/dt": V0["dVdt"] * k / p["dvdt_V_us"]}
        vworst = {r: round(max(v[r] for v in vrows.values()), 3) for r in next(iter(vrows.values()))}
        f = fit(items)
        ncol = max(c["n"] for c in f["columns"])
        th = {}
        for pid, n in items:
            p = ps[pid]
            s = per[pid]["share"]
            g, gg, cc = thermal(p, s, ncol, 28.0)
            steps = {}
            for i in STEPS:
                gi, ggi, _ = thermal(p, s, ncol, i)
                steps[f"{i:g}"] = {"vendor": round(i * s / p["I35"], 3), "gate": gi["eff"], "gate_gap": ggi["eff"],
                                   "strict_ok": gi["passes"] and i * s / p["I35"] <= 0.85,
                                   "gap_ok": ggi["passes"] and i * s / p["I35"] <= 0.85}
            bac.I_TANK = 28.0
            rel = bac.run_still(cc, prel, 61, bac.I_REL_TRIP, 0.0, 0.0, False)
            th[pid] = {"gate_28A": g["eff"], "T_op_max_C": g["T_op_max_C"], "gate_pass": g["passes"], "worst": g["worst"],
                       "gate_gap_28A": gg["eff"], "release_18.375A_rad": rel["with_radiation"]["eff"],
                       "release_18.375A_norad": rel["no_radiation"]["eff"], "steps": steps}
        hi_strict = max([i for i in STEPS if all(th[p]["steps"][f"{i:g}"]["strict_ok"] for p in th)], default=None)
        hi_gap = max([i for i in STEPS if all(th[p]["steps"][f"{i:g}"]["gap_ok"] for p in th)], default=None)
        stock_ok_proto = all(sum(v for kk, v in P28["stock"][ps[pid]["mpn"]].items() if kk in ("digikey", "newark", "jlc")) >= 20 * n
                             for pid, n in items)
        stock_ok_500 = all(sum(v for kk, v in P28["stock"][ps[pid]["mpn"]].items() if kk in ("digikey", "newark", "jlc")) >= 500 * n
                           for pid, n in items)
        cost = 0.0
        cost_src = {}
        for pid, n in items:
            src, unit = price(pid, 500 * n)
            cost = None if (cost is None or unit is None) else cost + n * unit
            cost_src[pid] = {"allocation": src, "mean_unit_usd": unit, "qty": 500 * n}
        y = yield_at(c_nom)
        vendor_worst = max(v["vendor_35k"] for v in per.values())
        gate_worst = max(t["gate_28A"] for t in th.values())
        gap_worst = max(t["gate_gap_28A"] for t in th.values())
        out["options"][oid] = {
            "label": label, "items": items, "C_nom_uF": round(c_nom, 4), "C_min_uF": round(c_min, 4),
            "yield_28A": round(y, 4), "yield_delta_pts": round(100 * (y - yield_at(0.50)), 1),
            "per_part": per, "vendor_worst_35k": vendor_worst, "voltage_rows_worst": vworst,
            "voltage_all_pass": all(v <= 1.0 for v in vworst.values()), "fit": f, "thermal": th,
            "gate_strict_worst_28A": gate_worst, "gate_gap_worst_28A": gap_worst,
            "release_worst_rad": max(t["release_18.375A_rad"] for t in th.values()),
            "release_worst_norad": max(t["release_18.375A_norad"] for t in th.values()),
            "highest_step_strict": hi_strict, "highest_step_gap": hi_gap,
            "stock_ok_20_boards": stock_ok_proto, "stock_ok_500_boards": stock_ok_500,
            "bank_cost_per_board_usd_at_500": (round(cost, 2) if cost is not None else "stock short"), "cost_src": cost_src,
            "reaches_28A_strict": vendor_worst <= 0.85 and gate_worst <= 1.0 and all(t["gate_pass"] for t in th.values())
                                  and all(v <= 1.0 for v in vworst.values()) and y >= yield_at(0.50) - 1e-9,
        }
    # control 1: knscha through the override equals bank_air_cand's gate
    ref = json.loads((ROOT / "results/bank_air_cand.json").read_text())["candidates"]["knscha"]["bank_air_28A_35k_gate"]["eff"]
    got = out["options"]["R1"]["thermal"]["knscha104"]["gate_28A"]
    out["controls"] = {"knscha_gate": [ref, got], "esr_factor": round(CTRL_FACTOR, 4), "failed": fails}
    if abs(ref - got) > 0.01:
        fails.append(f"knscha gate {got} vs {ref}")
    (ROOT / "results/options28.json").write_text(json.dumps(out, indent=1) + "\n")
    L = ["| id | bank | C nom / min uF | yield pts | vendor 35k worst | F3 R0/R1 | gate strict / gap 28 A | release rad / no-rad | "
         "highest step strict / gap | bodies, columns (pin span mm) | stock 20 / 500 boards | $/board @500 |", "|---" * 12 + "|"]
    for oid, o in out["options"].items():
        cols = " + ".join(f"{c['n']} ({c['pin_span_mm']})" for c in o["fit"]["columns"])
        L.append(f"| {oid} | {o['label']} | {o['C_nom_uF']} / {o['C_min_uF']} | {o['yield_delta_pts']:+.1f} | {o['vendor_worst_35k']} | "
                 f"{o['voltage_rows_worst']['F3 R0/R1 <= 0.85 VR']} | {o['gate_strict_worst_28A']} / {o['gate_gap_worst_28A']} | "
                 f"{o['release_worst_rad']} / {o['release_worst_norad']} | {o['highest_step_strict']} / {o['highest_step_gap']} | "
                 f"{o['fit']['bodies']}: {cols} | {o['stock_ok_20_boards']} / {o['stock_ok_500_boards']} | {o['bank_cost_per_board_usd_at_500']} |")
    L += ["", "Per part (28 A):", "", "| option | MPN | n | share | I part A | I35 / I40 A (basis) | vendor 35k / 40k | gate / gap | T_op max C |",
          "|---|---|---|---|---|---|---|---|---|"]
    for oid, o in out["options"].items():
        for pid, v in o["per_part"].items():
            t = o["thermal"][pid]
            L.append(f"| {oid} | {v['mpn']} | {v['n']} | {v['share']} | {v['I_part_28A_A']} | {v['I35_A']} / {v['I40_A']} ({v['I_basis']}) | "
                     f"{v['vendor_35k']} / {v['vendor_40k']} | {t['gate_28A']} / {t['gate_gap_28A']} | {t['T_op_max_C']} |")
    L += ["", "Parts V_allow(35 kHz) = I35 / (w C): " + ", ".join(f"{v['mpn']} {v['V35']:.0f} V" for v in out["parts"].values()),
          f"ESR-model control factor (plotted / model, R76UR2470 35 kHz): {CTRL_FACTOR:.4f}; controls {out['controls']}"]
    (ROOT / "results/options28.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
