# Leg-A component (package) inductance, to add to the board matrix

The FEM matrix is board copper only: each component is replaced by a closure
that the h → 0 extrapolation removes, i.e. an ideal zero-height connection
across the component's pads. The parts' own inductance is added in SPICE
from these sources. Part numbers are from `native-17/section.kicad_pcb`.

| Ref | Part | Inductance used | Source |
| --- | --- | --- | --- |
| Q2, Q3 | Infineon IPW65R018CFD7, TO-247-3 | **Ld 1.88 nH, Ls 2.82 nH, Lg 8.32 nH** per device | Infineon SPICE library "CFD7 650V", subcircuit `IPW65R018CFD7_L0`, dated 07.05.2021 (via [metacollin/LTspiceInfineonNMOSLibrary](https://github.com/metacollin/LTspiceInfineonNMOSLibrary), `sub/SimulationModel_PowerMOSFET_CoolMOS_CFD7_650V-new.lib`) |
| (cross-check) | TO-247-3 source lead | effective Ls ≈ 2 nH (0 mm pin to PCB) / 4 nH (5 mm) | Infineon AN 2013-05 V1.0 (May 2013), "CoolMOS C7 650V Switch in a Kelvin Source Configuration", p. 8 |
| (cross-check) | TO-247 common-source inductance, measured | 5.5–7.8 nH (three devices, on PCB) | Aikawa et al., IFEEC 2017–ECCE Asia, pp. 1172–1177, Table I, doi:10.1109/IFEEC.2017.7992207 |
| R5 | Vishay WSK2512R0010FEA, 1 mΩ 4-terminal | **0.5–5 nH** | Vishay WSK2512 datasheet, doc 30108, rev. 11-Dec-2023, p. 1 ("Very low inductance 0.5 nH to 5 nH") |
| C38, C39 | TDK B32652A0104K000, 100 nF 1000 VDC, 15 mm pitch, body 9.0 × 17.5 × 18.0 mm | **≤ ~20 nH (upper bound only)** | TDK Film Capacitors General Technical Information (Oct 2025) §2.5: "the maximum value is 1 nH per mm of lead length and capacitor length"; body length from the B3265x datasheet. No part-specific typical value found (TDK's product pages refuse automated fetches; the datasheet's impedance chart is a family curve, too coarse to read for one part). |
| R10, R12 | Yageo RC1206FR-073R9L (1206) | not yet looked up | — |

What this means for the loops (power loop through one capacitor, both FETs,
R5): package terms ≈ 2 × (1.88 + 2.82) = **9.4 nH** for the FETs + **0.5–5 nH**
for R5 + **≤ 20 nH** for the capacitor, on top of the board value. The
capacitor is the largest unknown, comparable to the board loop itself: a
single impedance/resonance measurement of one B32652A0104K000 (with the
seated lead length used on this board) would remove it.

Gate loops: each FET adds Lg + Ls = **11.1 nH** inside its package, plus the
gate resistor and the driver output (not quantified here).

**Update 2026-10-03 (D-7, `delegation/out-D7/`):** TDK's typical PSpice
models (TDK_B32651-8.lib v1.10) give resonance-equivalent ESL of
**1.060 nH for C38–C41** (B32652A0104K000) and **19.200 nH for C5/C6**
(B32656G0275J000). These are typical-model values, not mounted-part bounds;
lead length above the board is not included. The D2 local-capacitor sweep
is 1.06–20 nH; at 1.06 nH no decision verdict changes (`d2/README.md`).

