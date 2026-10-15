#!/usr/bin/env python3
"""B3 ratings gate: margin of the board's hot spots to the laminate's UL temperature and to each hot part's datasheet
limit, at the declared operating basis. Proposed home: validation-results/04-board-current-thermal/round5-native21/
b3-ratings/ (thermal-ratings audit, 2026-10-15).

    python3 b3_ratings_gate.py --runs DIR [--out margins.json] [--cases c18_h10@61,c22_h10@55,c28_h10@55]
                               [--release c18_h10] [--bay-c 55]

--cases takes CASE or CASE@BAY. CASE = c<ceiling>_h<h>[_jet<h_top>[a<air C>]]: the _jet suffix is an airflow case
(run_basis.JET_REGION at h_top on the top face, air at <air C>, default the bay; b3-ratings/jet-2026-10-15). Airflow
cases are labelled role "airflow": they never decide the release verdict and stay out of the ratchet metrics.
A case's bay is, first to apply: its @BAY, --bay-c, the bay_c its run files were solved at (run_basis.py writes it), BASIS, 55 C. A run file solved at another bay than the one asked for stops the gate (the FET
tab tie is absolute, so a bay is solved, not shifted). Default --cases: BASIS (with --bay-c alone: c22_h10,c28_h10,
the pre-2026-10-15 form). --release: the cases whose gated rows decide the verdict (default: the BASIS release cases
present); with none, every case decides it (the pre-2026-10-15 rule, still what gate_control.py uses).

DIR holds body-level B3 solves (b3-convergence/body_runs.run_case JSON, fill-fraction copper + package networks) named
<case>_p0p25.json and <case>_p0p5.json. The legacy thermal.py single-cell peak is NOT an input: it is a point-deposit
artefact that moves 50-80 K with the mesh (b3-convergence README section 1).

Estimate per quantity: Q(0.25) + K_MESH * |Q(0.25) - Q(0.5)| + (bay - 50 C). K_MESH = 3 reproduces the stage-19b
0.0625-0.125 mm window increments for the board block peak within ~1 K (it bounds the remaining error for observed
orders p >= 0.4); R5's element converges more slowly (p ~ 0.2) and is under-corrected by ~4 K - see the audit's
gate_control G6 table.

Basis (decided in the audit, DECISIONS 46; release case after DECISIONS 55; change only with evidence):
  * h 10 W/m2K is still air - the enclosure's bay model has no through-flow and D-18 ducts the blower through the sink
    only. A forced-air case counts only once an enclosure record gives the board-face airflow.
  * release case c18_h10 at bay 61 C: the 18.0 A release ceiling (DECISIONS 55) at its 1.05 x trip, at the enclosure R33
    study 14 worst bay with B3 heat (61 C). The b3_ratings release gate passes only if every gated row passes here;
    metric b3_release_margin_K = its worst gated margin.
  * ratchet cases c22_h10 (22 A) and c28_h10 (28 A Kconfig ceiling) at bay 55 C (study 14 expected value at a 40 C
    kitchen): b3_laminate_margin_K / b3_rated_part_margin_K, the card-to-card ratchets since s32.
  * line current 13.5 A in every case (run_study.I_LINE_A, the firmware inlet bound; was the 11.1 A hold to 2026-10-15).
Limits (sources re-read 2026-10-15; see the audit's ratings.py for page-level quotes):
  laminate 130 C   Kingboard KB-616(X) (KB-6164 / KB-6064) UL QMTS2 E123995 (2026-02-20): multilayer Max Oper Temp 130,
                   RTI elec 130 - applied to the 1 mm-block copper peak and the FET-row copper
  RECOM R24C2T25/R junction 150 C (Rev. 1-2024 p.2; OTP 160 +/- 10 C p.8)
  TPS7A4700        junction 125 C (SBVS204G p.4, p.6)
  CSS2H-2512R      element 170 C (REV 06/17/20 p.1); terminal <= 170 - 100 * P / (0.8 * 5 W) (p.3 curve, G6 20 % rule)
  HF film C38-C41 TDK B32652A0104K000 Top,max 110 C = TA + self-heating (B3265* June 2026 p.2, p.35, p.78) - gated
                   (thermal-refine 2026-10-15: the limit is a datasheet maximum; the body node is reached through the
                   assumed 50 K/W lead path. To 2026-10-15 it had no body-to-air path, an upper bound for a cap heated
                   from its leads; since jet-2026-10-15 the body loses heat to air from its p.14 9.0 x 17.5 x 18.0 mm
                   box at the local h, as a fin from its end contacts: thermal_body.film_body_g_air. The solve keeps the
                   weak 50 K/W lead tie (conservative for the board rows); the row is the run's top_bound_c, the body
                   tied to its hotter pad through copper leads over the 0.62 mm seat (thermal_body.FILM_HF_STRONG,
                   conservative for the cap))
  gate resistors   package-aware (candidate 39): the body model's package spec of each part picks the rating.
                   1206: R10/R12/R18/R20 FH RS-06L8R20FT (V11.0 2026-04-28 p.2) to stage 41 and R53/R54/R57/R58 UniRoyal
                   1206W4F100KT5E (V.3 p.4/9, p.5/9): 1/4 W at 70 C derating to 0 W at 155 C, range -55..155 C.
                   2512: R10/R12/R18/R20 UniRoyal 25121WF680JT4E from stage 42 (thick-film chip resistor data sheet V.3
                   2019-02-12: p.4/9 table 6 1 W at 70 C; p.5/9 table 7 -55..155 C, section 9 figure 1 linear to 0 W
                   at 155 C). Gated on the element (155 C) and on the derating line at the terminal with the R5 20 %
                   power margin; a gate resistor in any other package stops the gate
  advisory (limit known, package path assumed): bank MKP 110 C (board share only), DC-link C5/C6 TDK B32676G1905K000
                   Top,max 105 C case (B3267* June 2026 p.13; 110 C until 2026-10-15), B82726 125 C (p.4), other
                   1206 (MPNs not re-read)

Exit 0 if every gated margin of the release case(s) (or, with none, of every case) is >= 0, else 1. Advisory rows never
fail the gate.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MOT_C = 130.0
TAMB_MODEL_C = 50.0
K_MESH = 3.0
R5_RATED_W = 5.0
GATED = {"recom": ("Tj abs max (RECOM Rev.1-2024 p.2)", 150.0), "rgw": ("TJ max (TI SBVS204G p.4)", 125.0),
         "css2h": ("element max (Bourns CSS2H p.1)", 170.0)}
ADVISORY = {"film_radial": ("MKP Top,max (TDK June 2026 p.35)", 110.0), "film_4pin": ("MKP Top,max 105 C case (TDK B3267* June 2026 p.13)", 105.0),
            "choke": ("B82726 climatic upper (TDK p.4)", 125.0), "chip1206": ("1206 thick film (unverified)", 155.0)}
GATED_REFS = {r: ("MKP Top,max 110 C (TDK B3265* June 2026 p.35)", 110.0, None) for r in ("C38", "C39", "C40", "C41")}
# gate resistors: (ref group, body-model package spec) -> (basis, element limit C, rated W at 70 C); 0 W at 155 C
GATE_R = {"R10": "on", "R12": "on", "R18": "on", "R20": "on", "R53": "off", "R54": "off", "R57": "off", "R58": "off"}
GATE_R_PKG = {("on", "chip1206"): ("1206 element 155 C (FH RS-06L V11.0 p.2)", 155.0, 0.25),
              ("off", "chip1206"): ("1206 element 155 C (UniRoyal 1206W4F V.3 p.5/9)", 155.0, 0.25),
              ("on", "chip2512"): ("2512 element 155 C (UniRoyal 25121WF V.3 p.5/9)", 155.0, 1.0)}
PKG_NAME = {"chip1206": "1206", "chip2512": "2512"}
BASIS = {"c18_h10": {"ceiling_a": 18.0, "h": 10, "bay_c": 61.0, "role": "release"},
         "c22_h10": {"ceiling_a": 22.0, "h": 10, "bay_c": 55.0, "role": "ratchet"},
         "c28_h10": {"ceiling_a": 28.0, "h": 10, "bay_c": 55.0, "role": "ratchet"}}


CASE_RE = re.compile(r"^c(\d+(?:\.\d+)?)_h(\d+)(?:_jet(\d+(?:\.\d+)?)(?:a(\d+(?:\.\d+)?))?)?$")


def _case_match(case: str):
    m = CASE_RE.match(case)
    if not m:
        raise SystemExit(f"b3_ratings_gate: case {case!r} is not c<ceiling>_h<h>[_jet<h_top>[a<air C>]]")
    return m


def case_ceiling_h(case: str):
    """'c18_h10' -> (18.0, 10); 'c28_h10_jet100' -> (28.0, 10)."""
    m = _case_match(case)
    return float(m.group(1)), int(m.group(2))


def case_jet(case: str):
    """None for a still-air case; {'h_top': W/m2K, 'air_c': C or None (= the bay)} for an airflow case."""
    m = _case_match(case)
    if m.group(3) is None:
        return None
    return {"h_top": float(m.group(3)), "air_c": None if m.group(4) is None else float(m.group(4))}


def parse_cases(spec, bay):
    """'c18_h10@61,c22_h10' -> {case: bay or None}; an entry's @BAY wins over `bay`."""
    if isinstance(spec, dict):
        return dict(spec)
    items = spec.split(",") if isinstance(spec, str) else list(spec)
    out = {}
    for it in items:
        c, _, b = it.strip().partition("@")
        v = float(b) if b else bay
        if c in out and out[c] != v:       # one run file name per case: a second bay would overwrite the first
            raise SystemExit(f"b3_ratings_gate: case {c} given at two bays ({out[c]}, {v}); solve each bay in its own --runs")
        out[c] = v
    return out


def est(v25, v05, bay):
    return v25 + K_MESH * abs(v25 - v05) + (bay - TAMB_MODEL_C)


def evaluate(r25: dict, r05: dict, bay: float):
    p05 = {p["ref"]: p for p in r05["parts"]}
    rows = [dict(item="laminate: 1 mm-block copper peak", gated=True, limit_c=MOT_C,
                 est_c=est(r25["peak_1mm_block"]["temperature_c"], r05["peak_1mm_block"]["temperature_c"], bay),
                 at=[r25["peak_1mm_block"]["x_mm"], r25["peak_1mm_block"]["y_mm"], r25["peak_1mm_block"]["layer"]])]
    if r25.get("fet_row_max_c") is not None and r05.get("fet_row_max_c") is not None:
        rows.append(dict(item="laminate: FET-row copper", gated=True, limit_c=MOT_C,
                         est_c=est(r25["fet_row_max_c"], r05["fet_row_max_c"], bay)))
    for p in r25["parts"]:
        spec, q = p.get("spec"), p05.get(p["ref"])
        if spec is None or q is None:
            continue
        if p["ref"] in GATE_R:
            key = (GATE_R[p["ref"]], spec)
            if key not in GATE_R_PKG:
                raise SystemExit(f"b3_ratings_gate: no rating for gate resistor {p['ref']} in package spec {spec!r}")
            basis, lim, rated_w = GATE_R_PKG[key]
            rows.append(dict(item=f"{p['ref']}: {basis}", gated=True, limit_c=lim, est_c=est(p["tj_c"], q["tj_c"], bay)))
            lim_t = 155.0 - 85.0 * p["watts_into_model"] / (0.8 * rated_w)
            rows.append(dict(item=f"{p['ref']}: {PKG_NAME[spec]} terminal derating at {p['watts_into_model']:.3f} W "
                                  f"(20 % margin)", gated=True, limit_c=lim_t,
                             est_c=est(p["pad_max_cell_c"], q["pad_max_cell_c"], bay)))
        elif p["ref"] in GATED_REFS:
            basis, lim, rated_w = GATED_REFS[p["ref"]]
            key = "top_bound_c" if "top_bound_c" in p else "tj_c"     # the strong-tie bound once a body-air path exists
            rows.append(dict(item=f"{p['ref']}: {basis}", gated=True, limit_c=lim, est_c=est(p[key], q[key], bay)))
        elif spec in GATED:
            basis, lim = GATED[spec]
            rows.append(dict(item=f"{p['ref']}: {basis}", gated=True, limit_c=lim, est_c=est(p["tj_c"], q["tj_c"], bay)))
            if spec == "css2h":
                lim_t = 170.0 - 100.0 * p["watts_into_model"] / (0.8 * R5_RATED_W)
                rows.append(dict(item=f"{p['ref']}: terminal derating at {p['watts_into_model']:.3f} W (20 % margin)", gated=True,
                                 limit_c=lim_t, est_c=est(p["pad_max_cell_c"], q["pad_max_cell_c"], bay)))
        elif spec in ADVISORY:
            basis, lim = ADVISORY[spec]
            rows.append(dict(item=f"{p['ref']}: {basis}", gated=False, limit_c=lim, est_c=est(p["tj_c"], q["tj_c"], bay)))
    for r in rows:
        r["margin_k"] = round(r["limit_c"] - r["est_c"], 1)
        r["est_c"], r["limit_c"] = round(r["est_c"], 1), round(r["limit_c"], 1)
    return rows


def run(runs: Path, cases, bay: float | None = None, release=None):
    """cases: CASE / CASE@BAY strings or {case: bay}. release: cases whose gated rows decide `pass` (None: the BASIS
    release cases present; empty: every case). Ratchet metrics are over the other cases."""
    cases = parse_cases(cases, bay)
    if release is None:
        release = [c for c in cases if BASIS.get(c, {}).get("role") == "release"]
    release = list(release)
    if set(release) - set(cases):
        raise SystemExit(f"b3_ratings_gate: release case(s) {sorted(set(release) - set(cases))} not among {list(cases)}")
    airflow = [c for c in cases if case_jet(c) is not None]
    if set(release) & set(airflow):
        raise SystemExit(f"b3_ratings_gate: airflow case(s) {sorted(set(release) & set(airflow))} cannot be release cases "
                         "(the release basis is still air until a measured board-face h exists)")
    out = {"basis": {"cases": {}, "release": release, "k_mesh": K_MESH, "mot_c": MOT_C}, "cases": {}}
    for c, want in cases.items():
        f25, f05 = runs / f"{c}_p0p25.json", runs / f"{c}_p0p5.json"
        if not (f25.exists() and f05.exists()):
            raise SystemExit(f"b3_ratings_gate: missing {f25.name} or {f05.name} in {runs}")
        r25, r05 = json.loads(f25.read_text()), json.loads(f05.read_text())
        shas = {r25.get("board_sha256"), r05.get("board_sha256")}
        if len(shas) != 1:
            raise SystemExit(f"b3_ratings_gate: {c} meshes come from different boards {shas}")
        out.setdefault("board_sha256", {})[c] = shas.pop()
        solved = {r25.get("bay_c"), r05.get("bay_c")} - {None}
        b = want if want is not None else (solved.pop() if len(solved) == 1 else BASIS.get(c, {}).get("bay_c", 55.0))
        if solved and solved != {b}:
            raise SystemExit(f"b3_ratings_gate: {c} was solved at bay {sorted(solved)} C, asked for {b} C "
                             "(the FET tab tie is absolute: solve the bay, do not shift it)")
        lines = {r25.get("i_line_a"), r05.get("i_line_a")}
        if len(lines) != 1:
            raise SystemExit(f"b3_ratings_gate: {c} meshes use different line currents {lines}")
        jet = case_jet(c)
        regs = [r.get("region") for r in (r25, r05)]
        if jet is None and any(regs):
            raise SystemExit(f"b3_ratings_gate: {c} is a still-air case but its run files carry an airflow region")
        if jet is not None:
            want_rise = 0.0 if jet["air_c"] is None else jet["air_c"] - b
            for r in regs:
                if not r or r["h_top"] != jet["h_top"] or abs(r["t_air_rise_k"] - want_rise) > 1e-9:
                    raise SystemExit(f"b3_ratings_gate: {c} run files do not carry its region (h_top {jet['h_top']}, "
                                     f"air rise {want_rise} K over the bay): {r}")
        out["basis"]["cases"][c] = {"bay_c": b, "i_line_a": lines.pop(), "i_t_a": None if r25.get("i_t_a") is None else round(r25["i_t_a"], 3), "h": r25.get("h"),
                                    "role": "release" if c in release else "airflow" if jet else "ratchet"}
        if jet is not None:
            out["basis"]["cases"][c]["airflow"] = {"region_xy_mm": regs[0]["xy_mm"], "h_top": jet["h_top"],
                                                   "air_c": b + regs[0]["t_air_rise_k"], "face": regs[0].get("face"),
                                                   "body_air_credited": regs[0].get("body_air_credited")}
        rows = evaluate(r25, r05, b)
        out["cases"][c] = sorted(rows, key=lambda r: r["margin_k"])
    ratchet = ([c for c in cases if c not in release and c not in airflow] or [c for c in cases if c not in release]
               or list(cases))
    rr = [r for c in ratchet for r in out["cases"][c]]
    lam = [r["margin_k"] for r in rr if r["item"].startswith("laminate")]
    part = [r["margin_k"] for r in rr if r["gated"] and not r["item"].startswith("laminate")]
    adv = [r["margin_k"] for r in rr if not r["gated"]]
    worst = min((r for r in rr if r["gated"]), key=lambda r: r["margin_k"])
    out["metrics"] = {"b3_laminate_margin_K": min(lam), "b3_rated_part_margin_K": min(part),
                      "b3_advisory_margin_K": min(adv) if adv else None, "worst_gated": worst["item"],
                      "ratchet_cases": ratchet}
    decide = release or list(cases)
    gated = [(c, r) for c in decide for r in out["cases"][c] if r["gated"]]
    if release:
        wc, wr = min(gated, key=lambda t: t[1]["margin_k"])
        out["metrics"].update(b3_release_margin_K=wr["margin_k"], release_worst_gated=f"{wc}: {wr['item']}",
                              release_failing_rows=[f"{c}: {r['item']} {r['margin_k']:+.1f} K"
                                                    for c, r in gated if r["margin_k"] < 0])
    out["pass"] = all(r["margin_k"] >= 0 for _, r in gated)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out")
    ap.add_argument("--bay-c", type=float, help="bay for cases without @BAY (default: the run files' own, then BASIS)")
    ap.add_argument("--cases", help="default: BASIS; with --bay-c alone, the pre-2026-10-15 pair c22_h10,c28_h10")
    ap.add_argument("--release", help="comma list of release cases (default: BASIS release cases present; '' = none)")
    a = ap.parse_args()
    rel = None if a.release is None else [c for c in a.release.split(",") if c]
    if a.cases is None:
        a.cases = ("c22_h10,c28_h10" if a.bay_c is not None else
                   ",".join(f"{c}@{b['bay_c']:g}" for c, b in BASIS.items()))
    res = run(Path(a.runs), a.cases, a.bay_c, rel)
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    m, bs = res["metrics"], res["basis"]
    desc = ", ".join(f"{c} bay {v['bay_c']:g} C I_line {v['i_line_a']} A" + (" (release)" if v["role"] == "release" else "")
                     for c, v in bs["cases"].items())
    rel_s = (f"release margin {m['b3_release_margin_K']} K ({m['release_worst_gated']}); " if bs["release"] else "")
    print(f"b3 ratings gate ({desc}): {rel_s}ratchet laminate margin {m['b3_laminate_margin_K']} K, rated-part "
          f"margin {m['b3_rated_part_margin_K']} K, advisory {m['b3_advisory_margin_K']} K; ratchet worst gated: "
          f"{m['worst_gated']} -> {'PASS' if res['pass'] else 'FAIL'}")
    raise SystemExit(0 if res["pass"] else 1)


if __name__ == "__main__":
    main()
