# Power-entry loss budget

Read [results and next decisions](RESULTS.md) for the retained 18-case run.

Execution contract (2026-09-16): compute a source-bound planning loss budget
for the maintained shunt-repair board using the existing CCM current model.
Rust owns formulas, source checks and verdicts. The common unit runner must
execute it; missing loss terms cannot yield thermal acceptance. Evidence goes
in `evidence/`, including the common run and independent regression results.
No board geometry or retained FEM evidence changes in this step.

The reviewed operating grid is a sensitivity study, not a product input rating:
108/120/132 Vrms, 15 A true RMS, 180 µH ±20%, copper at 20/100°C.
Input power is the ideal current model's input power, not delivered DC power.
At 120 V/15 A even an ideal input leaves less than 1,800 W after losses.
The model omits line-zero-crossing distortion, controller maximum-duty effects,
startup, DCM, thermal feedback and current-loop dynamics.

The board's `STW65N65DM2` identity has no exact manufacturer record in the
sources retrieved for this study. ST publishes `STW65N65DM2AG` and
`STW63N65DM2`; neither is silently substituted. The MOSFET sweep uses explicit
design assumptions (50/100 mΩ, 20/50/100 ns each edge), not part guarantees.
It excludes Eoss and diode capacitive commutation loss. Resolve the exact
orderable MOSFET and validate actual 10 Ω gate-drive switching waveforms before
using a switch loss prediction to size cooling.

Retained primary sources:

| File | Source | Used condition |
| --- | --- | --- |
| sources/760800301.pdf | https://www.we-online.com/components/products/datasheet/760800301.pdf | 180 µH ±20%; maximum 20 mΩ at 20°C; no core-loss model |
| sources/Diodes-GBJ2510.pdf | https://www.diodes.com/datasheet/download/GBJ2510.pdf | 1.05 V maximum per diode at 12.5 A/25°C only |
| sources/RT1_Inrush.pdf | https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocFormat=pdf&DocLang=English&DocNm=RT1_Inrush&DocType=Data+Sheet&PartCntxt=2-1393240-3 | 360 Ω coil at 23°C, ±10%; contact loss unspecified |

The Rust report embeds these documents' hashes. Bridge loss uses a constant
1.05 V sensitivity assumption across the waveform; the datasheet's one test
point is **not** a forward-drop bound at every instantaneous current and
temperature. Inductor DC loss uses cold maximum DCR and assumed copper
coefficient 0.00393/K referenced to 20°C; AC/core losses remain missing.
Shunt loss uses +1% resistance at reference temperature; no hot TCR guarantee.
The relay calculation uses 15 V, 360 Ω coil and 91 Ω series resistor, energized;
driver drop, temperature and tolerances remain outside that nominal estimate.

Missing losses are named, never zero-filled: MOSFET, SiC diode, CMC, capacitor
bank and film capacitor, inductor AC/core, PCB/terminals/fuse, bypass contact,
controller and small-signal supply. Full-load unbypassed NTC operation is a
separate fault/startup case. The existing cooling study's 40 W bridge +65 W
other-electronics reservation is shown only for comparison, never as spare
capacity or an acceptance margin.

Next closure sequence: correct exact MOSFET identity in authored source and
native artifacts; model its gate transitions/Eoss plus SiC commutation;
obtain inductor core/AC loss and capacitor impedance; allocate each heat
source to its actual sink/board/air path. Installed airflow and sink-to-board
coupling must be established before the prior imposed 60°C board boundary
can represent an assembly. Then close switching-loop parasitics and
startup/inrush/shutdown/bias timing, and define the auxiliary-supply contract.
