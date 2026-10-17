#!/usr/bin/env python3
"""Margins of the B3 hot spots to their datasheet / UL ratings, per case, on the s32 board.

    python3 verdict.py   -> ../results/verdict.json, ../results/VERDICT-TABLES.md

Estimate per quantity = s32 body model at 0.25 mm (global) + the stage-19b fine-window increment for the same part,
case and quantity (b3-convergence/results.json: est - value at 0.25 mm; 0.0625-0.125 mm windows), uncertainty =
|that increment| + the 19b Richardson uncertainty + |Q(0.25) - Q(0.5)| on s32. Cases not in the 19b study (c22_h10,
nominal_h10) take the c28_h10 increments. Fix sensitivities: est_base + (Q_fix - Q_base) at 0.5 mm.
Ambient: the model's 50 C plus the enclosure session's bay-air estimates (R33 study 14: 55 C expected at a 40 C
kitchen, 61 C worst with B3 heat only, 78 C with all allowances stacked); the model is linear, so T shifts 1:1.
"""
import json
import math
from pathlib import Path

from paths import CONV, RESULTS, RUNS

BODY = RUNS / "body"
TAMB_MODEL = 50.0
BAY = {"model_50": 50.0, "bay_expected_55": 55.0, "bay_worst_B3only_61": 61.0, "bay_stacked_78": 78.0}
MOT = 130.0
R5_RATED_W = 5.0                                   # CSS2H 5 W at 70 C terminal -> 0 W at 170 C (p.1 / p.3)
VERIFIED = {"recom": 150.0, "rgw": 125.0, "css2h": 170.0}            # datasheet limits re-read in ratings.py
ASSUMED_PATH = {"film_radial": 110.0, "film_4pin": 110.0, "choke": 125.0, "chip1206": 155.0}  # limit known, package path assumed
CASES = {  # name: (op, h, realism note)
    "c28_h10": ("c28", 10, "28 A Kconfig ceiling (29.4 A trip), still-air board bay: REALISTIC if 28 A is commissioned"),
    "c22_h10": ("c22", 10, "22 A default ceiling (23.1 A trip), still-air board bay: REALISTIC default"),
    "c28_h25": ("c28", 25, "28 A with 25 W/m2K forced air over both board faces: NO record provides that airflow"),
    "der14_h10": ("der14", 10, "blower-stall derate hold (14.7 A), still air: realistic transient-to-steady case"),
    "nominal_h10": ("nominal", 10, "round-3 1710 W at 120 V (line 14.25 A > the 11.1 A inlet hold): NOT reachable; the scorecard's case"),
}
SENS = ["h15", "h20", "a4x0p7", "a4x0p5", "R5x0p5", "modx0p5", "ps0p5"]


def load(name):
    p = BODY / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def conv19b():
    r = json.loads((CONV / "results.json").read_text())
    inc = {}
    for case, rows in r["per_part"].items():
        for row in rows:
            for q in ("pad_mean_c", "pad_max_cell_c", "tj_c"):
                d = row.get(q)
                if not d or "0.25" not in d["values"]:
                    continue
                est = d.get("est", d["values"]["0.25"])
                inc[(case, row["ref"], q)] = (est - d["values"]["0.25"], d.get("uncert_k") or 0.0)
        bh = r["board_hotspots"][case]["peak_1mm_block_mean"]
        inc[(case, "board", "peak_1mm_block")] = (bh["est"] - bh["values"]["0.25"], bh.get("uncert_k") or 0.0)
    return inc


def estimate(case, ref, q, v25, v05, inc):
    key19 = case if (case, ref, q) in inc else "c28_h10"
    d, u = inc.get((key19, ref, q), (0.0, 0.0))
    if (key19, ref, q) not in inc:
        d, u = 0.0, abs(v25 - v05)            # no 19b data for this quantity: mesh step only
    return v25 + d, max(u, abs(v25 - v05), 0.5 * abs(d))   # central estimate, 1-sigma-like spread (not added to it)


def quantities(run):
    """{(ref, quantity): value} from one body-model run."""
    out = {("board", "peak_1mm_block"): run["peak_1mm_block"]["temperature_c"], ("board", "fet_row_max"): run["fet_row_max_c"]}
    for p in run["parts"]:
        out[(p["ref"], "pad_max_cell_c")] = p["pad_max_cell_c"]
        out[(p["ref"], "pad_mean_c")] = p["pad_mean_c"]
        if "tj_c" in p:
            out[(p["ref"], "tj_c")] = p["tj_c"]
            out[(p["ref"], "spec")] = p["spec"]
            out[(p["ref"], "watts")] = p["watts_into_model"]
    return out


def limits_for(qs, ref):
    """[(quantity, limit, basis, verified)] for one part in one run."""
    spec = qs.get((ref, "spec"))
    res = []
    if spec in VERIFIED:
        res.append(("tj_c", VERIFIED[spec], {"recom": "Tj abs max 150 (OTP 160+/-10)", "rgw": "TJ 125",
                                             "css2h": "element 170 operating max"}[spec], True))
    if spec == "css2h":
        p = qs[(ref, "watts")]
        res.append(("pad_max_cell_c", 170.0 - 100.0 * p / (0.8 * R5_RATED_W),
                    f"terminal derating at {p:.3f} W with the 20 % power margin (G6 rule)", True))
    if spec in ASSUMED_PATH:
        res.append(("tj_c", ASSUMED_PATH[spec], {"film_radial": "MKP Top,max 110 (TA + self-heating)", "film_4pin": "MKP Top,max 110",
                                                 "choke": "climatic upper 125", "chip1206": "1206 155 (unverified)"}[spec], False))
    return res


def main():
    inc = conv19b()
    out = {"basis": __doc__, "cases": {}, "sensitivities": {}, "h_estimate": h_estimate()}
    for cname, (op, h, note) in CASES.items():
        r25, r05 = load(f"{cname}_p0p25"), load(f"{cname}_p0p5")
        if not (r25 and r05):
            continue
        q25, q05 = quantities(r25), quantities(r05)
        rows = []
        v, u = estimate(cname, "board", "peak_1mm_block", q25[("board", "peak_1mm_block")], q05[("board", "peak_1mm_block")], inc)
        rows.append(dict(ref="board", rating="laminate KB-6164 MOT / RTI elec 130 C", quantity="1 mm-block copper peak",
                         est_c=v, unc_k=u, limit_c=MOT, verified=True, at=[r25["peak_1mm_block"]["x_mm"], r25["peak_1mm_block"]["y_mm"]]))
        fr = q25[("board", "fet_row_max")]
        rows.append(dict(ref="FET-row copper", rating="laminate MOT 130 C", quantity="FET-row copper max cell (0.25 mm)",
                         est_c=fr, unc_k=abs(fr - q05[("board", "fet_row_max")]), limit_c=MOT, verified=True))
        refs = sorted({k[0] for k in q25 if k[0] != "board" and k[1] == "tj_c"})
        for ref in refs:
            for q, lim, basis, ver in limits_for(q25, ref):
                v, u = estimate(cname, ref, q, q25[(ref, q)], q05[(ref, q)], inc)
                rows.append(dict(ref=ref, rating=basis, quantity={"tj_c": "junction / element / body node", "pad_max_cell_c": "terminal (pad max cell)"}[q],
                                 est_c=v, unc_k=u, limit_c=lim, verified=ver))
        for row in rows:
            row["margin_k_at"] = {b: round(row["limit_c"] - (row["est_c"] + (t - TAMB_MODEL)), 1) for b, t in BAY.items()}
            row["verdict_at"] = {b: classify(m, row["unc_k"]) for b, m in row["margin_k_at"].items()}
            row["est_c"], row["unc_k"], row["limit_c"] = round(row["est_c"], 1), round(row["unc_k"], 1), round(row["limit_c"], 1)
        # IRM-20: ambient-rated; the verdict is the local air the derating curve allows at the module's load
        ps = []
        for ref, load_w, rated_w, src in (("PS1", 4.83, 21.0, "controller verify ps1.p_total_W (DECISIONS 675)"),
                                         ("PS2", 9.59, 21.6, "80 kHz bias allocation (ALT-BIAS:52, ledger)")):
            frac = load_w / rated_w / 0.9                                   # ledger rule: <= 90 % of the derated power
            t_allow = 50 + (1 - frac) * 100 / 2.5 if frac >= 0.5 else 70 + (0.5 - frac) * 100 / 3.0
            ps.append(dict(ref=ref, load_w=load_w, rated_w=rated_w, load_source=src,
                           local_air_allowed_c=round(t_allow, 1),
                           margin_k_at={b: round(t_allow - t, 1) for b, t in BAY.items()},
                           board_pad_max_c=round(q25[(ref, "pad_max_cell_c")], 1),
                           note="local air at the module also includes the plume of the board under it (pad mean "
                                f"{q25[(ref, 'pad_mean_c')]:.0f} C at 50 C bay): bench-measure it"))
        out["cases"][cname] = {"op": op, "h": h, "note": note, "rows": rows, "irm20": ps,
                               "board_sha256": r25.get("board_sha256")}
    for op in ("c28", "c22"):
        base = load(f"{op}_h10_p0p5")
        if not base:
            continue
        qb = quantities(base)
        for s in SENS:
            name = f"{op}_{s}_p0p5" if s.startswith("h") else f"{op}_h10_p0p5_{s}"
            r = load(name)
            if not r:
                continue
            qs = quantities(r)
            keys = [("board", "peak_1mm_block"), ("board", "fet_row_max"), ("R5", "tj_c"), ("R5", "pad_max_cell_c"),
                    ("U41", "tj_c"), ("U42", "tj_c"), ("U26", "tj_c"), ("C40", "tj_c"), ("R58", "tj_c"), ("PS2", "pad_mean_c")]
            out["sensitivities"][f"{op}:{s}"] = {f"{k[0]}.{k[1]}": round(qs[k] - qb[k], 1) for k in keys if k in qs and k in qb}
    # still-air ceiling sweep (0.5 mm), corrected by c22_h10's (estimate - 0.5 mm value) per quantity
    c22 = out["cases"].get("c22_h10")
    b05 = load("c22_h10_p0p5")
    if c22 and b05:
        qb = quantities(b05)
        corr = {}
        for row in c22["rows"]:
            key = ("board", "peak_1mm_block") if row["ref"] == "board" else (
                ("board", "fet_row_max") if row["ref"] == "FET-row copper" else
                (row["ref"], "tj_c" if row["quantity"].startswith("junction") else "pad_max_cell_c"))
            if key in qb:
                corr[key] = row["est_c"] - qb[key]
        sweep = {}
        for ceil in (14, 16, 18, 20, 22):
            r = load(f"c{ceil}_h10_p0p5")
            if not r:
                continue
            q = quantities(r)
            p_r5 = q[("R5", "watts")]
            sweep[ceil] = {"board_block_est_c": round(q[("board", "peak_1mm_block")] + corr[("board", "peak_1mm_block")], 1),
                           "board_block_at": [r["peak_1mm_block"]["x_mm"], r["peak_1mm_block"]["y_mm"]],
                           "fet_row_est_c": round(q[("board", "fet_row_max")] + corr[("board", "fet_row_max")], 1),
                           "R5_element_est_c": round(q[("R5", "tj_c")] + corr[("R5", "tj_c")], 1),
                           "R5_terminal_est_c": round(q[("R5", "pad_max_cell_c")] + corr[("R5", "pad_max_cell_c")], 1),
                           "R5_terminal_limit_c": round(170.0 - 100.0 * p_r5 / (0.8 * R5_RATED_W), 1),
                           "U42_tj_est_c": round(q[("U42", "tj_c")] + corr[("U42", "tj_c")], 1),
                           "C40_body_est_c": round(q[("C40", "tj_c")] + corr[("C40", "tj_c")], 1)}
        out["ceiling_sweep_h10"] = {"note": "estimate incl. uncertainty, at 50 C; add (bay - 50) for other bay air", "rows": sweep}
        lim = {}
        for name, t in BAY.items():
            ok = [c for c, v in sweep.items() if v["board_block_est_c"] + (t - TAMB_MODEL) <= MOT
                  and v["R5_element_est_c"] + (t - TAMB_MODEL) <= 170.0 and v["U42_tj_est_c"] + (t - TAMB_MODEL) <= 150.0]
            lim[name] = max(ok) if ok else None
        out["ceiling_sweep_h10"]["max_ceiling_meeting_laminate_and_rated_parts_A"] = lim
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "verdict.json").write_text(json.dumps(out, indent=1) + "\n")
    write_md(out)


def classify(margin, unc):
    """VIOLATION: over the limit even at the optimistic end; EXCEEDS: central estimate over; THIN: inside, but not by
    the spread; OK otherwise."""
    if margin + unc < 0:
        return "VIOLATION"
    if margin < 0:
        return "EXCEEDS"
    if margin - unc < 0:
        return "THIN"
    return "OK"


def h_estimate():
    """Still-air board-face coefficient, order of magnitude: Incropera horizontal-plate correlations + radiation."""
    L = (0.290 * 0.140) / (2 * (0.290 + 0.140))       # characteristic length A/P of the 290 x 140 mm outline
    out = {}
    for dT in (50.0, 80.0):
        tf = 273.15 + 55 + dT / 2
        nu, alpha, k = 2.2e-5 * (tf / 363) ** 1.7, 3.1e-5 * (tf / 363) ** 1.7, 0.0305 * (tf / 363) ** 0.85
        ra = 9.81 * (1 / tf) * dT * L ** 3 / (nu * alpha)
        h_up = 0.54 * ra ** 0.25 * k / L              # hot surface facing up, 1e4 < Ra < 1e7
        h_dn = 0.52 * ra ** 0.2 * k / L               # hot surface facing down
        ts, ta = 273.15 + 55 + dT, 273.15 + 55
        h_rad = 0.9 * 5.67e-8 * (ts ** 2 + ta ** 2) * (ts + ta)   # to surroundings at bay air, view factor 1 (upper bound)
        out[f"dT_{int(dT)}K"] = {"Ra": round(ra), "h_conv_up": round(h_up, 1), "h_conv_down": round(h_dn, 1),
                                 "h_rad_upper_bound": round(h_rad, 1)}
    out["note"] = ("convection alone is 4-9 W/m2K; radiation adds up to ~9-10 only where a face sees cool walls (most of "
                   "the top face sees component bodies, the coil carrier and a 61-78 C bay). Still air therefore sits "
                   "near h 10-15; h 25 needs forced flow over the board, which no enclosure record provides.")
    return out


def write_md(out):
    L = ["# B3 hot spots against ratings (s32, body-level model)\n"]
    for c, d in out["cases"].items():
        L.append(f"\n## {c}: {d['note']}\n")
        L.append("| ref | rating | quantity | est C (50 C bay) | spread K | limit C | margin @50 | @55 | @61 | @78 | verdict @55 | source verified |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in sorted(d["rows"], key=lambda r: r["margin_k_at"]["model_50"])[:16]:
            m = r["margin_k_at"]
            L.append(f"| {r['ref']} | {r['rating']} | {r['quantity']} | {r['est_c']} | {r['unc_k']} | {r['limit_c']} | "
                     f"{m['model_50']} | {m['bay_expected_55']} | {m['bay_worst_B3only_61']} | {m['bay_stacked_78']} | "
                     f"{r['verdict_at']['bay_expected_55']} | {'yes' if r['verified'] else 'limit yes, package path ASSUMED'} |")
        for p in d["irm20"]:
            m = p["margin_k_at"]
            L.append(f"| {p['ref']} | IRM-20 ambient derating at {p['load_w']} W | local air allowed | - | - | "
                     f"{p['local_air_allowed_c']} | {m['model_50']} | {m['bay_expected_55']} | {m['bay_worst_B3only_61']} | {m['bay_stacked_78']} | {'OK' if m['bay_expected_55'] >= 0 else 'EXCEEDS'} (bay air, not board) | yes |")
    L.append("\n## Fix sensitivities (0.5 mm, delta K vs the same-mesh h10 baseline)\n")
    keys = sorted({k for v in out["sensitivities"].values() for k in v})
    L.append("| case:fix | " + " | ".join(keys) + " |")
    L.append("|---" * (len(keys) + 1) + "|")
    for s, v in out["sensitivities"].items():
        L.append(f"| {s} | " + " | ".join(str(v.get(k, "")) for k in keys) + " |")
    if "ceiling_sweep_h10" in out:
        L.append("\n## Still-air (h 10) ceiling sweep, estimate incl. uncertainty at 50 C bay\n")
        L.append("| ceiling A | board block | FET row | R5 element | R5 terminal / limit | U42 Tj | C40 body |")
        L.append("|---|---|---|---|---|---|---|")
        for c, v in out["ceiling_sweep_h10"]["rows"].items():
            L.append(f"| {c} | {v['board_block_est_c']} | {v['fet_row_est_c']} | {v['R5_element_est_c']} | "
                     f"{v['R5_terminal_est_c']} / {v['R5_terminal_limit_c']} | {v['U42_tj_est_c']} | {v['C40_body_est_c']} |")
        L.append(f"\nHighest ceiling meeting laminate 130 C, R5 170 C and U42 150 C: {out['ceiling_sweep_h10']['max_ceiling_meeting_laminate_and_rated_parts_A']}")
    L.append("\n## Still-air h estimate\n\n```\n" + json.dumps(out["h_estimate"], indent=1) + "\n```\n")
    (RESULTS / "VERDICT-TABLES.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
