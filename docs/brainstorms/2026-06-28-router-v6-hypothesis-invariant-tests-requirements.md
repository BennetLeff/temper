---
date: 2026-06-28
topic: router-v6-hypothesis-invariant-tests
---

# Router V6 Hypothesis Invariant Test Suite

## Summary

A Hypothesis-driven property-based test suite proving four classes of mathematical invariants on the Router V6 pipeline — output validity, geometric consistency, topological correctness, and DRC conformance. Uses `@given` strategies that generate arbitrary-but-valid Router V6 inputs and assert theorems hold across the input space. Resides in `tests/router_v6/` matching existing `test_*_pbt.py` conventions.

---

## Problem Frame

The Router V6 pipeline (stages 0-4 plus manufacturing DRC) is the most complex subsystem in temper-placer — SAT-based topological routing feeds into A* geometric realization, with 11+ specialized modules for channel analysis, escape via generation, clearance checking, and DFM validation. Bugs in this pipeline are disproportionately expensive: they produce silently wrong routing results (no crash, no exception), surface as downstream DRC violations in KiCad, and require full pipeline re-runs to diagnose.

Recent evidence: the `RouterV6Result() takes no arguments` bug (missing `@dataclass` decorator) passed code review, passed type checking, and only failed at runtime inside the closure test. The `250M boundary loss` bug (raw rotation logits passed to loss functions) survived for weeks because the metric was silently wrong. Both failures share a pattern: structural drift that conventional tests don't catch because they test fixed fixtures, not the space of valid inputs.

The existing `test_router_v6_*_pbt.py` tests (channel widths, routing space) demonstrate Hypothesis works well in this codebase. Extending this pattern to cover full pipeline invariants closes the gap between "the code runs" and "the code is correct for all valid inputs."

---

## Actors

- A1. **Router V6 pipeline** (the system under test): Stages 0-4 (parse, escape vias, channel analysis, topological routing, geometric realization) plus manufacturing DRC.
- A2. **Hypothesis engine**: Generates arbitrary-but-valid input combinations and searches for counterexamples to stated theorems.
- A3. **CI runner**: Executes the invariant suite on every PR touching Router V6 or its dependencies, with a per-test timeout.

---

## Key Flows

- F1. **Invariant test execution**
  - **Trigger:** `pytest tests/router_v6/test_router_v6_invariants.py` (or individual class files)
  - **Actors:** A1, A2
  - **Steps:** Hypothesis generates valid Board/Netlist/PlacementState tuples from composed strategies → Router V6 pipeline runs stages 0-4 → Each theorem class evaluates its invariants on the output → Hypothesis reports passing/falsifying examples
  - **Outcome:** All theorems hold across the generated input space. A falsifying example is minimized and reported with a human-readable counterexample.
  - **Covered by:** R1, R2, R3, R4

- F2. **CI regression detection**
  - **Trigger:** PR push touching `packages/temper-placer/src/temper_placer/router_v6/` or `tests/router_v6/`
  - **Actors:** A3, A1, A2
  - **Steps:** CI installs dependencies → runs Router V6 invariant suite → reports pass/fail in job summary → failing theorems block merge
  - **Outcome:** No Router V6 structural drift reaches main without failing at least one invariant.
  - **Covered by:** R5, R6

---

## Requirements

**Output validity invariants**

- R1. Stage output shape invariant: For any valid Board/Netlist/PlacementState, each stage (0 through 4) produces a non-None output with the correct dataclass type, required fields populated, and arrays with expected dimensions matching the input component count.
- R2. Pipeline result invariant: `RouterV6Result` has all fields populated, `success_count + failure_count + plane_net_count` equals total nets, and `completion_rate` is in `[0.0, 1.0]`.

**Geometric consistency invariants**

- R3. Trace containment invariant: All trace segments produced by stage 4 lie within board bounds. No segment endpoint has coordinates outside `[0, board_width] × [0, board_height]`.
- R4. Via validity invariant: All vias have positive diameter and drill size, diameter >= drill, and position within the component footprint that owns them.
- R5. Trace width positivity: All assigned trace widths are strictly positive and within the board's minimum/maximum trace width constraints.

**Topological correctness invariants**

- R6. SAT solution consistency: When the SAT solver produces a solution, every net in the netlist has a channel assignment and layer assignment. No two nets assigned to the same channel on the same layer have overlapping ordinal positions.
- R7. Channel capacity invariant: No channel's assigned net count exceeds its computed capacity. `sum(net_count_per_channel) <= max_capacity_per_channel` for all channels.
- R8. Escape via completeness: Every component that requires escape vias (based on dense package detection) receives at least one via per pin that needs escape routing.

**DRC conformance invariants**

- R9. Clearance minimum invariant: For any pair of distinct traces on the same layer, the minimum Euclidean distance between their centerlines exceeds the minimum clearance specified by design rules for their net classes.
- R10. Annular ring minimum: Every via's annular ring (pad diameter minus drill diameter divided by 2) meets or exceeds the minimum specified by the board's design rules.
- R11. Creepage distance: For any HV-classified trace and any LV-classified trace on external layers, the creepage distance meets or exceeds the required creepage for the voltage class.

**CI and operational invariants**

- R12. Hypothesis configuration: Each invariant test uses `@settings(deadline=None, max_examples=100)` with appropriate health check suppressions. No test exceeds 30 seconds wall time for 100 examples.
- R13. Falsifying example minimization: When Hypothesis finds a counterexample, the minimized example is reported with concrete input values (board dimensions, component positions, net assignments) that reproduce the failure.

---

## Acceptance Examples

- AE1. **Covers R1.** Given a valid Board (random width/height 50-200mm) and Netlist (2-20 components with random bounds 5-50mm), when stage 2 channel analysis runs, the Stage2Output has `obstacle_maps`, `routing_spaces`, `skeletons`, and `channel_widths` dicts matching the input layer count.
- AE2. **Covers R3.** Given a Board (100×150mm) and a stage 4 output with 15 routed nets, when trace containment is checked, no trace segment endpoint has x < 0, x > 100, y < 0, or y > 150.
- AE3. **Covers R6.** Given a Netlist with 10 nets and a SAT solution, when channel assignments are extracted, every net appears in exactly one channel and every channel's net count ≤ its capacity.
- AE4. **Covers R9.** Given a stage 4 output on a 2-layer board with design rules specifying 0.2mm clearance, when clearance is checked for all same-layer trace pairs, the minimum centerline distance ≥ 0.2mm + max_trace_width.

---

## Success Criteria

- Every Router V6 structural regression from the past 30 days (routing/ deletion cross-references, RouterV6Result missing @dataclass) would have been caught by at least one invariant before CI ran the closure test.
- The Hypothesis suite surfaces at least one pre-existing Router V6 edge case not covered by existing deterministic tests within the first CI run.
- A falsifying example from Hypothesis is reproducible on a developer machine with a single `pytest` invocation using the printed `@example` decorator.

---

## Scope Boundaries

- Router V6 stages 0-4 and manufacturing DRC only. Manufacturing DRC validators that require KiCad (full DRC via `kicad-cli`) are excluded; only in-memory DFM checks are covered.
- KiCad parser / IO layer, deterministic pipeline stages, and loss function invariants are out of scope (deferred to Phase 2).
- Shared theorem library extraction is out of scope (deferred to Phase 3, after the Router V6 suite validates the pattern).
- Production board fixtures (temper.kicad_pcb) are out of scope — all inputs are generated by Hypothesis strategies.
- Performance invariants (wall-clock time, memory usage) are out of scope — this suite tests correctness, not speed.

---

## Key Decisions

- Hypothesis-first: Chosen over static fixture-based invariants because the Router V6 input space is too large for hand-picked fixtures to cover. The existing PBT tests in `test_channel_widths_pbt.py` and `test_routing_space_pbt.py` validate this approach works in the Router V6 context.
- All four classes at once: Chosen over incremental delivery because the classes compose — geometric invariants depend on output validity, topological depends on geometric, and DRC depends on all three. Building them incrementally would require stubs that get replaced, adding rework.
- Single file or per-class files: Deferred to planning — both patterns exist in the codebase, and the choice depends on how much shared setup each class needs.

---

## Dependencies / Assumptions

- Hypothesis is already a dev dependency (present in `pyproject.toml`).
- The existing `tests/property/conftest.py` strategies (`design_rules_with_hv`, `board_state_with_ghost_pads`) can be extended rather than rewritten.
- The Router V6 pipeline can be invoked with generated inputs without requiring a parsed KiCad PCB file — the stage entry points accept in-memory `ParsedPCB` and `Netlist` objects.
- The existing `tests/router_v6/` CI step has enough time budget for 100-example Hypothesis runs (assumed ~30s per test class, ~2 minutes total).

---

## Outstanding Questions

### Resolve Before Planning

- [Affects R2] How are plane nets counted in the Router V6 pipeline? The `plane_net_count` field on `RoutingResults` needs verification — if it's always zero in generated inputs, the invariant `success_count + failure_count + plane_net_count == total_nets` may need adjustment.
- [Affects R3] Are trace segments in board-relative or absolute coordinates? The stage 4 output coordinate system needs verification against `board.get_relative_bounds_array()`.

### Deferred to Planning

- [Affects R9, R10, R11][Needs research] What is the minimum viable design rules fixture for DRC invariants? The full temper design rules are complex — a minimal subset that exercises clearance, annular ring, and creepage checks is sufficient for invariants.
- [Affects R12][Technical] Hypothesis health check suppressions — which checks fail on the Router V6 pipeline and need `suppress_health_check`? Determined during implementation.
- [Affects file structure][Technical] Single file (`test_router_v6_invariants.py`) vs per-class files — decided during planning based on shared setup needs and CI parallelization.
