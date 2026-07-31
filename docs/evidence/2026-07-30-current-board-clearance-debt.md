# Current-board clearance debt after handoff-actionables reconciliation

<!-- provenance: commit=ebf41c198ccf8c02c6e74eca5fd6e55abdb4236e dirty=false -->

**Date:** 2026-07-30
**Board:** `pcb/temper.kicad_pcb` after the source/netlist reconciliation that removed the unused mains-ZCD U3 circuit.
**Measurement:** `tests/requirements/safety/_real_board_fixture.py` and `verify_iec60335_compliance`, using the current enforced 12.6mm reinforced margin.

## Current finding

The synchronized board has 162 PCB components and 162 netlist components. The full safety fixture matches 152 components, classifies 152, and reports:

- **115 REQ-SAFE-01 violations across 78 pairs**;
- **10 unclassified components:** `C10`, `R28`, `R35`, `R37`, `R40`, `R47`, `R52`, `R59`, `R64`, `R67`;
- **six intrinsic same-footprint blocker references:** `C6`, `K1`, `K2`, `K3`, `T1`, and `U6`;
- **six unclassified components inside the 12.6mm fail-closed proximity margin:** `R37`, `R28`, `R35`, `R40`, `C10`, and `R59`.

The remaining inter-component records are distributed across the routed board, with the largest groups involving `R30`, `C17`, `C22`, `R26`, and the `F1`/control-area interfaces. This is a board-layout and routing problem, not evidence that the validator should be weakened.

## Candidate-placement falsifier

A full-domain CP-SAT re-solve was reproduced in read-only scratch space using the current model. It cleared the movable clearance pairs, but `write_placements_to_pcb` changes only footprint positions/rotations and preserves the existing routed copper. The candidate moved nearly every component and produced a reproducible routed-board regression: `shorting_items` and `unconnected_items` increased relative to the baseline. It was therefore not written to the tracked board.

The earlier copper-aware re-solve evidence records the same failure mode and measurements in detail:
[`2026-07-30-copper-aware-domain-resolve.md`](2026-07-30-copper-aware-domain-resolve.md).

## Required next implementation

The next safe change must add either a minimum-displacement objective/repair mode to the placement model or a placement-and-routing loop that evaluates copper after each candidate. It must preserve the full domain constraint set, keep the validator fail-closed for unclassified parts, and run the board DRC ceiling remeasurement in the same change. Same-footprint findings require footprint/source dispositions and cannot be solved by moving component origins.

No candidate from this investigation is a shippable board change.

## Minimum-displacement prototype

The CP-SAT entry point now accepts an opt-in `minimize_displacement_to` map
of reference coordinates. It adds Manhattan-distance objective terms in model
grid units while leaving all hard constraints authoritative; the existing
`hint_positions` warm start remains independent. The model-level tests pass.

A read-only run against the current board and full configured constraint set
returned `unknown` after the 30-second budget, with the existing configuration
to netlist/loop reference drift reported before solve. No placement or PCB
output was written. The next implementation step is to wire the current
domain names correctly, then use this objective for a bounded candidate and
measure its routed DRC before considering any board change.
