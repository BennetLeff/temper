# LT4363 Figure 5 reference check (revision 19 research)

Date: 2026-09-22

## Sources

* Current primary source: Analog Devices, `LT4363`, Rev. C, official URL:
  https://www.analog.com/media/en/technical-documentation/data-sheets/4363fb.pdf
  The web-extracted Rev. C text places Figure 5 on printed page 15 / PDF
  page index 14 and says: “An extra resistor, R1, in series with the gate
  capacitor can improve the turn off time. A diode, D1, should be placed
  across R1 with the cathode connected to C1 as shown in Figure 5.”
* Visual mirror retained as `4363fb-mirror.pdf`: RET Hungary mirror URL:
  https://www.ret.hu/media/product/32613/623865/4363fb.pdf
  This retained PDF is an older Rev. B artifact (footer `4363fb`, printed
  page 15), not the current Rev. C file. Rendered visual pages are
  `mirror-15.png` (Figure 5) and `mirror-04.png` (electrical table).

## Topology finding

The retained visual Figure 5 shows the LT4363 GATE output feeding the
external MOSFET gate through the series resistor R3. The gate-capacitor
branch is on the MOSFET-gate side of that series resistor: the capacitor C1
returns from that node to ground through the added R1 path, and D1 is in
parallel with R1. The diode cathode is on the C1/capacitor side; its anode is
on the MOSFET-gate side. This is the topology represented in Revision 18:

```
LT4363 GATE_DRV -- R6 -- Q_GATE (Q1 gate)
                         |-- R7 -- CG -- ground
                         |-- D1 (anode Q_GATE, cathode CG)
```

The Revision 18 netlist independently confirms the intended polarity: D1
pin 2 (`A_2`) is on `/Q_GATE`, while D1 pin 1 (`K_1`) is on the capacitor
node with R7 pin 2 and C3 pin 1. Therefore the critique's claim that the
branch is on the controller-side `GATE_DRV` node is not supported by the
Figure 5 visual or the current Figure 5 text; it appears to be a visual
reading error. The circuit is still only a prototype and its dynamic
turn-off behavior remains unqualified.

## Current-table caution

The rendered mirror table is Rev. B, not Rev. C. Its printed page 4 table
shows the UV/OV input-current row as `UV = 1.275 V: ±0.2 µA typ, ±1 µA max`
and `UV = −60 V: −1 mA typ, −2 mA max`; this must not be mixed with the
current Rev. C table. The current Rev. C web extraction gives the same
rows at lines 510–519 of the official PDF source, but any numerical timing
or current claim should cite Rev. C explicitly and use its table rather than
the retained mirror artifact.

