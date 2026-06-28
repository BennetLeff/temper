---
date: 2026-06-28
topic: astar-pathfinding-validation
status: draft
ideation_source: docs/ideation/2026-06-28-router-v6-mathematical-rigor-ideation.md
---

# A* Pathfinding Mathematical Validation

## Summary

Build a systematic mathematical validation suite for the Router V6 A*
pathfinding core. Deploy four layers: (1) an inductive complexity ladder
that proves invariants level-up from 1x1 base cases through real-world
boards, (2) metamorphic property-based tests deploying MET-MAPF's 10
pathfinding relations via Hypothesis, (3) a Dijkstra differential oracle
that pairs every A* test with a trivially-correct weighted-Dijkstra
result, and (4) a runtime invariant monitor embedded in the A* main loop.
Together these replace the current "no PBT" state with
computation-as-truth validation.

## Problem Frame

`astar_core.py` (~708 lines, 4 A* variants) has zero property-based
tests and zero algorithmic invariant verification. The existing A* test
suite (`test_astar_pathfinding.py`, `test_astar_perf_regression.py`,
`test_wave4_numba_astar.py`) verifies integration behavior (does
pathfinding complete on a small grid?), Numba parity (do both backends
agree?), and performance regression (did p95 latency regress?). None of
these verify that the algorithm is _correct_: that the heuristic is
admissible, that expanding a node never decreases its f-cost, that
rotating a grid preserves path cost, or that removing an obstacle never
increases the optimal path length.

The AtMostK bug demonstrated that golden fixtures reproduce reference
bugs — when both the Python and Numba implementations agree on the same
wrong answer, parity checks pass and golden fixtures encode the bug. No
existing test catches a suboptimal heuristic or a priority-queue
ordering error. Stage 2 proved that layered PBT works in this codebase
(micro-stage decomposition + per-sub-step PBT), but that template has
not been applied to the pathfinding core.

The gap is correctness confidence. A* is the most algorithmically
sophisticated component in the pipeline — if it produces suboptimal or
invalid paths, every downstream stage inherits the error. The validation
must move from "it doesn't crash" to "it produces defensible results
with mathematically verifiable invariants."

## Actors

- **A1. Router developer.** Changes the A* core (new heuristic, new
  variant, performance optimization). Needs immediate feedback on
  whether the change broke any invariant.
- **A2. CI system.** Runs validation gates on every PR. Must complete
  within the existing CI latency budget (~5 minutes for the router-v6
  test suite).
- **A3. Placer optimizer.** Consumes A* path costs as a loss signal.
  Needs confidence that cost changes reflect real routing quality, not
  algorithmic drift.

## Requirements

### Layer 1: Inductive Complexity Ladder

- **R1.** Define explicit complexity levels for A* validation with
  inherited invariants:
  - **Level 0 — Unit Properties.** Verify the octile distance heuristic
    is admissible (`octile_distance(a, b) ≤ true_shortest_path(a, b)`)
    on an empty 1xN and Nx1 grid (where true cost is the Manhattan
    distance). Verify the triangle inequality:
    `octile_distance(a, c) ≤ octile_distance(a, b) + octile_distance(b, c)`
    for all triples in a bounded coordinate space. Verify that
    `OCTILE_DIAG = sqrt(2) - 1` is within floating-point tolerance of
    the correct constant.
  - **Level 1 — Exhaustive 2x2.** On every possible 2x2 occupancy
    configuration (2^4 = 16 grids × all start/goal pairs), verify A*
    returns a path whose cost exactly matches the exhaustive shortest
    path computed by enumeration. Assert that no-path cases match the
    reachability analysis (Dijkstra on the same grid).
   - **Level 2 — Exhaustive 3x3.** On all 3x3 occupancy configurations
     (full 2^9 = 512 grids × all 72 start/goal pairs = 36,864 A* calls).
     Verify path cost optimality against the Dijkstra oracle and
     completeness parity.
  - **Level 3 — PBT on Arbitrary Grids.** Hypothesis-generated random
    grids (n×m, 2 ≤ n,m ≤ 100) with controlled obstacle density.
    Verify all metamorphic relations from Layer 2 apply. Validate
    against the Dijkstra oracle where grid size permits (≤30×30).
  - **Level 4 — Real-World Regression.** On the existing corpus of
    PCB test boards, verify pathfinding produces results consistent
    with known-good baselines. When Level 4 fails while Level 3 passes,
    the test harness must report which invariant survived sampling but
    failed on real geometry.

- **R2.** The test harness emits a structured failure report identifying
  which level and which invariant failed. The report must include the
  grid that triggered the failure, the expected vs. actual result, and
  the levels that passed (to localize the proof gap).

- **R3.** Each level has a CI marker (e.g., `@pytest.mark.l0_unit`,
  `@pytest.mark.l1_exhaustive`, `@pytest.mark.l2_exhaustive`,
  `@pytest.mark.l3_pbt`, `@pytest.mark.l4_regression`). Levels 0-2 run
  on every commit (fast: exhaustive on tiny grids). Levels 3-4 run on
  PR only (PBT has configurable iteration budget; regression requires
  test board corpus).

### Layer 2: Metamorphic A* Prover

- **R4.** Deploy metamorphic relation tests for `_astar_search` on
  2D uniform-cost grids. Each relation is a Hypothesis `@given`-based
  property. The relations to implement (from or inspired by MET-MAPF
  TOSEM 2024):

  **MR1 — Rotation Invariance.** Rotating an occupancy grid 90°, 180°,
  or 270° and rotating start/goal identically preserves the path cost
  (within floating-point epsilon). Verify that the rotated path, when
  inverse-rotated, lies on free cells in the original grid.

  **MR2 — Symmetry (Swap Start/Goal).** Swapping start and goal on an
  undirected grid produces a path of equal cost. (Applies to all A*
  variants; Theta* may produce different cell sequences but same cost.)

  **MR3 — Obstacle Monotonicity (Addition).** Adding an obstacle
  (blocking a free cell) never decreases the optimal path cost. If a
  path existed on the original grid, the new path cost must be ≥ the
  original cost, or the path must become unreachable.

  **MR4 — Obstacle Monotonicity (Removal).** Removing an obstacle
  (freeing a blocked cell) never increases the optimal path cost. If
  the original grid was reachable, the new path cost must be ≤ the
  original cost.

  **MR5 — Edge-Weight Scaling.** Multiplying all edge weights by a
  constant factor `k > 0` scales the path cost by exactly `k`. On the
  grid, this is equivalent to scaling the cell size parameter — verify
  that `k × cost(original)` equals `cost(scaled)` within epsilon.

  **MR6 — Empty-Grid Optimality.** On a grid with no obstacles, the
  path cost returned by A* must equal `octile_distance(start, goal)`.
  (Trivially true if the heuristic is admissible and consistent —
  this relation catches cases where it is not.)

  **MR7 — Grid Translation Invariance.** Translating the entire grid
  (occupancy + start + goal) by (Δx, Δy) preserves path cost. The
  returned path cells are shifted by the same delta. Verifies no
  coordinate-system bugs.

  **MR8 — Path Cells Free.** Every cell in the returned path (except
  start and goal, which may carry the net's own ID) must be free (grid
  value 0). Verifies the neighbor validity check is not bypassed.

  **MR9 — No Redundant Nodes.** No two consecutive cells in the
  returned path may be identical. The path length in cells ≤ the grid
  cell count (bounds check against infinite loops).

- **R5.** Each metamorphic relation is tested **exhaustively** on 3x3
  and 4x4 grids (where the full configuration space is enumerable) and
  via **random sampling** (Hypothesis, ≥200 examples per relation) on
  larger grids (up to 100×100).

- **R6.** Metamorphic relation tests live in a dedicated file:
  `packages/temper-placer/tests/router_v6/test_astar_metamorphic_pbt.py`.
  Each relation is a standalone `@given`-decorated test function with
  `@settings` (deadline, max_examples).

  **Hypothesis strategy specifications.** Grid-generation strategies
  follow the conventions established in
  `tests/router_v6/dfm_property_strategies.py`:
  - `grids(...)` — generates `OccupancyGrid` instances of dimension
    `(rows, cols)` with a configurable obstacle density `p_obstacle`
    (float) controlling independent Bernoulli trials per cell.
  - `start_goal_pairs(...)` — generates `(start, goal)` tuples within
    grid bounds, excluding obstacles (start/goal must land on free
    cells, or on cells carrying the net's own ID per production
    convention). Optionally accepts `same_layer: bool` to constrain to
    a single layer.
  - `obstacle_perturbations(...)` — given a base grid, returns a
    strategy that adds or removes obstacles for monotonicity relations
    (MR3, MR4).
  - `grid_translations(...)` — generates valid (Δx, Δy) offsets for
    translation invariance (MR7).

  Strategies are composable via Hypothesis's `@composite` decorator and
  produce dataclass test inputs following the pattern in
  `test_obstacle_map_pbt.py`. Each strategy includes a `.map()`
  variant for converting between occupancy grid representations as
  needed by the Numba parall el test harness.

### Layer 3: Dijkstra Differential Oracle

- **R7.** Implement a reference Dijkstra pathfinder for octile-weighted 2D
  grids (`dijkstra_shortest_path(start, goal, grid) -> path | None`) in
  the test utilities at `tests/router_v6/astar_oracle_utils.py`.
  Dijkstra's algorithm with octile edge weights (cardinal = 1.0,
  diagonal = √2 ≈ 1.414) is guaranteed to return the minimum-octile-cost
  path. The path cost is the sum of octile step costs along the path.

  > **Note:** Standard BFS/Lee is incorrect for 8-connected grids because
  > it optimizes hop count, not octile cost. A* on 8-connected grids
  > optimizes octile cost, and the oracle must match that objective.

- **R8.** Every A* test at Levels 1-3 (inductive ladder) and every
  metamorphic test at Layer 2 that generates grids ≤30×30 pairs its A*
  result with the Dijkstra oracle. Three assertions per pair:
  - **(a) Completeness Parity.** A* finds a path iff Dijkstra does.
  - **(b) Cost Optimality.** A* path cost matches Dijkstra path cost
    (exact equality within floating-point epsilon across all octile edge
    weights). Because both algorithms optimize the same octile-cost
    objective on the same graph, the costs must be identical.
  - **(c) Obstacle Monotonicity.** After randomly adding obstacles to
    the grid, the A* path cost must be ≥ original, and if original was
    reachable, the new cost must be ≥ or path becomes None.

- **R9.** Dijkstra oracle is gated by grid size: for grids >30×30,
  Dijkstra is skipped and the test relies on metamorphic relations and
  heuristic admissibility checks (R21) instead. The oracle utility emits
  a `pytest.skip`-equivalent log message when the grid exceeds the
  Dijkstra budget.

- **R10.** The Dijkstra oracle is validated itself: a smoke test verifies
  that Dijkstra on a known grid returns the known optimal octile cost,
  and that Dijkstra correctly reports None when start and goal are
  separated by a full wall of obstacles.

### Layer 4: Runtime Monotonicity and Admissibility Monitor

- **R11.** The monitor is enabled by wrapping A* calls in
  `with astar_monitor():` which sets an internal flag (e.g., a
  thread-local or module-level variable in the monitor module).
  `_astar_search`'s existing signature is unchanged. The context manager
  is the sole activation mechanism — there is no extra parameter on the
  A* functions. Production code that does not wrap calls in the context
  manager pays zero monitor overhead. Each O(1) invariant check is gated
  behind the flag so production routing is not slowed.

- **R12.** The monitor checks these invariants:
  - **(a) f-cost Monotonicity.** When node `n` is expanded from the
    priority queue, its f-cost (g + h) must be ≥ the f-cost of the
    previously expanded node. This verifies the priority queue ordering
    and that `heappop` returns nodes in non-decreasing f-order.
  - **(b) Single-Expansion.** A node may be popped from the frontier
    at most once. Detect duplicate expansions by tracking the closed
    set and logging (not raising) on re-expansion. (Theta* variants
    legitimately re-expand; this check applies only to `_astar_search`.)
  - **(c) Cost Lower Bound.** The g-cost at goal pop must equal the
    sum of edge costs along the reconstructed path. Recompute the path
    cost from the `came_from` chain and assert it matches `g_score[goal]`.
  - **(d) Path Completeness.** If `_astar_search` returns a path (not
    None), the path must start at `start`, end at `goal`, and every
    consecutive pair of cells must be valid 8-connected neighbors
    (|Δx| ≤ 1, |Δy| ≤ 1, not (0,0)).

- **R13.** Heuristic admissibility is validated offline via R21 (PBT
  property testing), not at runtime. The runtime monitor focuses on
  structural invariants — queue ordering (R12a), single-expansion
  (R12b), cost-lower-bound (R12c), and path completeness (R12d) — that
  are independent of the heuristic and do not require running a second
  search algorithm inside the search loop. Running an empty-grid
  Dijkstra from the current node to the goal as a sampled admissibility
  check is vacuous: on an empty grid, `octile_distance(current, goal)`
  already equals the shortest path cost, so the check reduces to
  `octile_distance ≤ octile_distance`, which is always true.

- **R14.** Monitor violations are reported as `StageDRCFailure` records
  (using the existing `@register_validator("AStar")` mechanism). In CI
  test mode, violations fail the test. In production mode (when the
  `astar_monitor()` context manager is active but not in pytest),
  violations are logged at WARNING level with the grid coordinates and
  expanded node count.

- **R15.** The monitor is invoked via a context manager so it can be
  enabled per-invocation without modifying any A* call site or changing
  any function signatures:
  ```python
  with astar_monitor():
      path = _astar_search(start, goal, grid)
  ```

### Integration and Testing Structure

- **R16.** New test files created:
  - `tests/router_v6/test_astar_inductive_ladder.py` — Levels 0-4
    (R1-R3). Reuses `astar_oracle_utils.py` for Dijkstra pairing.
  - `tests/router_v6/test_astar_metamorphic_pbt.py` — MR1-MR9 (R4-R6).
  - `tests/router_v6/astar_oracle_utils.py` — Dijkstra reference
    implementation and grid-generation helpers (R7, R10).
  - `tests/router_v6/test_astar_runtime_monitor.py` — Monitor
    integration tests (R11-R15).

- **R17.** Existing test files are modified only to add regression
  markers, not to change existing assertions:
  - `test_astar_pathfinding.py` — add `@pytest.mark.l4_regression`
    to existing integration tests.
  - `test_wave4_numba_astar.py` — Numba paths are validated against
    the metamorphic relations where applicable (MR2 symmetry, MR8
    path-cells-free, MR9 no-redundant-nodes).
  - `test_astar_perf_regression.py` — unchanged; performance
    regression is orthogonal to correctness validation.

- **R18.** All PBT tests follow the established convention: pair
  `@settings(max_examples, deadline)` with every `@given`, use dataclass
  constructors for test fixtures, and avoid mutation of shared state.

### Coverage of A* Variants

- **R19.** The inductive ladder (R1, Levels 0-3) and metamorphic
  relations (R4, MR1-MR9) apply to `_astar_search` (standard A*).
  Additional variant-specific requirements:
  - **(a) Theta\* (`_astar_search_theta_star`).** In addition to MR1-MR9,
    verify **Subpath Optimality** (taken from the shared suite as a
    Theta*-only property — standard A* on 8-connected grids cannot
    satisfy subpath optimality because the returned path is not
    necessarily comprised of straight-line shortcut segments): For any
    path produced by Theta\*, every contiguous subpath between cells
    `path[i]` and `path[j]` (j > i) must have cost equal to
    `octile_distance(path[i], path[j])` when the straight-line path
    between them is unobstructed. This verifies line-of-sight
    correctness. Verify that Theta* paths have ≤ cells than standard A*
    paths on the same grid (any-angle paths are shorter or equal in cell
    count).
  - **(b) Lazy Theta\* (`_astar_search_lazy_theta_star`).** Verify that
    Lazy Theta* returns a path on every grid where standard Theta*
    returns a path (not stricter; path cost may differ due to lazy
    evaluation, but reachability must match). Verify MR8 (all path
    cells free) and MR9 (no redundant nodes).
  - **(c) 3D A\* (`_astar_search_3d`).** Apply a reduced set of
    metamorphic relations suitable for multi-layer routing: MR3
    (obstacle monotonicity across layers), MR8 (all path cells free on
    their respective layers), MR9 (no redundant nodes within a layer).
    Verify that removing all vias from a 3D path that starts and ends
    on the same layer produces a valid same-layer path when one exists.

- **R20.** The Dijkstra oracle (R7-R10) applies only to same-layer 2D A*
  variants (`_astar_search`, `_astar_search_theta_star`,
  `_astar_search_lazy_theta_star`). The 3D variant is validated via
  metamorphic relations and the runtime monitor only.

### Heuristic Validation

- **R21.** Prove admissibility of the octile distance heuristic on
  paper (in a docstring or comment) and verify with PBT: on an empty
  2D grid of size up to 100×100, for 1000 random (start, goal) pairs,
  assert that `octile_distance(start, goal)` never exceeds the true
  shortest path cost computed by Dijkstra on an empty grid.

- **R22.** Verify the triangle inequality for `octile_distance` on
  1000 random triples (a, b, c) in a bounded coordinate space.

## Key Decisions

- **Computation-as-truth over golden-fixtures-as-truth.** The Dijkstra
  oracle replaces golden fixture trust. Dijkstra is trivially correct for
  octile-weighted grids and can be independently verified in under 30
  lines of code. This follows from the AtMostK postmortem: golden
  fixtures encode reference bugs.

- **Metamorphic over multi-oracle voting.** Deploying all 9 MET-MAPF
  relations covers more correctness dimensions than comparing A* against
  multiple external oracles. Metamorphic relations don't require knowing
  the correct output — only that outputs transform predictably under
  input transformations. This is especially valuable for grids too large
  for the Dijkstra oracle.

- **O(1) runtime checks, not heavyweight formal verification.** The
  runtime monitor checks structural invariants at the algorithm level
  (priority queue ordering, no duplicate expansion, path completeness)
  rather than attempting SMT-based or k-induction proofs of the full
  pathfinding implementation. Heuristic admissibility is validated
  offline via PBT (R21). This approach was explicitly rejected in the
  ideation session for being research-grade complexity without
  proportionate practical benefit.

- **Inductive ladder over monolithic property suite.** The four-level
  structure localizes failures to a specific invariant at a specific
  complexity level. When Level 4 fails while Level 3 passes, the
  invariant was too weak — the ladder identifies the proof gap rather
  than producing a generic "this board broke" failure.

- **Per-variant coverage, not one-size-fits-all.** The four A* variants
  have different correctness properties. Theta* can produce shorter
  paths (any-angle shortcuts) — cost comparison with standard A* must
  account for this. The 3D variant adds layer-transition moves that
  don't map to 2D metamorphic relations. R19 defines variant-specific
  requirements.

- **Intentional redundancy: ladder gates commits, metamorphic suite
  gates PRs.** The inductive ladder (Levels 0-2) runs on every commit and
  provides fast, deterministic correctness checks. The metamorphic PBT
  suite (Level 3) runs on PRs with configurable iteration budgets. The
  overlap between these layers is intentional: the ladder proves that
  invariants hold for all small grids, while the metamorphic suite probes
  those same invariants on random grids too large to exhaust. When both
  layers agree, confidence is multiplicative. When they disagree, the
  disagreement itself is a signal that the invariant may be dimension-
  dependent. This is not wasteful duplication — it is defense-in-depth
  for the pipeline's most algorithmically sophisticated component.

## Success Criteria

- **SC1.** All Level 0-2 tests pass on every commit (CI gate), with
  a combined runtime <5 seconds.
- **SC2.** All 9 metamorphic relations pass at ≥200 Hypothesis
  iterations each with a 2000ms deadline.
- **SC3.** The Dijkstra oracle is paired with every A* test on grids
  ≤30×30 and detects at least one known historical bug (from git history
  or an intentionally injected regression) when run against the buggy
  version.
- **SC4.** The runtime monitor, when enabled in test mode, detects a
  deliberately broken heuristic (e.g., returning a constant value) and
  reports a `StageDRCFailure`.
- **SC5.** The full validation suite (all layers) completes within the
  existing router-v6 CI test budget (~5 minutes).
- **SC6.** Zero modifications to `astar_core.py`'s production behavior
  when the monitor is not active (no `with astar_monitor()` context).
  The monitor infrastructure adds zero overhead to existing A* benchmarks
  when the context manager is not in use.
- **SC7.** Regression: no existing test in `tests/router_v6/` fails
  due to the new validation infrastructure.

## Scope Boundaries

### In Scope

- 2D A* variants: `_astar_search`, `_astar_search_theta_star`,
  `_astar_search_lazy_theta_star` (full validation with all 4 layers).
- 3D A* variant: `_astar_search_3d` (metamorphic relations + runtime
  monitor; no Dijkstra oracle for multi-layer grids).
- Octile distance heuristic: admissibility proof and PBT validation.
- All test infrastructure at `tests/router_v6/`.

### Deferred for Later

- Extending metamorphic testing to Numba JIT'd paths beyond the parity
  checks already in `test_wave4_numba_astar.py`. The Numba backend uses
  flat arrays and a manual heap — metamorphic relations would need
  separate Hypothesis strategies for flat-array grid representations.
- Adversarial counterexample search ("anti-golden property generation").
  Rejected in ideation as research-grade.
- SMT-based invariant verification (Z3). Rejected in ideation as
  Phase-2 depth item.
- Extending the Dijkstra oracle to multi-layer 3D grids with via costs.
- Coverage-guided fuzzing of JAX-compiled A* variants (requires
  significant JAX instrumentation work, rejected in ideation).

### Outside This Work's Identity

- Validation of the pipeline orchestration (`run_astar_pathfinding`,
  `_astar_route_with_ripup`, `_astar_route_multilayer`). These are
  integration concerns tested by existing files.
- SAT model builder validation (covered by Idea #4 in the ideation doc,
  a separate requirements document).
- Stage 1 and Stage 4 DRC fence extension (covered by Idea #5).
- Cross-stage conservation laws (covered by Idea #6).
- Any change to the `OccupancyGrid` or `neighbor_validity` modules
  beyond what's needed for test grid generation.

## Dependencies / Assumptions

- **Hypothesis ≥ 6.148.7** is already a project dependency and is the
  PBT framework. No new testing dependencies.
- **`@register_validator`** from `stage_validators.py` is
  production-hardened and supports registering "AStar" as a validator
  name (no existing "AStar" validator conflicts).
- **`StageDRCFailure`** dataclass (from `stage_validators.py`) is used
  as the failure-report type for runtime monitor violations.
- **Existing A* API stability.** The signature of `_astar_search(start,
  goal, grid, neighbor_tensor=None)` is stable. The monitor is enabled
  via a context manager that sets an internal flag; no changes to A*
  function signatures are required.
- **Test board corpus** at `packages/temper-placer/tests/router_v6/`
  is available for Level 4 regression tests. If no boards are available,
  Level 4 tests are skipped (following the pattern in
  `test_astar_perf_regression.py`).
- **Dijkstra feasibility boundary.** 30×30 = 900 cells; Dijkstra on an
  octile-weighted 8-connected grid explores O(900) nodes with O(8×900)
  neighbor checks. This is well within CI time budgets per test
  invocation.
- **Octile distance is the heuristic.** The validation assumes no
  alternative heuristic is in use. If a new heuristic is added, the
  admissibility checker (R21) must be extended.
- **Test grids use 0 for free cells and 1 for obstacles.** Start cells
  may carry the net's own ID (matching production convention where
  `cell_value == net_id` is free for that net's pathfinding).

## Outstanding Questions

### Deferred to Planning

- **Q1. Numba monitor.** Should the runtime monitor be implemented in
  the Numba JIT'd kernel (`_astar_search_numba_kernel`) or only in the
  Python `_astar_search` wrapper? The Numba kernel uses flat arrays and
  a manual heap — instrumenting it is more invasive. Proposal: monitor
  only the Python path initially; add Numba monitoring when a Numba-
  specific correctness bug is found.
- **Q2. MR1 rotation on Theta\*.** Rotating a grid 90° and running
  Theta* may produce different line-of-sight shortcut decisions due to
  Bresenham tie-breaking. Should MR1 assert exact cost equality or
  allow a bounded tolerance for Theta*? Proposal: assert exact equality
  for standard A*, ≤1% tolerance for Theta* variants.
- **Q3. Monitor in production.** Should the `astar_monitor()` context
  manager ever be used in production routing, or is this test/debug only?
  The ideation suggests log-and-continue in production. Proposal:
  test/debug only for V1; revisit if a production silent-corruption bug
  is found.
- **Q4. Grid-generation strategy reuse.** Should the grid-generation
  Hypothesis strategies (empty grids, random obstacle placement, etc.)
  live in `astar_oracle_utils.py` or in a shared
  `tests/router_v6/astar_property_strategies.py`? Proposal: start in
  `astar_oracle_utils.py`; extract to shared module if another test
  file needs them.
- **Q5 (RESOLVED). Level 2 exhaustive bound.** Full 3x3 exhaustive
  enumeration is adopted: all 2^9 = 512 grids × all 72 start/goal pairs
  = 36,864 A* calls, <1 second. The ≤3-obstacle bound was overly
  conservative; the full 3x3 space is trivially computable.

## Alternatives Considered

- **Golden fixture ladder only.** Rejected. Golden fixtures encode
  reference bugs (AtMostK postmortem). They verify stability, not
  correctness.
- **Single monolithic PBT suite.** Rejected. The inductive ladder
  structure localizes failures to specific invariants at specific
  complexity levels — a monolithic suite would produce "this board
  broke" without tracing the root cause.
- **Multi-oracle consensus voting (Dijkstra + networkx + brute-force).**
  Rejected in ideation. One oracle (weighted Dijkstra) is sufficient for
  octile-weighted grids; multiple oracles add complexity without
  proportionate benefit. Dijkstra is the canonical minimum-cost path
  oracle for graphs with non-negative edge weights.
- **Standard BFS/Lee as oracle.** Rejected. BFS/Lee on an 8-connected
  grid finds the minimum-hop path, not the minimum-octile-cost path. A*
  optimizes octile cost; using BFS as the oracle would compare different
  objective functions, yielding false-positive "different costs" on
  diagonals. Weighted Dijkstra with octile edge costs matches A*'s
  objective exactly.
- **SMT-based formal verification.** Rejected in ideation as Phase-2
  depth item. SMT on geometric pathfinding with obstacles is a research
  question, not a practical test strategy for V1.
- **Deferred: no A* validation at all.** Rejected. A* is the most
  algorithmically sophisticated component in the pipeline with zero
  invariant verification. The risk of silent corruption is high; the
  Stage 2 PBT template proves the approach works in this codebase.

## Sources / Research

- `packages/temper-placer/src/temper_placer/router_v6/astar_core.py`
  — A* implementation, 708 lines, 4 variants
- `packages/temper-placer/src/temper_placer/router_v6/astar_core_numba.py`
  — Numba JIT'd A* kernel
- `packages/temper-placer/src/temper_placer/router_v6/neighbor_validity.py`
  — pre-baked neighbor-validity tensors
- `packages/temper-placer/src/temper_placer/router_v6/stage_validators.py`
  — `@register_validator` + `StageDRCFailure` framework
- `packages/temper-placer/tests/router_v6/test_astar_pathfinding.py`
  — existing A* integration tests (96 lines, zero PBT)
- `packages/temper-placer/tests/router_v6/test_astar_perf_regression.py`
  — A* p95 latency regression gate
- `packages/temper-placer/tests/router_v6/test_wave4_numba_astar.py`
  — Numba parity tests
- `packages/temper-placer/tests/router_v6/test_obstacle_map_pbt.py`
  — example of Hypothesis PBT in this test suite (established pattern:
  `@given` + `@settings`, dataclass constructors)
- `packages/temper-placer/tests/router_v6/test_sat_solve_pbt.py`
  — example of minimal SAT PBT (placeholder state)
- `docs/ideation/2026-06-28-router-v6-mathematical-rigor-ideation.md`
  — ideation source document, Ideas #1 (Inductive Ladder), #2
  (Metamorphic Prover), #3 (Dijkstra Oracle), #7 (Runtime Monitor)
- `docs/brainstorms/2026-06-25-dfm-property-tests-requirements.md`
  — prior PBT requirements document establishing house style
- MET-MAPF (ACM TOSEM 2024): metamorphic relations for multi-agent
  pathfinding, adapted here for single-agent PCB routing. Subpath
  optimality (original MR7) is restricted to Theta* variants (R19a)
  because standard 8-connected A* does not guarantee subpath optimality.
- Dijkstra, E.W. (1959). "A Note on Two Problems in Connexion with
  Graphs." Numerische Mathematik.
- AtMostK fix postmortem (reference in ideation doc): 4-layer validation
  template — induction proof + exhaustive base-case + constraint audit +
  PBT cross-validation — informing the inductive ladder structure
- Stage 2 micro-stage PBT decomposition: proved layered verification
  works in this codebase, providing the template for the A* validation
  layers
