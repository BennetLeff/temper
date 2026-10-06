#!/usr/bin/env python3
"""Does remedy F6 fix hard turn-on (S4) on both legs? (round 17, native-19/20)

F6 = D-6's 1 ohm discharge + 1 nF Cgs + -2 V off bias. D-13 found it passes S4
on leg A's native-17 best matrix at 27/100 C (150 C indeterminate). Leg B's
power loop is larger (provisional matrix: S4 die VDS up to 537 V without F6),
so the remedy has to be judged on both legs before it can be chosen.

Deck: D-13's `decks/F6.cir` unchanged except D-14's `.options itl4=100000`
(physics-neutral, see f6_hot_itl4.py). Matrices: `legA-h0-best-n19` and
`legB-h0-prov-n19` (provisional, compose_legB_prov.py). Native-20 copper is
identical. Cases, at 27 and 100 C, both directions, ESL 1.06 / 10 nH:

  S4 hard turn-on  IL = -20 A, 170/198/280 V, dead time 391/443/498 ns
  S1 nominal       IL = 37 A,  198/280 V,     443 ns
  S2 fault         IL = 71 A,  280 V,         443 ns

Criteria (task table and D-13): die VDS <= 520 V (S1/S4), <= 585 V (S2);
|VGS| <= 30 V; off-gate < 3.0 V, < 1.9 V (hot screen) and < the model's own
threshold at Tj minus 0.5 V (D-13 results-threshold.json); ZVS for S1.

    python3 f6_legs.py [--workers 8]  ->  results/f6-legs/{results.json,summary.json,summary.md}
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import run_d2

HERE = Path(__file__).resolve().parent
D13 = HERE.parent / "delegation" / "out-D13"
OUT = HERE / "results" / "f6-legs"
PMEG = run_d2.KIT / "models" / "vendor" / "PMEG6030EP.txt"   # Nexperia model, fetch_models.sh (not committed)
TEMPS = (27, 100)
OPTION = ".options itl4=100000"
MATRICES = {"A": HERE / "legA-h0-best-n19.matrix.txt", "B": HERE / "legB-h0-prov-n19.matrix.txt"}
SCREEN = {r["temp_C"]: r["model_screen_V"] for r in json.loads((D13 / "results-threshold.json").read_text())}


def jobs(temps=TEMPS, case_set="decision", legs="AB"):
    if case_set == "startup":
        # S5: burst-start edge. Bridge idle, tank current 0, bus film caps still at the line peak
        # (or the 280 V maximum): the first turn-on hard-switches the full bus with no diode recovery.
        pts = [("S5", v, 0, dt) for v in (170, 198, 280) for dt in (391, 443, 498)]
        return list(itertools.product(legs, temps, pts, (0, 1), (1.06, 10)))
    pts = [("S4", v, -20, dt) for v in (170, 198, 280) for dt in (391, 443, 498)]
    pts += [("S1", v, 37, 443) for v in (198, 280)] + [("S2", 280, 71, 443)]
    return list(itertools.product(legs, temps, pts, (0, 1), (1.06, 10)))


def one(job):
    leg, temp, (case, vbus, il, dt), d, esl = job
    name = f"{leg}_T{temp}_{case}_v{vbus}_i{il}_d{d}_dt{dt}_esl{esl}"
    p = run_d2.matrix_params(run_d2.read_L(str(MATRICES[leg])))
    p.update(TJ=str(temp), VBUS=str(vbus), IL=str(il), DIR=str(d), DT=f"{dt}n", LESL=f"{esl}n", LSHUNT="2n", TRMAX="0.2n")
    keep = OUT / "runs" / name
    r = run_d2.run(OUT / "F6.cir", p, keep=keep)   # deck file name kept; content per --deck
    (keep / "IFX_CFD7_650V.lib").unlink(missing_ok=True)
    m = r["meas"]
    off, inc = ("ls", "hs") if d == 0 else ("hs", "ls")
    need = ["vds_ls_die_pk", "vds_hs_die_pk", f"vgs_{off}_off_max", f"vds_{inc}_at_on"] + \
           [f"vgs_{s}_die_{e}" for s in ("ls", "hs") for e in ("min", "max")]
    row = {"leg": leg, "temp_C": temp, "case": case, "vbus": vbus, "il": il, "dir": d, "dt_ns": dt, "esl_nH": esl}
    if r["aborted"] or r["failed"] or any(k not in m for k in need):
        row["status"] = "indeterminate"
        return row
    vds = max(m["vds_ls_die_pk"], m["vds_hs_die_pk"])
    offv = m[f"vgs_{off}_off_max"]
    vgs = max(abs(m[f"vgs_{s}_die_{e}"]) for s in ("ls", "hs") for e in ("min", "max"))
    lim = 585 if case == "S2" else 520
    row.update(status="complete", vds_pk=vds, off_V=offv, vgs_abs=vgs, incoming_V=m[f"vds_{inc}_at_on"],
               pass_vds=vds <= lim, pass_vgs=vgs <= 30, pass_3V=offv < 3.0, pass_1p9=offv < 1.9,
               pass_model=offv < SCREEN[temp], zvs=m[f"vds_{inc}_at_on"] <= 0.05 * vbus)
    row["pass"] = row["pass_vds"] and row["pass_vgs"] and row["pass_3V"] and row["pass_model"] and \
        (row["zvs"] if case == "S1" else True)
    row["pass_hot"] = row["pass"] and row["pass_1p9"]
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--diode", choices=["placeholder", "pmeg"], default="placeholder",
                    help="discharge diode: D-6's generic D6D, or the selected Nexperia PMEG6030EP vendor model (D-12)")
    ap.add_argument("--temps", default="27,100")
    ap.add_argument("--deck", choices=["F6", "baseline"], default="F6", help="D-13 deck: F6 remedy or the unipolar baseline")
    ap.add_argument("--cases", choices=["decision", "startup"], default="decision")
    ap.add_argument("--out", default=None)
    ap.add_argument("--matrix-b", default=None, help="leg B matrix file in d2/ (default: provisional)")
    ap.add_argument("--legs", default="AB")
    a = ap.parse_args()
    global OUT
    if a.out:
        OUT = HERE / "results" / a.out
    temps = tuple(int(x) for x in a.temps.split(","))
    if a.matrix_b:
        MATRICES["B"] = HERE / a.matrix_b
    OUT.mkdir(parents=True, exist_ok=True)
    deck = (D13 / "decks" / f"{a.deck}.cir").read_text()
    assert ".include params.inc" in deck
    deck = deck.replace(".include params.inc", ".include params.inc\n" + OPTION, 1)
    if a.diode == "pmeg" and a.deck == "F6":
        if not PMEG.is_file():
            raise SystemExit("PMEG6030EP model missing; run sim-kit/models/fetch_models.sh")
        old = ".model D6D D(Is=1u N=1 Rs=0.05 Cjo=20p Tt=0)\nDoffl gdl3 offl D6D"
        assert old in deck and "Doffh gdh3 offh D6D" in deck
        deck = deck.replace(old, f".include {PMEG}\nXDoffl gdl3 offl PMEG6030EP")
        deck = deck.replace("Doffh gdh3 offh D6D", "XDoffh gdh3 offh PMEG6030EP")
    (OUT / "F6.cir").write_text(deck)
    vendor = run_d2.KIT / "models" / "vendor" / "IFX_CFD7_650V.lib"
    if not vendor.is_file():
        raise SystemExit("vendor model missing; run sim-kit/models/fetch_models.sh")
    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(one, jobs(temps, a.cases, a.legs)))
    (OUT / "results.json").write_text(json.dumps(rows, indent=1) + "\n")
    summ = {"identity": {str(p.name): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (*MATRICES.values(), OUT / "F6.cir", Path(__file__), HERE / "run_d2.py")
                         + ((PMEG,) if a.diode == "pmeg" else ())}, "diode": a.diode,
            "model_screen_V": SCREEN, "groups": {}}
    lines = ["| leg | Tj °C | case | complete | pass (3.0 V + model + VDS) | pass incl. 1.9 V | max off-gate V | max die VDS V |",
             "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |"]
    for leg, temp, case in itertools.product(a.legs, temps, sorted({r["case"] for r in rows})):
        g = [r for r in rows if (r["leg"], r["temp_C"], r["case"]) == (leg, temp, case)]
        c = [r for r in g if r["status"] == "complete"]
        s = {"cases": len(g), "complete": len(c), "pass": sum(r["pass"] for r in c), "pass_hot": sum(r["pass_hot"] for r in c),
             "max_off_V": round(max((r["off_V"] for r in c), default=float("nan")), 3),
             "max_vds_V": round(max((r["vds_pk"] for r in c), default=float("nan")), 1)}
        summ["groups"][f"{leg}_T{temp}_{case}"] = s
        lines.append(f"| {leg} | {temp} | {case} | {s['complete']}/{s['cases']} | {s['pass']} | {s['pass_hot']} | {s['max_off_V']} | {s['max_vds_V']} |")
    (OUT / "summary.json").write_text(json.dumps(summ, indent=1) + "\n")
    (OUT / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
