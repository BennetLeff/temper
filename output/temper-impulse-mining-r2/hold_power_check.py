"""Cross-check sensor-r2's pan loss model against Impulse's published hold powers.

Impulse (YouTube jgJ89Jr_0a8, "Everything you need to know", 17:21-17:55 and
16:48): holding all four 9-inch burners at 482 F (250 C) draws "about 1.73 kW"
in total (~0.43 kW per burner), and holding "medium, around 350 F" (177 C)
takes about 150-300 W per burner (four at medium = 600-1200 W). Their pans,
lids and loads are unstated, and the figure is probably battery-side input.

This runs output/temper-sensor-r2/estimator_study.py's truth plant in its
perfect-feedback closed loop, holds each empty pan at 177 C and 250 C, and
reports the mean input power over the last 60 s of each hold. It is a
plausibility check of the loss model's magnitude, not a calibration.

Run: python3 hold_power_check.py  -> hold-power-check.json
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "temper-sensor-r2"))
import estimator_study as es  # noqa: E402

IMPULSE = {"177": [150.0, 300.0], "250": [432.5, 432.5]}   # W per burner


def main() -> None:
    es.SP_STEP_T = 400.0
    es.T_END = 800.0
    rows = []
    for pan in ("cast_iron_26", "carbon_steel_28", "triply_clad_24"):
        es.PANS[pan]["sp"] = (177.0, 250.0)
        for eta in es.ETA_SWEEP:
            L = es.run(pan, 1000.0, eta, 0.05, "perfect", seed=1)
            t, P = L[:, 0], L[:, 6]
            hold1 = (t > es.SP_STEP_T - 60) & (t < es.SP_STEP_T)
            hold2 = t > es.T_END - 60
            rows.append({"pan": pan, "eta": eta,
                         "P_hold_177C_W": round(float(P[hold1].mean()), 0),
                         "P_hold_250C_W": round(float(P[hold2].mean()), 0)})
    out = {"scope": __doc__.strip(), "impulse_W_per_burner": IMPULSE, "rows": rows}
    (HERE / "hold-power-check.json").write_text(json.dumps(out, indent=1) + "\n")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
