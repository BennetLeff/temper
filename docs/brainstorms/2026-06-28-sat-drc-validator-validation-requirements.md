---
date: "2026-06-28"
topic: sat-drc-validator-validation
origin: "docs/ideation/2026-06-28-router-v6-mathematical-rigor-ideation.md"
ideas: [4, 9, 10]
status: draft
---

# SAT Solver + DRC Validator Correctness Validation

## 1. Problem / Motivation

The Router V6 pipeline has correctness gaps at both the constraint-encoding
end (Stage 3 SAT model) and the validation end (Stage 5 DRC validators):

- **SAT model has zero property-based tests.** `build_sat_model()` (`sat_model.py:80`)
  is an empty constructor. `test_sat_solve_pbt.py` contains trivially-passing
  placeholders that verify nothing about SAT solving. The AtMostK encoding
  (`_encode_at_most_k`, Sinz 2005 sequential counter) was validated via a
  one-off 4-layer template — that pattern hasn't been generalized. SAT
  encoding bugs produce *satisfiable* models that encode the *wrong*
  constraint, the hardest class of bug to detect.

- **DFM validators are not checked for completeness.** Every existing PBT
  property (`test_*_properties.py`, 8 files) checks that reported violations
  are genuine — `actual < required`. No test verifies the validator finds
  *all* violations. An optimized spatial-index clearance engine that
  silently misses 2% of close pairs across cell boundaries would pass every
  existing check.

- **No structural induction on DFM validators.** `test_layer_independence_add_disjoint_net`
  verifies adding a net on a *disjoint* layer doesn't change violations.
  No test adds a compliant route on the *same* layer, where spatial-index
  boundary cases create false positives. The critical meta-property —
  "adding compliant geometry never creates false violations" — is unverified.

These gaps compound: an SAT encoding bug creates topologically broken
routing that a false-negative DRC validator passes. The combined failure
mode ships an undetected manufacturing defect.

## 2. Users & Value

| User | Value |
|------|-------|
| Firmware/PCB developer iterating on router | Catches constraint-encoding regressions before they corrupt routing output |
| DFM module author adding a new validator | Induction template proves the new validator has no false-positive bugs |
| CI/release pipeline | Completeness oracle replaces "trust golden fixtures" with verifiable computation |
| Future maintainer replacing SAT solver or spatial index | Property lattice localizes failure to a specific constraint layer or validator |

## 3. Scope & Out of Scope

### In Scope

- SAT model property-based testing from single-clause through cross-constraint composition
- Brute-force O(n²) oracle for clearance-validator completeness on small boards
- Structural induction proof for every DFM validator (empty board base case + compliant-route-addition inductive step)
- Parsimony invariant: variable/clause count bounded by polynomial of (grid_cells, nets, layers)
- Shared Hypothesis strategies for SAT model generation (analogous to `dfm_property_strategies.py`)

### Out of Scope

- Metamorphic A* pathfinding properties (covered by idea #2 of the ideation)
- Pipeline stage contract enforcement / DRC fence extension (ideas #5, #6)
- Runtime monotonicity monitors for A* (idea #7)
- Replacing pysat/satispy with a different solver backend
- Completeness oracles for non-clearance DFM modules (creepage, annular ring, etc.) —
  out of scope for initial pass; the clearance oracle establishes the pattern
- Real-world large-board regression testing (golden fixture ladder covers that)

## 4. Functional Requirements

### SAT Solver Inductive Property Lattice

- **FR1.** Single-clause CNF PBT: For a strategy generating a single SAT clause
  over a finite variable set, assert a solution exists iff the clause is
  satisfiable. Verify via pysat ground-truth solve.
- **FR2.** Multi-clause conjunction PBT: For N random clauses (2 ≤ N ≤ 20),
  assert that every solution returned by the solver satisfies all input
  clauses. Cross-validate with exhaustive enumeration for ≤8 variables.
- **FR3.** Conflict-driven learned-clause PBT: Tests the Temper SAT model's
  interaction with incremental clause addition, not pysat internals. Starting
  from a known-satisfiable base model (passed by FR1/FR2), add clauses that
  refine the solution space. Assert the solution space shrinks monotonically
  and learned clauses never eliminate any assignment that satisfied all
  original clauses. This validates that the Temper wrapper correctly delegates
  incremental SAT operations to pysat without dropping or duplicating clauses.
- **FR4.** AtMostK encoding correctness: For all combinations of (n=2..16,
  k=0..n), assert via pysat that solutions to the Sinz-encoded formula match
  the set of assignments with ≤k true variables. Cross-validate against
  exhaustive enumeration for n ≤ 8.
- **FR5.** Cross-constraint composition: For small grid instances (≤4×4 cells,
  ≤3 nets, ≤2 layers), generate the full SAT model via
  `populate_sat_from_constraints`. **Before solving**, compare the actual
  clauses produced against a hand-specified expected clause set representing
  the routing problem. Then solve via pysat, and verify the returned channel
  assignments satisfy every individual constraint type (connectivity, layer
  restriction, capacity) independently. The clause-set comparison catches
  encoding bugs (wrong or missing clauses) that the solver cannot detect by
  satisfiability alone — preventing the circular validation problem where the
  solver is both the system under test and the oracle.
- **FR6.** Parsimony invariant: For any SAT model built from a constraint
  model with C cells, N nets, and L layers, assert that
  `variable_count ≤ 100·C·N·L` and `clause_count ≤ 200·C·N·L`. These are
  generous initial bounds; they will tighten after profiling real SAT builds.
  Verifies the encoding doesn't explode combinatorially.
- **FR7.** The SAT property lattice must be orderable: Level 1 tests must pass
  before Level 2 is diagnostic (single-clause → multi-clause → CDCL →
  cross-constraint). A failure at Level N with all prior levels passing
  isolates the regression to the constraint type introduced at Level N.

### DRC Validator Completeness via Brute-Force Oracle

- **FR8.** Brute-force Oracle: Implement an O(n²) pair-check function that
  iterates over all segment pairs in compiled routes and reports every pair
  with clearance < threshold. This oracle must have zero dependencies on the
  production `clearance_engine` — it must duplicate no code path.
- **FR9.** Completeness assertion: For routings with ≤10 routes (≤500 total
  segments), run both the production `verify_clearance()` and the brute-force
  oracle. Assert that the violation sets are *identical* — same (net1, net2,
  layer) tuples, matching `actual_clearance` within floating-point epsilon.
- **FR10.** Near-boundary fuzzing: The input strategy for completeness tests
  must bias coordinates toward grid cell boundaries (e.g., positions within
  0.01mm of multiples of the spatial-index cell size), where
  boundary-crossing false-negatives are most likely.
- **FR11.** The completeness test must run as Hypothesis PBT with ≥200
  iterations and a deadline of 5000ms per iteration (the brute-force oracle
  is O(n²) but n is small).
- **FR11b (deferred).** Extend the completeness oracle pattern to creepage
  and acid traps. After the clearance oracle establishes the pattern (FR8–FR11),
  implement O(n²) brute-force oracles for creepage distance and acid trap angle
  checks, with the same "zero shared code path" constraint. This is deferred
  past the initial pass; clearance is the highest-risk module and proves the
  approach.

### Inductive DRC Validator Correctness

- **FR12.** Empty-board base case: For every DFM validator
  (`verify_clearance`, `verify_creepage`, `detect_acid_traps`,
  `check_annular_ring`, `generate_thermal_relief`, `check_copper_balance`,
  `generate_teardrops`, `build_manufacturing_report`), assert that
  `validator(RoutingResults(compiled_routes={}, failed_nets=[]))` produces
  zero violations.
- **FR13.** Compliant-route addition inductive step: Generate a
  `CompiledRoute` whose geometry is known-compliant (trace width ≥ minimum,
  clearance to all other geometry ≥ required, no acute angles producing
  acid traps, etc.), add it to a routing result that currently passes all
  validators, and assert the result still passes every validator. This
  must include same-layer additions (the gap left by
  `test_layer_independence_add_disjoint_net`).
- **FR13b.** Route modification inductive step: Starting from a routing result
  that passes all validators, modify an existing compliant route (e.g., shift
  a segment, reroute a path while preserving all clearance/width constraints)
  and assert the result still passes every validator. This catches spatial-index
  update bugs triggered by mutations rather than additions.
- **FR13c.** Route removal inductive step: Starting from a routing result that
  passes all validators, remove a compliant route and assert the result still
  passes every validator. This catches stale-index bugs where removal fails to
  update the spatial index, causing phantom violations from deleted geometry.
- **FR14.** The "known-compliant" geometry strategy must itself be verified:
  a separate test asserts that a routing containing *only* known-compliant
  routes passes all validators (bootstraps the strategy's correctness).
- **FR15.** The inductive tests must run for every DFM validator, not just
  clearance. Each validator gets its own `test_<module>_induction.py`
  following the existing per-module convention established by
  `test_<module>_properties.py`.

## 5. Non-Functional Requirements

- **NFR1.** All new PBT tests must use Hypothesis ≥6.148.7 with the
  `@given` + `@settings` decorator pattern, matching the existing DFM
  property test convention. Failures must produce actionable counterexample
  output.
- **NFR2.** Brute-force oracle execution time must not block the CI test
  pass. If O(n²) exceeds budget for larger n, use adaptive iteration count
  (fewer Hypothesis examples for larger n).
- **NFR3.** The completeness oracle must live in a separate file
  `clearance_oracle.py` in the same package as `clearance_engine`, independent
  from `clearance_check.py`. This ensures zero shared code paths with the
  production clearance engine while staying in the same package to track
  `RoutingResults`/`CompiledRoute` API changes. It must be gated by
  `if __debug__` to exclude from production deployments.
- **NFR4.** SAT property tests must not import or depend on the JAX runtime.
  The SAT model is pure Python dataclasses — the tests must run without GPU
  acceleration.
- **NFR5.** Failure localization: When a property test fails, the assertion
  message must identify which specific constraint type, variable, or
  (net1, net2, layer) tuple caused the violation.
- **NFR6.** Initial parsimony bounds: `variable_count ≤ 100·C·N·L`,
  `clause_count ≤ 200·C·N·L`, where C=cells, N=nets, L=layers. These are
  generous; they will tighten after profiling real SAT builds.
- **NFR7.** The SAT property lattice (FR7) ordering must be enforced in CI
  via `pytest-dependency` markers or sequential CI stages, so that Level N
  failures prevent execution of Level N+1 tests. Running all levels on a
  Level 1 failure wastes CI time and obscures the diagnostic signal.

## 6. Success Criteria

- **SC1.** Every SAT property test (FR1–FR6) passes ≥200 Hypothesis
  iterations within a 5000ms deadline per iteration.
- **SC2.** The AtMostK encoding (FR4) is cross-validated against exhaustive
  enumeration for all n ≤ 8 with 100% agreement.
- **SC3a.** Seeded bug detection: The completeness oracle (FR8–FR9) detects
  at least one seeded clearance false-negative (a known violation placed at
  0.01mm below threshold that the production engine misses) *or* confirms
  zero false-negatives on seeded tests. This gates further exploration.
- **SC3b.** After SC3a passes, the completeness oracle runs ≥200
  boundary-biased Hypothesis iterations and either finds a previously-unknown
  false-negative *or* confirms zero false-negatives across the full run.
- **SC4.** Every DFM validator (8 modules) passes the empty-board base case
  (FR12) and the compliant-route-addition inductive step (FR13) consistently.
- **SC5.** Adding a knowingly non-compliant route (clearance violation seeded
  at 0.01mm below threshold) to an otherwise-compliant board is detected by
  the corresponding validator — confirming the inductive step doesn't mask
  true violations.
- **SC6.** The SAT property lattice (FR7) produces a clear diagnostic when
  deliberately injected encoding bugs are introduced: a bug in the AtMostK
  encoding fails FR4 but passes FR1–FR3; a bug in layer constraints fails FR5
  but passes FR1–FR4.
- **SC7.** All existing DFM property tests (`test_*_properties.py`,
  `test_dfm_hypothesis_fuzzing.py`) continue to pass unchanged (additive,
  no regression).

## 7. Dependencies & Assumptions

- **A1.** pysat (python-sat) is available as a test dependency for ground-truth
  SAT solving. If not yet in the dependency tree, it must be added under
  `[project.optional-dependencies] test`.
- **A2.** The `SATModel` / `SATClause` / `SATVariable` dataclasses are stable
  enough to build generation strategies against. The `.literals` and `.name`
  attributes are the test surface.
- **A3.** The `populate_sat_from_constraints` function produces correct clause
  structure for standard constraint types. Edge cases in constraint
  interaction may surface during cross-constraint composition testing and
  are in-scope to fix.
- **A4.** `clearance_engine.get_clearance` is the sole optimized path for
  clearance checking. The brute-force oracle will be a separate code path.
- **A5.** `RoutingResults.compiled_routes` is a `dict[str, CompiledRoute]`
  and `CompiledRoute.path.coordinates` provides `list[tuple[float, float]]`.
  Segment endpoints are adjacent coordinate pairs.
- **A6.** The existing `dfm_property_strategies.py` pattern (shared
  Hypothesis strategies for DFM modules) will be replicated for SAT model
  strategies in a new `sat_property_strategies.py` module.
- **A7.** DFM validator public APIs are as listed in the DFM property tests
  plan (`docs/plans/2026-06-25-dfm-property-tests-plan.md`, U1–U8).

## 8. Open Questions

- **Q1.** Should the brute-force completeness oracle use segment-segment
  distance (identical algorithm to production) or a simpler point-to-point
  sampling approach that's easier to verify by inspection? Segment-segment
  is the correct comparison but duplicates the distance algorithm.
  *Recommendation: segment-segment with a simpler implementation (no
  spatial index, no early-out optimization).*

- **Q2.** Does the compliant-route generation strategy (FR13) need to handle
  all DFM constraint interactions simultaneously (e.g., a route must satisfy
  clearance, creepage, acid-trap angle minimums, annular ring minimums, AND
  copper balance limits)? Or is per-validator isolation sufficient?
  *Recommendation: per-validator isolation first (each validator gets its own
  "known-compliant" strategy for its specific constraints). Joint-compliance
  is deferred.*

- **Q3.** For the induction base case (FR12), some validators may crash on
  empty input rather than returning zero violations. Should the requirement
  be "zero violations" or "no unhandled exception"?
  *Recommendation: zero violations. A crash on empty input is a bug to fix,
  not a test to skip.*

- **Q4.** Should the SAT property lattice tests live in
  `tests/router_v6/test_sat_properties.py` (single file, multi-level) or
  `tests/router_v6/test_sat_lattice_level{1,2,3,4}.py` (per-level files)?
  *Recommendation: single file with clearly sectioned levels, matching the
  existing `test_sat_model.py` location. The lattice structure is
  conceptually a single test suite.*

- **Q5.** The `test_sat_solve_pbt.py` file contains dummy PBT tests that
  verify nothing. Should FR1–FR7 replace or live alongside it?
  *Recommendation: replace. The dummy tests provide zero value and their
  continued existence would be misleading next to real property tests.*

## 9. Alternatives Considered

| Alternative | Rejected Because |
|---|---|
| SMT-based verification (Z3) instead of PBT | Heavyweight dependency; PBT with pysat oracle gives 90% of the value at 20% of the integration cost. SMT remains a Phase-2 depth item. |
| Exhaustive enumeration for all n up to 16 instead of pysat cross-validation | Exponential — 2^16 = 65536 assignments feasible but 2^32 is not. pysat is the industry-standard ground truth. |
| Multi-validator completeness oracle (all DFM modules at once) | Each module has different violation semantics. Clearance is the highest-risk module (spatial-index boundary cases). Establish the pattern first, extend later. |
| Brute-force oracle inside the production `clearance_check.py` instead of separate module | Couples oracle correctness to the module being tested. Independent code path is the whole point of an oracle. |
| Induction via formal proof (Coq/Lean) instead of PBT | The DFM validators are Python functions with floating-point arithmetic — formal verification of imperative float code is a research challenge. PBT is the right tool for this level. |
| No completeness testing — trust golden fixtures + validity checks | The AtMostK bug proved both Python and Rust golden fixtures encoded the same wrong answer. Validity checks cannot detect missing violations. Completeness is the missing dimension. |
