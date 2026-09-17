# Power-entry loss budget

Read [results and next decisions](RESULTS.md) for the retained 18-case run, and
the [candidate screen](candidates.md) for the five re-engineering options
screened at a common required power. [The decision record](DECISION.md) states
which architecture the retained evidence supports and what remains unmeasured.

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

The board's `STW65N65DM2` identity is ST's marking form, not an order code.
The retained datasheet's Device summary gives the order code as `STW65N65DM2AG`
against marking `65N65DM2`; `STW63N65DM2` is a different orderable device and is
not substituted. The MOSFET sweep still uses explicit design assumptions
(50/100 mΩ, 20/50/100 ns each edge), not part guarantees, but the output
capacitance and gate terms are now that part's datasheet typicals rather than an
unnamed device's. Measured switching waveforms at the actual 10 Ω gate network
remain required before a switch loss prediction sizes cooling, and the authored
source, BOM and native board still carry the marking form pending a board
regeneration.

Retained primary sources:

| File | Source | Used condition |
| --- | --- | --- |
| sources/760800301.pdf | https://www.we-online.com/components/products/datasheet/760800301.pdf | 180 µH ±20%; maximum 20 mΩ at 20°C; no core-loss model |
| sources/Diodes-GBJ2510.pdf | https://www.diodes.com/datasheet/download/GBJ2510.pdf | 1.05 V maximum per diode at 12.5 A/25°C only |
| sources/RT1_Inrush.pdf | https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocFormat=pdf&DocLang=English&DocNm=RT1_Inrush&DocType=Data+Sheet&PartCntxt=2-1393240-3 | 360 Ω coil at 23°C, ±10%; contact loss unspecified |
| sources/STW65N65DM2AG.pdf | https://www.st.com/resource/en/datasheet/stw65n65dm2ag.pdf | Order code `STW65N65DM2AG`/marking `65N65DM2`; `RDS(on)` max 50 mΩ at 25°C; `C_oss eq.` 456 pF; `Qg` 120 nC |

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

The [candidate screen](candidates.md) adds the re-engineering question to this
unit. It fixes a common required power and derives the current each line needs
to carry it, rather than holding 15 A at every line (which would mean three
different powers and an unintentionally flat bridge term). It promotes nothing,
selects no architecture and adds no thermal verdict. Its useful output is a
priority order for the next measurement work: the boost cell's switching
behaviour can move the heat budget by tens of watts, low line cannot meet the
requirement at all inside the 15 A ceiling (179.3 W short at 108 V), paralleling
two bridges is inconclusive rather than rejected because the constant-drop model
has no slope term to share, and the active-rectifier question reduces to whether
the device's hot RDS(on) stays under about 63 mOhm.

Run the runner in `--release`. The power-entry stage replays about 1.2 GB of
retained FEM meshes, and a debug build is roughly an order of magnitude slower:
a debug run had not finished power-entry after 25 minutes, while the same run in
release completes all seven units in about five minutes.

Next closure sequence: correct exact MOSFET identity in authored source and
native artifacts; model its gate transitions/Eoss plus SiC commutation;
obtain inductor core/AC loss and capacitor impedance; allocate each heat
source to its actual sink/board/air path. Installed airflow and sink-to-board
coupling must be established before the prior imposed 60°C board boundary
can represent an assembly. Then close switching-loop parasitics and
startup/inrush/shutdown/bias timing, and define the auxiliary-supply contract.
