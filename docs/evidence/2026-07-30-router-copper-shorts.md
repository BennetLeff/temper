<!-- provenance: commit=bad833fbf6c4fc4fffea16d2e24a571ba9cd32db dirty=true -->

# Router-introduced copper shorts on `pcb/temper.kicad_pcb`: append-not-reason, confirmed and partially fixed

Issues #374 (closed — intra-component shorts eliminated by the pad-rotation
writer fix, `2382e168`) and #375 (this doc). Branch
`fix/router-copper-shorts`, base `origin/main` @ `bad833fb`. `dirty=true`:
the "after" numbers below come from the fix in this same working tree; the
"before" numbers come from an unmodified second worktree checked out at the
same commit. `pcb/temper.kicad_pcb` itself is untouched — read-only per the
task constraint.

Environment: macOS arm64 (Darwin 25.5.0), `kicad-cli` 10.0.4, Python 3.12.13,
`uv`.

## Summary (read this first)

The "router appends to existing copper rather than reasoning about it"
diagnosis is **confirmed** — but by a different, more precise mechanism than
"vias/tracks/zones are not obstacles." Tracks and zones *are* loaded into the
obstacle model (they always were). Two independent bugs made that
irrelevant:

1. **Existing vias were never loaded as obstacles at all.** `ParsedPCB` (the
   router's internal board representation) had no `vias` field — the parser
   extracted them (`ParseResult.vias`) and then silently dropped them before
   handing the board to the router. Fixed.
2. **A structural, pre-existing, and deliberate design decision** — outer
   layers with copper pours get classified `plane` and excluded from routing
   entirely (`docs/evidence/2026-07-28-tree-executor-grid-layer-mismatch.md`)
   — means that once a board carries `enable_zone_pours=True` output (which
   `route_pcb()` produces by default), a *second* `route_pcb()` call over
   that output routes new copper onto different physical layers than
   virtually all of the existing copper. This is not something I changed or
   propose changing (reverting it cost 12x completion per the cited doc); it
   is reported here because it explains *why* pre-existing tracks/zones,
   despite being correctly modeled, had **zero measured effect** on a
   re-route pass before the via fix.

**The current 81/82 `shorting_items` on the committed board are *not*
explained by either mechanism above.** Git history confirms
`pcb/temper.kicad_pcb`'s copper was produced by exactly one `route_pcb()`
call against a genuinely bare board (`556ccf4f`, "first route"); every commit
since is a placement resync, a manual footprint move, or the pad-rotation
writer fix (#374) — none of them re-invoked the router over existing copper.
So the append-not-reason bug, real as it is, has not yet had a chance to
touch the committed board. What it *does* fix, measured directly: issue
#375's own experiment (running `route_pcb()` against the already-routed
board) — median `shorting_items` drops 111 → 89 (-20%), with completion and
`unconnected_items` essentially flat. See "What remains" for the current
board's actual 81/82.

## 1. Does the router load existing board copper into occupancy grids?

Traced `route_pcb()` (`_adapter_convert.py:153`) → `RouterV6Pipeline.run()`
(`_pipeline_core.py:215`, Stage 0 loads via `parse_kicad_pcb_v6`) →
`Stage2Orchestrator` (`stage2_orchestrator.py:35`, first stage
`ObstacleMapStage`) → `build_obstacle_map()` (`obstacle_map.py:31`) →
`RoutingSpaceStage` (`routing_space.py:177`, `board - obstacles`) →
`OccupancyGridStage` (`occupancy_grid.py:504`, rasterizes routing space into
the grid A* actually reads).

**Tracks: yes, loaded, but net-agnostic (too strict, not too loose).**
`obstacle_map.py:127-138` (pre-fix) iterated `pcb.tracks` (populated from
`legacy_result.traces` in `kicad_parser.py:217`, itself real —
2338 tracks confirmed present) and buffered every one onto its own layer's
obstacle polygon, with **no net filter at all** — a net's own pre-existing
track blocks that same net's own new route attempt, same as anyone else's.
This is the wrong direction of bug (over-conservative, not permissive) and
is not implicated in the shorts.

**Zones: yes, loaded, same net-agnostic treatment**
(`obstacle_map.py:95-124`), with a standing `# TODO: If we route the SAME
net, we should allow entering the zone` acknowledging the same
over-conservative gap. Not implicated in shorting_items — sampling the
current board's 82 violations found **zero** that include a zone item (all
82 are Track/Via/Pad combinations only).

**Vias: no. Not loaded at all, on any layer, before this fix.**
`ParsedPCB` (`stage0_data.py`) had `tracks: list` but no `vias` field.
`parse_kicad_pcb_v6()` (`kicad_parser.py:176-219`) computed
`legacy_result = parse_kicad_pcb(pcb_path, ...)`, which *does* extract vias
(`ParseResult.vias`, populated by `_extract_vias_from_pcb`,
`io/_parse_tracks.py:59-98` — confirmed 48 vias present on the committed
board) — and then never passed `legacy_result.vias` into the `ParsedPCB(...)`
constructor. The value existed one line away and was dropped on the floor.
`obstacle_map.py`'s only via-handling code, before this fix, was section 2,
"Escape Vias" — vias *generated this run* for dense-package escapes, not
vias already on the board. Confirmed by grep: no other file in
`router_v6/` reads `pcb.vias` (searched for `pcb.vias` project-wide;
zero hits pre-fix).

## 2. Own-net vs. other-net scoping — is the direction of the bug right?

Both directions of the two-sided bug the task warned about are real, in
different obstacle classes:

- **Tracks and zones: too strict.** A net's own pre-existing copper blocks
  its own new route (no net exemption exists in `build_obstacle_map`).
  This is conservative, not a shorting cause, but is a real, separate
  completion tax on re-routes — not fixed here, flagged under "What
  remains."
- **Vias: too loose (before this fix) — the missing side entirely.** Not
  merely "other nets' vias aren't exempted correctly" — no net's vias,
  own or other, were obstacles at all.

The fix (see below) adds vias with the *correct* scoping in one step,
matching the pattern already used correctly for pads: block every existing
via for everyone by default (`obstacle_map.py`, static, net-agnostic, same
as tracks), then re-open only the routing net's own existing vias at route
time (`astar_grid.py::_unblock_net_pads`, dynamic, per-net) — mirroring the
existing, working `pad_centers_per_net` / `escape_vias_map` unblock pattern
instead of inventing a new one.

A layer subtlety mattered here and was caught by testing, not assumed: a
through-hole via's `.layers` field in this codebase's parsed representation
names only its two declared endpoint layers (`"F.Cu"`/`"B.Cu"`), matching
KiCad's own file convention — but the physical drill passes through every
copper layer in between, including the inner layers this board's router
actually routes new copper on (`In1.Cu`/`In2.Cu` — outer layers are
classified `plane` once they carry a zone pour, see Summary). Blocking only
the two declared endpoint layers would have made the fix a near-total no-op
on this board. The escape-via code two sections up already treats
through-hole vias as blocking *every* signal/mixed layer for exactly this
reason (`obstacle_map.py:82-92`, comment: "Assume Through-Hole Vias for
now (blocking all layers)"); the fix applies the same treatment to
pre-existing vias for consistency, confirmed by measurement below (`In1.Cu`
obstacle area moved from 580.45 mm² to 602.43 mm² only once "all
signal/mixed layers" was used — using just `via.layers` left it unchanged
at 580.45 mm²).

## 3. Are the 81 current shorts explained by this mechanism?

**No, not directly — 0%.** Git log for `pcb/temper.kicad_pcb`:

```
2382e168 fix(io): rotate pad bodies with their footprint (#374)   <- writer fix, no re-route
81385272 fix(pcb): place the corrected tank capacitors             <- 60-line manual move
65bd0159 fix(pcb): resync board to netlist after OVP-01            <- net-ID remap, "0 geometry changes ... verified"
556ccf4f feat(pcb): commit first route of temper.kicad_pcb          <- THE route_pcb() call, bare board
c6b1b463 fix(pcb): re-solve placement (before first route)
```

Every commit after `556ccf4f` either didn't touch copper geometry at all
(verified in the commit's own evidence doc for `65bd0159`) or was a small
manual/writer-level change. `route_pcb()` has been invoked against this
board exactly once, against a bare board with nothing to append onto.

To see whether the append-not-reason bug is even latent here, I ran a
controlled experiment holding placement and netlist fixed
(`scripts/route_board.py`'s existing `keep_existing_copper` toggle,
originally added for this exact comparison — see its module docstring) on
the **pre-fix** code:

| input | new segments (delta from pre-existing 2338) | new vias | routed/attempted |
|---|---|---|---|
| bare (copper stripped) | 1687 | 0 | 36/96 |
| already-routed (copper kept) | 1687 | 0 | 36/96 |

`comm -23` on the sorted `(segment ...)` lines from both outputs: **0 lines
differ.** The new routing work is byte-identical whether or not 2338
pre-existing tracks + 48 pre-existing vias were present in the input. That
is the cleanest possible confirmation that pre-existing copper had *zero*
effect on this router's output before the fix — for the reason in the
Summary (new copper always lands on `In1.Cu`/`In2.Cu`; all pre-existing
copper on this board lives on `F.Cu`/`B.Cu`, which — because it carries zone
pours — is excluded from the routing-space computation entirely, so the two
copper sets never share a layer to begin with).

Since the committed board's shorts weren't produced by a re-route, I sampled
them directly instead. Representative violations (median-of-9 run, full
classification below):

```
Pad 2 [V_BUS_SENSE] of R58 on F.Cu   {167.7575, 191.65}
Via [safety.ovp.r_adc_top2-p2] on F.Cu - B.Cu   {167.7575, 191.65}   <- identical coordinates
```
```
Via [RTD_SDI] on F.Cu - B.Cu   {22.265, 52.8}
Via [sw] on F.Cu - B.Cu        {22.45, 52.25}                        <- 0.63mm apart, both vias
```

A via landing at the *exact* coordinates of a different net's pad, and
two different nets' vias landing within clearance of each other, both
happened **within the single original bare-board pass** — a genuinely
different bug from either mechanism above: same-run dynamic via-blocking
(`OccupancyGrid.mark_via_blocked`, `occupancy_grid.py:348`, called from
`astar_core.py:475`) exists and is wired in, but evidently has gaps. I
confirmed the general shape of the problem (not its exact cause) by routing
this same placement/netlist completely from scratch — zero pre-existing
copper anywhere, so the "existing copper is invisible" mechanism cannot
apply — and it *still* produced 10 `shorting_items` at only 36/96 nets
routed:

```
kicad-cli pcb drc on a from-scratch bare route (36/96 nets):
  shorting_items: 10
  e.g. "Items shorting two nets (nets discharge.k_dis2-no and discharge.k_dis1-coil2)" x3
       "Items shorting two nets (nets cs_n and SW_NODE)"
```

Kind-pair breakdown of the committed board's 82 shorts (median-of-9 run,
full classification):

| item kinds | count | % |
|---|---|---|
| Track+Via | 33 | 40% |
| Pad+Track (incl. PTH pad) | 27 | 33% |
| Pad+Via (incl. PTH pad) | 16 | 20% |
| Via+Via | 3 | 4% |
| Track+Track | 2 | 2% |
| Pad+Pad (PTH) | 1 | 1% |

52/82 (63%) involve a via on at least one side. That is consistent with
"vias are under-modeled as obstacles somewhere in this router" as a general
failure family, but the *specific* code path is same-run escape-via /
via-in-pad placement or ripup-reroute unmark logic (`escape_via_generator.py`,
`via_placement.py`, `_unmark_route_blocked`) — not the pre-existing-file-copper
path this fix addresses. I did not find or fix the exact same-run defect;
see "What remains."

Net-pair concentration: the task's working hypothesis was "concentrated on
gnd and +3V3." Measured directly — it is not, particularly.
`gnd`/`+3V3`/`PWR_RTN` together account for **17/82 (21%)** of shorts, the
rest spread across 44 other distinct net pairs (many involving low-current
signal/gate-drive nets like `discharge.k_dis1-nc`↔`ina`, `y`↔`zcd`). Worth
correcting since it changes where a future investigation should look (not a
power/ground-specific issue).

## The fix

Minimal, three-part, matches an existing working pattern instead of
inventing a new one:

1. `stage0_data.py`: add `vias: list = field(default_factory=list)` to
   `ParsedPCB`.
2. `io/kicad_parser.py::parse_kicad_pcb_v6`: pass
   `vias=legacy_result.vias` — the value that was already being computed
   and silently discarded.
3. `router_v6/obstacle_map.py::build_obstacle_map`: new section 5, adds
   every existing via as a static obstacle on every signal/mixed layer
   (net-agnostic, matching tracks/zones/escape-vias' existing treatment).
4. `router_v6/astar_grid.py`: new `_extract_existing_via_centers_per_net()`
   (mirrors `_extract_pad_centers_per_net`), and `_unblock_net_pads()`
   grows an `existing_vias_map` parameter that re-opens the routing net's
   own pre-existing vias at route time — same treatment already given to
   that net's own pads and escape vias, just extended to a third obstacle
   class.
5. `router_v6/_astar_reconstruct.py::run_astar_pathfinding`: wires the new
   extraction call and threads `existing_vias_map` through the one call
   site of `_unblock_net_pads`.

No change to `_pipeline_route.py`, `route_stage.py`, A* search internals, or
any DRC/fence logic. `pcb/temper.kicad_pcb` was not touched.

## Before/after measurement

All numbers: median of N=5 `kicad-cli pcb drc` runs (this repo's own
protocol — DRC scatters run-to-run on an unchanged file) against the
*same* routed `.kicad_pcb`, since the router itself is confirmed
deterministic run-to-run here (`docs/evidence/2026-07-27-router-determinism.md`,
and independently reconfirmed: re-routing produced byte-identical segment
sets across repeated invocations in this investigation).

**Controlled experiment** (`scripts/route_board.py`, `keep_existing_copper=True`
— route the committed board's placement/netlist with its own existing
copper left in place, the exact scenario in issue #375's hypothesis):

| metric | before (unfixed) | after (fixed) | delta |
|---|---|---|---|
| total DRC violations (median) | 1542 | 1528 | -14 |
| `shorting_items` (median) | 111 | 89 | **-22 (-20%)** |
| `unconnected_items` (median) | 405 | 404 | -1 (flat/better) |
| completion_rate (deterministic) | 37.5% (36/96) | 35.4% (34/96) | -2.1 pt (2 nets) |
| new segments emitted | 1687 | 1553 | -134 |
| new vias emitted | 0 | 0 | 0 |

Raw per-run shorting_items: before `[117, 111, 102, 112, 105]`, after
`[97, 89, 90, 81, 73]`.

**Independent cross-check**, the repo's own canonical production-board test
(`test_temper_production_board_routing.py::test_route_pcb_production_board`,
single run each — a full `route_pcb()` invocation is ~65-75s, so this is a
spot check, not the median claim above):

| metric | before (unfixed) | after (fixed) |
|---|---|---|
| completion | 37.50% (40/108) | 35.42% (38/108) |
| `shorting_items` | 87 | 76 |
| `unconnected_items` | 405 | 404 |
| total DRC violations | 1524 | 1509 |

Same direction, same rough magnitude, independent harness. This test
`assert unconnected == 0`s and **fails on unmodified `origin/main`
already** (405 ≠ 0) — reproduced on a clean second worktree before
attributing anything to this change; the fix does not newly break it and
does not fix its pre-existing failure either (`unconnected_items` is
essentially unchanged, 405→404).

**Bare-board (from-scratch) regression check** — the actual production
routing flow, i.e. the one that built the committed board:

| metric | before | after |
|---|---|---|
| routed/attempted | 36/96 | 36/96 |
| new segments | 1687 | 1687 |
| new vias | 0 | 0 |
| `(segment ...)` lines, byte diff | — | 0 lines differ |

The fix is a confirmed no-op on the flow that produced the committed board
— it only activates once pre-existing vias exist in the input, which a
from-scratch bare route never has. Zero regression risk on that path.

**Judged against the PR #386 standard** (completion is not the objective,
correct copper is; a fix that raises completion while raising shorts is not
a fix): this fix *lowers* completion by 2 nets while *lowering* shorts by
20%, on the one scenario it touches. That is the opposite of the #386
failure mode — it trades a small, honest amount of "unrouted" for real
copper it used to fabricate wrongly on top of an obstacle it could not see.
`unconnected_items` did not get worse in either measurement.

## What remains (not fixed here, by design — see task's size/risk bar)

1. **The 81/82 shorts on the committed board are unexplained by this fix.**
   They come from a same-run (not cross-run) via/track collision-avoidance
   gap — plausibly in `escape_via_generator.py` or `via_placement.py` not
   cross-checking candidate via positions against *other* dense packages'
   pads/vias, or a `_unmark_route_blocked` gap after rip-up-reroute leaving
   stale free cells. I found symptomatic evidence (exact-coordinate
   via/pad collisions, 10 shorts on a from-scratch 36-net bare route with
   zero pre-existing copper) but did not isolate or fix the exact defect —
   that requires instrumenting the A* ripup/reroute loop and via-candidate
   selection directly, which is router-internals work, explicitly out of
   scope ("do not attempt a router rewrite").
2. **Tracks and zones are still net-agnostic (too strict) in the static
   obstacle map** — a net's own pre-existing copper still blocks its own
   re-route. Not a shorting cause (confirmed: 0/82 current shorts involve a
   zone item), but a real completion tax on any future re-route-on-existing-
   copper workflow. Fixing this the same way vias were fixed here (extend
   `_unblock_net_pads`/obstacle exemption to the net's own tracks) is a
   natural, similarly-scoped follow-up, deliberately not bundled into this
   change to keep the measured claim narrow.
3. **The `F.Cu`/`B.Cu`-become-`plane` layer reclassification** is a known,
   deliberate, already-documented tradeoff
   (`docs/evidence/2026-07-28-stackup-partial-revert.md`, `2026-07-28-
   tree-executor-grid-layer-mismatch.md`) — not touched, not proposed for
   change here. It is reported in this doc only because it explains why
   pre-existing tracks/zones (correctly modeled) measured as having zero
   effect on a re-route before the via fix.

## Suites

Full `packages/temper-placer/tests/router_v6/` suite (2250 collected):
**2208 passed, 7 failed, 15 skipped, 23 xfailed.** All 7 failures reproduced
independently on an unmodified `origin/main` worktree before attributing
anything here:

```
test_astar_3d_production_scale_spike.py::test_happy_path_same_layer_segment_finds_path[production]
test_astar_3d_production_scale_spike.py::test_happy_path_forced_transition_segment_finds_path_with_via[production]
test_astar_3d_production_scale_spike.py::test_scale_wall_time_baseline_production_board
test_astar_3d_production_scale_spike.py::test_via_legality_spot_check_against_clearance_radius
test_dfm_interaction.py::TestAllModulesFail::test_all_seven_raise_still_produces_report
test_temper_production_board_routing.py::TestProductionBoardRouting::test_route_pcb_production_board
test_via_insertion_anti_false_zero.py::test_committed_u8_measurement_record_is_well_formed
```

This is the exact same seven named in
`docs/evidence/2026-07-28-tree-executor-grid-layer-mismatch.md`'s own suite
table (pre-dating this change) — a missing committed measurement JSON, a
DFM-interaction test, the `unconnected==0` production-board assertion (see
the cross-check table above — it fails on unmodified `main` too, 405 ≠ 0),
and four `test_astar_3d_production_scale_spike` production-scale cases.
None introduced by this change. Zero new failures, zero previously-passing
tests broken.

## UNVERIFIED

* The exact same-run via/track collision mechanism behind the committed
  board's 81/82 shorts (item 1 above) — diagnosed by symptom, not isolated
  to a specific function or line.
* Whether extending the "own net exempted" treatment to tracks/zones (item
  2 above) would change completion/shorts in either direction — not
  measured, flagged as a follow-up only.
* Zone-filled DRC (`pcbnew.ZONE_FILLER`) was not run; all numbers above are
  unfilled `kicad-cli pcb drc`, consistent with this repo's other router
  evidence docs but higher in absolute terms than CI's filled runs.
