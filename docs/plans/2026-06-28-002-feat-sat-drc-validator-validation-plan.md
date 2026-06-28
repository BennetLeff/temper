---
title: "SAT Solver + DRC Validator Correctness Validation"
date: "2026-06-28"
status: active
depth: deep
source: "docs/brainstorms/2026-06-28-sat-drc-validator-validation-requirements.md"
origin: "docs/ideation/2026-06-28-router-v6-mathematical-rigor-ideation.md"
---

## Summary

Add three validation suites to close correctness gaps in the Router V6 pipeline:
(1) a **SAT inductive property lattice** (FR1–FR7) with clause-set comparison
that catches encoding bugs the solver cannot detect by satisfiability alone,
(2) a **DRC completeness oracle** (FR8–FR11) using an O(n²) independent
clearance implementation to verify the production engine finds *all*
violations, and (3) **inductive DRC validator proofs** (FR12–FR15) for
all 8 DFM modules (empty-board base case + compliant-route-addition plus
modification/removal inductive steps).  Together these replace
placeholder tests and validity-only checks with verifiable computation.

## Problem Frame

The Router V6 pipeline has correctness gaps at both the constraint-encoding
end (Stage 3 SAT model) and the validation end (Stage 5 DRC validators):

- **SAT side:** `build_sat_model()` (`sat_model.py:80`) is an empty
  constructor.  `test_sat_solve_pbt.py` contains trivially-passing
  placeholders (e.g., `if v == 0 and c == 0: assert True`).  The Sinz-2005
  AtMostK encoding was validated via a one-off 4-layer template that was
  never generalized.  SAT encoding bugs produce satisfiable models that
  encode the **wrong constraint** — the hardest class of bug to detect.

- **DRC completeness:** Every existing PBT property (`test_*_properties.py`,
  8 files) checks that reported violations are genuine (`actual < required`).
  No test verifies the validator finds *all* violations.  An optimized
  spatial-index engine that silently misses 2% of close pairs across cell
  boundaries would pass every existing check.

- **Inductive gap:** `test_layer_independence_add_disjoint_net` verifies
  adding a net on a *disjoint* layer doesn't change violations, but no test
  adds a compliant route on the *same* layer where spatial-index boundary
  cases create false positives.  Route modification and removal — operations
  that exercise spatial-index update/delete paths — are entirely unverified.

These gaps compound: an SAT encoding bug creates topologically broken routing
that a false-negative DRC validator passes, shipping an undetected
manufacturing defect.

## Requirements Traceability

Every functional requirement (FR1–FR15), non-functional requirement
(NFR1–NFR7), and success criterion (SC1–SC7) from the origin document maps
to an implementation unit below.

| Requirement | Unit | Description |
|---|---|---|
| FR1 | U1 | Single-clause CNF PBT with pysat ground-truth |
| FR2 | U1 | Multi-clause conjunction PBT, cross-validate ≤8 vars |
| FR3 | U1 | CDCL incremental-clause PBT (Temper wrapper, not pysat internals) |
| FR4 | U2 | AtMostK encoding correctness (n=2..16, k=0..n) |
| FR5 | U3 | Cross-constraint composition with clause-set comparison |
| FR6 | U4 | Parsimony invariant (variable/clause count bounds) |
| FR7 / NFR7 | U1–U4, U13 | Lattice ordering enforced via pytest-dependency |
| FR8–FR11 | U5–U7 | Brute-force clearance oracle + completeness PBT |
| FR11b | Deferred | Creepage/acid-trap completeness oracle (deferred past initial pass) |
| FR12 | U8 | Empty-board base case for all 8 DFM validators |
| FR13 | U9 | Compliant-route-addition inductive step for all 8 DFM validators |
| FR13b | U10 | Route modification inductive step |
| FR13c | U11 | Route removal inductive step |
| FR14 | U12 | Known-compliant strategy bootstrap verification |
| FR15 | U8–U11 | Per-module induction files following existing convention |
| NFR1 | U1–U12 | Hypothesis ≥6.148.7 with @given + @settings decorator pattern |
| NFR2 | U7 | Adaptive iteration count for O(n²) oracle deadline |
| NFR3 | U5 | `clearance_oracle.py` separate from `clearance_check.py`, gated by `if __debug__` |
| NFR4 | U1–U4 | SAT property tests must not import JAX runtime |
| NFR5 | U1–U12 | Assertion message identifies specific constraint/variable/(net1,net2,layer) |
| NFR6 | U4 | Parsimony bounds: variable_count ≤ 100·C·N·L, clause_count ≤ 200·C·N·L |
| SC1 | U1–U4 | ≥200 Hypothesis iterations, 5000ms deadline per iteration |
| SC2 | U2 | AtMostK cross-validated against exhaustive enumeration for all n ≤ 8 |
| SC3a | U6 | Seeded bug detection gate |
| SC3b | U7 | Boundary-biased fuzzing detects or confirms zero false-negatives |
| SC4 | U8–U11 | Every DFM validator passes base case + inductive steps |
| SC5 | U9 | Non-compliant route detected by corresponding validator |
| SC6 | U13 | Lattice diagnostic correctness with deliberately injected bugs |
| SC7 | U1–U12 | All existing DFM property tests continue to pass unchanged |

## Key Technical Decisions

### 1. `clearance_oracle.py` separate from `clearance_check.py`

The brute-force completeness oracle lives at
`packages/temper-placer/src/temper_placer/router_v6/clearance_oracle.py` —
in the same package as `clearance_check.py` (to track
`RoutingResults`/`CompiledRoute` API changes without cross-package
churn) but in a separate file with zero code-path overlap with the
production `clearance_engine` or `clearance_check`.  The entire file is
gated by `if __debug__:` to exclude from production deployments (NFR3).
It duplicates no imports, no helper functions, and no distance-computation
logic from `clearance_check.py`.

### 2. Parsimony bounds: 100·C·N·L and 200·C·N·L

Initial bounds (NFR6) are `variable_count ≤ 100·C·N·L` and
`clause_count ≤ 200·C·N·L`, where C=cells, N=nets, L=layers.  These
are generous — a fully-connected 100-cell routing problem with 50 nets
on 4 layers would allow up to 2M variables and 4M clauses.  The bounds
will tighten after profiling real SAT builds.  The factor difference
(variables ×2 ≈ clauses) comes from the Sinz sequential-counter
auxiliary variable overhead.

### 3. FR5 clause-set comparison (explicit expected-clause check)

The cross-constraint composition test (FR5/U3) does **not** use the SAT
solver as an oracle.  Instead, for small grid instances (≤4×4 cells, ≤3
nets, ≤2 layers), it asserts that `populate_sat_from_constraints` produces
the exact set of clauses — including auxiliary Sinz counter variables and
their clauses — that matches a hand-specified expected set.  This catches
encoding bugs (wrong or missing clauses) that the solver cannot detect by
satisfiability alone, preventing the circular validation problem where the
solver is both system under test and oracle.

### 4. SC3 split: seeded gate (3a) then boundary fuzzing (3b)

SC3 is split into two sequential sub-criteria:
- **SC3a (U6):** A seeded test places a known clearance violation at
  0.01mm below threshold and asserts the production engine misses it
  *or* the oracle catches it.  This gates further exploration — if the
  production engine already catches everything, the completeness gap
  is zero and SC3b is a confirmation run.
- **SC3b (U7):** After SC3a passes, run ≥200 boundary-biased Hypothesis
  iterations.  Either find a previously-unknown false-negative or confirm
  zero false-negatives across the full run.

### 5. `pytest-dependency` for lattice ordering

The SAT property lattice (FR7/NFR7) is enforced via `pytest-dependency`
markers: `@pytest.mark.dependency(name="sat-l1")` on single-clause tests,
`@pytest.mark.dependency(depends=["sat-l1"])` on multi-clause tests, etc.
A Level N failure prevents execution of Level N+1 tests, avoiding wasted
CI time and preserving the diagnostic signal.

### 6. FR13b/13c: route modification and removal inductive steps

Two supplementary inductive steps go beyond the basic addition step (FR13):
- **FR13b (U10):** Modify an existing compliant route (e.g., shift a
  segment, reroute a path while preserving all clearance/width constraints)
  and assert the result still passes every validator.  Catches
  spatial-index update bugs triggered by mutations.
- **FR13c (U11):** Remove a compliant route and assert the result still
  passes every validator.  Catches stale-index bugs where removal fails to
  update the spatial index, causing phantom violations from deleted geometry.

### 7. FR11b deferred: creepage/acid-trap completeness

Extending the brute-force completeness oracle pattern to creepage and
acid traps is deferred past the initial pass.  Clearance is the
highest-risk module (spatial-index boundary cases) and proves the
approach.  The pattern is documented in the plan for future execution.

## Implementation Units

### U1. SAT Single-Clause / Multi-Clause / CDCL Lattice Levels 1–3

- **Goal:** Replace `test_sat_solve_pbt.py` dummy tests with real
  Hypothesis PBT covering single-clause satisfiability (FR1),
  multi-clause conjunction (FR2), and CDCL incremental clause
  refinement (FR3).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_sat_solve_pbt.py` *(rewrite)*
- **Dependencies:** U15 (sat_property_strategies), pysat (test dependency)
- **Approach:**
  - FR1: Strategy generates a single SAT clause over a finite variable
    set (2–20 vars).  Encode via pysat, solve, assert sat iff clause is
    satisfiable.  Cross-validate with exhaustive enumeration for ≤8 vars.
  - FR2: Strategy generates N random clauses (2 ≤ N ≤ 20).  Assert every
    pysat solution satisfies all input clauses.  Exhaustive cross-validation
    for ≤8 vars.
  - FR3: Start from a known-satisfiable base model (passed by FR1/FR2),
    add clauses that refine the solution space.  Assert the solution space
    shrinks monotonically and learned clauses (Temper CDCL wrapper on
    pysat `IncrementalSAT`) never eliminate any assignment that satisfied
    all original clauses.
  - Each level marked with `@pytest.mark.dependency` for lattice ordering.
- **Test Scenarios:**
  - TS1. Single unit clause `(x0 ∨ ¬x1 ∨ x2)` → satisfiable, pysat agrees
  - TS2. Empty clause `()` → unsatisfiable, pysat agrees
  - TS3. Two contradictory clauses `(x0)` and `(¬x0)` → unsatisfiable
  - TS4. 10 random clauses over 6 vars → all solutions satisfy all clauses
  - TS5. CDCL: add exclusion clause to known-sat model → solution space
    shrinks, no original solutions lost
- **Verification:** SC1 (≥200 iterations, 5000ms deadline), SC6 (injected
  bug in single-clause encoding fails FR1 but passes nothing below it).
- **Patterns to Follow:** `@settings(max_examples=200, deadline=5000)`,
  `@given` decorator, Hypothesis `assume` for filtering.

### U2. AtMostK Encoding Correctness

- **Goal:** Exhaustively verify the Sinz-2005 sequential counter encoding
  (`_encode_at_most_k` in `sat_model.py:217`) for all n=2..16, k=0..n (FR4).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_sat_solve_pbt.py` *(same file as U1,
  separate test function)*
- **Dependencies:** U1 (same file, lattice Level 2), pysat
- **Approach:**
  - For each (n, k) pair, construct n primary variables, call
    `_encode_at_most_k` to add auxiliary variables and clauses.
  - Solve via pysat; enumerate all solutions.
  - Assert the solution set matches the set of assignments with ≤k true
    variables.
  - Cross-validate against exhaustive enumeration for n ≤ 8 with 100%
    agreement.
  - For n ∈ [9, 16], validate via pysat all-solutions enumeration
    (the counter encoding is tractable at these sizes).
  - Property: number of solutions = sum(binom(n, i) for i=0..k).
  - Boundary cases: k=0, k=n-1, k=n, n=2 k=1 (classic pairwise
    exclusion).
- **Test Scenarios:**
  - TS1. n=2, k=1 → solutions: (0,0), (1,0), (0,1) — exactly 3
  - TS2. n=4, k=0 → solutions: (0,0,0,0) — exactly 1
  - TS3. n=4, k=3 → all 16 vectors except (1,1,1,1) — exactly 15
  - TS4. n=8 exhaustive: pysat solution count == sum(binom(8, i))
  - TS5. n=16, k=5: pysat all-solutions enumeration produces expected count
- **Verification:** SC2 (n ≤ 8 exhaustive cross-validation at 100%
  agreement), SC1 (≥200 iterations, ≤5000ms per (n,k) pair).
- **Patterns to Follow:** Boundary value enumeration, `pytest.mark.parametrize`
  for (n, k) pairs.

### U3. Cross-Constraint Composition with Clause-Set Comparison

- **Goal:** Verify that `populate_sat_from_constraints` produces the
  exact expected clauses for small grid instances, then solve and verify
  assignments satisfy all constraint types independently (FR5).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_sat_solve_pbt.py` *(same file,
  lattice Level 4)*
- **Dependencies:** U1, U2, U15, `constraint_model.ModelBuilder`
- **Approach:**
  - Strategy generates a `ConstraintModel` with a known set of variables
    and constraints for a ≤4×4 grid, ≤3 nets, ≤2 layers.
  - **Before solving:** Call `populate_sat_from_constraints` and compare
    the produced clause set against a hand-specified expected clause set.
    The expected set includes connectivity clauses (each net must use ≥1
    channel), layer-restriction unit clauses, diff-pair equivalence
    clauses, capacity AtMostK clauses with their auxiliary Sinz variables.
    Assert exact-match on the clause set (same literals, same variable
    names modulo ordering).
  - **Then solve:** Solve via pysat and verify the returned channel
    assignments satisfy every individual constraint type independently
    (connectivity, layer restriction, capacity).
- **Test Scenarios:**
  - TS1. 2×2 grid, 1 net, 1 layer → connectivity clause + layer
    restriction → exact clause-set match + assignments satisfy both
  - TS2. 2×2 grid, 1 diff pair, 1 layer → diff-pair equivalence
    clauses + connectivity → clause-set match + assignments satisfy both
  - TS3. 3×3 grid, 3 nets, 1 layer → connectivity + capacity (AtMostK)
    → clause-set match including auxiliary Sinz vars
  - TS4. 4×4 grid, 2 nets, 2 layers → all constraint types composed
  - TS5. Deliberately wrong clause-set in expected: test catches mismatch
- **Verification:** SC1 (≥200 iterations), SC6 (injected encoding bug
  in layer constraints fails FR5 but passes FR1–FR4).
- **Patterns to Follow:** Constraint model construction via
  `ModelBuilder`, `pysat.Solver` for satisfiability, explicit
  clause-set data structures for comparison.

### U4. Parsimony Invariant

- **Goal:** Assert that SAT model variable and clause counts stay within
  polynomial bounds (FR6, NFR6).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_sat_solve_pbt.py` *(same file,
  standalone property, lattice Level 5)*
- **Dependencies:** U3, `constraint_model`, `populate_sat_from_constraints`
- **Approach:**
  - Strategy generates `ConstraintModel` instances with varied C (cells),
    N (nets), L (layers).  Call `populate_sat_from_constraints`.
  - Compute C = number of unique channels (edge IDs), N = number of nets,
    L = number of distinct layers.
  - Assert `model.variable_count ≤ 100 * C * N * L`.
  - Assert `model.clause_count ≤ 200 * C * N * L`.
  - Assert both counts are non-negative.
  - Verify the bounds are non-trivial: for a 10-cell, 5-net, 2-layer
    problem, the bound is 100·10·5·2 = 10,000 vars — the actual count
    should be far below this.  If it approaches the bound, something
    is wrong.
- **Test Scenarios:**
  - TS1. Empty constraint model (C=0 or N=0) → variable_count=0, clause_count=0
  - TS2. 10-cell, 3-net, 2-layer model → variable_count << 6,000,
    clause_count << 12,000
  - TS3. 50-cell, 10-net, 4-layer model → variable_count << 200,000,
    clause_count << 400,000
  - TS4. Monotonicity: increasing cells increases vars/clauses
- **Verification:** SC1 (properties hold across ≥200 iterations).
- **Patterns to Follow:** PBT with Hypothesis `@given`, integer
  strategies for grid dimensions.

### U5. Brute-Force Clearance Oracle

- **Goal:** Implement an O(n²) pair-check function with zero dependencies
  on the production `clearance_engine` or `clearance_check.py` (FR8, NFR3).
- **Files:**
  `packages/temper-placer/src/temper_placer/router_v6/clearance_oracle.py` *(new)*
- **Dependencies:** `RoutingResults`, `CompiledRoute`, `math`
- **Approach:**
  - File gated by `if __debug__:` to exclude from production (NFR3).
  - Function `oracle_clearance_violations(routing_results, min_clearance)`
    returns a set of `(net1, net2, layer, actual_clearance)` tuples.
  - Implements its own segment extraction from `CompiledRoute.path`
    (handles both `RoutePath` with `.coordinates` and `RoutePath3D`
    with `.segments`).
  - Own segment-to-segment distance computation — a simpler
    implementation of the clamped-projection algorithm (no spatial
    index, no early-out optimization per Q1 recommendation).
  - Own width handling: extracts `width_mm` from each route.
  - Own via-to-segment distance computation for cross-layer
    violations.
  - Zero imports from `clearance_check.py` or `clearance_engine.py`.
  - Does import from `routing_results.py` (data models, no logic).
- **Test Scenarios:**
  - TS1. Two parallel traces 0.1mm apart on F.Cu with min_clearance=0.127
    → oracle detects violation, actual=0.1-0.127-0.127
  - TS2. Two traces 1.0mm apart with min_clearance=0.127 → no violation
  - TS3. Via-to-trace: via at (0,0), trace y=0.05, min_clearance=0.2
    → violation detected
  - TS4. Empty routing results → empty violation set
  - TS5. Deterministic: same input run twice → identical output
- **Verification:** Unit-tested by the completeness test (U6) itself.
  The oracle is correct if it matches a manual O(n²) spot-check on
  known fixtures and produces deterministic output.

### U6. Seeded Bug Detection Gate (SC3a)

- **Goal:** Verify the completeness oracle can detect a deliberately
  seeded false-negative that the production engine misses (SC3a).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_clearance_properties.py` *(add
  test function)*
- **Dependencies:** U5, `verify_clearance`, `clearance_oracle`
- **Approach:**
  - Construct a routing with two routes placed exactly at
    `(min_clearance - 0.01)` mm apart in a region that crosses a
    spatial-index cell boundary.  The production engine uses a
    spatial-index optimization (`clearance_engine`) that may
    partition segments across cells — place the two segments such
    that they span adjacent grid cells.
  - Run both `verify_clearance()` and `oracle_clearance_violations()`.
  - If the oracle finds a violation the production engine missed, report
    the missed violation details (net1, net2, layer, actual, required).
  - If the production engine catches it, confirm zero false-negatives
    on the seeded fixture and proceed to SC3b.
- **Test Scenarios:**
  - TS1. Two segments on F.Cu, edge-to-edge distance = 0.117mm
    (0.01mm below 0.127mm threshold), endpoints at
    (0.0, 0.0)→(10.0, 0.0) and (0.0, 0.127)→(10.0, 0.127)
    → actual = 0.127 - 0.01 = 0.117 < 0.127 → violation expected
  - TS2. Two segments crossing a spatial-index cell boundary at x=5.0
    with the same geometry as TS1
  - TS3. Via at (0, 0) with trace at y = min_clearance - 0.01
    → violation expected
- **Verification:** SC3a — either detects a seeded false-negative
  or confirms zero false-negatives on seeded tests.

### U7. Boundary-Biased Completeness Fuzzing (SC3b)

- **Goal:** Run ≥200 boundary-biased Hypothesis iterations comparing
  the production engine against the brute-force oracle (FR9–FR11, SC3b).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_clearance_properties.py` *(add
  test function)*
- **Dependencies:** U5, U6, `verify_clearance`, `clearance_oracle`,
  U15 (boundary-biased routing strategy)
- **Approach:**
  - Strategy generates `RoutingResults` with ≤10 routes (≤500 total
    segments per NFR2).  Coordinates are biased toward grid cell
    boundaries: positions within 0.01mm of multiples of the
    spatial-index cell size (FR10).
  - Run `verify_clearance()` → production violation set P.
  - Run `oracle_clearance_violations()` → oracle violation set O.
  - Assert P == O — same `(net1, net2, layer)` tuples, matching
    `actual_clearance` within floating-point epsilon (1e-9).
  - If P != O, report detailed diff: violations in O not in P
    (false-negatives), violations in P not in O (check oracle bug
    or production false-positive).
  - Use adaptive minimum `max_examples` based on segment count:
    ≥200 for small boards, ≥100 for medium.
- **Test Scenarios:**
  - TS1. Fuzzed: 200 iterations with ≤5 routes each → P == O
  - TS2. Fuzzed: boundary-biased coordinates that land exactly on
    spatial-index cell edges → P == O
  - TS3. Via-heavy routing (5 routes, 20 vias) → P == O
  - TS4. Mixed-layer routing (F.Cu + In1.Cu) → P == O
- **Verification:** SC3b — either finds a previously-unknown
  false-negative or confirms zero false-negatives across the full run.
- **Patterns to Follow:** `@settings(max_examples=200, deadline=5000)`,
  `@given` with composite strategy from U15, floating-point comparison
  with `math.isclose(rel_tol=1e-9, abs_tol=1e-9)`.

### U8. Empty-Board Induction Base Case for All 8 DFM Validators

- **Goal:** Assert every DFM validator produces zero violations on empty
  input (FR12).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_induction_base.py` *(new)*
- **Dependencies:** All 8 DFM modules, `RoutingResults(compiled_routes={},
  failed_nets=[])`
- **Approach:**
  - Parameterized test: iterate over all 8 DFM validators:
    `verify_clearance`, `verify_creepage`, `detect_acid_traps`,
    `check_annular_rings`, `generate_thermal_relief`,
    `check_copper_balance`, `generate_teardrops`, `build_manufacturing_report`.
  - For each, call `validator(RoutingResults(compiled_routes={},
    failed_nets=[]))` and assert the result has zero violations
    (or equivalent — e.g., `manufacturing_report.total_violations == 0`
    accounting for copper-balance sentinel of 4 unbalanced empty layers).
  - If any validator crashes on empty input, that is a bug to fix
    (per Q3 recommendation: zero violations, not "no unhandled exception").
- **Test Scenarios:**
  - TS1. `verify_clearance` → `ClearanceReport(violations=[], total_checks=0)`
  - TS2. `verify_creepage` → `CreepageReport(violations=[])`
  - TS3. `detect_acid_traps` → `AcidTrapReport(acid_traps=[])`
  - TS4. `check_annular_rings` → `AnnularRingReport(violations=[])`
  - TS5. `generate_thermal_relief` → `ThermalReliefReport(thermal_reliefs=[])`
  - TS6. `check_copper_balance` → `CopperBalanceReport(layer_balances=[...],
    balanced_layer_count=0, unbalanced_layer_count=4)`
  - TS7. `generate_teardrops` → `TeardropReport(teardrop_count=0)`
  - TS8. `build_manufacturing_report` → `ManufacturingReport(...)` with
    sentinel-aware `total_violations`
- **Verification:** SC4 (all 8 validators pass empty-board base case).
- **Patterns to Follow:** `pytest.mark.parametrize` for validator
  iteration, existing empty-board tests in
  `test_dfm_hypothesis_fuzzing.py` (empty-is-zero invariant).

### U9. Compliant-Route-Addition Inductive Step for All 8 DFM Validators

- **Goal:** For each DFM validator, generate a known-compliant
  `CompiledRoute` and assert that adding it to a passing routing result
  keeps the result passing (FR13).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_clearance_induction.py` *(new)*
  `packages/temper-placer/tests/router_v6/test_creepage_induction.py` *(new)*
  `packages/temper-placer/tests/router_v6/test_acid_trap_induction.py` *(new)*
  `packages/temper-placer/tests/router_v6/test_annular_ring_induction.py` *(new)*
  `packages/temper-placer/tests/router_v6/test_thermal_relief_induction.py` *(new)*
  `packages/temper-placer/tests/router_v6/test_copper_balance_induction.py` *(new)*
  `packages/temper-placer/tests/router_v6/test_teardrop_induction.py` *(new)*
  `packages/temper-placer/tests/router_v6/test_manufacturing_report_induction.py` *(new)*
- **Dependencies:** U12 (known-compliant strategies), U8 (base case
  passing)
- **Approach:**
  - Per-validator isolation per Q2 recommendation (`test_<module>_induction.py`
    following the existing per-module convention per FR15).
  - Each file: generate a routing result with 2–5 routes that passes
    the target validator, then add one known-compliant route.  Assert
    the validator still returns zero violations (or no increase for
    modules like copper_balance where some increase is expected).
  - This includes same-layer additions (the gap left by
    `test_layer_independence_add_disjoint_net`).
  - Non-compliant variant (SC5): also add a route with a *seeded
    violation* (0.01mm below threshold) and assert the validator
    detects it — confirming the inductive step doesn't mask true
    violations.
- **Test Scenarios:**
  - TS1. Clearance: add compliant route on same layer → zero new violations
  - TS2. Clearance: add non-compliant route (0.01mm below threshold) →
    violation detected
  - TS3. Creepage: add compliant route on same layer → zero new violations
  - TS4. Acid trap: add compliant route with no acute angles → zero new traps
  - TS5. Acid trap: add non-compliant route with 45° angle, 0.1mm width →
    trap detected
  - TS6. Annular ring: add compliant route with well-dimensioned vias
    → zero new violations
  - TS7. Thermal relief: add compliant power-net route → relief count
    increases, no violations
  - TS8. Copper balance: add compliant route → layer balances update
    without violations
  - TS9. Teardrop: add compliant route with vias → teardrops generated,
    no violations
  - TS10. Manufacturing report: composite report reflects sub-module
    updates correctly
- **Verification:** SC4 (all 8 validators pass the addition step),
  SC5 (non-compliant route detected).
- **Patterns to Follow:** `test_clearance_properties.py` for
  clearance-specific patterns, `test_*_boundary.py` for per-module
  import conventions.

### U10. Route Modification Inductive Step

- **Goal:** Verify that modifying an existing compliant route without
  introducing violations does not cause false positives (FR13b).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_clearance_induction.py` *(add
  test function)*
  `packages/temper-placer/tests/router_v6/test_creepage_induction.py` *(add)*
  `packages/temper-placer/tests/router_v6/test_acid_trap_induction.py` *(add)*
  *(new functions in the same files as U9)*
- **Dependencies:** U9, U12
- **Approach:**
  - Start from a routing result that passes all validators.
  - Modify an existing route: shift all segments by a small offset
    (e.g., 5mm) that preserves all clearance, width, and angle
    constraints relative to all other geometry.
  - Assert the modified routing still passes all validators.
  - This catches spatial-index update bugs: if the engine caches
    old positions after a mutation, a false violation results.
- **Test Scenarios:**
  - TS1. Shift a route 5mm on F.Cu, verify clearance unchanged
  - TS2. Shift a route on In1.Cu, verify creepage unchanged
  - TS3. Shift a route while preserving all vertex angles → acid
    trap count unchanged
- **Verification:** SC4 (extends to modification step).

### U11. Route Removal Inductive Step

- **Goal:** Verify that removing a compliant route does not cause
  phantom violations from stale spatial-index entries (FR13c).
- **Files:**
  *(same files as U9, new test functions)*
- **Dependencies:** U9, U12
- **Approach:**
  - Start from a routing result that passes all validators with
    3+ routes.
  - Remove one compliant route.
  - Assert the result still passes all validators, with no increase
    in violation count.
  - This catches stale-index bugs: if the spatial index retains
    references to deleted geometry, the engine may phantom-detect
    violations against a non-existent route.
- **Test Scenarios:**
  - TS1. Remove middle net from 5-net routing → zero new violations
  - TS2. Remove all nets → returns to empty-board base case (zero
    violations)
  - TS3. Remove route with vias → via references purged from index
- **Verification:** SC4 (extends to removal step).

### U12. Known-Compliant Strategy Bootstrap Verification

- **Goal:** Verify that a routing containing *only* known-compliant
  routes passes all validators, bootstrapping the strategy's
  correctness (FR14).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_induction_strategy.py` *(new)*
- **Dependencies:** U15 (known_compliant_route strategy)
- **Approach:**
  - Strategy generates a `RoutingResults` containing 2–10
    `known_compliant_route` instances.
  - Run all 8 DFM validators on it.
  - Assert every validator reports zero violations.
  - This is the bootstrapping test: it proves that the
    "known-compliant" strategy actually produces compliant routes.
    Without this, the inductive steps in U9–U11 could pass
    trivially because the "compliant" route is vacuously compliant.
- **Test Scenarios:**
  - TS1. 2 known-compliant routes on F.Cu → all validators pass
  - TS2. 5 known-compliant routes on mixed layers → all validators pass
  - TS3. 10 known-compliant routes with vias → all validators pass
- **Verification:** Confirms the known-compliant strategy is
  self-consistent and not trivially-passing.

### U13. Lattice Diagnostic Correctness (Deliberately Injected Bugs)

- **Goal:** Confirm the property lattice produces clear diagnostics
  when encoding bugs are deliberately injected (SC6).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_sat_lattice_diagnostics.py` *(new)*
- **Dependencies:** U1–U4, U15, pytest-dependency
- **Approach:**
  - Temporarily monkeypatch `_encode_at_most_k` to produce wrong clauses
    (e.g., swap `>` for `<` in an exclusion clause).
  - Run FR4 → assert it fails.
  - Run FR1–FR3 → assert they still pass.
  - Monkeypatch `populate_sat_from_constraints` to omit layer constraints.
  - Run FR5 → assert it fails.
  - Run FR1–FR4 → assert they still pass.
  - These tests are manual verification (not CI gate); they prove the
    lattice structure works as designed.  They use
    `pytest-dependency`-marked fixtures to guarantee ordering.
- **Test Scenarios:**
  - TS1. AtMostK bug: FR4 fails, FR1–FR3 pass
  - TS2. Layer constraint omission: FR5 fails, FR1–FR4 pass
  - TS3. Connectivity clause bug: FR1 fails, all higher levels skipped
- **Verification:** SC6 (confirm lattice diagnostic isolation).
- **Patterns to Follow:** `pytest-dependency` markers,
  `monkeypatch` fixture, `@pytest.mark.skip` for CI gating.

### U14. CI Integration: pytest-dependency Lattice Ordering

- **Goal:** Enforce SAT lattice ordering and DRC induction sequencing
  in CI configuration (NFR7).
- **Files:**
  `packages/temper-placer/pyproject.toml` *(add pytest-dependency config)*
  `packages/temper-placer/tests/router_v6/conftest.py` *(add markers if needed)*
- **Dependencies:** U1–U4 (lattice tests), U8–U11 (induction tests)
- **Approach:**
  - Add `pytest-dependency` to test dependencies in `pyproject.toml`.
  - Register `@pytest.mark.dependency` marker in pytest config.
  - Mark SAT lattice tests: `sat-l1` (FR1), `sat-l2` (FR2, depends on
    sat-l1), `sat-l3` (FR3, depends on sat-l2), `sat-l4` (FR5, depends
    on sat-l3), `sat-l5` (FR6, depends on sat-l4).
  - Mark induction tests: `induction-base` (U8), `induction-add` (U9,
    depends on induction-base), `induction-modify` (U10, depends on
    induction-add), `induction-remove` (U11, depends on induction-add).
  - CI runs with `pytest --strict-markers -v`.
- **Test Scenarios:**
  - TS1. Run all SAT tests: Level 1 passes → Level 2 runs → etc.
  - TS2. Force Level 1 failure → Level 2+ skipped with "depends on
    sat-l1 which did not pass"
  - TS3. CI pipeline: `test_sat_solve_pbt.py` runs before
    `test_clearance_induction.py`
- **Verification:** Confirm CI skips dependent tests on failure,
  reports clear skip reasons.

### U15. Shared SAT Property Strategies Module

- **Goal:** Provide reusable Hypothesis strategies for SAT model
  generation (analogous to `dfm_property_strategies.py` per A6).
- **Files:**
  `packages/temper-placer/tests/router_v6/sat_property_strategies.py` *(new)*
- **Dependencies:** `SATModel`, `SATVariable`, `SATClause`,
  `constraint_model.ConstraintModel`, `hypothesis`
- **Approach:**
  - `sat_variable` → generates `SATVariable` with random name + description.
  - `sat_clause` → generates `SATClause` from a set of variables, random
    polarity per literal.
  - `sat_clause_set` → generates a list of `SATClause` over a shared
    variable set.
  - `constraint_model_grid` → generates a `ConstraintModel` for a known
    grid size (C cells, N nets, L layers) using `ModelBuilder` or direct
    construction.
  - `boundary_biased_routing_results` → generates `RoutingResults` with
    coordinates biased toward spatial-index cell boundaries (for U7).
  - `known_compliant_route` → generates a `CompiledRoute` with geometry
    known to satisfy all DFM constraints:
    - Trace width ≥ minimum (0.127mm)
    - Segments spaced ≥ 2× required clearance from each other and all
      existing routes
    - No acute angles < 90°
    - Vias with pad ≥ drill + 2× min_annular_ring
  - All strategies use `@st.composite` decorator pattern.
- **Test Scenarios:**
  - TS1. `sat_variable` generates valid SATVariable with non-empty name
  - TS2. `sat_clause` generates clause with literals pointing to valid vars
  - TS3. `constraint_model_grid(cells=4, nets=2, layers=1)` produces
    consistent ConstraintModel
  - TS4. `known_compliant_route` produces a CompiledRoute that passes
    all validators (verified by U12)
- **Verification:** Unit-tested by U1–U4 and U12 consuming the strategies.
- **Patterns to Follow:** `dfm_property_strategies.py` for
  `@st.composite` pattern, `strategies.py` for domain strategy conventions.

### U16. pysat Test Dependency Addition

- **Goal:** Add `pysat` (python-sat) as a test dependency for
  ground-truth SAT solving (A1).
- **Files:**
  `packages/temper-placer/pyproject.toml` *(modify)*
- **Dependencies:** None (leaf unit)
- **Approach:**
  - Add `python-sat` under `[project.optional-dependencies] test`.
  - Verify import: `from pysat.solver import Solver`.
  - Verify basic solve: create solver, add clause, solve, check result.
  - Document that pysat is test-only, not a runtime dependency.
- **Test Scenarios:**
  - TS1. `uv pip install -e ".[test]"` installs pysat
  - TS2. `python -c "from pysat.solver import Solver; print('OK')"` succeeds
- **Verification:** CI installs pysat and all SAT tests run.

## Risks

- **O(n²) oracle CI budget.**  The brute-force oracle is O(n²) in
  segment count.  With ≤500 segments (≤10 routes with 50 segments each),
  the worst case is ~125,000 pair comparisons per iteration × 200
  iterations = 25M comparisons.  At ~10μs per pair (analytical
  segment-to-segment distance), that's ~250ms per iteration — within
  the 5000ms deadline.  Mitigation: adaptive reduction to 100
  iterations for higher segment counts (NFR2).

- **Clause-set comparison brittleness.**  FR5 compares produced clauses
  against hand-specified expected sets.  If `populate_sat_from_constraints`
  changes variable naming conventions or ordering, the comparison will
  fail spuriously.  Mitigation: comparison operates on
  canonicalized clause representations (sorted literals by variable
  name, sorted clauses by string representation).  Expected sets are
  parameterized by the grid dimensions in the test, not hard-coded.

- **pysat availability in CI.**  `python-sat` must be available in
  the test environment.  It is a Python package with C extensions;
  if the wheel is not available for the CI platform, fallback to
  `pycosat` bindings or skip SAT tests.  Mitigation: validate pysat
  installation in CI before merging.

- **Known-compliant strategy correctness.**  If `known_compliant_route`
  generates geometry that is *not* actually compliant, the inductive
  steps could fail for the wrong reason (genuine violation vs. strategy
  bug).  Mitigation: U12 bootstraps the strategy by running all
  validators on a set of known-compliant-only routes and asserting
  zero violations.

- **Existing module crash on empty input.**  Some DFM validators may
  crash on empty `RoutingResults` rather than returning zero
  violations (Q3).  If so, that is a bug to fix per the requirement
  recommendation.  Mitigation: fix crashes before attempting
  induction tests; the base case (U8) is the first test to run.

- **Floating-point non-determinism.**  The completeness oracle
  (U5–U7) compares floating-point `actual_clearance` values between
  two independent implementations.  Mitigation: use
  `math.isclose(rel_tol=1e-9, abs_tol=1e-9)` for comparison.

## Dependencies and Sequencing

```
U16 (pysat dep) ──── U15 (sat strategies) ──┬── U1 (FR1–FR3, L1–L3)
                                             ├── U2 (FR4, L2)
                                             ├── U3 (FR5, L4)
                                             └── U4 (FR6, L5)
                                                      │
                                                      └── U13 (lattice diagnostics)
                                                      └── U14 (CI lattice ordering)

U5 (clearance oracle) ──┬── U6 (SC3a seeded gate)
                        └── U7 (SC3b boundary fuzzing)

U15 (sat strategies) ─── U12 (strategy bootstrap) ──┬── U8 (base case)
                                                      ├── U9 (addition induction)
                                                      ├── U10 (modification induction)
                                                      └── U11 (removal induction)
                                                               │
                                                               └── U14 (CI induction ordering)
```

- **Phase 1: Infrastructure.**  U16 (pysat dep) → U15 (sat strategies).
  U5 (clearance oracle).  These are leaf dependencies needed by all
  subsequent units.

- **Phase 2: SAT Lattice (parallel with Phase 3).**  U1, U2, U3, U4 in
  dependency order.  U1 establishes the test file pattern and lattice
  markers; U2–U4 layer on top.  U13 validates the lattice after
  completion.

- **Phase 3: DRC Completeness (parallel with Phase 2).**  U5 → U6 → U7
  in dependency order.  U5 builds the oracle; U6 gates; U7 fuzzes.

- **Phase 4: Induction (parallel with Phases 2–3).**  U12 bootstraps
  the strategy → U8 (base case) → U9, U10, U11 (inductive steps).
  Per-validator files in U9–U11 are independent of each other.

- **Phase 5: CI Integration.**  U14 adds pytest-dependency markers
  and CI configuration after all test implementations are stable.

- **Phase 6: Integration & Regression.**  Run full test suite:
  `pytest tests/router_v6/test_sat_*.py tests/router_v6/test_clearance_*.py
  tests/router_v6/test_*_induction.py tests/router_v6/test_*_properties.py
  tests/router_v6/test_dfm_hypothesis_fuzzing.py` and verify SC7 (no
  regression in existing tests).

## Scope Boundaries

### In Scope

- SAT inductive property lattice (FR1–FR7): 5 test levels
- AtMostK exhaustive verification for n=2..16
- Cross-constraint composition with clause-set comparison
- Parsimony invariant with initial bounds
- Brute-force clearance oracle + completeness PBT (FR8–FR11)
- Seeded bug detection gate (SC3a) + boundary fuzzing (SC3b)
- Empty-board base case for all 8 DFM validators (FR12)
- Compliant-route addition / modification / removal inductive steps
  for all 8 DFM validators (FR13, FR13b, FR13c)
- Known-compliant strategy bootstrap (FR14)
- Per-validator induction files (FR15)
- Shared SAT strategy module (A6)
- pysat test dependency (A1)
- pytest-dependency lattice ordering (NFR7)

### Out of Scope

- Metamorphic A* pathfinding properties (covered by idea #2 of the ideation)
- Pipeline stage contract enforcement / DRC fence extension (ideas #5, #6)
- Runtime monotonicity monitors for A* (idea #7)
- Replacing pysat/satispy with a different solver backend
- Completeness oracles for non-clearance DFM modules (creepage, annular ring,
  etc.) — defer to FR11b future work
- Real-world large-board regression testing (golden fixture ladder covers that)
- Fixing known DFM bugs discovered by new tests — filing tickets is in scope,
  fixing is not
- Adding the proposed A* "route soundness oracle" or node consistency PBT
  (the ideation's idea #2)

## Deferred Work

### FR11b: Extend Completeness Oracle to Creepage and Acid Traps

After the clearance oracle establishes the pattern (U5–U7), implement O(n²)
brute-force oracles for:
1. **Creepage distance checking** — iterate all segment pairs on the same
   layer between HV and LV nets, compute shortest surface-path distance
   (straight-line as first approximation, creepage-along-surface as
   refinement).  Compare against production `verify_creepage()`.
2. **Acid trap angle checking** — iterate all 3-point sequences in every
   route, compute vertex angles, compare against production
   `detect_acid_traps()`.

Both must have zero shared code paths with their respective production
modules.  Creepage is next-highest priority after clearance; acid traps
are deterministic (no spatial index) and less risky.  Estimated effort:
2–3 days per module after the clearance pattern is proven.

### Joint-Compliance Strategy (Q2 follow-up)

Current known-compliant strategies generate per-validator-isolated
geometry.  A future enhancement would create a
`jointly_compliant_route` strategy that simultaneously satisfies all
8 DFM constraints for a single route.  This enables a stronger
inductive test: add one route that is compliant for *all* validators
simultaneously and assert *all* validators still pass.  Deferred
because per-validator isolation provides 90% of the value with
much simpler strategy construction.

### Parsimony Bound Tightening (NFR6 follow-up)

After profiling real SAT builds from integration tests and golden
fixtures, tighten the bounds from 100·C·N·L / 200·C·N·L to
empirically-derived values (e.g., 5·C·N·L / 10·C·N·L).  The
current bounds are intentionally generous to avoid false positives
during initial rollout.

## Sources

- `docs/brainstorms/2026-06-28-sat-drc-validator-validation-requirements.md`
  — origin requirements (FR1–FR15, NFR1–NFR7, SC1–SC7)
- `docs/ideation/2026-06-28-router-v6-mathematical-rigor-ideation.md`
  — parent ideation (ideas 4, 9, 10)
- `packages/temper-placer/src/temper_placer/router_v6/sat_model.py`
  — SAT model dataclasses, `populate_sat_from_constraints`, `_encode_at_most_k`
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py`
  — `ConstraintModel`, `ModelBuilder`, `NetChannelVar`
- `packages/temper-placer/src/temper_placer/router_v6/clearance_check.py`
  — `verify_clearance()`, `_calculate_minimum_clearance()`,
  `_segment_to_segment_dist()`, `_point_to_segment_dist()`
- `packages/temper-placer/src/temper_placer/router_v6/clearance_engine.py`
  — `get_clearance()`, IEC standard consolidation
- `packages/temper-placer/src/temper_placer/router_v6/routing_results.py`
  — `RoutingResults`, `CompiledRoute`
- `packages/temper-placer/src/temper_placer/router_v6/via_placement.py`
  — `Via` dataclass
- `packages/temper-placer/tests/router_v6/test_sat_solve_pbt.py`
  — dummy tests to replace (lines 1–17)
- `packages/temper-placer/tests/router_v6/test_clearance_properties.py`
  — existing clearance property tests (R10, R11, TS3)
- `packages/temper-placer/tests/router_v6/dfm_property_strategies.py`
  — existing shared strategy module (pattern to replicate)
- `docs/plans/2026-06-25-dfm-property-tests-plan.md`
  — existing DFM property tests plan (plan structure conventions)
- `packages/temper-placer/tests/router_v6/test_dfm_hypothesis_fuzzing.py`
  — existing 6-invariant PBT suite, import patterns
- All 8 DFM module source files in
  `packages/temper-placer/src/temper_placer/router_v6/`:
  `acid_trap_detection.py`, `annular_ring_check.py`, `clearance_check.py`,
  `copper_balance.py`, `creepage_check.py`, `manufacturing_report.py`,
  `teardrop_generation.py`, `thermal_relief.py`
