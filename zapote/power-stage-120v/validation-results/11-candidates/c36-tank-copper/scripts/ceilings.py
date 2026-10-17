#!/usr/bin/env python3
"""Still-air ceilings from a margins.json pair of cases (c22 at 23.1 A trip, c28 at 29.4 A trip).

    python3 -I ceilings.py MARGINS.json [...]      -> one line per file

Every tank-current heat source scales with I^2 between the two cases and the rest is the same heat file, so each row's
margin is (nearly) linear in I_trip^2; the ceiling is the zero crossing / 1.05, bay 55 C.
Control: on the s38 margins (DECISIONS 51) this gives 21.5 A (laminate) and 21.0 A (laminate + film), as
refine-2026-10-15/results-s38/targets.json does by superposition. Bay 61 C is not reported: a flat -6 K shift gives
19.9 / 19.0 A against targets.json's 20.4 / 19.5 (the case temperature moves with the bay there), so it fails the control. Rows: laminate (block, FET row); laminate + HF film C38-C41 (candidate 36's scope); gate resistors
are candidate 39's and reported apart.
"""
import json
import sys

I22, I28 = 1.05 * 22.0, 1.05 * 28.0


def ceiling(m22, m28):
    a, b = I22 ** 2, I28 ** 2
    slope = (m28 - m22) / (b - a)
    if slope >= 0:
        return None
    x = a - m22 / slope
    return 0.0 if x <= 0 else round((x ** 0.5) / 1.05, 1)  # 0.0: the row fails with no tank current


def rows(d, pick):
    out = {}
    for c in ("c22_h10", "c28_h10"):
        for r in d["cases"][c]:
            if r["gated"] and pick(r["item"]):
                out.setdefault(r["item"], {})[c] = r["margin_k"]
    return out


def main():
    for f in sys.argv[1:]:
        d = json.load(open(f))
        res = {}
        for name, pick in (("laminate", lambda s: s.startswith("laminate")),
                           ("laminate+film", lambda s: s.startswith("laminate") or s[:3] in ("C38", "C39", "C40", "C41")),
                           ("gate R element", lambda s: "1206 element" in s)):
            cs = [ceiling(v["c22_h10"], v["c28_h10"]) for v in rows(d, pick).values()]
            cs = [c for c in cs if c is not None]
            res[name] = min(cs) if cs else None
        print(f, json.dumps(res))


if __name__ == "__main__":
    main()
