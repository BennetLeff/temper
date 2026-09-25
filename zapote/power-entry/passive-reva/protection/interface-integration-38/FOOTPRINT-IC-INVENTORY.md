# Rev38 small-package footprint inventory

**Historical 2026-09-23 package pass.** The later `source-build-06`
replaces the DW `ISO7742FDWR` row below with DWW
`ISO6742FQDWWRQ1` and also selects DWW `ISO7741FQDWWRQ1`; their joined
review-only footprints and remaining insulation gates are recorded in
`INSULATION-BASIS.md`. The historical exact selected MPN, top-view pin numbers, body and pad count
were compared with manufacturer data and installed KiCad 10 standard
footprints. The 12 source component declarations below now use a real
footprint. Because some modules repeat, joined `TBD_REVIEW_ONLY` netlist
occurrences fell from **48 to 23**. This is a package assignment, not native
PCB placement, assembly or isolation acceptance.

| MPN and verified package/pins | Installed KiCad footprint | Source declarations |
| --- | --- | ---: |
| `SN74HCS04PWR`, `SN74HCS21PWR`, `SN74HCS00PWR`: TI PW TSSOP-14, 0.65 mm pitch; pins 1–14 with no exposed pad | `Package_SO:TSSOP-14_4.4x5mm_P0.65mm` | 3 |
| `ISO7742FDWR`: TI DW SOIC-16W, 7.5 × 10.3 mm, 1.27 mm pitch; pins 1–16 with no exposed pad | `Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm` | 1 |
| `TPS389001DSER`: TI DSE WSON-6, 1.5 × 1.5 mm, 0.5 mm pitch; six numbered lands, no exposed pad | `Package_SON:WSON-6_1.5x1.5mm_P0.5mm` | 1 |
| `SN74LVC1G06DBVR`, `SN74LVC1G08DBVR`: TI DBV SOT-23-5; pins 1–5 with no exposed pad | `Package_TO_SOT_SMD:SOT-23-5` | 2 |
| `LM4040A25IDBZR`, `BAV23C-E3-08`, `AO3400A`: SOT-23; pins 1–3 with no exposed pad | `Package_TO_SOT_SMD:SOT-23` | 4 |
| `UCC28180D`: TI D SOIC-8, 3.9 × 4.9 mm, 1.27 mm pitch; pins 1–8 with no exposed pad | `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm` | 1 |

All six footprint files exist in the installed KiCad library. Their pad
numbers, pitch and body dimensions match the manufacturer package drawings.
The electrical pin map in each `.ato` component was also checked: HCS logic
and ISO7742 against the TI pin tables; TPS3890 SENSE=1/GND=2/MR=3/VDD=4/
CT=5/RESET=6; LVC1G06 NC=1/A=2/GND=3/Y=4/VCC=5; LVC1G08
A=1/B=2/GND=3/Y=4/VCC=5; LM4040 K=1/A=2/NC=3; BAV23C anodes=1,2 and
common cathode=3; AO3400A G=1/S=2/D=3; UCC28180 GND=1 through GATE=8.

The primary package and pin references are [TI HCS04](https://www.ti.com/lit/ds/symlink/sn74hcs04.pdf),
[HCS21](https://www.ti.com/lit/ds/symlink/sn74hcs21.pdf),
[HCS00](https://www.ti.com/lit/ds/symlink/sn74hcs00.pdf),
[ISO7742](https://www.ti.com/lit/ds/symlink/iso7742.pdf),
[TPS3890](https://www.ti.com/lit/ds/symlink/tps3890.pdf),
[LVC1G06](https://www.ti.com/lit/ds/symlink/sn74lvc1g06.pdf),
[LVC1G08](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf),
[LM4040](https://www.ti.com/lit/ds/symlink/lm4040.pdf),
[UCC28180](https://www.ti.com/lit/ds/symlink/ucc28180.pdf),
[Vishay BAV23C](https://www.vishay.com/docs/86374/bav23c.pdf), and
[AOS AO3400A](https://www.aosmd.com/sites/default/files/res/datasheets/AO3400A.pdf).

At the time of this pass, `TPS3431SDRBR` retained
`TBD_REVIEW_ONLY:TPS3431SDRBR_DRB0008A`. The
[TI DRB0008A drawing](https://www.ti.com/lit/ds/symlink/tps3431.pdf)
requires a 1.5 × 1.75 mm exposed thermal pad (pin 9, connected to GND).
The installed generic 3 × 3 mm VSON footprints use different exposed-pad
dimensions, so none is an exact match. It needs a reviewed native footprint.

Atopile 0.2.69 may alias different MPNs when they share the same footprint;
the generated CSV BOM carries the per-reference part identity. All eleven
unique selected MPNs above were present in that pass's joined CSV BOM. Joined
connectivity still comes from the netlist. The native review must also
verify current DWW barrier spacing, solder lands, thermal behavior, and physical
pin-1 orientation. Power, mains, magnetics, fuse, connector and other
special-package placeholders were outside this pass.
