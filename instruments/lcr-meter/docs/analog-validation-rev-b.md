> **Historical revision B report.** Superseded by revision C. Read the final coupled results in `validation/solver-resolution-rev-c-final/` and `docs/analog-validation-rev-c.md`; do not use this historical circuit as the manufacturing target.

# Rev B analog simulation evidence

The nominal source network, bounded TI AFE model, and standalone ADC driver have executable ngspice results. **The complete coupled manufacturer-model circuit did not converge**, so this work does not establish full-instrument stability, accuracy, ADC settling, or noise performance. No hardware measurements have been made.

## What was simulated

The circuits were transcribed from `cad/design.json` revision B, with source R30/R31=330 Ω, C34/C35=1 nF, C36=1 µF, R32=100 kΩ, OPA810 gain 6, OPA2810 unity source driver, matched RG/RF pairs 100 Ω/5 kΩ/100 kΩ, and the 100 kΩ range's5 pF feedback capacitor. Both DUT voltage buffers remain in the AFE model, including the DUT_LO follower; current uses LOW_BUF−TIA_OUT. The ADS9224R channel drivers use THS4551,1 kΩ resistors,4.02 Ω isolation,330 pF shunts and 3.3 nF differential capacitors. The THS4551 RGT package's additional 3.3 Ω feedback path is included explicitly in the standalone FDA circuit, as required by its datasheet.

The AD9833 is represented by a voltage source with 200 Ω Thevenin resistance, consistent with its internal DAC output resistor. This is a small-signal approximation; it does not model DAC harmonics, clock feedthrough, quantization, amplitude tolerance or nonlinear output loading. ADC inputs are represented by 16 pF each in the standalone FDA case. These static capacitors do **not** reproduce the ADS9224R switched sampling network or acquisition kickback.

Official unmodified TI models were downloaded on 2026-10-20:

- [OPA2810 PSpice SBOMB66](https://www.ti.com/lit/zip/sbomb66), `sources/ti/models/opa2810_a.lib`.
- [OPA810 PSpice SBOMB73A](https://www.ti.com/lit/zip/sbomb73a), `sources/ti/models/opa810_a.lib`.
- [THS4551 PSpice SBOMB92B](https://www.ti.com/lit/zip/sbomb92b), `sources/ti/models/ths4551.lib`.

The libraries run unmodified under ngspice 45.2 using its `ps` compatibility mode. The generated decks, logs, numeric data, model hashes, Rust generators/analyzer and rerun script are in `validation/spice-rev-b/`. Independent smoke tests produce OPA2810 unity gain 1.000003, OPA810 gain 6.000056, and FDA differential gain approximately 1.0033 at 1 Hz. These establish basic model loading and pin-order sanity only.

## Results and their scope

See [complete numerical results](../validation/spice-rev-b/results.md) and [AC response plot](../validation/spice-rev-b/ac-response.svg).

The source network gives gain 5.949 at 1 kHz,5.740 at 34.674 kHz,5.377 at 60.256 kHz, and 4.675 at 100 kHz, including nominal gain 6. The intended measurement band therefore has source amplitude and phase variation. Voltage/current ratio measurement and calibration must account for the resulting signal levels; this is not a flat precision voltage source.

For a0→0.3 V DDS DC step, the passive-network model predicts245.6 mV residual at the gain 6 output after 200 ms,12.54 mV after 500 ms, and 88.2 µV after 1 s. The firmware's minimum 1000 ms delay is justified by this nominal approximately 100.86 ms coupling time constant. Actual C36 tolerance, leakage, amplifier startup and DDS disable behavior still require a scope check. This simulation does not guarantee settling to a particular LCR accuracy.

The bounded AFE checks use 100 nF,500 nF and 9 µF ideal capacitors; an illustrative50 µH coil with 0.5 Ω series resistance; and 5 kΩ/100 kΩ resistors. The estimated complex impedance follows the nominal DUT within approximately 0.12% through 100 kHz **in this restricted nominal model**. That number is not an instrument accuracy specification. It excludes resistor/capacitor tolerances, fixture parasitics, ADC error and switching, source noise, model limitations, and the full FDA loading described below. Small negative real parts predicted for ideal capacitors are model phase mismatch, not negative physical ESR; the calibration/validity checks remain essential.

The matched RG/RF topology from [TIDUEU6](https://www.ti.com/lit/pdf/TIDUEU6) is preserved. For a capacitive DUT with no feedback capacitor, the ideal noise gain is `(1+s(RF+RG)Cx)/(1+sRG Cx)`: the pole frequency is twice the zero frequency when RF=RG. This is an analytical reference explanation, separate from the finite-gain model results. The100 kΩ range uses `Zf=RF/(1+jωRF·5pF)` in the impedance reconstruction. At 100 kHz, Zf is approximately 95.4 kΩ at−17.44°; treating it as a pure100 kΩ would produce an approximately+17.44° phase error and 4.82% magnitude scaling error even with ideal amplifiers.

The TIA series-voltage return-ratio diagnostic gives nominal crossing margins around 69° for the 100 Ω range with capacitive DUTs,52° for the illustrative coil,30° for the 5 kΩ range with a5 kΩ DUT, and 92° for the 100 kΩ/5 pF range with a100 kΩ DUT. These are limited single-loop diagnostics with approximate loading, not stability certificates. **The 5 kΩ case is a concrete peaking/ringing concern to investigate on the assembled board and in a convergent full model.** No additional feedback capacitor was silently added to the TI circuit on the basis of this incomplete analysis.

The standalone THS4551 model includes its actual ADC RC load and nominal 2.048 V output common mode, driven by ideal input voltage sources. Its low-frequency differential gain is 1.003297. A 10 mV input step gives 1.55% overshoot and approximately 296 ns to its last sample outside 0.1% of the final increment, measured after the 10 ns input edge. This does not prove16-bit settling within the ADC acquisition interval: a 0.1% result is far looser than a 16-bit settling requirement, and the ADC switching load is absent. Its AC response has mild peaking near 22 MHz despite the lower-frequency output filter rolloff; measured ringing and susceptibility remain relevant.

## Coupled-model failure and approximation

`gear.cir`, `merged.cir`, `diagnostic.cir`, and their logs preserve attempts to run the whole circuit with all official amplifier models and both FDA loads. The full model fails its DC operating point with NaNs/timestep errors. The reduced `coupled-smoke.cir` reproduces the problem when bipolar OPA outputs drive a THS4551 input network biased by VOCM 2.048 V. The component models and the OPA-only chain run separately. Nodesets, larger iteration limits, alternate integration and small numerical shunts did not resolve the failure. Failed analyses are not counted as passes.

The successful `transfer_*.cir` and `loop_*.cir` therefore replace each FDA with its **incremental ideal input-loading network**. Input summing-node voltage is `(Vpositive+Vnegative)/(2+2·1000/1003.3)`; each input source connects through 1 kΩ. This captures nominal differential/common-mode resistive loading, but intentionally omits the approximately 1.026 V DC summing-node bias and all finite-bandwidth FDA input behavior. Consequently it omits the real DC sink current imposed on the OPA buffers/TIA and its effect on operating point and output impedance. The standalone `fda.cir` preserves actual FDA DC bias and its capacitive output loads. Combining these two bounded results is **not** equivalent to a successful coupled simulation.

## Required physical qualification

Use an isolated, discharged dummy DUT and a current-limited supply. Verify all rails and DUT terminals before fitting the stage 53 parts. Check source start/stop transients after the 1 s delay, and look for oscillation/ringing at source buffer, TIA output, both voltage buffers and both ADC differential pairs. Exercise all three ranges, especially5 kΩ, using short/open and representative R/C/L fixtures. Verify ADC-input acquisition settling and capture integrity with actual conversion timing, and measure source-off noise/spurs at the intended test frequencies. Perform range- and frequency-specific calibration and validate independent standards before using reported ESR/Q to diagnose stage 53. These steps qualify the physical instrument; the simulations here do not inherit TI's reference-board accuracy claim.
