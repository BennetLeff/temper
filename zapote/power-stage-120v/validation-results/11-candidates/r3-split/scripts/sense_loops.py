#!/usr/bin/env python3 -I
"""S2-A / S2-B: what a connector in the OCP Kelvin pair does. Inputs read from the repo (read-only):
02-protection-timing/kelvin/budget-native21s20.json (13.648 mA of supply current returns through OCP_KELVIN_P copper, trip shift
-2.167 A, band 67.72-116.44 A, floor 64.17 A) and elec/src/power_stage_120v.ato lines 549-596 (OCP_NODE = 1.25 V + 0.5 V(KELVIN_N)
with r_ocp_ref 10k to REF25 2.5 V; OCP_THRESH 1.2037 V; u_ocp GND = OCP_KELVIN_P; R5 = 1 mohm).
    python3 -I sense_loops.py -> ../results/sense_loops.json"""
import json, math, sys
sys.dont_write_bytecode = True
from pathlib import Path
HERE = Path(__file__).resolve().parent; PS = HERE.parents[3]
B = json.load(open(PS/"validation-results/02-protection-timing/kelvin/budget-native21s20.json"))
R5 = 1e-3; I_ret = B["total_mA"]*1e-3
out = {"band_low_A": B["band_after_A"][0], "floor_A": B["floor_A"], "margin_to_floor_A": round(B["band_after_A"][0]-B["floor_A"], 3),
       "supply_return_mA_in_KELVIN_P": B["total_mA"]}
# 1) contact resistance in the KELVIN_P ground path (the 13.6 mA of comparator / LDO / AMC1311 current)
out["contact_R"] = {}
for rc_mohm in (10, 20, 40):
    for npins in (1, 2, 4):
        dV = I_ret*rc_mohm*1e-3/npins
        out["contact_R"][f"{rc_mohm}mohm_{npins}pin"] = dict(dV_mV=round(dV*1e3, 3), dA=round(dV/R5, 3))
# 2) open-circuit failure of the KELVIN_N pin: OCP_NODE is pulled to REF25 through r_ocp_ref (10k) -> reads 'no current'
REF25, THRESH = 2.5, 2.5*11.7/(12.6+11.7)
node_open = REF25
out["open_KELVIN_N"] = dict(OCP_NODE_V=node_open, OCP_THRESH_V=round(THRESH, 4), comparator_output="OK (INP > INN)", fail_direction="UNSAFE: OCP blind, no flag",
                            nominal_trip_V_at_93A=round(1.25+0.5*(-93*R5), 4))
# 3) pickup area added by the connector: field of a single straight conductor carrying the F8 basis (59.17 A pk, 60 kHz) at distance r.
MU0 = 4e-7*math.pi
def pickup(area_mm2, r_mm, I=59.17, f=60e3):
    return MU0/(2*math.pi*r_mm*1e-3)*(2*math.pi*f)*I*area_mm2*1e-6
out["pickup_upper_bound"] = {}
for area, label in ((22.9, "2.54 mm pair x 9 mm"), (8.0*1, "0.8 mm pair x 6 mm + 10 mm breakout")):
    for r in (30, 60, 100):
        v = pickup(area, r); out["pickup_upper_bound"][f"{label}, r={r} mm"] = dict(mV=round(v*1e3, 3), A_equiv=round(v/R5, 3))
out["note"] = ("Upper bound: a single wire carrying the whole 59 A at distance r; the real bus is a plane sandwich (In2 BUS_P over In1 HV_RET) whose external "
               "field is lower. The F8 method (study 06 FEM, copper dump) is the right tool and needs the connector placed first.")
json.dump(out, open(HERE.parent/"results/sense_loops.json", "w"), indent=1)
print(json.dumps(out, indent=1))
