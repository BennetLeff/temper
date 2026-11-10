# Rev G100 datasheet audit and independent layout review: consolidated findings (2026-11-09)

**Sources:**
- Seven subsystem datasheet audits on one brief ([BRIEF.md](BRIEF.md)): [power-entry](power-entry.md), [switcher-ldos](switcher-ldos.md), [mcu-digital](mcu-digital.md), [codec](codec.md), [afe](afe.md), [relays-connectors](relays-connectors.md), [protection](protection.md).
- The independent layout review of a frozen export: [`../rev-g100/independent-review-2026-11-09.md`](../rev-g100/independent-review-2026-11-09.md).
- Netlist snapshot: [parts.txt](parts.txt), [nets.txt](nets.txt).
- The auditors' scratch simulations are in [sims/](sims/). They are evidence for their reports, not committed gate tools.

**Columns:** "Origin" says where a finding came from:
- **G100**: introduced by the 100 × 100 re-layout;
- **G**: introduced by the Rev G protection;
- **F**: inherited from Rev F, so Rev F and Rev G carry it too.

"Checked" is my own verification of the auditor's claim before acting on it.

## Must fix before ordering

| ID | Origin | Finding | Checked | Disposition |
|---|---|---|---|---|
| PROT-01 | G | The jack guard never closes the switches. With the switches open, nothing ties a CUR jack to GND. The sense divider (1.65 V behind 1.62 MΩ) floats an open jack, or a floating DUT, at +1.65 V. `jackguard_mv` returns pin × 13.5 − 3300 × 6.25 = 1650 mV, above `JG_CLOSE_MV` 1000. A passive DUT does not ground the jacks | yes: arithmetic from `jackguard.c`; the study and the host test assume a jack "held at 0 V" | **Firmware:** close on \|V_HC − V_LC\| < 1 V with each jack inside −1.0 … +2.65 V (below the H3V3LD5B's 3.3 V standoff). Host test cases for the float |
| G-AFE-01 | F (AFE-01's 100 Ω row) | A DC source of 1–3 V on the LCUR jack overloads R43 (0.1 W at 1.05 V) and U7A (40 mA at 1.4 V) indefinitely, because the guard trips only above 3.0 V | yes: LCUR sits at the TIA virtual ground, so any DC there is a fault | **Firmware:** LCUR trips at 0.5 V once the switches have settled (the sense filter needs about 13 ms to fall from the 1.65 V float to 0.5 V) |
| SL-1 | F (since U17) | The −12 V rail goes positive at every power-up and power-down. +12 V is up (U11 EN = IN, RAW_P = 5 V − VF through L1/D2) 30–40 ms before ENN. The op amps' 15–17.5 mA leaves through V− and nothing sinks it until an input ESD diode conducts at about +0.6 V. That breaks TPS7A30 OUT-to-GND +0.3 V and OPA2810 input current 10 mA | yes: the mechanism follows from the netlist; no load on −12 V to GND except µA dividers | **Layout:** SS14 (on the BOM) with anode on −12V and cathode on GND, at C100 |
| G-PE-1 | G100 | U16's 100 nF IN bypass (C15) stayed at J1, about 29 mm of copper (two vias) from U16.1. C113 sits behind R121's 1.5 Ω. TPS2553: "0.1 µF or greater ceramic capacitor from IN to GND as close to the IC as possible" | yes: C15 at (62, 137), U16 at (55.6, 115.9) | **Layout:** move C15 beside U16 IN |
| M1 (review) | G100 | 5V B.Cu trunk 2.5–2.95 mm from H3's centre, inside the 3.5 mm reserved for an M3 standoff; a metal standoff bridges 5V to its GND pour through solder mask | yes: x 51.2 / y 144.25 against (54, 141) | **Layout:** take the corner on In2 (0.9 mm, two vias each end), so B.Cu stays ≥ 3.5 mm |
| RCG-01 | G100 (+ G's LEDs on VRLY) | Relay RESET at VBUS 4.40 V leaves about 4.10 V on the coils. Must-operate is 3.75 V at 20 °C and rises about 6–8 % at 40 °C, so the margin is gone at a relay temperature of about 45 °C. G100's trunk (110.5 mΩ against Rev F's 49.8) undid Rev F's R101 fix | yes: the chain adds up from `regulator-check.json` and R101 | **BOM / layout:** recover the drop (R101 value, trunk) and rerun `drive_budget.py` with the routed copper |
| MD-10 | G100 | J4 (SWD) has no GND reference since J5 went. The nearest GND pad is 9.3 mm away | yes | **Layout:** a GND test pad beside J4 |
| MD-6 | G100 | RUN runs 74 mm from U1.26 to C14 (Rev F 27 mm), 0.15 mm on In2, 42.8 mm beside MON12, with no filter at the pin | yes | **Layout:** 100 nF / 1 nF within 3 mm of U1.26 |

## Fix on this board if the copper allows (cheap, real)

| ID | Origin | Finding | Disposition |
|---|---|---|---|
| G-PE-7 | F | A redundant 0.2 mm VBUS loop runs 9.3 mm under J1's grounded shell, insulated only by solder mask | Delete it: the two VBUS pad pairs already join through the B.Cu feed |
| G-PE-6 | G100 | The whole 5V trunk leaves U16 through one 0.3 mm via (1.17 A against 1.34 A) | Add a second via at each trunk via |
| PROT-04 | G | Each jack TVS return is one via into In1 plus about 4 mm to the shell. At 8 kV the open switch sees about 33–48 V for about 1 ns (VOFF 60 V; no ESD rating) | Add a second GND via at each D21–D24 GND pad |
| PROT-05 | G | TLP172AM LED current is 4.98 mA (4.55 mA during the relay RESET pulse), against the 5 mA at which RON max is specified | R132/R133 300 → 270 Ω |
| G-AFE-05 | F | OPA2810 11.1: "Larger (2.2-µF to 6.8-µF) decoupling capacitors … must also be used". Only 1 µF (about 0.5 µF at 12 V) per rail | 1 µF → 2.2–4.7 µF 50 V X7R, same 0805 land, if a JLC part fits |
| SL-11 | F | TI specifies the TPS65131 CN cap as C0G; C85 is X7R | Swap to C0G, same land |
| SL-7 | F | TPS7A49/30 11.1: "The GND pin must be tied directly to the PowerPAD"; pin 4 reaches it only through a via and In1 | Add a top-layer bridge if it fits the copied LDO copper |
| SL-2…4 | F | The TPS65131 power loops are long: one ground via per cap, no top PGND pour. INP peak margin is 1.7 V static | Add GND vias at C89/C90/C82/C91/C92. Scope SW_P / SW_N at bring-up |
| MD-1, MD-2 | F | RP2040: VREG_VIN's 1 µF (C5) is about 7–14 mm of track from pin 44 ("must … close"); DVDD pin 50 has no 100 nF of its own | Try a closer 1 µF / 100 nF south of U1. If the QSPI fan-out leaves no room, accept and record as a Rev F carry-over |
| G-C1 | F | Before `codec_start()` the codec sinks 9 µA, so the TIA leg can pump 3V3A to 3.7–4.6 V at power-up through C74/D11 (AVDD abs max 3.9 V) | **Firmware:** wake U14 and power the ADC before `rails_wait()`. Hardware (Schottky 3V3A → 3V3) at a respin; scope C60 at bring-up |
| RCG-05 | G | REFCAPTURE sets K4 before checking the jacks. A charged DUT then puts about 14 V on R107, the 0.1 % reference | **Firmware:** require `jackguard_ready()` before setting K4 |

## Accept, with a recorded basis and a bring-up check

| ID | Finding | Basis |
|---|---|---|
| PROT-02 | The jack TVS is over its Fig. 3 power curve for a 50 V DUT above about 3 µF (19 % over IPP at 1 µF). | The protected envelope is **about 1 µF at 50 V, about 10 µF at 30 V**. The "50 V charged-part limit" in `rev-g-before-after.md` must be stated with that envelope. A bigger TVS adds capacitance on the measurement nodes |
| PROT-03, G-AFE-02/03 | The TLP172AM's off-state capacitance has no maximum. At 50 V unpowered, U6A's input exceeds 10 mA above 27 pF. HCUR is class B from 2 kV unpowered, LCUR from 8 kV | Bring-up limit: 27 pF or less. Quote 8 kV contact. Unpowered, the pulses are nanoseconds |
| MD-3 | RP2040 pin leakage (1 µA max) is ±1.5 V jack-referred | A datasheet maximum, typically nA. Bring-up: read `JACKS` with the jacks shorted and with them open. A firmware offset is the fallback |
| G-PE-2 | A 5V short with an unlimited source can push U16 IN past 7 V | Fault on fault (a short plus a non-USB source). Host ports ≤ 3 A stay ≤ 6.8 V |
| G-PE-3 | SRV05-4 VRWM is 5.0 V against VBUS up to 5.5 V | Accepted since Rev E: leakage only |
| G-PE-8 / review M2 | The north VBUS pad pair has a 0.2 mm exit, 1.17 A only if the plug touched that pair alone | A plug's four VBUS contacts are tied in the plug, so this is a double fault. `current_check.py` models J1's pins as one node; its docstring is corrected |
| review M3 | 12 V through 0.2 mm In2 jogs in the core | `current_check.py` uses the IPC-2152 generic chart, with the same area on every layer, and passes 0.5 A at 0.187 mm. The reviewer's 0.23 A is IPC-2221's internal curve. The 0.5 A is a fault level (normal load about 36 mA) |
| SL-8, SL-9, SL-12, SL-13, SL-15 | EN–IN tie under the LDOs; exposed-pad vias (ordered "plugged", which the TI note allows); U17 on a 3V3 dip; MON caps far from U1; R95/R96 as fuses | As in the reports. Bring-up: a brown-out test |
| RCG-02 | A 4.5 V coil type is recommended for 5 V drive | 0 stock at JLC; RCG-01's fix recovers the margin |
| RCG-12, RCG-15 | BNC centre hole 1.2 mm at stacked tolerance; TQ2SA stock at JLC falling (1,272) | Drawing note; buy relays early |
| review m2–m7 | Craft deviations (inherited counts identical to Rev G), R13 mid-route (lumped at 60 MHz), crystal, silk line width, references | Inherited or cosmetic |
| review B1 | The Gerbers in the review export were stale | An export error: I copied a pre-fix folder (17:39) instead of the gate run's current zip. The board was right |
