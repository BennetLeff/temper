#!/usr/bin/env python3
"""Transport-only 42-column tracker fixture; never an electrical model."""
import sys

fifo = sys.argv[4]
header = (
    "time v(acsrc,acn) v(vd) v(vb) v(sw) v(gate) i(Lboost) i(Vchannel) "
    "i(Vbody) i(Vac) v(q) v(en) v(fault) v(f2ctl) v(standby_req) v(arm) "
    "v(permit) i(Vf2sense) i(Vdboost1sense) i(Vdboost2sense) v(fault_inject) "
    "x1 x2 x3 x4 x5 x6 x7 x8 x9 x10 x11 x12 x13 x14 x15 x16 x17 x18 x19 x20 x21"
)
with open(fifo, "w", encoding="utf-8") as output:
    output.write(header + "\n")
    for index in range(1001):
        time_s = index * 20e-9
        f2 = 5.0 if time_s < 10e-6 else 0.0
        inject = 5.0 if time_s >= 10e-6 else 0.0
        fault = 5.0 if time_s >= 12e-6 else 0.0
        q = en = 5.0 if time_s < 12e-6 else 0.0
        values = [time_s, 120, 400, 390, 0, 0, 0, 0, 0, 0, q, en, fault, f2, 0, 5, 5, 0, 0, 0, inject]
        values.extend([0] * 21)
        output.write(" ".join(f"{value:.17e}" for value in values) + "\n")
