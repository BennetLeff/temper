# D-22: conducted EMI — converge the periodic source and size the additional DM filter stage

**Read [README.md](README.md) first (ground rules, board facts).**
Power-stage task 07 follow-up.

## Why it matters

D-19 (`out-D19/README.md`) found a **conditional −24.21 dB** average-detector
headroom at 210 kHz (170 V, 35 kHz, R = 2 Ω, ESL 1.06 nH, combined filter
sensitivity) and recommended reserving additional damped DM filtering. It is
**PARTIAL**: 15 of 16 periodic cases aborted and one did not settle; only two
operating points (170 V / 1.06 nH / R = 2 Ω at 35 and 60 kHz) produced
spectra; no 198 V, 10 nH or light-load periodic source is qualified; some
high-frequency lines move by up to 6.72 dB with the timestep. The owner is
laying out the enclosure now, so the size of any extra filter stage matters
before the layout freezes.

## Task

1. **Converge the periodic source.** Diagnose the aborts and the unsettled
   run in `out-D19/periodic-sweep.cir` the way D-14 did for the single-edge
   deck (the D2 deck now carries `.options itl4=100000`; D-19 already used it).
   Change numerics only, never physics; show that converged results do not
   move. Cover 170 / 198 V, 35 / 60 kHz, R = 2 Ω and the light-load diagnostic,
   ESL 1.06 and 10 nH. Establish timestep convergence for the reported lines
   (D-19's 6.72 dB movement must be resolved or bounded).
2. **Margin over the envelope.** With D-19's corrected receiver reference
   (`v(lisn)-v(pe)`) and round 3's filter/LISN/coil-PE models, report QP and
   AV margin 150 kHz–30 MHz for every converged case against the limit task
   07 uses (cite it). Separate DM and CM contributions.
3. **Size the extra stage.** Propose a damped DM stage (and CM change only if
   the CM result needs it) that gives **≥ 6 dB margin** at every line of every
   converged case: topology, X capacitor, DM inductor or choke (current
   rating at 15 A RMS input and 120/140 V line, saturation, winding loss),
   damping network, with orderable part numbers and cited datasheets; its
   volume and footprint; its dissipation; and the X-capacitor safety class
   and bleed requirement.
4. **Placement implication.** Where the stage goes (mains entry, left side:
   DECISIONS.md D6), and confirm it stays outside both legs' FEM regions
   (`round17/scripts/leg_region_diff.py` regions; leg box + 20 mm), so no
   FEM rerun is needed — or say which leg region it would touch.

## Deliverable

`round17/delegation/out-D22/README.md`: one-line answer (margin over the
envelope; the proposed stage, its size and cost), convergence evidence, the
margin tables, the stage design with parts, runner and raw outputs (no
vendor library). Proposals and simulation only: no board, netlist, `elec/`,
`pcb/` or firmware edits. Model-based pre-check, not a compliance claim.

## Acceptance

Every reported case converged (aborts listed as indeterminate, never as
margin); D-19's two settled cases reproduce before any numerics change;
every component rating cites a datasheet page; the ≥ 6 dB claim is shown per
case and line, with the sensitivities D-19 found dominant.
