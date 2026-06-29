---
date: "2026-06-28"
topic: railway-bmc-encoding-correctness
status: draft
---

# Railway-Style BMC Verification for Encoding Correctness

## Summary

Define an Encoder Specification Language (ESL) that declaratively states what each
constraint type means in terms of SAT primary-variable assignments. Then
bounded-model-check the actual CNF output from `populate_sat_from_constraints`
(sat_model.py:98) and `encode_to_cnf` (encoding.rs:78) against the ESL
specification for all reachable topologies up to a combinatorial bound (e.g.,
all configurations with ≤4 nets, ≤4 channels, and ≤2 non-exclusion constraint
types). Every ESL/CNF disagreement is a counterexample — a concrete routing
configuration the encoder gets wrong. Reuse the existing Hypothesis PBT
infrastructure for exhaustive base-case enumeration and strategy generation.
This mirrors the railway-interlocking pattern: declare safe routes, then prove
the signal logic implements every route and no unsafe ones.

---

## 1. Problem / Motivation

The Temper SAT pipeline currently uses a **3-layer correctness approach**:

| Layer | What | Where | Catch scope |
|-------|------|-------|-------------|
| L1. Formal proof | Inductive correctness argument in comments | encoding.rs:168–182 | Paper-level reasoning, not mechanically checked |
| L2. CDCL property lattice | FR1–FR6 properties (single-clause through cross-constraint composition) | test_sat_solve_pbt.py | Solver-level invariants (monotonicity, model validity, parsimony), not semantic correctness of the encoding |
| L3. Post-solve audit | `audit_result()` checks the solver assignment against the original constraint model | test_stage3_constraint_audit.py | Catches bugs *after* the solver assigns variables |

**The gap**: The AtMostK unsoundness bug (wrong exclusion-clause polarity in
`_encode_at_most_k`, sat_model.py:298) was caught only by the post-solve audit
(L3). Neither the formal proof (L1 — the comments were correct but the code
drifted) nor the CDCL lattice (L2 — the solver found *some* solution, just the
wrong one) caught it before the solver produced a bogus assignment.

The root cause: **no test ever checks that the CNF clauses encode the same
Boolean function as the constraint semantics.** The CDCL lattice tests *what the
solver does with the clauses*, not *whether the clauses mean the right thing.*
A polarity bug in `_encode_at_most_k` produces a CNF that is still satisfiable
— just satisfiable by assignments that violate the cardinality bound.

**What BMC adds (L0)**: Before the solver ever runs, verify that for every
primary-variable assignment, the ESL specification and the CNF encoding agree on
SAT/UNSAT. This catches *all* encoding bugs within the verification bound.
Railway interlocking systems use exactly this pattern: declare safe track
occupancy combinations (the ESL), then prove the signal circuit (the CNF) never
energizes an unsafe combination.

---

## 2. Users & Value

| User | Value |
|------|-------|
| Encoding author adding a new constraint type | ESL declaration forces them to state the semantics precisely; BMC catches polarity/omission/duplication bugs before any solver runs |
| CI reviewer | A failing BMC test produces a counterexample (primary-variable assignment) that is trivially understandable — no solver internals needed |
| Maintainer refactoring the encoder (e.g., switching from sequential-counter to totalizer) | BMC serves as a golden oracle: if the old and new encodings both pass the same ESL spec, they encode the same Boolean function |
| Future maintainer replacing the SAT solver backend | BMC is solver-independent — it checks clauses, not solver output |

---

## 3. Scope & Out of Scope

### In Scope

- **ESL design**: A Python DSL that declares, for each constraint type, a
  predicate over SAT primary-variable assignments. Example:
  ```python
  # ESL for CapacityConstraint: at most k of {x0, x1, ...} may be true
  capacity_esl = at_most_k(primary_vars=["x0", "x1", "x2", "x3"], k=2)
  ```

- **BMC verification engine**: For a given `ConstraintModel` + `SATModel`
  pair, enumerate all primary-variable assignments within the bound and check
  ESL-vs-CNF agreement. The engine calls the real `populate_sat_from_constraints`
  and extracts primary-variable clauses from the resulting `SATModel`.

- **Combinatorial topology enumeration**: Generate all reachable
  `ConstraintModel` instances up to the bound (≤4 nets, ≤4 channels, ≤2
  constraint types) via Hypothesis strategies, then BMC-check each one.

- **Counterexample format**: A counterexample is a tuple
  `(ConstraintModel, primary_var_assignment)` where the ESL predicate disagrees
  with the CNF. Printed in a diagnostic that can be trivially converted to a
  manual test case.

- **CI gate**: Run the BMC batch as a `pytest` test set under the existing
  `CI-full` Hypothesis profile (200 examples, 15000ms deadline) at PR time.

### Out of Scope

- **Verifying CDCL solver correctness** — covered by the existing property
  lattice (FR1–FR6, test_sat_solve_pbt.py)
- **Verifying constraint-audit correctness** — covered by the existing audit
  tests (test_stage3_constraint_audit.py)
- **Unbounded model checking or full SAT-solver equivalence** — BMC is bounded
  by the combinatorial enumeration
- **Replacing the inductive proof in comments** — the proof at
  encoding.rs:168–182 is still valuable as human documentation
- **Replacing any existing test** — BMC is additive, sitting as a new L0 layer
  before the CDCL lattice tests
- **BMC for the Rust-native `encode_to_cnf`** (encoding.rs:78) in the initial
  pass — the Python `populate_sat_from_constraints` (sat_model.py:98) is the
  primary target; Rust bindings can share the ESL spec later

---

## 4. Functional Requirements

### ESL Design

- **FR-LANG1.** ESL shall be a Python API composed of:
  - Predicate primitives: `all_true(vars)`, `any_true(vars)`, `at_most_k(vars, k)`,
    `exactly_one_of(vars)`, `implies(a, b)`, `iff(a, b)`
  - Composition operators: `and_(p1, p2, ...)`, `or_(p1, p2, ...)`
  - `eval_esl(predicate, assignment: dict[str, bool]) -> bool` — evaluate the
    predicate against an assignment.

- **FR-LANG2.** Each constraint type in the pipeline shall have exactly one ESL
  declaration. These declarations live alongside the constraint class
  definitions (constraint_model.py) for co-location:
  - `CapacityConstraint.esl()` → `at_most_k(vars, max_nets)`
  - `DiffPairConstraint.esl()` → `iff(p_var_name, n_var_name)`
  - `LayerConstraint.esl()` → `if allowed: all_true([var_name])` else
    `all_false([var_name])`

- **FR-LANG3.** The ESL must be **executable**: given a concrete
  `ConstraintModel` and a primary-variable assignment, `eval_esl` must return
  `True` iff the assignment satisfies all constraints in the model.
  This executable ESL is the *ground truth* against which the CNF is checked.

- **FR-LANG4.** Each ESL constructor maps to a set of Hypothesis strategies
  that generate valid constraint instances of that type, reusing existing
  strategies from `sat_property_strategies.py`.

### BMC Verification Engine

- **FR-BMC1.** For a given `(ConstraintModel, SATModel)` pair produced by
  `populate_sat_from_constraints`, the BMC engine shall:
  1. Extract the set of primary (non-auxiliary) SAT variables from the model
  2. Enumerate all 2^N assignments of those variables
  3. For each assignment, evaluate `eval_esl` and the CNF (via a SAT solver on
     the clauses with primary variables fixed to the assignment)
  4. Assert that `eval_esl(assignment) == CNF_satisfiable(assignment)` for
     all assignments

- **FR-BMC2.** The BMC engine shall use pysat (Glucose3) as the CNF oracle —
  the same solver already used in the CDCL lattice tests
  (test_sat_solve_pbt.py:36). For each primary-variable assignment, fix primary
  variables via unit clauses, then call `solver.solve()` on the remaining CNF.

- **FR-BMC3.** The verification bound defaults to N ≤ 10 primary variables
  (2^10 = 1024 assignments, sub-second per instance). The bound is
  configurable: tests targeting ≤4 nets × 4 channels = 16 primaries use N ≤ 10
  by assumption (auxiliary variables don't count toward the exhaustive
  enumeration bound since they're free in the SAT check).

- **FR-BMC4.** When a counterexample is found, the engine shall produce a
  diagnostic containing:
  - The full `ConstraintModel` (as JSON-ish dict)
  - The failing assignment in `{var_name: bool, ...}` format
  - The ESL evaluation result (`True`/`False`)
  - The CNF evaluation result (`SAT`/`UNSAT`)
  - The full CNF clause set (for manual inspection)
  - Which specific clause(s) cause the disagreement

- **FR-BMC5.** The BMC engine shall **not** import JAX or any JAX-dependent
  modules — NFR4 (no JAX in test imports) from the existing PBT suite applies
  equally to BMC.

### Combinatorial Topology Enumeration

- **FR-ENUM1.** A Hypothesis composite strategy shall generate all
  `(ConstraintModel, net_names)` pairs within the bound:
  ```
  max_nets=4, max_channels=4, max_layers=2, max_constraint_types=2
  ```
  This strategy reuses `constraint_model_grid` from
  sat_property_strategies.py:127 with tighter parameters.

- **FR-ENUM2.** The enumeration strategy shall cover all constraint-type
  combinations within the bound:
  - No constraints (connectivity-only)
  - Layer constraints only
  - Capacity constraints only (AtMostK triggered)
  - DiffPair constraints only
  - Layer + Capacity (cross-constraint)
  - Layer + DiffPair (cross-constraint)
  - All three simultaneously

- **FR-ENUM3.** The exhaustive base-case batch shall cover all `(n_nets,
  n_channels)` pairs where `n_nets × n_channels ≤ 10` and `n_layers ≤ 2`. This
  yields a finite set of canonical topologies:
  - 1 net × 1 channel (2 primaries)
  - 2 nets × 1 channel (2 primaries)
  - 1 net × 2 channels (2 primaries)
  - 2 nets × 2 channels (4 primaries)
  - 3 nets × 2 channels (6 primaries)
  - 2 nets × 3 channels (6 primaries)
  - 3 nets × 3 channels (9 primaries)
  - ... up to 4 nets × 4 channels (max 16 primaries, but constrained to ≤10
    primary variables for performance)

### Integration with Hypothesis

- **FR-HYP1.** The BMC batch shall use `@given` + `@settings` from Hypothesis
  ≥6.148.7 (NFR1 from the existing PBT suite). Strategies shall be imported from
  the shared `sat_property_strategies.py` module.

- **FR-HYP2.** The BMC batch shall observe the CI profile tier from
  conftest.py: CI-fast (50 examples) by default, CI-full (200 examples) in CI
  or when `CI-full` profile is active. The exhaustive base-case subset runs
  unconditionally (it's deterministic and fast).

- **FR-HYP3.** BMC tests shall be marked `@pytest.mark.bmc_l0_encoding` to
  distinguish them from the CDCL lattice tests (which use markers like
  `sat-l1`, `sat-l2`, etc. in the `pytest.mark.dependency` chain).

- **FR-HYP4.** The BMC batch shall fit within the existing 5000ms-per-example
  deadline. A single BMC instance (10 primary vars → 1024 SAT checks, each
  sub-millisecond for small CNFs) completes in <2s on typical hardware.

### Counterexample Semantics

- **FR-CEX1.** A counterexample is a **falsifying assignment** — a concrete
  primary-variable assignment `A` where either:
  - `eval_esl(A) == True` but the CNF is UNSAT under `A` (the encoder forbids
    a valid assignment; *false UNSAT*)
  - `eval_esl(A) == False` but the CNF is SAT under `A` (the encoder accepts
    an invalid assignment; *false SAT* — the AtMostK unsoundness class)

- **FR-CEX2.** False-SAT counterexamples are the higher-priority diagnostic
  because they produce "solutions" that violate the original constraints and
  would escape the CDCL lattice (which only checks that solver output satisfies
  CNF clauses, not that it satisfies routing constraints).

- **FR-CEX3.** Every counterexample must be reproducible by converting the
  diagnostic output to a standalone unit test that calls
  `populate_sat_from_constraints` with the exact `ConstraintModel` and checks
  the failing assignment.

### CI Gate Integration

- **FR-CI1.** The BMC batch shall run as part of the existing `router_v6` test
  suite (`pytest packages/temper-placer/tests/router_v6/`). It does not require
  a separate CI job.

- **FR-CI2.** The BMC tests shall use the `pytest-dependency` framework to
  declare a dependency on no higher-level test — BMC is a **pre-solve** check
  and must pass before any solver-dependent test is meaningful. It shall expose
  a marker `bmc-l0` that the existing lattice's `sat-l1` can depend on.

- **FR-CI3.** The exhaustive base-case batch (FR-ENUM3) runs on every commit
  (fast, deterministic, covers 100% of small topologies). The Hypothesis-driven
  random batch runs at PR time under the `CI-full` profile.

- **FR-CI4.** A BMC failure shall block PR merge (non-negotiable — an encoding
  bug in any constraint type invalidates every downstream routing decision).

### New-Encoding Adoption Protocol

- **FR-ADOPT1.** Adding a new constraint type `FooConstraint` to
  `constraint_model.py` shall require **before merge**:
  1. An `esl()` method on `FooConstraint`
  2. A `FooConstraint` entry in `populate_sat_from_constraints` (sat_model.py)
  3. An ESL registration in the shared ESL registry
  4. At least one exhaustive BMC test case covering the new constraint in
     isolation and in cross-constraint composition
  5. A lattice diagnostic test (analogous to the pattern in
     test_sat_lattice_diagnostics.py) that injects a deliberate bug and
     confirms the BMC layer catches it

- **FR-ADOPT2.** Changing the encoding of an existing constraint (e.g.,
  replacing the Sinz sequential counter with a totalizer inside
  `_encode_at_most_k`) shall **not** require ESL changes — the ESL declares
  *what* the constraint means, not *how* it's encoded. The existing BMC tests
  serve as regression gauntlet for the new encoding.

### Relationship to Existing Proptest Suites

- **FR-REL1.** The BMC layer sits **below** the CDCL lattice in the dependency
  chain: `BMC (L0) → CDCL lattice (L1–L5) → Constraint audit (post-solve
  verification)`. A BMC failure blocks all downstream tests.

- **FR-REL2.** The BMC layer does **not** duplicate any existing test:
  - CDCL lattice (test_sat_solve_pbt.py) tests solver behavior given clauses
  - Constraint audit (test_stage3_constraint_audit.py) tests solver output
    against constraints
  - BMC tests the encoding itself: clauses vs. constraint semantics

- **FR-REL3.** The BMC layer's Hypothesis strategies shall extend, not
  duplicate, `sat_property_strategies.py`. New strategies for topology
  enumeration live in the same module or a new `bmc_strategies.py` sibling.

---

## 5. Acceptance Examples

- **AE1. Covers FR-LANG1, FR-BMC1.** Given a `ConstraintModel` with one
  `LayerConstraint(allowed=False)` on variable `x0` and no other constraints,
  the ESL evaluates to `{x0: False}` being the only valid assignment. BMC
  checks all 2 assignments: `{x0: True}` is UNSAT (CNF has unit clause `¬x0`),
  `{x0: False}` is SAT. Agreement = pass.

- **AE2. Covers FR-BMC4, FR-CEX1.** Given the AtMostK unsoundness bug (the
  deliberate polarity swap in test_sat_lattice_diagnostics.py:116–119), BMC
  on a 3-variable k=2 instance finds the assignment `{x0=True, x1=True,
  x2=True}` where ESL says False (3 > 2) but the buggy CNF is SAT. Diagnostic:
  `Counterexample: AtMostK(3, 2), assignment={x0:T, x1:T, x2:T}, ESL=False,
  CNF=SAT`. This is the exact bug that the post-solve audit previously had to
  catch.

- **AE3. Covers FR-ENUM3.** The exhaustive batch runs 36 canonical topologies
  (all `(n_nets × n_channels)` pairs ≤10) with all constraint-type
  combinations, totaling ~200 BMC instances, completing in <30s on CI hardware.
  All pass.

- **AE4. Covers FR-ADOPT1.** A PR adding a new `MinSpacingConstraint` type
  includes: (a) an `esl()` method returning `at_most_k(vars, k)` with a
  topology-aware formula, (b) a `populate_sat_from_constraints` clause, (c) a
  BMC test with a deliberate polarity bug that the BMC layer catches.

- **AE5. Covers FR-CEX3.** The CI output for a BMC failure contains a
  copy-pasteable Python snippet:
  ```python
  def test_reproduce_bmc_failure():
      from temper_placer.router_v6.constraint_model import ConstraintModel, ...
      cm = ConstraintModel()
      cm.add_variable(NetChannelVar(name="x0", net_idx=0, channel_id="CH1"))
      ...
      sat = SATModel(variables=[], clauses=[])
      populate_sat_from_constraints(sat, cm, net_names=["N0"])
      # Assignment: {x0: True, x1: False}
      # ESL says: False, CNF says: SAT
      assert check_bmc(sat, cm, {"x0": True, "x1": False}) == ("esl_false", "cnf_sat")
  ```

- **AE6. Covers FR-REL2.** Running `pytest -k "bmc_l0"` runs only the BMC
  layer. Running `pytest -k "sat-l1"` runs the CDCL lattice's first level,
  which depends on `bmc-l0` passing. The layers are independently runnable and
  ordered.

---

## 6. Success Criteria

- **SC1. AtMostK regression gauntlet.** The BMC exhaustive batch catches the
  known AtMostK polarity bug (test_sat_lattice_diagnostics.py:116) as a
  false-SAT counterexample — the bug that the existing CDCL lattice missed.

- **SC2. False-negative immunity.** A deliberate bug in any constraint
  encoding (layer omission, diff-pair polarity swap, wrong AtMostK k-value) is
  caught by BMC as either a false-SAT or false-UNSAT counterexample for at
  least one topology within the enumeration bound.

- **SC3. Zero false positives.** On the correct encoding (current `main`),
  every BMC instance — both the exhaustive batch and the Hypothesis batch at
  200 examples — produces zero counterexamples.

- **SC4. Exhaustive batch ≤ 30s.** The complete exhaustive base-case
  enumeration runs in ≤30 seconds on CI hardware (≤1024 SAT checks per
  instance × ~200 instances × sub-ms per SAT check).

- **SC5. Diagnostic actionability.** Every counterexample diagnostic includes
  enough information to reproduce the failure without re-running Hypothesis —
  the copy-pasteable snippet (AE5) reproduces the exact counterexample.

- **SC6. FI gate on adoption.** A scriptable check (similar to the existing
  `import_linter_gate.py`) verifies that every constraint type in
  `constraint_model.py` has a corresponding ESL declaration and a BMC test
  entry. Missing either → CI failure.

---

## 7. Scope Boundaries

- **Does not** verify the Rust `encode_to_cnf` (encoding.rs:78) in the initial
  pass. The Python `populate_sat_from_constraints` is the primary target.
  However, the ESL spec is language-agnostic — the same predicates can validate
  the Rust encoder's CnfFormula output if exposed via PyO3.

- **Does not** replace or remove `audit_result()` or the post-solve audit
  tests — those catch bugs in the solver (assignment doesn't satisfy constraints
  despite correct encoding), while BMC catches bugs in the encoding.

- **Does not** require any changes to the Rust crate or the splr solver.

- **Does not** require JAX imports (NFR4 compliance).

- **Does not** verify constraint-model *generation* correctness (the
  `ModelBuilder` in constraint_model.py:153) — BMC checks the encoder, not the
  builder. Builder bugs (wrong constraint counts, missing variables) are
  already covered by `test_stage3_constraint_audit.py` and validator tests.

### Deferred for Later

- **Extending BMC to the Rust `encode_to_cnf`**: After the Python BMC layer
  proves the pattern, expose Rust `CnfFormula` to Python via PyO3, share the
  ESL spec, and run the same BMC batch on both encoders. This catches
  Rust/Python encoding drift.
- **Unbounded induction**: For constraint encodings that are correct by
  structural induction (like the Sinz sequential counter), prove a lemma that
  "BMC passing for n ≤ 10 + ESL satisfaction for n implies ESL satisfaction for
  n+1" — this would close the gap between bounded verification and the existing
  informal inductive proof.
- **ESL-to-CNF synthesis**: Use the ESL spec as the single source of truth and
  *generate* the CNF encoding from it, eliminating the implementation entirely.
  This is a longer-term architecture change (codegen approach, similar to
  `firmware/config.h` generation from `config.yaml`) and is deferred past the
  initial BMC pass.

---

## 8. Key Decisions

- **ESL as executable Python predicates over a combined `SATModel` +
  `ConstraintModel`.** The existing codebase already has Python `SATModel` and
  `ConstraintModel` types (sat_model.py, constraint_model.py). The ESL
  evaluates directly against a `ConstraintModel` + assignment dict, and the
  CNF is checked via pysat with primary variables fixed. This avoids the need
  for a separate ESL interpreter or formal notation.

- **BMC over the CNF trivially extended, not the complete solver output.**
  For each primary assignment, we add unit clauses fixing primary variables and
  ask pysat whether the remaining CNF (with free auxiliary variables) is
  satisfiable. This matches the actual solver usage: primary variables are
  decided by the solver, and a BMC counterexample is a primary assignment the
  CNF incorrectly accepts or rejects.

- **Bound of N ≤ 10 primary variables for exhaustive enumeration (2^10 =
  1024).** This covers all configurations with ≤4 nets × ≤3 channels (12
  primaries → 4096 is borderline; 4 nets × 2 channels = 8 primaries → 256
  assignments, very fast). The `constraint_model_grid` strategy's default
  max_cells=4, max_nets=3, max_layers=2 already stays within this bound for
  most instances.

- **BMC as L0, not replacing the CDCL lattice.** The CDCL lattice (FR1–FR6)
  tests solver behavior (incremental solve, monotonicity, parsimony). BMC tests
  encoding correctness (clause → semantics correspondence). Both are necessary;
  neither subsumes the other. The combined test pyramid is:
  ```
  L0: BMC (encoding correctness)       — new
  L1: Single-clause SAT                — existing
  L2: Multi-clause conjunction         — existing
  L3: CDCL incremental                 — existing
  L4: AtMostK encoding verification    — existing (cross-validates BMC)
  L5: Cross-constraint composition     — existing
  L6: Parsimony invariant              — existing
  Post: Constraint audit               — existing
  ```

- **Shared Hypothesis strategies with bounded generators.** The BMC batch's
  topology enumeration strategies extend `sat_property_strategies.py` rather
  than creating a parallel strategy module. The existing
  `constraint_model_grid` strategy (sat_property_strategies.py:127) is already
  close to what BMC needs — it just needs tighter parameter bounds and
  constraint-type coverage.

- **Adoption gate as CI check, not code review convention.** FR-CI6 mandates a
  scriptable adoption gate (analogous to `import_linter_gate.py`) that checks
  every `Constraint` subclass has a corresponding ESL declaration and BMC test.
  Human reviewers shouldn't need to manually verify this.

---

## 9. Dependencies / Assumptions

- The existing Hypothesis PBT infrastructure (strategies in
  sat_property_strategies.py, CI profiles in conftest.py, pysat integration in
  test_sat_solve_pbt.py) is the foundation for BMC — BMC strategies import from
  `sat_property_strategies.py` and BMC tests use the same pysat pattern.
- pysat (python-sat ≥0.1.8) is available in the test environment — already
  confirmed by the existing CDCL lattice tests.
- The Python `SATModel` and `_encode_at_most_k` (sat_model.py) are the primary
  encoding targets. The Rust `encoding.rs` is equivalent (same Sinz algorithm)
  but not tested by BMC in the initial pass.
- The `ConstraintModel` types (constraint_model.py) are stable enough that
  adding `esl()` methods doesn't break other stages — ESL methods are pure
  functions with no side effects.
- The existing `pytest-dependency` framework supports ordering BMC before
  CDCL lattice — the `depends` mechanism in test_sat_solve_pbt.py:56 already
  demonstrates this pattern.
- The combinatorial enumeration bound (N ≤ 10 primary variables) is sufficient
  to catch encoding bugs — the AtMostK polarity bug is caught at n=3, k=2 (3
  primaries), well within the bound. Constraint-type composition bugs (e.g.,
  layer + capacity interaction) are caught within 4 nets × 2 channels = 8
  primaries.
- CI hardware has sufficient CPU for the exhaustive batch (≤30s target) — the
  existing exhaustive tests (exhaustive_at_most_k_n1_to_n8 in encoding.rs:264)
  complete in milliseconds on a single core; the BMC batch distributes across
  pytest-xdist workers if available.

### Related Documents

- **Sinz sequential counter verification**: encoding.rs:168–182 (inductive
  proof) and encoding.rs:264–305 (exhaustive test, 3,286 checks for n ≤ 8)
- **CDCL property lattice**: test_sat_solve_pbt.py (FR1–FR6, 5-level lattice
  with pytest-dependency)
- **Lattice diagnostics**: test_sat_lattice_diagnostics.py (deliberate bug
  injection to verify lattice ordering)
- **Hypothesis strategies**: sat_property_strategies.py (shared strategies for
  SAT variables, clauses, constraint models)
- **Constraint audit**: test_stage3_constraint_audit.py (post-solve verification
  against original constraints)
- **CI profiles**: conftest.py (CI-fast / CI-full Hypothesis profiles)
- **ATMostK unsoundness reproduction**: test_sat_lattice_diagnostics.py:42–178
  (deliberate polarity swap in exclusion clauses)
