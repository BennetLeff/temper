# UCC28180 reference deviations

This value/topology comparison uses the frozen local baseline and TI's primary [UCC28180EVM-573 guide](https://www.ti.com/lit/pdf/sluuat3) and current-revision [TIDA-00779 design guide](https://www.ti.com/lit/pdf/tidube1). It is an inventory, not an adoption or simulation recommendation.

| Area | Frozen local baseline | TI reference value/topology | Finding |
|---|---|---|---|
| Current sense | 10 mΩ bridge shunt, 220 Ω series `Risense`, 1 nF `Cisense` | EVM schematic p6: 32 mΩ `R4` shunt, 221 Ω `R2` series ISENSE, 1 nF `C8`; 17.8 kΩ `R3` is FREQ, not current sense | Shunt value differs; 220 Ω/1 nF filter is close to EVM 221 Ω/1 nF. TIDA current-sense scaling remains unresolved |
| Voltage feedback | 1 MΩ / 13 kΩ divider, 680 pF | EVM p6: upper chain R9=332 kΩ, R10=332 kΩ, R11=340 kΩ, R12=0, with R8=49.9 Ω series; lower R13=13.3 kΩ and C15=820 pF | Confirmed EVM network/value mismatch; TIDA network still needs exact schematic comparison |
| ICOMP/VCOMP | 2.7 nF ICOMP; 40.2 kΩ, 4.7 µF, 220 nF VCOMP network | EVM p6: C7=2.7 nF ICOMP; R6=22.6 kΩ with C13=4.7 µF and C14=0.47 µF VCOMP. R7=10 kΩ is GATE pulldown, not feedback | ICOMP capacitor matches; VCOMP network differs. TIDA exact network comparison remains pending |
| Frequency | `RFREQ=16.2 kΩ`; surrogate computes ~129.107 kHz | EVM nominal 120 kHz; TIDA uses 47 kΩ for ~45 kHz | Confirmed frequency mismatch |
| Startup/bias | Scripted 15 V auxiliary, 5 V logic, permit/arm/standby PWL rails | EVM uses external regulated 12 V bias; TIDA uses external 12 V for controller, UCC27531, and relay (~55 mA), explicitly no bootstrap | Confirmed scripted-rail mismatch; equivalence unresolved |
| Gate drive | Host behavioral `Bgate` plus authored behavioral `Xdriver ... AUTH_UCC27511A_H` protection path | EVM uses UCC28180 integrated gate output; TIDA uses UCC28180 with UCC27531D driver | Confirmed implementation/model mismatch; local path is not an omitted driver, but it is not the reference IC implementation |
| Magnetics/output | 180 µH, 19.8 µF local + 2240 µF bank, generic devices | EVM 327 µH / 270 µF and named MOS/diode; TIDA 180 µH and 2040 µF at 3.5 kW | Confirmed value/device differences; saturation and thermal correlation pending |

The EVM is a 360 W, 390 V, 85–265 VAC design with 120 kHz average-current control and documented UVLO, soft/cycle current limits, open-loop detection, OVP hysteresis, and soft-start (guide pp. 2–5). TIDA-00779 is a 3.5 kW, 390 V CCM design for 190–270 VAC, using 45 kHz, a 47 kΩ FREQ resistor, 180 µH choke, and external 12 V bias (current-revision design guide pp. 3–9). Neither establishes the local 1.8 kW, 108/120 VAC induction-load behavior.

The current product benchmark is Breville Control Freak CMC850, listed as 120 V, 60 Hz, 1800 W mains input in the manufacturer-hosted [specification sheet](https://savagebros.com/wp-content/uploads/2024/10/Breville-ControlFreak-CMC850_USA.pdf). That is an input benchmark, not guaranteed DC/pan output. The local 15 A screen remains unchanged; low-line derating and efficiency must be resolved independently.

Local hashes and unresolved next comparisons are recorded in the companion JSON. No frozen case, solver, or raw trace was changed.
