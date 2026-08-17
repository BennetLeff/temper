---
title: "Creepage-aware obstacle halos — per-class C-space rings + pair-charged stamps; pad<->track creepage 194 -> 6"
date: 2026-08-16
module: router_v6
tags: [router, creepage, cspace, drc, width-aware]
problem_type: fix
---

# Creepage-aware obstacle halos in the N-layer router

## 1. Problem

The width-aware C-space (#1261, `docs/evidence/2026-08-16-width-aware-cspace.md`)
reserves `W/2 + clearance` around every static obstacle and stamps routed
copper at `w_F/2 + max(cl_F, C) + W/2`. That halo is **clearance-only**: an
HV pad reserves just 2.0 mm from an LV track even though the DRU
(`scripts/generate_kicad_dru.py`, RULE 4/4c) judges the pair at **12.6 mm**
PD3 reinforced creepage. The router therefore emits tracks that satisfy
DRC clearance but violate DRC creepage — measured as **194 pad↔track
creepage violations** on the 2026-08-16 current-main batched route (recipe
below), the same family the handoff's ~311 total recorded.

The obstacle map (`build_obstacle_map`) is a unioned MultiPolygon per layer
with **no per-net-class attribution**, so a single uniform erosion cannot
express "12.6 mm around HV pads, 0.2 mm around LV pads" — the class of each
obstacle must be tracked.

## 2. Fix

Three coordinated changes (`fix/creepage-and-merge`, commits
`453885ba6` + `136999235`):

1. **`obstacle_map.py`**: refactored `build_obstacle_map`'s geometry walk
   into a shared `_iter_obstacle_items` generator (same items, same order —
   union output bit-identical, verified by `test_obstacle_map.py` /
   `test_obstacle_map_pbt.py`), and added `build_class_obstacle_map`, which
   groups the SAME items by net class via
   `design_rules.get_rules_for_net(net).name`. Class grouping is a pure
   post-process, so it cannot drift from the unioned map. Items with no net
   (keepouts, unconnected pads) land under `None`.

2. **`occupancy_grid.py`**: `build_occupancy_grid` gained an optional
   `check_area` parameter for a caller-computed free area; the grid frame
   (origin/cell size/dims) still derives from `available_area`, so layout
   is identical to the uniform-erosion path. Zero-area LineString/Point
   artifacts left by the annulus carve are filtered (polygon-only) before
   rasterization.

3. **`_astar_nlayer.py`**:
   - family signature becomes `(width, floored_clearance, net_class)` —
     HighVoltage and HighVoltageTank share (5.0, 2.0) but need different
     obstacle spacing (10.0 mm tank↔HV functional creepage vs 0);
   - each family grid erodes per obstacle class:
     `W/2 + max(C, creepage(routing_class, obstacle_class))` instead of
     `W/2 + C`, by carving the pair-creepage annulus
     `buffer(W/2 + creep) - buffer(W/2 + C)` around that class's obstacles;
   - routed-copper stamps charge
     `max(cl_F, C, creepage(F_class, family_class)) + W/2` via
     `_stamp_clearance`.

Creepage values come from `zone_pour_creepage.default_creepage_table()`,
generated from the SAME DRU rules kicad-cli judges by (HV↔LV 12.6, tank↔HV
10.0, same-class/LV↔LV 0.0). Class obstacles are built from the board's
pads/escape vias/zones/tracks/vias with their nets; no-net items keep the
clearance-only halo (creepage is a net-to-net constraint). Without a pcb
(synthetic fixtures) behaviour is byte-identical to #1261.

## 3. Measurement

Both routes: `scripts/route_board.py --net-batching --batch-size 10`, board
`pcb/temper.kicad_pcb` @ `8504c7a73` (current main, post #1264/#1265),
**same DRU** (`generate_kicad_dru.py`, PD3/12.6 mm), kicad-cli 10.0.5,
`run_drc` protocol (`--all-track-errors`, sidecar-copied project).

| metric | baseline (main, no change) | creepage-aware (this fix) | Δ |
|---|---|---|---|
| pad-connected (fixed audit) | 88/139 | 57/139 | −31 |
| tracks / vias / zones | 5728 / 207 / 68 | 3279 / 164 / 138 | — |
| DRC errors total | 1208 | 629 | −579 |
| **creepage total** | **314** | **167** | **−147** |
| **creepage pad↔track** | **194** | **6** | **−188 (97%)** |
| creepage track↔track | 7 | 0 | −7 |
| creepage track↔via | 11 | 2 | −9 |
| creepage pad↔pad (placement-fixed) | 74 | 157 | +83 |
| creepage pad↔track per 1000 tracks | 33.9 | 1.8 | −95% |
| clearance | 499 (cap) | 210 | — |
| shorting_items | 62 | 44 | −18 |

### Reading the numbers honestly

- **pad↔track creepage 194 → 6 (−97%)** is the fix's headline: tracks no
  longer thread within creepage of opposite-class pads. Normalized per 1000
  tracks it is 33.9 → 1.8 (−95%), so the drop is not an artifact of fewer
  routed tracks.
- **pad↔pad went 74 → 157** on IDENTICAL pad placement. This is a DRC
  reporting artifact, not new placement violations: with tracks pushed back,
  pairs that the baseline reported as `Pad ↔ Track` (track present) now
  report as `Pad ↔ Pad` (track absent). The union (pad↔pad + pad↔track)
  fell 267 → 163.
- **Connectivity 88 → 57** is the honest cost of enforcement, not a routing
  regression: **all 33 lost nets carried a baseline creepage violation**.
  The halos refuse to emit copper into creepage-violating configurations;
  those nets either reroute at a compliant distance or decline honestly
  (fail-closed) instead of producing DRC-violating tracks. This matches the
  handoff's PD3 finding (`docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`):
  the placed board cannot meet 12.6 mm without re-placement; the router now
  stops papering over it.
- Baseline `clearance` sits at KiCad's 499 cap, so its 314 creepage count is
  complete (creepage is NOT capped — 314 > 199), but the clearance total is
  understated. The creepage comparison is unaffected.

## 4. Tests

- `test_astar_nlayer.py` (27 pass): family signature 3-tuple contract; the
  12.6 mm HV ring carved into an LV family (and NOT into an HV family); the
  10.0 mm tank↔HV ring with distinct HighVoltage/HighVoltageTank families;
  `_stamp_clearance` pair-charged stamps (4.5 mm same-class vs 12.7 mm
  HV→Signal).
- `test_obstacle_map.py` + `test_obstacle_map_pbt.py` (8 pass): refactored
  union output byte-identical.
- `test_occupancy_grid.py` + `test_occupancy_grid_pbt.py` (49 pass incl.
  Rust differential): `check_area` path + artifact filtering.
- CI-relevant router_v6 differentials/PBT (119 pass): unchanged behaviour
  without a pcb.

## 5. Artifacts

- Routed boards: `/tmp/opencode/baseline-creepage-route.kicad_pcb` (main),
  `/tmp/opencode/creepage-aware-route.kicad_pcb` (this fix), logs beside
  them. DRC: same generated DRU sidecar for both.
- No `pcb/temper.kicad_pcb` touched; no DRC ceiling touched; no check
  weakened.
