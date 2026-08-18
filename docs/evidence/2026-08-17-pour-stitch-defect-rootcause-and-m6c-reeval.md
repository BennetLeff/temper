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

## Baseline provenance (this document's own, not inherited)

To be filled in as measured. Two measurements of this board have differed by
~129 today per the coordinating brief; this document states its own kicad-cli
version, invocation, and sample count for every number it reports.

(measurement in progress -- see below, updated as work proceeds)
