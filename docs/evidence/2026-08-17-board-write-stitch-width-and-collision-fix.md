<!-- provenance: commit=4d7373ecadfebfff79a74933c3ce441b6cc8e127 dirty=false (worktree agent-a77928be4db4676d4, main tip at task start, includes PR #1332). pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1 at stub time, matches task brief -- this stub is a placeholder written before any board write, per this project's survival rule (a worktree with no commits is destroyed when the agent stops). -->
---
title: "Applying PR #1329 + PR #1332 to the committed board — landing the stitch width and collision-check fixes"
date: 2026-08-17
module: temper-placer
tags: [router, zone-stitch, power-islands, drc, track_width, board-write]
problem_type: verification-and-decision
status: in-progress
---

# Applying PR #1329 + PR #1332 to the committed board

**Status: IN PROGRESS**, committed incrementally per project survival rule
(a worktree with no commits is destroyed on stop).

## Task

Both PR #1329 (stitch width 0.3mm -> 1.0mm derived from
`TEMPER_NET_CLASSES["Power"].trace_width`) and PR #1332 (collision-check
fix for the two previously-unchecked `_power_islands.py` emission paths --
`_blocked()`'s zero-width probe and the unchecked via-drop stub) are merged
to main (`4d7373eca`). **The committed `pcb/temper.kicad_pcb` still carries
120 `(width 0.3000)` traces and 120 corresponding `track_width` violations**
-- the artifact is stale relative to the code, per HANDOFF-2026-08-17 §12's
"validated on scratch copy, never applied to committed artifact" trap.

Two predecessor evidence docs establish the mechanism and measured effect:
- `docs/evidence/2026-08-17-stitch-width-fix-board-reroute.md` (branch
  `worktree-agent-a838d24359b83fcae`, width-fix-only, deliberately NOT
  merged/applied to the board -- measured `shorting_items` 53->130, +77,
  root-caused to an unchecked emission path, not "no room").
- `docs/evidence/2026-08-17-stitch-congestion-rootcause-and-fix.md` (PR
  #1332, merged as `4da46bac2`/landed as part of `4d7373eca` -- fixes the
  root cause, re-measures `shorting_items` 130->42, HV<->LV creepage 88->77,
  connectivity 59/139, determinism confirmed byte-identical across 2 runs).

Board identity at task start: main `4d7373ecadfebfff79a74933c3ce441b6cc8e127`,
board sha256 `6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`
(unchanged from prior sessions; not touched by this task except with
explicit verification-first reporting per the owner's conditional
authorization).

## Plan

1. Isolated venv in this worktree (`make venv-isolate`/`uv sync`), verify
   `temper_placer.__file__` resolves inside this worktree, and
   `STITCH_TRACE_WIDTH_MM == 1.0` before trusting any number.
2. Route from current main (`4d7373eca`) on a scratch copy only, twice, for
   determinism.
3. Full DRC (`--severity-all --all-track-errors`, full project context,
   both refill modes) against the expected table in the task brief.
4. Independent connectivity check (both methods), fake completions, HV<->LV
   creepage breakdown, placement-invariance (0 footprint `(at ...)` lines
   changed), `grep -c "(width 0.3000)"` == 0.
5. Decide on the data against commit criteria. Write `pcb/temper.kicad_pcb`
   only at the final verified commit step.

(To be continued in this same file, appended incrementally as measurements
land.)
