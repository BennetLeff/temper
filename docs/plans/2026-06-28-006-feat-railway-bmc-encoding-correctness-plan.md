---
title: "feat: Railway-style BMC verification for SAT encoding correctness"
type: feat
status: draft
date: 2026-06-28
origin: docs/brainstorms/2026-06-28-railway-bmc-encoding-correctness-requirements.md
---

# Railway-Style BMC Verification for Encoding Correctness

## Summary

Add a bounded-model-checking layer (L0) that verifies the Python CNF encoder
(`populate_sat_from_constraints` in `sat_model.py:98`) against declarative ESL
predicates. For every `ConstraintModel` with N <= 10 primary variables, enumerate
all 2^N assignments and assert the ESL predicate and the pysat-evaluated CNF
agree on SAT/UNSAT. A counterexample is a concrete falsifying assignment --
print it in a copy-pasteable diagnostic. The BMC layer sits below the CDCL
property lattice in the pytest-dependency chain. A CI gate script enforces that
every `Constraint` subclass has an `esl()` method and a BMC test entry.

---

## Problem Frame

The 3-layer correctness architecture (formal proof in comments + CDCL property
lattice + post-solve audit) missed the AtMostK polarity bug: wrong exclusion-clause
polarity in `_encode_at_most_k` (`sat_model.py:298`) produced a CNF still satisfiable
by assignments that violated the cardinality bound. The post-solve audit caught it,
but after the solver produced a bogus assignment. BMC adds a pre-solve layer:
verify clauses against constraint semantics *before any solver runs*.

(see origin: `docs/brainstorms/2026-06-28-railway-bmc-encoding-correctness-requirements.md`)

---

## Requirements

| FR tag | Description | Origin doc section |
|--------|-------------|-------------------|
| FR-LANG1 | ESL API: predicate primitives + `eval_esl()` | 4.ESL Design |
| FR-LANG2 | Each constraint type has exactly one `esl()` method in `constraint_model.py` | 4.ESL Design |
| FR-LANG3 | ESL is executable ground truth; `eval_esl(model, assignment) -> bool` | 4.ESL Design |
| FR-LANG4 | ESL constructors map to Hypothesis strategies in `sat_property_strategies.py` | 4.ESL Design |
| FR-BMC1 | BMC engine: extract primaries, enumerate 2^N, check ESL vs CNF agreement | 4.BMC Engine |
| FR-BMC2 | Use pysat (Glucose3) as CNF oracle with primary vars fixed as unit clauses | 4.BMC Engine |
| FR-BMC3 | Default bound N <= 10 (1024 assignments); configurable | 4.BMC Engine |
| FR-BMC4 | Counterexample diagnostic: model, assignment, ESL/CNF results, clause set | 4.BMC Engine |
| FR-BMC5 | No JAX imports in BMC code (NFR4 compliance) | 4.BMC Engine |
| FR-ENUM1 | Hypothesis composite strategy: all `(ConstraintModel, net_names)` pairs within bound | 4.Topology Enum |
| FR-ENUM2 | Cover all constraint-type combinations within the enumeration bound | 4.Topology Enum |
| FR-ENUM3 | Exhaustive base-case batch: all `(n_nets, n_channels)` where product <= 10, n_layers <= 2 | 4.Topology Enum |
| FR-HYP1 | Use `@given` + `@settings` from Hypothesis >= 6.148.7 | 4.Hypothesis Integration |
| FR-HYP2 | Observe CI-fast (50 examples) / CI-full (200 examples) profile tiers | 4.Hypothesis Integration |
| FR-HYP3 | Mark tests `@pytest.mark.bmc_l0_encoding` | 4.Hypothesis Integration |
| FR-HYP4 | Fit within 5000ms-per-example deadline | 4.Hypothesis Integration |
| FR-CEX1 | Counterexample defined as falsifying assignment: ESL=True/CNF=UNSAT or ESL=False/CNF=SAT | 4.Counterexamples |
| FR-CEX2 | False-SAT counterexamples are higher-priority diagnostic | 4.Counterexamples |
| FR-CEX3 | Counterexample reproducible via copy-pasteable Python snippet | 4.Counterexamples |
| FR-CI1 | Run as part of existing `router_v6` test suite | 4.CI Gate |
| FR-CI2 | Dependency: `bmc-l0` marker that `sat-l1` depends on | 4.CI Gate |
| FR-CI3 | Exhaustive batch on every commit; Hypothesis batch at PR time under CI-full | 4.CI Gate |
| FR-CI4 | BMC failure blocks PR merge | 4.CI Gate |
| FR-CI5 | CI gate script scans `constraint_model.py` for enforcible ESL + BMC coverage | 4.CI Gate |
| FR-CI5.1 | Retry-with-seed for Hypothesis failures; no retry for exhaustive batch | 4.CI Gate |
| FR-ADOPT1 | New constraint type requires: esl() method, encoding path, ESL registry, BMC test, lattice diagnostic test | 4.Adoption |
| FR-ADOPT2 | Encoding changes do not require ESL changes -- ESL declares what, not how | 4.Adoption |
| FR-REL1 | BMC (L0) depends-on-none; sat-l1 depends on bmc-l0 | 4.Relationship |
| FR-REL2 | BMC does not duplicate CDCL lattice or constraint audit tests | 4.Relationship |
| FR-REL3 | BMC strategies extend (not duplicate) `sat_property_strategies.py` | 4.Relationship |

**Acceptance examples:** AE1 (LayerConstraint agreement), AE2 (AtMostK polarity bug caught), AE3 (exhaustive batch ~200 instances, <30s), AE4 (new constraint adoption flow), AE5 (copy-pasteable diagnostic snippet), AE6 (independent test selection via `-k bmc_l0`).

**Success criteria:** SC1 (AtMostK regression gauntlet), SC2 (false-negative immunity for all constraint types), SC3 (zero false positives on correct `main` encoding), SC4 (exhaustive batch <= 30s), SC5 (diagnostic actionability), SC6 (FI gate on adoption).

---

## Scope Boundaries

### In Scope
- ESL design as Python predicates with composition operators
- BMC engine: primary-variable enumeration + pysat CNF checking
- Combinatorial topology enumeration via Hypothesis strategies
- CI gate script for ESL/BMC coverage enforcement
- Counterexample diagnostics with copy-pasteable reproduction
- Integration into pytest-dependency chain as L0 below sat-l1

### Out of Scope
- Rust `encode_to_cnf` (`encoding.rs:78`) verification (deferred)
- CDCL solver correctness (covered by existing lattice)
- Constraint audit correctness (covered by existing tests)
- Unbounded model checking or induction proofs
- Replacing the inductive proof in `encoding.rs:168-182`
- ESL-to-CNF synthesis / codegen (future work)
- JAX imports (NFR4: no JAX in test imports)
- Constraint-model *generation* correctness (`ModelBuilder`) — builder bugs are covered by validator tests; BMC checks the encoder, not the builder

### Deferred for Later
- **Rust encoder BMC**: expose `CnfFormula` to Python via PyO3, share the ESL spec, run same BMC batch on both encoders
- **Unbounded induction**: prove BMC correctness for bounded case implies correctness for unbounded case (for Sinz sequential counter)
- **ESL-to-CNF synthesis**: use ESL as single source of truth to *generate* the CNF encoding

---

## Context & Research

### Relevant Code and Patterns

| File | Role |
|------|------|
| `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py` | Constraint types (lines 81-120) + ConstraintModel (line 122) — where `esl()` methods will be added |
| `packages/temper-placer/src/temper_placer/router_v6/sat_model.py` | `populate_sat_from_constraints()` (line 98) — the encoder under test; `_encode_at_most_k()` (line 217) — Sinz sequential counter |
| `packages/temper-placer/tests/router_v6/sat_property_strategies.py` | Shared Hypothesis strategies — `constraint_model_grid` (line 127) will be extended |
| `packages/temper-placer/tests/router_v6/test_sat_solve_pbt.py` | CDCL property lattice (sat-l1 through sat-l5) — BMC will sit below this chain |
| `packages/temper-placer/tests/router_v6/test_sat_lattice_diagnostics.py` | Deliberate bug injection (AtMostK polarity swap at line 116) — BMC must catch this |
| `packages/temper-placer/tests/router_v6/conftest.py` | CI-fast / CI-full Hypothesis profiles + marker registration |
| `scripts/import_linter_gate.py` | Pattern for CI gate script — BMC adoption gate will follow this structure |
| `packages/temper-rust-router/src/encoding.rs` | Rust Sinz sequential counter (line 78) + exhaustive tests (line 264) — reference implementation, not the test target |

### Institutional Learnings
- The AtMostK polarity bug was caught by the post-solve audit (L3), not by L1 or L2
- The existing CDCL lattice tests check solver behavior given clauses, not whether clauses encode correct semantics
- `test_sat_lattice_diagnostics.py:42-178` documents the exact AtMostK polarity bug that BMC must catch
- The Sinz sequential counter encoding is exhaustively verified for n <= 8 in `encoding.rs:264-305` (3,286 checks)
- The CDCL lattice has a well-established `pytest.mark.dependency` chain: sat-l1 -> sat-l2 -> sat-l3 -> sat-l4 -> sat-l5 (and sat-atmostk depends on sat-l1 independently)
- Hypothesis profiles are registered in `tests/router_v6/conftest.py:49-69` (`CI-fast`: 50 examples, `CI-full`: 200 examples)
- The existing `constraint_model_grid` strategy in `sat_property_strategies.py:127` generates `ConstraintModel` instances but currently only creates `LayerConstraint` entries — it needs `DiffPairConstraint` and `CapacityConstraint` variants

### Constraint Types and Their Semantics

| Constraint | ESL predicate | Encoding |
|------------|--------------|----------|
| `LayerConstraint(allowed=False)` | `var == False` | Unit clause `(¬var)` |
| `LayerConstraint(allowed=True)` | `var == True` | Unit clause `(var)` |
| `DiffPairConstraint` | `p_var == n_var` (iff) | Two clauses: `(¬p ∨ n) ∧ (p ∨ ¬n)` |
| `CapacityConstraint` | `sum(vars) <= max_nets` | Sinz sequential counter `_encode_at_most_k(vars, k)` |

---

## Key Technical Decisions

- **ESL as executable Python predicates over `ConstraintModel` + assignment dict.** The ESL evaluates directly against the Python constraint model, avoiding a separate interpreter. `eval_esl(model, assignment) -> bool` is the ground truth.
- **BMC over CNF with primary variables fixed as unit clauses.** For each primary assignment, add unit clauses that fix primary variables to the assignment values, then ask pysat whether the remaining CNF (with free auxiliary Sinz variables) is satisfiable. This matches actual solver usage.
- **Bound of N <= 10 primary variables for exhaustive enumeration (2^10 = 1024).** This covers all configurations with n_nets * n_channels <= 10 (e.g., 3x3, 4x2, 2x4). The AtMostK polarity bug is caught at n=3, k=2 (3 primaries), well within the bound.
- **BMC as L0, not replacing CDCL lattice.** BMC tests encoding correctness (clause semantics). CDCL lattice tests solver behavior given clauses. Both are necessary; neither subsumes the other.
- **Shared Hypothesis strategies with bounded generators.** BMC strategies extend `sat_property_strategies.py` rather than creating a parallel module. The existing `constraint_model_grid` strategy is extended with tighter bounds and full constraint-type coverage.
- **Adoption gate as CI script.** A separate Python script (analogous to `import_linter_gate.py`) scans `constraint_model.py` for `Constraint` subclasses and verifies each has an `esl()` method, a BMC test entry, and an ESL registry entry. Missing any -> CI failure.

---

## Implementation Units

### U1. ESL Design and Implementation

**Goal:** Define the Encoder Specification Language as composable Python predicates and add `esl()` methods to each constraint type in `constraint_model.py`.

**Requirements:** FR-LANG1, FR-LANG2, FR-LANG3, FR-LANG4

**Dependencies:** None

**Files:**
- Create: `packages/temper-placer/src/temper_placer/router_v6/esl.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py`

**Approach:**

1. Create `esl.py` with predicate primitives and composition operators:

```python
# Predicate primitives (over assignment: dict[str, bool])
def all_true(vars: list[str]) -> Callable[[dict[str, bool]], bool]
def any_true(vars: list[str]) -> Callable[[dict[str, bool]], bool]
def at_most_k(vars: list[str], k: int) -> Callable[[dict[str, bool]], bool]
def exactly_one_of(vars: list[str]) -> Callable[[dict[str, bool]], bool]
def implies(a: str, b: str) -> Callable[[dict[str, bool]], bool]
def iff(a: str, b: str) -> Callable[[dict[str, bool]], bool]

# Composition operators
def and_(*predicates) -> Callable[[dict[str, bool]], bool]
def or_(*predicates) -> Callable[[dict[str, bool]], bool]

# Top-level evaluation
def eval_esl(model: ConstraintModel, assignment: dict[str, bool]) -> bool
```

2. Add `esl()` methods to each constraint class in `constraint_model.py`:

```python
# CapacityConstraint.esl()
# Returns at_most_k([var.name for var, _ in terms], int(capacity * slack_factor / min_width))
# Edge case: k >= len(vars) -> trivially True (all_true([]))

# DiffPairConstraint.esl()
# Returns iff(p_var.name, n_var.name)

# LayerConstraint.esl()
# Returns all_true([var_name]) if allowed else all_false([var_name])
```

3. Add an ESL registry dict to `constraint_model.py` (near the `Constraint` base class):
```python
ESL_REGISTRY: dict[str, Callable] = {}
```
Each `esl()` method self-registers its constraint type name. This enables the CI gate script to detect types without an ESL entry.

4. `eval_esl()` iterates over all constraints in the model, evaluates each constraint's ESL predicate against the assignment, and returns the conjunction (all constraints must be satisfied). Uses `all()` short-circuit evaluation.

**Test scenarios:**
- Single `LayerConstraint(allowed=False)` -> `eval_esl` returns True only for `{var: False}` (covers AE1)
- Single `DiffPairConstraint` on `(x0, x1)` -> `eval_esl` returns True for `{x0: True, x1: True}` and `{x0: False, x1: False}`, False for mismatched
- Single `CapacityConstraint` with 3 vars, k=2 -> `eval_esl` returns False for `{x0: T, x1: T, x2: T}`, True for all assignments with <= 2 true vars
- Empty constraint model -> `eval_esl` returns True for all assignments (vacuously true)
- `at_most_k` with k >= len(vars) -> always True
- `at_most_k` with k=0 -> only all-False assignment is True
- Composition: `and_(iff(x0, x1), at_most_k([x0, x1, x2], 1))` -> only `{x0:F, x1:F, x2:T}`, `{x0:F, x1:F, x2:F}`, `{x0:T, x1:T, x2:F}` are valid

**Verification:**
- `pytest packages/temper-placer/tests/router_v6/test_esl.py -v` — new unit tests pass
- All ESL primitives have docstring with example usage

---

### U2. BMC Verification Engine

**Goal:** Implement the core BMC checker that enumerates all primary-variable assignments for a `(ConstraintModel, SATModel)` pair and asserts ESL-vs-CNF agreement.

**Requirements:** FR-BMC1, FR-BMC2, FR-BMC3, FR-BMC4, FR-BMC5

**Dependencies:** U1

**Files:**
- Create: `packages/temper-placer/src/temper_placer/router_v6/bmc.py`
- Create: `packages/temper-placer/tests/router_v6/test_bmc.py`

**Approach:**

1. Create `bmc.py` with the core verification function:

```python
def bmc_check(
    constraint_model: ConstraintModel,
    sat_model: SATModel,
    primary_var_names: list[str] | None = None,
) -> list[dict]:  # list of counterexample diagnostics
```

2. Algorithm:
   a. If `primary_var_names` is not provided, extract primary SAT variables by identifying those created from `NetChannelVar` instances (non-auxiliary variables — Sinz auxiliary vars have names starting with `sc_`).
   b. Let N = len(primary_var_names). If N > bound (default 10), raise `BmcBoundExceeded` or skip with warning.
   c. For each integer mask in 0..(2^N - 1):
      - Build assignment dict: `{var_name: bool(mask & (1 << i))}`
      - ESL result: `eval_esl(constraint_model, assignment)`
      - CNF result: Create a pysat Glucose3 solver, add all clauses from `sat_model`, add unit clauses fixing primary variables to their assigned values, call `solve()`.
      - If ESL != CNF result, record a counterexample.
   d. Return list of counterexample diagnostics.

3. Primary variable identification:
   - Traverse `constraint_model.variables` for `NetChannelVar` instances
   - For each, find the corresponding SAT variable in `sat_model.variables` by matching the name pattern `f"uses_N{net_idx}_{channel_id}"` or `f"uses_{net_name}_{channel_id}"`
   - Exclude variables whose SAT names start with `sc_` (Sinz auxiliary vars)
   - Also exclude any variable not found in `sat_model.variables` (variables that existed in the constraint model but weren't mapped to SAT)

4. Counterexample diagnostic format (FR-BMC4, FR-CEX1, FR-CEX3):
```python
{
    "constraint_model": {...},  # JSON-ish dict
    "assignment": {"x0": True, "x1": False, ...},
    "esl_result": True,          # or False
    "cnf_result": "SAT",         # or "UNSAT"
    "failure_type": "false_sat"  # or "false_unsat"
    "primary_vars": ["x0", "x1", ...],
    "all_clauses": [str(clause) for clause in sat_model.clauses],
    "implicated_clauses": [...],  # clauses that fired for this assignment
    "repro_snippet": "def test_reproduce_bmc_failure(): ..."  # copy-pasteable
}
```

5. pysat integration (FR-BMC2):
   - Map SAT variable names to pysat variable indices (1-indexed, as pysat uses)
   - Add all clauses from `sat_model.clauses` to the pysat solver (once per model, outside the enumeration loop; each assignment check creates a fresh solver instance)
   - For each assignment, add unit clauses fixing primary variables, then call `solver.solve()`
   - Delete solver after each check to prevent state leakage

6. No JAX imports (FR-BMC5) — the `bmc.py` module imports only `constraint_model`, `sat_model`, `pysat.solvers`, and standard library.

**Test scenarios:**
- Single var, no constraints -> ESL=True for both assignments, CNF=SAT (connectivity clause: `(x0)`) for `{x0: T}`, UNSAT for `{x0: F}`. Wait -- the connectivity clause `(x0)` means the CNF is SAT only when x0=True. So assignment `{x0: F}` makes the unit clause `(¬x0)` conflict with `(x0)` -> UNSAT. Agreement: ESL=True, CNF=UNSAT for `{x0:F}`. This is a false UNSAT counterexample caused by the connectivity clause, which is NOT a constraint -- connectivity clauses are part of the encoding but NOT part of the ESL (ESL only covers constraints). Need to handle this: the BMC check should only verify constraints, not connectivity. Solution: the CNF for the BMC check should include ONLY clauses from constraint encoding, NOT connectivity clauses. Alternatively: the ESL should also cover connectivity? No -- per FR-LANG2, ESL is per-constraint-type. Connectivity is not a constraint. Decision: the BMC model creation step should skip connectivity clauses. Or better: create the SAT model from constraints only, using a variant of `populate_sat_from_constraints` that skips connectivity (or strips connectivity clauses after creation).
- Corrected test: Single LayerConstraint(allowed=False) on x0 -> ESL says only {x0: F} is valid. CNF has unit clause (¬x0). {x0: T} -> unit clause (x0) conflicts -> UNSAT. {x0: F} -> unit clause (¬x0) is satisfied -> SAT. Agreement = pass. 0 counterexamples. (covers AE1)
- AtMostK polarity bug (n=3, k=2) -> assignment {x0:T, x1:T, x2:T}: ESL=False (3 > 2), CNF=SAT (buggy exclusion clause accepts it). Counterexample found. (covers AE2, SC1)
- DiffPair bug (n_var polarity swapped) -> assignment {p:T, n:F}: ESL=False, CNF=SAT. Counterexample found.
- LayerConstraint bug (allowed=True missing) -> assignment {x0:F}: ESL=False, CNF=SAT. Counterexample found.

**Verification:**
- `pytest packages/temper-placer/tests/router_v6/test_bmc.py -v` — BMC engine unit tests pass
- Known-bug counterexamples match expected diagnostics

---

### U3. Combinatorial Topology Enumeration Strategies

**Goal:** Extend Hypothesis strategies in `sat_property_strategies.py` to generate all constraint-type combinations within the enumeration bound, including cross-constraint compositions.

**Requirements:** FR-ENUM1, FR-ENUM2, FR-ENUM3, FR-REL3

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/tests/router_v6/sat_property_strategies.py`

**Approach:**

1. Extend `constraint_model_grid()` (line 127) to accept new parameter controls:

```python
@st.composite
def constraint_model_grid(
    draw: st.DrawFn,
    max_nets: int = 4,
    max_channels: int = 4,
    max_layers: int = 2,
    include_capacity: bool = True,
    include_diff_pair: bool = True,
    include_layer: bool = True,
    max_primary_vars: int = 10,
) -> ConstraintModel:
```

2. New internal constraints on the strategy:
   - The number of primary variables (`n_nets * n_channels`) must be <= `max_primary_vars` (default 10)
   - Each `(n_nets, n_channels)` pair is sampled uniformly from valid pairs
   - Constraint types are applied combinatorially based on boolean flags

3. Add constraint-type combination coverage:
```python
@st.composite
def constraint_model_with_all_types(
    draw: st.DrawFn,
    max_primary_vars: int = 10,
) -> ConstraintModel:
```
This strategy guarantees at least one of each applicable constraint type is included (not just randomly). It draws from:
- `nets * channels <= max_primary_vars` topologies
- Always adds at least one `LayerConstraint` (if `max_layers > 1`)
- Always adds at least one `DiffPairConstraint` (if `n_nets >= 2`)
- Always adds at least one `CapacityConstraint` (if `n_nets >= 3` to trigger AtMostK)

4. Add exhaustive base-case enumeration helper (FR-ENUM3):
```python
def exhaustive_topologies(
    max_primary_vars: int = 10,
    max_layers: int = 2,
) -> list[tuple[int, int, int, list[str]]]:  # (n_nets, n_channels, n_layers, layer_names)
```
Enumerates all `(n_nets, n_channels, n_layers)` triples where `n_nets * n_channels * n_layers` yields primary variable count <= `max_primary_vars`. Each triple generates a set of canonical `ConstraintModel` instances (one per constraint-type combination).

The exhaustive set of topologies (FR-ENUM3):
```
(1,1), (1,2), (2,1), (2,2), (3,1), (1,3), (3,2), (2,3), (4,1), (1,4),
(3,3), (4,2), (2,4), (4,3), (3,4) — but bounded to n_nets * n_channels <= 10
```
Each multiplied by 2 layer options and ~7 constraint-type combinations = ~210 BMC instances.

5. Add DiffPair variable-generation to the strategy:
   - When `include_diff_pair` is True and `n_nets >= 2`, create pairs of `NetChannelVar` instances (one per channel, shared between two net indices)
   - Add `DiffPairConstraint` entries linking each pair

6. Add CapacityConstraint generation to the strategy:
   - When `include_capacity` is True, create `CapacityConstraint` entries with `capacity` and `slack_factor` such that `max_nets < len(terms)` (triggers AtMostK)
   - Ensure `terms` list references the actual `NetChannelVar` instances in the model

**Test scenarios:**
- `constraint_model_grid(max_primary_vars=10)` always produces models with <= 10 primary `NetChannelVar` instances
- `constraint_model_with_all_types()` always includes at least one of each constraint type when flags allow
- `exhaustive_topologies()` returns all 26+ canonical (n_nets, n_channels, n_layers) triples
- Strategy produces valid `ConstraintModel` instances that `populate_sat_from_constraints()` accepts without error

**Verification:**
- `pytest packages/temper-placer/tests/router_v6/test_strategies.py -v` — new strategy unit tests pass
- Manual check: `exhaustive_topologies()` prints expected topology list

---

### U4. BMC Hypothesis Test Suite

**Goal:** Wire the BMC engine into Hypothesis PBT tests with the proper marker, profiles, and dependency chain.

**Requirements:** FR-HYP1, FR-HYP2, FR-HYP3, FR-HYP4, FR-CI1, FR-CI2, FR-REL1, FR-REL2

**Dependencies:** U2, U3

**Files:**
- Create: `packages/temper-placer/tests/router_v6/test_bmc_encoding.py`
- Modify: `packages/temper-placer/tests/router_v6/conftest.py`
- Modify: `packages/temper-placer/tests/router_v6/test_sat_solve_pbt.py`

**Approach:**

1. Register the `bmc_l0_encoding` marker in `conftest.py` (add to `pytest_configure`):
```python
config.addinivalue_line(
    "markers",
    "bmc_l0_encoding: BMC L0 encoding correctness tests (pre-solve verification)",
)
```

2. Create `test_bmc_encoding.py` with the BMC test class:

```python
@pytest.mark.dependency(name="bmc-l0")
@pytest.mark.bmc_l0_encoding
class TestBmcEncodingL0:
    """L0: BMC encoding correctness — ESL vs CNF agreement."""
```

3. Exhaustive base-case batch (FR-ENUM3, FR-CI3):
```python
@pytest.mark.parametrize("n_nets,n_channels,n_layers", [
    # All (n_nets, n_channels) pairs where product <= 10, n_layers <= 2
    (1, 1, 1), (1, 1, 2),
    (1, 2, 1), (1, 2, 2),
    (2, 1, 1), (2, 1, 2),
    (2, 2, 1), (2, 2, 2),
    (3, 1, 1), (3, 1, 2),
    (1, 3, 1), (1, 3, 2),
    (3, 2, 1), (3, 2, 2),
    (2, 3, 1), (2, 3, 2),
    (4, 1, 1), (4, 1, 2),
    (1, 4, 1), (1, 4, 2),
    (3, 3, 1), (3, 3, 2),
    (4, 2, 1), (4, 2, 2),
    (2, 4, 1), (2, 4, 2),
])
def test_exhaustive_bmc_all_constraint_types(self, n_nets, n_channels, n_layers):
    """For each canonical topology within the bound, test all constraint-type
    combinations via exhaustive enumeration of primary-variable assignments."""
    # Build ConstraintModel for this topology with all constraint-type combinations
    # For each combination, run bmc_check() and assert zero counterexamples
```

For each topology, the test creates 7 constraint-type combinations:
- No constraints (connectivity-only)
- Layer constraints only
- Capacity constraints only
- DiffPair constraints only
- Layer + Capacity (cross-constraint)
- Layer + DiffPair (cross-constraint)
- Capacity + DiffPair (cross-constraint)
- All three simultaneously

Total: ~26 topologies * 7 constraint combos = ~182 BMC instances.

4. Hypothesis-driven random batch (FR-HYP1, FR-HYP2):
```python
@settings.load_profile("CI-fast")  # defaults to 50 examples
@given(model_net_names=constraint_model_with_all_types(max_primary_vars=10))
def test_bmc_hypothesis_random(self, model_net_names):
    """Hypothesis-driven BMC: random ConstraintModel instances within bound."""
    model, net_names = model_net_names
    # Build SAT model, run bmc_check, assert zero counterexamples
```

The `@settings` profile adapts: CI-fast by default (50 examples, 5000ms deadline), CI-full in CI (200 examples, 15000ms deadline) as configured in conftest.py:68.

5. Add BMC dependency to the CDCL lattice (FR-CI2, FR-REL1):
   - In `test_sat_solve_pbt.py`, update the `sat-l1` marker:
   ```python
   @pytest.mark.dependency(depends=["bmc-l0"], name="sat-l1")
   ```
   - The `bmc-l0` marker depends on nothing (it's the base of the pyramid)

6. Verify the dependency chain in `test_sat_lattice_diagnostics.py`:
   - `test_lattice_connectivity_clause_bug_affects_higher_levels` (line 254) already validates the chain; add `bmc-l0` to the expected chain:
   ```python
   lattice_chain: list[tuple[str, str, list[str]]] = [
       ("bmc-l0", "TestBmcEncodingL0", []),
       ("sat-l1", "test_fr1_single_clause_sat", ["bmc-l0"]),
       ...
   ]
   ```

**Test scenarios:**
- `pytest -k "bmc_l0"` runs only BMC tests (covers AE6)
- `pytest -k "sat-l1"` runs CDCL lattice L1, which depends on bmc-l0 passing
- `pytest --profile=CI-full -k "test_bmc_hypothesis_random"` runs 200 Hypothesis examples
- Exhaustive batch completes in <30s (covers SC4)
- All exhaustive + Hypothesis on correct `main` encoding produce zero counterexamples (covers SC3)

**Verification:**
- `pytest packages/temper-placer/tests/router_v6/test_bmc_encoding.py -v` — all tests pass
- `pytest packages/temper-placer/tests/router_v6/test_sat_solve_pbt.py -v -k "sat-l1"` — still passes (depends on bmc-l0)
- `pytest packages/temper-placer/tests/router_v6/ --co -q | grep bmc_l0` — shows BMC tests in collection

---

### U5. Counterexample Diagnostics and Reproducibility

**Goal:** Ensure every counterexample diagnostic is actionable (copy-pasteable to a standalone unit test) and correctly classifies false-SAT vs false-UNSAT failures.

**Requirements:** FR-CEX1, FR-CEX2, FR-CEX3, SC5

**Dependencies:** U2

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/bmc.py` (add diagnostic rendering)
- Create: `packages/temper-placer/tests/router_v6/test_bmc_diagnostics.py`

**Approach:**

1. Add `render_counterexample(diagnostic: dict) -> str` to `bmc.py`:
```python
def render_counterexample(ce: dict) -> str:
    """Render a counterexample as a copy-pasteable Python snippet (AE5)."""
    return f'''def test_reproduce_bmc_failure():
    """BMC counterexample: {ce["failure_type"]}"""
    from temper_placer.router_v6.constraint_model import ConstraintModel, NetChannelVar
    from temper_placer.router_v6.sat_model import SATModel, populate_sat_from_constraints
    from temper_placer.router_v6.bmc import bmc_check
    ...
    # ESL says: {ce["esl_result"]}, CNF says: {ce["cnf_result"]}
    # Assignment: {ce["assignment"]}
    counterexamples = bmc_check(cm, sat, primary_var_names={list(ce["assignment"].keys())})
    assert len(counterexamples) == 1
    assert counterexamples[0]["failure_type"] == "{ce["failure_type"]}"
'''
```

2. Add implicated-clause identification (FR-BMC4 bullet 6):
   - After detecting a counterexample, re-run the pysat check and collect which clauses are involved in the conflict (for false-UNSAT) or which clauses are satisfied despite the ESL violation (for false-SAT)
   - Store implicated clause strings in the diagnostic

3. Prioritize false-SAT over false-UNSAT in output (FR-CEX2):
   - In the test failure message, list false-SAT counterexamples first with a `CRITICAL` tag
   - False-UNSAT counterexamples are listed second with a `WARNING` tag (the encoder is over-restrictive, which is safer than under-restrictive but still a bug)

4. Add a pytest fixture that dumps counterexample diagnostics to a temporary file when a test fails:
```python
@pytest.fixture
def bmc_diagnostics_dir(tmp_path):
    """Create a diagnostics directory for BMC counterexamples."""
    d = tmp_path / "bmc_diagnostics"
    d.mkdir()
    return d
```

5. In the test, on failure, write each counterexample as a standalone Python file to the diagnostics directory and print the path in the assertion message.

**Test scenarios:**
- Inject a known polarity bug and verify the diagnostic contains the correct repro snippet (covers AE5)
- False-SAT diagnostic lists `CRITICAL` tag
- False-UNSAT diagnostic lists `WARNING` tag
- Diagnostic file written on failure is executable as a standalone `pytest` test and reproduces the failure
- Empty counterexample list produces clean diagnostic (no crash)

**Verification:**
- `pytest packages/temper-placer/tests/router_v6/test_bmc_diagnostics.py -v` — all diagnostic tests pass
- Manual: run a failing test, copy-paste the repro snippet into a new file, run it — reproduces the failure

---

### U6. CI Adoption Gate Script

**Goal:** A CI script that scans `constraint_model.py` for `Constraint` subclasses and verifies each has an ESL declaration, an encoding path in `sat_model.py`, a BMC test entry, and an ESL registry entry. Analogous to `scripts/import_linter_gate.py`.

**Requirements:** FR-CI5, FR-CI5.1, SC6

**Dependencies:** U1, U4

**Files:**
- Create: `scripts/bmc_adoption_gate.py`
- Modify: `packages/temper-placer/tests/router_v6/conftest.py` (optional: retry-with-seed integration)

**Approach:**

1. Create `scripts/bmc_adoption_gate.py`:
   - Parse `constraint_model.py` using `ast` to find all `Constraint` subclasses (excluding `Constraint` itself)
   - For each subclass, verify:
     a. An `esl()` method exists on the class definition (source-level check via AST)
     b. An entry exists in `ESL_REGISTRY` (source-level check for dict assignment or registration call)
     c. An `isinstance(constraint, <Type>)` branch exists in `populate_sat_from_constraints` in `sat_model.py`
     d. At least one BMC test function references the constraint type (scan `tests/router_v6/test_bmc_*.py` for the class name)

2. Exit codes (following the `import_linter_gate.py` pattern):
   - 0: All constraint types have ESL + encoding + BMC test coverage
   - 3: Missing ESL or BMC test (blocks merge)
   - 5: Tool error (script failure, missing files)

3. Retry-with-seed for Hypothesis failures (FR-CI5.1):
   - In `conftest.py`, add a `pytest_sessionfinish` hook or use a helper that captures Hypothesis failure seeds
   - In the gate script, if the BMC Hypothesis test fails, extract the seed from pytest output, re-run with `--hypothesis-seed=<seed>`, and only block merge if the re-run also fails
   - This is safer implemented as a CI workflow step rather than in the gate script itself. The plan defers the exact mechanism to implementation — the retry logic lives in CI config, not in the script.

4. Integration into CI:
   - Add to `.github/workflows/` or equivalent CI config:
   ```yaml
   - name: BMC adoption gate
     run: uv run python scripts/bmc_adoption_gate.py
   ```

5. The gate script scans for:
   - `CapacityConstraint` -> must have `esl()`, `ESL_REGISTRY` entry, `isinstance(constraint, CapacityConstraint)` in `sat_model.py`, and test coverage
   - `DiffPairConstraint` -> same
   - `LayerConstraint` -> same
   - Any future constraint type -> same

**Test scenarios:**
- Current `main` branch -> all constraint types have full coverage -> exit 0
- Remove an `esl()` method -> exit 3 with diagnostic listing the missing method
- Remove a `populate_sat_from_constraints` branch -> exit 3 with diagnostic listing the missing encoding path
- Remove BMC test coverage -> exit 3 with diagnostic listing the missing test
- Missing `ESL_REGISTRY` entry -> exit 3 with diagnostic
- `constraint_model.py` not found -> exit 5

**Verification:**
- `uv run python scripts/bmc_adoption_gate.py` — passes (exit 0) on current `main`
- Temporarily comment out `LayerConstraint.esl()` — gate fails (exit 3)

---

### U7. Lattice Diagnostics — BMC Regression Gauntlet

**Goal:** Extend `test_sat_lattice_diagnostics.py` to verify that the BMC layer catches known bugs (the AtMostK polarity swap, layer omission, diff-pair polarity swap).

**Requirements:** SC1, SC2, FR-ADOPT1 (diagnostic test for new constraints)

**Dependencies:** U1, U2, U4

**Files:**
- Modify: `packages/temper-placer/tests/router_v6/test_sat_lattice_diagnostics.py`

**Approach:**

1. Add a test that verifies BMC catches the AtMostK polarity bug (SC1):
```python
@pytest.mark.dependency(depends=["bmc-l0"])
def test_bmc_catches_atmostk_polarity_bug(monkeypatch):
    """SC1: BMC catches the AtMostK polarity bug as a false-SAT counterexample."""
    # Monkeypatch _encode_at_most_k with the buggy version (same as test_lattice_fr4_fails_with_bug)
    # Build a 3-variable k=2 model
    # Run bmc_check() -> must produce at least one false-SAT counterexample
    # Verify counterexample is {x0:T, x1:T, x2:T} with ESL=False, CNF=SAT
```

2. Add tests for each constraint type with a deliberate bug (SC2):
```python
@pytest.mark.parametrize("constraint_type,bug_description", [
    ("capacity", "polarity swap in exclusion clause"),
    ("layer", "omitted from encoding"),
    ("diff_pair", "polarity swap in iff clause"),
    ("capacity", "wrong k value (off by one)"),
])
def test_bmc_catches_deliberate_bugs(constraint_type, bug_description, monkeypatch):
    """SC2: BMC catches deliberate bugs in every constraint encoding."""
    # For each bug type, monkeypatch the encoding, build a model within the bound,
    # run bmc_check, and assert at least one counterexample is found.
```

3. Add a test confirming zero false positives on correct encoding (SC3):
```python
def test_bmc_zero_false_positives_on_correct_encoding():
    """SC3: On correct main encoding, exhaustive batch produces zero counterexamples."""
    # This is essentially a smoke test that the exhaustive batch passes.
    # It calls the same logic as test_exhaustive_bmc_all_constraint_types
    # but is a manual verification test (not a CI gate itself).
```

4. Add the adoption-protocol diagnostic test pattern (FR-ADOPT1):
```python
def test_bmc_new_constraint_adoption_pattern():
    """FR-ADOPT1: Demonstrates the diagnostic pattern for new constraint adoption.
    
    This test verifies that:
    1. Every constraint type has an esl() method (via ESL_REGISTRY)
    2. Every constraint type has an encoding path in populate_sat_from_constraints
    3. For a deliberate bug in a hypothetical new constraint, BMC would catch it
    """
```

**Test scenarios:**
- BMC catches the exact AtMostK polarity bug from `test_sat_lattice_diagnostics.py:116` (covers SC1)
- BMC catches a layer constraint omission bug (covers SC2)
- BMC catches a diff-pair polarity swap bug (covers SC2)
- BMC catches a wrong-k-value bug in CapacityConstraint (covers SC2)
- On clean encoding, BMC produces zero counterexamples (covers SC3)
- All diagnostic tests produce actionable failure messages with repro snippets

**Verification:**
- `pytest packages/temper-placer/tests/router_v6/test_sat_lattice_diagnostics.py -v -k "bmc"` — all BMC diagnostic tests pass
- Deliberately break an ESL method -> corresponding diagnostic test fails with clear message

---

### U8. Constraint Model Encoding vs Connectivity Boundary

**Goal:** Resolve the tension between connectivity clauses (added by `populate_sat_from_constraints` at line 153-161) and constraint-only ESL semantics. Connectivity clauses are not constraints and should not be part of the BMC CNF check.

**Requirements:** FR-REL2 (BMC does not duplicate CDCL lattice), FR-BMC1 (BMC checks encoding correctness)

**Dependencies:** U1, U2

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/sat_model.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/bmc.py`

**Approach:**

1. The connectivity clauses (`(var1 ∨ var2 ∨ ...)` — each net must use at least one channel) are NOT part of any constraint's semantics. They are a solver directive, not a constraint. Including them in BMC would produce false counterexamples (e.g., a primary assignment that violates no constraint but has all vars false would be UNSAT due to connectivity).

2. Add a parameter to `populate_sat_from_constraints`:
```python
def populate_sat_from_constraints(
    sat_model: SATModel,
    constraint_model: ConstraintModel,
    net_names: list[str] | None = None,
    skip_connectivity: bool = False,  # NEW
) -> None:
```
When `skip_connectivity=True`, the connectivity clause generation (lines 153-161) is skipped. Default is `False` (backward compatible).

3. In `bmc.py`, call `populate_sat_from_constraints(sat, cm, net_names, skip_connectivity=True)` to get a SATModel with only constraint-encoding clauses.

4. Alternatively, add a utility in `bmc.py` that strips connectivity clauses from an existing SATModel:
```python
def _strip_connectivity_clauses(sat_model: SATModel) -> SATModel:
    """Return a copy of the SATModel without connectivity clauses."""
    # Filter out clauses whose description starts with "Connectivity:"
```
This approach avoids modifying the public API of `populate_sat_from_constraints`.

**Decision:** Use `skip_connectivity=True` parameter — it's cleaner and avoids post-hoc clause filtering. The parameter name is explicit about its purpose.

**Test scenarios:**
- Model with 1 var, no constraints, `skip_connectivity=True` -> 0 clauses (no connectivity, no constraints)
- Model with 1 var, no constraints, `skip_connectivity=False` -> 1 clause (connectivity only)
- Model with 1 var + LayerConstraint, `skip_connectivity=True` -> 1 clause (layer unit clause only)
- BMC on a model built with `skip_connectivity=True` passes (no connectivity false counterexamples)

**Verification:**
- `pytest packages/temper-placer/tests/router_v6/test_bmc.py -v -k "connectivity"` — passes
- Existing lattice tests (which use default `skip_connectivity=False`) still pass unchanged

---

### U9. Documentation and Adoption Checklist

**Goal:** Document the BMC layer, the ESL specification, and the adoption protocol for new constraint types. Update relevant in-code documentation.

**Requirements:** FR-ADOPT1, FR-ADOPT2

**Dependencies:** U1-U8

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py` (docstring additions)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/esl.py` (module docstring)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/bmc.py` (module docstring)
- Create: `packages/temper-placer/tests/router_v6/README_BMC.md` (optional, only if project convention demands test READMEs)

**Approach:**

1. Add module docstring to `esl.py` that explains:
   - Purpose: declarative specification language for constraint semantics
   - How each predicate primitive maps to Boolean logic
   - How `eval_esl` evaluates a `ConstraintModel` against an assignment
   - Relationship to constraint types: each constraint has exactly one `esl()` method

2. Add module docstring to `bmc.py` that explains:
   - Algorithm: enumerate all 2^N assignments, check ESL vs CNF via pysat
   - The bound of N <= 10 (1024 assignments)
   - Counterexample format and how to reproduce
   - Railway-interlocking analogy: declare safe routes, prove signal circuit never energizes unsafe ones

3. Add docstring to `Constraint` base class in `constraint_model.py`:
```python
@dataclass(kw_only=True)
class Constraint:
    """Base class for routing constraints.
    
    Each subclass MUST implement:
    - esl() -> Callable[[dict[str, bool]], bool]: ESL predicate for BMC verification
    - Registration in ESL_REGISTRY dict
    Contribute exactly one encoding branch in populate_sat_from_constraints().
    """
```

4. Add `# @req` traceability annotations:
   - In `esl.py`: `# @req(2026-06-28-006, FR-LANG1): ESL predicate primitives`
   - In `bmc.py`: `# @req(2026-06-28-006, FR-BMC1): BMC engine — enumeration + pysat check`
   - In `constraint_model.py:esl()`: `# @req(2026-06-28-006, FR-LANG2): Constraint ESL declaration`
   - In test files: `# @req(2026-06-28-006, FR-HYP3): BMC L0 Hypothesis test marker`

**Test scenarios:**
- All docstrings render correctly with `help()` or `__doc__`
- `@req` tags are valid per the traceability convention (if sentinel file exists in the directory)

**Verification:**
- `python -c "from temper_placer.router_v6.esl import at_most_k; help(at_most_k)"` — shows meaningful docstring
- `python -c "from temper_placer.router_v6.constraint_model import Constraint; help(Constraint)"` — shows adoption requirements

---

## System-Wide Impact

| Component | Change |
|-----------|--------|
| `constraint_model.py` | Adds `esl()` methods to `CapacityConstraint`, `DiffPairConstraint`, `LayerConstraint`; adds `ESL_REGISTRY` dict; adds `Constraint` base class docstring |
| `esl.py` (new) | Predicate primitives, composition operators, `eval_esl()`; no JAX imports |
| `bmc.py` (new) | BMC engine: enumeration + pysat check + counterexample diagnostics; no JAX imports |
| `sat_model.py` | Adds `skip_connectivity` parameter to `populate_sat_from_constraints()` |
| `sat_property_strategies.py` | Extends `constraint_model_grid()` with tighter bounds, capacity/diff-pair variants, `constraint_model_with_all_types()` |
| `test_bmc.py` (new) | BMC engine unit tests (no Hypothesis) |
| `test_bmc_encoding.py` (new) | Hypothesis-driven BMC tests with `@pytest.mark.bmc_l0_encoding` |
| `test_bmc_diagnostics.py` (new) | Counterexample diagnostic rendering tests |
| `test_sat_lattice_diagnostics.py` | Adds BMC regression gauntlet tests (SC1, SC2, SC3) |
| `test_sat_solve_pbt.py` | Updates `sat-l1` to depend on `bmc-l0` |
| `conftest.py` | Registers `bmc_l0_encoding` pytest marker |
| `bmc_adoption_gate.py` (new) | CI gate: scans for ESL + encoding + test coverage |
| `encoding.rs` | **No changes** (Rust encoder is deferred) |

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Connectivity clauses produce false BMC counterexamples | U8: `skip_connectivity` parameter in `populate_sat_from_constraints` |
| pysat not available in test environment | Checked: pysat already used in `test_sat_solve_pbt.py:36` — same environment |
| Hypothesis strategies produce invalid ConstraintModel instances | U3: strategies build from existing `NetChannelVar` patterns; validate with `populate_sat_from_constraints` as smoke test |
| Exhaustive batch exceeds 30s target (SC4) | 2^10 = 1024 checks per instance, each <1ms via pysat, ~200 instances = ~200s *worst case*; but many instances have <10 primaries (256 or fewer assignments). Conservative estimate: ~20s on CI hardware with xdist |
| BMC false-positives from ESL semantics mismatch | SC3: zero false positives on correct `main` encoding, verified by U7 diagnostic tests |
| pytest-dependency chain regression | U4: update lattice diagnostics test to include bmc-l0 in expected chain |
| `constraint_model_grid` strategy changes break existing lattice tests | U3: add new strategies with tighter bounds; preserve existing `constraint_model_grid` signature and behavior for backward compatibility |
| CI gate script false negatives (misses missing ESL/BMC coverage) | U6: AST-based source-level check; unit-test the gate script itself against deliberate violations |

---

## Sources & References

- **Origin document:** `docs/brainstorms/2026-06-28-railway-bmc-encoding-correctness-requirements.md`
- **Constraint model:** `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py`
- **SAT model + encoder:** `packages/temper-placer/src/temper_placer/router_v6/sat_model.py`
- **Hypothesis strategies:** `packages/temper-placer/tests/router_v6/sat_property_strategies.py`
- **CDCL lattice:** `packages/temper-placer/tests/router_v6/test_sat_solve_pbt.py`
- **Lattice diagnostics:** `packages/temper-placer/tests/router_v6/test_sat_lattice_diagnostics.py`
- **CI profiles:** `packages/temper-placer/tests/router_v6/conftest.py`
- **CI gate pattern:** `scripts/import_linter_gate.py`
- **Rust sequential counter:** `packages/temper-rust-router/src/encoding.rs` (lines 78, 168-182, 264-305)
- **Constraint audit:** `packages/temper-placer/tests/router_v6/test_stage3_constraint_audit.py`
- Sinz, C. (2005). "Towards an Optimal CNF Encoding of Boolean Cardinality Constraints." CP 2005.
- Railway interlocking pattern: "declare safe routes, prove signal circuit never energizes an unsafe combination"
- Traceability convention: `docs/TRACEABILITY.md`
