# Original CT deck stall diagnosis

The three round-two stalled parameter sets were replayed with ngspice 45.2,
the kit's unchanged `common/options.inc`, and a 15 s per-case limit. Each
stage changed only one feature from the original deck. The full transcripts
and deck hashes are in `outputs/stall_logs/` and
`outputs/stall_diagnosis.json`.

| Case (FREQ, I0, SLOPE, VOS, TPD) | Original 5 ns | Smooth cap only | 2.5 ns max step only | tanh width 1→5 mV only |
| --- | --- | --- | --- | --- |
| 33 kHz, 37 A, 10 MA/s, −4 mV, 45 ns | Timeout, last time 4.311 µs | Timeout, 4.307 µs | **Complete** | Complete |
| 33 kHz, 10 A, 1 MA/s, 0 mV, 55 ns | Timeout, 65.00 µs | Timeout, 65.02 µs | **Complete** | Complete |
| 39 kHz, 37 A, 1 MA/s, −4 mV, 45 ns | Timeout, 168.59 µs | Complete | **Complete** | Timeout, 143.01 µs |

The source cap knees are 11.3, 140 and 113 µs respectively. The first two
stalls precede their cap knees, so the source kink cannot be their cause.
The smooth-cap formula in `diagnose_stalls.py` removes the derivative kink
without changing the early ramp materially; it helped only the third case.
The original deck already declared a 5 ns maximum timestep; halving it to
2.5 ns completes **all three** without relaxing `reltol`, `abstol`, or
`vntol`. Widening the tanh is not a universal fix and was not adopted.
At VCC/2, the ideal tanh decision has the same crossing for either width,
but changing width still changes numerical behavior near the transition.

The completed original-deck `.meas` values at 2.5 ns match the independently
solved analog/feed-forward model in `outputs/ct_sweep.json`. Across the three
cases, maximum relative difference of `t_ip_trip`, `t_pos_trip`, and `t_or`
is **0.00167%** (the first case's `t_or`); all are below the required 1%.
The kit smoke test passed, including its CT reference. The 108-case grid
was rerun through the proven feed-forward decomposition (18 independent
analog transient solves × 3 offsets × 2 delays) because that model evaluates
the same analog waveform without ngspice's delay-line stiffness. Its 12
retained round-two timestamps differ by at most 0.0922 ns / 0.000378%; the
third prior case, the kit's 35 kHz smoke reference, differs by at most
0.00613%. `outputs/reference_comparisons.json` records the exact values.
Five-to-2.5-ns waveform convergence changed a crossing by at most
0.00721 ns (`outputs/timestep.json`).

This diagnosis validates the **kit's ideal behavioral comparator plus pure
delay**, not the TLV3201's physical small-overdrive response. The latter is
separately discussed in `README.md` and `overdrive_bound.csv`.
