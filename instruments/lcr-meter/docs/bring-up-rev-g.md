# Rev G bring-up, and what Rev F bring-up feeds into Rev G

**Status, 2026-11-10: the owner chose G100 (Rev G on 100 × 100 mm) for the first order ([rev-g100-handoff.md](rev-g100-handoff.md)); no board exists yet.** The steps here apply to G100 unchanged. Without a Rev F board first, Part A becomes "what each Rev F step would have told us", and G100 runs both parts itself. Status as of 2026-11-09: no Rev F or Rev G board exists. Rev F has not been ordered (`rev-f-handoff.md`). So open item 2 of [rev-g-plan.md](rev-g-plan.md) §6, "Rev F bring-up findings on the band nodes", cannot be closed yet. This page prepares it in two parts:
- **Part A** says, step by step, which Rev F bring-up result changes Rev G, and where.
- **Part B** lists the steps only a Rev G board has.

[bring-up-rev-e.md](bring-up-rev-e.md) stays the procedure for both boards, with the Rev F notes in [rev-f-handoff.md](rev-f-handoff.md) "When boards arrive".

**How a Rev F fix reaches Rev G.**
1. `cad/tools/rev_g.py` executes `cad/tools/rev_f.py` and its routes, then applies the Rev G edits. A value or copper fix made in `rev_f.py` / `rev_f_routes.py` therefore reaches Rev G on the next `cad/rebuild.sh`. Make the fix on `study/lcr-in-box` first, then merge it here.
2. After the rebuild, run `sh validation/rev-g/copper_shift_delta.sh`. If the fix moved analog copper inside the reused Rev F zoom windows, its `reused_rev_f_zoom_windows` count is no longer 0. In that case rerun those zooms (`run_reve.sh revg` without the reuse), then the stability matrix `revgxcng100`.
3. Rerun the gates in `rev-g-plan.md` §2. A copper change also gets the independent review again (frozen export, files not conclusions).

## Part A: Rev F bring-up results and their Rev G consequence

| Rev F step ([bring-up-rev-e.md](bring-up-rev-e.md)) | Same circuit on Rev G? | If Rev F finds a problem |
|---|---|---|
| §1 Inspection | yes, plus 31 new parts | — (Part B, G1) |
| §1a Indicator LEDs | yes | fix in `rev_f.py`; reaches Rev G on rebuild |
| §2 / §2a Power, start-up, hot-plug (U16, U17, C117, R121) | yes, the same parts and copper moved 10 mm | the same value fix applies. Rev G draws 0.476 A typical against Rev F's 0.46 A at attach, so rerun `startup_surge.py` with the Rev G load if the fix touches the current limit |
| §3 Firmware, codec clock, I2S edges | yes; one firmware tree (`LCR_REV_G=1`) | firmware fixes reach both builds; rebuild both UF2s |
| §4 Relays, coil identity (SET on pins 1–5 or 6–10) | yes, K1–K4. K4's second pole is used on Rev G (it shorts HCUR to HPOT during the reference check) | a firmware-only fix covers both. Check that `jackguard.c` drives K4 with the same polarity |
| §5 Quiet board | yes | the same fix |
| §6 Source, analog levels, stability | the core is the same; the jack side is not | a value change in the drive, TIA or follower loops (RISO, C104, RF / RG) goes into `rev_f.py`. Rerun `revfcng100` and `revgxcng100`: Rev G has more margin in TIA (69.7° vs 57.3°) but the same in drive (47.4° vs 47.8°) |
| §7 Internal reference (K4 + R107) | no: on Rev G the reference sits on the jack side, behind the LCUR switch and its 10 Ω | the Rev F number does not carry over. Measure it again on Rev G (Part B, G6) |
| §8 Calibration with the cal kit | the procedure, yes; the constants, no | Rev G calibrates on its own. Open compensation includes the jack TVS and switch capacitance |
| §9 Gate B-E1, DAC images | yes | applies directly |
| §10 80–85 kHz | yes | applies directly |
| §10 Unpowered ESD knee (`bench-esd-knee.json`) | no: on Rev G, unpowered, the photoMOS is open and the TVS takes the current | **the Rev F result is one of the three protection-study inputs.** The model expects 0.52–0.71 V. Outside that range, rerun `protection_screen.py` with the measured cell. The stronger-cell variant `jackside_esd_alt` raises the unpowered limit from 50 to 100 V |
| §10 3V3A under overload (AFE-07) | no: Rev G clamps in front | Rev F only |
| §10 Relay capacitances | yes | the measured values feed both stability decks; rerun both |

**What Rev F can measure for Rev G even with no Rev G board.** Rev F is an LCR meter. Once it is calibrated (§8), measure loose parts on the 100k range at 100 kHz, with Kelvin clips on the bare part and open compensation done at the clips. These are the three pass limits the protection study sets (`rev-g-protection/README.md`, "Open items"):

| Part | Measure | Pass | If it fails |
|---|---|---|---|
| TLP172AM (C2152276), output pins 3–4, LED off | C at 0 V bias | ≤ 40 pF (2 × the datasheet's 20 pF typical) | at 40 pF the unpowered 30 V target is met exactly (`jackside_coff2x`), so above it the target is no longer shown: rerun `protection_screen.py` with the measured value |
| H4V5HD3B (C20615803) | C at 0 V | ≤ 200 pF | `jackside_tvs_c2x` (both TVSs × 2) still meets 50 V and moves one accuracy cell; above the limit, rerun `protection_screen.py` and `normal_operation.py` with the measured values |
| H3V3LD5B (C20615817) | C at 0 V | ≤ 25 pF | as the row above |

Order a few loose parts with the Rev F parts if Rev F goes first. LCSC sells all three.

## G100 first power (pre-mortem 2026-11-15)

These come from the G100 pre-mortem ([`premortem-2026-11-15/PREMORTEM.md`](../validation/rev-g100/premortem-2026-11-15/PREMORTEM.md)). Do them on board 1 before the others are powered.

**Before first power:**
- **Have a CMSIS-DAP probe** (a Raspberry Pi Debug Probe) on the bench. JLC fits J4, the 2-pin SWD header (since 2026-11-15). If the firmware stops anywhere before USB, SWD is the only way to see where. TP22 (GND) is 3.1 mm from J4; TP8 is 3V3.
- **Nothing on the jacks until `INFO` says PASS.** The relays ship in either state, and K4 with the 1 kΩ reference sits on the jack side of the switches. The boot RESET opens it, but a blank flash never runs it.

**First power-up, blank flash:**
- **Scope 3V3A at C60** (audit G-C1). With a blank flash the codec sleeps while U17 brings up ±12 V by itself, and the audit computes 3.69 V there (TAC5112: 3.6 V operating, 3.9 V absolute). Below 3.9 V: carry on. Above it: power no other board until a 1 kΩ 0603 is stacked on C61 (3V3A to GND, 3.3 mA; it out-sinks the roughly 2 mA a railed TIA can inject). The Schottky to 3V3 is the respin fix.
- USB_SENSE at R6 reads about 1.1–1.5 V with a blank flash (the RP2040 pad pull-down against the 100 k / 100 k divider). That is expected. The firmware turns the pull-down off, and the pin then reads half of VBUS.

**Flash and check:**
- Hold BOOTSEL (SW1), tap RUN (SW2), and copy `firmware-rev-e/bin/temper-lcr-rev-g.uf2` to the RPI-RP2 drive.
- In a serial terminal, type `BUILD`. Expect `BUILD temper-lcr-rev-g 187500 1`. `INFO` says `E-codec` in every image, so `BUILD` is the only way to tell them apart.
- Then type `INFO`. Expect it to end in `PASS`, then go on to bring-up-rev-e.md §1–§3 and Part B below.
- **If no serial port appears** but HB (D19) blinks, the firmware is running and USB is the fault. If HB is dark too, the firmware is stopped: attach SWD.

**Fallback images.** `temper-lcr-rev-g-375k.uf2` is the jack-guard build at 375 kHz, the fallback for the DAC-image and 80–85 kHz unknowns (bring-up-rev-e.md §9). The `temper-lcr-rev-e*.uf2` images never close G100's jack switches.

**Test pads on G100.** bring-up-rev-e.md §1's table gives Rev F positions. On G100, TP1–TP6 and TP8–TP14 are 10 mm further south (TP6 is 6.5 mm south, TP9 is 2.6 mm east), and TP7 moved. KiCad board coordinates, read from `cad/temper-lcr.kicad_pcb`:

| TP | Silk | Net | x, y (mm) | TP | Silk | Net | x, y (mm) |
|---|---|---|---|---|---|---|---|
| TP1 | 5V | 5V | 100.5, 126.5 | TP12 | K3 | RLY_SET_HI | 122.0, 121.6 |
| TP2 | GND | GND | 103.1, 126.5 | TP13 | K4 | RLY_SET_REF | 147.9, 85.6 |
| TP3 | +12 | 12V | 106.0, 131.2 | TP14 | RST | RLY_RST | 97.295, 125.0 |
| TP4 | -12 | −12V | 109.8, 127.6 | TP15 | BCLK | I2S_BCLK | 56.2, 104.4 |
| TP5 | VRLY | VRLY | 123.6, 119.6 | TP16 | FSYNC | I2S_FSYNC | 56.2, 106.4 |
| TP6 | RAW+ | RAW_P | 128.775, 121.5 | TP17 | DOUT | I2S_DOUT | 56.2, 108.4 |
| TP7 | RAW- | RAW_N | 145.6, 116.825 | TP18 | DIN | I2S_DIN | 56.2, 110.4 |
| TP8 | 3V3 | 3V3 | 92.0, 141.6 | TP19 | GND | GND | 56.2, 112.4 |
| TP9 | GND | GND | 94.6, 141.6 | TP20 | VB | USB_VBUS | 61.225, 137.0 |
| TP10 | K1 | RLY_SET_LO | 107.2, 121.6 | TP21 | GND | GND | 61.25, 112.9 |
| TP11 | K2 | RLY_SET_MED | 88.9, 118.5 | TP22 | GND | GND | 72.1, 118.0 |

**Spares to have before the boards arrive** (LCSC, a few dollars; each is a fallback in the pre-mortem's §3 table):

| Part | Use |
|---|---|
| 0 Ω 0603 (10) | R101 → 0 Ω (G6a); jumpers |
| 0 Ω 0805 (10) | bypass one TLP172AM: across its output pads 4 and 6, 2.54 mm apart |
| 1 kΩ 0603 (10) | stack on C61 (3V3A pump); R9 10 k → 1 k if RUN glitches |
| 1 nF C0G 0603 (10) | C34 / C35, DAC images (bring-up-rev-e.md §9) |
| 412 kΩ 0603 (10) | R81 430 k → 412 k: RAW_P 13.65 V, 0.55 V more ringing margin (SL-2). R83 (240 k, RAW_N) takes its own value, worked out at the bench if needed |
| 4.7 Ω 0603 (10) | R95 / R96 1 Ω → 4.7 Ω if switcher pickup is conducted |
| TQ2SA-L2-5V-Z (2) | a relay that fails G6a or is damaged |
| W25Q16JV SOIC-8 208 mil (1) | if the GD25Q16E will not boot with `boot2_w25q080` |
| CMSIS-DAP probe (Raspberry Pi Debug Probe, or a Pico with `debugprobe`); 1 × 2 2.54 mm header (2) | SWD on J4 (JLC fits it); spare headers in case |

## Part B: steps only a Rev G board has

Run these after bring-up-rev-e.md §1–§3 pass, and before §6. Flash `firmware-rev-e/bin/temper-lcr-rev-g.uf2`, the jack-guard build: the default `temper-lcr-rev-e.uf2` never closes the switches. Until G3 passes, the firmware keeps the jack switches open, so the front end sees no DUT.

| Step | What | Expect | Record |
|---|---|---|---|
| G1 | Inspection: U18–U21 pin 1 (anode) as on the silk; D28 pin 3 toward DUT_LO; D21–D24 are bidirectional TVS (no polarity; C20615803) | as on the assembly drawing | photos |
| G2 | Switch drive. Jacks open. Type `JACKS FORCE 1` (it overrides the guard for at most 2 minutes, FAULT lights, and `JACKS` ends in `1`), measure the voltage across R132 and R133 (the LED-string resistors) , then `JACKS FORCE 0` | ≥ 5.03 mA per string at 5 V; at least the 3 mA IFT while a relay pulse runs (`drive-budget.json`). If the guard alone never closes but FORCE does, the fault is in the guard's readings (G5), not the switches | V and computed I |
| G3 | Isolation. Power off: jack centre pin to DUT_HI, HPOT, LPOT and DUT_LO with a DMM | > 10 MΩ (switch open) | four readings |
| G4 | Continuity. Power on, nothing else on the jacks, `JACKS FORCE 1`: jack centre to node with a DMM, then `JACKS FORCE 0` | 10 Ω + RON (HCUR / LCUR) and 100 Ω + RON (HPOT / LPOT); RON ≤ 2 Ω | four readings |
| G5 | Residual-voltage sense. Read the senses in a serial terminal on the board's port: type `JACKS` (reply `JACKS <state> <HCUR mV> <LCUR mV> <LCUR zero mV> <forced>`; the host CLI has no jack command). Jacks open: both read about +1.65 V (the divider's float). Once `closed`, LCUR's zero is the sense error the guard subtracts: record it. At ±300 mV it is clamped, and the board's divider or ADC is suspect. Apply +5 V and −5 V from a current-limited supply (≤ 1 mA) to HCUR, then LCUR | about 11 mV per code (1.5 MΩ / 240 kΩ / 240 kΩ); the guard opens the switches above 3 V on HCUR, or 0.4 V on LCUR after the zero, and re-arms after 1 s of calm jacks, then closes after 7 calm polls (35 ms) | readings, LCUR zero, trip times |
| G6 | Internal reference (bring-up-rev-e §7) through the jack side: K4 set also shorts the HCUR and HPOT jacks | the model puts the worst 85 kHz cell at 0.014 % (5k range) and 0.024 % (100k) (`rev-g-protection/README.md`, "The HPOT reference residual") | readings |
| G7 | Accuracy against Rev F (if built) on the same cal-kit parts | the same verdict cells, since the map gives 144 / 22 / 43 for both | captures |
| G8 | Charged-part check, last and optional. With the meter powered, touch HCUR–LCUR with a 1 µF film capacitor at 10 V, then 30 V, through two-terminal leads. Scope 3V3A | the guard trips. 3V3A stays under the TAC5112's 3.9 V (the model never ends class A on 3V3A). The meter measures normally afterwards | scope shots |
| G6a | Relay state check (G100's RESET margin: 4.169 V at the coils against 4.125 V for a 45 °C relay, `drive-budget.json`). Jacks open. (1) Run `temper-lcr relaycheck PORT 1000` at 5.0 V into J1 (USB-C breakout, as §2). (2) Lower the bench supply to 4.40 V and warm K1–K4 to about 45 °C (closed enclosure or hot air, thermocouple on a relay body); run it 20 times. Scope VRLY at a coil + pin on one run | PASS on every run. A FAIL names the relay that missed its RESET. Fix in order, repeating G6a after each: (a) replace R101 with a 0 Ω 0603 jumper (+about 40 mV at the coils: 0.33 Ω × 0.12 A); (b) fit TQ2SA-L2-4.5V-Z on K1–K4 (same footprint, `rev-g100-plan.md` §5). A longer RESET pulse does not help: a miss is short of voltage, not time | pass count at each step, VRLY minimum in the pulse, relay temperature |
| G9 | IEC 61000-4-2 contact on each centre pin (lab, if a gun is available), powered and unpowered, both polarities | class A powered, class B unpowered (nothing past the op-amp ESD cell's HBM pulse); the model holds both up to its 30 kV sweep top | lab report |

Commit everything to `validation/bring-up-rev-g/` with the step number, as on Rev F.
