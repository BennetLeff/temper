#!/usr/bin/env python3
"""Controls for the package-aware gate-resistor rows of b3_ratings_gate.py (candidate 39). Exit 1 if any fails.

    python3 -I gate_pkg_control.py RUNS_DIR [--out JSON]

RUNS_DIR holds c22_h10 / c28_h10 body solves (b3-ratings/run_basis.py). Checks:
  P1 the rows of every gate resistor follow its body-model package spec: 1206 -> 0.25 W line and the stage-29 strings,
     2512 -> 1 W line and the UniRoyal 25121WF basis;
  P2 the terminal-derating limit is 155 - 85 P / (0.8 P_rated) for the package found;
  P3 a 1206 run, relabelled 2512 with the same temperatures and watts, gains exactly 85 P (1/0.2 - 1/0.8) K of limit on
     that row (the rating is the only thing that changes);
  P4 a gate resistor in a package without a rating (spec 'chip0805') stops the gate instead of passing silently.
"""
import argparse
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
sys.path.insert(0, str(UNIT / "validation-results/04-board-current-thermal/round5-native21/b3-ratings"))
import b3_ratings_gate as g  # noqa: E402

GATE_ON = ("R10", "R12", "R18", "R20")


def rows_for(rows, ref):
    return [r for r in rows if r["item"].startswith(ref + ":")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("--out")
    a = ap.parse_args()
    runs = Path(a.runs)
    res, ok = {}, True
    for case in ("c22_h10", "c28_h10"):
        r25 = json.loads((runs / f"{case}_p0p25.json").read_text())
        r05 = json.loads((runs / f"{case}_p0p5.json").read_text())
        rows = g.evaluate(r25, r05, 55.0)
        parts = {p["ref"]: p for p in r25["parts"]}
        for ref in GATE_ON:
            spec, w = parts[ref]["spec"], parts[ref]["watts_into_model"]
            pkg, rated = {"chip1206": ("1206", 0.25), "chip2512": ("2512", 1.0)}[spec]
            rr = rows_for(rows, ref)
            der = [r for r in rr if "terminal derating" in r["item"]]
            ele = [r for r in rr if "element" in r["item"]]
            p1 = len(der) == 1 and len(ele) == 1 and der[0]["item"].startswith(f"{ref}: {pkg} terminal derating") \
                and ele[0]["item"].startswith(f"{ref}: {pkg} element 155 C")
            p2 = len(der) == 1 and abs(der[0]["limit_c"] - round(155.0 - 85.0 * w / (0.8 * rated), 1)) < 0.051
            res[f"P1_P2_{case}_{ref}"] = {"spec": spec, "watts": w, "rows": rr, "ok": p1 and p2}
            ok &= p1 and p2
        # P3: relabel a 1206 run as 2512 (or a 2512 run as 1206) and compare the derating limit
        ref = "R12"
        x25, x05 = copy.deepcopy(r25), copy.deepcopy(r05)
        other = "chip2512" if parts[ref]["spec"] == "chip1206" else "chip1206"
        for d in (x25, x05):
            for p in d["parts"]:
                if p["ref"] == ref:
                    p["spec"] = other
        w = parts[ref]["watts_into_model"]
        lim = {s: [r for r in rows_for(rr_, ref) if "terminal derating" in r["item"]][0]["limit_c"]
               for s, rr_ in ((parts[ref]["spec"], rows), (other, g.evaluate(x25, x05, 55.0)))}
        expect = 85.0 * w * (1 / 0.2 - 1 / 0.8)
        p3 = abs((lim["chip2512"] - lim["chip1206"]) - expect) < 0.11
        res[f"P3_{case}"] = {"limits": lim, "expected_gain_K": round(expect, 2), "ok": p3}
        ok &= p3
        # P4: an unrated package must stop the gate
        for d in (x25, x05):
            for p in d["parts"]:
                if p["ref"] == ref:
                    p["spec"] = "chip0805"
        try:
            g.evaluate(x25, x05, 55.0)
            p4 = False
        except SystemExit as e:
            p4 = "no rating for gate resistor R12" in str(e)
        res[f"P4_{case}"] = {"ok": p4}
        ok &= p4
    res["all_controls_pass"] = ok
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    for k, v in res.items():
        print(k, v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != "rows"})
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
