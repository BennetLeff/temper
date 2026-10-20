# Rev B delay characterization for stage53 phase comparison

Status: proposed protocol; **no assembled-probe delay has been measured**. Retain DC–5 MHz response characterization and the two Rev B ranges. The 35–60 kHz requirement is ≤1° residual phase after a documented correction, with uncertainty included. Publish complex response versus frequency as the calibration authority; a nominal propagation delay is a convenience for scope setup.

## Identity and present evidence

The mandatory native21-stage15b baseline checks passed on 2026-10-20: PCB SHA-256 `9a9c43c63f63d383c89b9dc1d4d03a34d4390cfa1c26bbe802d71e169c6ddf94`. This establishes the repository baseline, not stage53 applicability. The separately selected stage53 board, `worktrees/runs-native21/s53/c53int/section.kicad_pcb`, still hashes to `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`.

Direct PCB inspection identifies T1 as CST3015-200ED, R39 as 3 Ω, and C42 as GRM31C5C1H104JA01L, nominal 100 nF, across the same `ct_s1`/`ct_s2` nets. Recheck fitted parts and measure the burden before calibration. The [Coilcraft datasheet](https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf) gives 1:200, 12.8 mH ±25%, and 5.94 Ω maximum secondary DCR; it supplies no phase-accuracy guarantee for this assembled burden. The historical 1:100/1.5 Ω model cannot supply stage53 correction.

Calculated from [the retained Rev B nominal LV model](../../validation/spice/results.txt):

| Range | Phase, 35 / 60 kHz | Equivalent phase delay |
|---|---|---|
| Wide, 1000:1 | −0.535623° / −0.918203° | 42.51 / 42.51 ns |
| Fine, 200:1 | −0.676190° / −1.159176° | 53.67 / 53.67 ns |

These exclude the HV divider, ADA4817 buffers and actual assembly parasitics. They are **not full-probe delay specifications**. The model includes the range-dependent amplifier response, shared nominal 6 MHz RC filter and representative lumped cable loading.

## Three different delay measurements

For unwrapped phase `φ` in radians, phase delay is `τp(f)=−φ/(2πf)`; group delay is `τg(f)=−dφ/d(2πf)`. A step delay is the difference between defined input/output crossing times, for example 50% of their settled excursions. Rise time, ringing and threshold choice affect that last result. These agree for a pure delay; this filtered probe is not one across DC–5 MHz. DC establishes gain and zero, not phase delay.

One degree corresponds to **79.37 ns at 35 kHz** and **46.30 ns at 60 kHz**. This is the entire equivalent timing budget for a 1° comparison, including residual calibration and instrumentation errors; it is not an allowable error for every contributor separately.

## Low-voltage calibration fixture and sequence

1. Warm the enclosed, battery-powered probe. Fix shield, tip separation, input leads, output cable and 1 MΩ scope loading to their intended configuration. Start with all software phase/deskew corrections recorded and disabled. Complete DC ratio and AC compensation first.
2. Characterize the scope channel ratio using a common source, matched splitter paths and the same acquisition settings used below. Swap paths/channels to expose residual channel and cable differences. Include vertical-scale-dependent phase and the calibrated reference probe/attenuator transfer function. A generator frequency specification alone does not calibrate the reference path. [Tektronix explains](https://www.tek.com/en/documents/application-note/power-supply-measurement-and-analysis-3-pwr) why stored nominal delays still require a fixture for precise deskew.
3. Use a compact low-voltage fixture with defined local return and differential test pads. Drive P with N connected locally to return; repeat with N driven and correct its sign. Also measure balanced differential excitation using a characterized differential source. Reference the **actual voltage across those same pads** with a calibrated differential reference, or two independently characterized reference channels. About 20 V input, where supported, gives only 20 mV wide/100 mV fine; select amplitudes and averaging from measured phase repeatability, without clipping either path.
4. Acquire reference and output simultaneously. Sweep logarithmically through 10 MHz, with dense 35–60 kHz points including 35, 45 and 60 kHz. Fit sine/cosine coefficients at the common measured frequency; retain residuals, harmonics and repeated acquisitions. Calculate `Hprobe(f)=Vout/Vdiff` after reference/channel correction. Repeat both ranges, polarities, amplitudes and intended temperatures. Validate interpolation at withheld frequencies. Fit a causal transfer model only if its residuals justify it; retain measured complex points regardless.
5. Apply a low-voltage step, recording 50% crossing delay, 10–90% rise time, overshoot and settling separately. Use it to detect anomalies and support a stated nominal delay, not replace the swept calibration.

Do not connect the negative tip remotely to scope ground as a substitute for its local fixture connection. That creates unequal return loops and can manufacture a phase/CMRR result. [Tektronix describes this ground-loop mechanism](https://www.tek.com/en/documents/application-note/making-single-ended-measurements-differential-probe). Differential gain calibration does not establish CMRR: separately tie both tips together and apply common-mode excitation. Any later tip pods require recalibration with their actual lead geometry.

## CT comparison and publication

On an unpowered, isolated stage53 assembly, characterize the actual CT primary path with a limited low-voltage AC current source and calibrated four-terminal wideband shunt. Establish an isolated fixture current path before connection. Measure `HCT(f)=Vburden/Ireference` with C42 and the intended readout loading present. Characterize any conditioning electronics separately or include them explicitly. Check amplitude dependence and reset history.

For illustration only, ideal current transformation into `3 Ω || 100 nF` gives `H=(3/200)/(1+j2πf·300 ns)`: −3.7745° at 35 kHz and −6.4526° at 60 kHz. Magnetizing current, winding impedance, capacitance, temperature and readout alter this; the calculation is not calibration.

Correct voltage/current phase by `arg(YV/YI)−arg(Hprobe)+arg(HCT)`, counting channel/cable deskew exactly once. Capacitor-current integration additionally requires actual tank capacitance and its frequency-dependent impedance; it remains an independent consistency check, not probe calibration.

Save per-point frequency, complex gain, phase, amplitude, range, temperature, supply rails, tip/shield geometry, cable identities/lengths, scope model/serial/channels/scales/loading/sample settings, reference certificates, deskew values, repeats and expanded uncertainty with coverage factor. Preserve raw captures and calibration revision. Combine reference, fit, repeatability, drift, CT and channel uncertainties with stated correlations. Validate against known reference phase using `|residual|+U95≤1°`; distinguish probe-only acceptance from the combined voltage/current comparison budget. Publish a range-specific nominal delay with test conditions alongside the full response table; never apply one blanket phase correction through 5 MHz.

Trust summary: **high confidence** in the recorded board identity and inspected burden connectivity; **analytical confidence only** in the tabulated delay equivalents and ideal RC illustration. Bench transfer functions, correction uncertainty and achieved acceptance remain **unmeasured**.
