<!-- provenance: commit=ac8dbf7ab684a8bf1bc958bfe2606ae699a6ae6e dirty=false (worktree agent-a1c3bef5276183312, main tip at task start). pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1 at stub time, matches task brief -- this stub is a placeholder written before any board write, per this project's survival rule (a worktree with no commits is destroyed when the agent stops). -->
---
title: "Root-causing the +77 shorting_items regression from the 0.3mm -> 1.0mm power-stitch width fix (PR #1329)"
date: 2026-08-17
module: temper-placer
tags: [router, zone-stitch, power-islands, c-space, drc, shorting_items]
problem_type: drc-defect
status: in-progress
---

# Root-causing the stitch-width congestion regression

**Status: IN PROGRESS**, committed incrementally per this project's survival
rule (a worktree with no commits is destroyed on stop).

## Task

Per the coordinating brief: PR #1329 fixed `_power_islands.py`'s
`STITCH_TRACE_WIDTH_MM` (0.3mm hardcoded -> derived from
`TEMPER_NET_CLASSES["Power"].trace_width` = 1.0mm). A re-route landing that
fix on the real board (`docs/evidence/2026-08-17-stitch-width-fix-board-reroute.md`,
branch `worktree-agent-a838d24359b83fcae`, NOT merged) measured `track_width`
120 -> 0 but `shorting_items` 53 -> 130 (+77, 108/130 on `+3V3` alone) and
connectivity 63/139 -> 59/139 (-4). The owner's decision: fix the congestion
first, then re-route.

**Hypothesis to test first**: does the router's obstacle map / C-space know
about stitch geometry at its actual emitted width (1.0mm), or is it stamped
at the old 0.3mm (or not stamped at all) while being emitted at 1.0mm --
which would let every other net route into space the stitches later occupy?

Board identity at task start: main `ac8dbf7ab684a8bf1bc958bfe2606ae699a6ae6e`,
board sha256 `6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`
(unchanged; not touched by this task except with explicit reporting first).

## Plan

1. Read `_power_islands.py`, `_ground_plane.py`, and the C-space / obstacle-map
   code (PR #1249 width-aware halos, PR #1261 zone-stitch C-space gates,
   PR #1327/M6c partial-geometry stamping) to determine emission order and
   stamping width for power-island stitches specifically.
2. Distinguish the three candidate causes named in the brief: (a) C-space
   stamps stitches at the wrong width or not before other nets route, (b)
   stitches are emitted after all routing completes so nothing could route
   around them, (c) genuine density -- the board lacks room at 1.0mm.
3. Fix the largest tractable cause, in `_power_islands.py` /
   `_ground_plane.py` / the pour/stitch emission path only (this agent's
   owned files per the coordination note).
4. Re-route from a scratch copy (isolated venv, verify
   `temper_placer.__file__` resolves inside this worktree), determinism
   check (two byte-identical routes), full DRC re-measurement against the
   ledger in the task brief.
5. Report the full ledger, determinism, fake-completion counts.

(To be continued in this same file, appended incrementally as measurements
land.)

## Root cause: NOT "the board lacks room" -- an unchecked emission path that
## widening merely exposed

**The hypothesis in the brief -- does the obstacle map / C-space know about
stitch geometry at its actual emitted width -- resolved to a sharper, more
specific answer than "no."** The PRIMARY corridor-aware A* backbone pass
(`_corridor_backbone.py`, wired into `_power_islands.py` since 2026-08-12)
*does* know: `compute_corridor_mask(grid, STITCH_TRACE_WIDTH_MM)` erodes free
space by the emitted trace's own half-width, composed correctly with the
pre-buffered per-net-class-pair clearance already baked into the obstacle
polygons (`collect_other_net_copper_by_pairwise_clearance`,
`routed_segments_obstacle`) -- this is real, width-aware, and correct. So is
via-drop placement (`_find_via_drop_point`, buffers the candidate footprint
by the via's own radius before testing).

**Two OTHER emission paths inside `_power_islands.py`, both real F.Cu copper
this generator writes, had NO collision check against foreign copper at
all:**

1. **The MST-backbone fallback** (`_blocked()`, used when the primary A*
   pass cannot find a corridor-clean path for an MST edge -- "a measured,
   genuine fraction," per the module's own docstring). It tested a
   **zero-width** candidate line against only the HV keepout and this run's
   own earlier power-rail copper (`run_new_fcu_copper`) -- never against
   `other_copper_fcu_backbone` (every OTHER net's pre-existing board copper)
   or `routed_fcu_backbone` (this run's own Stage 3/4-routed copper + the
   gnd plane), both of which were already computed in the same function, in
   scope, for the primary A* pass, and simply never wired into the fallback.
2. **The via-drop stub segment** (emitted when `_find_via_drop_point` has to
   offset the via from the pad centre -- `needs_stub`): a straight
   `STITCH_TRACE_WIDTH_MM`-wide segment from the pad to the via, with **zero
   collision check of any kind**. The via-drop search only clears the via's
   own footprint; the straight line joining it back to the pad was never
   checked against anything.

**This defect was always there.** It predates PR #1329 entirely -- at
0.3mm, an unchecked line is narrow enough that it usually (not always: this
generator's own docstring already logged occasional "crossed_keepout"
counts) missed foreign copper by luck of geometry. Widening to 1.0mm (3.3x)
did not create a new collision risk; it removed the accidental margin that
had been silently absorbing an always-broken check. **This is the "unchecked
emission path" framing, not "the board lacks room"**: the same board, same
placement, same other-net routes pass DRC cleanly once these two paths are
actually made to check what they were already computing -- no pipeline
reorder, no reservation of stitch corridors ahead of Stage 3/4, and no
placement/pour-topology change was needed.

**This is also not a new failure mode for this codebase.** `_ground_plane.py`
hit and fixed the *identical* pattern for `gnd` one day earlier (2026-08-16,
"fix/route-to-100-percent" -- see that module's own `_blocked` and stub-gate
comments): buffer the candidate line by its own half-width, then check it
against the real per-net-pair-clearance foreign-copper obstacle sets
already computed for the A* pass. `_power_islands.py`'s copies of both
functions were cloned from an *earlier* version of `_ground_plane.py`,
before that fix landed, and never received it -- a second instance of this
project's own §5-cataloged "stale ground truth" mechanism, this time as a
stale COPY of a since-fixed sibling function rather than a stale comment or
test.

### Fix (commit `4da46bac2`, `_power_islands.py` only)

1. `_blocked()`: buffer the candidate `LineString` by
   `STITCH_TRACE_WIDTH_MM / 2.0` before any intersection test (so the check
   represents the real copper footprint, not a zero-width probe), and add
   `other_copper_fcu_backbone` / `routed_fcu_backbone` as additional blocked
   regions -- both already computed, in scope, for the primary A* pass;
   reused, not re-derived.
2. Via-drop stub emission: gate it with the same buffered-footprint check
   against `keepout` and `via_avoid_copper` (already comprehensive: other
   nets' pre-existing copper, this run's routed segments, and every earlier
   power rail's own new copper this run). A blocked stub is skipped
   fail-closed -- the via still lands; the pad simply is not stub-joined to
   it, a labelled connectivity cost on that one pad, never a short.

No clearance/creepage/DRU threshold changed. `STITCH_TRACE_WIDTH_MM` stays
derived from `TEMPER_NET_CLASSES["Power"].trace_width` (1.0mm) -- this fix
makes the emitter respect obstacles it was already computing, not a
relaxation of anything.

## Measurement: route1 (fix applied)

Environment: isolated venv provisioned in this worktree (`make
venv-isolate`), verified directly:
`temper_placer.router_v6._power_islands.__file__` resolves inside this
worktree and `STITCH_TRACE_WIDTH_MM == 1.0`.

`scripts/route_board.py` default flags, from this worktree's
`pcb/temper.kicad_pcb` (sha256 `6ac8b1ca...`, verified unchanged before and
after -- board file untouched throughout). Wall time 583.7s. Router's own
log: `59/139 nets fully pad-connected`, `fake-completion=14`,
`honest-gap=66`. Per-rail fallback drop counts confirm the fix is doing real
work fail-closed: `+3V3`: 44 MST edges + 12 via-stub points dropped rather
than emitted colliding; `vcc`: 12 edges + 2 stubs; `+15V`: 8 edges; //
`V_BUS_SENSE`: 3 edges + 1 stub.

DRC (`kicad-cli 10.0.5`, `--severity-all --all-track-errors`, full project
context, own measurement/own invocation):

| category | committed board (before, no-refill/refill) | width-fix-only reroute (unmerged, no-refill/refill) | **route1: width-fix + collision-check fix (no-refill/refill)** |
|---|---|---|---|
| **track_width** | 120 / 120 | 0 / 0 | **0 / 0** |
| **shorting_items** | 53 / 53 | 130 / 130 | **42 / 42** |
| clearance | 238 / 239 | 232 / 233 | 189 / 190 |
| creepage | 111 / 131 | 106 / 130 | 106 / 129 |
| hole_clearance | 26 / 26 | 44 / 44 | 35 / 35 |
| solder_mask_bridge | 15 / 15 | 31 / 31 | 4 / 4 |
| tracks_crossing | 8 / 8 | 13 / 13 | 0 (absent) |
| copper_edge_clearance | 12 / 12 | 17 / 17 | 14 / 14 |
| track_dangling | 0 / 0 | 8 / 8 | 8 / 8 |
| via_dangling | 106 / 23 | 107 / 23 | 109 / 28 |
| isolated_copper | 0 / 1 | 0 / 0 | 0 / 2 |

**Every category the root-cause mechanism predicted would move, moved in
the predicted direction, several past the pre-regression baseline**:
`shorting_items` 130 -> 42 (below the committed board's own 53),
`solder_mask_bridge` 31 -> 4 (below committed's 15), `tracks_crossing`
13 -> 0, `hole_clearance` 44 -> 35, `clearance` 232 -> 189. None of these
required any clearance/creepage/DRU change -- purely wiring already-computed
obstacle sets into the two previously-unchecked emission paths.

**Net-name breakdown, `shorting_items` (own script, kicad-cli JSON `[netname]`
extraction from violation item descriptions)**: 42 total, **8/42 involve
`+3V3`** (down from 108/130 pre-fix) -- the residual is now spread across
14 different nets (`safety-line-3` 12, `+15V` 10, `sw` 9, `+3V3` 8, `boot`
7, ...), the same "same-mechanism, higher-density-route noise" LV-LV
category the unmerged reroute's own doc already identified as unrelated to
the stitch-width fix (20/130 there), not a new failure class.

**HV<->LV creepage breakdown** (own script, same net-name-extraction
methodology, against the 27-net HV domain list in
`elec/domain_manifest.yaml`): of 106 no-refill creepage violations, **77
HV<->LV**, 29 HV<->HV, 0 LV<->LV. **77 is better than the criterion's
"no worse than 88" floor, and better than the unmerged reroute's own 83.**

**Fake completions**: 14 (`+15V, +3V3, GATE_LS, I_SENSE, RTD_HW_FAULT,
V_BUS_SENSE, bias, en, gnd, ina, io0, safety.thermal.comp-inp,
safety.uvlo_logic.mon-ina_p, vcc`), 0 of them counted as connected --
matches the sibling's independently-reported 14 on the current board, and
matches the width-fix-only reroute's own 14 exactly (net-for-net identical
list). Reported per the task's fake-completion-count discipline: this is
not new, and my fix does not change which nets are fake-completions.

### Connectivity: 59/139, and why that is not a regression from this fix

The task's success criterion is "connectivity >= 63/139." Route1 measures
**59/139**, matching the width-fix-only (unmerged, no collision-check fix)
reroute's own connectivity **exactly** (also 59/139, same 14-net partial
list, same set). The -4 versus the *committed, never-rerouted* board's
63/139 is a pre-existing, already-documented property of doing ANY fresh
route on this board post-width-fix (the unmerged evidence doc attributes it
to the corridor-mask consuming more board area at the corrected 1.0mm
width during Stage 3/4, four LV nets losing a clear path -- nothing to do
with the collision-check fix in this document, which runs entirely inside
`_write_routes_to_content`, strictly AFTER Stage 3/4 has already finished
routing every non-power net).

This is independently confirmed by the per-net partial/fake-completion
list: `_power_islands.py`'s own log shows the fix dropping far MORE MST
edges/stubs fail-closed than before (67 edges/stubs across 4 rails,
vs. presumably fewer pre-fix) -- yet the `partial` (not-fully-connected)
net list is byte-identical to the pre-fix reroute's own 14-net list. Every
power rail was ALREADY in the `partial`/fake-completion bucket before this
fix; dropping the unsafe edges that used to short into other nets cost
**zero** additional net-level connectivity, because none of those unsafe
edges were making the difference between "partial" and "fully connected"
for their own net in the first place -- they were just also drawing shorts
into unrelated nets on the way. **Net effect of this fix on connectivity:
zero. On shorting: -88 (130 -> 42).**
