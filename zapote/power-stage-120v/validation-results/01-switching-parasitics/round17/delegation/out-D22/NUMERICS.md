# Numerical qualification plan

Freeze the D-19 periodic circuit, model, matrix, sources, loads, temperature and initial operating-point calculation. Reproduce its two settled operating points with its runner before testing altered numerics. No added shunt resistance/capacitance, series resistance, model edits, ramped supply or imposed initial conditions are permitted in the source work.

The reported abort node is a convergence location, not a diagnosis of a faulty component. Test a bounded screen of iteration allowance, error tolerance and maximum timestep on short startup/commutation windows. Select a candidate only after checking the previously settled operating points. Preserve every attempted setting, timeout and abort. A candidate must then survive the complete 16-case envelope and longer settling windows.

Qualification requires both a complete transient endpoint and settled final cycles. Compare maximum adaptive steps at successive refinement tiers, retaining complex phase. Use a 524288-point periodic interpolation grid, independently checked against 131072 points. For significant receiver lines (within 40 dB of the AV limit), the target is 0.2 dB between the finest tiers; below that floor, report absolute complex-voltage differences relative to the floor. The implementation also requires that weak-line complex difference to be at most `10**(0.2/20)-1` (about 0.0233) times the floor; this is a deliberately stricter acceptance check, not an error bound. This avoids treating a cancellation zero as a meaningful large relative error. Retain all lines, including those outside the target. Passing a finite refinement comparison is numerical evidence, not a mathematical error bound.

The proposed filter must have at least 6 dB model margin on every regulated line in every qualified source/sensitivity case, with explicit numerical reserve and unresolved physical-model qualifications. Never convert an aborted, unsettled or materially step-sensitive source into a passing margin.

## Targeted follow-up after the initial refinement campaign

The 170 V / 35 kHz / R=2 Ω / ESL=1.06 nH anchor at 0.0625 ns passes the significant-line timestep target (0.105973 dB), but its weak-line cycle difference is 0.048611 times the floor, nearly the same as at 0.125 ns. This is consistent with residual startup settling and motivates a longer window; it is not proof of its cause. The four full-load 35 kHz points are therefore repeated for 32 cycles. `targeted-refinement.json` declares both comparison tiers before those runs start. Five 0.125 ns aborts are retained; one of those points is covered by the longer 35 kHz pair, and the other four are retried at 0.1 ns against their complete 0.25 ns references. The 170 V / 35 kHz / R=2 Ω / 10 nH longer pair uses 0.1 and 0.0625 ns because its 0.125 ns run aborted.

The source circuit, operating point, gate waveforms and model remain fixed. Changing the stop/capture window changes the numerical observation, not the circuit. Reference labels are explicit where a retry uses a different refinement sequence. Comparisons require identical physical parameters, cycle count, deck, common options, simulator and vendor hashes; only maximum timestep may differ. Acceptance thresholds are unchanged. At equal timestep the summary selects the longest complete capture.

The 170 V / 35 kHz / 2 ohm / 10 nH, 32-cycle 0.0625 ns retry aborted at the first commutation (2 us). `additional-refinement.json` retains the declared 0.1 ns reference and retries at 0.05 ns; all physical parameters and relative gate timing remain unchanged. The failed attempt remains indeterminate.

The 198 V / 60 kHz / 2 ohm / 10 nH point changes by 0.2119 dB on significant lines from 0.25 to 0.125 ns, narrowly missing the target. `fine-refinement.json` declares a 0.0625 ns comparison against its complete 0.125 ns run with the same 48-cycle window.

The 198 V / 35 kHz / 2 ohm / 1.06 nH, 32-cycle 0.125 ns run aborted at 873.872 us. `recovery-refinement.json` retries 0.1 ns against the completed 0.25 ns, 32-cycle reference. The full observation window is retained; the failed later commutation is not removed by shortening the run.

The completed 198 V / 35 kHz / 2 ohm / 10 nH, 32-cycle pair passes significant-line refinement (0.0942923 dB) but its weak-line difference remains 0.0299309 times the floor. `weak-refinement.json` declares a 0.0625 ns run against its 0.125 ns reference; no acceptance threshold is relaxed.

The 198 V / 60 kHz / 100 ohm / 1.06 nH point also aborted at 0.1 ns, at 60.3333 us. `retry-refinement.json` declares 0.08 ns against its complete 0.25 ns reference, retaining the same 48-cycle window. Both previous finer-step failures remain indeterminate.

The 198 V / 35 kHz / 2 ohm / 1.06 nH 0.1 ns recovery also aborted, at 273.429 us. `last-refinement.json` makes one further 32-cycle attempt at 0.08 ns against the complete 0.25 ns reference. If this also fails, this operating point remains unqualified; the observation window and acceptance criteria are not shortened or relaxed.

The 170 V / 60 kHz / 2 ohm / 10 nH 0.1 ns run completes, but its significant-line difference from 0.25 ns is 0.202466 dB and the weak-line check also fails. `closing-refinement.json` declares a 0.0625 ns run against the complete 0.1 ns reference over the same 48 cycles. The 0.2 dB target is applied without rounding.

The 170 V / 60 kHz / 2 ohm / 10 nH 0.0625 ns run aborted during startup. `terminal-refinement.json` tests 0.08 ns against the complete 0.1 ns capture over the same 48 cycles. This is the final additional attempt for this point; failure remains unqualified.
