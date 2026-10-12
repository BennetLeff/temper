# Controller → enclosure team: connector list and placement-critical parts (R27)

This is the electrical side of the R25 controller board. The enclosure team owns the outline, holes, landings and height envelope (CONTROLLER-SPEC R25). Nothing here is a layout; it states what a layout must keep. Coordinates are appliance world mm: board X−168…38, Y14…90, bottom at Z21, top copper at ≈ Z22.6, and the height limit Z40 leaves ≈ 17.4 mm above the board.

**R33 update (2026-10-10, enclosure R33 DECISIONS §3; R35 unchanged for the controller):** J5, J6 and J8 are deleted; one 12-way JST B12B-XH-A **J7** at X29.8–62.2, Y57.1–62.9 carries the UI bus to the fascia UI board (pin map below, DECISIONS C26). The module is the **ESP32-S3-WROOM-1U-N8** at X141–159, Y50–69.5 with its U.FL at (150, 67) and no antenna keep-out; nothing within 3 mm of the U.FL. The heights below are now from drawings (section "Height and cable exit").

**L3 coil NTC (2026-10-12, DECISIONS C32):** the coil sensor on J1 changes from the Vishay NTCALUG01A104GA lug (150 °C rating) to a **100 k / 300 °C glass NTC (Semitec 104GT-2 class)**, because the coil firmware trip is 165 °C and the hardware trip is 175.7 °C nominal. Its mount on the coil (high-temperature lug or bonded sleeve) needs the enclosure session's coil-NTC spec (R32/R36). J1's pin map is unchanged: 1 COIL_SENSE, 2 GND.

**L3 rim NTC (2026-10-10, DECISIONS C31):** the cartridge's rim sensor should be a **100 k / 300 °C glass NTC (Semitec 104GT-2 class)**, not a 10 k bead. The 10 k GT-2 part is rated only to 200 °C, and it gave 0.14 mV/K at 250 °C. Please fit the R36 rim boss for that bead.

**L3 update (2026-10-10, DECISIONS C28):** J10 now supplies the R32 blower at 5.5–12 V (adjustable, ≥ 1.5 A) with its FG tach on pin 3; same part and position. The blower buck's inductor is 6.0 mm tall (heights table).

**Stage 16 update (2026-10-12, DECISIONS C33):** the blower buck now runs from a separate chassis-mounted SELV supply **PS3** (Mean Well IRM-60-15ST at world (−139, 95), enclosure R41). It connects through the new **J13**, a JST B2P-VH 2-pos 3.96 mm top-entry header at body centre (88, 85.65), on the R41-approved spot (88, 86) at the rear edge with posts along X. The 8.5 mm-deep body (8.70 mm F.Fab outline) is pulled 0.35 mm forward so it does not overhang the edge. The harness is an 18 AWG twisted pair, about 450 mm, routed over the controller (R41). J13's 16.5 mm mated height (JST eVH p.1) uses R41's local allowance: "J13 local, Z ≤ 54 within ±6 mm of (88, 86)".

**R36 update (2026-10-10, DECISIONS C27):** the rim NTC adds **J12** (JST B2B-XH-A) for the 6-conductor cartridge cable. Its 4 RTD wires stay on J3 and the NTC pair goes to J12. J12's landing is **proposed** at (126, 86) on the rear edge, 13 mm left of J10; the enclosure must confirm or move it.

**R31 update (2026-10-09):** the enclosure re-posed native-21 by translation, so the whole controller layout is mirrored about X = 0: board X−38…168, J4 on the left edge mating −X, the WROOM at X−20…−2 behind the lens window, and J7 merged into a 4-pin J8 at (15, 41). The R31 coordinates are in `layout/world.py` (the layout's single parameter table) and DECISIONS C25; the coordinates in the tables below are the earlier R25–R28 ones.

**R30 update (2026-10-09):** the board now sits on six snap-in nylon supports in **Ø4.0** holes (same positions, Ø8 free of copper and parts) and is 2 mm higher: bottom Z23, top Z24.6, so ≈ 15.4 mm remain under Z40. The Z values below are R25's; add 2 mm. The layout (LAYOUT.md) implements R30; DECISIONS C24.

## Connector list (R25 landings)

| Ref | Part (LCSC) | Pins | Harness | Landing (face, X, Y, Z) | Pin map |
|---|---|---|---|---|---|
| J4 | Molex Micro-Fit 3.0 **43045-1600, 2×8 right-angle** THT with PCB pegs (C277731), mating +X | 16 | SELV_J4_to_controller, 1:1 to native-21 J4 (43025-1600 both ends) | right, 42.2, 42, 34 | 1 v15_selv, 2/4/15 selv_gnd, 3 v3v3 (out), 5–8 pwm_ha/la/hb/lb, 9 permit, 10 bus_fault, 11/12 vbus_p/n, 13 ct_zc, 14 ct_mon, 16 line_zc |
| J9 | JST B3B-XH-A(LF)(SN) (C144394) | 3 | probe_M12_to_controller | **right (R25 move), 39.2, 86, 35** | 1 probe sense (NTC to GND assumed), 2 GND, 3 shield/drain. **Probe type to confirm** |
| J10 | JST B3B-XH-A(LF)(SN) (C144394) | 3 | fan_to_controller (R32: Delta BFB1012VH-F00 blower, 3-wire; extension AWG22 at the XHP-3, 3 A per contact) | R31 centre (139, 86), unchanged | 1 V_BLOWER 5.5–12 V adjustable (1.42 A typ, 2.70 A max), 2 GND, 3 FG tach (blower red / black / blue). The blower has no PWM wire: speed is set by the supply voltage (DECISIONS C28) |
| J1 | JST B2B-XH-A(LF)(SN) (thermal-sense, unchanged) | 2 | NTC_coil_to_thermal_sense | top, −60, 88, 42.2 | 1 COIL_SENSE, 2 GND (polarity-free NTC) |
| J2 | JST B2B-XH-A(LF)(SN) (thermal-sense, unchanged) | 2 | NTC_sink_to_thermal_sense | top, 20, 88, 42.2 | 1 HS_SENSE, 2 GND |
| J3 | JST B4B-XH-A(LF)(SN) (RTD unit, unchanged) | 4 | pan_RTD_to_controller (SAB 4×AWG28, ≤ 500 mm) | rear, −165, 92, 34 | 1 FORCE+, 2 RTDIN+, 3 RTDIN−, 4 FORCE− |
| J7 | JST B12B-XH-A(LF)(SN) (C158027) | 12 | UI jumper to the fascia UI board (R33, 120 mm cut) | top, R33 body X29.8–62.2, Y57.1–62.9 | 1 +5 V (≤ 30 mA), 2 +3V3, 3 GND, 4 SCK, 5 GND, 6 MOSI, 7 MISO, 8 GND, 9 CS_OLED#, 10 OLED D/C, 11 GND, 12 CS_EXP# (DECISIONS C26) |
| J12 | JST B2B-XH-A(LF)(SN) (C158012) | 2 | sensor cartridge 6-conductor cable, rim NTC pair (R36) | top, **proposed** (126, 86) | 1 RIM_SENSE (NTC), 2 GND (NTC return) |
| J13 | JST B2P-VH(LF)(SN) (C20571196, per PLAN-16), top entry | 2 | PS3 → controller, 18 AWG twisted pair ≈ 450 mm, VHR-2N + SVH-21T-P1.1 at J13, ferrules at PS3 (stage 16) | top, body centre (88, 85.65) (R41: (88, 86)), posts along X | 1 V15_BLW (PS3 +V, 15 V, 2.72 A design), 2 return (PS3 −V; tied to selv_gnd here only) |
| J11 | Wurth 61300811121 1×8, 2.54 mm (C6400764) | 8 | none (bring-up only; may be left unfitted) | any accessible spot | 1 3V3, 2 GND, 3 TXD0, 4 n.c. (R33: GPIO44 is UI MISO), 5 EN, 6 IO0, 7 USB D−, 8 USB D+ |

## Landings vs mounting holes (R27)
R27 moved the rear holes to (−164, 80), (−75, 86) and (30, 80), and R28 moved the right-rear one to (26, 74); the front holes stay at (−164, 18), (−65, 18) and (34, 18). `tools/controller_calcs.py` `landings()` re-checks every landing with the worst-orientation bound (hole keepout radius 4 mm plus half the connector's longest body dimension):
- **All clear except J3, which is tight.** J3 (pan RTD) is 10.05 mm from (−164, 80), against a 10.2 mm worst-orientation bound.
- **J3 with an edge-aligned body:**
  - Lay the 12.4 × 5.75 mm XH body along the rear edge, centred no further left than X ≈ −161.8 so it stays on the board, which ends at X−168.
  - Its near side is then about 4.25 mm from the hole, clearing the 4 mm keepout by about 0.25 mm.
  - Layout must keep that orientation, or shift J3 a few mm to +X.

## Height and cable exit
Heights above the board's top surface (bottom Z23, top Z24.6 since R30; Z40 leaves 15.4 mm).

| Part | Height | Source |
|---|---|---|
| J1–J3, J7, J9, J10 JST XH header (B2B/B3B/B4B/B12B-XH-A) | 7.0 mm body; **9.8 mm mated** with the XHP housing (before the cable bend) | JST eXH.pdf (catalogue dated 2025-07-29): header drawing "7" above the board, "assembled board height of 9.8 mm" (p. 1) and assembly layout (9.8) (p. 2) |
| J4 Molex 43045-1600 right-angle + mated 43025-1600 | **10.29 mm mated** above the board | Molex part data for 43045-2001 (same right-angle THT snap-in-peg 43045 series, 20 circuits), "Mated Height 10.29mm" (Molex product sheet, generated 2026-03-06, farnell.com/datasheets/4740236.pdf). The 43045-1600 sales drawing itself (430451600_sd.pdf) could not be fetched (molex.com refuses this network), so the 16-circuit figure is by series, and the plug's −X overhang (R31: to X−50) is still unread |
| J11 Würth 61300811121 (bring-up only) | 8.54 mm (pin tips; 11.54 pin − 3.0 tail); a mated 2.54 mm socket adds its own height | Würth WR-PHD 61300811121 datasheet rev 003.000 (2023-01-08) |
| J13 JST B2P-VH (stage 16) | **16.5 mm mounting height** (mated, before the 18 AWG bend); body 7.86 × 8.5 mm | JST eVH.pdf p.1 and p.3; above the 15.4 mm board-wide allowance, inside R41's local allowance (Z ≤ 54 within ±6 mm of (88, 86)) |
| C1, C9 EEE-FK1E101P | 6.2 mm | Panasonic FK series, 8 × 6.2 |
| L1 SWPA6045 | 4.5 mm | Sunlord SWPA6045 |
| L2 SWRB1205S-100MT (L3 blower buck) | 6.0 mm max | Sunlord SWRB-S datasheet rev 2017/04/15 |
| U4 ESP32-S3-WROOM-1U-N8 | 3.2 ± 0.15 mm module; the U.FL plug adds ≤ 2.5 mm above its receptacle | Espressif WROOM-1/-1U DS v1.8 §10.1 |

- **Mounting holes:** the six Ø3.2 holes and Ø8 keepouts are honoured by layout, with no parts inside them.

## Placement-critical parts (layout must keep)
1. **Interlock region** (CONTROLLER-SPEC: own region, own decoupling, short traces to J4, no MCU traces through it).
   - **Parts:** U20 latch (LVC1G74), U21 TPS3823, U22 HC30, U23/U24 LVC14, U25 LVC1G08, U37 PERMIT gate (LVC1G08, latch AND RUN_EN, C23) and their pull-ups and bypasses. Next to them sit the trip glue: U3 TPS3703, U10 runaway TLV3201, U11 SENSOR_LIVE AND, U12 RAIL_FAULT inverter, and the 0 Ω OVP tie.
   - **Placement:** close to J4, on the J4 side of the board.
   - **Routing:** PERMIT (J4.9) and bus_fault (J4.10) go straight to the latch and inverter with no vias through the MCU region. U9 (LVC244 read-back buffer) sits on the region's boundary, and its outputs are the only interlock-to-MCU nets.
2. **J4 and the star ground.** selv_gnd stars at J4 pins 2, 4 and 15; the 15 V return current (≈ 0.85 A peak) must not flow through the analog or interlock grounds.
3. **D-11 bus receiver U5 (OPA2388), U13 LM4040 and their 0.1 % resistors.** D-11 places these at the receiving connector, so put them right at J4.11/12. Route vbus_p/vbus_n as a tight pair, without large capacitors on them.
4. **ct_mon buffer U6 at J4.14.** The ct_zc/line_zc 1 kΩ series resistors also belong at J4.
5. **Thermal-sense block** (comparators, references, and J1/J2 at the top landings in the cool front zone).
   - HS_SENSE/COIL_SENSE are high-impedance nodes with a ±1 µA budget: guard them, and keep them away from the ESP32 antenna and both buck switch nodes.
   - Buffers U6B/U7A sit beside the block.
6. **RTD front end** (MAX31865 U30, REF2025, window comparators, TPS389001; footprints from `zapote/rtd/unit/candidate` Temper_RTD library).
   - Place it near J3 at the rear left, with short sense leads, away from the fan buck (U2/L2), which is also at the rear left near J10.
   - Leave at least 10 mm between L2 and the RTD analog section.
7. **Bucks U1/L1 (3.3 V) and U2/L2 (12 V).**
   - Keep the hot loops compact (input capacitor, IC, GND) and the switch nodes small.
   - Keep them away from the thermal-sense and RTD analog nodes and from the antenna.
   - The 12 V buck near J10 shortens the 0.63 A path.
   - Each buck dissipates on the order of 0.5–1 W in total. Keep them out from under the OLED and buttons.
8. **ESP32-S3-WROOM-1U-N8** (R33).
   - At X141–159, Y50–69.5 with its U.FL at (150, 67); the 150 mm coax goes to the off-board chip-antenna board, so there is no on-board antenna keep-out.
   - Nothing taller than the plug within 3 mm of the U.FL (the layout keeps the 3 mm circle free of other parts).
   - **Wi-Fi: unqualified** (enclosure tests E4 and T4).
   - The EN RC and the 22 µF/100 nF decoupling go at the module.
9. **M12 probe J9.** Its TVS D1 goes at the connector pin, with a short return to selv_gnd. The probe lead is user-accessible, so ESD current must not cross the analog ground.
10. **PWM.** The 33 Ω series resistors go at the MCU and the 10 kΩ pull-downs at J4.
11. **Tank-RMS channel** (U14 AD8436, U15 MCP3202, D2 BAT54S).
    - Put U14 beside the ct_mon buffer U6 near J4.14, and keep its CAVG/coupling C0G capacitors tight to its pins.
    - It runs from v15, so keep its output buffer → 1 kΩ → clamp → U15 CH0 path short, with the clamp at U15.
    - U15 sits on the RTD SPI bus. Place it between the MCU and the RTD front end, not inside the RTD analog area.
12. **J7 UI bus (R33).** The six 100 Ω series resistors and the two SRV05-4 arrays go at J7; the CS pull-ups at the module. The 5 V LDO U16 and its 2 × 100 Ω droppers (≈ 0.12 W each) go near J7, away from the thermal-sense nodes.
