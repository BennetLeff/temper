#!/usr/bin/env python3
"""Refresh the datasheet ledger's B3 citations to the hot-copper margins.json of the s46 board (OPEN-ITEMS S17).

    python3 -I scripts/ledger_b3_refresh46.py   -> native-21/verification/datasheet-ledger/ledger.json (in place)

Why: the B3 hot-copper lane (cb65ce911, merged 4d9104a9e) re-solved b3-ratings/margins.json with copper loss at its own
temperature but made no ledger edits, so 30 keyed citations in 10 entries (all B3 temperature stresses) no longer match
the file and the ledger gate refuses them (stale est_c). The s46 chain re-solved margins.json on the s46 board (copper
identical to s45), so this refresh applies to s45 equally. It is mechanical, with two re-derivations and one re-basis:

  1. every keyed citation's est_c and its stress worst_case_value move to the margins.json row; the stress condition
     gains a note; every check of a touched entry is recomputed (ratio) and old numbers in its rule are replaced;
  2. derived ratings re-derived on their own stated curves at the new temperature: CSS2H-2512R "P allowed at <case>
     terminal T" = 5 W x (170 - T) / 100 (p.3 curve); RC1206FR "P derated at T" = 0.25 x (155 - T) / 85 (Fig. 10-1).
     Past the curve's end (CSS2H c28 terminal 184.6 C > 170 C) the check compares the terminal with the 170 C
     zero-power point instead (no power is allowed there);
  3. CC1206JKNPOCBN102 / GRM1885C1H472JA01D: the release check was the FET-row laminate copper as an upper bound for the
     caps (no row of their own). On hot copper that bound reads 126.1 C against the caps' 125 C. The run files now carry
     the caps' own pad-copper estimates (results/cap-probes-s46.md, the B3 gate's estimator): 116.7 C (C20) and 120.3 C
     (C56) at c18 @ 61. The pad estimate becomes the release (violation) check; the FET-row bound stays as a gap row.
A check that still fails at violation severity raises (status would have to change: not done silently).
Re-running it on the refreshed ledger changes nothing.
"""
import sys as _s; _s.dont_write_bytecode = True
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
MREL = "validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json"
M = json.loads((PS / MREL).read_text())
BOARD = set(M["board_sha256"].values())
assert len(BOARD) == 1
BOARD = BOARD.pop()
CAPS = json.loads((HERE.parent / "results/cap-probes-s46.json").read_text())
CAPS_MD = (HERE.parent / "results/cap-probes-s46.md").read_text().splitlines()
CAPS_REL = str((HERE.parent / "results/cap-probes-s46.md").relative_to(PS))
assert CAPS["board_sha256"] == BOARD
NOTE = f" [hot-copper BASIS, re-solved on the s46 board {BOARD[:8]} (copper = s45); ledger refresh c46]"


def row(case, item):
    hits = [r for r in M["cases"][case] if " ".join(r["item"].split()[:3]) == item]
    assert len(hits) == 1, (case, item)
    return hits[0]


def fmt(x):
    return f"{x:g}"


def refresh_entry(mpn, e):
    subs = {}       # old number string -> new number string (temperatures, derived limits)
    touched = False
    for s in e["stresses"]:
        ev = s.get("evidence")
        for c in (ev if isinstance(ev, list) else [ev]):
            if isinstance(c, dict) and "est_c" in c:
                new = row(c["b3_row"]["case"], c["b3_row"]["item"])["est_c"]
                old = c["est_c"]
                if abs(new - old) > 0.05:
                    c["est_c"] = new
                    if s["worst_case_value"] == old:
                        s["worst_case_value"] = new
                    subs[fmt(old)] = fmt(new)
                    touched = True
                if touched and NOTE not in s.get("condition", ""):
                    s["condition"] = s.get("condition", "") + NOTE
    if not touched:
        return False
    ratings = {r["parameter"]: r for r in e["ratings"]}
    renames = {}
    for r in e["ratings"]:
        p = r["parameter"]
        for old, new in list(subs.items()):
            if f" {old} C" not in p:
                continue
            t = float(new)
            if mpn == "CSS2H-2512R-1L00F" and p.startswith("P allowed at"):
                if t >= 170:
                    np_ = p.split(" terminal ")[0].replace("P allowed at", "Terminal zero-power point,") + " terminal"
                    renames[p] = np_
                    r.update(parameter=np_, datasheet_limit=170, unit="C",
                             basis="the p.3 terminal derating curve reaches 0 W at 170 C; past it no power is allowed")
                else:
                    lim = round(5 * (170 - t) / 100, 3)
                    subs[fmt(r["datasheet_limit"])] = fmt(lim)
                    renames[p] = p.replace(f" {old} C", f" {new} C")
                    r.update(parameter=renames[p], datasheet_limit=lim, basis=r["basis"].replace(old, new))
            elif mpn == "RC1206FR-07470KL" and p.startswith("P derated at"):
                lim = round(0.25 * (155 - t) / 85, 4)
                renames[p] = p.replace(f" {old} C", f" {new} C")
                r.update(parameter=renames[p], datasheet_limit=lim, basis=r["basis"].replace(old, new))
    for c in e["checks"]:
        if c["rating"] in renames:
            c["rating"] = renames[c["rating"]]
            if ratings.get(c["rating"]) is None and c["rating"].startswith("Terminal zero-power point"):
                pass
    # CSS2H c28: the check against the curve end compares the terminal temperature
    for c in e["checks"]:
        if c["rating"].startswith("Terminal zero-power point"):
            case = c["rating"].split(",")[1].split()[0]          # "c28"
            c["stress"] = f"T terminal {case}"
    ratings = {r["parameter"]: r for r in e["ratings"]}
    stresses = {s["parameter"]: s for s in e["stresses"]}
    for c in e["checks"]:
        r, s = ratings[c["rating"]], stresses[c["stress"]]
        ratio = round(s["worst_case_value"] / r["datasheet_limit"], 4)
        if ratio != c["ratio"]:
            rule = c["rule"]
            for old, new in sorted(subs.items(), key=lambda kv: -len(kv[0])):
                rule = rule.replace(old, new)
            if c["rating"].startswith("Terminal zero-power point"):
                rule = (f"airflow route (c22/c28): terminal {fmt(s['worst_case_value'])} C is past the curve's 170 C "
                        "zero-power point (no power allowed)")
            c["ratio"], c["rule"] = ratio, rule
        if c["severity"] == "violation" and ratio > c["max_ratio"] + 1e-9:
            raise SystemExit(f"[{mpn}] check {c['id']} fails at violation severity after the refresh: {ratio} > "
                             f"{c['max_ratio']} - re-audit by hand")
    return True


def caps(mpn, e, refs):
    """The caps' own pad estimate as the release check; the FET-row bound stays as a gap row."""
    def line(case):
        hits = [i + 1 for i, l in enumerate(CAPS_MD) if l.startswith(f"| {mpn} | {case} |")]
        assert len(hits) == 1
        return f"{CAPS_REL}:{hits[0]}"
    out = {}
    for case, tag in (("c18_h10", "c18 (release)"), ("c22_h10", "c22")):
        p = {r: CAPS["cases"][case]["pads_c"][r] for r in refs}
        w = max(p, key=p.get)
        out[tag] = (p[w], w, line(case))
    names = {tag: f"Pad temperature, {tag}" for tag in out}
    stresses = [s for s in e["stresses"] if s["parameter"] not in names.values()]
    for tag, (t, w, ev) in out.items():
        stresses.append({"parameter": names[tag], "worst_case_value": t, "unit": "C",
                         "condition": f"the caps' own pad-copper estimate (B3 gate estimator, hot copper), worst of "
                                      f"{' / '.join(refs)} ({w}); board {BOARD[:8]}", "evidence": ev})
    e["stresses"] = stresses
    checks = [c for c in e["checks"] if not c["id"].startswith("pad temperature")]
    for c in checks:
        if c["id"] == "temperature bound c18 (release)":
            c["severity"] = "gap"
            c["rule"] = (f"FET-row copper bound {fmt(next(s for s in e['stresses'] if s['parameter'] == c['stress'])['worst_case_value'])} "
                         "C vs 125 C at the release case: the bound used before the caps had their own estimate; since "
                         "stage 46 the release check is 'pad temperature c18 (release)'")
    lim = 125
    t18, t22 = out["c18 (release)"][0], out["c22"][0]
    checks += [{"id": "pad temperature c18 (release)", "rating": "Operating temperature max", "stress": names["c18 (release)"],
                "max_ratio": 1.0, "severity": "violation", "rule": f"{fmt(t18)} C <= 125 C at the release case (pad estimate)",
                "ratio": round(t18 / lim, 4)},
               {"id": "pad temperature c22", "rating": "Operating temperature max", "stress": names["c22"],
                "max_ratio": 1.0, "severity": "gap", "rule": f"airflow route (c22/c28): {fmt(t22)} C pad estimate vs 125 C",
                "ratio": round(t22 / lim, 4)}]
    e["checks"] = checks
    if t18 > lim:
        raise SystemExit(f"[{mpn}] pad estimate {t18} C over 125 C at the release case")


def main():
    led = json.loads(LEDGER.read_text())
    E = led["entries"]
    changed = []
    # the caps first: their release check moves to the pad estimate before the generic refresh judges it
    for mpn, refs in (("CC1206JKNPOCBN102", ["C12", "C13", "C19", "C20"]),
                      ("GRM1885C1H472JA01D", ["C55", "C56", "C62", "C63"])):
        caps(mpn, E[mpn], refs)
    for mpn, e in E.items():
        if refresh_entry(mpn, e):
            changed.append(mpn)
    # the CSS2H release element rule carried the pre-S17 caveat (a 4 K copper under-correction): hot copper now holds it
    for c in E["CSS2H-2512R-1L00F"]["checks"]:
        if c["id"] == "element c18 (release)":
            t = next(s for s in E["CSS2H-2512R-1L00F"]["stresses"] if s["parameter"] == c["stress"])["worst_case_value"]
            c["rule"] = f"{fmt(t)} C <= 85 % of 170 C (144.5 C); hot copper, so the former 4 K under-correction is in the value"
    LEDGER.write_text(json.dumps(led, indent=1) + "\n")
    print("refreshed:", changed)


if __name__ == "__main__":
    main()
