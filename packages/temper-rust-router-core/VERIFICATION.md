# A* Kernel (Rust) — Verification by Induction

U5 of the Python→Rust migration roadmap (docs/plans/2026-07-23-003),
porting `astar_core_numba.py::_astar_kernel_3d` and the Bresenham LOS
kernel. The Python reference (Numba-jitted) is the oracle; the Rust
kernel is selected via `TEMPER_ASTAR_BACKEND=rust` (roadmap KTD6) and
remains opt-in, with the Numba kernel as the default and fallback.

## Base Case: 1-Step Path

For start = goal, the kernel pops the start cell, detects `cur ==
goal`, and returns the single-cell path `[start]`. Both the Rust
kernel and the Numba reference produce `[start]`.

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
   mirror the Numba kernel exactly, so every decision sequence is
   identical and the k+1-th extension is the same cell.
3. **No cross-call interaction.** g_score, came_from, and closed are
   per-call arrays; extending the search by one step touches only
   per-cell state, so correctness extends over arbitrary grid sizes and
   iteration budgets.

## Empirical Verification

The differential suite
(`packages/temper-placer/tests/router_v6/test_astar_kernel_rust_differential.py`)
asserts path cell-sequence identity (KTD7) with the Numba kernel on:
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
length (9354.65 mm)** under the Numba and Rust kernels
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
