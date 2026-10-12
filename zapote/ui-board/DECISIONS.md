# UI board decisions

Schematic-level pass (2026-10-12). Each decision names its source. Datasheets were downloaded to a scratch directory outside the repo; they are cited by document and page. Numbers come from `tools/ui_calcs.py` (`evidence/ui_calcs.json`); anything marked **[ALLOCATION]** or **[UNVERIFIED]** is an engineering allowance that has no datasheet line behind it yet.

## U1. Scope and fixed inputs
- **What this is:** the fascia UI board, one PCB parallel to the fascia with the OLED, three IP67 buttons, the encoder socket, an SPI expander, a temperature sensor and a buzzer, joined to controller J7 by a 12-way, 120 mm JST XH jumper. It is a schematic, a BOM, calcs, a verifier and a mechanical floorplan. **No layout.**
- **Fixed by the controller (read-only):** `zapote/controller/DECISIONS.md` C26 (J7 pin map, 100 ohm at the controller end of every signal, SRV05-4 at J7, V5_UI at most 30 mA, UI 3V3 allocation 120 mA + 340 mA OLED), C3 (OLED is SPI), C23 (PERMIT = latch AND RUN_EN), `ENCLOSURE-HANDOFF.md`. Open item 3 there is what this unit answers: encoder, buzzer, STOP.
- **Fixed by the enclosure (read-only):** `output/temper-manufacturing-r41/` `design/r33/DECISIONS.md` section 3, `src/r33_world.py` (UI board outline, holes, connectors, M3 since R39), `src/controls_r5.py` (OLED, lens, buttons, encoder), HANDOFFs r35 to r41. No R39 to R41 change moves the UI board; R41 only repeats the sounder decision.
- **Fixed by firmware (read-only):** `git show 780eaab89:firmware/main/platform/ui_board_map.h`, copied to `inputs/firmware/` with its hash.

## U2. J7 and the bus terminations
- **Pin map: kept byte-equal** to C26: 1 V5_UI, 2 +3V3, 3 GND, 4 SCK, 5 GND, 6 MOSI, 7 MISO, 8 GND, 9 CS_OLED#, 10 OLED D/C, 11 GND, 12 CS_EXP#. `verify_ui.py` compares the board to four independent copies (the C26 table, the ENCLOSURE-HANDOFF row, the controller's frozen netlist, the controller's `verify_controller.py J7_MAP`) and to a literal.
- **Connector:** the controller's own part, JST B12B-XH-A(LF)(SN), LCSC C158027.
- **ESD at J7:** two SRV05-4 (U4, U5), Vcc on V3V3, on all six signals, the same part as the controller's U38/U39 (LCSC C2836319). The power pins carry none: a steering-diode array cannot sit on the 5 V pin from a 3.3 V clamp rail, and 3V3 is a stiff rail with 22 uF.
- **Terminations:** the controller already has 100 ohm in series at its end of every signal. The UI board drives only MISO, so it gets the one matching source resistor (R20, 100 ohm) between the chips and J7. Inputs (SCK, MOSI, CS_OLED#, CS_EXP#, D/C) have no series part on this board.
- **No pull on D/C or the chip selects here.** D/C goes straight to OLED pin 4: controller GPIO45 is a strap pin that must read low at reset (C26, R38). The chip selects are pulled up at the controller. Checked by `j7_dc_has_no_resistor_or_pull` and its mutation.

## U3. The OLED supply: the module makes its own 12 V; the 5 V pin cannot carry it
- **Question:** the panel of the NHD-3.12-25664UCW2 needs about 12 V. Does the UI board need a boost, or an OLED variant with an internal DC-DC?
- **Answer:** neither. The module (rev. 7, 2024-08-25) already contains the boost, and its factory jumpers (R14 closed) power logic, boost and panel from VDD (pin 2) at 2.8 to 3.5 V (Newhaven spec p.6). The supply current is 310 mA typ and **340 mA max** at 3.3 V with all pixels on (p.7). That is the number the controller already budgets on J7.2 (`verify_controller.py v3v3`, `oled_off_board_mA` 340).
- **Why not V5_UI:** jumper option 1 feeds the boost from pin 3 at up to 12 V. At 5 V the boost input draws **150 mA typ, 170 mA max** (p.7), 5.7 times the 30 mA the controller's 5 V path allows (2 x 100 ohm droppers, TLV76050). At 12 V it would be 70 mA max, but J7 carries no 12 V.
- **Why not an external 12 V on VCC (option 2):** 55 mA max at 12 V, but a 12 V boost from 3.3 V on this board would still pull about 235 mA from V3V3 at an allocated 85 % efficiency, to save about 100 mA, for an inductor, an IC and a switching node next to the encoder. Not worth it.
- **Wiring:** pins 3 (BC_VDD), 15 (VCC) and 18 (G_VDD) stay open. `oled.nhd_4wire_spi_pin_map` checks that they have no connection. The OLED socket carries 22 uF and 100 nF at its VDD pin for the boost start-up.
- **Check:** firmware's FW-UI-1 limits (at most 30 % pixels lit, dim after 30 s) will cut the real draw well below 340 mA. The datasheet gives no partial-load figure, so none is claimed.

## U4. V5_UI: reserved, unused
- **Budget:** 0.51 mA of 30 mA (a 100 nF capacitor C11 and a 10 kohm bleed R23 so the pin is never floating). `power.v5_budget_le_30mA` recomputes it from the netlist; moving the buzzer onto V5_UI (47 mA at 5.1 V) fails it.
- **Why nothing uses it:** the only candidates (OLED boost, buzzer) exceed it (U3, U9), and keeping the buzzer off V5_UI keeps its current steps off the controller's LDO and its two 100 ohm droppers, which are sized for 30 mA plus 5 mA of LDO ground current (C26; the LDO input reaches its 1.2 V dropout limit at about 42 mA in total). 30 mA is the controller's limit, not a hard wall.
- **Consequence for the controller:** none needed. The 5 V LDO, its droppers and the 15 V draw on the controller are budgeted for 30 mA the UI will not draw.

## U5. The 3V3 budget and the rail band
- **Loads at datasheet maxima, V3V3 = 3.465 V:** OLED 340 mA, encoder 30 mA (Grayhill p.3), buzzer 31.5 mA (30 mA at the 3.3 V rating scaled), MCP23S08 8 mA (1 mA at 1 MHz scaled to 8 MHz, **[ALLOCATION]**), pull-ups 2.1 mA, the rest under 1 mA. **Total 411.9 mA; 71.9 mA without the OLED.** The controller allocates 460 mA (340 + 120) and 120 mA excluding the OLED, so the UI board is inside both.
- **Voltage at the load:** the controller's rail band is 3.242 to 3.367 V. The jumper's drop at 0.41 A (AWG28, 120 mm, four XH contacts, three paralleled GND pins) is 40 mV **[ALLOCATION: wire and contact resistances from tables, not re-read]**, so the UI sees 3.202 to 3.367 V.
  - OLED 2.8 to 3.5 V: margin 0.40 V low, 0.13 V high.
  - MCP23S08 1.8 to 5.5 V, TMP122 2.7 to 5.5 V, TLV3202 2.7 to 5.5 V, buzzer 2 to 5 V: inside.
  - **Encoder 3.30 +/- 0.125 V (Grayhill p.3): 26 mV of margin on the low side, 58 mV on the high side.** This is the tightest voltage on the board. It is why the encoder's supply bead FB1 is a 50 mohm part (BLM18PG121SN1D), not a generic 450 mohm bead, and why the encoder has its own 10 uF. If the controller's 3V3 tolerance is ever widened, re-run `ui_calcs.py`.

## U6. Expander map: kept, with GP7 resolved
- **Map (MCP23S08, opcode 0x40, A1 = A0 = GND): unchanged from `ui_board_map.h`.** GP0 START, GP1 STOP, GP2 RESET, GP3 ENC_A, GP4 ENC_B, GP5 ENC_SW, GP6 buzzer (high = on), GP7 LOCAL. `verify_ui.py` traces every role from its GP pin to the physical part, so a change to the board or to the header fails.
- **GP7 (the "OLED RES# or TMP122 CS" the firmware left open) = TMP122 CS#.** The OLED reset is the on-board RC (U12). Reason: the FW-UI-1 derate needs the temperature sensor (enclosure R33), and a power-on RC reset is what the SSD1322 power sequence asks for. GP7 stays an input with pull-ups at reset (R17 10 kohm holds CS# high), exactly what the header does today. When firmware wants the temperature it sets IODIR.7 = 0 and drives OLAT.7 low for the read. **No bit moves.**
- **Naming mismatch to note, not a change:** the enclosure labels the three buttons back (u -75), select/start (u -35), stop (u 5). The firmware calls GP2 RESET (fault reset). The board wires the back button to GP2, select/start to GP0, stop to GP1. Firmware can map RESET to the back button, or the enclosure can relabel.
- **Net names:** `GP0_BTN_START` ... `GP7_TMP_CS_N` in the netlist.

## U7. Encoder: Grayhill 62VG15-H9S-030C, with a comparator
- **Part (enclosure `controls_r5.py`):** 3.3 V sealed optical encoder, 24 detents, 950 gf push, 3 in lead with an AMP 7-215083-6 plug. It mates a TE 7-215079-6 socket on the board (J2, LCSC C306122).
- **J2 pin map from the Grayhill drawing (62AG/VG Rev. 02/2024 p.3, VG style):** 1 GND, 2 and 3 the normally open push contact, 4 B, 5 A, 6 +3.3 V. This **replaces the assumed map in controller C15** (1 +3.3 V, 2 GND, 3 A, 4 B, 5 switch, 6 +5 V), which was written before the part was chosen. The controller no longer has J5, so nothing there changes; the mating of pin n to pin n on the lead is still to be confirmed with a sample (housing orientation).
- **Supply: 3.3 V, not 5 V.** The VG style is 3.3 V only (+/- 0.125 V, 30 mA max); the AG style is 5 V. Fed from V3V3 through FB1.
- **Outputs are open-collector phototransistors that need a 10 kohm pull-up each and less than 1 nF** (p.3). R9, R10 (and R8 for the switch) are 10 kohm to the encoder rail; C13, C14 are 470 pF at the connector.
- **The levels do not fit the expander.** The encoder guarantees low at most 1.0 V and high at least 2.0 V. The MCP23S08's input low is 0.2 x VDD = 0.63 V at 3.135 V (DS20001919F p.22 D031). The guaranteed low exceeds the expander's threshold by **0.37 V**: the datasheets do not guarantee that a worst-case encoder reads as low. So A and B go through a comparator (U3, TLV3202, rail-to-rail inputs, 1 mV typ and 6 mV max offset, SBOS561C p.6) with the threshold at 1.5 V from R15/R16 off the encoder rail and about 70 mV of hysteresis (R11 to R14). Worst corners (supply 3.175 to 3.425 V, 1 % resistors, 6 mV offset): trips 1.38 to 1.61 V, **0.38 V of margin on the low side and 0.39 V on the high side**. A typical phototransistor probably meets 0.63 V; the datasheet does not say. If the bench shows the margin is never needed, U3 and R11 to R16 can be dropped with a jumper from each raw node to its GP pin.
- **Rotation rate:** 100 rpm maximum x 24 detents x 4 states = 6.25 ms per state, so a 1 ms poll oversamples 6 times. The datasheet prints "optical rise/fall time 30 ms max" (p.3); if that unit is real and not a typo for microseconds, the usable rotation rate is far lower. **Bench item.**

## U8. Buttons: three APEM IPR3PAD2
- **Part (enclosure R33/R39):** IP67, normally open, round flat actuator, straight PC pins at 5.08 mm pitch, silver gold-plated contacts, 200 mA 50 VDC, contact bounce 10 ms (APEM IP series p.2, p.5). No LCSC listing: hand-fitted panel part, listed as the one `lcsc_exception` in the BOM, bought with the enclosure controls BOM.
- **Circuit per line:** switch to GND, a 10 kohm pull-up on the switch side (0.35 mA wetting current for the gold contacts), a 1 kohm series resistor to the expander pin, an SRV05-4 channel at the switch. The 10 kohm external pull-ups make the firmware's GPPU bits optional (they are harmless).
- **Debounce:** the datasheet bounce is 10 ms and firmware asks for 10 identical polls at 1 kHz, which just meets it. See U14.

## U9. Buzzer: self-oscillating electromagnetic, on V3V3, switched by GP6 (owner decision R35 section 4)
- **Part:** Inghai GSD9605YB-3V2800 (LCSC C255327, extended, stock 11 495). SMD, 9.6 x 9.6 x 5.0 mm, built-in driver, 2.7 kHz, 2 to 5 V operating, **3.3 V rated, 30 mA max**, 80 dB min at 10 cm, **-20 to +70 C** (spec sheet V1.1 p.1 to 2). Electromagnetic, so it has a coil: the flyback diode D1 is fitted across it.
- **Drive:** low-side N-MOSFET Q1 (AO3400A, LCSC C20917, basic: Vth at most 1.45 V, 48 mohm at 2.5 V). Gate drive from GP6 through R21 100 ohm, at least 2.4 V at worst against 1.45 V Vth. Vds on at 31.5 mA is 1.5 mV.
- **Default off at reset:** the MCP23S08 resets with every pin an input (IODIR = 0xFF), so GP6 is high impedance; R22 (100 kohm) holds the gate low, and the leakage of 1 uA across it is 0.1 V against a 0.65 V minimum Vth. `buzzer.default_off_at_reset` models this and fails if the pull-down becomes a pull-up (mutation `invert_buzzer_default`).
- **Allocation:** 31.5 mA of the controller's 90 mA buzzer allocation.
- **Temperature:** the buzzer is rated to 70 C; the board can be near the OLED's 85 C limit (R32 T3). Alternates with the same 9.6 x 9.6 footprint are in the BOM: C530415 GSD9605YB-5V2800 (-30 to +85 C, 5 V rated, operating 2 to 12 V, sound pressure at 3.3 V not specified) and C42420997 (-20 to +80 C). **Bench item:** sound pressure at 3.3 V and at temperature.
- **Sound port:** a closed fascia will muffle it; the enclosure has no port modelled (finding E4).

## U10. TMP122 (the FW-UI-1 derate sensor)
- **Part:** TI TMP122AIDBVR, SOT-23-6 (LCSC C2877606, extended). **Stock is 17 at JLC** (2026-10-12): buy before the board run.
- **Wiring:** SCK on the bus, CS# on GP7, SO/I on the MISO side before R20. The part reads temperature in the first 16 clocks of any frame and powers up active and continuous, so a read-only wiring needs no MOSI. Its output goes high impedance 30 ns after CS rises (SBOS272B p.9), so it can share MISO with the expander. Timing: 100 ns clock period minimum, output valid 30 ns after the falling edge, input sampled on the rising edge, which is mode 0 compatible. **Confirm idle-low on the bench.**
- **Accuracy:** 1.5 C max from -25 to +85 C. Place it on the front face under the OLED (U17 zones): SOT-23-6 is 1.45 mm and the gap is 3 mm.

## U11. ESD: every external-facing element
- **Four SRV05-4 arrays (U4 to U7), 12 of 16 channels used**, Vcc on V3V3: U4, U5 on J7 (six signals); U6 on the three buttons and the encoder switch; U7 on encoder A and B.
- **Series limiting:** buttons and encoder switch 1 kohm to the expander (residual about 8 mA at a 12 V clamp **[UNVERIFIED: the clamp value is taken from the LCSC listing of C2836319, not the datasheet]**, against the MCP23S08's 20 mA input clamp, DS20001919F p.21). Encoder A/B 10 kohm into the comparator (residual 0.8 mA against 10 mA, SBOS561C p.4).
- **What is external:** the button pins and the encoder socket. A finger reaches painted zamac bezels (APEM) and a Zamak shaft (Grayhill); the plungers are polyamide. The clamps are for whatever gets through to the pins.

## U12. OLED interface and reset
- **Pin map (NHD rev. 7 p.4, 4-wire SPI):** 1 GND, 2 V3V3, 4 D/C, 5 and 6 (R/W, E) GND, 7 SCLK, 8 SDIN, 10 to 14 (D3 to D7) GND, 16 /RES, 17 /CS, 19 and 20 (BS1, BS0) GND, 3, 9, 15, 18 open. Pin 1 of the module header is assumed at the left in the drawing (to confirm).
- **Reset:** 10 kohm to V3V3, 1 uF to ground, and a diode (D2) that discharges the capacitor when V3V3 falls. RES# is released 13 to 18 ms after power-up at 0.8 VDD (R and C tolerances, X5R derating). SSD1322 wants a low pulse of at least 2 us (Rev 0.10 p.48) and, in its power sequence, at least 1 ms after VCI before RES# goes low for at least 100 us (p.29); the RC gives the low period. **Firmware rule: do not write the OLED within 30 ms of UI power-up.**
- **Socket height: open.** See U17 finding E2.

## U13. SPI over the 120 mm jumper
- **Forward path (SCK, MOSI, CS):** 100 ohm at the controller with about 47 pF **[ALLOCATION]** gives a 10 ns 10-90 % edge. At 8 MHz the half period is 62.5 ns; the MCP23S08 needs 45 ns high and low (DS20001919F p.27 to 28); the margin is 12 ns after edge skew. SSD1322 (100 ns cycle, 20 ns high/low, Rev 0.10 p.51) and TMP122 (100 ns) are inside at 8 MHz.
- **Return path (MISO):** MCP23S08 output valid 45 ns after the clock falls (p.28) plus about 4 ns of RC leaves 14 ns of the 62.5 ns half period at 8 MHz, before the ESP32's own input delay. If that delay is the 25 ns of the GPIO matrix **[UNVERIFIED: ESP-IDF SPI master timing notes, not re-read]**, the margin at 8 MHz is **negative (-11 ns)**; at 5 MHz it is +27 ns. **Recommendation to firmware (not a map change): clock the expander and TMP122 at no more than 5 MHz as a separate device configuration and keep the OLED at 8 MHz.** An expander read is 4.8 us at 5 MHz, 0.5 % of a 1 ms poll.
- **Bus utilisation:** one full OLED frame (256 x 64 x 4 bit) is 8.2 ms at 8 MHz, in 512-byte chunks of 0.5 ms (C26).

## U14. Firmware-visible notes (none changes the GP map)
1. **Debounce:** APEM's contact bounce is 10 ms; 10 identical 1 kHz polls only just covers it. Use **at least 15**.
2. **UI liveness:** read the expander's IODIR register back each cycle (expected 0xBF with the buzzer output enabled, 0xFF after a power loss) and treat a mismatch, a stuck-0xFF/0x00 MISO, or a failed read as "UI lost": drop RUN_EN within 100 ms, not 1 s. This is what makes the software STOP acceptable (U15).
3. **OLED init:** wait 30 ms after UI power-up; RES# is the board's RC, not firmware's.
4. **TMP122:** set IODIR.7 = 0 and OLAT.7 = 1 once; to read, drive OLAT.7 low, clock 16 bits with CS_EXP# and CS_OLED# high, raise OLAT.7. Keep the OLED and expander deselected during the read.
5. **SPI clocks:** U13.
6. **Button names:** U6.

## U15. STOP: does it need to be a hardware trip?
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
- **23 lines, 56 placements: 22 with LCSC numbers (14 JLC basic, 8 extended) and one without (IPR3PAD2, hand-fitted).** Stock and library type read from the public JLCPCB parts search on 2026-10-12, read-only, nothing ordered. `bom/ui-parts.json`, `bom/ui-parts.csv` (JLCPCB BOM layout).
- **Extended (8):** J7, J2, J3 (connectors), U1 MCP23S08, U2 TMP122 (stock 17), U3 TLV3202, U4 to U7 SRV05-4, BZ1.
- **JLC listing of the MCP23S08 says 4.5 to 5.5 V; the datasheet says 1.8 to 5.5 V** (DS20001919F p.22, D001), 10 MHz at 2.7 V and above for -40 to +85 C (p.27); only the E-temperature range above 85 C is limited to 4.5 V. The board stays at or below 85 C because of the OLED.
- **Off-board items** (enclosure BOM): the OLED module, the encoder with its lead, the jumper.

## U17. Mechanical floorplan against the enclosure (R41)
- **Numbers from the enclosure source** (`r33_world.py`, R39 M3 holes; `controls_r5.py`), checked by `tools/floorplan.py` against the source when present and against `catalog.json`'s bounding box: board **u -106 to 64 (170 mm), v 15 to 96 (81 mm), 1.6 mm**, front face at w -14. Four Ø7 stud clearances at (-99, 38), (-99, 82), (29, 38), (29, 82); four Ø3.4 M3 holes on the OLED-carrier bosses at (-104, 60), (34, 60), (-75, 92), (5, 92); a 22 x 12 cut-out at u -94 to -72, v 42 to 54. Buttons at (-75, 26), (-35, 26), (5, 26) (bezel Ø17.5, cut-out Ø13.6). OLED 89.2 x 44 at (-35, 64), M2 holes on 83.2 x 38, lens 108.8 x 38.8. J7 (rear face) at (46, 49.5) and the encoder socket J2 at (55, 58). Grayhill encoder at (110, 53), off the board, 50 mm developed lead against 76 mm of cable.
- **The 24 mechanical checks pass** (holes inside the outline, buttons clear of holes by at least 3 mm, connectors inside, J7 and J2 clear of holes, stacker inside the OLED shadow, M2 clear of M3).
- **Face assignment for layout:** front face (w -14 to the OLED at -11): buttons, the OLED socket, TMP122 (1.45 mm tall under the OLED), the buzzer (9.6 x 9.6 x 5.0 mm, so outside the OLED footprint, at the left end). Rear face: J7, J2 and everything else. Advisory zones are drawn in `evidence/floorplan.svg`.
- **Findings for the enclosure (recorded, not ours to change):**
  - **E1:** the M3 hole at (-104, 60) leaves **0.3 mm** of FR-4 to the board edge (the Ø6 carrier boss overhangs the edge). Move it 3 mm inboard or notch the outline.
  - **E2 (open item U-OPEN-1):** the OLED stacker is modelled 3.0 mm high. The 1 x 20 2.54 mm female sockets on LCSC are 8.5 mm. The BOM carries C46595982 as a placeholder. Either the gap opens by 5.5 mm (taller carrier bosses) or the enclosure approves a soldered low-profile header (the OLED then cannot be unplugged).
  - **E3:** J7 and J2 envelopes are 1.4 mm apart; the mated XHP-12 and Micro-MaTch housings are larger.
  - **E4:** no sound port for the buzzer.

## U18. Layout notes for the next stage
- Clamps U4, U5 at J7; U6, U7 at their connectors; R20 at the chips. Each IC has its own 100 nF as `c_<name>` for `u_<name>` (the verifier pairs them by that name).
- Keep the SCK, MOSI and MISO runs short and with their GND neighbours; keep D/C and the CS lines away from the buzzer drain.
- The comparator and its 10 kohm inputs sit next to J2, not next to J7.
- The buzzer and Q1 sit at the far left, away from the sensor and the encoder rail.

## Open items
1. **E2 / U-OPEN-1:** OLED socket height versus the 3.0 mm gap (enclosure).
2. **E1:** hole (-104, 60) edge wall (enclosure).
3. **E4:** buzzer sound port (enclosure); sound pressure at 3.3 V and temperature (bench).
4. **Owner or lab:** STOP as hardware or software (U15).
5. **Firmware:** 5 MHz expander clock, 15-poll debounce, UI-lost rule, 30 ms OLED wait (U13, U14).
6. **Bench:** encoder low level against the comparator margin and the print of "30 ms" rise time (U7); the encoder rail's 26 mV low-side margin (U5); SRV05-4 clamp value (U11); harness resistances (U5).
7. **Procurement:** TMP122 stock 17.
