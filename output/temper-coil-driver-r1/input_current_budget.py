"""Power held back by estimating, rather than measuring, the input current.

Power-stage DECISIONS (2026-10-08, the 15 A input entry and its same-day
correction): native-21 has no line-current measurement, the owner chose a
firmware estimate, and the controller holds the power-stage current at
  I_ps,hold = (inlet_target - I_aux) / (1 + e_est) = (13.5 - 1.3) / (1 + e_est)
with e_est = 10 % provisional (11.1 A, about 1.33 kW at 120 V).

Impulse measures DC bus current continuously (Allegro ACS773) [patent
US12712433B1 FIG. 3]. Temper already has the R5 1 mOhm Kelvin shunt in the
leg return; an AMC1301 (same DWV family as the board's AMC1311; +-250 mV,
gain error +-0.3 % max, offset +-0.2 mV max, reinforced, UL 1577 5 kVrms -
TI product page read 2026-10-14) on R5 measures it. Error budget below
(offset nulled at power-up with the bridge off; shunt +-1 % initial, TCR
lumped into a 0.5 % temperature term; ADC and RMS method 0.5 %).
Run: python3 input_current_budget.py -> input_current_budget.json
"""
import json
from math import sqrt
from pathlib import Path

INLET_TARGET, I_AUX, V = 13.5, 1.3, 120.0


def hold(e):
    return (INLET_TARGET - I_AUX) / (1 + e)


def main():
    terms = {"shunt_initial": 0.01, "shunt_temperature": 0.005, "amc1301_gain": 0.003, "adc_and_rms_method": 0.005,
             "offset_residual_after_null_at_11A": 0.02e-3 / 1e-3 / 11.0}
    e_meas_rss = sqrt(sum(v * v for v in terms.values()))
    e_meas_lin = sum(terms.values())
    rows = []
    base = hold(0.10)
    for name, e in (("firmware estimate, provisional", 0.10), ("firmware estimate, bench +-5 %", 0.05),
                    ("measured, linear sum", e_meas_lin), ("measured, RSS", e_meas_rss)):
        h = hold(e)
        rows.append({"case": name, "e_est": round(e, 4), "I_ps_hold_A": round(h, 2),
                     "power_vs_provisional_pct": round(100 * (h / base - 1), 1),
                     "input_W_at_120V_approx": round(h * V * 0.995, 0)})
    out = {"scope": __doc__.strip(), "error_terms": terms, "rows": rows}
    Path(__file__).with_name("input_current_budget.json").write_text(json.dumps(out, indent=1) + "\n")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
