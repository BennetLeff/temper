# Active PFC architecture contract

The replacement prototype follows TI's published 2 kW-class CCM PFC review
(SLUP348, pp. 9-13). The reference places EMI and inrush protection ahead of
the CCM boost, recommends designing the PFC inductor for about 30% ripple at
the worst duty point, and derates power at low line. Its 10 A example is a
design procedure reference, not this product's qualification.

This unit declares a 15 A RMS input ceiling and 1,800 W nominal product class.
At 120 V RMS, 1,800 W requires 15 A at PF=1 before losses, so hardware and
firmware must fold back below low line or the measured current limit. The
target bus is 390 V nominal with four 560 uF / 450 V capacitors in parallel.
The PFC path is bridge plus -> boost inductor -> 650 V MOSFET drain / SiC
diode anode -> 390 V bus; the shunt is in the rectifier return and is sensed
by UCC28180 ISENSE.

Declared orderable identities are UCC28180D, Vishay IHV30EB150 (150 uH / 30 A),
STW65N65DM2, C3D20065D, GBU2510A, B43504A5567M000, and WSL2726R0100FEA.
IHV30EB150 has a manufacturer land-pattern family and +/-10% inductance at
30 A, but hot winding/core loss at the proposed 130 kHz remains open. The
prior Bourns SRP1265-150M sketch and incompatible footprint are rejected. The
inductor hot-current and saturation curves, switch/diode thermal design,
shunt Kelvin layout, capacitor ripple current, and controller compensation
network remain pending source and datasheet review. No physical qualification
is claimed.

The full UCC28180 graph includes the 220 ohm ISENSE lead resistor, gate
resistor, FREQ resistor, ICOMP/VCOMP compensation networks, 768 kOhm/10 kOhm
VSENSE divider, VCC bypass, explicit Kelvin shunt path, relay coil driver and
flyback diode. The 3-lead C3D20065D model uses A1/A2 separate anodes and a
common K cathode. The old voltage-doubler prototype and its source-build outputs remain retained
as rejected evidence, including the corrected 23-27 A RMS and excessive
capacitor-ripple finding. They are not merged into this PFC topology.
