<!-- provenance: commit=775a7a40e dirty=false at stub-creation time (worktree agent-a6d08342e4be16707). pcb/temper.kicad_pcb sha256 33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962 at stub time (this is the post-#1312 board; task is to fix router via emission, not the board's placement). This stub is a placeholder written before any code change, per this project's survival rule (a worktree with no commits is destroyed when the agent stops). -->
---
title: "Blind-via annular-width floor fix (annular_width 0->56, holes_co_located 0->17 regression from #1312)"
date: 2026-08-17
module: temper-orchestration
tags: [router, via, drc, fabrication, annular-width]
problem_type: fix-and-verify
status: in-progress
---

# Blind-via annular-width floor fix

**Status: IN PROGRESS.** Committing incrementally per this project's own
repeated lesson (HANDOFF-2026-08-17 SS15) that uncommitted work is the only
kind that gets lost.

## Task

PR #1312 regenerated the board's copper (0/139 -> 36/139 genuine multi-pad
connections, isolated_copper 109->0, aggregate DRC roughly halved) but
introduced one fabrication-blocking regression: 56 vias with annular ring
below the board's 0.254mm fab floor (JLCPCB 2oz), and 17 co-located holes
from the same mechanism. Root-caused in #1312's own evidence doc
(`docs/evidence/2026-08-17-board-copper-regeneration.md`) to the router's
blind-via emission not applying `net_settings.min_via_annular_width` from
`temper.kicad_pro`.

Touches exactly one HV net (`discharge.r_snub1-p2`, a redundant-not-incorrect
via); otherwise LV/sensing nets only, per #1312's own net-by-net check.

Prior art: #1159 set 44 vias to 0.254mm at the board level; #1173 raised the
annular ring to the 0.254mm fab floor at the board level
(`docs/evidence/2026-08-13-via-annular-ring-floor-fix.md`). Neither touched
the router's own via-emission path, which is what #1312 exercised at scale
for the first time via the ground-plane/power-island MST via-drop generators.

## Plan

1. Find where blind/buried vias get drill/pad diameters during emission:
   `packages/temper-orchestration/src/pipeline_route.rs` (via emission),
   `Via::emit_s_expr()` (the only sexpr API, private fields), `via_placement.py`,
   `_ground_plane.py`, `_power_islands.py` (MST via-drop generators #1312
   identified as the source of the related `via_dangling` findings).
2. Make via emission honour the 0.254mm annular floor as a property of the
   emitted via (constructor-level), not a post-hoc filter -- consistent with
   this repo's five type-system guards (HANDOFF SS7).
3. Re-route and measure annular_width/holes_co_located with and without
   `--refill-zones`, full project context (.kicad_pro + .kicad_dru sidecars),
   `--all-track-errors`.
4. Verify connectivity did not regress (36/139 genuine multi-pad, 63/139
   total, 0 fake completions).
5. Commit fix + regenerated board if clean; report tradeoff if not.

(To be continued in this same file.)
