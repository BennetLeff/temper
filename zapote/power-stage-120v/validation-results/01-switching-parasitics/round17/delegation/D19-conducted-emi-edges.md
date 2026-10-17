# D-19: conducted-EMI pre-check with the real switching edges (task 07)

**Read [README.md](README.md) first (ground rules, board facts).**
Power-stage task 07 follow-up; indexed here with the other delegated work.

## Why it matters

Task 07 round 3 (`validation-results/07-conducted-emi/round3/`) built the A7
input-filter deck and fixtures but is **PARTIAL / BLOCKED for B5/C1**: "Task
01/B1 must supply qualified 35/60 kHz leg edge waveforms or verified rise/fall
times across relevant current and line conditions". Round 17 now has
switching transients on the extracted board matrix
(`round17/d2/leg_matrix.cir`, `run_d2.py`, `grid.py`;
`d2/legA-h0-best.matrix.txt`), with native-18's 443 ns dead time
(`DECISIONS.md` 2026-10-03) and qualified capacitor ESL (D-7).

## Task

1. **Edges:** from the round-17 deck on the best matrix at 443 ns, extract
   switch-node (sw) and bus-current waveforms for the operating points task
   07 needs (35 and 60 kHz; full and light load; 170/198 V bus; both
   directions; ESL 1.06 and 10 nH): rise/fall times, dv/dt, ringing frequency
   and damping, and the ZVS/non-ZVS split (light load does not soft-switch,
   D-15). Use `run_ngspice.run(..., raw=True)` for waveforms; D-14's
   `.options itl4=100000` may be used (state it).
2. **Noise source:** build the differential- and common-mode source for the
   A7 deck from those edges (periodic switching at the tank frequency,
   correct duty and both legs), replacing round 3's assumed spectrum; keep
   round 3's filter, LISN and coil-PE models unchanged unless a round-3
   limitation requires a change (then show both).
3. **Margin:** the conducted spectrum 150 kHz–30 MHz against the limit task 07
   uses, with the per-scenario worst line; sensitivities that round 3 found
   dominant (L1 tolerance, coil-PE capacitance) and edge sensitivity (ESL,
   ZVS vs hard switching).
4. **Findings:** whether the input filter needs a change, and what.

## Deliverable

`round17/delegation/out-D19/README.md`: one-line answer (margin and worst
case, filter change needed or not), the edge table, spectra and margin table,
runner and raw outputs (no vendor library). Model-based pre-check only: no
compliance claim; no board, netlist, `elec/`, `pcb/` or firmware edits.

## Acceptance

The round-3 fixtures reproduce before the source is replaced; the switching
baseline reproduces `d2/results/grid-best-longdt/` for a matching case; FFT
windowing/resolution and periodic steady state are justified; aborts are
reported, never counted.
