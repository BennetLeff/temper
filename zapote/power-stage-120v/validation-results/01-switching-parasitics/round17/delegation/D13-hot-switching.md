# D-13: switching at hot junction (simulation)

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

Every D2 transient so far ran at ngspice's default 27 °C. The off-gate
criterion was then corrected for hot junction separately (D-6: model VGS(th)
falls ≈ 1.07 V from 25 to 150 °C → provisional 1.9 V screen). That mixes a
cold transient with a hot threshold. The Infineon L1 model takes junction
temperature from the simulator temperature (`E1 Tj w VALUE={TEMP}` in the
`IPW65R018CFD7_L1` subcircuit), so the transient itself can run hot:
threshold, Rds(on), capacitances and body-diode recovery all change with Tj.

## Task

1. Confirm how the vendor model uses `TEMP` (read the subcircuit; cite
   lines, do not copy the licensed file) and how to set it in the D2 run
   (`.temp` / `.options temp=` through `common/options.inc` or a deck copy).
2. Run the decision cases (S1 170/198/280 V and S2 280 V/71 A at 307 / 348 /
   443 ns; S4 198 V at 348 ns; both directions; ESL 1.06 and 10 nH) on
   `round17/d2/legA-h0-best.matrix.txt` at Tj = 27, 100 and 150 °C, for:
   the baseline deck; D-6's preferred remedy (copy its variant deck from
   `out-D6/decks/`); and the F7 long-dead-time case (443 ns nominal).
3. Judge off-gate **against the model's own threshold at the same Tj**
   (measure it as D-6 did with `threshold.cir` at each temperature) minus
   the 0.5 V allowance, and also against 3.0 V and 1.9 V for comparison.
   Report die VDS, ZVS, and the overlap-energy proxy D-6 used.
4. Report convergence: rerun at half the max timestep for a subset; list
   any aborts as indeterminate.

## Deliverable

`round17/delegation/out-D13/README.md`: one-line answer (does the hot
transient change the verdicts, and does the 1.9 V screen look conservative,
right or optimistic against the hot-threshold judgement), tables per Tj and
remedy, runner script and raw outputs (no vendor library).

## Acceptance

Baseline at 27 °C reproduces `d2/results/grid-best/` for the same cases;
model-temperature mechanism cited by line; every number from committed
outputs; aborts reported, never counted as passes. Simulation only.
