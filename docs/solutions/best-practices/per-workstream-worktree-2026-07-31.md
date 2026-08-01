---
title: "Per-workstream worktrees are the default for new work in a multi-agent repo"
date: "2026-07-31"
category: best-practices
module: development_workflow
problem_type: best_practice
component: development_workflow
severity: medium
applies_when:
  - "starting new work that will touch tracked Rust/Python source in this repo"
  - "a task's changes must be isolated from other agents' in-flight edits in the shared checkout"
  - "a workstream needs to be PR'd as one coherent unit against a specific base"
tags:
  - worktree-isolation
  - multi-agent-workflow
  - patch-extraction
  - shared-checkout-hazards
  - make-worktree
---

# Per-workstream worktrees are the default for new work

This repo runs dozens of concurrent agent worktrees against one shared `.git`,
one shared build cache (`target-shared`), and — unless isolated — one shared
`.venv`. The shared main checkout is a rotating workbench where multiple
agents' in-flight changes live side by side. Working there means your
uncommitted changes are *mixed with theirs*, and getting your work out later
requires surgical patch extraction.

## The pattern

**One worktree per workstream, branched from the right base, verified and
PR'd directly from that worktree.** Never start tracked-source work in the
shared main checkout.

```bash
# from the repo root:
make worktree NAME=fix-driver-latch BASE=origin/main VENV=1
cd ../temper-wt-fix-driver-latch   # do the work here
# ... edit, cargo test, cargo clippy, commit, push, gh pr create
```

- `NAME` = branch and PR name. `BASE` defaults to `origin/main`; point it at a
  migration branch when the work depends on unmerged work there.
- `VENV=1` provisions the worktree's own `.venv` (`make venv-isolate`, ~85s
  warm-cache) so a concurrent session's `uv sync`/`maturin` cannot silently
  revert an extension you just built. Skip it for pure-Python/docs work to
  save ~700 MB disk.
- `WT_PATH=...` overrides the default sibling path `../temper-wt-<NAME>`.

## Why (incidents this closes)

The pattern exists because working in the shared checkout produced, in one
session:

- **Parallel-edit clobber**: same-file edits issued in one batch race each
  other (last writer wins), silently dropping completed edits.
- **Stale extensions / shared-venv mutation**: another session's build
  replaces the `.so` your tests just used.
- **Patch extraction**: the only way to isolate your changes for a PR is
  `git diff <other-branch> -- <files>` + `git apply` into a fresh worktree —
  error-prone and easy to get wrong under concurrent edit.
- **Merge-order hazards**: adding lint gates or CI scope that references
  another agent's untracked files makes the crate red until their work lands.

A dedicated worktree removes all four at the source: your changes are the only
changes in the tree, so commit/verify/PR are direct and there is nothing to
extract.

## Conventions

- One branch = one PR = one coherent unit. Base it on what it depends on
  (`origin/main` for independent work; the migration branch for work that
  rides it).
- The shared main checkout stays the rotating workbench for in-flight agents;
  do not commit directly to it from a task.
- Clean up the worktree when the PR merges: `git worktree remove
  ../temper-wt-<NAME>` and `git branch -d <NAME>`.
