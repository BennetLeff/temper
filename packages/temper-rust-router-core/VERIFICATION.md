# A* Kernel (Rust) — Verification by Induction

U5 of the Python→Rust migration roadmap (docs/plans/2026-07-23-003),
porting the retired JIT A* kernel (`_astar_kernel_3d`) and the Bresenham
LOS kernel. The JIT-compiled Python kernel was the original oracle; the
Rust kernel was first validated against it via `TEMPER_ASTAR_BACKEND=rust`
(roadmap KTD6). **The JIT fallback was removed on 2026-07-31 (cleanup
C1); the Rust kernel is now the sole A* backend** — see the "JIT
Removal Record" section below for the justification.

## Base Case: 1-Step Path

For start = goal, the kernel pops the start cell, detects `cur ==
goal`, and returns the single-cell path `[start]`. Both the Rust
kernel and the retired JIT reference produce `[start]`.

## Induction Hypothesis: Correctness for Paths of Length k

**Hypothesis:** if the kernel produces a correct minimal-cost path of
length k (cell-sequence equal to the reference), it produces a correct
path of length k+1.

**Proof of inductive step:**

1. **Admissible heuristic.** The octile heuristic
   `max(dx, dy) + (√2 − 1) · min(dx, dy)` never overestimates the
   remaining 8-connected cost: straight steps cost 1.0, diagonal steps
   cost 1.4142135 (f32), and √2 − 1 is the exact excess of a diagonal
   over a straight step. A* therefore expands each cell at most once
   and terminates with an optimal path when one exists.
2. **Identical search state.** The binary heap (parallel f32/i32
   arrays with the same sift-up `<=` break and sift-down strict `<`
   tie order), the neighbor expansion order (E, SE, S, SW, W, NW, N,
   NE), the f32 arithmetic order (octile heuristic in f64 then cast;
   congestion `1 + log(1 + raw)` capped in f32; thermal additive) all
   mirror the retired JIT kernel exactly, so every decision sequence is
   identical and the k+1-th extension is the same cell.
3. **No cross-call interaction.** g_score, came_from, and closed are
   per-call arrays; extending the search by one step touches only
   per-cell state, so correctness extends over arbitrary grid sizes and
   iteration budgets.

## Empirical Verification

The differential suite
(`packages/temper-placer/tests/router_v6/test_astar_kernel_rust_differential.py`)
asserts path cell-sequence identity (KTD7) with the retired JIT kernel on:
open grids; 25 randomized obstacle grids; congestion cost fields;
thermal cost fields; blocked grids (both return None); and 300
randomized Bresenham LOS pairs, including net-id ownership.

PBT properties (`packages/temper-placer/tests/router_v6/test_astar_kernel_pbt.py`):
path endpoints are start/goal; consecutive cells are 8-connected; no
cell is revisited; path length is octilinear-bounded
(`max(|dr|,|dc|) ≤ steps ≤ |dr|+|dc|`); wall-separated grids terminate
with None; a congested blob on the direct route is detoured (when a
detour is geometrically possible).

The full-pipeline dispatch A/B (roadmap Verification Contract) was
executed 2026-07-31 on a 15-net subset of the real board
(`pcb/temper.kicad_pcb`, production invocation pattern from
test_production_board_routing_drc_regression): **identical completion
rate (0.3750), identical unrouted set, and bit-identical total route
length (9354.65 mm)** under the JIT and Rust kernels
(TEMPER_ASTAR_BACKEND unset vs =rust; warm-up run first; wall time
58.7s vs 58.0s). The kernel-level path identity (differential suite)
and the pipeline-level A/B together satisfy the U5 acceptance.

## Float Parity Notes

- The octile heuristic is computed in f64 and cast to f32, matching
  `np.float32(max + DIAG * min)` bit-for-bit.
- Congestion cost uses `1.0f32 + (1.0f32 + raw).ln()` mirroring
  `np.float32(1.0) + np.log(np.float32(1.0) + raw)`; numpy's float32
  `log` and Rust's `f32::ln` both delegate to the platform `logf`,
  verified bit-identical by the differential suite.
- Path identity is asserted as cell-sequence equality (KTD7); the
  differential suite additionally observes bit-identical paths on all
  tested inputs.

## JIT Removal Record (cleanup C1, 2026-07-31)

The JIT A* backend was removed on 2026-07-31 as the marquee cleanup
after the Python→Rust migration program:

- **Justification — the A/B evidence above.** The full-pipeline A/B
  executed 2026-07-31 recorded identical completion rate (0.3750),
  identical unrouted set, and bit-identical total route length
  (9354.65 mm) under the JIT and Rust kernels, and the differential
  suite had already asserted path cell-sequence identity (KTD7) on
  randomized grids.  The JIT fallback was therefore dead weight:
  a second kernel that must stay bit-identical to the Rust kernel,
  with its own JIT cold-start cost and a NumPy-version compatibility
  tail (the JIT runtime pinned ≤ NumPy 2.4).
- **What was removed** (all in `packages/temper-placer/`): the
  `@njit` kernels (`_astar_kernel_3d`, `_heap_push`, `_heap_pop`,
  and the JIT LOS kernel), the lazy-compile/cache machinery
  (`_get_kernel`, `_compile_kernel`, `_get_los_kernel`,
  `_compile_los_kernel`, `_LOS_GRID_CACHE`), the retired `_HAVE_*`
  import probe dance, the retired Python LOS wrapper, the
  `TEMPER_ASTAR_BACKEND` override
  (``_select_astar_backend()`` is now a rust/pure-python probe), the
  retired JIT timing stat (``rust_time_ms`` retained), the
  retired `enable_*_los` plumbing (pipeline flag, ``BoardState`` field,
  theta-star param — Theta*/Lazy Theta* now route LOS through
  ``_line_of_sight_rust`` with the pure-Python ``_line_of_sight`` as
  the only fallback), and the retired JIT runtime dependency.
- **Test surface:** the differential suite's JIT-vs-rust comparison
  tests were retired in favor of rust-path tests (open grid,
  start==goal, randomized obstacles, congestion/thermal fields, blocked
  grids returning None, LOS scenario tests) and the PBT + metamorphic
  suites.  The retired LOS-parity suite was reworked into
  `test_los_rust_correctness.py` (Rust LOS vs the pure-Python
  reference — the stronger property now that the Rust LOS is what
  production Theta* routing runs), and the retired wave-4 JIT A* suite
  was dropped.  The retired suites' parity evidence lives in this
  document and in the A/B record above.

---

## Theta* / Lazy Theta* Search Kernels — Verification by Induction

Wave-4 migration of `router_v6/_astar_theta_star.py` (the A*/Theta*
cluster).  The two search kernels — standard Theta* (LOS at push time)
and Lazy Theta* (LOS at pop time, with the closed-neighbor parent
correction) — plus the Bresenham LOS they share live in `theta_star.rs`.
The module's public entry points delegate to
`temper_rust_router.theta_star_search_py`, falling back to the retained
pure-Python reference when the extension is missing or the runtime
monitor is active (the monitor observes Python-side frontier pops, so an
active monitor keeps the search in Python).

### Base Case: single-cell search (start == goal)

Both variants pop the start cell first, detect `current == goal`, and
return the single-cell path.  The standard reconstruct walks an empty
`came_from` chain (`[start]`); the lazy reconstruct stops at the start
cell without appending it (`[goal] == [start]`).  Both the Rust kernel
and the pure-Python oracle produce `[start]`, pinned by the differential
(`test_differential_start_equals_goal`).

### Induction Hypothesis: correctness for paths of length k

**Hypothesis:** if the kernel produces a valid path of length k
(cell-sequence identical to the Python reference) it produces a valid
path of length k+1.

**Proof of inductive step:**

1. **Identical search state.**  The frontier is a binary min-heap ordered
   by `(f_score, counter)` where `counter` is a strictly increasing
   per-push integer.  Because `counter` is unique, every live heap entry
   has a distinct key and pop order is the sorted key order — identical
   to CPython heapq over the `(f_score, counter, node)` tuples the oracle
   pushes.  The neighbor-expansion order is the oracle's
   `_SAME_LAYER_DELTAS` (E, S, W, N, SE, SW, NW, NE), fixing the `counter`
   sequence and therefore the tie-breaking.  The step cost is
   `sqrt(dx*dx + dy*dy)` over exact integer cell deltas (catalog class
   B7: exact integer operands, exact double conversion below 2^53), so
   `f_score`/`g_score` are bit-identical to the Python floats.
2. **Identical decision points.**  Standard Theta* picks the parent→
   neighbor shortcut exactly when LOS holds; Lazy Theta* defers the LOS
   check to pop time and, on failure, re-derives the parent from the
   closed 8-connected neighbours with the same strict-`<` first-minimum
   rule; the congestion-derivative plateau abort uses the same constants
   (1000/5/3) and the same check position (after the closed-set
   increment, before neighbor expansion).  Every branch maps 1:1 to the
   oracle, so the k+1-th expansion is the same cell.
3. **Same-net and sentinel semantics.**  The traversability predicate
   `cell == 0 || cell == net_id` is replicated exactly, including the
   `net_id == -1` behaviour where the `-1` static-obstacle sentinel is
   treated as own-net (a quirk of the pre-migration code, preserved).
   LOS blocks a cell iff `cell != 0 && cell != net_id` — boolean-identical
   to the reference; the oracle's BB-shortcut fast path is omitted because
   it is boolean-neutral (it only short-circuits an all-zero bounding box,
   where Bresenham also returns True).
4. **No cross-call interaction.**  `came_from`, `g_score`, and `closed`
   are per-call flat arrays; extending the search by one step touches only
   per-cell state, so correctness extends over arbitrary grid sizes and
   iteration budgets.

### Known, recorded divergences (reported, not faked — contract §3)

- **Out-of-range start/goal.**  The Python reference never bounds-checks
  them (callers pre-check via `_segment_search`); a flat-array port cannot
  represent an out-of-range cell, so the Rust kernel returns `None`
  instead.  No production or test caller produces one.
- **Warm-start mapping the START cell.**  A `came_from_init` that maps the
  start cell to a parent absent from `g_score` makes the pre-migration
  Python raise `KeyError` (`g_score[parent]`); the Rust kernel silently
  treats that parent's `g_score` as infinite and takes the A* branch.
  The differential corpus deliberately excludes this malformed warm-start
  (see its `test_differential_came_from_init` docstring); a real warm
  start never contains the start cell.

### Empirical Verification

The differential suite
(`packages/temper-placer/tests/router_v6/test_astar_cluster_rust_differential.py`)
asserts exact path cell-sequence equality between the Rust kernel and the
verbatim pre-migration oracle on: 240 randomized obstacle grids (both
variants, `net_id` ∈ {0, -1, 3}, derivative on/off), exhaustive 2x2 (16
configurations) and 3x3 (512 configurations) occupancy space for both
variants, open/one-row/one-column/1x1 grids, blocked start/goal, a
full-height wall, `-1` sentinel grids, net-ownership strips, small
`max_iter` caps, and warm-start `came_from_init` chains.

PBT properties (`test_astar_cluster_pbt.py`, 9 properties each with a
vacuity guard proving a degenerate kernel violates it): endpoints
in-bounds; path cells free; no consecutive duplicates; every standard-
Theta* path edge has LOS (the property that reaches the Rust LOS kernel
inside the search); Dijkstra completeness parity (derivative off);
lazy/standard reachability parity; the `max_iter=1` determinism; and a
guaranteed-unroutable wall returning `None` for both variants.
Metamorphic relations (4): translation invariance (exact, integer
offsets with a wall border — a free border would change topology and is
deliberately excluded), obstacle-add monotonicity and obstacle-removal
path preservation (exact, derivative off), start/goal swap reachability
symmetry, and re-execution determinism.
