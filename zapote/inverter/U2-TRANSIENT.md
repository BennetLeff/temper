# Inverter P3 — coupled VD/VB bank and tank transient screen

**Result:** conditional investigation of a VB_BANK/HOT0 half bridge with a series tank capacitor. The executable model rejects several declared stress corners and leaves F2 interruption and failed-short behavior indeterminate. It does not select 47 kHz, a switch, capacitor, cooling solution or restart rule. No heating or physical safety qualification follows.

## Source and reproducibility

The topology boundary uses the saved U1 read-byte snapshot in [evidence/u1-source-snapshot.md](evidence/u1-source-snapshot.md), not a moving Rev38 checkout. The committed Rev38 PFC source SHA-256 is e3daa14ea8b74344c307a86908c86cbf4d9b44447af367febeb4b581a84ba761, and the accepted gate-drive source SHA-256 is 6e81398feb135f9a7382033173beda50f7a9cb8b7602ccab00a032f4fe40b2b1. Those bytes place the PFC diode-side 22 µF plus 470 nF on VD, four 560 µF cans and a 450 kΩ bleed on VB_BANK, F2 between VD and VB, and HOT0 as power return. Any Rev38 edit requires interface replay. The 0.47 µF **VB-side local** capacitor in these scenarios is hypothetical; the actual inverter commutation capacitor has not been selected. The historical 470 nF on VD is not this local capacitor.

The accepted standalone gate interface supplies PWM_H/PWM_L and active-high PERMIT at J1, isolated 15 V referenced to HV_RETURN at J2, high/low gate and Kelvin returns at J3/J4, and logic 3V3 at J5. Its digital construction acceptance does not establish loaded stop delay. The model's 20 µs loss-to-off delay and 300 ns dead time are declared fixtures, not measured driver behavior.

Run from the repository root:

~~~sh
rustc --edition=2021 -O zapote/inverter/evidence/coupled_transient.rs -o /tmp/zapote-coupled-transient
/tmp/zapote-coupled-transient zapote/inverter/evidence/transient-cases.csv > /tmp/zapote-transient-replay.csv
cmp /tmp/zapote-transient-replay.csv zapote/inverter/evidence/transient-output.csv
rustc --edition=2021 --test zapote/inverter/evidence/coupled_transient.rs -o /tmp/zapote-coupled-transient-test
/tmp/zapote-coupled-transient-test
rustfmt --check zapote/inverter/evidence/coupled_transient.rs
~~~

The scenario and saved result are [evidence/transient-cases.csv](evidence/transient-cases.csv) and [evidence/transient-output.csv](evidence/transient-output.csv). Every row declares F2 state, initial VD/VB/tank state, capacitances, loaded L/C and split resistance, source command and hard current/power clips, bleed, run time, gate/source events, and screen ceilings. Units are in the headers. A source command is max(0, base + gain × (target − VD)), then clipped to nonnegative maximum current and maximum power/VD. The source never sinks bank energy. “Stiff proxy” means a high-gain source capped at 100 A/50 kW; “limited proxy” uses the same feedback command capped at 6 A/1.8 kW. Neither is a measured Rev38 PFC controller or impedance.

## Model and conservation boundary

The ideal bridge switch node is 0 or VB for equal 50% PWM high/low intervals. Its series path returns to **HOT0**, not the historical doubler midpoint PWR_RTN. State is VD, VB, tank current from switch node into series C/coil, and tank-capacitor voltage. The tank equations are L·di/dt = Vswitch − Vcap − (Rcoil + Rpan)·i and C·dVcap/dt = i. Rcoil is a declared **coil copper heat proxy**; Rpan is a separate **reflected loaded-pan dissipation proxy**. They are not a measured impedance decomposition.

For fixed closed F2, VD = VB and Ctotal·dVB/dt = Isource − bridge-current − VD/RD − VB/RB, with Ctotal = CD + CB + Clocal. For fixed open F2, CD·dVD/dt = Isource − VD/RD while (CB + Clocal)·dVB/dt = −bridge-current − VB/RB. The ideal high/low diodes provide a path in dead time and after both gate commands turn off; negative tank current can return energy to VB. At zero current with both gates off and tank-cap voltage between HOT0 and VB, neither diode conducts, so the switch node floats. The solver projects current to zero within a 0.05 A numerical crossing tolerance, below the fixture's 0.1 A timing threshold; the discarded inductor energy is at most 0.11 µJ for 88 µH. The saved diode-path duration counts ideal diode conduction during PWM and after stop. It does not estimate reverse recovery, forward drop or diode temperature.

The ledger checks Eend = Estart + Esource − Ecoil − Epan − EVD-bleed − EVB-bleed, where E is ½CD·VD² + ½(CB + Clocal)·VB² + ½L·i² + ½C·Vcap². The numerical residual is a solver error, **not** a measurement or an estimate of missing heat. The output has an explicit UNMODELED device/capacitor/switching-loss field. No semiconductor conduction, switching, diode-recovery, film-cap ESR, magnetic/core, copper AC, commutation-loop, connector or gate-supply loss has been allocated. The ideal model therefore cannot issue a capacitor or device thermal pass.

An F2 opening while interconnect current may be nonzero is **INDETERMINATE**: its inductance, arc, snubber and transferred energy are missing. The separate fixed-open row starts **after** an externally unspecified opening transfer; its initial 390 V/390 V state is an assumed post-open state and its ledger covers only the subsequent 0.2 ms. Unequal-voltage reclose is rejected because the equalization R/L path is absent. A failed-short bank-to-bridge loop has no bounded current solution here: F2 lies upstream of the VB cans, outside that loop.

## Scenario receipts

All voltages, L/C, resistance, timing and source limits below are declared illustration inputs. The 430 V bus screen is an illustrative ceiling, not a Rev38 allowed operating voltage. The 1600 V capacitor-voltage screen and 160 A current screen are **one-way rejection checks** against historical [CDE 942C catalog](https://www.cde.com/resources/catalogs/942C.pdf) 1600 Vdc tank parts and the historical [Infineon IKW40N120H3 datasheet](https://www.infineon.com/dgdl/Infineon-IKW40N120H3-DataSheet-v01_10-EN.pdf?fileId=db3a304325305e6d012591d4832f7032) pulsed collector/diode figures. The 160 A rating is pulse/temperature dependent. Falling below either scalar figure would not clear AC+DC film stress, pulse width, switch sharing, recovery, overshoot or temperature.

| Case | Saved result | Interpretation |
| --- | --- | --- |
| 390 V, 59.84 µH/300 nF, 47 kHz, cap initially 0 or 195 V | Conditional ideal waveform; 67.34/67.36 A tank peaks, 1004/964 V capacitor-voltage peaks over 2 ms. | Initial cap bias changes the first cycles. Both L and f are historical/illustrative, not adopted operating points. |
| 30 µH/380 nF near 47 kHz, high-current, limited or off source | All reject the declared tank screens. Peaks are 590/567/565 A and 5.43/5.21/5.20 kV. VB ends 328/261/257 V after 2 ms in the mathematical trajectory. | The source delivers 69.33/3.51/0 J. This demonstrates source and bank sensitivity, **not** a physically survivable 2 ms pulse. Do not use the post-limit 58/48/47.6 J coil or pan integrations as a cooling design load. |
| No-pan and weak-pan proxies | Conditional ideal waveforms; 37.0/54.4 A tank peaks. | Pan dissipation is 0/0.156 J, while coil copper proxy is 0.073/0.156 J over 2 ms. Actual unloaded/loaded impedance and pan removal dynamics remain unknown. |
| PWM, PERMIT or gate-rail loss commanded at 0.5 ms | Same **declared** 20 µs delay gives ideal gate off at 0.520 ms. Current last exceeds the arbitrary 0.1 A threshold at 0.53894 ms. | Residual current persists about 18.9 µs after ideal gate off via diode paths in the converged fixture. Identical rows mean the model assigned the same delay, not that these faults physically behave alike. |
| Fixed-open F2 post-state, VD source remains on | Conditional post-open 0.2 ms: VD 390→429.11 V, VB 390→389.76 V. | Source can charge small VD capacitance toward the declared screen while the bank serves the tank. Opening transfer is excluded. |
| F2 opening with source on | Indeterminate at the opening boundary. | A closed-to-open conservation claim would invent missing interconnect energy. |
| Source loss at 0.5 ms | Conditional ideal waveform; source ledger 0.900000 J and VB ends 389.24 V after 2 ms. | Source-current schedule becomes zero; there is no inferred PFC restart or bus-safe state. |
| PWR_RTN, missing loaded L, 450 V above 430 V declared screen, unequal F2 reclose | Rejected. | Inputs that contradict Rev38 topology or omit a necessary state never become a zero-load pass. |

The 0.47 µF hypothetical VB-local capacitor holds 0.0357435 J at 390 V. The actual four nominal 560 µF bank cans hold 170.352 J at 390 V before tolerance; a 22.47 µF VD-side inventory holds about 1.709 J. These numbers are dimensionally separate from current or thermal qualification. The resistor splits in the scenarios are examples, so the listed coil/pan Joules are sensitivity results only.

## Checks and cross-unit handoff

Nine Rust tests cover two independent source-off RC solutions, the algebraic instantaneous power identity, ½CV² dimensions, driven energy closure and timestep convergence, no reverse source flow, midpoint/omitted-L/reclose/over-ceiling rejection, zero-current diode complementarity, current after a gate-off command, and a stop delayed beyond the modeled horizon. The gate-off threshold time converges between 5 and 2.5 ns steps within 0.1 µs; a 50 ns run using the earlier freewheel formulation produced a false late crossing near 0.878 ms and was discarded. The saved output replays byte for byte with the command above. Numerical residuals for all completed fixed-topology rows are at most 35 µJ, including rejected hypothetical trajectories; this only checks the stated ideal equations and cannot be interpreted as hardware loss.

For **discharge**, inventory CD = 22.47 µF on VD, CB = 2240 µF nominal on VB, plus any selected VB-local capacitor. When F2 is open, VD and VB are independent discharge islands; equal nonzero readings cannot prove safe restart. The hypothetical 0.47 µF local part contributes 0.03574 J at 390 V. F2 cannot clear the direct bank failed-short current path.

For **cooling**, the model locates declared Rcoil·i² at the coil/copper assembly, reflected Rpan·i² at the pan/load, and VD/VB bleed at their respective power-entry resistors. Only these modeled ohmic terms can be handed off as conditional scenario heat; the pan term is not automatically PCB or fan heat. All semiconductor, diode, tank/local capacitor, gate supply and commutation-loop losses are **unallocated**, so whole-cooker or fan-off thermal acceptance remains indeterminate. Rejected near-resonant rows are fault-screen alarms, not sustained dissipation budgets.

The next acceptance gate needs measured loaded complex coil/pan impedance across temperature, pan placement/removal and current; Rev38 VD/VB startup, ripple, sag, surge, F2 current and source current/power/transient envelopes; actual gate/PERMIT/rail-loss turn-off and diode recovery; selected VB-local capacitance, loop R/L and bank-side fault interruption; and exact device/capacitor loss and mounted cooling data. Re-run this screen with those bounded inputs, then validate switching and faults on the native circuit and hardware before choosing frequency or components. The accepted gate-drive interface and Rev38 protection/restart session contract remain separate obligations.
