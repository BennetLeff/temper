<!-- provenance: commit=eca0d755a dirty=false (worktree agent-ae9876aa8752c1a79, main tip at task start). pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1, matches task brief, NOT modified by this task -- all measurement on scratch copies under /tmp. -->
---
title: "+3V3 pour-stitch track_width defect: root cause and fix, independent of M6c; M6c re-evaluated on top of it"
date: 2026-08-17
module: temper-placer
tags: [router, zone-stitch, power-islands, drc, track_width]
problem_type: drc-defect
status: in-progress
---

# +3V3 pour-stitch defect: root cause + fix, then M6c re-evaluation

**Status: IN PROGRESS**, committed incrementally per this project's survival rule
(a worktree with no commits is destroyed on stop).

## Task

Three phases, per the coordinating brief:

1. Root-cause and fix a pre-existing `+3V3` pour-stitch `track_width` defect
   on current main, independent of M6c (branch `spike/router-m6c-partial-geometry`,
   PR #1327). Prior art already characterized this defect indirectly in
   `docs/evidence/2026-08-17-routing-cause-refresh-and-tractable-fix.md` §6: at
   M6c's own baseline (committed board `6ac8b1ca...`), `+3V3` already carries
   100 `track_width` violations pre-M6c, worsening to 167 under M6c's added
   congestion (traced there to "the pour/plane MST-stitch generator's own
   narrow via-drop-avoidance stubs, `_power_islands.py`"). That characterization
   did not fix the defect. This document does.
2. Rebase/cherry-pick M6c onto the fix and re-measure whether M6c is a net win
   with the confound removed.
3. If a genuine win: tests + a type-system guard for "safe, computed route
   geometry must not be silently discarded" (or a documented reason a test is
   the better expression).

## 1. Baseline provenance (this document's own, not inherited)

`kicad-cli 10.0.5`. Board: `pcb/temper.kicad_pcb`, sha256 `6ac8b1ca...`
(matches the task brief; unmodified throughout -- verified before and after
every step in this document). Measurement: a scratch copy of the committed
board, `.kicad_pro` copied verbatim from `pcb/temper.kicad_pro`, `.kicad_dru`
freshly regenerated via `generate_kicad_dru.generate_dru()` (called directly,
NOT via `scripts/generate_kicad_dru.py`'s `main()` -- that also overwrites 4
tracked `*.generated.yaml` config files as a side effect, which this
measurement must not touch). `kicad-cli pcb drc --severity-all
--all-track-errors --format json`, with and without `--refill-zones`.

**No-refill**: clearance 224, track_width 120, creepage 100, shorting_items
53, hole_clearance 26, solder_mask_bridge 15, copper_edge_clearance 12,
tracks_crossing 8, drill_out_of_range 6, courtyards_overlap 1 (errors, 565
total); silk_overlap 199 [CAPPED], lib_footprint_issues 168, via_dangling
106, silk_over_copper 42, missing_courtyard 5, silk_edge_clearance 1
(warnings, 521 total). **Total 1086.**

**`--refill-zones`**: clearance 225, creepage 121, track_width 120,
shorting_items 53, hole_clearance 26, solder_mask_bridge 15,
copper_edge_clearance 12, tracks_crossing 8, drill_out_of_range 6,
courtyards_overlap 1 (errors, 587); silk_overlap 199 [CAPPED],
lib_footprint_issues 168, silk_over_copper 42, via_dangling 23,
missing_courtyard 5, silk_edge_clearance 1 (warnings, 438). **Total 1025.**

Both totals match `docs/evidence/2026-08-17-routing-cause-refresh-and-tractable-fix.md`
§1/§6's own independently-measured baseline exactly (1086 no-refill, 1025
refill; track_width 120 both ways; creepage 100/121). This document's own
measurement reproduces that baseline from scratch (own script, own
kicad-cli invocation) rather than inheriting the number -- provenance
closed, no unexplained ~129 gap here.

## 2. Root cause: `_power_islands.py`'s `STITCH_TRACE_WIDTH_MM` hardcoded below the Power netclass DRU floor

Every `track_width` violation's own kicad-cli description was inspected
(not sampled): **all 120/120** read `"Track width (rule 'Power trace width'
min width 1.0000 mm; actual 0.3000 mm)"`, and **all 120/120** name a net in
`{+3V3 (100), vcc (10), +15V (8), V_BUS_SENSE (2)}` -- exactly
`_power_islands.py`'s `POWER_ISLAND_NETS`. This is not "most of the
category traces to X"; the entire category is one defect.

`pcb/temper.kicad_pro` classifies all four of these nets `"Power"`.
`design_rules.py`'s `TEMPER_NET_CLASSES["Power"].trace_width == 1.0` (mm),
which `generate_kicad_dru.py` turns into the DRU's `"Power trace width"`
rule at `min 1.0mm`. `_power_islands.py`'s module-level
`STITCH_TRACE_WIDTH_MM = 0.3` was used, unconditionally, for every stitch
backbone segment (`_emit_segment`, line ~777) and every keepout-detour
fallback segment (line ~704) this generator emits for these nets -- so
every segment it has ever written is, by construction, below the DRU floor
for its own net's class.

**This is the same defect class `_ground_plane.py` already hit and fixed**,
one day earlier in-repo history (2026-08-16, "full-route agent,
fix/route-to-100-percent"): that module's own `STITCH_TRACE_WIDTH_MM` was
raised 0.4 -> 1.0mm after measuring 216/747 track_width violations from the
identical mismatch against GND's 1.0mm DRU floor. `_power_islands.py`'s own
comment on its neighboring `VIA_SIZE_MM` constant claimed its
`STITCH_TRACE_WIDTH_MM` was "identical" to `_ground_plane.py`'s -- **that
claim was already false when written** (0.3 vs 1.0mm) and stayed false for
a full day of subsequent commits. One more instance of this project's own
named failure mode, "one fact, many homes, drifting" (handoff §3.1): the
fix landed in one home and never propagated to its sibling.

## 3. Fix (independent of M6c, `_power_islands.py` only)

`STITCH_TRACE_WIDTH_MM` now reads `TEMPER_NET_CLASSES["Power"].trace_width`
(imported from `core.design_rules`) instead of a second hardcoded literal --
deriving from the netclass SSOT rather than re-copying a number that can
drift from it again, since a drifted copy is exactly the bug being fixed.
Resolves to `1.0` today, verified by direct import. `compute_corridor_mask`
and the inter-net blocked-check radius are keyed off the same constant, so
the A* corridor search and inter-rail clearance widen consistently with the
emitted geometry -- the same single-knob relationship `_ground_plane.py`'s
own fix already established. No other file touched; `pcb/temper.kicad_pcb`
not touched (sha256 verified unchanged before and after).

Existing test suite: `test_power_islands.py` -- 1 of 2 tests fails, and it
is provably pre-existing/unrelated: `baseline = audit_pcb_file(scratch)`
runs on a bare `shutil.copy` of the committed board, **before**
`generate_power_islands_content` is even called, so nothing in this fix's
diff can affect it. It asserts the committed board's own pre-existing
`+3V3` copper is zero, which has been false since #1312's copper
regeneration gave these rails real copper independent of this module --
already documented as stale in the M6c evidence doc's own regression table
(§4, `test_power_islands.py::...measurably_improve_connectivity`). The
second test (`test_rails_do_not_overlap_on_shared_layer`) passes.

## 4. Full-route standalone measurement: fix applied, no M6c

`scripts/route_board.py` default recipe, from `pcb/temper.kicad_pcb`
(unmodified, sha verified), fresh process, this commit's code (Phase 1 fix
only, no M6c). Result pending -- route in progress, see §5 for the
determinism/DRC table once complete.
