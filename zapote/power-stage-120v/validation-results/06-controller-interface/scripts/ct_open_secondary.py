#!/usr/bin/env python3
"""First-order CT secondary voltage: terminated vs open (CST3015-100ED, T1).

Datasheet values (Coilcraft CST3015-100ED, as recorded with provenance in
docs/evidence/2026-08-13-tank-fault-sizing-inputs.md): secondary inductance
3.2 mH (1 kHz, 0.1 Vrms), turns 1:100, volt-time product 638 V-us, terminating
R 1.0 ohm, secondary DCR 1.5 ohm.

Open secondary model: the whole referred primary current becomes magnetizing
current, so V ~ omega * L_sec * I_s while the core is below saturation. This is
linear and ignores saturation shape, winding capacitance and ringing, so it is
an order-of-magnitude estimate (simulation/model class), not a bound. The
volt-time check shows whether the core saturates each half-cycle; if it does,
the waveform becomes spikes of roughly this amplitude with collapse in between.
"""
import json
import math

L_SEC = 3.2e-3      # H
N = 100
VT_LIMIT = 638e-6   # V*s
R_TERM = 1.0        # ohm, datasheet terminating resistor
R_SEC = 1.5         # ohm, secondary DCR

cases = []
for label, i_pk, f in (("full power peak", 37.0, 35e3), ("full power peak, 33 kHz", 37.0, 33e3),
                       ("OCP nominal trip", 61.0, 35e3), ("OCP trip + 10 A spread", 71.0, 35e3),
                       ("light load", 10.0, 60e3)):
    i_s = i_pk / N
    w = 2 * math.pi * f
    v_open_pk = w * L_SEC * i_s                   # unsaturated linear estimate
    vt_half = 2 * v_open_pk / w                   # V*s of a sine half-cycle at that amplitude
    # Flux from the voltage zero-crossing: (Vpk/w)(1 - cos wt). The core
    # saturates when that reaches the volt-time limit (applied as the
    # half-cycle swing); the voltage at that instant is the spike height.
    ratio = VT_LIMIT / (v_open_pk / w)
    v_at_sat = v_open_pk * math.sin(math.acos(1 - ratio)) if ratio < 2 else v_open_pk
    v_spike = min(v_open_pk, v_at_sat) if ratio < 1 else v_open_pk
    v_term_pk = i_s * R_TERM                      # terminated, burden voltage
    vt_term = 2 * (i_s * (R_TERM + R_SEC)) / w    # terminated core flux demand
    cases.append({"case": label, "primary_peak_a": i_pk, "f_hz": f,
                  "secondary_peak_a": round(i_s, 3),
                  "open_v_peak_est": round(v_open_pk, 1),
                  "open_half_cycle_vus_demand": round(vt_half * 1e6, 1),
                  "open_saturates": vt_half > VT_LIMIT,
                  "open_v_at_saturation_est": round(v_spike, 1),
                  "terminated_1ohm_v_peak": round(v_term_pk, 3),
                  "terminated_half_cycle_vus": round(vt_term * 1e6, 2)})
out = {"part": "CST3015-100ED", "L_sec_H": L_SEC, "ratio": N, "volt_time_limit_Vus": 638,
       "selv_reference": "SELV/ELV touch limits are tens of volts (e.g. 42.4 V peak / 60 V DC); state the applicable standard in the report",
       "cases": cases}
print(json.dumps(out, indent=1))
