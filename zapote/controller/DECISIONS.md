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
| v3v3 lost (regulator off, short) | Interlock, ISO7710s and u_fault_or unpowered | Latch Q unpowered, and PERMIT pulled low by 10 kΩ here plus 2 × 100 kΩ at native-21. Independently, v3v3 is the UCC21550s' VCCI: below VCCI UVLO (2.35–2.65 V falling) both outputs are held low whatever the inputs (SLUSE89C Table 7-1). **Safe** |
| v3v3 slow out of window (3.15–3.19 V or 3.41–3.46 V) | Logic still powered | TPS3703 → RAIL_FAULT (AUX, latched) and SENSOR_LIVE low → PERMIT low within the 1 ms filter |
| v3v3 brown-out below the LVC operating range | Logic states undefined | The order on a falling rail: TPS3703 UV (≥ 3.146 V), then TPS3823 (2.83–3.00 V), then UCC21550 VCCI UVLO (≤ 2.65 V) forces gate outputs low. **Flag:** confirm the sequence with the native-21 load on the bench |
| v15_selv lost | Both bucks stop; v3v3 decays | As for v3v3 lost |
| selv_gnd open at J4 (all three returns) | native-21 SELV floats | J4.10 has no valid low, so the 10 kΩ pull-up reads a fault, and PERMIT's reference is lost. native-21's PERMIT gate pull-down makes DIS high. **Flag:** a whole-return-open case also needs a bench check (FAULT-INTERFACE "does not qualify an open return wire") |
| J4 unplugged | All of the above at once | bus_fault pull-up reads a fault, latch drops, ct_mon reads 0 V (10 MΩ), VBUS < 100 mV is invalid in firmware. **Safe** |
| bus_fault conductor open | — | Interlock 10 kΩ pull-up gives a fault. **Safe** |
| PERMIT conductor open | native-21 sees no PERMIT | native-21's 100 kΩ pull-downs make DIS high. **Safe** |
| PWM conductor open / MCU reset / MCU unpowered | Driver inputs float | 10 kΩ pull-downs here plus 50 kΩ UCC21550 internal ones; the ESP32 PWM GPIOs have no reset pull-up and only low glitches (DS Tables 2-1/2-2). **Safe**, and PERMIT is independent of these anyway |
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

## Open items (need the owner or the enclosure team)
1. **Owner:** confirm D-18 is superseded, so the fan can sit on PS1 through the controller (C9).
2. **Owner:** M12 probe type and pin map (C14).
3. **UI board (R33, C26):** the encoder part and its supply (3.3 V, or 5 V within J7.1's 30 mA), the buzzer part (≤ 90 mA on J7.2), and whether STOP should be a hardware trip. The UI board must not pull D/C up (GPIO45 strap).
4. **Owner:** the runaway band. **DEFAULT** 296.6–319.1 °C (C6). It is set only by the 20k/10k ratio, so a new band is one resistor change. `verify_controller.py` checks that the fitted ratio equals `controller_calcs.py`, and `runaway()` reports the band. The BIAS-on start-up sequence for firmware stays.
5. **Bench:** the AD8436 settling with CAVG = 100 nF (the linear scaling from the datasheet's 10 µF figure is an assumption), and the envelope-tracking error over a half line cycle (C19).
6. **Power-stage:** the J4 harness spec. **DEFAULT:** ≤ 1 m AWG22 (R27's route is 74 mm). `controller_calcs.py harness_sensitivity()` shows native-21 still sees ≥ 3.208 V even at 8 m, so the design does not depend on this default. D-11's ≤ 400 pF/≤ 200 pF capacitance limits apply.
7. **Procurement:** AD8436BRQZ has zero JLC stock (consign or buy from ADI or a distributor). The TPS3703 Q1 has only 18 at JLC. MCP3202 has 197. Ported parts with JLC stock 0 or near 0: ERA-3AEB1652V and RG2012V-431-W-T1 (RTD block), and CD74HC30PWR (interlock, 7 in stock). See `bom/controller-parts.json`.
8. **Firmware:**
   - repeated ADC1 channels in one continuous pattern (C12);
   - the BIAS-on, settle, reset-request sequence (C6);
   - the WDI ≤ 400 ms heartbeat;
   - the UI bus driver (OLED + polled MCP23S08 on one SPI host, chunked frame writes, C26);
   - pins.h additions (UI SPI 40/41/44/47/48/45, RUN_EN 14, I²C SDA 37 / SCL 0, blower PWM 46 and tach 3, ADC on 8 and rim NTC on 9; expander: RTD_DRDY P07, SUP_RUN_OK P14, FAN_OFF P15, BLW_PG P16 (C33));
   - the blower fan law and tach supervision (C28).
9. **Layout stage:**
   - re-run the interlock, thermal-sense and RTD validators on the integrated board;
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
To apply to the BOM after the C34 layout stage lands; none changes a footprint or a net.
- **R53** ERA-3AEB1652V (0 stock) → **RT0603BRD0716K5L** (C728584): 16.5 k, 0.1 %, ±25 ppm, 0603, 0.1 W; drop-in.
- **U22** CD74HC30PWR (2 in stock) → **74HC30PW,118** (C546857): the same TSSOP-14 pinout and 2–6 V HC family. The interlock validator's exact-MPN check gets a waiver line.
- **R31** RC0603FR-078K06L (3 in stock) → **C861587** (8.06 k 1 % 0603). The match rests on parametric data only, so read the datasheet before applying.
- **J13** BOM code C20571196 (not found) → **C160315**. Same MPN, code fix.
- **R39** (MAX31865 RREF) RG2012V-431-W-T1 0.05 % (0 stock; no equal part in stock) → **RT0805BRD07430RL**, 0.1 %, ±25 ppm, for the prototype lot.
  - The extra 0.05 % is about 0.13 °C at the pan's operating point. The 10 Ω / 300 Ω fault thresholds are unaffected.
- **U14** AD8436BRQZ (0 stock): this is an owner decision.
  - Either consign 4 BRQZ (about $113 at DigiKey qty-1 prices), or fit AD8436ARQZ-R7 (C495329, 106 in stock; 0.5 % vs 0.25 %, ±500 vs ±250 µV offset) on the prototypes after an RMS-trip error-budget check.
- **CPL:** 15 rotations are corrected in `cpl-jlcpcb.proposed.csv`. Fold them into the fab output with the C34 regeneration, after re-auditing any part C34 moves. The 37 NEEDS-PREVIEW lines are checked in JLC's preview, one designator per LCSC code.
- **J4 drawing:** Molex 43045-1600 sales drawing still unread (molex.com refuses this network); `evidence/fab-loose-ends/j4/j4-interface.svg` is the interface drawing; the height and −X overhang stay [UNVERIFIED] until the owner fetches the drawing.
