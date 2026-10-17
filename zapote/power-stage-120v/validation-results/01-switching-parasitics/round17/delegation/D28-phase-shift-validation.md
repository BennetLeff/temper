# D-28: validate fixed-frequency phase-shift operation (the gated low-power mode)

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

`DECISIONS.md` 2026-10-05 (C1) approves only legs 180° apart; phase shift is
gated behind this brief. POWER-SECTION.md (§ control, around lines 111–113)
intends fixed-frequency phase shift below the ≈ 150 W frequency-control floor
and warns that the lagging leg loses ZVS at deep phase shift. The prototype
firmware (`prototype-closure/round4/firmware/README.md` 56–73,
`round5/firmware/`) already implements A/B separation from zero to half a
period. Round 17's grid tests each leg's commutation at given currents; under
phase shift the **leading** and **lagging** legs commutate different currents.

## Task

1. **Commutation currents vs phase:** from the series tank model used in
   round 17 / D-19 / D-22 (70 µH, 0.54 µF, the D-19 periodic two-leg deck, or
   task 05's envelope), compute each leg's switch current at its transitions as a
   function of phase separation (0 … 180°), frequency (the fixed frequency the
   prototype uses; cite it) and bus (170/198 V), for the low-power operating
   range. State the separation below which the lagging leg's current is too low
   (or of the wrong sign) for ZVS within the 443 ns dead time.
2. **Switching verdicts:** run the two-leg periodic deck (D-22's converged
   setup, `.options itl4=100000`, native-19 best matrix
   `d2/legA-h0-best-n19.matrix.txt` for both legs until leg B's own matrix
   exists, stated) at a phase sweep, and evaluate per leg: ZVS, off-gate peak
   (3.0 V and the 1.9 V hot screen), die VDS, and the overlap-energy proxy.
3. **CT phase inhibit:** propose the numeric inhibit (CT_ZC timing relative to
   the switch transitions) that keeps both legs inductive, consistent with the
   2026-10-03 frequency-update policy.
4. **Envelope:** the approved phase range (if any) per bus/power, the loss
   cost, and what remains bench-only.

## Deliverable

`round17/delegation/out-D28/README.md` (one-line answer: the phase range that
passes, or that none does), tables per phase, runner and raw outputs (no
licensed models). Simulation and proposal only: no board, netlist, `elec/`,
`pcb/` or firmware edits.

## Acceptance

The 180° point reproduces `d2/results/native19-carryover` (or D-22's periodic
cases) for matching conditions; every periodic case meets D-22's convergence
criteria or is indeterminate; the inhibit is stated with its basis.
