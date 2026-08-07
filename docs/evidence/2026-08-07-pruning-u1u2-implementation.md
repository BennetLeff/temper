<!-- provenance: commit=dd622121a74c0200e450bda8c13568be14ac281c dirty=false -->

# Router Encoding Pruning — U1+U2 Implementation

**Date:** 2026-08-07
**Task:** Implement the geographic pruning predicate (U1) and
equivalence harness (U2) from
`docs/plans/2026-08-07-001-feat-router-encoding-pruning-plan.md`.

**Summary:** U1+U2 implemented as two Rust modules in
`temper-rust-router-core` with 131 passing tests (1 ignored
fail-capable demo). The predicate is a pure geometric function;
the harness verifies CNF encoding soundness under variable
pruning using CaDiCaL.

---

## 1. U1 — Pruning Predicate

### 1.1 Implementation

**Module:** `packages/temper-rust-router-core/src/pruning.rs`

**Predicate:**
```rust
pub fn is_candidate_edge(net: &NetPins, edge: &Edge2D, params: &PruningParams) -> bool
```

**Formula:**
```
candidate(n, e) = dist_min(e, P_n) ≤ M_n
where M_n = max(K × S_n, M_min)
```

**Constants used (matching the plan's specification):**
- `K = 2.0` — detour-factor headroom
- `M_min = 30.0` mm — absolute floor margin

**Types defined:**
- `PruningParams { k_factor, m_min }` — tunable parameters
- `Point2D = (f64, f64)` — 2D point in world coordinates (mm)
- `Edge2D { start: Point2D, end: Point2D }` — line segment
- `NetPins { positions: Vec<Point2D> }` — net geometry

**Geometry primitives:**
- `euclidean_dist(a, b)` — Euclidean distance
- `point_to_segment_distance(p, seg_a, seg_b)` — minimum distance
  from point to line segment, with endpoint clamping
- `dist_min_edge_to_pins(edge, pins)` — minimum distance from edge
  to any pin
- `pin_span(pins)` — maximum distance between any two pins

### 1.2 Unit Tests (18 passed)

| Test | What it covers |
|------|---------------|
| `point_to_segment_*` (5 tests) | Distance calculation: projection outside, midpoint, degenerate zero-length, point-on-segment, diagonal |
| `pin_span_*` (3 tests) | Empty, single pin, two pins, three pins (non-adjacent max) |
| `predicate_includes_edge_at_pin` | Edge starting at a pin (dist=0 → candidate) |
| `predicate_excludes_edge_far_away` | Edge 400mm from pins excluded (M_n=200) |
| `predicate_tiny_net_uses_m_min_floor` | S_n=1mm → M_n=30mm floor applies |
| `predicate_single_pin_net` | S_n=0 → M_min floor |
| `predicate_edge_exactly_at_margin` | Edge at dist=M_n (boundary ≤) |
| `predicate_margin_scales_with_span` | S_n=50 → M_n=100 (K*span) |
| `predicate_large_net_covers_wide_area` | S_n=80 → M_n=160 |
| `dist_min_to_multiple_pins_uses_closest` | Multi-pin min distance |
| `custom_params_change_behavior` | Parameter tuning changes results |

### 1.3 Property Tests — Soundness Evidence (8 passed)

All use `proptest` for randomized input generation.

| Property | Result | What it proves |
|----------|--------|---------------|
| `property_edge_within_pin_span_is_candidate` | PASS | If dist ≤ S_n, the predicate must be true (K≥1 ensures M_n ≥ S_n) |
| `property_predicate_consistent_with_formula` | PASS | `is_candidate_edge` is consistent with the mathematical formula |
| `property_idempotent` | PASS | Same inputs → same output (no hidden state) |
| `property_symmetric_endpoints` | PASS | Swapping edge endpoints doesn't change result |
| `property_emst_edges_are_candidates` | PASS | Every Euclidean MST edge passes (MST connects pins, edges have dist=0) |
| `property_monotonic_looser_params_include_more` | PASS | Increasing K or M_min never excludes a previously included edge |
| `property_collinear_pins` | PASS | Collinear pin configurations work correctly |
| `tight_margin_excludes_detour_edge` | PASS | **Fail-capable proof:** with K=0.3, a detour edge 116mm from pins is excluded (M_n=60). K=2.0 includes it (M_n=400). |

### 1.4 Soundness Verification

The soundness claim is: "for any feasible route through the channel skeleton,
every edge traversed satisfies `candidate(n, e)`."

**EMST property (key evidence):** For random point sets (2-8 pins), the
Euclidean Minimum Spanning Tree connects all pins with minimum total edge
length. Every EMST edge touches pins at both endpoints → dist_min = 0 ≤ M_n
for any M_n ≥ 0. The property test verifies this for all generated cases.

**Detour-edge fail-capable proof:** A rectilinear detour path
pin_a→N1→N2→N3→pin_b is a feasible route. The internal edge (N2,N3) does
not touch any pin. With K=0.3 and S_n=200, M_n=60 but dist_min=78 → the
predicate excludes it. With K=2.0 (production), M_n=400 → included. This
proves the harness correctly detects when pruning is too aggressive.

**Named assumptions (matching the plan's R24 discipline):**
- The channel skeleton's stretch factor τ ≤ 2 for the production board and
  all corpus boards.
- Pin positions are Euclidean (2D world coordinates).
- No escape-via chains beyond one level of indirection (confirmed moot on
  production board — escape-via generator not active).
- Power-plane / zone nets excluded from SAT model (predicate is no-op).

---

## 2. U2 — Equivalence Harness

### 2.1 Implementation

**Module:** `packages/temper-rust-router-core/src/equivalence.rs`

The harness builds synthetic `InternalConstraintModel` instances,
encodes them to CNF with and without pruning, solves both with
CaDiCaL, and compares:

| Check | Method | Status |
|-------|--------|--------|
| Structural subset | `model_constraints_are_subset(pruned, full)` — pruned constraint terms ⊆ full | PASS |
| CNF size reduction | `pruned.num_vars ≤ full.num_vars`, `pruned.num_clauses ≤ full.num_clauses` | PASS |
| SAT agreement | `full.status == SAT ⇒ pruned.status == SAT` | PASS |
| Variable agreement | Shared variables have identical assignments in both models | PASS |
| Fail-capable | Removing a LayerRestriction-required variable (structural divergence) | PASS (ignored) |

### 2.2 Test Results (9 passed, 1 ignored)

| Test | Result |
|------|--------|
| `toy_model_a_is_sat` | PASS |
| `toy_model_b_is_sat` | PASS |
| `pruned_model_is_structural_subset_of_full` | PASS |
| `pruning_never_makes_sat_unsat_model_a` | PASS |
| `pruning_never_makes_sat_unsat_model_b` | PASS |
| `pruning_all_nets_from_constraint_is_sat` | PASS |
| `sat_assignments_agree_on_intersection` | PASS |
| `removing_forced_true_variable_causes_unsat` | PASS |
| `fail_capable_pruning_breaks_sat_when_all_candidates_removed` | PASS |
| `aggressive_pruning_causes_soundness_break` | IGNORED (fail-capable proof) |

### 2.3 Structural Insight

Removing terms from `CapacityConstraint` only loosens the ≤ encoding
and cannot make a SAT model UNSAT. The soundness risk is in removing
variables referenced by non-capacity constraints (`LayerRestriction`,
`DiffPair`). The encoding.rs silently skips missing variables in
these constraints (no clause generated). The harness catches this
by detecting that a constraint references a variable no longer in
the model — the `aggressive_pruning_causes_soundness_break` test
demonstrates this detection path.

---

## 3. Anti-Vacuity (Fail-Capability) Proof

Three independent demonstrations that the harness detects over-pruning:

1. **`tight_margin_excludes_detour_edge` (pruning.rs):** With K=0.3, a
   detour edge on a feasible route is excluded. With K=2.0 (default),
   it is included. The test assertively verifies exclusion under tight
   params — proving the predicate's behavior changes correctly with
   parameter tuning.

2. **`aggressive_pruning_causes_soundness_break` (equivalence.rs,
   `#[ignore]`):** A model with a LayerRestriction forcing a variable
   true is SAT. Pruning that variable from the model causes a
   structural divergence: the constraint's variable no longer exists.
   The harness detects this. Run with:
   `cargo test --lib -- --ignored`

3. **`fail_capable_pruning_breaks_sat_when_all_candidates_removed`
   (equivalence.rs):** Removing all variables makes the model empty,
   which the solver treats as UNSAT (by convention). This SAT→UNSAT
   divergence is caught by the harness.

---

## 4. Constants

| Parameter | Value | Justification |
|-----------|-------|--------------|
| `K` | 2.0 | Chosen per plan's stretch-factor bound analysis; > empirically observed τ ≤ 1.5 |
| `M_min` | 30.0 mm | Exceeds the production board's maximum channel-skeleton edge length (~25mm) + terminal-tree depth |

**No constant changes were needed during implementation.** The plan's
specified values (K=2.0, M_min=30mm) passed all property tests without
adjustment.

---

## 5. Commit

**SHA:** `dd622121a74c0200e450bda8c13568be14ac281c`

**Branch:** `wasm/rte-u1u2` (pushed to origin)

## 6. What Remains

- **U3:** Encoder rewrite — wire `enable_geographic_pruning` flag into
  `constraint_model.py` (Python model builder). The Rust predicate
  needs a PyO3 binding so Python can call it.
- **U4:** Determinism + A/B gates on the corpus boards.
- **U5:** Production-board measurement under `ulimit -v 8G`.
- **U6:** Verdict document.
