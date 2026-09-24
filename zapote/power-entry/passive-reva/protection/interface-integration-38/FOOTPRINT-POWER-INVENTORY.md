# Rev38 power and interface footprint inventory

2026-09-23. Twelve selected component declarations gained exact-name repo or
installed KiCad 10 footprints. The joined Atopile CSV BOM has **11 physical
`TBD_REVIEW_ONLY` references** after this pass, down from 23 after the passive
and small IC passes (127 before those passes). These assignments establish
package and electrical pad correspondence; they do not establish placement,
creepage, thermal capacity, assembly clearance, or a releasable PCB.

| Selected MPN | Assigned footprint | Pad and dimensional basis | Native review still needed |
| --- | --- | --- | --- |
| Phoenix Contact `1714984` | `temper:Phoenix_1714984` | Repo land pattern for the 3-position MKDS 5/3-9,5 has pads 1–3 at 9.52 mm pitch and 1.3 mm drills, matching the source terminal map. [Manufacturer product](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-mkds-5-3-95-1714984). | Fused inlet harness, PE termination, solder-joint and fault-current qualification. |
| Phoenix Contact `1714971` | `temper:Phoenix_1714971` | Repo 2-position MKDS pattern has pads 1–2 at 9.52 mm pitch and 1.3 mm drills; source sends and returns the external AUX fuse through separate pins. | External fuse holder and wire routing cannot be replaced with a copper bypass. |
| TDK `B82726S2163N030` | `temper:CMC_B82726S` | Repo pattern uses manufacturer pins 1/2 at 18 mm pitch and 4/3 at 38 mm pitch, with 23 mm row spacing. The source connects windings as 1–4 and 2–3. [TDK drawing](https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s2163.pdf). | Choke body, heat and mains separation on the joined board. |
| Ametherm `SL32 10015` | `temper:SL32_10015` | Repo pattern has two 1.0 mm holes at 7.8 mm pitch and source pins 1–2. | Inrush/steady thermal and lead-form qualification. |
| TE `RT33K012` | `temper:Relay_SPST_Schrack-RT33K012` | Repo pattern has coil pads 1/2 and duplicated contact pads 3/4, matching source NO=3 and COM=4; its geometry derives from the KiCad RT1 16 A Form A pattern. [TE part and datasheet](https://www.te.com/en/product-2-1393240-3.html). | Relay contact/coil separation, copper and relay-drop resistor heat in the actual placement. |
| TDK `B32922C3224M289` X2 | `Capacitor_THT:C_Rect_L18.0mm_W7.0mm_P15.00mm_FKS3_FKP3` | Installed two-pad pattern matches the [manufacturer's 18 × 7 mm maximum body and 15 mm lead pitch](https://product.tdk.com/en/search/capacitor/film/emi-suppression/info?part_no=B32922C3224M289). | Confirm lead diameter, hole and insertion/assembly allowance. |
| Vishay `VY1102M31Y5UQ63V0` Y1 | `Capacitor_THT:C_Disc_Vishay_VY1102M31Y5UQ63V0` | Repo exact-MPN two-pad pattern has 10 mm pitch and 1.2 mm drills. | Safety barrier creepage and lead/body clearance in the finished board. |
| Vishay `SS14` | `Diode_SMD:D_SMA` | Installed two-pad SMA pattern assigns cathode pad 1 and anode pad 2, as the source does. | Relay-coil pulse and thermal verification. |
| Wolfspeed `C3D20065D` | `Package_TO_SOT_THT:TO-247-3_Vertical` | Installed pads 1–3 at 5.45 mm pitch match the [5.44 mm package drawing](https://assets.wolfspeed.com/uploads/2023/12/Wolfspeed_C3D20065D_data_sheet.pdf): 1/A1, 2/K, 3/A2. The metal tab is cathode pin 4 but has no PCB pad. | Cathode tab, heatsink, torque, thermal path and insulation spacing. |
| TDK `B32672P6474K000` | `temper:B32672P6474K000` | Repo exact-MPN pattern has two pads at the specified 15 mm lead pitch and the 18 × 8 mm body outline. | Film-cap heat and local reservoir spacing. |
| Espressif `ESP32-S3-WROOM-1-N8R8` | `RF_Module:ESP32-S3-WROOM-1` | Installed pattern has perimeter pads 1–40 and thermal/ground pad 41; all match the source module pad declaration and [Espressif module land pattern](https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf). | Use WROOM-1 antenna keepout, not WROOM-1U; verify final module orientation and variant. |
| Stackpole `HCSM2818FT10L0` | `temper:HCSM2818FT10L0` | Repo exact-MPN two-pad shunt pattern carries the manufacturer land geometry (3.5/5.3/0.6 mm), source pins 1–2. | 5 W rating depends on copper area and surface temperature; current-sense Kelvin routing and thermal test remain open. |

The ESP row applies to the frozen `cooker-source-02` derivative: its staged
component and ground joins include pads 40/41. The tracked canonical cooker
source and its local 1–39-pad footprint remain unchanged, so this row does
not qualify the canonical board.

The **11 remaining physical placeholders** in `build/integrated.csv` are two
TPS3431 watchdog instances plus UCC27624, its gate resistor, F2, the local
22 µF reservoir, MOV, relay-drop resistor, both XGL6060 inductors, and the
TCA6408A-Q1 expander. Their reasons differ:

* `B32776P6226K000` has a four-lead repo footprint (pads 1/4 one electrode,
  2/3 the other) but the Rev38 source has only pins 1/2. Assigning that
  footprint would leave two physical leads without a net.
* F2 is specified as an off-board fuse/holder assembly; the repo's ETI clip
  footprint describes a provisional board-mounted arrangement and is not
  interchangeable with that assembly.
* The installed 15.5 mm MOV pattern underestimates the selected
  `V150LA10AP` [17 mm maximum disc width](https://www.littelfuse.com/assetdocs/littelfuse-varistor-la-datasheet?assetguid=f7c547ce-c2fa-4789-86cc-ec39a5060afb).
  The same drawing gives 20 mm maximum vertical height, not disc diameter.
* Both XGL6060 inductors need one reviewed two-pad pattern from the
  [Coilcraft package drawing](https://www.coilcraft.com/getmedia/329fe97c-7311-4726-9bf3-37718f42b168/xgl6060.pdf).
* TPS3431 needs its specified exposed-pad geometry; UCC27624 and TCA6408A
  need exact package/pin review; the gate and relay-drop resistors retain
  pulse or thermal questions. No placeholder was changed solely to improve
  the count.

Atopile 0.2.69 can alias parts that share a footprint in its netlist; the
generated CSV BOM is the source for per-reference MPN identity. A native
export must vendor the named repo footprint files and verify pin-to-pad
parity, rather than treating this Atopile build as native PCB evidence.

## Subsequent XGL6060 package resolution

Both `XGL6060-183MEC` and `XGL6060-153MEC` now use the same
`temper:L_Coilcraft_XGL6060-XXX` footprint. The source YAML/CSV is under
`libraries/footprint-sources/`; KiCad Library Tools `inductor/SMD` generated
the footprint from Coilcraft's XGL6060 drawing. It has pads 1 and 2, each
1.43 × 5.50 mm, at X = −2.02 and +2.02 mm. Its 6.51 × 6.71 mm body and
7.02 × 7.22 mm courtyard were checked against the drawing, and `kicad-cli
fp export svg` parsed and rendered the local footprint successfully. The
generator's dangling 3D-model reference was removed because no model was
produced. Native placement still needs switch-loop and thermal review.

After rebuilding both supply stages and `integrated`, the joined BOM has
**9 remaining physical placeholder references**: two TPS3431s, UCC27624,
its gate resistor, F2, B32776 local reservoir, MOV, relay-drop resistor,
and TCA6408A-Q1. The preceding 11-count is the end of the earlier power
footprint pass.

## Final package-screen count

`SMALL-PACKAGE-CLOSEOUT.md` assigns the exact TPS3431 and UCC27624 exposed-pad
packages, TCA6408A-Q1, and a 1206 hand-solder gate-resistor land. The
`F2-CAP-PACKAGE-DECISION.md` four-lead capacitor correction and
`MAINS-PACKAGE-CLOSEOUT.md` MOV/resistor decisions complete the other board
mounted references. The latest integrated BOM has **one** physical
placeholder: off-board F2 `U226`. The earlier 11 and 9 counts above are
dated intermediate pass results.
