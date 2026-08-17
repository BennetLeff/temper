<!-- provenance: commit=caec25d6137c5801e6aa974762b09371f210e894 dirty=false at stub-creation time (worktree agent-a0a4b5d875c1d2a8a). pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1 at stub time. This stub is a placeholder written before any code change, per this project's survival rule (a worktree with no commits is destroyed when the agent stops). -->
---
title: "Refreshing the per-cause unrouted-net breakdown on the regenerated board + attacking the largest tractable class (in progress)"
date: 2026-08-17
module: temper-placer
tags: [router, routing, pad-connectivity, root-cause]
problem_type: routing-completion
status: in-progress
---

# Refreshing the per-cause breakdown + fixing the largest tractable class

**Status: IN PROGRESS.** Committing incrementally per this project's
established survival rule.

## Task

Per `docs/HANDOFF-2026-08-17.md` and the coordinator's brief: the board's
copper was regenerated today (PR #1312) and both fab-floor blockers fixed
(PR #1316). Current committed board sha256
`6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`, measured
63/139 nets fully connected, 36/139 genuine multi-pad, DRC total 1086
(no-refill). PR #1306's Phase 2 per-cause table
(`docs/evidence/2026-08-17-unrouted-nets-rootcause-update.md`) predates
both the copper regeneration and the via fixes and was measured on a
*scratch* route of an *older* board (`fa067a952`, sha `9c1f4a37...`).

This task:
1. Refreshes the per-cause breakdown against the current board.
2. Ranks remaining unrouted nets by cause and tractability.
3. Fixes the largest tractable class (mechanism-level, not net-by-net).
4. Measures connectivity + full DRC (`--refill-zones` and without) before/after.
5. Verifies determinism of any proposed route.

## Plan

1. Build an isolated venv in this worktree (`make venv-isolate`), never
   touching the shared repo `.venv`.
2. Audit the current committed board directly with
   `pad_connectivity_audit.audit_pcb_file` (it is itself a routed board
   now, not scaffolding) to get the live per-net status.
3. Cross-reference against the 2026-08-15 (PR #1290) M1-M5 taxonomy and
   the 2026-08-17 (PR #1306) Phase 2 transition table to reclassify.
4. Identify the largest tractable mechanism class among the still-broken
   nets and propose a mechanism-level fix (not a single net).
5. Re-route on a scratch copy, measure DRC full-context
   (`--severity-all --all-track-errors`, with/without `--refill-zones`),
   confirm determinism across 2 runs.
6. Report before/after honestly, including anything that doesn't improve.

(To be continued in this same file / follow-up evidence docs.)
