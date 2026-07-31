---
title: "'Merged into main' is not a safety test for reaping a worktree — 5 of 6 candidates held uncommitted work"
date: "2026-07-29"
category: workflow-issues
module: agent-orchestration
problem_type: workflow_issue
component: development_workflow
severity: critical
applies_when:
  - "reclaiming disk by deleting agent worktrees under time/disk pressure"
  - "a worktree-reaping rule is 'branch is an ancestor of main' or 'branch is merged' with no working-tree check"
  - "deciding whether a worktree is safe to remove and the check considers only the branch, not the working tree"
  - "a naive dirtiness check (`git status --porcelain` with no path filter) reports nearly every worktree as dirty in this repo"
tags:
  - worktree-hygiene
  - disk-exhaustion
  - uncommitted-work
  - reaping-safety
  - tracked-target-dir
  - git-status-porcelain
---

# "Merged into main" is not a safety test for reaping a worktree

## Context

Worktree count reached 56, at roughly 1.8 GB each (~95 GB total), pushing
disk to 94% before cleanup. The obvious reaping rule — remove any worktree
whose branch is an ancestor of `main` (`git merge-base --is-ancestor
<branch> main`), since its commits are presumably safe in `main` already — was
checked against the candidate worktrees before executing, rather than being
trusted on its face. That check would have destroyed real work: **five of
six** "merged" worktrees held uncommitted changes on top of their
already-merged commits, including new untracked source files
(`short_rejection.py`, `check_vacuous_gates.py`), three evidence documents,
and a modified `pcb/temper.kicad_pcb`. A branch being an ancestor of `main`
says nothing about whether the working tree sitting on top of that branch's
checkout still has uncommitted edits — the ancestry check and the safety
question are about two different objects (the branch's commit graph vs. the
worktree's working tree).

**The naive alternative — `git status --porcelain` — is close to useless in
this repo without a path filter.** 472 files under `packages/*/target/` are
**tracked** (kept that way historically; see the shared-mutable-state
incident below for how deletion-by-name against this fact once destroyed
10,612 tracked files). Because build artifacts under `target/` regenerate
with every compile and are tracked, nearly every worktree reports on the
order of 472 dirty paths from stale build output alone — a bare
`git status --porcelain` cannot distinguish "472 lines of regenerated build
byproduct" from "one new untracked source file that represents real,
unrecoverable work." Every one of the 56 worktrees would have read as
"dirty" under a naive check, making the naive check as uninformative as no
check at all.

## The correct test

`git status --porcelain` **excluding `packages/*/target/`**, plus a recency
guard for worktrees a live agent might currently be working in:

```bash
for wt in $(git worktree list --porcelain | grep '^worktree' | cut -d' ' -f2); do
  branch=$(git -C "$wt" rev-parse --abbrev-ref HEAD)
  if git merge-base --is-ancestor "$branch" main; then
    dirty=$(git -C "$wt" status --porcelain -- . ':!packages/*/target')
    mtime=$(find "$wt" -newer /tmp/reap-cutoff -not -path '*/target/*' | head -1)
    if [ -z "$dirty" ] && [ -z "$mtime" ]; then
      echo "SAFE TO REMOVE: $wt"
    else
      echo "HOLDS UNCOMMITTED WORK, SKIP: $wt"
    fi
  fi
done
```

Two facts make this test the right one, not just a stricter one:

1. **Removing a worktree preserves its branch.** `git worktree remove` only
   detaches the working tree from the filesystem; the branch and every
   commit reachable from it survive in the shared object database. A
   worktree whose working tree is genuinely clean (no path outside
   `target/` differs from `HEAD`) is therefore always safe to remove — there
   is nothing in it that `git worktree remove` can lose, because the branch
   it points to still exists afterward.
2. **A worktree with uncommitted changes is exactly the case ancestry cannot
   see.** The five affected worktrees each had a branch fully merged into
   `main` — the ancestry check was correct about the branch — while the
   working tree sitting on that branch had moved on independently (new
   files, further edits) that were never committed anywhere. Removing any of
   those five would have destroyed that work with no recovery path, because
   nothing about it exists in any commit, on any branch, in the shared
   object database.

**Result:** 56 → 29 worktrees reaped safely (the ones that passed both the
ancestry check and the excluded-path dirtiness/recency check), reclaiming
disk from 26 GB free to 39 GB free.

## Guidance

1. **Never treat "branch is an ancestor of main" as sufficient to reap a
   worktree.** It is a necessary check on the branch; it says nothing about
   the working tree. Pair it with a working-tree dirtiness check before
   removing anything.
2. **A dirtiness check in this repo must exclude `packages/*/target/`, or it
   will report false-dirty on nearly every worktree** and either block all
   reaping (if treated as advisory) or get silenced entirely (if someone
   concludes the check is useless and stops running it) — the second
   outcome is worse than no check, because it looks like due diligence was
   done.
3. **Add a recency guard, not just a dirtiness guard.** A worktree can be
   byte-for-byte clean relative to its own `HEAD` and still be the working
   directory a live agent session is actively using right now (mid-edit,
   about to commit). Excluding recently-touched worktrees from automatic
   reaping is cheap insurance against reaping out from under a running
   session.
4. **A worktree that is genuinely clean outside `target/` is always safe to
   remove, full stop** — its branch and commits persist in the shared object
   database regardless. This is the one case that needs no further
   judgment call; the entire risk in this class of incident concentrates in
   the worktrees that are *not* clean.
5. **Before running any bulk worktree-removal command, run the safety check
   as a dry run first and read its output**, the same discipline this
   project applies to `git stash` and branch-repointing in shared
   checkouts — the failure mode (destroying uncommitted work with no
   recovery path) is the same shape as those, just triggered by
   `git worktree remove` instead of `git stash`/`git checkout -B`.

## Why This Matters

The reaping rule that looked obviously safe — "the branch already made it
into `main`, so the worktree is redundant" — was correct in the one
dimension it checked and silent about the one dimension that mattered.
Five of six candidates would have lost real, unrecoverable work: new source
files with no commit anywhere, evidence documents recording investigation
that would have to be redone, and a hand-edited PCB file. None of that loss
would have produced an error message — `git worktree remove` succeeds
unconditionally on a worktree with uncommitted changes unless `--force` is
withheld and the command is run without it, and even then the warning is
easy to script past under disk pressure. The check that caught this cost
one `git status --porcelain -- . ':!packages/*/target'` invocation per
candidate; the five-worktree loss it prevented would have cost the original
implementation effort behind each one.

## When to Apply

- Before any disk-pressure-driven worktree cleanup, automated or manual.
- Before trusting any reaping rule based solely on branch ancestry
  (`git merge-base --is-ancestor`, `git branch --merged`) — pair it with a
  working-tree check.
- Before writing a "is this worktree dirty" check in this repo specifically
  — exclude `packages/*/target/` or the check will be useless noise on every
  worktree.
- When a worktree cleanup script reports "N dirty, skipped" — inspect a
  sample manually before assuming the exclusion filter is complete; a filter
  that misses one tracked-and-regenerated directory reproduces the same
  false-dirty-everywhere failure this incident's naive check hit.

## Examples

```bash
# WRONG -- branch ancestry alone, blind to uncommitted worktree state
git merge-base --is-ancestor "$branch" main && git worktree remove "$wt" --force
# 5 of 6 candidates checked this way held uncommitted new files/edits

# WRONG -- naive dirtiness check, drowned out by tracked build artifacts
git -C "$wt" status --porcelain | wc -l    # ~472 on nearly every worktree,
                                            # from tracked packages/*/target/
                                            # regenerating on every compile

# RIGHT -- ancestry AND excluded-path dirtiness AND recency
git merge-base --is-ancestor "$branch" main \
  && [ -z "$(git -C "$wt" status --porcelain -- . ':!packages/*/target')" ] \
  && [ -z "$(find "$wt" -newer "$CUTOFF" -not -path '*/target/*')" ] \
  && git worktree remove "$wt"
```

## Related

- `docs/solutions/best-practices/shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28.md`
  — the sibling multi-worktree hazard from the same period: hand-cleanup
  under disk pressure destroying 10,612 *tracked* files by deleting
  `target/` directories by name rather than via `git check-ignore` (that
  incident is about deleting build output *inside* a worktree; this one is
  about deleting the *whole worktree*, but both are "isolation at the
  worktree level does not imply the cleanup mechanism is safe").
- `docs/solutions/workflow-issues/silent-source-loss-worktree-parallel-merges-2026-07-01.md`
  — a different worktree hazard (merge conflict resolution silently
  dropping files) with the same underlying lesson: verify before trusting
  that a git operation preserved everything it looked like it preserved.
- `docs/solutions/best-practices/a-measurement-carries-its-commit-2026-07-26.md`
  — names worktree proliferation (40+, later 51) as a standing hazard for
  stale measurements; this doc is the companion hazard on the cleanup side
  of the same proliferation problem.
