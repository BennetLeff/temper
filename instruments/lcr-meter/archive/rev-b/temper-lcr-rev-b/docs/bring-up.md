# Revision B bring-up and stage53 qualification

Applies to the TIDA-based revision B with an external regulated **5 V, 1 A, center-positive supply** and USB data. Revision A instructions are incompatible. No physical board has been tested during design.

Use a DMM, current-limited supply, oscilloscope and independently known impedance standards. The DUT interface shares USB ground. Test isolated, externally discharged components or disconnected subassemblies; verify residual voltage separately before connection.

## Assembly and power

1. Compare soldering and orientation with the final assembly drawing and placement audit, including exposed pads, USB and DC jack. Hand-fit the parts specified by the final BOM. Verify jack center goes to `5VIN`, sleeve to GND, and neither to USB VBUS. Mount on insulated standoffs and inspect for bridges/shorts.
2. With power removed, install **one matching RG/RF pair**: JP1+JP4 = 100 Ω; JP2+JP5 = 5 kΩ; JP3+JP6 = 100 kΩ. Start at 100 Ω. Software cannot sense jumpers. Never mix ranges or shunt power/debug headers.
3. J3 is DUT high/low. J4 is SWD clock/data; J5 is SWD ground/reference. Confirm final silkscreen/netlist before connecting.
4. Leave DUT disconnected. Apply monitored 5 V through J2. An initial 0.5 A bench limit is a diagnostic starting point; current limiting can itself prevent startup. Investigate heating, unstable current or wrong rails before proceeding.
5. Measure `5V`, `3V3`, filtered `5VA`, raw bipolar rails near +14.3/−14.4 V and postregulated rails near ±12 V. ADC AVDD must stay within 4.5–5.5 V. Check ripple as well as DC. Verify fixed PWM with converter power-save pins grounded.
6. Check MCU `1V1` and RUN. Hold BOOTSEL during reset, then copy `firmware/bin/temper-lcr-rev-b.uf2` to RPI-RP2 with external power supplied. SWD is the recovery path. See `firmware/README.md` for the pinned build.
7. Connect USB CDC and run `info` and `selftest` as documented in `host/README.md`. Require both fixed-pattern lanes to pass. This tests digital transfer, not analog accuracy.

## Analog levels and timing

- Check ADC REFOUT near 2.5 V, REFP_A/B near 4.096 V and REFby2 near 2.048 V. Probe with high impedance. FDA common mode must come from REFby2; do not load weak REFOUT with those inputs.
- Check 24 MHz DDS MCLK and ADC CONVST/READY/CS/SCLK/data timing at the IC pins. Confirm complete burst lengths and setup/hold. Instruction simulation does not prove physical propagation or metastability margin.
- Start with an approximately 100 Ω resistor on the 100 Ω range at 1 kHz and 50 kHz. Scope EXCITE, SOURCE_BUF, DUT_HI/LO, TIA_OUT, HIGH_BUF/LOW_BUF and differential FDA outputs. Check offset, amplitude, clipping, ringing and high-frequency oscillation. ADC input common mode should be near 2.048 V; individual inputs must remain within their specified interval.
- Scope ground clips go to meter GND. Do not ground a DUT or amplifier output with a clip. Use differential probes or two channels with both clips at GND.
- Verify settling after DDS enable/disable. The 1 µF/100 kΩ coupling network has approximately 100 ms time constant. Firmware now waits at least 1000 ms, approximately ten time constants; confirm the remaining transient on the first board.
- Explicitly test the 5 kΩ range with an approximately 5 kΩ resistor and a small excitation step. The bounded analog model predicts only about 30° TIA phase margin in this case; investigate peaking or sustained ringing before using that range. See `analog-validation-rev-b.md` for the model limitations.
- Repeat waveform checks with short/open fixtures, low resistance, 100 nF, 0.5 µF, 9 µF and representative coil/leads. Select suitable frequencies/ranges. Analog saturation can occur without ADC rail codes. Saturated open data are unsuitable calibration standards.

## Noise and calibration

Run `noise` to acquire actual ADC samples with DDS asleep. Check open and short fixtures around 1 kHz and across 35–60 kHz. Retain RMS, fitted-tone levels and repeatability. Moving switching above 1 MHz does not prove absence of pickup/aliasing. Keep coil and paired leads away from the converter and mechanically fixed.

Follow executable examples in `host/README.md`. On the 100 Ω range, begin with a short and independently characterized 20 Ω and 100 Ω resistors, entering measured values. Validate a separate approximately 47 Ω resistor, then independent capacitive/inductive standards. The CLI currently accepts real resistor standards; bound their reactive parasitics at the test frequencies.

Calibration is specific to unit, fixture, range, frequency grid and acquisition settings. Recalibrate after changes and evaluate temperature drift. Qualify higher ranges separately with suitably spaced standards and an independent third standard. The 100 kΩ branch includes 5 pF compensation; preserve complex feedback and per-frequency correction.

Record magnitude, phase, real-part error and repeatability against a reference instrument. Establish ESR/Q usefulness from measured phase error and fixture variation. Good capacitance agreement does not establish small-ESR accuracy. CLI validation thresholds are proposed acceptance criteria, not achieved specifications.

## Stage53 tests

Selected PCB SHA-256: `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`; its scoped manifest is beside `worktrees/runs-native21/s53/c53int/section.kicad_pcb`.

| Test | Initial setup | Limitation |
|---|---|---|
| Coil with/without pan | 100 Ω range, 35–60 kHz | Record pan position/material/gap, leads and temperature; small-signal only |
| Individual 100 nF resonant capacitors | 100 Ω, 35–60 kHz | Isolate parallel paths; C/complex Z/relative loss |
| Five-capacitor 0.5 µF bank | 100 Ω, 35–60 kHz | No high-current/ripple-rating inference |
| 9 µF bus capacitor | 100 Ω, start near 1 kHz | Validate capacitance; high-frequency ESR needs separate qualification |
| Chokes/snubber/gate capacitors | Suitable range/frequency | Disconnect or lift a lead where parallel paths matter |
| 1 mΩ shunt | Outside qualified scope | Use a suitable four-wire DC instrument |

The meter does not establish insulation strength, voltage withstand, large-signal coil loss/saturation or stage53 mains readiness. Save first-board results with the meter PCB hash and standards/fixture identities.
