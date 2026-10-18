"""How much does temper's low-power burst mode ripple the pan?

Power-stage DECISIONS (2026-10-05, F9): below the frequency-control floor
(about 150-160 W) power is set by line-synchronous bursts at the floor, with a
burst period T >= max(2 s, ...) and a 20 s default (flicker screen). Impulse
markets "true continuous control" and says on/off cycling at low settings
scorches pans (Cars & Capitalists, 7TZb8I5rVZ8 75:04-75:27); Control Freak
owners report gentle pulsing (Hungry Onion, Dec 2022).

This runs the sensor-r2 radial pan model (output/temper-sensor-r2/
estimator_study.Truth, imported read-only) to a steady hold at an average
power, then compares continuous power with bursts at the floor power, and
reports the peak-to-peak swing at the contact point (T_c) and the hottest ring.
It is open-loop on purpose: the closed loop cannot do better than the burst
quantum. Run: python3 burst_ripple.py -> burst-ripple.json
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "temper-sensor-r2"))
import estimator_study as es  # noqa: E402

FLOOR_W = 160.0          # burst amplitude, input W (floor 150-160 W)
ETA = 0.88
PERIODS = (20.0, 10.3, 2.5)   # default, the 250 W minimum, the 160 W minimum
CASES = [("carbon_steel_28", 60.0), ("carbon_steel_28", 120.0),
         ("triply_clad_24", 60.0), ("triply_clad_24", 120.0),
         ("disc_pot_water_1l5", 120.0)]


def run(pan, p_avg, period):
    tr = es.Truth(es.PANS[pan], 3000.0, ETA, 0)
    n_settle = int(2400 / es.DT_SIM)
    for _ in range(n_settle):
        tr.step(p_avg, 3000.0)
    t_on = period * p_avg / FLOOR_W
    tc, tmax = [], []
    win = max(period, 20.0)
    steps = int(4 * win / es.DT_SIM)
    for k in range(steps):
        t = k * es.DT_SIM
        p = p_avg if period == 0 else (FLOOR_W if (t % period) < t_on else 0.0)
        tr.step(p, 3000.0)
        if t >= 2 * win:
            tc.append(tr.T_c())
            tmax.append(float(tr.T.max()))
    return {"T_c_mean": round(float(np.mean(tc)), 1), "T_c_pp_K": round(float(np.ptp(tc)), 2),
            "hottest_ring_mean": round(float(np.mean(tmax)), 1), "hottest_ring_pp_K": round(float(np.ptp(tmax)), 2)}


def main():
    rows = []
    for pan, p_avg in CASES:
        base = run(pan, p_avg, 0)
        for period in PERIODS:
            r = run(pan, p_avg, period)
            rows.append({"pan": pan, "P_avg_W": p_avg, "period_s": period, "duty": round(p_avg / FLOOR_W, 3),
                         "continuous": base, "burst": r})
            print(f"{pan:20s} {p_avg:5.0f} W  T={period:5.1f} s  T_c {base['T_c_mean']:6.1f} C  "
                  f"pp cont {base['T_c_pp_K']:.2f} burst {r['T_c_pp_K']:.2f} K   hottest ring pp {r['hottest_ring_pp_K']:.2f} K")
    out = {"scope": __doc__.strip(), "floor_W": FLOOR_W, "eta": ETA, "rows": rows}
    Path(__file__).with_name("burst-ripple.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
