# D-24: S4 hard turn-on vs body-diode recovery — can simulation decide it?

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

S4 (hard turn-on at −20 A) fails at every dead time and temperature in the
D2 grid: die VDS up to 543 V, off-gate up to 5.2 V (FINDINGS F2). D-3
(`out-D3/`) found the Infineon L1 model's body-diode recovery abrupt and
could not establish from the datasheet whether that snap-off is real. The
fix (F6, negative bias, ≈ $115–119 and a layout change) is held in reserve
pending a bench measurement. The owner wants to decide **in simulation**
wherever possible.

## Task

1. **Recovery parameter space:** identify in the IPW65R018CFD7_L1 model
   (cite subcircuit lines; do not copy the licensed file) which parameters set
   reverse recovery (stored charge, transit time, softness). Using D-3's
   matched-condition fixture, map how Qrr, trr, Irrm and the softness factor
   move with them.
2. **Plausible range:** bound that space with evidence: the datasheet's
   Qrr/trr/Irrm (typ/max, conditions), CFD7-family application notes,
   Infineon's published double-pulse data for CFD7 parts, and any
   peer-reviewed or vendor measurement of CFD7 recovery softness. Each bound
   cites its source; say where only typical values exist.
3. **Sweep:** run S4 (198 and 280 V, both directions, 443 ns, ESL 1.06 and
   10 nH, Tj 27 and 150 °C) on `d2/legA-h0-best.matrix.txt` across that range.
   Find the boundary where S4 passes (die VDS ≤ 520 V and off-gate < 1.9 V hot
   screen).
4. **Decision value:** state plainly one of: (a) S4 fails for every plausible
   recovery → F6 (or another remedy) is needed regardless of the bench;
   (b) S4 passes across the plausible range → the model's snap-off is outside
   it and no remedy is needed; (c) the answer depends on where the device
   sits → name the one measurement (and its threshold) that decides it.

## Deliverable

`round17/delegation/out-D24/README.md` (one-line answer first: a, b or c),
the parameter map, the plausible-range table with sources, the S4 sweep
table, runner and raw outputs (no licensed model). Simulation only.

## Acceptance

The unmodified model reproduces the grid's S4 rows; every bound is cited;
parameter edits are applied to a local copy (never committed) and documented
as diffs of parameter values; aborts are indeterminate.
