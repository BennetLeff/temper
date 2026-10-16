#!/usr/bin/env python3
"""Datasheet-ledger edit: a datasheet temperature rating plus release / c28 local-temperature stresses for every BOM line
whose entry had no temperature rating (temp-ratings 2026-10-15, s47 board 4139c87b). Style of
validation-results/11-candidates/c47-ref25-grade/scripts/ledger47.py.

    python3 -I ledger_temps.py [--ledger COPY/ledger.json] [--results results.json]

Edits ledger.json in place (default: the unit ledger; integrated after 2f7241f61, re-applied over the S20 re-cite); it no longer refuses
a ledger inside a worktree. Re-running it on the edited ledger gives the same file (rows it added
are replaced, never duplicated).

Per entry:
* rating "Temperature rating (<applies-to>)" [C], basis + datasheet page from results.json (scripts/ratings_table.py);
  resistors get "Terminal temperature limit at P (derating line, 20 % margin)" for the worst ref too;
* stresses "Local temperature, release case (c17.5_h10 @ 61 C)" and "Local temperature, c28_h10 @ 55 C": the worst ref's
  B3 estimate; evidence = the proposed committed home of results.json (HOME below), plus keyed margins.json rows where
  the gate already has a row for the ref, plus the c47 monitor sweep for the semiconductors it lists;
* checks: release, severity violation (max 1.0); c28, severity gap (max 1.0; an overrun is the airflow-route owner gap,
  as for the other c28 rows, DECISIONS 56);
* status: UNAUDITED -> PARTIAL (temperature audited, electrical ratings still open: stated as a gap); VERIFIED stays
  VERIFIED only if no check fails; a failing release check -> VIOLATION with a finding.
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
HOME = "validation-results/04-board-current-thermal/round5-native21/b3-ratings/temp-ratings-2026-10-15"
MARGINS = "validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json"
SWEEP = "validation-results/11-candidates/c47-ref25-grade/results/monitor-sweep-s47.json"
TAG = "temp-ratings 2026-10-15"
REL, C28 = "c17.5_h10", "c28_h10"
P_REL = "Local temperature, release case (c17.5_h10 @ 61 C)"
P_C28 = "Local temperature, c28_h10 @ 55 C"
R_TEMP = "Temperature rating"
R_TERM = "Terminal temperature limit at P (derating line, 20 % margin)"


def keyed_rows(margins, case, ref):
    """margins.json rows for ref in case, as gate keyed-citation dicts (first three item tokens)."""
    out = []
    for r in margins["cases"][case]:
        if r["item"].split(":")[0] == ref:
            out.append({"file": MARGINS, "b3_row": {"case": case, "item": " ".join(r["item"].split()[:3])},
                        "est_c": r["est_c"], "margin_k": r["margin_k"]})
    return out


def evidence(rec, case, margins, sweep_refs):
    w = rec["release" if case == REL else "c28"]
    ev = [f"{HOME}/results.json; {HOME}/results.md; {HOME}/scripts/temp_ratings.py"]
    if w["ref"] in sweep_refs:
        ev.append(SWEEP)
    ev += keyed_rows(margins, case, w["ref"])
    return ev


def build(rec, margins, sweep_refs):
    R = rec["rating"]
    rel, c28 = rec["release"], rec["c28"]
    applies = R["applies"]
    rat = [{"parameter": f"{R_TEMP} ({applies})", "datasheet_limit": R["t_max_c"], "unit": "C",
            "basis": R["basis"] + f" [{TAG}]", "source": R["source"]}]
    if rec["model"] == "res":
        lim_r, lim_c = rel["limit_c"], c28["limit_c"]
        rat.append({"parameter": f"{R_TERM}, release worst ref {rel['ref']}", "datasheet_limit": lim_r, "unit": "C",
                    "basis": f"{R['res'][2]:g} - ({R['res'][2]:g} - {R['res'][1]:g}) x {rel['p_w']:.4g} W / (0.8 x "
                             f"{R['res'][0]:g} W): {R['source']} derating line with the G6 20 % power margin ({rel['p_basis']})",
                    "source": R["source"]})
        rat.append({"parameter": f"{R_TERM}, c28 worst ref {c28['ref']}", "datasheet_limit": lim_c, "unit": "C",
                    "basis": f"same line at {c28['p_w']:.4g} W ({c28['p_basis']})", "source": R["source"]})
        r_rel, r_c28 = rat[1]["parameter"], rat[2]["parameter"]
    else:
        r_rel = r_c28 = rat[0]["parameter"]

    def cond(w, case, bay):
        s = f"{rec['refs'] and w['ref']}: {w['what']}; B3 hot-copper estimate (gate estimator, pad-copper probe"
        if "self_heat_k" in w:
            s += f" {w['pad_c']} C + self-heat {w['self_heat_k']} K at {w['p_w']:.3g} W ({w['p_basis']})"
            if w.get("extra_k"):
                s += f" + {w['extra_k']} K ({w['extra_basis']})"
        elif "element_c" in w:
            s += f"; body element {w['element_c']} C"
        s += f"), {case} still air at bay {bay:g} C; worst of {len(rec['refs'])} ref(s); board s47 4139c87b"
        return s

    st = [{"parameter": P_REL, "worst_case_value": rel["est_c"], "unit": "C", "condition": cond(rel, REL, 61),
           "evidence": evidence(rec, REL, margins, sweep_refs)},
          {"parameter": P_C28, "worst_case_value": c28["est_c"], "unit": "C", "condition": cond(c28, C28, 55),
           "evidence": evidence(rec, C28, margins, sweep_refs)}]
    lim_rel = next(r["datasheet_limit"] for r in rat if r["parameter"] == r_rel)
    lim_c28 = next(r["datasheet_limit"] for r in rat if r["parameter"] == r_c28)
    ck = [{"id": f"temperature, release case ({TAG})", "rating": r_rel, "stress": P_REL, "max_ratio": 1.0,
           "severity": "violation", "rule": f"{rel['est_c']} C <= {lim_rel} C ({rel['ref']})",
           "ratio": round(rel["est_c"] / lim_rel, 4)},
          {"id": f"temperature, c28 ({TAG})", "rating": r_c28, "stress": P_C28, "max_ratio": 1.0, "severity": "gap",
           "rule": f"{c28['est_c']} C <= {lim_c28} C ({c28['ref']}); an overrun is the airflow-route (c22/c28) owner gap",
           "ratio": round(c28["est_c"] / lim_c28, 4)}]
    if rec["model"] == "res" and "element_c" in rel:
        rat.append({"parameter": f"{R_TEMP} (element)", "datasheet_limit": R["t_max_c"], "unit": "C",
                    "basis": "element / body at the top of the operating range", "source": R["source"]})
        for case, w, sev in ((REL, rel, "violation"), (C28, c28, "gap")):
            p = f"Element temperature, {case}"
            st.append({"parameter": p, "worst_case_value": w["element_c"], "unit": "C",
                       "condition": f"{w['ref']}: B3 body model tj_c", "evidence": evidence(rec, case, margins, sweep_refs)})
            ck.append({"id": f"element, {case} ({TAG})", "rating": f"{R_TEMP} (element)", "stress": p, "max_ratio": 1.0,
                       "severity": sev, "rule": f"{w['element_c']} C <= {R['t_max_c']} C", "ratio": round(w["element_c"] / R["t_max_c"], 4)})
    return rat, st, ck


def apply(e, rec, margins, sweep_refs):
    keep = lambda lst, k: [x for x in lst if TAG not in str(x.get(k, "")) and not str(x.get("parameter", "")).startswith(
        (R_TEMP, R_TERM, "Local temperature, release case (c17.5", "Local temperature, c28_h10 @", "Element temperature, c"))]
    e["ratings"] = keep(e["ratings"], "basis")
    e["stresses"] = keep(e["stresses"], "condition")
    e["checks"] = [c for c in e["checks"] if TAG not in c.get("id", "")]
    was_unaudited = e["status"] == "UNAUDITED" or any(g.startswith(f"[{TAG}] only the temperature rating") for g in e["gaps"])
    e["gaps"] = [g for g in e["gaps"] if not g.startswith(f"[{TAG}]")]
    rat, st, ck = build(rec, margins, sweep_refs)
    e["ratings"] += rat
    e["stresses"] += st
    e["checks"] += ck
    rel, c28 = rec["release"], rec["c28"]
    gaps = [f"[{TAG}] the local temperature is the B3 body-model estimate (pad copper as the local-ambient / die proxy, "
            "hot copper, still air at the BASIS bays), not a measurement" + (f"; {rec['rating']['gap']}" if rec["rating"].get("gap") else "")]
    if c28["margin_k"] < 0:
        gaps.append(f"[{TAG}] owner: airflow route (c22/c28): at c28_h10 (28 A, bay 55 C, still air) {c28['ref']} is "
                    f"{c28['est_c']} C against {c28['limit_c']} C ({c28['margin_k']:+.1f} K); the firmware ships 17.5 A "
                    "(DECISIONS 61), where it is " f"{rel['est_c']} C ({rel['margin_k']:+.1f} K)")
    if was_unaudited:
        gaps.append(f"[{TAG}] only the temperature rating is audited; the electrical ratings (voltage, current, power) of "
                    "this line are not yet in the ledger")
        e["status"] = "PARTIAL"
    failing_rel = rel["margin_k"] < 0
    if failing_rel:
        e["status"] = "VIOLATION"
        e["finding"] = (f"[{TAG}] {rel['ref']} {rel['est_c']} C over its {rel['limit_c']} C rating at the release case "
                        f"c17.5_h10 @ 61 C ({rel['margin_k']:+.1f} K)")
    elif c28["margin_k"] < 0 and e["status"] == "VERIFIED":
        e["status"] = "PARTIAL"
    e["gaps"] = e["gaps"] + gaps if e["status"] != "VERIFIED" else e["gaps"]
    return e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=str(HERE.parents[4] / "native-21/verification/datasheet-ledger/ledger.json"))
    ap.add_argument("--results", default=str(HERE / "results.json"))
    ap.add_argument("--margins", default=str(HERE.parent / "margins.json"))
    ap.add_argument("--sweep", default="/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v/" + SWEEP)
    a = ap.parse_args()
    lp = Path(a.ledger).resolve()
    led = json.loads(lp.read_text())
    res = json.loads(Path(a.results).read_text())
    margins = json.loads(Path(a.margins).read_text())
    sw = json.loads(Path(a.sweep).read_text())
    sweep_refs = {r["ref"] for r in sw["sweep_unrated"] + sw["sweep_rated_le_105c"]}
    n = 0
    for rec in res["lines"]:
        if "release" not in rec:
            continue
        e = led["entries"][rec["mpn"]]
        assert set(e["designators"]) == set(rec["refs"]), rec["mpn"]
        apply(e, rec, margins, sweep_refs)
        n += 1
    lp.write_text(json.dumps(led, indent=1) + "\n")
    st = {}
    for e in led["entries"].values():
        st[e["status"]] = st.get(e["status"], 0) + 1
    print(f"ledger_temps: {n} entries edited in {lp}; statuses {st}")


if __name__ == "__main__":
    main()
