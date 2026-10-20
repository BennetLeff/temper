# Calibration and qualification record template

Status: **bench tests not executed**. Present evidence includes schematic ERC, native PCB DRC with explicit voltage-dependent spacing rules, schematic-to-board connectivity checks, divider geometry symmetry checks, ideal calculations and layer/3D review. The DRC rules were exercised with known-bad clearance and missing-slot fixtures. No CMRR, bandwidth, high-voltage withstand or recovery result has been measured. See [layout assumptions and assembly constraints](layout.md).

Record the assembled PCB revision, component substitutions, selected compensation values, lead lengths, shield geometry, scope/cable configuration, ambient temperature and both supply voltages with every result. Calibration belongs to that complete assembly. Repeating it after moving a shield or replacing an input lead is necessary.

## 1. Low-voltage bring-up

With the DUT disconnected, verify switch wiring, polarity, the two regulated rails and the ±2.495 V references. Confirm no oscillation at either buffer, the difference amplifier or output driver in both gain positions. Check with the intended cable and scope load, including a longer cable as a stability stress test. Measure regulator and amplifier temperatures with fresh batteries and record current from each battery.

Verify the overload LED sets with either polarity at each input and at the output threshold, remains set after removing the overload and clears with reset. Check startup, shutdown and loss of either battery. A lit LED immediately after startup can be cleared only after confirming valid rails. This design does not automatically inhibit measurements during low-battery operation.

## 2. DC ratio and zero

Warm the powered probe, short both tips to GND and record output offset in each range. There is no analog zero trimmer; use a documented scope offset/subtraction and record drift. Offset uncertainty matters for low-amplitude signals: several millivolts at a buffer become volts of input-referred error through a 2000:1 divider.

Apply a traceable, ground-referenced low-voltage DC source to each tip in turn with the other at ground. Reverse polarity. Adjust RV1/RV2 for equal divider ratios and verify the overall 1000:1 and 200:1 gains. The nominal pot resistance is 12.501 Ω; set by ratio measurement, not an ohmmeter reading alone. Record both absolute gain and common-mode leakage; gain correction in the scope cannot repair a mismatch between the legs.

## 3. AC compensation and frequency response

Use a low-voltage generator and a calibrated reference scope channel to measure gain and phase at 35, 45 and 60 kHz. Around 20 V input is useful where the generator/fixture supports it, but the probe output is only 20 mV on 1000:1 or 100 mV on 200:1. Account for output noise and offset; use appropriate averaging and repeatability checks. The reference channel, generator amplitude and fixture all contribute uncertainty.

Fit/select the low-leg C0G capacitors with the enclosure closed and leads in their fixed positions. Use swept sine response and a low-voltage step response to distinguish low-frequency compensation mismatch from distributed ladder parasitics. Verify both legs individually, then differential operation in both ranges. A single square-wave adjustment is insufficient evidence of flat 35–60 kHz response and 5 MHz rejection.

Measure small-signal response from DC through 10 MHz, locating the actual −3 dB bandwidth. The nominal RC pole alone is 4.941 MHz and adds approximately −0.406° at 35 kHz and −0.696° at 60 kHz. Account for the remaining amplifier/fixture delay. Proposed acceptance is ±2% amplitude at 35–60 kHz and ≤1° residual phase error after the stated calibration correction; report the uncertainty rather than claiming those numbers from component tolerances.

## 4. CMRR and loading

Tie the tips together at the source. Measure the common-mode voltage to earth with an appropriate ground-referenced reference and measure the residual probe output. For a probe ratio K (1000 or 200), calculate:

`CMRR_dB = 20 log10(|Vcm| / (K × |Vout_residual|))`.

Use matching amplitude conventions (RMS or peak) and report frequency, range, excitation amplitude and noise floor. If the residual is below the measurement noise, report a lower bound. Test 35–60 kHz and the switching-edge spectrum through 5 MHz; do not label a single 60 kHz result “60 dB DC–5 MHz.” Repeat after temperature stabilization and permitted lead movement.

The input-referred common-mode error is `|Vcm| / 10^(CMRR_dB/20)`. For example, at 1 kV common mode and 60 dB CMRR, the possible error is 1 V. It is 0.2% of a 500 V wanted signal but 10% of a 10 V wanted signal. Allocate this error alongside gain, offset, noise and reference uncertainty for each coil/capacitor measurement. The 60 dB goal does not override that calculation.

Measure input-to-earth capacitance and the edge current in the shield return, with the intended physical assembly. Compare 33 pF and 15 pF segment populations using separately compensated low legs. The 15 pF population requires approximately 5.997 nF ideal total bottom capacitance; changing only the top capacitors invalidates compensation. Compare measured rejection, edge current and DUT perturbation before accepting 33 pF. A tentative ≤10 pF per-tip loading target includes the entire lead and enclosure, not just the 6.6 pF ideal ladder.

## 5. Voltage extension and overload recovery

First establish higher-voltage linearity on a controlled, ground-referenced fixture whose reference probe is rated for the applied waveform. A passive single-ended HV probe is appropriate only because that reference fixture is ground-referenced. Measure actual reference-probe gain/phase uncertainty. C0G stability supports transferring a low-voltage ratio calibration, but it does not establish insulation, resistor voltage coefficient, corona, heating, reference motion or transient sharing at high voltage.

Qualify differential and tip-to-earth limits separately, in both polarities and both gain positions. Start with the initial targets: ±1.5 kV differential on 1000:1 and ±300 V on 200:1, with each tip no more than ±1.5 kV to earth. Proposed continuous tests include DC and 35/60 kHz sine at the target peak voltages through thermal stabilization, with a minimum 60-minute hold. Record gain change, phase, leakage, temperature and partial-discharge/corona observations where the fixture supports them. Fixture ratings and insulation design must be established before energizing these tests.

Only then evaluate the extension to ±3 kV differential / tip-to-earth and ±600 V differential on 200:1. A proposed **limited burst-survival test**, separate from continuous accuracy qualification, is 3 kV peak sine at 35 and 60 kHz, 100 ms per burst, one burst per second, 100 bursts at each condition, covering each tip versus earth and differential excitation. Reverse DC polarity for separate 3 kV, 100 ms, 100-event tests. This defines an initial test objective; it does not define impulse withstand or authorize unrestricted 3 kV use. Record source impedance, rise/fall time and the actual waveform. A switching-impulse rating needs its own measured peak, dv/dt, width, source impedance and event count.

For recovery, begin at low voltage by intentionally exceeding the 200:1 output range, then return to a known in-range 35–60 kHz signal. Progress to the 1.5 kV differential / ×10 case only after lower-voltage behavior is understood. Measure connector peak voltage, raw amplifier saturation, reference disturbance, time to regain ±2% accuracy and whether the latch sets. Repeat both polarities, burst lengths, supply extremes and thermal conditions. Proposed recovery target: regain the specified amplitude accuracy within one 60 kHz cycle (16.7 µs); a faster fault-capture requirement must be stated and tested separately.

The 5 MHz bandwidth is initially a small-signal target. Derive and qualify voltage-versus-frequency and transient derating for the completed assembly before applying large high-frequency inputs. Unpowered-input survival is a separate test and is not claimed by the powered test results.

## 6. Stage-53 cross-check

Compare the direct capacitor voltage with integration of the independently measured capacitor current using the actual bank capacitance and CT transfer function. This is an independent consistency check, not a probe calibration. It is invalid when the capacitor bank fault changes the assumed capacitance or current path. Keep direct voltage capture for fault tests.

The inspected stage-53 T1 is CST3015-200ED (1:200) with a 3 Ω burden. Do not copy the older 1:100 / 1.5 Ω bench document into this comparison. Recheck the actual populated CT and burden before interpreting measured currents.

## Required result record

| Test | Result | Conditions / uncertainty |
|---|---|---|
| Rails, startup, battery loss and temperature | NOT RUN | |
| DC ratio, offset and drift, both ranges | NOT RUN | |
| 35–60 kHz amplitude and phase | NOT RUN | |
| Small-signal bandwidth and stability | NOT RUN | |
| CMRR versus frequency and amplitude | NOT RUN | |
| Input capacitance, shield edge current, DUT disturbance | NOT RUN | |
| Initial continuous voltage qualification | NOT RUN | |
| Extended range and defined burst survival | NOT RUN | |
| Output clamp and overload recovery | NOT RUN | |
| Unpowered and single-rail conditions | NOT RUN | |
| Stage-53 CT integration cross-check | NOT RUN | |
