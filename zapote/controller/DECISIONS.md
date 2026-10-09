# Controller decisions

These are design calls I made during schematic capture, as a senior designer, from the inputs in [README.md](README.md). Each one gives the basis and is flagged where the owner or enclosure team should confirm it. Numbers come from `tools/controller_calcs.py` or `tools/verify_controller.py`. Open items are at the end.

## C1. One unit; blocks ported by a provable line filter
- **What:** `zapote/controller` follows the unit pattern (`ato.yaml`, `elec/src`, `tools`, `frozen`). Interlock and thermal-sense are ported by `tools/port_blocks.py`, and `RTDSensing` is used from the byte-identical library.
- **What changed in the ports:** only the inter-board headers and the thermal `+3V3`/`gnd` net-name overrides are removed, and the verifier proves that. On the integrated board those boundaries become copper.
- **What is not changed:** no value, MPN or internal connection.
- **Re-run each block's own validation** (Rust validators) on the integrated layout, per CONTROLLER-SPEC. That is a layout-stage item.

## C2. GPIO map: keep round-5 `pins.h` where it exists
- **Kept from pins.h:** PWM 4/5/15/16, REQUEST→IL_RESET_N 17, HEARTBEAT→IL_WDI 18, FAULT_HIGH 21, RAIL_OK 35, INTERLOCK_OK (PERMIT read-back) 36, SUP_RUN_OK 37, fast SPI 10–13 → RTD (CS/CLK/MISO/MOSI = 10/11/12/13), RTD_DRDY on 14.
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

## C9. Fan supply: a regulator on the controller, on by default (spec R19 L1, R24)
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
| RTD_AVDD lost | MAX31865 off | TPS389001 gives RTD_HW_FAULT and SENSOR_LIVE low |
| Interlock 3.3 V shared with the MCU (common-cause) | One regulator feeds both | Accepted: every rail fault takes PERMIT low (rows above). The architecture asked for its own region and decoupling, not its own regulator |

## Open items (need the owner or the enclosure team)
1. **Owner:** confirm D-18 is superseded, so the fan can sit on PS1 through the controller (C9).
2. **Owner:** M12 probe type and pin map (C14).
3. **Owner/UI:** the Grayhill encoder part, its supply voltage and the 6-way pin map (C15). Also the APEM switch contact form, and whether STOP should be a hardware trip (C16).
4. **Owner:** the runaway band. **DEFAULT** 296.6–319.1 °C (C6). It is set only by the 20k/10k ratio, so a new band is one resistor change. `verify_controller.py` checks that the fitted ratio equals `controller_calcs.py`, and `runaway()` reports the band. The BIAS-on start-up sequence for firmware stays.
5. **Bench:** the AD8436 settling with CAVG = 100 nF (the linear scaling from the datasheet's 10 µF figure is an assumption), and the envelope-tracking error over a half line cycle (C19).
6. **Power-stage:** the J4 harness spec. **DEFAULT:** ≤ 1 m AWG22 (R27's route is 74 mm). `controller_calcs.py harness_sensitivity()` shows native-21 still sees ≥ 3.208 V even at 8 m, so the design does not depend on this default. D-11's ≤ 400 pF/≤ 200 pF capacitance limits apply.
7. **Procurement:** AD8436BRQZ has zero JLC stock (consign or buy from ADI or a distributor). The TPS3703 Q1 has only 18 at JLC. MCP3202 has 197. Ported parts with JLC stock 0 or near 0: ERA-3AEB1652V and RG2012V-431-W-T1 (RTD block), and CD74HC30PWR (interlock, 7 in stock). See `bom/controller-parts.json`.
8. **Firmware:**
   - repeated ADC1 channels in one continuous pattern (C12);
   - the BIAS-on, settle, reset-request sequence (C6);
   - the WDI ≤ 400 ms heartbeat;
   - the OLED SPI driver;
   - pins.h additions (OLED, I²C on 9/0, fan 46/3, ADC on 8).
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

## Layout inputs from the enclosure (R27, 2026-10-08)

Binding when the controller PCB is laid out (source: output/temper-manufacturing-r27/design/r27/CONTROLLER-SPEC.md, "R27 answers").
- **Mounting holes:**
  - rear holes at world (−164, 80), (−75, 86) and (30, 80), moved by the enclosure to clear the cable landings;
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
