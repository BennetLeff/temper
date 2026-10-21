# Calibration and qualification record template

Status: **bench tests not executed** (Rev C board; the Rev B version of this plan is in git at `ca79d882f`). Present evidence includes schematic ERC, native PCB DRC with explicit voltage-dependent spacing rules, schematic-to-board connectivity checks, divider geometry symmetry checks, ideal calculations and layer/3D review. The DRC rules were exercised with known-bad clearance, missing-slot, closed-notch and shortened-notch fixtures. No CMRR, bandwidth, high-voltage withstand or recovery result has been measured. See [layout assumptions and assembly constraints](layout.md).

Record the assembled PCB revision, component substitutions, selected compensation values, lead lengths, shield geometry, scope/cable configuration, ambient temperature and both supply voltages with every result. Calibration belongs to that complete assembly. Repeating it after moving a shield or replacing an input lead is necessary.

The operating restrictions of the [Rev B build and operating decision](revb-build-decision.md) carry over to Rev C unchanged. The 2026-10-20 [cost-down](cost-down.md) replaces the 0.1% resistor grade with ten 1% Uni-Royal HV12 bodies and a wider DC trim. This departs from the Rev B decision to keep 0.1%. Instead of a resistor-comparison campaign it adds the temperature-tracking and self-heating checks in section 2; if they fail, Stackpole HVCB2512BDE2M00 is a drop-in upgrade with no trim change. The restricted stage-53 setup is battery-powered, isolation-transformer-fed and free of an additional galvanic HOT-to-earth reference. It excludes BRING-UP steps 2–4 while their prescribed `hv_ret`–PE bond remains fitted. Ground-referenced calibration fixtures below are separate controlled qualification setups, not permission to use the prototype on an earthed HOT domain.

## 1. Low-voltage bring-up

With the DUT disconnected, verify the PCB-mount switch positions, battery polarity (BH9VPC pin 1 = +), the two regulated rails and the four threshold nodes (LIM_P/LIM_N about ±0.681 V, OUT_LIM_P/OUT_LIM_N about ±0.619 V; Rev C has no TL431 references). Confirm no oscillation at either input buffer, the fixed ×2 difference amplifier, the fixed ×5 stage or the output driver in both range positions. Check with the intended cable and scope load, including a longer cable as a stability stress test. Measure regulator and amplifier temperatures with fresh batteries and record current from each battery.

Verify the warning LED sets with either polarity at each input and at the selected-path threshold, remains set after removing the overload and clears with reset. Verify the conditional warning budget: gain at least 98% of nominal, buffer offsets within ±5 mV each, and actual selected-path zero within ±25 mV wide / ±130 mV fine before scope offset subtraction. Nominal warnings are about 1363 V per tip and 1239 V wide / 248 V fine; because the thresholds now derive from the rails, record both rails with every trip-point measurement. Measure the actual trip points over the stated temperature and supply ranges; confirm they warn before the initial ±1.5 kV tip limit and ±1.5 kV wide / ±300 V fine differential limits. An early warning is intentional margin, not a newly calibrated hard measurement boundary. Check startup, shutdown and loss of either battery. A lit LED immediately after startup can be cleared only after confirming valid rails. This design does not automatically inhibit measurements during low-battery operation.

At low voltage first, switch ranges while observing both gain-stage outputs and the final output. Verify break-before-make behavior, the selected node's DC return, contact bounce, transient amplitude and settling. Neither feedback loop should open. Check valid wide-range signals large enough to saturate the unused ×5 stage: the wide output must remain accurate and the warning detector must respond to the selected path, not the unused saturated output. Switching can still produce an invalid transient or latch the warning; establish the settling interval before treating the new-range trace as valid. Opening a feedback loop no longer imposes the former de-energize-to-select-range rule; this does not authorize moving HV leads or opening the enclosure while energized.

## 2. DC ratio and zero

Warm the powered probe, short both tips to GND and record output offset in each range. There is no analog zero trimmer; use a documented scope offset/subtraction and record drift. Offset uncertainty matters for low-amplitude signals: several millivolts at a buffer become volts of input-referred error through a 2000:1 divider.

Apply a traceable, ground-referenced low-voltage DC source to each tip in turn with the other at ground. Reverse polarity. Adjust RV1/RV2 for equal divider ratios and verify the overall 1000:1 and 200:1 gains. The nominal pot resistance is 132.5 Ω (500 Ω pot, 20 Ω per turn); set by ratio measurement, not an ohmmeter reading alone. Record both absolute gain and common-mode leakage; gain correction in the scope cannot repair a mismatch between the legs. Confirm that the ratio can be set and holds within 100 ppm of equal; the 500 Ω pot is ten times coarser than Rev B's 50 Ω.

**Temperature tracking (1% HV12 string).** The datasheet TCR limits allow 254 ppm/°C of leg-to-leg ratio drift, which is 51.9 dB DC CMRR after a 10 °C change from the trim temperature (`validation/cost-down.txt` §3). After trimming at room temperature, re-measure the DC ratio of each leg after a 30-minute powered warm-up and again at an ambient at least 10 °C away. Proposed acceptance: DC CMRR ≥ 60 dB over the operating range. **Self-heating.** With one leg at the highest available DC voltage (up to 3 kV), record its ratio over 10 minutes; the estimate is up to 3057 ppm at 3 kV DC (§4).

## 3. AC compensation and frequency response

Use a low-voltage generator and a calibrated reference scope channel to measure gain and phase at 35, 45 and 60 kHz. Around 20 V input is useful where the generator/fixture supports it, but the probe output is only 20 mV on 1000:1 or 100 mV on 200:1. Account for output noise and offset; use appropriate averaging and repeatability checks. The reference channel, generator amplitude and fixture all contribute uncertainty.

Begin with C41/C51 fitted, S1 (C42/C52) and S2 (C43/C53) at their nominal 3.0 nF and 160 pF, and both trimmers mid-range. Choose S1 from the measured stage-1 residual, re-measure, then choose S2, then trim; the no-gap proof in `validation/checks.txt` bounds the allowable measurement error (29.4 pF for S1, 11.1 pF for S2). When a select-on-test change is needed, de-energize and disconnect the probe before opening it and changing parts. Close the fixed shield and restore the defined lead geometry before measuring again. Make fine adjustments through the dedicated shield access holes with an insulated adjustment tool, using low-voltage excitation. Withdraw the tool before accepting a reading; its capacitance can alter the result. Keep access-hole geometry and any covers fixed for calibration and use.

Use swept sine response and a low-voltage step response to distinguish low-frequency compensation mismatch from distributed ladder parasitics. Verify both legs individually, then differential operation in both ranges. A single trimmer setting cannot correct arbitrary ladder parasitics across the whole band. Record both the coarse population and the fine adjustment, and verify repeatability after tool withdrawal and temperature stabilization.

Measure small-signal response from DC through 10 MHz, locating the actual −3 dB bandwidth. The nominal RC pole (R69 220 Ω, C61 100 pF), including selector source resistance, is 5.900 MHz and adds approximately −0.340° at 35 kHz and −0.583° at 60 kHz. The OPA2810/OPA810 vendor model gives 5.63 MHz wide and 5.13 MHz fine with no peaking (first-order estimates 5.56 / 4.94 MHz); account for actual amplifier/fixture delay and component tolerances. Proposed acceptance is ±2% amplitude at 35–60 kHz and ≤1° residual phase error after the stated calibration correction; report the uncertainty rather than claiming those numbers from component tolerances.

## 4. CMRR and loading

Tie the tips together at the source. Measure the common-mode voltage to earth with an appropriate ground-referenced reference and measure the residual probe output. For a probe ratio K (1000 or 200), calculate:

`CMRR_dB = 20 log10(|Vcm| / (K × |Vout_residual|))`.

Use matching amplitude conventions (RMS or peak) and report frequency, range, excitation amplitude and noise floor. If the residual is below the measurement noise, report a lower bound. Test 35–60 kHz and the switching-edge spectrum through 5 MHz; do not label a single 60 kHz result “60 dB DC–5 MHz.” Repeat after temperature stabilization and permitted lead movement.

The input-referred common-mode error is `|Vcm| / 10^(CMRR_dB/20)`. For example, at 1 kV common mode and 60 dB CMRR, the possible error is 1 V. It is 0.2% of a 500 V wanted signal but 10% of a 10 V wanted signal. Allocate this error alongside gain, offset, noise and reference uncertainty for each coil/capacitor measurement. The 60 dB goal does not override that calculation.

Measure input-to-earth capacitance and the edge current in the shield return, with the intended physical assembly. Compare 33 pF and 15 pF segment populations using separately compensated low legs. The 15 pF population requires approximately 5.997 nF ideal total bottom capacitance; changing only the top capacitors invalidates compensation. Compare measured rejection, edge current and DUT perturbation before accepting 33 pF. The per-tip loading target includes the entire lead and enclosure, not just the 6.6 pF ideal ladder. The tentative 10 pF target cannot be met by a lead that reaches both stage-53 bank nodes; it is revised to **12 pF**, against an 11.6 pF estimate (see [HV leads](hv-leads.md#capacitance-budget)). Measure each tip to GND at 1 MHz, with the leads in the recorded dress and ≥ 50 mm from earthed metal.

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

The design and its calculated budget are in [HV leads](hv-leads.md) and [`validation/leads/leads.txt`](../validation/leads/leads.txt). These tests check what the calculation assumes. Record the lead lengths, the dress photograph and the tip accessories with every result.

**Incoming wire OD and hipot.** Measure the insulation OD with calipers at both ends of each cut lead: accept 2.87–3.15 mm, the envelope `leads.rs` gates over (Rowe publishes no tolerance). Neither the Rowe R800-1020 listing nor the Alpha 392040 specification gives a withstand voltage, only the UL 3239 10 kV DC rating. Before fitting, wrap each cut lead in aluminium foil over its whole insulated length, leaving 25 mm bare at each end. Apply **5 kV DC for 60 s** between conductor and foil. Pass: no breakdown, leakage ≤ 1 µA. This is half the UL rating and 1.67 × the 3 kV extension.

**Lead and feedthrough hipot**, after assembly step 3 and before soldering (the divider would otherwise carry the test current and limit it to the ±3 kV envelope):

1. Fit the FR4 plate to the empty extrusion with its screws, the leads through the glands and the glands tightened. Cap each lead's internal cut end with heat-shrink and hold it ≥ 25 mm from metal.
2. Wrap foil around the external lead length up to the gland nut, and bond the foil to the extrusion.
3. Apply **4.5 kV DC (1.5 × the 3 kV extension) for 60 s**, conductor to extrusion and foil, each lead in turn. Pass: no breakdown, leakage ≤ 1 µA, no audible or visible discharge in a darkened room.
4. Repeat between the two conductors (twisted together, foil removed), 4.5 kV DC for 60 s, same pass criteria. This covers |V+ − V−| ≤ 3 kV with both insulations in series.

After soldering, the leads are tested only inside the ±3 kV envelope, as part of section 5.

**Assembled setback inspection.** With the lid off, measure lead conductor to lid plane (gated ≥ 20 mm; design 22.43 mm), W_HV joint to lid and floor, and tail length (≤ 1.0 mm). Confirm H3/H4 hardware is nylon. Photograph the bridge ties.

**Lead-movement CMRR sensitivity.** Using section 4's method, calibrate and measure CMRR at 60 kHz, 1 MHz and 5 MHz with the leads in the recorded dress (J5 and J2 tied together on the fixture). Then, without recalibrating, repeat with:

- the twisted section moved 50 mm toward an earthed plate (axis ≥ 50 mm from it);
- the tails spread to the bank spacing (58.5 mm) and closed to the coil spacing (15 mm);
- the probe box rotated 90° on the bench;
- the lid removed and refitted.

Record each CMRR and each tip's capacitance to GND. Proposed acceptance: CMRR change ≤ 3 dB and per-tip capacitance change ≤ 0.5 pF across these cases. The estimate (`leads.txt`) puts lead-path CM-to-DM conversion at −74 dB at 5 MHz; a larger measured change points to coupling inside the box. As a stress case only, lay one lead on the earthed plate and record the CMRR and capacitance change; this configuration is not permitted in use.

**Tip retention.**

- *Hook clip on the C22 test pin:* 20 cycles of attach and detach, then 5 N pull along the tail in three directions (along the pin, and both ways across it), 10 s each. Pass: the clip stays on the pin and the pin joint is undamaged.
- *TIP+ M4 ring on J5 and the TIP− fork adapter on J2:* torque to 1.2 N·m. Then 15 N pull on the lead at the ring or adapter for 10 s. Pass: no rotation past the stop, no movement of the crimp or solder joint, no damage to the barrel insulation, and the fork does not slide out from under the washer.
- *Shrouded plug in the clip and in the adapter:* 10 insertions each, then the 5 N pull above.
- *Gland:* 20 N pull on the external lead for 60 s, 25 times (the wire's maximum pull tension is 35 N). Pass: the length mark at the gland face moves ≤ 1 mm and the internal slack between the last bridge tie and the W_HV joint is unchanged. These numbers are chosen for this prototype, not quoted from a standard.

**Thermal.** The wire, gland and FR4 are rated 100 °C or higher; no lead self-heating is expected (the leads carry milliamps). Record the plate temperature during the section 5 60-minute holds.

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
| Range-change transient / settling and unused fine-stage saturation | NOT RUN | |
| Initial-envelope warning trip limits, both polarities and ranges | NOT RUN | |
| Unpowered and single-rail conditions | NOT RUN | |
| Stage-53 CT integration cross-check | NOT RUN | |
| 2 MΩ HV12 (HV121WF2004T4E) linearity at 600 V per body (VCR) | NOT RUN | |
| DC ratio tracking after warm-up and ≥ 10 °C ambient change; self-heating at high DC | NOT RUN | |
| 500 Ω DC trim settability (≤ 100 ppm) | NOT RUN | |
| Clamp current shared with OPA2810 input ESD diodes (R12/R32 limit) | NOT RUN | |
| PCB-mount BNC/E-Switch toggle fit (axis height, B5 flanged bushing, 1.5 mm end plate), Yageo 1812 body height, panel bonding, 3-D 20 mm setback in the owner's enclosure | NOT RUN | |
| Lead wire incoming hipot, 5 kV DC 60 s, each lead | NOT RUN | |
| Lead and feedthrough hipot, 4.5 kV DC 60 s, to enclosure and between leads | NOT RUN | |
| Assembled lead setback (conductor to lid ≥ 20 mm), tail length, H3/H4 nylon | NOT RUN | |
| Per-tip capacitance to GND, recorded dress (target ≤ 12 pF) | NOT RUN | |
| Lead-movement CMRR and capacitance sensitivity | NOT RUN | |
| Tip retention: hook clip, M4 rings, shrouded plugs, gland pull | NOT RUN | |
