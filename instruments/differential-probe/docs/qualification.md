# Calibration and qualification record template

Status: **bench tests not executed** (Rev C board; the Rev B version of this plan is in git at `ca79d882f`). Present evidence includes schematic ERC, native PCB DRC with explicit voltage-dependent spacing rules, schematic-to-board connectivity checks, divider geometry symmetry checks, ideal calculations and layer/3D review. The DRC rules were exercised with known-bad clearance, missing-slot, closed-notch and shortened-notch fixtures. No CMRR, bandwidth, high-voltage withstand or recovery result has been measured. See [layout assumptions and assembly constraints](layout.md).

Record the assembled PCB revision, component substitutions, selected compensation values, lead lengths, shield geometry, scope/cable configuration, ambient temperature and both supply voltages with every result. Calibration belongs to that complete assembly. Repeating it after moving a shield or replacing an input lead is necessary.

The operating restrictions of the [Rev B build and operating decision](revb-build-decision.md) carry over to Rev C unchanged. The 2026-10-20 [cost-down](cost-down.md) replaces the 0.1% resistor grade with ten 1% Uni-Royal HV12 bodies and a wider DC trim. This departs from the Rev B decision to keep 0.1%. Instead of a resistor-comparison campaign it adds the temperature-tracking and self-heating checks in section 2; if they fail, Stackpole HVCB2512BDE2M00 is a drop-in upgrade with no trim change. The restricted stage-53 setup is battery-powered, isolation-transformer-fed and free of an additional galvanic HOT-to-earth reference. It excludes BRING-UP steps 2–4 while their prescribed `hv_ret`–PE bond remains fitted. Ground-referenced calibration fixtures below are separate controlled qualification setups, not permission to use the prototype on an earthed HOT domain.

## 1. Low-voltage bring-up

With the DUT disconnected, verify the PCB-mount switch positions, battery polarity (BH9VPC pin 1 = +), the two regulated rails and the four threshold nodes (LIM_P/LIM_N about ±0.681 V, OUT_LIM_P/OUT_LIM_N about ±0.619 V; Rev C has no TL431 references). Confirm no oscillation at either input buffer, the fixed ×2 difference amplifier, the fixed ×5 stage or the output driver in both range positions. Check with the intended cable and scope load, including a longer cable as a stability stress test. Measure regulator and amplifier temperatures with fresh batteries and record current from each battery.

Verify the warning LED sets with either polarity at each input and at the selected-path threshold, remains set after removing the overload and clears with reset. Verify the conditional warning budget: calibrated gain at 25 °C at least 98.82% of nominal on the wide range and 98.86% on the fine range (98% after worst-case divider and gain-resistor drift over −25…85 °C; `validation/checks.txt`), buffer offsets within ±5 mV each, and actual selected-path zero within ±10 mV wide / ±45 mV fine before scope offset subtraction, which needs the zero trims set (§2; untrimmed the limits were ±25 / ±130 mV). Nominal warnings are about 1363 V per tip and 1239 V wide / 248 V fine; because the thresholds now derive from the rails, record both rails with every trip-point measurement. Measure the actual trip points over the stated temperature and supply ranges; confirm they warn before the initial ±1.5 kV tip limit and ±1.5 kV wide / ±300 V fine differential limits. An early warning is intentional margin, not a newly calibrated hard measurement boundary. Check startup, shutdown and loss of either battery. A lit LED immediately after startup can be cleared only after confirming valid rails. This design does not automatically inhibit measurements during low-battery operation.

**Trigger output (J4).** With the LED clear, J4 must read 0 V (within 10 mV) on a 1 MΩ input. Set the latch with each comparator condition in turn and record the J4 level into 1 MΩ and into a 50 Ω termination; model 4.445–4.920 V and 0.418–0.484 V (`validation/checks.txt`). Confirm reset clears J4 and the LED together, and that J4 cannot be set while the LED is off. Shorting J4 to its shell while latched must not clear or set the LED. Driving J4 from a 50 Ω source at −7 V and +11 V for 10 s must leave the latch state, both rails and the thresholds unchanged. Measure latency with a fast overdrive step at the selected-output comparator: time from the OV_N falling edge to J4 crossing 2 V on 1 MΩ (estimate 1.64 µs, an estimate, not a bound), and from the input step to J4. Repeat the latency at −25 °C and 85 °C if the chamber allows; the CD4013 timing maxima are 25 °C figures.

**Rails-OK indicator (D11).** With fresh batteries D11 must be lit in both range positions. Then power the board from two adjustable bench supplies in place of the batteries (current limit 60 mA), and sweep each regulated rail by trimming the supply into dropout and, for the over-voltage side, by back-driving the rail through 100 Ω from a third supply (the regulator then stops sourcing; keep the battery-side input above the rail) with the other rail held normal. Record the rail magnitude at which D11 goes out on each side: model UV 4.381–4.618 V and OV 4.927–5.200 V on +4.8 V, UV 4.335–4.595 V and OV 4.931–5.234 V on −4.8 V (`validation/checks.txt`). D11 must be lit at the measured regulated rails with at least 10 mV to every measured threshold; repeat at −25 °C and 85 °C if the chamber allows. Record the added battery current with D11 lit (model about 4.3 mA on +4.8 V and 2.2 mA on −4.8 V). Run the battery-loss check above with D11 watched: it must go out when either battery is removed.

At low voltage first, switch ranges while observing both gain-stage outputs and the final output. Verify break-before-make behavior, the selected node's DC return, contact bounce, transient amplitude and settling. Neither feedback loop should open. Check valid wide-range signals large enough to saturate the unused ×5 stage: the wide output must remain accurate and the warning detector must respond to the selected path, not the unused saturated output. Switching can still produce an invalid transient or latch the warning; establish the settling interval before treating the new-range trace as valid. Opening a feedback loop no longer imposes the former de-energize-to-select-range rule; this does not authorize moving HV leads or opening the enclosure while energized.

## 2. DC ratio and zero

Warm the powered probe for 30 minutes, short both tips to GND at the probe and record the output offset in each range before trimming. Then set the analog zero of each range at the BNC on a 1 MΩ input: RV3 on wide and RV4 on fine. The ranges are independent. Clockwise raises the output on both. Trim to within 0.1 mV wide and 0.5 mV fine, averaging the scope reading; the pots move about 1.8 mV and 11 mV per turn. Then measure SELECTED to GND on each range (the comparator's view, which keeps U3A's offset). Acceptance: within ±10 mV wide and ±45 mV fine. The model's worst case is 1.5 mV at 25 °C, rising to 9.58 / 44.39 mV over −25…85 °C (`validation/checks.txt`). Record the residual at the BNC after a power cycle, after re-docking, and at an ambient at least 10 °C away. Any remaining offset needs a documented scope offset/subtraction; record its drift. Offset uncertainty matters for low-amplitude signals: several millivolts at a buffer become volts of input-referred error through a 2000:1 divider.

Apply a traceable, ground-referenced low-voltage DC source to each tip in turn with the other at ground. Reverse polarity. Adjust RV1/RV2 for equal divider ratios and verify the overall 1000:1 and 200:1 gains. The nominal pot resistance is 132.5 Ω (500 Ω pot, 20 Ω per turn); set by ratio measurement, not an ohmmeter reading alone. Record both absolute gain and common-mode leakage; gain correction in the scope cannot repair a mismatch between the legs. Confirm that the ratio can be set and holds within 100 ppm of equal; the 500 Ω pot is ten times coarser than Rev B's 50 Ω.

**Temperature tracking (1% HV12 string).** The datasheet TCR limits allow 254 ppm/°C of leg-to-leg ratio drift, which is 51.9 dB DC CMRR after a 10 °C change from the trim temperature (`validation/cost-down.txt` §3). After trimming at room temperature, re-measure the DC ratio of each leg after a 30-minute powered warm-up and again at an ambient at least 10 °C away. Proposed acceptance: DC CMRR ≥ 60 dB over the operating range. **Self-heating.** With one leg at the highest available DC voltage (up to 3 kV), record its ratio over 10 minutes; the estimate is up to 3057 ppm at 3 kV DC (§4).

## 3. AC compensation and frequency response

Use a low-voltage generator and a calibrated reference scope channel to measure gain and phase at 35, 45 and 60 kHz. Around 20 V input is useful where the generator/fixture supports it, but the probe output is only 20 mV on 1000:1 or 100 mV on 200:1. Account for output noise and offset; use appropriate averaging and repeatability checks. The reference channel, generator amplitude and fixture all contribute uncertainty.

Begin with C41/C51 fitted, S1 (C42/C52) and S2 (C43/C53) at their nominal 3.0 nF and 160 pF, and both trimmers mid-range. Choose S1 from the measured stage-1 residual, re-measure, then choose S2, then trim; the no-gap proof in `validation/checks.txt` bounds the allowable measurement error (29.4 pF for S1, 11.1 pF for S2). When a select-on-test change is needed, de-energize and disconnect the probe before opening it and changing parts. Close the fixed shield and restore the defined lead geometry before measuring again. Make fine adjustments through the dedicated shield access holes with an insulated adjustment tool, using low-voltage excitation. Withdraw the tool before accepting a reading; its capacitance can alter the result. Keep access-hole geometry and any covers fixed for calibration and use.

Use swept sine response and a low-voltage step response to distinguish low-frequency compensation mismatch from distributed ladder parasitics. Verify both legs individually, then differential operation in both ranges. A single trimmer setting cannot correct arbitrary ladder parasitics across the whole band. Record both the coarse population and the fine adjustment, and verify repeatability after tool withdrawal and temperature stabilization.

Measure small-signal response from DC through 15 MHz, locating the actual −3 dB bandwidth. The output filter has two poles: R69 220 Ω / C61 47 pF ahead of the driver (12.55–12.56 MHz including the selector source resistance) and R70 49.9 Ω into C62 330 pF plus the cable and scope input at the BNC (7.09 MHz with a lumped 120 pF); together they add approximately −0.44° at 35 kHz and −0.76° at 60 kHz (`validation/checks.txt`). The OPA2810/OPA810 vendor model gives 5.77 MHz wide and 5.27 MHz fine with no peaking, and −1.00° / −1.24° at 60 kHz (`validation/spice/results.txt`; first-order estimates 5.46 / 4.90 MHz); account for actual amplifier/fixture delay, the real cable and component tolerances. Proposed acceptance is ±2% amplitude at 35–60 kHz and ≤1° residual phase error after the stated calibration correction; report the uncertainty rather than claiming those numbers from component tolerances.

**Bandwidth jumper (JP1).** Record the JP1 state with every result; the calibration belongs to one state. On one board, after the bridged-state measurements, cut JP1 with a scalpel between its pads, confirm it is open with an ohmmeter (C62 then reads open from OUT to GND), and repeat the swept response and the 35/60 kHz gain and phase in both ranges. Model: 10.86 MHz wide / 8.45 MHz fine, −0.64° / −0.89° at 60 kHz, no peaking. Check the step response for ringing with the intended cable in both states. Restore the bridge with a solder blob and confirm the original response returns within the measurement repeatability before using the board in the bridged state again.

**Output noise.** With both tips shorted to GND at the probe, record the BNC output RMS noise in both ranges at full scope bandwidth and with the scope's 20 MHz limit, 1 MΩ input. Refer it to the tips by dividing by the measured gain. Model, bridged: 172 mV wide / 116 mV fine full band, 127 / 109 mV to 20 MHz (`validation/spice/output-filter-study.txt`). The scope's own noise floor at that setting must be subtracted in quadrature and stated.

## 4. CMRR and loading

Tie the tips together at the source. Measure the common-mode voltage to earth with an appropriate ground-referenced reference and measure the residual probe output. For a probe ratio K (1000 or 200), calculate:

`CMRR_dB = 20 log10(|Vcm| / (K × |Vout_residual|))`.

Use matching amplitude conventions (RMS or peak) and report frequency, range, excitation amplitude and noise floor. If the residual is below the measurement noise, report a lower bound. Test 35–60 kHz and the switching-edge spectrum through 5 MHz; do not label a single 60 kHz result “60 dB DC–5 MHz.” Repeat after temperature stabilization and permitted lead movement.

The input-referred common-mode error is `|Vcm| / 10^(CMRR_dB/20)`. For example, at 1 kV common mode and 60 dB CMRR, the possible error is 1 V. It is 0.2% of a 500 V wanted signal but 10% of a 10 V wanted signal. Allocate this error alongside gain, offset, noise and reference uncertainty for each coil/capacitor measurement. The 60 dB goal does not override that calculation.

Measure input-to-earth capacitance and the edge current in the shield return, with the intended physical assembly. Compare 33 pF and 15 pF segment populations using separately compensated low legs. The 15 pF population requires approximately 5.997 nF ideal total bottom capacitance; changing only the top capacitors invalidates compensation. Compare measured rejection, edge current and DUT perturbation before accepting 33 pF. The per-tip loading target includes the entire lead and enclosure, not just the 6.6 pF ideal ladder. The tentative 10 pF target cannot be met by a lead that reaches both stage-53 bank nodes; it is revised to **12 pF**, against estimates of 11.71–11.93 pF for the option-B probes (see [HV leads](hv-leads.md#capacitance-budget)). Measure each tip to GND at 1 MHz with the probe docked (section 7).

## 5. Voltage extension and overload recovery

First establish higher-voltage linearity on a controlled, ground-referenced fixture whose reference probe is rated for the applied waveform. A passive single-ended HV probe is appropriate only because that reference fixture is ground-referenced. Measure actual reference-probe gain/phase uncertainty. C0G stability supports transferring a low-voltage ratio calibration, but it does not establish insulation, resistor voltage coefficient, corona, heating, reference motion or transient sharing at high voltage.

Qualify differential and tip-to-earth limits separately, in both polarities and both gain positions. Start with the initial targets: ±1.5 kV differential on 1000:1 and ±300 V on 200:1, with each tip no more than ±1.5 kV to earth. Proposed continuous tests include DC and 35/60 kHz sine at the target peak voltages through thermal stabilization, with a minimum 60-minute hold. Record gain change, phase, leakage, temperature and partial-discharge/corona observations where the fixture supports them. Fixture ratings and insulation design must be established before energizing these tests.

Only then evaluate the extension to ±3 kV differential / tip-to-earth and ±600 V differential on 200:1. The compact Rev C envelope (unchanged from Rev B) requires all three constraints simultaneously: `|V+| ≤ 3 kV`, `|V−| ≤ 3 kV`, and `|V+ − V−| ≤ 3 kV`. It does not include applying +3 kV and −3 kV to the two tips together. A proposed **limited burst-survival test**, separate from continuous accuracy qualification, is 3 kV peak sine at 35 and 60 kHz, 100 ms per burst, one burst per second, 100 bursts at each condition, covering each tip versus earth and differential excitation within that combined envelope. Reverse DC polarity for separate 3 kV, 100 ms, 100-event tests. This defines an initial test objective; it does not define impulse withstand or authorize unrestricted 3 kV use. Record source impedance, rise/fall time and the actual waveform. A switching-impulse rating needs its own measured peak, dv/dt, width, source impedance and event count. The initial-limit warning will remain active during extension tests; it does not expand its thresholds automatically.

**Continuous-DC limit for the HV12 string.** With the cost-down 1 W HV12 bodies, the single-fault case (the 3-body group bypassed, two bodies left) stays within rating up to 2 × √(1 W × 2 MΩ) = **2.83 kV continuous DC per tip** (`docs/cost-down.md`, Stress). Above that, apply DC only as the 100 ms bursts defined here. AC at 35–60 kHz up to the 3 kVpk extension is unaffected (56 % of rating in the same fault). Fitting the Stackpole HVCB2512BDE2M00 upgrade removes this limit.

For recovery, begin at low voltage by intentionally exceeding the 200:1 output range, then return to a known in-range 35–60 kHz signal. Progress to the 1.5 kV differential / ×10 case only after lower-voltage behavior is understood. Measure connector peak voltage, U12 saturation, selected-path behavior, reference disturbance, time to regain ±2% accuracy and whether the latch sets. Repeat both polarities, burst lengths, supply extremes and thermal conditions. Proposed recovery target: regain the specified amplitude accuracy within one 60 kHz cycle (16.7 µs); a faster fault-capture requirement must be stated and tested separately.

The 5 MHz bandwidth is initially a small-signal target. Derive and qualify voltage-versus-frequency and transient derating for the completed assembly before applying large high-frequency inputs. Unpowered-input survival is a separate test and is not claimed by the powered test results.

## 6. Stage-53 cross-check

Compare the direct capacitor voltage with integration of the independently measured capacitor current using the actual bank capacitance and CT transfer function. This is an independent consistency check, not a probe calibration. It is invalid when the capacitor bank fault changes the assumed capacitance or current path. Keep direct voltage capture for fault tests.

The inspected stage-53 T1 is CST3015-200ED (1:200) with a 3 Ω burden. Do not copy the older 1:100 / 1.5 Ω bench document into this comparison. The [stage-53 CT correction](stage53-ct-correction.md) records the verified datasheet, corrected flux estimates and the separate DC-pulse/reset limitations. Recheck the actual populated CT and burden before interpreting measured currents.

Measure R39 and the effective shunt capacitance across `ct_s1`–`ct_s2` on the assembled unit; do not use nominal 100 nF as a calibration value. C42's specified MPN is GRM31C5C1H104JA01L, C0G ±5%, not X7R ±10%. Record actual fitted part, measurement frequency, test level, temperature, fixture/loading correction and uncertainties. An in-circuit capacitance reading through the 3 Ω burden and CT winding is not a valid measurement unless the method explicitly separates those parallel paths. Measure the capacitor isolated from those paths, or fit the assembled complex transimpedance with an independently measured injected current.

For the ideal CT/burden model use `Hct(f) = (Rb / 200) / (1 + j·2πf·Rb·Cb)`. Recover current as `I(f) = 200·(1/Rb + j·2πf·Cb)·Vburden(f)`; then obtain capacitor voltage from `Vc(f) = I(f)/(j·2πf·Cbank)` with measured bank capacitance and the verified current polarity. Include the measured downstream conditioning and acquisition transfer if observing CT_MON rather than directly across the burden. Do not add CT winding resistance to Rb in this signal correction; it belongs in a fuller CT model and the separate flux estimate.

Nominal 3 Ω / 100 nF gives −6.4526° and 0.993665 voltage magnitude relative to the DC scale at 60 kHz; the inverse correction advances current by +6.4526° and multiplies its magnitude by 1.006375. These are calculated examples, **not calibration values**. Use the measured complex CT response where available and do not apply this RC correction twice. Integrate only within the characterized bandwidth; differentiation implicit in the inverse RC correction amplifies high-frequency noise. Record the integration constant/baseline for time-domain reconstruction. Allocate probe, CT, channel/cable and reference uncertainty together against the ≤1° residual target.

## 7. Leads, feedthroughs and tips

The design and its calculated budget are in [HV leads](hv-leads.md) and [`validation/leads/leads.txt`](../validation/leads/leads.txt). Option B uses two dedicated probes docked on stage 53 in a fixed, printed geometry; these tests check what the calculation assumes. Record the reel, the cut lengths and the docked photograph with every result.

**Incoming wire (acceptance basis of the unrated generic wire).** On receipt of each reel:

1. Measure the insulation OD with calipers at both ends of each cut lead and at three points on the reel. Accept 2.87–3.15 mm, the range `leads.rs` gates over.
2. Strip 10 mm and measure the conductor bundle across its widest point. Accept ≤ 1.05 mm; it must pass C22's 1.2 mm hole.
3. Take a 300 mm sample from the reel. Wrap it in aluminium foil over its insulated length, leaving 25 mm bare at each end, and apply **5 kV DC for 60 s** between conductor and foil. Pass: no breakdown, leakage ≤ 1 µA. Reject the reel on any failure and use a rated UL 3239 10 kV wire (Rowe R800-1020 or Alpha 392040).
4. Repeat the 5 kV DC 60 s test on every cut lead before fitting.

5 kV is 1.67 × the 3 kV extension. The test is the only voltage basis for the generic wire; the "10 kV" in the listing is not used.

**Lead and feedthrough hipot**, before the W_HV joints are soldered (the divider would otherwise carry the test current):

1. Fit the wall insert to the empty enclosure with the leads through the glands and the glands tightened. Cap each internal cut end with heat-shrink and hold it ≥ 25 mm from metal.
2. Wrap foil round the external length up to the gland dome and bond it to the enclosure.
3. Apply **4.5 kV DC for 60 s**, conductor to enclosure and foil, each lead in turn. Pass: no breakdown, leakage ≤ 1 µA, no audible or visible discharge in a darkened room.
4. Repeat between the two conductors (foil removed), 4.5 kV DC for 60 s.

After soldering, the leads are tested only inside the ±3 kV envelope (section 5).

**Assembled setback inspection.** With the lid off: lead conductor to lid plane (≥ 20 mm; design 22.54 mm), W_HV joint to lid and floor, tail length ≤ 1.0 mm, nylon at H3/H4. On stage 53: nylon at H6, H7, H8, H10; no lead within 1 mm of a stage-53 body (closest by design: probe 1 TIP+ to C22, 1.43 mm); both ring sleeves seated in the dock-coil channels.

**Per-tip capacitance with the dock fitted.** Stage 53 unpowered. Measure each tip to probe GND at 1 MHz with each probe docked and its spine fitted, then on the calibration jigs. Target ≤ 12 pF (estimates: probe 1 11.71/11.72, probe 2 11.80/11.93 pF). Record the difference between stage 53 and the jig: it tests whether the jig reproduces stage 53's stray environment.

**CMRR in the fixed geometry and re-dock repeatability.** Calibrate each probe as in [HV leads](hv-leads.md#calibration) and measure CMRR at 60 kHz, 1 MHz and 5 MHz using section 4's method: on the CM jig for both probes, and in place on stage 53 by the floating-DUT CM drive (stage 53 unpowered, isolated from mains and earth, bank discharged, the CM source between J5 and earth; probe 2 only below 100 kHz). Then, without recalibrating, undock and re-dock five times (spine and dock removed and refitted, screws re-torqued). Proposed acceptance: CMRR within 3 dB and per-tip capacitance within 0.1 pF across re-docks, and the floating-DUT result within 6 dB of the jig result. The estimate (`leads.txt`) puts lead CM-to-DM conversion at 68 dB (probe 1) and 70 dB (probe 2) at 5 MHz. A larger change points to a part that moves or to coupling inside the box. As a stress case only, move the probe box 50 mm and record the change; this is not a permitted configuration.

**C22 solder joint, no tension.** After probe 1 is docked and TIP− soldered:

1. Inspect the joint at 10× from the top and bottom: full fillet, insulation ending ≤ 1 mm above the pad, tail ≤ 1 mm.
2. With a non-conductive probe, deflect the lead 1 mm sideways between the clamp and the board. It must move freely and spring back, showing slack in the S-jog.
3. Pull 10 N on the lead above the dock (at the spine end) for 10 s, three times. Pass: no visible movement of the lead at the joint (a mark on the insulation 2 mm above the pad stays put under 10×), and the clamp and riser clip stay seated.

**Tip retention.**

- *Rings on J5 and J2:* torque to 1.2 N·m. Then 15 N pull on the lead at the ring for 10 s (dock removed). Pass: no movement of the crimp or the heat-shrink, no rotation of the ring under the washer.
- *Dock and spine:* 20 N pull on each lead outside the box for 60 s, 10 times. Pass: no lead pulled out of a groove or saddle, no change at the rings or the C22 joint, and the gland length mark moves ≤ 1 mm.
- *Snap saddles and riser clips:* 10 insertions and removals of an offcut lead. Pass: no cracking, and the lead is still retained.

These forces are chosen for this prototype, not quoted from a standard.

**Thermal.** Glands, ring sleeves and resin are rated 100 °C or higher (the wire 150 °C for the rated fallbacks; the generic wire's rating is not known). No lead self-heating is expected. Record the dock temperatures near the bank capacitors and T1 during the section 5 holds.

## Required result record

| Test | Result | Conditions / uncertainty |
|---|---|---|
| Rails, startup, battery loss and temperature | NOT RUN | |
| DC ratio, offset and drift, both ranges | NOT RUN | |
| Rails-OK indicator D11: lit with healthy rails, UV/OV trip points on each rail, margin to the regulated rails, added battery current, battery loss | NOT RUN | |
| Analog zero trims RV3/RV4: reach, settability (0.1 / 0.5 mV), SELECTED residual (±10 / ±45 mV), stability after power cycle, re-dock and ±10 °C | NOT RUN | |
| 35–60 kHz amplitude and phase | NOT RUN | |
| Small-signal bandwidth and stability, JP1 bridged and cut | NOT RUN | |
| Output noise, both ranges, full bandwidth and 20 MHz limit | NOT RUN | |
| CMRR versus frequency and amplitude | NOT RUN | |
| Input capacitance, shield edge current, DUT disturbance | NOT RUN | |
| Initial continuous voltage qualification | NOT RUN | |
| Extended range and defined burst survival | NOT RUN | |
| Output clamp and overload recovery | NOT RUN | |
| Range-change transient / settling and unused fine-stage saturation | NOT RUN | |
| Initial-envelope warning trip limits, both polarities and ranges | NOT RUN | |
| Trigger output J4: idle level, latched level into 1 MΩ and 50 Ω, reset, short and back-drive tolerance, latency from OV_N and from the input step | NOT RUN | |
| Unpowered and single-rail conditions | NOT RUN | |
| Stage-53 CT integration cross-check | NOT RUN | |
| 2 MΩ HV12 (HV121WF2004T4E) linearity at 600 V per body (VCR) | NOT RUN | |
| DC ratio tracking after warm-up and ≥ 10 °C ambient change; self-heating at high DC | NOT RUN | |
| 500 Ω DC trim settability (≤ 100 ppm) | NOT RUN | |
| Clamp current shared with OPA2810 input ESD diodes (R12/R32 limit) | NOT RUN | |
| PCB-mount BNC (J3, J4)/E-Switch toggle fit and J4–SW1 nut clearance (axis height, B5 flanged bushing, 1.5 mm end plate), Yageo 1812 body height, panel bonding, 3-D 20 mm setback in the owner's enclosure | NOT RUN | |
| Lead wire incoming OD, conductor bundle and 5 kV DC 60 s hipot (reel sample and each lead) | NOT RUN | |
| Lead and feedthrough hipot, 4.5 kV DC 60 s, to enclosure and between leads | NOT RUN | |
| Assembled lead setback (conductor to lid ≥ 20 mm), tail length, nylon at H3/H4 and H6–H10 | NOT RUN | |
| Per-tip capacitance to GND with the dock fitted, stage 53 and jig (target ≤ 12 pF) | NOT RUN | |
| CMRR in the fixed geometry, re-dock repeatability, floating-DUT CM check | NOT RUN | |
| C22 solder joint inspection and no-tension check | NOT RUN | |
| Tip retention: M4 rings, dock and spine pull, snap saddles and clips | NOT RUN | |
