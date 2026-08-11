<!-- provenance: commit=HEAD at spike start (fanout16/work-1 on origin/main at 1ef19c161, rebased to bcea9d1), branch=fanout16/work-1, dirty=false for pcb/temper.kicad_pcb (never read or written). No crate was built; no production file was edited. -->

# A* same-net Rust wiring spike: what it takes to route `net_id >= 0` through the Rust kernel

**Date:** 2026-08-11
**Task:** determine exactly what it takes to route `net_id >= 0` nets through
the Rust A* kernel (`astar_kernel_3d`) -- the largest ported-but-unwired
instance in the repo. Currently `_astar_search.py:92` special-cases
`net_id >= 0` to the pure-Python `_astar_search` because the Rust kernel
consumes a binary validity tensor that cannot distinguish committed copper
belonging to the net being routed.

**Verdict:** PORTABLE-WITH-SMALL-CHANGE.  The Rust kernel needs ~80 lines
of Rust and ~20 lines of Python to accept the raw occupancy grid directly
(like `line_of_sight_py` already does), inline the same-net predicate, and
apply the same-net cost discount.  This is a single PR, ~100 lines, 4 files.
It simultaneously fixes the FFI marshalling cost (replacing the 29.7 MB
validity tensor with the 3.7 MB raw grid) -- see the companion FFI cost doc.

## 1. F-A1 -- The same-net predicate (VERIFIED)

### 1.1 Exact predicate

Extracted from `astar_core.py:_astar_search`, lines 327-336
(verified by reading the source and running
`tools/measurements/astar_same_net_wiring/extract_same_net_predicate.py`):

```python
if net_id >= 0:
    if not in_bounds(nx, ny, grid.width_cells, grid.height_cells):
        continue                           # BLOCKED
    if corridor_mask is not None and not corridor_mask[ny, nx]:
        continue                           # BLOCKED
    cell_value = grid.grid[ny, nx]         # int8, row-major (height, width)
    if cell_value != 0 and cell_value != net_id:
        continue                           # BLOCKED
    is_same_net = cell_value == net_id     # TRUE iff this cell is our own copper
```

### 1.2 Cell value semantics

The grid is a 2D `int8` numpy array (`grid.grid`). Cell values:
- `0` = FREE (traversable, cost 1.0 or √2)
- `-1` = STATIC OBSTACLE (board outline, keepouts -- treated as `!= 0 && != net_id` → BLOCKED)
- positive integer `N` = cell occupied by net `N` (traversable only when `N == net_id`)

Three marking functions write net_ids onto the grid:
- `mark_path_blocked(path, trace_width, clearance, net_id)` → stores `net_id`
- `mark_via_blocked(x, y, via_diameter, clearance, net_id)` → stores `net_id`
- `mark_segment_blocked(p1, p2, trace_width, clearance, net_id)` → stores `net_id`

**Therefore same-net traversability covers: traces, pads, and vias** -- all
three are represented by the same `net_id` integer on the grid.

### 1.3 Same-net cost discount

When `cell_value == net_id`, the move cost is multiplied by
`_SAME_NET_COST_DISCOUNT = 0.25` (line 349). This incentivizes tree
branches to share copper space, reducing overall footprint for cross-net
routes. Without this discount, the Rust kernel would treat free cells and
same-net cells identically, and multi-pad tree nets could produce
different (likely longer) paths.

## 2. F-A2 -- FFI shape recommendation (OPTION A)

Two options were evaluated:

### Option A: Pass raw grid + net_id (RECOMMENDED)

The Rust kernel receives the raw `(rows*cols)` int8 occupancy grid and a
`net_id` integer. Per expansion, it does an inline bounds check and one
array lookup: `grid[y*w + x]` → check `cell != 0 && cell != net_id`.

- **Payload:** 3.7 MB (2380×1560 int8) -- 8× smaller than the current
  29.7 MB validity tensor.
- **Per-expansion cost:** one array lookup + one integer compare per
  neighbor (8 per expansion). For a typical 2,600-iteration short segment,
  that's ~20,800 extra operations -- negligible against the ~30ms savings
  from not building the tensor.
- **Precedent:** `line_of_sight_py` (lib.rs:500-524) already uses this
  exact pattern: `grid.get(...) → cell != 0 && cell != net_id`. Same code
  shape, same predicate, already proven working and PBT-verified.
- **Same-net discount:** naturally expressed as `if cell == net_id { step *= 0.25 }`.
- **Validity tensor:** becomes optional. When grid is supplied, validity
  is not consulted. This preserves backward compatibility for `net_id < 0`
  callers (coarse-to-fine) that still pass validity tensors.

### Option B: Build same-net-aware validity tensor in Python

Build the validity tensor WITH the same-net predicate baked in
(`dst == 0 OR dst == net_id`), keep kernel unchanged.

- **Payload:** 29.7 MB (unchanged). Still 4× copy (build→astype→tobytes→Rust Vec).
- **Build cost:** still ~30ms per call, now net_id-specific (cannot be
  reused across nets).
- **Cannot encode cost discount:** the tensor is binary. Same-net cells
  get the same cost as free cells, diverging from the Python reference for
  multi-pad tree nets.
- **Verdict:** Inferior. Solves the wiring problem at the expense of the
  marshalling cost (which the companion FFI doc measured at 72-86% of
  A* wall-clock) and loses parity on the cost discount.

**Recommendation: Option A.** It addresses both the same-net wiring and the
FFI marshalling cost in one change. It is the natural companion to the
Tier 1 fix recommended in `docs/evidence/2026-08-11-astar-ffi-marshalling-cost.md` §6.

## 3. F-A3 -- Parity verdict (ANALYZED, pending implementation)

The Rust kernel (`astar_kernel_3d`) should produce **bit-identical** paths
to the Python reference (`_astar_search`) for `net_id >= 0` nets when all
divergence sources are closed, because:

1. **Same heuristic:** Both use octile distance, f64→f32 cast, identical formula.
2. **Same neighbor order:** Both use E, SE, S, SW, W, NW, N, NE.
3. **Same frontier semantics:** Both use binary min-heap. The Rust kernel's
   sift-up `<=` break / sift-down strict `<` tie order mirrors Python's
   `heapq` (verified bit-identical for `net_id < 0` in the existing
   differential suite at `test_astar_kernel_rust_differential.py`).
4. **Same-net predicate:** Integer comparison (`cell != 0 && cell != net_id`)
   -- no float arithmetic, no rounding, deterministic.
5. **Same-net cost discount:** Simple f32 multiply -- no branching that
   would affect tie-breaking order differently. The tie-breaking difference
   between Python and Rust heaps is ALREADY present for `net_id < 0` and has
   been proven to produce identical paths in the existing differential suite.

**Risk:** The cost discount changes the cost landscape. When the discount
makes some cells cost 0.25× instead of 1.0×, cells that were tied on
f_score may no longer be tied, which changes the heap order. This is NOT a
parity bug -- it is a deterministic behaviour change driven by different
costs, and the Rust kernel's heap tie-breaking has been proven to match
Python for the existing test corpus. The test corpus just needs `net_id > 0`
and same-net occupancy patterns added.

**Verification plan:**
1. Extend `test_astar_kernel_rust_differential.py` to include `net_id > 0`
   grids with same-net occupancy patterns (own pads, own traces, other-net
   pads, mixed).
2. Run the existing PBT suite (`test_astar_kernel_pbt.py`) with same-net
   grids.
3. Assert cell-sequence identity (KTD7 convention) on 300+ randomized
   same-net grids.
4. Assert the same-net discount produces shorter paths than no-discount
   on multi-pad tree nets (vacuity guard).

The harness already exists. Scope: ~5 new test functions, ~30 test cases.

## 4. F-A4 -- Is the 3D kernel even needed?

Despite its name, `astar_kernel_3d` is a **2D** A* kernel. The "3d" is a
historical artifact from the now-retired JIT kernel. It searches a single
2D grid with 8-connected neighbors.

The true 3D path is `_astar_search_3d` (astar_core.py:371), which is pure
Python and handles via-insertion with layer transitions. Its call chain:

```
_segment_search → _dispatch_search → [2D A*, primary path]
_astar_route_multilayer:
  1. Try primary grid (2D A*)
  2. If fails: try alternate grid (2D A*)
  3. If both fail: _route_segment_3d → _astar_search_3d (3D, fallback only)
```

**The Rust kernel covers the 2D path, which is the PRIMARY path for ALL net
routing.** The 3D fallback is only exercised when both 2D layers fail, and
even then, `_astar_search_3d` uses `grid.is_free()` which has NO same-net
awareness (it only checks `== 0`). This is a pre-existing limitation in the
3D fallback that is out of scope for this spike -- the 3D fallback is
rarely exercised, and its same-net limitation can be addressed separately
(if at all) since the 2D path handles the vast majority of real routes.

**For wiring `net_id >= 0` through the Rust kernel: only the 2D path needs
attention. The 3D fallback can remain pure Python.**

## 5. Migration spec

### 5.1 Rust changes (2 files)

**`packages/temper-rust-router-core/src/astar.rs`** (~50 lines):

```rust
pub struct AstarInput<'a> {
    // ... existing fields ...
    /// (rows*cols,) int8 occupancy grid. When supplied, the kernel does
    /// inline bounds + occupancy checks per expansion instead of
    /// consulting `validity`. net_id controls the same-net predicate.
    pub grid: Option<&'a [i8]>,
    pub net_id: i64,
    /// (rows*cols,) uint8 corridor mask (0=blocked, 1=allowed).
    pub corridor_mask: Option<&'a [u8]>,
}
```

Per-expansion logic (in the `for d in 0..8` loop):
```rust
// When grid is supplied, check bounds + occupancy inline
if let Some(g) = input.grid {
    if ndc < 0 || ndr < 0 || ndc >= input.cols as i64 || ndr >= input.rows as i64 {
        continue;
    }
    let cell = g[(ndr * input.cols as i64 + ndc) as usize] as i64;
    if cell != 0 && cell != input.net_id {
        continue;
    }
    // Corridor check
    if let Some(ref mask) = input.corridor_mask {
        if mask[(ndr * input.cols as i64 + ndc) as usize] == 0 {
            continue;
        }
    }
    // Same-net cost discount
    if cell == input.net_id {
        step *= 0.25f32;  // _SAME_NET_COST_DISCOUNT
    }
} else {
    // existing validity-tensor path (backward compat for net_id < 0)
    ...
}
```

**`packages/temper-rust-router/src/lib.rs`** (~20 lines):

`astar_kernel_3d_py` gains:
```rust
grid_bytes: Option<Vec<u8>>,
net_id: i64,
corridor_mask_bytes: Option<Vec<u8>>,
```

### 5.2 Python changes (2 files)

**`packages/temper-placer/src/temper_placer/router_v6/astar_core_rust.py`** (~15 lines):

`_astar_search_rust_kernel` gains `net_id: int = -1` and `corridor_mask:
np.ndarray | None = None` parameters. When `net_id >= 0`:
- Pass `grid.grid.tobytes()` instead of building/encoding a validity tensor
- Pass `net_id` and optional `corridor_mask` to the kernel
- Avoid the 30ms `build_neighbor_validity_tensor_2d` call entirely

**`packages/temper-placer/src/temper_placer/router_v6/_astar_search.py`** (~5 lines):

In `_dispatch_search` (line 92-96), **remove** the special case:
```python
# BEFORE (to be removed):
if net_id >= 0:
    return _astar_search(start, goal, grid, net_id=net_id, corridor_mask=corridor_mask)
```

After removal, ALL 2D plain A* calls flow through `_astar_search_rust`
(line 98+), which dispatches to the Rust kernel. The `_astar_search`
pure-Python reference remains available as a fallback only (when
`temper_rust_router` cannot be imported).

### 5.3 Differential test plan

1. **Extend existing harness**: Add `net_id > 0` grids with same-net
   occupancy patterns to `test_astar_kernel_rust_differential.py`.
   Grid patterns:
   - Own-net pad in middle of free grid (should route through it with discount)
   - Own-net trace blocking direct path (should route through it)
   - Other-net trace blocking direct path (should detour)
   - Mixed: own-net + other-net interleaved (should route through own-net only)

2. **PBT extension**: Add properties to `test_astar_kernel_pbt.py`:
   - P7: path never enters a cell owned by a different net
   - P8: path can enter cells owned by the routed net
   - P9: same-net discount yields cost ≤ no-discount cost

3. **Anti-vacuity**: A grid where the discount changes the path
   (verifies D2 is actually wired, not silently ignored).

4. **Full-pipeline A/B**: Run `test_production_board_routing_drc_regression`
   with `TEMPER_ASTAR_BACKEND` comparing Rust vs Python for `net_id >= 0`
   nets, asserting identical completion rate and route length.

### 5.4 Backward compatibility

- `net_id = -1` (the default): grid_bytes is `None`, validity tensor path
  used as before. Zero behavior change for coarse-to-fine corridor search
  and any other `net_id < 0` caller.
- `net_id >= 0` with `grid_bytes` supplied: new inline path. Falls back to
  validity tensor if grid is not supplied.
- The `line_of_sight_py` function already has `net_id` support (lib.rs:522)
  and is unchanged -- it already works for `net_id >= 0`.

## 6. Measurement scripts

`tools/measurements/astar_same_net_wiring/`:
- `extract_same_net_predicate.py` -- AST-parses the Python reference to
  document the exact same-net predicate and cell-value semantics.
- `parity_analysis.py` -- enumerates every divergence source between the
  Python reference and Rust kernel for `net_id >= 0`, assesses parity
  risk, and documents the change surface.

Both are read-only analysis scripts; they modify no source files and
build no crates.

## 7. What this doesn't answer

- **Live parity measurement:** The Rust kernel does not yet accept a raw
  grid or `net_id`, so no differential run is possible. The parity verdict
  in §3 is a code-reading analysis, not a measurement. The differential
  test plan in §5.3 is the implementation's acceptance gate.
- **Per-expansion cost overhead:** The inline bounds + occupancy check is
  slightly more expensive per expansion than the current single-bit read.
  However, the search expands far fewer cells than the grid contains (2,600
  for a short segment on a 3.7M-cell grid -- 0.07%), so the per-expansion
  overhead is negligible compared to eliminating the 30ms full-grid scan.
  Profiling after implementation is the correct way to confirm this, not
  a pre-build estimate.
- **3D fallback same-net awareness:** The `_astar_search_3d` function has
  no same-net awareness (uses `grid.is_free()` which only checks `== 0`).
  This is a pre-existing limitation in a rarely-exercised fallback path
  and is out of scope for this spike.
