# Inverter interface contract — U1 in progress

Source snapshot: `06d9070c3` Rev38 candidate and the accepted standalone gate-drive interface. This defines a handoff, not a selected switching or coil circuit.

| Boundary | Current evidence | Required envelope before design acceptance |
| --- | --- | --- |
| DC bus | Rev38 `VB_BANK` across four candidate 560 µF, 450 V capacitors to `HOT0`; about 390 V is the intended nominal bus. VD and VB are separated by F2. | Maximum/minimum VB, ripple, transient, startup and collapse; return and disconnect behavior; bank-ready meaning. Capacitor rating is not permission for 450 V operation. |
| Gate-drive logic J1 | `PWM_H`, `PWM_L`, active-high `PERMIT`, `CTRL_GND`; floating PERMIT disables according to gate-drive interface. | PWM timing/dead time under a real load, interlock mapping and electrical compatibility with the selected controller. |
| Gate-drive supply J2/J5 | External isolated `+15V_LS`/`HV_RETURN` and primary `3V3`/`CTRL_GND`; high-side rail is bootstrap-derived. | Startup before switching, droop, bias/pulse load, isolation and loss response, supplied by auxiliary U1. |
| Gate outputs J3/J4 | `GATE_H_OUT`/Kelvin and `GATE_L_OUT`/Kelvin; J4 return shares `HV_RETURN`. | Exact switch pin/package and loop geometry, loaded turn-off, parasitic and overvoltage/current limit. |
| Shutdown | Rev38 owns PFC stop/restart; accepted gate-drive PERMIT is active-high and default-disabled. | Inverter-specific stop latency, residual tank/bus energy, failed-short switch path and latch/re-arm policy. Gate-off alone does not interrupt a failed-short switch. |
| Cross-unit outputs | Inverter dissipates heat and may add bus capacitance. | Publish local capacitor/energy map to discharge U1 and loss/heat locations to cooling U1. |

No bridge choice, switch, frequency or tank value is accepted here. The selected inverter must demonstrate that its normal and fault input demands fit Rev38's bus envelope without silently changing that bus protection contract.
