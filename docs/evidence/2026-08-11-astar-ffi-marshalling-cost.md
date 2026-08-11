<!-- provenance: commit=c23f67cf6067bfdd523cfa6868c554a3eefe4bb8 (== origin/main at task start, confirmed via scripts/assert-base.sh), branch docs/astar-ffi-marshalling-cost, dirty=false for pcb/temper.kicad_pcb (read-only: parsed for board geometry, never written) -->

# A* FFI marshalling cost: how much of A* wall-clock is moving bytes, not searching

**Date:** 2026-08-11
**Task:** measurement only, no FFI restructuring. Quantify the cost of the
validity-tensor/congestion/thermal serialization that happens on every
`_astar_search_rust_kernel` call in
`packages/temper-placer/src/temper_placer/router_v6/astar_core_rust.py`,
and size (without implementing) a fix.

## Headline

**On this board's real production routing grid, marshalling — not
searching — is the majority of A\* wall-clock, and it gets worse the
shorter the net segment.** Measured directly against the real occupancy
grid built from `pcb/temper.kicad_pcb` (2,380 × 1,560 cells, see §1), a
representative individual `astar_kernel_3d_py` call spends:

| net-segment length | marshalling share of that call's wall-clock |
|---|---|
| 2–8 mm (typical short hop) | **86.1%** |
| 8–25 mm (typical medium hop) | **84.9%** |
| 25–90 mm (long cross-board route) | **58.1%** |
| weighted mean, 24 real trials | **72.0%** |

The reason is structural, not incidental: `build_neighbor_validity_tensor_2d`
does an O(rows × cols × 8) numpy scan of the **entire** grid every call
(≈30 ms, flat, regardless of how far apart start/goal are), while the
actual Rust search cost scales with the number of cells the search
*expands*, which is roughly proportional to path length. On a dense board
with mostly short net segments, the flat per-call marshalling tax
dominates almost every single invocation. Full breakdown, byte counts,
call-count extrapolation, redundancy findings, and a costed fix are below.

## 0. Method and provenance

Base commit `c23f67cf6` (== `origin/main`, verified via
`scripts/assert-base.sh origin/main`). All measurements below were taken
by running real code paths against real inputs — no numbers are estimated
or reused from the task prompt. Two inputs were used, each read-only:

- **`pcb/temper.kicad_pcb`** (the actual Temper board, 152 mm × 234 mm, 4
  layer stackup, 110 nets, 169 components) — used to get the *real*
  production grid dimensions and a *real* occupancy pattern for
  representative-call profiling (§1–§2). Never modified; only parsed and
  run through Stage 2 (channel analysis), which does not touch the file
  on disk.
- **`Piantor_Right`** test fixture (33-net, 2-layer digital keyboard PCB,
  `packages/temper-placer/tests/fixtures/external/.cache/piantor_right/piantor_right_unrouted.kicad_pcb`)
  — used for a full, bounded, real end-to-end route (§3) to get actual A*
  invocation counts, using the pipeline's own already-shipped
  `RouteProfileStats` timers rather than a fresh full route of the much
  larger/more expensive `temper.kicad_pcb` (which the task explicitly
  warned against reproducing in full — see "Cautions").

All scripts run via `uv run --no-sync python3` with
`LD_LIBRARY_PATH=/home/bennet/miniconda3/lib`,
`PYTHONPATH=<repo>/packages/temper-placer/src`, against the already-built
`temper_rust_router` extension in the main checkout's synced `.venv` (no
rebuild performed, nothing installed/synced). No file under `pcb/`,
`packages/temper-placer/configs/netclass_rules.yaml`,
`tools/wasm/wasm_tier_topology.json`, `.github/workflows/*`, or
`neighbor_validity.py`/`temper-geometry` was edited.

## 1. Real grid dimensions (measured, not estimated)

`packages/temper-placer/src/temper_placer/router_v6/occupancy_grid.py`'s
`build_occupancy_grid()` is the function that actually produces the grids
A* runs against in production (via `OccupancyGridStage`, Stage 2.5 of the
real pipeline `RouterV6Pipeline` — confirmed by tracing
`route_pcb` → `V6RouterAdapter.route()` → `RouterV6Pipeline.run()` →
`_run_stage2()` → `Stage2Orchestrator` → `OccupancyGridStage.run()`).
Its defaults are `cell_size=0.1` mm, `margin=2.0` mm — not overridden
anywhere in the production call chain.

(Note: a *second*, separate grid-building path exists —
`GridPrepStage` in `grid_prep_stage.py`, hard-coding `width_cells =
height_cells = 2000` regardless of board size — but it belongs to
`Stage4Orchestrator`'s standalone micro-pipeline, which is not on the
`route_pcb`/`RouterV6Pipeline` production path exercised by `make route`.
It is not used for this measurement; flagged here only so it isn't
confused with the real numbers below.)

Running `RouterV6Pipeline._run_stage2()` directly against
`pcb/temper.kicad_pcb` (parse + channel analysis + occupancy grid build;
no A* yet — 77 s wall, dominated by channel/EDT analysis, not grid
construction) gives the **real** per-layer grid for this board:

```
layer=F.Cu   width_cells=1560 height_cells=2380 cell_size=0.1  origin=(18.0, 18.0)
layer=B.Cu   width_cells=1560 height_cells=2380 cell_size=0.1
layer=In1.Cu width_cells=1560 height_cells=2380 cell_size=0.1  (plane, not routed)
layer=In2.Cu width_cells=1560 height_cells=2380 cell_size=0.1  (plane, not routed)
```

1,560 × 2,380 = **3,712,800 cells** per layer. F.Cu is 23.3% free
(866,432 free cells — dense board, mostly occupied by pads/keepouts/pours),
B.Cu 23.6% free. This matches the task prompt's 0.1 mm-cell-size guess
almost exactly; the ~230 mm × 380 mm cell-grid extent (board is
152 mm × 234 mm + 2 mm margin each side, rounded up) is measured, not
assumed.

## 2. Byte sizes per A* call, and what actually copies

For this board's real grid (rows=2380, cols=1560):

| payload | shape | dtype | bytes | notes |
|---|---|---|---|---|
| validity tensor | (2380, 1560, 8) | bool (1 B) | **29,702,400 (29.7 MB)** | rebuilt from scratch every call, no cache |
| congestion field | (2380, 1560) | float32 | 14,851,200 (14.9 MB) | **not used** by the default production route (measured 0 bytes in §3) |
| thermal field | (2380, 1560) | float32 | 14,851,200 (14.9 MB) | same — 0 bytes by default |
| raw occupancy grid (`grid.grid`, for comparison) | (2380, 1560) | int8 (1 B) | 3,712,800 (3.7 MB) | this is what `mark_path_blocked` already mutates zero-copy — 8× smaller than the validity tensor |

The validity-tensor path actually copies the *same* ~29.7 MB payload
**four times** per call, not once:
1. `build_neighbor_validity_tensor_2d` allocates a new `(rows,cols,8)`
   `bool_` array (29.7 MB).
2. `.astype(np.uint8)` (`astar_core_rust.py:120`) allocates a second,
   distinct 29.7 MB array (bool→uint8 is not a no-op view).
3. `.tobytes()` (`astar_core_rust.py:138`) copies that array's buffer
   into a new Python `bytes` object (29.7 MB).
4. On the Rust side, `astar_kernel_3d_py`'s signature takes
   `validity_bytes: Vec<u8>` (`packages/temper-rust-router/src/lib.rs:464`)
   — pyo3 extracting a `Vec<u8>` from a `PyBytes` **copies** the buffer
   into a new Rust-owned allocation, a fourth copy.

Contrast with the write direction the task points at:
`mark_path_rect_into_grid_py` (`packages/temper-geometry/src/occupancy_raster.rs:644-664`)
takes `grid: PyBuffer<i8>` — a zero-copy buffer-protocol binding directly
onto `OccupancyGrid.grid`'s numpy memory, mutated in place, no
serialization, no copy, ever. The read side (A*) is the asymmetric,
expensive direction; the write side already does this correctly.

## 3. Profiling a representative A* call (real grid, real occupancy)

Ran `build_neighbor_validity_tensor_2d` → `astype/reshape/ascontiguousarray`
→ `tobytes()` → `astar_kernel_3d_py` → decode, each individually timed,
against the real F.Cu grid from §1, for 24 (start, goal) pairs on real
free cells, grouped into three distance bands representative of
short/medium/long net segments on this board:

```
      band   n   dist  path    iters  build_ms astype_ms tobytes_ms kernel_ms  total_ms marshal%
     20-80   8     58   108     2646     31.78      4.47       3.55      6.42     46.28    86.1%
    80-250   8    161   166    10955     29.58      3.91       2.97      6.49     43.03    84.9%
   250-900   8    536   241   290921     30.08      4.10       2.90     31.17     68.34    58.1%

OVERALL n=24: marshal=908.3ms kernel=352.7ms total=1261.2ms marshal_frac=72.0%
```

(`dist`/`path`/`iters` are in cells; 1 cell = 0.1 mm, so bands are
≈2–8 mm, ≈8–25 mm, ≈25–90 mm.) `build_neighbor_validity_tensor_2d` alone
is a near-constant ~30 ms regardless of how hard the search is — it's an
O(grid size) cost, not an O(search) cost — so it's the dominant term
whenever the search itself is cheap (short/medium hops: 2,600–11,000
iterations, 6.4 ms). Only the longest band (536-cell / ~54 mm hops,
290,921 iterations) pushes the actual Rust search above the fixed
marshalling floor.

`astype`+`tobytes` add another consistent ~7 ms/call on top of the ~30 ms
build; `decode` is negligible (<0.1 ms). This matches the module's own
existing instrumentation: `astar_core_rust.py`'s `t0_rust` timer wraps
only the kernel call; everything measured above as "build/astype/tobytes"
happens *before* that timer starts and is therefore invisible to
`RouteProfileStats.rust_time_ms` — it only shows up in the gap between
`astar_total_ms` and `rust_time_ms` (confirmed directly in §4).

## 4. Counting the calls (real, bounded, full route)

Running the real `temper.kicad_pcb` board through Stage 3 (SAT) + Stage 4
(A*) end-to-end was avoided per the task's explicit caution against
repeating "a previous spike [that] burned its whole budget on an
expensive reproduction" — Stage 2 alone already took 77 s on this board.
Instead, `Piantor_Right` (33 nets, small enough to route completely) was
run **fully**, end-to-end, through the real `RouterV6Pipeline`, with a
call-counting wrapper installed around `astar_core_rust._astar_search_rust_kernel`
(a runtime monkeypatch in the measurement script — no source file edited)
and using the pipeline's own already-shipped `RouteProfileStats`:

```
board=Piantor_Right nets=33  wall_time=81.6s
A* rust-kernel call_count = 56          (≈1.7 calls / net)
grid sizes seen = {(939,1429) fine, (235,358) coarse}   # confirms coarse+fine 2-call-per-segment pattern
total validity bytes marshalled = 279,168,832 (279.2 MB)
total congestion bytes marshalled = 0        <- confirms congestion/thermal are NOT wired into the default production route
total thermal bytes marshalled    = 0
stats.rust_time_ms    (kernel-call wall time, aggregate)            = 157.5 ms
stats.astar_total_ms  (kernel-call + Python marshalling, aggregate) = 192.2 ms
=> Python-side marshalling (astar_total - rust_time)                = 34.8 ms  (18.1% of Rust-backed A* time)
```

Two things worth separating clearly:

- **Within the A* phase**, marshalling is a real, structural cost (§3:
  58–86% per call on the *bigger* temper grid; 18% aggregate on
  Piantor's much smaller grid — consistent with marshalling scaling with
  grid *area* while search cost scales with grid *area* only weakly,
  more with path length. The bigger the grid, the worse the marshalling
  tax, independent of how hard any single search is.)
- **A\* is a rounding error of full-pipeline wall-clock on a small board**:
  192 ms of A* (marshalling + kernel combined) out of an 81.6 s total
  pipeline run for Piantor — i.e. Stage 2 (channel/EDT analysis) and
  Stage 3 (SAT) dominate total wall-clock by roughly 400×. The same is
  true directionally on `temper.kicad_pcb`: Stage 2 alone measured 77 s
  in §1. **This means fixing the A* marshalling cost will not move
  full-pipeline wall-clock much on boards this size** — it matters for
  the A* *phase* specifically, and will matter more as either (a) net
  count/grid size grows, or (b) Stage 2/3 get optimized down and A*
  stops being hidden in their shadow.

### Extrapolating to a full `temper.kicad_pcb` route — EXTRAPOLATION, explicitly labelled

Using Piantor's measured ≈1.7 Rust-A*-calls/net and its observed 1:1
coarse:fine call pairing, scaled to `temper.kicad_pcb`'s 110 nets:

- **≈187 Rust A\* calls** (110 × 1.7) — likely an *undercount*: Piantor is
  a simple 2-terminal-net digital board; `temper.kicad_pcb` is a
  power/mixed board routed with `enable_all_pad_tree=True`, so
  multi-pad nets (GND/power rails with many pads) will add more segments
  than a 2-terminal keyboard net does. Treat 187 as a floor, not a point
  estimate.
- Assuming the same ~1:1 coarse/fine split (≈93.5 of each) and using
  **this board's own directly-measured per-call costs** (§3: fine call
  ≈37 ms marshal on the real 2380×1560 grid; coarse call ≈37ms/16≈2.3 ms
  on the 4×-downsampled ~595×390 grid):
  - fine calls: 93.5 × 37 ms ≈ **3.46 s**
  - coarse calls: 93.5 × 2.3 ms ≈ **0.22 s**
  - **≈3.7 s of pure marshalling for one full board route**, and
    **≈93.5 × 29.7 MB + 93.5 × 1.86 MB ≈ 2.95 GB of validity-tensor bytes
    `.tobytes()`'d** across that one route (before counting the 3 other
    same-size copies identified in §2 — real transient allocation is
    several times that).
  - Rip-up: `_MAX_REROUTE_ATTEMPTS_PER_NET = 2`
    (`_astar_search.py:44`), so `_astar_reconstruct.py`'s reroute loop
    caps at `110 × 2 = 220` additional attempts
    (`max_reroute_attempts`, `_astar_reconstruct.py:497`) — an *upper
    bound*, not a measured figure (actual rip-up count depends on
    congestion this run wasn't taken to). In the worst realistic case
    this roughly doubles the above, i.e. **up to ≈7 s** of marshalling
    for one full route.

## 5. Redundancy: is the tensor ever cached? No.

Grepped every call site
(`astar_core.py:267`, `astar_core_rust.py:116`, `_astar_search.py:218`)
and the function itself (`neighbor_validity.py`) — there is no
`lru_cache`, no memoization, no generation counter, nothing. Every call
without an explicit `neighbor_tensor=` argument rebuilds from scratch.

Concretely wasteful case, confirmed by tracing the mutation site: the
grid is only mutated **once per net**, after that net's full route
succeeds (`grid.mark_path_blocked(...)` at `astar_grid.py:317` /
`terminal_tree_execution.py:215` — both *after* the segment/waypoint loop
completes, not inside it). But `_astar_route` / `_astar_route_multilayer`
call `_segment_search` once per **waypoint pair**
(`_astar_search.py:274-291`, `407-421`) without ever passing a cached
`neighbor_tensor`. So for any net with more than one waypoint (any
`enable_all_pad_tree=True` multi-pad tree — GND/power nets on this board
plausibly have many pads), every segment after the first rebuilds and
re-serializes a validity tensor from a grid that has **not changed at
all** since the previous segment's rebuild in the same loop. This is the
"cheapest possible win" the task asks about: a cache keyed on grid
identity + a mutation counter (bumped only inside
`mark_path_blocked`/`mark_via_blocked`/`unmark_*`) would collapse those
N−1 redundant rebuilds to 1, with **zero Rust changes** — purely a
Python-side cache in `astar_core_rust.py` / `OccupancyGrid`. It would not
help *between* different nets (the grid legitimately changes there), so
its ceiling is bounded by how many multi-segment nets a given board has;
on this board (`enable_all_pad_tree=True`, 110 nets, mixed power/signal)
that's plausibly nontrivial but wasn't directly measured (would require
the full expensive route this task avoided reproducing).

Separately, the coarse-to-fine strategy (`enable_coarse_to_fine=True` by
default in `RouterV6Pipeline`, confirmed unmodified in
`V6RouterAdapter.route()` at `_adapter_core.py:195-203`) intentionally
does 2 Rust A* calls per segment (coarse downsample + corridor-masked
fine) — not redundant by accident, but each of those 2 calls pays its own
full marshalling tax independently; the corridor-masked fine tensor build
in particular still allocates and scans the **entire** full-resolution
grid (`build_neighbor_validity_tensor_2d(grid, corridor_mask=...)` at
`_astar_search.py:218`) even though the corridor mask means only a
narrow band of it is ever reachable.

## 6. Sizing the fix (not implemented, per task instructions)

### Tier 1 — stop pre-materializing and copying the tensor (recommended first move)

The write side already proves the pattern works: `mark_path_rect_into_grid_py`
takes `grid: PyBuffer<i8>` (zero-copy, §2). The read side should do the
same instead of shipping a pre-built, pre-serialized `(rows,cols,8)`
tensor:

- **`packages/temper-rust-router/src/lib.rs`**: change
  `astar_kernel_3d_py`'s validity input from `validity_bytes: Vec<u8>` to
  a `PyBuffer<i8>` (or `PyReadonlyArray2<i8>`) over the raw occupancy
  grid (rows×cols, 1 byte/cell — 8× smaller than the validity tensor),
  and move the 8-directional bounds+occupancy check inline into
  `astar.rs`'s expansion loop — i.e. compute validity on demand per
  expansion instead of pre-computing it for every cell up front. This is
  exactly what the *retired* JIT kernel did before this port (see
  `neighbor_validity.py`'s own module docstring: it exists to replace
  "an inlined bounds + numpy + occupancy check" with "a single bit
  read" — the inlining just needs to move from Python/numba into Rust
  instead of being deleted).
- **`astar_core_rust.py`**: `_astar_search_rust_kernel` drops the
  `build_neighbor_validity_tensor_2d` call, the `astype`/`reshape`/
  `ascontiguousarray`, and the `.tobytes()` entirely; passes `grid.grid`
  (already a contiguous `int8` array, per `OccupancyGrid`) directly.
- **Congestion/thermal**: same treatment — `PyReadonlyArray1<f32>`
  instead of `.tobytes()`'d bytes, in both the Rust signature and the
  Python call site (currently 0 bytes in production per §4, but the
  change is symmetric and cheap to include).
- **Corridor mask** (the one piece of real logic, not just plumbing):
  currently baked into the tensor via numpy `&`-masking before
  serialization (`neighbor_validity.py:93-97`). Needs a second optional
  zero-copy mask array threaded into the kernel and checked inline
  alongside the occupancy check.
- **Re-verification**: the original JIT→Rust port was proven
  bit-identical via a differential suite recorded in
  `packages/temper-rust-router-core/VERIFICATION.md`; the same discipline
  (not a new one) would need to re-run against this change. The harness
  already exists, which bounds this cost — it is not built from scratch.
- **Expected effect**, from §3's real numbers: eliminates the ~30 ms
  `build` step and the ~7 ms `astype+tobytes` step almost entirely
  (replaced by O(1) buffer binding instead of O(grid size) scan+copy),
  which is 84–86% of a short/medium-segment call's wall-clock on this
  board's grid. That's roughly a 3–6× per-call speedup for the majority
  (short/medium) case, and a meaningful chunk even on long segments
  (58% → near-0 marshalling floor, kernel-bound instead).
- **Blast radius**: 2 files change meaningfully (one Rust kernel
  signature + inline logic, one Python call site). Does not touch
  `OccupancyGrid`'s public shape, `mark_path_blocked`, or any of the 7
  other Python modules that read `grid.grid` directly
  (`astar_core.py`, `astar_grid.py`, `_astar_heuristics.py`,
  `_astar_theta_star.py`, `neighbor_validity.py`, `resource_bound.py`,
  plus `astar_core_rust.py` itself) — none of them need to change.

### Tier 2 — fully Rust-resident grid (what the task explicitly asks to size)

Keeping `OccupancyGrid` resident in Rust behind a handle (A* takes a
handle instead of bytes, matching how `mark_path_blocked` already mutates
in place) removes even the Tier-1 zero-copy buffer crossing per call.
This is a substantially bigger, cross-cutting change: the grep above
found **7 other Python modules** reading `grid.grid` directly today
(corridor extraction, congestion tensor construction, resource-bound
capacity analysis, Theta*/heuristics, diagnostics/benchmark code, not
counted exhaustively). A resident-handle design either (a) keeps a
synced Python-side mirror for all of those (defeats the purpose — still
paying a copy, just moved), or (b) ports each of them to operate against
the Rust handle too — a multi-module migration in the same shape as this
repo's own precedent for exactly this kind of shim-then-delete move
(`docs/solutions/architecture-patterns/temper-drc-rust-migration-shim-then-delete-2026-08-03.md`,
the `temper-drc` → Rust migration). No week/day estimate is given here —
the point being sized is scope, not duration: Tier 2 is an
architecture project bounded by "port every `grid.grid` consumer," not a
two-file change. **Recommendation: do Tier 1 first** (isolates almost all
of the measured cost, small and independently testable); revisit Tier 2
only if profiling after Tier 1 shows the remaining buffer-crossing
overhead still matters, or if the concurrent corridor-aware A* spike
(another agent, editing `neighbor_validity.py`/`temper-geometry`) creates
an independent reason to want a resident grid.

## 7. What this doesn't answer

- No number for actual rip-up count on `temper.kicad_pcb` (§4's 220 is a
  cap, not a measurement) — would require the full expensive route this
  task was explicitly told not to reproduce.
- No number for how much of the within-net redundancy (§5) actually
  fires on this specific board — depends on how many of its 110 nets are
  multi-pad trees, which wasn't measured directly.
- Piantor's ≈1.7 calls/net is a real measurement on a *different*
  (smaller, simpler, digital) board, used only to establish the
  coarse+fine call *pattern* and as a floor for the §4 extrapolation —
  not claimed to be `temper.kicad_pcb`'s own ratio.
