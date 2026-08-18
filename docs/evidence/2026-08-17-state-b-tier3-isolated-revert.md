<!-- provenance: commit=11a7e7c52 dirty=false (worktree agent-aae83c10fb1cc9674, main tip at task start). pcb/temper.kicad_pcb sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b, matches task brief exactly ("current main"). -->
---
title: "State B: M6c reverted, Tier-3 span-scaled budget fix ALSO reverted — isolating which of #1334's two changes caused fake completions 14->6"
date: 2026-08-17
module: temper-placer
tags: [router, revert, routing-completion, drc, fake-completions]
problem_type: routing-diagnostic
status: in-progress
---

# State B: isolating M6c-revert vs Tier-3-fix as the cause of fake completions 14 -> 6

**Status: IN PROGRESS.** Stub committed first per this project's survival
rule (a worktree with no commits is destroyed on stop). Findings and
measurements follow in later commits to this same file.

## Task, per the coordinating brief

Commit `11a7e7c52` (current main tip) did two things in one commit:
1. Reverted M6c (partial-geometry writing on unreachable serial waypoint
   chains) back to pre-PR-#1329 state, across four files.
2. Landed the Tier-3 span-scaled search-budget fix (`_astar_nlayer.py`
   only, one call site: `segment_3d_fallback_max_iter=max(per_net_max_iter,
   _SEGMENT_3D_FALLBACK_MAX_ITER)`), replacing Tier 3's flat 200,000
   default.

Fake completions moved 14 (state A: M6c present, Tier 3 absent, board
`cb5184eae9...`) -> 6 (state D: M6c reverted, Tier 3 landed, board
`26981fea2d...`, current main). Which change caused it?

**State B (this task): M6c reverted, Tier 3 ALSO reverted/absent.** Take
current main, keep the M6c revert, but undo only the ~40-line Tier-3
call-site change identified in `_astar_nlayer.py` (confirmed by direct
diff inspection of `11a7e7c52` to be the ONLY Tier-3-related change in
the whole commit — the other three M6c files and `_power_islands.py`
carry zero Tier-3 content). Route twice, count fake completions and their
specific net identities, compare against A (14) and D (6).

## 0. State at task start

- Main tip: `11a7e7c52`.
- `pcb/temper.kicad_pcb` sha256
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` --
  matches the task brief's stated current-main hash exactly.
- Confirmed by direct `git show 11a7e7c52 --stat` and full diff
  inspection: the Tier-3 fix touches exactly one file
  (`_astar_nlayer.py`), one call site (the `_astar_route_nlayer(...)` call
  inside `attempt_route`, plus its preceding comment block) — no other
  file in the commit (`routing_results.py`, `terminal_tree_execution.py`,
  `test_all_pad_tree_routing.py`, `pcb/temper.kicad_pcb`) contains any
  `segment_3d_fallback_max_iter`/`_SEGMENT_3D_FALLBACK_MAX_ITER` content.
  `_power_islands.py` is not part of this commit's diff at all (last
  touched by PR #1329/#1332, both upstream of this commit) — confirmed
  untouched, will not be touched by this task either.

## 1. Plan

1. Isolated venv (`make venv-isolate`), verify `temper_placer.__file__`
   resolves inside this worktree before trusting any number. Watch for
   the documented CARGO_TARGET_DIR stale-fingerprint hazard.
2. Edit `_astar_nlayer.py`: remove the `segment_3d_fallback_max_iter=...`
   kwarg (and its comment block) from the `_astar_route_nlayer` call site,
   restoring the implicit default (`_SEGMENT_3D_FALLBACK_MAX_ITER` =
   200,000 flat, unscaled) — i.e. exactly what state D's file looked like
   before the Tier-3 hunk of #1334 was applied, with the M6c revert left
   fully in place (already true of the working tree at commit start).
3. Two full `route_board.py` runs from the committed board's own
   placement, byte-identical required.
4. Count fake completions via `NetRouteResult`/`verify_continuity()` /
   `pad_connectivity_audit`, same methodology as the m6c-revert-tier3-
   reland doc. Report specific net identities.
5. Report connectivity alongside. Compare against A (14, `cb5184eae9`)
   and D (6, `26981fea2d`, current committed board unchanged).
6. Do NOT commit any board changes. `pcb/temper.kicad_pcb` must remain at
   `26981fea2d...` (byte-identical to the currently committed file) when
   this task ends — only scratch copies under `/tmp` are routed.

Findings follow below in later commits to this file.
