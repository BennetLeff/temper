---
plan_id: 2026-06-28-007
plan_type: feat
title: "feat: Router V6 Hypothesis-driven invariant test suite"
status: active
origin: docs/brainstorms/2026-06-28-router-v6-hypothesis-invariant-tests-requirements.md
tags: [router-v6, hypothesis, pbt, invariants, testing]
---

# feat: Router V6 Hypothesis-driven invariant test suite

## Summary

Add a Hypothesis-driven property-based invariant test suite for the Router V6 pipeline, covering four theorem classes: output validity, geometric consistency, topological correctness, and DRC conformance. Tests use `@given` with `@st.composite` strategies that generate arbitrary-but-valid Router V6 inputs, and assert theorems hold across the input space.

---

## Problem Frame

The Router V6 pipeline (stages 0-4 plus DFM) is the most complex subsystem in temper-placer. Bugs here are disproportionately expensive: they produce silently wrong routing results, surface as downstream DRC violations in KiCad, and require full pipeline re-runs to diagnose. Two recent regressions — `RouterV6Result() takes no arguments` (missing `@dataclass`) and the 250M boundary loss bug (raw rotation logits) — both passed code review and type checking, only failing at runtime. Conventional fixture-based tests don't cover the space of valid inputs; Hypothesis property tests do.

17 PBT files already exist in `tests/router_v6/`, covering Stage 2 sub-steps and Stage 3 SAT validation. Stage 4 (geometric realization) and DFM (beyond basic fuzzing) have no invariant suite. The existing DFM fuzzing suite (`test_dfm_hypothesis_fuzzing.py`) proves the pattern works — it already tests crash-safety and non-negative counts across 7 DFM modules using composed strategies.

---

## Requirements Trace

Source: `docs/brainstorms/2026-06-28-router-v6-hypothesis-invariant-tests-requirements.md`

| R-ID | Summary | Covered by |
|------|---------|------------|
| R1 | Stage output shapes non-None, correct dataclass type, correct array dimensions | U2 |
| R2 | RouterV6Result fields populated, completion_rate in [0,1] | U2 |
| R3 | All trace segments within board bounds | U3 |
| R4 | Via diameter > 0, diameter >= drill, position within footprint | U3 |
| R5 | Trace widths positive and within board constraints | U3 |
| R6 | SAT solution: every net has channel + layer assignment, no overlapping ordinals | U4 |
| R7 | Channel capacity: assigned nets <= max capacity | U4 |
| R8 | Escape via completeness: every pin in dense package gets a via | U4 |
| R9 | Clearance minimum between same-layer traces | U5 |
| R10 | Annular ring minimum for all vias | U5 |
| R11 | Creepage distance for HV/LV trace pairs | U5 |
| R12 | Hypothesis configuration: max_examples=100, deadline=30000 | U6 |
| R13 | Falsifying example minimization with concrete reproduction values | U6 |

---

## Key Technical Decisions

1. **Micro-stage invocation over full pipeline run**: The `RouterV6Pipeline.run()` requires a `.kicad_pcb` file on disk. For Hypothesis tests (100+ examples), we invoke micro-stages directly with `BoardState` or constructed `ParsedPCB` objects, following the existing pattern from `test_obstacle_map_pbt.py:_make_minimal_pcb()`. This avoids per-example file I/O and keeps tests sub-second.

2. **Use `stage0_data.DesignRules` not `core/design_rules.DesignRules`**: The Router V6 pipeline uses its own `DesignRules` dataclass (in `stage0_data.py`). Strategy generation must target this type, not the `core/design_rules` variant used by the deterministic pipeline. The existing `fixture_design_rules_temper` fixture uses the wrong type and cannot be reused directly.

3. **DFM stub pattern for DRC invariants**: Following `dfm_property_strategies.py`, we construct minimal `Path`, `Via`, `Route`, and `RoutingResults` objects to feed DFM checkers directly, rather than running the full pipeline to produce them. This keeps the DRC class (U5) independent of the earlier classes (U3, U4).

4. **Single strategy file, per-class test files**: A shared `router_v6_property_strategies.py` holds composite `@st.composite` strategies for generating `ParsedPCB`, `RoutingResults`, and DFM inputs. Each theorem class gets its own `test_router_v6_*_pbt.py` file, matching the existing 17-file PBT convention.

5. **Plane net count**: The `plane_net_count` field on `RoutingResults` defaults to 0 and is set during routing (not at result construction). The output validity invariant uses `success_count + failure_count` for the completion check, excluding `plane_net_count` pending verification of which routing code path sets it.

---

## Implementation Units

### U1. Shared property strategies for Router V6

**Goal:** Create composite Hypothesis strategies for generating arbitrary-but-valid Router V6 inputs (ParsedPCB, RoutingResults, DFM inputs) that all invariant test classes compose from.

**Requirements:** R1-R11 (enabling infrastructure)

**Dependencies:** None

**Files:**
- `packages/temper-placer/tests/router_v6/router_v6_property_strategies.py` (new)

**Approach:**
- Define anchored constants: `BOARD_WIDTH_RANGE=(50, 300)`, `BOARD_HEIGHT_RANGE=(50, 300)`, `LAYERS=["F.Cu", "B.Cu"]`, `NET_CLASSES=["Signal", "Power", "HighVoltage"]`
- `@st.composite` for `parsed_pcb(draw)` → `ParsedPCB` with `stage0_data.DesignRules`, `stage0_data.StackupInfo`, and `Component`/`Net` lists with random bounds in [1, 50]mm and positions within board
- `@st.composite` for `routing_results_with_traces(draw)` → `RoutingResults` with `CompiledRoute`s that carry `RoutePath`s with coordinates within `BOARD_WIDTH_RANGE`, `BOARD_HEIGHT_RANGE`. Include mixed success/failure nets and plane nets
- `@st.composite` for `stage_output(draw, stage_name)` → appropriate stage output dataclass for that stage (Stage2Output, Stage3Output, Stage4Output), populated with plausible random data
- Follow the `dfm_property_strategies.py` pattern of realistic net name vocabulary, mixed HV/power/signal nets, and board-bounded coordinates

**Patterns to follow:**
- `packages/temper-placer/tests/router_v6/dfm_property_strategies.py` — composite strategy composition with `@st.composite`
- `packages/temper-placer/tests/property/conftest.py` — `@st.composite` patterns for `arbitrary_netlist`, `design_rules_with_hv`

**Test scenarios:**
- Covers R1-R11. Each generated ParsedPCB has non-empty component and net lists, positive board dimensions, valid layer stackup with F.Cu/B.Cu
- RoutingResults has compiled_routes and failed_nets lists, plane_net_count consistent with generated input
- Strategies produce diverse inputs across 100 draws (varying component counts, board sizes, net classes)

**Verification:** Strategy file imports cleanly. `st.floats()` ranges produce values within board bounds. A smoke test using `@given(parsed_pcb())` passes basic assertions (board width > 0, component list non-empty).

---

### U2. Output validity invariants

**Goal:** Prove that all Router V6 stages produce structurally valid outputs (non-None, correct types, correct array dimensions, RouterV6Result fields populated).

**Requirements:** R1, R2

**Dependencies:** U1 (strategies for ParsedPCB and StageOutput generation)

**Files:**
- `packages/temper-placer/tests/router_v6/test_router_v6_output_validity_pbt.py` (new)

**Approach:**
- **Stage 2 invariant**: Given a valid ParsedPCB via `parsed_pcb()` strategy, run `Stage2Orchestrator.run_in_memory(pcb, escape_vias)` (or construct `Stage2Output` directly). Assert `obstacle_maps`, `routing_spaces`, `skeletons`, `channel_widths` are non-None dicts with keys matching layer names from the stackup.
- **Stage 3 invariant**: Given `Stage2Output` from the strategy, construct `Stage3Output` with required fields. Assert `constraint_model`, `sat_model`, `solution`, `topology_graph` are non-None; `solution.status` is a valid `SolverStatus` value.
- **Stage 4 invariant**: Given `Stage3Output`, construct `RoutingResults`. Assert `compiled_routes` is a dict, `failed_nets` is a list, `success_count + failure_count` matches expected net count, `completion_rate` is in [0.0, 1.0].
- **Full result invariant**: Construct `RouterV6Result`. Assert all five fields (pcb, escape_vias, stage2, stage3, stage4) are non-None; `runtime_seconds >= 0`.

**Patterns to follow:**
- `packages/temper-placer/tests/router_v6/test_channel_widths_pbt.py` — `@given` with direct dataclass construction
- `packages/temper-placer/tests/router_v6/test_stage4_result_pbt.py` — stage validator pattern with `BoardState`

**Test scenarios:**
- Happy path: Valid ParsedPCB → Stage2Orchestrator produces non-None output
- Happy path: Valid Stage2Input → Stage3Output constructed with all fields
- Happy path: Valid RoutingResults → RouterV6Result constructed with completion_rate in [0,1]
- Edge case: ParsedPCB with zero components → Stage2Output still has empty dicts (not None)
- Edge case: RoutingResults with 0 success + 0 failure → completion_rate = 0.0 (not NaN)
- Error path: None ParsedPCB → Stage2Orchestrator raises TypeError (not silent None)

**Verification:** All `@given` tests pass with max_examples=100. No `@settings` without `@given` pairing (copy-paste foot-gun). Each invariant assertion has a descriptive failure message.

---

### U3. Geometric consistency invariants

**Goal:** Prove that all geometric outputs of the Router V6 pipeline (trace segments, vias, trace widths) satisfy spatial invariants relative to board bounds and manufacturing constraints.

**Requirements:** R3, R4, R5

**Dependencies:** U1 (strategies for RoutingResults with traces), U2 (confirms stage outputs have correct shapes before geometric checking)

**Files:**
- `packages/temper-placer/tests/router_v6/test_router_v6_geometric_invariants_pbt.py` (new)

**Approach:**
- **Trace containment**: Given `RoutingResults` with `CompiledRoute`s carrying `RoutePath.coordinates` via the strategy, assert every coordinate (x, y) satisfies `0 <= x <= board.width` and `0 <= y <= board.height`. Coordinates are board-relative (verified by `get_relative_bounds_array()`).
- **Via validity**: Given `CompiledRoute.vias`, assert each via has `diameter > 0`, `drill > 0`, `diameter >= drill`. Via positions are within the board bounds.
- **Trace width positivity**: Given `CompiledRoute.width_mm`, assert `width_mm > 0` and `min_trace_width <= width_mm <= max_trace_width` (where min/max come from design rules).
- **Path length consistency**: Given `CompiledRoute.path.path_length`, assert it matches the sum of segment lengths computed from coordinates (within floating-point tolerance).

**Patterns to follow:**
- `packages/temper-placer/tests/router_v6/dfm_property_strategies.py` — `realistic_routing_results()` composite strategy
- `packages/temper-placer/tests/core/test_placement_invariants.py` — Theorem III (clamping invariants) for the board-bounds assertion pattern

**Test scenarios:**
- Happy path: Generated RoutingResults with traces within 100×150mm board → all coordinates pass bounds check
- Edge case: Trace with a single segment at board edge (x=0, y=0) → passes bounds check (inclusive)
- Edge case: Via with diameter = drill = 0.1mm → passes diameter >= drill
- Error path: Trace with negative x coordinate → invariant fails with descriptive message naming the offending coordinate
- Integration: After stage2_orchestrator runs, all occupancy_grid entries have positive cell size

**Verification:** All `@given` tests pass. The trace containment invariant catches coordinates outside [0, w]×[0, h]. The via invariant catches diameter < drill.

---

### U4. Topological correctness invariants

**Goal:** Prove that the SAT-based topological router produces logically consistent channel assignments and capacity-compliant routing.

**Requirements:** R6, R7, R8

**Dependencies:** U1 (strategies), U2 (stage output shapes confirmed valid)

**Files:**
- `packages/temper-placer/tests/router_v6/test_router_v6_topological_invariants_pbt.py` (new)

**Approach:**
- **Channel assignment completeness**: Given a generated `Netlist` with N nets and a `Stage3Output` (or `ConstraintModel` + `TopologicalSolution`), assert every net name appears in exactly one channel assignment. No net is assigned to two channels; no net is unassigned.
- **No ordinal overlap**: For any two nets assigned to the same channel on the same layer, their `OrderVar` ordinals must not overlap (the SAT encoding enforces this via `at_most_one` constraints).
- **Channel capacity**: For each channel, `len(assigned_nets) <= channel.max_capacity`. The `_encode_at_most_k()` function in the SAT solver guarantees this, but the invariant cross-validates it.
- **Escape via completeness**: Given a `DensePackage` (from `identify_dense_packages()`), the `generate_escape_vias()` call produces a non-empty `EscapeVia` list where each dense package component has at least one via per pin that requires escape.
- **Cross-validation** (optional, `@pytest.mark.slow`): If `pysat` is available, compare the Rust SAT solver result against pysat's Glucose3 CDCL on the same constraint model. Assert agreement on SAT/UNSAT status. Follows the pattern from `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md`.

**Patterns to follow:**
- `packages/temper-placer/tests/router_v6/test_sat_solve_pbt.py` — SAT solver property tests with `@given`
- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — Hypothesis cross-validation pattern

**Test scenarios:**
- Happy path: 10-net Netlist, SATISFIABLE solution → every net has a channel assignment
- Happy path: DensePackage with 2 BGA components → escape via generator produces vias for all pins
- Edge case: UNSATISFIABLE model → `solution.is_satisfiable` is False, assignment is empty
- Edge case: Channel with capacity = 1 receives exactly 1 net → capacity invariant holds
- Error path: Channel assigned nets exceed capacity → invariant fails with expected vs actual count
- Covers R8: DensePackage with 0 components → generate_escape_vias returns empty list (not None)

**Verification:** All `@given` tests pass. Channel assignment invariant catches duplicate or missing assignments. Capacité invariant catches over-assigned channels. Cross-validation test (if slow) catches solver implementation drift.

---

### U5. DRC conformance invariants

**Goal:** Prove that Router V6 DFM checks hold mathematical invariants on all valid RoutingResults inputs — clearance minimums, annular ring minimums, and creepage distances meet design rule thresholds.

**Requirements:** R9, R10, R11

**Dependencies:** U1 (DFM input strategies via `dfm_property_strategies.py` pattern)

**Files:**
- `packages/temper-placer/tests/router_v6/test_router_v6_drc_invariants_pbt.py` (new)

**Approach:**
- **Clearance invariant**: Given `RoutingResults` with traces on the same layer (via strategy), run `verify_clearance(routing_results, min_clearance=0.2)`. Assert that every violation in the `ClearanceReport` correctly identifies segments closer than `min_clearance`. **Idempotence**: running clearance check twice produces the same violations.
- **Annular ring invariant**: Given `RoutingResults` with vias (via strategy), run `check_annular_rings(routing_results, min_annular_ring=0.1)`. Assert `violation_count >= 0` and every reported violation has `actual_ring < min_annular_ring`.
- **Creepage invariant**: Given mixed HV/Signal `RoutingResults`, run `verify_creepage(routing_results, default_creepage=2.0)`. Assert all reported violations are between HV nets and other nets; no Signal-to-Signal pairs are flagged.
- **Empty-is-zero**: Given `RoutingResults` with zero compiled_routes and zero failed_nets, all DFM checks return zero violations.
- **No-crash**: Every DFM check function returns without raising for any RoutingResults (even with extreme but valid values — trace widths of 10mm, vias with diameter=drill=0.01mm, etc.).
- **Consistency**: `total_violations >= critical_violations` in the manufactured report aggregation.

**Patterns to follow:**
- `packages/temper-placer/tests/router_v6/test_dfm_hypothesis_fuzzing.py` — existing DFM fuzzing with 200 iterations, `@st.composite` strategies
- `packages/temper-placer/tests/router_v6/dfm_boundary_constants.py` — stub Path/Via/Route/Results for direct DFM invocation

**Test scenarios:**
- Covers R9: Generated traces on same layer with 0.05mm separation → clearance violation reported (min_clearance=0.2)
- Covers R10: Generated vias with drill=diameter → annular_ring=0.0 → violation reported
- Covers R11: HV trace near LV trace within 1.5mm → creepage violation reported (default_creepage=2.0)
- Happy path: Well-separated traces (1.0mm clearance) → zero violations
- Edge case: Empty RoutingResults → all DFM checks return empty reports, zero violations
- Error path: None RoutingResults → DFM check raises TypeError (not silent None)
- Covers R10: External layer vias get full threshold, internal layer vias get 50% threshold — both reported correctly

**Verification:** All `@given` tests pass with max_examples=100. Idempotence invariant holds across 100 random RoutingResults. Empty-is-zero holds. No crash on any generated input.

**Execution note:** The existing `test_dfm_hypothesis_fuzzing.py` already covers no-crash, non-negative counts, and consistency for 7 DFM modules. This unit extends those tests with clearance-driven invariants (R9-R11) and should NOT duplicate the existing fuzz tests.

---

### U6. CI integration and marker configuration

**Goal:** Configure Hypothesis settings, pytest markers, and CI gating for the new invariant test files.

**Requirements:** R12, R13

**Dependencies:** U2, U3, U4, U5 (test files must exist)

**Files:**
- `packages/temper-placer/tests/router_v6/test_router_v6_output_validity_pbt.py` (modify — add markers from U2)
- `packages/temper-placer/tests/router_v6/test_router_v6_geometric_invariants_pbt.py` (modify — add markers from U3)
- `packages/temper-placer/tests/router_v6/test_router_v6_topological_invariants_pbt.py` (modify — add markers from U4)
- `packages/temper-placer/tests/router_v6/test_router_v6_drc_invariants_pbt.py` (modify — add markers from U5)

**Approach:**
- Every test file uses `@settings(max_examples=100, deadline=30000)` with appropriate `suppress_health_check` (too_slow for first-time JIT compilation, data_too_large for large RoutingResults).
- Cross-validation tests (SAT pysat comparison, exhaustive enumeration) use `@pytest.mark.slow`.
- All invariant tests use `@pytest.mark.property` (already defined in `pyproject.toml`).
- CI: the existing `pytest tests/router_v6/` step automatically picks up new `test_*_pbt.py` files. No workflow changes needed.
- Falsifying example minimization: Hypothesis's built-in `.example()` decorator or `@reproduce_failure()` is used. Each invariant test prints generated input values on failure via `print()` inside the `@given` body.
- Coverage: each new PBT file carries `--cov=temper_placer.router_v6.<module> --cov-fail-under=90` (from the micro-stage decomposition learnings). Added to the `test` job's coverage invocation or documented as a follow-up gate.

**Patterns to follow:**
- `docs/solutions/design-patterns/decomposing-monolithic-stage-micro-stages-2026-06-22.md` — PBT convention: max_examples=100, deadline=30000, coverage gate at 90%
- `docs/solutions/test-failures/temper-placer-source-test-drift-2026-06-23.md` — `@settings` must always pair with `@given`

**Test scenarios:**
- Each `@given` test uses `@settings(max_examples=100, deadline=30000)`
- Slow tests use `@pytest.mark.slow` and are skippable with `-m "not slow"`
- Property tests use `@pytest.mark.property` for CI filtering
- Falsifying example from a deliberate invariant violation produces minimized, human-readable input values

**Verification:** `pytest tests/router_v6/ -k "test_router_v6"` runs all four invariant classes. `pytest -m "not slow"` runs only the fast tests. A deliberate invariant violation produces a Hypothesis shrinking output with concrete reproduction values.

---

## Scope Boundaries

### Deferred for later
- KiCad parser, deterministic pipeline, and loss function invariant suites
- Shared theorem library extraction from the placement invariants pattern
- Production board fixtures (temper.kicad_pcb) — all inputs are Hypothesis-generated
- Performance invariants (wall-clock time, memory usage)

### Deferred to Follow-Up Work
- Coverage gate enforcement (`--cov-fail-under=90`) on new PBT files — deferred until baseline coverage is stable
- `@pytest.mark.slow` SAT cross-validation test — deferred until pysat dependency is confirmed available in CI

---

## Dependencies / Assumptions

- Hypothesis 6.148.7 is already a dev dependency (present in `pyproject.toml`)
- The existing `tests/router_v6/` CI step runs `pytest tests/router_v6/` and picks up new `test_*_pbt.py` files automatically
- `stage0_data.DesignRules` can be constructed in-memory without a KiCad PCB file (verified: pure dataclass with defaults)
- `ParsedPCB` can be constructed with `components`, `nets`, `design_rules`, `stackup`, and `board` fields in-memory
- `RoutingResults` can be constructed from `compiled_routes` and `failed_nets` without running the full pipeline
- Traces are in board-relative coordinates (verified: `get_relative_bounds_array()` returns [0, 0, w, h])
- Plane nets are excluded from success/failure counts during invariant evaluation (pending verification)

---

## Outstanding Questions

### Resolved During Planning
- Trace coordinate system: board-relative (verified via `get_relative_bounds_array()`)
- Plane net count: defaults to 0, excluded from invariant completion_rate check

### Deferred to Implementation
- Exact Hypothesis health check suppressions for each test — determined when first batch of examples runs
- Whether `pysat` is available in CI for the SAT cross-validation slow test
