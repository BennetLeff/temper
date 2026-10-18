"""Boil-time comparison: temper's input-power options vs the Control Freak test.

Calibration point: Eater's Control Freak test (yt:BcSqJ7sZiAQ, 2017-08-08,
04:37-04:45): 2 L of water, wide uncovered pan, boiled in about 10:55 (655 s);
the reviewers had expected about 5 minutes. The Control Freak is rated 1800 W
input (120 V, 15 A).

Model: energy to bring 2 L from 20 C to 100 C, plus a pan term, delivered at
P_net = eta * P_in - P_loss, where P_loss (evaporation and convection from the
open pan, averaged over the heat-up) is backed out from the Control Freak run
for each assumed eta and then held fixed for every temper option (same pot,
same water). Coil-to-pan efficiency eta is swept 0.80-0.90 (typical induction
range; not measured for either product). This is a comparison, not a
prediction of absolute boil time.

Temper input options (power-stage DECISIONS, 2026-10-08 and the coil-driver-r1
input-current budget): held at 11.09 A power-stage current (about 1.33 kW
input, firmware estimate with 10 % margin), 11.62 A (bench +/-5 %), 12.05 A
(measured with an AMC1301), inlet regulated at 13.5 A minus 1.3 A auxiliary
(12.2 A, no estimate margin), and a 15 A nameplate like the Control Freak.
Run: python3 boil_time.py -> boil-time.json
"""
import json
from pathlib import Path

E_WATER = 2.0 * 4186.0 * 80.0          # J
E_PAN = 600.0 * 80.0                   # J, ~1.2 kg clad pan
CF_T = 655.0                           # s
CF_P = 1800.0                          # W input
V = 120.0
OPTIONS = {"held 11.09 A (estimate, +10 %)": 11.09 * V, "held 11.62 A (bench +/-5 %)": 11.62 * V,
           "held 12.05 A (AMC1301 measured)": 12.05 * V, "12.2 A (13.5 A inlet - 1.3 A aux, no margin)": 12.2 * V,
           "15 A nameplate (Control Freak class)": 15.0 * V}


def main():
    rows = []
    for eta in (0.80, 0.85, 0.90):
        p_loss = eta * CF_P - (E_WATER + E_PAN) / CF_T
        for name, p_in in OPTIONS.items():
            p_net = eta * p_in - p_loss
            t = (E_WATER + E_PAN) / p_net
            rows.append({"eta": eta, "option": name, "P_in_W": round(p_in), "P_loss_W": round(p_loss),
                         "t_s": round(t), "t_min": f"{int(t // 60)}:{int(t % 60):02d}",
                         "vs_control_freak": round(t / CF_T, 2)})
            print(f"eta {eta:.2f}  {name:44s} {p_in:6.0f} W  {rows[-1]['t_min']:>6s}  x{rows[-1]['vs_control_freak']}")
    Path(__file__).with_name("boil-time.json").write_text(json.dumps({"scope": __doc__.strip(), "rows": rows}, indent=1) + "\n")


if __name__ == "__main__":
    main()
