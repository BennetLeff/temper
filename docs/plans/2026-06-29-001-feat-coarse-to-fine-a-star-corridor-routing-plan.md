---
title: "feat: Coarse-to-fine A* corridor routing to reduce per-net expansion count"
type: feat
status: active
date: 2026-06-29
origin: docs/plans/2026-06-29-001-feat-coarse-to-fine-a-star-corridor-routing-plan.md
---

# Coarse-to-Fine A* Corridor Routing

## Summary

Route on a 4× coarsened occupancy grid first (1/16 the cells), establish a
routing corridor, then refine via full-resolution A* constrained to that
corridor (expanded by a buffer margin).  This reduces the search space
~100× while preserving path quality through the refinement step.

The coarse grid is built by max-pooling (any blocked fine cell → blocked
coarse cell), a single numpy operation per layer.

---

## Problem Frame

On `temper.kicad_pcb`, the router V6's full-resolution Theta* A* on the
1000×1000 occupancy grid expands up to 1M cells per net, producing 761K
line-of-sight calls that consume 87.7% of total routing time.  While the
A* itself is correct and the inner loop is Numba-jitted (R10), the brute-
force search over 1M cells is the dominant cost.

The coarse-to-fine approach is a well-established robotics path-planning
technique: reason about the world at low resolution to establish a rough
corridor, then refine at high resolution within that corridor.  On PCB
boards the obstacles (components, keep-out zones, previously-routed nets)
are spatially coherent, so a 4× downsampled grid faithfully represents
the topology of free space.

---

## Requirements

### Core Routing Requirements

- **R1.** Coarse grid is built by max-pooling a 4× factor from the fine
  occupancy grid: a coarse cell is BLOCKED iff any of its 16 sub-cells
  is not FREE.
- **R2.** Coarse routing uses plain octile A* (not Theta*) on the coarse
  grid to find a coarse path between waypoints.  Theta* is unnecessary
  at coarse resolution — the path is advisory, not geometric.
- **R3.** Corridor extraction: for each coarse path cell, expand by a
  buffer of `B` fine cells in each direction (x and y).  The union of
  all expanded cells forms the fine-grid corridor mask.
- **R4.** Constrained fine routing runs full-resolution A* (including
  Theta* and Lazy Theta* when enabled) restricted to corridor cells.
- **R5.** Fallback: if the constrained fine route fails, retry with
  unrestricted full-resolution A*.
- **R6.** Multi-layer routing (F.Cu + B.Cu via `alternate_grid`) uses
  coarse-to-fine per layer independently, with fallback unchanged.

### A/B Testing & Metrics Requirements

- **R7.** A/B comparison fixture: run both modes (current full-resolution
  vs coarse-to-fine) on the same netlist from `temper.kicad_pcb` and
  compare per-net metrics.
- **R8.** Metrics collected per net:
  - Total A* expansions (coarse phase + fine phase)
  - Line-of-sight (LOS) call count (Theta* only)
  - Wall-clock time (ms)
  - Path length in mm (HPWL equivalent)
  - Closure rate (routed / total)
- **R9.** A/B results must be reproducible from a single CLI invocation
  and output a comparison table (stdout + JSON).

### Correctness Verification Requirements

- **R10.** Coarse-path is a valid corridor: every coarse cell in the path
  must be FREE on the coarse grid.
- **R11.** Fine-path must stay within the corridor + buffer margin: no
  fine cell in the path exceeds `B` cells distance from any coarse path
  cell.
- **R12.** Final path must satisfy the same connectivity (start → goal
  via waypoints) and clearance constraints as the baseline.
- **R13.** Hypothesis property-based test for coarse grid correctness:
  - **Downsampling correctness**: A fine cell is BLOCKED ⇒ the
    corresponding coarse cell is BLOCKED.  A coarse cell is FREE ⇒ all
    its fine sub-cells are FREE.
  - **Round-trip consistency**: `downsample(factor=4).free_cell_count`
    reflects 4×4 pooling semantics.
  - **Edge invariance**: Coarsening the board outline never produces a
    coarse grid larger than `ceil(fine_dims / factor)`.

### Performance Targets

- **R14.** Coarse phase < 10% of current full-resolution routing time
  (expected: ~5ms per net at 250×250 coarse grid).
- **R15.** Fine phase < 30% of current routing time (expected: ~30ms per
  net with corridor constrained to ~5000 cells).
- **R16.** Total expansions per net < 50K (vs 500K–1M current).
- **R17.** No regression in closure rate on `temper.kicad_pcb`.

---

## Scope Boundaries

### In Scope
- `OccupancyGrid.downsample()` — refine vectorized numpy implementation
  (already scaffolded at `occupancy_grid.py:104`)
- Corridor extraction utility in a new module or within `astar_pathfinding.py`
- Constrained A* variant (masked grid or neighbor-filter)
- Integration into `_segment_search` / `_dispatch_search` in
  `astar_pathfinding.py`
- A/B comparison fixture script
- Hypothesis PBT for coarse grid correctness

### Out of Scope
- Adaptive downsampling factor (fixed 4×)
- Multi-resolution hierarchies beyond 2-level
- Corridor caching / reuse across nets (each net gets its own corridor)
- Changes to Stage 2 (channel analysis) or Stage 3 (SAT)
- Changes to the Numba kernel (corridor mask applied in Python layer
  before dispatch)

### Deferred to Follow-Up Work
- Adaptive downsampling based on board dimensions (e.g., factor = max(2,
  min(grid_dims) // 64))
- Corridor reuse for bundle-neighbor nets (nets in same channel can
  share corridor)
- Progressive corridor widening on retry (expand buffer if constrained
  A* fails before full fallback)

---

## Context & Research

### Relevant Code and Patterns

| File | Role |
|------|------|
| `occupancy_grid.py:104-128` | `OccupancyGrid.downsample()` — already scaffolded, uses loop-based max-pooling |
| `astar_pathfinding.py:136-388` | `run_astar_pathfinding()` — orchestrates per-net A*, holds latency tracking |
| `astar_pathfinding.py:675-731` | `_dispatch_search()` and `_segment_search()` — entry points to A* kernel |
| `astar_core.py:112-206` | `_astar_search()` — pure-Python A* with neighbor-validity tensor |
| `astar_core_numba.py` | Numba-jitted A* kernel (R10) — reads neighbor-validity tensor |
| `neighbor_validity.py:46-90` | `build_neighbor_validity_tensor_2d()` — builds (rows, cols, 8) bool tensor |
| `route_stage.py:19-87` | `RouteStage.run()` — wires `run_astar_pathfinding` into the pipeline |
| `stage4_orchestrator.py` | Stage 4 micro-stage chain (GridPrep → NetPrep → Route → ResultAggregate) |
| `pipeline.py:990-1082` | `_run_stage4()` — Stage 4 entry, creates `BoardState`, calls orchestrator |
| `benchmark.py` | Post-route metrics aggregation from `PathfindingResult` |
| `astar_monitor.py` | Runtime A* invariant monitor (f-cost monotonicity, path completeness) |

### Institutional Learnings

- The `OccupancyGrid.downsample()` method was scaffolded during the U4
  exploration (occupancy_grid.py:104, committed).  It currently uses a
  Python nested loop with `np.any()`.  This is correct but ~10× slower
  than a vectorized numpy stride-trick or block-reduce operation.  Given
  that downsampling is called once per layer (not per net), the loop is
  acceptable for correctness-first implementation and can be vectorized
  as a follow-up.
- The Numba A* kernel (`astar_core_numba._astar_search_numba`) reads a
  neighbor-validity tensor pre-baked as a flat `int8` array.  Corridor-
  constrained A* can be implemented by building a modified validity
  tensor where moves into non-corridor cells are marked invalid.  This
  avoids any changes to the Numba kernel itself.
- The `per_path_latency_ms` field in `PathfindingResult` already tracks
  per-net wall-clock time; it accumulates across ripup/reroute attempts.
  Coarse-to-fine timing can be measured by adding separate `coarse_ms`
  and `fine_ms` fields.

### Existing Patterns to Follow

- Grid operations in the router use numpy vectorized slicing (e.g.,
  `grid[cy, cx]` for cell reads, `grid[y_start:y_end, x_start:x_end]`
  for region writes).
- New modules go in `packages/temper-placer/src/temper_placer/router_v6/`
  with a docstring header.
- Tests go in `packages/temper-placer/tests/router_v6/` with `test_`
  prefix and `pytest` conventions.
- Hypothesis PBT tests use `hypothesis.given()` with `st.integers()`,
  `st.lists()`, etc.

---

## Key Technical Decisions

### D1. Fixed 4× downsampling factor

A fixed 4× factor is chosen over adaptive sizing for the initial
implementation.  Rationale:
- On `temper.kicad_pcb`, a 1000×1000 fine grid becomes 250×250 coarse
  (62,500 cells, 16× reduction).  A* on 62K cells completes in ~5ms.
- A coarse cell represents 0.4mm × 0.4mm on a 0.1mm fine cell.  This
  is sufficient to capture the topology of the board: most obstacles
  (components, keep-outs) are ≥1mm across.
- Adaptive sizing (e.g., `factor = max(2, min(grid_dims) // 64)`) can
  be added later as a tunable parameter.

### D2. Fixed 3-cell corridor buffer

A 3-cell buffer (0.3mm on 0.1mm cell size) is chosen for the corridor
expansion.  Rationale:
- Trace width + clearance typically consumes 2–3 fine cells (0.2mm
  trace + 0.2mm clearance = 0.4mm = 4 cells diameter).  A 3-cell
  expansion on each side of the coarse path center gives a corridor
  width of ~7 coarse-equivalent cells = ~2.8mm.
- This is generous enough to contain the fine-resolution path while
  keeping the corridor to ~5000 cells for a typical 150-cell coarse
  path.
- The buffer is proportional to the coarse cell size: `B = int(3 *
  factor)`, i.e., 12 fine cells for factor=4.  This makes `B` scale
  with the downsampling factor if adaptive sizing is added later.

### D3. Corridor constraint via modified neighbor-validity tensor

Rather than modifying the grid (copy + mark non-corridor cells blocked),
we build a corridor-aware neighbor-validity tensor.  For each cell, a
neighbor move is valid only if:
1. The destination cell is in-bounds and FREE (existing check), AND
2. The destination cell is within the corridor mask.

This approach:
- Preserves the original grid (no copy needed)
- Works with the existing `_tensor_is_valid()` call site
- Compatible with both pure-Python and Numba A* paths
- The corridor mask is a boolean numpy array of shape `(rows, cols)`

### D4. Coarse routing uses plain A*, not Theta*

The coarse path is advisory — its purpose is to establish the corridor,
not to produce a geometrically optimal route.  Plain octile A* on the
coarse grid is sufficient and avoids the overhead of line-of-sight
checks at coarse resolution (where they would provide negligible
benefit).

### D5. Fallback triggers on any routing failure

If the constrained fine A* fails for any waypoint pair (or if the
coarse A* itself fails), the system falls back to unrestricted full-
resolution A* for that net.  This ensures the closure rate never
regresses — the fallback path is identical to the current production
behavior.

### D6. Coarse-to-fine per waypoint pair, not per net

The routing currently works per waypoint pair within a net (see
`_astar_route()` and `_astar_route_multilayer()`).  Coarse-to-fine
is applied per waypoint pair: coarse A* from segment start to segment
goal, corridor extraction, constrained fine A*.  This keeps the change
localized to `_segment_search()`.

---

## Implementation Units

### U1. Vectorize `OccupancyGrid.downsample()`

**Goal:** Replace the Python nested-loop max-pooling with a vectorized
numpy implementation that processes the entire grid in O(1) Python
overhead.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/occupancy_grid.py`

**Approach:**
- Use numpy block-reduce via reshaping: reshape the fine grid from
  `(H, W)` to `(new_H, factor, new_W, factor)` and apply `np.any()` over
  axes 1 and 3.  Any non-zero block → BLOCKED coarse cell.
- Handle edge padding: if the fine grid dimensions are not evenly
  divisible by `factor`, pad with BLOCKED cells (conservative: treat
  partial edge blocks as blocked).
- Update the docstring to note the vectorized implementation.

**Test scenarios:**
- All-free grid: all coarse cells FREE
- All-blocked grid: all coarse cells BLOCKED
- One blocked cell per 4×4 block: all coarse cells BLOCKED
- Mixed: one blocked cell in some blocks, none in others

**Verification:**
- Existing `test_occupancy_grid.py` tests pass (no regression)
- New Hypothesis PBT in U6

---

### U2. Corridor extraction utility

**Goal:** Given a coarse path (list of coarse grid cells), produce a
fine-grid boolean corridor mask via cell expansion.

**Requirements:** R3

**Dependencies:** U1

**Files:**
- New: `packages/temper-placer/src/temper_placer/router_v6/corridor.py`

**Approach:**
```python
def extract_corridor_mask(
    coarse_path: list[tuple[int, int]],
    coarse_grid: OccupancyGrid,
    fine_grid: OccupancyGrid,
    buffer_cells: int = 12,  # 3 * factor for factor=4
) -> np.ndarray:
    """Return boolean mask of shape (fine_rows, fine_cols) for corridor."""
```
- For each coarse cell in the path, compute the corresponding fine-grid
  rectangle: `(cx * factor, cy * factor)` to `((cx+1) * factor, (cy+1)
  * factor)`.
- Expand each rectangle by `buffer_cells` in each direction, clamped to
  fine grid bounds.
- OR all rectangles into a single boolean mask.
- The mask is True for cells within the corridor.

**Test scenarios:**
- Single-cell coarse path: corridor is a 4×4 block + buffer
- Multi-cell coarse path: corridor covers all expanded blocks
- Path near grid edge: buffer clamped to bounds
- Empty path: empty corridor mask

**Verification:**
- Unit test with known grid dimensions and manual calculation

---

### U3. Corridor-aware neighbor-validity tensor

**Goal:** Build a neighbor-validity tensor that restricts A* moves to
corridor cells.

**Requirements:** R4

**Dependencies:** U1, U2

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/neighbor_validity.py`

**Approach:**
- Add `corridor_mask: np.ndarray | None = None` parameter to
  `build_neighbor_validity_tensor_2d()`.
- After the existing `dst_free` check, add a second condition:
  `dst_in_corridor = corridor_mask[dst_slice]` and AND with
  `dst_free`.
- When `corridor_mask is None`, behavior is unchanged (backward
  compatible).

**Test scenarios:**
- Corridor covers all free cells: same as unrestricted
- Corridor excludes specific cells: those cells' neighbors marked invalid
- None corridor: backward-compatible behavior

**Verification:**
- Existing A* tests pass with `corridor_mask=None`
- New test: A* with narrow corridor fails where unrestricted succeeds

---

### U4. Integrate coarse-to-fine into `_segment_search`

**Goal:** Wire coarse-to-fine routing into the A* dispatch path, with
fallback on failure.

**Requirements:** R2, R4, R5, R6

**Dependencies:** U1, U2, U3

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py`

**Approach:**

1. Add coarse-to-fine control parameters to `run_astar_pathfinding()`:
   - `enable_coarse_to_fine: bool = False`
   - `coarse_factor: int = 4`
   - `corridor_buffer_cells: int = 12`  (3 × factor)

2. In `_segment_search()`, when coarse-to-fine is enabled:
   a. Downsample the grid (cached per grid, not per segment): maintain a
      `coarse_grid_cache` dict mapping `(layer_name, factor)` →
      `OccupancyGrid`.
   b. Convert start/goal to coarse coordinates:
      `coarse_start = (fine_x // factor, fine_y // factor)`
      `coarse_goal = (fine_gx // factor, fine_gy // factor)`
   c. Run plain A* on coarse grid via `_dispatch_search()` with
      `use_theta_star=False`.
   d. If coarse path found:
      - Extract corridor mask via U2
      - Build corridor-aware neighbor-validity tensor via U3
      - Run fine A* (respecting Theta*/Lazy Theta* flags) with
        constrained tensor
   e. If fine path found → return it (success).
   f. If coarse path not found OR fine path not found → fall through to
      unrestricted A* (existing behavior).

3. Track coarse/fine timing:
   - Add `coarse_ms` and `fine_ms` fields to `PathfindingResult`
   - Add `per_net_coarse_ms` and `per_net_fine_ms` dicts
   - Accumulate in `_add_latency` or separate counters

4. Multi-layer handling: apply coarse-to-fine independently to each
   layer's grid.  The `_segment_search` function already receives a
   specific `grid` parameter; no changes needed to the multilayer
   dispatch logic.

**Test scenarios:**
- Happy path: coarse path found, fine path within corridor found
- Coarse A* fails (blocked start/goal): fallback to unrestricted fine A*
- Fine A* fails (corridor too narrow): fallback to unrestricted fine A*
- Multi-layer: coarse-to-fine on both F.Cu and B.Cu independently

**Verification:**
- Integration test on `temper.kicad_pcb` with A/B comparison

---

### U5. A/B comparison fixture

**Goal:** Run current vs coarse-to-fine routing on the same board and
netlist, collect per-net metrics, generate comparison report.

**Requirements:** R7, R8, R9

**Dependencies:** U4

**Files:**
- New: `scripts/bench_coarse_to_fine.py`
- Modify: `scripts/manifest.yaml` (new entry)

**Approach:**
- CLI: `uv run python scripts/bench_coarse_to_fine.py --pcb temper.kicad_pcb [--nets NET1,NET2] [--output report.json]`
- Run baseline: `RouterV6Pipeline` with default config
- Run coarse-to-fine: `RouterV6Pipeline` with `enable_coarse_to_fine=True`
- For each net, compare:
  - A* expansions (total: coarse + fine vs baseline)
  - LOS calls (Theta*)
  - Wall time (ms)
  - Path length (mm)
  - Closure status
- Output comparison table to stdout and JSON

**Output format (stdout):**
```
  Net        | Baseline  | Coarse2Fine | Δ Time  | Δ Expansions | Same Path?
  -----------|-----------|-------------|---------|--------------|-----------
  /SPI_MOSI   | 452ms     | 48ms        | -89%   | 890K → 12K   | ✓ (0.1mm)
  ...
  TOTALS      | 12,340ms  | 2,100ms     | -83%   | 23M → 0.4M   | 22/24 nets
```

**Test scenarios:**
- N/A (benchmark script, not a test)

**Verification:**
- Manual run on `temper.kicad_pcb`
- Check that over 5 runs, metrics are stable (±5%)

---

### U6. Hypothesis PBT for coarse grid correctness

**Goal:** Property-based tests verifying the mathematical correctness of
the downsampled grid.

**Requirements:** R13

**Dependencies:** U1

**Files:**
- New: `packages/temper-placer/tests/router_v6/test_coarse_grid_pbt.py`

**Approach:**
1. **Downsampling correctness:** Generate random OccupancyGrid instances,
   downsample, then verify:
   - For every fine cell `(fx, fy)`: if `fine[fy, fx] != 0`, then
     `coarse[fy//factor, fx//factor] != 0`.
   - Contrapositive: if `coarse[cy, cx] == 0`, then all fine cells in
     block `(cx*factor:(cx+1)*factor, cy*factor:(cy+1)*factor)` are `0`.
2. **Dimension consistency:** `coarse.width_cells == max(1,
   fine.width_cells // factor)`, same for height.
3. **Origin preservation:** Coarse grid origin matches fine grid origin.
4. **Cell size scaling:** Coarse `cell_size == fine.cell_size * factor`.

**Test scenarios:**
- Random grid sizes (10–200 cells per dimension)
- Various blocking patterns: all-free, all-blocked, checkerboard, single
  blocked cell, edge-blocked-only
- Various factors: 2, 3, 4, 8 (powers and non-powers)

**Verification:**
- `pytest packages/temper-placer/tests/router_v6/test_coarse_grid_pbt.py`

---

### U7. Integration wiring into pipeline and orchestrator

**Goal:** Add coarse-to-fine routing as an opt-in feature flag through
the pipeline and orchestrator layers.

**Requirements:** R1–R6 (integration)

**Dependencies:** U4

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/route_stage.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/stage4_orchestrator.py`

**Approach:**
- Add `enable_coarse_to_fine: bool = False` to `RouterV6Pipeline.__init__()`
- Thread through `BoardState` as `enable_coarse_to_fine` attribute
- In `RouteStage.run()`, pass `enable_coarse_to_fine` to
  `run_astar_pathfinding()`
- In `_run_stage4()`, set the field on `BoardState`
- No changes to `Stage4Orchestrator` (it passes `BoardState` through)

**Test scenarios:**
- Pipeline run with `enable_coarse_to_fine=True` completes without error
- Pipeline run with `enable_coarse_to_fine=False` produces identical
  results to current production

**Verification:**
- Integration test: full pipeline run on a small test board

---

## Risk Assessment

### Risk 1: Corridor too narrow → fine A* fails → fallback eliminates benefit

**Probability:** Medium.  On `temper.kicad_pcb`, the board is not highly
congested and channels are wide; 12-cell buffer should be sufficient.
The 3-bit problem nets (SPI_MOSI, I_SENSE) may still need fallback.

**Mitigation:** The fallback ensures correctness.  Deferred work can add
progressive corridor widening on retry (expand buffer by 2× on first
failure, then fallback).

### Risk 2: Coarse A* path differs from optimal fine path

**Probability:** Low for path topology, medium for exact geometry.  The
coarse grid preserves obstacle topology faithfully (max-pooling is
conservative — it never creates false openings).  The coarse path will
be topologically correct; the fine path refines the exact geometry.

**Mitigation:** The fine A* within the corridor will find the optimal
path *within the corridor*.  If the globally optimal path lies outside
the corridor (unlikely for a generous buffer), the fallback catches it.

### Risk 3: Coarse grid on edge dimensions

**Probability:** Low.  The downsampling pads with blocked cells when
dimensions are not evenly divisible.  This is conservative and may
add a 1-cell blocked border on the right/bottom edges.

**Mitigation:** The buffer expansion compensates for the conservative
edge padding.

### Risk 4: Numba kernel overhead dominates for small corridors

**Probability:** Low.  The Numba kernel call overhead (~0.1ms) is
amortized over the search.  For very small corridors (< 100 cells),
the coarse+fine overhead may exceed the baseline, but for typical
corridors (5000+ cells) the savings dominate.

**Mitigation:** Add a minimum corridor size threshold (e.g., skip
coarse-to-fine if the coarse path has < 5 cells, indicating a trivial
route).

---

## Success Criteria

1. **Closure rate:** No regression on `temper.kicad_pcb` (currently
   22/24 or 24/24 depending on `max_iter`).
2. **Expansion count:** Total expansions per net reduced from mean
   500K to < 50K (10× improvement).
3. **Wall time:** Total routing time reduced by ≥ 60% on
   `temper.kicad_pcb`.
4. **Path quality:** Final path lengths within 5% of baseline for ≥ 95%
   of nets.
5. **Correctness:** All Hypothesis PBT tests pass.  All existing router
   V6 tests pass.
6. **Fallback correctness:** Every net that routes in baseline also
   routes with coarse-to-fine (equal or better closure rate).

---

## Appendix A: Expansion Count Model

For a net spanning ~150mm on a 1000×1000 grid (1M cells):

| Phase | Grid | Cells | A* Expansions (est.) | Time (est.) |
|-------|------|-------|---------------------|-------------|
| Current | 1000×1000 fine | 1,000,000 | 500K–1M | 200–450ms |
| Coarse | 250×250 coarse | 62,500 | 10K–30K | 3–8ms |
| Corridor | ~5000 fine cells | 5,000 | 5K–20K | 10–40ms |
| **Total (C2F)** | — | — | **15K–50K** | **15–50ms** |

This represents a **~10–20× reduction** in expansions and a **~5–10×
reduction** in wall-clock time per net.

## Appendix B: Corridor Buffer Derivation

Given:
- Fine cell size = 0.1mm
- Coarse factor = 4 (coarse cell = 0.4mm)
- Trace width = 0.2mm → 2 fine cells
- Clearance = 0.2mm → 2 fine cells
- Total blocked radius per trace = 2 + 2 = 4 fine cells from centerline

The coarse path centerline may be up to 0.2mm (0.5 coarse cells) from
the optimal fine path centerline.  To ensure the corridor contains the
fine path with all its clearance expansion:

```
B_fine = ceil(trace_radius + max_centerline_deviation + margin)
       = ceil(4 + 2 + 6) = 12 fine cells
       = 3 coarse cells
```

This is the default buffer.  It can be tuned via
`corridor_buffer_cells` parameter.

## Appendix C: A/B Test Harness Pseudocode

```python
def run_ab_comparison(pcb_path, netlist=None):
    """Run baseline and coarse-to-fine, collect per-net metrics."""
    baseline = RouterV6Pipeline(enable_theta_star=True, enable_coarse_to_fine=False)
    c2f = RouterV6Pipeline(enable_theta_star=True, enable_coarse_to_fine=True)

    result_baseline = baseline.run(pcb_path)
    result_c2f = c2f.run(pcb_path)

    for net in common_nets:
        b = lookup_metrics(result_baseline, net)
        c = lookup_metrics(result_c2f, net)
        report_row(net, b, c)
```

This produces the comparison table specified in R9.
