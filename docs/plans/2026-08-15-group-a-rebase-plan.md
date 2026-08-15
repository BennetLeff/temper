# Group-A Rebase Plan — 34 branches on board b7d865b7 (2026-08-15)

Status: **PREPARED, NOT EXECUTED.** Blocked on PR #1134 (board resync) landing on
main. This document is the verified branch list, the conflict map from a dry-run
simulation, and the execution procedure. Execution must not begin until the
resync is on main.

## 1. Gate: what we are waiting for

| PR | branch | state | board it produces |
|---|---|---|---|
| #1201 | fix/zcd-orphan-footprint-removal | OPEN (not merged) | 5e5015f8 (ZCD removal) |
| #1134 | fix/board-schematic-resync | OPEN (not merged) | **b7d865b7 (the resync)** |

Per Agent 9's decision record (`docs/evidence/2026-08-15-board-freeze-merge-sequence.md`),
merge order is #1201 first, then #1134. Neither has merged. main's committed board
is still `6928b7c8` (freeze-start hash; `git show origin/main:pcb/temper.kicad_pcb |
sha256sum`).

The resync worktree (`/home/bennet/Desktop/temper-board-schematic-resync`) is clean,
last commit 2026-08-13 11:39 -0600; PR #1134's last activity 2026-08-13. No agent
appears to be actively mid-edit on it. If this stays stalled, the blocker is owner
merge action (and #1201 must land first per the plan).

## 2. Verified branch list (34/34 match Agent 9's matrix)

Verified 2026-08-15 against live `origin/*` after `git fetch --prune`:

- **34/34** branches have tip board sha256 = `b7d865b7` (resync output)
- **34/34** branches have merge-base board = `6928b7c8` (== current main board)
- **34/34** branches contain resync commit `96ebe489c` as an ancestor
- **34/34** branches have **zero** board commits beyond the resync
  (`git rev-list --count 96ebe489c..origin/<b> -- pcb/temper.kicad_pcb` == 0)
- **34/34** have open PRs; PR numbers match Agent 9's matrix exactly

Full matrix is in `/tmp/opencode/group_a_branches.txt` and
`docs/evidence/2026-08-15-board-freeze-merge-sequence.md` §4.

Because each branch's board is byte-identical to what main will become once #1134
lands, the board file itself cannot conflict in any of these rebases. This is the
core premise and it is **verified**, not assumed.

## 3. Dry-run simulation (performed, nothing pushed)

Simulated "main after #1134" by merging `origin/fix/board-schematic-resync` into a
scratch branch off origin/main (`sim/after-resync`); merged board hash =
`b7d865b7` — byte-identical to the resync's own board. Then rebased every Group-A
branch onto the sim in a throwaway worktree, one at a time, aborting after each.

Result: **27 CLEAN, 7 CONFLICT — every conflict is in a non-board file; zero
`pcb/temper.kicad_pcb` conflicts in any branch.**

### Conflict map (7 branches, 6 distinct hunks)

| branch | PR | conflicting file | classification | resolution sketch |
|---|---|---|---|---|
| chore/inert-code-audit | #1189 | `packages/temper-placer/src/temper_placer/validation/gate_input_registry.py` | registry entries added on both sides (1 hunk, 21 lines) | union — keep both registry entries; mechanical |
| fix/circle-poly-bounds | #1179 | `packages/temper-design-bundle/src/parse_engine.rs` | both sides added `#[test]` fns in same region (1 large hunk ~206 lines) | keep both test sets; verify `cargo test` after |
| fix/dedup-defect-multiplier | #1181 | `.../router_v6/_pipeline_grid.py` | docstring-only (branch consolidates to SSOT `net_pad_positions`; main kept long inline doc) | take branch side (delegation is newer refactor); trivial |
| fix/hyphen-netclass-boundary | #1162 | `packages/temper-placer/tests/core/_design_rules_py_oracle.py` | comment/RE-PIN note only, 2 hunks — **oracle data unchanged** | take merged comment; **oracle content identical so no re-pin** |
| fix/oracle-registry-blindspot | #1184 | `.../router_v6/_pipeline_grid.py` | **same dedup-commit conflict as #1181** (docstring-only) | same resolution as #1181 |
| fix/trace-width-authoritative-source | #1188 | `.../router_v6/trace_width_assignment.py` | docstring + width-selection logic, 2 hunks | needs care: branch's `_netclass_trace_width` vs main's keyword cascade — logic-level, resolve deliberately |
| geom/dedupe-primitives-a374c69e | #1183 | `.../router_v6/_pipeline_grid.py` | **same dedup-commit conflict as #1181** (docstring-only) | same resolution as #1181 |

Notes:
- Three branches (#1181/#1184/#1183) hit the **identical** `_pipeline_grid.py`
  conflict because they share dedup commit `319f564f5` — one studied resolution
  covers all three.
- The oracle conflict (#1162) is in a **pinned oracle**; the conflict is confined
  to the RE-PIN documentation comments. Resolution must keep the oracle data
  bytes identical, otherwise `scripts/oracle_hashes.json` re-pin discipline
  (handoff §1) applies. Dry-run inspection confirms the data is not part of the
  conflict hunks.
- All conflicts are smaller than the file's conflict count suggests: 6 files, 1–2
  hunks each, all in code/docs the branches own.

### Caveat on simulation fidelity

The sim merge resolved #1134's own landing conflicts in
`test_domain_clearance.py` and `drc_ceiling.json` by taking the branch side
(`--theirs`). Those two files are not part of any Group-A branch's conflict set,
so the choice does not affect the conflict map. main may also move further before
#1134 lands (more PRs merge), which can only add new conflicts, never remove the
board-clean property (that property is structural: identical board bytes on both
sides).

## 4. Execution procedure (run only after #1134 is on main)

One branch at a time, never batched. For each branch:

1. `git fetch origin`
2. Verify the branch's tip board is still `b7d865b7`; if not, **stop** and report
   (something else moved it).
3. `git worktree add /tmp/opencode/rebase-<branch> -b rebase/<branch> origin/<branch>`
4. `git rebase origin/main`
5. Clean → `git push origin rebase/<branch>:<branch> --force-with-lease`;
   PR (all 34 exist) updates automatically.
6. Conflict:
   - **Any `pcb/temper.kicad_pcb` conflict → STOP immediately, report, do not
     resolve** (hand-resolving the board has destroyed content twice).
   - Non-board conflicts from the map above → resolve per the sketches; verify
     (`cargo test`/pytest for touched modules); commit; continue.
   - New/unknown conflicts → resolve only if trivially mechanical; otherwise
     stop and report that branch.
7. `git worktree remove /tmp/opencode/rebase-<branch>`

Special cases:
- `fix/board-schematic-resync` (#1134): once it is merged, its branch is likely
  merged/deleted by GitHub — skip it if gone; if the branch still exists, rebasing
  it onto main is still clean (verified in dry-run).
- Branches where the shared dedup resolution applies: resolve once, apply to all
  three, verify each independently.

## 5. Report format

Deliver a table: branch → result (rebased/conflict/stopped) → PR state
(updated/unchanged). Conflicted branches get an explanation; board-conflict
branches are reported as STOP with zero guessing.
