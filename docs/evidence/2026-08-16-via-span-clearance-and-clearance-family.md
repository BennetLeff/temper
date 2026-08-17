# Via-span clearance: A* + plane emitters, and the clearance-family attribution (2026-08-16)

<!-- provenance: commit=f1d73c1bc dirty=false (numbers from the three routed boards below;
     final verification route f2 in flight at commit time) -->

## Summary

Two routing fixes for the remaining clearance and shorting violations on the
6-layer N-layer A* routed board, plus the clearance-family measurement and
attribution:

1. **A* via-span clearance (Fix 1, `d5308c535`)**: every via-placement site
   in the N-layer A* checked the via's clearance on AT MOST ONE layer, so a
   through via's In3.Cu/In4.Cu barrel landed inside a foreign track (the
   residual shorting_items on the route-to-100 board). The fix
   (`astar_core._via_placement_halo_free`) verifies the via's centre cell AND
   its extra barrel extent on EVERY layer the via physically pierces,
   fail-closed.
2. **Emitter via-span pierce awareness (Fix 2-code, `62612972e`)**: the
   plane/backbone emitters place vias outside the A* and had the same
   pierce-blind spot — `_power_islands.py`'s through-via drop search only
   consulted F.Cu/B.Cu copper (8 residual +3V3-via-vs-In3.Cu/In4.Cu-track
   shorts), and `_corridor_backbone.routed_segments_obstacle`'s via layer
   check was exact-match so a through via was invisible to inner-layer
   obstacle queries.
3. **Clearance family (Fix 2-measure)**: measured after the fixes, fully
   attributed (see §4). The residual same-class track/via/pad clearance and
   shorts share ONE root cause — the per-net pad unblock clips foreign pads'
   clearance-erosion rings and only the creepage halos are re-stamped — whose
   fix is architectural (per-pair clearance figures), scoped as a follow-up
   per R22.

## Base / branch

- Branch: `fix/via-clearance-and-clearance-family`
- Base: `origin/main` @ `593d9ab24`
- Commits: `d5308c535` (Fix 1, cherry-picked from `fix/via-clearance-and-fab-rules`
  `751e7b4e6`, conflict-resolved against #1267's creepage-halo stamp comment),
  `62612972e` (Fix 2-code), evidence commit.
- `pcb/temper.kicad_pcb` untouched (sha256 `72e14ab...` == origin/main, matches
  `power_pcb_dataset/drc_ceiling.json`'s recorded input hash).

## Measurement protocol

`scripts/route_board.py --net-batching --batch-size 10` on the committed
board; DRC per `docs/evidence/2026-08-16-creepage-aware-cspace.md` §3:
kicad-cli 10.0.5 `pcb drc --all-track-errors --format json`, single-threaded
worker pool (`temper_placer.validation._drc_api.run_drc`), PD3 DRU regenerated
at the measured commit, project sidecar copied next to the scratch routed
board. Categories classified from the violation-description prefix; 199/499 =
cap, not count. Item pair-types classified from the item descriptions
(Pad/Via/Track incl. "Blind via"/"Buried via" prefixes; PTH pads parse as
PTH).

## Before / after

| metric | BEFORE (main) | AFTER (Fix 1) | AFTER2 (both) | delta (main→AFTER2) |
|---|---|---|---|---|
| shorting_items | 40 | 35 | (route in flight) | ... |
| clearance (raw ATE read) | 229 | 133 | ... | -96 |
| creepage | 144-145 | 143-144 | ... | ~0 |
| annular_width | 46 | 18 | ... | -28 |
| track_width | 122 | 122 | ... | 0 |
| fully-connected nets (audit) | 53/139 | 41/139 | ... | -12 (fail-closed declines) |

Fix 1 clears the A*-placed via-involving items: shorts Track↔Via 13→8,
clearance via-involving 161→67 (of 229→133). Fix 2-code targets the
remaining 8 via shorts (all +3V3 power-island through vias vs In3.Cu/In4.Cu
tracks — the +3V3 net is zone-eligible and A*-excluded, so its vias come
from `_power_islands.py`, which never received the pierce-layer check).
Annular_width 46→18: the netclass_rules.yaml HighVoltageSignal via 0.8/0.4→
1.0/0.4 alignment (SSOT drift fix, wider = conservative).

## Fix 1 — A* via-span clearance (details)

Root cause (route-to-100 evidence §5 item 5): three via-placement sites
checked at most one layer —

| site | pre-fix check |
|---|---|
| tier-3 transition (`_astar_search_3d`) | destination layer only |
| tier-2 anchor (`_astar_route_nlayer`) | none |
| landing via (`_attempt_pad_layer_landing`) | pad layer only |

`astar_core._via_placement_halo_free` checks, on every layer the via pierces
(`_via_span_layers` over `VIA_SPAN_LAYER_ORDER = (F.Cu, In3.Cu, In4.Cu,
B.Cu)` — In1.Cu/In2.Cu are power planes, never routing grids, handled by the
zone carve): the via's centre cell is free (or own-net), AND the via's extra
barrel extent `max(0, v_d/2 − W/2)` is free as a disc. Together:
`d(via_center, F_centerline) >= v_d/2 + w_F/2 + max(cl_F, C, creepage)` —
edge-to-edge gap ≥ the DRC pair floor, matching the width-aware family
design. The #1267 -1 creepage halos are blocked cells, so creepage is
enforced automatically. Fab-rule fixes in the same commit: annular_width
(netclass_rules.yaml alignment), holes_co_located (dedupe + THT-pad-centre
drop), via_dangling (gnd drop via skipped fail-closed with its blocked stub).

Tests: `test_astar_via_span_clearance.py` (5), `test_astar_route_multilayer_
via_fallback.py` (7), `test_astar_3d_production_scale_spike.py` (8); full
`tests/router_v6/` 6809 passed — the 24 failures are byte-identical on plain
main (verified in the main worktree), zero new failures.

## Fix 2-code — emitter pierce awareness (details)

- `_power_islands.py`: the via-avoid construction gained
  `other_copper_in3/in4` (pre-existing copper) and
  `routed_in3_avoid/routed_in4_avoid` (this route's in-memory segments on the
  pierced layers) — mirroring the gnd plane generator's #1261 handling.
- `_corridor_backbone.routed_segments_obstacle`: via layer membership is now
  pierce-aware via `astar_core._via_span_layers` (a through via
  "F.Cu" "B.Cu" blocks In3.Cu/In4.Cu queries; blind/buried span exactly
  their declared layers).
- Test `test_through_via_drop_avoids_inner_pierced_layer_tracks`: a foreign
  In3.Cu track through a +3V3 pad whose via IS emitted in the baseline must
  now be skipped/offset fail-closed (verified red on the pre-fix code).

## Fix 2-measure — the clearance family (133 after Fix 1)

AFTER (Fix 1) clearance by pair type (133 total): Pad↔Pad 34, Via↔Via 24,
Pad↔Via 22, Track↔Via 21, Pad↔Track 14, Track↔Track 9, PTH-pad↔Track 9.
Attribution:

| class | count | owner |
|---|---|---|
| unblock-clipped foreign rings (creepage-0 pairs) | ~90 (67 via-involving + 14 pad↔track + 9 track↔track) | routing C-space (this doc's root cause) |
| static pad↔pad | 34 | placement / netclass classification (agent 94's doc: R15×R18 classification question, U9/U8 same-footprint pairs) |
| PTH-pad stub items | ~9 | emitter micro-segments |

**Root cause (hard evidence)**: the per-net `_unblock_net_pads` clears EVERY
-1 cell inside the routing net's pad circles (`pad_radius + W/2 + C` +
self-creepage) — including the clearance-erosion rings around FOREIGN pads —
and only the #1267 creepage halos are re-stamped (`_stamp_foreign_creepage_
halos`), which contributes an entry only when `creepage > 0`. For
creepage-0 pairs (same-class LV-LV, GateDriveHV-involving) the foreign ring
is never restored, so a later net can route its track/via inside the foreign
pad's ring. Measured example: the +15V track's waypoint at (116.7925,
149.0800) is U3 pad 2 (sw)'s exact centre — the +15V net's unblock of U3's
adjacent +15V pads (0.95mm pitch) clipped sw's ring, so the A* path passed
straight through sw's pad (a short), and the +15V via's halo check saw the
clipped ring too (clearance items).

**Why the obvious fix is architectural, not a patch**: re-stamping the
foreign rings (even with an own-pad-footprint mask) would re-block the
approach corridor to most pads on this board — the family-C erosion
(`W/2 + C` with the SEARCHING family's clearance) over-approximates the DRU's
pair figure for cross-class pairs (e.g. the Power family erodes every foreign
pad by 1.0mm while +15V↔sw grades at 0.2-0.5mm), and U3's +15V pad 3 sits
0.95mm from sw's pad, inside sw's 1.96mm Power-family ring: re-stamping
would honestly decline those pads (connectivity collapse). A correct fix
needs per-pair clearance figures in the obstacle map (the "live clearance
constraints matching the creepage-halo pattern" the brief anticipated) —
scoped as a follow-up per R22 (architectural fixes are documented, not
inlined in a bugfix).

## Connectivity

fully-connected nets: 53/139 (main) → 41/139 (Fix 1). The drop is the
fail-closed contract working: routes whose vias cannot pass the pierce-layer
halo decline instead of fabricating (matches the cspace doc's measured
honest-decline regime on this placement).

## Files changed

- `packages/temper-placer/src/temper_placer/router_v6/astar_core.py` (Fix 1)
- `packages/temper-placer/src/temper_placer/router_v6/_astar_nlayer.py` (Fix 1)
- `packages/temper-placer/src/temper_placer/router_v6/_astar_search.py` (Fix 1)
- `packages/temper-placer/src/temper_placer/router_v6/_ground_plane.py` (Fix 1)
- `packages/temper-placer/configs/netclass_rules.yaml` (Fix 1 fab rules)
- `packages/temper-placer/src/temper_placer/router_v6/_power_islands.py` (Fix 2-code)
- `packages/temper-placer/src/temper_placer/router_v6/_corridor_backbone.py` (Fix 2-code)
- `packages/temper-placer/tests/router_v6/test_astar_via_span_clearance.py` (new)
- `packages/temper-placer/tests/router_v6/test_power_islands.py` (new test)

## Follow-ups (out of scope, documented)

1. Per-pair clearance figures in the obstacle map (the unblock-clipped-ring
   root cause above) — the actual Fix-2 code change; needs careful design
   for the connectivity trade-off. ~90 of 133 residual clearance items +
   most residual shorts.
2. Static pad↔pad (34): placement / netclass-assignment domain (agent 94's
   doc lists the classification questions: hb-gnd, discharge.*, input absent
   from kicad_pro netclass_assignments).
3. The route-to-100 doc's w1_1/w1_2 HV-classifier gap (A*-routed as
   HighVoltage on In3.Cu/In4.Cu) — latent classification drift.
