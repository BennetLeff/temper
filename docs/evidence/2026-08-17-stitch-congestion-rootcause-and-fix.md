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
