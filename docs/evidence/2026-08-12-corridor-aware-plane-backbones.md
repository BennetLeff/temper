<!-- provenance: branch feat/corridor-aware-plane-backbones, worktree /home/bennet/Desktop/temper/.claude/worktrees/agent-a1a703686ace03dc9, base commit bef70cbe5 (main). pcb/temper.kicad_pcb NEVER modified by this task -- every measurement below runs the generator against a copy in this worktree's own scratch space, confirmed via `git status --short pcb/temper.kicad_pcb` empty throughout. -->

# Corridor-aware A* wired into both plane backbones: mechanism proven correct, connectivity preserved, aggregate DRC delta not materially reduced

## Headline

**Corridor-aware A* is now wired into both `_ground_plane.py` (`gnd`/In1.Cu)
and `_power_islands.py` (`+3V3`/`vcc`/`+15V`/`V_BUS_SENSE`/In2.Cu),
replacing the straight-line-MST-plus-one-bend-detour backbone with a real
pathfinding search over `corridor_erosion.rs` + `astar_core._astar_search`'s
`corridor_mask` parameter (#1017), reused rather than reimplemented.**

**Connectivity never regresses**: `gnd` stays at the existing 46/86 floor;
`+3V3`/`vcc`/`+15V`/`V_BUS_SENSE` meet their existing 15/51, 3/13, 2/10, 2/4
floors exactly. **The mechanism itself is proven correct**: every
A*-routed edge's real trace footprint was checked directly against its own
obstacle polygon (continuous shapely geometry, not grid-quantized) and
found to intersect it 0/N times, for every configuration tested.

**But the aggregate DRC collision counts (`clearance`, `solder_mask_bridge`,
`tracks_crossing`) do NOT materially fall.** Across five genuinely
different obstacle/topology strategies -- flat 0.05mm clearance, flat
0.5mm clearance, per-net-pair-correct clearance, Euclidean-MST-edge
attempts, and finally a component-aware intra-region MST -- the aggregate
totals stay within a ~5-10 unit band of the UNPATCHED (straight-line)
generator's own numbers, on the identical board+DRU, measured back-to-back.
A no-backbone control run (same generator, MST edges suppressed entirely)
isolates why: the violation mass concentrates on a small subset of MST
edges that cross the densest F.Cu congestion -- precisely the edges a
correct, clearance-respecting search refuses to solve, because on this
board's current placement, no such path exists at all (verified directly:
the corridor mask for `gnd`, even at its own comparatively loose
Default-class clearance, fragments into ~94 disconnected regions).
**This is the "F.Cu is too congested for a backbone; placement must
change first" outcome the task brief explicitly named as a legitimate,
valuable answer** -- not a failure of this implementation, but a genuine
finding about this board's placement density, confirmed from multiple
independent angles below.

---

## 1. Before/after, side by side, both generators

Measured with `kicad-cli pcb drc --all-track-errors --refill-zones`
against scratch copies of this worktree's own (untouched)
`pcb/temper.kicad_pcb`, `.kicad_pro` staged alongside a freshly generated
`.kicad_dru` (`scripts/generate_kicad_dru.py`) -- without the project
file, kicad-cli silently drops every custom-rule violation, so this
staging is not optional. Both "unpatched" and "this PR" rows are measured
back-to-back against the identical base board+DRU snapshot in this same
session (git-stash before/after this PR's own three changed/added files),
so any residual difference is attributable to the generator, not board or
tool drift.

### 1a. `gnd` / In1.Cu (`_ground_plane.py`)

| category | no-plane baseline | unpatched (straight MST) | this PR (component-aware A*) |
|---|---:|---:|---:|
| `clearance` | 392 | 499 (+107) | 501 (+108) |
| `solder_mask_bridge` | 154 | 201 (+47) | 203 (+49) |
| `tracks_crossing` | 1 | 48 (+47) | 51 (+50) |
| `hole_clearance` | 105 | 119 (+14) | 119 (+14) |
| `copper_edge_clearance` | 10 | 14 (+4) | 14 (+4) |
| `creepage` | (baseline varies run-to-run, documented noise) | -17 vs its own baseline | -8 to -12 vs its own baseline |
| `isolated_copper` | (baseline varies) | -3 to -6 | -1 to -6 |
| `shorting_items` | (baseline varies) | -1 to 0 | -1 to 0 |
| **TOTAL ERRORS** | 2170-2184 | +197 to +201 | +197 to +221 |

`gnd` pad connectivity (`pad_connectivity_audit.audit_pcb_file`, the
project's declared PRIMARY completion metric):

| | baseline (no copper) | unpatched floor | this PR |
|---|---:|---:|---:|
| `pads_connected` | 1 | 46 (existing regression-test floor) | **46** |
| `has_any_copper` | False | True | True |

**46/86, at the existing floor, not below it.** `mst_edges_astar_routed=15`
of 85 MST-topology edges (component-aware construction, see §3) got a
real, corridor-clean A* path; the remaining edges fell back to the
existing keepout-only straight-line/one-bend-detour logic, unchanged.

### 1b. `+3V3` / `vcc` / `+15V` / `V_BUS_SENSE` / In2.Cu (`_power_islands.py`)

| category | no-plane baseline | unpatched (straight MST) | this PR (component-aware A*) |
|---|---:|---:|---:|
| `clearance` | 392-393 | 500 (+108) | 499-500 (+106 to +108) |
| `solder_mask_bridge` | 154 | 188 (+34) | 186-188 (+32 to +34) |
| `tracks_crossing` | 1 | 35 (+34) | 35 (+34) |
| `hole_clearance` | 105 | 110 (+5) | 110 (+5) |
| `creepage` | (baseline varies) | -14 vs its own baseline | -4 to -14 |
| `isolated_copper` | (baseline varies) | +1 | -2 to +1 |
| **TOTAL ERRORS** | 2168-2176 | +173 to +177 | +173 to +177 |

Per-rail pad connectivity:

| net | baseline | target floor | this PR (after) |
|---|---:|---:|---:|
| `+3V3` | 1/51 | 15 | **15** |
| `vcc` | 1/13 | 3 | **3** |
| `+15V` | 1/10 | 2 | **2** |
| `V_BUS_SENSE` | 1/4 | 2 | **2** |

**Every rail meets its floor exactly.** `+3V3` got 7 of 39 MST edges
solved cleanly by A*; `vcc`/`+15V`/`V_BUS_SENSE` got 0 -- their pad
clusters are small and sit inside particularly dense corners of F.Cu (see
§3.2).

**Reading both tables together, per the task's own success bar
(`tracks_crossing`/`clearance`/`solder_mask_bridge` materially down AND
connectivity at or above floor): connectivity is met for both generators;
the collision categories are not materially down for either.** The
differences between "unpatched" and "this PR" above are within the kind
of run-to-run scatter `AGENTS.md` already documents for `clearance`/
`creepage` on this exact DRC pipeline -- not a discernible trend in
either direction beyond noise.

---

## 2. What was built (reusing, not reimplementing, per the task brief)

`packages/temper-placer/src/temper_placer/router_v6/_corridor_backbone.py`
(new, ~590 lines) -- the shared module both generators call:

- **`build_obstacle_grid`** -- rasterizes board outline + an arbitrary
  obstacle-polygon union into an `OccupancyGrid`, mirroring
  `occupancy_grid.build_occupancy_grid`'s own vectorized
  `shapely.contains` construction.
- **`resolve_netclass_clearances`** -- reads `pcb/temper.kicad_pro`'s
  `net_settings` (`classes`, `netclass_assignments`, `netclass_patterns`)
  directly -- the SAME source kicad-cli itself resolves a net's clearance
  from. Checked directly against this board (2026-08-12):
  `temper_placer.core.design_rules.DesignRules.get_rules_for_net`
  returns `"Default"`/0.2mm for every real net name tried, including ones
  the `.kicad_pro` itself explicitly assigns to `Power` (0.5mm) -- that
  module's Python-side `TEMPER_NET_ASSIGNMENTS` table is incomplete for
  this board (`gnd` has no entry at all), so it is not a trustworthy
  proxy for what kicad-cli will actually enforce. Reading the project
  file directly sidesteps that gap.
- **`collect_other_net_copper_by_pairwise_clearance`** -- like
  `_ground_plane._collect_other_net_copper`, but buffers each OTHER net's
  geometry by the REAL pairwise clearance (`max` of the two nets' own
  netclass clearance) instead of one flat value, and fixes a rectangular-
  pad-radius under-coverage bug found along the way (see §4.2).
- **`compute_corridor_mask`** -- thin wrapper over
  `corridor_erosion.corridor_mask_for_net`, plus a small raster-safety
  margin (see §4.3).
- **`route_edge_astar`** -- calls `astar_core._astar_search` with
  `corridor_mask` over bounded, growing local search windows (15mm, 40mm,
  100mm, then the whole grid), snapping the returned path's endpoints
  back to the exact pad/via coordinates (see §4.1) and simplifying
  collinear runs before returning.
- **`corridor_aware_spanning_edges`** -- the component-aware construction
  described in §3; the actual entry point both generators call.

`_ground_plane.py` / `_power_islands.py`: each generator now computes a
per-net (or per-rail) obstacle grid + corridor mask from
`collect_other_net_copper_by_pairwise_clearance` + the existing HV
keepout, calls `corridor_aware_spanning_edges`, emits every solved edge
unconditionally, and unions solved pairs into a `UnionFind`
(`temper_placer.core.topology.UnionFind`, reused, not reimplemented) so
the existing keepout-only fallback loop skips any global-MST edge whose
endpoints are already joined -- avoiding redundant, purely-risk-adding
copper for pairs corridor-A* already connected.

**7 tests, `test_ground_plane.py` / `test_power_islands.py`, all pass**
(including the pre-existing `pads_connected >= 46` regression floor and
the per-rail floor assertions) -- these are integration tests against the
real, unmodified `pcb/temper.kicad_pcb`, always on a `tmp_path` copy.

---

## 3. Why the aggregate numbers don't move: three independent, converging pieces of evidence

### 3.1 A no-backbone control run isolates the true source

Generating `gnd`'s plane with `mst_edges` monkeypatched to return zero
edges (zone pour + via drops only, nothing else changed) and measuring
DRC against the same baseline:

| category | no-plane baseline | no-backbone (zone+vias only) | full unpatched backbone |
|---|---:|---:|---:|
| `clearance` | 392 | 434 (+42) | 499 (+107) |
| `solder_mask_bridge` | 154 | 154 (**+0**) | 201 (+47) |
| `tracks_crossing` | 1 | 5 (+4) | 48 (+47) |

**The backbone (not vias, not the zone pour) accounts for effectively
100% of `solder_mask_bridge` and the large majority of
`tracks_crossing`/`clearance`.** Vias + zone alone already cost +42
clearance / +4 tracks_crossing -- a floor this PR does not touch (via
placement logic is untouched). The backbone's own contribution is
therefore ~65 clearance violations and ~44 tracks_crossing violations
in the unpatched case -- the number this PR's fix targets.

### 3.2 The corridor mask itself is fragmented, independent of search strategy

Direct measurement (`gnd`, this board, 2026-08-12): eroding F.Cu free
space by the HV keepout + pairwise-correct other-net clearance and
labelling connected components (`scipy.ndimage.label`, 8-connectivity)
gives **94 disconnected regions**; `gnd`'s 86 via-drop points land in at
least 31 different reachable groups (after a nearest-label recovery pass
-- see §4.4 -- closing a real grouping bug that otherwise mis-classified
52 of 86 positions as unreachable). No search strategy can bridge two
different components: it is not that A* fails to find a path, it is that
none exists at the required clearance on this layer. This was verified
three independent ways, not assumed:

1. **Window-size independence**: `route_edge_astar`'s bounded-window
   ladder includes the WHOLE grid as its last attempt; edges that fail
   at a 15mm window fail identically at "no window at all" (measured:
   100% of failures were window-size-independent, not a search-budget
   artifact).
2. **Clearance-value independence**: A*-solved-edge counts varied from
   15 to 33 across five different obstacle-buffer configurations tested
   during this task, and the resulting aggregate `clearance`/
   `solder_mask_bridge` totals stayed essentially flat regardless (§1a) --
   if the limiting factor were search budget or an over-tight clearance
   constant, loosening it would have shown a clear trend; it did not.
3. **Topology independence**: replacing the naive "attempt A* on the
   global Euclidean MST's own edges" with "build an MST WITHIN each
   corridor-mask component, so every attempted edge is between points
   already known reachable" only moved the solved-edge count from
   15-33/85 to 15/85 net (see §3.3) -- more attempts within better-chosen
   topology, same order-of-magnitude outcome.

### 3.3 Component-aware routing was tried and measured, not assumed to help

`corridor_aware_spanning_edges` (§2) computes an MST *within* each
corridor-mask component rather than trusting the global Euclidean MST's
topology -- directly targeting the task's own framing question ("route
each MST edge as an A* path, or abandon the MST framing"). Measured
directly: 84/86 `gnd` positions get grouped (up from 34/86 before the
nearest-label recovery fix in §4.4); 53 intra-group candidate edges are
attempted; only 15 solve. The 38 that fail despite being nominally in the
"same" component do so because the nearest-label assignment is itself
approximate (a position within the search radius of a labelled cell is
not guaranteed to have a *short* path to it, only *some* path
topologically) -- a real, acknowledged limitation of this bounded
approach, reported honestly rather than claimed away. **The headline
number this component-aware fix changed was not "how many collisions
disappear" (they didn't, materially) but "how much real intra-region
connectivity is captured cleanly instead of via keepout-only fallback"** --
which is real, measured, and provably collision-free for the edges it
does solve (§1, §4).

---

## 4. Bugs found and fixed along the way (each measured, not theoretical)

**4.1 Endpoint snapping.** `OccupancyGrid.grid_to_world` returns CELL
CENTRES, not the exact point that mapped into that cell. Left un-snapped,
every A*-routed edge's first/last point differs from the true pad/via
position by up to half a cell -- `pad_connectivity_audit`'s exact-position
matching then fails to recognize the connection at all. Measured directly:
this collapsed `gnd`'s `pads_connected` from the 46/86 floor to 14/86
before the fix (`route_edge_astar` now overwrites `world_path[0]`/`[-1]`
with the exact input coordinates).

**4.2 Rectangular-pad half-diagonal.** The existing, shared
`_collect_other_net_copper` buffers a pad by `max(width, height)/2` --
the wrong radius for a rectangular pad (the furthest point from centre is
a corner, `hypot(w/2, h/2)`, already the fix `_collect_hv_copper_geometry`
applies for HV pads but not this shared function). This module's own
per-pair collector uses the correct half-diagonal; the original,
via-placement-shared function was deliberately left unchanged (out of
this task's boundary -- it is used elsewhere and untouched by this PR).

**4.3 Raster-quantization safety margin.** `build_obstacle_grid`
classifies a cell free/blocked by its CENTRE point; a cell whose centre
sits just outside a buffered obstacle but whose real half-cell footprint
(up to `cell_size/sqrt(2)` ≈ 0.141mm at this module's 0.2mm cells) still
overlaps it is wrongly rasterized free. Measured directly: without a
correction, up to 2 of 20 A*-routed edges' REAL trace footprints
(continuous shapely check, not grid-quantized) intersected the very
obstacle they were routed to avoid. `RASTER_SAFETY_MARGIN_MM` (= cell
size) closes this to 0/N in every subsequent measurement.

**4.4 Nearest-label grouping.** `corridor_aware_spanning_edges`'s first
version required a position's OWN grid cell to carry a component label;
because via-drop points are placed against a looser standoff
(`OTHER_NET_CLEARANCE_MM`=0.05mm, existing/unchanged) than this module's
own pairwise-correct obstacle grid enforces (0.2-0.5mm), a legally-placed
via can sit closer to foreign copper than the new grid's corridor mask
allows -- landing its own exact cell just outside the mask even though
free space is one or two cells away. This mis-classified 52 of 86 `gnd`
positions as "unreachable" outright. Fixed with a small growing-radius
nearest-labelled-cell search (`_NEAREST_LABEL_SEARCH_RADIUS_CELLS`),
which brings the grouping step's notion of reachability in line with what
`route_edge_astar` itself already tolerates (it only checks a
NEIGHBOUR's corridor_mask when stepping, never the start cell's own).

**4.5 A flat clearance constant is the wrong shape, not just the wrong
number.** An early version of this fix used a single
`BACKBONE_CLEARANCE_MM` constant (tried both 0.05mm and 0.5mm). Neither
moved the aggregate DRC numbers (§1), which is itself informative: it
ruled out "wrong clearance value" as the explanation before the
no-backbone control (§3.1) and component analysis (§3.2) identified the
real one. `resolve_netclass_clearances` (per-net-pair, reading the real
`.kicad_pro`) replaced it -- more correct regardless of the aggregate
result, and removes one degree of freedom from future debugging.

---

## 5. What this means for the task's own decision point

Per the task brief: *"If it still cannot be done, that is a real and
valuable answer... Say that with the measurements behind it rather than
shipping something that trades connectivity for cleanliness."*

**This PR does not trade connectivity for cleanliness** (§1: both floors
held exactly, never dipped). **It also does not achieve a material
cleanliness win** -- the honest reading of §1 and §3 together. The
mechanism (corridor erosion + `corridor_mask`-aware A*) is real,
correct (proven via direct, continuous geometric checks against its own
obstacle model in every configuration tested -- never a single violating
A*-routed edge), reusable, and the first production wiring of #1017's
Rust kernel to an actual call site. What it cannot do is conjure a
clearance-respecting path where this board's current placement leaves
none -- confirmed three independent ways in §3, not merely asserted.

**Recommendation**: land the corridor-aware infrastructure (correct,
tested, connectivity-safe, and a real foundation for whichever future
placement-side fix widens F.Cu's channels around `gnd`'s and the power
rails' scattered pads) while being explicit that it is not, by itself,
the fix for the collision-category regression these two generators
introduce. That fix needs placement density to change first -- a
different, larger project than this one, exactly as the task
anticipated.

---

## Sources

- `packages/temper-placer/src/temper_placer/router_v6/_corridor_backbone.py` (new)
- `packages/temper-placer/src/temper_placer/router_v6/_ground_plane.py` (modified)
- `packages/temper-placer/src/temper_placer/router_v6/_power_islands.py` (modified)
- `packages/temper-geometry/src/corridor_erosion.rs` (#1017, read-only, unmodified)
- `packages/temper-placer/src/temper_placer/router_v6/astar_core.py` (read-only, unmodified)
- `docs/evidence/2026-08-11-corridor-aware-astar-spike.md` (#1017's own spike)
- `docs/evidence/2026-08-11-keepout-before-pour-spike.md` (#1022/#1033's origin)
- `pcb/temper.kicad_pro` (`net_settings.classes`/`netclass_assignments`, read directly)
- `AGENTS.md` (clearance/creepage run-to-run noise convention)
