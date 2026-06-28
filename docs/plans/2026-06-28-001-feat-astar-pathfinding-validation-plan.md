---
title: "A* Pathfinding Mathematical Validation Suite"
date: 2026-06-28
status: active
depth: deep
source: docs/brainstorms/2026-06-28-astar-pathfinding-validation-requirements.md
---

## Summary

Build a four-layer mathematical validation suite for the Router V6 A*
pathfinding core. Deploy: (1) an inductive complexity ladder from 1x1
base cases through real-world PCB boards, (2) metamorphic property-based
tests of 9 MET-MAPF relations via Hypothesis, (3) a trivially-correct
Dijkstra differential oracle paired with every A* test on grids ≤30×30,
and (4) a zero-overhead runtime invariant monitor embedded via context
manager. Together these replace the current "no PBT, no invariant
verification" state with computation-as-truth validation.

---

## Problem Frame

`astar_core.py` (~708 lines, 4 A* variants) has zero property-based
tests and zero algorithmic invariant verification. The existing A* test
suite (`test_astar_pathfinding.py`, `test_astar_perf_regression.py`,
`test_wave4_numba_astar.py`) verifies integration behavior (does
pathfinding complete?), Numba parity, and p95 latency. None verify that
the algorithm is _correct_: that the heuristic is admissible, that
f-costs are monotonic, that rotating a grid preserves path cost, or that
removing an obstacle never increases the optimal path length.

The AtMostK bug demonstrated that golden fixtures reproduce reference
bugs — when both the Python and Numba implementations agree on the same
wrong answer, parity checks pass and golden fixtures encode the bug. No
existing test catches a suboptimal heuristic or a priority-queue
ordering error. The Stage 2 PBT template proved that layered property
testing works in this codebase but has not been applied to the
pathfinding core.

**Actors:**
- **A1. Router developer.** Changes the A* core; needs immediate
  invariant-violation feedback.
- **A2. CI system.** Must gate every PR within the existing ~5-minute
  router-v6 test budget.
- **A3. Placer optimizer.** Consumes path costs as a loss signal; needs
  confidence that cost changes reflect routing quality, not algorithmic
  drift.

---

## Scope Boundaries

### In Scope

- 2D A* variants: `_astar_search`, `_astar_search_theta_star`,
  `_astar_search_lazy_theta_star` — full validation (all 4 layers).
- 3D A* variant: `_astar_search_3d` — metamorphic relations + runtime
  monitor only (no Dijkstra oracle for multi-layer grids).
- Octile distance heuristic: admissibility proof and PBT validation
  (R21, R22).
- All new test infrastructure lives under
  `packages/temper-placer/tests/router_v6/`.
- Dijkstra oracle gated at 30×30 grid upper bound.

### Deferred

- Extending metamorphic testing to Numba JIT'd paths beyond the parity
  checks already in `test_wave4_numba_astar.py`. The Numba backend uses
  flat arrays and a manual heap — metamorphic relations would need
  separate Hypothesis strategies for flat-array grid representations.
- Adversarial counterexample search ("anti-golden property generation").
  Rejected in ideation as research-grade.
- SMT-based invariant verification (Z3). Rejected as Phase-2 depth item.
- Extending the Dijkstra oracle to multi-layer 3D grids with via costs.
- Coverage-guided fuzzing of JAX-compiled A* variants. Requires
  significant JAX instrumentation work.

### Out of Scope (this work's identity)

- Validation of pipeline orchestration (`run_astar_pathfinding`,
  `_astar_route_with_ripup`, `_astar_route_multilayer`). These are
  integration concerns tested by existing files.
- SAT model builder validation (separate requirements document).
- Stage 1 and Stage 4 DRC fence extension.
- Cross-stage conservation laws.
- Any change to `OccupancyGrid` or `neighbor_validity` modules beyond
  what's needed for test grid generation.

---

## Key Decisions

1. **Dijkstra oracle with octile weights, not BFS.** Standard BFS/Lee
   on 8-connected grids optimizes hop count, not octile cost. A*
   optimizes octile cost. The oracle must use Dijkstra with octile edge
   weights (cardinal = 1.0, diagonal = √2) to match A*'s objective
   exactly. The Dijkstra implementation is trivially correct for graphs
   with non-negative edge weights (~40 lines).

2. **Computation-as-truth over golden-fixtures-as-truth.** Dijkstra is
   the canonical minimum-cost path oracle. It is independently
   verifiable, replaces golden fixture trust, and follows from the
   AtMostK postmortem where golden fixtures encoded reference bugs.
   Multi-oracle consensus voting is rejected — one correct oracle is
   sufficient.

3. **Context manager monitor, zero production overhead.** The runtime
   monitor is activated only by wrapping A* calls in
   `with astar_monitor():`. No changes to any A* function signatures.
   Each O(1) invariant check is gated behind an internal flag so
   production routing that does not use the context manager pays zero
   overhead.

4. **Full 3x3 exhaustive at Level 2.** All 2^9 = 512 occupancy grids ×
   all 72 unordered start/goal pairs = 36,864 A* calls, <1 second on
   standard CI hardware. The ≤3-obstacle bound was overly conservative;
   the full space is trivially computable.

5. **MR7 (Subpath Optimality) restricted to Theta\* only.** Standard
   8-connected A* does not guarantee subpath optimality — the returned
   path is a sequence of 8-connected moves, not straight-line shortcut
   segments. Subpath optimality (path[i]..path[j] cost equals
   octile_distance when unobstructed) is a Theta*-only property.

6. **Implementation order.** oracle infra → strategies → inductive
   ladder → metamorphic suite → oracle pairing → runtime monitor →
   variant tests. This order ensures each unit can build on the
   completed infrastructure of the previous one.

7. **Intentional redundancy: ladder gates commits, metamorphic suite
   gates PRs.** The inductive ladder (Levels 0-2) runs on every commit
   (<5 seconds). The metamorphic PBT suite (Level 3) runs on PRs with
   configurable iteration budgets. The overlap is defense-in-depth, not
   duplication — when both layers agree, confidence is multiplicative.

---

## Implementation Units

### U1. Dijkstra Oracle Infrastructure

**Goal:** Implement a reference Dijkstra pathfinder for octile-weighted
2D grids and verify it with smoke tests. The oracle is the
computation-as-truth anchor for the entire validation suite.

**Dependencies:** None (built on pure Python + numpy for grid
representation). No dependency on `astar_core.py` — the oracle must be
independently verifiable.

**Files:**
- `packages/temper-placer/tests/router_v6/astar_oracle_utils.py` *(new)*

**Approach:**
1. Implement `dijkstra_shortest_path(start, goal, grid) -> (path, cost)
   | (None, float('inf'))`. Uses a `heapq`-based priority queue with
   octile edge weights: cardinal moves cost 1.0, diagonal moves cost
   √2 ≈ 1.414. Tracks `g_score` and `came_from` dicts. Returns the
   minimum-octile-cost path and its total cost, or `(None, inf)` when
   unreachable.
2. Grid is a numpy 2D int8 array where 0 = free, 1 = obstacle. Start
   and goal cells that carry the net's own ID (>1) are treated as free
   (matching production convention).
3. Implement `dijkstra_cost_only(start, goal, grid) -> float` as a
   faster variant that stops at the goal and returns only the cost (no
   path reconstruction). Used by the heuristic admissibility checker
   (R21) where only the cost matters.
4. Add `DIJKSTRA_MAX_CELLS = 900` (30×30) constant for gating.
5. Add three smoke tests inline in the same file (not in a separate
   test file):
   - **TS1. Empty 3×3 straight path.** `start=(0,0), goal=(2,0)` on an
     all-free 3×3 grid → cost = 2.0, path length = 3.
   - **TS2. Empty 3×3 diagonal path.** `start=(0,0), goal=(2,2)` on an
     all-free 3×3 grid → cost = 2 × √2 ≈ 2.828, path length = 3.
   - **TS3. Unreachable (wall).** A 3×3 grid with a full column of
     obstacles separating start and goal → returns `(None, inf)`.
   - **TS4. Known optimal against brute force on full 3×3 space.**
     For all 512 grids × all start/goal pairs, verify Dijkstra cost
     matches brute-force enumeration of all 8-connected paths ≤6 hops
     (3×3 longest path is 2 hops). This self-verifies the oracle.

**Verification:** `python -m pytest
packages/temper-placer/tests/router_v6/astar_oracle_utils.py -v` — all
internal smoke tests pass. The brute-force cross-check on 3×3 is the
self-validation gate (R10).

**Hypothesis strategies:** Excluded from U1. The `grids(...)`,
`start_goal_pairs(...)`, `obstacle_perturbations(...)`, and
`grid_translations(...)` strategies live in U2.

---

### U2. A* Property Testing Hypothesis Strategies

**Goal:** Build composable Hypothesis strategies for generating
occupancy grids, start/goal pairs, obstacle perturbations, and grid
translations — following the conventions established in
`dfm_property_strategies.py`. These strategies power the inductive
ladder (U3), metamorphic suite (U4), and oracle pairing (U5).

**Dependencies:** U1 (for `dijkstra_shortest_path` in strategy
validation), `OccupancyGrid` from `occupancy_grid.py`.

**Files:**
- `packages/temper-placer/tests/router_v6/astar_property_strategies.py` *(new)*
  (per Q4 resolution: separate module from oracle utils to keep the
  oracle clean of Hypothesis imports)

**Approach:**
1. `grids(rows, cols, p_obstacle) -> OccupancyGrid` strategy:
   - `@st.composite` decorator.
   - `rows`, `cols`: `st.integers(2, 30)` for oracle-pairing grids;
     `st.integers(2, 100)` for metamorphic-only grids.
   - `p_obstacle`: `st.floats(0.0, 0.6)` for obstacle density. Each
     cell independently drawn from Bernoulli(p_obstacle). Ensures at
     least one free cell exists (if all blocked, retry via
     `assume`).
   - Returns `OccupancyGrid` instance following the constructor
     signature: `OccupancyGrid(layer, grid_array, origin, cell_size,
     width_cells, height_cells)`.
   - Includes a `grid_array` property accessor so strategies can also
     return raw numpy arrays for callers that need them.

2. `start_goal_pairs(grid, same_layer=True) -> (start, goal)` strategy:
   - `@st.composite` decorator.
   - Draws two *distinct* free cells from the grid's free-cell set
     (0-valued cells) via `st.sampled_from(free_cells)`. Ensures
     start ≠ goal via `assume`.
   - Returns a tuple `((sx, sy), (gx, gy))` in grid coordinates.

3. `obstacle_perturbations(grid, mode='add') -> OccupancyGrid` strategy:
   - `@st.composite` decorator.
   - `mode='add'`: selects a free cell (not start/goal) and blocks it
     (sets to 1). Returns the perturbed grid. Ensures at least one free
     cell remains for the start/goal pair.
   - `mode='remove'`: selects a blocked cell and frees it (sets to 0).
     Returns the perturbed grid.
   - `mode='either'`: randomly picks add or remove.
   - The caller provides the start/goal pair to avoid blocking them.

4. `grid_translations(grid, max_shift=None) -> (grid, dx, dy)` strategy:
   - `@st.composite` decorator.
   - Draws `dx`, `dy` such that the translated grid fits within a
     bounded coordinate space (default: (2×width, 2×height) to allow
     shift without clipping).
   - Creates a new larger grid, copies occupancy shifted by `(dx, dy)`.
   - Returns the translated grid and the translation vector.

5. Strategy validation: each strategy includes a one-line docstring
   example of expected behavior (e.g., "generates a |rows|×|cols| grid
   with p_obstacle fraction of blocked cells").

**Verification:** Unit tests in U3 exercise all strategies through the
inductive ladder. Each strategy is also informally validated by running
`strategy.example()` and verifying the output shape/types.

---

### U3. Inductive Complexity Ladder

**Goal:** Implement four deterministic complexity levels (Levels 0-4)
that prove invariants scale up from 1xN base cases through real PCB
boards. Each level inherits invariants from the level below. Structured
failure reports identify which level and which invariant failed.

**Dependencies:** U1 (Dijkstra oracle), U2 (Hypothesis strategies).
A* functions imported from `astar_core.py`:
`_astar_search`, `octile_distance`, `_heuristic`, `OCTILE_DIAG`.

**Files:**
- `packages/temper-placer/tests/router_v6/test_astar_inductive_ladder.py` *(new)*

**Approach:**

**Level 0 — Unit Properties (CI: every commit, `@pytest.mark.l0_unit`):**
1. `test_l0_octile_admissible_1d_horizontal`: On an empty 1×N grid
   (N=1..10), for all start/goal pairs, verify
   `octile_distance(s, g) ≤ true_path_cost` where true path cost is
   `abs(g[1] - s[1])` (Manhattan, since only horizontal moves exist on
   1×N). Edge case: N=1, only one cell — A* returns the trivial path
   with cost 0.
2. `test_l0_octile_admissible_1d_vertical`: Same on N×1 grid.
3. `test_l0_octile_triangle_inequality`: For 1000 random triples
   `(a, b, c)` in coordinate space `[0, 100) × [0, 100)`, verify
   `octile(a, c) ≤ octile(a, b) + octile(b, c)` within 1e-12 epsilon.
   Tests the metric property used by the heuristic.
4. `test_l0_octile_diag_constant`: Verify `OCTILE_DIAG == sqrt(2) - 1`
   within floating-point tolerance (`abs(OCTILE_DIAG - (sqrt(2)-1)) < 1e-15`).

**Level 1 — Exhaustive 2x2 (CI: every commit, `@pytest.mark.l1_exhaustive`):**
1. `test_l1_2x2_exhaustive`: For every 2×2 occupancy configuration
   (2^4 = 16), for every unordered start/goal pair (6 per grid):
   - Run `_astar_search(start, goal, grid)`.
   - Run `dijkstra_shortest_path(start, goal, grid)` from U1.
   - Assert completeness parity: both return a path or both return None.
   - Assert cost optimality: A* cost == Dijkstra cost within 1e-12.
   - Assert path-cells-free: every cell in the A* path is free in the
     grid (MR8).
   - Assert no-redundant-nodes: no consecutive duplicate cells (MR9).
   Total: 16 × 6 = 96 A*+Dijkstra pairs, <0.1 seconds.

**Level 2 — Exhaustive 3x3 (CI: every commit, `@pytest.mark.l2_exhaustive`):**
1. `test_l2_3x3_exhaustive`: For every 3×3 occupancy configuration
   (2^9 = 512), for every unordered start/goal pair (72 per grid):
   - Same four assertions as Level 1: completeness parity, cost
     optimality, path-cells-free, no-redundant-nodes.
   - Total: 512 × 72 = 36,864 A*+Dijkstra pairs, <1 second.
   - **Edge case coverage**: The 3×3 exhaustive space includes:
     - Fully blocked grid (1 config) — all pairs unreachable.
     - Single free cell (9 configs) — no start/goal pairs (need 2
       distinct cells), A* returns None for all.
     - "Maze" configurations (e.g., a winding corridor) — tests that
       suboptimal expansions (node re-expansion) don't occur.
     - Diagonal-only connectivity (corners connected only by diagonal)
       — tests diagonal cost correctness.

**Level 3 — PBT on Arbitrary Grids (CI: PR only, `@pytest.mark.l3_pbt`):**
1. `test_l3_pbt_octile_admissible`: On 1000 Hypothesis-generated empty
   grids (size 2..100), verify `octile_distance(s, g)` never exceeds
   `dijkstra_cost_only(s, g, empty_grid)` (Dijkstra on empty grid).
   This is R21 — heuristic admissibility proof-by-PBT.
2. `test_l3_pbt_completeness_parity`: On 200 Hypothesis-generated
   random grids (size 2..30, obstacle density 0.0–0.6), verify
   completeness parity (A* finds path iff Dijkstra does) via U5 pairing.
3. `test_l3_pbt_cost_optimality`: Same 200 grids, verify cost
   optimality via U5 pairing.
4. `test_l3_pbt_path_cells_free`: Verify MR8 on the 200 grids.
5. `test_l3_pbt_no_redundant_nodes`: Verify MR9 on the 200 grids.

**Level 4 — Real-World Regression (CI: PR only, `@pytest.mark.l4_regression`):**
1. `test_l4_regression_boards`: On the existing test board corpus
   (same boards used by `test_astar_perf_regression.py`), run A* on
   all nets and verify:
   - No path contains an obstacle cell (MR8 on real geometry).
   - No path has infinite loops (path length ≤ grid cell count).
   - If Level 4 fails while Levels 0-3 pass: the test harness reports
     which invariant survived sampling but failed on real geometry.
   - If no corpus boards are available, `pytest.skip` with a message
     (following the pattern in `test_astar_perf_regression.py`).
2. Existing integration tests in `test_astar_pathfinding.py` are
   decorated with `@pytest.mark.l4_regression` (R17) — no assertion
   changes.

**Failure report structure (R2):**
```python
class LadderFailure:
    level: int          # 0..4
    invariant: str      # e.g., "completeness_parity"
    grid_shape: tuple   # (rows, cols)
    start: tuple
    goal: tuple
    expected: Any
    actual: Any
    levels_passed: list[int]  # levels that passed before this failure
```

**Verification:**
- `pytest -m l0_unit`: ~50ms, 4 tests pass.
- `pytest -m "l1_exhaustive or l2_exhaustive"`: <1s, 2 tests pass with
  exhaustive enumeration.
- `pytest -m l3_pbt --hypothesis-max-examples=20`: fast smoke test to
  verify strategies work; full 200-example run in CI.
- `pytest -m l4_regression`: skips if no board corpus, passes if boards
  available with consistent results.

---

### U4. Metamorphic PBT Suite

**Goal:** Implement all 9 metamorphic relation tests (MR1-MR9) as
standalone Hypothesis `@given`-based property tests. Each relation is
tested exhaustively on 3×3/4×4 grids and via random sampling (≥200
examples) on grids up to 100×100. Tests live in a dedicated file.

**Dependencies:** U1 (Dijkstra oracle for MR6 — empty-grid optimality),
U2 (grid/start_goal/perturbation/translation strategies), U3 (inductive
ladder must pass first — Levels 0-2 are the base-case proof that these
relations hold on small grids).

**Files:**
- `packages/temper-placer/tests/router_v6/test_astar_metamorphic_pbt.py` *(new)*

**Approach:**

Each MR is a standalone `@given`-decorated function with
`@settings(max_examples=..., deadline=2000)`.

**MR1 — Rotation Invariance:**
```
@given(grid=grids(3, 20, p_obstacle=0.3), rotation=st.sampled_from([90, 180, 270]))
@settings(max_examples=200)
def test_mr1_rotation_invariance(grid, rotation):
    # Rotate grid and start/goal by `rotation` degrees
    # Assert cost(rotated) == cost(original) within 1e-12 for standard A*
    # Assert cost(rotated) within 1% for Theta* variants (Bresenham tie-breaking Q2)
    # Assert inverse-rotated path cells lie on free cells in original grid
```
Edge cases: rotation of an empty grid (cost remains octile distance);
rotation of a fully-blocked grid (both return None).

**MR2 — Symmetry (Swap Start/Goal):**
```
@given(grid=grids(2, 30, p_obstacle=0.3), pair=start_goal_pairs(grid))
@settings(max_examples=200)
def test_mr2_symmetry(grid, pair):
    start, goal = pair
    # Assert cost(start→goal) == cost(goal→start) within 1e-12
    # For Theta*: assert same cost, paths may differ
```
Edge case: start and goal are the same cell (both costs = 0, path =
[start]).

**MR3 — Obstacle Monotonicity (Addition):**
```
@given(grid=grids(2, 30, p_obstacle=0.15), pair=start_goal_pairs(grid),
       perturbed=obstacle_perturbations(grid, start, goal, mode='add'))
@settings(max_examples=200)
def test_mr3_obstacle_addition(grid, pair, perturbed):
    # original_cost = A*(start, goal, grid)
    # new_cost = A*(start, goal, perturbed)
    # If original was unreachable, no assertion
    # If original was reachable: new_cost >= original_cost or new is None
```
Edge case: add obstacle on the only free path → new becomes None;
add obstacle off-path → cost unchanged.

**MR4 — Obstacle Monotonicity (Removal):**
```
@given(grid=grids(2, 30, p_obstacle=0.15), pair=start_goal_pairs(grid),
       perturbed=obstacle_perturbations(grid, start, goal, mode='remove'))
@settings(max_examples=200)
def test_mr4_obstacle_removal(grid, pair, perturbed):
    # If original was reachable: new_cost <= original_cost
    # If original was unreachable: new may become reachable
```
Edge case: remove obstacle making a previously unreachable pair
reachable; remove an obstacle not on any path → cost unchanged (≤
not <).

**MR5 — Edge-Weight Scaling:**
```
@given(grid=grids(2, 30, p_obstacle=0.3), pair=start_goal_pairs(grid),
       k=st.floats(0.5, 5.0))
@settings(max_examples=200)
def test_mr5_edge_weight_scaling(grid, pair, k):
    # Scale cell_size by 1/k → effectively scales all edge weights by k
    # Assert cost(scaled_grid) == k * cost(original) within 1e-12
```
This is tested by constructing a grid with scaled cell_size rather than
modifying the A* algorithm. Edge case: k = 0 (invalid — filtered by
float range); k extremely small (0.5) or large (5.0).

**MR6 — Empty-Grid Optimality:**
```
@given(grid=grids(2, 100, p_obstacle=0.0), pair=start_goal_pairs(grid))
@settings(max_examples=200)
def test_mr6_empty_grid_optimality(grid, pair):
    start, goal = pair
    cost = A*(start, goal, grid).cost
    # Assert cost == octile_distance(start, goal) within 1e-12
    # Also assert Dijkstra matches (redundant check: Dijkstra on empty
    #   grid also returns octile_distance)
```
This is the canonical test that catches non-admissible heuristics.
Edge case: start == goal (cost = 0); co-linear start/goal (cost =
abs(dx)); diagonal (cost = max(dx,dy) * sqrt(2)).

**MR7 — Grid Translation Invariance:**
```
@given(grid=grids(2, 20, p_obstacle=0.3), pair=start_goal_pairs(grid),
       translation=grid_translations(grid))
@settings(max_examples=200)
def test_mr7_translation_invariance(grid, pair, translation):
    translated_grid, dx, dy = translation
    t_start = (start[0]+dx, start[1]+dy)
    t_goal = (goal[0]+dx, goal[1]+dy)
    # Assert cost(translated) == cost(original) within 1e-12
    # Assert path cells are shifted by (dx, dy)
```
Edge case: translation that moves grid out of bounds (strategy ensures
bounds); empty grid translation (cost still octile).

**MR8 — Path Cells Free:**
```
@given(grid=grids(2, 100, p_obstacle=0.4), pair=start_goal_pairs(grid))
@settings(max_examples=200)
def test_mr8_path_cells_free(grid, pair):
    path = A*(start, goal, grid)
    if path is not None:
        for cell in path:
            # Start/goal may carry net's own ID (>1) → treated as free
            assert grid[cell] == 0 or grid[cell] == net_id
```
This catches neighbor-validity bypass bugs. Edge case: A* returns an
empty path (should not happen — if reachable, path has ≥1 cell);
A* returns a path through a cell that is occupied by another net (1
and not net_id) → assertion failure.

**MR9 — No Redundant Nodes:**
```
@given(grid=grids(2, 100, p_obstacle=0.4), pair=start_goal_pairs(grid))
@settings(max_examples=200)
def test_mr9_no_redundant_nodes(grid, pair):
    path = A*(start, goal, grid)
    if path is not None:
        for i in range(len(path) - 1):
            assert path[i] != path[i+1], f"Consecutive duplicate at {path[i]}"
        assert len(path) <= grid.width_cells * grid.height_cells
```
Catches infinite loops. Edge case: 1-cell path (start == goal) — loop
doesn't execute; very long path on a large empty grid — should still
be ≤ |grid cells|.

**Exhaustive verification (R5):** Each MR is also parameterized via
`@pytest.mark.parametrize` on the full 3×3 and 4×4 configuration
spaces (4×4 = 2^16 = 65,536 grids — filtered to a representative
subset of 1000 random configs + all 2^16 start/goal pairs for the
empty grid, which is the most structurally varied). These are separate
test functions decorated with `@pytest.mark.l2_exhaustive`.

**Verification:**
- `pytest test_astar_metamorphic_pbt.py -m "not l2_exhaustive" --hypothesis-max-examples=10`: fast
  smoke test.
- `pytest test_astar_metamorphic_pbt.py -m l2_exhaustive`: exhaustive
  3×3 verification of all 9 relations.
- Full CI run: ≥200 Hypothesis iterations per relation,
  deadline=2000ms, all pass.

---

### U5. Oracle Pairing Integration

**Goal:** Ensure every A* test in the inductive ladder (U3) and every
applicable metamorphic test (U4) that operates on grids ≤30×30 is
paired with the Dijkstra oracle. The oracle provides three assertions:
completeness parity, cost optimality, and obstacle monotonicity.

**Dependencies:** U1 (Dijkstra oracle), U3 (inductive ladder), U4
(metamorphic suite). This unit is primarily integration — adding oracle
calls and assertions to existing test functions from U3 and U4.

**Files:**
- `packages/temper-placer/tests/router_v6/test_astar_inductive_ladder.py`
  — add oracle pairing to Levels 1-3.
- `packages/temper-placer/tests/router_v6/test_astar_metamorphic_pbt.py`
  — add oracle pairing to MR6 and to any MR that generates grids ≤30×30.
  (MR1, MR2, MR3, MR4, MR5, MR7, MR8, MR9 all generate grids ≤30×30
  by default.)

**Approach:**
1. Helper function `assert_oracle_parity(a_star_result, dijkstra_result,
   grid_shape)`:
   - **(a) Completeness Parity (R8a):** `(a_star is None) == (dijkstra
     is None)`. If mismatch, include in failure report which algorithm
     found a path and which didn't.
   - **(b) Cost Optimality (R8b):** When both find a path,
     `abs(a_star_cost - dijkstra_cost) < 1e-12` for exact equality
     across all octile edge weights.
   - **(c) Obstacle Monotonicity (R8c):** For the MR3/MR4 test
     contexts, the oracle is also run on the perturbed grid. Assert
     `perturbed_cost >= original_cost` (addition) or
     `perturbed_cost <= original_cost` (removal).

2. Oracle gating (R9): Before calling the oracle, check
   `grid.width_cells * grid.height_cells <= 900` (30×30). If the grid
   exceeds this, the oracle is skipped and a `pytest.skip`-equivalent
   log message is emitted: `"Grid 35x35 exceeds Dijkstra budget (max
   30x30), relying on metamorphic checks."`. For the metamorphic suite,
   MR6 explicitly needs the oracle — the strategy caps at 30×30 for
   MR6 but allows up to 100×100 for MR8/MR9 (which don't need the
   oracle).

3. U3 Level 1 (2×2) and Level 2 (3×3) already pair with the oracle
   directly. U3 Level 3 adds oracle pairing to all 200-sample tests.
   U4 adds oracle pairing to MR1, MR2, MR3, MR4, MR5, MR6, MR7.

4. Historical bug detection (SC3): An intentionally-injected regression
   test is not included (the plan does not ship bugs). Instead, SC3 is
   verified by referencing a historical bug from git history (if one
   exists in the commit log involving suboptimal heuristic or PQ
   ordering) and confirming the oracle would have caught it. If no
   historical bug is found, SC3 is satisfied by confirming the oracle
   detects a manually broken heuristic in a one-off test (not committed).

**Verification:**
- All U3 tests pass with oracle assertions (Levels 1-3).
- All U4 tests that use grids ≤30×30 pass with oracle assertions.
- MR8/MR9 on 100×100 grids do not invoke the oracle but still pass.
- A run with a deliberately-broken `_heuristic` (e.g., returning 0.0
  always) causes oracle cost-optimality failures in Level 2 and Level 3.

---

### U6. Runtime Invariant Monitor

**Goal:** Implement a context-manager-activated monitor that checks four
structural invariants during A* execution. Violations are reported as
`StageDRCFailure` records in test mode and logged at WARNING level in
production mode. Zero overhead when the context manager is not active.

**Dependencies:** `stage_validators.py` (`@register_validator`,
`StageDRCFailure`), `astar_core.py` (monitor reads internal state of
`_astar_search`). U3 (inductive ladder) to validate monitor detection
against known invariants.

**Files:**
- `packages/temper-placer/src/temper_placer/router_v6/astar_monitor.py` *(new)*
- `packages/temper-placer/tests/router_v6/test_astar_runtime_monitor.py` *(new)*

**Approach:**

1. **Monitor module (`astar_monitor.py`):**
   - Module-level flag `_MONITOR_ACTIVE: bool = False`.
   - Context manager `astar_monitor()` sets `_MONITOR_ACTIVE = True` on
     enter, restores on exit. Thread-safe via `threading.local()` for
     future multi-threaded use (current codebase is single-threaded, but
     the pattern is defensive).
   - `@register_validator("AStar")` decorator for the monitor validator
     function `validate_astar_invariants(state) -> list[StageDRCFailure]`.
     (Note: the monitor does not receive a `BoardState` — it reads
     module-level state accumulated during A* execution. The validator
     registration follows the existing pattern for consistency but the
     validator function is invoked separately from `run_validators`.)
   - Actually, re-reading R14: "Monitor violations are reported as
     `StageDRCFailure` records (using the existing
     `@register_validator("AStar")` mechanism)." But the monitor needs
     to report during/after A* execution, not as a stage validator
     after a pipeline stage. The approach is: the monitor accumulates
     failures in a list during A* execution; after the `with
     astar_monitor():` block exits, the `__exit__` method runs the
     registered validator, which reads the accumulated failures and
     either raises (CI mode) or logs (production mode).
   - **Revised design:** The context manager's `__exit__` checks
     `"PYTEST_CURRENT_TEST" in os.environ` to determine CI vs.
     production mode. In CI mode, it runs all registered "AStar"
     validators and asserts empty (via pytest.fail on violations). In
     production mode, it logs at WARNING level.

2. **Invariant checks (R12):**
   - **(a) f-cost Monotonicity.** The monitor wraps `heappop` to track
     the last f-cost popped. On each pop, assert `current_f >= last_f`
     (or `last_f` is None on first pop). Violation: f-cost decreased —
     PQ ordering bug.
   - **(b) Single-Expansion.** Track a `closed_set_monitor` (separate
     from A*'s internal `closed_set` to avoid interference). On each
     node expansion, assert it's not already in the monitor's closed
     set. This check applies only to `_astar_search` (standard A*) —
     Theta* variants legitimately re-expand. Gated by a flag
     `check_single_expansion=False` for Theta* variants.
   - **(c) Cost Lower Bound.** After A* returns a path, the monitor
     recomputes the g-cost from the `came_from` chain and asserts it
     matches `g_score[goal]`. This verifies that the reconstructed path
     cost equals the g-cost at the goal.
   - **(d) Path Completeness.** After A* returns a path, assert:
     `path[0] == start`, `path[-1] == goal`, every consecutive pair
     `(path[i], path[i+1])` satisfies `|Δx| ≤ 1, |Δy| ≤ 1,
     (Δx, Δy) ≠ (0, 0)`.

3. **Monitor implementation strategy:**
   - The monitor does not modify `_astar_search`. It intercepts at
     three points:
     - **Before search:** record `start`, `goal`, grid dimension.
     - **During search:** the monitor hooks into the inner loop by
       monkey-patching `heapq.heappop` and `heapq.heappush` within the
       `with` block. This is the least-invasive approach — no changes
       to `astar_core.py`.
     - Actually, monkey-patching `heapq` globals is fragile. Better
       approach: the context manager enables a flag; `_astar_search`
       checks the flag at key points. But R11 says "no extra parameter
       on the A* functions" and "the context manager is the sole
       activation mechanism." The flag approach is:
       ```python
       # In astar_monitor.py:
       _MONITOR_ACTIVE = False
       
       class astar_monitor:
           def __enter__(self):
               global _MONITOR_ACTIVE
               _MONITOR_ACTIVE = True
               self._state = MonitorState()
               return self
           def __exit__(self, ...):
               _MONITOR_ACTIVE = False
               # validate self._state
       
       # In astar_core.py (ONE LINE ADDITION):
       from temper_placer.router_v6.astar_monitor import _MONITOR_ACTIVE, MonitorState
       # ... inside _astar_search loop, before heappop:
       if _MONITOR_ACTIVE:
           monitor_state.record_pop(current, frontier[0][0] if frontier else None)
       ```
       This violates "no changes to A* function signatures" but the
       requirement says "no extra parameter on the A* functions" — the
       change is _internal_ to `_astar_search`, adding O(1) flag checks
       gated behind a module-level bool. The ~5 lines added to
       `astar_core.py` are acceptable because:
       - They don't change the function signature.
       - Production code without `astar_monitor()` active executes
         `if False:` branches (branch-predictable, effectively zero
         overhead).
       - The requirement is that the monitor "sets an internal flag"
         and the context manager "is the sole activation mechanism".

     - **Specific insertion points in `_astar_search`:**
       - Line 149 (after heappop): record `last_f = current_f`; assert
         `current_f >= last_f` if monitor active.
       - Line 149 (after heappop): add `current` to monitor-closed-set;
         assert not already present if `check_single_expansion`.
       - Line 157 (after path reconstruction, before return): compute
         `recomputed_cost = sum(edge_costs along came_from chain)` and
         assert `recomputed_cost == g_score[goal]`.
       - Line 157 (before return): verify path completeness (start,
         goal, consecutive adjacency).

     - **Floating-point tolerance for invariants:**
       - f-cost monotonicity: `current_f + 1e-12 >= last_f`.
       - Cost lower bound: `abs(recomputed - g_score[goal]) < 1e-12`.
       - Path adjacency: integer check, no tolerance needed.

4. **Test file (`test_astar_runtime_monitor.py`):**
   - `test_monitor_no_violations_empty_grid`: A* on empty 10×10 grid
     with monitor active → no violations. Assert monitor state has
     zero failures.
   - `test_monitor_no_violations_obstacle_grid`: A* on a grid with
     obstacles → path found, no violations.
   - `test_monitor_no_path`: A* with start and goal separated by a wall
     → returns None, monitor records no violations (the search loop
     terminates normally with frontier exhaustion).
   - `test_monitor_detects_broken_heuristic` (SC4): Manually call
     `_astar_search` with a deliberately broken heuristic (e.g.,
     monkey-patch `_heuristic` to return a constant 42.0). With monitor
     active, verify that f-cost monotonicity violations are reported
     (the heuristic is no longer consistent → f-cost may decrease).
   - `test_monitor_detects_cost_lower_bound_mismatch`: Manually
     corrupt the `g_score[goal]` after path construction in a test
     harness to verify the cost-lower-bound check fires.
   - `test_monitor_no_overhead_when_inactive`: Run A* without the
     context manager, verify no monitor-related code executes (timing
     assertion: runtime difference <10% of baseline).
   - `test_monitor_theta_star_no_single_expansion_check`: Theta* with
     monitor active → single-expansion check is NOT applied (Theta*
     legitimately re-expands). Other checks (c, d) still apply.

**Verification:**
- `pytest test_astar_runtime_monitor.py -v` — all tests pass.
- With `astar_monitor()` active, a deliberately broken heuristic causes
  `StageDRCFailure`(s) to be reported (SC4).
- Without `astar_monitor()`, existing A* benchmarks show no p95 latency
  regression (SC6).
- `test_astar_pathfinding.py` unchanged and still passes (SC7).

---

### U7. Variant-Specific Tests

**Goal:** Extend the validation suite to cover the three additional A*
variants with variant-appropriate properties. Theta* variants get
subpath optimality checks; all variants get the applicable metamorphic
relations. No Dijkstra oracle for 3D.

**Dependencies:** U1-U6 must be complete and passing.
`_astar_search_theta_star`, `_astar_search_lazy_theta_star`,
`_astar_search_3d` from `astar_core.py`.

**Files:**
- `packages/temper-placer/tests/router_v6/test_astar_metamorphic_pbt.py` — add Theta*
  and Lazy Theta* variant tests.
- `packages/temper-placer/tests/router_v6/test_astar_runtime_monitor.py` — add
  Theta* monitor tests (no single-expansion check).

**Approach:**

**(a) Theta\* (`_astar_search_theta_star`) — R19a:**

1. **Subpath Optimality (Theta\*-only MR7):**
   ```
   @given(grid=grids(2, 30, p_obstacle=0.3), pair=start_goal_pairs(grid))
   @settings(max_examples=200)
   def test_mr7_thetastar_subpath_optimality(grid, pair):
       path = _astar_search_theta_star(grid, start, goal, net_id=0)
       if path is None: return
       for i in range(len(path)):
           for j in range(i+1, len(path)):
               if _line_of_sight(path[i], path[j], grid, net_id=0):
                   # Path cost between i,j must equal octile_distance
                   expected = octile_distance(path[i], path[j])
                   actual = sum(edge_costs(path[k], path[k+1]) for k in range(i, j))
                   assert abs(actual - expected) < 1e-6
   ```
   Note: exhaustive on 3×3 (all configs); sampling on larger grids.
   The inner O(n²) loop on path length is acceptable for 3×3 (max path
   length ~9) but for larger grids, limit j to i+5 (local subpath
   check).

2. **Theta\* path cells ≤ standard A* path cells:**
   ```
   @given(grid=grids(2, 30, p_obstacle=0.3), pair=start_goal_pairs(grid))
   @settings(max_examples=200)
   def test_thetastar_cell_count_le_astar(grid, pair):
       theta_path = _astar_search_theta_star(grid, start, goal, net_id=0)
       astar_path = _astar_search(start, goal, grid)
       if theta_path and astar_path:
           assert len(theta_path) <= len(astar_path)
   ```
   Theta* produces any-angle shortcuts, so cell count must be ≤ standard
   A*. If standard A* returns None but Theta* returns a path, no
   assertion (Thetax is not "more complete" — both search the same graph;
   if Theta* finds a path, standard A* should also).

3. All MR1-MR9 also apply to Theta* with one exception: MR1 rotation
   tolerance is relaxed to ≤1% for Theta* (Q2 decision — Bresenham
   tie-breaking may produce different shortcut decisions under
   rotation).

**(b) Lazy Theta\* (`_astar_search_lazy_theta_star`) — R19b:**

1. **Reachability parity with Theta\*:**
   ```
   @given(grid=grids(2, 30, p_obstacle=0.3), pair=start_goal_pairs(grid))
   @settings(max_examples=200)
   def test_lazy_thetastar_reachability_parity(grid, pair):
       theta_result = _astar_search_theta_star(grid, start, goal, net_id=0)
       lazy_result = _astar_search_lazy_theta_star(grid, start, goal, net_id=0)
       # If Theta* finds a path, Lazy Theta* must also find a path
       if theta_result is not None:
           assert lazy_result is not None
   ```
   (The reverse is not required — Lazy Theta* may be stricter in some
   edge cases due to delayed LOS checks.)

2. MR8 (path cells free) and MR9 (no redundant nodes) apply to Lazy
   Theta*:
   ```
   @given(grid=grids(2, 100, p_obstacle=0.4), pair=start_goal_pairs(grid))
   @settings(max_examples=200)
   def test_lazy_thetastar_path_cells_free(grid, pair):
       path = _astar_search_lazy_theta_star(grid, start, goal, net_id=0)
       if path is not None:
           for cell in path:
               assert grid.grid[cell[1], cell[0]] == 0
           for i in range(len(path) - 1):
               assert path[i] != path[i+1]
           assert len(path) <= grid.width_cells * grid.height_cells
   ```

**(c) 3D A\* (`_astar_search_3d`) — R19c, R20:**

1. MR3 (obstacle monotonicity across layers): Given a multi-layer grid
   config, add an obstacle on layer A → cost on any path using that
   layer must not decrease.
   ```
   @given(...)  # multi-layer grid strategy (U2 extension for 3D)
   @settings(max_examples=100)
   def test_3d_obstacle_monotonicity(grids, start_node, goal_node):
       # grids: dict of layer_name -> OccupancyGrid
       # Add obstacle on one layer, verify cost does not decrease
   ```

2. MR8 (path cells free on their respective layers): Each cell in a 3D
   path must be free on its declared layer.

3. MR9 (no redundant nodes within a layer): Consecutive cells on the
   same layer must not be identical.

4. Via-removal test: If start and goal are on the same layer, and a 3D
   path uses vias (layer transitions), verify that removing all
   via-related segments and keeping only the same-layer cells produces
   a valid path on the start/goal layer when one exists.

3D tests do **not** use the Dijkstra oracle (R20).

**Verification:**
- Theta* subpath optimality passes on 3×3 exhaustive (all 512
  configurations × all start/goal pairs).
- Lazy Theta* reachability parity with standard Theta* passes on ≥200
  samples.
- 3D MR8 and MR9 pass on ≥100 multi-layer grid samples.
- All variant tests are decorated with `@pytest.mark.l3_pbt`.

---

### U8. CI Integration and Regression Safety

**Goal:** Wire the four-layer validation suite into CI with appropriate
markers, ensure existing tests are not modified (only decorated), and
validate the full suite runs within the ~5 minute CI budget (SC5).

**Dependencies:** U1-U7.

**Files:**
- `packages/temper-placer/tests/router_v6/test_astar_pathfinding.py` — add
  `@pytest.mark.l4_regression` to existing test functions (R17).
- `packages/temper-placer/tests/router_v6/test_wave4_numba_astar.py` — add
  metamorphic checks for Numba paths where applicable (MR2 symmetry, MR8
  path-cells-free, MR9 no-redundant-nodes).
- `packages/temper-placer/tests/router_v6/test_astar_perf_regression.py` — unchanged
  (R17).
- `.github/workflows/python-tests.yml` — add marker-based test selection
  (if not already present).

**Approach:**
1. **Marker registration.** Register custom pytest markers in
   `pyproject.toml` or `conftest.py`:
   ```ini
   [tool.pytest.ini_options]
   markers = [
       "l0_unit: Level 0 - unit properties (CI: every commit)",
       "l1_exhaustive: Level 1 - exhaustive 2x2 (CI: every commit)",
       "l2_exhaustive: Level 2 - exhaustive 3x3 (CI: every commit)",
       "l3_pbt: Level 3 - PBT on arbitrary grids (CI: PR only)",
       "l4_regression: Level 4 - real-world regression (CI: PR only)",
   ]
   ```

2. **CI job structure:**
   - **Commit gate** (every push): `pytest -m "l0_unit or l1_exhaustive
     or l2_exhaustive" tests/router_v6/` — runs Levels 0-2, <5 seconds
     (SC1).
   - **PR gate** (every PR): `pytest -m "l0_unit or l1_exhaustive or
     l2_exhaustive or l3_pbt or l4_regression" tests/router_v6/
     --hypothesis-profile=ci` — runs full suite, <5 minutes (SC5).
     Uses a Hypothesis CI profile with `max_examples=200, deadline=2000`
     (SC2).

3. **Regression safety (SC7):**
   - Run `pytest tests/router_v6/test_astar_pathfinding.py tests/router_v6/test_astar_perf_regression.py tests/router_v6/test_wave4_numba_astar.py`
     and verify all existing tests pass.
   - Run the full test suite: `pytest tests/router_v6/` — no test
     failures.

4. **Timing budget (SC5):**
   - Level 0: ~50ms (4 tests, constant-time).
   - Level 1: ~100ms (96 A* calls).
   - Level 2: <1s (36,864 A* calls).
   - Level 3: ~90s (200 examples × 9 MRs + 200 × Level 3 PBT = ~2,200
     A*+Dijkstra pairs; ~40ms per pair = ~88s).
   - Level 4: ~120s (regression boards; same cost as existing perf
     regression).
   - Monitor tests: ~5s.
   - Variant tests: ~60s (Theta* subpath optimality is O(n²) per path —
     mitigated by sampling limit).
   - **Total:** ~4.5 minutes, within the 5-minute budget.

**Verification:**
- `pytest -m l0_unit tests/router_v6/` exits 0 in <1s.
- `pytest -m "l1_exhaustive or l2_exhaustive" tests/router_v6/` exits 0 in <2s.
- Full suite with `--hypothesis-profile=ci` completes within 5 minutes.
- No existing test file reports new failures (SC7).

---

## Deferred Work

| Item | Reason |
|---|---|
| Numba monitor instrumentation (`_astar_search_numba_kernel`) | Numba uses flat arrays and manual heap; instrumenting is invasive. Monitor Python path first (Q1 resolution). |
| Adversarial counterexample search | Rejected in ideation as research-grade. |
| SMT-based invariant verification (Z3) | Phase-2 depth item; current approach (computation-as-truth) is sufficient. |
| Dijkstra oracle for multi-layer 3D grids | Via costs and layer-transition graphs are a separate optimization domain. |
| Coverage-guided fuzzing of JAX A* variants | Requires JAX instrumentation; not in scope for this plan. |
| Extending metamorphic PBT to Numba kernel | Numba kernel uses flat arrays — needs separate Hypothesis strategies. |
| Production-mode runtime monitor | Test/debug only for V1 (Q3 resolution). Revisit if silent-corruption bug found in production. |

---

## Success Criteria Mapping

| SC | Description | Validated By |
|----|-------------|-------------|
| SC1 | Level 0-2 pass on every commit, <5s | U3 Levels 0-2 + U8 CI commit gate |
| SC2 | All 9 MRs pass ≥200 iterations, 2000ms deadline | U4 + U8 CI PR gate |
| SC3 | Dijkstra oracle detects known/regression bug | U5 + intentionally-broken-heuristic test in U6 |
| SC4 | Monitor detects broken heuristic, reports StageDRCFailure | U6 `test_monitor_detects_broken_heuristic` |
| SC5 | Full suite <5 minutes | U8 timing budget |
| SC6 | Zero overhead when monitor inactive | U6 `test_monitor_no_overhead_when_inactive` + existing perf regression |
| SC7 | No existing test failures | U8 regression safety |

---

## Outstanding Questions (Resolved)

- **Q1. Numba monitor.** Resolved: monitor only the Python path initially.
- **Q2. MR1 rotation on Theta\*.** Resolved: exact equality for standard A*,
  ≤1% tolerance for Theta* variants.
- **Q3. Monitor in production.** Resolved: test/debug only for V1.
- **Q4. Grid-generation strategy file.** Resolved: separate file
  `astar_property_strategies.py` to keep oracle utils clean of Hypothesis imports.
- **Q5 (RESOLVED). Level 2 exhaustive bound.** Full 3x3 exhaustive
  enumeration: 2^9 = 512 grids × 72 pairs = 36,864 calls, <1 second.

---

## Requirements Traceability

| Requirement | Unit(s) | Description |
|-------------|---------|-------------|
| R1 | U3 | Inductive ladder level definitions (L0-L4) |
| R2 | U3 | Structured failure reports |
| R3 | U3 | CI markers (`l0_unit`..`l4_regression`) |
| R4 | U4 | Metamorphic relations MR1-MR9 |
| R5 | U4 | Exhaustive 3×3 + random sampling verification |
| R6 | U2, U4 | Hypothesis strategies + metamorphic test file |
| R7 | U1 | Dijkstra oracle implementation |
| R8 | U5 | Oracle pairing assertions (a,b,c) |
| R9 | U5 | Oracle gating at 30×30 |
| R10 | U1 | Oracle smoke tests |
| R11 | U6 | Context manager activation, no signature changes |
| R12 | U6 | Four invariant checks (a,b,c,d) |
| R13 | U1, U3 | Admissibility validated offline (R21) |
| R14 | U6 | StageDRCFailure reporting |
| R15 | U6 | `with astar_monitor():` context manager |
| R16 | U1, U3, U4, U6 | New test file list |
| R17 | U8 | Existing test file modifications |
| R18 | U2, U4 | PBT conventions (dataclass constructors, Hypothesis settings) |
| R19 | U7 | Variant-specific coverage |
| R20 | U7 | Dijkstra oracle scope (2D only) |
| R21 | U1, U3 | Heuristic admissibility PBT |
| R22 | U3 | Triangle inequality verification |
