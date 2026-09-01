<!-- provenance: commit=8dc81a3360a7bbe3b7d66d5d555b9d5e35ae1698 dirty=UNKNOWN -->

# Corridor-aware A*: does configuration-space erosion fix the width-blind-search bug, and where does it hit a wall

**Date:** 2026-08-11
**Task:** a spike to prototype and measure configuration-space (C-space)
corridor erosion as a fix for the root cause documented in
`docs/evidence/2026-08-11-track-width-shorting-root-cause.md`: Router V6's
A* searches the occupancy grid width-BLIND while `mark_path_blocked` marks
copper width-AWARE, so A* can return a centreline that is clear at the
centre and not clear at the trace's actual footprint.

## Headline

**The erosion mechanism itself works, is unit-tested, and is proven
end-to-end against the real board on the one net where the board's
existing layout leaves it room to work (`GATE_LS`).** For the other 8 of
the 9 named nets — all in the `HighVoltage`/`HighVoltageIsolated` net
classes, whose `clearance_mm` is **6.0mm** (not a typo — see §3) — a
bounded, single-layer, 2-endpoint corridor-aware search finds **no**
fully-compliant path at all, even though a naive width-blind search still
finds *a* (violating) path for 4 of those 8. That is not a bug in the
erosion kernel; it is the erosion kernel correctly refusing to fabricate a
compliant route where the current placement doesn't leave one, on this
bounded search. **This is exactly the "erosion works but the board is too
congested at these widths" outcome the task brief flagged as an
acceptable, important finding** — it says the fix belongs partly in
placement/channel allocation, not only in the router's search.

## 1. What was built

### 1.1 The Rust erosion kernel

`packages/temper-geometry/src/corridor_erosion.rs` (new module, `pub mod
corridor_erosion;` in `lib.rs`, unconditional so it is `wasm32`-testable;
the pyo3 bridge function is feature-gated like the rest of this crate's
mixed pure/python modules).

- `expansion_cells_ceil(radius_mm, cell_size)` — `ceil(radius_mm /
  cell_size)`, saturating instead of panicking on non-finite input.
- `erode_free_mask(grid, width_cells, height_cells, net_id, expansion)` —
  the actual erosion: a cell is valid iff every cell within a
  `(2*expansion+1)`-square window centred on it is either free (`0`) or
  belongs to `net_id`. Implemented as a 2D summed-area table so cost is
  `O(width*height)` regardless of `expansion` (no `(2e+1)^2` inner loop).
- `corridor_mask_for_net(...)` — convenience wrapper deriving `expansion`
  from `(trace_width, clearance, cell_size)` **the identical way
  `occupancy_raster::mark_path_rect` does**
  (`radius_mm = trace_width/2 + clearance`, then `ceil`).
- `corridor_mask_for_net_py` — the pyo3 bridge, returning `PyBytes` in the
  same shape/convention as the existing `extract_corridor_mask` (so the
  Python side does the same `np.frombuffer(...).reshape(...)` it already
  does for that function).

**Structuring-element parity, checked by reading the marking function
first, per the task brief.** `mark_path_rect`'s `mark_point_rect` (read in
full before writing any erosion code) stamps a *square* window of
half-width `expansion` cells around each interpolated path point — a
Chebyshev (L∞) ball, not a Euclidean disc and not a rotated rectangle
despite the "rect" in the name (that refers to the per-point stamp, not
the swept envelope). Eroding by the identical square window is therefore
the exact inverse of that stamp, not an approximation that disagrees at
corners — which is the trap the brief named by name (a Euclidean-disc
erosion would falsely validate a diagonal cell the square marking stamp
would actually cover; see `test_structuring_element_is_square_not_disc`).

**Own-net exemption, the false-negative trap.** `erode_free_mask` treats a
cell as an obstacle only when it is nonzero *and* not equal to `net_id`.
Own copper and own pads share `net_id` on the grid (same convention
`mark_path_rect`/`mark_via_circle` already use), so they are never
obstacles to themselves — mirroring the exemption
`astar_core._astar_search`'s existing `net_id >= 0` branch already applies
to *direct* (non-eroded) occupancy. Tested directly:
`test_own_net_pad_is_exempt_from_erosion` /
`test_other_net_pad_is_not_exempt` build a grid with a 3×3 pad and assert
the corridor is valid when eroding for that pad's own net and invalid when
eroding for any other net.

**12 unit tests**, `cargo test --manifest-path
packages/temper-geometry/Cargo.toml --no-default-features` (compiles and
passes with **and** without the `python` feature): own-net exemption
(both directions), the static `-1` sentinel never being exempt, the
out-of-bounds-is-free convention (justified in the module doc: a footprint
that hangs off the grid can never actually be marked by `mark_point_rect`
either, so there's nothing out there to collide with — the *opposite*
convention from `downsample_or_blocks`, which treats OOB as blocked for an
unrelated, conservative reason), the square-vs-disc discriminator, a
handful of ceil-rounding edge cases, and a differential test pinning the
summed-area-table implementation against a naive
`O(w·h·(2e+1)²)` reference over several hand-built grids at 5 different
`net_id`/`expansion` combinations. `python3 scripts/gen_wasm_test_registry.py
--crate temper-geometry` (then `--check`) is clean — 8271 tests across 60
modules, this module's 12 among them.

### 1.2 Wiring: the actual gap turned out to be one level deeper than expected

The brief pointed at `neighbor_validity.build_neighbor_validity_tensor_2d`'s
existing `corridor_mask` parameter as "the wiring hook that already
exists." Reading `astar_core._astar_search` before wiring anything in
found that hook is a dead end for real per-net routing: the function has
**two independent code paths** —

```python
if net_id >= 0:
    # inline occupancy check against grid.grid[ny, nx] directly
    ...
else:
    # net_id < 0: build/consult neighbor_tensor (corridor_mask support lives here)
    ...
```

Every production call site that routes a real net passes a real,
non-negative `net_id` (`_dispatch_search` in `_astar_search.py`: `if
net_id >= 0: return _astar_search(start, goal, grid, net_id=net_id)` —
this bypasses the Rust kernel AND `neighbor_tensor` entirely, precisely
because the Rust kernel's binary validity tensor can't express "this cell
belongs to my own net, treat it as passable"). `corridor_mask` was
therefore already wired into the tensor path used only by `net_id < 0`
callers (coarse-to-fine restriction, `_segment_search_coarse_to_fine`,
itself gated `if enable_coarse_to_fine and net_id < 0` in `_segment_search`)
— i.e. never the path that actually routes a real net today.

**Fix**: added `corridor_mask: np.ndarray | None = None` to
`_astar_search`, consulted only in the `net_id >= 0` branch:

```python
if net_id >= 0:
    if not in_bounds(nx, ny, grid.width_cells, grid.height_cells):
        continue
    if corridor_mask is not None and not corridor_mask[ny, nx]:
        continue
    cell_value = grid.grid[ny, nx]
    ...
```

Threaded through as an optional, default-`None` (fully backward
compatible) kwarg: `_astar_search` → `_dispatch_search` → `_segment_search`
→ `_astar_route` (`packages/temper-placer/src/temper_placer/router_v6/{astar_core,_astar_search}.py`).
Not threaded into `_astar_route_multilayer` / `_astar_route_with_ripup` /
the Theta*/Lazy-Theta* variants — out of scope for a bounded spike (see
§6). `packages/temper-placer/src/temper_placer/router_v6/corridor_erosion.py`
is the thin Python shim (`corridor_mask_for_net(grid, net_id, trace_width,
clearance) -> np.ndarray`), matching the existing `corridor.py` /
`extract_corridor_mask` pattern exactly.

**4 new Python tests**
(`packages/temper-placer/tests/router_v6/test_corridor_erosion.py`),
including a direct regression test for the exact gap above
(`test_astar_search_net_id_branch_respects_corridor_mask`: builds a 1-row
grid, confirms a direct path exists with no mask, confirms the *same*
search with a corridor mask blocking the one possible midpoint cell
correctly returns `None`) and a parity check
(`test_corridor_mask_matches_expansion_from_mark_path_blocked`) that
stamps a path with `mark_path_blocked` for a foreign net, then confirms
every cell that stamp touched reads as invalid corridor for a different
net at the identical `(trace_width, clearance)`.

## 2. Method for the real-board measurement

Bounded, per the task's explicit "smallest route needed, no full-board
route" instruction:

1. Parse `pcb/temper.kicad_pcb` live (`temper_placer.io.kicad_parser.parse_kicad_pcb`,
   `normalize=False`) — 110 nets, 2290 track segments, 48 vias, 527 pads.
2. Build one `OccupancyGrid` per copper layer the 9 nets actually use
   (`F.Cu`, `B.Cu` — none of the 9 have a layer transition, confirmed by
   inspection), covering the full board bbox
   (190.0mm × 242.4mm) at **0.25mm** cells (coarser than production's
   0.1mm default — chosen to keep the pure-Python `_astar_search` inner
   loop tractable for this spike; a physical corridor either fits a given
   gap or it doesn't, largely independent of grid discretization aside
   from quantization noise, but this was not independently re-measured at
   0.1mm — see §6.3).
3. Mark every OTHER net's pads, tracks (at their real, currently-drawn
   width — not the corrected width), and vias onto those grids, each net
   getting its **own** `net_id` (1..110, enumerated from the real net
   list) — so cross-net erosion exemption falls out automatically from
   the same mechanism §1 tests, with no separate "foreign net" bucket
   needed. The 9 target nets' own (undersized) existing copper is
   deliberately excluded — each is re-derived from scratch, not patched.
4. For each of the 9 nets, pick its two *nearest* pads (not farthest —
   see §6) as start/goal. Run `_astar_search` twice on the same grid:
   - **baseline**: exactly today's production behaviour — `net_id`-only
     occupancy, no corridor mask.
   - **corridor**: with `corridor_mask_for_net(grid, net_id,
     <DRU-correct trace_width>, <DRU-correct clearance>)` fed through the
     new parameter. Widths/clearances come from
     `design_rules.get_rules_for_net(net)` (the same net-class table
     `netclass_rules.yaml` compiles, read-only — this task does not touch
     that file), matching the exact values
     `docs/evidence/2026-08-11-track-width-shorting-root-cause.md` §1
     already resolved for these 9 nets.
5. For every path found (either variant), check whether it is actually
   compliant: re-run `corridor_mask_for_net` at the correct width and
   confirm every path cell lands inside it. This is the direct grid-level
   analogue of a `Pad↔Track`/`Track↔Track` DRC short — a cell outside the
   corridor is, by the kernel's own definition, one whose full-width
   footprint touches a different net's copper.

## 3. Measurement

| net | layer | width (mm) | clearance (mm) | baseline | baseline compliant? | corridor | corridor compliant? |
|---|---|---:|---:|---|---|---|---|
| `discharge.k_dis1-nc` | B.Cu | 3.00 | 6.00 | found (31 cells) | **no** (31/31 cells violate) | no path | — |
| `hb.gate_hs.driver-p2` | B.Cu | 2.00 | 6.00 | no path | — | no path | — |
| `hb.power_loop.q_high-g` | F.Cu | 3.00 | 6.00 | no path | — | no path | — |
| `zcd` | B.Cu | 3.00 | 6.00 | found (469 cells) | **no** (459/469 violate) | no path | — |
| `a` | F.Cu | 3.00 | 6.00 | no path | — | no path | — |
| `w1_2` | F.Cu | 3.00 | 6.00 | found (80 cells) | **no** (63/80 violate) | no path | — |
| `GATE_LS` | B.Cu | 0.40 | 0.25 | found (225 cells) | **no** (80/225 violate) | found (230 cells) | **yes** (0/230) |
| `hb.gate_hs.driver-p1-1` | F.Cu | 2.00 | 6.00 | no path | — | no path | — |
| `power_in.ntc-no` | F.Cu | 3.00 | 6.00 | no path | — | no path | — |

**Summary**: baseline finds *a* path for 4/9 nets — **0 of those 4 are
actually compliant at the correct width**, directly reproducing the root
cause on live board geometry (every width-blind "success" is a latent
short/clearance violation once drawn correctly). Corridor-aware search
finds a path for 1/9 nets, and it is **exactly, verifiably compliant**
(0 of 230 cells violate) — proof the mechanism works end-to-end, not just
in the Rust unit tests. For the other 8, corridor-aware search reports
no path: for the 4 where baseline also found nothing, this is consistent
(no route of *any* kind connects those pads on a single layer at this
scope); for the 4 where baseline found a violating path, corridor-aware
search correctly **refuses to launder it** rather than silently returning
something non-compliant — a true "no false green," which is the entire
point of the fix.

**Why 8 of 9 are the hard case, concretely**: `discharge.k_dis1-nc`,
`hb.gate_hs.driver-p2`, `hb.power_loop.q_high-g`, `zcd`, `a`, `w1_2`, and
`hb.gate_hs.driver-p1-1` are `HighVoltage`/`HighVoltageIsolated` (per
`netclass_rules.yaml`: `clearance: 6.0`, matched to `creepage_mm: 6.0` —
this is deliberate mains-safety spacing, not an oversized general
clearance typo). At `radius_mm = trace_width/2 + clearance` that's a
7.5mm (3mm trace) or 7mm (2mm trace) exclusion radius around *every other
net's copper simultaneously* on the same layer. `GATE_LS` is
`GateDriveHV` — HV-domain by safety classification, but `clearance: 0.25`,
`trace_width: 0.4` (a normal signal-scale footprint) — and it is exactly
the one net for which corridor-aware search succeeded. The pattern is
consistent with clearance magnitude, not HV classification per se.

## 4. Threats to this measurement's validity (read before generalizing "infeasible" to production)

This spike's grid marks **every** other net's *entire, final* copper
simultaneously, at each net's real clearance. Production Stage 4 does not
do that: it marks copper incrementally, net by net, in whatever order
Stage 3/4 processes the batch — so the *actual* search for a given net at
the moment it was really routed faced only whatever had been placed
*before* it, not the finished board. This spike's simultaneous-avoid-
everyone-at-once setup is therefore a **harder** test than what production
solves, in one specific way (it does not model routing order), while also
being **easier** in others it does not model at all (zone/copper-pour
polygons, board-edge/keepout clearance, multi-terminal tree topology —
this spike used only each net's 2 nearest pads, not its real historical
route topology — and the 3D via-aware fallback that lets a real net escape
local congestion by changing layers). Given both directions are
unmodeled, the honest reading of §3 is: **the mechanism is proven
correct** (GATE_LS, plus 12 Rust + 4 Python unit tests); **whether the
8 HV nets are infeasible in the *real*, order-aware, multi-layer,
multi-terminal Stage 4** is not settled by this spike and needs a
production-shaped test to answer (see §6).

A second, independent sanity check ruled out this being a marking bug
rather than genuine congestion: for net `a` (whose two pads are 161mm
apart — nearest and farthest pair coincide, it only has 2 pads), the
immediate neighbourhood of both endpoints is nearly saturated at a 5mm
radius (0.65%/0.71% free) but opens up substantially by a 10mm radius
(42%/60% free) — it is not a sealed pocket with zero egress. `_astar_search`'s
~0.4s runtime to conclude "no path" for this net is consistent with a
real, board-spanning connectivity search that exhausts a genuinely
disconnected reachable region after expanding through that opened-up
space, not an instantaneous local trap.

## 5. What was and wasn't verified

**Verified live this session**: the Rust kernel's 12 unit tests (own-net
exemption both directions, static-sentinel non-exemption, OOB-is-free,
square-vs-disc, SAT-vs-naive-reference parity, ceil-rounding edges) under
both `--no-default-features` and `--features python`; `cargo clippy -D
warnings` clean both ways; the wasm test registry regenerated and
`--check`-clean; the 4 new Python tests (own-net exemption round-tripped
through the real pyo3 boundary, the exact `_astar_search` wiring gap
closed and regression-tested, corridor-mask/mark_path_blocked structuring-
element parity from the Python side); the real-board measurement in §3,
computed live against the current, unmodified `pcb/temper.kicad_pcb`; that
none of `packages/temper-placer/tests/router_v6/`'s pre-existing 1240+
tests regressed (21 pre-existing failures observed, all traced to a
networkx API mismatch — `Graph.is_connected`/`edges_with_data` missing —
in `bundle_analyzer.py`/`channel_skeleton.py`, or to `kicad-cli` not being
resolvable in this sandbox for `test_phase1_anti_false_zero.py`; none of
the 21 failing files import or exercise `astar_core.py`, `_astar_search.py`,
`occupancy_raster.rs`, or `corridor_erosion.{rs,py}`, and one instance
(`test_bundle_analyzer.py::test_identical_signal_nets_bundle`) was checked
directly and fails on `AttributeError: 'Graph' object has no attribute
'edges_with_data'` — nothing this spike touched).

**Not verified / explicitly out of scope**: a full-board KiCad DRC round
trip (writing the corridor-aware `GATE_LS` route back into a scratch copy
and re-measuring `shorting_items`/`track_width`/`clearance` via
`kicad-cli`) — the grid-level compliance check in §3 (a cell either lands
inside the eroded corridor or it doesn't, by the kernel's own exact
definition) is the direct, verified analogue of that DRC category and was
used instead, to stay inside the bounded-spike budget; a full Stage 4
production route with corridor masking wired into
`_astar_route_multilayer`/`_astar_route_with_ripup`/net-batching (§6);
whether net ordering, multi-layer via escapes, or real multi-terminal tree
topology change the 8-HV-net infeasibility result (§4).

## 6. What a production implementation would take

1. **Wire `corridor_mask` into the rest of the call chain** this spike
   left untouched: `_astar_route_multilayer` (the real per-segment
   production entry point, which currently calls `_segment_search` with
   no `corridor_mask` at all), `_astar_route_with_ripup`, and the
   Theta*/Lazy-Theta* variants (`_astar_search_theta_star`/
   `_astar_search_lazy_theta_star` have no corridor-mask concept today).
2. **Decide the caching granularity**, per the brief's own question.
   §3's method computes the eroded mask fresh per net because the own-net
   exemption depends on `net_id` (a net's own already-placed copper isn't
   knowable from `(width_class, layer)` alone) — and morphological erosion
   does not decompose as `erode(A) ∪ dilate(B)` for a mask that's a union
   of "everyone else" (`A`) and "my own copper" (`B`); it has to be
   `erode(A ∪ B)` computed directly, or the exemption becomes unsound
   (a cell near, but not fully inside, this net's own copper could be
   falsely marked valid). Since the kernel is `O(width·height)`
   regardless of erosion radius, computing it fresh per net is cheap in
   isolation (§3: sub-second per net at a 0.25mm/760×970 grid) — the real
   cost driver for production would be running it O(number of nets) times
   per Stage 4 pass at 0.1mm resolution (≈16x more cells than this
   spike's grid), which needs measuring directly rather than assumed.
3. **Re-run §3's measurement at production's real 0.1mm cell size, in
   actual Stage-4 net-processing order, with real multi-terminal tree
   topology and the 3D via-aware fallback enabled** — the three
   unmodeled factors §4 names — before concluding the 8 HV nets are
   really infeasible under production's actual constraints rather than
   this spike's specific bounded approximation of them.
4. **If §6.3 confirms genuine infeasibility for 6mm-clearance HV nets**,
   that is a placement-density finding, not a router bug — it would mean
   (as the task brief itself anticipated) the fix needs a companion
   placement change opening wider channels around HV-domain components,
   coordinated with whoever owns the concurrently-running creepage/HV-
   barrier work this task was explicitly told not to touch.
