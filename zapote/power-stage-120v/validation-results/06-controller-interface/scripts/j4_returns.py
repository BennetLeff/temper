#!/usr/bin/env python3
"""J4 SELV returns after native-21 moved J4.16 to LINE_ZC (D-20 R16/R20).

Three SELV_GND contacts (J4.2/.4/.15) now carry the PS1 15 V return plus all
signal returns. Screen: per-contact current and the DC ground offset between
the boards, against each single-ended signal's margin, with all three contacts
and with one missing (R20: "qualify a missing contact").

Assumptions (stated, not measured; replace with the harness design):
- harness 2.0 m each way (the D-31 timing allocation's length), 24 AWG copper
  at 84.2 mOhm/m (20 C) x 1.2 for temperature;
- Micro-Fit 3.0 contact resistance 10 mOhm per mated contact, two ends;
- return current = full PS1 rating 1.4 A (J4.1 schedule) + 41.657 mA V3V3
  subtotal; this is pessimistic, the controller's real draw is not allocated.
"""
import json
from pathlib import Path

R_WIRE = 2.0 * 0.0842 * 1.2
R_CONTACT = 2 * 0.010
I_RET = 1.4 + 0.041657
# single-ended margins (V) that a ground offset subtracts from (D-10 / D-20 schedule)
MARGINS = {
    "PWM low (VIL 0.8 V - controller VOL 0.3465 V)": 0.8 - 0.3465,
    "PWM high (controller VOH 2.508 V - VIH 2.3 V)": 2.508 - 2.3,
    "BUS_FAULT low (receiver VIL 0.8 V assumed - 0.3 V)": 0.8 - 0.3,
    "PERMIT (UCC21550 DIS path via AO3400A gate, Vth 0.65 V min)": 0.65,
}
CT_MON_V_PER_A = 0.015


def case(n):
    r = (R_WIRE + R_CONTACT) / n
    v = I_RET * r
    return {"contacts": n, "per_contact_A": round(I_RET / n, 3), "offset_mV": round(v * 1e3, 1),
            "ct_mon_error_A": round(v / CT_MON_V_PER_A, 2),
            "margins_after_offset_V": {k: round(m - v, 3) for k, m in MARGINS.items()}}


def main():
    res = {"assumptions": {"R_wire_ohm": R_WIRE, "R_contact_ohm": R_CONTACT, "I_return_A": I_RET},
           "native20_four_returns": case(4), "native21_three_returns": case(3), "native21_one_missing": case(2)}
    out = Path(__file__).resolve().parents[1] / "outputs" / "j4_returns.json"
    out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
