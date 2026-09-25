# Gate-drive interfaces

| Connector | Pins | Boundary |
|---|---|---|
| J1 | PWM_H, PWM_L, PERMIT, CTRL_GND | Primary logic; PERMIT is active-high and floating-safe disabled |
| J2 | +15V_LS, HV_RETURN | External isolated low-side supply boundary |
| J3 | GATE_H_OUT, GATE_H_KELVIN | High-side gate and exact Kelvin return |
| J4 | GATE_L_OUT, GATE_L_KELVIN/HV_RETURN | Low-side gate and return |
| J5 | 3V3, CTRL_GND | Primary auxiliary supply |

The high-side rail is bootstrap-derived from the isolated 15 V low-side input;
there is no local transformer or DC/DC. Primary logic ground remains separate
from HV_RETURN. The 39 kΩ dead-time resistor is conditional interpolation
within the documented characterization envelope; measured timing is pending
hardware qualification.
