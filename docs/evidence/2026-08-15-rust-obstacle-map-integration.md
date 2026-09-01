<!-- provenance: commit=dabbeaf73c678be2aa969d30f547eeda41d18c07 dirty=UNKNOWN -->

# Rust obstacle-map integration: the A* containment predicate moves to temper-geometry

**Date:** 2026-08-15
**Task:** wire the Rust geometry kernels into the Python A* obstacle checking.
**Result:** the last Python collision-geometry kernel in the obstacle pipeline —
the `shapely.contains()` rasterisation of the occupancy grid — is now a
strict-interior scanline in `temper-geometry` (`rasterize_area_polygons_py`),
proven cell-for-cell identical to GEOS on the real board (~22.3 M cells, 0
mismatches) at ~125× the speed (47.5 s → 0.38 s per route). The A* search
itself was already Rust.

## 1. What the investigation found: the premise was mostly already true

The dispatch assumed "the A* pathfinder is Python but the collision primitives
are Rust, and the obstacle map doesn't consult the Rust kernels." Tracing the
live call path on `origin/main` showed the collision side is already wired:

| pipeline stage | backend on origin/main |
|---|---|
| A* expansion (occupancy reads) | **Rust** — `astar_kernel_3d_py` (temper-rust-router), raw int8 grid zero-copy when `net_id >= 0` (S8 same-net wiring, live in production) |
| Theta\* / Lazy Theta\* | **Rust** — `theta_star_search_py` |
| Line-of-sight | **Rust** — `line_of_sight_py` |
| Grid mark/unmark/blocking-nets/downsample | **Rust** — `occupancy_raster` (Wave 4) |
| Escape-via generation, via placement | **Rust** |
| Obstacle-map polygon construction (`build_obstacle_map`) | Python/Shapely/GEOS — inputs Rust-backed (via circles via `circle_buffer_ring_py`, pads via `core.pad_geometry`) |
| Routing-space difference (`board − obstacles`) | Python/GEOS — documented JUSTIFIED-KEEP (S1 spike: GEOS polygon algebra not bit-reproducible) |
| **Grid rasterisation (`shapely.contains()` over every cell centre)** | **Python/GEOS — the last Python collision kernel in the path** |

The one genuine gap was the containment step: `build_occupancy_grid` samples
~3.7 M cell centres per layer against the eroded available area with a GEOS
prepared-geometry predicate. Measured on `pcb/temper.kicad_pcb`'s six layers:
**45.8 s per route** (F.Cu 17.9 s, B.Cu 11.2 s, inner layers ~4 s each) — a
real cost, and the only place the obstacle map still did collision geometry in
Python.

## 2. Design: Option B — keep the GEOS-produced polygons, move the *predicate*

Of the three options in the task:

- **Option A (Rust-built obstacle map with clearance halos)** — rejected: it
  requires reimplementing GEOS's union/difference/buffer vertex emission, which
  the S1 spike (`docs/evidence/2026-08-04-geos-polygon-algebra-spike.md`) found
  not bit-reproducible, and it would change the grid bytes and therefore every
  routing decision. That is the documented JUSTIFIED-KEEP boundary, and this
  task is not licensed to relitigate it.
- **Option C (switch to the Rust A\* entirely)** — already done at the kernel
  level: `_astar_search_rust`/`theta_star_search_py` are the production search
  backends. The "dark behind `enable_nlayer_astar_spike=False`" code is the
  Python `_astar_nlayer.py` spike (N-layer *plumbing*, not the search kernel);
  there is no separate production-ready self-contained Rust A\* to switch to.
  The Rust kernels are production-ready (verified below); what they are *not*
  is a self-contained router — they still need the grid, whose construction was
  the Python gap.
- **Option B (Rust predicate over the existing obstacle map)** — chosen. The
  S1 spike's non-reproducibility finding is about GEOS polygon **algebra**:
  *which vertices* a union/difference/buffer emits. "Is this cell centre
  strictly inside a polygon whose vertices are given" is a different,
  well-defined point-in-polygon question. So the split is: GEOS keeps producing
  the eroded available-area vertices (erosion stays Python — JUSTIFIED-KEEP);
  Rust evaluates containment over those exact vertices. This preserves the
  grid byte-for-byte (proven below) while removing GEOS from the router's
  collision hot path.

**Kernel:** `temper-geometry/src/occupancy_raster.rs`'s new
`rasterize_area_polygons_py` — a per-row scanline: collect x-crossings of each
outer ring (half-open `y1 <= row_y < y2` PNPOLY convention), sort, pair into
inside-intervals, subtract hole intervals, free the cells whose centres lie
strictly inside a surviving interval; a horizontal-edge pass re-blocks cells
whose centre lies exactly on an edge (the one boundary case interval endpoints
cannot see). Cost is O(V log V + cells) per layer vs O(V × cells) for a naive
per-cell test.

**Convention — boundary cells stay blocked.** GEOS `contains` excludes the
boundary (DE-9IM `T*****FF*`); the kernel matches. This is the conservative
direction and matters: the boundary is already C-space-inflated by
trace-width/2, so a route centred exactly on it would sit at exactly the
clearance distance.

## 3. Differential evidence: 0 mismatches across ~22.3 M cells

GEOS `contains(check_area, points)` vs `rasterize_area_polygons_py` on every
cell of every layer of the real board (cell_size 0.1, margin 2.0, inflation
0.1000 — the production `OccupancyGridStage` parameters):

```
layer   GEOS (s)  Rust (s)  free GEOS  free Rust  mismatches
F.Cu      18.789     0.057     868653     868653      0
In3.Cu     4.303     0.078    3473352    3473352      0
In1.Cu     4.708     0.074    3473352    3473352      0
In2.Cu     3.977     0.080    3473352    3473352      0
In4.Cu     4.316     0.069    3473352    3473352      0
B.Cu      11.449     0.024     880117     880117      0
TOTAL     47.542     0.382                         0   (~22.3 M cells)
```

- **Parity:** cell-for-cell identical, including the free-cell counts on every
  layer.
- **Speed:** 47.5 s → 0.38 s, ~125×, on one full route's grid construction.
- The randomized differential (120 trials: boxes/circles/donuts/U-shapes at
  arbitrary offsets — deliberately landing edges on cell-centre rows) and an
  explicit boundary-alignment test are committed in
  `test_occupancy_grid_rust_differential.py`; the randomized suite caught and
  fixed a real index-clamp bug (negative interval bound wrapping to a huge
  `usize`) during development, which is exactly what the differential is for.

## 4. Route + DRC verification

Full production route of `pcb/temper.kicad_pcb` through `route_board.py
--net-batching --batch-size 10` (the task-mandated recipe), with the new
kernel live, on the 2026-08-15 board (sha256 `077d4b69` — unmodified before,
during, and after; `git status --short pcb/` clean):

```
Result: 94/106 nets (88.7%)  segments=5629 vias=76 zones=320  wall=647.8s
Result (pad connectivity, PRIMARY metric): 63/139 nets fully pad-connected  fake-completion=63 honest-gap=13
Unrouted (12): +3V3, RTD_SCK, discharge.r_snub2-p2, fb, gnd, power_in.bypass_relay-coil2,
                rtd_pan.rail_monitor-outa, s1, safety.fault_or-y2, sdi, sdo, y
[net-batching] 14 batch(es), 14 solved at batch level, 0 crashed
```

The 63/139 pad-connectivity figure is the honest baseline for this base
commit: the handoff records 59 pre-fix → 66 (after #1196) → 69 (after #1197)
on the *unmerged fix branches*; this worktree's base is `origin/main`
(`6285d6889`), which does not carry those fixes, so 63 is the expected
unfixed-baseline result, not a regression.

DRC on the routed output (`kicad-cli pcb drc --all-track-errors`, kicad-cli
10.0.5):

```
1542 violations + 327 unconnected items
  clearance 501 (kicad-cli cap-adjacent; true count requires the uncapped sweep)
  shorting_items 202, hole_clearance 201, silk_overlap 199 (cap), solder_mask_bridge 189
  ... dominated by the router's real output copper on a board the handoff
  documents as "essentially unrouted" at this base
```

No DRC ceiling re-measurement is required: `pcb/temper.kicad_pcb` is
byte-identical (the DRC ceiling contract keys on the *committed board's*
content hash, and this task never writes the board). The routed output is a
scratch artifact under `/tmp`. The parity proof in §3 is the no-regression
argument: the A* input grid is cell-for-cell identical to what the previous
code produced, the A* kernel is the same deterministic Rust, and every other
pipeline stage is untouched — so this route is byte-equivalent to what the
pre-change code would have produced on this board.

## 5. Is the Rust A* path production-ready?

**Yes, at the kernel level — and it has been the production backend since
cleanup C1 (2026-07-31).** `_astar_search_rust` → `astar_kernel_3d_py` is the
sole A* backend; the pure-Python `_astar_search` remains only as an
import-failure fallback. Theta\* is similarly Rust. What is *not* production:
the N-layer **plumbing** (`_astar_nlayer.py`, dark behind
`enable_nlayer_astar_spike=False`), which is a spike about searching more than
two layers at once, not about the search algorithm. Nothing in this task
changed that verdict; the grid the Rust kernels search is now built by Rust
too, closing the last Python collision kernel in the path.

## 6. Follow-ups

- `_corridor_backbone.build_obstacle_grid` (`_corridor_backbone.py`) mirrors
  the same `shapely.contains` rasterisation for the corridor-aware A* spike
  path. Not wired in this change (spike path, YAGNI); the kernel is
  drop-in-ready there when the corridor path is productionized.
- The now-unused `shapely.contains` imports were removed from
  `occupancy_grid.py`; the GEOS reference lives in the differential test.
