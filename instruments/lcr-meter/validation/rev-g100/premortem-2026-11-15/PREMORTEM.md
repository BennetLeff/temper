# Rev G100 first-spin pre-mortem (2026-11-15)

Board `cad/temper-lcr.kicad_pcb` on `study/lcr-rev-g100` (1ea381450). Read-only on the design; everything here was in `build/premortem-2026-11-15/` and is committed as `validation/rev-g100/premortem-2026-11-15/`. Dispositions: [DISPOSITIONS.md](DISPOSITIONS.md).

**Verdict: order now, copper unchanged.** I found no hardware fault that needs copper. I found one firmware fault that would make every board look dead at first power-up (item 1), and several places where the fallback is not yet written down. All of them are fixed in firmware, by a value on an existing footprint, or by a bring-up step. Category (b) is empty: see "Copper changes".

**Evidence in this folder:**
- `netlist.txt`: parts and nets from `cad/design.json`.
- `dump_board.py` → `board.json`: footprints, pads and test pads from the board (KiCad Python).
- `access.py` → `access.txt`: probe access per net, unconnected IC pins, test-pad neighbours.
- `pin_levels.py` → `pin_levels.txt`: USB_SENSE level and the jack-sense error terms.

"Verified" below means I read it in the named file or computed it with one of these scripts. "Believed" is engineering judgement with no file behind it.

## 1. Ranked bodge causes

| # | Cause | Likelihood | Impact | Fix |
|---|---|---|---|---|
| 1 | USB_SENSE sits at 1.1–1.6 V, not 2.5 V, so the firmware never starts USB | **high** | every board looks dead after the first flash | (a) firmware |
| 2 | Jack-guard sense offsets reach the 0.5 V LCUR trip; no way to force the switches | medium–high | meter refuses to measure; pressure to bypass U18–U21 | (a) firmware; no-wire bypass exists |
| 3 | Codec asleep while ±12 V are up (blank flash, BOOTSEL, hung firmware): 3V3A pumped past 3.6 V | medium (3.6 V), low (3.9 V) | codec stress on the very first power-up | (a) bring-up step; stacked bleeder as fallback |
| 4 | Switcher: SW-node ringing against abs max, and pickup into the TIA | low–medium | reliability, or tone collisions | (a) BOM trim first; beyond that copper |
| 5 | DAC images fold onto the tone (gate B-E1) | unknown (no data exists) | coil / capacitor error up to 0.75 % | (a) BOM step is planned; the step after it is copper |
| 6 | RP2040 core supply / RUN (MD-1, MD-2, MD-6) | low | random resets or no boot | (a) firmware and one value; beyond that copper |
| 7 | Relay RESET margin 44 mV at 4.40 V, 45 °C | low | silent wrong range (caught by `relaycheck`) | (a) BOM, planned |
| 8 | Debug: USB CDC is the only console, no spare GPIO has a pad | certain to be felt | slower debug of items 1–2 | (a) fit J4, buy a probe |
| 9 | K4 latched closed until the first good boot: R107 sits across the jacks | low | the 0.1 % reference takes a charged DUT | (a) bring-up rule, firmware |
| 10 | No Rev G 375 kHz image; RP2040-E5 fix shares GPIO15; stale test-pad table | certain, small | lost time | (a) |

### 1. USB_SENSE: the pad pull-down halves the level (new; firmware)

**Verified.**
- `firmware-rev-e/src/main.c:660-661` does `gpio_init(PIN_USB_VBUS); gpio_set_dir(..., GPIO_IN)` and nothing else to GPIO13.
- The SDK's `gpio_init` and `gpio_set_function` do not touch pulls (`pico-sdk-2.2.0/src/rp2_common/hardware_gpio/gpio.c:38-48, 273-277`: "This doesn't affect e.g. pullup/pulldown").
- The pad resets with its pull-down on: `sources/new/RP2040-datasheet.txt:22732` (PDE reset 0x1) and Table 615 (GPIO13 reset state "Pull-Down"). RPD is 50–80 kΩ (line 46397).
- R5 / R6 are 100 k / 100 k (`cad/design.json`). `pin_levels.txt`: the pin is 1.25–1.54 V at VBUS 5.0 V and 1.10–1.35 V at 4.40 V. VIH is 2.0 V and VIL 0.8 V (lines 46336, 46345), so the level is in the undefined band.
- `main.c:698` is `while (!gpio_get(PIN_USB_VBUS)) tight_loop_contents();`, before `stdio_init_all()`. `main.c:714` drops USB whenever the pin reads low, and `main.c:600` refuses every capture.
- The checks missed it: `validation/firmware-pins/firmware_pins_check.py:218-223` and audit N4 (`validation/datasheet-audit-rev-g100/mcu-digital.md:47`) both compute 4.40 V × 0.5 = 2.2 V with no pull-down.

**Believed.** The pin rises from 0 V, so it must cross the Schmitt trigger's upper threshold; a 3.3 V CMOS Schmitt input rarely switches high at 1.3–1.5 V. I expect most boards to hang at line 698: rail LEDs on, HB dark, no USB device. A board that does read high at 5.0 V would drop USB on a sagging port.

**Fix, (a) firmware:** `gpio_disable_pulls(PIN_USB_VBUS);` after `gpio_init`. Also add RPD to `firmware_pins_check.py` so the check models the pad. Worth doing as well: call `stdio_init_all()` before the wait, so a wrong VBUS reading can never again hide the console. No BOM change is needed. Recovery on an affected board is SW1 + SW2 (BOOTSEL), which works.

### 2. Jack-guard sense accuracy against a 0.5 V trip (known in part as MD-3; firmware)

**Verified** (`pin_levels.txt`, `firmware-rev-e/src/jackguard.h`, `main.c:149-161`):
- 1 LSB is 10.9 mV at the jack. 1 % resistors alone give ±222 mV at a 0 V jack. Leakage at the datasheet maximum gives ±1.5 V (audit MD-3).
- Not in MD-3: an ADC offset of 20 mV at the pin is 270 mV at the jack, and 256 conversions per 5 ms poll from a 111 kΩ source add up to 117 mV (upper bound, 1 pF sample capacitor).
- `JG_TRIP_LC_MV` is 500. Inside a capture the test uses **one** conversion per jack (`jacks_over`), so ADC noise adds directly.
- The firmware has no command that forces the switches (`JACKS` only reads, `main.c:516-521`), yet bring-up G2–G4 need them on (`docs/bring-up-rev-g.md`, "Command the switches on").

**Believed.** RP2040 ADC offsets of 10–30 mV are common; the datasheet gives no figure. Tolerance plus offset can reach 0.5 V, so some boards will report `jacks_tripped` with nothing connected.

**Fix, (a) firmware, before boards arrive:**
- a stored per-board zero for each sense (audit DB-6 already measures it);
- average 8–16 conversions in `jacks_over`;
- a bring-up-only `JACKS FORCE 0|1`, so a guard-logic fault can be told from a switch or LED fault.

**No-wire hardware fallback (verified geometry):** each TLP172AM's output pads 4 and 6 are 2.54 mm apart on one side (`board.json`: U18 pads at (67.0, 60.33) and (67.0, 62.87)). Removing the part and fitting a 0 Ω 0805 across those two pads bypasses a switch with no wire. Buy ten 0 Ω 0805.

### 3. Codec asleep with ±12 V up (residual of G-C1; bring-up, optional stacked part)

**Verified.** U17 enables ±12 V by itself 20–60 ms after attach (`rails.h` header, nets CONV_ENP / CONV_ENN). The firmware fix for G-C1 (`main.c:687-691`) wakes the codec before the rails, but with a blank flash, in BOOTSEL, with RUN held, or with firmware hung before line 691, the codec stays in POR sleep at 9 µA. Audit G-C1 (`validation/datasheet-audit-rev-g100/codec.md:15`) computes 3.69 V on first power-up (above the 3.6 V operating limit, below the 3.9 V absolute maximum), and 3.97–4.59 V in two rarer cases. Every new board's first power-up is a blank-flash power-up.

**Fix, (a):** scope C60 on the first blank power-up of the first board, before the others are powered. If it passes 3.9 V, **believed** fallback with no wire: stack a 1 kΩ 0603 on C61 (3V3A to GND, 3.3 mA), which out-sinks the roughly 2 mA a railed leg can inject through 970 Ω. The Schottky to 3V3 stays the respin fix.

### 4. Switcher ringing and pickup (known: SL-2…4, plan §3)

**Verified.** `validation/datasheet-audit-rev-g100/switcher-ldos.md:20-22`: INP static peak 15.29 V against 17 V; estimated ringing 1.5–3 V at the 2.2 A limit. No snubber or local RAW_P capacitor footprint exists (`netlist.txt`: SW_P has only U13, D2, L1). Pickup is +4 dB relative to Rev F, absolute unknown (`docs/rev-g100-plan.md` §3).

**Fallbacks.**
- Ringing, (a) BOM: lower the setpoints on the existing dividers. R81 430 k → 412 k gives RAW_P 13.65 V (1.213 × (1 + 412 / 40.2)), 0.55 V more margin, with the LDO still above dropout. The same trim on R83 for RAW_N. **Believed** sufficient for a marginal reading; not for a gross one.
- Conducted pickup, (a) BOM: R95 / R96 1 Ω → 4.7 Ω on the same lands.
- Magnetic pickup or gross ringing: **needs copper.** The existing fallback is the Rev G 100 × 110 board, not a wire.

### 5. DAC images (known: gate B-E1)

**Verified.** `docs/bring-up-rev-e.md` §9 step 5: fit 1 nF at C34 / C35 and 0 Ω at C114 / C115 (same lands). "If it still fails, the source needs a second pole (layout change)". No footprint for a second pole exists.

**Fallback before copper, (a):** the 375 kHz build moves the interpolation images up by a factor of two, but no Rev G 375 kHz image is built (item 10).

### 6. RP2040 supply and RUN (known: MD-1, MD-2, MD-6)

No pad can take a capacitor at pins 44 / 45 / 50 or 26, so a hardware fix is copper. Fallbacks not yet recorded, both **believed**:
- DVDD droop: `vreg_set_voltage(VREG_VOLTAGE_1_20)` at the top of `main()` (firmware).
- RUN glitches: R9 10 k → 1 k on the same land (R8 is already 1 k, so the part is on the BOM).

### 7. Relay RESET margin (known: RCG-01, G6a)

BOM only, as planned: R101 → 0 Ω, then 4.5 V coils. A longer pulse does not help. Buy 0 Ω 0603 and two spare relays.

### 8. Debug and recovery access

**Verified** (`access.txt`):
- Every net has a pad of 0.6 mm or more except the two LED mid-string nets ISO_S1M / ISO_S2M. Nothing that matters needs a fine-pitch joint: I2C at R72 / R73, ISO_DRIVE at R134, CONV_ENP / ENN at R119 / R120, 1V1 at C8, CODEC_VREF at C62, TDM at TP15–TP18, coil drains at TP10–TP14, TIA_OUT at C104 / R67, switch nodes at D2 / D3.
- No test pad is within 3 mm of a tall part; C117, the relays and the inductors are all further away.
- GPIO 0, 1, 12, 16–21 and 24 and the codec's GPIO1 / GPIO2 / GPO1 have no copper at all. On a QFN that means no spare signal can ever be added.
- Recovery: SW1 / SW2 work with the lid off. SWD is J4 (DNP, through-hole) plus TP22 (GND, 3.1 mm away) and TP8 (3V3).

**Fix, (a):** solder the 2-pin header at J4 on the first board before first power, and have a CMSIS-DAP probe on the bench: with item 1, SWD is the only way to see where the firmware stops. HB (R117) and FLT (R118) are the two free debug outputs; STATUS at R12 is already a capture gate for a scope trigger.

### 9. K4 and the reference resistor

**Verified.** K4 and R107 are on the jack side of the switches (`netlist.txt`: JK_HCUR–K4–REF_A–R107–JK_LCUR). Relays ship in either state. The boot RESET runs only when the rails come up (`main.c:695-696`), and never with a blank flash.

**Fix, (a):** bring-up rule "nothing on the jacks until `INFO` says PASS". Firmware: pulse RESET at boot even on a rail fault; VRLY does not depend on ±12 V.

### 10. Small, certain items

- **No Rev G 375 kHz image.** `firmware-rev-e/build.sh` builds three images; `temper-lcr-rev-e-375k.uf2` never closes the jack switches. It is the fallback for the 80–85 kHz and DAC-image unknowns. Add a fourth build.
- **RP2040-E5 fix uses GPIO15, which is ISO_DRIVE.** `pico-sdk-2.2.0/src/rp2_common/pico_fix/rp2040_usb_device_enumeration/rp2040_usb_device_enumeration.c:85` (`dp = 15`); it tri-states the pin for about 1 ms after a bus reset. It runs only on B0 / B1 silicon (line 27) and is linked in (`rp2040_chip_version` is in the ELF). Current parts are B2, so no effect is expected. Set `PICO_RP2040_USB_DEVICE_ENUMERATION_FIX=0` to remove the sharing.
- **Stale test-pad table.** `docs/bring-up-rev-e.md:49-64` gives Rev F coordinates. On G100, TP1–TP14 are 10 mm further south (TP1 is at (100.5, 126.5)), TP7 is at (145.6, 116.8), and TP20–TP22 are not listed. Regenerate the table from the board.
- **No watchdog.** A hang with ISO_DRIVE high leaves the jacks connected and unguarded. Low priority.

## 2. Uncontrolled states

Verified from `netlist.txt`, `main.c` and RP2040 Table 615 (every GPIO resets to input with pull-down).

| Output | Blank flash / BOOTSEL / RUN low / boot before `main()` | USB pulled mid-operation | Hazard |
|---|---|---|---|
| Relay drivers Q2–Q6 (GPIO 6, 7, 10, 11, 14) | off: pad pull-down plus 100 kΩ at each gate | a pulse in progress is cut; state unknown until the next boot RESET | none electrical; see item 9 for K4 |
| Jack switches Q7 (GPIO15) | off: pad pull-down plus R135 | LEDs lose VRLY; firmware also drives low | none; jacks cannot connect by themselves |
| Codec | no reset pin; POR sleep, outputs off | — | item 3 |
| ±12 V (U17 → U13) | **on, not firmware-controlled** | collapses with 5 V | item 3 |
| LDO / load-switch enables | tied to their inputs | — | none |
| I2C | 4.7 kΩ pull-ups win over the pad pull-downs (3.08 V) | — | none |
| USB_SENSE (GPIO13) | 100 k / 100 k loses to the pad pull-down | — | **item 1** |
| ADC pins 26–29 | pull-downs load the dividers until `adc_gpio_init` | — | none |

Straps: TAC5112 ADDR and GPI1 to GND, TPS65131 PSP / PSN to GND, U17 EN on C116 (internal pull-up), TPS2553 / AP2112 / TPS7A EN to IN. None floats (audit G-C12, SL-12, SL-16 agree). Pin functions: I2C0 on GPIO 8 / 9, ADC0–3 on 26–29, PIO on 2–5: all legal.

## 3. Bench unknowns and their fallback

| Unknown | Fallback if it goes wrong | Needs copper? |
|---|---|---|
| Which relay coil is SET | firmware: swap roles | no |
| Codec at 187.5 kHz, three channels | firmware: clock fallbacks exist; else a lower rate (loses tones above about 40 kHz) | no |
| GD25Q16E with `boot2_w25q080` | firmware: generic 03h boot2; else swap U2 (SOIC-8) for W25Q16JV | no |
| Crystal start-up (25 mm loop) | firmware: `PICO_XOSC_STARTUP_DELAY_MULTIPLIER`; BOM: R10, C12, C13 | no |
| Codec CM_TOL mode | firmware register | no |
| DAC images at the modulator rate | BOM: C34 / C35 / C114 / C115; firmware: 375 kHz image | **yes, if both fail** |
| 80–85 kHz image | firmware: cap the tone range, or 375 kHz image | no |
| Switcher pickup | BOM: R95 / R96; source-off check flags collisions | **yes, if magnetic** (Rev G 100 × 110) |
| Switch-node ringing (SL-2, SL-3) | BOM: R81 / R83 setpoint trim | **yes, if gross** |
| Relay RESET margin | BOM: R101 0 Ω, then 4.5 V coils | no |
| Hot-plug peak | BOM: R121 / C113 | no |
| Start-up surge, UVLO hiccup | BOM: C117, R110, U17 delay variant | no |
| I2S edges (BCLK 69 mm, no series resistor) | firmware: drive strength and slew | no (believed) |
| Self-test loopback bit offset | firmware | no |
| Stability with real leads, relay capacitance | BOM: R104, C104, R94, C78 | no |
| Jack-sense leakage and offset (MD-3, item 2) | firmware zero; 0 Ω bypass | no |
| USB_SENSE threshold (item 1) | firmware | no |
| Switch LED current (G2) | BOM: R132 / R133 | no |
| TLP172AM off capacitance, TVS capacitance, ESD knee | lower the stated protection envelope | no |
| 3V3A pump (item 3) | stacked 1 kΩ on C61 | no |
| RP2040 decoupling, RUN (MD-1, MD-2, MD-6) | firmware VREG voltage; R9 1 k | **yes, if those fail** |
| R121 pulse survival | BOM: larger pulse-rated 0603 | no |

Five rows can end in copper. None is likely, and none can be made safe by a small copper change now: each would be a re-layout of the switcher block, the source stage or U1's south side.

## 4. Recommendations

### (a) No copper change

**Firmware, before boards arrive (none of this delays the order):**
1. `gpio_disable_pulls(PIN_USB_VBUS)`; start USB before waiting on VBUS; add RPD to `firmware_pins_check.py`.
2. Jack guard: stored zero, averaged in-capture test, `JACKS FORCE`.
3. Build `temper-lcr-rev-g-375k.uf2`.
4. `PICO_RP2040_USB_DEVICE_ENUMERATION_FIX=0`.
5. Boot RESET pulse even on a rail fault.

**Bring-up steps to add:**
1. Fit J4 on board 1 before first power.
2. Scope C60 on the first blank power-up.
3. Nothing on the jacks until `INFO` says PASS.
4. Regenerate the test-pad table for G100.

**Order:** keep the tooling-hole remark and "Confirm production file: Yes" (package review §1); that remains the most likely way to get a cut trace.

**Spares to buy (LCSC, a few dollars):** 0 Ω 0603 and 0805, 1 kΩ 0603, 1 nF C0G 0603, 412 kΩ and 4.7 Ω 0603, two TQ2SA-L2-5V, one W25Q16JV SOIC-8 208 mil, a 1 × 2 header, a CMSIS-DAP probe.

### (b) Copper changes that are Pareto

**None.** Every candidate costs a re-verification and a fresh review while relay stock falls (209 left), and none removes a likely bodge: the likely problems (items 1 and 2) are firmware.

### (c) Worthwhile, but a trade (respin list)

| Change | Gain | Trade |
|---|---|---|
| Schottky 3V3A → 3V3 (audit DG-5) | closes item 3 in the states firmware cannot reach | analog-supply copper: re-extraction, review |
| Pads on GPIO16 / 17 (UART) and GPIO24 (trigger) (audit DB-2, DB-3) | a console that survives a USB fault | stubs on U1's crowded north edge; review days |
| DNP RC snubber lands at SW_P / SW_N and 100 nF at D2 | turns item 4's copper case into a populate | moves Rev F's proven switcher copper |
| R5 / R6 to 10 k / 10 k | immune to the pad pull-down | BOM only, but loses 4.40 V margin (2.0 V at the pin with RPD 50 k); the firmware fix is better |

## 5. Already covered (not repeated)

- Tooling holes, relay stock, image naming, placement preview: package review 2026-11-15.
- PROT-01, G-AFE-01, RCG-05, SL-1 (D29), G-PE-1, MD-10 (TP22), RCG-01 (R101): done.
- MD-1 / MD-2 / MD-6, SL-2…4, G-PE-8, m0–m10: accepted with a recorded basis.
- Coil identity, boot2, CM_TOL, B-E1, 80–85 kHz, hot-plug, start-up, G6a: each has a bring-up step.
- Pinouts and CPL rotations: pinout ledger and orientation audit. I re-read the Rev G additions (U18–U21 strings, K4's two poles, D28, the sense dividers) against `netlist.txt` and found them consistent.

## 6. Not checked

- I did not open `previews/schematic.pdf`; `cad/design.json` and the board were the source.
- No simulation was run. The switcher, stability and protection numbers are the audit's.
- RP2040 Schmitt thresholds and ADC offset are not in the datasheet; items 1 and 2 rest on the spec limits plus judgement.
- The host (`host/src/`) was not read beyond its README references.
