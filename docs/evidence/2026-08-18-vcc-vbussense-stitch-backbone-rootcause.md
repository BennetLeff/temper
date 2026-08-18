<!-- provenance: commit=11a7e7c52d21ebca3ff8ff06e6e3b941441189fd dirty=false (worktree agent-a9684758c5ea3beaf, main tip at task start). pcb/temper.kicad_pcb sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b at stub time, matches task brief -- this stub is a placeholder written before any board write, per this project's survival rule (a worktree with no commits is destroyed when the agent stops). -->
---
title: "vcc and V_BUS_SENSE have zero stitch segments at any width -- root cause and fix"
date: 2026-08-18
module: temper-placer
tags: [router, zone-stitch, power-islands, c-space, drc, connectivity]
problem_type: drc-defect
status: in-progress
---

# vcc / V_BUS_SENSE: zero-stitch-segment root cause and fix

**Status: IN PROGRESS**, committed incrementally per this project's survival
rule (a worktree with no commits is destroyed on stop).

## Task, per the coordinating brief

Of the four `POWER_ISLAND_NETS`, `+3V3` (89 segments) and `+15V` (32
segments) kept genuine 1.0mm backbone copper after PR #1332's collision
check landed. `vcc` (0 segments, 11 vias) and `V_BUS_SENSE` (0 segments, 3
vias) kept none -- every MST backbone edge for both rails collided at the
corrected 1.0mm width and was dropped fail-closed, per
`docs/evidence/2026-08-17-board-write-stitch-width-and-collision-fix.md`
(`vcc`: 12 edges + 2 stubs dropped; `V_BUS_SENSE`: 3 edges + 1 stub
dropped -- 100% of both rails' edge sets).

Root-cause why every edge collides for these two rails specifically
(routing order / MST topology / corridor width / via-drop placement), fix
it in `_power_islands.py` (checking `_ground_plane.py` for a twin) if
tractable at 1.0mm, or document the placement-infeasibility finding with
evidence if not. Hard constraints: stitch width floor 1.0mm (never lower),
PR #1332's collision check stays (never weaken/bypass), no
clearance/creepage/DRU/copper-weight threshold changes, no
`pcb/temper.kicad_pcb` write without reporting first.

Board identity at task start: main `11a7e7c52d`, board sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
(unchanged; not touched by this task except with explicit reporting
first).

## Plan

1. Read `_power_islands.py` end to end: MST construction, primary A*
   corridor-backbone pass, `_blocked()` fallback, via-drop stub emission.
   Diff against `_ground_plane.py` for the clone-drift pattern already
   found 3x this project.
2. Instrument/measure why `vcc` and `V_BUS_SENSE` specifically hit 100%
   collision -- net ordering (are they routed after `+3V3`/`+15V` consume
   the shared corridors?), MST edge geometry (edge length/routing through
   congested areas), corridor width at 1.0mm+clearance, via-drop offset
   geometry.
3. Fix the largest tractable cause in `_power_islands.py` (and
   `_ground_plane.py` if a twin function is implicated), or write up the
   placement-infeasibility finding with geometric evidence.
4. Re-route from a scratch copy (isolated venv, verify
   `temper_placer.__file__` resolves inside this worktree), determinism
   check (two byte-identical routes), full DRC re-measurement against the
   task's ledger (shorting_items <=42, clearance <=189, HV<->LV creepage
   <=77, connectivity >=60/139, fake completions <=6 by name,
   track_width stays 0).
5. Report the full ledger, fake completions by name, any `_ground_plane.py`
   twin touched.

(To be continued in this same file, appended incrementally as measurements
land.)
