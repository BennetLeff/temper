---
plan_id: 2026-06-28-008
plan_type: feat
title: "feat: Hypothesis invariant test suites for IO, deterministic pipeline, and loss functions"
status: active
origin: docs/brainstorms/2026-06-28-router-v6-hypothesis-invariant-tests-requirements.md
tags: [hypothesis, pbt, invariants, testing, io, deterministic, losses]
---

# feat: Hypothesis invariant test suites for IO, deterministic pipeline, and loss functions

## Summary

Extend the Hypothesis-driven invariant test suite pattern to three remaining areas: the KiCad parser / IO layer (coordinate system and data fidelity), deterministic pipeline stages (stage output validity and structural drift), and loss functions (mathematical property invariants matching the placement invariants pattern). Uses the proven strategy from Router V6: shared `@st.composite` strategies, per-class PBT files, `@pytest.mark.property` convention.

---

## Problem Frame

The Router V6 invariant suite (26 tests across 4 classes) proved the pattern works. Three other areas remain untested with invariants:

- **IO layer**: The 250M boundary loss bug originated in a coordinate-system mismatch (raw logits vs softmax). The parse → board → context chain has no invariant coverage.
- **Deterministic pipeline**: The routing/ deletion (#44) broke cross-references silently at import time — stage output invariant checks would have caught structural drift before CI.
- **Loss functions**: Only BoundaryLoss has invariant tests (from the placement suite). OverlapLoss, WirelengthLoss, ClearanceLoss, and ~30 other losses have no property-based tests.

---

## Requirements Trace

From `docs/brainstorms/2026-06-28-router-v6-hypothesis-invariant-tests-requirements.md` (Scope Boundaries: Deferred for later).

| Area | Key invariants |
|------|---------------|
| IO / KiCad parser | Parsed component positions within board bounds, component bounds positive, netlist consistency (nets match component pins), board dimensions match PCB file, coordinate units in mm |
| Deterministic pipeline | Stage outputs non-None with correct types, stage-to-stage data passes through unmodified, isolation slot geometry valid, HV/LV partition correct, connectivity graph connected |
| Loss functions | Zero-when-no-violation, positive-when-violation, monotonic in distance, gradient finite (no NaN/Inf), idempotent, empty-is-zero |

---

## Key Technical Decisions

1. **Separate strategy file per area**: Each area gets its own `*_property_strategies.py` following the Router V6 pattern. IO strategies generate `Board` + `ParsedPCB` + `PlacementConstraints`; loss strategies reuse the existing `tests/conftest.py` fixtures (`simple_board`, `simple_netlist`); deterministic strategies use `BoardState` construction.

2. **IO layer focuses on parse-output invariants**: Given a parsed KiCad file (or generated `ParsedPCB`), assert structural invariants on the output — not on the parser internals. This avoids coupling to parser implementation details.

3. **Loss functions follow the placement invariants pattern**: Each loss gets a theorem class: zero-when-no-violation, positive-when-violation, monotonicity, gradient finiteness, idempotence, empty-is-zero. Reuses `simple_board`/`simple_netlist` fixtures from conftest.

4. **Deterministic pipeline tests stage output shapes**: Following the Router V6 output validity class, test that each stage produces non-None outputs with correct field types and array dimensions. Geometric invariants (isolation slot validity, HV/LV partition) deferred to a follow-up after fixture generation stabilizes.

---

## Implementation Units

### U1. IO / KiCad parser: shared strategies + invariants

**Goal:** Build a Hypothesis strategy file for IO inputs and a PBT test file asserting parse-output invariants.

**Requirements:** IO invariants (parsed positions in bounds, component bounds positive, netlist consistency, coordinate units)

**Dependencies:** None (independent of other units)

**Files:**
- `packages/temper-placer/tests/io/io_property_strategies.py` (new) — `@st.composite` for `Board`, `ParsedPCB`, `PlacementConstraints`
- `packages/temper-placer/tests/io/test_io_invariants_pbt.py` (new) — property tests

**Approach:**
- Strategies: `parsed_pcb_with_bounds()` generates a `ParsedPCB` with components placed within board bounds and positive dimensions. `board_and_netlist()` generates a `Board` + `Netlist` pair with consistent component-to-net mapping.
- Invariants: parsed component positions within `[0, board.width] × [0, board.height]`, component `bounds` are positive floats, every pin's net exists in the netlist, board dimensions match the PCB file's dimensions.
- **Coordinate unit test**: Given a `ParsedPCB`, all component initial positions have magnitude consistent with board dimensions (not nanometers, not meters).

**Patterns to follow:**
- `packages/temper-placer/tests/router_v6/router_v6_property_strategies.py` — strategy composition pattern
- `packages/temper-placer/tests/core/test_placement_invariants.py` — Theorem VI (coordinate scaling invariant)

**Test scenarios:**
- Happy path: Generated ParsedPCB with 10 components → all positions within board bounds
- Happy path: Generated Board + Netlist → every pin net exists in Netlist.nets
- Edge case: Component at board edge (x=0, y=0) → position passes (inclusive check)
- Edge case: Zero-component ParsedPCB → no position assertions fail (vacuously true)
- Covers coordinate scaling: Component positions in mm, not nm — magnitude check passes

**Verification:** `pytest tests/io/test_io_invariants_pbt.py` passes with 100 examples. No `@settings` without `@given`.

---

### U2. Deterministic pipeline: stage output invariants

**Goal:** Build PBT tests for deterministic pipeline stage output validity and structural invariants.

**Requirements:** Stage outputs non-None with correct types, stage-to-stage data pass-through, connectivity graph connected

**Dependencies:** None (independent of other units)

**Files:**
- `packages/temper-placer/tests/deterministic/deterministic_property_strategies.py` (new) — `@st.composite` for `BoardState` generation
- `packages/temper-placer/tests/deterministic/stages/test_deterministic_invariants_pbt.py` (new) — property tests

**Approach:**
- Strategies: `board_state_with_zones()` generates a `BoardState` with random component count (2-20), random board dimensions (50-300mm), and random zone assignments. Reuses the `fixture_minimal_pcb` pattern from conftest.
- Invariants: Every stage's `run()` method returns a `BoardState` (not None). Stage output fields are populated after running (not None, not empty). The connectivity validation stage produces a connected or explicitly partitioned graph. The HV/LV partition stage separates components by net class.
- **Structural drift invariant**: Iterate over all registered stages, assert each `.run()` returns a valid `BoardState` with the stage's output fields present. This catches the routing/ deletion class of bug — if a stage's dependency module is deleted, the stage fails at import time, not runtime.

**Patterns to follow:**
- `packages/temper-placer/tests/router_v6/test_router_v6_output_validity_pbt.py` — stage output shape invariants
- `packages/temper-placer/tests/deterministic/fixtures.py` — existing BoardState fixture patterns

**Test scenarios:**
- Happy path: Generated BoardState → every registered stage produces non-None output
- Happy path: After clearance_grid stage → clearance_grid field is populated
- Edge case: BoardState with zero components → stages handle gracefully (no crash)
- Covers structural drift: Stage's dependency module deleted → import fails, invariant catches it
- Covers data pass-through: BoardState before and after a pass-through stage → unchanged fields remain identical

**Verification:** `pytest tests/deterministic/stages/test_deterministic_invariants_pbt.py` passes. Coverage confirms each stage's `run()` method is exercised at least once.

---

### U3. Loss functions: mathematical property invariants

**Goal:** Build PBT tests for loss functions following the placement invariants pattern — each loss gets hypothesis tests for zero-when-no-violation, positive-when-violation, monotonicity, gradient finiteness.

**Requirements:** Loss function invariants (zero-when-no-violation, positive-when-violation, monotonic, gradient finite, idempotent, empty-is-zero)

**Dependencies:** None (independent of other units)

**Files:**
- `packages/temper-placer/tests/losses/test_loss_invariants_pbt.py` (new) — property tests for all loss functions

**Approach:**
- Reuse existing `simple_board`, `simple_netlist`, `rng_key` fixtures from conftest. No new strategy file needed for basic invariants.
- **Zero-when-no-violation**: Place all components within board bounds, assert BoundaryLoss = 0. Components with no overlap, assert OverlapLoss = 0. (Already done for BoundaryLoss in placement invariants — extend to other losses.)
- **Positive-when-violation**: Place one component outside bounds, assert BoundaryLoss > 0. Overlap two components, assert OverlapLoss > 0.
- **Monotonicity**: For distance-based losses (boundary, overlap, wirelength), moving a component farther from the violation increases the loss.
- **Gradient finiteness**: For each loss, compute gradient with `jax.grad()` — assert no NaN or Inf values.
- **Idempotence**: Calling the loss function twice with same inputs produces the same value.
- **Empty-is-zero**: Passing empty/zero inputs produces zero loss (where applicable).
- Target losses: `BoundaryLoss`, `OverlapLoss`, `WirelengthLoss`, `ClearanceLoss` (if accessible), `SpreadLoss`, and any other losses with well-defined zero conditions.

**Patterns to follow:**
- `packages/temper-placer/tests/core/test_placement_invariants.py` — Theorem II (boundary loss invariants)
- `packages/temper-placer/tests/losses/test_loop_area_oracles.py` — existing loss oracle test pattern

**Test scenarios:**
- Happy path: 5 components within 200×150mm board → BoundaryLoss = 0
- Happy path: 5 components with no overlap → OverlapLoss = 0
- Edge case: Single component at board center → all loss values are finite
- Covers positive-when-violation: Component at (200, 200) on 100×100 board → BoundaryLoss > 0
- Covers monotonicity: Distance doubled → loss at least 2× (approximately)
- Covers gradient: `jax.grad` returns finite values for all losses at valid positions
- Covers idempotence: Same input twice → same output within float tolerance

**Verification:** `pytest tests/losses/test_loss_invariants_pbt.py` passes all invariants for at least BoundaryLoss, OverlapLoss, WirelengthLoss, and SpreadLoss.

---

## Scope Boundaries

### Deferred for later
- Geometric invariants for deterministic pipeline stages (isolation slot validity, HV/LV partition correctness) — deferred until BoardState generation strategies stabilize
- Performance invariants (loss function execution time)
- Shared theorem library extraction

### Deferred to Follow-Up Work
- Coverage gate enforcement (`--cov-fail-under=90`) on new PBT files
- Loss function cross-validation against reference implementations (e.g., pysat for SAT losses)

---

## Dependencies / Assumptions

- Hypothesis 6.148.7 is installed (already in `pyproject.toml`)
- Existing conftest fixtures (`simple_board`, `simple_netlist`, `rng_key`, `fixture_minimal_pcb`, `fixture_design_rules_temper`) are available and working
- The `BoardState` class can be constructed with generated data (verified: pure dataclass)
- Loss functions accept `positions: Array, rotations: Array, context: LossContext` and return `LossResult` with `.value` and `.breakdown`
- All three units are independent and can be implemented in parallel

---

## Outstanding Questions

### Resolved During Planning
- IO strategies use existing `ParsedPCB` generation from router_v6 strategies with adjustments — cross-import is acceptable between test directories
- Loss function tests reuse conftest fixtures rather than creating new strategies — avoids strategy proliferation for well-tested fixtures

### Deferred to Implementation
- Exact list of loss functions to cover — determined by which losses have well-defined zero conditions and accessible `LossContext` construction
- Whether deterministic stages need per-stage strategy files or a single shared file — depends on how many stages have unique input requirements
