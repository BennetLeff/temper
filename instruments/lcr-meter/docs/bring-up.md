# Revision D bring-up and stage53 qualification

**For the Rev E board (codec, relays, BNCs) use [bring-up-rev-e.md](bring-up-rev-e.md).** This page is the Rev D procedure.

Applies to TIDA-based revision D with an external regulated **5 V, 1 A, center-positive supply** and USB data. Confirm fitted compensation: one local C104 = 100 pF directly between U7A output and summing input, shared by all three ranges. C105 and C41 are removed. The feedback capacitor must not pass through a range jumper. Verify R90–R93 = 22 Ω, C106–C109 = 100 pF, and R64/R65/R70/R71 = 4.32 Ω in the revised FDA feedback/output networks. Verify R94 = 22 Ω 0.1 % between J3 LO and the U7A summing node (the LOW follower U7B +IN stays on the J3 side), R95/R96 = 1 Ω at the LDO inputs, R83 = 1.74 MΩ and the rail monitors R97–R100. Use Rev D (`D-riso22`) firmware/host software and fresh calibration for this feedback network. Earlier revisions have different behavior. No physical board has been tested during design.

Use a DMM, current-limited supply, oscilloscope and independently known impedance standards. The DUT interface shares USB ground. Test isolated, externally discharged components or disconnected subassemblies; verify residual voltage separately before connection.

## Assembly and power

1. Compare soldering and orientation with the final assembly drawing and placement audit, including exposed pads, USB and DC jack. Hand-fit the parts specified by the final BOM. Verify jack center goes to `5VIN`, sleeve to GND, and neither to USB VBUS. Mount on insulated standoffs and inspect for bridges/shorts.
2. With power removed, install **one matching RG/RF pair**: JP1+JP4 = 100 Ω; JP2+JP5 = 5 kΩ; JP3+JP6 = 100 kΩ. Start at 100 Ω. Use the specified Samtec SNT-100-BK-G shunts with the TSW-102-07-G-S headers, fully seated. Software cannot sense jumpers. Never mix ranges or shunt power/debug headers.
3. J3 is DUT high/low. J4 is SWD clock/data; J5 is SWD ground/reference. Confirm final silkscreen/netlist before connecting.
4. Leave DUT disconnected. Apply monitored 5 V through J2. An initial 0.5 A bench limit is a diagnostic starting point; current limiting can itself prevent startup. Investigate heating, unstable current or wrong rails before proceeding.
5. Measure `5V`, `3V3`, filtered `5VA`, raw bipolar rails near +14.3/−14.4 V, LDO inputs (LDOIN_P/N: the drop from the raw rails is the rail current through 1 Ω, so it also measures each rail's load) and postregulated rails near ±12 V. ADC AVDD must stay within 4.5–5.5 V. Check ripple as well as DC. Verify fixed PWM with converter power-save pins grounded.
6. Check MCU `1V1` and RUN. Hold BOOTSEL during reset, then copy `firmware/bin/temper-lcr-rev-d.uf2` to RPI-RP2 with external power supplied. SWD is the recovery path. See `firmware/README.md` for the pinned build.
7. Connect USB CDC and run `info` and `selftest` as documented in `host/README.md`. Confirm the reported hardware/software identity is `D-riso22` and require both fixed-pattern lanes to pass. This tests digital transfer, not analog accuracy. `info` also prints the RP2040 rail-monitor readings; compare them with the DMM values from step 5. They should agree within about 3 % (they read ratiometrically to 3V3). From here on an agent can repeat the rail check with `temper-lcr rails`, and every capture refuses to run with a rail outside 10.8–13.2 V.

## Analog levels and timing

- Check ADC REFOUT near 2.5 V, REFP_A/B near 4.096 V and REFby2 near 2.048 V. Probe with high impedance. FDA common mode must come from REFby2; do not load weak REFOUT with those inputs.
- Check 24 MHz DDS MCLK and ADC CONVST/READY/CS/SCLK/data timing at the IC pins. Confirm complete burst lengths and setup/hold. Instruction simulation does not prove physical propagation or metastability margin.
- Start with an approximately 100 Ω resistor on the 100 Ω range at 1.5 kHz and 50.5 kHz. Scope EXCITE, SOURCE_BUF, DUT_HI/LO, TIA_OUT, HIGH_BUF/LOW_BUF and differential FDA outputs. Check offset, amplitude, clipping, ringing and high-frequency oscillation. The physical FDA output common mode should be near REFby2 (2.048 V); the post-22 Ω takeoff and ADC common mode are approximately 2.025 V in the loaded DC model. Measure both locations. ADC input-pair common mode must remain within 1.848–2.248 V for a 4.096 V reference, and individual inputs within 0–4.096 V, including transients.
- Scope ground clips go to meter GND. Do not ground a DUT or amplifier output with a clip. Use differential probes or two channels with both clips at GND.
- Use short probe grounds, low probe capacitance and enough bandwidth to see ringing in the tens of MHz: at least 100 MHz, preferably 200 MHz. Record probe loading. A 20 MHz bandwidth limit can hide this behavior. Ordinary passive probes can materially load DUT_LO or an amplifier output; use a low-capacitance active probe where needed and include fixture/probe loading in the test setup.
- Verify settling after DDS enable/disable. The 100 nF/100 kΩ coupling network (C36, Rev D audit) has approximately 10 ms time constant. Firmware waits at least 150 ms or 20 cycles, approximately fifteen time constants; confirm the remaining transient on the first board at 100 Hz and the worst load.
- Test approximately matched resistors on **all three ranges**: 100 Ω, 5 kΩ and 100 kΩ. Check open/short fixtures as well as the representative R/C/L loads below. The Rev C compensation addresses the 5 kΩ ringing. Rev D's R94 addresses the 100 Ω range's sensitivity to fixture and cable capacitance, which Rev C limited to about 220 pF per DUT terminal. See `analog-validation-rev-c.md` and `../validation/stability-full-chain/fixture-envelope.md` for the tested envelope. Repeat the 100 Ω open/short ringing check with the longest lead set you intend to use.
- For a small-step ringing check, use a controlled, characterized local disturbance that excites the amplifier bandwidth without clipping. The DDS reconstruction filter suppresses fast edges, so a step commanded through the DDS alone is insufficient. Record the actual stimulus and probe setup; do not connect a low-impedance generator directly across the virtual-ground summing node. Sustained or growing ringing, clipping or unexplained spectral peaks require investigation before measurements are accepted.
- Check both FDA differential outputs and pair common mode after their 22 Ω / 4.32 Ω networks during conversion. Probe at the ADC pins as well as main amplifier OUT pins; unused RGT FB pads are not feedback test points. Confirm no conversion-related common-mode ringing or range violation.
- Repeat waveform checks with short/open fixtures, low resistance, 100 nF, 0.5 µF, 9 µF and representative coil/leads. Select suitable frequencies/ranges. Analog saturation can occur without ADC rail codes. Saturated open data are unsuitable calibration standards.

## Noise and calibration

Run `noise` to acquire actual ADC samples with DDS asleep. Check open and short fixtures at the measurement grid (1.5, 35.5, 40.5, 50.5 and 60.5 kHz). The host refuses whole-kHz frequencies, where USB start-of-frame lines and aliased DDS harmonics fall in the fit; `noise ... 1000 --allow-hazard` deliberately measures the 1 kHz SOF line. Every `capture` also takes a source-off record and fails a point whose source-off tone exceeds 10⁻⁴ of the signal; treat such failures as interference to find, not to override. Retain RMS, fitted-tone levels and repeatability. Moving switching above 1 MHz does not prove absence of pickup/aliasing. Keep coil and paired leads away from the converter and mechanically fixed.

Follow executable examples in `host/README.md`. On the 100 Ω range, begin with a short and independently characterized 20 Ω and 100 Ω resistors, entering measured values. Know their ratio to 0.03 % or better (measure both once against one reference); marked ±0.1 % values leave about −16 mΩ of error on coil R. With R94 fitted, LO sits at I·22 Ω, so LO-lead capacitance diverts a small fixed share of the current: fix the leads in place after calibration, or recalibrate after moving them (±20 % lead C at 200 pF moves coil R by about 8 mΩ at 60 kHz). Validate a separate approximately 47 Ω resistor, then independent capacitive/inductive standards. The CLI currently accepts real resistor standards; bound their reactive parasitics at the test frequencies.

Calibration is specific to unit, fixture, range, frequency grid and acquisition settings. Recalibrate after changes and evaluate temperature drift. Qualify higher ranges separately with suitably spaced standards and an independent third standard. All three ranges share the local 100 pF feedback capacitor and R94; preserve the corresponding complex feedback (22 Ω + RF‖100 pF) and per-frequency correction. The 100 kΩ feedback pole is approximately 15.9 kHz: at 100 kHz its feedback impedance is about 15.7 kΩ, reducing resistive sensitivity by roughly 6.4×. Start high-resistance qualification near 1.5 kHz and establish a measured useful frequency limit. This tradeoff does not materially reduce the 100 Ω range’s stage53 coil/capacitor sensitivity at 35–60 kHz. Do not reuse Rev B or Rev C calibration files with Rev D; the host refuses them.

Keep acquisition at the planned 1 MSPS setting. The [bounded switched-load stress check](../validation/adc-switched-load/README.md) supports this operating window, while its shortened-window negative control exceeds the half-LSB recovery threshold. That simplified model does not establish actual ADC accuracy or clear a higher sampling rate. Verify settling and kickback using the real conversion timing on the first board.

Record magnitude, phase, real-part error and repeatability against a reference instrument. Establish ESR/Q usefulness from measured phase error and fixture variation. Good capacitance agreement does not establish small-ESR accuracy. CLI validation thresholds are proposed acceptance criteria, not achieved specifications.

## Stage53 tests

Selected PCB SHA-256: `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`; its scoped manifest is beside `worktrees/runs-native21/s53/c53int/section.kicad_pcb`.

| Test | Initial setup | Limitation |
|---|---|---|
| Coil with/without pan | 100 Ω range, 35–60 kHz | Record pan position/material/gap, leads and temperature; small-signal only |
| Individual 100 nF resonant capacitors | 100 Ω, 35–60 kHz | Isolate parallel paths; C/complex Z/relative loss |
| Five-capacitor 0.5 µF bank | 100 Ω, 35–60 kHz | No high-current/ripple-rating inference |
| 9 µF bus capacitor | 100 Ω, 1.5 kHz (−j11.8 Ω) | Validate capacitance; high-frequency ESR needs separate qualification |
| Chokes/snubber/gate capacitors | Suitable range/frequency | Disconnect or lift a lead where parallel paths matter |
| 1 mΩ shunt | Outside qualified scope | Use a suitable four-wire DC instrument |

The meter does not establish insulation strength, voltage withstand, large-signal coil loss/saturation or stage53 mains readiness. Save first-board results with the meter PCB hash and standards/fixture identities.
