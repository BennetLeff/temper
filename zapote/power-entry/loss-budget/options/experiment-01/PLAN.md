# Experiment 01: three MOSFETs with the existing controller drive

Question: does IPW65R045C7 or IPW65R041CFD7 merit the next electrical-design
iteration when compared with STW65N65DM2AG using the maintained Rust switching
model and explicitly uncertain driver/device inputs?

This is a reproducible component sensitivity experiment, not a new physical
solver, a part selection, or a change to the circuit/PCB. Reuse
`zapote_erc::pfc_switching::simulate` and `pfc_losses::moments`. The production
loss adapter remains incumbent-specific and unchanged. Experiment results
must always retain physical applicability and qualification as INDETERMINATE.

## Comparison conditions

- Compare at **400 V**, explicitly separate from the authored approximately
  389.615 V bus: both replacement datasheets publish numeric Eoss at 400 V.
  This avoids silently treating their 400 V energy as a 389.615 V value. Use
  the source-derived switching frequency and 180 µH inductor.
- Lines 108/120/132 Vrms at a fixed 15 A input RMS ceiling are different-power
  sensitivities. Report ideal model input power; do not claim equal DC output,
  1,800 W delivered, efficiency or a whole-board heat total.
- Common input grid: gate bias 9/10/11 V; cold maximum Rds multiplied by 1/2
  (the second is an assumed multiplier, **not a temperature claim**); explicit
  current-transfer charge 5/10/20 nC; additional lumped driver resistance
  0/5/10 Ω. Existing external gate resistor stays 10 Ω. Clearly label the
  simulator's external-resistance argument as the sum of the gate resistor and
  assumed driver resistance, not a changed authored resistor. It is a symmetric
  driver approximation, not measured source/sink I–V.
- Device-specific charge/applicability sensitivity: Qgd multiplier 0.5/1/1.5
  and plateau offset -0.5/0/+0.5 V. These ranges are deliberately hypothetical,
  not tolerance bounds. Each device may take different multipliers/offsets
  when comparing uncertainty envelopes; matched assumptions alone cannot prove
  robust ranking. Qg remains the documented typical point, with its conditions.
- Keep source/sink peak limits 1.5/2 A, loop-inductance assumption 10 nH and
  timestep 0.25 ns. Retain event currents and duty-weighted RMS separately.
  Do not interpret event-average overshoot as the line-cycle worst case.

## Device inputs and evidence

Use the retained exact PDFs, validate PDF header/hash and record revision,
page and test conditions. Source values to verify before running:

| Device | Rds max at 25°C | Qg typical | Qgd typical | Plateau point | Internal Rg | Eoss at 400 V |
| --- | --- | --- | --- | --- | --- | --- |
| STW65N65DM2AG | 50 mΩ | 120 nC | 58 nC | 6.2 V assumed | 3.3 Ω | 17.5 µJ digitized, ±0.6 µJ extraction uncertainty |
| IPW65R045C7 | 45 mΩ | 93 nC | 30 nC | 5.4 V typical | 0.85 Ω | 11.7 µJ typical |
| IPW65R041CFD7 | 41 mΩ | 102 nC | 31 nC | 5.7 V typical | 3.8 Ω | 14 µJ typical |

The ST charge point is 520 V/60 A/10 V; the Infineon charge points are
400 V/about 25 A/10 V. That mismatch remains a physical-applicability gap;
the hypothetical multipliers do not repair or bound it. Keep unmodeled
commutation, driver behavior, temperature feedback and other board losses named.
Preserve overlap, Eoss, conduction and gate-network terms separately.

## Deliverables and acceptance

1. Small Rust experiment module and CLI under zapote-harness; no copied switching
   physics and no changes to the production model or authored PCB/BOM.
2. Deterministic structured raw results for all 4,374 cases (1,458/device), exact
   inputs and source digests. Numerical checks include finite values and
   disjoint accounting; analytical reference remains separately scoped.
3. Nominal comparison at 120 V, gate 10 V, Rds multiplier 1, transfer 10 nC,
   additional driver resistance 0, Qgd multiplier 1 and plateau offset 0.
   Report these as conditional partial MOSFET + gate-network watts, not total
   board loss. Show the effect of driver resistance and independent device
   uncertainty; identify overlapping rankings honestly.
4. Tests reject altered source bytes/identity, NaN and duplicate or incomplete
   scenario grids. An independent arithmetic check reconstructs nominal branch
   moments/triangle energies from retained inputs without calling simulate.
5. Coordinator reviews actual files, verifies datasheet inputs and independent
   arithmetic, runs focused tests and retains commands/source hashes. Write a
   concise results/next-decision report. No CAD change follows automatically.

Execution: Luna owns the new Rust module/CLI and new tests; coordinator owns
this contract, independent source/arithmetic audit, integration and result prose.
Use an isolated worktree. Release-only builds share the existing Zapote target;
disk space is limited. Do not run the large thermal replay from a sparse tree.
