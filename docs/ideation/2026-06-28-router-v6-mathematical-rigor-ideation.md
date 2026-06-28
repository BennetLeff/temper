---
date: 2026-06-28
topic: router-v6-mathematical-rigor
focus: Mathematical induction + property-based testing to validate router-v6 pipeline correctness step by step, building from first principles upward
mode: repo-grounded
---

# Ideation: Router V6 Mathematical Rigor and Property-Based Testing

## Grounding Context

**Codebase context:** Router V6 in `packages/temper-placer/` — Python/JAX, 5-stage pipeline (parse→place→route→DRC), \~65 source files, \~80 test files. Hypothesis PBT already deployed across DFM modules with \~10+ `*_pbt.py` files and shared `dfm_property_strategies.py`. Stage validators exist via `@register_validator` decorator + per-stage DRC fence. Stage 2 was decomposed into 8 micro-stages with per-sub-step PBT — providing a proven template. **Critical gap:** A\* pathfinding core (`astar_core.py`) and SAT model builder have zero or placeholder PBT. No systematic induction-from-simple-to-complex test structure exists. Golden fixture ladder exists per (board, stage) pair — but golden fixtures reproduce reference bugs; they're stability, not correctness.

**Past learnings:** (1) AtMostK fix — 4-layer mathematical validation template: induction proof + exhaustive base-case + constraint audit + PBT cross-validation. (2) DRC fence already auto-discovers invariants — stages 1 and 4 have no fence yet. (3) Stage 2 micro-stage decomposition has proven 6-layer testing pyramid. (4) Golden fixtures alone reproduced a known bug. (5) Test drift prevention: `@dataclass` for constructors, always pair `@settings` with `@given`.

**External context:** MET-MAPF defined 10 metamorphic relations for pathfinding. Contract-based pipeline validation (Design by Contract) maps to stage pre/post-conditions. Oracle strategies: Lee/BFS on small grids, networkx Dijkstra, exhaustive enumeration. FreeRouting uses regression-only testing. PCB-Bench (ICLR 2026) provides correctness criteria taxonomy.

## Topic Axes

1. **Pipeline stage contracts** — Pre/post-condition invariants verified at each stage boundary (parse→place→route→DRC)
2. **Inductive test architecture** — The wiring for composing tests from simple/atomic cases upward to complex realistic boards
3. **Oracle and ground-truth strategies** — Generating known-correct reference results (Lee/BFS, networkx, exhaustive enumeration, golden fixtures)
4. **Algorithm-invariant verification** — Proving/testing individual algorithmic components satisfy their mathematical invariants in isolation
5. **Post-condition audits and runtime checks** — Always-on validation at runtime that catches violations in production, not just tests

## Ranked Ideas

### 1. Inductive Complexity Ladder for A\* Pathfinding

**Axis:** Inductive test architecture
**Stage:** 3-4

Build an explicit inductive proof structure starting from trivially-exhaustive base cases. Each level inherits invariants from the level below. Level 0: unit properties on atomic primitives (distance metric admissibility, heuristic triangle inequality). Level 1: exhaustive verification on all 2x2 grid configurations. Level 2: exhaustive on 3x3 grids. Level 3: PBT with metamorphic relations on arbitrary n x m grids via random sampling. Level 4: regression on real-world PCB boards. When Level 4 fails while Level 3 passes, the invariant was too weak — the structure localizes the proof gap.

**Basis:** `direct:` A\* core has zero PBT. Stage 2's 6-layer pyramid already proved layered verification works in this codebase. MET-MAPF provides the invariant suite to lift across levels.
**Rationale:** The diagnostic power is the value: a failure traces to a specific invariant at a specific complexity level, not a monolithic "this board broke."
**Downsides:** Some invariants only emerge at scale (3x3 may not expose all bugs). Upfront investment before signal appears on real boards.
**Confidence:** 85%
**Complexity:** Medium
**Status:** Explored

### 2. Metamorphic A\* Prover via MET-MAPF Relations

**Axis:** Algorithm-invariant verification
**Stage:** 3-4

Deploy all 10 metamorphic relations from MET-MAPF (ACM TOSEM 2024) as `@given`-based PBT properties on `astar_core.py`. Metamorphic relations don't need a ground-truth oracle — they verify the algorithm behaves consistently under input transformations: rotating the grid 90° preserves path cost, swapping start and goal yields symmetric cost, removing an obstacle never increases the optimal path cost, doubling all edge weights doubles path cost, etc. Each relation is verified exhaustively on 3x3/4x4 grids and via random sampling up to 100x100. The suite is implementation-agnostic — it verifies any future pathfinding replacement.

**Basis:** `external:` MET-MAPF provides 10 peer-reviewed metamorphic relations for pathfinding. `direct:` `astar_core.py` has zero Hypothesis PBT.
**Rationale:** Metamorphic relations test correctness without needing to know the correct output — only that outputs transform predictably under input transformations.
**Downsides:** Not all 10 MRs apply cleanly to obstacle-aware PCB routing. Maintaining 10 property suites requires discipline.
**Confidence:** 90%
**Complexity:** Medium
**Status:** Explored

### 3. Lee/BFS Differential Oracle for A\* Correctness

**Axis:** Oracle and ground-truth strategies
**Stage:** 3-4

The AtMostK bug proved golden fixtures reproduce reference bugs. Replace that trust model: pair every A\* test with a Lee/BFS run on the same grid. BFS is exhaustively correct for uniform-cost grids — when A\* disagrees, A\* is wrong. Three assertions per test: (a) completeness parity (A\* finds a path iff BFS does), (b) path cost matches within floating-point epsilon, (c) monotonicity (adding obstacles never shortens the A\* path). BFS feasible on grids up to \~30x30.

**Basis:** `direct:` Golden fixtures encoded the AtMostK bug in both Python and Rust — stability checks catch nothing when both sides agree on a wrong answer. `external:` Lee's 1961 algorithm is the canonical optimality oracle for uniform-cost grids.
**Rationale:** Replaces "trust golden fixtures" with "trust computation." The oracle is trivial to verify independently.
**Downsides:** BFS is exponential in grid size — only a partial oracle above 30x30. JAX vs. Python reference implementation is a performance tradeoff.
**Confidence:** 85%
**Complexity:** Low
**Status:** Explored

### 4. SAT Solver Inductive Property Lattice

**Axis:** Algorithm-invariant verification
**Stage:** 3

Build SAT model-builder PBT from single clauses upward. Level 1: single-clause CNF — prove solution exists iff the clause is satisfiable. Level 2: multi-clause conjunction — prove all returned solutions satisfy all clauses. Level 3: conflict-driven with learned clauses — prove solution space shrinks monotonically and learned clauses never eliminate valid solutions. Level 4: cross-constraint composition — AtMostK + connectivity + layer constraints, verified against brute-force oracle for small N. Includes a parsimony invariant: variable count must stay within a polynomial bound of (grid\_cells, nets, layers).

**Basis:** `direct:` `sat_model.py:80` (`build_sat_model`) has zero PBT. The AtMostK fix validated the Sinz encoding via the 4-layer template — this generalizes that pattern to all constraint types.
**Rationale:** SAT encoding bugs produce satisfiable models that encode the wrong constraint — the hardest class of bug to detect without formal verification.
**Downsides:** Cross-constraint composition needs a brute-force oracle. Constraint interaction testing is the hardest layer and may need iterative tuning.
**Confidence:** 80%
**Complexity:** Medium
**Status:** Explored

### 5. Primitive-Type Fence Extension to Stages 1 and 4

**Axis:** Pipeline stage contracts
**Stage:** 1, 4

The DRC fence covers stages 2-3-5. Stages 1 (parse entry point) and 4 (route exit point) have no fence — documented gap at `router_v6/pipeline.py:320-324`. Define `Via` and `Trace` as first-class primitive types alongside existing `Component` and `Net`, register them with the fence's `@register_validator` auto-discovery, and unlock invariant-learning for the entry and exit stages.

**Basis:** `direct:` The gap is documented in code (`# NOTE: No Stage 1 fence`, `# NOTE: No Stage 4 fence`). The `@register_validator` + `InvariantSpec` protocol for stages 2-3 is production-hardened.
**Rationale:** Stage 1 garbage-in corrupts everything downstream; Stage 4 undetected errors ship to manufacturing. Closing both gaps with proven infrastructure.
**Downsides:** Via/Trace primitives may need different invariant templates. Adding invariants at Stage 4 may surface existing violations needing fixes before CI gating.
**Confidence:** 90%
**Complexity:** Medium
**Status:** Explored

### 6. Double-Entry Conservation Laws Across Stage Boundaries

**Axis:** Pipeline stage contracts
**Stage:** All

No existing mechanism detects when a pipeline stage silently drops or duplicates an object. Apply double-entry bookkeeping: a `StageLedger` tracks each object type (components, vias, traces, nets, pads) across all 5 stage boundaries. Conservation is defined as isomorphism — some stages legitimately transform objects (route creates vias from net connections), and the ledger records the mapping. On imbalance, it produces a precise audit trail showing which stage lost or duplicated what.

**Basis:** `direct:` No cross-stage data-loss detection exists. `external:` Double-entry bookkeeping has been the gold standard for financial correctness since 15th-century Venice — every transaction is self-verifying.
**Rationale:** Cross-stage data corruption is invisible to per-stage validators. Conservation catches it at the boundary.
**Downsides:** Defining conservation as isomorphism requires a careful mapping function per boundary. Lossy transformations need approximate rather than exact accounting.
**Confidence:** 85%
**Complexity:** Low
**Status:** Explored

### 7. Runtime Monotonicity and Admissibility Monitor for A\*

**Axis:** Post-condition audits and runtime checks
**Stage:** 3-4

Embed an always-on invariant monitor inside the A\* main loop checking four properties per iteration: (a) f-cost monotonicity (priority queue correctness), (b) single-expansion (closed-set correctness), (c) octile heuristic admissibility on empty-grid subregions verified via fast BFS, (d) final path length equals g-cost of goal node at pop time. O(1) cost per iteration. Violations log `StageDRCFailure` records. Wraps into `@register_validator("AStar")` for CI enforcement.

**Basis:** `reasoned:` A\* is called within stages, not at boundaries — its invariants need call-time validation. `direct:` The clearance grid fence demonstrates runtime invariant checks with wall-time budgets work in production.
**Rationale:** A\* bugs are silent — a broken heuristic produces paths that look correct but are suboptimal. Runtime monitors catch corruption at the moment it occurs.
**Downsides:** Admissibility check needs fast BFS on empty-grid subregions. Hard-fail vs. log-and-continue in production needs a policy decision.
**Confidence:** 75%
**Complexity:** Low
**Status:** Explored

### 8. Inductive Ladder: Occupancy Grid → Channel Skeleton Correctness

**Axis:** Inductive test architecture
**Stage:** 2

Stage 2 was decomposed into 8 micro-stages with per-sub-step PBT, but there's no proof that satisfying all sub-step invariants implies the channel skeleton graph is correct. Individual micro-stage tests can all pass while the aggregate output — the graph Stage 3's SAT solver depends on — is broken. Build the induction step: prove that if the occupancy grid is cell-non-negative and correctly inflated, then the extracted channel skeleton has connected subgraphs per net, sufficient channel widths for trace + clearance, and no orphan nodes.

**Basis:** `direct:` Stage 2's 8 micro-stages with per-sub-step PBT exist — the composition proof is the missing piece. `reasoned:` Local properties (per-cell inflation, per-net channel width) don't automatically compose into global properties (graph connectivity, channel sufficiency).
**Rationale:** The composition gap hides real bugs — each micro-stage test passes independently while the skeleton graph is silently incorrect.
**Downsides:** May reveal that existing sub-step invariants are individually sound but jointly insufficient — requiring invariant strengthening.
**Confidence:** 80%
**Complexity:** Medium
**Status:** Explored

### 9. DRC Validator Completeness via Brute-Force Oracle

**Axis:** Oracle and ground-truth strategies
**Stage:** 5

Existing DFM PBT suites verify that reported violations are genuine (`actual < required`). They do not verify the validator finds *all* violations. An optimized spatial-index clearance engine that silently misses 2% of close pairs would pass every existing PBT check. For small boards (\~10 routes), run a brute-force O(n²) pair-check alongside the production validator and assert the violation sets match exactly.

**Basis:** `direct:` `test_clearance_properties.py:61` only checks violation validity, not completeness — no completeness test exists anywhere in `tests/router_v6/`. `clearance_check.py` imports `get_clearance` from `clearance_engine` (an optimized path). `reasoned:` Every spatial-index-based validator has boundary cases where close pairs span index cell boundaries.
**Rationale:** Validator completeness is the meta-correctness question — are the validators themselves correct? A validator that misses violations wastes routing compute on boards that fail endpoint KiCad DRC.
**Downsides:** Pair-check comparison only feasible up to \~10 routes. Requires maintaining brute-force oracle code alongside the optimized validator.
**Confidence:** 85%
**Complexity:** Low
**Status:** Explored

### 10. Inductive DRC Validator Correctness: Empty Board + Monotonic Trace Addition

**Axis:** Inductive test architecture
**Stage:** 5

Structural induction on `RoutingResults` for every DFM validator. Base case: empty board produces zero violations. Inductive step: take a board that passes all validators, add one `CompiledRoute` whose geometry satisfies every design rule, and assert the new board still passes. Tests the single most critical meta-property: "adding compliant geometry never creates false violations." No existing PBT verifies this incrementally with same-layer additions.

**Basis:** `reasoned:` Structural induction from PL verification applied to geometry accumulation in `RoutingResults.compiled_routes`. `direct:` `test_layer_independence_add_disjoint_net` adds a net on a *disjoint* layer — no test adds a *same-layer* compliant net, which is where spatial-index boundary cases create false positives.
**Rationale:** If this property fails, the validator has a false-positive bug that blocks the optimizer from reaching a valid solution.
**Downsides:** Defining "known compliant" geometry strategies that guarantee a route satisfies all design rules is non-trivial — the strategy itself must be verified.
**Confidence:** 75%
**Complexity:** Medium
**Status:** Explored

## Rejection Summary

| #  | Idea                                       | Reason Rejected                                                                                 |
| :- | :----------------------------------------- | :---------------------------------------------------------------------------------------------- |
| —  | Contract Inheritance/Composition Lattices  | Duplicate each other; formal refinement proofs heavyweight for first-pass                       |
| —  | Cross-Stage Invariant Gap Analysis         | Duplicates contract belts + conservation laws; same outcome, weaker mechanism                   |
| —  | SAT Constraint Composability Induction     | Overlaps with #4 (SAT Inductive Property Lattice) which has stronger structure                  |
| —  | Compositional Test Tiling                  | "Composition lemma" requires formal proof unlikely to hold for realistic routing geometries     |
| —  | Test Synthesis from Verified Invariants    | Proving property-preserving transforms is as hard as proving the algorithm correct              |
| —  | Hardware K-Induction for A\*               | K-induction on geometric pathfinding is a research question, not a practical test strategy      |
| —  | Multi-Oracle Consensus Voting              | Three oracles adds complexity without proportionate benefit over simpler Lee-oracle             |
| —  | Exhaustive-Enumeration Oracle variants     | Subsumed by #3 (Lee/BFS oracle) — same ground-truth guarantee, simpler                          |
| —  | Deterministic Replay Oracle (GGPO)         | Requires seeding all non-deterministic sources; less direct than oracle comparison              |
| —  | Coverage-Guided Metamorphic Fuzzing        | Instrumenting JAX-compiled A\* for coverage requires significant tooling work                   |
| —  | Anti-Golden Property Generation            | Adversarial search for counterexamples is research-level; unclear if it finds non-trivial cases |
| —  | Heuristic Admissibility standalone         | Folded into #7 (runtime monitor) which tests admissibility continuously                         |
| —  | SAT Encoding Parsimony standalone          | Folded into #4 (SAT inductive lattice) as the variable-count bound invariant                    |
| —  | Aerospace Traceability Matrix              | Overlaps with existing `TRACEABILITY.md` sentinel + `@req` annotations                          |
| —  | SMT-Based Invariant Verification (Z3)      | Heavyweight; better as Phase-2 depth item after PBT foundation                                  |
| —  | Round-Trip Pipeline Inversion              | Routing has lossy stages — no precise inverse exists                                            |
| —  | Proof-Carrying Pipeline Commit             | Requiring proof skeletons per commit cripples velocity                                          |
| —  | Safety-Certification Trace Matrix          | Already addressed by `TRACEABILITY.md` infrastructure                                           |
| —  | First-Principles Dependency Graph          | Manual DAG maintenance burden; auto-generation from imports is speculative                      |
| —  | Contract Linter for Pipeline Stages        | Static analysis complement to #5 but lower urgency than closing the fence gap                   |
| —  | Runtime Contract Monitor (context manager) | Follows naturally from #5 (fence extension enables contract monitoring)                         |
| —  | Stage 0 Legalization Contracts             | Covered implicitly by #5 (fence extension) and #6 (conservation laws)                           |
| —  | Stage 1 Net Assignment Preservation        | Subsumed by #5 (fence extension) once Via/Trace primitives enable Stage 1 invariants            |
| —  | DRC Validator Pre/Post-Condition Contracts | Follows naturally from #5 and #9 — contract framework is the execution mechanism                |
| —  | Clearance-Creepage Overlap Consistency     | Interesting but narrow; subsumed by #9 (completeness oracle catches all cross-validator gaps)   |
| —  | Validator Report Integrity (runtime)       | Practical but subsumed by #9 — completeness check is the stronger guarantee                     |
