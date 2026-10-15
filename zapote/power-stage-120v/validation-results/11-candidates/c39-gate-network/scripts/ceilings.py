#!/usr/bin/env python3
"""Still-air ceilings from a margins.json pair of cases (c22 at 23.1 A trip, c28 at 29.4 A trip): candidate 36's method
(c36-tank-copper/scripts/ceilings.py), with the gate-network rows named for candidate 39.

    python3 -I ceilings.py MARGINS.json [...]      -> one JSON line per file

Every tank-current heat source scales with I^2 between the two cases and the rest of the heat file (gate drive, drivers,
RECOM, U26) is the same, so each row's margin is (nearly) linear in I_trip^2; the ceiling is the zero crossing / 1.05.
The bay is whatever the margins file was solved at (run_basis.py --bay-c): bay 61 is solved, not shifted, because the
FET case tie moves with the bay (candidate 36's control rejects a flat shift).
Control: on c36's s38 margins this gives candidate 36's 21.5 A (laminate) and 21.0 A (laminate + film).
Rows:
  laminate          laminate block peak and FET-row copper;
  laminate+film     plus the HF film caps C38-C41 (candidate 36's scope);
  gate R_on         R10 / R12 / R18 / R20 terminal derating and element (1206 on s41, 2512 on s42);
  gate R_off        R53 / R54 / R57 / R58 (1 ohm 1206 turn-off resistors) terminal derating and element;
  all gated         every gated row.
A row that fails with no tank current reads 0.0 (its margin is negative at I = 0).
"""
import json
import sys

I22, I28 = 1.05 * 22.0, 1.05 * 28.0
RON = ("R10", "R12", "R18", "R20")
ROFF = ("R53", "R54", "R57", "R58")


def ceiling(m22, m28):
    a, b = I22 ** 2, I28 ** 2
    slope = (m28 - m22) / (b - a)
    if slope >= 0:
        return None
    x = a - m22 / slope
    return 0.0 if x <= 0 else round((x ** 0.5) / 1.05, 1)


def rows(d, pick):
    out = {}
    for c in ("c22_h10", "c28_h10"):
        for r in d["cases"][c]:
            if r["gated"] and pick(r["item"]):
                out.setdefault(r["item"], {})[c] = r["margin_k"]
    return out


PICKS = (("laminate", lambda s: s.startswith("laminate")),
         ("laminate+film", lambda s: s.startswith("laminate") or s[:3] in ("C38", "C39", "C40", "C41")),
         ("gate R_on", lambda s: s.split(":")[0] in RON),
         ("gate R_off", lambda s: s.split(":")[0] in ROFF),
         ("all gated", lambda s: True))


def main():
    for f in sys.argv[1:]:
        d = json.load(open(f))
        res = {}
        for name, pick in PICKS:
            got = {k: ceiling(v["c22_h10"], v["c28_h10"]) for k, v in rows(d, pick).items() if len(v) == 2}
            got = {k: c for k, c in got.items() if c is not None}
            if got:
                k = min(got, key=got.get)
                res[name] = {"ceiling_A": got[k], "row": k}
            else:
                res[name] = None
        print(f, json.dumps(res))


if __name__ == "__main__":
    main()
