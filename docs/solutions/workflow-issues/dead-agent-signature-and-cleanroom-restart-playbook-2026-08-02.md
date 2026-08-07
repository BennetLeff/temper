---
title: "Dead-agent signature and the clean-room restart playbook for flaky providers"
date: 2026-08-02
category: workflow-issues
module: development_workflow
problem_type: workflow
component: agent_orchestration
severity: high
applies_when:
  - "A provider backend is flaky (stream-read failures) and subagent sessions die without an error notification"
  - "A dispatched agent stops mid-task: the question is dead vs alive, and restarting a live agent duplicates work while not restarting a dead one stalls the pipeline"
  - "Multiple agents share one repo with 60+ concurrent worktrees and uncommitted state is the only record of a dead agent's work"
  - "A restarted task reuses a worktree/branch that a still-alive prior dispatch may also be using"
symptoms:
  - "12 provider-stream deaths in one session; most died silently (no error notification) — only some generated 'ProviderShared.stream: Failed to read' errors"
  - "Dead agents left a consistent signature: environment setup done (venv present), zero commits, zero pushes, stale worktree mtime, unchanged dirty-file set across sweeps"
  - "One agent judged dead was actually alive-but-slow (load-average 12): its work landed 1.5h later, and the restart correctly self-stopped via its guard"
  - "Uncommitted-but-complete work was recovered from dead agents' worktrees: a 91-line wiring diff, a staged 3-file doc patch, 2.8MB of measurement artifacts"
root_cause: external_infrastructure
resolution_type: playbook
tags:
  - subagent-orchestration
  - dead-agent-detection
  - salvage
  - clean-room-restart
---

# Dead-agent signature and the clean-room restart playbook

## The dead-agent signature

A dead agent is indistinguishable from an alive-but-slow one by absence of
notifications. The observable signature, in order of reliability:

1. **Zero commits/pushes** despite an explicit commit-early mandate, for a
   duration that exceeds the task's shortest plausible path (here: hours).
2. **Stale worktree mtime** and an **unchanged dirty-file set** across two
   sweeps — the strongest signal. Alive agents (even slow ones) accumulate
   dirty files and commits; dead ones freeze.
3. **Setup completed but nothing after**: venv exists (uv sync ran), then a
   clean tree at the base commit forever. This was the signature of every
   confirmed death, including the ones that died before any error notification
   arrived.

False-positive risk is real under machine thrash (load-average 12 this session
made a small re-baseline task take 1.5h). When in doubt, sweep twice with an
interval, and restart only on the unchanged-signature basis — but note that
waiting too long stalls everything downstream.

## The clean-room restart playbook

1. **Salvage before restart**: `git diff > /tmp/<task>.patch` from the dead
   agent's worktree (includes untracked files via `git status` inspection —
   copy those separately). This session recovered a complete wiring diff, a
   staged doc patch (committed as-is after verification), and a run-C
   measurement dataset (2.8MB of cores/tables) that became the continuation's
   starting point.
2. **Restart on a continuation branch from the dead agent's pushed commit**
   (never from the shared base): `git worktree add -b <branch>-continued
   <worktree>-2 origin/<dead-branch>`, apply the salvage patch with
   `git apply --3way`, and instruct the agent to verify the salvaged work
   rather than trust it.
3. **Duplicate-detection guard**: the restart prompt must contain "if the
   branch ever shows commits you didn't make, STOP and report". This session it
   fired correctly: A8-r3 detected the concurrent A8-r2 completion mid-session,
   stopped with zero modifications, and produced a read-only verification
   report instead of a conflict.
4. **Commit-early mandates on every dispatch** ("commit the wiring review as
   its own commit before running the solve"): a death after any commit loses at
   most that commit.
5. **Reuse worktrees with built venvs** for restarts when clean at the right
   base — saves the 3-10 minute uv sync + make extensions setup and avoids
   piling more 700MB venvs on a disk that already ran out of space once this
   session.
6. **Doc-only tasks need no venv**: tell the agent explicitly to skip
   uv sync/make extensions.
7. **Treat the orchestrator as the salvage point**: for small complete edits
   (a staged 3-file patch), committing the dead agent's work yourself is
   cheaper than a third dispatch — verify the diff against the task contract
   first.

## What not to do

- Don't delete the dead agent's worktree before salvaging — uncommitted state
  dies with it (the branch survives, the dirty files do not).
- Don't restart into the same worktree/branch blindly — if the original was
  alive, both agents collide on dirty files. The guard covers commits; it does
  not cover simultaneous file edits.
- Don't judge dead/alive by notifications alone: most deaths this session
  produced none.

## Evidence

- This session's dispatch log: 12 deaths (A3, A5 ×2, A8/A9/A11 ×3 rounds each,
  A10 ×2), 4 clean-room restarts with salvage, 1 guard-stop success (A8-r3).
- `docs/handoffs/2026-08-01-k3-gap2-validator-audit-handoff.md` §6 — the
  standing worktree-deletion and git-stash traps this playbook complements.
