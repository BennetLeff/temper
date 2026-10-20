# Independent final local-C104 5 kΩ replay

This parent-run check independently reruns the final complete coupled analog chain with matched 5 kΩ DUT/RG/RF, no additional fixture capacitance, **100 pF directly across the TIA**, **5 nH in its local capacitor path**, and **100 nH in the selected RF/header path**. Both final FDA networks retain their actual DC loading. Vendor models are unmodified.

Only output filenames differ from Astra’s retained source deck; `receipt.json` records both hashes. The reducer independently inverts the two-current-injection Z matrix, subtracts the test bridge admittance, then derives the bilateral return ratio. It does not call Astra’s determinant-shortcut reducer.

The result is **58.659088° at 58.57438 MHz**, with minimum sampled |1+T| **0.710550970** across **1081 frequencies**. This is one representative methodological cross-check, not another exhaustive grid. The main analog report supplies the full load/tolerance envelope and independent internal controlled-source checks.

The run requires the strict true DC point: five OPA MID helpers near 0 V, both FDA helpers near 2.5 V, negligible source AC-coupling DC, finite and unsaturated outputs, complete AC arrays and no aborted or transient-fallback analysis. Expected datasets are deleted before every run. No model node or output is forced to a target voltage. KLU plus the reproducible seed resolves numerical conditioning; `optran` disables transient fallback.

Run `sh run.sh` with Rust and KLU-enabled ngspice 45.2. The seed is retained at `../solver-resolution-rev-c-final/final-seed.inc`. This supersedes the older range-specific 10 pF 5 kΩ replay in `../independent-full-chain-rev-c/` for the current circuit. Neither run measures physical hardware.
