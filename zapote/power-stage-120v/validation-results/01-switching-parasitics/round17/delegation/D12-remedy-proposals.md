# D-12: gate-drive remedy design proposals (F6 vs F7)

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

Against D-6's provisional 1.9 V hot-junction off-gate screen, nominal
operation at the current 348 ns dead time fails (`01-switching-parasitics/STATUS.md`,
FINDINGS F5). Two candidate remedies exist, both simulated only:

- **F6 (D-6):** ≈1 Ω discharge path (split Rg with a diode) + 1 nF gate–source
  capacitor + −2 V turn-off bias; alternative 1 nF + −4 V. Passes all 32
  decision cases including S4. Needs a negative gate bias the board does not
  have (`out-D6/README.md`, "Proposals and supply feasibility").
- **F7:** lengthen the dead time (DT-pin resistor of U1/U2). The best-matrix
  grid (`d2/results/grid-best/`, `d2/results/grid-best-longdt/`) shows
  nominal S1 keeps ZVS and passes the hot screen at long dead time; it does
  **not** fix S4 hard turn-on and costs light-load ZVS.

The owner needs a like-for-like comparison of what each takes to build.

## Task

For **F6** (both the −2 V and −4 V variants) and **F7**:

1. **Circuit:** the exact schematic change, as a net/part list against
   `frozen/default.net` (which parts added, which removed, which nets). For F6,
   choose the negative-bias implementation from TI SLUSE89C §8 (Zener
   gate network on the existing bootstrap/15 V supplies vs separate isolated
   negative supplies; cite pages and figures) and show it fits the
   UCC21550's 25 V output-supply limit, bootstrap startup and duty-cycle
   limits. For F7, the DT resistor value(s) from D-1's equation
   (`out-D1/`) that put the **minimum** dead time ≥ 391 ns with D-1's
   tolerance stack, and the resulting nominal and maximum.
2. **Parts:** orderable part numbers (Zener, diode, resistors, capacitors,
   any supply) with the ratings that matter (voltage, power, tolerance,
   temperature coefficient, Zener tolerance and dynamic resistance, diode
   recovery), each from a cited datasheet page; footprint/package.
3. **BOM delta and cost** at the quantities in `frozen/default.csv`
   (unit price source and date; label as an estimate).
4. **Layout impact:** which changes fall inside a leg's FEM region and so
   need the FEM rerun. Use `round17/scripts/leg_region_diff.py` logic:
   a value-only change in the same footprint changes no copper (no rerun);
   new parts near the gate loop do. Estimate added gate-loop copper.
5. **Risks:** what each remedy changes elsewhere: gate charge and driver
   dissipation, startup/UVLO behaviour with negative bias, light-load loss
   with long dead time (cite D-15 if available), S4 (F7 does not fix it).

## Deliverable

`round17/delegation/out-D12/README.md`: a one-paragraph recommendation (which
remedy, why, what the owner must decide), a comparison table (circuit change,
parts, BOM delta, rerun needed, residual risks) and committed scripts for any
calculation (`dt_resistor.py`, `bias_network.py`) with outputs. **Proposals
only: do not edit the board, netlist, `elec/`, `pcb/` or firmware.**

## Acceptance

Every rating and price traces to a cited datasheet page or distributor page
(with date); calculations are reproducible; the comparison states which
claims are simulation-only.
