#!/usr/bin/env python3
"""R5.4 -> plane via field: fusing I2t of n equally-sharing plated barrels (same method as f1_containment.barrel_i2t,
Onderdonk, Ta 105 C), and how many barrels reach 1,698 (the drain-pad floor, scenarios.py) and 3,420 (2 x F1).

    python3 -I r5_via_field.py
"""
import importlib.util, json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pp_common import F1C, RESULTS

spec = importlib.util.spec_from_file_location("f1c", str(F1C)); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
TA = m.TA_HOT


def barrel(drill, plate):
    ri = drill / 2
    a = math.pi * ((ri + plate) ** 2 - ri ** 2)
    return a, m.onderdonk_i2t(a, TA)


rows = []
print("drill mm  plating um  area mm2  I2t one barrel   n for 1,698   n for 3,420   I2t at n=6 (today)")
for drill in (0.30, 0.40, 0.50):
    for plate in (0.018, 0.020, 0.025):
        a, i1 = barrel(drill, plate)
        n1 = math.ceil(math.sqrt(1698 / i1)); n2 = math.ceil(math.sqrt(3420 / i1))
        rows.append({"drill": drill, "plating_um": plate * 1e3, "area_mm2": a, "I2t_one": i1, "n_for_1698": n1, "n_for_3420": n2, "I2t_n6": 36 * i1})
        print("%5.2f     %5.0f      %.4f    %8.1f        %3d          %3d          %8.0f" % (drill, plate * 1e3, a, i1, n1, n2, 36 * i1))
RESULTS.mkdir(exist_ok=True)
(RESULTS / "r5_via_field.json").write_text(json.dumps(rows, indent=1) + "\n")
