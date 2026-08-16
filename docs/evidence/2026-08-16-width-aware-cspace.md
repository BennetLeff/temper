<!-- provenance: commit=2a161284a dirty=false -->

<!-- worktree /tmp/opencode/agent-cspace, branch fix/router-width-aware-cspace, based on fdbe0a6ad (origin/main). kicad-cli 10.0.5. Every number in this document was measured live with `temper_placer.validation._drc_api.run_drc`'s protocol (kicad-cli pcb drc --all-track-errors --format json, project sidecar resolvable). -->

# Width-aware C-space: per-net-width occupancy-grid families in the N-layer A* router

**Date:** 2026-08-16
**Branch:** `fix/router-width-aware-cspace`
**Disposition: code change lands with this document** — the fix that
`docs/evidence/2026-08-11-track-width-shorting-root-cause.md` §3 correctly
refused to ship standalone (drawing wide copper on a centerline the router
only ever cleared for a 0.25mm trace) once the widths became real.

## 1. The defect

The N-layer A* path (`_astar_nlayer.py`, live for every board with >2
routable signal layers — the production 6-layer board has 4) built its
occupancy grids ONCE with:

* a **static** obstacle layer eroded by `default_trace_width_mm / 2`
  = **0.1mm** around pads, vias, the board edge and keepouts, for every
  net regardless of width, and
* **dynamic** routed-copper stamps at the flat board default
  (`trace_width = default_trace_width_mm` = 0.2mm, `clearance =
  default_clearance_mm` = 0.2mm → 0.3mm radius around a centerline).

Meanwhile Stage 4.4's `assign_trace_widths` emits the netclass SSOT's real
widths — up to **5.0mm** for `HighVoltage` (the 2026-08-13 current re-scope
`docs/evidence/2026-08-13-netclass-current-scoping.md`). A 5.0mm track
occupies 2.5mm on each side of its centerline; the C-space reserved 0.1-0.3mm.
The A* pathfinder therefore cannot see the actual copper extent and routes
tracks through each other and through pads.

Measured on the 6-layer routed board (2026-08-15, current main):
**204 `shorting_items`**, of which the 5.0mm HighVoltage net `w1_1` alone
accounts for **120** (62 pad↔track, 39 track↔track, 19 pad↔track vs PTH
pads). Fresh re-measurement on a current-main route produced in this
session (2026-08-16, `/tmp/opencode/definitive-route.kicad_pcb`):
**201 `shorting_items`** = 97 pad↔track (74 SMD + 23 PTH), 46 track↔track,
51 track↔via, 7 via↔other.

This is the exact failure mode `2026-08-11-track-width-shorting-root-cause.md`
predicted would follow the width-label fix ("drawing 2–3mm-wide copper on a
centerline the router only ever cleared for a 0.25mm trace") — that
document's §3 width-patch experiment moved `shorting_items` 0 because the
committed board's 9 HV nets were all *undersized* (0.25mm); once the widths
became real, the shorts materialised.

## 2. The fix

One occupancy-grid family per distinct `(trace_width, floored_clearance)`
signature among the nets a run actually routes (`_build_width_families` in
`_astar_nlayer.py`). A net of width W and clearance C searches
`family[(W, C)]`, whose C-space is built so that:

* **static obstacles** (pads, vias, board edge, keepouts) are eroded by
  `W/2 + max(C, 0.2)` — the searching net's own half-width plus the DRC's
  0.2mm track-involving floor (`clearance_floor.DEFAULT_ROUTING_CLEARANCE_MM`,
  RULE 10 of `scripts/generate_kicad_dru.py`). Its centerline can never come
  within its own copper extent of a static obstacle → no pad↔track shorts;
* **routed foreign copper** is stamped into every family at
  `w_F/2 + max(cl_F, C, 0.2) + W/2` — the marked net's half-width plus the
  *searching* family's half-width plus a clearance floor. The edge-to-edge
  gap between the marked net and any net searching that family is
  `>= max(cl_F, C, 0.2) > 0` **by construction**, order-independent (the same
  per-family structure `profile_grids.py` gives the legacy 2-layer path,
  extended here to the static obstacle layer);
* **vias** are stamped at the routed net's real `via_diameter_mm` (was a
  hardcoded 0.6mm — a 1.2mm HV via under-reserved by 0.3mm per side).

The per-family static erosion rebuilds grids from the Stage-2
`RoutingSpace` objects (new `routing_spaces=` parameter threaded from
`_pipeline_route.py`). GEOS `buffer(-x)` is cheap (0.04-0.1s/layer) and the
containment rasterisation is the 2026-08-15 Rust scanline
(`docs/evidence/2026-08-15-rust-obstacle-map-integration.md`), so a 4-layer,
~7-family rebuild adds seconds to a ~10-minute route. When `routing_spaces`
is absent (synthetic test fixtures), a single identity family over the
caller's grids preserves the historical behaviour exactly.

The clearance is floored at 0.2mm because RULE 10 grades *any* pair where
either side is a track at >= 0.2mm, so a class declaring less (FinePitch
0.1mm) still needs the floor charged; flooring also merges classes that
behave identically once floored (Signal 0.15 and Default 0.2, both 0.2mm
wide) into one family.

### Why this is safe (short-free by construction)

For a routed net F (width w_F, clearance cl_F) and any net N searching
family (W, C):

* static: N's centerline is kept >= W/2 + C from every static obstacle
  edge → N's copper edge is >= C > 0 from it;
* dynamic: N's centerline is kept >= w_F/2 + max(cl_F, C) + W/2 from F's
  centerline → the copper edge-to-edge gap is
  `w_F/2 + max(cl_F,C) + W/2 - w_F/2 - W/2 = max(cl_F, C) >= 0.2mm > 0`.

The grid rasteriser (`occupancy_raster.rs`) only ever reserves *more* than
the nominal radius (`expansion = ceil(radius/cell)`), so quantization adds
margin, never removes it. Old behavior for same-width pairs is preserved or
tightened (two 0.2mm Default nets: radius 0.1+0.2+0.1 = 0.4mm, exactly the
legacy single-grid charge).

### Deliberately NOT changed

* The **pair-clearance refinement** (`pair_clearance.py`'s generated DRU
  table, which the legacy path uses via `profile_grids`) is not wired into
  the N-layer path here: the charged floor is the pair members' own
  clearances, not the per-pair table value, so cross-domain pairs can still
  produce *clearance* violations (never shorts). Adopting the pair table in
  the N-layer path is the natural follow-up.
* `pcb/temper.kicad_pcb` is untouched (route output goes to a scratch path;
  DRC measured there).
* No ceiling, clearance, creepage, or DRU threshold was changed.

## 3. Measurement

### Before (current main, this session)

`/tmp/opencode/definitive-route.kicad_pcb` — a full `route_board.py
--net-batching --batch-size 10` run produced by current main before this
fix (another session's run, 2026-08-16 09:06-09:20), DRC'd with
`kicad-cli pcb drc --all-track-errors`:

| category | count |
|---|---|
| shorting_items | **201** |
| clearance | 510 |
| creepage | 484 |
| track_width | 199 |
| hole_clearance | 201 |

shorting breakdown: 97 pad↔track (74 SMD + 23 PTH), 46 track↔track, 51
track↔via, 7 via↔other.

(Cross-check: the 2026-08-15 6-layer routed output measured 204, with
`w1_1` — 5.0mm HighVoltage — accounting for 120.)

### After

Full `route_board.py --net-batching --batch-size 10` route with this fix
(`/tmp/opencode/after-width-aware-route.kicad_pcb`, wall 1069s; the same
recipe as the before run) + DRC:

| category | before | after | delta |
|---|---|---|---|
| shorting_items | 201 | **183** | **−18** |
| clearance | 510 | 501 | −9 |
| creepage | 484 | (see raw) | — |
| track_width | 199 | (see raw) | — |
| hole_clearance | 201 | 73 | −128 |
| tracks_crossing | 11 | 37 | +26 |

The headline 201 → 183 understates the fix, because the remaining shorts
split into two mechanisms with different owners:

* **A*-routed copper (what this fix governs): 52 → 13 (−75%)**, and the
  two categories the width defect produced directly — track↔track and
  pad↔track — went **35 → 0 and 8 → 0**. The 13 survivors are all
  track↔via micro-segments at route termini, the documented same-run
  via-disc-vs-copper placement gap
  (`docs/evidence/2026-07-30-router-copper-shorts.md`), not a
  width-agnostic residue.
* **Zone-stitch backbones** (`_zone_pour_stitch.py`, the pad-to-pad
  straight-line emitter that connects pours and consults NO C-space at
  all, before or after this fix): 149 → 170 (churn — the stitch's fixed
  straight lines cross a differently-routed A* layout; `gnd`'s 55mm
  single-segment backbones alone account for 99 shorts in the after
  board). This is a separate, pre-existing defect this task does not
  claim to fix; its own fix is making the stitch consult the same
  C-space, scoped as a follow-up.

Cost: completion 76/106 → 66/106 routed, 92/139 → 88/139 fully
pad-connected. This is the honest price of the C-space now reserving the
real copper extent: the 10 nets that no longer route are the ones whose
previous "routes" threaded 0.1-0.3mm from obstacles a 0.2-5.0mm track has
no right to occupy. `unconnected_items` 241 vs the CI ratchet bar 463
(unchanged, comfortably under).

The CI gate `test_production_board_routing_drc_regression`'s shorting bar
(178) was seeded against the monolithic-path artifact and was already red
on current main (net-batching measures 201); this fix moves the same
recipe 201 → 183 toward the bar without touching it. Re-baselining that
bar is an owner call with its own N>=5 provenance block, per that test's
own docstring.

## 4. Tests

`tests/router_v6/test_astar_nlayer.py` grows a width-aware C-space section:

* `_width_family_signature` floors sub-0.2mm clearances (FinePitch 0.1 →
  0.2) and merges equivalent classes;
* `_family_static_inflation` = W/2 + C;
* `_build_width_families` erodes the static layer per width (identical
  frames, different free area) and is identity without `routing_spaces`;
* end-to-end: a 0.2mm net routed down x=20 stamps a 4.6mm-radius halo in
  the 5.0mm family (0.1 + max(0.2,2.0) + 2.5) but only 0.4mm in its own —
  verified at the driver's real `_mark_route_blocked` call sites — and the
  5.0mm net attempting to cross it declines honestly (control: it routes
  fine when the narrow net's copper is absent);
* `_mark_route_blocked` stamps vias at the net's real `via_diameter_mm`
  (default 0.6 preserved for legacy callers).

Suite: 24 passed in `test_astar_nlayer.py`; 90 passed across the
nlayer/astar-pathfinding/pair-clearance/occupancy-grid differential suites;
12 passed (2 skipped) across the stage-4 parity suites; 29 passed in
router-integration + pipeline-differential. No regressions observed.

## 5. What was and wasn't verified

Verified: the defect mechanism (per-net width emitted vs 0.1-0.3mm C-space,
measured 201 shorts on a current-main route); the family construction; the
per-family stamp radii; the decline-vs-control behavior; the after-route DRC
(A*-routed shorts 52 → 13, track↔track and pad↔track to zero); the full
existing test surface stays green.

Not verified / outstanding: the pair-clearance table in the N-layer path
(follow-up — cross-domain pairs can still produce clearance violations,
never shorts); the zone-stitch backbone's total lack of C-space
consultation (pre-existing, quantified above at ~150-170 shorts on this
board, separate follow-up); the residual track↔via terminus micro-segments
(the 2026-07-30 same-run via-gap, ~13); re-baselining
`test_production_board_routing_drc_regression`'s shorting bar for the
net-batching artifact (owner call).
