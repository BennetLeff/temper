# Power-stage footprint check

Checked against the cited manufacturer drawings on 2026-09-25 and parsed/exported
with KiCad 10.0.4. Coordinates and dimensions below are in millimetres, in each
footprint's local frame. `VERIFIED` covers the component envelope, terminal
dimensions and pin order; it is not a board-level insulation or assembly approval.

| ID | Unit library file; SHA-256 | Manufacturer source | Implemented geometry and pads | Verdict |
| --- | --- | --- | --- | --- |
| F1 | `temper.pretty/CDE_942C_D19.0_L34.0_Axial_ReviewOnly.kicad_mod`<br>`587e95529a9d370383f4ed43185803496c23f72418c8deeb04ab0a1a379a5473` | [CDE Type 942C catalog](https://www.cde.com/resources/catalogs/942C.pdf), 942C12P1K-F rating table p. 3 and axial drawing p. 1 | Body Ø19 × 34, lead Ø1.0; pads 1 `(0,0)`, 2 `(42.5,0)`, Ø3.0 / drill Ø1.4; horizontal body. | **PROVISIONAL:** body/lead dimensions match drawing; 42.5 formed pitch is an assembly choice. CDE gives 41 mm minimum straight lead each side but no minimum bend distance. Validate bend, stress relief and adhesive/strap attachment with a sample. Non-polar. |
| F2 | `temper.pretty/CDE_942C_D26.5_L34.0_Axial_ReviewOnly.kicad_mod`<br>`bad1891a78d5c7f934f13cc8dea511810fba739c3f4882d5516a1f4ef01ff06c` | [CDE Type 942C catalog](https://www.cde.com/resources/catalogs/942C.pdf), 942C12P22K-F rating table p. 3 and axial drawing p. 1 | Body Ø26.5 × 34, lead Ø1.2; pads 1 `(0,0)`, 2 `(42.5,0)`, Ø3.2 / drill Ø1.6. | **PROVISIONAL:** formed pitch and heavy-part restraint need physical validation; body/lead dimensions verified. Non-polar. |
| F3 | `temper.pretty/CDE_942C_D32.0_L54.0_Axial_ReviewOnly.kicad_mod`<br>`ec86412a8bb80b19fb968d526cc7712f3f30a7b91e83785971dae8d006605367` | [CDE Type 942C catalog](https://www.cde.com/resources/catalogs/942C.pdf), 942C6W2P5K-F rating table p. 2 and axial drawing p. 1 | Body Ø32 × 54, lead Ø1.2; pads 1 `(0,0)`, 2 `(62.5,0)`, Ø3.2 / drill Ø1.6. | **PROVISIONAL:** formed pitch and heavy-part restraint need physical validation; body/lead dimensions verified. Non-polar. |
| F4 | `temper.pretty/TMOV20RP_ReviewOnly.kicad_mod`<br>`6d8ff131617aa7aacd71dd52a05d03b33366496b25b463a865371dc3b0a33eda` | [Littelfuse TMOV/iTMOV datasheet](https://www.littelfuse.com/assetdocs/tmov-itmov?assetguid=bd475732-1071-4352-b8aa-f78b0007eb05), rev GD, 2025-10-15, pp. 6, 8, 20 mm two-lead E bulk-pack drawing and RP part table | Disc Fab Ø23, thickness max 9; seated height max 28; pads 1 `(0,0)`, 2 `(7.5,0)`, Ø2.4 / drill Ø1.2; courtyard Ø24. | **PROVISIONAL:** 7.5 pitch and two leads verified, but bulk leads are offset `e1=1.5–4.0`; form lead 2 into line and check assembled fit. |
| F5 | `temper.pretty/B82726S2_ReviewOnly.kicad_mod`<br>`e8c7a8faa69dc90b0ade3ec0eb3930abf7295bcf4a77f93696ca69d01f592d67` | [TDK B82726S22*3A020 datasheet](https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s22x3.pdf), May 2026, pp. 2–3, dimensional drawing and pin configuration | Body Fab 45 × 26, pins Ø2±0.1; pads 1 `(0,0)`, 2 `(10,0)`, 3 `(10,25)`, 4 `(0,25)`, Ø4 / drill Ø2.5; winding pairs **1–4** and **2–3**. | **VERIFIED:** drawing and source pin map agree. Body Fab width 26 covers the drawing's 25 mm maximum and TDK listing's 25.5 mm maximum. Internal clearance ≥2.5 and creepage ≥3; keep unrelated copper out from between pins. |
| F6 | `temper.pretty/Diode_Bridge_GBJ2510.kicad_mod`<br>`a4ef38e48747d09cefd6e964686dd5b2c88c4a91127031952a20d3eb23543c5c` | [Diodes Inc. GBJ2510 datasheet](https://www.diodes.com/datasheet/download/GBJ2510.pdf), DS21221 rev 11-2, May 2025, p. 4 package drawing | Pads 1 `(0,0)` `+`, 2 `(10,0)` `~`, 3 `(17.5,0)` `~`, 4 `(25,0)` `−`; all Ø4 / drill Ø1.6. | **VERIFIED:** drawing and source `BridgeGbj2510` pin map agree. Byte-identical to `archive/rev38-power-entry-2026-09-25:zapote/power-entry/passive-reva/libraries/Diode_THT.pretty/Diode_Bridge_GBJ2510.kicad_mod` (same hash). |
| F7 | `temper.pretty/CST3015.kicad_mod`<br>`3c79ad69b9d37b4252ef7affa7774dcd55d613ce957b110e455523168ddb3621` | [Coilcraft CST3015 datasheet](https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf), document 1608-2, revised 2025-09-08, p. 2 recommended land pattern; corrected donor `zapote/current-sense/candidate/candidate-libs/temper.pretty/CST3015_Datasheet2025.kicad_mod` | Pads 1 `(5.58,-11.55)` / 2 `(-5.58,-11.55)`, 4.8×9.0; pads 3 `(-6.88,13.75)` / 4 `(6.88,13.75)`, 3.0×4.6. Primary horizontal inner gap 6.36; secondary 10.76; primary-to-secondary vertical copper-edge gap **18.5**. | **VERIFIED:** drawing visually checked independently by coordinator and two Sol reviewers. The 18.5 dimension is an edge gap, not a row-center pitch. PCB geometry does not increase the package's published ≥8 mm insulation guarantee. |
| F8 | `lib.pretty/SOIC16W_Isolated.kicad_mod`<br>`9e7dde8e635f41eb35de9cc01ab03629dcabc80b5e3edce53098ced058baa2a3` | [TI UCC21550 datasheet](https://www.ti.com/lit/ds/symlink/ucc21550.pdf), SLUSE89C revised August 2024, p. 50 DWK0014A HV/isolation land pattern; donor `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod` | 14 SMD pads (1–11, 14–16), 1.65×0.6, x=±4.875, y on 1.27 pitch; nearest opposite copper edges 8.10 apart. | **VERIFIED:** byte-identical to donor (same hash); donor's stated HV land geometry matches the TI drawing. Board-level insulation still requires Part 4 review. |
| F9 | `lib.pretty/SOIC16W_DW0016B_HV.kicad_mod`<br>`0122bebb19f2a697a3ee831907d6d402e7e27cb63b13b483b7a1b176db4091b0` | [TI ISO7710 datasheet](https://www.ti.com/lit/ds/symlink/iso7710.pdf), SLLSER9E revised December 2024, p. 33, DW0016B land pattern (drawing 4221009/B), "HV / ISOLATION OPTION" | 16 SMD pads 1.65×0.6, x=±4.875, y on 1.27 pitch; nearest opposite copper edges 8.10 apart. Derived from F8 with pads 12 and 13 restored. | **VERIFIED:** TI states 8.1 mm clearance/creepage for this option vs 7.3 mm for IPC-7351 nominal. Used by U9 ISO7710DWR (previously the stock KiCad SOIC-16W, 7.25 mm). |

The current Littelfuse drawing gives `A=21–28 mm` and `D=18–23 mm` for this
row; Part 2's older minima were 23 and 19 mm. Its maxima, lead count,
diameter, and 6.5–8.5 mm spacing still support this footprint. The plan also
described TDK body width as 25 mm maximum; TDK's product listing says 25.5 mm
maximum, which the 26 mm Fab width accommodates.

The CDE footprint pitch leaves 4.25 mm from nominal body end to hole centre
at each end. The catalog's 41 mm straight lead minimum is supply length, not
a bend-clearance requirement; check formed samples. These heavy capacitors
require adhesive or a strap in the final mechanical design. The TMOV's offset
lead also requires a formed-sample check before fabrication.

The initial F7 copy from `pcb/libs` had incorrect geometry: its primary
pad dimensions were transposed and its rows gave only 9.1 mm copper gap.
Removing invalid comment lines made it parse but did not fix the dimensions.
The final unit copy instead uses the corrected current-sense land pattern,
with only the footprint identifier changed to `CST3015` so the source library
reference remains valid. The coordinator read the actual manufacturer drawing,
including pin numbers, before accepting this replacement. Both donor files
remain unchanged. F8 is byte-for-byte identical to its donor.

`kicad-cli fp upgrade --output /tmp/ps-fpcheck-temper` and the same command
for `lib.pretty` parsed both libraries. `kicad-cli fp export svg` exported all
eight footprints; the five authored outlines, silk, marker and pad positions
were visually inspected from rendered SVGs. The final corrected library also passes native vendoring and raw-pad source
parity; see `NATIVE-01.md`.
