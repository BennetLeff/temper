# Controller → enclosure team: connector list and placement-critical parts (R27)

This is the electrical side of the R25 controller board. The enclosure team owns the outline, holes, landings and height envelope (CONTROLLER-SPEC R25). Nothing here is a layout; it states what a layout must keep. Coordinates are appliance world mm: board X−168…38, Y14…90, bottom at Z21, top copper at ≈ Z22.6, and the height limit Z40 leaves ≈ 17.4 mm above the board.

## Connector list (R25 landings)

| Ref | Part (LCSC) | Pins | Harness | Landing (face, X, Y, Z) | Pin map |
|---|---|---|---|---|---|
| J4 | Molex Micro-Fit 3.0 **43045-1600, 2×8 right-angle** THT with PCB pegs (C277731), mating +X | 16 | SELV_J4_to_controller, 1:1 to native-21 J4 (43025-1600 both ends) | right, 42.2, 42, 34 | 1 v15_selv, 2/4/15 selv_gnd, 3 v3v3 (out), 5–8 pwm_ha/la/hb/lb, 9 permit, 10 bus_fault, 11/12 vbus_p/n, 13 ct_zc, 14 ct_mon, 16 line_zc |
| J5 | TE Micro-MaTch 7-215079-6, female-on-board 2×3 (C306122) | 6 | UI_controller_to_encoder: Grayhill factory cable plus extension, mates 7-215083-6 | **right (R25 move), 42.2, 64, 36** | 1 +3.3 V, 2 GND, 3 A, 4 B, 5 switch, 6 **+5 V** (current-limited). The extension harness wires the encoder to pin 1 or pin 6 to suit its supply; all signal inputs accept 5 V. **Encoder pin map to confirm** |
| J6 | JST B8B-XH-A(LF)(SN) (C157972) | 8 | UI_controller_to_OLED | top, −35, 70, 42.2 | 1 +3V3, 2 GND, 3 SCLK, 4 SDIN, 5 CS#, 6 D/C, 7 RES#, 8 GND. At the OLED end the harness ties BS1, BS0, R/W, E and D3–D7 to VSS (4-wire SPI) |
| J7 | JST B3B-XH-A(LF)(SN) (C144394) | 3 | UI_controller_to_buttons, landing 1 | top, −90, 41, 42.2 | 1 BTN1, 2 BTN2, 3 GND (switch closes to GND) |
| J8 | JST B2B-XH-A(LF)(SN) (C158012) | 2 | UI_controller_to_buttons, landing 2 | top, 5, 41, 42.2 | 1 BTN3, 2 GND |
| J9 | JST B3B-XH-A(LF)(SN) (C144394) | 3 | probe_M12_to_controller | **right (R25 move), 39.2, 86, 35** | 1 probe sense (NTC to GND assumed), 2 GND, 3 shield/drain. **Probe type to confirm** |
| J10 | JST B3B-XH-A(LF)(SN) (C144394) | 3 | fan_to_controller (Delta PFB0612EHE-F00, 3-wire) | **rear (R25 move), −155, 91.3, 30** | 1 +12 V, 2 GND, 3 tach |
| J1 | JST B2B-XH-A(LF)(SN) (thermal-sense, unchanged) | 2 | NTC_coil_to_thermal_sense | top, −60, 88, 42.2 | 1 COIL_SENSE, 2 GND (polarity-free NTC) |
| J2 | JST B2B-XH-A(LF)(SN) (thermal-sense, unchanged) | 2 | NTC_sink_to_thermal_sense | top, 20, 88, 42.2 | 1 HS_SENSE, 2 GND |
| J3 | JST B4B-XH-A(LF)(SN) (RTD unit, unchanged) | 4 | pan_RTD_to_controller (SAB 4×AWG28, ≤ 500 mm) | rear, −165, 92, 34 | 1 FORCE+, 2 RTDIN+, 3 RTDIN−, 4 FORCE− |
| J11 | Wurth 61300811121 1×8, 2.54 mm (C6400764) | 8 | none (bring-up only; may be left unfitted) | any accessible spot | 1 3V3, 2 GND, 3 TXD0, 4 RXD0, 5 EN, 6 IO0, 7 USB D−, 8 USB D+ |

## Landings vs mounting holes (R27)
R27 moved the rear holes to (−164, 80), (−75, 86) and (30, 80), and R28 moved the right-rear one to (26, 74); the front holes stay at (−164, 18), (−65, 18) and (34, 18). `tools/controller_calcs.py` `landings()` re-checks every landing with the worst-orientation bound (hole keepout radius 4 mm plus half the connector's longest body dimension):
- **All clear except J3, which is tight.** J3 (pan RTD) is 10.05 mm from (−164, 80), against a 10.2 mm worst-orientation bound.
- **J3 with an edge-aligned body:**
  - Lay the 12.4 × 5.75 mm XH body along the rear edge, centred no further left than X ≈ −161.8 so it stays on the board, which ends at X−168.
  - Its near side is then about 4.25 mm from the hole, clearing the 4 mm keepout by about 0.25 mm.
  - Layout must keep that orientation, or shift J3 a few mm to +X.

## Height and cable exit
- **J4 (resolved in part).** Now the right-angle 43045-1600, mating +X at the right edge near Y42, per R27. The header, mated plug and lead bend must stay within X38–63, Y32–52, Z ≤ 40, with the plug body above Z30 beyond X50. I could not fetch Molex's drawing (430450201_sd), so header height and plug overhang against that envelope are **[UNVERIFIED]**; check them before layout.
- **Tallest other parts:**
  - JST XH headers: 7.0 mm body plus the mated housing;
  - C1 EEE-FK1E101P: 6.2 mm;
  - J11 pin header: its stack height is not taken from a drawing here; it is a bring-up part and can be left unfitted;
  - L1/L2 SWPA6045: 4.5 mm;
  - ESP32-S3-WROOM-1: 3.1 ± 0.15 mm (DS §10.1).

  The board parts sit well under the 17.4 mm allowance. The mated heights of J4 (above) and the XH plugs with their cable bends are not taken from drawings here; confirm them with the harness.
- **Mounting holes:** the six Ø3.2 holes and Ø8 keepouts are honoured by layout, with no parts inside them.

## Placement-critical parts (layout must keep)
1. **Interlock region** (CONTROLLER-SPEC: own region, own decoupling, short traces to J4, no MCU traces through it).
   - **Parts:** U20 latch (LVC1G74), U21 TPS3823, U22 HC30, U23/U24 LVC14, U25 LVC1G08 and their pull-ups and bypasses. Next to them sit the trip glue: U3 TPS3703, U10 runaway TLV3201, U11 SENSOR_LIVE AND, U12 RAIL_FAULT inverter, and the 0 Ω OVP tie.
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
8. **ESP32-S3-WROOM-1** (R27).
   - Place it at the board's front edge between X−80 and X10, antenna end facing the front lens window (X−89…19).
   - Keep Espressif's antenna copper/metal keep-out clear.
   - **Wi-Fi: option, unqualified** (enclosure test E4); the fallback is WROOM-1U with an external antenna behind the lens bezel.
   - The EN RC and the 22 µF/100 nF decoupling go at the module.
9. **M12 probe J9.** Its TVS D1 goes at the connector pin, with a short return to selv_gnd. The probe lead is user-accessible, so ESD current must not cross the analog ground.
10. **PWM.** The 33 Ω series resistors go at the MCU and the 10 kΩ pull-downs at J4.
11. **Tank-RMS channel** (U14 AD8436, U15 MCP3202, D2 BAT54S).
    - Put U14 beside the ct_mon buffer U6 near J4.14, and keep its CAVG/coupling C0G capacitors tight to its pins.
    - It runs from v15, so keep its output buffer → 1 kΩ → clamp → U15 CH0 path short, with the clamp at U15.
    - U15 sits on the RTD SPI bus. Place it between the MCU and the RTD front end, not inside the RTD analog area.
12. **Encoder/button protection.** U17 (LVC2G17), the 1 kΩ series resistors and the pull-ups go near J5/J7/J8. The 5 V LDO U16 and its 2 × 100 Ω droppers (≈ 0.12 W each) go near J5, away from the thermal-sense nodes.
