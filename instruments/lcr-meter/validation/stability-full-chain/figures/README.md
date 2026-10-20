# Five-kilohm transient comparison — final local compensation

`5k-before-after.png`, `.svg` and `.pdf` render the validated full-chain `pulse5k_cf0.dat` and `pulse5k_cf100_local.dat` datasets. Both use matched 5 kΩ source/feedback resistors, a 5 kΩ DUT, and a 1 µA current pulse from DUT_HI to DUT_LO beginning at 1 µs with a 1 ns rising edge. Both final FDA networks remain present: 22 Ω before the feedback takeoff, 1 kΩ || 100 pF, then 4.32 Ω to the ADC filters. Both include 100 nH in the RF/header branch. The compensated case has 100 pF directly across the TIA with 5 nH in that local capacitor path. No added fixture capacitance is included here.

The vertical axis is the negative TIA output change from the pre-edge value at approximately 0.9 µs, in mV. The final increment is nominally 2.5 mV. The inset resolves the fast ringing that the full 5.2 µs view compresses. The Rust transient audit supplies numerical metrics; this Python renderer only formats saved data.

| Case | Rising-edge overshoot | Last outside 1% band after edge |
|---|---:|---:|
| No feedback capacitor | 94.560662% | 292.907 ns |
| Fixed local 100 pF | 0.000087% | 2300.503 ns |

The stronger compensation slows the step response while suppressing ringing. These figures describe this small-signal matched-load test, not an accuracy specification or every DUT. The main report covers all ranges, other loads, tolerance/inductance cases and the high-range bandwidth tradeoff. Hardware waveform qualification remains required.

Source datasets: `../../solver-resolution-fixed-local/uncompensated5k_tran.dat` and `matched5k_tran.dat`; validated for true DC, finite 20 µs arrays, output headroom and KCL. Saved plot-source hashes:

- `pulse5k_cf0.dat`: `277c1ee2d8d31d5a434998007e8e9fe1ab1a89a8d146cdf7bd6bac0d8c46f8a8`
- `pulse5k_cf100_local.dat`: `8228d8dcf5e7312cf81ddfaa2fc943a5cf321fb120b1b1d912f0735375f07695`

The older `pulse5k_cf10.dat` is retained historical data and is **not** plotted or used to qualify the final circuit.

Reproduce with Python 3.12 and Matplotlib 3.10.8: `MPLCONFIGDIR=/tmp/temper-lcr-mpl python3 plot_transient.py`.
