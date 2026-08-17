<!-- provenance: commit=aec4bf1f8 dirty=false at stub-creation time (worktree agent-a62e31eb2a2fa68d7). pcb/temper.kicad_pcb sha256 bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5 at stub time -- this stub is a placeholder written before any board write, per this worktree's survival rule (a worktree with no commits is destroyed when the agent stops). -->
---
title: "Regenerating the committed board's copper: verification-before-write (in progress)"
date: 2026-08-17
module: temper-placer
tags: [router, routing, pad-connectivity, drc, board-write, safety]
problem_type: verification-and-decision
status: in-progress
---

# Regenerating the committed board's copper

**Status: STUB, work in progress.** This document will be filled in with the
full before/after measurement (pad connectivity, DRC with and without
`--refill-zones`, isolated_copper, HV-domain net table, determinism check)
and the commit/no-commit decision, per the task brief. Committed now, empty,
so this worktree is not destroyed before the work completes.

## Task

Per `docs/HANDOFF-2026-08-17.md` and
`docs/evidence/2026-08-17-pad-terminal-attachment-generalization.md`: the
committed board's copper has not been regenerated since `556ccf4f0`
(2026-07-27), while placement has moved 46 times since. Of 48 nets with
copper on the committed board, 0 touch their own pads (independently
verified in the referenced doc, not taken on trust here). Task: route from
current main, verify exhaustively, commit only if a strict improvement (or
an explicitly justified, small, understood tradeoff).

## Board identity at task start

- Main: `aec4bf1f8`
- Board sha256 (before any write): `bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5`

## Plan

1. Route from current main using `scripts/route_board.py` default flags, on a
   scratch copy — never write `pcb/temper.kicad_pcb` mid-experiment.
2. Run twice, diff for byte-identical output (non-determinism is a stop
   condition).
3. Verify pad connectivity two independent ways (audit tool +
   from-scratch Euclidean distance), full DRC both with and without
   `--refill-zones` using the SSOT-generated DRU, isolated_copper
   specifically, HV-domain nets individually, fake-completion count.
4. Decide on the data. Commit only if it holds up; otherwise report why not.

(To be continued in this same file.)
