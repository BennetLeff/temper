#!/usr/bin/env python3
"""G09 T1 option: CST3015-100ED (1:100, 1.5 ohm burden; benchmark) vs CST3015-200ED (1:200, 3.0 ohm burden).
Datasheet values: Coilcraft Document 1608-1 (rev 09/08/25) table; same body/footprint family (one dimension drawing).
All numbers below are computed from those table values and the schematic constants in power_stage_120v.ato.

  * volts per primary amp  = R_burden / N     (must be equal: trips and CT_MON scale unchanged)
  * comparator trip currents from the 3.3 V divider references (2.21k / 10k) -> amps
  * secondary volt-time at the worst primary peak vs the part's V-us limit
  * magnetising-current error and phase lead (time) at the lowest drive frequencies
  * secondary-referred burden dissipation
  * charge-injection pickup of a primary-secondary capacitance C_ww on a switching edge: the 100 nF burden shunt
    absorbs the charge, so dV = C_ww*Vedge/C_b is independent of N and R_burden; in amps: dV / (V per A).
    C_ww is NOT published for either part (MAG-27 open): this is a scaling table, not a prediction.
Run: python3 -I ct_options.py -> ../results/ct_options.json
"""
import json, math
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARTS = {
    "CST3015-100ED": {"N": 100, "L_mH": 3.2, "L_tol": 0.25, "dcr_sec": 1.54, "vus": 638, "rt": 1.0, "burden": 1.5},
    "CST3015-200ED": {"N": 200, "L_mH": 12.8, "L_tol": 0.25, "dcr_sec": 5.94, "vus": 1276, "rt": 2.0, "burden": 3.0},
}
V33 = 3.3
REF_HI = V33 * 10.0 / (2.21 + 10.0)      # CT_REF_HI (r_ct_hi_top 2.21k, r_ct_hi_bot 10k)
MID = V33 / 2                            # CT_S2 bias (1k / 1k)
C_B = 100e-9                             # c_ct_burden C0G
VEDGE = 198.0                            # sw_a swing (bus 198 V basis used by the 02 studies)
out = {}
for nm, p in PARTS.items():
    vpa = p["burden"] / p["N"]                                   # V per primary amp
    r = {"V_per_A": vpa, "trip_pos_A": round((REF_HI - MID) / vpa, 2)}
    r["rt_check_V_per_100A_at_RT"] = p["rt"] / p["N"] * 100       # datasheet RT definition: 1 V at 100 A
    r["swing_at_88A_V"] = round(88 * vpa, 3)                      # must stay inside +-1.65 V
    vs = {}
    for ipk, f in ((76.09, 35e3), (76.09, 25e3), (118.74, 25e3), (59.17, 35e3)):
        isec = ipk / p["N"]
        vpk = isec * (p["burden"] + p["dcr_sec"])                 # winding EMF the core must support
        vus = vpk / (math.pi * f) * 1e6                           # half-sine volt-seconds, V-us
        vs[f"{ipk}A@{int(f/1e3)}k"] = {"Vsec_pk": round(vpk, 3), "Vus": round(vus, 1), "frac_of_limit": round(vus / p["vus"], 3)}
    r["volt_time"] = vs
    me = {}
    for f in (25e3, 35e3):
        lmin = p["L_mH"] * 1e-3 * (1 - p["L_tol"])
        rt = p["burden"] + p["dcr_sec"]
        x = 2 * math.pi * f * lmin
        me[f"{int(f/1e3)}k"] = {"mag_err_pct": round(100 * rt / x, 3), "lead_ns": round(math.atan(rt / x) / (2 * math.pi * f) * 1e9, 1)}
    r["magnetising_worst_L"] = me
    r["burden_W_at_28A_rms"] = round((28.0 / p["N"]) ** 2 * p["burden"], 4)
    r["burden_tau_ns"] = round(p["burden"] * C_B * 1e9, 0)
    r["pickup_equiv_A"] = {f"C_ww={c}pF": round(c * 1e-12 * VEDGE / C_B / vpa, 2) for c in (2, 5, 10, 20)}
    out[nm] = r
assert abs(out["CST3015-100ED"]["V_per_A"] - out["CST3015-200ED"]["V_per_A"]) < 1e-12
assert abs(out["CST3015-100ED"]["trip_pos_A"] - 70.18) < 0.05           # schematic comment: "~70 A"
(HERE.parent / "results" / "ct_options.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
