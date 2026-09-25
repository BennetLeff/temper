# Source graph and acceptance boundary

Read alongside the executable fixture and final report; this document defines intended connections, not evidence that a fixture meets them.

## Electrical nodes

| Node | Producer / connection | Consumer / interpretation |
|---|---|---|
| HOT0 | MOSFET source, bulk/local capacitor returns, isolated auxiliary output negative | Controller GND, driver GND, protection GND; never a SELV/MCU bond |
| BR_MINUS | Rectifier negative, opposite side of10mΩ shunt from HOT0 | Negative current-sense voltage; do not move shunt into only the MOSFET branch |
| RECT_PLUS | Full-wave bridge positive | Selected180µH inductor, including winding resistance |
| SW | Inductor output, MOSFET drain, both SiC diode anodes | VDS measurement must reference actual MOSFET source |
| VD | Common diode cathode, local reservoir positive, F2 upstream | Independent diode-side OV/mismatch detector |
| VB | F2 downstream,4×560µF bulk bank, load | UCC28180 VSENSE divider and independent bank-side detector |
| ISENSE | BR_MINUS through220Ω,1nF to HOT0 | Actual negative UCC current sense, not ideal injected measured current |
| VSENSE | VB through5×200kΩ,13kΩ to HOT0,680pF | UCC regulation/OVP/standby; external standby clamp must not disable independent VD/VB sensing |
| PWM | UCC28180 GATE through existing1kΩ input isolation/10kΩ pulldown | UCC27511A IN+; no synthetic fixed-duty source in accepted integration fixture |
| AUX15 | Selected auxiliary interface | UCC28180 VCC, UCC27511A VDD and disable pullup, supervisor/fast-UV dividers |
| LOGIC5 | Selected5V producer | RevB detection/reference/logic including220Ω bleeder |

Retained source `elec/src/power_entry_passive_reva.ato` has no F2/local-reservoir split and drives its MOSFET directly. The new fixture is an integration candidate. Neither its connectivity nor new supply parts are already present in the retained54-part source/native board. RevisionB's79-part compiled graph is a standalone protection circuit.

## Control ownership

- External system control owns precharge/bypass completion, continuity diagnosis and permission to attempt PFC startup. Equality of VD and VB cannot prove F2 continuity.
- Local RevB latch requires a fresh rising ARM edge after health/rails/permit qualify. Loss of health or permit dominates the latch.
- The existing SELV interlock has its own fresh falling reset convention and3.3V permit. It is not a physical producer of the HOT-domain ports merely because signal names resemble them. Isolation and protocol translation remain an integration item until implemented.
- A simulated ARM/PERMIT waveform is a stimulus. It cannot establish the external sequencing producer or qualify partial-power behavior.
- Controller OVP can stop/retry automatically. Local fault latching and actual PFC standby coupling require separate observations; absence of PWM alone is insufficient to prove a latched shutdown.
- A gate command gets no current-interruption credit for a shorted switch. The healthy-device model cannot establish F2 capacitor-fault interruption or disposal of reservoir energy outside F2.

## Manufacturer checks needed before model acceptance

For the selected UCC28180, a plausible feedback loop alone is insufficient. Bind the model implementation to manufacturer behavior: leading-edge modulation; frequency from16.2kΩ; negative ISENSE; SOC discharging VCOMP; cycle-latched PCL with blanking; OVP high/reset hysteresis; VSENSE standby; VCOMP soft-start/discharge and external compensation. Explicitly list any unsupported functions and distinguish injected-pin tests from power-stage feedback tests. A short, precharged switching witness does not prove cold startup or settled regulation.
