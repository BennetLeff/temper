#!/usr/bin/env python3
"""U11 / U12 divider options for the Rev E extended-line consolidation (2026-10-29).

python3 validation/power-spurs/ldo_divider_options.py   -> ldo_divider_options.json

Same corner method as regulator_check.py (exact ratio bound, every resistor of a leg at the same
tolerance extreme, x(1 +- 2.5 %) LDO overall accuracy), with and without resistor TCR at
25 +- 35 C (opposite drift of the two legs).  "R5 row" = TPS65131 raw-rail minimum - VOUT max -
2x estimated load x 1 ohm (R95/R96), the regulator_check.py "Option R5" row; target >= 1 V.
Raw minima come from regulator_check.py's own functions on the current design (R81/R82, R83+R111/R84).
Part 1 compares candidate dividers; part 2 enumerates U12 dividers built only from the 0.1 % /
25 ppm values already on the BOM (series legs, divider current 5 uA ... 0.5 mA, |VOUT| min >= 11.3 V).
"""
import itertools
import json
import pathlib

import common as c
import regulator_check as rc

HERE = pathlib.Path(__file__).resolve().parent
DT = rc.DT_BOARD
RAW_MIN = {"pos": (rc.boost_vpos("min"), rc.boost_vpos("min", True)),
           "neg": (abs(rc.inverter_vneg("min")), abs(rc.inverter_vneg("min", True)))}
VFB = {"pos": abs(c.TPS7A49["vfb_typ"]), "neg": abs(c.TPS7A30["vfb_typ"])}
ACC = {"pos": c.TPS7A49["acc_overall"], "neg": c.TPS7A30["acc_overall"]}
LOAD2 = {k: 2 * v for k, v in rc.LOAD.items()}


def corners(kind, top, bot, tol, tcr):
    out = {"nom": VFB[kind] * (1 + top / bot)}
    for name, dt in (("tol", 0.0), ("tcr", DT)):
        e = tol + tcr * dt
        hi = VFB[kind] * (1 + top * (1 + e) / (bot * (1 - e))) * (1 + ACC[kind])
        lo = VFB[kind] * (1 + top * (1 - e) / (bot * (1 + e))) * (1 - ACC[kind])
        raw = RAW_MIN[kind][0 if name == "tol" else 1]
        out[name] = {"min": lo, "max": hi, "r5_headroom": raw - hi - LOAD2[kind]}
    return out


OPTIONS = [  # rail, label, top ohms, bottom ohms, tolerance, TCR, placements
    ("pos", "HEAD 91k / 10k 0.1 %", 91e3, 10e3, 1e-3, 25e-6, 2),
    ("pos", "91k / 10k 1 % (preferred / basic)", 91e3, 10e3, 1e-2, 100e-6, 2),
    ("pos", "82k / 9.1k 1 % basic  << fitted", 82e3, 9.1e3, 1e-2, 100e-6, 2),
    ("neg", "HEAD 91k + 1k / 10k 0.1 %", 92e3, 10e3, 1e-3, 25e-6, 3),
    ("neg", "100k / 5k + 5k + 1k 0.1 %  << fitted", 100e3, 11e3, 1e-3, 25e-6, 4),
    ("neg", "91k / 10k 1 %", 91e3, 10e3, 1e-2, 100e-6, 2),
    ("neg", "82k / 9.1k 1 %", 82e3, 9.1e3, 1e-2, 100e-6, 2),
]
BOM_01 = [22, 100, 1e3, 2e3, 2.2e3, 5e3, 100e3]   # 0.1 % 25 ppm/C values on the Rev E BOM


def main():
    res = {"dt_k": DT, "raw_min_v": RAW_MIN, "options": [], "u12_from_bom_values": []}
    print(f"raw min (tolerance / +TCR): pos {RAW_MIN['pos'][0]:.3f} / {RAW_MIN['pos'][1]:.3f} V, "
          f"neg {RAW_MIN['neg'][0]:.3f} / {RAW_MIN['neg'][1]:.3f} V")
    for kind, label, top, bot, tol, tcr, n in OPTIONS:
        r = corners(kind, top, bot, tol, tcr)
        res["options"].append({"rail": kind, "option": label, "placements": n, **r})
        print(f"{kind} {label:40} nom {r['nom']:.3f}  min/max {r['tol']['min']:.3f}/{r['tol']['max']:.3f}"
              f"  R5 {r['tol']['r5_headroom']:.3f} | +TCR min {r['tcr']['min']:.3f} R5 {r['tcr']['r5_headroom']:.3f}")
    print("\nU12 from 0.1 % BOM values, divider current 5 uA ... 0.5 mA, R5 row >= 1 V:")
    rows = []
    for nt, nb in itertools.product((1, 2, 3), repeat=2):
        if nt + nb > 5:
            continue
        for top in itertools.combinations_with_replacement(BOM_01, nt):
            for bot in itertools.combinations_with_replacement(BOM_01, nb):
                t, b = sum(top), sum(bot)
                if not 5e-6 <= VFB["neg"] / b <= 0.5e-3:
                    continue
                r = corners("neg", t, b, 1e-3, 25e-6)
                if r["tol"]["r5_headroom"] >= 1.0 and r["tcr"]["min"] >= 11.3:
                    rows.append((nt + nb, top, bot, r))
    rows.sort(key=lambda x: (x[0], -x[3]["tcr"]["r5_headroom"]))
    for n, top, bot, r in rows:
        res["u12_from_bom_values"].append({"placements": n, "top": top, "bottom": bot, **r})
        print(f"  {n} parts  {'+'.join(f'{v:g}' for v in top)} / {'+'.join(f'{v:g}' for v in bot)}: nom {r['nom']:.3f}"
              f"  R5 {r['tol']['r5_headroom']:.3f} / +TCR {r['tcr']['r5_headroom']:.3f}")
    (HERE / "ldo_divider_options.json").write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
