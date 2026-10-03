#!/usr/bin/env python3
"""Round 17 D2: run leg_matrix.cir from a FEM port matrix.

    run_d2.py --matrix FILE [--leg A] --vbus 170 --il 37 --dir 0 --esl 10 [--dt 348] [--step 0.2]
    run_d2.py --wiring-check

FILE holds a RESULT line with "L_nH" (inductance_matrix.py) or "L0_nH"
(extrapolate.py). Ports are P1 (first capacitor), P2 (second), P3 (gate
high), P4 (gate low), in that order, as in the FEM campaign.

--wiring-check: with every board inductance ~0 and no coupling, the matrix
deck and round 3's complementary_leg.cir describe the same circuit (local
capacitance 0.4 uF in both), so their die peaks must agree. A miswired node
shows up as a mismatch.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
POWER = HERE.parents[3]
KIT = POWER / "validation-plan" / "sim-kit"
sys.path.insert(0, str(KIT / "common"))
sys.path.insert(0, str(HERE.parent / "scripts"))
from run_ngspice import run  # noqa: E402
import matrix_gate  # noqa: E402

DECK = HERE / "leg_matrix.cir"
R3DECK = POWER / "validation-results/01-switching-parasitics/round3/b1-board-grid/complementary_leg.cir"
MEAS = ("vds_ls_die_pk", "vds_hs_die_pk", "vgs_ls_die_max", "vgs_ls_die_min", "vgs_hs_die_max", "vgs_hs_die_min",
        "vgs_ls_off_max", "vgs_hs_off_max")


def read_L(path: str) -> list[list[float]]:
    """Port matrix in deck order P1 (first cap), P2, P3 (gate high), P4 (gate low).
    The order is checked (D-4 review, P2): recorded port names must start with
    P1..P4 in sequence; otherwise physical ids must ascend; extrapolate.py
    output carries its names."""
    for line in open(path):
        if line.startswith("RESULT "):
            d = json.loads(line[7:])
            names = [p["name"] for p in d.get("port_identity", [])] or d.get("names") or []
            if names and [n[:2] for n in names] != [f"P{k + 1}" for k in range(len(names))]:
                raise SystemExit(f"{path}: port order {names} is not P1..P{len(names)}")
            phys = [int(p) for p in d.get("ports", []) if str(p).isdigit()]
            if phys and phys != sorted(phys):
                raise SystemExit(f"{path}: ports {phys} not ascending")
            L = d.get("L0_nH") or d["L_nH"]
            matrix_gate.check(L, path)                    # square, finite, symmetric, SPD (D-9)
            return L
    raise ValueError(f"no RESULT in {path}")


def matrix_params(L: list[list[float]]) -> dict[str, str]:
    n = len(L)                       # 4 (leg_matrix.cir) or 5 (leg_matrix5.cir, P5 = bulk C6)
    p = {f"LP{i + 1}": f"{L[i][i]:.9g}n" for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            p[f"K{i + 1}{j + 1}"] = f"{L[i][j] / math.sqrt(L[i][i] * L[j][j]):.9g}"
    return p


def case(params: dict, tag: str) -> dict:
    r = run(DECK, params, keep=HERE / "runs" / tag)
    return {"tag": tag, "aborted": r["aborted"], "meas": {k: r["meas"].get(k) for k in MEAS}, "params": params}


def wiring_check() -> None:
    tiny = "0.01n"
    base = {"VBUS": "170", "IL": "37", "DIR": "0", "DT": "348n", "TRMAX": "0.2n"}
    new = dict(base, LP1=tiny, LP2=tiny, LP3=tiny, LP4=tiny, K12="0", K13="0", K14="0", K23="0", K24="0", K34="0",
               LESL=tiny, LSHUNT=tiny, LBULK="30n", C38="0.2u", C39="0.2u")
    old = dict(base, LD_HS=tiny, LS_HS=tiny, LD_LS=tiny, LS_LS=tiny, LCS=tiny, LCAP=tiny, LBULK="30n",
               LG_HS=tiny, LG_LS=tiny, CLOC="0.4u")
    a = run(DECK, new, keep=HERE / "runs" / "wiring-new")
    b = run(R3DECK, old, keep=HERE / "runs" / "wiring-round3")
    rows = {k: (a["meas"].get(k), b["meas"].get(k)) for k in MEAS if not k.endswith("_off_max")}
    print(json.dumps({"aborted": [a["aborted"], b["aborted"]], "new_vs_round3": rows}, indent=1))
    bad = [k for k, (x, y) in rows.items() if x is None or y is None or abs(x - y) > 0.01 * max(1.0, abs(y))]
    print("RESULT " + json.dumps({"wiring_ok": not bad and not a["aborted"] and not b["aborted"], "mismatch": bad}))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiring-check", action="store_true")
    ap.add_argument("--matrix")
    ap.add_argument("--vbus", default="170")
    ap.add_argument("--il", default="37")
    ap.add_argument("--dir", default="0")
    ap.add_argument("--esl", default="10", help="capacitor ESL, nH")
    ap.add_argument("--shunt", default="2", help="shunt inductance, nH")
    ap.add_argument("--dt", default="348", help="dead time, ns")
    ap.add_argument("--step", default="0.2", help="max time step, ns")
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    if a.wiring_check:
        wiring_check()
        return
    p = matrix_params(read_L(a.matrix))
    p.update(VBUS=a.vbus, IL=a.il, DIR=a.dir, LESL=f"{a.esl}n", LSHUNT=f"{a.shunt}n", DT=f"{a.dt}n", TRMAX=f"{a.step}n")
    tag = a.tag or f"v{a.vbus}_i{a.il}_d{a.dir}_esl{a.esl}"
    r = case(p, tag)
    print("RESULT " + json.dumps(r))


if __name__ == "__main__":
    main()
