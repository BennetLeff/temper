#!/usr/bin/env python3
"""D-31 part 1: device stress when the protection turns the bridge off at fault current.

Uses the round-17 D2 deck unchanged (`d2/leg_matrix.cir`, which carries
D-14's `.options itl4=100000`) on the native-19 best matrix
(`d2/legA-h0-best-n19.matrix.txt`). A DIS shutdown turns the conducting
device off and leaves its partner off; the deck turns the outgoing device
off at T1 and commands the partner on one dead time later, so the turn-off
overshoot of interest occurs in the first dead time window either way (the
partner then turns on into its own conducting body diode). Currents:

  60 A   CT trip region (round 3: 50.56-60.01 A static, 59.87 A at OR)
  85 A   shunt OCP static maximum (round 3: 85.55 A)
  106 A  shunt-filter overshoot at 3 MA/s (round 3: 102.64 A) plus the
         downstream ledger delay at the tank's maximum di/dt (280 V / 70 uH)
  120 A  margin

Outputs: survival.json, survival.md. Screens: die VDS <= 520 V (task 01
screen) and < 650 V (IPW65R018CFD7 V(BR)DSS; single-pulse avalanche current
IAS is only 8.3 A, so breakdown at these currents is outside the rating).
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
D2 = HERE.parents[1] / "d2"
sys.path.insert(0, str(D2))
import run_d2  # noqa: E402

MATRIX = D2 / "legA-h0-best-n19.matrix.txt"
CURRENTS = (60, 85, 106, 120)


def cases(currents):
    return list(itertools.product((198, 280), currents, (0, 1), (1.06, 10)))


def one(c):
    vbus, il, d, esl = c
    tag = f"v{vbus}_i{il}_d{d}_esl{esl}"
    p = run_d2.matrix_params(run_d2.read_L(str(MATRIX)))
    p.update(VBUS=str(vbus), IL=str(il), DIR=str(d), LESL=f"{esl}n", LSHUNT="2n", DT="443n", TRMAX="0.2n")
    r = run_d2.run(run_d2.DECK, p, keep=HERE / "runs" / tag)
    (HERE / "runs" / tag / "IFX_CFD7_650V.lib").unlink(missing_ok=True)
    m = r["meas"]
    out = "ls" if d == 0 else "hs"
    vds = [m.get("vds_ls_die_pk"), m.get("vds_hs_die_pk")]
    ok = not r["aborted"] and all(v is not None for v in vds)
    return {"vbus": vbus, "il": il, "dir": d, "esl_nH": esl, "aborted": r["aborted"],
            "vds_pk": max(vds) if ok else None, "outgoing": out,
            "vgs_abs_max": max(abs(m[k]) for k in ("vgs_ls_die_max", "vgs_ls_die_min", "vgs_hs_die_max", "vgs_hs_die_min"))
            if ok else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currents", default=",".join(map(str, CURRENTS)), help="comma list of turn-off currents (A)")
    ap.add_argument("--out", default="survival", help="output basename (.json/.md)")
    a = ap.parse_args()
    todo = cases([int(x) for x in a.currents.split(",")])
    vendor = run_d2.KIT / "models" / "vendor" / "IFX_CFD7_650V.lib"
    if not vendor.is_file():
        raise SystemExit("vendor model missing; run sim-kit/models/fetch_models.sh")
    with ProcessPoolExecutor(8) as ex:
        rows = list(ex.map(one, todo))
    for r in rows:
        r["pass_520"] = r["vds_pk"] is not None and r["vds_pk"] <= 520
        r["pass_650"] = r["vds_pk"] is not None and r["vds_pk"] < 650
    (HERE / f"{a.out}.json").write_text(json.dumps({"matrix": str(MATRIX.relative_to(HERE.parents[5])), "rows": rows}, indent=1) + "\n")
    lines = ["| Bus V | I off A | dir | ESL nH | die VDS peak V | <= 520 V | < 650 V |", "| ---: | ---: | ---: | ---: | ---: | --- | --- |"]
    for r in rows:
        v = "aborted" if r["vds_pk"] is None else f"{r['vds_pk']:.1f}"
        lines.append(f"| {r['vbus']} | {r['il']} | {r['dir']} | {r['esl_nH']} | {v} | {r['pass_520']} | {r['pass_650']} |")
    (HERE / f"{a.out}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
