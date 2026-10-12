# UI board decisions

Schematic-level pass (2026-10-12), **revision 2 the same day** for the owner's decision of 2026-10-12: the Grayhill encoder (J2, comparator U3, encoder pull-ups and ESD) and the APEM IPR3PAD2 buttons are removed; the controls are PCB tact switches under owned metal caps and a removable magnetic knob read through the 3 mm 5052 fascia by a TMAG5170 on this unit. Requirements source: `output/temper-owned-controls/UI-BOARD-REQUIREMENTS.md`. **U19 to U32 are the current design; U1 to U18 keep their text with a status line: SUPERSEDED (no longer applies), REVISED (read the item named) or UNCHANGED.** Each decision names its source. Datasheets were downloaded to a scratch directory outside the repo; they are cited by document and page. Numbers come from `tools/ui_calcs.py` (`evidence/ui_calcs.json`); anything marked **[ALLOCATION]** or **[UNVERIFIED]** is an engineering allowance that has no datasheet line behind it yet.

## U1. Scope and fixed inputs
- **Status: REVISED by U19 (scope). The OLED, J7, expander, TMP122 and buzzer parts of this item stand; "three IP67 buttons" and "the encoder socket" no longer do.**
- **What this is:** the fascia UI board, one PCB parallel to the fascia with the OLED, three IP67 buttons, the encoder socket, an SPI expander, a temperature sensor and a buzzer, joined to controller J7 by a 12-way, 120 mm JST XH jumper. It is a schematic, a BOM, calcs, a verifier and a mechanical floorplan. **No layout.**
- **Fixed by the controller (read-only):** `zapote/controller/DECISIONS.md` C26 (J7 pin map, 100 ohm at the controller end of every signal, SRV05-4 at J7, V5_UI at most 30 mA, UI 3V3 allocation 120 mA + 340 mA OLED), C3 (OLED is SPI), C23 (PERMIT = latch AND RUN_EN), `ENCLOSURE-HANDOFF.md`. Open item 3 there is what this unit answers: encoder, buzzer, STOP.
- **Fixed by the enclosure (read-only):** `output/temper-manufacturing-r41/` `design/r33/DECISIONS.md` section 3, `src/r33_world.py` (UI board outline, holes, connectors, M3 since R39), `src/controls_r5.py` (OLED, lens, buttons, encoder), HANDOFFs r35 to r41. No R39 to R41 change moves the UI board; R41 only repeats the sounder decision.
- **Fixed by firmware (read-only):** `git show 780eaab89:firmware/main/platform/ui_board_map.h`, copied to `inputs/firmware/` with its hash.

## U2. J7 and the bus terminations
- **Status: UNCHANGED. J7 is byte-equal to C26 (verifier: 5 equalities). CS_EXP# and CS_OLED# now also feed the NAND U9 (a 5 pF input each, no resistor, no pull: `j7_*_has_no_resistor_or_pull` still holds).**
- **Pin map: kept byte-equal** to C26: 1 V5_UI, 2 +3V3, 3 GND, 4 SCK, 5 GND, 6 MOSI, 7 MISO, 8 GND, 9 CS_OLED#, 10 OLED D/C, 11 GND, 12 CS_EXP#. `verify_ui.py` compares the board to four independent copies (the C26 table, the ENCLOSURE-HANDOFF row, the controller's frozen netlist, the controller's `verify_controller.py J7_MAP`) and to a literal.
- **Connector:** the controller's own part, JST B12B-XH-A(LF)(SN), LCSC C158027.
- **ESD at J7:** two SRV05-4 (U4, U5), Vcc on V3V3, on all six signals, the same part as the controller's U38/U39 (LCSC C2836319). The power pins carry none: a steering-diode array cannot sit on the 5 V pin from a 3.3 V clamp rail, and 3V3 is a stiff rail with 22 uF.
- **Terminations:** the controller already has 100 ohm in series at its end of every signal. The UI board drives only MISO, so it gets the one matching source resistor (R20, 100 ohm) between the chips and J7. Inputs (SCK, MOSI, CS_OLED#, CS_EXP#, D/C) have no series part on this board.
- **No pull on D/C or the chip selects here.** D/C goes straight to OLED pin 4: controller GPIO45 is a strap pin that must read low at reset (C26, R38). The chip selects are pulled up at the controller. Checked by `j7_dc_has_no_resistor_or_pull` and its mutation.

## U3. The OLED supply: the module makes its own 12 V; the 5 V pin cannot carry it
- **Status: UNCHANGED.**
- **Question:** the panel of the NHD-3.12-25664UCW2 needs about 12 V. Does the UI board need a boost, or an OLED variant with an internal DC-DC?
- **Answer:** neither. The module (rev. 7, 2024-08-25) already contains the boost, and its factory jumpers (R14 closed) power logic, boost and panel from VDD (pin 2) at 2.8 to 3.5 V (Newhaven spec p.6). The supply current is 310 mA typ and **340 mA max** at 3.3 V with all pixels on (p.7). That is the number the controller already budgets on J7.2 (`verify_controller.py v3v3`, `oled_off_board_mA` 340).
- **Why not V5_UI:** jumper option 1 feeds the boost from pin 3 at up to 12 V. At 5 V the boost input draws **150 mA typ, 170 mA max** (p.7), 5.7 times the 30 mA the controller's 5 V path allows (2 x 100 ohm droppers, TLV76050). At 12 V it would be 70 mA max, but J7 carries no 12 V.
- **Why not an external 12 V on VCC (option 2):** 55 mA max at 12 V, but a 12 V boost from 3.3 V on this board would still pull about 235 mA from V3V3 at an allocated 85 % efficiency, to save about 100 mA, for an inductor, an IC and a switching node next to the encoder. Not worth it.
- **Wiring:** pins 3 (BC_VDD), 15 (VCC) and 18 (G_VDD) stay open. `oled.nhd_4wire_spi_pin_map` checks that they have no connection. The OLED socket carries 22 uF and 100 nF at its VDD pin for the boost start-up.
- **Check:** firmware's FW-UI-1 limits (at most 30 % pixels lit, dim after 30 s) will cut the real draw well below 340 mA. The datasheet gives no partial-load figure, so none is claimed.

## U4. V5_UI: reserved, unused
- **Status: UNCHANGED. The 5 V pin still ends in C11 and R23 only; the 70 C buzzer that U4 kept off V5_UI is gone, and the replacement draws 30 mA, so the argument holds more narrowly (30.6 mA at 5.1 V against 30).**
- **Budget:** 0.51 mA of 30 mA (a 100 nF capacitor C11 and a 10 kohm bleed R23 so the pin is never floating). `power.v5_budget_le_30mA` recomputes it from the netlist; moving the buzzer onto V5_UI (47 mA at 5.1 V) fails it.
- **Why nothing uses it:** the only candidates (OLED boost, buzzer) exceed it (U3, U9), and keeping the buzzer off V5_UI keeps its current steps off the controller's LDO and its two 100 ohm droppers, which are sized for 30 mA plus 5 mA of LDO ground current (C26; the LDO input reaches its 1.2 V dropout limit at about 42 mA in total). 30 mA is the controller's limit, not a hard wall.
- **Consequence for the controller:** none needed. The 5 V LDO, its droppers and the 15 V draw on the controller are budgeted for 30 mA the UI will not draw.

## U5. The 3V3 budget and the rail band
- **Status: REVISED by U29. The encoder numbers (30 mA, 26 mV low-side margin, FB1, C8) are gone with the encoder; the band, harness drop and OLED margins stand and are recomputed in U29.**
- **Loads at datasheet maxima, V3V3 = 3.465 V:** OLED 340 mA, encoder 30 mA (Grayhill p.3), buzzer 31.5 mA (30 mA at the 3.3 V rating scaled), MCP23S08 8 mA (1 mA at 1 MHz scaled to 8 MHz, **[ALLOCATION]**), pull-ups 2.1 mA, the rest under 1 mA. **Total 411.9 mA; 71.9 mA without the OLED.** The controller allocates 460 mA (340 + 120) and 120 mA excluding the OLED, so the UI board is inside both.
- **Voltage at the load:** the controller's rail band is 3.242 to 3.367 V. The jumper's drop at 0.41 A (AWG28, 120 mm, four XH contacts, three paralleled GND pins) is 40 mV **[ALLOCATION: wire and contact resistances from tables, not re-read]**, so the UI sees 3.202 to 3.367 V.
  - OLED 2.8 to 3.5 V: margin 0.40 V low, 0.13 V high.
  - MCP23S08 1.8 to 5.5 V, TMP122 2.7 to 5.5 V, TLV3202 2.7 to 5.5 V, buzzer 2 to 5 V: inside.
  - **Encoder 3.30 +/- 0.125 V (Grayhill p.3): 26 mV of margin on the low side, 58 mV on the high side.** This is the tightest voltage on the board. It is why the encoder's supply bead FB1 is a 50 mohm part (BLM18PG121SN1D), not a generic 450 mohm bead, and why the encoder has its own 10 uF. If the controller's 3V3 tolerance is ever widened, re-run `ui_calcs.py`.

## U6. Expander map: kept, with GP7 resolved
- **Status: REVISED by U20. GP0, GP1, GP2, GP6 and GP7 are as before (GP7 now reaches the TMP122 through a gate); **GP3 is the TMAG5170 select, GP4 its ALERT input, GP5 a spare input.** The header at 780eaab89 still names GP3-GP5 ENC_A/B/SW; firmware must replace them (U21).**
- **Map (MCP23S08, opcode 0x40, A1 = A0 = GND): unchanged from `ui_board_map.h`.** GP0 START, GP1 STOP, GP2 RESET, GP3 ENC_A, GP4 ENC_B, GP5 ENC_SW, GP6 buzzer (high = on), GP7 LOCAL. `verify_ui.py` traces every role from its GP pin to the physical part, so a change to the board or to the header fails.
- **GP7 (the "OLED RES# or TMP122 CS" the firmware left open) = TMP122 CS#.** The OLED reset is the on-board RC (U12). Reason: the FW-UI-1 derate needs the temperature sensor (enclosure R33), and a power-on RC reset is what the SSD1322 power sequence asks for. GP7 stays an input with pull-ups at reset (R17 10 kohm holds CS# high), exactly what the header does today. When firmware wants the temperature it sets IODIR.7 = 0 and drives OLAT.7 low for the read. **No bit moves.**
- **Naming mismatch to note, not a change:** the enclosure labels the three buttons back (u -75), select/start (u -35), stop (u 5). The firmware calls GP2 RESET (fault reset). The board wires the back button to GP2, select/start to GP0, stop to GP1. Firmware can map RESET to the back button, or the enclosure can relabel.
- **Net names:** `GP0_BTN_START` ... `GP7_TMP_CS_N` in the netlist.

## U7. Encoder: Grayhill 62VG15-H9S-030C, with a comparator
- **Status: SUPERSEDED by U19 and U23 (encoder, J2, comparator, FB1 and every encoder pull-up are removed). Kept as the record of why the comparator existed.**
- **Part (enclosure `controls_r5.py`):** 3.3 V sealed optical encoder, 24 detents, 950 gf push, 3 in lead with an AMP 7-215083-6 plug. It mates a TE 7-215079-6 socket on the board (J2, LCSC C306122).
- **J2 pin map from the Grayhill drawing (62AG/VG Rev. 02/2024 p.3, VG style):** 1 GND, 2 and 3 the normally open push contact, 4 B, 5 A, 6 +3.3 V. This **replaces the assumed map in controller C15** (1 +3.3 V, 2 GND, 3 A, 4 B, 5 switch, 6 +5 V), which was written before the part was chosen. The controller no longer has J5, so nothing there changes; the mating of pin n to pin n on the lead is still to be confirmed with a sample (housing orientation).
- **Supply: 3.3 V, not 5 V.** The VG style is 3.3 V only (+/- 0.125 V, 30 mA max); the AG style is 5 V. Fed from V3V3 through FB1.
- **Outputs are open-collector phototransistors that need a 10 kohm pull-up each and less than 1 nF** (p.3). R9, R10 (and R8 for the switch) are 10 kohm to the encoder rail; C13, C14 are 470 pF at the connector.
- **The levels do not fit the expander.** The encoder guarantees low at most 1.0 V and high at least 2.0 V. The MCP23S08's input low is 0.2 x VDD = 0.63 V at 3.135 V (DS20001919F p.22 D031). The guaranteed low exceeds the expander's threshold by **0.37 V**: the datasheets do not guarantee that a worst-case encoder reads as low. So A and B go through a comparator (U3, TLV3202, rail-to-rail inputs, 1 mV typ and 6 mV max offset, SBOS561C p.6) with the threshold at 1.5 V from R15/R16 off the encoder rail and about 70 mV of hysteresis (R11 to R14). Worst corners (supply 3.175 to 3.425 V, 1 % resistors, 6 mV offset): trips 1.38 to 1.61 V, **0.38 V of margin on the low side and 0.39 V on the high side**. A typical phototransistor probably meets 0.63 V; the datasheet does not say. If the bench shows the margin is never needed, U3 and R11 to R16 can be dropped with a jumper from each raw node to its GP pin.
- **Rotation rate:** 100 rpm maximum x 24 detents x 4 states = 6.25 ms per state, so a 1 ms poll oversamples 6 times. The datasheet prints "optical rise/fall time 30 ms max" (p.3); if that unit is real and not a typo for microseconds, the usable rotation rate is far lower. **Bench item.**

## U8. Buttons: three APEM IPR3PAD2
- **Status: SUPERSEDED by U27 (KSC223G LFG tact switches). The circuit per line (10 kohm pull-up, 1 kohm series, SRV05-4 channel) is kept unchanged.**
- **Part (enclosure R33/R39):** IP67, normally open, round flat actuator, straight PC pins at 5.08 mm pitch, silver gold-plated contacts, 200 mA 50 VDC, contact bounce 10 ms (APEM IP series p.2, p.5). No LCSC listing: hand-fitted panel part, listed as the one `lcsc_exception` in the BOM, bought with the enclosure controls BOM.
- **Circuit per line:** switch to GND, a 10 kohm pull-up on the switch side (0.35 mA wetting current for the gold contacts), a 1 kohm series resistor to the expander pin, an SRV05-4 channel at the switch. The 10 kohm external pull-ups make the firmware's GPPU bits optional (they are harmless).
- **Debounce:** the datasheet bounce is 10 ms and firmware asks for 10 identical polls at 1 kHz, which just meets it. See U14.

## U9. Buzzer: self-oscillating electromagnetic, on V3V3, switched by GP6 (owner decision R35 section 4)
- **Status: REVISED by U28. The part (70 C), its location and its sound-port datum change; the drive circuit (Q1, R21, R22, D1) is unchanged.**
- **Part:** Inghai GSD9605YB-3V2800 (LCSC C255327, extended, stock 11 495). SMD, 9.6 x 9.6 x 5.0 mm, built-in driver, 2.7 kHz, 2 to 5 V operating, **3.3 V rated, 30 mA max**, 80 dB min at 10 cm, **-20 to +70 C** (spec sheet V1.1 p.1 to 2). Electromagnetic, so it has a coil: the flyback diode D1 is fitted across it.
- **Drive:** low-side N-MOSFET Q1 (AO3400A, LCSC C20917, basic: Vth at most 1.45 V, 48 mohm at 2.5 V). Gate drive from GP6 through R21 100 ohm, at least 2.4 V at worst against 1.45 V Vth. Vds on at 31.5 mA is 1.5 mV.
- **Default off at reset:** the MCP23S08 resets with every pin an input (IODIR = 0xFF), so GP6 is high impedance; R22 (100 kohm) holds the gate low, and the leakage of 1 uA across it is 0.1 V against a 0.65 V minimum Vth. `buzzer.default_off_at_reset` models this and fails if the pull-down becomes a pull-up (mutation `invert_buzzer_default`).
- **Allocation:** 31.5 mA of the controller's 90 mA buzzer allocation.
- **Temperature:** the buzzer is rated to 70 C; the board can be near the OLED's 85 C limit (R32 T3). Alternates with the same 9.6 x 9.6 footprint are in the BOM: C530415 GSD9605YB-5V2800 (-30 to +85 C, 5 V rated, operating 2 to 12 V, sound pressure at 3.3 V not specified) and C42420997 (-20 to +80 C). **Bench item:** sound pressure at 3.3 V and at temperature.
- **Sound port:** a closed fascia will muffle it; the enclosure has no port modelled (finding E4).

## U10. TMP122 (the FW-UI-1 derate sensor)
- **Status: REVISED by U20-U22. The sensor now hears CS# only through the qualification gate; its read sequence in U14 item 4 is replaced by U21.**
- **Part:** TI TMP122AIDBVR, SOT-23-6 (LCSC C2877606, extended). **Stock is 17 at JLC** (2026-10-12): buy before the board run.
- **Wiring:** SCK on the bus, CS# on GP7, SO/I on the MISO side before R20. The part reads temperature in the first 16 clocks of any frame and powers up active and continuous, so a read-only wiring needs no MOSI. Its output goes high impedance 30 ns after CS rises (SBOS272B p.9), so it can share MISO with the expander. Timing: 100 ns clock period minimum, output valid 30 ns after the falling edge, input sampled on the rising edge, which is mode 0 compatible. **Confirm idle-low on the bench.**
- **Accuracy:** 1.5 C max from -25 to +85 C. Place it on the front face under the OLED (U17 zones): SOT-23-6 is 1.45 mm and the gap is 3 mm.

## U11. ESD: every external-facing element
- **Status: REVISED by U26. Arrays U4, U5 (J7) and U6 (three buttons, one channel spare) stay; U7 moves to the sensor tab; the encoder channels are gone.**
- **Four SRV05-4 arrays (U4 to U7), 12 of 16 channels used**, Vcc on V3V3: U4, U5 on J7 (six signals); U6 on the three buttons and the encoder switch; U7 on encoder A and B.
- **Series limiting:** buttons and encoder switch 1 kohm to the expander (residual about 8 mA at a 12 V clamp **[UNVERIFIED: the clamp value is taken from the LCSC listing of C2836319, not the datasheet]**, against the MCP23S08's 20 mA input clamp, DS20001919F p.21). Encoder A/B 10 kohm into the comparator (residual 0.8 mA against 10 mA, SBOS561C p.4).
- **What is external:** the button pins and the encoder socket. A finger reaches painted zamac bezels (APEM) and a Zamak shaft (Grayhill); the plungers are polyamide. The clamps are for whatever gets through to the pins.

## U12. OLED interface and reset
- **Status: UNCHANGED.**
- **Pin map (NHD rev. 7 p.4, 4-wire SPI):** 1 GND, 2 V3V3, 4 D/C, 5 and 6 (R/W, E) GND, 7 SCLK, 8 SDIN, 10 to 14 (D3 to D7) GND, 16 /RES, 17 /CS, 19 and 20 (BS1, BS0) GND, 3, 9, 15, 18 open. Pin 1 of the module header is assumed at the left in the drawing (to confirm).
- **Reset:** 10 kohm to V3V3, 1 uF to ground, and a diode (D2) that discharges the capacitor when V3V3 falls. RES# is released 13 to 18 ms after power-up at 0.8 VDD (R and C tolerances, X5R derating). SSD1322 wants a low pulse of at least 2 us (Rev 0.10 p.48) and, in its power sequence, at least 1 ms after VCI before RES# goes low for at least 100 us (p.29); the RC gives the low period. **Firmware rule: do not write the OLED within 30 ms of UI power-up.**
- **Socket height: open.** See U17 finding E2.

## U13. SPI over the 120 mm jumper
- **Status: EXTENDED by U22 (the TMAG5170 path and the extra load of the tab harness; the forward-clock margin at 8 MHz falls from 12 ns to 10 ns). The 5 MHz expander / TMP122 recommendation stands.**
- **Forward path (SCK, MOSI, CS):** 100 ohm at the controller with about 47 pF **[ALLOCATION]** gives a 10 ns 10-90 % edge. At 8 MHz the half period is 62.5 ns; the MCP23S08 needs 45 ns high and low (DS20001919F p.27 to 28); the margin is 12 ns after edge skew. SSD1322 (100 ns cycle, 20 ns high/low, Rev 0.10 p.51) and TMP122 (100 ns) are inside at 8 MHz.
- **Return path (MISO):** MCP23S08 output valid 45 ns after the clock falls (p.28) plus about 4 ns of RC leaves 14 ns of the 62.5 ns half period at 8 MHz, before the ESP32's own input delay. If that delay is the 25 ns of the GPIO matrix **[UNVERIFIED: ESP-IDF SPI master timing notes, not re-read]**, the margin at 8 MHz is **negative (-11 ns)**; at 5 MHz it is +27 ns. **Recommendation to firmware (not a map change): clock the expander and TMP122 at no more than 5 MHz as a separate device configuration and keep the OLED at 8 MHz.** An expander read is 4.8 us at 5 MHz, 0.5 % of a 1 ms poll.
- **Bus utilisation:** one full OLED frame (256 x 64 x 4 bit) is 8.2 ms at 8 MHz, in 512-byte chunks of 0.5 ms (C26).

## U14. Firmware-visible notes (none changes the GP map)
- **Status: REVISED. Item 2 (IODIR read-back) now expects 0x37 when initialised (outputs on bits 3, 6, 7) and 0xFF after a reset; item 4 (TMP122 sequence) is replaced by U21; item 6 (button names) stands; item 1 (debounce) stands, with the KSC2 bounce still to be taken from its drawing.**
1. **Debounce:** APEM's contact bounce is 10 ms; 10 identical 1 kHz polls only just covers it. Use **at least 15**.
2. **UI liveness:** read the expander's IODIR register back each cycle (expected 0xBF with the buzzer output enabled, 0xFF after a power loss) and treat a mismatch, a stuck-0xFF/0x00 MISO, or a failed read as "UI lost": drop RUN_EN within 100 ms, not 1 s. This is what makes the software STOP acceptable (U15).
3. **OLED init:** wait 30 ms after UI power-up; RES# is the board's RC, not firmware's.
4. **TMP122:** set IODIR.7 = 0 and OLAT.7 = 1 once; to read, drive OLAT.7 low, clock 16 bits with CS_EXP# and CS_OLED# high, raise OLAT.7. Keep the OLED and expander deselected during the read.
5. **SPI clocks:** U13.
6. **Button names:** U6.

## U15. STOP: does it need to be a hardware trip?
- **Status: UNCHANGED in substance (software STOP with the "UI lost = stop" rule). The hardware-STOP option below was written around the APEM IPR5PAD2; with the tact family the NC-contact part, if the owner or the lab asks for it, is to be found again (not looked at in this revision).**
- **What exists on the controller (C23, C4, section "failure analysis"):** PERMIT = latch Q AND RUN_EN. RUN_EN is a firmware GPIO (GPIO14) that can only remove permission. The latch trips in hardware on bus over-current and over-voltage, coil, heatsink and runaway temperature, rail faults and watchdog expiry (MCU hang: at most 1.6 s). Every protective function is hardware and independent of the UI. The user STOP is today a software command: button, expander, SPI, firmware, RUN_EN and PWM.
- **What J7 allows:** there is no spare pin. A hardware STOP needs one.
- **Latency:** polling 1 ms plus 10 to 15 ms of debounce plus firmware: about 15 to 25 ms to dropping RUN_EN. A user stop does not need microseconds; when RUN_EN falls the PERMIT gate disables the gate drivers (C23).
- **What the software path cannot do alone:** if the UI board, its jumper or the expander fails, STOP is dead while the hob keeps cooking. U14 item 2 closes that for every J7 or expander fault: the controller treats a UI it cannot read as a STOP. What it does not cover is a single failed STOP contact (welded or open) on an otherwise live UI.
- **Standards (IEC 60335-1, IEC 60335-2-6):** I could not read the standard text in this session (it is not in the repo, and it is paywalled). My reading, to be confirmed with the test lab: neither standard requires a hard-wired user off key on an induction hob; they require that fault conditions of electronic circuits do not create a hazard (60335-1 clause 19.11 and annex R for software), which here is met by the hardware protective trips, and that the appliance cannot switch itself on from a UI fault, which is a firmware (START needs a deliberate action) and not a STOP matter. A software "off" with a monitored UI link is the common architecture for hobs with electronic controls. **[UNVERIFIED]**
- **Recommendation: keep STOP as a software command, with U14 item 2 as a requirement (UI lost = stop), and do not change the controller or J7.** Reasons: it removes the dangerous failure (a dead UI keeps the hob on); the protective functions already do not depend on it; a hardware STOP costs a controller change and the layout is already a routed candidate.
- **If the owner or the lab asks for a hardware STOP, the cheapest fail-safe design I found (not built):**
  1. J7.3 (GND) becomes STOP_OK; GND stays on pins 5, 8, 11, and every signal is still beside a GND (SCK keeps only pin 5). The controller's checks `j7_at_least_3_gnd` and `every_j7_signal_beside_a_gnd` still hold.
  2. STOP becomes the **IPR5PAD2** (the same IP series with straight PC pins and a normally closed and normally open combined contact; the APEM catalogue p.5 lists IP.5PAD, **the exact IPR5PAD2 code and its pinout are unconfirmed**). Its NC pole carries V3V3 through 1 kohm to STOP_OK; its NO pole keeps feeding GP1, so the software path stays.
  3. On the controller, STOP_OK enters a three-input AND with the latch and RUN_EN (SN74LVC1G11 in place of U37, or a second LVC1G08), with a 10 kohm pull-down so an open or unplugged jumper reads STOP. It can only remove permission, like RUN_EN (C23), and it needs no latch.
  4. Cost: one controller part and one pin; the enclosure's STOP button part number; an SRV05-4 channel (there are 4 spare on the UI board). Risk to watch: STOP_OK runs 120 mm beside SCK.

## U16. BOM
- **Status: SUPERSEDED by U31.**
- **23 lines, 56 placements: 22 with LCSC numbers (14 JLC basic, 8 extended) and one without (IPR3PAD2, hand-fitted).** Stock and library type read from the public JLCPCB parts search on 2026-10-12, read-only, nothing ordered. `bom/ui-parts.json`, `bom/ui-parts.csv` (JLCPCB BOM layout).
- **Extended (8):** J7, J2, J3 (connectors), U1 MCP23S08, U2 TMP122 (stock 17), U3 TLV3202, U4 to U7 SRV05-4, BZ1.
- **JLC listing of the MCP23S08 says 4.5 to 5.5 V; the datasheet says 1.8 to 5.5 V** (DS20001919F p.22, D001), 10 MHz at 2.7 V and above for -40 to +85 C (p.27); only the E-temperature range above 85 C is limited to 4.5 V. The board stays at or below 85 C because of the OLED.
- **Off-board items** (enclosure BOM): the OLED module, the encoder with its lead, the jumper.

## U17. Mechanical floorplan against the enclosure (R41)
- **Status: REVISED by U30. The board outline, holes, OLED and button centres stand; the encoder, J2 and the 3 in lead are gone; the sensor tab, keep-outs, buzzer datum and J8 are new.**
- **Numbers from the enclosure source** (`r33_world.py`, R39 M3 holes; `controls_r5.py`), checked by `tools/floorplan.py` against the source when present and against `catalog.json`'s bounding box: board **u -106 to 64 (170 mm), v 15 to 96 (81 mm), 1.6 mm**, front face at w -14. Four Ø7 stud clearances at (-99, 38), (-99, 82), (29, 38), (29, 82); four Ø3.4 M3 holes on the OLED-carrier bosses at (-104, 60), (34, 60), (-75, 92), (5, 92); a 22 x 12 cut-out at u -94 to -72, v 42 to 54. Buttons at (-75, 26), (-35, 26), (5, 26) (bezel Ø17.5, cut-out Ø13.6). OLED 89.2 x 44 at (-35, 64), M2 holes on 83.2 x 38, lens 108.8 x 38.8. J7 (rear face) at (46, 49.5) and the encoder socket J2 at (55, 58). Grayhill encoder at (110, 53), off the board, 50 mm developed lead against 76 mm of cable.
- **The 24 mechanical checks pass** (holes inside the outline, buttons clear of holes by at least 3 mm, connectors inside, J7 and J2 clear of holes, stacker inside the OLED shadow, M2 clear of M3).
- **Face assignment for layout:** front face (w -14 to the OLED at -11): buttons, the OLED socket, TMP122 (1.45 mm tall under the OLED), the buzzer (9.6 x 9.6 x 5.0 mm, so outside the OLED footprint, at the left end). Rear face: J7, J2 and everything else. Advisory zones are drawn in `evidence/floorplan.svg`.
- **Findings for the enclosure (recorded, not ours to change):**
  - **E1:** the M3 hole at (-104, 60) leaves **0.3 mm** of FR-4 to the board edge (the Ø6 carrier boss overhangs the edge). Move it 3 mm inboard or notch the outline.
  - **E2 (open item U-OPEN-1):** the OLED stacker is modelled 3.0 mm high. The 1 x 20 2.54 mm female sockets on LCSC are 8.5 mm. The BOM carries C46595982 as a placeholder. Either the gap opens by 5.5 mm (taller carrier bosses) or the enclosure approves a soldered low-profile header (the OLED then cannot be unplugged).
  - **E3:** J7 and J2 envelopes are 1.4 mm apart; the mated XHP-12 and Micro-MaTch housings are larger.
  - **E4:** no sound port for the buzzer.

## U18. Layout notes for the next stage
- **Status: REVISED: the encoder and comparator notes are void; see U20 (place U9, U10 at the expander) and U26 (tab).**
- Clamps U4, U5 at J7; U6, U7 at their connectors; R20 at the chips. Each IC has its own 100 nF as `c_<name>` for `u_<name>` (the verifier pairs them by that name).
- Keep the SCK, MOSI and MISO runs short and with their GND neighbours; keep D/C and the CS lines away from the buzzer drain.
- The comparator and its 10 kohm inputs sit next to J2, not next to J7.
- The buzzer and Q1 sit at the far left, away from the sensor and the encoder rail.

## Open items (revision 1, superseded by U32)
1. **E2 / U-OPEN-1:** OLED socket height versus the 3.0 mm gap (enclosure).
2. **E1:** hole (-104, 60) edge wall (enclosure).
3. **E4:** buzzer sound port (enclosure); sound pressure at 3.3 V and temperature (bench).
4. **Owner or lab:** STOP as hardware or software (U15).
5. **Firmware:** 5 MHz expander clock, 15-poll debounce, UI-lost rule, 30 ms OLED wait (U13, U14).
6. **Bench:** encoder low level against the comparator margin and the print of "30 ms" rise time (U7); the encoder rail's 26 mV low-side margin (U5); SRV05-4 clamp value (U11); harness resistances (U5).
7. **Procurement:** TMP122 stock 17.

## U19. Revision 2: the owner's decision and what changes (2026-10-12)
- **Removed:** Grayhill 62VG15-H9S-030C encoder with its socket J2 (TE 7-215079-6), the comparator U3 (TLV3202), the reference divider and hysteresis resistors, the encoder pull-ups, noise capacitors, supply bead FB1, C8, C9, the encoder ESD array U7, and the three APEM IPR3PAD2 buttons. `verify_ui.py` section `removed` checks that none of these MPNs, instances or nets is left in the netlist or the BOM.
- **Added:** three C&K KSC223G LFG tact switches (U27); a TMAG5170A1 Hall sensor on a separate sensor tab (U23-U26) with a 10-way harness (J8, J9); the CS qualification gates U9, U10 (U20-U22); a 390 ohm series resistor in the sensor's SDO; a replacement buzzer (U28); an SRV05-4 on the tab (U7).
- **Unchanged:** J7 (all 12 pins byte-equal to controller C26), the OLED interface and reset, the TMP122, the expander and opcode 0x40, GP0 Select/Start, GP1 Stop, GP2 Back, GP6 buzzer, GP7 TMP122 select, V5_UI unused, the SRV05-4 scheme at J7 and at the buttons.
- **Net effect:** 51 placements (was 56), 22 BOM lines (was 23), 3V3 non-OLED current 45.3 mA (U29).

## U20. CS qualification: the scheme and its truth table
- **Problem:** a device selected by an expander GP is selected by an SPI write to the expander itself. That write clocks SCK and MOSI while the device may still be selected (it would decode the frame: a TMAG5170 could take a register write and drive MISO; the TMP122 would drive MISO), and the same happens for every OLED frame. The sensor's select must therefore be qualified in hardware by the two chip selects of the shared bus.
- **Scheme (U9, U10, three gates):** `BUS_BUSY = NAND(CS_EXP#, CS_OLED#)` (U9, SN74LVC1G00DBVR); `CS_dev# = GPx OR BUS_BUSY` (U10, SN74LVC2G32DCUR, one OR per device). A device is selected only when **its GP is low AND CS_EXP# is high AND CS_OLED# is high**. GP3 drives the sensor's gate (GP3 low = select), GP7 the TMP122's: the same low-selects convention as before, so the firmware's GP7 meaning does not change.
- **Truth table, each device (X = GP3 or GP7; evaluated from the netlist for both devices by `verify_ui.py` section `cs`, 8 of 8 rows each):**

| GPx | CS_EXP# | CS_OLED# | BUS_BUSY | CS_dev# | device |
|---|---|---|---|---|---|
| 0 | 0 | 0 | 1 | 1 | deselected (expander and OLED both active) |
| 0 | 0 | 1 | 1 | 1 | deselected (expander write or read) |
| 0 | 1 | 0 | 1 | 1 | deselected (OLED frame) |
| **0** | **1** | **1** | 0 | **0** | **selected** (the only row) |
| 1 | 0 | 0 | 1 | 1 | deselected |
| 1 | 0 | 1 | 1 | 1 | deselected |
| 1 | 1 | 0 | 1 | 1 | deselected |
| 1 | 1 | 1 | 0 | 1 | deselected (idle) |

- **Power-up and reset:** the MCP23S08 resets with every GP an input (IODIR = 0xFF, high impedance). R26 (GP3) and R17 (GP7) pull the request lines high, so both CS# outputs are high whatever CS_EXP# and CS_OLED# do (`*_cs_deselected_at_reset`, which also evaluates the four chip-select combinations). If a gate is unpowered or the harness is unplugged, R24 (at the sensor) and R29 (at the TMP122) hold CS# high. All three ICs and both devices share V3V3, so the gates and the devices come up together; the gates have 10 uA ICC and no enable pin.
- **MISO: every driver is high-Z unless qualified-selected.** Three drivers share MISO_LOCAL: MCP23S08 SO (enabled only by CS_EXP# low, and it drives only the data bytes of a read: DS20001919F p.6 and Fig. 2-5 p.26), TMAG5170 SDO (high impedance while CS is high, SBASAF4 p.28), TMP122 SO/I (high impedance 30 ns after CS rises, SBOS272B p.9). Exhaustive 16-row table over (GP3, GP7, CS_EXP#, CS_OLED#), read from the netlist (`miso_drivers_high_z_unless_qualified_selected`): the sensor drives only for (GP3, CS_EXP#, CS_OLED#) = (0, 1, 1), the TMP122 only for (GP7, CS_EXP#, CS_OLED#) = (0, 1, 1), the expander only for CS_EXP# = 0; **at most one driver is ever enabled except when firmware drives GP3 and GP7 low together** (one row of 16). In that row the sensor's 390 ohm R28 keeps the shorted current at 3.465 V / 390 ohm = 8.9 mA, under the sensor's 10 mA absolute maximum (SBASAF4 p.4); the check `tmag_sdo_series_resistor_limits_double_select_below_10mA` recomputes it from the netlist value.
- **A sensor left armed by mistake is safe:** with GP3 low during an expander or OLED frame, BUS_BUSY deselects the sensor 18.8 ns (worst case) after that frame's chip select falls, 31 ns before the first expander clock (TCSS 50 ns): the sensor decodes nothing and drives nothing; the frame it was in is lost.
- **Why not a decoder:** a 2-to-4 decoder would also give mutual exclusion, but GP7 is fixed as the TMP122's select, and a decoder needs both GPs to encode the address (the owner's reference). Two OR gates plus one NAND keep one GP per device and are checkable row by row. The one cost is that a firmware bug that drives both GPs low is not blocked by hardware, only current-limited (above).
- **Layout notes:** U9 and U10 next to the expander, each with its own 100 nF (C17, C18); R26, R17, R24, R29 as drawn. CS_TMAG# runs 150 mm through the harness: it is a gate output (driven, not floating), with a GND neighbour at J8 pin 2.

## U21. Firmware sequence (required, not a map change) and the MISO check
1. **Init after UI power-up (wait 30 ms, U12):** write OLAT with bits 3 and 7 = 1 **before** writing IODIR with bits 3, 6, 7 = 0. OLAT resets to 0 and would drive the pins low. IODIR then reads 0x37. GP4 and GP5 stay inputs; GPPU may stay as in the header.
2. **Expander device configuration:** mode 0, at most 5 MHz, **`cs_ena_posttrans` >= 3 bit cycles**: CS_EXP# stays low at least 600 ns after the last clock, so the GP output (valid up to 500 ns after the data clock, MCP23S08 TGPOV, p.29) has settled before CS_EXP# rises. Without it a late GP edge produces a zero-clock select pulse of up to 355 ns on the sensor (calc: `zero_clock_select_glitch_ns_posttrans0`).
3. **Lock the whole SPI bus** for steps 4-6 (OLED chunks cannot interleave).
4. **Select:** write OLAT with GP3 low (TMAG) or GP7 low (TMP122).
5. **Wait >= 1 us, then clock exactly 32 bits (TMAG5170) or exactly 16 bits (TMP122) with no hardware chip select** (`spics_io_num = -1`): CS_EXP# and CS_OLED# stay high, so the gate holds the selection. SCK at most 5 MHz: 1 MHz first, 2.5 MHz recommended cap (U22).
6. **Wait >= 1 us, then release:** write OLAT with the GP high. CS_EXP# falling deselects the sensor before the first expander clock.
7. **Unlock.** One select/release pair per sensor frame: CS must toggle between 32-clock frames (SBASAF4 p.28). Never leave GP3 or GP7 low outside steps 4-6; never set both low.
8. **Reset and brown-out:** an expander reset returns IODIR to 0xFF; the pins float to their pull-ups and both devices deselect. The IODIR read-back of U14 item 2 detects it; firmware repeats step 1.
- **MISO check (calcs `cs_qualification`, verifier `cs`):** the MCP23S08 first drives SO at the 17th clock of a read, at least 3.2 us after its CS falls (5 MHz); the sensor and the TMP122 are high impedance at most 74 ns after that same edge (gate 18.8 ns + TMAG disable 55 ns): the handover margin is 3.1 us. During the sensor frame CS_EXP# is high: the MCP23S08's SO is high impedance (write and idle states), and the OLED has no MISO. With the sequence obeyed no two drivers are ever enabled.
- **If GP3 were left low across an expander read (not allowed):** the sensor reselects at most 2 ns after CS_EXP# rises while the MCP23S08 may still drive for up to 100 ns (TDIS): at most 98 ns of overlap with no SCK edge in it, current limited by R28.

## U22. Timing proof of the qualification
All numbers are worst case inside the cited limits and are recomputed by `tools/ui_calcs.py` (section `cs_qualification`; the verifier reads its checks).
- **Gates:** NAND tpd 1 to 5.0 ns, OR 1 to 4.8 ns (3.3 +/- 0.3 V, -40 to 125 C: TI SCES212 p.6, SCES201N p.6). Plus 4 ns for the chip-select edge from the J7 pin to the gate input (100 ohm at the controller, cable) and 5 ns for CS_TMAG# to reach the sensor over the harness [ALLOCATION].
- **Select (step 4 to 5):** CS_dev# falls at most **18.8 ns** after CS_EXP# rises (the GP edge is already settled with `cs_ena_posttrans` 3: CS_EXP# rises 700 ns after the last data clock against TGPOV 500 ns). The sensor needs 45 ns before the first SCK rising edge (tsu_cs, SBASAF4 p.10); with a 1 us wait the margin is **936 ns**. TMP122: t5 = 40 ns, margin 941 ns.
- **Release (step 6):** CS_dev# rises at most **18.8 ns** after CS_EXP# falls, **31 ns** before the first clock of the expander write (the MCP23S08 needs CS setup TCSS = 50 ns, so the ESP32 gives at least that). The sensor's hold (last SCK fall to CS rise, th_cs 45 ns) is met with 957 ns.
- **Frame spacing:** CS_dev# stays high at least 11.6 us between two sensor frames (two expander writes and two waits) against tw_cs = 100 ns.
- **Sensor SDO on MISO:** TMAG5170 SDO valid 45 ns after the SCK falling edge (p.11) plus RC through R28 (390 ohm), the harness, R20 and the controller's 100 ohm: **62 ns**. Against the half period and the ESP32's 25 ns GPIO-matrix input delay [UNVERIFIED allocation]: margin 413 ns at 1 MHz, 113 ns at 2.5 MHz, **13 ns at 5 MHz**. The ceiling with 10 ns of margin is 5.15 MHz, so the owner's "at most 5 MHz after signal checks" holds; I recommend **2.5 MHz as the cap** and 5 MHz only after a scope check of the MISO eye. The expander and TMP122 stay at 5 MHz (U13); the OLED at 8 MHz.
- **Forward path with the tab:** the harness adds 10.5 pF and the sensor's inputs to SCK and MOSI; the 8 MHz clock-high margin at the MCP23S08 falls from 12 ns to 10 ns (unchanged recommendation: OLED at 8 MHz is its own device configuration).

## U23. TMAG5170: range, averaging and update schedule
- **Part:** TMAG5170A1QDGKR (LCSC C5220642, stock 4 342 and USD 2.31 at qty 1 on 2026-10-12, extended). SPI mode 0 (SDI latched on the rising edge, SDO changes on the falling edge, p.28), 3.3 V (2.3 to 5.5 V), CRC on (default; never write CRC_DIS), 32-bit frames. TEST (pin 7) is grounded; ALERT goes to GP4 with R25.
- **Range: +/-100 mT (X_RANGE = Y_RANGE = Z_RANGE = 10b).** The seated field is 55.7 mT at 20 C and 52.7 mT at 176 C (U25): the +/-50 mT range clips at nominal. With a 0.5 mm push, a 0.2 mm tighter gap, -40 C and +5 % magnet tolerance the largest field is 73.0 mT: 27 % headroom and inside the 80 % of full scale at which the datasheet specifies its angle error (p.8). The weakest field (hot, gap +0.2 mm, -5 %) is 47.3 mT. Resolution: 3.07 uT per LSB, 0.004 degree.
- **Conversion: CONV_AVG = 100b (16x), XYZ, continuous mode, SmCo temperature coefficient (MAG_TEMPCO = 10b), temperature channel once per set.** One set takes 1.25 ms (0.8 ksps, p.17). DEVICE_CONFIG = 0x422C, SENSOR_CONFIG = 0x01EA, SYSTEM_CONFIG = 0x0000, written in configuration mode (SENSOR_CONFIG, SYSTEM_CONFIG, then DEVICE_CONFIG last). Angle by atan2 of the raw X and Y in firmware (the CORDIC output is 0.25 degree effective); Z and |B| for push and removal.
- **Why 16x:** angle noise (1 sigma) = per-axis noise / signal; per-axis noise at +/-100 mT is read from SBASAF4 Fig. 6-8, p.12 (upper envelope, +/-10 %, [UNVERIFIED: read from a plot]). Peak-to-peak over 10 s is 2000 samples, about 7 sigma:

| CONV_AVG | 1x | 2x | 4x | 8x | **16x** | 32x |
|---|---|---|---|---|---|---|
| noise per axis, uT | 190 | 135 | 95 | 62 | **45** | 34 |
| p-p jitter at 52.7 mT, deg | 1.45 | 1.03 | 0.72 | 0.47 | **0.343** | 0.259 |
| set time, ms | 0.1 | 0.18 | 0.32 | 0.63 | **1.25** | 2.5 |

  8x does not leave room for the stray field (U24); 32x spends 2.5 ms for 0.08 degree. The X and Y results of one set are converted 0.4 ms apart: at 2 revolutions per second the skew is 0.29 degree **while turning** (not a static error).
- **Update schedule:** read every 5 ms (200 Hz). Three frames per set (X, Y, Z results); each response arrives in the next frame and carries conversion status and the set count; accept a set only when the three responses share the set count, CRC is good and no ERROR_STAT / CRC_STAT / FRAME_STAT / conversion-status flag is set (CRC correct is not the same as fresh and plausible). Bus time per update: 311 us at 1 MHz (6.2 % of 5 ms), 253 us at 2.5 MHz; worst data age 2.1 ms including one 512-byte OLED chunk (0.51 ms) ahead of it. Run the AFE diagnostics at power-up and once a second. Read TEMP_RESULT once per group (25 C code 17522, 60 LSB per C) for gain-mismatch correction.
- **Inhibit:** any invalid or stale set inhibits at that sample; no valid set for 100 ms (20 updates) inhibits; replacement needs 200 ms of valid, stable data and an explicit Start (the owner's SPEC). The bus lock of U21 and the exact frame lengths are firmware obligations.
- **Quantities to calibrate per unit (not here):** the sensitivity mismatch between X and Y drifts up to +/-4.0 % from 25 to 125 C (SBASAF4 p.7), which is 1.15 degree of angle error if uncorrected (0.23 degree at the typical 0.8 %): the per-unit calibration must include the temperature channel.

## U24. Stray-field angle error and the 55 kHz gap
- **Inputs (owner's solver, die at w = -4 mm, 45 A peak, no fascia in the model):** 33.206 uT rms (31 kHz, pan, bare), 0.960 (pan, base and roof), 112.241 (60 kHz, no pan, bare), 17.696 (no pan, base and roof). Signal: 52.685 mT (hot magnet), the weakest design field, so the error is a maximum.
- **Worst-case angle error** = asin(sqrt(2) x B_rms / B_signal) at the worst phase and direction, **no filtering credit**:

| case | B rms, uT | peak, uT | peak angle error, deg | p-p jitter with noise, deg |
|---|---|---|---|---|
| pan, 31 kHz, bare | 33.206 | 46.96 | 0.0511 | 0.445 |
| pan, 31 kHz, base and roof | 0.960 | 1.36 | 0.0015 | 0.346 |
| **no pan, 60 kHz, bare (worst)** | 112.241 | 158.73 | **0.1726** | **0.688** |
| no pan, 60 kHz, base and roof | 17.696 | 25.03 | 0.0272 | 0.397 |

  Stray-field angle error is **at most 0.173 degree** in every case (0.027 degree assembled); the non-repeatable error (3.5 sigma noise 0.171 + stray + quantisation + 0.057 residual gain mismatch) is at most 0.40 degree, which leaves at least 0.6 degree of the 1 degree for the calibration residual, the magnet and the mechanism. **The 0.5 degree p-p jitter holds in the three pan or assembled cases (0.35 to 0.45) and does not hold in the bare no-pan 60 kHz transient (0.69):** noise 0.34 plus a 2 x 0.17 degree tone. It stays under the 1 degree step hysteresis everywhere. More averaging cannot reach 0.5 in that case at 200 Hz; the owner's remedies are the base and roof (0.40) or inhibiting a no-pan operation. This is the only target the electronics do not meet, reported by calcs as `jitter_pp_bare_nopan_exceeds_0p5deg` and excluded from the gate on purpose.
- **Filtering: none is claimed.** The sensor samples one axis about every 25 us (40 ksps); a coil tone aliases, and a 16-sample average passes it at 50 % or more between 38.5 and 41.5 kHz, which is inside the 31 to 55 kHz tank range (gain exactly 1.0 at 40 kHz); elsewhere in the range it is 0.13 or less (31 kHz: 0.09; 55 kHz: 0.08 over the 3.0 to 3.5 MHz oscillator tolerance). The error is bounded by the unfiltered amplitude above.
- **The 55 kHz gap:** no solver result exists there. Bounds, [ASSUMPTION]: with a pan, at most the 31 kHz pan value (the pan's screening grows with frequency): at most 0.051 degree; without a pan, at most the 60 kHz bare value (the quasi-static coil field at the same 45 A does not grow with frequency): at most 0.173 degree. A stray amplitude of 162.6 uT rms would use 0.25 degree and 650 uT rms the whole 1 degree: the bare no-pan envelope has 1.45 times headroom to the former. The bench closes it: log raw X, Y, Z with the coil running through 31 to 55 kHz and its harmonics (the owner's VALIDATION), and record whether 28 A is peak or rms (a factor 0.88).

## U25. Magnet field margin, push and removal
- **Model:** the owner's closed form (uniform diametral cylinder, on axis): B = Br/4 [z2/sqrt(R^2+z2^2) - z1/sqrt(R^2+z1^2)], R = 5 mm, h = 5 mm. It reproduces the owner's table to 0.01 mT: 55.728 mT at a 5 mm gap (Br 1.19 T), 20.106 at 9 mm, 6.384 at 15 mm, 52.685 at 176 C, +15.29 % for a 0.5 mm push, -5.46 % / +5.82 % for +/-0.2 mm. Checks `model_reproduces_owner_*` fail if the formula or the constants drift.
- **Removal:** threshold at half the weakest seated field, 23.7 mT, is crossed when the knob is lifted to a 7.85 mm gap (2.9 mm lift). The sensor's own X/Y/Z threshold alerts could do this in hardware; firmware compares |B| each set.
- **Push:** a 0.5 mm push raises |B| by 15.3 %; the 16x noise on |B| is 0.09 %; gap tolerance is +/-5.5 % and 20 to 176 C is -5.4 %. Rule: relative change against a slow baseline (time constant far above 1 s), threshold about 8 %. Absolute |B| cannot separate push from tolerance and temperature, as the owner says; the mechanism's tilt and the retention steel are not in this model.
- **Not in the model:** tilt, lateral offset, the knob's retention steel, irreversible magnet loss, the finite fascia; these are the owner's bench items.

## U26. Sensor tab, harness, ESD return path and steel keep-out
- **Why a separate tab:** the owner's table puts the die at w = -4 mm (5 mm below the magnet's nearest face at w = +1). The UI board's front face is at w = -14, so the sensor on the main board would sit at w = -13.2 (14 mm gap, 6 mT). The sensor therefore lives on a **separate small PCB (the "sensor tab")**, 64 x 32 mm, centred on the knob axis, front face at **w = -4.78**, so that the Hall plane (0.32 mm below the package top, package top 1.1 mm above the board; SBASAF4 p.16 and DGK0008A drawing) is at w = -4.00. The package top then clears the fascia rear (w = -3) by 0.68 mm. If the enclosure prefers one rigid-flex board the netlist is unchanged; one rigid board cannot do it.
- **Harness (J8 on this board, J9 on the tab, JST SM10B-SRSS-TB, 1:1, about 150 mm):** 1 CS_TMAG#, 2 GND, 3 SCK, 4 GND, 5 MOSI, 6 GND, 7 MISO (R28 390 ohm at the sensor), 8 GND, 9 ALERT, 10 V3V3. A GND beside every signal. The 3.4 mA supply drops about 1 mV in the harness. Twist or keep each signal with its GND to limit pick-up: 3 cm^2 of loop at 158 uT, 60 kHz would couple 18 mV.
- **Tab parts:** U8 TMAG5170, C16 100 nF at 5 to 9 mm from the Hall element, R24 (CS# pull-up), R28, SRV05-4 U7 on SCK, MOSI, CS# and ALERT (the "re-evaluate clamps at any sensor extension" request; Vcc on V3V3).
- **ESD:** contact discharge from a cap or the knob must reach the bonded fascia through the enclosure's deliberate conductive contacts. On this unit: no net in the netlist is a chassis, PE or fascia net (`no_chassis_or_pe_net_in_the_netlist...`); the tab mounts on **insulating** standoffs at NPTH holes with no copper in the keep-out of the holes; J8/J9 mount pads are not tied to ground at layout; the SRV05-4 arrays clamp to V3V3 and GND for what gets through the switch pins and the harness, never as the discharge path; the main board's four M3 holes stay non-plated and unbonded to GND, as in R41. Anodizing, grease and bearings are not relied on (the owner's SPEC).
- **Steel / fastener keep-out: R = 25 mm around (110, 53).** Dipole upper bound for an M3 x 8 steel screw (1.2e-7 m^3, demagnetising factor 0.1, factors 2 on both axes): 1.36 degree at 15 mm, 0.24 at 20 mm, **0.063 at 25 mm**, 0.021 at 30 mm (floorplan check `steel_screw_at_the_keepout_radius_le_0p07deg`; far-field dipoles, not a field map: the owner's assembled map sets the final radius). The tab's three M2.5 non-magnetic standoffs sit at (83, 42), (83, 64), (138, 53): the fastener heads clear the circle by at least 25.5 mm. J9 (82, 53) is 25.9 mm out. No component within 12 mm of the Hall element except U8 and C16; no steel on either face.
- **Thermal:** U29.

## U27. Tact switches
- **Part:** C&K (Littelfuse) KSC223G LFG, current manufacturer reference **Y31B13136FPLFG**, gold contacts, G (gullwing) terminals, 6.2 x 6.2 mm body, actuator top 3.5 mm above the board, 2.25 +/- 0.55 N, electrical travel 0.35 +0.25/-0.15 mm, minimum contact load 0.1 mA at 20 mV, maximum 10 mA (the owner's quotation of the KSC2 drawing). **I could not fetch the KSC2 drawing** (access denied, three mirrors): the figures are the owner's, the footprint is "the manufacturer's G land pattern" named `Temper_UI:CK_KSC2_G_gullwing_6.2x6.2mm` in the netlist, and the pad pairing (two electrical terminals, two internally shorted pairs?) is to be taken from the drawing at layout (as the owner's SOURCES.md also says).
- **Centres (front face, the board's front at w = -14):** SW3 Back/Reset (-75, 26) GP2; SW1 Select/Start (-35, 26) GP0; SW2 Stop (5, 26) GP1. Body clear of every hole by at least 3 mm; the caps' R7 envelopes are 26 mm apart.
- **Circuit per line (unchanged from U8):** switch to GND, 10 kohm pull-up on the switch side, 1 kohm series to the expander pin, SRV05-4 channel at the switch. Contact current closed: 0.282 mA (3.135 V, 1 % resistors) to 0.35 mA (3.465 V), inside the 0.1 to 10 mA envelope (`pullups.wetting_ge_0p1mA_ksc2_minimum`).
- **Debounce:** the KSC2 bounce time is not in the owner's figures; U14 item 1 (15 polls at 1 kHz) stands as the allocation, and Stop stays raw-immediate in the owner's driver.
- **Sourcing:** JLC lists C2798957 (KSC223G LFG) with **0 stock** on 2026-10-12, and Y31B13136FPLFG is not in the JLC parts search. The BOM carries it as the one `lcsc_exception` (consigned or hand-fitted, like the IPR3PAD2 it replaces).
- **Open:** the 10 % minimum tactile ratio does not guarantee the assembled 25 % snap (owner's SPEC); that is a cap-stack force trace, not a board matter.

## U28. Buzzer: part, temperature, location and sound-port datum
- **Decision: GSD9605YB-5V2800 (LCSC C530415), -30 to +85 C, 2 to 12 V operating, 30 mA, 9.6 x 9.6 x 5.0 mm, same footprint**, in place of the 70 C GSD9605YB-3V2800. Stock 280 at JLC (2026-10-12, USD 0.72). The spec sheet link on LCSC returned HTML, so the rating is the LCSC listing's [UNVERIFIED]. Drive circuit unchanged (Q1, R21, R22, D1).
- **Why:** a one-node model (calcs `buzzer_thermal`: fascia radiation and a 6 mm air gap, sides to the internal air at 8 W/m2K, bottom and pads to the board, 0.1 W self-heating) with the owner's thermal table (fascia at v = 26: 139.7 C, internal air 65 C in the 40 C ambient case, pushed pan 300) gives a body temperature of **69.9 C with the board at the 65 C air, 79.3 C at 75 C, 83.9 C at the 80 C design limit.** The board, not the fascia, sets it (fascia coupling 1.3 mW/K against 38 mW/K to the board). The 70 C part has 0.1 K of margin at the 65 C board and fails at 75 C; the 80 C alternative (C42420997, 3V3) fails at the 80 C board; the 85 C part has 1.1 K at the 80 C limit. Margin is thin at the limit: the board zone must stay below 80 C and be measured.
- **Location (the cooler spot):** the front face's lowest-v corner, at the far left, away from the OLED's 1.1 W and from J7: **body centre (u, v) = (-95.0, 24.0)**, box 9.6 x 9.6 (u -99.8 to -90.2, v 19.2 to 28.8). Clear of the board edge by 4.2 mm, of the Ø7 stud (-99, 38) by 5.7 mm, of the cap R7 of SW3 by 8.2 mm, of the OLED by 16.9 mm (floorplan checks).
- **Sealed port datum:** centre **(u, v) = (-95.0, 24.0)**, membrane / port opening up to Ø6 mm (centred within +/-0.5 mm); the buzzer top (sound outlet) is at **w = -9.0**, 6.0 mm behind the fascia rear (w = -3): a 6 mm acoustic cavity to be sealed to the membrane (the owner's E4).
- **Open:** sound pressure at 3.3 V (the listing gives 80 dB at 5 V) and at temperature; the 3.3 V figure of the old part was 80 dB at 10 cm. Bench item.

## U29. Power and thermal allocation
- **3V3 at datasheet maxima, V3V3 = 3.465 V:** OLED 340 mA, buzzer 30.0, MCP23S08 8.0 (allocation), TMAG5170 3.4 (IACT, p.5), pull-ups 3.81 (eleven 10 kohm lines all low at once), TMP122 0.075, gates 0.02, SRV05-4 leakage 0.004. **Total 385.3 mA; without the OLED 45.3 mA against the controller's 120 mA: 74.7 mA of headroom** (the verifier recomputes it from the netlist and gets 385.32). Bridge to the owner's 78.1 mA: 71.9 - 30 (encoder) = 41.9 mA; this board counts three more pull-ups the owner's figure left out (+1.04 mA), drops the comparator, its divider and three encoder pull-ups (-1.32), takes the buzzer at 30 not 31.5 mA (-1.5), and adds the sensor (+3.4), the gates (+0.02) and five new pull-ups (+1.73): 45.3 mA. V5_UI 0.51 mA of 30 mA (unused).
- **Rail at the UI** (U5 method): 3.205 to 3.367 V (0.037 V of drop at 0.385 A, AWG28 and contact resistances [ALLOCATION]). OLED margins 0.40 V low and 0.13 V high (now the tightest); TMAG5170 2.3 V minimum, 0.90 V of margin.
- **Thermal allocation:** keep the main board at or below 80 C where the MCP23S08, TMP122 and OLED sit (the owner's SPEC). Buzzer body 69.9 to 83.9 C for a 65 to 80 C board (U28). TMP122 stays in its zone under the OLED (u -42 to -28, v 52 to 58), front face, so FW-UI-1 sees the OLED zone. **Sensor tab:** a plate model (calcs `sensor_thermal`: tab 64 x 32 mm, 1.78 mm air gap and radiation to the fascia, 8 W/m2K to the internal air, low-conductivity standoffs, 100 K/W package to board [ALLOCATION]) with the knob fascia at 150.2 C and 65 C air gives a tab at 119 C and a **die at 120 C: inside the 150 C rating and the 125 C design target by 5 K**, with a fascia-to-air coupling ratio of 1.73 against the allowed 2.38 for 125 C (the owner's relation). The owner's thermal proof governs; a taller or less conductive standoff, or a window in the carrier, lowers the coupling.

## U30. Datums (enclosure front-local frame: u right, v up, w outward; fascia rear w = -3, front w = 0)
| item | datum |
|---|---|
| Knob axis | (110, 53) |
| TMAG5170 Hall centre (die) | **(110.000, 53.000, w -4.00)** |
| TMAG5170 package centre | (109.730, 53.040) with pin 1 upper left seen from the front, package top toward the fascia (Hall is 1.77 mm from the pin 1-4 edge and 1.54 mm from the pin 1 end of the 3.0 mm body: SBASAF4 p.16) |
| Sensor tab | u 78 to 142, v 37 to 69, front face w -4.78, rear face w -6.38, 1.6 mm; package top w -3.68 |
| Tab standoffs (M2.5, non-magnetic, 1.78 mm, insulating) | (83, 42), (83, 64), (138, 53) |
| Tab connector J9 | (82, 53), long axis along v |
| UI board connector J8 | (56, 78), rear face |
| Steel / fastener keep-out | R 25 around (110, 53) (R 12 for components) |
| Face-to-die gap | 5.0 mm (magnet nearest face w +1.00) |
| Tact switches (front face) | (-75, 26) Back GP2; (-35, 26) Select/Start GP0; (5, 26) Stop GP1; body 6.2 x 6.2 |
| **Buzzer BZ1 / sealed port** | **(-95.0, 24.0)** body 9.6 x 9.6, front face, top at w -9.0, port up to Ø6 |
| Main board | unchanged: u -106 to 64, v 15 to 96, front face w -14, 1.6 mm |
All of these are drawn in `evidence/floorplan.svg` and checked by `tools/floorplan.py` (47 checks).
- **Findings for the enclosure (R44):** E1 (hole (-104, 60) 0.3 mm wall), E2 (OLED socket 8.5 mm against the 3.0 mm gap) are unchanged; E3 J7 service access after J2's removal; E4 now carries the buzzer datum; **E5 (new)** the sensor tab: three non-magnetic standoffs 1.78 mm high, a window for the harness, no steel within 25 mm of (110, 53).

## U31. BOM delta (stock and price read from the public JLCPCB parts search on 2026-10-12, read-only, nothing ordered)
- **Removed (8 lines):** 7-215079-6 (J2), TLV3202AIDR, BLM18PG121SN1D, GSD9605YB-3V2800, 0603B471K500NT x2, 0603WAF4703T5E x2, 0603WAF1202T5E, IPR3PAD2 x3 (hand-fitted, not in the JLC prices).
- **Added (7 lines):** TMAG5170A1QDGKR C5220642 (stock 4 342, USD 2.3095), SN74LVC1G00DBVR C7826 (5 336, 0.1224), SN74LVC2G32DCUR C91874 (9 631, 0.5473), SM10B-SRSS-TB(LF)(SN) x2 C160409 (84 949, 0.4317 each), GSD9605YB-5V2800 C530415 (280, 0.7199), 0603WAF3900T5E C23151 (basic), Y31B13136FPLFG x3 (exception: C2798957 listed, **0 stock**, USD 0.4194).
- **Quantity changes:** 1 kohm 4 to 3, 10 kohm 13 to 12, 10 uF 2 to 1.
- **Totals:** 22 lines (was 23), 51 placements (was 56), 21 with LCSC codes (11 basic, 10 extended) and one without (the tact, consigned). JLC-listed parts at qty-1 prices: USD 12.60 (was 11.32), +USD 1.28 per board, before the tacts (3 x 0.42 = USD 1.26 when stocked) and without the IPR3PAD2 and Grayhill that left. **TMP122 stock 17** is still the shortage to buy ahead of the run.
- **Off-board (enclosure BOM):** the sensor-tab harness (SHR-10V-S x2, 20 contacts, AWG28-30, about 150 mm), the magnet, three non-magnetic standoffs.

## U32. Open items and risks (revision 2)
1. **Firmware (U21):** the whole sequence; replace the ENC_A/B/SW names of GP3-GP5; `cs_ena_posttrans` >= 3 on the expander device; sensor frames without a hardware chip select; IODIR 0x37 read-back.
2. **Enclosure (R44):** E5 (tab standoffs, window, keep-out); E1, E2, E3; E4 with the datum of U28.
3. **Bench:** MISO eye of the sensor at 2.5 and 5 MHz; the ESP32 GPIO-matrix input delay (25 ns assumed); stray field through 31 to 55 kHz and harmonics (U24) and the bare no-pan 0.69 degree jitter; tact drawing, footprint pairing, bounce and force trace; buzzer sound pressure at 3.3 V and body temperature; tab and die temperature against 125 C; noise numbers read from a plot (U23); the tilt, retention-steel and irreversible-loss effects on the magnet.
4. **Documents not obtained:** KSC2 drawing (access denied), Inghai spec sheet for the 5V2800 (the LCSC link returned HTML), the JST SH drawing.
5. **Procurement:** the tact (0 stock), the TMP122 (17), the buzzer (280).
6. **Owner or lab:** STOP as hardware or software (U15), unchanged.
7. **A firmware error that drives GP3 and GP7 low together is limited to 8.9 mA, not blocked** (U20).
