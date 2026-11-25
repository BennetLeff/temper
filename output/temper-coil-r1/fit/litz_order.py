"""Litz per coil and the spool to order (Remington 260/38LITZ), from the R1 CAD and the bench lead lengths.

Per coil = winding as wound (R1 + the spare outer turn: the spare is wound first and trimmed at W8, so it is bought)
         + both leads at the bench length (fit/bench_leads.py) + in-barrel strip length (Panduit P14-8RHT6-C 7.1 mm)
         + one re-termination per lead (25 mm: a failed crimp is cut off and redone) + 50 mm handling at the spool end.
Per order = 2 coils + the W9 termination qualification (3 samples x 1.00 m + 2 x strip, BUILD-AND-MEASURE W9: "repeat until
two samples pass") + 10 % of one coil for a practice winding start (it is unwound and kept as scrap lengths).
Cross-check: coil_geometry.Winding.length_m (ring-sum model of the same spiral).
Spools (Remington product page, read 2026-10-21): 2 oz 9 ft $33.25, 4 oz 19 ft $57.58, 8 oz 38 ft $102.86, 1 lb 76 ft
$187.65, 2.5 lb 189 ft $455.20, 5 lb 378 ft $800.25, 10 lb 756 ft $1,434.06.
Run: .venv/bin/python -B fit/litz_order.py  -> fit/results/litz_order.json (needs fit/results/bench_leads.json)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import r1_parts as R  # noqa: E402
from r1_parts import G  # noqa: E402

FT = 0.3048
SPOOLS = [("2 oz", 9, 33.25), ("4 oz", 19, 57.58), ("8 oz", 38, 102.86), ("1 lb", 76, 187.65), ("2.5 lb", 189, 455.20),
          ("5 lb", 378, 800.25), ("10 lb", 756, 1434.06)]
STRIP, RETERM, HANDLING = 7.1, 25.0, 50.0
QUAL = 3 * (1000.0 + 2 * STRIP)


def main():
    bench = json.loads((HERE / "results" / "bench_leads.json").read_text())["leads"]
    w_r1 = R.winding("R1")[1]["length_mm"]
    w_sp = R.winding("spare")[1]["length_mm"]
    leads = bench["J2"]["developed_mm"] + bench["J5"]["developed_mm"]
    per_coil = w_sp + leads + 2 * (STRIP + RETERM) + HANDLING
    order = 2 * per_coil + QUAL + 0.1 * per_coil
    fits = [dict(spool=n, ft=ft, m=round(ft * FT, 2), usd=usd, covers_order=ft * FT * 1000 >= order,
                 coils_covered=int((ft * FT * 1000 - QUAL) // per_coil)) for n, ft, usd in SPOOLS]
    combo = dict(spool="1 lb + 8 oz (two spools, maybe two lots)", ft=76 + 38, m=round(114 * FT, 2), usd=round(187.65 + 102.86, 2))
    combo.update(covers_order=combo["m"] * 1000 >= order, coils_covered=int((combo["m"] * 1000 - QUAL) // per_coil))
    fits.append(combo)
    pick = next(s for s in fits if s["covers_order"])
    res = dict(about=__doc__.strip(),
               per_coil_mm=dict(winding_R1=w_r1, winding_with_spare=w_sp, spare_turn=w_sp - w_r1, leads_bench=leads,
                                strip_and_retermination=2 * (STRIP + RETERM), handling=HANDLING, total=per_coil),
               model_crosscheck_m=dict(R1_rings=G.R1.length_m(with_leads=False), R1_with_spare_rings=G.with_spare(G.R1).length_m(with_leads=False)),
               qualification_mm=QUAL, practice_mm=0.1 * per_coil, order_mm=order, spools=fits, pick=pick)
    (HERE / "results" / "litz_order.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "about"}, indent=1))


if __name__ == "__main__":
    main()
