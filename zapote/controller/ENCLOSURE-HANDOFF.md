# Controller → enclosure team: connector list and placement-critical parts

This is the electrical side of the R25 controller board. The enclosure team owns the outline, holes, landings and height envelope (CONTROLLER-SPEC R25). Nothing here is a layout; it states what a layout must keep. Coordinates are appliance world mm: board X−168…38, Y14…90, bottom at Z21, top copper at ≈ Z22.6, and the height limit Z40 leaves ≈ 17.4 mm above the board.

## Connector list (R25 landings)

| Ref | Part (LCSC) | Pins | Harness | Landing (face, X, Y, Z) | Pin map |
|---|---|---|---|---|---|
| J4 | Molex Micro-Fit 3.0 43045-1612, 2×8 vertical (C491447) | 16 | SELV_J4_to_controller, 1:1 to native-21 J4 (43025-1600 both ends) | right, 42.2, 42, 34 | 1 v15_selv, 2/4/15 selv_gnd, 3 v3v3 (out), 5–8 pwm_ha/la/hb/lb, 9 permit, 10 bus_fault, 11/12 vbus_p/n, 13 ct_zc, 14 ct_mon, 16 line_zc |
| J5 | TE Micro-MaTch 7-215079-6, female-on-board 2×3 (C306122) | 6 | UI_controller_to_encoder: Grayhill factory cable plus extension, mates 7-215083-6 | **right (R25 move), 42.2, 64, 36** | 1 +3.3 V (0 Ω link), 2 GND, 3 A, 4 B, 5 switch, 6 GND. **Pin map to confirm** |
| J6 | JST B8B-XH-A(LF)(SN) (C157972) | 8 | UI_controller_to_OLED | top, −35, 70, 42.2 | 1 +3V3, 2 GND, 3 SCLK, 4 SDIN, 5 CS#, 6 D/C, 7 RES#, 8 GND. At the OLED end the harness ties BS1, BS0, R/W, E and D3–D7 to VSS (4-wire SPI) |
| J7 | JST B3B-XH-A(LF)(SN) (C144394) | 3 | UI_controller_to_buttons, landing 1 | top, −90, 41, 42.2 | 1 BTN1, 2 BTN2, 3 GND (switch closes to GND) |
| J8 | JST B2B-XH-A(LF)(SN) (C158012) | 2 | UI_controller_to_buttons, landing 2 | top, 5, 41, 42.2 | 1 BTN3, 2 GND |
| J9 | JST B3B-XH-A(LF)(SN) (C144394) | 3 | probe_M12_to_controller | **right (R25 move), 39.2, 86, 35** | 1 probe sense (NTC to GND assumed), 2 GND, 3 shield/drain. **Probe type to confirm** |
| J10 | JST B3B-XH-A(LF)(SN) (C144394) | 3 | fan_to_controller (Delta PFB0612EHE-F00, 3-wire) | **rear (R25 move), −155, 91.3, 30** | 1 +12 V, 2 GND, 3 tach |
| J1 | JST B2B-XH-A(LF)(SN) (thermal-sense, unchanged) | 2 | NTC_coil_to_thermal_sense | top, −60, 88, 42.2 | 1 COIL_SENSE, 2 GND (polarity-free NTC) |
| J2 | JST B2B-XH-A(LF)(SN) (thermal-sense, unchanged) | 2 | NTC_sink_to_thermal_sense | top, 20, 88, 42.2 | 1 HS_SENSE, 2 GND |
| J3 | JST B4B-XH-A(LF)(SN) (RTD unit, unchanged) | 4 | pan_RTD_to_controller (SAB 4×AWG28, ≤ 500 mm) | rear, −165, 92, 34 | 1 FORCE+, 2 RTDIN+, 3 RTDIN−, 4 FORCE− |
| J11 | Wurth 61300811121 1×8, 2.54 mm (C6400764) | 8 | none (bring-up only; may be left unfitted) | any accessible spot | 1 3V3, 2 GND, 3 TXD0, 4 RXD0, 5 EN, 6 IO0, 7 USB D−, 8 USB D+ |

## Landing conflicts found
**The basis.** This is `tools/controller_calcs.py`'s `landings()`, written to `evidence/controller_calcs.json`. The calculation assumes the connector is centred on its landing, projected onto the board. The keepout it must clear is the spec's Ø8 screw-head area, plus half the connector's body length, with orientation unknown.

| Connector | Landing | Nearest hole | Centre distance | Needed | Note |
|---|---|---|---|---|---|
| J3 pan RTD | (−165, 92) | (−164, 86) | 4.1 mm | 10.2 mm | **Conflict.** The landing is at the rear-left corner hole. Move the landing to X ≥ −153, or let the connector sit about 10 mm inboard and route the lead along the edge |
| J9 M12 probe (R25) | (39.2, 86) | (34, 86) | 4.0 mm | 9.0 mm | **Conflict.** The new landing lines up with the right-rear hole. Suggest Y ≤ 77 (clear of the hole and still above the encoder at Y64), or accept the connector inboard at X ≈ 25 |
| J1 coil NTC | (−60, 88) | (−65, 86) | 5.4 mm | 7.7 mm | **Conflict, marginal.** Move the landing to X ≥ −57, or offset the connector 2.5 mm right |
| J10 fan (R25) | (−155, 91.3) | (−164, 86) | 9.9 mm | 9.0 mm | Clear by 0.9 mm with the connector centred on the landing. Keep it there or move it right |

All other landings clear by 6 mm or more.

## Height and cable exit
- **J4 (flag).** The vertical Micro-Fit 43045-1612 is 9.91 mm tall (JLC listing). The mated 43025-1600 plug and the 3.5 mm cable then leave vertically, but the landing is a horizontal exit at Z34, about 11.4 mm above the board, and the limit is Z40. Either confirm a tight bend fits under Z40, or switch J4 to the right-angle Micro-Fit 3.0 2×8 header (same pinout; the part number is yet to be selected and checked). Mated height was not available in the sources I read [UNVERIFIED].
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
8. **ESP32-S3-WROOM-1.**
   - Put the PCB antenna at a board edge with the module's copper keepout (Espressif WROOM-1 datasheet layout guidance), on the side facing the most open, non-metal part of the enclosure.
   - **Flag:** Wi-Fi range inside the metal chassis is unqualified.
   - The EN RC and the 22 µF/100 nF decoupling go at the module.
9. **M12 probe J9.** Its TVS D1 goes at the connector pin, with a short return to selv_gnd. The probe lead is user-accessible, so ESD current must not cross the analog ground.
10. **PWM.** The 33 Ω series resistors go at the MCU and the 10 kΩ pull-downs at J4.
