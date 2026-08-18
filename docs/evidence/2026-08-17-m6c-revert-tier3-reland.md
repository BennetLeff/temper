<!-- provenance: commit=342e1bd08 dirty=false (worktree agent-a7e7a9c50f564ffdb, main tip at task start). pcb/temper.kicad_pcb sha256 cb5184eae9fea94c4b7b3c68c553ce97923a0d8f9af9d0fbb87442ab593c39b3, matches task brief. -->
---
title: "Revert M6c (PR #1329's incidental carry), land Tier-3 span-scaled budget fix, re-route and measure"
date: 2026-08-17
module: temper-placer
tags: [router, revert, routing-completion, drc]
problem_type: routing-completion
status: in-progress
---

# M6c revert + Tier-3 span-scaled budget reland

**Status: IN PROGRESS.** Stub committed first per this project's survival
rule (a worktree with no commits is destroyed on stop). Findings and
measurements follow in later commits to this same file.

## Task, per the coordinating brief

1. Revert M6c's four files to their pre-PR-#1329 state
   (`_astar_nlayer.py`, `routing_results.py`, `terminal_tree_execution.py`,
   `test_all_pad_tree_routing.py`), while keeping PR #1329's
   `_power_islands.py` stitch-width fix and PR #1332's collision-check
   work on that same file.
2. Land the Tier-3 span-scaled search-budget fix from branch
   `worktree-agent-a117df333e1fd0c5f` (built on M6c-containing main;
   needs reconciling against the revert).
3. Re-route and measure: connectivity, DRC (both refill modes, HV/LV
   creepage broken out), fake-completion count, determinism (two
   byte-identical routes), in an isolated venv verified to resolve inside
   this worktree.
4. Commit the board only if connectivity improves (target >= 62/139) and
   no DRC category regresses. Otherwise report the finding as-is.

## 0. State at task start

- Main tip: `342e1bd08`.
- `pcb/temper.kicad_pcb` sha256 `cb5184eae9fea94c4b7b3c68c553ce97923a0d8f9af9d0fbb87442ab593c39b3` --
  matches the task brief exactly.
- M6c's four files landed via PR #1329 (`7979a0ee1`, 2026-08-17 18:33),
  bundled with the independent `_power_islands.py` pour-stitch fix.
  `7979a0ee1^` is confirmed (via `git log -- <path>`) to be the last
  commit touching `_astar_nlayer.py` before M6c, i.e. the correct revert
  target for all four M6c files.
- `_power_islands.py` at current HEAD carries both `STITCH_TRACE_WIDTH_MM
  = TEMPER_NET_CLASSES["Power"].trace_width` (PR #1329) and the
  `other_copper_fcu_backbone`/`routed_fcu_backbone` collision checks
  (PR #1332) -- confirmed present by direct grep before starting the
  revert.
- Tier-3 fix source: `docs/evidence/2026-08-17-hop-reachability-rootcause-and-fix.md`
  on worktree `agent-a117df333e1fd0c5f` (branch tip `666cfd64d`). Its own
  §6 states the fix was verified only via unit/property regression (394
  passed, 2 pre-existing unrelated failures) and structural
  can't-fabricate-completions argument -- three full-route verification
  attempts were killed unfinished. A full-board connectivity/DRC/
  determinism measurement of the shipped fix does not yet exist anywhere
  and is this task's job to produce.

## 1-4. To follow

Revert mechanics, reconciliation diff, isolated-venv proof, and the full
measured ledger will be appended to this document as they are completed.
