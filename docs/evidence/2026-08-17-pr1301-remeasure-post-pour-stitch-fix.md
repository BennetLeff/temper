<!-- provenance: commit in progress on branch pr1301-rebase-work (PR #1301's 4 commits rebased cleanly onto main 2cc9eeb1e). Worktree agent-a45a533968d4d8742. pcb/temper.kicad_pcb NOT modified -- all measurement on scratch copies under /tmp. STUB -- being filled in incrementally per this project's survival rule (a worktree with no commits is destroyed on stop). -->
---
title: "PR #1301 re-measurement on the pour-stitch-fixed base: does track_width +71 vanish?"
date: 2026-08-17
module: temper-placer/router_v6
tags: [router, clearance, drc, pr-1301]
problem_type: pr-reevaluation
status: in-progress
---

# PR #1301 re-measurement — STUB, in progress

## Task

Re-evaluate PR #1301 (per-pair clearance halos, `_astar_nlayer.py` +
`pair_clearance.py`) now that PR #1329 (pour-stitch `STITCH_TRACE_WIDTH_MM`
fix, `track_width` 120→0) has merged to main. #1301 was held on an
independent reviewer re-measurement showing `track_width` +71 as the
dominant, unexplained cost (clearance −29 against track_width +71,
shorting_items +13, creepage +5, tracks_crossing +4; total +52). Hypothesis:
100% of that +71 was the same pour-stitch defect PR #1329 already fixed
(both operate on the same congested board region), so re-measured on the
fixed base, #1301 should look like clearance −29 against much smaller
costs.

## 1. Rebase (done)

`fix/per-pair-clearance-halos-nlayer-astar` (origin tip `f64032f09`)
rebased cleanly onto main `2cc9eeb1e` (the commit this task's brief pins as
current). Local branch `pr1301-rebase-work` in this worktree, 4 commits:
`1e7c1cb27` (fix), `f612ff55a` (test), `8516fcbf4` (evidence doc),
`15b76db4c` (evidence doc followup) -- content-identical to the PR's own
`0e0b40e33`/`2762f7af0`/`e39ec28a2`/`f64032f09` (verified: `pair_clearance.py`
byte-identical; `_astar_nlayer.py` differs only by unrelated rebase-forward
content already on main, e.g. M6c's serial-waypoint-chain resilience and
`#1303`'s mypy-suppression removal). No commits discarded, no force-push
over the PR branch. Backed up to `origin/pr1301-rebase-work` (new branch,
does not touch `fix/per-pair-clearance-halos-nlayer-astar`).

**Note for the M6c sibling**: main's own `_astar_nlayer.py` (independent of
this rebase) already carries M6c-shaped serial-waypoint-chain resilience
code as of commit `1e7c1cb27`'s ancestry -- if your M6c re-evaluation also
touches this file, diff against current main first; some of what M6c would
add may already be present.

## 2. Baseline + after-route measurement (in progress)

Two scratch worktrees, no Rust changes between them (PR #1301 touches only
`.py`/`.md`), same shared `.venv`'s compiled extensions, sys.path override
per worktree (`route_via.py`) to avoid the documented shared-venv trap
(main checkout's editable pointer):

- `_scratch/baseline-main` -- detached at `2cc9eeb1e`, i.e. main WITHOUT
  PR #1301.
- this worktree (`pr1301-rebase-work`) -- main WITH PR #1301 rebased on.

Full `route_board.py` default recipe on each, then DRC (`kicad-cli 10.0.5`,
`--severity-all --all-track-errors`, full project context: `.kicad_pro` +
freshly-generated `.kicad_dru` + `fp-lib-table` + `libs`), with and without
`--refill-zones`. Connectivity via `pad_connectivity_audit.audit_pcb_file`
(the same `NetConnectivityResult.category`/`is_fake_completion` verdict the
project's other evidence docs use -- never "A* returned a path").

Results to follow in an update to this document.

## 3. Still to do

- Full DRC ledger diff (all categories, not just the 5 headline ones).
- `shorting_items` root cause if it survives — HV involvement check.
- Determinism: two independent `pr1301-rebase-work` routes, byte comparison.
- Merge decision.
