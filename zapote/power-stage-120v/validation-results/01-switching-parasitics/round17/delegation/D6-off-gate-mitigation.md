# D-6: gate-drive remedies for the off-gate failures (simulation only)

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

Every failing case in the D2 grid v2 (`round17/d2/README.md`, "Grid v2")
fails the off-gate criterion: the turned-off MOSFET's gate exceeds 3.0 V
around its partner's turn-on. At 307 ns dead time all nominal S1 cases
fail (3.45–4.01 V); S4 (hard turn-on, −20 A) fails at every dead time
(3.25–5.14 V, die VDS up to 543 V). We want to know which standard remedy
buys the most margin, before anyone proposes a board change.

## Task

Use the existing deck and runner unchanged except for the remedy under
test: `round17/d2/leg_matrix.cir`, `run_d2.py`, matrix
`round17/d2/legA-h0-lin12-m20corr.matrix.txt` (crop-corrected). Copy the
deck into your output folder for each variant; do not edit the originals.

1. **Criterion check first:** from the IPW65R018CFD7 datasheet (cite rev,
   page), get VGS(th) min at 25 °C and the hottest specified junction
   temperature (or its temperature coefficient). Is "3.0 V = 3.5 V min − 0.5 V"
   conservative or optimistic at hot junction? Recommend a criterion with
   its basis.
2. **Remedies** (one at a time, then the best combination):
   a. lower turn-off gate resistance (split Rg_on / Rg_off with a diode;
      try 1, 2 Ω off with 3.9 Ω on);
   b. external gate–source capacitor (1, 2.2, 4.7 nF) — note its effect on
      switching speed and on ZVS at 348 ns;
   c. negative turn-off bias (−2, −4 V), only if UCC21550 supply
      arrangement permits it (cite the datasheet; say if it needs a
      second supply);
   d. active Miller clamp, only if the UCC21550 variant on the board has
      one (cite; if not, say so and skip).
3. For each: off-gate peak and die VDS for the decision cases — S1 170/198/280 V
   at 307 and 348 ns, S2 280 V/71 A at 348 ns, S4 198 V at 348 ns —
   ESL 10 nH. Report also switching loss proxies (VDS·ID overlap energy per
   transition) so speed costs are visible.

## Deliverable

`round17/delegation/out-D6/README.md`: one-line answer (which remedy, how
much margin, at what cost), the criterion recommendation, a table per
remedy, committed variant decks + a runner script + raw outputs (not the
vendor model).

## Acceptance

Same matrix and deck as the grid, so the baseline row reproduces the grid
v2 numbers for those cases (check it). Any remedy that changes a part is a
proposal only — do not edit board or netlist files. Simulation results are
model results, not hardware qualification; say so.
