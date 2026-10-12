#!/usr/bin/env python3
"""Stage-17 gate G7: shunt-OCP band before the Kelvin shift with R5 = CSS2H-2512R-1L00F (1 %, 75 ppm/C).

    python3 ocp_band17.py   -> ocp_band17.json (exit 1 if the control fails)

Method = the committed one (stage15-28A/ocp_bands.py, kelvin_budget.py BAND_BEFORE): task-02 round-3
thresholds.py exact_corners() at -10 and +85 C ambient with R5 +50 K, R34 12.6 k / R35 11.7 k (0.1 %, 25 ppm),
R32 = R33 = 10 k, LM4040 +/-20 mV, comparator Vos +/-4 mV and input bias. Only R5's tuple changes
(thresholds.SHUNT -> thresholds.SHUNT_CSS2H). The 1 mOhm value is kept, so no divider change.
Control: the stage-16 tuple (thresholds.SHUNT, WSK 250 ppm) reproduces the committed 68.58-118.74 A.
The output feeds kelvin_budget.py BAND_BEFORE["native21s17"].
"""
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
VR = HERE.parents[2]
spec = importlib.util.spec_from_file_location("thr", VR / "02-protection-timing/round3/thresholds.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
RT = (0.001, 25e-6)
m.PARTS.update({"R34": (12.6e3, *RT), "R35": (11.7e3, *RT)})


def band(shunt):
    m.PARTS["R5"] = shunt
    r = [m.exact_corners(t, 50.0)["shunt_a"] for t in (-10.0, 85.0)]
    nominal = m.thresholds({k: v[0] for k, v in m.PARTS.items()}, 2.5, 0.0)[0]
    return round(min(x["min"] for x in r), 2), round(max(x["max"] for x in r), 2), round(nominal, 3)


ctrl = band(m.SHUNT)
assert ctrl[:2] == (68.58, 118.74), ctrl
new = band(m.SHUNT_CSS2H)
out = {"method": "thresholds.py exact_corners, -10/+85 C ambient, R5 +50 K, R34 12.6 k / R35 11.7 k",
       "control_stage16_wsk_250ppm": {"tuple": list(m.SHUNT), "band_before_kelvin_a": list(ctrl[:2]), "nominal_trip_a": ctrl[2]},
       "stage17_css2h_75ppm": {"tuple": list(m.SHUNT_CSS2H), "band_before_kelvin_a": list(new[:2]), "nominal_trip_a": new[2]},
       "low_edge_change_a": round(new[0] - ctrl[0], 2)}
(HERE / "ocp_band17.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
