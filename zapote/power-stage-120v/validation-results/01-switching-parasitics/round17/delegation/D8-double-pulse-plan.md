# D-8: double-pulse test plan for diode recovery and dead time (document only)

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

Two open questions cannot be closed by simulation:
- **S4 hard turn-on** fails at every dead time in the D2 grid (die VDS up to
  543 V, off-gate up to 5.1 V). D-3 (`out-D3/`) found the Infineon L1
  model's body-diode recovery is abrupt and that the datasheet cannot
  establish whether that snap-off is realistic.
- **Dead time:** the off-gate margin is between 307 and 348 ns (D2 grid v2);
  D-5 is computing the worst case at the gates, but the real value should
  be measured.

`validation-plan/BENCH-SWITCHING.md` and `validation-plan/01-switching-parasitics.md`
already describe bench switching tests; build on them, do not duplicate.

## Task

Write a runnable double-pulse test (DPT) procedure for leg A of the
native-17 board:

1. Fixture: load inductor value and construction for the S4 condition
   (−20 A at 170/198 V, matching D-3's matched-condition fixture), bus
   capacitance, how the board is powered and isolated, interlocks.
2. Measurements: VDS and VGS of both devices (probe types, bandwidth,
   ground-lead length, isolated vs differential for the high side), drain
   current (shunt R5 vs coaxial shunt vs Rogowski — pros/cons, bandwidth),
   timing deskew procedure.
3. Pulse sequences for: (a) diode reverse recovery at the S4 condition and
   at D-3's 25 °C matched test (to compare Qrr, trr, Irrm with D-3),
   (b) dead time at the gates for both edges, (c) off-gate rebound at the
   partner's turn-on.
4. Pass/fail readings mapped to the D2 criteria (VDS ≤ 520 V, off-gate
   < 3.0 V or D-6's revised criterion, |VGS| ≤ 30 V), and what each
   outcome would change in the simulation (e.g. replace the diode model).
5. Safety: energy stored, discharge, current limits, abort criteria.
6. Equipment list with minimum specs.

## Deliverable

`round17/delegation/out-D8/README.md`: the procedure, a one-page summary
table (test → condition → measurement → criterion → decision), and an
equipment list. No simulation needed; cite D-3/D-5/D-6 and datasheets.

## Acceptance

A technician with the listed equipment could run it without asking
questions; every condition traces to a round-17 case or D-3 fixture; every
criterion traces to the D2 criteria or a datasheet limit.
