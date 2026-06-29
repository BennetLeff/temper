---
title: "feat: Hierarchical Net Bundling with Type-Gated Lazy Grounding"
type: feat
status: draft
date: 2026-06-28
origin: docs/brainstorms/2026-06-28-net-bundling-lazy-grounding-requirements.md
---

# Hierarchical Net Bundling with Type-Gated Lazy Grounding

## Summary

Pre-partition nets into bundle equivalence classes sharing the same constraint-type
signature and geometric neighborhood. Encode Safety constraints eagerly per bundle
class, ground Performance constraints lazily via a CEGAR loop (counterexample-guided
abstraction refinement) between successive `solve()` calls on CaDiCaL, and skip
Aesthetic constraints entirely at the SAT layer. Reduces the routing SAT model from
O(n·|E|) variables to O(b·|E| + n) where b << n is the number of bundle classes.

---

## Problem Frame

The current `ModelBuilder` (`constraint_model.py:176-185`) creates one `NetChannelVar`
per (net × skeleton edge) and one `ViaVar` per (net × skeleton node) for every net
that passes the `target_net_names` filter. On the Temper PCB (23 nets, 2 signal
layers, ~6,000 skeleton edges) this produces ~228K variables — ~138K NetChannelVars +
~85K ViaVars. Even with `max_sat_nets` gating to the 3 simplest nets, the model is
29K variables, and splr 0.13 panicked at M=6+ nets.

The `max_sat_nets` lever solves the problem coarsely — it excludes nets from SAT
entirely. Nets above the cutoff get no channel assignment from the topology stage and
must rely on direct A* routing with no capacity-coordination guarantees.

The root cause is that the current encoding treats every net as an independent
variable-generator. However, many nets are *substitutionally equivalent* for
constraint purposes — two signal nets of the same width in the same geometric region
contribute identically to capacity constraints and differ only in which specific pins
they connect. Encoding one capacity constraint per bundle class and instantiating
per-net variables only when needed collapses the O(n·|E|) variable space.

**Current solver:** rustsat-cadical (CaDiCaL via rustsat traits). splr 0.13 was
replaced 2026-06-28. CaDiCaL supports `add_clause()` between `solve()` calls at root
level. The `SolveIncremental` trait is available from rustsat.

---

## Requirements

All requirements originate from `docs/brainstorms/2026-06-28-net-bundling-lazy-grounding-requirements.md`.

### Core Bundle Partitioning

- **R1 (Bundle equivalence):** The bundle analyzer shall partition nets into
  equivalence classes such that two nets are in the same class iff they have
  identical `(net_class, trace_width, clearance, has_diff_pair, pin_layer_set)`
  tuples AND their geometric footprints (convex hull of pin positions expanded by
  median channel edge length) overlap on >50% of skeleton edges by Jaccard index.

- **R2 (Bundle manifest):** The bundle analyzer shall produce a `BundleManifest` data
  structure containing for each bundle class: `net_indices`, `type_signature`,
  `geometric_footprint`, and a `constraint_types` set enumerating which of {Safety,
  Performance, Aesthetic} apply.

- **R2.1 (Determinism):** Bundle partitioning shall be deterministic — given
  identical nets and skeletons, the same bundle classes shall be produced. Sort order
  shall be by bundle_id (lexicographic on first net name).

### Type-Gating Policy

- **R3 (Safety constraints — eager):** All constraints classified as Safety shall be
  fully grounded as SAT clauses before the solver begins CDCL search. Safety
  constraints include: HV/LV isolation (capacity constraints on channels adjacent to
  HV nets), layer restrictions (SMD pin layer assignment), and minimum clearance for
  safety-critical net pairs.

- **R4 (Performance constraints — lazy):** All constraints classified as Performance
  shall be grounded lazily during the CEGAR loop, only when the full assignment from a
  safety-CNF solve makes a violation concretely possible. Performance constraints
  include: differential pair skew, impedance-controlled length matching, and
  signal-integrity ordering.

- **R5 (Aesthetic constraints — never):** Constraints classified as Aesthetic shall
  never be lowered to SAT clauses. They shall be recorded in the `BundleManifest` for
  post-processing refinement of the solved topology.

- **R5.1 (Constraint classification resolution):** The classification of each
  constraint as Safety/Performance/Aesthetic shall be determined by a configurable
  mapping from constraint kind → gating tier, defaulting to:
  `CapacityConstraint` on channels touching HV nets → Safety;
  `CapacityConstraint` on signal-only channels → Performance;
  `DiffPairConstraint` → Performance;
  `LayerConstraint` → Safety.

### Lazy Clause Callback Interface

- **R6 (Lazy addition API):** The SAT solver interface shall support adding variables
  and clauses after the initial solve has begun. At minimum: `add_var_lazy(name:
  str) → var_idx` and `add_clause_lazy(literals: [i32])` callable between
  incremental `solve()` invocations via CaDiCaL's `SolveIncremental` trait.

- **R7 (Violation-concrete trigger):** The lazy grounding watchdog shall add
  Performance clauses when — and only when — a full assignment to class-level
  variables, when mapped through the bundle-to-net homomorphism, makes it concretely
  possible that at least one Performance constraint is violated.

- **R7.1 (Early termination guard):** The lazy grounding watchdog SHALL impose a
  budget limit on per-net variable instantiation per CEGAR iteration. The budget
  formula SHALL be M × |bundle_nets| where M is an empirically calibrated multiplier
  (initial value: 10, recalibrated in the first integration sprint).

- **R7.2 (Budget exhaustion degradation):** When the watchdog's instantiation budget
  is exhausted before all Performance constraints are grounded, nets with ungrounded
  Performance constraints SHALL be routed via the existing A* fallback (same
  degradation path as nets excluded by `max_sat_nets`).

### Homomorphism Instantiation

- **R8 (Homomorphism correctness):** For non-diff-pair bundles, the homomorphism
  mapping class-variable `uses[B, channel_id]` to per-net-variable `uses[net_i,
  channel_id]` shall preserve constraint semantics: every satisfying assignment of
  the per-net encoding, when projected through the homomorphism, shall satisfy the
  class-level encoding; and every satisfying assignment of the class-level encoding
  shall be extendable (by assigning per-net variables) to a satisfying assignment of
  the full encoding. For diff-pair bundles, diff-pair nets SHALL be placed in their
  own dedicated 2-net bundle classes until OQ-D3 is resolved.

- **R8.1 (Inverse mapping for extraction):** After SAT solving, the topology
  extractor (`extraction.rs:9-94`) shall use the inverse homomorphism to map
  class-variable assignments back to per-net channel assignments for all nets in the
  bundle.

### Integration with Existing ModelBuilder

- **R9 (Backward compatibility):** The `ModelBuilder.build()` API shall be unchanged.
  An optional `enable_bundling: bool = False` parameter shall gate the new bundle
  path. When `False`, the current eager-all-variables behavior is preserved
  unmodified. The existing `target_net_names` parameter shall continue to work
  regardless of bundling mode.

- **R9.1 (Constraint audit integration):** The existing constraint audit
  (`audit.rs:39-129`) shall validate bundled SAT results against the expanded (fully
  grounded) constraint set. Audit violations shall report in terms of per-net variable
  names even when the solver operated on class-level variables.

### Correctness Guarantees

- **R10 (Bundled-vs-unbundled equivalence):** For any constraint set C where all
  constraints are of type Safety (eagerly grounded), the bundled encoding shall
  produce bit-identical SAT/UNSAT results to the unbundled (current) encoding.

- **R10.1 (Soundness):** If the bundled encoding returns SAT, every safety constraint
  in the original model is satisfied by the extracted per-net assignments
  (post-homomorphism).

- **R10.2 (Completeness):** If a satisfying per-net assignment exists, the bundled
  encoding with full lazy grounding shall return SAT.

**Origin actors:** A1 (ModelBuilder), A2 (SAT Solver / CaDiCaL), A3 (Pipeline
Orchestrator), A4 (Bundle Analyzer), A5 (Lazy-Clause Provider)
**Origin flows:** F1 (Bundle Analysis Pass), F2 (Eager Safety Encoding), F3 (Lazy
Performance Grounding via CEGAR), F4 (Aesthetic post-processing)
**Origin acceptance examples:** AE1 (two identical signal nets), AE2 (diff pair
bundles), AE3 (HV net safety isolation)

---

## Scope Boundaries

### In scope

- Bundle equivalence class analysis based on net type signature and geometric footprint
- Type-gating policy (Safety vs Performance vs Aesthetic) with configurable classification rules
- Eager encoding of Safety constraints at class-variable granularity
- Lazy encoding of Performance constraints triggered by post-solve assignment inspection (CEGAR)
- Homomorphism mapping between class variables and per-net variables, including inverse for extraction
- Integration with existing Python `ModelBuilder` and Rust `encoding.rs`, `solver.rs`, `extraction.rs`, `audit.rs`
- Correctness validation via property-based tests for the homomorphism

### Explicitly outside scope

- **OrderVar bundling:** `OrderVar` (`constraint_model.py:68-78`) is inherently
  per-net and cannot be class-aggregated. OrderVar creation remains per-net
  (O(n·|E|) worst case) and is excluded from bundling.
- **ViaVar bundling:** Via variables are pin-position-specific and cannot be shared
  across nets. ViaVar count remains O(n·|V|).
- **Constraint type inference / auto-classification:** Adding a `safety_category`
  field to `NetClassRules` is prerequisite work; the field already exists at
  `stage0_data.py:88` (`safety_category: str | None`). Populating it from net class
  specs is out of scope; the plan uses the net-name-based heuristics in
  `net_classification.py:75-87` with the mapping: `hv` → Safety, `power` →
  Performance, `ground` → Safety, `signal` → Performance.
- **Solver replacement:** Already done — CaDiCaL via rustsat is the active
  solver. No further solver migration is in scope.
- **Aesthetic post-processing algorithms:** The actual post-processing for length
  matching, color guides, etc. are deferred. This plan delivers a stub that records
  aesthetic metadata in the `BundleManifest` for downstream consumption.
- **Fine-grained lazy clause generation during CDCL search:** KD4 confirms the
  CEGAR loop runs between `solve()` calls, not during CDCL search. No IPASIR callback
  API is needed.

---

## Context & Research

### Relevant Code and Patterns

- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py:27-415` —
  `Variable`, `NetChannelVar`, `ViaVar`, `OrderVar`, `CapacityConstraint`,
  `DiffPairConstraint`, `LayerConstraint`, `ConstraintModel`, `ModelBuilder`
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:594-700` —
  `_run_stage3()`, SAT net selection, Rust dispatch, constraint audit integration
- `packages/temper-placer/src/temper_placer/router_v6/net_classification.py:21-88` —
  `classify_net_type()`, `is_hv_net()`, `is_power_net()`, `is_ground_net()`,
  `is_signal_net()`
- `packages/temper-placer/src/temper_placer/router_v6/stage0_data.py:76-88` —
  `NetClassRules` with existing `safety_category: str | None` field (line 88)
- `packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py:27-49` —
  `ChannelSkeleton` with `graph: nx.Graph` (nodes as `(x, y)` tuples)
- `packages/temper-rust-router/src/types.rs:1-389` — `InternalVariable`,
  `InternalConstraint`, `InternalConstraintModel`, `TopologyResult`, `TopologyGraph`
- `packages/temper-rust-router/src/types_py_bridge.rs:1-87` — Python→Rust bridge
  for constraint model data
- `packages/temper-rust-router/src/encoding.rs:1-306` — CNF encoding with Sinz
  (2005) sequential counter for `AtMostK`
- `packages/temper-rust-router/src/solver.rs:1-240` — `solve_with_cadical()`,
  `solve_with_cadical_cores()` using rustsat-cadical
- `packages/temper-rust-router/src/extraction.rs:1-111` — `extract_topology()`,
  variable name parsing (`uses_` prefix)
- `packages/temper-rust-router/src/audit.rs:1-349` — `audit_constraints()`,
  `AuditViolation` enum
- `packages/temper-rust-router/Cargo.toml` — rustsat 0.7.5, rustsat-cadical 0.7.5
  (active), splr (removed)

### Institutional Learnings

- **splr → CaDiCaL migration** (`docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md:512-565`):
  splr 0.13 panicked on >6 nets. Replaced with rustsat-cadical which handles the full
  model. CaDiCaL supports incremental `solve()` via the `SolveIncremental` trait — the
  CEGAR loop in this plan depends on this capability. The `FreezeVar` trait is also
  available to prevent variable elimination during preprocessing.
- **Constraint audit over golden fixtures** (same plan amendment): The Rust solver
  validates output against the constraint model directly (`audit.rs`) rather than
  against golden fixtures from the buggy Python solver. This plan extends the audit to
  validate bundled results by expanding class variables to per-net variables before
  checking.
- **Binary-handoff pattern** (`packages/temper-rust-router/src/types_py_bridge.rs`):
  Python passes `ConstraintModel` as typed Python objects; Rust converts to internal
  `InternalConstraintModel`. The `BundleManifest` follows the same pattern — Python
  builds it, Rust consumes it via a new bridge function.

### External References

- Sinz, C. (2005). "Towards an Optimal CNF Encoding of Boolean Cardinality
  Constraints." CP 2005 — the sequential counter encoding used in `encoding.rs`.
- Ohrimenko et al. (2009). "Lazy Decomposition for Distributed Constraint
  Satisfaction" — the LCG "lift" pattern for class→per-net variable homomorphism.
- CaDiCaL — SAT solver with `add_clause()` between `solve()` calls (root level),
  accessed via rustsat's `SolveIncremental` trait. Supports `freeze_var()` to prevent
  variable elimination during incremental solves.
- Jaccard index — used as the geometric overlap metric for bundle equivalence (R1).

---

## Key Technical Decisions

- **KD1 (Bundle equivalence criteria):** Bundle equivalence is defined by
  *constraint-type signature* (net class + physical dimensions) AND *geometric
  overlap* (Jaccard > 0.5 on skeleton edges) — not by graph isomorphism. Reasons: (a)
  graph isomorphism is NP-complete, (b) type signature captures structural properties
  relevant for constraints, (c) geometric overlap prevents nets in disjoint regions
  from incorrectly sharing a class variable.

- **KD2 (Safety always eager):** Safety constraints are always eager — never lazy.
  The whole point of Safety constraints (HV/LV isolation) is that they must NEVER be
  violated. Deferring them creates a window where the solver could commit to an
  assignment that already violates safety.

- **KD3 (Homomorphism pattern):** The homomorphism is injective from class variables
  to per-net variable *sets* (each class variable maps to N per-net variables where N
  = number of nets in the class). The reverse mapping is surjective — multiple per-net
  variables map to one class variable. This is the standard "lift" pattern from LCG
  (Ohrimenko et al. 2009).

- **KD4 (CEGAR, not mid-search callbacks):** The watchdog for lazy grounding runs
  *between* incremental `solve()` calls, not *during* CDCL search. CaDiCaL exposes
  `add_clause()` between `solve()` calls via the `SolveIncremental` trait from
  rustsat. This is counterexample-guided abstraction refinement (CEGAR), not
  fine-grained lazy clause generation. Flow: solve safety CNF → inspect full
  assignment → identify Performance violations → add blocking clauses → resolve.

- **KD5 (Python analyzer, Rust watchdog):** The bundle analyzer is a new Python
  module (`bundle_analyzer.py`) in `temper-placer`. The lazy grounding watchdog is a
  new Rust module (`watchdog.rs`) in `temper-rust-router`. The `BundleManifest`
  crosses the PyO3 boundary via a new bridge function. This keeps the Rust→Python
  boundary aligned with the existing pattern and simplifies the Rust code — Rust
  receives a pre-bundled constraint model where class variables are already resolved.

- **KD6 (Diff pair singleton bundles):** Diff-pair nets are placed in their own
  dedicated 2-net bundle classes. This avoids the paired-instantiation complexity
  described in OQ-D3. The homomorphism for diff-pair bundles is a pass-through (1:1
  mapping, no aggregation). This is a minimal-viable approach that can be relaxed
  after OQ-D3 is resolved.

- **KD7 (Class-variable naming convention):** Class-level variables follow the naming
  pattern `uses_B{bundle_id}_{channel_id}` (distinct from per-net
  `uses_N{net_idx}_{channel_id}`). The `B` prefix enables the extraction, audit, and
  watchdog modules to distinguish class variables from per-net variables without
  additional metadata.

---

## High-Level Technical Design

```
Python (temper-placer)                   Rust (temper-rust-router)
═══════════════════════                  ═══════════════════════════

ModelBuilder.build(enable_bundling=True)
  │
  ├─ BundleAnalyzer.analyze() → BundleManifest
  │
  ├─ _create_class_channel_vars()     (class-level vars only)
  ├─ _create_safety_constraints()     (AtMostK over class vars)
  │
  └─ solve_topology_rust_bundled(     ──►  bridge_bundled_model()
       constraint_model,                       │
       bundle_manifest,              ├─ encode_eager_cnf() → safety CNF
       net_names                    )      │  (class vars + safety clauses)
                                      ├─ CaDiCaL::solve() → SAT/UNSAT
                                      │     │
                                      │     ├─ SAT → watchdog::inspect()
                                      │     │    ├─ no Performance viol → extract
                                      │     │    └─ Performance viol found:
                                      │     │         ├─ instantiate per-net vars
                                      │     │         ├─ add blocking clauses
                                      │     │         └─ CaDiCaL::solve() (loop)
                                      │     │
                                      │     └─ UNSAT → return
                                      │
                                      ├─ extraction::extract_bundled()
                                      │    (inverse homomorphism expand)
                                      │
                                      └─ audit::audit_constraints()
                                           (expand class vars → per-net)
```

### Data Flow

1. **Pre-solve (Python):** `BundleAnalyzer.analyze(nets, skeletons)` produces a
   `BundleManifest`. `ModelBuilder.build(enable_bundling=True)` creates a
   `ConstraintModel` with class-level `NetChannelVar` instances (prefix `uses_B`)
   and only Safety-typed constraints. The `BundleManifest` is passed alongside the
   constraint model to Rust.

2. **Encoding (Rust):** `encode_eager_cnf()` translates the class-level constraint
   model to CNF. Class variables get SAT indices. Only Safety constraints are
   encoded — Performance and Aesthetic constraints are recorded in the watchdog's
   internal state for downstream checking.

3. **CEGAR Loop (Rust):** `solve_bundled()` enters a loop:
   - Call `CaDiCaL::solve()` on the current CNF.
   - On SAT: inspect the full assignment against recorded Performance constraints
     (class variable assignments → check if any diff pair is split, etc.).
   - If violations found and budget remains: instantiate per-net variables for
     affected nets, add blocking clauses, loop.
   - If no violations: extract topology via inverse homomorphism, audit, return.
   - On UNSAT: return UNSAT.
   - On budget exhaustion: mark affected nets for A* fallback.

4. **Extraction (Rust):** `extract_bundled()` parses `uses_B{bundle_id}_{channel_id}`
   assignments, looks up the bundle's net members in the `BundleManifest`, and
   expands to per-net `uses_N{net_idx}_{channel_id}` assignments for each member.

5. **Audit (Rust):** `audit_constraints()` receives the fully-expanded per-net
   constraint model and checks all constraints against the expanded assignments.

---

## Output Structure

```
packages/temper-placer/src/temper_placer/router_v6/
├── bundle_analyzer.py           # NEW: Bundle equivalence analysis, BundleManifest
├── type_gating.py               # NEW: Safety/Performance/Aesthetic classification
└── constraint_model.py          # MODIFY: add enable_bundling path, class-var creation

packages/temper-rust-router/src/
├── watchdog.rs                  # NEW: CEGAR loop, Performance violation detection
├── solver.rs                    # MODIFY: add solve_bundled() entry point
├── encoding.rs                  # MODIFY: add encode_eager_cnf() for class vars
├── extraction.rs                # MODIFY: add extract_bundled() with inverse homomorphism
├── audit.rs                     # MODIFY: class-variable expansion before audit
├── types.rs                     # MODIFY: add BundleClass, BundleManifest variants
├── types_py_bridge.rs           # MODIFY: add bundle manifest bridge from Python
└── lib.rs                       # MODIFY: add solve_topology_rust_bundled() PyO3 entry

packages/temper-rust-router/tests/
├── test_bundling.rs             # NEW: bundling-specific unit tests
└── test_watchdog.rs             # NEW: CEGAR loop property tests

packages/temper-placer/tests/router_v6/
├── test_bundle_analyzer.py      # NEW: bundle equivalence and determinism tests
├── test_type_gating.py          # NEW: constraint classification tests
└── test_bundled_equivalence.py  # NEW: bundled-vs-unbundled equivalence tests
```

---

## Implementation Units

### U1. Bundle Analyzer — Equivalence Classes and BundleManifest

**Goal:** Implement `BundleAnalyzer` that partitions nets into bundle equivalence
classes based on constraint-type signature and geometric overlap, producing a
deterministic `BundleManifest`.

**Requirements:** R1, R2, R2.1

**Dependencies:** None (standalone analysis module)

**Files:**
- Create: `packages/temper-placer/src/temper_placer/router_v6/bundle_analyzer.py`
- Create: `packages/temper-placer/tests/router_v6/test_bundle_analyzer.py`

**Approach:**
- `BundleAnalyzer.__init__(nets, skeletons, design_rules, diff_pairs)` computes per-net:
  1. **Constraint-type signature** — a `TypeSignature` namedtuple or dataclass with
     fields `(net_class: str, trace_width: float, clearance: float, has_diff_pair:
     bool, pin_layer_set: frozenset[str])`. Net class via `classify_net_type()` from
     `net_classification.py`. Width/clearance from `design_rules.get_rules_for_net()`.
     `has_diff_pair` from the diff_pairs list. `pin_layer_set` from component pin
     lookups on the `pcb` argument.
  2. **Geometric footprint** — the convex hull of the net's pin positions (resolved
     via `_net_pad_positions()` in `pipeline.py` or an equivalent inlined helper),
     expanded by a margin equal to the median channel edge length across all
     skeletons (`sum(edge_weight) / num_edges`).
  3. **Covered skeleton edges** — for each skeleton edge, check if the edge's
     midpoint lies within the net's geometric footprint polygon (using shapely
     `Polygon.contains(Point)`). Collect as a `frozenset[str]` of edge IDs.
- **Partitioning:** Iterate nets. Two nets share a bundle class iff their type
  signatures are identical AND the Jaccard index on their edge-cover sets > 0.5.
  Jaccard = |A ∩ B| / |A ∪ B|.
- **Constraint type classification** (delegated to TypeGating from U2): For each
  bundle class, determine `constraint_types` as `Set[ConstraintType]` where
  `ConstraintType` is `Literal["safety", "performance", "aesthetic"]`. This is a
  placeholder — full classification logic is in U2; U1 just calls
  `type_gating.classify_bundle_constraints(bundle)`.
- **Diff pair handling:** Per KD6, diff-pair nets form their own singleton (2-net)
  bundle classes irrespective of type-signature overlap. The `BundleAnalyzer`
  recognizes diff pairs from the `diff_pairs` list and forces each pair into a
  dedicated bundle.
- **Output:** `BundleManifest` dataclass with fields:
  - `bundles: dict[int, BundleClass]` where `BundleClass` has:
    - `bundle_id: int`
    - `net_indices: list[int]` (sorted by net index for determinism)
    - `type_signature: TypeSignature`
    - `geometric_footprint: Polygon`
    - `constraint_types: frozenset[str]` (`"safety"`, `"performance"`, `"aesthetic"`)
    - `is_diff_pair: bool`
  - `bundle_id_for_net: dict[int, int]` — reverse lookup net_idx → bundle_id
  - `unbundled_net_indices: list[int]` — nets that could not be bundled (singletons)
  - Sorted: bundles ordered by `bundle_id`, which is assigned in increasing order of
    the first net index in the class.
- Performance target: O(n log n) in the number of nets. Pairwise Jaccard computation
  is O(b² · |E_skeleton|) in the worst case for small b, but with clustering based
  on type-signature pre-grouping, the effective cost is O(n log n).

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py:153-363` —
  `ModelBuilder` structure, the consumer of the manifest
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:159-192` —
  `_net_pad_positions()` for pin coordinate resolution
- `packages/temper-placer/src/temper_placer/router_v6/net_classification.py:75-87` —
  `classify_net_type()` for the net_class field in TypeSignature

**Test scenarios:**
- **T-U1-1 (Identical signal nets bundle):** Two signal nets with identical widths,
  same region, overlapping footprints → same bundle class. Assert `len(manifest.bundles) == 1`,
  `manifest.bundles[0].net_indices == [0, 1]`.
- **T-U1-2 (Dissimilar types don't bundle):** An HV net and a signal net in the same
  region → different bundle classes. Assert `len(manifest.bundles) == 2`.
- **T-U1-3 (Different widths don't bundle):** Two signal nets with 0.2mm and 0.5mm
  trace widths in the same region → different bundle classes (width differs).
- **T-U1-4 (Disjoint regions don't bundle):** Two identical signal nets on opposite
  corners of the board (Jaccard = 0) → different bundle classes.
- **T-U1-5 (Diff pair always singleton):** A diff pair with matching type signatures
  → whether or not they would otherwise bundle with other signal nets, they form
  their own 2-net bundle.
- **T-U1-6 (Determinism):** Run `BundleAnalyzer` three times with identical inputs →
  identical `bundle_id` assignments and sort order. Assert `manifest1 == manifest2 ==
  manifest3` (dataclass equality).
- **T-U1-7 (Empty nets):** Zero nets → empty `BundleManifest` with zero bundles and
  empty `bundle_id_for_net`.
- **T-U1-8 (Jaccard boundary):** Two nets with Jaccard exactly 0.50001 (overlap just
  above threshold) → bundled. Jaccard exactly 0.49999 → not bundled. Verify with
  controlled geometric inputs.

**Verification:**
- `python -m pytest packages/temper-placer/tests/router_v6/test_bundle_analyzer.py -v` — all tests pass
- Manual: Run on Temper PCB nets (23 nets) → verify bundle class count b,
  confirm b ≤ n (the number of nets)

---

### U2. Type-Gating Policy — Constraint Classification

**Goal:** Implement the configurable mapping from constraint kind → gating tier
(Safety/Performance/Aesthetic) and classify each bundle's constraint types.

**Requirements:** R3, R4, R5, R5.1

**Dependencies:** U1 (BundleManifest exists, bundle classes defined)

**Files:**
- Create: `packages/temper-placer/src/temper_placer/router_v6/type_gating.py`
- Create: `packages/temper-placer/tests/router_v6/test_type_gating.py`

**Approach:**
- Define `ConstraintType = Literal["safety", "performance", "aesthetic"]`.
- Define `ConstraintKind = Literal["capacity", "diff_pair", "layer_restriction"]`.
- `TypeGating` class with a configurable `rules: dict[ConstraintKind, ConstraintType]`
  defaulting to:
  ```python
  {
      "capacity": "safety",        # overridden per-channel below
      "diff_pair": "performance",
      "layer_restriction": "safety",
  }
  ```
  And a secondary rule per channel: if a `CapacityConstraint`'s channel touches an
  HV net, its type is upgraded to "safety"; all other `CapacityConstraint` instances
  are "performance".
- `classify_constraint(constraint_kind, channel_id, touches_hv) → ConstraintType`.
  `touches_hv` is determined by checking whether any of the constraint's variable
  terms belong to nets classified as `"hv"` by `is_hv_net()`.
- `classify_bundle_constraints(bundle, channel_adjacency) → frozenset[ConstraintType]`:
  for each constraint kind applicable to the bundle (capacity, diff_pair if bundle
  is a diff pair, layer_restriction), determine the gating tier.
- **Safety-first rule:** If any constraint for a bundle is Safety, the bundle's
  `constraint_types` must include `"safety"`. This ensures the safety clauses are
  always encoded before any `solve()` call.
- **Configurability:** The rules dict is passed as a constructor argument with
  defaults. Tests can inject alternative mappings to verify the gating mechanism
  without depending on net-name heuristics.

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/router_v6/net_classification.py:28-30` —
  HV net patterns used for `touches_hv` detection
- `packages/temper-placer/src/temper_placer/router_v6/stage0_data.py:88` —
  `safety_category` field reference (exists but may not be populated)

**Test scenarios:**
- **T-U2-1 (Safety default):** A `LayerConstraint` → classified as Safety. Assert
  `classify_constraint("layer_restriction", "CH1", touching_hv=False) == "safety"`.
- **T-U2-2 (Diff pair → Performance):** A `DiffPairConstraint` → classified as
  Performance. Assert `classify_constraint("diff_pair", "CH1", ...) == "performance"`.
- **T-U2-3 (HV capacity → Safety):** A `CapacityConstraint` on a channel touching an
  HV net → classified as Safety.
- **T-U2-4 (Signal capacity → Performance):** A `CapacityConstraint` on a
  signal-only channel → classified as Performance.
- **T-U2-5 (Configurable mapping):** Instantiate `TypeGating` with
  `rules={"capacity": "aesthetic", ...}` → capacity constraints classified as
  Aesthetic. Verify the injection mechanism works.
- **T-U2-6 (Bundle classification):** A diff-pair bundle → constraint_types contains
  `"safety"` (layer restrictions) and `"performance"` (diff pair). A plain signal
  bundle → constraint_types contains `"performance"` only.
- **T-U2-7 (Empty bundle):** Unbundled net with zero constraints → empty
  constraint_types set.

**Verification:**
- `python -m pytest packages/temper-placer/tests/router_v6/test_type_gating.py -v` — all tests pass
- Assert SC3: no Safety constraint is ever classified as Performance or Aesthetic

---

### U3. Eager Safety Encoding — Class-Variable Constraint Model

**Goal:** Extend `ModelBuilder` to create class-level `NetChannelVar` instances and
Safety-only constraints when `enable_bundling=True`. Pass the `BundleManifest` to
Rust alongside the constraint model.

**Requirements:** R3, R9

**Dependencies:** U1 (BundleManifest), U2 (TypeGating)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`
- Create: `packages/temper-placer/tests/router_v6/test_bundled_model_builder.py`

**Approach:**
- `ModelBuilder.__init__` gains `enable_bundling: bool = False` and optional
  `bundle_manifest: BundleManifest | None = None` parameters.
- When `enable_bundling=True` and `bundle_manifest` is provided:
  - `_create_channel_vars()` is replaced by `_create_class_channel_vars()`: iterate
    bundle classes instead of nets. For each bundle, for each skeleton edge, create
    one `NetChannelVar` with name `uses_B{bundle_id}_{channel_id}` and
    `var_type="bundle"`. The `net_idx` field is repurposed to hold `bundle_id`.
  - `_create_capacity_constraints()` builds `CapacityConstraint` terms from class
    variables. Width is the min width across all nets in the bundle (pessimistic
    assumption — safe). The AtMostK bound is `floor(channel_capacity / min_width)`.
  - `_create_layer_constraints()` creates `LayerConstraint` only for bundles where
    a Safety layer restriction applies (e.g., SMD pad layer enforcement).
  - `_create_diff_pair_constraints()` is suppressed — diff pairs are Performance and
    handled lazily by the watchdog.
- The existing `_create_via_vars()` continues to create per-net via vars (out of
  scope for bundling per scope boundary).
- The `BundleManifest` is serialized alongside the constraint model for Rust
  consumption. A new dataclass `BundledModel` wraps `(ConstraintModel, BundleManifest)`.
- In `pipeline.py:_run_stage3()`, when `enable_bundling=True`:
  1. Run `BundleAnalyzer.analyze()` before `ModelBuilder.build()`.
  2. Pass `bundle_manifest` to `ModelBuilder`.
  3. Pass both `constraint_model` and `bundle_manifest` to the Rust entry point
     (a new `solve_topology_rust_bundled()` function).

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py:187-277` —
  existing `_create_channel_vars` and `_create_capacity_constraints` (the pattern to
  fork for class-level creation)
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:594-700` —
  `_run_stage3()` integration point

**Test scenarios:**
- **T-U3-1 (Class variables created):** 3 nets form 1 bundle class, 2 skeleton edges
  → ModelBuilder with bundling creates 2 `NetChannelVar` instances (1 bundle × 2
  edges), not 6 (3 nets × 2 edges). All var names start with `uses_B`.
- **T-U3-2 (Safety constraints only):** The generated ConstraintModel contains
  `CapacityConstraint` and `LayerConstraint` instances, but no `DiffPairConstraint`
  instances (Performance, deferred).
- **T-U3-3 (Enable bundling False — unchanged):** With `enable_bundling=False`,
  the model is identical to the current unbundled model. Existing tests pass unchanged.
- **T-U3-4 (Empty manifest):** `bundle_manifest` with zero bundles → model has zero
  class channel vars, only via vars.
- **T-U3-5 (BundleManifest round-trip):** Build a `BundledModel`, serialize it to
  the pipeline's existing data path, verify the manifest can be reconstructed.
- **T-U3-6 (Variable count reduction):** On a test fixture with 10 identical signal
  nets, 1 channel → bundled model has 1 class variable. Assert variable count
  reduction ≥ 90% vs unbundled (SC1 pre-check).

**Verification:**
- `python -m pytest packages/temper-placer/tests/router_v6/test_bundled_model_builder.py -v` — all tests pass
- Run `test_constraint_generation` on the pipeline — model passes existing validators
- Manual: Print variable count for Temper PCB with bundling vs without — verify ≥90%
  reduction in `NetChannelVar` count

---

### U4. CEGAR Watchdog — Lazy Performance Grounding Loop

**Goal:** Implement the CEGAR watchdog in Rust that manages a CaDiCaL instance
through multiple `solve()` calls, detects Performance violations in SAT solutions,
instantiates per-net variables with budget limits, and adds blocking clauses.

**Requirements:** R6, R7, R7.1, R7.2

**Dependencies:** U3 (class-variable constraint model arrives from Python), U1
(extract_bundled from U5 — the watchdog needs homomorphism for violation detection)

**Files:**
- Create: `packages/temper-rust-router/src/watchdog.rs`
- Modify: `packages/temper-rust-router/src/solver.rs`
- Create: `packages/temper-rust-router/tests/test_watchdog.rs`
- Modify: `packages/temper-rust-router/src/lib.rs`

**Approach:**
- **`Watchdog` struct** holds:
  - `solver: CaDiCaL` — the CaDiCaL instance (initialized with safety CNF)
  - `bundle_manifest: InternalBundleManifest` — Rust-side representation of the
    bundle manifest (types defined in U1, bridged from Python)
  - `per_net_var_map: HashMap<String, usize>` — per-net variable names → SAT indices
  - `eager_var_count: usize` — number of class-level variables (fixed)
  - `budget_total: usize` — total per-net variable instantiation budget = M × |bundle_nets|
  - `budget_used: usize` — consumed budget counter
  - `cegar_iterations: usize` — iteration counter for logging
  - `budget_exhausted_nets: Vec<String>` — nets marked for A* fallback

- **`Watchdog::solve()`** — the main CEGAR loop:
  1. Call `solver.solve()` via the `SolveIncremental` trait.
  2. On `Unsat`: return `Unsat` — the safety CNF is unsatisfiable.
  3. On `Sat`: retrieve `full_solution()`.
  4. Call `inspect_violations()` to find Performance violations.
  5. If no violations: return `Sat` with assignments — done.
  6. If violations found:
     a. For each violation, call `instantiate_per_net_vars()` to create per-net
        variables and blocking clauses.
     b. If budget exhausted for a net: mark it for A* fallback, skip its clauses.
     c. Check if any clauses were added; if not (budget fully exhausted), return
        `Sat` with degraded marks.
     d. Increment `cegar_iterations` counter.
     e. Go to step 1 (re-solve).

- **`inspect_violations()`:**
  - Takes the full solution from `solver.full_solution()`.
  - For each diff-pair bundle: check if the bundle's class variable is assigned TRUE
    on two different channels. If the bundle variable is `uses_B42_CH1 = true` and
    also `uses_B42_CH2 = true`, the pair could be split. This is the trigger
    condition: "the partial assignment is compatible with a violation."
  - For each signal-only CapacityConstraint: check if the capacity bound is exceeded.
    Since class-level AtMostK already enforces this for class variables, a violation
    only occurs when the watchdog has instantiated per-net variables and the count
    exceeds the bound for those per-net vars.
  - Returns `Vec<Violation>` where `Violation { bundle_id, constraint_kind, channel_id }`.

- **`instantiate_per_net_vars(bundle_id, channel_id)`:**
  - Look up bundle → [net_indices] from manifest.
  - For each net index, create a per-net variable `uses_N{net_idx}_{channel_id}` via
    `solver.add_var()` (CaDiCaL creates variables implicitly from clause literals, but
    the watchdog tracks indices in `per_net_var_map`).
  - For diff pairs: add equivalence clauses `(uses_N{p_idx}_CH ↔ uses_N{n_idx}_CH)`
    per channel where the split was detected.
  - For capacity: add blocking per-net clauses with the correct AtMostK bound
    (sequential counter, referencing the per-net variables).
  - Track budget: each per-net variable costs 1 unit, each new sequential counter
    clause's auxiliary variables also count toward the budget.

- **Budget management:**
  - `budget_total = 10 * total_nets_in_bundles` (M=10, as per R7.1).
  - `budget_used` increments for each per-net variable instantiated plus auxiliary
    variables from sequential counter encoding.
  - When budget exhausted and violations remain for a net: add net to
    `budget_exhausted_nets`, skip its clause addition, continue with remaining
    violations.
  - Budget-exhausted nets are returned to Python as `degraded_nets` in the result.

- **Iteration limit:** Maximum 20 CEGAR iterations (safety valve). If exceeded,
  return `Unknown` with all ungrounded nets marked for A* fallback.

**Patterns to follow:**
- `packages/temper-rust-router/src/solver.rs:20-100` — CaDiCaL solve pattern
  (`solve_with_cadical`), now extended for incremental solves via
  `SolveIncremental::solve()` returning `Result<SolverResult>` between clause
  additions
- `packages/temper-rust-router/src/encoding.rs:20-75` — `encode_at_most_k()`
  sequential counter, reused for per-net blocking clauses
- rustsat 0.7.5 `SolveIncremental` trait — `add_clause()` after `solve()` is
  supported by CaDiCaL at the root level

**Test scenarios:**
- **T-U4-1 (Safety-only CNF — SAT, no violations):** A model with 1 bundle class
  (2 identical signal nets), 1 channel (capacity 2). Safety CNF has at most 2 class
  vars assigned. First solve returns SAT. `inspect_violations()` finds no Performance
  constraints (no diff pairs). Returns SAT without any lazy grounding.
- **T-U4-2 (Diff pair split detected):** A diff-pair bundle with variable
  `uses_B1_CH1 = true` and `uses_B1_CH2 = true`. `inspect_violations()` detects the
  split is possible. Watchdog instantiates per-net vars and adds equivalence clauses.
  Re-solve produces SAT with both members on the same channel.
- **T-U4-3 (Budget exhausted):** Set budget to 2 for a 10-net bundle. After 2 per-net
  variables instantiated, remaining performance violations for remaining 8 nets are
  skipped. Result includes `degraded_nets` containing the 8 ungrounded nets.
- **T-U4-4 (UNSAT safety CNF):** Safety CNF is unsatisfiable (channel with 0
  capacity, 1 bundle). First `solve()` returns `Unsat`. Watchdog returns `Unsat`
  without entering the CEGAR loop.
- **T-U4-5 (Multiple CEGAR iterations):** A complex model where the first blocking
  clause causes a cascade violation → watchdog iterates 2-3 times before converging.
  Assert `cegar_iterations > 1` and result is SAT.
- **T-U4-6 (Iteration limit reached):** Configure iteration limit to 1. A model
  requiring 2 iterations returns `Unknown` after the limit is hit.
- **T-U4-7 (FreezeVar usage):** Verify that class-level variables added to the safety
  CNF are NOT eliminated by CaDiCaL preprocessing between solves — the watchdog
  freezes them via `solver.freeze_var()` before the first solve.

**Verification:**
- `cargo test -p temper-rust-router test_watchdog` — all tests pass
- Property test: for random bundle models with ≤6 bundles, ≤4 channels, the watchdog
  loop terminates (SAT or UNSAT) within 20 iterations and budget <= M × total_nets
- Manual: verify CaDiCaL `add_clause()` + second `solve()` works with
  `SolveIncremental` trait via a minimal integration test (2 vars, 2 sequential solves)

---

### U5. Homomorphism — Class Variable ↔ Per-Net Variable Mapping

**Goal:** Implement the homomorphism that maps class-variable assignments to per-net
assignments (forward/expansion for extraction) and per-net variable sets to class
variables (inverse/projection for encoding). Validate the homomorphism preserves
constraint semantics.

**Requirements:** R8, R8.1

**Dependencies:** U1 (BundleManifest with net-to-bundle mapping), U4 (watchdog
instantiates per-net vars)

**Files:**
- Modify: `packages/temper-rust-router/src/extraction.rs`
- Modify: `packages/temper-rust-router/src/encoding.rs`
- Create: `packages/temper-rust-router/tests/test_homomorphism.rs`
- Modify: `packages/temper-rust-router/src/types.rs`

**Approach:**
- **`Homomorphism` struct** (in `extraction.rs` or a new module) holds:
  - `bundle_id_to_net_indices: HashMap<usize, Vec<usize>>` — from manifest
  - `net_idx_to_bundle_id: HashMap<usize, usize>` — reverse lookup
  - `class_var_to_net_vars: HashMap<String, Vec<String>>` — from class var name
    `uses_B{bundle_id}_{channel_id}` to per-net var names
    `uses_N{net_idx}_{channel_id}` for all nets in the bundle.

- **Forward (expand for extraction):** After the CEGAR loop returns SAT, the
  solver's assignments contain class-level variables (and possibly instantiated
  per-net variables). `expand_assignments()` maps each true class variable
  `uses_B{bid}_{ch}` to true per-net variables for all member nets. If a per-net
  variable was explicitly instantiated (its assignment overrides the expansion), the
  explicit value takes precedence.
- **Inverse (project for checking):** Given per-net assignments, `project_to_class()`
  maps each per-net variable to its bundle's class variable. For a bundle,
  `uses[B, ch] = true` iff at least one member net has `uses[net_i, ch] = true`.
- **Diff pair handling:** For diff-pair bundles (KD6), the homomorphism is identity
  — each net gets its own class variable, no aggregation. The bundle just groups the
  pair for the watchdog's diff-pair check.
- **Extraction integration:** `extract_bundled()` replaces
  `extract_topology()`. It parses both `uses_B` and `uses_N` variables, expands
  class assignments via the homomorphism, and produces the same `TopologyGraph`
  format as the unbundled path.
- **Encoding integration:** `encode_eager_cnf()` uses the homomorphism's inverse
  for class-variable naming: when building the capacity constraint for a channel,
  the constraint terms reference class vars `uses_B{bid}_{ch}`, not per-net vars.

**Patterns to follow:**
- `packages/temper-rust-router/src/extraction.rs:13-94` — existing
  `extract_topology()`, signature preserved; implementation adapted to handle both
  `uses_B` and `uses_N` prefix parsing
- `packages/temper-rust-router/src/encoding.rs:78-163` — existing
  `encode_to_cnf()`, extended with class-variable mode

**Test scenarios:**
- **T-U5-1 (Identity for singleton):** A singleton bundle (1 net per class) —
  `expand_assignments({"uses_B0_CH1": true})` produces `{"uses_N0_CH1": true}`.
  Assert 1:1 mapping.
- **T-U5-2 (Expansion for multi-net bundle):** Bundle with nets [0, 1, 2], class
  var `uses_B0_CH1 = true` → expands to `uses_N0_CH1 = true`, `uses_N1_CH1 = true`,
  `uses_N2_CH1 = true`. All three nets get the channel.
- **T-U5-3 (Per-net override):** Bundle with nets [0, 1]. Class var `uses_B0_CH1 =
  true` BUT per-net var `uses_N0_CH1 = false` was explicitly assigned. Expansion uses
  the explicit value for N0, class-variable expansion for N1.
- **T-U5-4 (Inverse/projection):** `project_to_class({uses_N0_CH1: true,
  uses_N1_CH1: false})` for bundle 0 → `uses_B0_CH1 = true` (at least one is true).
  `project_to_class({uses_N0_CH1: false, uses_N1_CH1: false})` → `uses_B0_CH1 =
  false`.
- **T-U5-5 (Diff pair passthrough):** Diff-pair bundle with nets [3, 4] → class vars
  are named with per-net conventions. Homomorphism is identity. Test expansion is a
  no-op (vars already per-net scoped).
- **T-U5-6 (Extract bundled):** Complete extraction pipeline: build a
  `BundleManifest`, run `extract_bundled()` with mock assignments, verify
  `TopologyGraph` has correct per-net channel assignments.
- **T-U5-7 (Exhaustive small-n homomorphism proof):** For n ≤ 6 nets, ≤4 channels,
  enumerate all assignments to class variables and verify that the expansion
  satisfies all constraints in the fully-grounded model. Property-based test using
  the brute-force checker from `audit.rs:225-273`.

**Verification:**
- `cargo test -p temper-rust-router test_homomorphism` — all tests pass
- Property test: for random bundle manifests (2-4 bundles, 2-6 nets, 2-4 channels),
  check that `expand ∘ project = id` on the per-net variable space (modulo nets that
  are always false).
- Manual: run the full extraction→audit pipeline on a bundled model — audit reports
  0 violations on the expanded model.

---

### U6. ModelBuilder Integration — Feature Flag and Pipeline Wiring

**Goal:** Wire the bundle analyzer, bundled model building, and Rust bundled solver
into `RouterV6Pipeline._run_stage3()` behind `enable_bundling` flag with unchanged
backward-compatible behavior.

**Requirements:** R9, R5 (aesthetic stub)

**Dependencies:** U1 (bundle analyzer), U2 (type gating), U3 (bundled model builder),
U4 (CEGAR watchdog), U5 (homomorphism / extraction)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py`
- Modify: `packages/temper-rust-router/src/lib.rs`
- Modify: `packages/temper-rust-router/src/types_py_bridge.rs`
- Create: `packages/temper-placer/tests/router_v6/test_bundled_pipeline.py`

**Approach:**
- **Rust `lib.rs` changes:**
  - Add `#[pyfunction] fn solve_topology_rust_bundled(variables, constraints,
    bundle_manifest: &Bound<'_, PyDict>, net_names) -> PyResult<PyObject>` — the new
    PyO3 entry point.
  - The function bridges `BundleManifest` from Python dict via a new
    `bridge_bundle_manifest()` function in `types_py_bridge.rs`.
  - Calls `watchdog::Watchdog::new()` → `watchdog.solve()` → `extraction::extract_bundled()` →
    `audit::audit_constraints()`.
  - Returns a dict with `status`, `assignments`, `topology_graph`,
    `solver_time_ms`, `num_vars`, `num_clauses`, `cegar_iterations`, `budget_used`,
    `degraded_nets`, `unsat_core`.
- **`types_py_bridge.rs` additions:**
  - `bridge_bundle_manifest(py_dict) -> InternalBundleManifest` — parses Python
    `BundleManifest` to Rust struct with `BundleClass { bundle_id, net_indices,
    type_signature, constraint_types, is_diff_pair }`.
- **Pipeline `__init__` change:**
  - Add `enable_bundling: bool = False` parameter alongside existing `max_sat_nets`.
  - When `enable_bundling=True` and `max_sat_nets is not None`, warn and use
    `enable_bundling` (bundling supersedes selective SAT).
- **`_run_stage3()` changes:**
  - When `enable_bundling=True`:
    1. Run `BundleAnalyzer.analyze()` before `ModelBuilder.build()`.
    2. Build `TypeGating` with default rules.
    3. Call `model_builder.build(enable_bundling=True, bundle_manifest=manifest)`.
    4. Serialize `BundleManifest` as a Python dict for PyO3.
    5. Call `solve_topology_rust_bundled(py_vars, py_cons, manifest_dict, net_names)`.
    6. Build `Stage3Output` from result, including `degraded_nets` in solution metadata.
  - When `enable_bundling=False`: existing behavior unchanged.
- **Aesthetic stub (R5):** An empty list `aesthetic_preferences` is recorded in
  `Stage3Output` for downstream consumption. No SAT clauses are added for aesthetic
  constraints. The `BundleManifest.constraint_types` set includes
  `"aesthetic"` where applicable, and the extracted topology carries this metadata.

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:594-700` —
  existing `_run_stage3()` for the Rust dispatch pattern
- `packages/temper-rust-router/src/lib.rs:26-102` — existing `solve_topology_rust()`
  PyO3 entry point pattern
- `packages/temper-rust-router/src/types_py_bridge.rs:6-87` — existing
  `model_from_python()` PyO3 bridge pattern

**Test scenarios:**
- **T-U6-1 (Feature flag off — no regression):** `enable_bundling=False` on a known
  model → output identical to pre-bundling codebase (variable count, clause count,
  SAT result). Assert SC6.
- **T-U6-2 (Feature flag on — bundled path):** `enable_bundling=True` on a model
  with 3 signal nets in 1 region → bundled model produced, solves successfully,
  topology extracted for all 3 nets.
- **T-U6-3 (degraded_nets propagation):** A model where budget is exhausted for net
  "SIG_X" → result includes `degraded_nets: ["SIG_X"]`. Downstream A* picks up the
  fallback.
- **T-U6-4 (max_sat_nets warning):** `enable_bundling=True, max_sat_nets=3` → a
  warning is logged, bundling takes precedence, all nets enter bundling (not just 3).
- **T-U6-5 (empty bundle manifest):** No bundles produced (all nets too dissimilar) →
  bundled path degrades gracefully to unbundled behavior (1:1 bundle-to-net mapping).
- **T-U6-6 (Aesthetic metadata preserved):** After bundled solve, `Stage3Output`
  includes `aesthetic_preferences` list (empty for now, but the field exists).

**Verification:**
- `python -m pytest packages/temper-placer/tests/router_v6/test_bundled_pipeline.py -v`
  — all tests pass
- Run closure test with `enable_bundling=False` — identical results to
  pre-bundling (SC6)
- Run closure test with `enable_bundling=True` on `pcb/temper_placed.kicad_pcb` —
  pipeline completes, SM1 ≥90%, SM2 ≥96.7% (SC5 pre-check)

---

### U7. Audit Adaptation — Expand Class Variables Before Check

**Goal:** Adapt the constraint audit (`audit.rs`) to validate bundled SAT results by
expanding class-variable assignments to per-net assignments before checking
constraints.

**Requirements:** R9.1

**Dependencies:** U5 (homomorphism expansion), U6 (pipeline wires audit)

**Files:**
- Modify: `packages/temper-rust-router/src/audit.rs`
- Modify: `packages/temper-rust-router/src/lib.rs`
- Create: `packages/temper-rust-router/tests/test_bundled_audit.rs`

**Approach:**
- Extend `audit_constraints()` to accept an optional `bundle_manifest:
  Option<&InternalBundleManifest>` parameter.
- When `bundle_manifest` is present:
  1. Before checking constraints, call `expand_assignments()` from the
     homomorphism to convert class-var assignments → per-net assignments.
  2. Build an expanded `InternalConstraintModel` from the manifest: for each bundle
     class, expand its constraints to per-net constraints (same constraint type, but
     with per-net variable names and widths).
  3. Run the existing constraint check logic against the expanded model and expanded
     assignments.
  4. Report violations in terms of per-net variable names (as currently done).
- When `bundle_manifest` is `None`: existing behavior unchanged.
- The Rust `lib.rs` `audit_result()` function is updated to accept an optional
  `bundle_manifest` Python dict and pass it through.

**Patterns to follow:**
- `packages/temper-rust-router/src/audit.rs:39-129` — existing
  `audit_constraints()`, logic extended not replaced
- `packages/temper-rust-router/src/lib.rs:109-191` — existing `audit_result()`
  function signature, extended with optional param

**Test scenarios:**
- **T-U7-1 (Bundled audit clean):** A bundled model with 1 bundle (2 nets), correct
  assignments → audit returns zero violations.
- **T-U7-2 (Bundled audit — capacity violation):** Assign both nets in a bundle to a
  channel with capacity for 1 net → audit detects capacity violation, reports in
  terms of per-net names `uses_N0_CH1` and `uses_N1_CH1`.
- **T-U7-3 (Bundled audit — diff pair mismatch):** A diff-pair bundle where the
  watchdog failed to ground the equivalence constraint → audit detects the mismatch
  and reports `p_var` / `n_var` mismatch.
- **T-U7-4 (Unbundled audit unchanged):** Call `audit_result()` without
  `bundle_manifest` → existing tests pass unchanged (audit_completeness_all_n4_combos
  etc.).
- **T-U7-5 (Empty bundle manifest):** Manifest with zero bundles → audit treats it
  as unbundled, no expansion needed.

**Verification:**
- `cargo test -p temper-rust-router test_bundled_audit` — all tests pass
- Existing `test_audit.rs` tests (from `audit.rs` inline tests) pass unchanged
- Integration: run constraint audit on bundled Temper PCB result → 0 violations

---

### U8. Correctness Validation — Bundled-vs-Unbundled Equivalence

**Goal:** Implement property-based tests and CI gate that verify the bundled encoding
is sound and complete relative to the unbundled encoding.

**Requirements:** R10, R10.1, R10.2, SC2, SC3, SC4

**Dependencies:** U1-U7 (all components integrated)

**Files:**
- Create: `packages/temper-placer/tests/router_v6/test_bundled_equivalence.py`
- Create: `packages/temper-rust-router/tests/test_bundling.rs`
- Modify: `packages/temper-rust-router/src/solver.rs` (telemetry for SC4)

**Approach:**
- **SC3 (Safety guarantee):** Add an assertion in `Watchdog::new()` that every Safety
  constraint is present in the CNF before the first `solve()`. The watchdog receives
  the full constraint list from the safety CNF and cross-references with the
  `BundleManifest.constraint_types`. Assert that no constraint marked `"safety"` is
  absent.
- **SC4 (Performance trigger correctness):** Add watchdog telemetry: each time a
  Performance clause is added, log the trigger assignment (which class variables were
  true causing the violation). In CI, verify that every lazy addition's log entry
  shows a guard condition that evaluates to true for that assignment.
- **SC2 (Lazy grounding correctness):** Property-based test in `test_bundling.rs`:
  - Generate random constraint sets with ≤8 nets, ≤4 channels, mix of Safety and
    Performance constraints.
  - Solve with bundled encoding (CEGAR loop).
  - Solve the same constraint set with fully eager encoding (all constraints encoded
    upfront).
  - Assert identical SAT/UNSAT result.
  - If SAT: assert that the per-net channel assignments (after homomorphism
    expansion) are identical modulo variable names.
  - Exhaustive for small n (n ≤ 4) — check all 2^(4×4) possible assignments.
- **R10 (Safety-only bit-identical):** For constraint sets with only Safety
  constraints (no Performance), the bundled encoding must produce bit-identical
  SAT/UNSAT to the unbundled encoding. Test with property-based generation of
  100 random Safety-only models.
- **R10.1 (Soundness):** For every SAT result from the bundled solver, assert that
  the expanded per-net assignments satisfy all Safety constraints (via audit).
- **R10.2 (Completeness):** For a known satisfiable model (e.g., 2 nets, 1 channel,
  capacity 2), the bundled solver with lazy grounding returns SAT.

**Test scenarios:**
- **T-U8-1 (Safety-only equivalence):** 100 random Safety-only models → bundled SAT
  = unbundled SAT for all.
- **T-U8-2 (Full equivalence with Performance):** ≤8 nets, ≤4 channels, ≤2 diff
  pairs → bundled result = fully eager result for all random configurations.
- **T-U8-3 (Safety in CNF before solve):** Assert watchdog constructor panics if a
  Safety constraint is missing from the CNF (injected test via mock).
- **T-U8-4 (Telemetry — every lazy add has trigger):** Mock a watchdog with a
  known-safe assignment that triggers a diff-pair split. Verify the telemetry log
  entry records the trigger assignment correctly.
- **T-U8-5 (Soundness — expanded model passes audit):** Take bundled SAT result,
  expand via homomorphism, run audit on expanded model → 0 violations.
- **T-U8-6 (Completeness — trivial case):** 1 bundle (1 net), 1 channel, capacity 1.
  Bundled solver returns SAT. Unbundled also returns SAT.

**Verification:**
- `cargo test -p temper-rust-router test_bundling` — all equivalence tests pass
- `python -m pytest packages/temper-placer/tests/router_v6/test_bundled_equivalence.py -v` — all Python-side tests pass
- CI: `check_constraint_audit` gate (or equivalent) passes on bundled model

---

### U9. End-to-End Integration — Closure Test Regression

**Goal:** Validate the bundled routing pipeline on the Temper PCB closure test,
ensuring SM1 completion rate ≥90% and SM2 DRC pass rate ≥96.7% are preserved, and
variable count reduction meets the SC1 target.

**Requirements:** SC1, SC5, SC6

**Dependencies:** U1-U8 (all units complete)

**Files:**
- Modify: `scripts/ci_closure_test.py` (or equivalent — add `--enable-bundling` flag)
- Create: `metrics/bundling_variable_reduction.json` (data output, not committed)

**Approach:**
- Add `--enable-bundling` flag to the closure test script. When set, instantiate
  `RouterV6Pipeline(enable_bundling=True)` and run the full 5-stage pipeline.
- **SC1 (Variable count reduction):** After `ModelBuilder.build(enable_bundling=True)`,
  log the number of `NetChannelVar` instances. Compare to unbundled baseline.
  Requirement: ≤10% of eager variable count (≥90% reduction).
- **SC5 (Closure preservation):** Run the full pipeline with bundling on
  `pcb/temper_placed.kicad_pcb`. Measure:
  - SM1 completion rate (should be ≥90%)
  - SM2 DRC pass rate (should be ≥96.7%)
  - Compare to `enable_bundling=False` baseline on the same board.
- **SC6 (No regression):** Run closure test with `enable_bundling=False` and assert:
  - Variable count matches pre-bundling baseline
  - Clause count matches pre-bundling baseline
  - SAT assignments match pre-bundling baseline
  - CI diff test gate passes.
- **Bundle class count:** Report b (number of bundle classes) for the Temper PCB.
  Expected: b < 23 (the net count). Log for OQ-R4 resolution.
- **CEGAR telemetry:** Log number of CEGAR iterations, budget used, budget
  exhausted nets (if any) to validate the watchdog behavior on real data.

**Verification:**
- `python scripts/ci_closure_test.py pcb/temper.kicad_pcb --enable-bundling` — pipeline completes
- SM1 ≥90%, SM2 ≥96.7%
- Variable count reduction ≥90% vs unbundled
- `python scripts/ci_closure_test.py pcb/temper.kicad_pcb` (no flag) — results
  identical to pre-bundling baseline (SC6)

---

### U10. (Optional) Empirical Calibration — Jaccard Threshold and Budget Multiplier

**Goal:** Calibrate the Jaccard overlap threshold (OQ-R3) and budget multiplier M
(OQ-D2) against the Temper PCB data to optimize the compression-vs-correctness
trade-off.

**Requirements:** OQ-R3, OQ-D2

**Dependencies:** U1 (bundle analyzer functional), U9 (closure test runs)

**Files:**
- Create: `scripts/calibrate_bundling_params.py`

**Approach:**
- Run `BundleAnalyzer` on Temper PCB data with Jaccard thresholds sweeping from 0.1
  to 0.9 in 0.1 increments. For each threshold, record:
  - Number of bundle classes b
  - Number of singleton bundles (nets that couldn't bundle)
  - Variable count reduction %
- Sweep budget multiplier M from 2 to 50 (logarithmic steps: 2, 5, 10, 20, 50). For
  each M, run the bundled solver on the Temper PCB and record:
  - CEGAR iterations
  - Budget exhausted nets (count)
  - Solver time
  - SAT/UNSAT outcome
- Select the smallest M that produces zero budget-exhausted nets and minimal CEGAR
  iterations.
- Select the Jaccard threshold that maximizes variable-count reduction while
  preserving at least one multi-net bundle (not all singletons).
- Output recommendations to a JSON report.

**Test scenarios:**
- Run calibrate script, verify it produces parameter recommendations.

**Verification:**
- Script runs and outputs valid JSON with threshold and multiplier recommendations.

---

## System-Wide Impact

- **Interaction graph:** `RouterV6Pipeline._run_stage3()` is the single integration
  point. Stage 2 output (skeletons, channel_widths) is consumed unchanged for bundle
  analysis. Stage 4 input (TopologyGraph + per-net channel assignments) format is
  preserved — `Stage3Output` dataclass is the contract, with optional
  `aesthetic_preferences` field added.
- **Error propagation:** `ImportError` on Rust crate → pipeline fails (no silent
  degradation — the Rust solver is a required dependency since the splr→CaDiCaL
  migration). Watchdog budget exhaustion → affected nets returned as `degraded_nets`
  and picked up by A* fallback in Stage 4. Rust solver panic → caught by PyO3,
  converted to Python exception.
- **State lifecycle risks:** None. The topology stage is stateless. The
  `BundleManifest` is computed once per invocation and consumed read-only by Rust.
- **API surface parity:** `enable_bundling: bool = False` is the only new public API
  parameter. When `False`, behavior is bit-identical to pre-bundling codebase. The
  existing `max_sat_nets` parameter continues to work but emits a warning when used
  with `enable_bundling=True` (bundling supersedes it).
- **Unchanged invariants:** `skip_stage3=True` bypasses bundling entirely. All
  existing Stage 1, 2, 4, 5 code is untouched. Stage 3's `Stage3Output` dataclass
  adds one optional field (`aesthetic_preferences`).
- **Variable naming convention:** Class variables use `uses_B{bundle_id}_{channel_id}`
  (KD7). Extraction and audit modules recognize both `uses_B` and `uses_N` prefixes.

---

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| CaDiCaL `SolveIncremental` trait does not support `add_clause()` after `solve()` as expected | Low | High | Verified: CaDiCaL supports clause addition at root level between solves. The `SolveIncremental` trait from rustsat 0.7.5 exposes `add_clause()`. Property-based test in U4 validates this early. |
| Jaccard threshold 0.5 is wrong for Temper PCB (too many singletons or too few classes) | Medium | Medium | U1 includes an empirical data-collection step; U10 calibrates the threshold if needed. Default 0.5 is the starting point; the plan accommodates tuning. |
| Budget multiplier M=10 is too low, causing premature degradation on real PCBs | Medium | Medium | U10 calibrates M against the Temper PCB. R7.1 explicitly states M is recalibrated in the first integration sprint. The degradation path (A* fallback) is graceful — nets still route, just without SAT coordination. |
| Homomorphism does not preserve equivalence for Performance constraints | Low | High | Exhaustive small-n property tests in U8 (n ≤ 8, ≤4 channels) verify the homomorphism against a brute-force checker. The inductive proof from Sinz (2005) covers the cardinality constraint encoding. |
| Diff pair homomorphism complexity (OQ-D3) blocks all diff pairs | Low | Low | KD6 defers this: diff pairs get their own singleton bundles (no aggregation). The homomorphism for diff pairs is identity. This is correct but yields no compression for diff pairs — acceptable for the initial implementation. |
| Bundle analysis time exceeds `ModelBuilder` time, negating variable-count savings | Low | Low | Bundle analysis is O(n log n) with pairwise Jaccard computed only within type-signature pre-groups. On 23 nets (Temper PCB), this is trivial. Even on 200-net boards, the cost is dominated by the SAT solve. |
| `safety_category` field on `NetClassRules` is not populated in production data | Medium | Low | The plan falls back to net-name-based heuristics from `net_classification.py` (R3-R5 fallback mapping specified). This is sufficient for the initial implementation. Adding `safety_category` population from KiCad net class specs is prerequisite work deferred to a follow-up. |

---

## Documentation / Operational Notes

- Update `AGENTS.md` with the `enable_bundling` parameter and its interaction with
  `max_sat_nets`.
- Add docstrings to `BundleAnalyzer`, `TypeGating`, and `Watchdog` explaining the
  equivalence criteria, gating policy, and CEGAR loop respectively.
- Document the `uses_B` vs `uses_N` variable naming convention in
  `packages/temper-rust-router/README.md` (or equivalent crate docs) for future
  maintainers.
- The `degraded_nets` list in solver output is user-facing — log a summary in
  pipeline verbose output when nets are routed via A* fallback due to budget
  exhaustion.

---

## Sources & References

- **Origin requirements:** `docs/brainstorms/2026-06-28-net-bundling-lazy-grounding-requirements.md`
- **Prior plan (Rust topology stage):** `docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md`
- **Relevant code:**
  - `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py`
  - `packages/temper-placer/src/temper_placer/router_v6/net_classification.py`
  - `packages/temper-placer/src/temper_placer/router_v6/stage0_data.py`
  - `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`
  - `packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py`
  - `packages/temper-rust-router/src/solver.rs`
  - `packages/temper-rust-router/src/encoding.rs`
  - `packages/temper-rust-router/src/extraction.rs`
  - `packages/temper-rust-router/src/audit.rs`
  - `packages/temper-rust-router/src/types.rs`
  - `packages/temper-rust-router/src/types_py_bridge.rs`
  - `packages/temper-rust-router/Cargo.toml`
- **External:**
  - Sinz, C. (2005). "Towards an Optimal CNF Encoding of Boolean Cardinality Constraints." CP 2005.
  - Ohrimenko et al. (2009). "Lazy Decomposition for Distributed Constraint Satisfaction."
  - rustsat 0.7.5 / rustsat-cadical 0.7.5 — `SolveIncremental`, `FreezeVar` traits
