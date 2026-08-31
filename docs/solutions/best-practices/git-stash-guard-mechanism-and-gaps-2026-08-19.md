---
title: "The git stash guard: mechanism, known gaps, and the alternatives that were ruled out"
date: "2026-08-19"
category: best-practices
module: development_workflow
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - "running `git stash`, `git stash apply`, `git stash pop`, or `git stash drop` in any worktree of this repo — the stash stack is repo-global, not per-worktree"
  - "choosing a mechanism to enforce a repo-wide git policy across worktrees that share one `.git` directory"
  - "reading a `git stash list` that looks empty and concluding the stack is clean"
tags:
  - git-stash
  - reference-transaction-hook
  - shared-worktree-state
  - multi-agent-workflow
  - guard-mechanism
---

# The git stash guard: mechanism, known gaps, and ruled-out alternatives

## The rule

**Never use `git stash`, in any form, in this repo.** The stash stack is
repo-global — shared by every worktree against the same `.git`. A
`git stash pop` from your worktree can apply *another session's* stashed
changes into your working tree, and a `git stash drop`/`clear` can destroy
another session's unrecovered work. See
`docs/evidence/2026-07-28-git-stash-guard-incidents.md` for the incidents
that made this a hard rule.

## The mechanism: a reference-transaction hook

`scripts/git-hooks/reference-transaction`, installed into the shared
`.git/hooks/` directory by `scripts/install_git_stash_guard.py`, blocks
`git stash` / `git stash push` / `git stash push -u` / `git stash save` /
`git stash clear` outright (exit 128, `fatal: ref updates aborted by
hook`).

This is a real, tested block: it fires under non-interactive, direct `git`
invocation, from every worktree sharing this repo's `.git` directory,
without relying on any shell alias or `PATH` trick — a git hook is invoked
by the `git` binary itself, regardless of what invoked `git`.

`make worktree` runs the installer on every invocation, so the guard
reinstalls itself — idempotently — every time a worktree is created, and
cannot silently go missing from a fresh clone or a `.git/hooks/` wiped by
other tooling. Check or (re)install by hand:

```bash
python3 scripts/install_git_stash_guard.py --check   # report only
python3 scripts/install_git_stash_guard.py            # install/update
```

## Known, tested gaps — the hook is not full coverage

- **`git stash apply` can never be blocked by this hook**: `apply` performs
  no ref transaction, and no hook of any kind fires for it.
- **`git stash pop` / `git stash drop <entry>` cannot reliably be blocked**
  except in the edge case where the entry being removed is the *only* one
  left on the stack. With 80+ existing entries, dropping/popping any one of
  them rewrites the reflog directly, bypassing the hookable ref-transaction
  API entirely.

**The prohibition on `apply`, `pop`, and `drop` is a policy rule, not an
enforced one.** Do not treat the hook as covering them. The full empirical
writeup (what was tested, in a throwaway `/tmp` repo, and the results) is
in the comments at the top of `scripts/git-hooks/reference-transaction`;
`scripts/tests/test_git_stash_guard.py` pins every one of the seven
commands against the real hook so a future git version that changes this
behaviour fails a test, not silently changes the security posture.

### The "last remaining entry" edge case

Even in the one case where dropping *is* blocked (removing the last
remaining entry), git rewrites `refs/stash`'s reflog *before* the hook is
consulted, so `git stash list` goes empty regardless of the block. The
underlying commit is not deleted (`refs/stash` itself is unchanged and the
object stays resolvable/reachable), but it becomes invisible to the normal
stash UI. **Do not read "hook fired" as "the stack looks untouched"** for
this one case; it means "the data was not destroyed," which is not the same
thing.

## Defense in depth: the reflog-snapshot detector

`uv run python scripts/check_stash_stack_gate.py` snapshots the stash
reflog and diffs it against the last snapshot, flagging any addition or
disappearance since the last run. It is not a CI gate (CI runners don't
share this `.git` directory) — run it manually, on a timer, or from a
`/loop` against the actual dev machine. A baseline snapshot lives at
`<git-common-dir>/stash-guard-snapshot.json`. It stays alongside the hook
rather than being superseded by it, because it is the only thing that sees
`apply`/`pop`/`drop` activity the hook structurally cannot block.

## The bypass, and why it is narrow

For a human, working alone, in a clean single-worktree context — *not* the
concurrent-agent failure mode this guards against:

```bash
ALLOW_GIT_STASH=1 git stash push -m "..."
```

## Safe alternatives to the underlying need

Comparing with/without your changes is a real need and is not disabled, just
routed elsewhere:

```bash
git worktree add ../scratch-<name> -b scratch/<name>   # isolated copy
git branch wip/<name> && git commit -am wip             # scratch branch
git diff > /tmp/patch.diff                               # patch file, git apply later
```

## What was ruled out and why

Tested empirically (see the PR that introduced this section for the full
transcript):

- **A `pre-commit` hook never fires for stash** — stash is not a commit
  operation.
- **A shell alias/function shadowing `git stash` only protects interactive
  shells that source it** — agents invoke `git` directly.
- **`git config alias.stash=...` does not work** — this git version
  resolves built-in commands (`stash`, `status`, `log`, ...) before
  consulting aliases, so an alias can never shadow an existing subcommand,
  only add a new one.
- **A `PATH` wrapper earlier than the real `git` was not pursued** — it
  requires modifying the user's shell environment (not something a
  repo-scoped fix should assume or require) and offers no more coverage
  than the hook already provides.

## Related

- `docs/evidence/2026-07-28-git-stash-guard-incidents.md` — the incidents.
- `docs/solutions/best-practices/shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28.md`
  — the same-day incident cluster.
