# Rev38 F2 board-to-holder interface candidate

Status: **exact connector candidate found; footprint and fault-current acceptance OPEN**. F2 remains the off-board Mersen `A70QS50-14F` in `US141/Z331153`; this note selects no alternate holder or fuse.

## Candidate: Phoenix Contact 1017526

The [Phoenix Contact `TDPT 16/ 2-SC-10,16-ZB` product record](https://www.phoenixcontact.com/en-pc/products/pcb-terminal-block-tdpt-16-2-sc-1016-zb-1017526) identifies order number **1017526**, a two-position PCB screw terminal with two distinct potentials. It can be the *board end* of the dedicated VD-out/VB-return cable pair. Position 1 would carry `VD_LOCAL` to the holder input; position 2 would return holder output to `VB_BANK`. Neither position is HOT0, and the block does not replace F2.

| Published property | Exact-part evidence | Rev38 disposition |
| --- | --- | --- |
| Nominal current and insulation | 76 A, 1000 V for IEC III/2; 800 V for III/3; cULus listing table gives 58 A, 600 V for B/C | Above the 50 A fuse nameplate as a nominal component screen. Confirm the intended residential certification category and DC application; ratings do not establish fault-current withstand or PCB trace capacity. |
| Wire and assembly | 0.75–16 mm² rigid/flexible, AWG 20–6; 18 mm strip; 1.4–1.7 N·m screw torque | Select one conductor size and insulation/termination method for the actual cable and holder, then qualify bend radius, strain relief and assembly torque. |
| Temperature | −40 to 105 °C operation **subject to current derating**; housing PA, CTI 600, UL94 V-0 | Measure local enclosure and terminal temperature at worst sustained and pulsed load. The 76 A nominal figure is not an all-temperature permission. |
| Insulation geometry | Manufacturer states 8 mm minimum clearance and 8 mm creepage for III/2, 1000 V/8 kV; III/3 is 8 mm clearance and 10 mm creepage at 800 V/8 kV | Check adjacent live structures, solder pads, copper and enclosure in the native board; the terminal's internal figures do not prove board spacing. |
| Board pattern | 10.16 mm pitch, **zigzag W pinning**, two solder pins per potential, 3.5 mm solder-pin length | Phoenix's 2018 family drawing establishes the stagger and nominal centers below. Its illustrative Ø2.0 mm holes conflict with the 1.85 mm hole specified in both the 2018 data table and the current product page. Resolve that conflict before a production footprint is assigned. |

The product page also lists a 21.34 × 31.9 mm board-facing envelope and 31.2 mm installed height. The [manufacturer's generated product PDF](https://www.phoenixcontact.com/en-gb/products/printed-circuit-board-terminal-tdpt-16-2-sc-1016-zb-1017526?type=pdf), dated 2026-08-29, repeats the current 1.85 mm hole and 1 × 0.9 mm pin entries. It has no dimensioned four-hole pattern or land diameter. This newer catalog evidence favors 1.85 mm but does not formally supersede the controlled 2018 drawing's illustrative Ø2.0 mm callout. No Rev38 library footprint exists for 1017526.

### Manufacturer drilling drawing and pad-center derivation

Phoenix Contact's [1017526 datasheet, 2018-04-23, product version 01, document revision 00](https://media.digikey.com/pdf/Data%20Sheets/Phoenix%20Contact%20PDFs/1017526_Ds.pdf), page 6, reproduces its family drawing titled `TDPT 16/..-SC-10,16-ZB`, drawing `01114300 / 00`, dated 2018-01-31. The drawing explicitly has a two-position row in its width table (`21.34 ±0.40 mm`) even though it depicts a five-position example. The drawing labels the land illustration **“footprint only for information.”** Its nominal dimensions are: 5.59 ±0.2 mm from the left housing edge to the *center* of the first solder-pin pair, 3.6 ±0.1 mm between the two pins of one potential, 10.16 ±0.2 mm between potential centers along the pitch direction, and 10.16 mm between the two staggered rows. The first row is 25.3 mm from the opposite end of the 31.9 mm housing, so its nominal offset from that end is 6.6 mm. Reading the first two potentials from the five-position family drawing gives this **dimensional screen** (mm):

| Physical pin | Potential, viewed from screw-entry side | Center from housing left edge X | Center from housing rear edge Y | Relative center if first pair midpoint is `(0, 0)` |
| --- | --- | ---: | ---: | --- |
| 1a | Left screw position / `VD_LOCAL` candidate | 3.79 | 6.60 | `(-1.80, 0)` |
| 1b | Left screw position / `VD_LOCAL` candidate | 7.39 | 6.60 | `(1.80, 0)` |
| 2a | Right screw position / `VB_BANK` candidate | 13.95 | 16.76 | `(8.36, 10.16)` |
| 2b | Right screw position / `VB_BANK` candidate | 17.55 | 16.76 | `(11.96, 10.16)` |

The two pins per potential and the pair grouping follow the manufacturer's product description and drawing. The net names above are the proposed Rev38 cable assignment, **not** a claim that Phoenix assigns electrical polarity. Check the actual part for pin-to-screw continuity and confirm the drawing's viewing face before numbering native pads.

The 2018 drawing calls out **Ø2.0 mm** holes, while that same datasheet's page 5 says **1.85 mm** hole diameter. The [current Phoenix product record](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-tdpt-16-2-sc-1016-zb-1017526) also says **1.85 mm** and lists **1 × 0.9 mm** pins; the 2018 data table and section drawing instead say **1.4 × 0.9 mm** pins. These are manufacturer-internal inconsistencies, not pad-center uncertainty. The manufacturer ECAD/drilling revision or a current sample measurement is needed to select drill and land dimensions. A footprint derived from this drawing alone would be a layout screen, not a released board pattern, and must not be assigned to F2 for native acceptance.

The same 2018 datasheet, page 8, records a **303 A AC** short-time withstand test with a **16 mm²** conductor under IEC 60947-7-4. It does not state the pulse duration or waveform there, and the result does not establish a DC fault-current rating for this board's solder joints, copper, or cable. Retain the fault envelope as an open qualification item.

## Circuit and assembly boundary

The joined Atopile source now contains both `f2`, the two-contact off-board series fuse, and `f2_board`, a separate 1017526 four-pin board-terminal candidate. `f2.diode` and terminal pins 1/2 join `VD_LOCAL`; `f2.bank` and terminal pins 3/4 join `VB_BANK`. This numbering follows the Phoenix-hosted SamacSys preview and is still a **candidate**, pending confirmation against the delivered part and its final drilling data. The Rust audit checks both solder pins on each potential and rejects a split or crossed potential. `source-build-02` is the frozen 300-reference export of this topology. The off-board F2 stays in the assembly schematic/BOM; a board-only netlist may terminate at the two distinct terminal potentials, but its evidence must trace the external holder path back to the joined circuit. Putting `temper:A70QS50_ETI_CH14_Prototype` clips on the board would contradict the selected US141 holder.

Before promoting this candidate, close four specific inputs:

1. Reconcile the manufacturer's Ø2.0/1.85 mm hole and 1.4/1.0 mm pin-size discrepancies with its current ECAD/drilling revision or a current sample. Then verify the four drawing-derived pad coordinates, pad-to-screw continuity, annular-ring tolerances, courtyard and copper spacing in KiCad. Check whether the 10.16 mm staggered two-position block leaves adequate clearance and creepage between the solder lands at the required fault and installation voltages.
2. Set the intended cable gauge, insulation, termination, restraint, enclosure routing and holder terminal details. Include both cable/contact resistance and inductance in the F2 capacitor-discharge and thermal analysis.
3. Establish the maximum continuous, pulsed and prospective fault current at this interface, then obtain a justifiable short-time withstand/temperature-rise basis for the block, joints, copper and cable. The manufacturer's 303 A AC test result has no stated time or waveform and is not a numeric DC fault envelope for the assembled interface.
4. Confirm the applicable voltage/category and listing basis for the residential product, including whether the cULus 600 V table covers the required DC use. The selected F2 fuse's DC clearing/let-through and minimum-breaking-current questions remain separately open under the [retained disposition](../DISPOSITION.md).

Until these are closed, retain the `TBD_REVIEW_ONLY` F2 footprint in `pfc_power.ato`; do not silently use the provisional PCB clips or claim a physical F2 interface PASS.
