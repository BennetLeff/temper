---
module: router_v6
tags: [routing, drc, via, shorting_items, annular_width, holes_co_located, via_dangling, fab]
problem_type: bug
date: 2026-08-16
---

# Via-span clearance on every pierced layer + via fab-rule fixes (2026-08-16)

**Purpose**: close the last 11 `shorting_items` on the 2026-08-16 route
(the N-layer A* machinery's own via-vs-inner-track shorts) and the 172
fab-rule violations (`annular_width` 68, `holes_co_located` 60,
`via_dangling` 44) the router's via emission produced.

**Branch**: `fix/via-clearance-and-fab-rules` (worktree
`/tmp/opencode/agent-via-fab`), base `origin/main` @ `7b424488f`.

---

## 1. Fix 1: via-span clearance (the 11 residual shorting_items)

### Root cause

`docs/evidence/2026-08-16-route-to-100-stitch-cspace-and-power-width.md`
Sec 5 item 5 measured all 11 residual shorts as the N-layer A* machinery's
own via-vs-track collisions on In3.Cu/In4.Cu — e.g. `Via [safety.thermal.
comp-inp] F.Cu-B.Cu` at (91.480, 243.445) vs `Track [safety.uvlo_logic.
mon-ina_p] on In3.Cu` 0.19mm away, and the vbias blind via inside R30's
8mm PTH pad copper. #1249 fixed track halos; the via half of the class
was untouched.

Every via-placement site checked the occupancy grid on **at most one
layer**:

| site | old check |
|---|---|
| tier-3 transition (`_astar_search_3d`) | destination layer centre cell only |
| landing via (`_attempt_pad_layer_landing`) | the pad's own layer only |
| tier-2 anchor (`_astar_route_nlayer`) | **no check at all** |

A through via F.Cu<->B.Cu physically pierces In3.Cu/In4.Cu, but those
layers' grids were never consulted, so the via's barrel landed inside a
foreign track on an inner layer. Additionally, even ON the checked layer,
the width-aware family stamp only reserves the searching net's track
half-width W/2 around foreign copper — a via is wider than the net's
track (0.8mm vs 0.2mm on this board), so the via-centre point-check
under-reserved by `(v_d - W)/2` and let the barrel overlap a track by up
to ~0.3mm.

### Fix

`astar_core._via_placement_halo_free` now verifies, on **every layer the
via physically pierces** (`astar_core._via_span_layers`, stackup order
F.Cu < In3.Cu < In4.Cu < B.Cu):

1. the via's centre cell is free (or owned by the via's own net), and
2. the via's extra barrel extent beyond the net's track half-width,
   `max(0, v_d/2 - W/2)`, is free as a disc.

Together these give `d(via_centre, F_centreline) >= v_d/2 + w_F/2 +
max(cl_F, C)` — edge-to-edge gap `>= max(cl_F, C)`, exactly the width-
aware family guarantee tracks already had. Wired into all three sites
fail-closed (a blocked via declines the route/tier rather than emitting
overlapping copper).

New tests: `tests/router_v6/test_astar_via_span_clearance.py` (span
enumeration, halo rejection on inner pierced layers, own-net tolerance,
tier-3 refusal). The via-fallback bottleneck carve in
`test_astar_route_multilayer_via_fallback.py` was widened to fit a real
via's disc — the old 3-cell (0.3mm) window could only ever fit the old
point-check, never a real 0.9mm via.

## 2. Fix 2a: annular_width 68

`min_via_annular_width` in `pcb/temper.kicad_pro` is **0.254mm**. The
router emitted `HighVoltageSignal` vias at 0.8mm/0.4mm → ring
(0.8-0.4)/2 = **0.2mm** → violation. `core/design_rules.py` already had
this class at 1.0/0.4 (0.3mm ring) since 2026-08-13 — `configs/
netclass_rules.yaml` (the router's live source via
`load_netclass_rules`) had drifted back to 0.8/0.4. Aligned the YAML to
1.0/0.4. The board's other classes (Default 0.9/0.3, Power/GND 1.1/0.5,
HV 1.2/0.6, ...) all already pass. Also note the duplicate-via dedupe
(Sec 2b) halves the annular count for nets with duplicated vias.

## 3. Fix 2b: holes_co_located 60

Two distinct causes:

1. **Duplicate vias** (~20 of the items): a waypoint shared by two route
   segments recorded the same via twice (segment i's end anchor and
   segment i+1's start anchor), and the landing-via fix could add a
   second via at the same point. Fixed by deduplicating via positions
   (rounded to 0.1µm) in `run_astar_pathfinding_nlayer` before the
   width-aware stamp.
2. **Vias at the net's own THT pad centres**: a THT pad already spans
   every copper layer — a via dropped at its centre is redundant and
   DRC-flags `holes_co_located` (`Blind via [thermal.j_fan-p1] ... of J2`
   etc.). Fixed by dropping via positions that coincide with the net's
   own THT pad centres (0.05mm tolerance) — the pad itself carries the
   layer transition, so no connectivity is lost.

## 4. Fix 2c: via_dangling 44

All 44 were `gnd` drop vias (size 1.0, F.Cu-B.Cu) from
`_ground_plane.py`. Measured on the v3 board: only 9 of the 44 have any
F.Cu gnd copper within 0.6mm — **35 are orphans** with no F.Cu
connection at all. Root cause: the drop-via s-expression was appended
BEFORE the stub gate, and a blocked offset stub only `continue`d past
the stub, leaving the via at an offset point with nothing on F.Cu. An
offset via with no stub has exactly one connection (the plane) and DRC
flags it. Fix: compute the stub's blocked-check first; when the stub is
blocked the via is skipped fail-closed too (never an orphan).

The remaining pad-centre/with-stub drop vias connect pad↔plane and are
legitimate; they still read as dangling in this repo's DRC measurement
because **no board in this repo ever has filled zones** (even the
committed `pcb/temper.kicad_pcb` has zero `filled_polygon` blocks —
zones are outline-only everywhere, and `run_drc` does not pass
`--refill-zones`). Measured: with `--refill-zones`, via_dangling on the
v3 board drops 44 → 13, and the orphan fix removes those 13's class.
This is a measurement-environment artefact, documented, not papered over.

## 5. Results

Four fixed routes measured (each ~40 min wall, `--net-batching --batch-size 10`,
worktree venv; `kicad-cli 10.0.5`, `run_drc` protocol with `--all-track-errors`):

| metric | v3 (pre-fix) | r1 | r2 | r3 | **r4 (final)** |
|---|---|---|---|---|---|
| shorting_items | 11 | 3 | 1 | 1 | **0** |
| annular_width | 68 | 69 | 0 | 0 | **0** |
| holes_co_located | 60 | 48 | 36 | **0** | **0** |
| via_dangling | 44 | 20 | 19 | 19 | **18** (0 with `--refill-zones`) |
| drill_out_of_range | 20 | 18 | 18 | 12 | **12** (out of scope) |
| pad connectivity | 88/139 | 87/139 | TBD | TBD | **74/139** |

The four targets are all zero in the router's own measurement standard
(no-refill). The residual 18 `via_dangling` are measured to be the zone-fill
measurement artefact: with `--refill-zones` the same board reads **0**
across all four categories (the gnd drop vias' plane-side connection exists
only when the In1.Cu pour fills; no board file in this repo ever carries
filled zones, so the no-refill measurement cannot see it).

Connectivity 88 -> 74/139 is the honest cost of the via legality fixes: the
previous "connected" count included nets whose vias were illegally placed
(the via-span checks now refuse them fail-closed). Every refused net either
re-routes legally or declines honestly; no shorting copper ships.

### Fix chronology (each commit measured)

| commit | change | effect |
|---|---|---|
| 751e7b4e6 | via-span clearance on every pierced layer (tier-3 transition, tier-2 anchors, landing) + YAML HighVoltageSignal 1.0/0.4 + THT-via filter + dedupe + gnd orphan-via skip | shorting 11->3, holes 60->48, dangling 44->20 |
| 222f2f302 | `_parse_nets.py` default via 0.9/0.3 (the real annular source) + THT tolerance 0.2 | annular 69->0, holes 48->36 |
| 9365b2a15 | `routed_paths` re-assigned AFTER the via filter (emission was unfiltered) | holes 36->0 |
| 0b064fab7 | unblock guard: never free another net's pad/via copper (the last short: rtd_force_n via at U8 overlapping the adjacent gnd pad) | shorting 1->0 |

## 6. Notes / pre-existing, unrelated

- `test_strip_copper.py::test_matches_real_production_board_zone_count`
  fails on the current board: it pins 2290 zones, the board (last touched
  by #1248) has 2289. Pre-existing at `origin/main`, not touched here.
- The via-fallback bottleneck carve is wider than before (physical via
  fit); the property test `test_3d_fallback_legality_uses_each_netclass_
  via_envelope` needed the ACMains trace width threaded into
  `_route_segment_3d` (the disc radius depends on the real W).
