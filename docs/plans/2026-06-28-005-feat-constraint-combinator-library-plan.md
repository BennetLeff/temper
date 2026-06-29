---
title: "feat: Constraint Combinator Library with Soundness-Preserving Composition"
type: feat
status: active
date: 2026-06-28
origin: docs/brainstorms/2026-06-28-constraint-combinator-library-requirements.md
dependencies:
  - docs/brainstorms/2026-06-28-constraint-lowering-compiler-requirements.md  # R5 boundary
---

# Constraint Combinator Library

## Summary

Add a `combinator` module inside `packages/temper-rust-router/` that defines proven sound
primitive CNF encodings (P1–P4 active, P3/P5/P6 deferred), three composition operators
(Conjoin, Conditional, RestrictDomain), a rewrite engine (RW1–RW7) that eliminates
redundancy from `InternalConstraintModel` before CNF encoding, and a `PROOFS.toml`
proof registry enforced by CI.

The rewrite engine reduces clause count by subsuming looser cardinality bounds under
tighter ones, propagating unit clauses through capacity constraints, and deduplicating
identical constraints — all with provable termination, confluence, and semantics
preservation. No new `InternalConstraint` variants are added in the initial release;
the module works within the existing 3-variant enum (`types.rs:290-306`).

---

## Problem Frame

The SAT model has 3 low-level constraint types with no formal composition semantics.
When constraints overlap on the same net/channel pair, they are concatenated as clauses
in `encode_to_cnf` (`encoding.rs:111-151`). Three problems:

1. **Redundant cardinality bounds.** Multiple `Capacity` constraints on the same channel
   produce independent sequential-counter encodings with separate auxiliary variables.
2. **Implicit semantics via clause concatenation.** Layer restrictions and capacity
   constraints on the same channel interact implicitly — the pipeline author cannot
   express "unit clause + cardinality" as a composed entity the system can simplify.
3. **Unsoundness risk on new encodings.** No formal framework for proving CNF
   encodings correct. The current approach — ad-hoc encoding + exhaustive n≤8 tests
   (`encoding.rs:264-305`) — is developer-discipline-based.

The combinator addresses all three: primitives carry inductive correctness proofs,
composition preserves soundness structurally, and the rewrite engine eliminates
structural redundancy before clause generation.

---

## Architecture Overview

### Type Hierarchy

```
Composition Operators  (Conjoin, Conditional, RestrictDomain)
        │                       ↑ RW1-RW7 rewrite on flattened
        ▼  lower_composed()     │ InternalConstraint instances
Primitive Types        (P1–P4: MutualExclusion, CardinalityBound,
                        LayerAssignment; P3/P5/P6 deferred)
        │
        ▼  map to variants
InternalConstraint      (Capacity, DiffPair, LayerRestriction)
        │
        ▼  encode_to_cnf()
CNF Clauses             (fed to CaDiCaL via rustsat)
```

### Pipeline Integration (lib.rs)

```
model_from_python()          ← existing: Python → InternalConstraintModel
    │
    ▼
combinator::rewrite(&model)  ← NEW: applies RW1-RW7, returns simplified model
    │
    ▼
encode_to_cnf(&model)        ← existing: InternalConstraintModel → CnfFormula
    │
    ▼
solve_with_cadical(&cnf)     ← existing
```

The rewrite engine runs synchronously after `model_from_python` and before
`encode_to_cnf`. It must complete in <100ms for the full Temper PCB model
(~6,000 channels, ~130K variables).

### Module Location

The combinator lives as a new module `combinator/` inside `packages/temper-rust-router/`,
not a separate crate. This gives zero-friction access to `InternalConstraint` and avoids
circular-dependency risk. The crate boundary decision can be revisited when the
Constraint Lowering Compiler (a separate crate) needs to depend on combinator types.

```
packages/temper-rust-router/src/
    combinator/
        mod.rs                  # module root, pub re-exports
        types.rs                # composition tree types
        primitives.rs           # P1-P4 primitive definitions + desugaring
        rewrite.rs              # RW1-RW7 rewrite engine
        lower.rs                # lower_composed() implementation
        proofs.rs               # debug-assert proof registry
    lib.rs                      # modified: wire rewrite before encode_to_cnf
    types.rs                    # unchanged (no new InternalConstraint variants)
    encoding.rs                 # unchanged
    audit.rs                    # unchanged (no new variants to audit)
```

---

## Unit Decomposition

### U1. Composition Tree Type Definitions (`combinator/types.rs`)

Define the composition tree IR that the combinator manipulates internally.

**Types to define:**

```rust
/// A primitive constraint in isolation (before composition).
/// P3/P5/P6 are deferred — no InternalConstraint variants yet.
#[derive(Clone, Debug, PartialEq)]
pub enum PrimitiveConstraint {
    /// P1. MutualExclusion: equality mode (x ↔ y)
    MutualExclusion {
        p_var_name: String,
        n_var_name: String,
    },
    /// P2. CardinalityBound: AtMostK over a set of Boolean variables on one channel
    CardinalityBound {
        channel_id: String,
        k: usize,
        terms: Vec<(String, f64)>,  // (var_name, width)
    },
    /// P4. LayerAssignment: unit clause x = v
    LayerAssignment {
        var_name: String,
        value: bool,
    },
    // P3 (SpatialOrder), P5 (AdjacencyPair), P6 (SeparationDistance) deferred
}

/// A composition tree node.
#[derive(Clone, Debug, PartialEq)]
pub enum ComposedConstraint {
    /// A leaf: a single primitive constraint.
    Primitive(PrimitiveConstraint),
    /// C1 ∧ C2: both must hold.
    Conjoin(Box<ComposedConstraint>, Box<ComposedConstraint>),
    /// A → C: if all antecedent assignments hold, constraint C must hold.
    Conditional {
        antecedent: Vec<(String, bool)>,  // [(var_name, value)]
        consequent: Box<ComposedConstraint>,
    },
    /// C|[vars]: restrict C to apply only to variables in the given set.
    RestrictDomain {
        inner: Box<ComposedConstraint>,
        vars: Vec<String>,
    },
}
```

**Helper constructors** (public API for constraint authors):

- `MutualExclusion::equality(p_var_name, n_var_name)` → `ComposedConstraint`
- `MutualExclusion::exclusive(p_var_name, n_var_name)` → `ComposedConstraint`
  (deferred: exclusive mode has no InternalConstraint mapping yet)
- `CardinalityBound::new(channel_id, k, terms)` → `ComposedConstraint`
- `LayerAssignment::new(var_name, value)` → `ComposedConstraint`
- `compose_conjoin(a: ComposedConstraint, b: ComposedConstraint)` → `ComposedConstraint`
- `compose_conditional(antecedent, consequent)` → `ComposedConstraint`
- `compose_restrict_domain(inner, vars)` → `ComposedConstraint`

**Acceptance:** `cargo build` compiles with new types. Types are `pub` but only re-exported
from `combinator::types` (not through `lib.rs` until U5 integration).

---

### U2. lower_composed() — Composition Tree → InternalConstraintModel (`combinator/lower.rs`)

Expand a `ComposedConstraint` tree into a flat `InternalConstraintModel`. This is the
bridge between the composition IR and the existing CNF pipeline.

**Algorithm:**

```
lower_composed(tree) → InternalConstraintModel:
  - Conjoin(A, B)  → A.lower() ∪ B.lower()  (merge variable+constraint lists)
  - Conditional(A → C):
      For each (var, val) in A, emit LayerAssignment(var, val)
      Emit C.lower()
      Additionally, for each InternalConstraint in C.lower(),
        add the antecedent literals as guard variables tracked in a side-channel
        (for future UNSAT provenance; initially the antecedent vars are
         independent unit clauses — sound because A is modeled as unit
         clauses, not as implications in CNF)
      NOTE: For the initial release, Conditional desugars by adding the
        antecedent as a set of LayerAssignment unit clauses AND C's lowered
        constraints. The implication-as-clause encoding (¬A ∨ C) is deferred
        until the audit can track guared constraints.
  - RestrictDomain(C, vars):
      lower C, then filter each InternalConstraint's variable set to only
        include variables in `vars`. Drop any constraint whose variable set
        becomes empty.
  - Primitive(P1 MutualExclusion) → DiffPair { p_var_name, n_var_name }
  - Primitive(P2 CardinalityBound) → Capacity { channel_id, capacity derived
      from k and min_width, slack_factor=1.0, terms }
  - Primitive(P4 LayerAssignment) → LayerRestriction { var_name, allowed=value }
```

**Key design choice:** `Conditional` is lowered as conjunctions of unit clauses
(antecedent assignments) plus the consequent's constraints. This is correct because
the SAT solver sees the antecedent as independent unit clauses, and the consequent
constraints as independent clauses — the SAT solver's job is to satisfy all of them.
If the antecedent is not chosen (the unit clauses are violated), the solver must still
satisfy the consequent constraints, which is a _weaker_ constraint than implication.
For the initial release, this is acceptable — the true implication semantics will be
added as a refinement in a follow-up (tracked in deferred items).

**Capacity derivation from P2 CardinalityBound:** The existing Capacity encoding
computes `max_nets = floor(capacity * slack / min_width)`. To go from `CardinalityBound(k=k, terms)`
to `Capacity(channel_id, capacity, slack_factor, terms)`:
- `slack_factor = 1.0`
- `min_width = min(terms[*].1)`
- `capacity = k * min_width` (so that `floor(capacity * 1.0 / min_width) = floor(k) = k`)

**Acceptance (AE1):**
```rust
let p2 = ComposedConstraint::Primitive(PrimitiveConstraint::CardinalityBound {
    channel_id: "L1_E5".into(), k: 3,
    terms: vec![("A".into(), 1.0), ("B".into(), 1.0), ("C".into(), 1.0)],
});
let p4 = ComposedConstraint::Primitive(PrimitiveConstraint::LayerAssignment {
    var_name: "A".into(), value: true,
});
let composed = ComposedConstraint::Conjoin(Box::new(p2), Box::new(p4));
let model = lower_composed(&composed);
// model.constraints contains: Capacity(k=3, [...]) + LayerRestriction("A"=true)
```

---

### U3. Rewrite Engine Core (`combinator/rewrite.rs`)

Apply RW1–RW7 to an `InternalConstraintModel` until fixpoint. The engine operates on
the flattened `InternalConstraint` list — treating it as a multiset of constraints.

**Error type:**
```rust
#[derive(Debug, PartialEq)]
pub enum RewriteError {
    /// Structural contradiction detected pre-solve (RW7).
    UnsatPreSolve {
        var_name: String,
        constraint1: String,
        constraint2: String,
    },
}
```

**Algorithm skeleton:**
```rust
pub fn rewrite(model: &InternalConstraintModel) -> Result<InternalConstraintModel, RewriteError> {
    let mut constraints = model.constraints.clone();
    let mut changed = true;
    let max_iterations = constraints.len() * 2; // termination bound
    let mut iteration = 0;

    while changed && iteration < max_iterations {
        changed = false;
        iteration += 1;

// --- RW7. LayerConflict (must fire first — detects UNSAT) ---
        if let Some(err) = detect_layer_conflict(&constraints) {
            return Err(err);
        }

// --- RW5. DiffPairDedup ---
        let before = constraints.len();
        constraints = dedup_diff_pairs(constraints);
        if constraints.len() < before { changed = true; }

// --- RW6. LayerDedup ---
        let before = constraints.len();
        constraints = dedup_layers(constraints);  // drop duplicates with same (var, allowed)
        if constraints.len() < before { changed = true; }

// --- RW3. LayerPropagate (true unit clause removes var from Capacity + decrements K) ---
        let before = constraints.len();
        constraints = propagate_layer_true(&constraints);
        if constraints.len() != before { changed = true; }

// --- RW4. LayerPropagateFalse (false unit clause removes var from Capacity, K unchanged) ---
        let before = constraints.len();
        constraints = propagate_layer_false(&constraints);
        if constraints.len() != before { changed = true; }

// --- RW1. CapSubsume ---
        let before = constraints.len();
        constraints = subsume_capacity(&constraints);
        if constraints.len() != before { changed = true; }

// --- RW2. CapEliminate (after RW1 may produce K >= |V|) ---
        let before = constraints.len();
        constraints = eliminate_trivial_capacity(&constraints);
        if constraints.len() < before { changed = true; }
    }

    Ok(InternalConstraintModel {
        variables: model.variables.clone(),
        constraints,
    })
}
```

**RW1. CapSubsume:**
- Group Capacity constraints by `channel_id`.
- For each pair `(C1: K1, V1)` and `(C2: K2, V2)`:
  - If V1 ⊆ V2 and K1 ≤ K2: tighten C2 → `min(K2, K1 + |V2 \ V1|)`
  - Use hash sets of var names for O(1) subset checks.
- After tightening, if two Capacity constraints end up with identical variable sets,
  keep only the one with the smaller K.

**RW2. CapEliminate:**
- Remove any `Capacity { terms: V, capacity, slack_factor, ... }` where
  the computed `max_nets ≥ |V|` (the constraint is trivially satisfiable).
  `max_nets = floor(capacity * slack / min_width)`.

**RW3. LayerPropagate:**
- Collect all `LayerRestriction { var_name, allowed: true }`.
- For each such unit clause, find all Capacity constraints containing `var_name`.
  Remove the variable from `terms`, replace K with K-1.
  After removal, if K=0 and |V|>0, add unit clauses (¬v) for each v∈V and remove the Capacity.

**RW4. LayerPropagateFalse:**
- Collect all `LayerRestriction { var_name, allowed: false }`.
- Remove `var_name` from all Capacity constraints' `terms`. K stays unchanged.

**RW5. DiffPairDedup:**
- Drop duplicate `DiffPair { channel_id, p_var_name, n_var_name }` (keep first).

**RW6. LayerDedup:**
- Drop duplicate `LayerRestriction { var_name, allowed }` with same (var_name, allowed).
  If two LayerRestrictions share var_name but differ in allowed, RW7 fires first.

**RW7. LayerConflict:**
- Scan for `LayerRestriction(var, true)` and `LayerRestriction(var, false)`.
  Return `RewriteError::UnsatPreSolve { var_name, ... }`.

**Design constraint:** The rewrite engine MUST be confluent. Rule order is fixed
(conflict detection first, dedup first to reduce work for propagation, propagation
before subsumption because propagation shrinks variable sets, subsumption before
trivial elimination because subsumption may produce trivially-satisfiable constraints).
The fixpoint loop ensures all rules are exhausted regardless of order dependencies;
the fixed order is a performance optimization, not a correctness requirement.

**Termination proof sketch:** Each rule strictly reduces some measure:
- Dedup (RW5/RW6): reduces constraint count
- Eliminate (RW2): reduces constraint count
- Propagate (RW3/RW4): removes terms from Capacity, potentially reducing remaining constraints
- Subsumption (RW1): tightens bounds (monotonic decrease in per-variable-set K)
The maximum possible iterations ≤ initial constraint count (each iteration must change
at least one constraint's term set, K, or remove a constraint).

**Acceptance (AE2):**
```rust
let model = InternalConstraintModel {
    constraints: vec![
        Capacity { channel_id: "L1_E5", capacity: 4.0, slack: 1.0, terms: vec![("A",1.0),("B",1.0),("C",1.0),("D",1.0),("E",1.0)] },
        LayerRestriction { var_name: "A", allowed: true },
    ],
};
let rewritten = rewrite(&model).unwrap();
// Capacity terms: [B, C, D, E], max_k computed as 3 (was 4, decremented for A removal)
// LayerRestriction("A"=true) preserved
```

**Acceptance (AE3):**
```rust
let model = InternalConstraintModel {
    constraints: vec![
        LayerRestriction { var_name: "N3_L1_E5", allowed: true },
        LayerRestriction { var_name: "N3_L1_E5", allowed: false },
    ],
};
let err = rewrite(&model).unwrap_err();
assert!(matches!(err, RewriteError::UnsatPreSolve { .. }));
```

---

### U4. Proof Framework (`combinator/proofs.rs`, `PROOFS.toml`)

**PROOFS.toml** (crate root):
```toml
[primitive.P1_MutualExclusion]
encoding = "combinator/primitives.rs"
exhaustive_test = "combinator/primitives.rs::tests::exhaustive_p1_n4"
cross_validation = "combinator/primitives.rs::tests::cross_validate_p1_100_random"

[primitive.P2_CardinalityBound]
encoding = "combinator/primitives.rs"
proof_inductive = "docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md"
exhaustive_test = "encoding.rs::tests::exhaustive_at_most_k_n1_to_n8"
cross_validation = "combinator/primitives.rs::tests::cross_validate_p2_100_random"

[primitive.P4_LayerAssignment]
encoding = "combinator/primitives.rs"
exhaustive_test = "combinator/primitives.rs::tests::exhaustive_p4"

[compose.Conjoin]
proof = "combinator/compose.rs::tests::conjoin_soundness"

[compose.Conditional]
proof = "combinator/compose.rs::tests::conditional_soundness"

[compose.RestrictDomain]
proof = "combinator/compose.rs::tests::restrict_soundness"

[rewrite.engine]
exhaustive_n6 = "combinator/rewrite.rs::tests::exhaustive_rewrite_preserves_sat"
confluence_10000 = "combinator/rewrite.rs::tests::confluence_proptest_10000"
```

**CI gate:** A script (`scripts/verify_proofs.py`) reads `PROOFS.toml`, checks that
every referenced:
- Encoding source file exists
- Test function exists (by grepping for `fn <test_name>` in the source file)
- For cross-validation tests: verify `proptest` or `hypothesis` dependency exists

This gate runs in `python-tests.yml` and blocks merge.

**Compile-time assertions** (in `combinator/proofs.rs`):
```rust
/// Debug-assert proof registry. At build time, verifies that every primitive
/// P1-P4 has exhaustive n≤4 tests registered in PROOFS.toml.
/// This is a manual check — CI enforces PROOFS.toml completeness via the
/// verify_proofs.py script.
#[cfg(debug_assertions)]
pub mod proof_registry {
    // Document the proof chain. No runtime cost.
    // CI checks completeness via PROOFS.toml + verify_proofs.py.
}
```

---

### U5. Integration into lib.rs Pipeline

Wire the rewrite engine between `model_from_python` and `encode_to_cnf` in `lib.rs`.

**Current call chain (lines 36-40):**
```rust
let model: InternalConstraintModel =
    types_py_bridge::model_from_python(net_names.clone(), py_vars, py_cons)?;
let (cnf, var_names) = encoding::encode_to_cnf(&model);
```

**New call chain:**
```rust
let model: InternalConstraintModel =
    types_py_bridge::model_from_python(net_names.clone(), py_vars, py_cons)?;

// Apply combinator rewrite engine
let model = combinator::rewrite::rewrite(&model)
    .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("{:?}", e)))?;

let (cnf, var_names) = encoding::encode_to_cnf(&model);
```

**Metrics collection** (debug-only):
- Log the pre-rewrite constraint count, post-rewrite constraint count
- Log clause count delta (pre vs post if measured)
- Gate: if rewrite adds constraints (`post > pre`), emit a `tracing::warn!` in debug

**Error propagation:**
- `UnsatPreSolve` → Python `RuntimeError` with message naming conflicting variables
- The error is caught by `RouterV6Pipeline` which can surface it as a pre-solve failure
  (no SAT solver invocation needed)

**Acceptance:** Existing `test_topology_solver.py` tests pass. `cargo test` in the Rust
crate passes. A manual run of the Temper PCB pipeline shows no regression.

---

### U6. Test Infrastructure

All tests live in `src/combinator/` test modules (module-level `#[cfg(test)]`).

#### Tier 1: Primitive Encoding Correctness

| Test | Location | Description | Pattern from |
|------|----------|-------------|-------------|
| `exhaustive_p1_n4` | `combinator/primitives.rs` | For all 2^4 assignments of 4 vars, verify MutualExclusion CNF is SAT iff equality holds | Analogous to `encoding.rs:264` |
| `exhaustive_p2_n8` | reuses `encoding.rs:264` | Existing AtMostK exhaustive test covers P2 | Already in codebase |
| `exhaustive_p4` | `combinator/primitives.rs` | Unit clause trivially correct; test for all 2^1=2 assignments | New |
| `cross_validate_p1_100_random` | `combinator/primitives.rs` | Generate 100 random var-pair assignments; verify Combinator encoding matches independent reference (DPLL) | New |
| `cross_validate_p2_100_random` | `combinator/primitives.rs` | Generate 100 random (n,k) pairs; verify AtMostK encoding matches DPLL count check | New |

#### Tier 2: Composition Soundness

| Test | Location | Description |
|------|----------|-------------|
| `conjoin_soundness` | `combinator/compose.rs` | `verify(C1 ∧ C2) ↔ verify(C1) ∧ verify(C2)` for all n≤4 primitive combinations via DPLL |
| `conditional_soundness` | `combinator/compose.rs` | `verify(A → C)` matches truth-table implication for all antecedent assignments |
| `restrict_soundness` | `combinator/compose.rs` | `verify(C\|[vars])` admits only assignments where C holds and unused vars are unconstrained |
| `compositional_dpll_all_small` | `combinator/compose.rs` | For all n≤4, all primitive combinations with all 3 operators, DPLL agrees with conjunctive semantics |

#### Tier 3: Rewrite Engine Correctness

| Test | Location | Description |
|------|----------|-------------|
| `rw1_subsume_equivalence` | `combinator/rewrite.rs` | For all n≤5 var sets, subsumption preserves SAT/UNSAT |
| `rw2_eliminate_equivalence` | `combinator/rewrite.rs` | Trivial capacity elimination preserves SAT/UNSAT |
| `rw3_propagate_equivalence` | `combinator/rewrite.rs` | Unit propagation through capacity preserves SAT/UNSAT |
| `rw4_false_propagate_equivalence` | `combinator/rewrite.rs` | False unit removal from capacity preserves SAT/UNSAT |
| `rw5_rw6_dedup_equivalence` | `combinator/rewrite.rs` | Dedup is idempotent and preserves SAT/UNSAT |
| `rw7_conflict_detection` | `combinator/rewrite.rs` | Contradictory layer restrictions produce UnsatPreSolve |
| `exhaustive_rewrite_preserves_sat` | `combinator/rewrite.rs` | For n≤6 variables, all possible constraint combinations, rewrite output is SAT-equivalent to input (DPLL verified) |
| `confluence_proptest_10000` | `combinator/rewrite.rs` | With `proptest`, generate 10,000 random constraint models, apply rewrite in multiple rule orderings, verify all orderings yield same final model |
| `fixpoint_termination` | `combinator/rewrite.rs` | Rewrite terminates in ≤ 2*|constraints| iterations for all random models |
| `no_false_unsat` | `combinator/rewrite.rs` | When RW7 fires, a DPLL solver independently confirms UNSAT |
| `rw3_post_zero_k_adds_neg_unit` | `combinator/rewrite.rs` | After RW3, if K=0 and V non-empty, unit clauses (¬v) are added for all remaining vars |

#### Tier 4: Integration Tests

| Test | Location | Description |
|------|----------|-------------|
| `roundtrip_modelbuilder_rewrite` | `combinator/integration.rs` | Build a model matching typical ModelBuilder output; rewrite it; verify clause count ≤ original; verify same SAT/UNSAT via DPLL |
| `audit_compatibility` | `combinator/integration.rs` | Rewritten model passes all existing audit tests unchanged |
| `no_regression_atmostk_exhaustive` | `combinator/integration.rs` | Rewrite engine is a no-op on standalone AtMostK encodings (no LayerRestrictions to trigger RW3/RW4) |
| `no_regression_diffpair` | `combinator/integration.rs` | DiffPair-only model is unchanged by rewrite (dedup only if duplicates exist) |
| `performance_gate_lt_100ms` | `combinator/bench.rs` | Micro-benchmark: rewrite a model with 6,000 Capacity + 1,000 LayerRestriction in <100ms |

#### Tier 5: CI Gates

Added to `python-tests.yml` and `cargo test`:
- `cargo test --lib` — all combinator tests run on every push
- `scripts/verify_proofs.py` — `PROOFS.toml` completeness, every push, blocks merge
- Nightly: `proptest` 10,000-model confluence + fixpoint tests (not on every push; these run ~30s)
- Non-regression gate: clause count does not increase after rewrite on the Temper PCB model
  (measured in nightly CI by running the pipeline and comparing clause counts)

**Test dependencies added to `Cargo.toml` `[dev-dependencies]`:**
```toml
proptest = "1"
```

---

### U7. Documentation & Discoverability

- Module-level `//!` doc on `combinator/mod.rs` explaining the type hierarchy and pipeline
- Each rewrite rule (RW1-RW7) has a doc comment with:
  - Input pattern
  - Output pattern
  - Termination argument (what measure decreases)
  - Confluence argument (why rule order doesn't matter)
- Primitives (P1-P4) each carry doc comments referencing their proof location
- Deferred primitives (P3/P5/P6) are declared as `#[allow(dead_code)]` type stubs
  with doc comments explaining why they're deferred

---

## Test Scenarios (End-to-End)

### TS1: No Overlap (Rewrite No-Op)

A model with one Capacity per channel, one DiffPair per pair, one LayerRestriction per var.
Rewrite returns the identical model (no rules fire). DPLL confirms same SAT outcomes.

### TS2: Overlapping Capacity with Subsumption (RW1 + RW2)

Channel `L1_E5`: `Capacity(K=2, V={A,B,C})` and `Capacity(K=5, V={A,B,C,D,E})`.
Expected rewrite:
1. RW1: V1⊆V2, K1=2≤5 → tighten second to K=min(5, 2+2)=4
2. Second constraint K=4 < |V|=5, so it survives. Result: 2 constraints remain.
3. No RW2 trigger (K < |V| for both).

### TS3: Layer Propagation + Chain Reaction (RW3 → RW2)

Channel `L1_E5`: `Capacity(K=1, V={A,B})` and `LayerRestriction(A=true)`.
Expected rewrite:
1. RW3: Remove A from Capacity, K becomes 0, V={B}
2. Post-RW3 chain: K=0, |V|=1 → add unit clause (¬B), remove Capacity
3. Result: LayerRestriction(A=true) + new LayerRestriction(B=false)

### TS4: Structural Contradiction (RW7)

`LayerRestriction(N3_L1_E5, true)` and `LayerRestriction(N3_L1_E5, false)`.
Rewrite returns `UnsatPreSolve { var_name: "N3_L1_E5", ... }`.
SAT solver is never invoked.

### TS5: DiffPair Dedup (RW5)

Two identical `DiffPair(CH, p, n)` constraints.
Rewrite returns exactly one. CNF has 2 clauses (the equality pair), not 4.

### TS6: Composition Round-Trip

```rust
let c = Conjoin(
    Primitive(CardinalityBound { channel: "CH1", k: 3, terms: [A,B,C,D] }),
    Primitive(LayerAssignment { var: "A", value: true }),
);
let model = lower_composed(&c);
let rewritten = rewrite(&model).unwrap();
// rewritten has: Capacity(K=3-1=2, [B,C,D]), LayerRestriction(A=true)
// DPLL: for all variable assignments, SAT iff at most 2 of {B,C,D} are true and A is true
```

---

## Deferred Items (Not in Initial Release)

| Item | Rationale |
|------|-----------|
| P3 (SpatialOrder) | `OrderVar` exists in `types.rs:101-130` but is never populated by `ModelBuilder`. No consumer in the pipeline. Add when spatial ordering has a concrete use case. Requires new `InternalConstraint::SpatialOrder` variant + encoding match arm. |
| P5 (AdjacencyPair) | Requires new `InternalConstraint::Adjacency` variant + encoding + audit. Desugaring to P1+P4 composition would lose rewrite optimization. Defer until a concrete thermal coupling use case is needed. |
| P6 (SeparationDistance) | Requires new `InternalConstraint::Separation` variant + encoding + audit. Defer until clearance/creepage constraints are designed. |
| RW8 (DiffPairConflict) | Requires `MutualExclusion(exclusive=true)` variant of P1, which has no InternalConstraint mapping in the current 3-variant enum. |
| RW9 (AdjacencySubsume) | Depends on P5 (AdjacencyPair) being active with its own InternalConstraint variant. |
| Conditional true-implication encoding | Current Conditional desugars as conjunction of unit clauses. The proper implication-as-clause encoding (which would allow the SAT solver to violate the antecedent without violating the consequent) requires guard-variable tracking in the audit. Deferred. |
| Cross-validation via pysat | Requires Python subprocess bridge. The requirements specify 100-random-model cross-check vs pysat. For initial release, DPLL cross-validation (self-contained, no external dependency) is the primary soundness gate. pysat cross-validation is a follow-up CI enhancement. |
| Performance measurement on Temper PCB | SC5 (10% clause reduction) requires a measurement spike — run ModelBuilder, dump constraint stats, count overlaps. This is calibration work, not implementation. Deferred until U1-U6 ship and the rewrite engine is measurable end-to-end. |

---

## Cross-Document Dependency

The Constraint Lowering Compiler (`docs/brainstorms/2026-06-28-constraint-lowering-compiler-requirements.md`,
**R5**) currently restricts output to the 3 existing `InternalConstraint` variants.
This plan respects that boundary — no new variants are added. The combinator operates
entirely within the existing 3-variant enum.

If P3/P5/P6 are later activated, the compiler doc's R5 must be amended to permit emitting
the new variants. The combinator plan can then add the variants (tracked as deferred
items above) without renegotiating the compiler boundary.

---

## Success Criteria

| ID | Criterion | Measured By |
|----|-----------|-------------|
| SC1 | Every active primitive (P1, P2, P4) has exhaustive n≤4+n≤8 tests passing in CI | CI gate: `cargo test` |
| SC2 | Composition operators carry generic soundness tests (DPLL equivalence for all n≤4 combinations) | CI gate: `cargo test` in `combinator/compose.rs` |
| SC3 | Rewrite engine proven terminating and confluent via 10,000-model proptest | Nightly CI |
| SC4 | No new `InternalConstraint` variants added (P3/P5/P6 deferred) | `types.rs:290-306` unchanged in diff |
| SC5 | Rewrite engine completes in <100ms for a 6,000-constraint model | Micro-benchmark in `combinator/bench.rs` |
| SC6 | All existing tests in `encoding.rs` and `audit.rs` pass with rewrite active | CI gate: `cargo test` |
| SC7 | `PROOFS.toml` completeness enforced by CI | `scripts/verify_proofs.py` gate |
| SC8 | Clause count never increases after rewrite (non-regression) | Nightly CI measurement on Temper PCB model |

---

## Open Questions

### Q1. Conditional Operator Semantics
The initial release models `Conditional(A → C)` as a conjunction of unit clauses
(antecedent assignments) plus C's lowered constraints. This is _weaker_ than true
implication — the solver must satisfy C even when the antecedent is violated.
For the initial release this is sound (it over-constrains), but it may cause
false UNSAT. When should the proper implication encoding be implemented?

**Plan answer:** Deferred (see Deferred Items). The current pipeline uses no
Conditional compositions. This operator is scaffolding for future composition work.
If false UNSAT appears, the implication encoding will be prioritized.

### Q2. Module vs. Separate Crate
Requirements doc leaves this to planning. The plan selects **module inside
temper-rust-router** for:
- Zero-friction access to `InternalConstraint`, `InternalConstraintModel`
- No circular dependency risk
- Simpler CI (one crate, one `cargo test`)
The Constraint Lowering Compiler will be a separate crate; it will depend on
`temper-rust-router` for the `InternalConstraint` types anyway, so the combinator
being in the same crate poses no dependency problem.

### Q3. Clause-Count Reduction Target (SC5)
Requirements hypothesize ≥10% reduction via subsumption + unit propagation. This
plan defers the measurement spike (see Deferred Items). The non-regression gate
(SC8: "never increases clause count") is the active enforcement mechanism.
If the Temper PCB model has minimal overlapping constraints, the rewrite may be
a no-op — the plan accepts this outcome.

### Q4. PROOFS.toml Verification Script
When should `scripts/verify_proofs.py` be written? This plan includes it in U4
(the proof framework) because CI gating requires the script. It will be a simple
Python script that reads `PROOFS.toml`, checks file+function existence, and exits
non-zero on missing entries.

---

## Implementation Order

Recommended build order (each unit builds on the previous):

1. **U1** — types: compiles in isolation, no integration risk
2. **U2** — lower_composed(): depends on U1 types, testable in isolation
3. **U3** — rewrite engine: depends on InternalConstraintModel (existing), testable in isolation
4. **U4** — PROOFS.toml + scripts/verify_proofs.py (+ CI hook)
5. **U5** — lib.rs integration: minimal change, blocked by U3
6. **U6** — tests: written alongside each unit, but proptest/confluence tests land here
7. **U7** — docs: doc comments added in U1-U3; final module-level README lands here

Units U1-U3 can be developed in parallel by separate authors once U1 types are stabilized.
U5 is the smallest change (~5 lines in lib.rs).
