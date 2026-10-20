# Historical range-specific 10 pF 5 kΩ replay

**Superseded for the current circuit:** see [local-C104 replay](../independent-full-chain-fixed-cf-rev-c/README.md). This evidence describes the earlier 10 pF range-specific compensation, not the fitted fixed 100 pF capacitor.

The parent reviewer independently reran Astra's final matched-5 kΩ, no-added-fixture-capacitance TIA test. This retains the complete coupled chain, all five OPA amplifier stages, both final 22 Ω / 100 pF / 4.32 Ω FDA networks and their actual DC loading. All vendor model libraries are unmodified. The selected declaration order is preserved exactly; only the output filenames change. Numerical conditioning does not change the network connectivity or values.

`reduce.rs` independently constructs and inverts the measured Z matrix, subtracts the 100 Ω test bridge admittance, then calculates `(Y12+Y21)/(Y11+Y22)`. It does not call Astra's determinant-shortcut implementation. The result is **66.929462° at 41.32951 MHz**, with minimum sampled |1+T| **0.785303780** over 1081 frequencies. The independent internal controlled-source cut gives 66.92952° at 41.32956 MHz, agreeing within 0.001°.

The reducer checks the true DC point: all five symmetric-supply OPA MID helpers near 0 V, both FDA MID helpers near 2.5 V, source AC-coupling DC near zero, physical FDA output levels inside their rails, finite values and complete frequency arrays. Failed analyses, transient-OP fallbacks and stale data are rejected; expected datasets are removed before each run. `optran` disables transient fallback. No output or node is forced to the desired answer.

Run `sh run.sh` with Rust and KLU-enabled ngspice 45.2. The retained seed is `../solver-resolution-rev-c-final/final-seed.inc`. This is a representative methodological cross-check, not a second exhaustive qualification grid. See the main Rev C report for the DUT/tolerance envelope, multiple-crossing limitations and required physical measurements.
