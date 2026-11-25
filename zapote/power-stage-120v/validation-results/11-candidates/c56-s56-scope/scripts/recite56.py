#!/usr/bin/env python3
"""Stage 56 datasheet-ledger re-cite: every keyed B3 citation onto the s56 margins.json (board native21s56).

    python3 -I validation-results/11-candidates/c56-s56-scope/scripts/apply_ledger56.py
    python3 -I validation-results/11-candidates/c56-s56-scope/scripts/recite56.py   -> ledger.json (in place)

c55-findings/scripts/recite55.py with the stage-56 note. Run after the s56 chain; re-running gives the same file.
"""
import sys as _s; _s.dont_write_bytecode = True
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
MARGINS = PS / "validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json"
REL = str(MARGINS.relative_to(PS))
NOTE = ("S56 (2026-11-24, 11-candidates/c56-s56-scope): B3 rows re-cited to the s56 margins.json (R127 / R129 27 k -> 16 k, "
        "BOM only; no copper or heat-source change).")
m = json.loads(MARGINS.read_text())


def row(case, item):
    hits = [r for r in m["cases"][case] if " ".join(r["item"].split()[:3]) == item]
    assert len(hits) == 1, (case, item, len(hits))
    return hits[0]


def fmt(v):
    return f"{v:.1f}"


led = json.loads(LEDGER.read_text())
E = led["entries"]
touched = set()
for k, e in E.items():
    changed_s, changed_r = {}, {}
    for s in e.get("stresses", []):
        ev = s["evidence"] if isinstance(s["evidence"], list) else []
        for x in ev:
            if not (isinstance(x, dict) and x.get("file") == REL and "b3_row" in x):
                continue
            r = row(x["b3_row"]["case"], x["b3_row"]["item"])
            for f in ("est_c", "margin_k", "limit_c"):
                if f in x and abs(x[f] - r[f]) > 1e-9:
                    if f == "est_c" and abs(s["worst_case_value"] - x[f]) < 0.05:
                        changed_s[s["parameter"]] = (s["worst_case_value"], r[f])
                        s["worst_case_value"] = r[f]
                    x[f] = r[f]
                    touched.add(k)
    if k == "PS122WF680JT4E":
        for case, item, par in (("c17.5_h10", "R10: 2512 terminal", "Power derated at the c17.5 terminal estimate (release)"),
                                ("c22_h10", "R12: 2512 terminal", "Power derated at the c22 terminal estimate")):
            t = row(case, item)["est_c"]
            rt = next(r for r in e["ratings"] if r["parameter"] == par)
            v = round(2.0 * (155.0 - t) / 85.0, 4)          # PS12: 2 W at 70 C, zero at 155 C
            basis = re.sub(r"at T = [0-9.]+ C", f"at T = {fmt(t)} C", rt["basis"])
            if v != rt["datasheet_limit"] or basis != rt["basis"]:
                if v != rt["datasheet_limit"]:
                    changed_r[par] = (rt["datasheet_limit"], v)
                rt["datasheet_limit"], rt["basis"] = v, basis
                touched.add(k)
    if k == "CSS2H-2512R-1L00F":
        for case, tag in (("c17.5_h10", "c17.5"), ("c22_h10", "c22"), ("c28_h10", "c28")):
            t = row(case, "R5: terminal derating")["est_c"]
            rt = next(r for r in e["ratings"] if r["parameter"].startswith(f"P allowed at {tag} terminal "))
            new_par = re.sub(r"terminal [0-9.]+ C", f"terminal {fmt(t)} C", rt["parameter"])
            v = max(round(5.0 * (170.0 - t) / 100.0, 3), 0.001)
            basis = re.sub(r"\(170 - [0-9.]+\)", f"(170 - {fmt(t)})", rt["basis"])
            if new_par != rt["parameter"] or v != rt["datasheet_limit"] or basis != rt["basis"]:
                old_par = rt["parameter"]
                changed_r[new_par] = (rt["datasheet_limit"], v)
                for c in e["checks"]:
                    if c["rating"] == old_par:
                        c["rating"] = new_par
                rt["parameter"], rt["datasheet_limit"] = new_par, v
                rt["basis"] = re.sub(r"\(170 - [0-9.]+\)", f"(170 - {fmt(t)})", rt["basis"])
                touched.add(k)
    if changed_s or changed_r:
        S = {s["parameter"]: s["worst_case_value"] for s in e["stresses"]}
        R = {r["parameter"]: r["datasheet_limit"] for r in e["ratings"]}
        for c in e["checks"]:
            if c["stress"] in changed_s or c["rating"] in changed_r:
                c["ratio"] = round(S[c["stress"]] / R[c["rating"]], 4)
                for pair in (changed_s.get(c["stress"]), changed_r.get(c["rating"])):
                    if pair is not None and pair[0] > 10:          # temperatures only (the W limits are not quoted as such)
                        c["rule"] = c["rule"].replace(fmt(pair[0]), fmt(pair[1]))
    if k in touched and NOTE not in (e.get("notes") or ""):
        e["notes"] = ((e.get("notes") or "") + " " + NOTE).strip()

# PS122WF680JT4E's release-check rule quotes the R10 row's margin, the c22 power check the R12 terminal and margin
e = E["PS122WF680JT4E"]
r10, r12 = row("c17.5_h10", "R10: 2512 terminal"), row("c22_h10", "R12: 2512 terminal")
for c in e["checks"]:
    if c["id"] == "power c17.5 (release)":
        c["rule"] = f"<= 80 % of the derated power at the release terminal (B3 row R10 {r10['margin_k']:+.1f} K, 2 W line)"
    if c["id"] == "power c22":
        lim = next(r for r in e["ratings"] if r["parameter"] == "Power derated at the c22 terminal estimate")["datasheet_limit"]
        c["rule"] = (f"airflow route (c22/c28): 0.217 W against {lim} W at the {fmt(r12['est_c'])} C c22 terminal (R12; B3 "
                     f"row {r12['margin_k']:+.1f} K, hot copper, 2 W line)")

LEDGER.write_text(json.dumps(led, indent=1) + "\n")
print("ledger: touched", sorted(touched))
