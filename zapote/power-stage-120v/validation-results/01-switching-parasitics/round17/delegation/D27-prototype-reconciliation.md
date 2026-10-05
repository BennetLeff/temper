# D-27: reconcile prototype-closure with DECISIONS.md and round-17 findings

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

Two sessions worked on the power stage in parallel and were integrated in
PR #1647. The `prototype-closure/` tree (rounds 2–5: cooling, EMI,
manufacturing, protection, power, firmware, supervisor and sensor boards)
was built without `DECISIONS.md` and the round-17 validation; round 17 made
decisions in the same areas (heatsink and airflow, inlet EMI module, R5,
dead time, controller gap/allocation, bus sense, PWM safe state). Before
either line builds further, every overlap must be checked so contradictions
surface now, in the box, not at assembly.

## Task

1. **Inventory** each design assumption or choice in `prototype-closure/`
   (and `docs/hardware/power-section-120v/` where it changed in #1647) that
   overlaps a `DECISIONS.md` entry dated 2026-09-25 … 2026-10-05 or a round-17
   STATUS/FINDINGS row. Cover at least: heatsink, pad/insulator, fan and fan
   supply, airflow direction and duct (D-18 entry); inlet EMI filter and its
   placement (2026-10-05 entry, D-22); R5 part, rating and local-ambient limit;
   dead time and R9/R17; controller-inserted gap, PWM allocation, frequency
   updates, bus-sense receiver/ADC/thresholds (2026-10-03 controller entries);
   PWM failed-init safe state and PWM pull-downs (2026-10-05); precharge and
   catch hardware vs task-02/D-17 protection assumptions; firmware on STM32
   vs ESP32 vs D-20's controller requirements.
2. **Classify** each overlap: AGREES / CONTRADICTS / ONE-SIDED (a decision
   exists on one side only) / SUPERSEDES (newer evidence on one side), with
   file:line on both sides.
3. **For each CONTRADICTS**, state the consequence and the evidence each side
   rests on; propose a resolution, but do **not** edit either side.
4. **Enclosure fit (in-box):** using the STEP envelopes and enclosure/cooling
   assemblies in the repository, check whether the D-18 sink/fan/duct
   allocation and the D-22 inlet module (110 × 80 × 50 mm, outside the leg FEM
   regions and the heatsink exhaust) fit the current enclosure design;
   report collisions and clearances, labelled as nominal geometry checks.

## Deliverable

`round17/delegation/out-D27/README.md`: one-line summary (counts per class,
the contradictions that matter), the overlap table with file:line citations,
proposed resolutions, the fit check, and any scripts used. Document and
analysis only: no edits to `DECISIONS.md`, `prototype-closure/`, the board,
netlist, `elec/`, `pcb/` or firmware.

## Acceptance

Every row cites both sides; no contradiction is resolved by silently
preferring one side; the fit check states its geometry sources and limits.
