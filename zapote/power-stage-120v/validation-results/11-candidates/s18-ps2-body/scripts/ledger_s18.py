#!/usr/bin/env python3
"""S18 datasheet-ledger edit: re-cite the B3 rows to the S18 margins.json and give MPM-20-24 its B3 local-air stress.

    python3 -I scripts/ledger_s18.py    -> native-21/verification/datasheet-ledger/ledger.json (in place)

The PS2 body-to-air path moves every B3 row a little (0.33 W less heat into the board at the release case), so the
ledger's keyed citations into b3-ratings/margins.json (README "Generated b3-ratings/margins.json is cited by key") go
stale. For every stress evidence {file: margins.json, b3_row, est_c / margin_k / limit_c}:
  * the cited numbers take the row's new values; the stress's worst_case_value follows when it equalled the old est_c;
  * ratings derived from a cited terminal row follow it (25121WF680JT4E: 1 W x (155 - T) / 85 at the R10 c17.5 / R12
    c22 terminal; CSS2H-2512R-1L00F: 5 W x (170 - T) / 100, parameter names carry T);
  * every check on a changed stress or rating gets its ratio recomputed (stress / limit, 4 places, the gate's rule) and
    the old number replaced by the new one in its rule text.
MPM-20-24 gains the B3 PS2 row (local air against the p.3 curve at the as-built load, 90 % rule) as a keyed stress and a
check. Re-running it on the edited ledger gives the same file.
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
NOTE = ("S18 (2026-10-15, 11-candidates/s18-ps2-body): B3 rows re-cited to the margins.json with PS2's body-to-air path "
        "(0.33 W less heat into the board at the release case).")
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
    if k == "25121WF680JT4E":
        for case, item, par in (("c17.5_h10", "R10: 2512 terminal", "Power derated at the c17.5 terminal estimate (release)"),
                                ("c22_h10", "R12: 2512 terminal", "Power derated at the c22 terminal estimate")):
            t = row(case, item)["est_c"]
            rt = next(r for r in e["ratings"] if r["parameter"] == par)
            v = round(1.0 * (155.0 - t) / 85.0, 4)
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

# 25121WF680JT4E's release-check rule quotes the R10 row's margin, the c22 power check the R12 terminal and margin
e = E["25121WF680JT4E"]
r10, r12 = row("c17.5_h10", "R10: 2512 terminal"), row("c22_h10", "R12: 2512 terminal")
for c in e["checks"]:
    if c["id"] == "power c17.5 (release)":
        c["rule"] = re.sub(r"B3 row R10 [+-][0-9.]+ K", f"B3 row R10 {r10['margin_k']:+.1f} K", c["rule"])
    if c["id"] == "power c22":
        lim = next(r for r in e["ratings"] if r["parameter"] == "Power derated at the c22 terminal estimate")["datasheet_limit"]
        c["rule"] = (f"airflow route (c22/c28): 0.217 W against {lim} W at the {fmt(r12['est_c'])} C c22 terminal (R12; B3 "
                     f"row {r12['margin_k']:+.1f} K, hot copper)")

# MPM-20-24: the B3 PS2 row (OPEN-ITEMS S18) as a keyed stress and check
e = E["MPM-20-24"]
rel_case = next(c for c, v in m["basis"]["cases"].items() if v["role"] == "release")
ps2 = {c: next(r for r in rows if r["item"].startswith("PS2: ")) for c, rows in m["cases"].items()}
worst = min(ps2, key=lambda c: ps2[c]["margin_k"])
rp = {"parameter": "Ambient limit at the as-built load (90 % rule)", "datasheet_limit": ps2[rel_case]["limit_c"], "unit": "C",
      "basis": f"p.3 Derating Curve (12V~24V, HORIZONTAL; x-axis 'AMBIENT TEMPERATURE'): the ambient at which 0.9 x curve x "
               f"21.6 W = {ps2[rel_case]['p_out_w']} W (the B3 heat row's 60 kHz window-top load, 32.8 %); "
               f"{ps2[rel_case]['limit_curve_c']} C on the curve itself; p.2 'WORKING TEMP. -35 ~ +85 C (Refer to "
               f"\"Derating Curve\")'", "source": "p.2 ENVIRONMENT; p.3 Derating Curve"}
sp = {"parameter": "Local air at PS2, B3 (release case)", "worst_case_value": ps2[rel_case]["est_c"], "unit": "C",
      "condition": f"B3 hot-copper gated row PS2 (body-to-air path, OPEN-ITEMS S18): bay {m['basis']['cases'][rel_case]['bay_c']:g} C "
                   f"+ the 15 K board-heated-air rule (layer estimate {ps2[rel_case]['air_layer_k']} K), {rel_case}; "
                   f"case node {ps2[rel_case]['case_c']} C, pads {ps2[rel_case]['pad_max_c']} C (reported, not rated); "
                   f"worst BASIS margin {ps2[worst]['margin_k']:+.1f} K ({worst})",
      "evidence": [{"file": REL, "b3_row": {"case": rel_case, "item": "PS2: MPM-20-24 local"}, "est_c": ps2[rel_case]["est_c"],
                    "limit_c": ps2[rel_case]["limit_c"]}]}
for lst, new in ((e["ratings"], rp), (e["stresses"], sp)):
    for i, x in enumerate(lst):
        if x["parameter"] == new["parameter"]:
            lst[i] = new
            break
    else:
        lst.append(new)
ck = {"id": "local air (B3, release)", "rating": rp["parameter"], "stress": sp["parameter"], "max_ratio": 1.0,
      "severity": "violation", "rule": f"{sp['worst_case_value']} C <= {rp['datasheet_limit']} C (B3 gate row PS2, "
                                       f"{ps2[rel_case]['margin_k']:+.1f} K)",
      "ratio": round(sp["worst_case_value"] / rp["datasheet_limit"], 4)}
for i, c in enumerate(e["checks"]):
    if c["id"] == ck["id"]:
        e["checks"][i] = ck
        break
else:
    e["checks"].append(ck)
if NOTE not in (e.get("notes") or ""):
    e["notes"] = ((e.get("notes") or "") + " S18 (2026-10-15): B3 now models PS2's case-to-air path and rates its local "
                  "air (the quantity p.2 / p.3 rate) against the p.3 curve at the as-built load; the 9.59 W allocation "
                  "would read 70.5 C (90 % rule) against the same 76.0 C air. " + NOTE).strip()
LEDGER.write_text(json.dumps(led, indent=1) + "\n")
print("ledger: touched", sorted(touched | {"MPM-20-24"}))
