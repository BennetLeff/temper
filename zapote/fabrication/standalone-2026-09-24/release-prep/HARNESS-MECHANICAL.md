# Mating harnesses and mechanical review — separate board prototypes

**Status:** low-voltage bench harness specification and physical check list, not an approved cooker harness. No harness has been built, continuity-tested, fitted, or energized. All pin numbers below refer to the native board pad numbers, never a guessed cable viewing direction.

## Common connector construction

The installed JST XH headers are `B2B-XH-A(LF)(SN)`, `B4B-XH-A(LF)(SN)`, `B6B-XH-A(LF)(SN)`, and `B8B-XH-A(LF)(SN)`. Use the matching JST `XHP-2`, `XHP-4`, `XHP-6`, and `XHP-8` housings respectively and normal insertion-force `SXH-001T-P0.6` tin contacts with **26 AWG** wire whose insulation outside diameter is within JST's 0.9–1.9 mm range. JST's [XH catalog](https://www.jst-mfg.com/product/pdf/eng/eXH.pdf) specifies this contact for 28–22 AWG and the connector at 3 A with AWG 22, −25 to +85 °C; 26 AWG use does **not** inherit a 3 A rating. Record wire specification, crimp applicator/die, conductor and insulation crimp inspection, pull test, pin retention and finished cable continuity before use. The installed headers have friction retention; provide strain relief in the test fixture. Connector color and printed tags are identification aids, not mechanical keying.

| Board/connector | Mate | Board pin assignment | Prototype cable rule |
| --- | --- | --- | --- |
| RTD J1 probe | XHP-4 | 1 FORCE+, 2 SENSE+, 3 SENSE−, 4 FORCE− | Four separate 26 AWG conductors, ≤500 mm end to end, ≤1 Ω each including contacts; connect only a characterized PT100 four-wire probe; label both ends. |
| Current J2 | XHP-4 | 1 +3V3, 2 isolated GND, 3 OCP_FAULT, 4 SENSE_MON | Bench logic supply/monitor breakout; keep isolated from J1 primary; do not wire SENSE_MON straight to an unqualified MCU ADC. |
| Thermal J1 heatsink | XHP-2 | 1 HS_SENSE, 2 GND | Vishay NTCALUG01A104GA 100 kΩ remote sensor; polarity independent. |
| Thermal J2 coil | XHP-2 | 1 COIL_SENSE, 2 GND | Same sensor; use a unique physical route/tag to avoid J1/J2 swap. |
| Thermal J3 host | XHP-6 | 1 +3V3, 2 GND, 3 HS_FAULT, 4 COIL_FAULT, 5 HS_SENSE, 6 COIL_SENSE | Isolated low-voltage bench breakout. |
| Interlock J1 faults | XHP-8 | 1 GND, 2 OCP, 3 OVP, 4 HS_FAULT, 5 COIL_FAULT, 6 RTD_FAULT, 7 RUNAWAY_FAULT, 8 AUX_FAULT | Keep this mating cable physically segregated/tagged from J2. Disconnected individual faults must read asserted under the stated leakage budget. |
| Interlock J2 host | XHP-8 | 1 +3V3, 2 GND, 3 WDI, 4 RESET_N, 5 SENSOR_LIVE, 6 PERMIT, 7 LATCHED_FAULT, 8 WDT_RESET_N | Host receiver must pull PERMIT low; no MCU automatic restart pulse policy. **Same housing as J1: connector swap is possible.** |
| Gate J1 control | XHP-4 | 1 PWM_H, 2 PWM_L, 3 PERMIT, 4 CTRL_GND | Low-voltage source with a default-low PERMIT and independent shutdown. |

The pin map for gate J2–J5 below was independently extracted from the accepted native schematic with `kicad-cli sch export netlist --format kicadxml` on 2026-09-24. All four installed headers are Würth `61300211121`, 2.54 mm, unkeyed. The [Würth product data](https://www.we-online.com/components/products/datasheet/6130xx11121.pdf) identifies the 2-pin header but does not establish a qualified wire-housing mate for this application. **No final mating part or cable assembly is approved.** Use individually guarded, tagged, continuity-checked connections only in an approved low-energy fixture; these are not power-stage wiring instructions.

| Gate header | Pin 1 | Pin 2 | Physical risk to close |
| --- | --- | --- | --- |
| J2 | +15V_LS | GATE_L_KELVIN / HV_RETURN | Isolated 15 V supply return and insulation boundary |
| J3 | GATE_H_OUT | GATE_H_KELVIN | High-side Kelvin pair, floating at switching potential |
| J4 | GATE_L_OUT | GATE_L_KELVIN | Low-side Kelvin pair; avoid loop area and connector interchange |
| J5 | +3V3 | CTRL_GND | Logic supply; must not be mated to J2–J4 |

## Current primary construction boundary

Current J1.1 `PRIMARY_IN` and J1.2 `PRIMARY_OUT` are **bare copper solder lands**, not a rated 15 A connector. The two 3.00 mm plated holes and 8 mm/70 µm primary tracks in the saved board are prototype geometry, not a current, thermal, retention or insulation qualification. Do not provide a production primary harness by simply soldering wire to the pads. The next physical design drawing must specify conductor or busbar alloy/cross-section, insulation system and creepage, attachment geometry/process, strain relief, bend radius, solder thermal process, current waveform and duration, contact resistance/temperature acceptance, CT body support and high-pot/clearance fixture. Until reviewed, assembly excludes J1 and the board is limited to isolated low-energy secondary/fixture work.

## Mechanical and wiring acceptance register

| Item | Digital result | Required closure before order/energization |
| --- | --- | --- |
| CST3015 T1 lands | [Existing official drawing comparison](../../../current-sense/evidence/cst3015-footprint-review.md) matches primary 4.8×9.0 mm, secondary 3.0×4.6 mm, 18.5 mm row-edge gap; body envelope 23×30 mm, height 15.2 mm. | Obtain exact part, assembly courtyard/stencil review, body support and primary termination drawing. No 3D interference or fixture fit accepted. |
| RTD FTSH-105-01-F-D J2 | [Saved footprint review](../../../rtd/circuit/footprint_receipt.txt) verifies 10 numbered 0.71 mm holes and 1.05 mm pads against Samtec print. Samtec lists [FFSD cable assemblies](https://www.samtec.com/products/ftsh-105-01-f-d) as mating family. | Select a specific 2×5 cable ordering code/length, confirm board-side pin-1 orientation and body/strain-relief envelope against the exact mate. Plain `-D` header has no shroud/key; reversed mating is possible. |
| RTD U6 WSON | [Saved footprint review](../../../rtd/circuit/footprint_receipt.txt) checks six pads against TI DSE drawing. | First-article optical/X-ray decision for mask-defined versus non-mask-defined pads and solder print; vendor approval. |
| Gate U1 UCC21550 DWK | Existing VRML is expressly approximate: 7.5×10.3×2.5 mm body. [TI DWK drawing](https://www.ti.com/lit/ds/symlink/ucc21550-q1.pdf) allows 7.4–7.6 × 10.1–10.5 mm and up to 2.65 mm height. The model therefore does **not** bound maximum package size. | Replace/check against manufacturer STEP or bounding-box model, inspect all clearances to adjacent components, board edge and enclosure/fixture; confirm skipped DWK pins 12/13, pad row and assembly orientation. |
| Interlock J1/J2 | Both are identical XH 8-position headers. | Appliance harness requires different keyed connector designs, separated connector locations with documented routing/retention, or a validated interposer that prevents interchange. Tags/colors alone are not a fail-safe fix. |
| Gate J2–J5 | Identical unkeyed 2-pin headers; one pair is floating high-side. | Redesign/select mechanically distinct qualified interfaces and rate each assembled connection for voltage, insulation, temperature and vibration before inverter integration. |
| Thermal sensors | Vishay NTCALUG01A104GA lead length is 38.1 mm; XH connector is limited to +85 °C including rise. | Place PCB/connectors in cooler electronics space; design and qualify insulated extension, splice, retention, routing and contact thermal environment. |
| Enclosure and board mounts | Gerbers give outlines; no accepted enclosure, standoff, coil/pan/fan geometry or cable routing drawing in this package. | Dimensioned enclosure and fixture fit check, connector insertion/removal envelope, creepage/clearance and service access before an integrated cooker build. |

## Continuity and miswire witness required for every fabricated cable

With all boards unpowered: inspect contact part/insulation fit and latch, continuity-test every numbered contact to the named far-end node, test every adjacent conductor for shorts, verify no +3V3 path to interlock J1 or gate J2–J4, and deliberately attempt the plausible wrong mating combinations in a dead fixture. A swap that can connect must be treated as an unresolved mechanical defect. Record cable serial number, drawing revision, measured length and conductor resistance, inspection photos and tester result. These are acceptance criteria, not tests already run.
