#!/usr/bin/env python3
"""Candidate A: bus OVP moved from U7 (TLV3201 + LM4040 REF25 + R36/R37) to U14's spare over-voltage channel (INB),
fed from a tap in the bus divider's bottom leg (R30 15.8 k split into R30a + R30b, same total, so VSENSE_IN and the
AMC1311 scale are unchanged).

    python3 -I scripts/ovp_band.py [SNAP_PS_DIR]          -> results/ovp_band.json

Control: today's OVP band from the committed task-02 round-3 corner model (thresholds.py exact_corners, imported
read-only) at -10 and +85 C. The new band uses the same resistor corner values (corner_values) for R26..R29, and the
same 0.1 % / 25 ppm model for the two R30 halves; the threshold is the supervisor's rising INB threshold:
  TPS3701 SBVS240C 6.5: VIT+(INB) 397..403 mV, release VIT-(INB) 387..400 mV, IIN +-25 nA
  TPS3700 SBVS187G 6.5: VIT+ 396..404 mV, VIT- 387..400 mV, I(INB-) +-15 nA (0.1 V) / the INA+ row +-25 nA used
A pair passes when its trip band lies inside today's band (dominance: every rating that used today's OVP corner holds).
"""
import sys as _s; _s.dont_write_bytecode = True  # never write .pyc next to the read-only snapshot sources
import importlib.util, itertools, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import monitor_tps3701 as mt  # E192 list and stock helper  # noqa: E402

PS = mt.PS
spec = importlib.util.spec_from_file_location("thr", PS / "validation-results/02-protection-timing/round3/thresholds.py")
thr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(thr)

SUP = {"TPS3701": {"trip": (0.397, 0.403), "release": (0.387, 0.400), "iin": 25e-9},
       "TPS3700": {"trip": (0.396, 0.404), "release": (0.387, 0.400), "iin": 25e-9}}
TEMPS = (-10.0, 85.0)
RT = (0.001, 25e-6)


def old_band():
    lo, hi = 1e9, -1e9
    for t in TEMPS:
        r = thr.exact_corners(t, 50.0)["ovp_v"]
        lo, hi = min(lo, r["min"]), max(hi, r["max"])
    return lo, hi


def new_band(ra_k, rb_k, sup, which="trip"):
    s = SUP[sup]
    lo, hi = 1e9, -1e9
    for t in TEMPS:
        cv = thr.corner_values(t, 50.0)
        dt = abs(t - 25)
        e = RT[0] + RT[1] * dt
        tops = [cv[f"R{i}"] for i in range(26, 30)]
        for bits in itertools.product((0, 1), repeat=6):
            rtop = sum(tops[i][bits[i]] for i in range(4))
            ra = ra_k * 1e3 * (1 + (e if bits[4] else -e))
            rb = rb_k * 1e3 * (1 + (e if bits[5] else -e))
            rth = rb * (rtop + ra) / (rtop + ra + rb)
            for v in s[which]:
                for i in (-s["iin"], s["iin"]):
                    x = (v + i * rth) * (rtop + ra + rb) / rb
                    lo, hi = min(lo, x), max(hi, x)
    return lo, hi


def main():
    old = old_band()
    print(f"control: today's OVP band (round-3 model, U7 TLV3201 + LM4040, -10/85 C) {old[0]:.2f}..{old[1]:.2f} V")
    res = {"old_band_V": [round(x, 2) for x in old], "designs": {}}
    total = 15.8
    for sup in ("TPS3701", "TPS3700"):
        cands = []
        for rb in mt.e96_decades(2.0, 3.5):
            for ra in mt.e96_decades(total - rb - 0.2, total - rb + 0.2):
                scale = abs(ra + rb - total) / total
                if scale > 0.006:                                 # VSENSE_IN / AMC1311 scale change <= 0.6 %
                    continue
                lo, hi = new_band(ra, rb, sup)
                # Acceptance: the upper corner (the bus maximum that D3 / C5C6 / ALT-BIAS ratings use) must not rise;
                # the lower corner (nuisance restart-inhibit) may fall by at most 1 % of today's.
                if hi > old[1] or lo < old[0] * 0.99:
                    continue
                strict = lo >= old[0]
                cands.append(((not strict), round(scale, 4), abs((lo + hi) / 2 - (old[0] + old[1]) / 2), ra, rb, lo, hi))
        cands.sort()
        chosen = None
        for c in cands:
            sa, sb = mt.stocked(c[3], need=500), mt.stocked(c[4], need=500)
            if sa and sb:
                chosen = c + (sa, sb)
                break
        if not chosen:
            res["designs"][sup] = "no stocked pair meets the acceptance"
            print(sup, "no stocked pair meets the acceptance")
            continue
        notstrict, _, _, ra, rb, lo, hi, sa, sb = chosen
        rlo, rhi = new_band(ra, rb, sup, "release")
        sc = ((ra + rb) / total * (1880 + total) / (1880 + ra + rb) - 1) * 100
        res["designs"][sup] = {"R30a_k": ra, "R30b_k": rb, "sum_k": round(ra + rb, 3), "vbus_scale_change_pct": round(sc, 3),
                               "trip_band_V": [round(lo, 2), round(hi, 2)], "inside_old_band": not notstrict,
                               "upper_corner_change_V": round(hi - old[1], 2), "lower_corner_change_V": round(lo - old[0], 2),
                               "release_band_V": [round(rlo, 2), round(rhi, 2)],
                               "width_vs_old": round((hi - lo) / (old[1] - old[0]), 3), "R30a_part": sa, "R30b_part": sb,
                               "strictly_inside_candidates_unstocked": [c[3:5] for c in cands if not c[0]][:4]}
        print(f"{sup}: R30a {ra}k + R30b {rb}k = {ra+rb:.2f}k (VSENSE scale {sc:+.2f} %)   trip {lo:.2f}..{hi:.2f} V "
              f"(today {old[0]:.2f}..{old[1]:.2f}: upper {hi-old[1]:+.2f}, lower {lo-old[0]:+.2f})   release {rlo:.2f}..{rhi:.2f} V"
              f"   parts {sa['mpn']} ({sa['jlc_stock']}) / {sb['mpn']} ({sb['jlc_stock']})")
    json.dump(res, open(HERE.parent / "results/ovp_band.json", "w"), indent=1)


if __name__ == "__main__":
    main()
