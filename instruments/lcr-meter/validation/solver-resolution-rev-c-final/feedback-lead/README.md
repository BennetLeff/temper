# Feedback-path inductance transient qualification

All **18 cases passed** strict true-DC initialization, complete finite 20 µs transient checks and ADC input headroom checks. This directory adds evidence without changing the preceding 75 accepted cases.

The nominal open-circuit test settles to a band of 1% of its peak TIA change in **35.17 ns at 20 nH**, versus **98.06 ns at 50 nH** after the rising edge. Across the paired corners, these ranges are **32.34–37.96 ns** and **74.80–129.38 ns** respectively. Nominal rising-step overshoot is **0.003% at 20 nH** and **4.960% at 50 nH**. The 10 nH cases provide an additional shorter-path comparison.

The coil's approximately 2.26–2.30 µs settling is dominated by its physical L/R response. Its small final DC response makes a conventional percentage-overshoot comparison misleading; the report instead provides absolute peak changes and an explicitly defined peak-relative settling band.

Actual ADC pins span **2.024913–2.025836 V** across all 18 cases. The macro-models retain the real FDA bias currents: roughly 1.013 mA sunk by the HIGH buffer, 2.026 mA by the LOW buffer, and 1.013–1.020 mA by the TIA. Detailed current windows include the feedback inductance, RG and DUT currents.

- [Results and measurement definitions](results.md)
- [Current and ADC windows](current-summary.md)
- [Full numeric current windows](current-windows.csv)
- [Case, corner and accepted declaration-order manifest](run-results.csv)

## Exact modeled circuit

Both DUT terminals have 100 pF to ground. The load is either 1 TΩ open circuit or a 50 µH coil in series with 0.5 Ω. RF = 100 Ω and CF = 100 pF are parallel from DUT LOW to `rf_end`; the 10/20/50 nH feedback-path inductance is in series from `rf_end` to the TIA output. No damping resistor or other value change is introduced.

The final FDA network remains 22 Ω from physical output to feedback takeoff, 1 kΩ || 100 pF feedback from that takeoff to the opposite input, and 4.32 Ω from takeoff to the existing ADC filter. The official amplifier models are unmodified, with real common-mode bias and input loading. Corners pair C104 ±5%, analog rail magnitudes ±5%, and FDA supply ±5%. Fixture and other filter capacitances remain nominal.

The test uses a 1 µA HI-to-LOW pulse with 1 ns edges and 10 µs width. Simulation duration is 20 µs, maximum step 1 ns. `reltol=1e-5`, `abstol=1e-12`, `vntol=1e-7`, Gear integration, and Newton-only initialization remain unchanged. The declaration-order helper and seed are hash-pinned from the parent validation package.

## Interpretation

All tested cases are bounded over the finite observation window. That does not establish every internal loop's stability or phase margin. The 50 nH negative control can remain bounded while failing the separate 45° loop-margin criterion. These imposed inductances are stress assumptions, not extracted PCB measurements. The proposed routing change therefore still needs its independent layout/path review.

The overall peak includes both pulse edges. Open-load rising-step overshoot excludes the separate falling-edge inverse excursion. The saved traces expose both effects. No physical-board noise, accuracy or performance claim is made.

## Reproduce

Run `./rerun.sh --check` to rebuild the Rust summarizer and verify saved outputs and pinned inputs. Run `./rerun.sh --full` to repeat all 18 simulations, selecting only strict, true-DC declaration orders, then verify them. Input hashes cover the official models, seed, helper, and source decks from the parent directory. Set `NGSPICE` if the executable is not `/opt/homebrew/bin/ngspice`. Rust edition 2021 is required.
