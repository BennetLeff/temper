# Controller decisions

These are design calls I made during schematic capture, as a senior designer, from the inputs in [README.md](README.md). Each one gives the basis and is flagged where the owner or enclosure team should confirm it. Numbers come from `tools/controller_calcs.py` or `tools/verify_controller.py`. Open items are at the end.

## C1. One unit; blocks ported by a provable line filter
- **What:** `zapote/controller` follows the unit pattern (`ato.yaml`, `elec/src`, `tools`, `frozen`). Interlock and thermal-sense are ported by `tools/port_blocks.py`, and `RTDSensing` is used from the byte-identical library.
- **What changed in the ports:** only the inter-board headers and the thermal `+3V3`/`gnd` net-name overrides are removed, and the verifier proves that. On the integrated board those boundaries become copper.
- **What is not changed:** no value, MPN or internal connection.
- **Re-run each block's own validation** (Rust validators) on the integrated layout, per CONTROLLER-SPEC. That is a layout-stage item.

## C2. GPIO map: keep round-5 `pins.h` where it exists
- **Kept from pins.h:** PWM 4/5/15/16, REQUEST→IL_RESET_N 17, HEARTBEAT→IL_WDI 18, FAULT_HIGH 21, RAIL_OK 35, INTERLOCK_OK (PERMIT read-back) 36, SUP_RUN_OK 37, fast SPI 10–13 → RTD (CS/CLK/MISO/MOSI = 10/11/12/13). RTD_DRDY was on 14; C23 moves it to expander P07 and puts RUN_EN on GPIO14.
- **"Supervisor run-OK":** `bridge_feedback_t.sup_run_ok` is the interlock's TPS3823 output (`WDT_RESET_N`). There is no separate STM32 supervisor on this board.
- **Ambiguity resolved (flag).** The architecture lists ADC1 = GPIO 1, 2, 6, 7, **10** *and* RTD SPI = **10**–13, which conflicts on GPIO10. It also keeps GPIO8/9 for pins.h's UART. That UART was round 5's link to the STM32 supervisor, which the integrated interlock replaces, so **GPIO8 becomes the fifth ADC1 channel (M12) and GPIO9 becomes I²C SDA**. The ADC1 channels are 1, 2, 6, 7 and 8, still exactly five.
- **Strap use (checked by `misc`):**
  - GPIO0 = I²C SCL, whose 4.7 kΩ pull-up also holds the SPI-boot strap; the debug header can pull it low to download.
  - GPIO45 = OLED D/C with a 100 kΩ pull-down (VDD_SPI strap must be 0).
  - GPIO46 = fan-off FET gate with a 100 kΩ pull-down (strap 0).
  - GPIO3 = fan tach; its JTAG-select strap is only active if an eFuse is burnt.
- **Debug:** GPIO19/20 (USB Serial/JTAG) go to the debug header.

## C3. The OLED is SPI, not I²C (architecture open item 6, answered)
- **Why:** the NHD-3.12-25664UCW2 (SSD1322) offers 6800/8080 parallel or 3/4-wire SPI only (Newhaven DS "MPU Interface Pin Selections"). There is no I²C.
- **Wiring:** 4-wire SPI on GPIO40/41 (SCLK/SDIN), D/C on GPIO45, RES# and CS# from the expander (P04/P05). CS# moved off GPIO42 in the follow-up (C20): the OLED is the only device on its bus, so CS# only needs setting once, and the expander pin powers up as an input with its pull-up, so the display is deselected at reset. The harness ties the module's BS1/BS0, R/W, E and D3–D7 to VSS at the OLED end (the J6 pin map is in ENCLOSURE-HANDOFF).
- **Supply:** the factory 3.3 V jumper option is kept, at 340 mA maximum. Using its 12 V panel option would need a tighter 12 V rail than the fan rail (R11 review), so I didn't.
- **I²C** (GPIO9 SDA, GPIO0 SCL) now serves only the TCA9555.

## C4. The MCU can observe protective nets but never drive them
- **Topology:** every read-back of PERMIT, bus_fault, `WDT_RESET_N`, RAIL_OK, LATCHED_FAULT, RTD_HW_FAULT, HS_FAULT and COIL_FAULT passes through one SN74LVC244A (OE tied low).
- **Why:** a GPIO left as an output, or an expander pin set to output, cannot hold PERMIT high or mask a fault.
- **Firmware's only inputs to the trip logic** are WDI (into the TPS3823) and a RESET_N request edge. The verifier proves both are non-overriding.
- **Leakage:** the buffer's ≤ 5 µA input current (85 °C) is inside each interlock input's 20 µA aggregate budget.

## C5. OVP input tied healthy (settled)
Through a removable 0 Ω link (`r_ovp_tie`) to selv_gnd. bus_fault already ORs DC-bus OCP, OVP and HOT5 with both tank-CT polarities, and it enters the OCP input.

## C6. Runaway producer: hardware comparator on the RTD channel (architecture open item 3)
- **Circuit:** a TLV3201 compares RTDIN+ (through the RTD block's existing 100 kΩ window branch) with BIAS × 10k/(20k + 10k). The 0.1 %, 25 ppm RT0603 divider takes BIAS from the MAX31865's own bias pin.
- **Why ratiometric:** referencing to BIAS cancels its ±3 % tolerance.
- **Trip:** a nominal 215 Ω (308 °C), with a band of **296.6–319.1 °C**. That covers resistor tolerance and drift, Rref, ±5 mV comparator offset and 0–1 Ω leads.
- **Margin:** the band sits above the 250 °C cooking maximum. Firmware's 300 °C `RUNAWAY_MAX_ABSOLUTE_TEMP_C` and its 15 °C/s rate limit stay as the first line; the hardware is the backstop, and on a worst-case unit it may trip up to 3.4 °C before firmware.
- **It also trips** if BIAS is off or the RTD is open (fail-safe). Firmware must enable BIAS, wait ≥ 10 ms (MAX31865 startup, and the 0.67 ms threshold RC) and then request a reset.
- **Flag:** this adds a 67 µA load on BIAS and a comparator input on the RTD block's window node. The RTD validator (`zapote-rtd`) must re-run on the integrated layout.

## C7. SENSOR_LIVE and AUX producers (architecture open item 4)
- **SENSOR_LIVE** = RAIL_OK AND RTD_RAIL_OK (SN74LVC1G08).
  - RAIL_OK: the TPS3703 window on v3v3, open drain with a 10 kΩ pull-up.
  - RTD_RAIL_OK: the RTD block's own TPS389001 on RTD_AVDD.
  - Thermal-sense has no separate validity output. It runs from v3v3, so RAIL_OK is its power validity, and its open, short and hot conditions are already separate latched inputs.
  - Freshness of the RTD *sample* is a firmware matter and isn't represented in hardware.
- **AUX** = RAIL_FAULT = NOT RAIL_OK (SN74LVC1G14). A rail excursion therefore latches, rather than only gating, and AUX gets a documented producer, as the interlock interface requires.
- **Start-up inhibit:** for 7–13 ms after the rail enters its window, both hold the interlock inhibited, on top of the TPS3823's power-on reset.

## C8. 3.3 V regulation and window
- **Regulator:** TPS62933F (forced CCM) at 500 kHz with 10 µH and 3 × 22 µF.
- **Feedback:** 22.1k/7.06k 0.1 % gives 3.304 V nominal, centred between the window's UV release and OV trip. The first capture used 31.6k/10k (3.328 V), which left 13 mV to OV, so I changed it.
- **Supervisor:** the TPS3703A4330 senses through 1 kΩ/1 µF (τ = 1 ms), so µs-scale ESP32-TX and OLED load steps can't nuisance-latch the interlock. Real rail faults are ms-scale.
- **Part (follow-up):** fitted as **TPS3703A4330DSERQ1** (C1850327), because JLC showed 0 stock for the commercial TPS3703A4330DSER. The Q1 datasheet (SBVS344D) gives the same DSE pinout (SENSE1 VDD2 CT3 RESET4 GND5 MR6), ±0.7 % accuracy, 0.3–0.8 % hysteresis, 7–13 ms delay and supply/SENSE currents, so every calculation is unchanged.

## C9. Fan supply: a regulator on the controller, on by default (spec R19 L1, R24; superseded by C28)
- **Converter:** 15 V → 12.0 V with a TPS62933 (11.78–12.22 V, inside the Delta PFB0612EHE-F00's 7–13.2 V). At 14.5 V input the duty is 0.846, against a 0.923 typical limit without foldback, and foldback allows 98 %.
- **Default state:** the fan is on (EN floats high). Firmware can only switch it off, via the 2N7002 on GPIO46.
- **Connector:** the fan is 3-wire, so the 3-pin header carries +12 V, GND and tach. Tach has a 10 kΩ pull-up to 3.3 V into GPIO3. There is no PWM pin; the spec makes it optional.
- **Flag (conflict):** power-stage D-18 (2026-10-03) said fans get a dedicated SELV supply "not fed from PS1 or J4.1". R24's CONTROLLER-SPEC, which is later and covers a single 7.6 W fan, puts the fan on PS1 through this regulator, and I followed R24. PS1 then carries 12.4 W at simultaneous peak against its 21 W rating; the owner should confirm D-18 is superseded.

## C10. D-11 bus receiver as specified, with one resistor substitution
- **As specified:** OPA2388 half-gain difference stage (20k/10k RT0603 0.1 %) and an LM4040A25 reference behind 1 kΩ; the bias buffer is the OPA2388's B half; 100 Ω/100 nF into GPIO2, ATTEN2.
- **Substitution:** D-11's bias-divider bottom of 10.1 kΩ has no JLC-stocked RT0603 (RT0603BRD0710K1L returns no listing), so I fitted RT0603BRD0710KL at 10.0 kΩ.
- **Effect:**
  - The zero reading moves from 0.250 to 0.248 V (−2.2 mV).
  - The < 100 mV invalid and 1210 mV over-range thresholds are unaffected in meaning; 1210 mV ↔ 231 V bus.
  - Factory zero calibration absorbs the offset.
- **Flag:** D-11's harness capacitance limits (≤ 400 pF to ground, ≤ 200 pF between conductors) become a J4 harness requirement.

## C11. ct_mon: unity buffer, wideband (settled answer; RMS added in C19)
- **Load:** a TLV9062 follower, ≥ 10 MΩ DC (the 10 MΩ defines the input as 0 V when J4 is unplugged, so firmware can detect it). Gain error is 0.02 % against the ≈ 2 kΩ source.
- **Bandwidth:** the output RC is 100 Ω/1 nF (1.6 MHz), so the ≈ 32 kHz tank waveform reaches the ADC.
- **Range:** 1.18–2.12 V at 22 A RMS and 0.83–2.48 V at the 55 A trip, inside ATTEN3's 0–2.9 V.
- **Flag (risk):** `input_limits.h` wants tank RMS over the switching period. At 20 kS/s that can only be estimated statistically: asynchronous sampling, many periods per half line cycle. The ESP32 SAR's aperture and settling at 32 kHz are not specified.
  - **Superseded (owner-approved):** a true-RMS converter now gives firmware the RMS directly (C19). The raw path stays for phase and waveform checks.

## C12. ADC sampling plan
- **Pattern** (one continuous ADC1 sequence at 80 kS/s): `VBUS, CT_MON, VBUS, CT_MON, VBUS, HS, COIL, M12`.
- **Rates:** VBUS 30 kS/s with a ≤ 50 µs gap, CT_MON 20 kS/s, the rest 10 kS/s.
- **Basis:** ESP-IDF v5.2.3 allows ≤ 83 333 S/s and a 24-entry pattern on the S3.
- **Flag:** repeated channels in one pattern must be confirmed on the target IDF version at bring-up.

## C13. Buffers on HS_SENSE / COIL_SENSE (the "qualified receiver")
- **What:** the thermal-sense analog nodes see only a TLV9062 non-inverting input (0.5 pA typical; I allocate ≤ 1 nA, 0.1 % of the ±1 µA budget). No ADC switched-capacitor load and no other part touch them.
- **Range:** values above ATTEN3's 2.9 V occur only cold or open, which the open comparator already flags.

## C14. M12 probe assumed to be an NTC divider (architecture open item 5)
- **Circuit:** J9 pin 1 is the probe sense line. It has a 10.0 kΩ 0.1 % pull-up to v3v3, the same form as thermal-sense, and an ESD5Z3.3 TVS at the pin. A 10 kΩ/100 nF filter feeds a TLV9062 buffer into GPIO8 (ATTEN3). Pin 2 is GND and pin 3 is shield/drain to GND.
- **DEFAULT (recorded, owner item open):** M12 = NTC to ground at the probe.
- **If the default changes:**
  - **Another NTC value:** change one resistor (r_m12_pu); no topology change.
  - **A Pt100 or other low-resistance probe:** it cannot use this divider usefully. It goes to a second MAX31865 on the existing RTD SPI bus, with its CS on spare expander pin P06 and its DRDY polled. The ADC1 channel then becomes spare. Nothing else on the board depends on the M12 type.

## C15. Encoder (TE Micro-MaTch): safe with a 3.3 V or a 5 V encoder (follow-up)
- **Connector:** J5 is TE 7-215079-6 (female-on-board, 6 positions), mating the 7-215083-6 on the encoder lead.
- **Pin map (default):** 1 +3.3 V (0 Ω link), 2 GND, 3 A, 4 B, 5 switch, **6 +5 V**.
  - The Grayhill part isn't chosen, so J5 offers both supplies and the short extension harness selects one. No jumper or DNP option is needed.
  - +5 V comes from a TLV76050 (100 mA, internal current limit and thermal shutdown) fed from v15 through 2 × 100 Ω 1206. Calcs: LDO ≤ 0.14 W, +39 °C; resistors 0.12 W each, half their rating. A factory cable that grounds pin 6 only current-limits the LDO.
- **Input protection:** each of A, B and switch has a 10 kΩ pull-up to 3.3 V (for open-collector outputs) and 1 kΩ in series.
  - A and B pass through an SN74LVC2G17 Schmitt buffer, whose inputs accept 5.5 V at VCC 3.3 V (SCES381N), into GPIO47/48.
  - The switch goes to the TCA9555, whose I/O is 5 V tolerant (SCPS200E §9.3.1).
  - No encoder line touches an ESP32 pin directly (`verify_controller.py` ui section, mutation-tested).
- **Remaining flag:** the encoder's own pin map must still be wired correctly in the extension.

## C16. Buttons (two landings on the Y41 trunk)
- **Connectors:** J7 (3-pin: BTN1, BTN2, GND) at X−90 and J8 (2-pin: BTN3, GND) at X5. The switches close to GND, use the TCA9555's internal pull-ups and are polled. Each line has 1 kΩ in series into the 5 V-tolerant expander (follow-up), so an illuminated or 5 V-referenced switch can't stress the board.
- **Option, not taken:** a normally-closed STOP contact could be an independent hardware trip on AUX. I didn't take it, because the APEM contact form is unknown and AUX carries the rail fault.

## C17. J4 and its harness
- **Header (follow-up, R27):** **Molex 43045-1600**, the right-angle Micro-Fit 3.0 2×8 THT header with plastic PCB pegs (C277731). KiCad footprint `Molex_Micro-Fit_3.0_43045-1600_2x08_P3.00mm_Horizontal`, mating +X on the right edge near Y42.
  - native-21 keeps the vertical 43045-1612. The circuit numbers are Micro-Fit's, so the harness stays 43025-1600 to 43025-1600, pin 1 to pin 1, and the J4 contract check is unchanged.
  - **[UNVERIFIED]:** Molex's drawing (430450201_sd, cited by the KiCad footprint) could not be fetched from here. Its fit in the R27 envelope (X38–63, Y32–52, Z ≤ 40, plug body above Z30 beyond X50) must be checked against the drawing before layout. Distributor listings confirm right-angle, 16 circuits, 3.00 mm, through-hole, PCB pegs.
- **Returns:** LINE_ZC took one of the four selv_gnd contacts, leaving pins 2, 4 and 15 to return ≈ 0.85 A (15 V return) at peak. That is 3 × 8.5 A rated contacts, with a 22 mV ground shift over 1 m of AWG22 (included in the native-21 rail check).
- **Input protection:** none on 15 V. The IRM-20-15 is current-limited, and the harness contacts are rated far above the load.

## C18. Debug header
J11 (1×8, 2.54 mm) carries 3V3, GND, TXD0, RXD0, EN, IO0, USB D−/D+ for flashing and JTAG. Fit it for development; it can be left unpopulated in production.

## C19. True-RMS tank current (owner-approved follow-up)
- **Part:** **AD8436BRQZ.** Its datasheet (Rev. B Table 1) gives 65 kHz for 1 % additional error and 1 MHz −3 dB at 300 mV rms, which covers the 31–55 kHz tank band.
  - The LTC1968 has a higher bandwidth (500 kHz for 1 % per ADI's product page), but it needs 4.5–5.5 V and I could not read its datasheet here.
  - The LTC1966's datasheet was also unreachable. Its bandwidth for 1 % error is not claimed.
- **Circuit (single supply on v15_selv, datasheet "Single Supply"):**
  - Input: the ct_mon buffer output, AC-coupled (100 nF C0G) into the FET input buffer with 10 MΩ to IGND.
  - Core: the unity buffer drives the core through 100 nF C0G.
  - Averaging: CAVG is 100 nF C0G to VCC. The datasheet forbids X7R here, and the verifier checks it.
  - Output: OUT feeds the internal 16 kΩ with 10 nF C0G (≈ 1 kHz, 2f ripple ×0.016), then the output buffer at gain 4 (30k/10k 0.1 %).
- **Levels:** 22 A RMS reads 1.32 V and the 55 A peak trip 2.33 V. Coupling error is 0.002 % at 31 kHz.
- **Settling:** 3.4 ms to 0.1 % (falling), from the datasheet's 10 µF figure scaled linearly to 100 nF (bench item). That is within the 8.3 ms half-cycle.
- **Protection:** the output buffer runs from 15 V, so 1 kΩ plus a BAT54S clamp holds the ADC input within VDD + 0.5 V up to an 11 mA fault (DS11005 VF ≤ 0.5 V at 30 mA). Leakage contributes ≤ 0.15 %.
- **Kept:** the raw ct_mon ADC1 path (CT_MON_ADC), for phase and waveform sanity.
- **Open (bench):** the RMS output smooths the 120 Hz envelope with a time constant of order 0.5 ms (estimated). Its effect on the per-half-cycle product mean(V·I·cosφ) in `input_limits.h` has to be measured against true-RMS line current (the same bench run that sets e_est).

## C20. Where the RMS channel is converted
- **Choice:** an **external MCP3202** (12-bit, 2 channels) on the RTD SPI bus (RTD_SCK/SDI/SDO; DOUT high-Z when deselected, 33 Ω series). Its CS is GPIO42 with a 10 kΩ pull-up.
  - **CH0** is the RMS output.
  - **CH1** reads the LM4040A25 2.5 V (0.1 %) node, so firmware divides out the v3v3 reference (3.242–3.367 V).
- **Why not freeing an ADC1 channel:** all five ADC1 channels carry required signals.
- **Why not ADC2:** the only free ADC2 pads are GPIO19/20 (debug USB). ESP32-S3 ADC2 cannot be read while Wi-Fi is active, and C21 keeps Wi-Fi as an option. A signal the 15 A inlet cap depends on must not conflict with it.
- **GPIO cost:** GPIO42 (previously OLED CS#, now on the expander).
- **Firmware:** the MAX31865 (SPI mode 1/3) and MCP3202 (mode 0/3) share the bus. Use mode 3 for both, or per-device modes in ESP-IDF, with bus locking.

## C21. Wi-Fi: option, unqualified (enclosure test E4)
Wi-Fi is not required now. The WROOM-1 (PCB antenna) is kept at no cost, per R27:
- placed at the board's front edge between X−80 and X10, antenna end facing the front lens window;
- Espressif's antenna copper/metal keep-out kept clear;
- WROOM-1U with an external antenna as the fallback.

Nothing on the board needs ADC2 or depends on Wi-Fi being off except ADC2 itself, which is unused.

## C22. Recorded defaults for open owner items
These are DEFAULTS, labelled in the docs and the calcs. The design doesn't break if they change:
- **M12 = NTC** (C14 gives the change path);
- **J4 harness ≤ 1 m AWG22** (the rail stays in contract to beyond 8 m);
- **runaway band 297–319 °C** (one resistor ratio, cross-checked by the verifier).

## C23. PERMIT = latch OK AND RUN_EN (firmware gate enable, 2026-10-09)
- **Why:** the firmware binding (firmware/components/power/COMMISSIONING.md item H1, commit e4f9ca830 on codex/power-stage-integration) needs a gate enable separate from the PWM pads. Until now PERMIT came only from the latch.
- **Circuit:** U37 SN74LVC1G08 (already on the BOM as U11/U25; LCSC C7666) with its own 100 nF (C70). Input A is the interlock latch Q, renamed `PERMIT_LATCH` (the ported block, with its 10 kΩ pull-down, is unchanged); input B is `RUN_EN`; the output is `permit` to J4.9 with a new 10 kΩ pull-down (R103), so with v3v3 lost the gate's Ioff output is high-Z and PERMIT still reads low (plus native-21's 2 × 100 kΩ). The MCU still reads the final PERMIT through U9 (GPIO36).
- **RUN_EN source: a direct GPIO (GPIO14), for the fastest stop.** No GPIO was free, so I moved `RTD_DRDY` from GPIO14 to TCA9555 P07: in auto-conversion mode the MAX31865 can be read on its fixed conversion period or its DRDY polled over I²C, while a stop through the expander would cost an I²C transaction (≈ 0.1 ms at 400 kHz) and depend on the bus. P06 stays reserved for a second MAX31865 CS (C14).
- **Default "not permitted":** 4.7 kΩ pull-down (R102), no pull-up. GPIO14 has no reset pull-up (ESP32-S3 DS Table 2-1, the same table `misc` uses for the PWM pins), so RUN_EN is low at reset, while firmware leaves the pin an input, and with the MCU unpowered (pads high-Z). Driving it high costs 0.7 mA.
- **No firmware shortcut:** `verify_controller.py` proves PERMIT is the AND of the latch and RUN_EN, that RUN_EN feeds nothing but that gate, and, over all 32 768 cases, that PERMIT is never high while any source is unhealthy, the latch is tripped or RUN_EN is low. Mutation tests: RUN_EN bypassing the gate, RUN_EN onto the latch, RUN_EN without its pull-down, and RUN_EN pulled up each fail their check.
- **GPIO / expander map change:** GPIO14 = RUN_EN (output, push-pull; high = permitted). TCA9555 P07 = RTD_DRDY (input, active low). Firmware pins.h: `R5_RUN_EN 14`; the RTD driver polls DRDY via the expander or uses the conversion period.

## C24. Enclosure R30: snap-in supports, Ø4.0 holes, board 2 mm higher (2026-10-09)
Source: output/temper-manufacturing-r30/design/r30/CONTROLLER-SPEC.md "R30 mounting change", which supersedes R27/R28 for mounting.
- **Mounting:** six dual-locking snap-in nylon supports (12 mm, UL94 V-0) at the unchanged six positions replace the standoffs and twelve screws. The board holes are **Ø4.0** (were Ø3.2); a Ø8 area around each stays free of copper and parts. Layout: `layout/world.py` (HOLE_D 4.0), milled Edge.Cuts holes, Ø8 rule areas on every copper layer; `layout/check_layout.py` checks diameter, position and the Ø8 keep-out.
- **Height:** board bottom Z23, top Z24.6 (was Z21/Z22.6). The allowance under Z40 is now 15.4 mm; JST XH (7.0 mm) mated sits at about Z35 per R30. The J4 header and plug envelope rises 2 mm with the board; the R27 "plug above Z30 beyond X50" rule is easier to meet, and the Molex drawing check (C17) stays open.
- **Antenna keep-out:** the hole at (−65, 18) still lies inside Espressif's 15 mm lateral keep-out of the WROOM; with R30 the support there is all-nylon, so the keep-out holds no copper and no metal. Recorded in LAYOUT.md open items.

## C25. Enclosure R31: mirrored pose, one button landing, ESP32 behind the lens (2026-10-09)
Source: output/temper-manufacturing-r31/design/r31/CONTROLLER-SPEC.md, "R31" section (authority over R27–R30; R30 mounting and heights still apply). R4–R30 had modelled native-21 as a mirror image; R31 re-poses it, and the controller moves with it.
- **Outline and holes:** board X−38…168, Y14…90, bottom Z23. Ø4.0 snap-in holes at (164, 18), (164, 80), (65, 18), (75, 86), (−34, 18), (−26, 74), Ø8 keep-outs.
- **J4:** right-angle 43045-1600 on the **left** edge, body X−38…−24.3 / Y27.8…57.0, mating **−X** (it mates native-21's J4 at X−109…−83 through the 1:1 harness). Pins 9/10 (PERMIT, bus_fault) now sit at the front end of the header, so the PERMIT gate U37 and R103 sit in the strip between J4 and the module, at J4.9.
- **ESP32-S3-WROOM-1:** X−20…−2, Y14…39.5, behind the fixed lens window. Its Espressif keep-out (15 mm each side) again contains a hole, (−34, 18), 14 mm from the module side; the support is all-nylon and the layout keeps the area free of copper. Enclosure to confirm (LAYOUT.md open item).
- **Buttons (schematic change):** J7 is deleted and J8 becomes a 4-pin JST B4B-XH-A (already on the BOM as the RTD connector, C144395): 1 BTN1, 2 BTN2, 3 BTN3, 4 GND. Each line keeps its 1 kΩ series resistor into the TCA9555. `verify_controller.py` ui section and its mutation test now name J8.1–3. The part count drops to 225.
- **Other connectors:** J1 (55, 84), J2 (−20, 84), J3 (152, 86), J5 (−32, 64), J6 (35, 70), J9 (−33, 86), J10 (139, 86).
- **Layout parameterisation:** every enclosure number is in `layout/world.py`; `layout/floorplan.py` reads the connector, J4 and module poses from it and places the circuit regions; `layout/check_layout.py` checks the built board against it. `tools/controller_calcs.py landings()` uses the R31 table.

## C26. Enclosure R33: WROOM-1U, one 12-way UI bus J7, J5/J6/J8 deleted (2026-10-10)
Source: output/temper-manufacturing-r33/design/r33/DECISIONS.md §3 ("Controller spec delta (CONTROLLER-SPEC R33)"); R35 HANDOFF "Controller layout" restates it unchanged (R35 governs; no controller difference). Supersedes C3 (OLED wiring), C15 (encoder), C16/C25 (buttons) and the C21 module choice.
- **Module:** ESP32-S3-WROOM-1U-N8 (LCSC C2980297), same 41-pin pinout as the -1 (Espressif DS v1.8 Table 3-1), at world X141–159, Y50–69.5, U.FL at (150, 67). The antenna is an off-board 2450AT18A100 chip-antenna board on a 150 mm 1.13 mm coax, so **there is no antenna keep-out on this board**. Layout keeps the U.FL reachable: no other part within 3 mm of it.
- **Deleted:** J5 (encoder), J6 (OLED), J8 (buttons), the encoder Schmitt buffer U17 (LVC2G17), its pull-ups and 1 kΩ series parts, the button series resistors. Nothing in the interlock, trip glue or read-back path moved or changed.
- **Kept:** the TLV76050 +5 V (U16, now `V5_UI`) for J7.1, with the same 30 mA budget (`controller_calcs.py ui_5v_supply()`); the TCA9555 (fault read-backs, RTD_DRDY), whose P00–P06 and P14–P17 are now spare.
- **J7 pin map** (JST B12B-XH-A, LCSC C158027):

  | Pin | Net | Pin | Net |
  |---|---|---|---|
  | 1 | +5 V (V5_UI, ≤ 30 mA) | 7 | MISO |
  | 2 | +3V3 | 8 | GND |
  | 3 | GND | 9 | CS_OLED# |
  | 4 | SCK | 10 | OLED D/C |
  | 5 | GND | 11 | GND |
  | 6 | MOSI | 12 | CS_EXP# |

  - **Why this map:** the UI board's MCP23S08 is an SPI part, so the bus is SCK, MOSI, MISO, CS_OLED#, CS_EXP#, D/C: six signals plus +5 V, +3V3 = 8 pins, leaving 4 for GND. With four GNDs every signal pin has a GND beside it, and SCK, the fastest edge, has GND on both sides. The owner's sounder decision (relayed 2026-10-10: self-oscillating buzzer on a UI-board expander output) removed the SOUNDER_PWM request, so the twelfth pin goes to GND as the coordinator suggested.
  - **No EXP_INT:** the expander is polled. Firmware reads it over the UI bus at ≥ 1 kHz and splits OLED frame writes into ≤ 512-byte chunks (≈ 0.4 ms at 10 MHz), so encoder edges are not starved. An interrupt line would cost the fourth GND.
  - **Not I²C:** extending the controller's I²C bus (which carries the TCA9555 fault read-backs) 120 mm off-board would let a UI-board fault hang the read-back bus. The UI bus is SPI only.
  - **Separate from the RTD bus:** the UI bus has its own GPIOs (an SPI host through the GPIO matrix); the RTD / MCP3202 bus on GPIO10–13 + 42 never leaves the board. `verify_controller.py` checks both (`ui_bus_separate_from_rtd_adc_spi`, `rtd_adc_spi_stays_on_board`).
- **GPIOs:** SCK 40, MOSI 41, MISO 44 (U0RXD), CS_OLED# 47, CS_EXP# 48, D/C 45. Removing the OLED and encoder freed 40, 41, 45, 47, 48 (five); the sixth is U0RXD. The console and downloads use USB-Serial-JTAG on 19/20, so J11 pin 4 (UART RX) is now unconnected; UART TX stays on J11.3 for the ROM log. GPIO45 keeps its 100 kΩ pull-down (VDD_SPI strap), so **the UI board must not pull D/C up**. CS_OLED# and CS_EXP# have 10 kΩ pull-ups here, so both devices are deselected while GPIO47/48 float during reset.
- **Protection:** 100 Ω in series at the controller end of every signal (source termination for the 120 mm jumper; it also limits ESD current into the GPIO) and two SRV05-4 arrays (LCSC C2836319, ±12 kV contact) at J7, Vcc pin on v3v3.
- **UI-board notes for its designer:** the MCP23S08 has eight I/O for 3 buttons, encoder A/B/switch and the buzzer (7), plus one of OLED RES# or the TMP122 CS. Use an RC power-on reset for the SSD1322 or an MCP23S17; the TMP122 CS can come from the expander. OLED 3.3 V jumper option, ≤ 340 mA, on J7.2. UI-board 3.3 V allocation 120 mA (logic, 3.3 V encoder option, buzzer), budgeted in `verify_controller.py v3v3`.
- **Firmware pins.h (C23 + C26):** `R5_RUN_EN 14`; RTD_DRDY on expander P07; UI SPI host: SCK 40, MOSI 41, MISO 44, CS_OLED 47, CS_EXP 48, OLED_DC 45; UART0 RX no longer available.
- **Not in this re-base (flag):** R32's controller additions (`design/r32/CONTROLLER-SPEC.md`), still in force per R35 HANDOFF: an adjustable 5.5–12 V ≥ 1.5 A blower output in place of the fixed 12 V fan rail, and a differential RC ≤ 1 kHz on the RTD and NTC inputs. The fan buck is still fixed at 12 V (C9). Open item 12.

## C27. Enclosure R36: rim NTC channel and the 6-conductor cartridge cable (2026-10-10)
Source: coordinator relay of the R36 change. A glass-encapsulated 10 k bead NTC on the sensor cartridge's PEEK rim, read from the glass underside; the cartridge cable is now 6 conductors (4-wire RTD + 2 for the NTC). R36's design folder has no controller spec yet, so the pin map below is mine.
- **Channel (built like the coil NTC channel):** *(L3: the pull-up is now 1.00 k for a 100 k / 300 °C NTC, C31; the RC moved before the buffer, C29)*
  - 10.0 kΩ 0.1 % pull-up to v3v3 (same 10 k divider form as the coil NTC; 0.1 % as on M12);
  - 100 nF at the node;
  - ESD5Z3.3 TVS at the connector pin;
  - a TLV9061 CMOS follower (same family as the TLV9062 buffers);
  - 100 Ω / 100 nF into the ADC pad.
  It is a measurement channel only: no interlock comparator (none was asked for). The R32 differential-RC request for NTC inputs still applies to all NTC channels (open item 12).
- **ADC choice:** no ADC1 pin was free (GPIO1–10 all used). ADC2 cannot be used while Wi-Fi runs. I freed **GPIO9 (ADC1_CH8)** in two moves:
  - SUP_RUN_OK_RB moves from GPIO37 to TCA9555 P14. It is still a buffered read-back (C4) and it is not in the trip path. Firmware reads it only to confirm the watchdog state, so the I²C latency is harmless.
  - I²C SDA moves from GPIO9 to GPIO37 (GPIO matrix; no strap).
  Sampling: RIM joins the ADC1 pattern as a ninth slot. VBUS still gets 26.7 ksps with a worst gap of 62.5 µs (`controller_calcs.py adc_pattern`). The rejected alternative was an MCP3204 in place of the MCP3202 (a spare CH2, ratiometric to v3v3). It would put a 130 mm analog line from the rear-right cartridge to the front-left converter. GPIO9 is at the module, beside the cartridge connector.
- **Cartridge connector:** the RTD block's J3 (JST B4B-XH-A) is part of the byte-locked RTD library (`verify_controller.py sources`), so the rim NTC gets its own **J12** (JST B2B-XH-A). The 6-conductor cable ends in two XH housings:

  | Connector | Pin | Net | Cartridge conductor |
  |---|---|---|---|
  | J3 | 1 | rtd_force_p (MAX31865 FORCE+) | RTD force + |
  | J3 | 2 | rtd_sense_p (RTDIN+) | RTD sense + |
  | J3 | 3 | rtd_sense_n (RTDIN−) | RTD sense − |
  | J3 | 4 | rtd_force_n (FORCE−) | RTD force − |
  | J12 | 1 | RIM_SENSE | rim NTC |
  | J12 | 2 | selv_gnd | rim NTC return |

  J12's landing is **proposed** at world (126, 86) on the rear edge, 13 mm left of J10. **Enclosure to confirm** (`layout/world.py`).
- **Firmware pins.h:** RIM_ADC = GPIO9 (ADC1_CH8); I2C_SDA = GPIO37; SUP_RUN_OK read through expander P14.

## C28. Blower supply: adjustable 5.5–12 V on J10, tach-supervised (L3, R32 requirement, 2026-10-10)
Source: R32 CONTROLLER-SPEC "R32 additions" (blower output 5.5–12 V ≥ 1.5 A for the Delta BFB1012VH-F00 plus its tach; J10 stays the fan header; fan law and tach-loss derate). Blower data: Delta spec BFB1012VH-F00, sample rev 01: operating 5.5–13.2 V, 1.42 A typical (2.70 A maximum), 17.04 W (32.4 W maximum), lead wires red +, black −, blue FG, current shutdown on a locked rotor. Numbers: `tools/controller_calcs.py blower_supply()`.
- **Converter:** the existing TPS62933 (U2, 3 A class, high-side limit 4.2–5.8 A, SLUSEA4D) with a new inductor. The 22 µH SWPA6045 (Isat 2.2 A) is replaced by a **Sunlord SWRB1205S-100MT**: 10 µH, 4.0 A rated, 25 mΩ, 12.5 × 12.5 × 6.0 mm (C169383). It carries the blower's 2.70 A maximum plus ripple (peak 3.2 A at the worst corner). A third 10 µF input capacitor is added.
- **Speed control: PWM injected into FB.**
  - GPIO46 (LEDC PWM) → 12.1 k / 1 µF (13 Hz) → 56.2 k into FB, with FB set by 140 k (0.1 %) / 11.5 k (0.1 %).
  - Duty 0 gives 11.96–12.40 V; duty 100 % gives 5.03–5.78 V, over the VFB, resistor and 3.3 V-rail corners.
  - Firmware closes the speed loop on the tach, so the absolute voltage only needs to span the blower's 5.5 V floor.
  - **Fail-safe direction:** GPIO46 is a strap with a 100 k pull-down, so at reset, with the MCU off or with duty 0 the blower runs at full speed. A PWM pin stuck high gives the lowest speed, which the tach sees.
- **Switch-off (fan law "off below 50 °C"):** the 2N7002 on the buck's EN is now driven by expander P15. Its gate pull-down is now 10 k, so while the TCA9555 powers up as an input with its 100 k pull-up the gate sits at ≤ 0.32 V. That is below the 2N7002's 1.0 V minimum threshold, so the blower runs by default.
- **Tach (FG):**
  - The blower's FG is open collector: 10 k pull-up to 3.3 V and an ESD5Z3.3 at J10, then 1 k / 1 nF into GPIO3 (PCNT).
  - A stalled, locked (Delta shuts the current down) or unplugged blower, or a broken FG wire, all read 0 Hz.
  - **Firmware (fan law, R32):** drive = max(sink loop, coil loop); coil derate above 150 °C. Tach below a speed threshold for > 1 s while driven means blower failed: derate tank power at once, and stop if the sink or coil keeps rising.
  - This is a firmware path. A hardware tach-loss trip into the interlock would need a retriggerable monostable feeding a spare interlock input; it is not added here and is listed as an option.
  - No current sense: ADC1 is full and the tach already covers stall, lock and open circuit.
- **Connector J10** (fixed at (139, 86), R31/R32): JST **B3B-XH-A**, unchanged. XH is rated 3 A per contact with AWG22 crimps (JST eXH.pdf), which covers the 2.70 A maximum.
  - Pin map: **1 V_BLOWER (5.5–12 V), 2 GND, 3 FG**. The blower is 3-wire with no PWM input, so R32's spec and harness list keep a 3-pin J10 and a 3-core extension.
  - The extension must be AWG22 at the XHP-3 housing.
- **Thermal:** U2 at the blower's 1.42 A typical runs at ≈ 97 °C on the JEDEC 112.2 °C/W figure at 60 °C ambient. The 2.70 A start/lock peak gives ≈ 115 °C on TI's EVM figure (60.2 °C/W). The inductor loss is 0.05 W typical.
- **Layout:** the buck moves to X 81–102 so its larger inductor still keeps L2 ≥ 10 mm from the RTD front end. V_BLOWER and v15_selv are routed 0.8 mm wide.
- **Supply budget (superseded by C33: the blower buck now runs from PS3 via J13; open item 13 closed):** PS1 (IRM-20-15, 21 W) carries the controller at the R32 drive cap: 14.8 W, `verify_controller.py v3v3`. At full blower speed the total is 23.7 W with the Delta typical 17.04 W, and 40.8 W at its 32.4 W maximum. Both exceed the 21 W rating, and R32's fan law asks for full speed in a fault. Either PS1 grows (≥ 30 W class) or the blower gets its own SELV supply, as power-stage D-18 originally said. The controller design does not change either way.

## C29. Filtering on the NTC and RTD inputs (L3, R32 / study 06 "differential RC ≤ 1 kHz")
- **NTC channels (HS, COIL, M12, RIM):** every MCU reading passes a series 10 k into 100 nF before its CMOS buffer, a 159 Hz corner. The node source impedance only adds to the R, so the corner stays ≤ 159 Hz whatever the NTC resistance.
  - **HS and COIL:** the RC is added at the top level, between the thermal-sense node and the buffer, outside the ported block.
  - **M12:** already had it.
  - **RIM:** now built the same way, with the node holding only the pull-up and the TVS.
  - **Why it counts as differential:** the NTC return conductor lands on selv_gnd at the connector, so pickup on the twisted pair appears as a differential voltage at the node, and the RC acts on exactly that.
  - **Trip path untouched:** the thermal-sense block's own trip comparators keep the block's validated node filter (100 nF at the node, inside the ported block), so the hardware trip timing is unchanged.
  - `verify_controller.py adc1` checks each corner (≤ 1 kHz) and a mutation test removes one capacitor.
- **RTD (byte-locked library, no stage added):**
  - J3 and RTDIN± are inside the locked RTDSensing module, so a series element can't be inserted between them without editing that library (`verify_controller.py sources`).
  - A ≤ 1 kHz differential RC also conflicts with the RTD unit's own requirement. Its comment in `modules.ato` explains that the 1 MΩ open-lead pull-ups with a larger C miss the 100 ms open-lead response (τ = 1 MΩ × C; a 2 × 1 kΩ / 80 nF 1 kHz filter gives τ ≈ 80 ms, 10.5 τ ≈ 0.84 s).
  - The existing protection is the RTD unit's 1 nF C0G differential capacitor at the converter plus the MAX31865's own conversion filter.
  - **Change request to the RTD unit owner:** if bench EM2/S3 show 31 kHz pickup in the RTD reading, add the filter in the RTD unit source and re-run its validator.
- **Wiring note:** NTC and RTD leads under the coil stay twisted pairs (R32).

## C30. Block validators (interlock, thermal-sense, RTD): what a re-run on this layout needs
- **Build:** all three are binaries of the Cargo workspace crate `zapote-harness` (`zapote/Cargo.toml`). Their logic sits in `zapote-erc`, `zapote-drc` and `zapote-core`, with crates.io dependencies (anyhow, serde, serde_json, sha2, thiserror; libc and flate2 via `zapote-thermal`). None is a single-file `rustc` program, so they need a workspace build, which this task excluded.
- **Inputs:** each consumes its unit's own source manifest, a native KiCad export (`current-sense/tools/extract_current_sense_native.py`; for the RTD, `rtd/native_measure.py` plus `rtd/unit/bind_native.py`) and its contract. Each also checks an exact component census of its standalone board: 25 parts for interlock, 27 for thermal-sense, 36 for RTD.
- **To run them on the controller:**
  1. a workspace build;
  2. native exports of `pcb/controller.kicad_pcb`, filtered to each block's parts and re-mapped from the controller's prefixed instance paths (`interlock.*`, `thermal.*`, `rtd_pan.*`) to the unit names;
  3. for the RTD, a controller profile in place of `rtd/unit/profile.json`.
- **Coverage today:** `verify_controller.py` covers the netlist-level parts: the ports are byte-equal to their sources, and the trip-path logic is simulated exhaustively. The validators' layout checks (clearance, bypass locality) are partly covered by the KiCad DRC and the decoupling check. The validators themselves have not been re-run (open item 9).

## C31. Rim NTC: a 100 k / 300 °C glass NTC with a 1.00 k pull-up (L3, firmware pin-map finding, 2026-10-10)
Finding (relayed by the coordinator): the C27 channel, a 10 k bead into a 10 k pull-up, sits at the bottom of the ADC range near the 250 °C pan cap. Numbers below come from `tools/controller_calcs.py rim_ntc()`, using the Semitec GT-2 series datasheet R-T table (2023-08-01).

| °C | 104GT-2, R | Node V (1.00 k pull-up) | mV/K | Old: 10 k bead (103GT-2), 10 k pull-up |
|---|---|---|---|---|
| 25 | 100 kΩ | 3.267 | 1.5 | 1.650 V, 37.9 mV/K |
| 200 | 439.3 Ω | 1.007 | 14.3 | 19.6 mV, 0.36 mV/K |
| 250 | 174.0 Ω | 0.489 | 7.0 | 8.7 mV, 0.14 mV/K |
| 280 | 107.9 Ω | 0.321 | 4.4 | outside the 10 k part's range |

- **Choice:** a 100 k glass NTC rated to 300 °C. The reference part is the **Semitec 104GT-2**: 100 kΩ ± 3 % at 25 °C, B25/85 4267 K ± 2 %, −50…+300 °C, ≈ 0.6 mW/°C, ≈ 7 s in still air, 3.0 mW rated. It is paired with a **1.00 kΩ 0.1 %** pull-up (RT0603BRD071KL, C110776).
  - The node sits at 0.49 V and 7.0 mV/K at 250 °C, about 50× the old slope.
  - The 25 °C end stays near the top of the range, but the rim channel exists for the hot end.
- **Why not the alternative** (keep the 10 k bead and drop the pull-up to 200–330 Ω): the GT-2 10 k part (103GT-2) is rated only to +200 °C, so it is out of rating at the 250 °C cap whatever the pull-up. A 270 Ω pull-up would also push up to 12 mA from v3v3 and up to 10 mW into the bead, over its 3 mW rating.
- **Self-heating:** NTC power peaks at 2.7 mW where it equals the pull-up (≈ 157 °C), within the 3 mW rating. In still air that is ≤ 4.5 K; it is 2.3 K at 250 °C and 1.6 K at 280 °C. Mounted against the glass in the rim boss it will be lower. Firmware can correct with the known current. The v3v3 load is ≤ 3.3 mA.
- **Enclosure (R36 rim boss):** the cartridge's NTC becomes a 100 k / 300 °C glass bead (104GT-2 class; body and lead dimensions per the Semitec GT-2 drawing). This replaces "glass 10 k bead". The part and its potting must be agreed with the enclosure session for the rim boss.
- **Filter and ADC path:** unchanged: TVS at J12, 10 k / 100 nF (159 Hz) into the TLV9061 follower, then GPIO9. The 10 k series resistor still dominates the RC, so the C29 corner holds.

## C32. Thermal trip ladder: hardware comparators above the firmware trips (L3, coordinator decision 2026-10-12)
**Finding** (firmware `thermal_mgmt` / `coil_guard`): the ported thermal-sense comparators tripped below the R32 fan-law operating points.
- **Heatsink:** 85 °C hardware trip (64-corner 82.4–87.6 °C) against the 88.6 °C sink fan setpoint. The sink runs at 88.6 °C at R_SA 0.29 in normal full-power operation (R32 airflow REPORT), so both the hardware latch and the firmware's 80 °C `OVER_TEMP_THRESHOLD` would trip in normal use.
- **Coil:** 120 °C hardware trip (116.0–123.4 °C) against the 140 °C coil fan setpoint and the 150–160 °C derate band.

**Required ladder:** fan-law control point < firmware derate < firmware hard trip < hardware comparator trip (the independent backstop).

| | Fan law | Firmware derate | Firmware trip | Hardware trip, nominal (64-corner band) | Release, nominal (band) |
|---|---|---|---|---|---|
| Heatsink | 88.6 °C | — | **95 °C** | **101.4 °C (98.3–104.6)** | 85.6 °C (83.0–88.2) |
| Coil | 140 °C | 150–160 °C | **165 °C** | **175.7 °C (169.7–182.0)** | 152.4 °C (147.4–157.7) |

**Resistors:** set by top-level overrides in `controller.ato`, so the port stays byte-identical to `zapote/thermal-sense` (`port_blocks.py --check` OK). The 10 k pull-ups and the open-detect divider are unchanged.
- **Heatsink:** top 9.09 k → **11.5 k** 1 % (RC0603FR-0711K5L); bottom 11.5 k → **8.06 k** 1 % (RC0603FR-078K06L); hysteresis 34.8 k unchanged.
- **Coil:** top 20 k → **90.9 k** 0.1 % (RT0603BRD0790K9L); bottom 8.06 k → **7.06 k** 0.1 % (RT0603BRD077K06L); hysteresis 42.2 k → **140 k** 0.1 % (RT0603BRD07140KL).
- All values are already on the BOM.

**Sensors:**
- **Heatsink:** Vishay NTCALUG01A104GA is unchanged (rated −55…+150 °C; the 104.6 °C high corner is inside its rating).
- **Coil:** changes to a **100 k glass NTC rated to 300 °C, Semitec 104GT-2 class**: 100 kΩ ± 3 %, B25/85 4267 K ± 2 %, −50…+300 °C, from the Semitec GT-2 datasheet. It is the same part family as the rim NTC (C31). The lug NTC's 150 °C rating does not cover the coil band (165 °C firmware trip).
  - Its mount on the coil (a high-temperature lug or bonded sleeve, replacing the NTCALUG01 lug) is for the enclosure session, under the R32/R36 coil-NTC spec.
  - The coil's ADC curve changes with it: firmware `thermal_mgmt` must switch `THERMAL_NTC_COIL` from Vishay curve 11 to the Semitec 104GT-2 table.

**Margins** (`tools/controller_calcs.py thermal_trips()`, checked from the netlist values by `verify_controller.py` "thermal"; a mutation test restores the old coil reference and must fail):
- **Heatsink, low corner:** 98.3 °C is above 95 °C + 2 K (the Vishay sensor tolerance at 95 °C). Firmware and comparator read the same NTC, so the sensor tolerance moves both together; the relative margin is set by the resistors and the comparator.
- **Heatsink, high corner and the FETs:** at 104.6 °C, Tj ≈ T_sink + 27.8 K = **132.4 °C** for the IPW65R018CFD7 at 28 A (basis A). That is ≤ 135 °C, keeping ≥ 15 K to the 150 °C datasheet maximum.
  - Inputs: θjc 0.28 °C/W (task 03 round 3 README, datasheet RθJC max) and θcs 0.634 °C/W (2 mm AlN plus 2× grease), from power-stage task 05 round 6 `board_side.py` / `requirement.py` (commit 18318042c).
  - The firmware trip at 95 °C gives Tj ≈ 123 °C, inside the 125 °C design target.
- **Coil, low corner:** 169.7 °C is above the firmware's 165 °C trip by 4.7 K. Most of the band is the sensor (R25 ± 3 %, B ± 2 % at 175 °C); the 0.1 % resistors keep the circuit's share small. The trip sits at 175.7 °C nominal rather than 170 °C because of that sensor spread. A tighter-tolerance 300 °C NTC would let it come down.
- **Open and short detection:** unchanged and still met with both sensors.
  - Open margins: no false "open" at 0 °C with ≥ 0.042 V margin, and a real open clears OPEN_REF by ≥ 0.027 V. Both exceed the contract's 14 mV comparator error.
  - Short: a shorted NTC reads hot and trips.
  - The hot-or-open FAULT and the interlock latch are unchanged.

**The interlock config chain (`OVER_TEMP_THRESHOLD` 80 °C):** this is a firmware compile-time constant (`firmware/config.yaml`, which generates `config.h`), not a hardware or zapote contract value. Its rationale (`docs/evidence/2026-08-15-thermal-threshold-decision.md`) argues from the retired IGBT IKW40N120H3 and from an 85 °C hardware latch.
- The new evidence is `docs/evidence/2026-10-12-thermal-trip-ladder-l3.md` (IPW65R018CFD7, θjc/θcs, this ladder). The old file now points to it.
- The firmware change is **not made on this branch**: `OVER_TEMP_THRESHOLD` must go 80 → 95 °C. Firmware tests pin 80 °C in `test_safety.c:41`, `test_state_machine.c:922` and `test_sil_fault_injection.c:588`, and the legacy `fan_guard.c` has `T_MAX 80`. The firmware session's merged `thermal_mgmt` branch owns those files, so the edit belongs there to avoid a conflicting merge (change request in the evidence file).

**Validators:** the thermal-sense Rust validator cannot be re-run here; it needs a workspace build (C30). Its contract (`sensor-contract.json`: 85/120 °C, Vishay sensor) describes the standalone unit, not these controller values. The Python port in `controller_calcs.py` reproduces its 64-corner method for the controller and is what this commit checks. Updating the unit's contract and validator constants for the controller values is a change request to the thermal-sense unit.

## FMEA: shared supply, ground and connector (CONTROLLER-SPEC requirement, before layout freeze)

| Failure | Effect | Detection / safe state |
|---|---|---|
| v3v3 lost (regulator off, short) | Interlock, ISO7710s and u_fault_or unpowered | Latch Q unpowered, and PERMIT pulled low by 10 kΩ here plus 2 × 100 kΩ at native-21. Independently, v3v3 is the 2EDR8259X drivers' VDDI (power-board stage 29): below VDDI UVLO (turn-off threshold ≥ 2.55 V, turn-on ≤ 2.95 V) both outputs are held low whatever the inputs (SLUSE89C Table 7-1). **Safe** |
| v3v3 slow out of window (3.15–3.19 V or 3.41–3.46 V) | Logic still powered | TPS3703 → RAIL_FAULT (AUX, latched) and SENSOR_LIVE low → PERMIT low within the 1 ms filter |
| v3v3 brown-out below the LVC operating range | Logic states undefined | The order on a falling rail: TPS3703 UV (≥ 3.146 V), then TPS3823 (2.83–3.00 V), then 2EDR8259X VDDI UVLO (turns off at ≥ 2.55 V) forces gate outputs low. **Flag:** confirm the sequence with the native-21 load on the bench |
| v15_selv lost | Both bucks stop; v3v3 decays | As for v3v3 lost |
| selv_gnd open at J4 (all three returns) | native-21 SELV floats | J4.10 has no valid low, so the 10 kΩ pull-up reads a fault, and PERMIT's reference is lost. native-21's PERMIT gate pull-down makes DIS high. **Flag:** a whole-return-open case also needs a bench check (FAULT-INTERFACE "does not qualify an open return wire") |
| J4 unplugged | All of the above at once | bus_fault pull-up reads a fault, latch drops, ct_mon reads 0 V (10 MΩ), VBUS < 100 mV is invalid in firmware. **Safe** |
| bus_fault conductor open | — | Interlock 10 kΩ pull-up gives a fault. **Safe** |
| PERMIT conductor open | native-21 sees no PERMIT | native-21's 100 kΩ pull-downs make DIS high. **Safe** |
| PWM conductor open / MCU reset / MCU unpowered | Driver inputs float | 10 kΩ pull-downs here; the 2EDR8259X inputs have an internal pull-down (R_IN,PD 150 kΩ typ; open inputs give low outputs: Infineon datasheet Rev. 1.7 Table 4 and the electrical characteristics), and the power board adds none on U1/U2 PWM, the ESP32 PWM GPIOs have no reset pull-up and only low glitches (DS Tables 2-1/2-2). **Safe**, and PERMIT is independent of these anyway |
| MCU hangs | WDI stops | TPS3823 times out (≤ 1.6 s) and PERMIT goes low |
| MCU GPIO misconfigured as output on a read-back | — | Buffered (C4); cannot reach a protective net |
| RUN_EN stuck high (GPIO fault, firmware bug) | Gate enable always on | PERMIT still needs the latch Q: every trip source drops PERMIT (C23). RUN_EN stuck low only removes permission. **Safe** |
| RUN_EN conductor open / MCU unpowered | — | 4.7 kΩ pull-down: not permitted. **Safe** |
| RTD_AVDD lost | MAX31865 off | TPS389001 gives RTD_HW_FAULT and SENSOR_LIVE low |
| Interlock 3.3 V shared with the MCU (common-cause) | One regulator feeds both | Accepted: every rail fault takes PERMIT low (rows above). The architecture asked for its own region and decoupling, not its own regulator |

## C33. Blower buck input from a separate SELV supply PS3 via J13 (stage 16, 2026-10-12)
Source: power-stage stage-16 plan `validation-results/08-manufacturing-package/native-21/stage16-blower-supply/PLAN-16.md` (commit 7ed77d61b, §3/§4) and the coordinator's relay; enclosure R41 approved J13's position and height. Numbers: `tools/controller_calcs.py ps3_budget()` and `blw_pg()`; checks: `verify_controller.py` section `blwin`.
- **Why:** C28's open item 13. With the blower at full speed PS1 (IRM-20-15, 21 W) would carry 23.7 W typical and 40.8 W at the blower maximum. The owner wants a blower start or stall unable to brown out the logic rail.
- **Topology:** PS3 is a Mean Well IRM-60-15ST, chassis-mounted at world (−139, 95) (enclosure R41; not on this board). It feeds the existing TPS62933 blower buck U2 over its own 18 AWG twisted pair (about 450 mm).
  - U2's VIN, the top of its EN divider (100 k / 12.1 k) and its three input capacitors move from v15_selv to the new net **V15_BLW**.
  - A 100 µF 25 V electrolytic (EEE-FK1E101P, same part as the v15_selv bulk) sits on V15_BLW to damp the harness against the ceramics. 25 V is above PS3's 20.25 V OVP maximum.
  - The EN UVLO (start ≤ 12.07 V, stop ≥ 9.80 V, `en_uvlo()`) now follows PS3. PS3 has the same 15 V ±2.5 % output as PS1.
  - Unchanged: the FB network and GPIO46 speed injection, FAN_OFF on P15, J10 and its FG path, and every C28 fail-safe direction.
  - New case: PS3 missing → U2 off → FG reads 0 Hz → the existing tach-loss derate.
- **Connector J13:** JST **B2P-VH(LF)(SN)**, 2-position, 3.96 mm, top entry, posts along X (LCSC C20571196 from PLAN-16; not re-queried here).
  - **Pin 1 V15_BLW, pin 2 return (selv_gnd).**
  - Rating (JST eVH.pdf p.1): 10 A with AWG16, 7 A with AWG18 on the shrouded header. Against the lower 7 A figure: the 2.72 A design load and the 5.46 A start bound (U2 at its 5.8 A high-side limit) both fit.
  - Mates VHR-2N + SVH-21T-P1.1.
  - **Position:** enclosure R41 approved body centre (88, 86) at the rear edge. The 8.5 mm VH body (eVH p.3; KiCad F.Fab outline 8.70 mm) would overhang the Y90 edge there, so the body centre is (88, 85.65), flush with the edge and 0.35 mm from R41's point (connector tolerance 0.5 mm).
  - **Height:** eVH p.1 gives a 16.5 mm mounting height, above the board-wide 15.4 mm. R41 grants a local allowance, "J13 local, Z ≤ 54 within ±6 mm of (88, 86)", which is 29.4 mm above the board top and includes the 18 AWG bend. `check_layout.py` checks that J13's body lies inside that square.
- **Return path and ground (decision):** PS3's −V is tied to selv_gnd at **one point only, J13.2**, which sits about 10 mm behind U2's input capacitors (J13 pins at Y ≈ 86, input capacitors at Y 72–78).
  - PS3 is Class II with no FG terminal (IRM-60-SPEC p.1), so no second path exists through PE or the chassis. selv_gnd stays referenced to earth through native-21's R_FE as before.
  - PS1's return enters at J4 (far left); PS3's at J13. The two supplies share only the solid In1 plane. Neither output is earthed elsewhere, so the two returns form no loop that encloses mains or tank current.
  - **Loop:** PS3+ → J13.1 → V15_BLW pour/bulk/input caps → U2 → L2 → V_BLOWER → J10.1 → blower → J10.2 → In1 plane → U2/input-cap ground vias → J13.2 → PS3−.
    - The switching loop (input caps, U2, ground via) is unchanged from L3 and local to the buck.
    - The blower's DC return crosses the plane from J10 to the buck, as in L3.
    - What changes: the 15 V supply current no longer crosses the board from J4. It enters and leaves at J13 beside the buck, about 120 mm shorter.
  - The harness loop area is kept small by the twisted pair.
- **BLW_PG (recommended option, taken):** 20 k / 4.7 k (1 %) from V15_BLW into expander **P16**, as signal BLW_PG. The divider sits at J13, so only a ≤ 3.9 V node runs to the expander.
  - PS3 present at 14.63 V gives ≥ 2.74 V, above VIH (0.7 × 3.465 = 2.43 V).
  - PS3 absent, with V15_BLW open and the TCA9555 pull-up bounded at 50 k, gives ≤ 0.30 V, below VIL 0.94 V.
  - At the 20.25 V OVP it gives 3.88 V, within the 5 V-tolerant input (TI SCPS200E). Divider current is 0.61 mA.
  - **Firmware:** read P16 as an input. P16 = 1 means PS3 is present. FG at 0 Hz with P16 = 0 means "PS3 absent". FG at 0 Hz with P16 = 1 while driven means "blower failed". Both derate as C28.
- **PS1 after the split:** 3.3 V rail plus the direct v15 loads = **4.83 W of 21 W** (`verify_controller.py` `ps1_within_21W_at_full_blower`), whatever the blower speed.
- **PS3 budget** (`ps3_budget()`):
  - The blower draws 35.7 W / 2.88 A at the buck's 12.40 V duty-0 corner (fan law from Delta's 32.4 W at 12 V, an estimate as PLAN-16). At η 0.90 that is a **39.7 W PS3 output**, 2.72 A at 14.63 V.
  - That is 66 % of 60 W, inside the 45 W derated figure at 60 °C (IRM-60-SPEC p.3 curve).
  - The harness drops 172 mV (63.3 mΩ loop), leaving ≥ 14.45 V at U2 against the 13.54 V it needs for 12.40 V out without foldback.
    - The loop is 450 mm of AWG18 out and back at 80 °C, plus four 10 mΩ interfaces: the two J13 VH contacts (JST eVH, initial maximum) and PS3's two screw terminals (assumed equal to the VH figure).
    - Enclosure R41 routes the pair in 292 mm of 18 AWG; 450 mm is kept as the envelope.
    - Before 2026-10-12 this was 51 mV, which counted the wire at 20 °C only.
  - At start-up, U2's 4.2–5.8 A limit bounds the 15 V draw at 3.96–5.46 A, against PS3's 4.6 A low OCP corner. PLAN-16 bench gate G-B1 measures the blower's start current.
- **Layout:**
  - The buck cluster moved 5.5 mm forward, so J13 sits at the rear edge behind U2. The FB divider and injection resistor sit in the strip between U2/L2 and J13, beside the FB pin.
  - The PS3 current never depends on a routed track. V15_BLW runs in F.Cu pours (`floorplan.py` BLW_FEED):
    - a 1.7 mm band from J13.1 (thermal-relieved, 0.6 mm spokes) down the left of U2 into the VIN pour;
    - a 2.0 mm strip across the bulk capacitor's + pad and the three input capacitors.
  - `check_layout.py` `power_widths` fails unless J13.1, the bulk + pad and every input-capacitor V15_BLW pad lie in one filled V15_BLW region. The only routed V15_BLW tracks are the EN-divider and BLW_PG branches (mA).
  - The router never necks V_BLOWER or the blower SW node to 0.25 mm (`gridroute.py` NO_NECK). V_BLOWER is checked at ≥ 0.8 mm.
- **Supersedes:** C28's supply-budget bullet. Open item 13 is closed.

## C34. Layout fixes from the block-validator re-run (L4, 2026-10-12)
Source: the C30 re-run of the interlock, thermal-sense and RTD validators (`evidence/block-validators/`, commit 5dca3ef62). Its failures split into contract deviations of the integration (host connectors absent, the C32 trip resistors, DRDY on the expander) and four layout findings. C34 fixes the four in the generator; the rest are justified line by line in `evidence/block-validators/WAIVERS.md`. No validator, contract or unit profile was changed.

| Finding (before) | Fix | After |
|---|---|---|
| `DRC.BOARD.STACKUP`: layers sum to 1.6062 mm, board 1.6 mm (interlock, thermal) | `build_board.py` STACKUP: core 1.065 → **1.0588 mm**, so copper + dielectric + mask = 1.6000 mm | pass |
| Thermal `DRC.NATIVE.CLEARANCE` ×4 below the unit's 0.20 mm (0.1826, 0.1804, 0.1988, 0.1999 mm) | Net class **Thermal** (0.20 mm) on every thermal-block net, selected as the validator's filter selects them (each net on a `thermal.*` pad, less selv_gnd/v3v3): COIL_/HS_ FAULT, HOT, OPEN, REF, SENSE and OPEN_REF. KiCad's DRC enforces it (the larger class clearance wins, pours included); `gridroute.py` routes to it (cover radius and exact checks per net pair). The validator also sees the shared plane nets' whole copper, so a first closing run still failed on one selv_gnd / v3v3 pair (0.19 mm, 70 mm from the block): a KiCad custom rule (`pcb/controller.kicad_dru`, from `floorplan.PAIR_CLEARANCE`) and the router's exact check now hold **selv_gnd to v3v3 ≥ 0.20 mm** board-wide (it touched only routed v3v3 links; the plane fan-out already kept 0.20) | pass |
| RTD `DRC.RTD.LOCAL_DECOUPLING`: `c_rtd_input` 10.0 / 14.0 mm from the MAX31865 inputs (rule ≤ 3 mm) | `floorplan.py` places it across the ADC's RTDIN+/RTDIN− end, (154.5, 76.5) rot 90: pad 1 → pin 10 and pad 2 → pin 11 about 2.1 mm, pad to pad | pass |
| RTD `DRC.RTD.NATIVE_GEOMETRY` ×146 "analog_return trace exits the filled return corridor" | see "Analog return" below | pass (0) |
| RTD indeterminate: no RTD_AVDD zone on F.Cu | a local **RTD_AVDD F.Cu pour** (`route.py`, zone RTD_AVDD_F) over the MAX31865 VDD pin and the RTD_AVDD pads within 6 mm (its bypass), above GND_F | pass |

**Analog return (decision: fix it in the layout rather than ask for a controller profile).** The 146 failures were real: 72 RTD analog trace pieces ran on B.Cu, whose nearest plane is the In2 **v3v3** plane, and the other 74 left their own vias through an In1 antipad of 0.25 mm clearance (wider than the unit's 0.20 mm terminal envelope) or had no ground via within 3 mm of the layer change. The analog family is the unit's `sensitive_nets` (rtd_sense_p/n, rtd_force_p/n, bias = `p1`, refin_n, window_rtdin_p = `rtd_pan.low_window-inp`, vbias; `floorplan.py` RTD_ANALOG_NETS). Now:
- **Layers:** the router keeps them on **F.Cu and In2.Cu**, the two layers whose reference is the solid selv_gnd plane on In1.Cu. B.Cu is closed to them.
- **In1 plane clearance 0.25 → 0.20 mm**, so each via's antipad is the via + 0.20 mm, the unit's terminal envelope.
- **No track over an In1 hole:** an analog track avoids every other item's In1 antipad, including two antipads closer than the plane's 0.25 mm minimum width (they merge into one hole); every via of another net keeps its antipad ≥ 0.125 mm from analog copper; analog vias keep 1.2 mm drill-to-drill.
- **Return beside every layer change:** an analog via is placed only within 2.5 mm of a selv_gnd plane via (the unit asks ≤ 3 mm). `fanout.py` adds a **stitching grid** of selv_gnd vias (3 mm pitch, where none sits within 1.5 mm already and the spot is legal) over the RTD region, world X 115–167, Y 55–89, not under the module: 96 vias on this board.
- **Not adopted:** making In2 ground under the RTD block (as the unit board does) would cut the v3v3 plane feeding the decoupling there, and a B.Cu +3V3 pour would duplicate the In2 plane. Those two unit layer roles stay indeterminate (WAIVERS W4). An informative run with the controller's own roles (`results/informative-controller-rtd-layer-roles.json`) shows the remaining gap: the RTD SPI nets run partly on B.Cu over the v3v3 plane. SPI is ≤ 5 MHz with 33 Ω series resistors and does not share the analog corridor; putting it under the same rule is a follow-up (open item 14).

**Parts moved (CPL rotation audit; `fab/cpl-jlcpcb.csv`, rotations as KiCad writes them):** C31 `rtd_pan.c_rtd_input` (explicit pose; 0° → **90°**). Auto-placed parts that moved with it: C18 `c_tach` (90° → **180°**), C51 `c_ct_adc` (270° → **90°**), R43 `rtd_pan.r_mosi` (90° → **180°**), R44 `rtd_pan.r_cs` (90° → **180°**), R45 `rtd_pan.r_miso` (270° → **0°**); position only, rotation unchanged: R39 `rtd_pan.r_ref`, R40 `rtd_pan.r_rtdin_p_bias`, R42 `rtd_pan.r_sclk`, R80 `r_ct_adc`. Nothing else moved (`pcb/placement.json`). All are 0603 passives.

**Gates** (all from `layout/make.py`, unchanged thresholds): DRC 0 errors / 0 unconnected / parity 0; JLC DFM PASS; `check_layout.py` 12/12; fab review PASS; `verify_controller.py` 182/182 and 33/33 mutation tests (schematic unchanged). Convergence and the validator counts: LAYOUT.md "Results" and `evidence/block-validators/README.md`.

## Open items (need the owner or the enclosure team)
1. **Owner:** confirm D-18 is superseded, so the fan can sit on PS1 through the controller (C9).
2. **Owner:** M12 probe type and pin map (C14).
3. **UI board (R33, C26):** the encoder part and its supply (3.3 V, or 5 V within J7.1's 30 mA), the buzzer part (≤ 90 mA on J7.2), and whether STOP should be a hardware trip. The UI board must not pull D/C up (GPIO45 strap).
4. **Owner:** the runaway band. **Now 298.8–323.1 °C** with the C1 leads and the divider on S− (C38; the C6 DEFAULT was 296.6–319.1 °C). It is set only by the 20k/10k ratio, so a new band is one resistor change. `verify_controller.py` checks that the fitted ratio equals `controller_calcs.py`, and `runaway()` reports the band. The BIAS-on start-up sequence for firmware stays.
5. **Bench:** the AD8436 settling with CAVG = 100 nF (the linear scaling from the datasheet's 10 µF figure is an assumption), and the envelope-tracking error over a half line cycle (C19).
6. **Power-stage:** the J4 harness spec. **DEFAULT:** ≤ 1 m AWG22 (R27's route is 74 mm). `controller_calcs.py harness_sensitivity()` shows native-21 still sees ≥ 3.208 V even at 8 m, so the design does not depend on this default. D-11's ≤ 400 pF/≤ 200 pF capacitance limits apply.
7. **Procurement (superseded by `ORDER.md` §2, C48: AD8436BRQZ, ERA-3AEB1652V and CD74HC30PWR were swapped in C35/C36):** AD8436BRQZ has zero JLC stock (consign or buy from ADI or a distributor). The TPS3703 Q1 has only 18 at JLC. MCP3202 has 197. Ported parts with JLC stock 0 or near 0: ERA-3AEB1652V and RG2012V-431-W-T1 (RTD block), and CD74HC30PWR (interlock, 7 in stock). See `bom/controller-parts.json`.
8. **Firmware:**
   - repeated ADC1 channels in one continuous pattern (C12);
   - the BIAS-on, settle, reset-request sequence (C6);
   - the WDI ≤ 400 ms heartbeat;
   - the UI bus driver (OLED + polled MCP23S08 on one SPI host, chunked frame writes, C26);
   - pins.h additions (UI SPI 40/41/44/47/48/45, RUN_EN 14, I²C SDA 37 / SCL 0, blower PWM 46 and tach 3, ADC on 8 and rim NTC on 9; expander: RTD_DRDY P07, SUP_RUN_OK P14, FAN_OFF P15, BLW_PG P16 (C33));
   - the blower fan law and tach supervision (C28).
9. **Layout stage:**
   - ~~re-run the interlock, thermal-sense and RTD validators on the integrated board~~ done (C30 run, C34 fixes; remaining findings waived in `evidence/block-validators/WAIVERS.md`);
   - the native KiCad ERC/DRC and Rust stackup gate;
   - TPS389001 uses the RTD unit's `Temper_RTD` footprint library.
10. **Bench:**
    - supervisor nuisance trips under combined load steps;
    - v3v3 decay with the native-21 load;
    - open-return and whole-J4 cases;
    - fan start at the PS1 low corner;
    - D-11 accuracy and ct_mon estimation.
11. **Enclosure:** connector-versus-hole and height conflicts. See [ENCLOSURE-HANDOFF.md](ENCLOSURE-HANDOFF.md).
12. **R32 delta:** the blower output (C28) and the NTC filtering (C29) are designed in. The RTD filter is a change request to the RTD unit (C29).
13. ~~**Owner / power stage: PS1 at full blower speed (C28).**~~ **Closed by C33 (stage 16):** the blower buck runs from PS3 (IRM-60-15ST) through J13; PS1 now carries 4.83 W of 21 W.
14. **RTD unit / layout (C34):** the RTD SPI nets' return. Under the controller's own layer roles the RTD validator fails them where they run on B.Cu over the v3v3 plane (WAIVERS W4). Either route them like the RTD analog nets (F/In2, return vias) or accept the v3v3 image; and a per-board `return_planes` in the RTD profile (a change for the RTD unit's owner) would make that check part of the verdict.
15. **Power stage (C39):** the 2EDR8259X DIS-to-output delay (not in its datasheet). ≤ 190 ns: the capacitive-mode detector vetoes the first S4 edge; under half a period, one S4 edge passes. Bench it with the D-8 double-pulse set-up. Also confirm the CT_ZC polarity and its first-edge behaviour at low current (strap R72 if reversed).
16. **Bench T3 (C38):** the rim maximum under a 250 °C hold, before the rim trip's 86.6 k is fitted for use. The trip band is 262.1–288.3 °C.
17. **Procurement (C37):** RG2012V-431-W-T1 (Rref) has stock 0 at JLC/LCSC: consign it. Quantity and fallback: `ORDER.md` §2. SN74LVC74APWR has 1,588.
18. **Firmware (C37, C39, C42, C46):** MAX31865 high threshold word **35544**, as firmware and sensor-r3 `cr7_thresholds.py` now use (C46; the same encoding gives the −40 °C low word 12844); manual MAX31865 fault cycle with ≥ 5.5 ms per step (≥ 5 τ_max, sensor-r3 D-FCYC); bursts start at or above resonance; RUN_EN raised only with PWM idle; WDI only from the supervisor task.
19. **Enclosure (C40, C41):** the J12 harness gets a third (drain) contact; J11 is a flush TC2050 land (no header height).
20. **Routing robustness (C44, closed by C47):** `layout/convergence.py --runs 3` on the C1 + CR-8 board: 3/3 runs close with all gates passing.
21. **Rim trip resistor (C38, coordinator 2026-10-15):** `r_rim_th_top` stays **86.6 k**. The leak study's 76.8 k is on hold until the bench measures the glass temperature beside the rim NTC under a 250 °C hold. ≤ 244.5 °C means 76.8 k (rerun `rim_trip()`); otherwise 86.6 k stays. Same bench session as item 16.
22. **Firmware (C45):** `adc_gain` = 0.85507 for HS_ADC (5.90 k / 6.90 k), not the 0.849 of the CR-8 example values. Plausibility: with the divider's bottom open, HS_ADC exceeds 2.9 V whenever the sink is below about 32 °C, so a cold-start reading at the top of the range flags it.

## Layout inputs from the enclosure (R27, 2026-10-08)

Binding when the controller PCB is laid out (source: output/temper-manufacturing-r27/design/r27/CONTROLLER-SPEC.md, "R27 answers").
- **Mounting holes:**
  - rear holes at world (−164, 80), (−75, 86) and **(26, 74)**, moved by the enclosure to clear the cable landings. The right-rear hole moved again in R28 (from (30, 80)) so their J9 clears; source output/temper-manufacturing-r28/design/r28/CONTROLLER-SPEC.md;
  - front holes unchanged at (−164, 18), (−65, 18) and (34, 18);
  - nearest landings: pan RTD 12.0, fan 14.4, M12 11.0, coil NTC 15.1, sink NTC 12.8 mm.
- **J4 (harness to native-21):**
  - a **right-angle** Micro-Fit 3.0 2×8 header on the right edge, mating +X, near Y42;
  - the header, mated plug and lead bend may occupy X38–63, Y32–52, Z ≤ 40;
  - above native-21's tongue (X ≥ 50), the plug body stays above Z30.
  - Selected in the follow-up: Molex 43045-1600 (C17); envelope fit against Molex's drawing still [UNVERIFIED].
- **Wi-Fi:**
  - the ESP32-S3-WROOM-1 sits at the board's front edge, X−80…10, antenna end facing front toward the glass lens window (X−89…19, ~108 × 38), with Espressif's antenna keep-out;
  - fallback: WROOM-1U with an external antenna behind the lens bezel;
  - range is unqualified (enclosure bench test E4).
- **Fan:** from the controller's 12 V buck (power-stage D-18 fan clause superseded, commit 307d332af).

### R28 connector-level placements (enclosure, 2026-10-08)

These are layout inputs (output/temper-manufacturing-r28/design/r28/CONTROLLER-SPEC.md). They are the enclosure's names for the ENCLOSURE-HANDOFF connectors, so reconcile the reference designators at layout start.
- **Connectors:** J1 (−55, 84), J2 (20, 84), J3 (−152, 86), J5 Micro-MaTch (32, 64), J6 (−35, 70), J7 (−88, 41), J8 (5, 41), J9 (33, 86), J10 (−139, 86).
- **J4:** right-angle Micro-Fit on the right edge (X26–38, Y29.6–54.4, plug to X50).
- **ESP32 module:** X−54…−36, Y14…39.5, antenna at the front edge.
- **Holes:** (−164, 18), (−164, 80), (−65, 18), (−75, 86), (34, 18), (26, 74). `controller_calcs.landings()` was re-checked; verify PASS.

## C35. Prototype-lot sourcing swaps (2026-10-12; evidence `evidence/fab-loose-ends/consignment/`, JLC/LCSC stock read 2026-10-12)
Applied by C36. None changes a footprint or a net.
- **R53** ERA-3AEB1652V (0 stock) → **RT0603BRD0716K5L** (C728584): 16.5 k, 0.1 %, ±25 ppm, 0603, 0.1 W; drop-in.
- **U22** CD74HC30PWR (2 in stock) → **74HC30PW,118** (C546857): the same TSSOP-14 pinout and 2–6 V HC family. The interlock validator's exact-MPN check gets a waiver line.
- **R31** RC0603FR-078K06L (3 in stock) → **C861587** (8.06 k 1 % 0603). The match rests on parametric data only, so read the datasheet before applying.
- **J13** BOM code C20571196 (not found) → **C160315**. Same MPN, code fix.
- **R39** (MAX31865 RREF) RG2012V-431-W-T1 0.05 % (0 stock; no equal part in stock) → **RT0805BRD07430RL**, 0.1 %, ±25 ppm, for the prototype lot.
  - The extra 0.05 % is about 0.13–0.26 °C over 0–250 °C (PT100: 0.05 % of 100–194 Ω at 0.39–0.37 Ω/K). The 10 Ω / 300 Ω fault thresholds are unaffected.
- **U14 → AD8436ARQZ-R7** (C495329, 106 in stock) for the prototypes, decided 2026-10-12 after the owner questioned the cost (`evidence/rms-alternatives/`, rerun reproduced).
  - It costs $15.04 against $30.24 for the BRQZ chain at qty 4.
  - The grade difference is an initial gain error, which the COMMISSIONING step-1 trim removes. The converter's worst case is −1.5 to +0.8 %, inside the ±3 % criterion.
  - **Production direction:** delete U14, U15 (MCP3202) and the buffers (18 parts, about $30 per board) and compute tank RMS from the existing raw CT_MON ADC1 path, with the sample clock chosen per half cycle. The model gives −3.1 to +3.0 % with assumed ESP32 ADC drift.
    - Before that is adopted: the retiming, a crest-guard rewrite, a stuck-low plausibility check, and a bench check of ESP32-S3 ADC drift and INL.
    - The prototypes carry both paths, so bench firmware can compare a shadow CT_MON RMS against the AD8436 and a current probe.
  - Rejected:
    - the precision rectifier: it reads 2–4.8 % low at 40–55 kHz and at 4 A;
    - LTC1968: $14, 17 in stock.
  - Found on the way, applies to every option: the 13–14-slot half-cycle estimator scatters −2.95 to +1.14 % with slot phase (from code reading), and a stuck-low RMS is not detected today. Both are firmware fixes.
- **CPL:** 15 rotations are corrected in `cpl-jlcpcb.proposed.csv`. Fold them into the fab output with the C34 regeneration, after re-auditing any part C34 moves. The 37 NEEDS-PREVIEW lines are checked in JLC's preview, one designator per LCSC code.
- **J4 drawing:** Molex 43045-1600 sales drawing still unread (molex.com refuses this network); `evidence/fab-loose-ends/j4/j4-interface.svg` is the interface drawing; the height and −X overhang stay [UNVERIFIED] until the owner fetches the drawing.

## C36. C35 sourcing swaps applied, CPL rotations folded (2026-10-12, branch controller-release; evidence `evidence/release-proto/`)
Applied on the C34 board without a re-route: `layout/refresh_parts.py` re-stamps the Value/MPN fields from `frozen/`, and `evidence/release-proto/geom_hash.py` shows footprint, pad, track, via, zone-fill and drawing hashes identical before and after. No footprint, net or copper changed. The block validators were not re-run (no Rust build); their expected exact-MPN findings are pre-waived in `evidence/block-validators/WAIVERS.md` (W2 note, W6).

| Ref | Was (LCSC) | Now (LCSC) | Where |
|---|---|---|---|
| R53 | ERA-3AEB1652V (C2074586) | RT0603BRD0716K5L (C728584) | `controller.ato` `rtd_pan.r_avdd_top.mpn` |
| U22 | CD74HC30PWR (C2866074) | 74HC30PW,118 (C546857) | `controller.ato` `interlock.aggregate.mpn` |
| R31 | RC0603FR-078K06L (C131052) | RT0603BRD078K06L (C861587) | `controller.ato` `thermal.hs_bottom.mpn` |
| J13 | B2P-VH(LF)(SN) (C20571196) | same MPN, C160315 | `bom/controller-parts.json` |
| R39 | RG2012V-431-W-T1 (C4260028) | RT0805BRD07430RL (C865488), 0.1 % | `controller.ato` `rtd_pan.r_ref.mpn`/`.value` |
| U14 | AD8436BRQZ (C652840) | AD8436ARQZ-R7 (C495329) | `controller_parts.ato` `Ad8436Rq.mpn` |

- **R31 datasheet check:** the Yageo RT series datasheet (ordering-code table) decodes RT0603 B R D 07 8K06 L as 8.06 kOhm, 0.1 %, D = 25 ppm/C, 0603, 0.1 W; LCSC C861587 reads "8.06k 100mW 75V thin film +/-25ppm +/-0.1% 0603". 25 ppm is within the 100 ppm limit. The only datasheet reachable here was the 2004 series issue (Yageo's own site 404s from this network), so the per-part TCR rests on that code table plus the LCSC listing; stock 2,718 at JLC.
- Library copies (`modules.ato`, `interlock_block.ato`, `thermal_block.ato`) stay byte-identical: the swaps are overrides in `controller.ato`; only `Ad8436Rq` (a controller-owned part) changed in place. `thermal_block.ato`'s own `coil_bottom` default (8.06 k, old MPN) is overridden by the controller to 7.06 k, so R31 (`hs_bottom`) is the only 8.06 k part.
- `verify_controller.py`: HC30 and AD8436 models are keyed by the new MPNs (same pin tables and budgets); VERIFY PASS, 33/33 mutation tests.
- **CPL:** `CPL_ROTATION_OFFSET` in `layout/fab.py` (keyed by LCSC code) folds the 15 audited corrections (U5-U9, U15, U20-U24, U30, U36, U38, U39) into `fab/cpl-jlcpcb.csv`; `fab/cpl-jlcpcb.csv` equals the audit's proposed CPL. The audit was re-run on the C34 board (it moved C31, C18, C51, R43-R45, all symmetric passives, class OK): 197 OK / 15 CORRECTED / 36 NEEDS-PREVIEW (the old 37 included J13, now resolved by the new code). `audit.py` now reads the KiCad rotation from the board so re-running it after the fold is idempotent. The 36 NEEDS-PREVIEW lines are in `fab/fab-notes.md`.
- **New fab hashes:** frozen netlist sha256 `2f5c40d238bed1f67dfe88a3701d25ba4480784209620a033c7ddc5614d98d1f`; `fab/controller-gerbers.zip` sha256 `9331ee6de5c5e192f582c8d0f38cbce5e7a00d2b60313f38b4fb09085d61938d` (the Gerber files differ from C34 only in their creation-date lines); `fab/bom-jlcpcb.csv` `ca5aa070...`; `fab/cpl-jlcpcb.csv` `b575b4d5...`. Gates: DRC 0 errors / 0 unconnected / parity 0, DFM PASS, layout check 12/12, fab review PASS.

## C37. Pan RTD sense filter and J3 protection (sensor-r3 CR-1, CR-2; 2026-10-15, branch controller-c1-crs)
Source: `sensor-c1-impulse-mining:output/temper-sensor-r3/pcb/CHANGE-REQUEST.md` (commit 1431caad5). Applied exactly as specified.
- **Block:** `rtd_pan` is now `RTDSensingC1` (`elec/src/rtd_c1_block.ato`), generated by `tools/port_rtd_c1.py` from the byte-identical library `RTDSensing` plus a listed set of line edits and an appended C1 section. `port_rtd_c1.py --check` is a verifier check (`sources`), so the block cannot drift from the library or from the change request.
  - Two-stage differential RC per sense line: 1.00 k (RT0603BRD071KL) / 100 nF C0G 1206 (GRM31C5C1H104JA01L) / 1.00 k / 100 nF C0G 1206 across RTDIN±, plus 1 nF C0G from each RTDIN pin to selv_gnd.
  - 220 nF X7R (CC0603KRX7R9BB224) and an ESD5Z3.3T1G on each J3 pin.
  - The 499 k open-input pull-ups (RC0603FR-07499KL), the window branch and the low-window return move to the connector-side nodes (`rtd_sense_p_ext` / `rtd_sense_n_ext` = J3.2 / J3.3); 10 nF C0G on the window node.
  - No series resistance in FORCE±.
- **CR-2, Rref:** the library's RG2012V-431-W-T1 (0.05 %, 5 ppm/K) again; the C35 RT0805BRD07430RL override is removed. **Sourcing:** JLC/LCSC stock 0 on 2026-10-15 (`evidence/c1-crs/new-parts-snapshot.json`): consign it. Reason: CR-1's accuracy budget (`checks.py` item 1b) is computed with 0.05 % / 5 ppm.
- **As-built check:** `evidence/sensor-r3-checks/run_as_built.py` reads the frozen netlist, rebuilds the sensor-r3 design dict from the captured parts and runs the unmodified `checks.py` items (two input paths pointed at copies in that folder). Result `checks-as-built.json`: **no difference from the change request; 11/11 gates PASS** (pickup 0.105 LSB worst DM at 20 kHz, runaway shift 0.03 K, open lead detected, protection, ratings).
- **Firmware (to the sensor/firmware owner):**
  - High threshold word: **35544** (corrected by C46; this note first said 35542 on an arithmetic slip, see C46).
  - With the CR-1 filter the input time constant is far above the MAX31865's 100 µs limit for the **automatic** fault-detection cycle. `checks.py` firmware constants call for the **manual** cycle (5 ms wait). Firmware must not use the automatic cycle with this board.
  - *Update 2026-10-16:* 5 ms is not enough margin. Sensor-r3 `firmware/DECISIONS.md` D-FCYC (`fault_cycle.py`, branch sensor-c1-impulse-mining 87edb1b32) solves the CR-1 network over 1536 tolerance corners: τ_max = 1009.9 µs, so 5 ms is only 4.95 τ_max. The firmware waits **≥ 5.5 ms per manual step (≥ 5 τ_max)** and 11.5 ms for the restart after step 2. It also shows the automatic cycle false-flags a healthy input (fault status 07h = 0x18) at all 48 transient corners, which confirms the note above. These are sensor-r3 figures, not rerun here.
- **Layout:** the CR asks for the 220 nF and TVS within 3 mm of the J3 pads. That cannot be met: J3's XH body runs 3.44 mm in front of its pin row (courtyard), and the MAX31865 sits 2.6 mm in front of that. Placement (`floorplan.py`): the TVS (upright) and the sense-line caps (flat) in the strip between the MAX31865 and J3, directly in front of their pins; the J3.4 pair and the pull-ups right of J3; the J3.1 cap left of the strip. Pad-to-pad distances are measured on the routed board and reported in `evidence/layout-check.json` (`rtd_j3_protection`); the TVS-to-pin figure is set by the connector body, not by the layout. R1/C1/R2 sit in two rows right of the MAX31865, in front of the Ø8 hole keep-out; `c_rtd_input` keeps the ≤ 3 mm rule to pins 10 / 11.

## C38. Runaway trip referred to S−, and a rim-NTC hardware trip (sensor-r3 CR-3, CR-5; UL 858 25.3.1 backstop; 2026-10-15)
- **CR-3:** `r_runaway_bot` returns to `rtd_sense_n_ext` (J3.3), not selv_gnd, and the window branch now taps J3.2. The comparator then compares V(S+) − V(S−) with k (V(BIAS) − V(S−)), so the FORCE− lead and the MAX31865's internal FORCE− switch drop out of the trip. `controller_calcs.py runaway()` (analytic, 256 corners: divider and Rref tolerance + TCR, VBIAS 1.95–2.06 V, Vos ±5.75 mV, leads 0.9–1.1 × 1.80 Ω, FORCE− switch 0.5–20 Ω, unspecified by the vendor so swept) gives **298.8–323.1 °C** (nominal 310.8 °C); the sensor-r3 circuit solve on the as-built values gives 299.2–321.9 °C. Gate: above 250 °C max setpoint + 5 K + 15 K, below the bond's 325 °C. Supersedes open item 4's DEFAULT band (296.6–319.1 °C, which assumed 0–1 Ω leads and no switch; the captured circuit was 237.5–316.3 °C with the C1 leads).
- **CR-5:** U40 TLV3201 compares `rim_filt` (the 104GT-2 node behind its 10 k / 100 nF filter) with v3v3 × 10 k / (86.6 k + 10 k) (RT0603BRD0786K6L / RT0603BRD0710KL, 0.1 %): high = rim hotter than the trip point, or the NTC shorted. U41 SN74LVC1G32 ORs it with the RTD runaway comparator into `RUNAWAY_FAULT` (the interlock has no free input). `controller_calcs.py rim_trip()` (64 corners: R25 ±3 %, B ±2 %, resistors 0.1 % + 25 ppm/K, Vos referred to 3.135 V, self-heating 1.7 K) gives **262.1–288.3 °C** (nominal 275.6 °C); sensor-r3's figure is 262.3–288.1 °C.
  - An **open** rim NTC reads cold and does not trip (the firmware's rim-open rule in sensor-r3 item 5 covers it).
  - **Fit condition** (sensor-r3): enable only after bench T3 logs the rim maximum under a 250 °C hold at or below the band's low end − 10 K. Until then the 86.6 k can be left unfitted; the comparator then reads the rim as cold.
- **Verifier:** `trip` now checks the window branch on J3.2, the divider on J3.3, the two-stage path from RTDIN± to J3, and the rim comparator's inputs. The PERMIT simulation carries `u_rim_trip` as a source with healthy level 0. `trip_sim.Sim` evaluates the gates in topological order and the trip check simulates only PERMIT's fan-in cone, so the exhaustive enumeration (now 2¹⁴ source states with C39, 262 144 cases) stays at about 15 s.

## C39. Hardware capacitive-mode detector (native-21 OPEN-ITEMS S14; 2026-10-15)
S14: the S4 body-diode edge breaks the IPW65R018CFD7's reverse-diode dv/dt and diF/dt ratings, and the software latch lets 370–740 S4 edges per leg through before it acts. The controller already has both inputs (the leg-A PWM commands and `ct_zc` on J4.13) and a free interlock fault input (OVP, tied healthy until now). So the detector needs no J4 change and nothing on native-21.
- **Circuit:**
  - U45/U46 SN74LVC1G14 invert the MCU-side `pwm_ha` / `pwm_la` commands, so each flip-flop clocks on a turn-off command.
  - U43 SN74LVC1G86 XORs `ct_zc` (J4 side, ahead of its series resistor, so the MCU pin cannot mask it) with a polarity strap. The strap is fitted as 0 Ω to selv_gnd (non-inverting), with a 100 k pull-up as the alternative.
  - U42 SN74LVC74A: FF1 samples CM_ZC at the HS turn-off command and FF2 at the LS turn-off command. Inductive operation has current > 0 at HS turn-off and < 0 at LS turn-off (firmware convention: CT_ZC high = current positive). A capacitive sample sets 1Q̄ (HA) or 2Q (LA).
  - U44 SN74LVC1G32 ORs them into `CAP_FAULT` → `interlock.ovp_fault`. The interlock latch holds the trip, so the detector itself re-samples every edge and needs no latch.
  - RUN_EN low presets FF1 and clears FF2 to their healthy states. RUN_EN low already forces PERMIT low, so this adds no path to PERMIT; the trip check confirms that RUN_EN still feeds only the PERMIT gate in the cone.
  - Read-backs 1Q / 2Q̄ go through 10 k to expander P00/P01 (`CM_HA_OK_RB`, `CM_LA_OK_RB`), so firmware can name the cause.
- **Verified (`verify_controller.py` section `capmode`, 27 checks):** structure from the netlist, then a sequence simulation of the captured gates (16 points per period). Results:
  - inductive 1–89° never faults;
  - capacitive −1 to −89° faults on the first turn-off edge;
  - a one-period capacitive excursion gives a fault pulse of one period (≥ ½ period required, against the LVC1G74's 2.7 ns minimum CLR width);
  - RUN_EN low clears it and holds it healthy from the power-up fault state;
  - a stuck CT_ZC (either level) faults within one period;
  - a reversed CT faults with the fitted strap and runs with the strap swapped;
  - the fault outputs are in PERMIT's fan-in cone, and the PERMIT simulation treats U42 as a free source (healthy 0).
  
  New mutation tests cover tied-off CAP_FAULT, swapped clocks, a removed strap and RUN_EN on the wrong asynchronous pin.
- **Timing (`controller_calcs.py capmode()`):**
  - The maximum chain from the HS turn-off command to native-21's DIS pin is **218 ns**: TI maxima at 3.3 V ± 0.3 V, 74HC30 bounded by its 2.0 V figure (165 ns), 10 ns harness allocation, native-21's LVC1G00.
  - Native-21's dead time is 408–569 ns (2EDR8259X, R9/R17 49.9 k). The partner's gate reaches the 1.9 V hot Vth screen 79 ns after it starts to rise, conservatively: the gate-loop L from the extracted leg B21 matrix (LS 46.85 / HS 55.66 nH, `inputs/native-21/legB21-h0-best.matrix.txt`, from f4ed8b17a), R_on 68 Ω −1 % and Cgs 4.7 nF −5 % (candidate 39), +15 / −2 V drive, FET Ciss left out.
  - That leaves **190 ns** for the 2EDR8259X DIS-to-output delay before the partner output starts, or 269 ns before its gate reaches Vth. **The DIS-to-output delay is not in the 2EDR8259X datasheet** (power-stage open item). If the bench finds it within that slack, the first S4 edge is vetoed: zero hard edges. If not, but it is under half a period (8.3 µs at 60 kHz), one hard edge passes. Either way this replaces 370–740.
- **Blind band:** the sample reads `ct_zc` as it was up to 55 ns before the command (TLV3201 tpd max on native-21). A current zero that lands inside the dead time, ≤ 624 ns ≈ 13.5° at 60 kHz, is not seen as capacitive. Partial ZVS loss there stays with the firmware's inductive margin and the S14 software latch.
- **Burst start:** a normalised series-RLC model driven from rest at f/f₀ 1.02–1.8, Q 1–15 never samples a wrong sign in the first 40 edges, so there is no false trip at burst start above resonance. A start at 0.9 f₀ trips on the first edges (the negative control). The smallest correct-sign sample is 0.056 V/Z₀. CT_ZC must resolve that at the first edges: a bench item, with native-21's "zero-cross behaviour with no tank current".
- **Firmware:**
  - start every burst at or above resonance (the 2026-10-03 inductive-side rule);
  - raise RUN_EN only with the PWM idle (RUN_EN rising re-arms the detector);
  - after a trip, read `CM_HA_OK_RB` / `CM_LA_OK_RB`;
  - confirm the CT polarity at bring-up (swap the strap if a reversed CT makes inductive operation trip).
- **Not done:** per-edge vetoing inside native-21, a ZVS-miss detector at the switch node. That would be a power-board change and is not reserved. The detector watches leg A only. At the approved 180° operating point leg B commutates at the same current zeros.

## C40. J12 harness drain and rim-line TVS (sensor-r3 CR-4, CR-6; 2026-10-15)
- **CR-4:** J12 is a **B3B-XH-A** (3-pin): 1 RIM_SENSE, 2 NTC return, 3 harness foil drain, all returns on selv_gnd. The body centre stays at world (126, 86). The 3-pin housing is 2.5 mm wider than R36's 2-pin, so the rim follower U36 moves 1.2 mm left. Enclosure: the harness gets a third (drain) contact (ENCLOSURE-HANDOFF).
- **CR-6:** the RIM_SENSE TVS is **ESD5Z5.0T1G** (VRWM 5.0 V). The ESD5Z3.3 it replaces has VRWM 3.3 V, below the v3v3 maximum 3.465 V that the 1 k pull-up can put on the line with the NTC open. `sensor_io` checks VRWM ≥ the line maximum for every connector TVS, and a mutation test puts the 3.3 V part back.

## C41. No reset/boot control reachable from outside: J11 becomes a TC2050 land (item 4; 2026-10-15)
- **Audit:** the board has **no tactile switch** (EN has its RC; IO0 has its pull-up; there were never buttons). The exposure was **J11**, an unshrouded 1×8 2.54 mm header carrying EN and IO0. A loose XH housing, a ribbon or a tool against the board could short EN or IO0 to ground or between pins in shipping or service, and hold the module in reset or in download mode: the Impulse failure.
- **Change:** J11 is a **Tag-Connect TC2050-IDC-NL** footprint (copper pads + 3 NPTH; KiCad attributes exclude it from BOM and CPL), same signals: 1 3V3, 2 EN, 3 IO0, 4 U0TXD, 5 GND, 6 USB D−, 7 USB D+, 8 GND. Nothing protrudes; programming and USB use a TC2050-IDC-NL cable.
- **Checks (`misc`):** no switch footprint on the board; EN and GPIO0 reach no connector but the TC2050 land; USB 19/20 on the land.

## C42. PERMIT watchdog: the hardware one already exists; no second watchdog (item 3; 2026-10-15)
Question (native-21 S15): does PERMIT need an MCU watchdog for UL 858 25.3.1 (safe with the control dead or stuck)?
- **What is on the board:**
  - PERMIT = latch Q AND RUN_EN (C23).
  - The latch's CLR input includes U21 **TPS3823-33**. Its WDI is the MCU heartbeat (GPIO18) with a **1 k pull-down**. The TPS3823's own floating-WDI behaviour (it pulses itself and never times out: SLVS165O pin table) cannot hide a dead or tri-stated MCU pin. A heartbeat that stops at either level times out in **0.9–2.5 s** (SLVS165O 6.8 t_tout), which latches the fault and drops PERMIT, firmware-independently.
  - RUN_EN has a 4.7 k pull-down, so a reset or hung GPIO matrix also drops PERMIT.
- **Decision: no additional watchdog or PERMIT timer.** A second external watchdog would cover the same failure (no heartbeat). Neither watchdog covers the remaining case: firmware that is wrong but still toggles WDI, such as a hung control loop with a live timer ISR. That case is bounded by firmware-independent trips that act on the hazard itself:
  - on this board: the RTD runaway (C38, ≤ 323.1 °C), the new rim trip (≤ 288.3 °C), the heatsink/coil thermal comparators (C32), and now the capacitive-mode detector (C39);
  - on native-21: R5 Kelvin OCP, U7 OVP, the bias heartbeat, the CT trips and the **TCO loop**, which S15 names as the 25.3.1 backstop.
- **Firmware rule (to the firmware owner):** WDI is toggled only by the supervisor task after it has checked the control loop's progress (sequence counter, RTD read age). Never from an ISR, a hardware timer, LEDC or RMT. The ≤ 400 ms heartbeat stays (inside the 0.9 s minimum).
- The certifier decides whether the TCO plus these trips satisfy 25.3.1; nothing on this board blocks that argument.

## C43. J4 stays 2 × 8: AMC1301 bus-current pins are a documented option only (item 5; 2026-10-15)
temper-8d / coil-driver-r1 asked for an AMC1301 on native-21's R5 shunt, with 2 more J4 pins. Native-21 has not adopted it (OPEN-ITEMS S13: "a later candidate"). **No change.** If it is adopted:
- J4 becomes a 2 × 9 Micro-Fit (43045-1800 class, both ends and the harness), with the AMC1301 OUTP/OUTN pair on the two new pins;
- a differential receiver like D-11's feeds one free ADC1 channel (`verify.json` `adc1_pins_not_analog` lists them);
- one MCU budget line is added.

No copper, pins or parts are reserved now.

## C44. C1 layout, block validators and fab package (2026-10-15)
- **Placement:**
  - The capacitive-mode detector (U42–U46, R1/R2 follow) moved out of the MCU-to-J4 signal bus to the free front-edge field right of the X65 hole (X 76–90 / Y 21–27); the board text moved from X98 to X115. In the bus (first placement) the board routed once, but the next run left UI_CS_OLED_N open after all repairs, and a gridroute `--eco` plus `route.py --continue` then left EXT_ADC_CS_N open.
  - The runaway divider and six RTD resistors are pinned at their C36 poses (U41 in the column had pushed r_runaway_top to 7.8 mm from L2, under the 10 mm partition gate).
  - The 499 k pull-ups sit outside the hole keep-out's shadow: run 1's `rtd_sense_p_ext` route along the right edge gave 10 copper-to-edge errors.
- **Board:** make.py ALL GATES PASS on one clean-start run: DRC 0 / 0 / parity 0, 36 warnings; DFM PASS; 13/13 layout checks; gerbv PASS. Routing robustness for C1 is **not** re-proved: the three-run convergence (2–3 h per run on this board) was not run then (open item 20; done in C47, 3/3).
- **CPL:** the audit was rerun with the 7 new LCSC codes. U42 SN74LVC74APWR is CORRECTED +270° (geometry and DB agree) and folded into `CPL_ROTATION_OFFSET`. U43 SN74LVC1G86 (geometry 180 vs DB 270) and D7 ESD5Z5.0 are NEEDS-PREVIEW, with the other SOT-23-5 logic. Rref (C4260028) has no EasyEDA footprint; it is a symmetric 0805 passive, OK.
- **Block validators:**
  - The RTD binder aborted on the C37 census, and would already have aborted on C36's `r_avdd_top` swap. It now takes a declared-deviation file (`evidence/block-validators/rtd-deviations-c37.json`): 16 extra parts, 4 MPNs, 6 pad-net moves. It relaxes only the binder's own gates; a stale entry aborts, and Rust gets the unmodified export.
  - Result: interlock 69 / 6 / 5 (+ the HC30 MPN, W6), thermal 88 / 9 / 7, RTD 5 / 33 / 5 (+15, W7).
  - Making the RTD unit's contract accept the C37 filter is a change request to `zapote/rtd`.

## C45. Heatsink ADC divider after the follower (sensor-r3 CR-8; owner-approved 2026-10-15)
Source: `sensor-c1-impulse-mining:output/temper-sensor-r3/firmware/DECISIONS.md` D-HSNTC "CR-8", with `hs_ntc.py` / `cold_soak.py`.

**Problem:** as built, HS_ADC was the U6B follower of HS_SENSE through 100 Ω / 100 nF. That node is above the ESP32-S3's calibrated 2900 mV (ATTEN3) whenever the sink is below about 32 °C with nominal parts (`hs_adc_divider()` `as_built_node_over_2v9_below_C`; sensor-r3 gives 28.6–35.7 °C over tolerances). So firmware cannot read room temperature, and the cold-soak Pt100 leakage check (D-SOAK) cannot run in a normal kitchen.

**Change:**
- `r_hs_adc` (follower to HS_ADC) is now **1.00 k 0.1 %, RT0603BRD071KL**, replacing the 100 Ω.
- New **`r_hs_adc_bot` 5.90 k 0.1 %, ERA-3AEB5901V**, from HS_ADC to selv_gnd.
- `c_hs_adc` 100 nF stays at HS_ADC.
- Both MPNs were already on the BOM: C37's filter resistor and the RTD window's `r_high_top`.
- The divider replaces the old RC rather than sitting in front of it. The 1.00 k isolates the op-amp from the 100 nF better than the 100 Ω did, and a divider before the RC would only have added a part.

**Gain, for firmware `adc_gain`:**
- Nominal **0.855072** (5.90 / 6.90).
- Band from 0.1 % tolerance: 0.854824–0.855320.
- With ±25 ppm/K over the board's −40…85 °C (65 K): **0.854421–0.855722**.

**Checks (`controller_calcs.py hs_adc_divider()`; `verify_controller.py` section `hs_adc`, 9/9; 3 mutation tests):**
- ADC maximum at −40 °C: **2.877 V < 2.900 V**. Corner: rail 3.367 V, NTC R25 +2 % and β +1.5 %, hs_fixed −1 %, TLV9062 Vos +1.6 mV, gain high corner.
- ADC at 150 °C ≥ 0.386 V.
- Source to the SAR: Thevenin 855 Ω with 100 nF, τ 85.5 µs. The continuous ADC1 pattern samples HS at 8.9 ksps (every 112.5 µs); the driver's 8 samples per 100 ms is far slower.
- Sampling error: worst case 0.44 mV DC + 0.16 mV residual kick = **0.028 K at 95 °C** (21.1 mV/K). This assumes a 20 pF sample capacitor (Espressif does not publish it) and a 2.9 V swing from the previous channel. The old 100 Ω had less source error, but it read out of range below 32 °C.
- Follower load 0.49 mA.
- HS_SENSE net check: its passives are exactly hs_fixed, the thermal block's node filter cap and r_hs_filt, plus the hot comparator IN− (TLV3201) and the open comparator IN+ (TLV9031). **The C32 ladder is unchanged:** 95 °C firmware < 101.4 °C hardware, band 98.3–104.6 °C; `thermal` 11/11 is unchanged.

**Single faults:**
- **Bottom open, or top shorted:** the gain becomes 1.
  - At a true 95 °C, firmware reads **86.1 °C (−8.9 K)**, and its 95 °C trip fires at a true 103.3 °C.
  - The hardware hot comparator is on HS_SENSE, upstream of the follower and divider and independent of both. It trips at 98.3–104.6 °C, and at the 104.6 °C corner Tj ≈ 132.4 °C ≤ 135 °C (C32). **The fault is covered.**
  - It is also visible: with gain 1, HS_ADC exceeds 2.9 V whenever the sink is below about 32 °C, so it shows at a cold start (open item 22).
- **Top open, or bottom shorted:** HS_ADC reads 0 V, which firmware takes as hot (above 150 °C), so it fails safe as a nuisance trip.

**Placement:** `r_hs_adc_bot` is anchored at the module's HS_ADC pad beside `r_hs_adc` (`floorplan.py` ANCHOR).

**Board (one clean-start make.py run, ALL GATES PASS):**
- DRC 0 errors / 0 unconnected / parity 0, 35 warnings; JLC DFM PASS; 13/13 layout checks (partition 10.5 mm); gerbv PASS.
- CPL audit: R89 / R90 are OK (two-pad passives), 284 lines.
- Block validators unchanged from C44: interlock 69 / 6 / 5, thermal 88 / 9 / 7, RTD 5 / 33 / 5. No new waiver: the divider is outside the thermal block, and its mapping shows 70 pads, 0 moved.

**Not changed (coordinator):** the CR-5 rim-trip resistor stays 86.6 k (open item 21).

## C46. MAX31865 high threshold word is 35544, not 35542 (2026-10-16)
C37 called 35542 right and CR-7's 35544 wrong ("233.22 Ω, outside the 233.21 Ω window"). **That was an arithmetic slip.** Word 35544 is code 17772, which is 17772 × 430 / 32768 = **233.2141 Ω**, not 233.22. The "window" was only CR-7's two-decimal print of R(360 °C).

**From first principles** (`controller_calcs.py max31865_thresholds()`, in verify's `calcs` check):
- R(360 °C) = 100 × (1 + 3.9083e-3·360 − 5.775e-7·360²) = **233.2144 Ω** (IEC 60751 Callendar–Van Dusen).
- Code = 233.2144 / 430 × 32768 = **17772.022**.
- The MAX31865 compares inclusively (high fault when the RTD code ≥ the threshold). The repo's own validator encodes it the same way: zapote-erc `ERC.RTD.FIRMWARE_THRESHOLD_ENCODING` expects an "inclusive floor" high word and an "inclusive ceil" low word.
- So the high word is floor(17772.022) << 1 = **35544**:
  - 35544 trips at **359.9992 °C**.
  - The next word, 35546, would trip above 360 °C.
  - 35542 trips at 359.9616 °C: also safe, but 0.04 K early, and it is not the validator's encoding.
- The low word for −40 °C (84.2707 Ω, code 6421.82) is ceil → **12844**, which trips at −39.994 °C.

**Changes:**
- C37's firmware note and open item 18 now say 35544.
- The board's `checks.py` already used the exact R(360 °C) and printed 35544 (`checks-as-built.json`); no window constant existed in code.
- New calcs checks: the high word is 35544, it trips at or below 360 °C, and the next word would trip above it. Firmware, sensor-r3 `cr7_thresholds.py` and this repo now agree.

## C47. Routing convergence on the C1 + CR-8 board: 3/3 (closes open item 20; 2026-10-16)
`python3 layout/convergence.py --runs 3`. Each run starts with `pcb/route/` moved away; no other writer was active in the worktree.

| Run | Exit | Wall time | DRC errors / unconnected / parity | Warnings |
|---|---|---|---|---|
| 1 | 0, ALL GATES PASS | 5867 s | 0 / 0 / 0 | 42: connection_width 26, silk_edge_clearance 14, lib_footprint_mismatch 2 |
| 2 | 0, ALL GATES PASS | 3670 s | 0 / 0 / 0 | 35: connection_width 19, silk_edge_clearance 14, lib_footprint_mismatch 2 |
| 3 | 0, ALL GATES PASS | 3319 s | 0 / 0 / 0 | 34: connection_width 18, silk_edge_clearance 14, lib_footprint_mismatch 2 |

- The committed board is run 3 (sha256 `77ed3751…`), with its fab package regenerated by that run. JLC DFM PASS: 1074 vias, 4314 tracks. 13/13 layout checks; partition 10.5 mm. gerbv PASS.
- The placement is unchanged from C45, so the BOM, the CPL and the CPL audit are unchanged.
- Block validators on all three boards: interlock 69 / 6 / 5, thermal 88 / 9 / 7, RTD 5 / 33 / 5. These are the same verdicts, all waived (W1–W7).

## C48. Prototype order package; U4 goes to JLC as SMD (2026-10-17)
- `ORDER.md` is the package: upload files with their sha256, board options, the consign list, checks before paying, open items that do not block fab, and quantity.
- It was built with `tools/verify_controller.py` (PASS) and `layout/make.py --no-route` (ALL GATES PASS) only. No re-route; the board is still C47 run 3.
- The gerbers, zip, assembly PDF and `drc.json` from `--no-route` differ only in date lines, so the committed files are kept.
- **Fix:** `layout/fab.py` used to mark a footprint THT whenever it had a plated hole, so the WROOM module U4 (SMD, 12 plated thermal vias in its ground pad) was listed as `THT`. It now uses the footprint's own type.
  - The BOM and CPL change on that one line only: 275 SMD / 9 THT.
  - The CPL audit was rerun with the same DB (sha256 `fce26b89…`): 16 CORRECTED / 224 OK / 44 NEEDS-PREVIEW.
- **Consign:** only RG2012V-431-W-T1 (R39), 1 per board + 2 spares. Nothing else is below 2 × a 5-board build in the repo snapshots of 2026-10-12 and 2026-10-15 (`evidence/order/order_table.py`). Parts are USD 65.32 per board at JLC quantity-1 prices.

## C49. J13 rail merge and BIAS_GOOD on J4.1: branch `controller-j13-merge` (2026-10-18; power-stage CONTROLLER-REQUEST items 1, 2, 11, 12)
- **Change (elec):** PS1 is gone on the power board, so the logic rail `v15_selv` is fed from `V15_BLW` (J13) through `D9` (SS14, 40 V 1 A, LCSC C2480). J4.1 is no longer a 15 V input: it is `bias_good_j4` from the power board (U40 through its R146 220 k), read on GPIO35 through `R124` 10 k with `C97` 1 nF C0G and `R123` 1 M to `selv_gnd` at the pin. `RAIL_OK_RB` moved from GPIO35 to expander P02 (U9 Y1_4 still buffers it). **No TVS on this input** (first built with an ESD5Z3.3; removed): its leakage is specified at 25 °C only (50 nA max, onsemi ESD5Z series table), and a hot TVS (10-100x) would pull the high level through the 220 k + 10 k source below VIH. Like the other J4 lines it has none; 15 V on J4.1 from a pre-stage-38 power board is limited to about 1.5 mA by the 10 k into the pin's own clamp (accepted).
- **Designators:** the four new parts carry explicit high designators (D9, R123, R124, C97). Without them the auto-numbering shifted 141 existing designators, and ORDER.md's R39 (Rref) pointed at another part (independent review, MAJOR 1). No existing designator changes.
- **Calcs (`controller_calcs.py`):** `merge_rail`: logic rail at least 13.9 V at the worst corner against a buck start of 12.1 V; PS3 total 44.55 W against 65 W, and 99 % of the 45 W 60 °C derated figure (the IRM-60 curve; the MPM-65-15ST curve is not read yet). `bias_good`: high level 0.82 x VDD against VIH 0.75 x VDD; open reads low; tau about 190 us (the firmware README's BIAS_GOOD design).
- **Independent review MAJOR 2 (a blower fault can reset the controller): reduced to a bench item with datasheet numbers (2026-10-18).** Read: MEAN WELL MPM-65-SPEC 2024-10-30 (overload hiccup at 115-135 % of 65 W = 4.98-5.85 A at 15 V; 15 V derating 100 % to 50 °C, 80 % at 60 °C, 50 % at 70 °C; peak 4.77 A / 71.6 W for 10 s at <= 33 % duty; hold-up 12 ms at 115 VAC; setup time 1000 ms) and TI SLUSEA4D (t_SS = C_SS x 0.8 V / I_SS, I_SS 4.5-6.5 µA, so 10 nF gives 1.1-2.0 ms; IHS_LIMIT 4.2-5.8 A; UV hiccup off 10.5 x t_SS). `tools/ps3_loss_sim.py` (in `verify_controller`, `blwin`): the merged continuous load is 44.55 W = 69 % of rated, 86 % of the 60 °C derated 52 W, and the PS3 derating allows 63.8 °C ambient (the enclosure request is <= 58 °C). PS3 trips only if the 12 V load draws about 4.96 A at 12.4 V, 1.84 x the fan's 2.70 A rated maximum; the earlier "start at U2's current limit" bound (3.96-5.46 A) was a bound on the buck, not on the fan, and used the IRM-60 4.6 A point. Soft-start charging the output capacitance adds only 0.22-0.39 A, so `c_ss_12` stays 10 nF. If PS3 does lose power (hiccup, mains dip longer than the 12 ms hold-up), the logic rail holds 0.87 ms, the buck then stops and v3v3 reaches the driver VDDI UVLO within 15-31 µs: the drivers' outputs go low before the MCU browns out. It fails safe (no auto-restart), but the unit stops. **Still open (bench):** the fan's start / lock current and PS3's hiccup on/off times are in neither datasheet. Item 5 of the request (scope the logic rail during blower start and PS3 overload) stays. **Reverses if** the fan draws more than 4.96 A at start.
- **Firmware:** `controller_pins.h` and the n21 hardware layer follow (`CTRL_GPIO_BIAS_GOOD_RB` 35, `CTRL_EXP_RAIL_OK_RB` 2); the guard `firmware/tools/check_controller_pinmap.py` passes against this branch's `controller.ato`. This firmware does not match the C48 controller.
- **Verification:** `verify_controller.py` PASS with J4 pin 1 expected as `bias_good_j4` (the pinned 2026-10-08 native-21 snapshot still has PS1's 15 V there; refreshing the snapshot breaks the v3v3 load model, which does not know the stage 29+ parts: a follow-up). The layout results follow in this entry's addendum.
- **Layout (addendum, 2026-10-18):** one clean full `layout/make.py` run routed with 0 open nets after earlier runs left 1 and then 6 open (the router varies run to run: DECISIONS C34's 3/3 convergence was for the C48 netlist; it was **not** repeated for this one). DRC 0 errors / 0 unconnected / parity 0, 34 warnings (as C48); interlock, 14 layout checks, JLC DFM and gerbv pass. The first run put the 1 M pull-down inside the PERMIT-gate keep-out box (the interlock check caught it); the four new parts now sit beside U4 (BIAS_GOOD, three parts) and J13 (merge diode).
- **New gate: stranded vias** (`layout/via_hygiene.py`, check 14 in `check_layout.py`, a strip step in `make.py` after the DRC). It found 3 on the committed C48 board (a ground via between J12 pads 2 and 3 touching no copper, and single-layer stubs on `rtd_healthy` and `PERMIT_RB`) and 1 on this board; `make.py` now removes them (a via on fewer than two layers carries nothing, so no net opens) and re-runs the DRC. The C48 board still has its three.
- **Fab package:** regenerated for this board (`ORDER.md` carries the new hashes; BOM 89 lines, CPL 288 placements). D9 (SS14, C2480) must be checked in JLC's CPL preview (polarized, new footprint).

## C50. Decision: the first controller order is the C49 (J13-merge) board, not C48 (2026-10-18, owner delegation: "can you drive that decision")
- **Decision:** order `controller-j13-merge` (C49) for the prototype lot. Ordering itself stays the owner's purchase; this records which package to use. `ORDER.md` now describes the C49 board (BOM 89 lines, CPL 288, USD 65.35 per board in parts, 83 extended lines).
- **Why:** the power board (s48 and later) has no PS1 and drives BIAS_GOOD on J4.1. C48 cannot be powered by it (CONTROLLER-REQUEST addendum 3) and would need a bench 15 V on J4.1, firmware rolled back to before `0550fffcf` (GPIO35 is RAIL_OK_RB there; the BIAS_GOOD checks read NOT_FITTED), and a second controller spin to reach the real design. C49 matches the power board, the firmware and the end design, and the firmware's BIAS_GOOD interlock checks run on it. The routing risk is bounded: the ordered board is one fixed DRC-clean file.
- **Accepted risks (bench):** (1) a blower fault that drives PS3 into hiccup resets the controller (fails safe); only a fan drawing over about 4.96 A at 12.4 V does it; scope the logic rail during blower start (request item 5). (2) GPIO35 and D9 have not been on hardware. (3) one clean route only, no 3-run convergence for this netlist. The fix for (1) if it bites is a controller re-spin.
- **Before paying:** D9's orientation is checked against JLC's own C2480 footprint (pad 1 = cathode, left, as in KiCad: rotation 0 is right; `evidence/fab-loose-ends/cpl-rotation/D9-C2480.md`), and the preview is the final check along with the other NEEDS-PREVIEW codes; owner approval of the spend. **Done 2026-10-18:** the strict ESP-IDF v5.3.6 build (`firmware/build-evidence/esp-idf/build.sh`, with the hardware binding on so `n21_hw_esp32.c` compiles) passes on the firmware that matches this board (power-stage commit `f0cbab2f0`: 25 platform symbols defined, 0 diag stubs, `induction_cooker.bin` 412,960 bytes). **JLC accepts the Gerbers** (quote page, 2026-10-18: detects a 4-layer 76 x 206 mm board, 5 pcs bare about USD 34.70 before assembly, shipping extra); the PCB Assembly step (BOM / CPL upload and the 3D preview) was not reached: the browser automation was blocked at the PCB Assembly toggle, so the CPL preview is still the owner's. **Stock re-read 2026-10-18** (JLC parts API, `evidence/order/stock-read-2026-10-18.json`): all 89 lines matched their LCSC codes and 88 have stock of at least 2 x the need for 5 boards; the one exception is R39's RG2012V-431-W-T1 (C4260028, stock 0), the part ORDER.md already consigns or marks do-not-place. Read again on the day you pay.
- **Reverses if:** the CI IDF build fails on the controller-pin edits in a way that needs a pin change, or a stock read shows C2480 / C105578 unavailable with no equivalent.
- **Convergence (addendum, 2026-10-19): this netlist closes on 1 of 3 clean runs** (`evidence/convergence-c49.json`, `layout/convergence.py --runs 3` in an isolated worktree). Run 1 ends ALL GATES PASS (0 open, DRC 0 errors, 44 warnings, 3917 s); runs 2 and 3 each leave 1 net open (DRC not clean, 4571 s and 5593 s). C48's 3/3 (C47) does not carry over: the router is less reliable on this board than it was on C48, probably because the BIAS_GOOD parts now sit beside U4. The committed board is a fixed, verified file from a passing run, so the order is unaffected; a future spin or any re-route of this netlist should not count on closing first time.
- **JLC preview (addendum, 2026-10-19; owner flipped the PCB Assembly toggle, I drove the viewer):** JLC accepts the Gerbers (4 layers, 76 x 206 mm), matches 88 of 89 BOM lines, requires **Standard PCBA** (83 extended part types, U4 Standard Only), and shows the NEEDS-PREVIEW parts wrongly rotated as first uploaded (U11 U12 U16 Q1 by 180, U3 by 90). D9 is correct at 0. `layout/fab.py` now applies the audit's geometry offsets to those codes (34 CPL rotations; new CPL sha256 `799bf9566663ff8f60242532c232115a95f0cc4f9ed452ed88a3d7024d6657d1`); the viewer then agrees on U11 U12 U16 Q1 and C9. This supersedes the earlier "D9 expect 180" note and the C50 statement that the preview was the owner's alone: the owner should still re-check the codes listed in `PREVIEW-2026-10-19.md`.
- **JLC preview, later the same day:** a large-zoom pass confirmed pin-1 agreement on 16 parts across all the corrected IC and diode codes (list in `PREVIEW-2026-10-19.md`). It also showed the first fix was too broad: with the geometry offset the right-angle Micro-Fit J4 body hung off the board edge, so the THT connectors J1 J2 J3 J4 J7 are back at KiCad's rotation (29 rotations changed, CPL sha256 `2327ec703cd241ee096b4f687d8c01d75f4d71893b833a98193fda6f53465473`) and still need an owner look in the preview. The browser extension disconnected before I could re-check J4 after the revert.

## C51. Food-probe RTD, bay NTC, R45 face fan; U30 land fixed; snapshot moved to stage 56 (2026-11-25, branch `controller-c51`; circuit only, no layout yet)
- **U30 could not have been soldered on C48 or C49.** MAX31865AAP is the 5.3 mm SSOP-20 (JLC C89608 and C779509: `SSOP-20_L7.2-W5.3-P0.65-LS7.8`; DigiKey lists 20-SSOP 0.209 in, 5.30 mm wide). The library carried the 3.9 mm QSOP land, so the pad rows are 0.89 mm in from the leads. The CPL audit printed that misfit and used it only to choose a rotation, and U30 is not among the parts the 2026-10-19 JLC preview record names. The vendor's own package drawing was not reachable on 2026-11-25; the evidence is JLC's pads and the distributor listing. `ORDER.md` on `controller-j13-merge` says do not order.
- **Gate:** `tools/check_land_patterns.py` compares every fitted part's pads with JLC's pads for its LCSC code (RMS limit 0.30 mm; no record or different pad numbers fails; 3 named exceptions, a stale exception fails). It compares pad centres only. 94 of 96 parts compared.
- **MAX31865 ordering code:** `MAX31865AAP+T` (C779509, 2,141 in stock, USD 7.92) for both channels. The tube code `MAX31865AAP+` had 22 at USD 12.79.
- **Food probe (J9):** 4-wire Pt1000, second MAX31865 (U50) on the RTD SPI bus. CS# on expander P06, DRDY# on P05.
  - Every SPI line has 1 k at U50 and the supply has its own bead, so a damaged plug-in channel, or a CS stuck low (it hangs on I2C), leaves the pan converter readable. The pan channel, its window comparators and its rail monitor are untouched (`c51.food_shares_only_listed_nets`).
  - Rref is 4.30 k 0.1 % 25 ppm (stocked). Worst case 0.1 % is 0.37 K and 25 ppm over 60 K is 0.55 K at 100 C; an ice-point offset in firmware removes the first. Open-lead pull-ups are 1 M, whose 1.1-2.6 K loading firmware must remove (the 1 % tolerance leaves 0.03 K).
  - Entry capacitors are 100 nF, not CR-1's 220 nF: at 4.3 k the filter would not settle in the 5.5 ms manual-cycle step (5 tau is 4.74 ms with 100 nF, over 5.5 ms with 220 nF).
  - **J9 is 4-pin, not the plan's 5-pin.** A 5-pin XH (14.9 mm) at X -33 overhangs the board edge and does not fit beside J2. The M12 shell bonds to the chassis at the wall. The 4-pin body needs J9 moved 1.5 mm (proposed centre X -31.5): an enclosure request for R45.
- **Bay NTC (J14, R45-BAY-NTC):** takes the old M12 divider, U7B and GPIO8. Pull-up 47.0 k, not the plan's 10 k: the slope at 61 C is the same 27 mV/K, and an open lead stays apart from a cold bay (0 C reads 2.92 V, open reads 3.30 V; with 10 k the 25 C node is already past 2.9 V). J14 is a JST PH: every other 2-pin header is an XH thermistor lead, and a swapped coil lead would defeat the coil trip.
- **Face fan (J15):** fixed 12 V TPS62933 (U51, 11.80-12.20 V) from V15_BLW, EMC2301 (U52, 0x2F) on the internal I2C, ALERT# on P17. No ESP32 pin.
  - PWM reaches the fan through a cascode BSS138 with its gate on v3v3. The fan's 5.25 V pull-up would exceed the EMC2301's 3.6 V-above-VDD limit whenever v3v3 is off (DS20006532A p. 3). With v3v3 off the fan sees an open line, which is full speed.
  - **The EMC2301 does not start the fan by itself:** drive is 0 at power-up and goes to 100 % after 4 s without a Fan Setting write (section 4.11). That watchdog runs once. Firmware must set WD_EN for continuous operation, and must not count on stall detection while the watchdog is active. An MCU hang then gives full speed within 4 s.
  - J15 is 5-pin. A 4-pin XH would let a fan lead carry 12 V into J3 or J9 (`c51.j15_header_is_unique_on_the_board`).
  - The 8 W fan figure is an allocation: no fan is selected.
- **PS3 must be the MPM-90-15ST.** With the face fan PS3 carries 53.4 W against 50.1 W derated for the MPM-65 at 61 C: it does not fit. The MPM-90 (MPM-90-SPEC 2024-10-30: 85.05 W, 75 % at 60 C and 50 % at 70 C on the 100 VAC line, read from the graph) gives 61.7 W at 61 C and 54.2 W at 3000 m (3.5 C per 1000 m above 2000 m, note 7), where 0.8 W is left. Same 109 x 52 x 33.5 mm ST case (Case IRM60), touch current < 100 uA, hold-up 10 ms typ at 115 VAC (MPM-65: 12). Its overload trips at 97.8 W or more, so the blower would have to draw 5.91 A; U2's own limit is 5.8 A at most, which closes C49's accepted risk 1 at these corners (the margin is 0.1 A).
- **Snapshot:** `inputs/native-21` is now stage 56 (`f0c669a86`), so all 16 J4 pins compare with the board of record. The four parts that blocked this are modelled with the power board's own census figures. J4.3 is 27.7 mA here against that census's 36.7 mA; the difference is the U46 pump's switching peak (DC budget here, peak there). The rail at native-21 is 3.239 V at the low corner; 9 mA more changes the drop by under 1 mV.
- **CT at stage 56:** 3 ohm / 1:200 keeps 15 mV/A. CT_MON stays inside ATTEN3 at the 79.32 A trip corner (0.46-2.84 V). **The MCP3202 RMS channel saturates at 76.4 A peak,** below that corner; the trip itself is hardware on the power board.
- **R39 stays RG2012V-431-W-T1, consigned.** JLC has 0 of it and 0 of the other 0.05 % or 10 ppm options read (RG2012N-431-W-T1, TNPW0805430RBEEA, RT0805BRB07430RL). RT0805BRD07430RL (0.1 %, 25 ppm) is stocked and is the CR-2 regression C37 reverted.
- **Stock reader:** `fetch_stock._jlc("", mpn)` accepts the first search hit because an empty code is a substring of every URL (`c1-crs/fetch_new_parts.py` calls it that way). `evidence/c51/read_parts.py` requires the exact MPN.
- **Food-probe unplug (review catch, checked 2026-11-25, `rtd_food_unplug`).** A full unplug opens FORCE+ too: REFIN- is above 0.85 VBIAS 0.9 ms later (Rref x 110 nF), well inside the 5.5 ms step, so firmware needs no 250 ms wait for it.
  - The reference current is then zero, so the RTD code carries no temperature after the unplug. Firmware must use the fault cycle's D5 bit, not the code.
  - A single open sense lead is the slow case: 124 ms (SENSE+) or 72 ms (SENSE-) to leave the proposed window, code ratio 0.20-0.55 (about -36 C to 380 C), set when the firmware is written. The review's 100 ms omitted the filter capacitors, which the open lead also charges.
- **J9 clamps are BAV199-7-F (D10-D13, to RTD2_AVDD and ground), not ESD5Z3.3.** ESD5Z3.3 leakage is 50 nA max at 25 C and not specified hot (ESD5Z2.5T1/D Rev. 16). At Pt1000 current (about 0.37 mA) pin leakage on FORCE+ and SENSE+ reads low by 0.7-1.9 K at 0.5 uA per pin and 7-19 K at 5 uA (0-300 C), and 1.1 uA hides an open SENSE+. BAV199 is 80 nA max at 150 C (DS30232 Rev. 12-2; Philips agrees): at most 0.31 K at 300 C, 0.17 K at 100 C.
  - **Layout rule:** C112-C115 sit at J9, between its pins and D10-D13, so the capacitors take the ESD impulse ahead of the clamps (BAV199 has no IEC 61000-4-2 rating).
  - **C143 10 uF on RTD2_AVDD** takes the clamps' ESD charge: 8 kV / 150 pF is 1.2 uC, 0.24 V on 5 uF, so AVDD reaches about 3.7 V from a 3.465 V rail (VDD abs max 4.0 V, MAX31865 datasheet, not re-read here). BAV199 has no IEC 61000-4-2 rating (4 A for 1 us); the metal-sheathed probe's contact discharge is a bench item.
  - The same question on the pan channel is a tenth as large (about 3.7 mA, so 0.07-0.19 K at 0.5 uA) and its TVS stay.
- **Fan and PS3:** the candidate fan (9GA0612P6G001, 3.12 W on the maker's page) would cut the PS3 load by about 5.4 W against the 8 W allocation (6.2 W instead of 0.8 W left at 3000 m). The 8 W allocation stays until a fan is selected, with an h study behind it.
- **Layers (decided): four layers first.** C51 is routed only after R45 agrees J9 / J14 / J15. If fewer than 2 of 3 runs converge, C51 goes to six layers: `gridroute.py` signals F, In2 and B, and six layers needs two more signal layers there. Cost, stackup (the review names JLC06161H-3313) and the effect on thermal and RF checks have not been read.
- **s56 lands:** 15 of the 26 lines without JLC geometry now compared and pass (power stage `c58-s56-lands`); 11 remain, plus F1 and BR1, which have no JLC code.
- **Not done:** layout, routing, CPL, firmware (P05 / P06 / P17 / 0x2F / 47 k / Pt1000), an independent review, and the enclosure's agreement on J9, J14 and J15. C49's 1-of-3 routing record stands, and U30's larger land will move its neighbours.

## C52. R39 on a stocked 10 ppm/K Rref with CR-2 gate 1b at 0.45 K; four stock swaps; C51 fully JLC-assembled (owner, 2026-11-26)
Owner direction 2026-11-25: JLC assembles as much as possible, near-zero hand soldering. Basis: `evidence/c51/jlc-max-r1/README.md`
(JLC reads 2026-11-26 04:13–04:31Z, commit 2f7887738). Owner decision 2026-11-26: "adopt RESI PTFR0805B430RN9 (C351565) and relax
CR-2 gate 1b to ±0.45 K ... and apply the four zero-risk C51 stock swaps".
- **R39 (pan MAX31865 Rref) → RESI PTFR0805B430RN9, C351565** (430 Ω 0805, B = ±0.1 %, N = ±10 ppm/°C per the RESI ordering
  code; JLC 48,662). It replaces the Susumu RG2012V-431-W-T1 (0.05 %, 5 ppm/K), which had 0 stock at JLC on every read since
  2026-10-12 and no small-quantity source. Same value and land: the threshold words (35544 / 12844), firmware constants and copper
  do not change. Override in `controller.ato` (`rtd_c1_block.ato` stays the library text plus the listed C37 edits).
- **CR-2 gate 1b is ±0.45 K** (was ±0.30 K): `evidence/sensor-r3-checks/checks.py` `GATE_1B_K`. As built: board terms 0.418 K, RSS
  0.408 K at 250 °C (Rref tempco 0.322 K of it, from 10 ppm/K over the gate's 60 K board swing). The sensor-r3 proposal now
  names the 0.1 % / 10 ppm/K Rref, so the as-built comparison reports no difference. Not in the gate: Rref load-life drift (RESI:
  2000 h at 70 °C rated load < 0.01 % typ, < 0.1 % max; R39 runs at about 6.7 mW of 125 mW; 0.01 % is 0.05 K at 250 °C).
- **Runaway trip** (`controller_calcs.runaway`, corners now Rref 0.1 % + 10 ppm/K × 60 K): 298.3–323.6 °C, inside the
  270–325 °C gate, 1.4 °C below its upper bound (was 299.2–321.9 °C with the RG2012V).
- **Firmware still has no CR-2 gain calibration** (`rtd_convert.c` divides by a fixed 430.0). Until it exists, Rref tolerance adds
  directly: 0.54 K at 250 °C for 0.1 % (0.27 K for the old 0.05 %). The 0.45 K gate assumes the single-point calibration.
  Comments in fw-unified `max31865.h:65` and `rtd_convert.h:37` still name the RG2012V (no code change).
- **Stock swaps (BOM only, no net or land change; ratings equal):**
  - C1, C9: Panasonic EEE-FK1E101P (0 at JLC) → **Nichicon UCD1E101MCL6GS, C445471** (772): 100 µF 25 V ±20 %, D8 × 6.2
    (JLC attributes; maker datasheet not read). Changed in `controller_parts.ato` `Cap100u25Elec`. Land fit 0.245 mm RMS
    against the 0.30 mm gate (JLC's land is wider than CP_Elec_8x6.2); polarity stays a JLC-preview item.
  - R47: ERA-3AEB6192V (2 left) → **RT0603BRD0761K9L, C861498** (5,464), 61.9 k 0.1 % 25 ppm.
  - U11, U25, U33, U37: SN74LVC1G08DBVR (36 left, under the 5-board need) → **SN74LVC1G08QDBVRQ1, C840098** (7,990), same DBV
    pinout, tpd max 4.5 ns (SCES556H), so the capmode slack is unchanged. `verify_controller.py` models both codes.
  - R32: RC0603FR-0734K8L (67, falling) → **AF0603FR-0734K8L, C2098331** (31,248), 34.8 k 1 % 100 ppm. EasyEDA has no pad record
    for C2098331 (`evidence/c52/missing.json`), so it is a named land-gate exception on the stock R_0603 land.
- **JLC pads** for the new codes: `evidence/c52/fetch_pro_pads.py` (pro.easyeda.com; the old easyeda.com route 403s), control
  C7666 reproduces the committed record exactly. The RG2012V land exception is removed (stale).
- **Result:** freeze, `verify_controller.py` VERIFY: PASS, land patterns PASS (95 of 97 compared, 2 named exceptions), sensor-r3
  as-built 11/11 PASS with no difference from the change request. With these, no C51 BOM line is consigned or owner-fitted;
  JLC hand-solders the 11 THT connectors. Order-day items stay: pre-order U3, U14, U15; re-read R23/R36/R152 and R31.
- **Reverses if:** a ≤ 5 ppm/K 0.05 % 430 Ω part appears in JLC stock (go back to the 0.30 K gate), or bench data show the board's
  temperature swing from calibration exceeds about 36 K with the PTFR (re-check 1b against the measured swing).

## C53. C51 layout: placement, J9 moved to (43.5, 86), six layers (2026-11-26, owner chose "C51 controller layout next")
- **J9 moves from the C51 request's (-31.5, 86) to (43.5, 86), rotated 180.** The rear-left corner holds about a quarter of the
  food-probe channel: J2, the Ø8 keep-out at (-26, 74), J4 and the interlock block fill the rest. At X43.5 the channel (U50, 4 caps,
  4 BAV199, 2 filter stages, Rref, the 1 k SPI resistors) sits in the free field between J9 and J7. Rotated 180, J9 reads F-, S-,
  S+, F+ left to right, which meets U50 (also rotated 180) at its pin 11 (S-) / 10 (S+) end without crossing the sense pair.
  The R43 corridor check passes at the new spot (free >= 30 mm, need 19.0; plug 17.8 mm from the HOT block). R45 still has to
  agree, and the M12 lead gets about 75 mm longer (ENCLOSURE-HANDOFF "C53 revision"). J14 and J15 stay at the C51 request.
- **Routing before R45 agrees (changes C51's "routed only after R45 agrees").** The corridor check found all three columns free,
  and what R45 still owes (cable routes, ties, retention tests) does not move a connector. A connector move later is a
  `world.py` edit and a re-run.
- **Placement:**
  - Food channel: the 100 nF caps at the J9 pins, the BAV199 row behind them (C51 rule: caps take the ESD first), the first
    filter stage (R1n, C1, R1p) between the two sense clamps, the second stage (R2n, C2, R2p) in the 2.5 mm row at U50's pins
    10/11, the CM caps beside those pins, the 1 M open-lead pull-ups at the ends of that row. The food nets join the RTD analog
    family (F.Cu / In2.Cu only, return via within 2.5 mm) with their own stitch grid (X35-56, Y63.5-89).
  - Face fan: U51 / L3 in the free field in front of the blower buck (U51 at (82, 54)); U52 (EMC2301), the PWM cascode Q2,
    the two ESD diodes and the tach resistors at J15. Pinning R154/R155 kept the blower buck's SS cap and EN divider at U2.
  - Bay NTC: TVS and 47 k pull-up at J14, the 159 Hz RC at its buffer (u_buf2), the ADC RC at the module.
  - U30 moves 1.3 mm forward with C31: its 5.3 mm SSOP land (C51 fix) reached the J3 protection strip.
  - Pan Rref R39 is now anchored to U30 (16 mm away, where C49 had it 24 mm away with no anchor; the space round U30 is full).
- **Gates added (`check_layout.py`):** `rtd_j9_protection` (each line's cap nearer the pin than its clamp; a cap moved behind
  its clamp fails it), and `partition` now holds both bucks (L2/U2 and L3/U51) >= 10 mm from both RTD channels. Fixed:
  `rtd_j3_protection` found J3 by its B4B-XH MPN, which C51's J9 shares; it now uses the designator.
- **First two routes did not close; both faults were placement.**
  - Route 1 (runs 1 and 3; run 2 stopped): one open item each, `rtd_food.adc-cs_n` (U50 pin 16 to its 1 k series
    resistor R135). Anchored to U50, R135 had been put at (36.5, 80.6) beside J9, so its stub crossed the clamp row and
    the food stitch grid. Fix: the four food SPI resistors and the CS pull-up got explicit poses (moving R135 alone let
    the anchor drop R134 into its spot).
  - Route 2 (run 1; runs 2 and 3 stopped): `cs_n` and `sclk` open (pins 16 and 15). The real cause was that U50's
    SPI side (pins 14-17) faced U12 (`u_rail_inv`) 1 mm away, and U12's 3V3 and RAIL_FAULT vias filled the escape.
    That row predates C53. Fix: U3/U11/U12 move left to X 24.8/30/36 (U3 only 2.2 mm, held off U24). R135 sits
    under U50 pins 18-20 (GND, GND, NC), 4 mm from pin 16. U12's cap C57 is pinned below U12 (3V3 pad 3.78 mm from
    pin 5, gate 5 mm), so X 38.1..41.5, Y 66..72 stays free for the escape.
  - Convergence counts route 3's three runs only (four layers); the six-layer board starts its own three.
- **Four layers closes on 1 of 3, so C51 goes to six layers (C51's rule, applied as written).** Route 3, from three clean
  starts on the fixed placement: run 1 left 7 open (`p1` and `refin_n` at U30, `rtd_sense_p_ext`, IL_WDI, RAIL_OK,
  UI_MISO, UI_SCK); run 2 left 5 open (`rtd_sense_n_ext`, RAIL_OK_RB, LATCHED_FAULT_RB, RTD_SDO, rx_a_out); run 3
  passed every gate (6219 s). Summaries: `evidence/c53-four-layer/`. Unlike routes 1 and 2, there is no single
  blockage. Both failing runs level off at 4-10 open through every repair stage (route logs), and half of the open nets are
  long cross-board runs. C49 also closed on 1 of 3 (2026-10-19 addendum), so this is the netlist family's level, not
  a C53 regression. One more placement pass was considered and rejected. U30's pin rows sit 2.2 mm from the WROOM box
  (R33) and under 1 mm from the J3 protection strip, both fixed, so no pan-only move frees its Rref and SPI
  resistors, and it would leave the cross-board nets as they are.
- **Six-layer stack-up: JLC06161H-3313** (jlcpcb.com/impedance, read 2026-11-26): F.Cu signal, In1 selv_gnd plane (3313
  prepreg 0.0994 to F), In2 v3v3 pour + signals, In3 signals (2116 prepreg 0.1088 to In2), In4 selv_gnd plane (new:
  B.Cu now has a reference plane), B.Cu signal. Each core is entered as 0.5708 mm (JLC lists 0.55) so the stack sums
  to 1.6 mm, as C34 did for four layers.
  - The RTD analog family stays on F/In2 over In1, unchanged.
  - In2 sits 0.11 mm above In3 and 0.57 mm below In1, so build_board puts a no-tracks rule area on In3 over both
    RTD stitch regions (vias may still cross). Nothing then runs broadside under an RTD analog track.
  - The router signals F, In2, In3, B. In3 prefers Y, against F's X.
  - C51 expected two more signal layers. This stack adds one, In3, and makes In4 a second selv_gnd plane.
    Two signal layers would leave B.Cu with no reference plane and put two signal layers next to each other a
    second time. The four-layer failures were 5-7 nets, and one more signal layer roughly adds half again to the
    routing area. If the six-layer runs still do not close, In4 becoming a signal layer is the next step.
  - Scripts changed: build_board, export_geom, gridroute, route, check_layout (outline gate:
    `world.COPPER_LAYERS`), jlc_dfm_check (multilayer limits re-read 2026-11-26, unchanged; the six-layer size
    limit was not re-read), fab (six copper Gerbers).
  - **Finish: ENIG, not HASL.** JLC's capability page (read 2026-11-26): "FR-4/HDI boards with 6 or more layers ...
    do not support HASL". JLC's via-covering article (updated 2026-11-10): "For our 6-layer and above multi-layer
    boards, resin filling is now available for free"; the capability page makes epoxy fill-and-cap the default
    for 6+ layers. No JLC page gives an ENIG price, so whether it costs extra is unread.
    The stack-up's `copper_finish` and fab-notes now say ENIG.
  - If these runs do not reach 2 of 3, the first change is In3 to X-preferred DIRPEN (1.0, 2.0, 1.5). The board is
    206 x 76, half the four-layer failures were long X runs, and F is the only X-preferred layer now. In4 to signals
    comes only after that (it costs B.Cu its plane). (Suggested in an outside review of the diff.)
  - Not read yet: the price difference at JLC, and the thermal and RF checks on the new stack-up.
- **The first three six-layer runs were invalid: a router bug, not the board.** They were stopped after 6.5 h at
  rounds 14-15 (evidence/c53-six-layer-invalid/).
  - Symptom: every round started from about 97 open pairs, and each round took 25-35 min against 2-4 min on four
    layers.
  - Cause: gridroute.py's exact check (`Exact.via_ok`) ran `seg_ok` on every layer with that layer's track
    keep-outs. So the new In3 RTD rule areas (tracks not allowed, vias allowed) rejected every via inside them:
    0 of 3000 sampled via spots passed, 1049 pass with the fix.
  - The grid search does allow vias there, as KiCad does. So each round routed about 90 pairs, and the legalise laps
    then discarded 87-99 of them (unchanged from lap 1 to lap 3).
  - Fix: track keep-outs no longer apply to vias; via-forbidding rule areas are still checked through `keep_v`.
  - Guard: gridroute.py exits non-zero when at least 20 routes, and at least 20 % of all routes, still fail the exact
    check after three laps without shrinking. That means the raster and the exact check disagree on a rule, so the
    run should stop rather than go on routing.
  - Convergence restarts from three fresh runs.
- **The second three six-layer runs closed 2 of 3, but every board put current on 0.5 oz inner copper; superseded.**
  - Run 1 passed every gate (21 rounds, 5253 s). Run 2 ended with `coil_buf_out` open (36 rounds). Run 3 passed
    (25 rounds). Evidence: evidence/c53-six-layer-superseded/.
  - Run 1's board had V_BLOWER (>= 1.5 A, C28) 35 mm on In2/In3, v15_selv (fed through D9, SS14 1 A) 76 mm on In3 and
    V15_BLW 29 mm on In3, all on 0.5 oz copper. C49's four-layer board kept V_BLOWER on F/B entirely and had 5.9 mm
    of v15_selv on In2.
  - LAYOUT.md's ampacity case is IPC-2221's external formula on 1 oz copper (0.8 mm: 2.0 A at 10 K). The internal
    formula (I = 0.024·ΔT^0.44·A^0.725) on 0.5 oz gives about 0.6 A for 0.8 mm at 10 K, and 1.1 A at 40 K.
  - `power_widths` checks width only, so it passed.
  - Fix: gridroute.py `OUTER_ONLY` keeps V_BLOWER, sw_12, v15_selv and V15_BLW on F/B. v3v3 is unchanged (In2 is its
    pour).
  - New gate `power_layers` in check_layout.py: no track of those nets on an inner layer. It fails run 1's board and
    passes every other check there.
  - Convergence restarts from three more runs.
- **via_hygiene.py removed connecting vias (fixed).**
  - Run 1 of the outer-only set closed its routing (28 rounds, final 0 open) and its first DRC was clean
    (0 unconnected).
  - The stranded-via strip then removed 4 vias, and the second DRC found 2 unconnected (IL_RESET_N, pwm_hb) and
    4 dangling stubs.
  - Cause: a via counted as stranded unless copper of its net covered the via's centre on 2 layers. KiCad connects
    copper that overlaps any part of the via's pad, and these 0.14-0.42 mm stubs ended off-centre.
  - On the routed board, 3 of the 4 vias had tracks overlapping their pads on 2 layers (IL_RESET_N F/In2,
    RUNAWAY_TH F/In2, pwm_hb B/In2).
  - Fix: the test is pad overlap (`HitTest(pos, via radius)` for tracks, pads and filled zones). On that board it
    finds no stranded via.
  - Run 1's post-route steps were regenerated with `make.py --no-route` from its own routed board; the routing is
    unchanged, so it counts as that run's result. Logs: build/c53-run1-hygiene-fail.log and
    build/c53-run1-noroute.log.
  - Earlier failures were not this bug. The four-layer runs 1 and 2 had 7 and 5 nets open on their first DRC,
    before the strip, and the superseded six-layer runs that reached the strip stayed clean.
- **The outer-only set closed 1 of 3, so In3 goes X-preferred.** Evidence: evidence/c53-six-layer-outer-only/.
  - Run 1 passed every gate, `power_layers` included (28 rounds; 22 warnings, all of the committed board's kinds).
  - Run 2 left UI_CS_EXP_N (94 mm X span) and rtd2_force_p (RTD analog, F/In2 only, at U50) open after 35 rounds
    (13679 s).
  - Run 3 left RTD_FAULT_RB (79 mm X span) open after 31 rounds.
  - With the superseded set's coil_buf_out (64 mm), three of the four late failures are long X runs, and F was the
    only X-preferred layer.
  - Change: In3 DIRPEN (2.0, 1.0, 1.5) -> (1.0, 2.0, 1.5), the fallback recorded above. Three fresh runs.
  - In4 to signals stays the next step if this does not reach 2 of 3.
- **Stack-up checks beyond ampacity (C53).**
  - RF: the board has no RF net. The ESP32-S3-WROOM-1U's U.FL is on the module and the antenna is off-board on
    coax (R33), so the stack-up carries no RF line.
  - Impedance: none controlled (unchanged).
  - Thermal: heat leaves through the same parts and pours. The six-layer board adds the In4 selv_gnd plane and
    keeps 1 oz outer copper, so no thermal figure in LAYOUT.md gets worse. Only the current-carrying tracks depended
    on the layer, and `power_layers` now gates that.
  - Not read: JLC's six-layer price and minimum quantity (the quote page needs the order form; to be read at
    order time).
- **The In3 X-preferred set closed 3 of 3** (evidence/c53-six-layer-in3x/).
  - Runs 1–3 passed every gate, `power_layers` included: 33, 23 and 33 rounds; 5301, 4783 and 5541 s; 24, 23 and
    24 warnings, all of the committed board's kinds.
  - Superseded before a board of record was taken, because the block validators found a placement fault (next item).
- **The block validators could not read a six-layer board (fixed).**
  - zapote-core / zapote-drc hardcoded four copper layers in the zone schema, the RTD return-plane contract, the
    layer order and the reference-plane table.
  - On the six-layer board the RTD run stopped at INPUT_SCHEMA ("native zone uses unknown copper layer In4.Cu"). Its
    fail count fell from 33 to 27 because those checks never ran, not because any passed. Interlock and thermal read the
    board normally.
  - Fix: `Board.copper_layer_count`, filled by the harness from the export (default 4, so older inputs are unchanged).
    Layer names are accepted for any count, F.Cu < InN.Cu < B.Cu, and six layers reference F/In2 to In1 and In3/B to In4.
    The other stacks have no reference, so their traces are not proven. Rust tests pass.
  - The binder also aborted on four undeclared C51/C52 MPNs (U30 MAX31865AAP+T, R39 PTFR0805B430RN9, R47
    RT0603BRD0761K9L, U33 SN74LVC1G08QDBVRQ1). They are now in rtd-deviations-c37.json, and Rust still reports each one.
- **C30 (U30 DVDD bypass) was 3.10 mm from its pin. The RTD unit's rule is 3 mm** (DRC.RTD.LOCAL_DECOUPLING, pad edge
  to pad edge).
  - Auto-placement put C30 at the far end of U30's pin-1 corner. The C51 land is larger, and the 5 mm `decoupling` gate
    passed it. C47 met the rule.
  - The same measure put U50's C111 at 2.96 mm (U50 is outside the block validator's filter).
  - Fix: explicit poses for C29/C30 and C110/C111 (2.42 / 2.51 / 1.02 / 2.61 mm). New gate `rtd_decoupling`
    (check_layout): both MAX31865s, with the validator's measure.
  - Placement changed, so the routing convergence is rerun: three fresh runs.
- **pcb/libs footprints added in C51 were untracked:** SSOP-20 5.3 mm (U30, U50), MSOP-8, JST PH 2-pin, XH 5-pin. A
  clean checkout could not build the board. Committed in b77bb230a.
- **Bring-up pre-mortem (fresh Fable reviewer, frozen export: netlist, BOM/CPL, sources at b77bb230a, firmware
  fw/c51-s56-unified fbd6f5ca9; report evidence/c53-premortem/PREMORTEM.md).**
  - No firmware-vs-netlist error: all 36 `controller_pins.h` signals, the straps, the I2C addresses and the expander
    bits check out. Reset defaults (PERMIT low) are as designed. The MAX31865 SSOP-20 pinout was checked pad by pad
    against the Maxim table (FORCE2 grounded for 4-wire).
  - **F1, fixed: 12 placements would have gone to JLC at the wrong rotation.** Among them, C1/C9 (100 uF electrolytics
    across 15 V) would have been reversed, and U11/U25/U33/U37 (the AND gates on the PERMIT path) would have been 90°
    off. Also affected: U52 EMC2301, Q2, D10-D13.
    - Cause: `CPL_ROTATION_OFFSET` is keyed by LCSC code and ended at C49, so codes added by C51/C52 got offset 0. The
      C52 U11-class swap moved to a different JLC footprint (C840098 needs 270; C7666 needed 180).
    - Confirmed with audit.py `geometry()` on the committed JLC pad records (fit RMS 0.03-0.28 mm at the needed offset).
      Controls U30, U50, U20, D9 and U2 agree with the CPL.
    - Fix: six table entries (with L2, whose identical pads only renumber), and a gate in fab.py,
      `cpl_rotation_gate`. Every placement's offset is checked against JLC's pad geometry. An SMD disagreement fails the
      build, and so does a part with no JLC pad record, unless it is a two-pad resistor (R32's code has none). With the
      new entries removed, the gate fails all 13 placements; with them, it passes.
    - fab-notes' NEEDS-PREVIEW list is now built from the gate: the THT connectors, plus one part per C53 code.
  - **F2 (order process):** JLC numbers seven THT headers 180° from ours. The CPL keeps KiCad's rotation, and the bodies
    must follow the silk. J7 reversed would short v3v3 to the UI board's ground; J15 reversed puts 12 V on the fan's
    PWM pin. ORDER gets three steps:
    1. In JLC's placement preview, rotate any header whose key renders 180° from the silk key wall, there in JLC's
       editor (its THT operators follow the render, not text remarks).
    2. Add an assembly remark.
    3. Check each key on arrival before plugging J7 or J15.
  - **F3:** J4 circuit numbering rests on one library. Buzz J4.3 and J4.9 against the power board before mating
    (bring-up step).
  - **F4, accepted:** U30 CS# has no pull-up (U15 and U50 have one). The bus is idle until firmware init, and the init
    rewrites the configuration. Not worth a placement change and a fourth convergence set.
  - **F5, firmware follow-up (fw/c51-s56-unified):** the food-probe CS# output latch is written only in `create()`. A
    lone TCA9555 reset leaves the probe reading "no reading" (fail-silent) until reboot.
  - **F6:** first flash is over J11 (TC2050) with a home-made USB lead; there is no UART fallback. Make the cable before
    the boards arrive.
  - **F7:** README's power tree still had PS1 on J4.1 (fixed, C49 path).
- **Final convergence set (RTD bypass poses): 2 of 3, which meets the C51 rule** (evidence/c53-six-layer-final/,
  evidence/convergence.json).
  - Runs 1 and 3 passed every gate, `rtd_decoupling`, `power_layers` and the CPL rotation gate included: 17 rounds
    each; 3250 s and 3419 s; 21 and 23 warnings.
  - Run 2's router left I2C_SCL_BOOT open after 18 rounds (a 0.14 mm In3 stub short of its via).
  - Board of record: run 1 (sha256 11265a33…, commit eb8218075).
  - Block validators on it: interlock 68/7/5, thermal 87/10/7, RTD 5/40/5. The C30 locality fail is gone, and every
    added fail is W8.
- **Independent layout review of eb8218075 (fresh Fable reviewer, frozen export; report
  evidence/c53-layout-review/REVIEW.md): no BLOCKER, five MAJOR. The board of record above is superseded.**
  - Every finding below was re-measured on the board before acting.
  - The copper fixes went in together, so the routing convergence is rerun (three fresh runs). The rerun board then
    gets a fresh review.
  - **M3, fixed: the face-fan buck (U51/L3/J15, C51) had no power-stage copper.**
    - `sw_fan2` was 9.7 mm of 0.15 mm track. `V12_FAN2` was 55 mm of 0.15 mm through three vias (0.67 A against
      0.60 A for 10 K). U51's VIN came over 0.25 mm V15_BLW necks.
    - Fix: build_board `buck_pours` for U51 (SW band to L3 pad 1, VIN pour), and the caps at U2's offsets on the pours.
      `sw_fan2`/`V12_FAN2` join the Power class and OUTER_ONLY. V12_FAN2 routes at 0.6 mm with no neck. V15_BLW routes
      at 0.8 mm (was 1.0) with no neck.
    - New gate `power_paths`: each supply's source and load pads are joined by pours or tracks of at least the net's
      path width (V_BLOWER 0.8, V12_FAN2 0.6, V15_BLW 0.5, v15_selv 0.25 mm), counting vias and pin stubs up to
      1.2 mm. On the old board it fails exactly V12_FAN2 and U51's V15_BLW branch.
  - **M4, fixed: V_BLOWER's four layer changes were single 0.6/0.3 vias** (1.42 A typical, 2.70 A max, about 1 A per
    barrel).
    - New step `layout/power_vias.py`, run in route.py before the pours: it adds companion vias on the high-current
      nets, aiming for three barrels per layer change. Each companion is checked with gridroute's exact clearance and
      drill checks.
    - New gate `power_vias`: at least two barrels at every site. On the old routed board it added 28 vias with DRC
      still clean.
  - **M5 and m1, fixed: In2 v3v3 pour islands carrying IC supplies hung on single links.** The ESP32 module's island
    had one via and a 0.3 mm track. C30 (U30 DVDD) sat on another island from its pin.
    - New `layout/v3v3_islands.py` counts each island's links. plane_islands.py asks the router for a second link on
      any supply island with one.
    - New gate `v3v3_islands`. On the old board it finds the reviewer's islands: four with one link.
    - Locked F.Cu stubs now tie each MAX31865's DVDD pin to its bypass. C110/C111 swapped, so C111's pad is level with
      U50.2. `rtd_decoupling` now also requires that F.Cu path.
    - An In3 v3v3 fill was considered and rejected: In3 sits 0.11 mm from In2's RTD analog traces, and the RTD
      regions forbid In3 fills.
  - **M2, gated:** a THT connector whose JLC footprint numbers the pins differently must be listed in
    `fab.THT_REVIEWED` (the eight known, with the order-process check), or fab fails. A two-pad resistor with no JLC
    pad record (R32) may take offset 0 or 180 only. The THT orientation itself is an order step (F2 above).
  - **M1, open (owner): J4 numbering.** Molex's site refused automated reads of the 43045-1600 drawing (timeouts from
    both the fetch tool and curl). The power board's mate is the same KiCad Molex family (vertical 43045-1612), so a
    1:1 harness maps pin n to pin n unless KiCad's generator differs between the two. No copper change. Owner: read the
    drawing; bring-up: buzz J4.3 and J4.9 before mating.
  - **Minor items:**
    - m2: the J13.1 feed pour reaches past the pad on +X/+Y/−Y, so all four spokes form (was one).
    - m3: the interlock gate and the router's forbid list also count nets the MCU drives through a ≤ 100 Ω series
      part. That catches pwm_hb's 25 mm In3 run through the latch block; the op-amp `*_buf_out` nets go into the ADC
      and are excluded. The gate uses an exact segment/box test.
    - m6: a 10 mm selv_gnd stitching grid, placed after routing (see set 1 below). New gate `gnd_stitch`: every point
      3 mm or more inside the edge, off the module, within 11 mm of a ground via. The old board measures 23.4 mm worst
      (27 % beyond 7 mm); with the grid, 10.0 mm worst (1.9 %).
    - m7: three fiducials, board-only, each with a 1.5 mm keep-out.
    - m10: silk revision text.
    - m11: drill maps out of the zip.
    - Stale strings fixed: the jlc-dfm stack-up and C1's height-table name (UCD1E101MCL6GS, D8 × 6.2, as C52).
  - **Accepted:**
    - m4: In2/In3 broadside runs. The inferred glitch is a few hundred mV for about 10 ns, on lines filtered or
      latched downstream.
    - m5: RTD tap resistors 35–40 mm from U30. They are RC-filtered, and moving them is a placement study.
    - m8: via-in-pad. It is acceptable with JLC's epoxy fill and cap, which becomes an order-form item.
    - m12: digital and SS tracks under L2's shielded body.
    - J11 courtyard edge overhang: copper-only lands, nothing fitted.
  - **To ORDER:** m9 stock reads for the 18 unread lines, JLC's six-layer minimum quantity, POFV, and the THT
    orientation steps.
  - **Review-fix convergence set 1: 0/3.** Runs ended at 1–3 opens after 6,148–6,405 s and about 36 rounds (the
    superseded set took 14 rounds). Logs: build/conv/failed-review-fix-set1.
    - Long cross-board nets stayed open in every run (BLW_PG, SUP_RUN_OK_RB, RUNAWAY_FAULT). The m6 grid had been placed
      before routing as 61 locked through vias, which blocked all six layers of those corridors. Fix: the grid is now
      placed after routing (power_vias.py), only where the routed copper leaves room.
    - Run 2 left U51's V15_BLW feed open. Its branch hangs off R150.1, the EN divider pad 1 mm outside the VIN pour, and
      no 0.8 mm track can pass R150.2 to get there. Fix: V15_BLW gets one narrower try at 0.5 mm, the power_paths
      width; no 0.25 mm neck.
    - Found while testing: a track-less via added to a filled board is re-netted by KiCad's connectivity at save. A
      random 8–16 of 70 stitch vias became v3v3. They are now marked free vias, and three repeat applies gave 0 wrong
      nets.
  - **Review-fix convergence set 2: 0/3.** Runs 2 and 3 ended at 6 and 2 opens after 8,374 and 8,775 s and 34–36
    rounds. Run 1 was stopped at round 36 with 2 open (BLW_PG, RUNAWAY_FAULT). Logs: build/conv/failed-review-fix-set2.
    - The set-1 diagnosis of V15_BLW was wrong. The pair R150.1 → U51.3 failed in nearly every round of runs 1 and 3,
      and each failure put V15_BLW first in a repair that ripped 77–200 pairs. The open pair's far end is U51 pin 3,
      a 0.5 mm-pitch SOT-583 pin that no 0.8 or 0.5 mm track can land on. KiCad names the pin, not the VIN pour it
      sits in. Fix: build_board adds a locked 0.8 mm F.Cu stub from R150.1 straight down into the fan2 VIN pour. It
      stops the build if R150 is not above the pour or the stub touches another pad. The NARROW fallback stays for
      V15_BLW's other branches.
    - A "J7.2 ↔ V3V3_plane zone" item reached the router with the zone end at the zone's first corner, the board
      corner (20.3, 20.3). The router tried a 77 mm route there every round. Fix: plane_islands re-aims a pad-to-zone
      item at the zone's nearest through copper in its largest fill outline.
    - Checked and kept: the m3 interlock-forbid expansion for the PWM lines. A round-1 A/B on the rebuilt board, with
      and without the pwm_* forbid, gave the same pass-1 result (22 open) and the same pass-2 sequence. RUNAWAY_FAULT
      routes alone on the unrouted board in one pass (1 via, 133 mm on In3), so its late failures are churn.
  - **Review-fix set 3, run 1: routed in 18 rounds, about 40 min**, with DRC 0 errors and 0 unconnected; set 2 took 34–36
    rounds. Three post-route gates failed, which no earlier set had reached:
    - power_widths: V15_BLW's two 1.035 mm buck VIN pin stubs (0.3 mm, locked) counted as narrow track. power_widths
      cut stubs at 1.0 mm, power_paths at 1.2 mm. Both now use 1.2 mm.
    - power_vias: four single-via sites. The planner only tried spots along the via's tracks or square to them. It now
      also tries a 16-direction ring, with no stub on a layer where a same-net pour holds both vias. On run 1's routed
      geometry the zero-companion sites went from 4 to 1. That one, the V15_BLW via beside R150, is boxed in by
      In2/In3 signal tracks.
    - The power_vias gate itself now follows the review's M4 criterion, "single via in a > 1 A path". It was ≥ 2
      barrels at every layer change of the four nets. A site's current is the sum of the loads cut off from the
      source when its vias are removed, or the net's whole load if all of them keep a parallel path. Two barrels are
      required above 1 A. The V15_BLW via beside R150 feeds only U51: 0.61 A, so one barrel carries it 1.6×. V_BLOWER's
      single sites were 2.70 A and now get companions.
    - gnd_stitch: 11.71 mm worst, against the 11 mm limit, by J13. The grid nodes there found no legal spot within
      3 mm. STITCH_SEARCH is now 5 mm: 69 stitch vias, worst 10.0 mm at a board corner.
    - Checked on run 1's board with the old plan's vias and stubs removed and the new plan applied:
      - DRC: 0 errors, 0 unconnected.
      - All 108 planned vias kept their nets after save.
      - Every layout gate passed.
    - Runs 2 and 3 were stopped at round 23 (old post-route code), and all three runs were restarted on this code.
      route.py now saves pcb/route/work-routed.kicad_pcb before the post-route steps.
  - **Review-fix set 4: runs 2 and 3 routed clean** (DRC 0 errors, 0 unconnected; 31 and 26 rounds, 79 and 73 min), **and
    both failed the power_vias gate on one 2.70 A V_BLOWER via each.**
    - The two vias were at C16 by U52 (run 3) and near J4 (run 2). By the time power_vias.py ran, I2C tracks and a v3v3
      via had taken the room around each one. Run 1 was stopped at round 12. Archive: build/conv/failed-review-fix-set4/.
    - Two runs out of two means a companion added after routing is a matter of luck. The change: gridroute.py now
      places each CLUSTER-net via's two companions (V_BLOWER, V15_BLW: the nets with > 1 A sites) when it makes the
      route.
      - It uses power_vias.py's candidate spots and stubs, exactly checked against the copper routed so far.
      - A via that cannot get both is barred (1 mm) and the pair re-routed, up to 4 times per width/margin try.
      - If no try clusters every via, the route with the fewest short vias is kept.
      - power_vias.py stays as the back-up.
    - cleanup.py's loop pass skips the CLUSTER nets. Each companion's stub closes a loop with the track it sits on, and
      that pass would delete the stub and strand the via. Their dangling pass still runs.
    - Smoke test: cluster() on run 3's routed V_BLOWER and V15_BLW copper finds the same short vias power_vias.py found.
    - Set 5 runs on this code.
  - **Review-fix set 5 (companions placed at route time): runs 2 and 3 did not route.** They left 6 and 4 pairs open after
    38 and 35 rounds (137 and 123 min). Run 1 was stopped at round 33 on the same course. Archive:
    build/conv/failed-review-fix-set5/.
    - The companions did work: no V_BLOWER or V15_BLW via was left short.
    - Every open pair, and most repair targets, sat in the band V_BLOWER crosses: C16, U52, J10, U29 and U34
      (x 160-200). Run 2 also left V_BLOWER itself open from C16 to J10.
    - Run 2 also had one DRC error, an RTD via 0.75 mm from the board edge.
    - Reading: V_BLOWER routed late, after the short local links (shortest-first order). Its clusters then fought
      for the leftover room, and negotiated rip-up kept displacing and re-routing it.
    - Set 6: CLUSTER nets route first in every round and pay 4× the via cost, and in pass 2 a signal path may not
      rip a CLUSTER route.
  - **Review-fix set 6 (CLUSTER first, 4× via cost, not ripped by signals): run 3 left 2 long signal pairs open after
    38 rounds** (coil_buf_out 47 mm, RTD_SDO 47 mm, both on the left half). Runs 1 and 2 were stopped at rounds 37 and
    31, deep in the repair cycles. Archive: build/conv/failed-review-fix-set6/.
    - Not from the clusters. V_BLOWER and V15_BLW lie at x > 137 and cross neither corridor. They have 15 vias against
      set 4's 10, out of about 1165 on the board.
    - Four fixes, all checked on run 3's saved board.
    - **ECO stage (route.py eco_passes, ECO_PASSES = 2).** Repair rips only within REPAIR_R of a pair's ends, so a
      long pair blocked mid-corridor never frees.
      - gridroute --eco existed but was not wired in.
      - On run 3's board, one ECO pass ripped 57 pieces of 37 nets. One normal round re-routed them (44 open, then 0).
    - **plane_islands re-issued a pair forever.** A 2 mm² one-via In2 island hangs off U29/U35's v3v3 copper.
      - links (island vias with a path out) is 1 whatever is routed to that via, so every round added the same
        B.Cu track: 22 copies on the test board.
      - The IC copper reaches 5 vias of the main pour. Its supply is linked, and the island carries none of it.
      - v3v3_islands now reports main_links. An island is weak only if links < 2 and main_links < 2. M5's case, the
        ESP32 pin fed by one via and a 0.3 mm track, has main_links 1 and still fails.
      - A weak pair now targets a main-pour via the copper does not reach yet. An island with no free via is targeted
        at an In2 point inside it, so the route adds a via there.
    - **power_paths joined a track to a pour only by an end point inside the fill.** U51's locked VIN stub ended on
      VIN_FAN2's fill edge, which a nearby `en` via had pushed there. KiCad's DRC connected it; the gate split U51.3
      off. The track-to-zone test is now shape overlap, as in KiCad's connectivity.
    - Result on run 3's board after ECO: DRC 0 errors, 0 unconnected, parity 0. All layout gates, JLC DFM and the fab
      review pass.
    - Set 7 runs on this code.
  - **Board edge 0.05 mm too large in the router's geometry.** export_geom.py took geom["edge"] from
    GetBoardEdgesBoundingBox(), which includes half the 0.1 mm Edge.Cuts line ([19.95, 19.95, 226.05, 96.05] for the
    20-226 × 20-96 outline). The router kept copper 0.5 mm inside that, so 0.45 mm from the real edge.
    - This was set 5 run 2's one DRC error: an RTD via 0.45 mm from the edge against the 0.5 mm rule.
    - The edge is now inset by half the outline's line width, giving [20.0, 20.0, 226.0, 96.0].
    - Found by an outside audit of 07f7b8582. Set 7 was stopped at 40 min and restarted with this fix.
  - **Set 7 (6942fdd41): 0/3. Every run routed clean (DRC 0 errors, 0 unconnected) and failed one layout gate.**
    Archive: build/conv/failed-review-fix-set7/.
    - Run 1, v3v3_islands: U36's island (3.1 mm², one via, one link, main_links 1) is a sliver beside a via pad.
      - interior_point() found no room for a new via, and plane_islands dropped the pair without telling anyone.
      - Routing then closed at 0 open, and only the gate saw the island.
      - Fix: with no free via and no interior point, pair the island's linked via with the nearest main-pour via its
        copper does not reach yet. That gives a second main link, which is what is_weak asks for.
      - On run 1's board the pair is now issued (U36 via to the main-pour via at 167.7, 30.1).
    - Runs 2 and 3, power_widths: V15_BLW R150.1 -> R17.1 was laid at 0.5 mm for 10 mm, the same path in both.
      - gridroute's NARROW try routed the whole pair at 0.5 mm. power_widths (review M3) wants 0.8 mm on every
        V15_BLW track over 1.2 mm, so any NARROW route longer than that failed the gate. The router and the gate
        disagreed.
      - Why 0.5 won (read from attempt(), not logged by the run): V15_BLW is a CLUSTER net. A 0.8 mm route found
        only through vias is kept as a fallback when their companions come up short. The 0.5 mm all-F.Cu route has
        no vias, so it returned at once.
      - Fix: NARROW is now a neck. The route keeps 0.8 mm, and only an end piece of at most NECK_MM = 1.0 mm, from the
        pad to the first full-width cell, may be 0.5 mm. That is inside the gate's 1.2 mm pin-stub allowance. The gate
        is unchanged.
      - On run 2's final geometry, 0.8 mm routes R150.1 -> R17.1 with no neck. A synthetic pad in a 0.95 mm channel
        routes only with the neck (1.0 mm at 0.5, then 0.8). Run 3's geometry also routes at 0.8 mm.
      - If a 0.8 mm route's vias are short of companions, power_vias and its gate see them, as before.
    - Run 1's saved board with the island fix: one ECO pass, then 0 open, DRC 0/0/0, ALL GATES PASS.
    - Set 8 runs on this code (76287a259).
  - **Set 8 (76287a259): 1/3.**
    - Run 2: ALL GATES PASS in 54 min. Its routing closed before the ECO stage.
    - Runs 1 and 3: DRC shorts and crossings, 6 and 43 errors. Every one first appears in the DRC right after ECO pass
      0. Archive: build/conv/failed-review-fix-set8/.
    - Cause, two holes in gridroute.eco()'s model of the board.
      - (a) A path that crossed net N2 deleted only the crossed pieces on the board, but remove_route() dropped all of
        N2 from the router. A later pair of the same pass then crossed N2's surviving tracks unseen: no rip item, so
        a short.
      - (b) Paths of the same pass were only a soft cost to each other and were never checked for crossings.
    - Fix.
      - The router keeps every piece the board keeps.
      - A path that crosses another net's ECO path of the pass is left to the rounds.
      - Pairs go longest first, so the long PERMIT_RB is not the one that waits.
      - ECO_PASSES is 3 (was 2): a waiting pair can rip the earlier ECO copper in the next pass.
    - New guard: every pass's output is checked against the input geometry, the board's copper minus the pass's
      deletions plus the other new paths. A pair within clearance of another net is dropped with its deletions.
    - Replay: the four saved ECO inputs (both runs, passes 0 and 1) re-run on those runs' final geometry, with an
      independent checker.
      - Old code: run 1's exact short set (PERMIT_RB with RTD_SDI, UI_MOSI and rtd_sense_p_ext; sense with FAN_TACH),
        plus 15 and 6 conflicts on run 3, including ECO-to-ECO crossings.
      - New code: 0 in all four. The guard, applied to the old outputs, flags exactly the shorted nets.
    - Run 2 is not counted: set 9 runs 3 fresh runs on this code.
