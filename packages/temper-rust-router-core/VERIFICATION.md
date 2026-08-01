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
