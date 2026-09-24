# Rev38 generic passive footprint inventory

2026-09-23. This pass assigns installed KiCad standard two-pad footprints to
46 source-level passive instances whose selected MPNs encode the same EIA body
size. It changes package assignments only. The joined netlist contains 48
`TBD_REVIEW_ONLY` physical occurrences after the pass, down from 127 before
it; repeated modules account for the larger occurrence reduction.

| Selected MPN families and source instances | Installed KiCad footprint | Count |
| --- | --- | ---: |
| Yageo `RC0603FR-*`, source, AUX, ESP pull-ups, driver defaults, rail supervisors, F2 input, receiver default | `Resistor_SMD:R_0603_1608Metric` | 15 |
| Yageo `RC1206FR-*` and Vishay `TNPW1206*`, AC relay gate, F2 dividers, PFC control | `Resistor_SMD:R_1206_3216Metric` | 14 |
| Yageo `RC2512FR-07150KL` and Vishay `CRCW2512200KFKEG`, bank bleeder and PFC VSENSE chain | `Resistor_SMD:R_2512_6332Metric` | 6 |
| Murata `GRM188*`, source watchdog, ESP EN, rail supervisor timing, F2 filter, receiver timing | `Capacitor_SMD:C_0603_1608Metric` | 5 |
| KEMET `C0805C*`, PFC sense, compensation, feed and VCC | `Capacitor_SMD:C_0805_2012Metric` | 5 |
| Murata `GRM32ER71H475KA88L`, PFC compensation | `Capacitor_SMD:C_1210_3225Metric` | 1 |

The exact standard footprint files were present in the installed KiCad
`Resistor_SMD.pretty` and `Capacitor_SMD.pretty` libraries. Each has two SMD
pads numbered 1 and 2. Its pad geometry and nominal chip size agree with the
respective EIA body: 0603 = 1.6 × 0.8 mm, 0805 = 2.0 × 1.25 mm,
1206 = 3.2 × 1.6 mm, 1210 = 3.2 × 2.5 mm, and 2512 = 6.3 × 3.2 mm.
The installed 0603 resistor pads are 0.80 × 0.95 mm, and the 1206 resistor
pads are 1.125 × 1.75 mm. Vishay recommends 0.75 × 1.00 mm and
1.05 × 1.80 mm, respectively, for reflow. The KiCad 2512 resistor pads are
1.225 × 3.35 mm against Vishay's 1.45 × 3.50 mm reflow recommendation:
the KiCad pattern gives a shorter toe and must be accepted by the native
assembly review before release. These are body and pad-number-compatible
standard footprints, not released assembly drawings. See the [Vishay
land-pattern table](https://www.vishay.com/docs/20035/dcrcwe3.pdf).

## Electrical screen bounded to footprint selection

- [Yageo RC_L specification](https://yageogroup.com/content/datasheet/asset/file/PYU-RC_GROUP_51_ROHS_L): the chosen `RC0603`, `RC1206`, and `RC2512` sizes are 75 V/0.1 W, 200 V/0.25 W, and 200 V/1 W at 70 °C in the ordinary grade, respectively. The AUX and logic resistor nodes are at or below the local 15 V rail in the nominal circuit. The three 150 kΩ bank bleeders split a 400 V bank nominally into 133.3 V and 0.119 W apiece. This assumes all three are intact and equal; discharge time, abnormal voltage sharing, board temperature and fault energy remain open.
- [Vishay TNPW e3 specification](https://www.vishay.com/docs/28758/tnpw_e3.pdf) gives the 1206 thin-film body, 200 V operating limit and power derating. The F2 dividers use four 200 kΩ plus 187 kΩ and a 5.62 kΩ bottom element, so a 400 V bus gives about 80.5 V across a 200 kΩ top element and 0.032 W. This nominal arithmetic does not qualify bus surges or resistor-open faults.
- [Vishay D/CRCW e3 specification](https://www.vishay.com/docs/20035/dcrcwe3.pdf) identifies the 2512 body. The five 200 kΩ PFC VSENSE top resistors share approximately 400 V, giving about 79 V and 0.031 W each in the intact nominal chain. The native layout still must verify creepage and clearance along the high-voltage chain.
- [Murata GRM catalog](https://www.murata.com/-/media/webrenewal/tool/library/common-pdf/dynamic-model/component-list-d-mlcc-2504.ashx?cvid=20250523010405000000&la=en) confirms `GRM188R71A105KA61` as 0603/10 V and `GRM32ER71H475KA88` as 1210/50 V. The former is on SELV3V3. [Murata's 1210 part sheet](https://www.murata.com/en-eu/api/pdfdownloadapi?cate=luCeramicCapacitorsSMD&partno=GRM32ER71H475KA88L) specifies 3.2 × 2.5 mm and 50 V. The other selected GRM188 C0G and X7R MPNs use 0603 bodies; capacitor effective capacitance and DC-bias behavior are separate electrical reviews.
- [KEMET 0805 product specification](https://search.kemet.com/component-documentation/download/specsheet/C0805C105K5RACTU) specifies a 2.0 × 1.25 mm body and 50 V for the selected PFC VCC 1 µF part. The other `C0805C*5*` PFC capacitors have the same 0805 case and 50 V code. Their nominal PFC control and protected-AUX node voltages are below 50 V; their effective capacitance, tolerance and ripple remain part of controller qualification.

`AC_RELAY_DROP_R91_2512` and `GATE_R10_1206` deliberately retain their
review placeholders. Their EIA package names alone cannot qualify relay coil
fault heating or the switching pulse load. Other special IC, inductor,
connector, mains, fuse and power-device placeholders were untouched.

Atopile 0.2.69 can copy one MPN into netlist records of unlike components
that share a standard footprint. The generated CSV BOM retains per-reference
MPNs; native BOM review and the Rev38 audit must use it as the part identity
authority while continuing to use the netlist for connectivity. This pass
does not approve assembly procurement, placement, creepage, thermal rise,
startup, or fault response.
