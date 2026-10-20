# Historical Rev C compensation investigation

**Superseded intermediate circuit.** Use [the current validation report](analog-validation-rev-c.md). The following records why remote per-range compensation was rejected; its performance values do not describe the final fixed-local-capacitor design.

# Rev C full-chain stability and acquisition evidence

The coupled manufacturer-model convergence problem has been resolved without removing the FDA's DC bias or its load on the TI analog core. The investigation also found two real compensation concerns: the uncompensated 5 kΩ TIA and the original ADC-driver implementation. Revision C changes both circuits. Revision B is superseded and must not be ordered from its old files.

This is a simulation-qualified engineering prototype, not a physically qualified instrument. The acceptance criteria are: a true, finite unsaturated operating point; at least 45° at the relevant descending unity crossings, with approximately 60° preferred nominally; no sustained or growing response in the tested disturbances; and bounded ADC charge-recovery error at the retained 1 MSPS timing. Multiple crossings are reported separately and are not reduced to an arbitrary first-crossing “margin.” These criteria apply only to the stated models and test envelope.

## Changes supported by the evidence

| Circuit | Revision B | Revision C |
|---|---|---|
| 100 Ω TIA feedback | 100 Ω only | R43 in parallel with C104, 100 pF C0G ±5% |
| 5 kΩ TIA feedback | 5 kΩ only | R44 in parallel with C105, 10 pF C0G ±5% |
| 100 kΩ TIA feedback | 100 kΩ in parallel with 5 pF | Retained R45/C41 |
| FDA feedback | Dedicated RGT FB pads, 1 kΩ resistors | External feedback takeoff after each new 22 Ω output resistor; 1 kΩ in parallel with 100 pF |
| ADC isolation | 4.02 Ω per leg | 4.32 Ω per leg after the feedback takeoff |
| ADC shunt/differential capacitors | 330 pF per leg, 3.3 nF differential | Retained |
| Software | Rev B feedback model and calibration identity | Rev C identity, all three complex feedback impedances, rejects Rev B calibration |

The TIDA-060029 source resistor, matched feedback-resistor values, voltage followers and TIA topology remain. Added feedback capacitors are explicit deviations from TI's low and medium ranges. The driver revision follows the complete [ADS9224REVM guide, SBAU315B](https://www.ti.com/lit/pdf/SBAU315), pages 6 and 26. That board includes feedback capacitors and a resistor before the feedback takeoff, details absent from the abbreviated ADC datasheet diagram. Its inside resistor is 10 Ω; this board uses 22 Ω because both independent TI models retain better margin at the tested corners.

THS4551 RGT FB pads are optional taps through internal 3.3 Ω paths, not series resistors in the main OUT paths. They are left unconnected when external feedback is taken after the new 22 Ω resistors. This is an electrical inference from the manufacturer's functional diagram and conditional feedback-trace guidance, rather than an explicit vendor instruction saying “leave NC.” The native schematic and PCB include the complete post-resistor feedback path. REFby2 remains directly connected to both VOCM inputs with its local 1 µF capacitor; the EVM's separate 100 Ω/100 nF VOCM branches are not copied.

## Why the original simulation failed

The official unmodified OPA810, OPA2810 and 2021 THS4551 GWL libraries are retained with hashes. The original SPARSE solver fails on this stiff coupled network; KLU resolves that numerical limitation. The exact one-line solver A/B decks and logs are preserved in `validation/solver-resolution/gear.cir` and `klu.cir`.

A second failure could masquerade as success: transient operating-point fallback left the THS4551 model's internal MID reference near zero rather than its correct 2.499998750 V at a 5 V supply. Its artificial internal 1 F capacitor and 1 MΩ divider make a short fallback transient inadequate. An AC-coupling node could likewise retain a false DC offset. Exit status and “transient op finished successfully” were therefore insufficient. The retained negative regression must fail the operating-point guard.

The final network uses ngspice 45.2, PSpice compatibility, KLU, `reltol=1e-5`, `abstol=1e-12`, and `vntol=1e-7`. Resistor-node `.nodeset` guesses come from a verified coupled operating point and are released during Newton iteration. They are not forced initial conditions. `optran 1 0 0 0 0 0` disables gmin/source stepping and transient-OP fallback in the final full-chain harness. Some loads remain sensitive to matrix declaration order; a deterministic, bounded permutation search finds a valid Newton ordering while preserving every component line, connection and value. The line-map regression proves electrical identity. Every accepted run checks internal bias, AC-input DC, finite data, complete row counts, and absence of aborted analysis. Old output arrays are removed before rerunning.

The exact successful and failing decks, the seed-generation chain, permutation implementation, models, simulator details and reproducible guards are in [the final solver evidence](../validation/solver-resolution-rev-c-final/README.md). [Earlier solver diagnosis](../validation/solver-resolution/README.md) is historical evidence for the preceding ADC network; its performance numbers are not transferred to the final circuit.

## Loop measurement and results

The full-chain TIA analysis uses two independent current injections and a two-port impedance matrix. It inverts the matrix, removes the finite test-bridge admittance, and evaluates the bilateral Tian return ratio `(Y12 + Y21)/(Y11 + Y22)`. This preserves reverse loading through input capacitance and the rest of the closed circuit. A simple series-voltage probe at the summing input would not safely neglect that loading near the MHz crossings.

The [analytical oracle](../validation/stability-full-chain/return-ratio-oracle/README.md) tests known stable, unstable and multiple-crossing loops, matrix inversion/de-embedding, phase branches, and finite-band Nyquist limitations. A final-network 5 kΩ bridge sweep uses actual 1, 10, 100 and 1000 Ω bridges. The external DC-node change across the bridge sweep is at most1.52nV; near-unity complex-return variation is below3×10⁻⁶ and crossing angles agree below10⁻⁷ degrees. At low frequencies where loop gain is approximately3.6×10⁵, de-embedding a small bridge loses precision and shows up to2.1% variation. That numerical limitation is retained in the [invariance receipt](../validation/stability-full-chain/bridge-invariance-final.md), not represented as global invariance. All crossings are enumerated. Signed principal angular separation from −1 is reported; an upward crossing with a negative signed angle is not itself an instability verdict. No open-loop right-half-plane pole count is inferred from the samples, so no blanket Nyquist certificate is claimed.

An independent check cuts the ideal zero-current input to each amplifier's internal forward controlled source. Only a clearly named derived probe copy is instrumented; the official model remains untouched. All physical input capacitance, external feedback and output loading remain connected. The matched-range TIA results agree with the bilateral method. Source OPA810, OPA2810 source follower, HIGH follower and LOW follower have nominal conditional margins of approximately 76.40°, at least 57.06°, at least 56.12°, and at least 56.92°, respectively. See [all fifteen internal-cut cases](../validation/stability-full-chain/internal-loops-final.md).

| Range | Matched-resistor nominal margin | Lowest load/fixture grid | Lowest paired corner | Nominal20nH feedback-path minimum | Nominal50nH feedback-path minimum |
|---|---:|---:|---:|---:|---:|
|100 Ω|64.14°|49.29°|49.12°|45.85°|**33.05° — rejected envelope**|
|5 kΩ|66.93°|53.68°|51.83°|53.67°|53.67°|
|100 kΩ|71.13°|69.77°|69.46°|69.74°|69.69°|

The50nH case is an intentional failed stress condition on the low range, not a pass hidden in an average. It motivated a further compact feedback-layout change. Combined20nH plus the low-range component/supply paired corners gives a minimum45.43°;25nH drops to44.06°. Thus the low-range physical feedback path must be kept within the stated20nH design assumption, with the geometry estimate and hardware qualification documented separately. The other ranges retain more margin at50nH. These separate sweeps are not every joint combination of all perturbations.

The 5 kΩ and 100 kΩ ranges also pass a separate 100 nH lead-inductance sweep across all seven loads and both fixture-capacitance settings. Their minimum descending-crossing margins are approximately 53.66° and 69.61°, respectively. This gives the longer high-range jumper routes a wider modeled allowance; it does not establish their actual inductance. See the [28-case high-range lead sweep](../validation/stability-full-chain/matrix-final_leadwide.md).

The final5kΩ circuit with its10pF removed gives14.15° with a matched resistor and4.85° with100pF terminal capacitances. These are checked true-DC results; they replace the earlier provisional estimates. The new10pF compensation and independent fast-pulse comparison therefore address an observed model weakness, rather than a convergence artifact.

See [complete sweep summary](../validation/stability-full-chain/final-summary.md), [all paired corners](../validation/stability-full-chain/matrix-final_corners.md) and [compact-path corner sweep](../validation/stability-full-chain/matrix-final_compact.md).

The final TIA grid covers each range with a matched resistor, 10 mΩ short, 1 TΩ open, 100 nF, 500 nF, 9 µF, and a 50 µH + 0.5 Ω illustrative coil. Fixture capacitance is 0 or 100 pF from **each** DUT terminal to ground. The 84 paired corners vary feedback capacitance ±5%, RG/RF opposed ±0.1%, and analog/FDA supply rails ±5%. These are paired extremes, not every independently mismatched component combination. Another 84 cases add 20 or 50 nH in the feedback jumper path, after the parallel RF/CF network. These are bounded lumped sensitivity assumptions, not PCB-extracted or measured parasitics. The 5 pF part's actual ±0.1 pF tolerance is covered by the wider ±5% simulation.

The coil has multiple narrow return-ratio features on the deliberately mismatched 100 kΩ range. Its AC mesh is refined to 4800 points/decade; a sample-to-sample return-difference angle check rejects unresolved trajectories. Complete crossings and the minimum sampled return difference remain available in the case files. Use the 100 Ω range for the intended stage53 coil measurement.

Both final FDA differential loops give approximately 63.77° in the coupled circuit on all three ranges. Independent standalone controlled-source cuts using the current GWL and original 2016 TI model give 63.76° and 60.38° nominally. Across 64 combined corners per model, the minima are **62.57° and 59.19°**. The older model explicitly includes the manufacturer's internal 0.6 pF capacitors; the newer model uses another topology. No guessed capacitors were added to the newer vendor model. [Independent FDA evidence](../validation/fda-independent/README.md) documents the exact topology, model extraction, 134 runs and limitations.

The FDA common-mode input-port calculation is only an external coupling check; it does not open the amplifier's internal common-mode servo and therefore does not certify that servo's phase margin. A separate 10 mV, 10 ns VOCM step is bounded on all ranges, with about 45.69% common-mode overshoot and differential glitches below 0.43 µV. This is a small-disturbance test, not power-up qualification.

## Time-domain and acquisition checks

The final full chain passes true DC, AC and 120 µs sine-transient checks for 100 nF, 500 nF, 9 µF and the illustrative coil on the 100 Ω range, plus matched 5 kΩ and 100 kΩ resistors. Saved values are finite and output-current KCL residuals are below 1.6 pA. The physical FDA output common mode is approximately 2.048 V; the post-22 Ω feedback/ADC common mode is approximately 2.025 V because each input-resistor network draws about 1 mA. That real load remains in the coupled model.

A fast, local current disturbance from DUT_HI to DUT_LO excites the TIA directly, bypassing the DDS reconstruction filter. On 5 kΩ, removing its new capacitor gives **94.25% overshoot**; fitting 10 pF reduces nominal modeled overshoot below 0.0001%. The last excursion outside 1% changes from approximately 323 ns to 226 ns. These are model results, not measured board waveforms.

![5 kΩ fast local disturbance before and after compensation](../validation/stability-full-chain/figures/5k-before-after.png)

All54 supply/fixture pulse cases pass their finite, complete10µs trace and true-DC checks:27 with the old uncompensated5kΩ branch as a comparison, and27 with10pF. For the compensated branch, last excursion outside1% is225.84–226.48ns without added fixture capacitance,382.21–382.39ns with25pF per terminal, and1217.16–1218.12ns with100pF. Fixture capacitance can smooth a current pulse, so absence of overshoot is not used as a substitute for the independent loop analysis.

Ten further20µs fast-disturbance cases cover the stage-component/open/short fixtures and four deliberately mismatched100kΩ+coil ground-capacitance combinations. All are finite and bounded over the saved window. The LOW-only100pF high-range coil case decays slowly: HIGH-buffer envelope falls from5.75mV during12–15µs to4.00mV during16–20µs, and is **not settled** by20µs. An optional100µs extension was interrupted and is not counted. The complete accepted full-chain matrix has75 cases; see [corner results](../validation/solver-resolution-rev-c-final/corner-summary.md) and [extended traces](../validation/solver-resolution-rev-c-final/extended-final-results.md).

An additional [18-case feedback-lead pulse study](../validation/solver-resolution-rev-c-final/feedback-lead/README.md) retains the full coupled chain and tests the low range with open and coil fixtures, 100 pF to ground at each terminal, 10/20/50 nH feedback inductance, and paired supply/compensation extremes. Every trace is finite and bounded. On the open fixture, nominal 20 nH settles within 1% of peak in about 35 ns, versus about 98 ns at 50 nH; paired corners span approximately 32–38 ns and 75–129 ns. Bounded ringing at 50 nH does **not** override its failed 45° loop-margin criterion.

The ADC switching model is a separate bounded stress test based on the ADS9224R's documented 120 Ω switch resistance, 16 pF sampling capacitance and 1 pF pin capacitance. It perturbs five exact FDA copies with different capacitor reset states, and compares them with a sixth, always-tracking reference. At the retained 1 MSPS timing and conservative 640 ns acquisition window, the worst differential recovery error is **0.9166 µV**, below the 62.5 µV half-LSB comparison threshold. Actual ADC-pin voltages remain about 1.039–3.013 V and instantaneous common mode about 1.923–2.130 V, inside the specified ranges. Halving the integration timestep confirms the result.

The deliberately shortened 140 ns acquisition control gives **66.45 µV** error and fails that threshold. This is a useful negative control and a reason not to advertise a 3 MSPS upgrade from these files. The experiment does not include the real ADC's charge-injection waveform, all switch parasitics, reference disturbance or noise, and does not prove 16-bit physical accuracy. See [switched-load evidence](../validation/adc-switched-load/README.md).

## Limits and pre-order disposition

The retained evidence uses typical manufacturer macros at 27°C, ideal supply/reference sources and stated lumped loads. It does not provide semiconductor process corners, broad temperature qualification, extracted PCB parasitics, regulator-loop stability, switching-power pickup, ADC nonlinearity, source noise, fixture calibration accuracy, or physical startup/overload recovery. KLU does not support small-signal noise analysis; none is presented as a noise qualification.

The AD9833 is represented by a sine source with its nominal 200 Ω output resistance; digital feedthrough and DAC harmonics are omitted. The source RC filter, AC-coupling time constant and gain are included. Physical source settling, noise sweeps, all-range ringing checks, acquisition integrity and independent calibration standards remain required in [bring-up](bring-up.md).

This intermediate design was superseded by the fixed local 100 pF feedback capacitor. Its per-range compensation and lead-inductance results are development history, not the released Rev C circuit.

The firmware and host identify revision C and its feedback model. `Zf = RF/(1+jωRF·CF)` now applies on all three ranges. Old revision B calibration is rejected. No files have been uploaded to JLCPCB and no order has been placed.
