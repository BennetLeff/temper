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
