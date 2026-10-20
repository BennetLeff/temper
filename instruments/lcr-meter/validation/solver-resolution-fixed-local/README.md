# Final Rev C fixed-local compensation: coupled transient evidence

This directory qualifies the final `C-local100p` feedback arrangement in a fully coupled source, TIDA-060029 analog front end, and two THS4551 ADC-driver macromodels. It supersedes the **per-range-capacitor** transient results in `../solver-resolution-rev-c-final/` for the final hardware. Those earlier results remain historical evidence.

The retained circuit includes real FDA DC input currents and common-mode bias, all four OPA2810 channels, the OPA810 source stage and coupling network, and both complete ADC input RC loads. No amplifier is replaced with an ideal op amp and no bias current is removed to obtain convergence.

## Circuit and stress assumptions

- One fixed **100 pF** capacitor connects locally between the TIA output and inverting input for every range. RF remains 100 Ω / 5 kΩ / 100 kΩ, paired with equal RG.
- The stress network places **100 nH only in the selected RF branch**, and **5 nH only in the local capacitor branch**. These are explicit lumped assumptions, not extracted PCB inductances. The lead's separate AC matrix covers additional local-path sensitivity.
- FDA physical outputs each feed 22 Ω to the feedback takeoff. Each takeoff returns through 1 kΩ ∥ 100 pF to the opposite input, then feeds 4.32 Ω to the ADC node. Each ADC node has 330 pF plus 16 pF static loading to ground; 3.3 nF connects each differential pair. The RGT internal FB pins are unused, so their open 3.3 Ω branches are not inserted in the signal path.
- The source and TIDA amplifiers use ±12 V; FDA supply is 5 V and VOCM is 2.048 V. Paired open-fixture corners vary AFE/FDA rails and local capacitor together by ±5%. No rail-dependent change is made to the external 2.048 V VOCM source.
- The models are unmodified official TI OPA2810, OPA810 and **2021 GWL THS4551** releases. Their exact hashes are in `MODEL-SHA256SUMS`. The lead's separate FDA review covers the alternate TI architecture and switched-input stress.

## Completed checks

There are **16 complete OP/AC/transient cases**: 15 final-compensation cases and one deliberately uncompensated 5 kΩ comparator. Three additional 21-point, strict-OP AC sweeps cover matched loads from 1 kHz through 100 kHz.

| Evidence | Cases | Results |
|---|---:|---|
| Local 1 µA HI→LO pulse, 1 ns edges | 7 | All three matched ranges; 100 Ω open and 50 µH + 0.5 Ω coil with 100 pF per DUT terminal to ground; paired open-fixture corners |
| Same 5 kΩ pulse without compensation | 1 | Controlled before/after comparison; same source, FDA, load and lead assumptions |
| Actual-amplitude 100 kHz sine | 3 | Matched 100 Ω / 5 kΩ / 100 kΩ loads, DDS 0.3 V peak |
| 10 mV VOCM step | 1 | Matched 5 kΩ, 1 ns edges, real DC loading |
| Stage53 load-equivalent sine | 4 | 100 nF / 500 nF / 50 µH + 0.5 Ω at 50 kHz; 9 µF at 1 kHz, all on 100 Ω range |

Read [results.md](results.md), [sine-common-mode.md](sine-common-mode.md), and [stage53-results.md](stage53-results.md). Exact values are in their CSV companions, `ac-results.csv` and `dc-kcl.csv`. Every transient's complete data and corresponding deck/log are retained.

The 5 kΩ comparison reduces rising overshoot from **94.56% to <0.001%**, while increasing 1% settling from about **293 ns to 2.30 µs**. The matched 100 kΩ range takes about **46.0 µs** to settle to 1%, consistent with its 10 µs nominal RF×CF time constant. The 100 Ω open-fixture corners remain bounded with ≤0.733% rising overshoot. Pulse settling is reported against the 1 Hz current-disturbance transfer, not a potentially unsettled end-of-pulse sample.

At 100 kHz the matched 100 kΩ sine produces about **0.698 V peak on A and 0.110 V peak on B**. Nominal |100 kΩ ∥ 100 pF| is 15.718 kΩ (−16.07 dB relative to DC). Prefer this range at ≤10 kHz for current-channel signal strength; calibration can correct the complex transfer but cannot recover lost signal-to-noise ratio. The updated host still permits calibrated measurements to 100 kHz with quality checks.

The VOCM step's ADC common-mode overshoot is 45.72%, with 1% settling around 1.50 µs and differential glitches below 0.40 µV in this deterministic model. This is a common-mode transient result, not the differential TIA stability margin.

## Solver guards and limits

ngspice 45.2/KLU runs with `reltol=1e-5 abstol=1e-12 vntol=1e-7 method=gear`. `optran 1 0 0 0 0 0` permits strict Newton initialization and disables gmin/source/transient fallback. Resistor-node `.nodeset` entries are initial guesses only. The solver independently converges the unchanged network. All current cases accept original declaration order 0; `strict_order.rs` retains a deterministic order-search fallback that never changes a component or model.

The false-OP regression matters: the THS4551 model contains a very slow internal midpoint state. A quasi-transient fallback can return finite but incorrect bias. Every accepted case requires each FDA's internal MID to equal `V5 / (2 + 1e-6)` within 1 µV, a physically valid source coupling DC input, and all finite raw operating-point values. Three helper regressions verify true-OP acceptance, false-OP rejection and exact component-set preservation.

Validators require complete finite OP/AC/transient files, monotonic timestamps, the requested final time, ADC pin/differential headroom, and bounded amplifier output voltages/currents. External HIGH/LOW/TIA DC KCL residuals are approximately 1 pA. Logs/process status alone cannot pass a case. Output current below the 20 mA harness threshold is a checked window, not a new device rating. The 9 µF case approaches that threshold (TIA about −19.90 to +19.36 mA); bench qualification must verify source and TIA behavior.

Pulse windows are 20 µs with 1 ns maximum step, except the matched 100 kΩ case: 120 µs, 60 µs pulse width, maximum 5 ns. Matched sine runs are 120 µs with maximum 5 ns. Stage53 50 kHz runs use 240 µs/10 ns maximum, except 500 nF extends to 600 µs; the smooth 1 kHz case uses 12 ms/250 ns maximum. Strict tolerances remain unchanged; adaptive solver steps can be smaller. Sinusoidal fits use final four cycles (three for the extended 500 nF case) and agree with full-chain AC amplitudes within 1%. No claim extends beyond these finite windows and specified loads.

This evidence does **not** establish physical instrument accuracy, startup settling, noise/SNR, manufacturing variation, unmodeled parasitics, or switching-supply rejection. Static ADC capacitance does not reproduce sampling kickback; see the separate FDA stress review. Real stage53 components are tested isolated and discharged, never powered/in-circuit. The ideal capacitor fits show small uncalibrated real-part errors; those are not predicted physical ESR. Independent standards and fixture calibration remain necessary.

## Reproduction

Run `./rerun.sh --check` to verify hashes, run the three solver-regression tests, and recompute all result tables from retained traces. Rust 2021 and ngspice with KLU/PSpice compatibility are required. `NGSPICE` can select the executable.

Run `./rerun.sh --full` **in a copy of this directory** to preserve the captured evidence. It regenerates and runs all cases with relative local includes, then checks the results. New raw files contain new timestamps, so their evidence manifest will differ. Helper executables are built in a temporary directory and removed automatically. `base.cir` is the source template; `run.rs` adds the explicitly separated local-capacitor and RF lead branches. The standalone `ac_sweep.rs` provides 21-point sweeps with both endpoints; the pulse decks' preliminary `ac lin 2` command returned only the 1 kHz point in this ngspice build and is not used to claim 100 kHz coverage.
