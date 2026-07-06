---
date: 2026-07-01
topic: hypothesis-pcl-property-tests
---

# Hypothesis Property-Test Suite for PCL Constraint Invariants

## Summary

A Hypothesis-driven property-based test suite for PCL constraint invariants using the established 4-layer architecture — shared strategies for PCL domain types, monotonic invariant theorems on loss functions, DAG-level output contract type validation, and CI integration as a gate on every PR touching PCL code.

---

## Problem Frame

The PCL silent-skip bug (keepout constraints never applied because `.pcl.yaml` auto-discovery fails silently) and the 250M-value corruption bug (raw rotation logits fed to loss functions expecting softmax) both passed fixture-only tests and survived for weeks in production. These share a pattern: structural drift that fixed fixtures don't catch because fixtures assert specific inputs, not the space of valid inputs. Property-based testing is the project's verification strategy — no formal methods (TLA+, Alloy, Coq) are in use, making Hypothesis the highest-assurance layer between code changes and production correctness.

---

## Actors

- A1. **Pipeline developer**: Adds or modifies PCL constraint types, loss functions, or stage handlers. Writes property tests for new constraint types following the 4-layer architecture.
- A2. **CI system**: Runs property tests on every PR touching PCL code or the loss bridge. Rejects regressions with minimized counterexamples. Enforces that new constraint types include invariant coverage.
- A3. **Constraint author**: Writes PCL YAML manifests defining adjacency, separation, enclosing, alignment, edge-placement, anchoring, and loop-area constraints. Consumes the constraint loading pipeline. Relies on the property suite to catch loading bugs (like silent auto-discovery failure).

---

## Key Flows

- F1. **New constraint type property test creation**
  - **Trigger:** Pipeline developer adds a new constraint type to the PCL schema (e.g., differential pair spacing, thermal zone exclusion).
  - **Actors:** A1, A2
  - **Steps:**
    1. Developer defines a `@st.composite` strategy for the new constraint type, composing from existing primitive strategies (geometric shapes, layer selectors, numerical bounds).
    2. Developer extends the `ConstraintCollection` composite strategy to include the new type alongside existing types.
    3. Developer writes theorem test methods for the new constraint type in the appropriate invariant class (loss sign, per-type monotonicity, tier-weight ordering).
    4. Developer runs `pytest tests/pcl/ -k "property"` locally and verifies Hypothesis finds no counterexamples at `max_examples=100`.
    5. CI runs the full PCL property suite on the PR and passes.
  - **Outcome:** New constraint type has property-test coverage for all invariants — loss non-negativity, zero-loss equivalence, per-type monotonicity under tightening, tier-weight ordering.
  - **Covered by:** R1, R2, R3, R4, R5, R6

- F2. **Constraint regression detection**
  - **Trigger:** PR modifies the loss bridge, constraint parser, or stage handlers touching constraint loading or evaluation.
  - **Actors:** A2, A1
  - **Steps:**
    1. CI detects file changes matching `packages/temper-placer/src/**/pcl/**` or `packages/temper-placer/src/**/loss_bridge/**` via paths-filter.
    2. CI runs `pytest tests/pcl/ -k "property" --hypothesis-max-examples=100 --deadline=30000`.
    3. Hypothesis generates random constraint configurations, component placements, and loss scenarios.
    4. Each theorem class evaluates its invariants on the generated inputs.
    5. On failure, Hypothesis shrinks to a minimal counterexample and reports: the invariant violated, the minimized input, and a human-readable trace.
  - **Outcome:** PR is blocked if any property test fails with a counterexample. The counterexample is included in the CI job summary for reproduction.
  - **Covered by:** R9, R10

- F3. **DAG stage output type validation at CI**
  - **Trigger:** Any stage in the PCL pipeline produces output that enters the DAG context.
  - **Actors:** A2, A1
  - **Steps:**
    1. After each stage executes, the DAG engine inspects `StageResult.outputs` keys.
    2. For each output key declared in the stage's `contract.output_schema`, the engine checks `assert isinstance(output_value, declared_type)` (keys declared in `provides` are checked for existence; type validation uses the `contract` field).
    3. On type mismatch, the pipeline fails with a diagnostic message naming the stage, data key, expected type, and actual type (e.g., `TypeError: input_stage output 'constraints' expected ConstraintCollection, got PlacementConstraints`).
    4. In CI, the property test generates type-mismatch scenarios via Hypothesis strategies that intentionally produce wrong-typed outputs.
    5. The test asserts the DAG engine rejects them.
  - **Outcome:** Constraint-type mismatch bugs (like PCL silent-skip producing legacy `PlacementConstraints` instead of `ConstraintCollection`) are caught at the DAG boundary in CI, not silently downstream.
  - **Covered by:** R7, R8

---

## Requirements

### PCL Domain Strategies

- **R1.** Shared `@st.composite` strategies generate valid instances of `ConstraintCollection`, `AdjacentConstraint`, `SeparatedConstraint`, `EnclosingConstraint`, `AlignedConstraint`, `OnSideConstraint`, `AnchoredConstraint`, `LoopAreaConstraint`, and `PlacementState`. Strategies live in a shared `tests/pcl/strategies.py` module importable by all PBT test files. Strategies are built from scratch — no prior PBT test files exist in the codebase.

- **R2.** Strategies compose bottom-up: primitive strategies (shapes, layers, numerical bounds, component specs) build into constraint strategies which build into full `PlacementState + list[BaseConstraint]` scenario generators. Each composite strategy accepts `draw(**kwargs)` to allow callers to constrain dimensions (e.g., max components, board size).

- **R3.** Strategies must generate edge cases by default: empty constraint sets, single-constraint scenarios, board-edge placements, overlapping constraints on different types (e.g., enclosing zone + separation rule on same components), and zero-size components. Edge-case generation uses Hypothesis's `@st.composite` combinators (`st.just()`, `st.sampled_from([])`, boundary-value `st.floats()`) rather than manual enumeration.

### Invariant Theorems

- **R4.** Loss function invariants are tested for all constraint types:
  - `assert loss >= 0.0` — total loss is always non-negative.
  - `assert loss <= eps` when all constraints are satisfied — zero loss iff constraints satisfied (floating-point tolerance `eps = 1e-6`).
  - `assert loss > eps` when any constraint is violated — strictly positive penalty for violations.

- **R5.** Per-constraint-type monotonicity is tested. Each constraint type has a well-defined "tightening" direction that increases the constraint's restrictiveness and must not decrease its individual penalty contribution. Tightening semantics per type:

  | Constraint Type      | Tightening Direction              |
  |----------------------|----------------------------------|
  | `AdjacentConstraint` | Reducing `max_distance_mm`       |
  | `SeparatedConstraint`| Increasing `min_distance_mm`     |
  | `EnclosingConstraint`| Increasing `margin_mm`           |
  | `AlignedConstraint`  | Reducing `tolerance_mm`          |
  | `OnSideConstraint`   | Reducing `max_distance_mm`       |
  | `AnchoredConstraint` | Reducing region size             |
  | `LoopAreaConstraint` | Reducing `max_area_mm2`          |

  For a given placement, tightening a single constraint of type T never decreases that constraint type's individual loss contribution: `assert loss_t(tightened_constraint, placement) >= loss_t(original_constraint, placement)`.

  **Important qualifying assumption:** Total-loss monotonicity (adding/removing constraints) is NOT guaranteed when constraints produce opposing gradients (e.g., a thermal zone favoring one board edge and an EMI zone penalizing that same edge). R5 tests per-constraint-type monotonicity only, not cross-constraint total-loss monotonicity. Cross-constraint interactions are documented as an open question (see Outstanding Questions).

- **R6.** Tier-weight ordering is tested across all constraint types: for a single constraint type with a fixed violation magnitude, `SOFT penalty < STRONG penalty < HARD penalty`. Strategies generate placements with a fixed violation magnitude and vary only the constraint tier; the test asserts strict ordering of resulting loss values.

### DAG-Level Contract Validation

- **R7.** Each stage's `provides` field (`list[str]`) declares output data keys produced by the stage. The stage's `contract` field (`Contract | None`) declares `output_schema: dict[str, type]` for type validation. At runtime, the DAG engine validates (a) that all keys in `provides` are present in the stage output, and (b) if `contract` is set, that each output key matches its declared type via `isinstance` check. Validation runs after every `_execute_stage()` invocation before outputs are stored into the DAG context dict.

- **R8.** Type mismatch produces a diagnostic `ContractViolation` containing: stage name, output key, expected type, actual type. The property test for this behavior uses a Hypothesis strategy that wraps stage output with deliberately wrong types and asserts the DAG engine raises the expected error.

### CI Integration

- **R9.** Hypothesis property tests run as a CI gate on every PR touching PCL code, the loss bridge, or constraint-related stage handlers. File filter covers `packages/temper-placer/src/**/pcl/**`, `packages/temper-placer/src/**/constraint*/**`, `packages/temper-placer/src/**/loss*/**`, and `tests/pcl/**`.

- **R10.** Property test configuration: `max_examples=100`, `deadline=30000` (30 seconds per test case). Hypothesis settings are applied via `@settings(max_examples=100, deadline=timedelta(seconds=30))` on each test class. CI may extend deadline to 60 seconds per test with a project-level override if CI hardware underperforms.

---

## Acceptance Examples

- **AE1.** Covers R4. Given a randomly generated placement where all components satisfy an enclosing constraint (generated via `st.composite` strategy that places components inside the enclosing zone boundary), when the enclosing constraint's loss function evaluates `loss(collection, placement)`, `assert loss <= 1e-6`.

- **AE2.** Covers R5. Given a placement with a component far enough from its neighbor to violate an `AdjacentConstraint` with `max_distance_mm=20`, and the same placement tested against the same constraint with `max_distance_mm` tightened to 10 (more restrictive), the loss for the tighter constraint is greater than or equal to the looser: `assert loss(adjacent_max10, placement) >= loss(adjacent_max20, placement)`.

- **AE3.** Covers R7, R8. Given the PCL input stage wraps legacy `PlacementConstraints` in its `StageResult.outputs` under the key `constraints`, but the stage declares `provides: ["constraints"]` and `contract.output_schema: {"constraints": ConstraintCollection}`, when the DAG engine validates the output after `_execute_stage()`, the pipeline raises `ContractViolation` with message: `"input_stage output 'constraints' expected ConstraintCollection, got PlacementConstraints"`.

- **AE4.** Covers R3, R9. Given CI runs on a PR that adds a new constraint type (e.g., a hypothetical `ThermalExclusionConstraint`) with an empty constraint-set edge case, a single-constraint case covering the entire board, and a mixed-constraint case with overlapping adjacent and separation constraints — all pass invariance checks within the `max_examples=100` generation budget.

---

## Success Criteria

- PCL silent-skip (`.pcl.yaml` auto-discovery failure producing wrong constraint type) is caught by property tests at CI time with a minimized counterexample, not weeks later in production.
- Adding a new constraint type to the PCL schema requires property-test coverage — CI rejects constraint types that lack invariant test coverage (enforced by test file convention and import check, not a hard schema validator).
- DAG contract validation catches constraint-type mismatch bugs at stage boundaries before downstream stages consume incorrectly-typed data.

---

## Scope Boundaries

- **Not formal verification.** No TLA+, Alloy, or Coq specifications. Hypothesis property-based testing is the verification strategy. This is randomized testing over the input space, not exhaustive proof.
- **Not SMT solving.** Z3-based verification of constraint interactions is a separate planned feature, not part of this test suite.
- **Not automatic test generation.** Invariant theorems and strategies are hand-written. PCL schema introspection for auto-generating tests is out of scope.
- **CI gate scope.** The property test CI gate applies to PCL code changes only (constraint types, loss bridge, constraint parsing, constraint stage handlers). It does not gate the full temper-placer pipeline on every PR.
- **No runtime monitoring.** The DAG contract validation is a test-time assertion and a CI gate. Production pipeline runs use whatever type the stage produces (existing behavior). Runtime in-production validation is a separate feature.

---

## Key Decisions

- **max_examples=100, deadline=30s.** Calibrated from the Router V6 property test suite, which achieved acceptable CI runtime with these settings. This provides statistically meaningful coverage (100 random scenarios per invariant) without bloating CI time.
- **Float tolerance eps=1e-6.** Monotonic invariants use `math.isclose` with `rel_tol=1e-6, abs_tol=1e-6` for zero-loss assertions. JAX's mixed-precision and asynchronous dispatch produce small residuals that this tolerance absorbs without masking genuine violations.
- **DAG validation is additive.** Existing stages with legacy types (e.g., `PlacementConstraints` instead of `ConstraintCollection`) get a migration window. The validation only checks stages whose contract declares the new PCL types. Legacy stages without PCL contracts are unaffected.
- **4-layer architecture reuse.** Tests follow the Router V6 pattern: (1) shared strategies module, (2) theorem classes organized by invariant category, (3) per-class test files with `@pytest.mark.property` + `@given(...)` + `@settings(...)`, (4) existing PCL test files in `tests/pcl/` are complemented by new property-test files — strategies are built from scratch since no prior PBT test files exist.

---

## Dependencies / Assumptions

- **Hypothesis library** is already a dev dependency and proven stable in CI (Router V6 suite uses it).
- **No existing PBT files.** No `test_keepout_pbt.py` or `test_tag_dispatch_pbt.py` exist in the codebase (stale `.pyc` cache files may exist, but no `.py` source files). All Hypothesis strategies must be built from scratch.
- **JAX non-determinism** across CPU/GPU/TPU backends is manageable with `eps=1e-6` tolerance thresholds. Empirical evidence from Router V6 suite confirms this holds for placement loss functions.
- **Constraint types referenced** (`ConstraintCollection`, `AdjacentConstraint`, `SeparatedConstraint`, `EnclosingConstraint`, `AlignedConstraint`, `OnSideConstraint`, `AnchoredConstraint`, `LoopAreaConstraint`, `PlacementState`) exist in the PCL schema and are importable from `temper_placer.pcl` and `temper_placer.core.state`.
- **DAG engine** (`runner.py`) supports `provides` (`list[str]`) and `contract` (`Contract | None` with `input_schema`/`output_schema` dicts) for post-stage output validation. The `Contract` class and `ContractViolation` exception exist in `protocol.py`. The runner already validates contracts at stage boundaries via `_check_output_contract` — the test suite exercises this existing behaviour.

---

## Outstanding Questions

### Resolve Before Planning

- [Affects R5] Monotonicity is scoped to per-constraint-type tightening only (see R5 per-type table). An explicit assumption accompanies this: "for constraint sets where no two constraints produce opposing gradients at any placement." The open question is whether to also test total-loss monotonicity under the stronger assumption that constraint sets are non-opposing, or accept that total-loss monotonicity is not guaranteed and test only per-type. User decision required.

- [Affects R7] Should DAG contract validation be a hard failure immediately (`ContractViolation`), or a `FutureWarning` during a migration window? The PCL silent-skip bug suggests hard failure is appropriate, but there may be unknown legacy consumers. The `Contract` class and `_check_output_contract` already exist in `runner.py` and raise on mismatch — the test suite exercises this behaviour as-is. User decision required on whether a migration window soft-failure mode is needed.

- [Affects R5] Is the per-type tightening direction correct for `AnchoredConstraint`? `AnchoredConstraint` supports either `region` (tuple of 4 floats) or `position` (tuple of 2 floats). Tightening semantics for `position` are not obvious (a point has no size to reduce). User decision required on whether `AnchoredConstraint` tightening is defined only for `region`-based anchors, or whether `position` anchors are excluded from tightening tests.

- [Affects R4] Per-type vs. aggregate zero-loss assertion. R4 defines `loss >= 0` and `loss <= eps` on the aggregate loss function. Individual constraint types may define loss differently (e.g., adjacency penalty activates above threshold, separation below threshold). User decision required on whether zero-loss equivalence is tested for each constraint type individually or only on the aggregate.

### Deferred to Planning

- [Affects R4] Appropriate floating-point tolerance for zero-loss assertion given JAX's mixed-precision (`bfloat16` vs `float32`) and asynchronous dispatch. 1e-6 works for `float32`; `bfloat16` may require 1e-3. Decision deferred until empirical measurements on CI hardware.
- [Affects R10] Whether `deadline=30000` (30 seconds) is feasible on CI hardware for all property tests. Router V6 suite achieved this, but PCL constraint types may have heavier loss function evaluation. Deferred to planning with a fallback to 60s per test.

(End of file - total 183 lines)
