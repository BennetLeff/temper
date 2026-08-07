---
title: Router SAT Encoding Geographic Pruning — Plan
type: feat
date: 2026-08-07
topic: router-encoding-pruning
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
---

# Router SAT Encoding Geographic Pruning — Plan

## Goal Capsule

**Objective:** Replace the global Sinz (2005) sequential-counter cardinality
encoding with a geographically-pruned cardinality encoding so the production
board's SAT model drops from 42M CNF variables / 78M clauses by a factor of
~10–40×, making the R3 producer (`route_pcb()`) runnable on a standard 16 GB
runner without OOM.

**Root cause addressed (attribution from the OOM diagnosis,
`docs/evidence/2026-08-07-router-oom-diagnosis.md` §2):** The Sinz encoding
in `packages/temper-rust-router-core/src/encoding.rs`
(`encode_at_most_k`) expands ~2M primary variables into 42M CNF vars / 78M
clauses across 20,734 capacity constraints, each over **all 96 nets**
regardless of whether a net's pins are anywhere near the edge. The dominant
term is `O(n_nets × E)` where `E ≈ 21,912` is the full-board channel-skeleton
edge count — the encoder assigns a `NetChannelVar` for every (net, edge) pair
unconditionally (see `constraint_model.py::_create_per_net_channel_vars` and
`_create_capacity_constraints`). The July 27 Stage 3 model-and-rewrite doc
(`docs/evidence/2026-07-27-stage3-model-and-rewrite.md`) ranked this as the
highest-leverage unfixed issue (recommendation #2).

**Product authority:** temper-placer + temper-rust-router-core maintainers.

**Open blockers:** none. The OOM diagnosis established that the model size is
intrinsic to the current encoding and that no code regression caused it. The
`var_to_net` clone removal (#898) already recovered ~1.5 GB without changing
the model. This plan's work is the architectural follow-up scoped by that
diagnosis.

---

## Product Contract

### Summary

The geographic pruning replaces the unconditional per-net-per-edge variable
creation with a **candidacy predicate**: a `NetChannelVar` for net `n` on edge
`e` is created only if `e` is geometrically near the pins of `n`. This reduces
the number of terms per `CapacityConstraint` from 96 (all nets) to a small
constant (nets whose pins are within routing distance of that edge). The
cardinality encoding itself (`encode_at_most_k`) is unchanged — the reduction
comes from shrinking the input, not from changing the Sinz algorithm. The
CNF auxiliary-variable blowup is `O(n·k)` per constraint, so reducing `n`
from 96 to ~3–10 reduces the auxiliary-variable count by ~10–30× per
constraint, and the total CNF size by a similar factor.

The candidate set is a **conservative overapproximation** of the feaseable-
routing region: the predicate must include every edge the net *could* use,
while excluding edges the net *cannot* use. Soundness (no false negatives —
never drop a feasible route) is the correctness crux. The plan's U1 defines
the exact predicate and its soundness argument; U2 builds an equivalence
harness to validate it empirically against the full encoding on a corpus.

### Key Decisions

- **D1. Pruning predicate is a per-edge filter, not a per-net filter**
  (plan-settled). The predicate gates on whether net `n` is a candidate for
  edge `e` — not whether edge `e` is a candidate for net `n`. The `CapacityConstraint`
  for edge `e` only includes nets that pass the filter. This mirrors the
  existing code structure: `_create_capacity_constraints` already iterates
  per-edge and builds per-edge `terms` lists; the predicate is inserted as a
  filter in that loop.

- **D2. The cardinality encoding primitive (Sinz sequential counter) is
  preserved** (plan-settled). Geographic pruning shrinks the *input* to the
  existing `encode_at_most_k`; it does not change the encoding algorithm.
  Changing the primitive (e.g., to a Totalizer or Binary Adder) is deferred
  to a separate investigation (see Open Questions E.1). The Sinz encoding
  has a published correctness proof and 101/101 passing exhaustive tests
  (`n ∈ 1..8`), and its known limitation — `O(n·k)` auxiliary-variable
  blowup — is mitigated by reducing `n`.

- **D3. The pruning is applied in the Python model-builder
  (`constraint_model.py`), not in the Rust encoder** (plan-settled). The
  predicate requires access to pin positions (Python-world
  `pin_world_position`) and the channel-skeleton edge geometry (available in
  Python's `ChannelSkeleton`). The Rust encoder operates on the already-
  pruned `InternalConstraintModel` and requires no geometry awareness. This
  keeps the Rust surface purely combinatorial and the Python surface
  responsible for geometric decisions — consistent with the existing
  `_apply_pcl_constraints` layer-constraint pattern (which already uses
  pin-edge geometry for layer restrictions at lines 556–576 of
  `constraint_model.py`).

- **D4. Determinism is preserved by construction** (plan-settled). The
  pruning predicate depends only on static board geometry (pin positions,
  channel-skeleton edge endpoints), which are immutable after Stage 2. No
  random seed, hash-map iteration order, or solver-timing sensitivity
  enters the predicate. The determinism protocol
  (`docs/evidence/2026-07-27-router-determinism.md`) requires bit-identical
  output on identical input — the behavioral A/B (U4) enforces this.

- **D5. The encoding change does not alter the ortools CP-SAT boundary
  verdict** (plan-settled — see Section F). The router's SAT pipeline
  (CaDiCaL, Sinz encoding) and the placer's CP-SAT pipeline (ortools) are
  independent solver chains. The geographic pruning reduces the router's
  CNF size; the placer boundary remains KEEP per the Wave-4 Phase 1 spike
  (`docs/evidence/2026-08-01-ortools-cpsat-spike.md`).

### Requirements

- **R1.** The pruned encoding must never exclude a feasible route that the
  full encoding admits (soundness — no false negatives). The pruning
  predicate is a conservative overapproximation with a written soundness
  argument (U1).
- **R2.** The pruned encoding must be behaviorally equivalent to the full
  encoding on the board corpus — same routing completion, same routed nets,
  bit-identical route geometry — as validated by the equivalence harness (U2)
  and the behavioral A/B gate (U4).
- **R3.** The CNF size reduction must be ≥10× on the production board,
  measured as `(pre-CNF-vars / post-CNF-vars)` under the production
  `route_pcb()` defaults (U5).
- **R4.** The pruned router must complete under `ulimit -v 8388608` (8 GB
  virtual memory) on the production board with the production
  `sat_conflict_limit=20_000` (U5).
- **R5.** Determinism: five consecutive `route_pcb()` runs on identical input
  must produce bit-identical `routed_pcb_content` (SHA-256 match), per the
  determinism protocol (U4).
- **R6.** The behavioral A/B gate (pre-change vs post-change on the corpus)
  must pass — bit-identical route output on every board in the corpus (U4).
- **R7.** The performance A/B gate must pass — the CNF size and solve time
  must not regress beyond the repo's margins (`TIMING_MARGIN = 0.20`,
  `COMPLETION_MARGIN = 0.10`) on any corpus board (U4).
- **R8.** The anti-vacuity demonstration must show that the equivalence
  harness actually catches a pruning failure — a deliberately-too-tight
  margin produces a route-completion regression, proving the harness is
  fail-capable (U4).
- **R9.** The CNF's post-solve audit (`audit_constraints`) must pass without
  violations on every corpus board and on the production board (U4, U5).

### Pruning Predicate (U1 specification)

This is the core technical specification — the exact predicate that
determines which edges a net may use, and the soundness argument that proves
it never excludes feasible routes.

#### Predicate definition

For net `n` with pin positions `P_n = {p_1, ..., p_m}` in world coordinates
(mm), and channel-skeleton edge `e = (u, v)` where `u, v` are (x, y) nodes:

```
candidate(n, e) = dist_min(e, P_n) ≤ M_n
```

Where:

- `dist_min(e, P_n) = min(dist_point_to_segment(u, v, p_i) for p_i in P_n)`
  — the minimum Euclidean distance from any pin of `n` to the line segment
  `e`. When the perpendicular projection of `p_i` onto `uv` falls outside the
  segment, `dist_point_to_segment` returns the distance to the nearest
  endpoint.
- `M_n = max(K × S_n, M_min)` is the per-net margin.
- `S_n = max_{p_i, p_j ∈ P_n} euclidean_dist(p_i, p_j)` is the net's pin
  span (the maximum Euclidean distance between any two of its pins).
- `K = 2.0` — the detour-factor headroom (conservative for channel-skeleton
  stretch factors ≤ 2).
- `M_min = 30.0 mm` — the absolute floor margin for nets with small pin
  spans (must exceed the board's maximum channel-skeleton edge length plus
  maximum terminal-tree depth).

**In the model-builder**, this predicate gates two sites:

1. **`_create_per_net_channel_vars`**: a `NetChannelVar` for `(net_idx,
   edge_id)` is created only if `candidate(net, edge)` is true.
2. **`_create_capacity_constraints`**: the terms list for each edge's
   `CapacityConstraint` is built from the (already-filtered) variables
   created in step 1, plus explicit filtering as a defense-in-depth
   consistency check.

#### Soundness argument (R24-style conservative bound)

**Claim:** For every net `n` and every feasible routing of `n` through the
channel skeleton, every edge traversed by the route satisfies
`candidate(n, e)`.

**Proof sketch (conservative overapproximation):**

1. **Span bounding.** Let `S_n` be the net's pin span. Any feasible route
   connects all pins of `n` as a Steiner tree in the channel-skeleton graph
   `G = (V, E)`. The route's total edge length `L_route ≥ S_n` (the
   Euclidean distance between the farthest-apart pins is a lower bound on
   any connecting path's length).

2. **Detour factor.** The channel skeleton is the medial-axis Voronoi graph
   of the board's free space — a planar graph embedded in the board
   geometry. For any two nodes `a, b` in `G`, the shortest-path distance
   `d_G(a, b)` satisfies `d_G(a, b) ≤ τ · euclidean_dist(a, b)` where `τ` is
   the graph's **stretch factor** (spanning ratio). For a medial-axis graph
   derived from a set of polygonal obstacles, the stretch factor is bounded
   by the obstacle geometry. On the production board (component footprints,
   keepout zones, board edge), the empirically observed stretch factor is
   ≤ 1.5 — routes follow the skeleton, which closely approximates the
   shortest obstacle-avoiding path. (The equivalence harness validates this
   bound explicitly.)

3. **Node-to-pin distance bound.** Let `v` be any node on the Steiner tree
   route. Let `p_i` be the nearest pin to `v` in the route's tree (i.e.,
   the pin `v` connects to through the tree). The path from `p_i` to `v` in
   the route has length `L_pv ≤ L_route`. The Euclidean distance from `p_i`
   to `v` is at most `L_pv` (Euclidean distance ≤ path length). Since any
   subpath of the route cannot exceed the total route length,
   `euclidean_dist(p_i, v) ≤ τ · S_n` (using the stretch-factor bound on the
   specific pin-to-node subpath, and noting that the route's tree diameter
   ≤ τ · S_n).

4. **Edge-to-pin distance bound.** For any edge `e = (u, v)` on the route,
   `dist_min(e, P_n) ≤ min(euclidean_dist(u, P_n), euclidean_dist(v, P_n))`.
   Both `u` and `v` are route nodes, so by step 3,
   `dist_min(e, P_n) ≤ τ · S_n`.

5. **Margin sufficiency.** With `K = 2.0 ≥ τ` and `M_min = 30.0mm`, we have
   `M_n = max(2 · S_n, 30.0) ≥ τ · S_n` for all nets. Therefore,
   `dist_min(e, P_n) ≤ M_n` holds for every edge on every feasible route, and
   `candidate(n, e)` is true.

**Conservative bound classification:** The predicate is a conservative
overapproximation (may include false positives — edges the net will not
actually use — but guarantees zero false negatives). The margin `K = 2.0`
is set above the empirically observed stretch factor of the production
board's channel skeleton, with headroom. The equivalence harness (U2)
provides exhaustive empirical validation for the corpus.

**Named assumptions and limitations:**
- The argument assumes the channel skeleton's stretch factor τ ≤ 2 for the
  production board and all corpus boards. If a board has a τ > 2 (e.g., a
  board with a narrow maze-like channel forcing long detours), the default
  margin may be insufficient. The harness detects this: if any net's route
  on a corpus board uses an edge excluded by the predicate, the U2 gate
  fails. The remedy is to increase `K` or `M_min` for that board class.
- The argument assumes pin positions are correctly mapped to their nearest
  skeleton nodes (the terminal-tree root). The existing
  `_apply_pcl_constraints` already performs this mapping (lines 556–576 of
  `constraint_model.py`), so no new geometry is needed.
- The argument does not address power planes or zone pours (net classes
  that are not routed through the skeleton). Per the OOM diagnosis §8,
  zone-pour-treated net classes are excluded from the SAT model; the
  predicate is a no-op for them.

---

## Unit Breakdown with Gates

### U1. Pruning Model — Predicate Specification and Soundness Argument

**Scope:** Define the exact geographic predicate (reproduced above in the
Pruning Predicate section), the per-net margin formula, and the written
soundness argument. This is a **document artifact** — the unit closes when
the predicate definition and soundness argument are reviewed and committed
in this plan document.

**What U1 does NOT cover:** implementation, empirical validation, or
corpus measurement. Those are U2–U6.

**Evidence that closes it:**
- The predicate definition is exact: `candidate(n, e) = dist_min(e, P_n) ≤ M_n`
  with `M_n = max(K × S_n, M_min)`, `K = 2.0`, `M_min = 30.0 mm`.
- The soundness argument (conservative overapproximation, stretch-factor
  bound, named assumptions) is written and linked from this plan.
- The "escape hatch" is specified: if the U2 harness finds a counterexample
  (a net routed through an edge excluded by the predicate), the margin
  parameters `K` and `M_min` are tunable constants, and the plan documents
  the escalation path (increase `K` → re-run harness → update this argument).
- The affected nets enumeration is produced: for the production board, nets
  with `S_n > 50mm` (spanning > half the board's smaller dimension) get
  `M_n ≥ 100mm` → nearly full-board candidate set → negligible pruning for
  those nets. These are acceptable: spanning nets legitimately need board-
  wide access. The pruning benefit comes from the majority of nets with
  `S_n ≤ 30mm`.

**Gate:** The soundness argument must satisfy the R24 discipline —
conservative-bound classification, named assumptions, and the U2 equivalence
harness as the empirical validation instrument.

---

### U2. Equivalence Harness — Differential CNF Satisfiability

**Scope:** Before touching the encoder, build a differential test that
compares pruned-encoding CNF satisfiability against full-encoding CNF on a
corpus of small-to-mid boards plus the production board's netlist. The
harness is the gate for U3 — the encoder rewrite must not land until the
harness passes on the full encoding (trivially, since pre-change = post-
change before U3), and then must remain green across U3.

**What the harness tests:**

1. **Route-existence agreement.** For every board in the corpus, build the
   constraint model twice — once with the full encoding (status quo) and
   once with the pruning predicate active. Assert that both models are
   satisfiable (SAT) or both are unsatisfiable (UNSAT). A divergence
   (full-SAT but pruned-UNSAT) is a soundness break — the pruning excluded a
   feasible route.

2. **Bit-identical assignments on SAT boards.** For boards where both models
   are SAT, assert that the variable assignments (for the intersection of
   variables present in both models) are bit-identical. A divergence
   (different satisfying assignment for the same net) indicates the pruning
   changed the solution space, which may or may not be a soundness break but
   requires investigation.

3. **DRC-equivalent output.** For SAT boards, produce routed PCB content
   from both models, run DRC on both, and assert identical violation counts.

**Corpus specification:**
- The existing 12 board fixtures from `tests/router_v6/` (the boards used
  by the determinism protocol and the production-board routing DRC
  regression test `test_production_board_routing_drc_regression`).
- The production board netlist (`pcb/temper.kicad_pcb`, 108 nets, 170
  footprints) — the full-board model.
- Optional: synthetic boards from the PBT suite's hypothesis generators,
  to stress-test the predicate on pathological net geometries (collinear
  pins, single-pin nets, nets with pins at all four corners).

**Harness structure:**
- Location: `packages/temper-placer/tests/router_v6/test_encoding_pruning_equivalence.py`.
- Pattern: PBT (`hypothesis`) for synthetic boards; parametrized (`pytest.mark.parametrize`) for the fixed corpus.
- Each test case: build model → apply predicate (pruned) → `solve_topology_rust` (both) → assert agreement.
- Must pass on the full encoding (trivially) before U3 begins.

**Evidence that closes U2:**
- The harness file exists and is committed.
- The harness passes on the full encoding (pre-U3 — identity check, both
  models use the same full encoding).
- The harness is proven fail-capable: a deliberately-too-aggressive
  predicate (e.g., `M_min = 0.1mm` — excludes nearly all edges for most
  nets) causes a route-completion regression on at least one corpus board.
  This is the anti-vacuity demonstration required by R8.

**Gate:** U3 must not begin until the harness is committed and passing
(identity mode).

---

### U3. Encoder Rewrite — Model-Builder Pruning

**Scope:** Implement the geographic pruning filter in
`constraint_model.py`, behind a feature flag (`enable_geographic_pruning`
on `ModelBuilder`, default `False`). Keep the full encoding as the default
and make the pruned encoding available behind the flag for A/B. The Rust
encoder (`encoding.rs`, `solve_topology_rust`) is **not changed**.

**Implementation sites:**

1. **`ModelBuilder.__init__`**: add `enable_geographic_pruning: bool = False`
   parameter.

2. **`ModelBuilder._create_per_net_channel_vars`**: when
   `enable_geographic_pruning` is true, apply the `candidate(n, e)` predicate
   before creating each `NetChannelVar`. The predicate implementation shares
   the existing pin-position access pattern from `_apply_pcl_constraints`
   (lines 540–586 of `constraint_model.py`).

3. **`ModelBuilder._create_capacity_constraints`**: when pruning is active,
   add a defense-in-depth assertion that every term in `capacity_constraint`
   corresponds to a net that passes the predicate for that edge (optional,
   debug-only).

4. **`_create_via_vars`**: apply the same geographic predicate to via
   variables. A via is only relevant for net `n` if the via-anchor node is
   within the expanded bounding box of `n`'s pins. This is the same
   predicate with `dist_min(node, P_n) ≤ M_n`.

**Constraints:**
- No changes to `encoding.rs`, `rewrite.rs`, `solver.rs`, or any Rust code.
- No changes to the `InternalConstraintModel` type or the CNF encoding path.
- The full encoding path (default) is unchanged and all existing tests pass.
- When `enable_geographic_pruning=True`, the model is strictly smaller (fewer
  variables per constraint, shorter terms lists).

**Evidence that closes U3:**
- The feature flag is implemented, tested, and committed.
- `cargo test --release` (router crates) passes — unchanged (no Rust changes).
- `pytest tests/router_v6/` passes on the full-encoding path (default).
- `pytest tests/router_v6/ --pruning` passes on the pruned path (U2 harness
  is the primary gate; additional targeted tests for the predicate itself:
  edge cases — nets with zero pins, single-pin nets, collinear pins,
  edge-on-pin-boundary).
- The predicate is unit-tested independently:
  - `test_predicate_includes_edges_near_pin`
  - `test_predicate_excludes_edges_far_from_pin`
  - `test_predicate_margin_scales_with_pin_span`
  - `test_predicate_min_margin_floor`
- The defense-in-depth assertion in `_create_capacity_constraints` is tested.

---

### U4. Determinism + A/B Gates

**Scope:** Run the full gate set: behavioral A/B (bit-identical route output
on the corpus, pre-change vs post-change), performance A/B (CNF size, solve
time, memory), determinism (five consecutive identical runs), and the
anti-vacuity demonstration.

**Gate checklist:**

| Gate | Instrument | Pass criterion |
|---|---|---|
| **Behavioral A/B** | `test_encoding_pruning_equivalence.py` (U2 harness) on the corpus | Bit-identical route output (SHA-256 match), identical completion rate, identical unrouted-net set |
| **Determinism** | Five consecutive `route_pcb()` runs on the production board with pruning enabled | Bit-identical `routed_pcb_content` (SHA-256 match across all five) |
| **Performance A/B — CNF size** | `num_vars`, `num_clauses` from `solve_topology_rust` on the production board, full vs pruned | `num_vars_pruned / num_vars_full ≤ 0.10` (≥10× reduction); `num_clauses_pruned / num_clauses_full ≤ 0.10` |
| **Performance A/B — solve time** | `solver_time_ms` from `solve_topology_rust` on the production board | `solve_time_pruned / solve_time_full ≤ 1.0 + TIMING_MARGIN` (no regression; expected large improvement) |
| **Performance A/B — memory** | Peak RSS during `solve_topology_rust` on the production board | `RSS_pruned ≤ RSS_full × (1.0 - COMPLETION_MARGIN)` (no regression beyond margin) |
| **Anti-vacuity** | U2 harness with deliberately-too-tight margin (`M_min = 0.1mm`) | At least one corpus board shows a completion regression (pruned-UNSAT while full-SAT) |
| **Post-solve audit** | `audit_constraints` on every corpus board, both full and pruned | Zero violations |
| **Existing suite** | Full `tests/router_v6/` on both full and pruned paths | All tests pass (any new failures are regressions) |

**Evidence that closes U4:**
- All gates pass. Results are recorded in a gate-results table in this plan
  document (updated in the implementation commit) or in a linked evidence
  doc.
- The behavioral A/B results are deterministic and reproducible.

---

### U5. Production-Board Measurement + R3 Unblock

**Scope:** Run the pruned encoding on the production board under resource
limits and record the outcome. This is the "does it actually work?" gate.

**Measurement protocol:**

1. Run `route_pcb()` on `pcb/temper.kicad_pcb` with `enable_geographic_pruning=True`,
   production defaults (`sat_conflict_limit=20_000`, `enable_manufacturing_drc=False`),
   under `ulimit -v 8388608` (8 GB virtual memory cap).

2. Record:
   - CNF size: `num_vars`, `num_clauses` (from the `[phase-trace]` output or solver stats).
   - Solve time: `solver_time_ms`.
   - Total wall time: parse → Stage 2 → model build → Stage 3 → Stage 4.
   - Peak RSS (from `time -v` or platform-equivalent).
   - Completion: routed count, unrouted count, unrouted net names.
   - DRC violations (if manufacturing DRC is later enabled).
   - Exit code (must not be OOM-killed; must exit 0).

3. Compare against the July 27 baseline (42M vars, 78M clauses, 52.67s
   Stage 3, ~7 GB RSS, 36/96 = 37.5% completion at 0 conflicts).

4. Expected outcome: CNF size ≤ 4.2M vars / 7.8M clauses (≥10× reduction),
   solve time ≤ 30s, peak RSS ≤ 4 GB (fits comfortably in 8 GB cap), same
   completion rate (37.5% = 36/96 routed) within the behavioral A/B margin.

**Evidence that closes U5:**
- The measurement log (commit + env + output) is recorded in an evidence
  doc (e.g., `docs/evidence/2026-08-07-pruned-encoding-measurement.md`).
- The route completes without OOM.
- The CNF size reduction meets or exceeds the 10× threshold.

---

### U6. Verdict — Tractable? Relationship to ortools CP-SAT Spike

**Scope:** Answer the two architectural questions:

1. **Does the pruning make the production route tractable on a standard
   (16 GB) runner?** Yes/no, with the measured CNF size and peak RSS as
   evidence. If yes, the R3 producer is unblocked and the route stage can
   run on the repo's CI runners and developer laptops. If no (reduction <5×
   or still >8 GB), the plan documents the remaining gap and next steps.

2. **Does this change the ortools CP-SAT boundary verdict?** No — the
   router's SAT encoding (CaDiCaL + Sinz) and the placer's CP-SAT encoding
   (ortools) are **independent solver pipelines** serving different stages:
   - The **router** (Stage 3) solves net topology: assigns each net to
     channel-skeleton edges with capacity constraints, producing a routing
     topology that Stage 4 (A*) then realizes.
   - The **placer** (CP-SAT) solves component placement: assigns (x, y,
     rotation) to components with separation/alignment/keepout/enclosure
     constraints.
   
   The geographic pruning reduces the router's CNF size. The placer's
   ortools boundary (KEEP verdict per
   `docs/evidence/2026-08-01-ortools-cpsat-spike.md`) is unaffected —
   the placer's constraint surface (C1–C13, 8 PCL handlers) is separate
   from the router's encoding (Sinz cardinality for capacity constraints).
   The two pipelines share no encoding logic, solver engine, or model
   representation.
   
   **The pruning does, however, change the cost basis of the overall route
   stage**, which was cited in the Wave-4 plan's Phase 1 spike as one
   motivation for investigating the solver boundary: if the router is too
   expensive to run on standard hardware, the entire pipeline is gated.
   Making the router tractable removes that gate — but the placer boundary
   verdict stands independently on its own merits (feature coverage, solver
   parity, the KEEP acceptance criteria).
   
   **Verdict: does not defer or reopen the ortools spike.** The spike's
   Phase 1 blocker correction
   (`docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`
   Phase 1 section, 2026-08-04 correction) already recorded the honest
   blocker: acceptance is unassertable across solver engines, and no
   pure-Rust candidate is mature enough. Reducing the router's CNF size
   does not create a new candidate or change the blocker analysis.

**Evidence that closes U6:**
- The U5 measurement is recorded and linked.
- The verdict is stated in this plan document (Section F, below).
- The Wave-4 plan's Phase 1 section does **not** require amendment (the
  pruning neither removes nor changes the KEEP verdict's acceptance
  criteria).

---

## Gates for the Soundness Claim (U1)

The pruning predicate's soundness claim is gated by three instruments,
following the R24 discipline:

| Instrument | Type | What it proves |
|---|---|---|
| **Written conservative-bound argument** (this plan) | Static proof | The margin `M_n = max(K × S_n, M_min)` with `K = 2.0` is a conservative overapproximation by the stretch-factor bound |
| **U2 equivalence harness — BMC-exhaustive on small N** | Empirical proof | For every board in the corpus (including the production board), the pruned encoding admits the same routes as the full encoding |
| **U4 anti-vacuity demonstration** | Fail-capability proof | A deliberately-too-tight margin causes a route-completion regression, proving the harness actually detects soundness breaks |

**Escalation path if the harness finds a counterexample:**
1. Record the net, edge, and board that caused the divergence.
2. Measure the actual `dist_min(e, P_n)` for the counterexample edge.
3. If `dist_min > M_n`: the margin was too tight for this net. Increase `K`
   (e.g., to 3.0 or 4.0) and re-run the harness.
4. If `dist_min ≤ M_n` but the route still diverges: the predicate is
   incorrectly implemented (e.g., `dist_point_to_segment` bug). Fix the bug,
   not the margin.
5. Re-run the harness. Repeat until green.
6. Update the soundness argument with the new `K` value and the
   counterexample it resolved.
7. Record the final `K` in this plan's Pruning Predicate section.

**Documented trade (named, enumerated):**
- **Trade 1: Absence of escape-via routing.** The predicate uses Euclidean
  distance to skeleton edges. The escape-via generator
  (`escape_via_generator.py`) may create vias at nodes that are not the
  nearest skeleton node to any pin — e.g., when a pin's breakout requires a
  via at a non-adjacent node. The predicate's `M_n` margin is large enough
  to cover one layer of escape-via indirection, but not an arbitrarily deep
  escape-via chain. **Affected nets on the production board:** none (the
  escape-via generator is not active in the production route path; confirmed
  by the OOM diagnosis §7 — `via_diameter_mm` / `via_diameter` schema
  mismatch prevents the generator from running).
- **Trade 2: Power-plane / zone nets.** Nets assigned to zone pours (power
  planes, ground fills) are not routed through the skeleton and have no
  `NetChannelVar` entries in the model. The predicate is a no-op for these
  nets. **Affected nets on the production board:** 12 nets (108 parsed − 96
  attempted = 12 excluded as zone-pour-treated, per the determinism doc's
  UNVERIFIED section). This is status-quo behavior — no regression.

---

## Sequencing Table

| Unit | Depends on | Estimated effort | Risk |
|---|---|---|---|
| **U1** (predicate spec + soundness) | None — doc artifact | 0.5 day | Low — specification, not implementation |
| **U2** (equivalence harness) | U1 (predicate defined) | 2–3 days | Medium — harness must be fail-capable; corpus must include production board |
| **U3** (encoder rewrite) | U2 (harness green on full encoding) | 2–3 days | Low — feature-flag, no Rust changes, well-isolated code sites |
| **U4** (determinism + A/B gates) | U3 (implementation) | 1–2 days | Low — existing gate infrastructure, scripted A/B |
| **U5** (production-board measurement) | U3, U4 green | 0.5 day | Medium — needs a quiet 16 GB+ machine |
| **U6** (verdict) | U5 (measurement) | 0.5 day | Low — doc artifact |

**Total estimated effort:** 7–10 days.

**Parallelism:** U1 and U2 can be drafted concurrently (U1 specifies the
predicate; U2 can start with placeholder parameters). U3 requires U2 green.
U4 requires U3. U5 requires U4 green. U6 requires U5.

---

## Non-Goals

- **No CP-SAT boundary change.** The ortools verdict (KEEP) stands. The
  router's SAT encoding and the placer's CP-SAT engine are separate.
- **No ortools port.** The router uses CaDiCaL via rustsat; the placer uses
  ortools. Neither changes.
- **No change to the committed board** (`pcb/temper.kicad_pcb`). The board
  copper is not modified. Only the router's internal model changes.
- **No new routing heuristics.** The routing algorithm (Stage 3 SAT topology
  → Stage 4 A* pathfinding) is unchanged. Only the SAT model's size changes.
- **No change to the cardinality encoding primitive.** The Sinz sequential
  counter is preserved. Changing it (to Totalizer, Ladder, Binary Adder) is
  deferred to a separate investigation (see E.1).
- **No Rust geometry crate.** The pruning predicate is implemented in Python
  using existing `pin_world_position` and skeleton edge geometry. No new
  Rust extension crate.
- **No rewrite-engine changes.** The rewrite engine's internal constraint
  model is not changed. It receives a smaller model and operates identically.
- **No bundle-manifest changes.** The `enable_bundling` path is an
  alternative variable-construction strategy; the geographic pruning is
  orthogonal and does not interact with it. This plan does not wire
  `enable_bundling=True` into the production path (that was the July 27
  Stage 3 doc's recommendation #2 — this plan's approach is strictly
  simpler and complementary).
- **No corpus expansion beyond existing boards.** The equivalence harness
  uses the existing corpus plus the production board. No new board fixtures
  are required.

---

## Open Questions

- **E.1. Is the Sinz sequential counter the right cardinality encoding when
  pruned?** With `n` per capacity constraint reduced from 96 to ~3–10, the
  Sinz encoding adds `(n−1) × k ≈ 3 × 10 = 30` auxiliary variables per
  constraint (down from ~950). At this scale, the choice of cardinality
  encoding is less significant. But for constraints with larger `n` (e.g.,
  a bottleneck channel near the board center where many nets' candidate
  regions overlap), `n` could be 20–40, and a more efficient encoding
  (Totalizer, `O(n log n)`) might further reduce CNF size. **Deferred** to
  a follow-up spike after U5's measurement shows the actual per-constraint
  `n` distribution on the production board.

- **E.2. How is "near its pins" defined for power planes and zone pours?**
  Power-plane nets are not routed through the channel skeleton — they are
  assigned to zone pours in Stage 4. The `_create_per_net_channel_vars` loop
  iterates over `self.nets` (all 108 parsed nets), but capacity constraints
  are only built for nets that have `NetChannelVar` entries. Zone-pour nets
  have no channel variables and are not in the model. **The predicate is a
  no-op for these nets.** No special handling is needed. The open question is
  whether future net-class-aware routing will require different predicate
  margins for HV nets (which must maintain larger clearances and therefore
  have larger effective routing footprints) — deferred to a future HV-routing
  task.

- **E.3. Does the pruning predicate interact with the escape-via generator?**
  The escape-via generator (`escape_via_generator.py`) creates vias at
  non-adjacent skeleton nodes for pin breakouts that cannot use a
  single-layer route. If active, it could create routes that use skeleton
  edges far from any pin. On the production board, the generator is **not
  active** (`via_diameter_mm` / `via_diameter` schema mismatch prevents it
  from running — see OOM diagnosis §7). If the generator is fixed and
  activated in the future, the margin `M_n` may need to increase (or a
  hop-based predicate may be needed). The plan's U1 trade enumeration
  records this. **Deferred** — out of scope until the generator is fixed.

- **E.4. Should the geographic pruning interact with `enable_bundling`?**
  Bundling groups nets into equivalence classes (nets that share the same
  route). The geographic predicate is orthogonal — a net's candidate edges
  depend on its pins, not on its bundle membership. The two features can
  coexist: a net in a bundle gets the union of candidate edges from all
  bundle members (pin-union predicate), or each net keeps its own candidate
  set and the bundle variable inherits the intersection. **Deferred** —
  bundling is not active in production and this plan does not change that.

- **E.5. What is the actual per-net pin-span distribution on the production
  board?** The predicate's margin formula `M_n = max(K × S_n, M_min)` is
  sensitive to the pin-span distribution — if most nets have large spans
  (e.g., >50mm), the pruning benefit is minimal. The July 27 Stage 3 doc
  estimated a 10–40× reduction; the actual factor depends on how many nets
  are locally-routed vs board-spanning. **Answerable by measurement** — the
  U2 harness can report per-net candidate-edge counts before U3 begins.

- **E.6. Should the pruning be the default, or remain behind a flag?**
  The plan specifies a feature flag (`enable_geographic_pruning`, default
  `False`) for the implementation phase. Whether to make it the default in
  `route_pcb()` is a separate decision, gated by the U4/U5 measurements and
  a product-authority review. The plan does not prescribe the default —
  it prescribes the gate set that must pass before any default change.

---

## F. Verdict — Relationship to ortools CP-SAT Spike (R4)

The Wave-4 Phase 1 spike (`docs/evidence/2026-08-01-ortools-cpsat-spike.md`)
evaluated the CP-SAT solver boundary (the placer's placement engine) and
returned KEEP. The geographic pruning in this plan applies to the **router's
SAT encoding** (Stage 3 topology), which is a different solver pipeline:

| Pipeline | Solver | Encoding | Stage | This plan changes? |
|---|---|---|---|---|
| Router SAT | CaDiCaL (rustsat) | Sinz cardinality CNF | Stage 3 (topology) | **Yes** — reduces model size via geographic pruning |
| Placer CP-SAT | ortools 9.15.6755 | CP-SAT proto model | Placement (separate pipeline) | **No** |

The two pipelines are connected only at the workflow level: `route_pcb()`
calls the placer (to position components), then the router (to route nets).
The router's CNF size has no bearing on the placer's constraint surface,
solver engine, or the KEEP/R4 acceptance criteria.

**The pruning does not change the boundary verdict.** It does, however,
remove one practical motivation cited for investigating the boundary: the
router was too large to run on standard hardware, making the full pipeline
fragile. With the router tractable, the placer boundary's KEEP verdict stands
on its own feature-coverage and solver-parity merits, as documented in the
spike's §3.

**Does not defer or reopen the spike.** No amendment to the Wave-4 plan's
Phase 1 section is needed.

---

## Sources

- OOM diagnosis: `docs/evidence/2026-08-07-router-oom-diagnosis.md`
  (attribution, Sinz blowup, 42M/78M CNF breakdown, recommended mitigation).
- Stage 3 model and rewrite: `docs/evidence/2026-07-27-stage3-model-and-rewrite.md`
  (Q2 root cause, ranked recommendation #2 — geographic pruning).
- First route and profile: `docs/evidence/2026-07-27-first-route-and-profile.md`
  (~7 GB / ~1.7 min baseline).
- Router determinism: `docs/evidence/2026-07-27-router-determinism.md`
  (determinism protocol, byte-identical proof, completion rate).
- Ortools CP-SAT spike: `docs/evidence/2026-08-01-ortools-cpsat-spike.md`
  (KEEP verdict, feature enumeration, acceptance criteria).
- Wave-4 migration plan: `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`
  (Phase 1 ortools boundary spike, KEEP contract, blocker correction).
- Physics verification methodology: `docs/physics-verification-methodology.md`
  (R24 discipline, conservative-bound proofs, BMC-exhaustive validation).
- Router encoding: `packages/temper-rust-router-core/src/encoding.rs`
  (Sinz sequential counter, `encode_at_most_k`).
- Router entry point: `packages/temper-rust-router/src/lib.rs`
  (`solve_topology_rust`, CNF encode → solve → extract pipeline).
- Constraint model builder: `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py`
  (`_create_per_net_channel_vars`, `_create_capacity_constraints`,
  `_apply_pcl_constraints` with pin-edge geometry).
- Sinz reference: Sinz, C. (2005). "Towards an Optimal CNF Encoding of
  Boolean Cardinality Constraints." CP 2005.
