---
date: 2026-06-28
topic: constraint-combinator-library
---

# Constraint Combinator Library with Soundness-Preserving Composition

## Summary

Define a small set of sound primitive CNF encodings that are universally sufficient for PCB routing constraints, then build a combinator library that composes those primitives into the designer-level constraints the pipeline emits — plus a rewrite engine that simplifies the composed constraint set before CNF generation, eliminating redundancies and merging overlapping bounds. Every primitive carries an inductive correctness proof; every combinator preserves soundness by construction.

---

## Problem Frame

The SAT constraint model has 3 low-level constraint types (`Capacity`, `DiffPair`, `Layer` — defined in `packages/temper-rust-router/src/types.rs:290-306`) with **no formal composition semantics**. When constraints overlap on the same net/channel pair, there is no defined behavior — they are concatenated as clauses in the `encode_to_cnf` loop (`encoding.rs:111-151`). This creates three concrete problems:

1. **Redundant cardinality bounds**. The same channel may receive multiple `Capacity` constraints for overlapping net subsets. Each triggers its own `encode_at_most_k` (Sinz 2005 sequential counter, `encoding.rs:20-75`) with independent auxiliary variables, producing O(2·n·k) clauses where O(n·k) would suffice if the tighter bound subsumed the looser.

2. **Implicit semantics via clause concatenation**. A `LayerRestriction(allowed=true)` on `uses[N3, L1_E5]` and a `Capacity` on the same channel encoding `AtMostK(..., K=3)` are conjunctive — the solver satisfies both independently. But the pipeline author has no way to express "layer restriction AND capacity bound for the same variable" as a composed entity that can be simplified (e.g., the layer assignment is a unit clause that reduces K by 1 if that net is counted in the capacity terms).

3. **Unsoundness risk on new encodings**. The AtMostK encoding was proven unsound in its original form (`docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md`). When a new constraint type needs a new CNF encoding, there is no formal framework ensuring the encoding is correct. The current approach — ad-hoc encoding + exhaustive n≤8 tests (`encoding.rs:264-305`) — relies on developer discipline rather than a structural guarantee.

The combinator library addresses all three: primitives are proven correct once, composition preserves soundness, and the rewrite engine eliminates structural redundancy before clause generation.

---

## Actors

- **A1. Constraint Author** — selects primitives and composes them into routing constraints (e.g., "the HV nets on channel E5 must be ≤ 3 AND each net must use exactly one channel")
- **A2. Rewrite Engine** — applies simplification rules to the composed constraint set before CNF encoding (subsumption, absorption, bound-merging)
- **A3. CNF Encoder** — (`encoding.rs:encode_to_cnf`) consumes the simplified InternalConstraint model; unchanged from the combinator's perspective
- **A4. Constraint Audit** — (`audit.rs:audit_constraints`) validates solver output against the composed constraint semantics; unchanged operationally but extended to cover new primitive types
- **A5. SAT Solver** — (splr CDCL via `solver.rs:solve_with_splr`) receives CNF clauses; entirely unchanged

---

## Primitive Constraint Set

### Selection criteria

A constraint encoding qualifies as a primitive if:
- It is a **standalone sound constraint** with an inductive correctness proof (not a derived convenience)
- It is **universally sufficient** — every PCB routing constraint expressible in the pipeline can be composed from these primitives
- It maps to a **bounded-size CNF encoding** with provable auxiliary-variable overhead

### The six primitives

| Primitive | Semantics | CNF Encoding | Maps from (existing) | Status | Proof |
|-----------|-----------|-------------|---------------------|--------|-------|
| **P1. MutualExclusion** | `x ↔ y` (equality) or `x ↔ ¬y` (exclusive) over Boolean variables | 2 clauses per pair | `DiffPairConstraint`, `LayerConstraint` (when applied as per-net equality) | Active (maps to `DiffPairConstraint`) | Trivial: (¬x ∨ y) ∧ (x ∨ ¬y) for equality; (¬x ∨ ¬y) ∧ (x ∨ y) for exclusion |
| **P2. CardinalityBound** | `∑vars ≤ K` over a set of Boolean variables | Sequential counter, O(n·K) aux vars, O(n·K) clauses | `CapacityConstraint` | Active (maps to `CapacityConstraint`) | Sinz (2005) — proven by induction, base cases exhaustively verified for n ≤ 8 in `encoding.rs:264-305` |
| **P3. SpatialOrder** | `order[a,b,channel] → ¬order[b,a,channel]` with transitivity: `order[a,b] ∧ order[b,c] → order[a,c]` over a channel | 3 clauses per triplet per channel | Reserved in types (`OrderVar` in `types.rs:101-130`, `InternalVariable::Ordering` in `types.rs:281-287`) but currently **unencoded** in `encoding.rs` | Deferred (`OrderVar` not used by `ModelBuilder`) | Anti-symmetry + transitivity clauses; same structural proof as partial-order SAT encoding (standard) |
| **P4. LayerAssignment** | `uses[n,c] = v` (unit clause) over a Boolean variable | 1 clause | `LayerConstraint` (currently encoded as unit clause, `encoding.rs:144-149`) | Active (maps to `LayerConstraint`) | Trivial: (x) if v=true, (¬x) if v=false |
| **P5. AdjacencyPair** | `uses[a,c] → ∨_{b ∈ neighbors(a)} uses[b,c]` — if net `a` uses channel `c`, at least one of its required-neighbor nets must also use `c` | 1 clause: (¬uses[a,c] ∨ neighbor₁ ∨ ... ∨ neighborₖ). No aux vars. | No existing constraint uses this. Required for thermal coupling pairs, differential pair physical proximity (beyond logical equality) | Deferred (no `InternalConstraint` variant yet) | Direct: the clause is SAT iff `uses[a,c]→(neighbor₁∨...∨neighborₖ)`. No induction needed. |
| **P6. SeparationDistance** | `uses[a,c] ∧ uses[b,c] → (layer[a] ≠ layer[b] ∨ clearance(c) ≥ min_sep(a,b))`. If channel `c` cannot accommodate the separation, at least one net must not use `c`. | Encoded as `(¬uses[a,c] ∨ ¬uses[b,c])` when channel width < min_sep. Otherwise no clause (separation is geometric, not logical, for that channel). | Not yet encoded. The capacity slack factor (`ConstraintModel._create_capacity_constraints` at `constraint_model.py:237` uses fixed `0.8` slack) is a blunt proxy for this. | Deferred (requires `ChannelSeparationConstraint` from companion doc #4) | For non-CNF channels: correctness reduces to a unit clause per violating channel pair. For CNF: equivalence to mutual exclusion on that channel. |

### Sufficiency argument

Every existing constraint in the pipeline maps deterministically to at least one primitive:

- `CapacityConstraint` → **P2 (CardinalityBound)** with max_nets derived from capacity·slack/min_width
- `DiffPairConstraint` → **P1 (MutualExclusion, equality mode)** for the p/n variable pair
- `LayerConstraint` → **P4 (LayerAssignment)** as a unit clause
- `OrderVar` (reserved, NOT CURRENTLY CONSUMED by `ModelBuilder`) → **P3 (SpatialOrder)** [DEFERRED — P3 is a future primitive with no current consumer]
- Future therma/impedance constraints → **P5 (AdjacencyPair)**
- Future clearance/creepage constraints → **P6 (SeparationDistance)**

The primitives are closed under composition: composing any subset of P1–P6 with Boolean connectives yields either another primitive or a conjunction of primitives (see Composition Algebra below).

---

## Composition Algebra

### Operators

The combinator library defines three composition operators:

| Operator | Notation | Meaning | Soundness Preserving? |
|----------|----------|---------|----------------------|
| **Conjoin** | `C₁ ∧ C₂` | Both constraints must hold simultaneously | Yes — if C₁ and C₂ are sound models of CNF₁ and CNF₂, then CNF₁ ∪ CNF₂ is a sound model for C₁ ∧ C₂ (conjunction of clausal theories) |
| **Conditional** | `A → C` | If condition A holds (set of assignments), then constraint C must hold | Yes — `A → C` desugars to `¬A ∨ C`, which is a clause. Soundness reduces to P1+P4 composition |
| **RestrictDomain** | `C|[vars]` | Constrain C to apply only to a subset of variables | Yes — equivalent to `(uses_var₁ ∨ ... ∨ uses_varₖ) → C`. Desugars via Conditional operator |

### Non-operators (not needed)

- **Disjunction** (C₁ ∨ C₂) is not a sound composition operator for SAT constraints because the disjunction of two constraint models is not equivalent to the disjunction of their CNF encodings without Tseitin transformation. The pipeline expresses conditional routing (if route via channel A then constraint X, else constraint Y) via `RestrictDomain`, not via full disjunction.
- **Negation** of a constraint is not supported — the pipeline never expresses "this constraint must NOT hold."

### Composition proof obligation

For every composition `op(C₁, C₂, ...)` where each `Cᵢ` is backed by a soundness proof `Pᵢ` (inductive proof that its CNF encoding admits exactly the intended satisfying assignments), the composition must carry a derived proof `P_op` that demonstrates:

1. The resulting CNF is the conjunction of the constituent CNFs (for Conjoin) or the Tseitin-equivalent expansion (for Conditional)
2. No spurious models are introduced (soundness)
3. No valid models are excluded (completeness, within the primitive's expressiveness)

The proof for Conjoin is trivial: the conjunction of sound CNFs is sound. The proof for Conditional reduces to the correctness of the implication-as-clause encoding (one clause, structurally identical to P1).

### Non-composing constraints — the merge rule

When two primitives of the same type apply to overlapping variable sets, they are **merged**, not composed:

- **P1+P1 on the same variable pair**: `x ↔ y` conjoined with `x ↔ y` → single equality clause pair (idempotent). `x ↔ y` conjoined with `x ↔ ¬y` → UNSAT (detected pre-solve).
- **P2+P2 on the same channel**: `∑V1 ≤ K1` and `∑V2 ≤ K2` where V1 ⊆ V2: K1 subsumes K2 if K1 ≤ K2. If V1 ⊂ V2, the tighter bound for V1 is kept, and the looser bound for V2 is tightened to `∑V2 ≤ min(K2, K1 + |V2\V1|)`. If the merged bound is ≥ |V2|, the constraint is eliminated entirely.
- **P4+P4 on the same variable**: If both assign `x = true` → one unit clause (idempotent). If `x = true` and `x = false` → UNSAT (detected pre-solve).
- **P4+P2 overlap**: If `LayerAssignment(uses[n,c]=true)` and channel has `CardinalityBound(...) → AtMostK`, the variable `uses[n,c]` is removed from the AtMostK variable set (its value is determined by the unit clause) and K is decremented by 1. This is the **unit-propagation elimination** rewrite.

The rewrite rules RW1–RW7 below are the operational encoding of the merge rules described above. The merge rules section is the specification in primitive space; the rewrite rules section is the implementation in `InternalConstraint` space. They describe the same transformations.

## Type Hierarchy

The constraint system uses three distinct type layers that compose hierarchically:

```
Composition Operators  (Conjoin, Conditional, RestrictDomain)
        │
        ▼  lower_composed()
Primitive Types        (P1–P6: MutualExclusion, CardinalityBound, SpatialOrder,
                        LayerAssignment, AdjacencyPair, SeparationDistance)
        │
        ▼  model_from_python / direct encoding
InternalConstraint      (Capacity, DiffPair, LayerRestriction)
        │
        ▼  encode_to_cnf()
CNF Clauses             (flat clause set fed to splr)
```

**Composition-to-primitive mapping:**
- `Conjoin(P2, P2)` → two CardinalityBound primitives (merged via P2+P2 merge rules)
- `Conjoin(P4, P2)` → LayerAssignment + CardinalityBound (resolved via P4+P2 unit-propagation merge)
- `Conditional(A → P1)` → MutualExclusion guarded by antecedent assignments (encoded as implication clause)
- `RestrictDomain(P2, vars)` → CardinalityBound with variable set intersected against `vars`

**Primitive-to-InternalConstraint mapping:**
| Primitive | InternalConstraint variant |
|-----------|---------------------------|
| P1 (MutualExclusion) | `DiffPair` (equality mode) |
| P2 (CardinalityBound) | `Capacity` |
| P3 (SpatialOrder) | *(no variant yet — deferred)* |
| P4 (LayerAssignment) | `LayerRestriction` (unit clause) |
| P5 (AdjacencyPair) | *(no variant yet — deferred)* |
| P6 (SeparationDistance) | *(no variant yet — deferred)* |

---

## Rewrite / Optimization Engine

### Pipeline position

The rewrite engine runs **after** constraint model construction and composition but **before** lowering to `InternalConstraintModel`. It operates on the composition tree — an intermediate representation with composition operators (`Conjoin`, `Conditional`, `RestrictDomain`) whose leaves are primitives P1–P6.

```
composition tree (primitives + operators)
    → [REWRITE ENGINE]        ← runs on composition tree
    → lower_composed()        ← expands compositions into InternalConstraint instances
    → encode_to_cnf()
    → solve_with_splr()
    → audit_constraints()
```

### Lowering Specification

`lower_composed` transforms a Composition tree into an `InternalConstraintModel`. It is defined as:

- **Conjoin(A, B)** → `A.lower_composed()` ∪ `B.lower_composed()` — the internal instances of both children are merged into one model.
- **Conditional(A → C)** → add the clause `(¬A_var₁ ∨ ... ∨ ¬A_varₙ ∨ C_var₁ ∨ ... ∨ C_varₘ)` to the model (implication-as-clause encoding, structurally identical to P1/P4 composition), then lower C normally. The antecedent A is a set of variable assignments treated as unit literals.
- **RestrictDomain(A, vars)** → lower A, then intersect every `InternalConstraint`'s variable set against `vars`, dropping any constraint whose variable set becomes empty.

The output of `lower_composed()` is a flat `InternalConstraintModel` whose constraints are only `InternalConstraint` variants (Capacity, DiffPair, LayerRestriction) — the composition operators are fully expanded before CNF encoding.

### Rewrite rules

| Rule ID | Input Pattern | Output Pattern | Effect |
|---------|--------------|----------------|--------|
| **RW1. CapSubsume** | `Capacity(CH, K₁, V₁)` and `Capacity(CH, K₂, V₂)` with V₁ ⊆ V₂, K₁ ≤ K₂ | `Capacity(CH, K₁, V₁)` and `Capacity(CH, min(K₂, K₁+|V₂\V₁|), V₂)` | Tightens the looser bound to respect the tighter subset bound |
| **RW2. CapEliminate** | `Capacity(CH, K, V)` where K ≥ |V| | Remove constraint | Trivially satisfiable — all |V| variables can be true |
| **RW3. LayerPropagate** | `LayerRestriction(var=v, allowed=true)` and `Capacity(CH, K, {...var...})` | `LayerRestriction(var=v, allowed=true)` and `Capacity(CH, K-1, V\{var})` | Unit clause eliminates one variable from cardinality and reduces K |
| **RW4. LayerPropagateFalse** | `LayerRestriction(var=v, allowed=false)` and `Capacity(CH, K, {...var...})` | `LayerRestriction(var=v, allowed=false)` and `Capacity(CH, K, V\{var})` | Falsified variable removed from cardinality (K unchanged) |
| **RW5. DiffPairDedup** | `DiffPair(CH, p, n)` duplicated | Single `DiffPair(CH, p, n)` | Idempotent — equality clauses are identical |
| **RW6. LayerDedup** | `LayerRestriction(var=v, ...)` duplicated with same `allowed` | Single instance | Idempotent |
| **RW7. LayerConflict** | `LayerRestriction(var=v, allowed=true)` and `LayerRestriction(var=v, allowed=false)` | Raise `UnsatPreSolve` error | Structural contradiction — no need to invoke SAT solver |

After RW3/RW4, if K becomes 0 and the remaining variable set V is non-empty, re-fire RW2: a non-empty V with K=0 forces all remaining variables to false (add unit clauses (¬v) for each v ∈ V and remove the Capacity constraint).

### Future rewrite rules (deferred until InternalConstraint gains corresponding variants)

These rules reference primitive types (MutualExclusion, AdjacencyPair) that do not yet have `InternalConstraint` variants (`types.rs:290-306` has only Capacity, DiffPair, LayerRestriction). They are deferred until the type system is extended:

| Rule ID | Input Pattern | Output Pattern | Effect |
|---------|--------------|----------------|--------|
| **RW8. DiffPairConflict** | `DiffPair(CH, p, n)` + `MutualExclusion(CH, p, n, exclusive=true)` | Raise `UnsatPreSolve` error | Equality and exclusive can't both hold |
| **RW9. AdjacencySubsume** | `AdjacencyPair(net=a, channel=c, neighbors=N₁)` and `AdjacencyPair(a, c, N₂)` with N₁ ⊆ N₂ | `AdjacencyPair(a, c, N₁)` | Tighter neighbor set subsumes looser (fewer neighbors = stronger constraint) |

Note: P1+P1 merge (equivalent to RW8 functionality) is already handled by RW5 (DiffPairDedup) for the `DiffPair` variant; the `MutualExclusion`-specific rule RW8 becomes relevant only when MutualExclusion gains its own `InternalConstraint` variant.

### Rewrite engine properties

The rewrite engine MUST be:
1. **Terminating** — each rewrite reduces some measure (clause count, aux-var count, or constraint count). The fixpoint is reached when no rule fires.
2. **Confluent** — rule application order does not affect the final constraint set (Church-Rosser property). The rules form a terminating, confluent rewrite system.
3. **Semantics-preserving** — the rewritten model is logically equivalent to the original: both admit exactly the same satisfying assignments over the primary variables. Auxiliary variables may differ but primary-variable projectability is preserved.

Termination and confluence proofs are part of the primality verification for each rule.

---

## Correctness Architecture

### Primitive-level proofs

Each primitive P1–P6 carries a proof file in the combinator crate with this structure:

```
packages/temper-constraint-combinator/
  src/
    primitives/
      p1_mutual_exclusion.rs      # encoding + proof
      p2_cardinality_bound.rs     # encoding + Sinz 2005 proof
      p3_spatial_order.rs         # encoding + partial-order proof
      p4_layer_assignment.rs      # encoding (trivial)
      p5_adjacency_pair.rs        # encoding + direct proof
      p6_separation_distance.rs   # encoding + reduction-to-P1 proof
      proofs/
        p2_induction.md           # Inductive proof (copied from encoding.rs:167-181)
        p3_transitivity.md        # Partial-order antisymmetry + transitivity proof
```

**Proof structure for each primitive:**
1. **Base cases**: Exhaustive verification via mini-DPLL solver for all primary-variable assignments up to n ≤ 8 (pattern established in `encoding.rs:264-305`)
2. **Inductive step**: Documented in `proofs/*.md`, following the Sinz (2005) pattern in `encoding.rs:167-181`
3. **Cross-validation**: Hypothesis property-based test comparing the primitive's encoding against an independent reference (e.g., pysat's `CardEnc.atmost` for P2) on 100 random models — pattern from `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md:103`

### Composition-level proofs

For each composition operator, a generic proof shows soundness preservation regardless of which primitives are composed. The proof is structural — it does not enumerate primitive pairs.

### Proof registry

A compile-time proof registry maps each primitive + composition combination to its proof artifact. At build time, a CI gate verifies that every claimed proof file exists and that every proof's base cases pass. A `PROOFS.toml` manifest records:

```toml
[primitive.P2_CardinalityBound]
encoding = "p2_cardinality_bound.rs"
proof_inductive = "proofs/p2_induction.md"
exhaustive_test = "tests/p2_exhaustive_n8.rs"
cross_validation = "tests/p2_cross_validate_pysat.rs"

[compose.Conjoin]
proof = "proofs/conjoin_soundness.md"
```

---

## Integration with Existing ModelBuilder

### Integration point

The combinator library integrates at the `InternalConstraintModel` boundary — after the Python `ConstraintModel` is converted to Rust types but before `encode_to_cnf` is called. The existing call chain:

```
lib.rs:36: types_py_bridge::model_from_python(net_names, py_vars, py_cons)?
    → InternalConstraintModel

lib.rs:40: encoding::encode_to_cnf(&model)
    → CnfFormula

lib.rs:45: solver::solve_with_splr(&cnf, &var_names)
    → TopologyResult
```

Becomes:

```
composition tree (from ModelBuilder + constraint lowering compiler)
    → combinator::rewrite(&tree)              ← rewrite on composition tree
    → combinator::lower_composed(&tree)        ← expand to InternalConstraintModel

lib.rs:40: encoding::encode_to_cnf(&model)
    → CnfFormula

lib.rs:45: solver::solve_with_splr(&cnf, &var_names)
    → TopologyResult
```

### What ModelBuilder emits vs. what Combinator receives

`ModelBuilder` (`constraint_model.py:153`) continues to emit `CapacityConstraint`, `DiffPairConstraint`, `LayerConstraint` for structural routing needs. The combinator receives these as `InternalConstraint` instances and treats them as pre-encoded primitives (P2, P1, P4 respectively). The rewrite engine applies RW1–RW7 to the entire constraint set, including both ModelBuilder-originated and compiler-originated constraints.

### Relationship to the Constraint Lowering Compiler

The existing requirements doc `2026-06-28-constraint-lowering-compiler-requirements.md` defines a compiler that lowers PCL (designer-level) constraints into the existing 3 low-level types. The combinator library is the **encoding foundation** beneath that compiler:

- **Lowering Compiler** produces `InternalConstraint` instances — its target ISA is the existing 3 types
- **Combinator Library** defines the primitives whose CNF encodings are proven sound, provides the rewrite engine that simplifies the `InternalConstraintModel` before encoding, and ensures that any new encoding added (via the compiler or directly) carries a correctness proof

They are complementary: the compiler bridges designer intent to constraints; the combinator ensures those constraints are sound and non-redundant at the CNF level.

**Cross-document note:** The constraint lowering compiler (`2026-06-28-constraint-lowering-compiler-requirements.md`, R5) currently restricts output to the 3 existing `InternalConstraint` variants. If this document adds new variants (P3/P5/P6), the compiler doc's R5 must be amended to permit emitting them. Until then, P3/P5/P6 are for direct-authoring only.

---

## How New Constraints Are Added

### Current process (anti-pattern)

To add a constraint today:
1. Define a Python dataclass (e.g., `NewConstraint(Constraint)`) in `constraint_model.py`
2. Define a corresponding `InternalConstraint` variant in `types.rs:290`
3. Add a match arm in `encoding.rs:111` to emit CNF clauses
4. Add a match arm in `audit.rs:72` to validate against the constraint
5. Write ad-hoc tests in the encoding test module

Steps 2–5 touch four files across Python and Rust. Step 3 offers no guardrail against unsound encoding.

### Target process (with combinator)

To add a new constraint:
1. **If expressible from existing primitives**: Define a **composition** of P1–P6 using the combinator operators (Conjoin, Conditional, RestrictDomain). No new encoding code needed — the combinator expands it to existing primitive CNF. Add a desugaring rule in the combinator's rule table. Add a property test proving the composition is equivalent to the designer intent.
2. **If a new primitive is needed**: Implement the primitive with (a) CNF encoding function, (b) inductive correctness proof, (c) exhaustive verification up to n ≤ 8, (d) cross-validation against an independent reference, (e) entry in `PROOFS.toml`. The primitive becomes part of P1–P7. Add composition rules for how it interacts with existing primitives (merge rules, subsumption). Add audit match arm in `audit.rs`.
3. Neither case requires changes to `encoding.rs::encode_to_cnf` — the rewritten model contains only `InternalConstraint` variants that the existing encoder already handles.

### Example: adding a "ThermalPair" constraint

"ThermalPair(net1, net2, channel)" requires two thermally coupled nets to use adjacent sub-channels within a channel. Expressible as:
```
AdjacencyPair(net1, channel, neighbors={net2})
  ∧ AdjacencyPair(net2, channel, neighbors={net1})
  ∧ MutualExclusion(net1_channel_var, net2_channel_var, exclusive=false)
```

This is a pure composition (no new primitive). The constraint author writes a `compose_thermal_pair(net1, net2, channel)` function that returns this composition. The rewrite engine treats the composed `AdjacencyPair` constraints identically to any other occurrence. No new `InternalConstraint` variant. No `encoding.rs` changes. No new match arm in `audit.rs` — the audit already validates primitives individually.

---

## Test Strategy

### Tier 1: Primitive encoding correctness (per-primitive)

| Test | What it proves | Pattern from codebase |
|------|---------------|----------------------|
| Exhaustive n ≤ 8 | For all 2^n primary assignments, the CNF encoding is SAT iff the constraint holds. Tests all k ≤ n-1 for P2. | `encoding.rs:264-305` (existing) |
| Mini-DPLL equivalence | The CNF encoding is satisfiable exactly when the constraint semantics permit. DPLL solver is self-contained (no external dependency). | `encoding.rs:189-261` (existing) |
| Cross-validation vs. pysat | On 100 random models with varying n and K, the Rust encoding and pysat's `CardEnc.atmost` agree on SAT/UNSAT. | Referenced in `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md:103` |

### Tier 2: Composition soundness

| Test | What it proves |
|------|---------------|
| Compositional DPLL | For all small-n compositions (n ≤ 4, all primitive combinations), DPLL on the composed CNF agrees with the conjunctive semantics of the individual primitives |
| Operator generic property: Conjoin | `verify(C₁ ∧ C₂) ↔ verify(C₁) ∧ verify(C₂)` for all small models, using Hypothesis PBT |
| Operator generic property: Conditional | `verify(A → C)` matches truth-table semantics of implication for all A-variable assignments |

### Tier 3: Rewrite engine correctness

| Test | What it proves |
|------|---------------|
| Pre/post rewrite equivalence | For every rewrite rule RW1–RW7, the rewritten model is satisfiability-equivalent to the original (same SAT/UNSAT outcome for the same primary variables) — proven exhaustively for small-n models (n ≤ 6) and via Hypothesis PBT for random larger models |
| Fixpoint convergence | The rewrite engine reaches a fixpoint in ≤ N steps where N ≤ initial constraint count — proven by termination measure (constraint count + aux-var count strictly decreases or stays same with no cycles) |
| Confluence (QCheck/Rust) | Applying rewrite rules in any order yields the same final constraint set — tested via random rule-ordering on random input models using `proptest` |
| No false UNSAT | When RW7 detects a structural contradiction (pre-SAT), a DPLL solver confirms UNSAT independently — the contradiction is real, not a rewrite artifact |

### Tier 4: Integration tests

| Test | What it proves |
|------|---------------|
| ModelBuilder → rewrite → encode round-trip | The Temper PCB constraint model (built by `ModelBuilder`) passes through the rewrite engine and emerges with fewer clauses (monotonically non-increasing) and identical SAT/UNSAT outcome to the un-rewritten model, verified via pysat cross-check |
| Audit compatibility | All existing audit tests in `audit.rs:131-347` pass when the model is rewritten — rewrite does not change which assignments are valid |
| No regression on known-good encodings | The exhaustive AtMostK tests (`encoding.rs:264-305`), the audit completeness test (`audit.rs:275-320`), and the diff-pair/layer tests all pass with the rewrite engine active |

### Tier 5: CI gates

| Gate | Frequency | Blocks merge? |
|------|-----------|--------------|
| `cargo test` (all primitives + rewrite) | Every push | Yes |
| Hypothesis PBT cross-validation vs. pysat | Nightly + PR | Yes (Rust solver correctness is critical path) |
| Exhaustive DPLL on n ≤ 8 for all primitives | Every push | Yes |
| `PROOFS.toml` completeness check | Every push | Yes — every primitive must have all required proof entries |
| Rewrite fixpoint termination (random order, 10,000 models) | Nightly | Yes |

### Performance regression guard

The rewrite engine MUST NOT increase clause count or variable count for any model. A CI test measures clause+variable counts before and after rewrite on the Temper PCB model and fails if either increases. This is a **non-regression** gate, not a specific-performance gate.

---

## Acceptance Examples

- **AE1. Merged capacity bounds (covers RW1, RW2).** A channel `L1_E5` receives two `Capacity` constraints: `Capacity(L1_E5, K=3, nets=[A,B,C])` and `Capacity(L1_E5, K=6, nets=[A,B,C,D,E,F])`. RW1 applies: V₁={A,B,C} ⊆ V₂={A,B,C,D,E,F} and K₁=3 ≤ K₂=6, so the second constraint becomes `Capacity(L1_E5, K=min(6, 3+|{D,E,F}|)=6, [A,B,C,D,E,F])` — the full variable set is kept, K is unchanged. Then RW2 fires: K=6 and |V| = |{A,B,C,D,E,F}| = 6, so K ≥ |V| and the constraint is eliminated entirely (at most 6 of 6 variables is trivially satisfied). The net result is a single remaining constraint: `Capacity(L1_E5, K=3, [A,B,C])`.

- **AE2. Layer unit propagation reduces cardinality (covers RW3).** A channel has `Capacity(L1_E5, K=4, nets=[A,B,C,D,E])` and `LayerRestriction(uses[A,L1_E5]=true)`. The rewrite engine removes A from the capacity variable set and sets K'=3 for nets=[B,C,D,E]. The unit clause is kept. Net result: AtMostK is encoded for 4 variables with K=3 instead of 5 variables with K=4 — saving O(k) auxiliary variables and O(k) clauses.

- **AE3. Structural contradiction detected pre-solve (covers RW7).** `LayerRestriction(uses[N3,L1_E5]=true)` and `LayerRestriction(uses[N3,L1_E5]=false)` both appear in the model. The rewrite engine raises `UnsatPreSolve` without invoking the SAT solver. The error message identifies the conflicting constraints by name (`layer_restr_N3_L1_E5_E0_...`).

- **AE4. Composed constraint from primitives (covers composition).** A "thermal pair with separation" constraint for nets Q1_HV and Q2_HV on channel E5 is expressed as:
  ```
  MutualExclusion(Q1_E5, Q2_E5, equality)          // P1: must route together
    ∧ AdjacencyPair(Q1_HV, E5, {Q2_HV})             // P5: must be adjacent
    ∧ Conditional(is_HV ∧ shared_channel,
        SeparationDistance(Q1_HV, Q2_HV, 6.0mm))    // P6: 6mm separation if both HV
  ```
  The combinator lowers this to InternalConstraint instances. The rewrite engine merges any overlapping sub-constraints with existing ModelBuilder constraints. No new encoding code written.

- **AE5. Identical diff-pair constraints deduplicated (covers RW5).** If `ModelBuilder._create_diff_pair_constraints` and a manually-added `DiffPairConstraint` produce the same `DiffPair(CH, p, n)` constraint, the rewrite engine keeps one instance and discards the duplicate. The CNF encoder sees one pair of equality clauses, not two.

---

## Success Criteria

- **SC1.** Every primitive (P1–P6) has an inductive correctness proof documented in `PROOFS.toml` with exhaustive n ≤ 8 verification passing in CI.
- **SC2.** The composition operators (Conjoin, Conditional, RestrictDomain) carry generic soundness proofs — no per-composition manual verification needed.
- **SC3.** The rewrite engine is proven terminating, confluent, and semantics-preserving — each property verified by `proptest` on 10,000 random models.
- **SC4.** Adding a new designer-level constraint (e.g., ThermalPair) requires only a composition function (~20 lines) — no new `InternalConstraint` variant, no `encoding.rs` changes, no `audit.rs` changes.
- **SC5.** The rewrite engine reduces clause count for the Temper PCB model (baseline: ~619K clauses from sequential-counter encoding) by ≥ 10% through subsumption, unit-propagation elimination, and deduplication. If clause count does not decrease, the audit documents why (e.g., no overlapping constraints in the test model — rewrite is a no-op for this PCB).
- **SC6.** All existing tests in `encoding.rs` and `audit.rs` pass unmodified with the rewrite engine active.
- **SC7.** A new primitive's encoding passes the same proof bar as existing primitives: inductive proof + exhaustive n ≤ 8 + pysat cross-validation on 100 random models. The proof bar is enforced by CI.

---

## Scope Boundaries

- The combinator library defines **primitive encodings and composition** — it does NOT define designer-level constraint types or PCL lowering. That is the Constraint Lowering Compiler's domain (`2026-06-28-constraint-lowering-compiler-requirements.md`).
- The rewrite engine operates on `InternalConstraintModel` — it does NOT rewrite CNF clauses directly. CNF-level optimization (e.g., subsumption of identical clauses, pure-literal elimination) remains the SAT solver's responsibility.
- The combinator does NOT modify `splr` or introduce a new SAT solver backend.
- The combinator does NOT replace `ModelBuilder` — that class continues to emit structural routing constraints (capacity from channel widths, diff pairs from net inference, layer restrictions from SMD pins).
- The combinator does NOT handle runtime constraint modification during search (lazy grounding, incremental SAT).
- Post-solve audit (`audit.rs`) continues to validate solver output against constraints. The audit is extended to validate against new primitive types if they introduce new `InternalConstraint` variants, but the combinator aims to minimize such additions.

---

## Key Decisions

- **Conjunction as the only composition connective.** Disjunction is excluded because the disjunction of constraint models is not equivalent to the disjunction of their CNF encodings without introducing Tseitin variables — which would re-enter the unsound-encoding territory. Conditional desugars to clause form so it's safe. The pipeline's routing alternatives (route via channel A OR channel B) are expressed as separate variables with connectivity constraints, not as disjunctions of constraint models.

- **Rewrite operates on InternalConstraintModel, not raw CNF.** Semantics-preserving rewrites on the structured constraint model are easier to prove correct than rewrites on flat clause sets, and the structured form carries enough information for the rewrite rules to fire (e.g., RW3 requires knowing that a variable appears in a specific Capacity constraint's variable set).

- **Merge is type-specific, not generic.** P1+P1 merge differs from P2+P2 merge. A generic merge framework would need to encode primitive-specific semantics. Instead, each primitive pair has a defined merge rule. This is explicit but predictable.

- **Proof manifest (PROOFS.toml) over code comments.** A machine-readable manifest enables CI to verify proofs exist without parsing Rust source. The existing `encoding.rs:167-181` block comment is a proof, but it's not verifiable by tooling.

- **Combinator as a separate crate or module within temper-rust-router.** The combinator depends on `InternalConstraintModel` and `InternalConstraint` from `temper-rust-router::types`. Two options: (a) new `temper-constraint-combinator` crate with path dependency, or (b) new `combinator` module within `temper-rust-router`. Decision deferred to planning — the tradeoff is crate isolation vs. avoiding circular dependencies if the rewrite engine needs solver types.

---

## Dependencies / Assumptions

- `InternalConstraintModel`, `InternalConstraint`, and `InternalVariable` are `pub` within `temper-rust-router::types` and accessible to the combinator. **Confirmed**: `types.rs` types are publicly accessible. The `InternalConstraint` enum (`types.rs:289-306`) has 3 variants — the combinator may add new variants for primitives P3, P5, P6 that currently lack `InternalConstraint` representations.

- The Sinz (2005) sequential counter is the canonical P2 encoding. **Confirmed**: `encoding.rs:20-75` implements it and `encoding.rs:167-181` documents the inductive proof. The combinator's P2 primitive reuses this implementation but wraps it in the proof framework.

- `OrderVar` (`types.rs:101-130`) exists but has no corresponding `InternalConstraint` variant and is unused in `encoding.rs`. The combinator's P3 primitive will need a new `InternalConstraint::SpatialOrder` variant and a corresponding encoding match arm in `encoding.rs`. This is the only case where a genuinely new encoding path is added.

- The constraint audit (`audit.rs`) is extensible. **Confirmed**: `audit.rs:72-129` matches on `InternalConstraint` variants with a `match c { ... }` that will need new arms for any new variants (P3, P5, P6). The audit tests (`audit.rs:131-347`) will need corresponding test cases.

- The rewrite engine runs synchronously in the critical path before `encode_to_cnf`. Its runtime must be negligible relative to SAT solving time. For the Temper PCB (~6,000 channels, ~130K variables), the rewrite is O(|constraints|²) in the worst case (comparing each constraint against each other). With ~6,000 capacity constraints, this is ~36M pair checks — acceptable if each check is O(1) (hash-set lookup). The rewrite engine MUST complete in <100ms for the full Temper PCB model.

---

## Outstanding Questions

### Resolve Before Planning

- **[Affects SC5]** What is the actual clause-count reduction from RW1–RW7 on the Temper PCB model? The 10% criterion is a hypothesis. If the current model has minimal overlapping constraints (each channel gets exactly one Capacity, each diff-pair appears once, each layer restriction is a single unit clause), the rewrite engine may be a no-op. A measurement spike (run ModelBuilder, dump constraint stats, count overlaps) is needed to calibrate SC5.

- **[Affects P3]** Does `SpatialOrder` (P3) have a concrete use in the current pipeline, or is it reserved for future multi-net ordering within channels? `OrderVar` is defined in types but never populated by `ModelBuilder`. If P3 has no near-term consumer, it could be deferred to a later primitive batch rather than implemented in the initial combinator release.

- **[Affects P5, P6]** AdjacencyPair and SeparationDistance currently lack `InternalConstraint` variants. Should the combinator add `InternalConstraint::Adjacency` and `InternalConstraint::Separation` variants, or should these be desugared into conjunctions of existing types (P1 + P4) before reaching `InternalConstraintModel`? The latter avoids `encoding.rs` changes but may lose optimization opportunities (the rewrite engine can't optimize what it can't see). The former preserves rewrite visibility at the cost of new encoding code.

- **[Affects architecture]** Crate or module? If the combinator lives inside `temper-rust-router` as a module, it has zero-friction access to `InternalConstraint` and can freely add variants. If it's a separate crate, `InternalConstraint` additions in `temper-rust-router` require the combinator crate to update. The module approach is simpler for initial development; the crate approach aligns with the compiler's standalone-crate decision.

### Deferred to Planning

- Exact representation of composition in Rust types — a `ComposedConstraint` enum? A trait-based system? A constraint tree?
- Proof format — are proofs machine-checkable (e.g., `prusti` annotations on Rust code, or Lean/Coq external proofs) or human-readable markdown with exhaustive-test backing? The current codebase uses the latter (exhaustive DPLL tests). The requirements doc establishes the proof bar; the implementation decides the format.
- How the rewrite engine integrates with the Constraint Lowering Compiler — does the compiler emit pre-rewritten constraints, or does it emit raw InternalConstraints that the rewrite engine then simplifies? The latter is simpler and preserves the single-responsibility principle.
- Whether `PROOFS.toml` should be a CI gate or a documentation artifact. The requirements say CI gate, but the tooling to check "does this proof file exist and have required sections" needs design.
