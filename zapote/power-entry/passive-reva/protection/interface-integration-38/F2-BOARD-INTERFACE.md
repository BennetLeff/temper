# Rev38 F2 board-to-holder interface candidate

Status: **two separate board studs joined in `source-build-06`; layout and fault-current acceptance OPEN**. F2 remains the off-board Mersen `A70QS50-14F` in `US141/Z331153`; this note selects no alternate holder or fuse. The Phoenix studies below are historical screens, not the current board termination.

## Historical candidate: Phoenix Contact 1017526

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

### Phoenix-linked CAD archive cross-check (2026-09-24)

The 1017526 product page's 3D/CAD download served a **SamacSys** KiCad archive, not a controlled Phoenix drilling revision. Archive SHA-256: `d41db8f3ae569c3f1caae4a4b74dbbb552ac77875e8a4ae2b5aab78135b75446`; its `part_info.txt` says released 2018-11-29. The enclosed `1017526.kicad_mod` has four Ø2.0 mm drills, 3.0 mm circular lands and pad centers `(0, 0)`, `(3.60, 0)`, `(10.16, 10.16)`, `(13.76, 10.16)` mm. Its 21.34 × 31.9 mm fabrication outline agrees with Phoenix's current 1017526 body size. The centers independently corroborate the drawing-derived stagger and candidate pin grouping; the Ø2.0 mm drill **does not resolve** the current 1.85 mm Phoenix product-data callout. A file offered from the product page is not evidence that Phoenix approved this third-party land pattern for the current part revision.

The similar Phoenix [1017531 push-in product](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-tdpt-16-2-sp-1016-zb-1017531) has a published Ø2.0 mm hole and 1.2 × 1.0 mm pin, so it looked like a possible way to avoid the drill conflict. Its Phoenix-linked SamacSys KiCad archive (SHA-256 `2ae21695cfc35e40890cb5986ba02188be1ef4ca2a31b2ff18e465805f65ff81`, `part_info.txt` released 2019-06-03) shares the same four pad centers and Ø2.0 mm drills. However, that archive copies the **21.34 mm** fabrication-body width of 1017526 while Phoenix lists **17.74 mm** for 1017531. Its pad 1/2 shapes also differ from the 1017526 archive. This stale or mislabeled body outline prevented its use as an unreviewed replacement for the then-selected 1017526. Both Phoenix candidates are historical relative to `source-build-06`.

### Additional terminal study: Phoenix 1709681

The current [Phoenix MKDS 10 HV/ 2-ZB-10,16 product record](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-mkds-10-hv-2-zb-1016-1709681) identifies order number **1709681**. It says two potentials with two solder pins per potential, 76 A and 1000 V IEC III/2, 800 V IEC III/3, and cULus B/C 60 A at 600 V. Its catalog dimensions are 20.32 mm width, 18.7 mm length, 35.8 mm total height, 30.8 mm installed height, 5 mm solder-pin length, 1 × 0.9 mm pins, and **1.5 mm PCB holes**. The current page also specifies 0.5–16 mm² conductors, 10 mm strip length and 1.2–1.5 N·m tightening torque. This avoided the then-selected 1017526 page's 1.85/2.0 mm drilling conflict but did **not** establish fault-current withstand or a complete two-position land pattern.

I visually inspected the Phoenix-hosted [drilling plan](https://caas.phoenixcontact.com/caas/v1/stable/media/21262/full/b1500?format=jpg) and [dimensional drawing](https://caas.phoenixcontact.com/caas/v1/stable/media/42906/full/b1500?format=jpg) on that exact product page on 2026-09-24. Both illustrations show the **three-position family example**; the former depicts alternating top/bottom pairs, and the latter explicitly labels itself as the three-position version. The drilling view dimensions each within-potential pin pair at 4 mm, successive potential centers at 10.16 mm horizontally, and the stagger at 10.16 mm vertically. The side view puts one pin row 1.98 mm from the housing's rear face. The front view places the last pin 3.18 mm from the right housing edge. Truncating the family pattern to two positions yields this **review-only candidate**, with pad 1 as origin and X increasing across the terminals, Y increasing toward the wire-entry face:

| Proposed pad | Proposed potential | Nominal center (mm) | Basis |
| --- | --- | --- | --- |
| 1 | First / left screw position, proposed `VD_LOCAL` | `(0, 0)` | Phoenix first pin pair in the rear row |
| 2 | First / left screw position, proposed `VD_LOCAL` | `(4.00, 0)` | 4 mm pair separation |
| 3 | Second / right screw position, proposed `VB_BANK` | `(10.16, 10.16)` | 10.16 mm position pitch and stagger |
| 4 | Second / right screw position, proposed `VB_BANK` | `(14.16, 10.16)` | 4 mm pair separation |

The resulting nominal body rectangle, derived from the 20.32 × 18.7 mm catalog envelope and the family drawing's 3.18 mm right and 1.98 mm rear offsets, is `X = -2.98…17.34`, `Y = -1.98…16.72` mm. That extrapolation is a placement screen, not a tolerance-controlled two-position mechanical drawing. Phoenix does not publish numeric pad identifiers in these drawings. The left/right screw assignment, pair continuity, orientation relative to the board's viewing face, and final pad numbers need a sample continuity check or a Phoenix-controlled two-position ECAD/drawing before source substitution.

The unassigned [Phoenix_1709681_ReviewOnly footprint](../../libraries/temper.pretty/Phoenix_1709681_ReviewOnly.kicad_mod) implements those four candidate centers and the catalog's **1.5 mm nominal PCB hole**. Whether Phoenix intends that as a finished diameter must be checked before fabrication. Its **2.5 mm circular copper lands** (rectangular pad 1 for orientation) are an engineering choice, not a Phoenix land recommendation. Nominal annular ring is `(2.5 − 1.5)/2 = 0.50 mm`, above the project's [0.254 mm 2 oz fabrication floor](../../../../../docs/hardware/FAB_CAPABILITY.md); drill/registration tolerances and solder-joint/current capacity still need fabrication and thermal review. The 0.5 mm courtyard expansion excludes tool access, cable bend, strain relief and enclosure clearance. No 3D model has been verified. The footprint is deliberately named `ReviewOnly` and is **not assigned** in the selected source or native board.

On that candidate land pattern, the nearest opposite-potential pads are 2 and 3: center distance `sqrt(6.16² + 10.16²) = 11.882 mm`, nominal edge-to-edge copper gap **9.382 mm**, and nominal hole-edge gap **10.382 mm**. These are flat geometry checks only. Phoenix publishes 8 mm clearance / 10 mm creepage for its III/3 800 V component rating. A straight board-surface path between these candidate copper lands is **less than 10 mm**, so the footprint cannot claim that same creepage figure if it applies to the board construction. The molded terminal rating and hole spacing do not qualify solder fillets, adjacent copper, pollution environment or VD-to-VB fault voltage. The project's SELV isolation requirement is a separate boundary and must not be inferred from this HOT-to-HOT pair gap.

The 1709681 page names IEC 60947-7-4 short-time withstand and temperature-rise tests without a numeric fault pulse or DC result. Its 76 A nominal component rating and cULus 60 A table do not qualify the F2 discharge path, PCB copper, PTHs, solder joints, wire or holder at prospective fault current. The study did not revise the historical 1017526 source. It also does not qualify the current Würth stud assembly.

Validation receipt: `kicad-cli fp export svg --footprint Phoenix_1709681_ReviewOnly --layers F.Cu,F.SilkS,F.Fab,F.CrtYd` parsed and exported the library footprint on 2026-09-24. The exported SVG text contains one rectangular and three round copper pads at the expected relative centers. A visual review of the footprint render, physical sample fit, 3D collision check and board DRC remain **NOT RUN**. This receipt establishes syntax and pad placement only.

The same 2018 datasheet, page 8, records a **303 A AC** short-time withstand test with a **16 mm²** conductor under IEC 60947-7-4. It does not state the pulse duration or waveform there, and the result does not establish a DC fault-current rating for this board's solder joints, copper, or cable. Retain the fault envelope as an open qualification item.

## Current separate-stud source candidate

Two [Würth 74651173R REDCUBE THR studs](https://www.we-online.com/components/products/datasheet/74651173R.pdf),
one wholly on `VD_LOCAL` and one wholly on `VB_BANK`, are now joined in
`source-build-06`. They let the native board set the distance between F2
potentials independently. Würth marks the
part active and publishes a four-hole 5.87 mm square land pattern with
Ø1.85 mm holes and Ø3.2 mm lands. All four pins of one stud are the same
electrical potential. This removes the Phoenix 1017526 drill conflict and
cross-potential pad grouping for a **layout prototype**. The frozen export
and exact pin audit now cover two distinct source instances. Each stud has
four physical posts sharing logical pad 1 in the review-only footprint.

The stud's 50 A figure is at 20 °C and depends on the PCB, lug and cable.
Its data sheet does not supply an installed voltage/insulation approval or
DC fault-current pulse rating. Lug insulation, torque, restraint, exposed
metal spacing, solder/PTH/copper temperature, and F2 let-through remain
open. A review-only footprint alone cannot qualify the assembly. The
[stud footprint screen](WURTH-STUD-FOOTPRINT-SCREEN.md) records the candidate
land pattern and its remaining drill, torque and fault checks.

Phoenix [1333816](https://www.phoenixcontact.com/en-us/products/pcb-terminal-block-lpta-16-1-100-1333816)
offers a one-potential 76 A terminal with 600 V cULus and stated conditional
1500 V DC single-position use, but the available official record lacks a
complete dimensioned drilling pattern. Phoenix
[1735875](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-spt-16-2-v-100-zb-1735875?type=pdf)
has a six-hole drawing, but its pad-to-potential numbering is unresolved.
Neither was selected for the current source.

## Circuit and assembly boundary

The joined Atopile source contains `f2`, the two-contact off-board series
fuse, and separate `f2_vd_stud` and `f2_vb_stud` board instances. The first
joins `VD_LOCAL` and the second `VB_BANK`; neither short-circuits F2. The
Rust audit checks exact stud identity and distinct potential assignment.
`source-build-06` is the current frozen **296-reference** export of this
topology. The off-board F2 stays in the assembly schematic/BOM; a board-only
netlist may terminate at the two distinct stud potentials, but its evidence
must trace the external holder path back to the joined circuit. Putting
`temper:A70QS50_ETI_CH14_Prototype` clips on the board would contradict the
selected US141 holder.

Before promoting the current stud candidate, close these inputs:

1. Confirm Würth's four-post drill/land pattern, finished-hole and annular-ring tolerances, lug stack and M3 attachment against a controlled drawing and physical sample. Review stud-to-stud copper and exposed-metal clearance/creepage in the actual native board. The Phoenix drilling conflict is historical and does not set the Würth footprint.
2. Set the intended cable gauge, insulation, termination, restraint, enclosure routing and holder terminal details. Include both cable/contact resistance and inductance in the F2 capacitor-discharge and thermal analysis.
3. Establish the maximum continuous, pulsed and prospective fault current at this interface, then obtain a justifiable short-time withstand/temperature-rise basis for each stud, lug, PTH, solder joint, copper and cable. The Würth 50 A at 20 °C figure is not a DC fault envelope for the assembled interface.
4. Confirm the applicable voltage and insulation basis for the residential product and maximum open-F2 differential. The selected F2 fuse's DC clearing/let-through and minimum-breaking-current questions remain separately open under the [retained disposition](../DISPOSITION.md).

Until these are closed, retain the `Wurth_74651173R_ReviewOnly` footprint status in `pfc_power.ato`; do not silently use provisional PCB clips or claim a physical F2 interface PASS.
