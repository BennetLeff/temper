<!-- provenance: commit=eb5022510d8f1272adf0a27d76c849aa2bb6e210 dirty=false -->

# Git stash corruption incidents: the repo-global stash stack, and the reference-transaction hook that blocks it

**Date:** 2026-07-28 (incidents), hook shipped 2026-07-28, gap closed 2026-07-29
**Status:** resolved — the guard is installed, tested, and reinstalled on every `make worktree`

## Why the stash stack is dangerous in this repo

This repo runs 60+ concurrent agent worktrees against one shared `.git`
directory. The stash stack is repo-global — it is **not** per-worktree. A
`git stash pop` run from one worktree can apply *another session's* stashed
changes into that working tree, and a `git stash drop`/`clear` can destroy
another session's unrecovered work.

The stash list currently sits 80+ entries deep, including rescue records
from prior incidents. Asking politely does not hold at this concurrency.

## Incident 1: 2026-07-28 — stash used despite an explicit prohibition

An agent used `git stash` on 2026-07-28 despite an explicit brief
prohibition. Its push/pop happened to balance, so no data was lost — but
only by luck.

The same day, `docs/solutions/best-practices/shared-mutable-state-dominant-
cost-multi-agent-repo-2026-07-28.md` records a separate, more damaging
instance: a session ran `git stash` / `git stash pop` in direct violation
of the rule and popped a **different** session's entry — a race against a
concurrent session that briefly placed four unrelated files in the wrong
working tree and dropped that other session's stash entry outright.
Recovery required tagging a dangling commit object before GC could reclaim
it and hand-writing a patch file for the other session to apply. A third
invocation that day was an accidental same-rule violation that was harmless
only because nothing was uncommitted at the moment it ran. Three violations
of one hard rule in one day, one with real cross-session damage.

## Incident 2: the hook existed for two weeks before anyone installed it

The reference-transaction hook mechanism was documented and tested — in a
throwaway `/tmp` repo — long before it was ever installed into the live
shared `.git/hooks/`. That distinction mattered: for two weeks the
mechanism existed, documented and tested, while **three more agents used
`git stash` in a single session with the hook doing nothing**.

Timeline:

| Commit | Date | What |
|---|---|---|
| `5f1d532e2` | 2026-07-28 | `chore(stash-guard): block git stash push/save/clear repo-wide via reference-transaction hook` — the guard ships |
| `fdb3f2391` | 2026-07-29 | `fix(hooks): stop git-stash-guard aborting git's own auto-gc (#462)` — the guard stops breaking git's own housekeeping |

The lesson: a documented, tested guard is not an enforced guard until it is
installed in the place that actually fires. `make worktree` now runs
`scripts/install_git_stash_guard.py` on every invocation, so the guard
reinstalls itself — idempotently — every time a worktree is created and
cannot silently go missing from a fresh clone or a `.git/hooks/` wiped by
other tooling.

## The empirical writeup and its pins

- The full empirical writeup (what was tested, in a throwaway `/tmp` repo,
  and what the results were) lives in the comments at the top of
  `scripts/git-hooks/reference-transaction`.
- `scripts/tests/test_git_stash_guard.py` (`TestBlocksRealStashOperations`,
  `TestDocumentedGaps`) pins every one of `stash` / `push` / `push -u` /
  `save` / `clear` / `apply` / `pop` / `drop` against the real hook, so any
  future git version that changes the behaviour fails a test rather than
  silently changing the security posture.

## Related

- `docs/solutions/best-practices/git-stash-guard-mechanism-and-gaps-2026-08-19.md`
  — the guard's design rationale, what it can and cannot block, and the
  alternatives that were ruled out.
- `docs/solutions/best-practices/shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28.md`
  — the same-day incident cluster (stash corruption, disk exhaustion, stale
  extensions, branch-pointer churn) that motivated the guard.
- `scripts/check_stash_stack_gate.py` — the reflog-snapshot detector that
  sees the `apply`/`pop`/`drop` activity the hook structurally cannot.
