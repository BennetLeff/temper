# Revision E bring-up and first-board qualification

Applies to the Rev E board (`E-codec`, protocol 3): TAC5112 codec, latching range relays K1–K3, K4 internal 1 kΩ reference, four BNC jacks, 140 × 105 mm. Rev D's procedure ([bring-up.md](bring-up.md)) does not apply: Rev E has no jumpers, no ADS9224R/THS4551/AD9833 and no DDS. No Rev E board has been tested. Each step says what to record. A step that fails stops the sequence until it is understood.

**Equipment.**
- A bench supply with a current limit, feeding a **USB-C power-only breakout** (5.1 kΩ on CC is on the board, so any breakout that passes VBUS and GND works). It powers the board through J1 for section 2, before any computer is attached.
- An inline **USB-C current meter** (VBUS voltage and current) for section 3 onward.
- 6½-digit DMM (also used to characterize the cal kit, [CHARACTERIZE.md](../calkit/CHARACTERIZE.md)).
- Oscilloscope, ≥ 100 MHz, short ground springs; a logic analyser (≥ 100 MS/s) for the TDM bus.
- The cal kit card, Kelvin clip leads (jaws < 14 mm) and four BNC–clip leads.
- `firmware-rev-e/bin/temper-lcr-rev-e.uf2` and `host/bin/temper-lcr-macos-arm64` (`temper-lcr` below).

**Safety.** The DUT shares USB ground. Measure only discharged, isolated parts. Check residual voltage on any capacitor before clipping on.

**Record keeping.** Commit every capture, `info`/`codec` printout, scope screenshot and note to `validation/bring-up-rev-e/` with the step number. Then a later agent can redo the analysis without the board.

## 1. Inspection, before power

1. Compare the board with `previews/assembly-top.png` and the JLC placement preview. Pay most attention to keyed parts: U1 (RP2040), U13 (TPS65131), U14 (TAC5112), U5–U7, U11/U12, U15, K1–K4 (pin-1 bar), D-parts and Q2–Q6. On Rev F, check that D4's lens faces the front edge and that D18 (−12) is turned the other way from D15–D17 (its anode is on GND).
2. Check that the BNCs (J3 HCUR, J7 HPOT, J8 LPOT, J9 LCUR) face the top edge and match their silk. Power enters only through J1 (USB-C); there is no DC jack. Check U16 (TPS2553, pin-1 mark) and R110 (24 kΩ).
3. DMM, power off:
   - no short from USB_VBUS, 5V, 3V3, 3V3A, RAW_P/RAW_N or ±12V to GND;
   - USB_VBUS to 5V is open (U16 off), not a short;
   - each BNC shell to GND is 0 Ω;
   - J3 to J7 centre about 1 kΩ (R105), and J8 to J9 centre about 1 kΩ (R106).

## 1a. Indicator LEDs (Rev F board)

Rev F adds an orange front-panel light and six red debug LEDs, visible with the lid off ([rev-f-plan.md](rev-f-plan.md), "Indicator LEDs"). A rail LED only shows that the rail is present (it glows from about 2 V up); it says nothing about tolerance. Use the DMM and `RAILS` for values.

| LED | Silk / place | Meaning | Expected at power-up (bench supply into J1, firmware loaded) |
|---|---|---|---|
| D15 | 5V, at the rail monitors | 5 V rail after U16 | on within about 1 ms (U16 soft start) |
| D16 | 3V3 | 3V3 (U3) | on with 5V |
| D17 | +12 | +12 V (U11) | on a few ms later, after the TPS65131 starts; dark = boost, U11 or ENP |
| D18 | −12 | −12 V (U12) | on with +12; dark alone = inverter, U12 or ENN |
| D19 | HB, west of U1 | firmware heartbeat (GPIO23) | dark during boot (codec bring-up, self-test, relay reset), then blinks at 1 Hz while idle; dark during each capture |
| D20 | FLT, west of U1 | fault (GPIO22) | off after a passing boot self-test; on if the self-test or the boot relay reset failed, or after any `ERR` reply; a successful command clears it unless the self-test is still failing; dark during captures |
| D4 | front panel, left of HCUR | STATUS (GPIO25) | off at idle; on for the duration of each capture |

With a blank flash (no firmware) HB, FLT and STATUS stay dark: the RP2040 pads reset as inputs with pull-downs. HB blinks with the bench supply alone, because the firmware's main loop runs once it sees VBUS, computer or not. The rail LEDs draw about 2 mA in all (about 0.4–0.6 mA each; 5 V input share of all LEDs about 12 mA, `regulator_check.py`), so record the idle current in §2.1 with them lit.

Rev F also has fourteen bare 1.5 mm test pads (board-only, not on the BOM), labelled on silk: nine on the supplies and five on the relay coil lines. Each GND pad is 2.6 mm from a rail pad, so a scope ground spring reaches both: probe 5V, +12, −12 against the power-area GND (TP2) and 3V3 against the digital GND (TP9). Positions are KiCad board coordinates (mm; the board spans x 50–150, y 45–145, the BNC edge at y 45). Expected values are the §2 rail checks at 5.0 V in.

| TP | Silk | Net | Position (x, y) | Where | Expect |
|---|---|---|---|---|---|
| TP1 | 5V | 5V | 100.5, 116.5 | power area, above the rail-LED row | about 0.08 V below VBUS (4.92 V at 5.0 V in) |
| TP2 | GND | GND | 103.1, 116.5 | beside TP1 | 0 V (scope ground, power area) |
| TP3 | +12 | 12V | 106.0, 121.2 | on the 12V run to R115 | +11.65…+12.29 V |
| TP4 | -12 | −12V | 109.8, 117.6 | above the −12 rail-LED column (R116, D18) | −11.67…−12.32 V |
| TP5 | VRLY | VRLY | 123.6, 109.6 | east of D8 | about 5 V |
| TP6 | RAW+ | RAW_P | 128.775, 115.0 | on the RAW_P run to R95 | +14.3 V nominal (+13.8…+14.9 V) |
| TP7 | RAW- | RAW_N | 142.5, 115.0 | on the RAW_N run to R96 | −14.1 V nominal (−13.3…−14.8 V) |
| TP8 | 3V3 | 3V3 | 92.0, 131.6 | digital area, east of J5 | 3.3 V |
| TP9 | GND | GND | 92.0, 134.2 | beside TP8 | 0 V (scope ground, digital area) |
| TP10 | K1 | RLY_SET_LO | 107.2, 111.6 | east of Q4 (K1 SET driver drain) | VRLY at rest; about 0 V for each 20 ms K1 SET pulse |
| TP11 | K2 | RLY_SET_MED | 88.9, 108.5 | north-west of Q3 (K2 SET driver drain) | as TP10, for K2 |
| TP12 | K3 | RLY_SET_HI | 122.0, 111.6 | east of Q5 (K3 SET driver drain) | as TP10, for K3 |
| TP13 | K4 | RLY_SET_REF | 147.9, 75.6 | north-east of Q6 (K4 SET driver drain) | as TP10, for K4 |
| TP14 | RST | RLY_RST | 97.295, 115.0 | south of Q2 (shared RESET driver drain) | VRLY at rest; about 0 V for each 20 ms RESET pulse (all four coils) |

The five coil pads sit on the MOSFET drains, at least 10 mm from every analog-net item (`rev_f.py` asserts it; 10.7 mm for K2, 13.6–19.0 mm for the others), so probing them does not touch the measurement path. At turn-off the drain swings above VRLY until the 1N4148 across the coil clamps it, about VRLY + 1 V; a larger or longer overshoot means the clamp diode is missing or reversed. Use TP2 for the scope ground. `RELAY_PULSE_MS` is 20 ms (`firmware-rev-e/src/relay.h`); the TQ2SA needs 4 ms at most.

CODEC_VREF and 5VA have no test pad: both sit in the analog core, where a pad would need new copper next to the codec. Measure them at their decoupling capacitors.

## 2. Power and rails, no computer

1. Leave the jacks open. Apply 5.0 V through the USB-C breakout into J1 with a 0.5 A limit. Record the current, and watch for heating. U16 soft-starts the 5 V rail and limits it at 1.0–1.16 A (R110, TPS2553 datasheet eq. 1); the bench limit is the tighter one here.
2. Lower the supply to 4.40 V (the USB minimum at the device) and confirm 12 V/−12 V and 3V3A stay in range. Record the 5V node: it should sit about 0.08 V below VBUS (U16 and the entry copper, `validation/power-spurs/regulator_check.py`).
3. At 5.0 V, measure and record each rail:

| Net | Expect | Note |
|---|---|---|
| 5V, 3V3, 1V1 | 5.0, 3.3, 1.1 V | digital |
| 5VA → 3V3A | 5.0 → 3.3 V | FB1 then U15; codec AVDD |
| CODEC_VREF | 2.75 V | codec reference (default) |
| CODEC_DREG | datasheet value | codec digital regulator output |
| RAW_P / RAW_N | +14.3 / −14.1 V nominal (+13.8…+14.9 / −13.3…−14.8 V) | `validation/power-spurs/regulator_check.json` |
| LDOIN_P / LDOIN_N | RAW minus rail current × 1 Ω | the drop is the rail current: about 35/40 mA estimated, less on Rev E |
| 12V / −12V | 11.65–12.29 / −11.67…−12.32 V | |
| VRLY | about 5 V | relay coil supply (R101, C112) |

4. Measure fsw on SW_P (1.25–1.50 MHz) and record it. Scope RAW_P/N, ±12 V and 3V3A for ripple and spikes (Rev D R4). Hot-plug the USB-C cable once and scope USB_VBUS and 5V: TPS65131 VIN abs-max is 6 V. U16 ramps 5V in about 1 ms; record the ramp and any overshoot.
5. Move to the computer through the inline USB-C meter. Record VBUS and current at idle, during a capture, and during a range change (relay pulses add about 0.11 A for milliseconds). The estimate is 0.45 A; a USB-C port or a USB 3 port (900 mA) is needed, and a USB 2.0 type-A port (500 mA) is marginal. If the computer's VBUS at the board is below 4.40 V under load, use a powered hub or a USB-C charger port.

## 2a. Start-up sequence (Rev F, datasheet audit 2026-10-30)

The TPS65131 enables come from U17 (LM3880). FLAG1 releases ENP and FLAG2 releases ENN 10 ms later, after U17's EN delay of about 18 ms. C117 (330 µF polymer) carries each converter's start-up surge above U16's 0.99 A limit. The model is `validation/power-spurs/startup_surge.py`; the reasons are in `validation/datasheet-audit-rev-f/README.md`.

1. Before power, check C117's polarity: + (pad 1, chamfered corner and silk +) is on the south land, toward the board edge.
2. Use four scope channels: 5V at TP (5V), CONV_ENP at R119.1, CONV_ENN at R120.1, and RAW_P at TP (RAW+). Trigger on 5V rising, then plug USB at 4.40 V and again at 5.0 V. Expect:
   - 5V ramps to VBUS in about 2–3 ms;
   - ENP rises about 20–60 ms after attach;
   - ENN rises 8.5–11.5 ms after ENP;
   - RAW_P is in regulation before ENN rises;
   - 5V stays ≥ 3.86 V through both starts (model worst case; 3.7 V is the 3V3 headroom line).

   Any repeated ramp on 5V or RAW_P is a UVLO hiccup: stop and record it.
3. Hot-plug at the VB pad (TP20, USB_VBUS at U16 IN, with the GND pad beside it), using 1 m and 2 m cables, and at least once with a **USB-A to C cable** from an always-on port: that is the hard-step case. The peak must stay under 7 V (TPS2553 IN abs max), and under 6 V wherever it reaches U13 VIN. `validation/power-spurs/hotplug_spice.py` predicts at most 6.24 V with R121; a higher reading means the cable is outside its assumed 0.3–1.5 µH / 0.05–0.30 Ω, so record the cable and rerun the script with it.

## 3. Firmware and digital

1. Hold BOOTSEL, connect USB and copy `temper-lcr-rev-e.uf2` to RPI-RP2. A blank board needs no BOOTSEL press: with no valid boot2 in flash the ROM drops to USB mass storage after 0.5 s. J4–J6 are not fitted; solder a 2-pin header at J4/J5 if SWD recovery is ever needed. The flash is a GD25Q16E (2 MB), not the Pico's Winbond part: the firmware booting from flash after the copy confirms that `boot2_w25q080` sets its QE bit and runs quad reads. If it does not boot, rebuild with `PICO_BOOT_STAGE2_CHOOSE_GENERIC_03H=1` (slower, command-set independent) and report it.
2. Run `temper-lcr info PORT`. It must show `INFO 3 E-codec … 120000000 187500 4096 100000 …` and `PASS`: boot runs the codec bring-up and the self-test, and selects the 100 kΩ range. Compare its rail readings with the DMM (within about 3 %).
3. Run `temper-lcr codec PORT` and record it:
   - DEV_STS0: both ADC channels and DAC channel 1 powered;
   - DEV_STS1 mode: 7;
   - CLK_DET_STS0: bin 10 (187.5 kHz).
4. Logic analyser on BCLK, FSYNC, DIN and DOUT (GPIO 4/5/2/3, codec pins 2/3/5/4; on Rev F at test pads TP15–TP18, with the GND pad TP19):
   - 12 MHz BCLK, 64 BCLK per frame, one-BCLK FSYNC;
   - DOUT settled well inside 41.7 ns from the rising edge;
   - rise and fall times under 10 ns.

   Record one capture.
5. Run `temper-lcr selftest PORT`. This is a digital loopback (firmware README, *Self-test*). If it fails with a constant bit offset on a board that passes step 4, the codec echo is retimed: the fix is an expected offset in firmware, not hardware.
6. If you want the 375 kHz build: steps 2–5 with that UF2. `CODEC` must show bin 5 and every channel powered.

## 4. Relays

1. With the source silent, run `temper-lcr range PORT 100`, then 5000, then 100000. Scope VRLY during a RESET pulse (all four coils): at least 4.5 V. Record the waveform. On Rev F, scope TP14 (RESET) and the SET pad of the range being selected (TP10–TP13) at the same time: each drain pulls low for 20 ms, RESET first.
2. **K4 stays open.**
   - Run `refcheck PORT 5000 1500 ref.json` with the jacks open, then a normal `capture` of the open jacks on the 5 kΩ range. The capture must read far above 1 kΩ: if it reads about 1 kΩ, K4 is still closed.
   - Repeat after cutting power in the middle of a `refcheck` (boot must reset K4).

## 5. Quiet board (source off)

The Rev E host does the zero-waveform check itself on `capture` ([power-spurs Rev E](../validation/power-spurs/README-rev-e.md) R-E2, [host README](../host/README.md)); steps 1 and 3 and the `raw` method in step 2 remain by hand, because the host check sees only the tone bin.

1. Silence the source with `temper-lcr off PORT`, then run `temper-lcr raw PORT 8192 quiet.json` with the jacks open and again with the Kelvin short. Compare the RMS per channel with [rev-e-codec](../validation/rev-e-codec/README.md).
2. `temper-lcr capture` now does this at every point: after each source-on capture it uploads `PERIOD` zero words, captures again with the same SKIP and PERIODS, and requires the line at the tone bin below 10⁻⁴ of the source-on line on A and B (it doubles the capture time). It exits non-zero and saves the file if any point fails, and `analyze`, `calibrate` and `validate` refuse that point unless `--allow-source-off-fail`. Read the per-point `source_off_check` ratios and `noise_sigma_codes` in the capture file as a record of the quiet board. The manual method still serves for spectra, where the check only sees one bin: for each grid period, upload a waveform of that many zero words with `temper-lcr wave PORT zeros-P.txt`, then take `raw` again. The grid periods are 125 (1.5 kHz), 75 (27.5 kHz), 375 (35.5, 50.5 and 60.5 kHz) and 125 (40.5 kHz). This catches activity locked to the waveform period. Take the DFT of the record at the grid frequencies (23 Hz bins at 8192 frames). Any line standing above the noise floor at a grid frequency is interference: find it before calibrating.
3. Repeat step 2 powered from the real host's USB-C port (and, if it will be used, its charger or hub), with the coil and leads in their working position. VBUS is now the only supply: a host VBUS line inside the tone bin needs at least 25 mV (9 µF at 60.5 kHz) to 0.44 V (the other reference parts) to reach 10⁻⁴ ([power-spurs Rev E](../validation/power-spurs/README-rev-e.md), mechanism 5). Any line found here is recorded with the host model.

## 6. Source, analog levels and stability

1. With a 100 Ω resistor (cal kit R3) on the 100 Ω range, run `temper-lcr tone-hz PORT 1500 1700`. Scope:
   - SOURCE_BUF: 1.7 V peak, a DC offset of a few mV;
   - DUT_HI, HIGH and LOW follower outputs, TIA_OUT;
   - the four codec input legs: common mode near 0 V before the coupling capacitors.

   Repeat with the jacks shorted and open.
2. Stability with the real leads: on each range, with the open, the short and 100 Ω, plus 1 m BNC leads on all four jacks, look at TIA_OUT and SOURCE_BUF at full bandwidth. There must be no sustained ringing or oscillation. The simulated worst margin is 46.8° on the source driver. It rests on estimated relay-internal capacitance, so this is the check that confirms it.
3. Level linearity (gain compression): capture R3 at 27.5 and 60.5 kHz at 200, 500, 1000 and 1700 mV. The uncalibrated |Z| must agree within 0.01 %.
4. Codec passband: sweep `tone-hz` 1 kHz–85 kHz into R3 and capture each point. A/B must be smooth, with no roll-off at 60–85 kHz in either channel (firmware README step 9). This also tests whether CM_TOL = 01 works in wideband mode. If it does not, the channel residual rises or the codec status fails: use CM_TOL = 10. TI SBAA634A Table 2-3 already measures mode 01 at 1 kHz (TAC5112, 40 k: SNR 101 dB, THD+N -97 dB, CMRR 47 dB, within 1 dB of mode 00), so this step only confirms it holds at 27-85 kHz.

## 7. Internal reference

Run `temper-lcr refcheck PORT 100 1500,27500,60500 ref-100.json` with the **jacks unplugged**, and the same on 5000 and 100000. Repeat three times over 30 minutes and record the drift. This is the session reference that the accuracy figures assume.

## 8. Calibration with the cal kit

1. Characterize the kit's resistors with the DMM ([CHARACTERIZE.md](../calkit/CHARACTERIZE.md)) and write the standards file. Until a reference meter has measured L and C, use the §5 ESTIMATES for both, and keep the 100 kΩ range at 10 kHz or below.
2. Per range, capture SHORT, LOAD1, LOAD2 and the check resistor on the grid `1500,27500,35500,40500,50500,60500`, with one fixture string. Capture the short with `--short-standard`, so that its near-zero voltage channel is judged against the current channel in the source-off check. Then:

```sh
temper-lcr calibrate short.json r1.json R1 r3.json R3 cal-100.json --standards=kit.json
temper-lcr validate r2.json cal-100.json R2 0.1 --standards=kit.json
```

   Use the rows in CHARACTERIZE.md §1. Record the validate errors per frequency.
3. Check the reactive standards with `analyze`:
   - C1 and the C2–C6 bank: C within ±1 %, tan δ between −3×10⁻⁴ and +1×10⁻³ at 35–60 kHz;
   - L1: R at least the DCR measured on the DMM, L within ±20 % (CHARACTERIZE.md §6).
4. **Session procedure.** At the start of each later session, re-capture the Kelvin short and re-run `calibrate` with the new short and the stored load captures. Also run `refcheck` and compare it with step 7.

## 9. Gate B-E1: DAC images at the modulator rate

The desk analysis ([power-spurs Rev E](../validation/power-spurs/README-rev-e.md) §4) cannot rule out DAC images near the codec's unpublished modulator rate. If present, they fold onto the tone and put a systematic error on coils and capacitors that resistor calibration does not remove. The pessimistic estimate is up to 0.75 % on a coil at a 3 MHz modulator. This step settles it.

1. Calibrate both the 100 Ω and the 5 kΩ ranges (step 8).
2. Clip L1 on and capture at 60.5 kHz, 1700 mV, on both ranges. `analyze` each against its own calibration.
3. **Pass:** L and R agree within 0.3 %. The pessimistic disagreement would be 3.7 % at 16 fs, 1 % at 32 fs and 0.2 % at 64 fs.
4. L1 is ferrite, and the two ranges drive it at about 10 mA and 0.3 mA. To check that this is not ferrite amplitude dependence, also capture it on the 100 Ω range at 170 mV. If L moves by more than 0.05 % between 1700 and 170 mV, redo the screen with any air-cored coil of 30–100 µH.
5. **Fail:** fit 1 nF C0G at C34 and C35 and 0 Ω at C114 and C115 (each U5 difference-stage capacitor is now two 560 pF in series, 280 pF). This lowers the pole from 284 to 80 kHz: 3.6× less image for 2 dB of tone at 60 kHz. Then repeat steps 2–3. If it still fails, the source needs a second pole (layout change, next revision). Meanwhile limit coil accuracy claims to the measured disagreement.
6. While the tone plays, a scope FFT on SOURCE_BUF around 1–13 MHz shows where the DAC images sit. That is the modulator rate, which no document gives. Record it.

## 10. Remaining first-board checks

- **80–85 kHz.** The DAC interpolation image at fs − f falls in the ADC transition band, and neither attenuation is published. Measure C1 at 80 and 85 kHz against 60.5 kHz. C must agree within 0.1 %, or the top of the range is unusable for reactive parts. The host warns on every tone above 80.4 kHz until this is settled.
- **Long capture.** A 60 s `capture` (`--seconds=59`) with other USB traffic on the host must finish without `acquisition_overrun`.
- **Temper targets.** On the 100 Ω range at the half-kHz grid, measure the stage53 coil, the 100 nF and 0.5 µF resonant capacitors (35.5–60.5 kHz) and the 9 µF bus capacitor (1.5 kHz, characterized film capacitor), with the session procedure (step 8.4). Record the results against a reference meter where one is available.
- **Relay capacitances (optional).** Measure a loose TQ2SA's contact-to-coil and pole-to-pole capacitance, and rerun `reverelaycng100_r104` with the values (`validation/stability-full-chain`). That replaces the estimate under the 46.8° margin.

## What to update afterwards

- `validation/README.md`: add a measured-results section; the receipt there is desk evidence only.
- `docs/rev-e-plan.md`: a decision row for each gate (B-E1, CM_TOL, 80–85 kHz) with its result.
- Where a measurement replaces an ESTIMATE, update the model (relay C, modulator rate, standards' L/C) and rerun the analysis that used it: `validation/power-spurs/rev_e_spurs.py`, `validation/rev-e-accuracy-map/rerun.sh`, `validation/stability-full-chain`.
