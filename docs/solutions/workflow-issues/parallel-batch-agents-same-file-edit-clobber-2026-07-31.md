---
module: workflow
tags: [parallel-agents, worker-bee, parallel-edit-clobber, shared-worktree, compound-engineering]
problem_type: workflow_issue
date: 2026-07-31
severity: high
---

# Parallel batch agents and same-file edits: the clobber and the coordination lessons

## Problem

A single compound-engineering session ran up to four parallel worker agents
against one codebase. Two distinct failure modes repeatedly cost rework:

1. **Parallel-edit clobber** — issuing multiple `edit`-tool operations on the
   *same file* in one batch silently drops edits (last writer wins). Four
   separate incidents: `channel_widths.rs`, `router_clearance.rs`,
   `temper-rust-router/src/lib.rs`, and `astar.rs` each had a successfully-
   reported edit that never landed because a sibling edit in the same batch
   overwrote it.
2. **Same-worktree dependency collision** — two parallel agents editing
   *different crates in the same worktree* can still collide when one crate
   is a build dependency of the other. Agent A editing `astar.rs`
   (router-core) broke Agent B's `clippy` on `temper-rust-router`, which
   depends on router-core; A's intermediate state (an `f32::consts::SQRT_2`
   that was a hard `E0223` under the edition) was compiled by B mid-flight.
   B also had `lib.rs` overwritten by A once.

## What Was Done

- Diagnosed the clobber by `git diff`-ing a file right after a batch that
  "succeeded" and finding only one of two reported replacements present.
- Switched to strictly sequential same-file edits (one `edit` call, verify,
  next) and to `perl` one-liners for identical multi-site patterns.
- Re-dispatched parallel agents into **separate worktrees** (one per batch)
  instead of one shared worktree, so dependency-chain collisions were
  impossible.
- For the cross-crate dependency case specifically: never run a crate's
  verification while a sibling agent edits one of its dependencies; separate
  worktrees make the dependency chain irrelevant.

## Root Cause

`edit`/`write` operations are read-modify-write against the working tree;
parallel same-file operations race, and the losing writer's in-memory base
is stale. Parallel agents in one worktree share more state than their file
lists suggest: the `Cargo.toml` dependency graph and the `target-shared`
build cache are worktree-wide.

## Prevention

- One `edit` per file per batch; verify (`git diff`) before the next edit to
  the same file.
- One agent = one worktree = one coherent file set. `make worktree
  NAME=<batch> BASE=origin/main` is the repo's tool for this.
- Never verify crate X while another agent edits a crate in X's dependency
  closure.
- After any batch, `git diff` the batch's files against what the batch
  *reported* — the diff is the truth, the tool's "1 replacement" is not.

## Related

- `docs/solutions/best-practices/per-workstream-worktree-2026-07-31.md` — the
  worktree-isolation default this session codified.
