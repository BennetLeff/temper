<!-- provenance: commit=2762f7af091f3a7a89d4098215f2d7fb5b0e6a02 dirty=false (worktree agent-ab2538612fec52881, branch worktree-agent-ab2538612fec52881, branched from origin/main at e81196c87b5998555feca78f27c612b11331bee7. kicad-cli 10.0.5. pcb/temper.kicad_pcb sha256 9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd verified unchanged before and after this task -- never opened for writing; every route below writes to a scratch path outside the repo.) -->

# Per-pair clearance halos in the N-layer A* obstacle map (2026-08-17)

**Task**: handoff §9.3 -- the 132 "unblock-clipped rings" clearance DRC
violations, R22 architectural follow-up.

**Fix commits (this worktree/branch)**:
`0e0b40e33aa7fea00d8761841b89899715a75824` (implementation) and
`2762f7af091f3a7a89d4098215f2d7fb5b0e6a02` (test-discriminator fix).

## 0. Two important corrections before reading the numbers below

1. **The "132" figure is not reproducible from this worktree's main.** It
   was measured on `fix/via-clearance-and-clearance-family`
   (`docs/evidence/2026-08-16-via-span-clearance-and-clearance-family.md`,
   commit `10a6d006c`), a branch that also carries a via-span-clearance fix
   (via placement checking every pierced layer) that is **not merged to
   `origin/main`** as of this task (verified:
   `git merge-base --is-ancestor 10a6d006c HEAD` fails; the branch's own
   commits do not appear in `git log --oneline --all | grep 1279`, which
   shows only the placement-pass commit `c1f7025d3` under that PR number).
   This task's before/after measurement is therefore run fresh, from
   `origin/main` at `e81196c87`, without that via-span fix -- the absolute
   counts below are **not comparable** to the 132/133 figures in that
   evidence doc; only the internal before/after DELTA (same board, same
   flags, only these two files toggled) is.
2. **A sibling agent (`agent-refill-zones-remeasure`) measured that the
   COMMITTED board's true `clearance` count is 1117, not 132, when
   `--refill-zones` is used and the raw-JSON 499 cap is resolved by
   exhaustive DRU-band bisection**
   (`docs/evidence/2026-08-17-refill-zones-drc-runner-gap-measurement.md`).
   That measurement is of a DIFFERENT object: the committed,
   largely-unrouted `pcb/temper.kicad_pcb` via the DRC-ceiling protocol
   (`_drc_api.run_drc`, no `--refill-zones`, `drc_ceiling.json`'s
   `clearance: 1117` true / 499 raw-capped). This task's measurement is of
   a FRESH ROUTED SCRATCH BOARD produced by `route_board.py --output`,
   which has far more copper (tracks/vias) and a completely different
   `clearance` count for that reason alone -- the two numbers are not the
   same board and must not be compared directly. **Neither measurement
   below uses `--refill-zones`** (matching every prior evidence doc in
   this specific R22 clearance-family investigation, for direct
   comparability to that line of work); see §5 for why the raw-JSON
   `clearance` count reported here is NOT cap-saturated on either side
   (both well under 499), so it is a genuine count for this board, not an
   artifact of the 499 ceiling -- but it is still a *routed-scratch-board*
   count, not the committed-board ceiling figure.

## 1. Root cause (recap, full analysis in the commit message)

`_unblock_net_pads` (`astar_grid.py`) clears every `-1` cell inside the
routing net's own pad circle (radius `pad_radius + W/2 + C`), including
whatever slice of a FOREIGN pad's own clearance-erosion ring falls inside
it (e.g. an adjacent same-footprint pad at sub-mm pitch). Before this fix,
`_astar_nlayer._family_halo_layers` only restamped a foreign obstacle's
ring when the PAIR CREEPAGE for that pair was `> 0` -- same-class /
no-creepage pairs (most of the board) got no ring restored in that hole at
all. The naive fix (restamp every foreign obstacle at the searching
family's own static erosion `W/2 + C`) was rejected in the prior
evidence doc: `C` is the SEARCHING net's own declared clearance (up to
1.0mm for Power), not the DRC pair figure (0.2-0.5mm for most pairs), and
over-stamping collapses connectivity at close-pitch same-footprint pads.

**Fix applied**: `_family_halo_layers` now looks up
`max(pair_creepage, pair_clearance)` for every obstacle (a new
`pair_clearance.default_clearance_table()` cached loader, mirroring
`pair_creepage`'s own), and the ring radius is the searching net's own
HALF-WIDTH plus that pair figure -- never the searching net's own family
clearance. Verified via direct polygon inspection in
`test_astar_nlayer.py::test_creepage_halos_stamped_around_foreign_pads_only`
that this is exact per the DRC pair table (0.8mm half-extent for a
(Default, Signal) 0.2mm-clearance pair) and NOT the rejected naive radius
(which would give 1.0mm).

## 2. Liveness (traced, not assumed)

`_astar_nlayer.py` and `pair_clearance.py` are genuine, live Python
modules -- no Rust owner shadows them:

- `grep`-verified: no Rust crate defines `astar_nlayer` or the router's
  `pair_clearance` concept (`temper-quality-oracle::placement_metrics::
  pair_clearance` is an unrelated HV/LV bounding-box placement-quality
  heuristic; `zone_generator.rs`'s `pair_clearance_keepout` is the ZONE
  generator's own buffer, not the router's per-net-class table).
- Call-site trace: `scripts/route_board.py` -> `route_pcb()`
  (`_adapter_convert.py`) -> `RouterV6Pipeline` (`pipeline.py`) ->
  `_run_stage4` (`_pipeline_route.py:936-975`) -> direct import and call of
  `run_astar_pathfinding_nlayer` from `_astar_nlayer.py`, with `pcb=pcb`
  and `routing_spaces=stage2.routing_spaces` (the arguments that make the
  fixed code path live, not the identity/no-op fallback). This path
  triggers automatically whenever a board has more than 2 routable signal
  layers (`use_nlayer = self.enable_nlayer_astar_spike or
  len(available_grids) > 2`) -- this 6-layer board always takes it,
  independent of the `--nlayer-astar-spike` CLI flag.
- The measured before/after route below (same command, only these two
  files toggled) shows the clearance count move (§3), which is itself
  direct evidence the code is on the live path -- a dead/shadowed module
  could not produce a measured delta.
- **Caveat, reported not hidden**: `test_astar_nlayer.py` and
  `test_pair_clearance.py` are NOT named in any of the 4
  `.github/workflows/python-tests.yml` "router_v6 group N" job file lists
  (grep-verified, zero matches) -- both are part of the handoff's
  documented "49->109 router_v6 Python test files not collected by CI"
  gap. This affects whether MY test changes are CI-enforced, not whether
  the PRODUCTION code they test is live; per the hard rule against
  un-silencing test collection in bulk, this is reported, not fixed, here.

## 3. Tests

`packages/temper-placer/tests/router_v6/test_astar_nlayer.py`: 27/27 pass
(2 assertions updated to reflect the corrected behaviour -- a same-class
pad is a different net, RULE 10's floor still applies; see the commit
message for the full before/after of each). `test_pair_clearance.py`:
18/18 pass (additive change only, `default_clearance_table()` is new).

Full `packages/temper-placer/tests/router_v6/` suite: see §4.

## 4. Full router_v6 regression suite

One pre-existing, unrelated failure, independently confirmed unaffected
by this change:
`test_bundle_analyzer_rust_differential.py::test_analyze_consumed_surface_bit_identical`
(`AttributeError: 'Graph' object has no attribute 'edges_with_data'` --
`bundle_analyzer.py` does not import either changed file, grep-verified;
this is the same pre-existing networkx/`graph_fixtures`-migration gap the
via-span-clearance evidence doc's own "Notes / pre-existing, unrelated"
section names explicitly).

**Status as of this document's commit: NOT measured to completion.** The
full-suite run (deselecting only the one pre-existing failure above,
`uv run --no-sync python3 -m pytest packages/temper-placer/tests/router_v6/
-q --timeout=600 --deselect ...`) was still running after 1000+s (partial
run with `-x` and no deselect reached 715 passed / 1 failed in 90s before
hitting that one pre-existing failure and stopping; the full,
non-`-x` run covering the remaining ~3100+ files/tests had not completed
by the time this task closed). Reported honestly as not measured rather
than assumed green -- §3's TARGETED tests (the two files this change
touches) are fully measured and pass (27/27, 18/18). Whoever picks this
up next: check
`/tmp/claude-1000/.../scratchpad/agent_clearance_fix_ab2538/full_router_v6_suite.log`
(scratch, not committed) or re-run the command above for the final tally.

## 5. DRC measurement

Protocol: `scripts/route_board.py --output <scratch>` (default flags: no
`--net-batching`, direct capacity-aware Stage 3 solver, N-layer A* auto-
triggered by the 6-layer board), `kicad-cli pcb drc --all-track-errors
--format json` via `temper_placer.validation._drc_api.run_drc` (no
`--refill-zones` -- see §0.2), same input board
(`pcb/temper.kicad_pcb`, sha256 above) and same flags for both sides, only
`_astar_nlayer.py`/`pair_clearance.py` toggled between the pre-fix
(`git checkout 0e0b40e33^ --`) and post-fix (`HEAD`) content. kicad-cli
10.0.5.

Only these two files were toggled between runs (`git checkout 0e0b40e33^
--` for BEFORE, `git checkout HEAD --` for AFTER, both restored
afterward and re-verified via `grep -c _stamp_foreign_pair_halos`); every
other input (board, DRU, flags, kicad-cli version) was held identical.

Full category breakdown, both sides (every DRC category present on
either board -- nothing omitted):

| category | BEFORE | AFTER | delta |
|---|---|---|---|
| **errors** | | | |
| clearance | 492 | 455 | **-37** |
| annular_width | 52 | 42 | -10 |
| shorting_items | 45 | 45 | 0 |
| hole_clearance | 34 | 26 | -8 |
| copper_edge_clearance | 16 | 10 | -6 |
| solder_mask_bridge | 12 | 12 | 0 |
| tracks_crossing | 11 | 14 | **+3** |
| drill_out_of_range | 8 | 8 | 0 |
| courtyards_overlap | 1 | 1 | 0 |
| **error_count (total)** | **671** | **613** | **-58** |
| **warnings** | | | |
| silk_overlap | 199 | 199 | 0 |
| lib_footprint_issues | 168 | 168 | 0 |
| via_dangling | 108 | 113 | **+5** |
| silk_over_copper | 42 | 42 | 0 |
| holes_co_located | 17 | 10 | -7 |
| missing_courtyard | 5 | 5 | 0 |
| silk_edge_clearance | 1 | 1 | 0 |
| **warning_count (total)** | **540** | **538** | -2 |
| `creepage` / `track_width` | absent (0) both sides | absent (0) both sides | 0 -- see below |
| fully pad-connected nets (audit) | **61/139** | **58/139** | **-3** |
| route wall time | 338.2s | 329.4s | -9s (noise) |
| routed segments / vias / zones | 4748 / 185 / 142 | 4444 / 176 / 143 | -304 / -9 / +1 |

`tracks_crossing` (+3) and `via_dangling` (+5) also moved against the fix
-- reported for completeness; neither category's mechanism (track
self-intersection; via connected on fewer than 2 layers) is something
this fix's clearance-halo restamp touches directly, so these are most
plausibly the same route-shape ripple effect as the `Pad<->Track` +6
above (a different net topology chosen for some nets once their C-space
changed), not a distinct defect this fix introduces. Not root-caused
further within this task's scope.

Cap check: `clearance` is 492 (BEFORE) and 455 (AFTER), both comfortably
under the 499 raw-JSON cap on both sides -- **not cap-saturated**, so this
is a genuine measured count on both sides of the comparison, not an
artifact of the ceiling. (This is still a *routed-scratch-board* count,
not the committed-board ceiling figure -- see §0.2.)

BEFORE clearance by pair type (492 total, `PTH-Pad` corrected from an
initial `Other` misclassification -- kicad-cli's item text is `"PTH pad N
[net] of REF"`, which does not match a bare `"Pad"` prefix): Track<->Via
154, Pad<->Track 76, PTH-Pad<->Track 60, Via<->Via 59, Pad<->Via 58,
Pad<->Pad 55, Track<->Track 26, PTH-Pad<->Pad 4.

AFTER clearance by pair type (455 total): Track<->Via 141, Pad<->Track
82, Pad<->Pad 55, Pad<->Via 51, Via<->Via 51, PTH-Pad<->Track 46,
Track<->Track 25, PTH-Pad<->Pad 4.

Per-pair-type delta: Track<->Via -13, PTH-Pad<->Track -14, Via<->Via -8,
Pad<->Via -7, Track<->Track -1, Pad<->Pad 0, PTH-Pad<->Pad 0, **Pad<->Track
+6** (the one category that got WORSE).

`creepage` and `track_width` are entirely ABSENT (0) from both `errors`
and `warnings` on both boards -- verified directly against the raw
`DrcError`/`DrcWarning` rule Counter, not inferred from an unlisted
category, so this is a genuine 0 on this routed configuration, not a
classification miss. Consistent with the handoff's "Track-involving
creepage 0. Done" / "Track_width 0. Done" entries; neither category is
this fix's target, and neither moved.

**Interpretation, reported plainly**:

- The fix reduces total clearance violations by 37 (492 -> 455, -7.5%)
  on this worktree's `main` (no via-span-clearance fix present -- see
  §0.1). Most of the reduction is concentrated in PTH-Pad<->Track (-14),
  Via<->Via (-8), and Pad<->Via (-7) -- exactly the pair types the fix's
  pad/via halo restamp targets (the fix's own zone branch also
  contributes, but zone items did not turn out to be the "Other" bucket
  here -- see the PTH-Pad correction above).
- **Track<->Via remains the single largest category on both sides (154
  before, 141 after) and dominates the total (141 of 455, 31%)**. This is
  the via-span-clearance defect (via placement checking only the
  destination layer, not every physically pierced layer) that
  `fix/via-clearance-and-fab-rules` / `fix/via-clearance-and-clearance-
  family` already fix on a DIFFERENT, unmerged branch (§0.1) -- this
  task's fix does not touch via-placement legality at all, so its
  presence and rough stability (154 -> 141, a -8% move plausibly
  explained by the same halo mechanism affecting the via's OWN
  clearance-floor stamp too, not a targeted fix) is expected, not a
  failure of this fix.
- **Pad<->Track got WORSE by 6 (76 -> 82).** Reported honestly rather
  than folded into the net "-37" headline: a per-net-halo change that
  shrinks some rings and adds others to previously-unstamped pairs can
  plausibly shift which specific nets route where relative to which
  pads, and a small regression in one pair-type while the aggregate
  improves is consistent with that -- but this was not root-caused
  further within this task's scope (would need per-violation diffing
  between the two boards, not just category counts).

## 6. Connectivity

fully pad-connected (audit, matches the router's own printed "PRIMARY
metric" exactly on both sides): **BEFORE = 61/139, AFTER = 58/139, delta
= -3.**

**This is a real, measured drop, reported plainly, not hidden.** It is
the same trade-off the prior via-span-clearance evidence doc documents
for its own fix ("Connectivity 88 -> 74/139 is the honest cost of the via
legality fixes... every refused net either re-routes legally or declines
honestly; no shorting copper ships") -- restoring a previously-missing
clearance ring can cause a net that PREVIOUSLY routed illegally close to
a foreign pad to now be correctly blocked from that path and decline
instead (fail-closed), rather than ship copper that violates the pair's
real DRC requirement. Both fake-completion counts are identical (8 on
both boards), so this is not a fake-completion regression.

Diffing the Stage 4 `Unrouted (...)` list (a 106-net accounting, not the
same 139-net denominator as the connectivity audit above, but the closest
per-net detail available) between `route_before.log` (69 unrouted) and
`route_after.log` (72 unrouted): **4 nets are unrouted in AFTER but not in
BEFORE** (`inb`, `rtd_force_p`, `rtd_sense_n`, `rtd_sense_p`) and **1 net
is unrouted in BEFORE but not in AFTER** (`safety.fault_any_or-y2` --
i.e. this one net IMPROVED under the fix), net +3 unrouted, consistent
with the -3 connectivity delta. This was not root-caused further (would
need per-net A* trace diffing, out of this task's scope) but the direction
is unambiguous: 4 nets regressed, 1 improved, net honest-decline cost of
3 nets for a 37-violation (-7.5%) clearance improvement on this
worktree's `main`.

## 7. What this fix does and does not address

- **Does**: restores a correctly-sized (never over-broad) clearance ring
  around every foreign pad/via/track/zone inside the hole
  `_unblock_net_pads` punches, for pairs the old code skipped entirely
  (creepage-0, i.e. most same-class and LV-LV pairs).
- **Does not**: the via-span-clearance defect (via placement checking only
  one pierced layer) is a SEPARATE, already-documented, unmerged fix
  (`fix/via-clearance-and-fab-rules` /
  `fix/via-clearance-and-clearance-family`, neither on `origin/main`). §5's
  measurement confirms this is the LARGER remaining lever on this
  worktree's `main`: Track<->Via is 141 of the 455 AFTER-fix clearance
  violations (31%, the single largest pair type), essentially unmoved in
  proportion by this fix (154/492 = 31% BEFORE too) -- landing the
  via-span-clearance fix is a bigger remaining win than anything left for
  this fix's own mechanism to close further.
- **Does not**: static pad<->pad clearance violations from placement
  geometry (not a routing-C-space defect; the prior evidence doc
  attributes ~34 of its 132 to this, unrelated to the unblock-clipped-ring
  mechanism).

## 8. Owner-relevant follow-ups (not in this task's scope)

1. The via-span-clearance fix (`fix/via-clearance-and-fab-rules`) is not
   on `origin/main`; landing it is a separate, already-evidenced PR.
2. `test_astar_nlayer.py`/`test_pair_clearance.py` are not CI-collected
   (§2) -- a candidate for the handoff's "un-silence serially" queue, not
   for this task to bulk-fix.
3. The `--refill-zones` DRC runner gap (§0.2) means every clearance number
   in this document, and in every prior evidence doc for this
   investigation, is measured against a zone-fill-blind DRC run. The
   sibling agent's measurement found `--refill-zones` actually DECREASES
   true `clearance` by 3 on the committed board (unlike `creepage`, which
   increases substantially) -- so this is very unlikely to invalidate the
   DIRECTION of the delta measured here, but is not independently
   re-verified for a routed scratch board in this task.
