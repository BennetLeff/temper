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

## U1 source reconciliation (2026-09-23)

| Boundary | Source fact | Required handoff |
| --- | --- | --- |
| VB and return | Rev38 `pfc_power.ato` places four 560 µF/450 V capacitor positives, F2's bank terminal and the bleeder at `VB_BANK`; negatives are `HOT0`. A separate 22 µF/630 V plus 470 nF film reservoir stays on VD when F2 opens. The target is about 390 V nominal (`PFC-POWER.md`). | Inverter input is **VB_BANK/HOT0**, downstream of F2. Power entry must bound VB minimum/maximum, ripple, surge, startup ramp, collapse, source impedance and bank-ready meaning. The 450 V component rating does not set the allowed operating maximum. |
| Old return topology | Historical `elec/src/main.ato` uses a voltage doubler with about +170/−170 V relative to midpoint `PWR_RTN`, 340 V nominal bus and 400 V declared absolute maximum. Its tank returns through the CT to that **midpoint** (`main.ato` lines 682–688, 817–824). | Rev38 exposes no such midpoint. Replacing `PWR_RTN` with HOT0 changes capacitor bias, coil common mode, tank return and current path. Old 47 kHz/current/ZVS results cannot transfer by renaming nets. |
| HF path | The old `HalfBridge` owns a 470 nF capacitor across its own HV rails (`modules.ato`). Rev38's 470 nF is on **VD**, across F2 from the VB-fed inverter. | Size and locate any VB-to-HOT0 local commutation capacitor from loop inductance, ripple and pulse current. Its value and energy are unselected; discharge and cooling need the selected result. |
| Fault energy | Four nominal 560 µF cans total 2.24 mF, or 170.4 J at 390 V by `0.5 C V²` before tolerance. Rev38's VD/VB comparator thresholds and physical response are unaccepted (`F2-DETECTOR.md`, `timing-analysis.md`). | A bank-to-inverter failed-short path is supplied directly by those cans. **F2 is not in the VB-bank-to-bridge discharge loop.** Downstream interruption, conductor withstand, enclosure and discharge need their own allocation. This arithmetic is an energy inventory, not a current or voltage qualification. |

### Accepted gate connector mapping

`zapote/gate-drive/source-build-09/elec/src/gate_drive_unit.ato` and `zapote/gate-drive/INTERFACES.md` define exact pins. `zapote/gate-drive/ACCEPTANCE.md` passes digital construction only; bootstrap startup, dead time and loaded turn-off await hardware.

| Gate connector | Accepted assignment | Inverter connection and condition |
| --- | --- | --- |
| J1 | 1 PWM_H, 2 PWM_L, 3 active-high PERMIT, 4 CTRL_GND; floating PERMIT disables driver via pulldown/DIS pullup. | Name a PWM source and an independent inverter-PERMIT owner at integration. Keep CTRL_GND separate from HOT0. Rev38 PFC RUN/STOP is a boost control and is not yet an inverter-PERMIT handoff. Bound reset/rail loss and PWM overlap. |
| J2 | 1 +15V_LS, 2 HV_RETURN; feeds low-side driver and high-side bootstrap. | Map HV_RETURN to the intended HOT0/Kelvin power join; auxiliary supplies an **isolated** 15 V rail referenced to it. Bound ramp, pulse current, droop, hold-up and bootstrap recharge. |
| J3 | 1 GATE_H_OUT, 2 GATE_H_KELVIN = high-side emitter/switch node. | Kelvin return goes directly to selected high switch emitter; J3 is not the tank-current conductor. Cable/trace loop inductance and switch-node common mode remain open. |
| J4 | 1 GATE_L_OUT, 2 GATE_L_KELVIN/HV_RETURN = low-side emitter/HOT0 reference. | Kelvin return goes directly to selected low switch emitter at the intended HOT0 join; keep bank current out of the gate lead. A J3/J4 return swap invalidates the drive model. |
| J5 | 1 3V3, 2 CTRL_GND. | Isolated control-side source and rail-order/default-off guarantee are needed from auxiliary. |

The accepted unit has a 39 kΩ dead-time setting, 3.9 Ω series gate resistors and 2.2 kΩ gate-to-Kelvin pulldowns. The historical `HalfBridge` embeds another UCC21550 driver with a **34 kΩ** dead-time setting and its own gate network. Reusing that module whole would silently replace the accepted gate interface; only its two-switch topology is a candidate.

### Stop and fault cases

1. PERMIT low, command stop or interlock loss: require inactive PWM **and** driver disable; derive and measure gate-off-to-current-zero latency. A logic-low sample alone cannot prove cessation.
2. Gate-supply or 3V3 loss: test every rail order, driver UVLO, gate-to-Kelvin discharge and an uncharged bootstrap. The standalone digital pass gives no loaded waveforms.
3. No pan, live pan removal or detuning: require a sensing/trip limit derived from measured current, phase, energy and device temperature.
4. One bridge device failed short or simultaneous conduction: PERMIT cannot interrupt failed silicon. Define a bank-side interruption and energy-containment path separately; F2 does not clear the bank's direct short path.
5. Charged VB after PWM stops or F2 opens: gate-off does not discharge the VB bank or any future inverter-side capacitor. Preserve Rev38's session-invalidating restart behavior (`response-contract.md`).

**U2 gate:** power entry must publish a bounded VB waveform and bank-ready contract; auxiliary must bound isolated 15 V and 3V3 rails; the inverter must choose a return topology and acquire the measured coil/pan matrix in [coil-evidence.md](coil-evidence.md). A provisional simulation can explore sensitivity, but cannot select a switch, frequency range or safe operating limit until those inputs are bounded.
