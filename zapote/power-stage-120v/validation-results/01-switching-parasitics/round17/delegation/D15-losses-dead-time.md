# D-15: switching losses and ZVS versus dead time on the FEM matrix (C1/C2 rerun)

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

Round 4's dead-time ZVS map (`round4/c1-zvs/`) and loss comparison
(`round4/c2-losses/`) ran on reference inductances and were explicitly
conditional on the D1 board matrix ("BLOCKED for a board-specific ZVS or
dead-time choice"). The board matrix now exists
(`round17/d2/legA-h0-best.matrix.txt`), and the dead time has become a
design lever: FINDINGS F7 proposes lengthening it (≈ 443 ns nominal, up to
≈ 498 ns with tolerance) to pass the hot off-gate screen, at the cost of
light-load ZVS (`d2/results/grid-best-longdt/`).

## Task

1. Rerun C1 (ZVS map vs dead time and load current) and C2 (switching-loss
   comparison) on the best matrix using the round-17 D2 deck
   (`d2/leg_matrix.cir`, `run_d2.py`), not round 4's reference deck. Read the
   round-4 READMEs for their method, corrections and corner definitions.
2. Dead times: 307, 348, 391, 443, 498 ns. Load: the tank current range of
   `docs/hardware/power-section-120v/POWER-SECTION.md` §2 (37 A peak at full
   power down to light load), bus 170 / 198 V; ESL 1.06 and 10 nH.
3. Report per point: ZVS (incoming VDS at turn-on, as `grid.py` defines it),
   turn-on and turn-off overlap energy (D-6's proxy definition), and body-diode
   conduction time during the dead time with its conduction loss estimate.
4. Combine into a per-switch loss estimate versus dead time over a
   representative operating cycle (state the weighting), so the owner can
   see what F7 costs against 348 ns.

## Deliverable

`round17/delegation/out-D15/README.md`: one-line answer (loss and ZVS cost
of moving from 348 ns to ≈ 443 ns nominal), the ZVS map, the loss table,
runner script and raw outputs (no vendor library).

## Acceptance

At 348 ns the decision cases reproduce `d2/results/grid-best/`; energies use
a stated, consistent definition (overlap proxy, not measured loss); every
number from committed outputs. Simulation only.
