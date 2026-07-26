---
title: "What delegated agents succeed and fail at — bounded deliverables win, open-ended diagnosis burns budget"
date: "2026-07-26"
category: workflow-issues
module: agent-orchestration
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "deciding whether to delegate a task to a subagent or investigate directly"
  - "writing a subagent prompt that starts with 'find out why' or 'figure out what's wrong with'"
  - "a subagent reports it launched a background job and is now waiting"
  - "multiple subagents will write to the same checkout instead of isolated worktrees"
tags:
  - subagent-dispatch
  - task-shape
  - open-ended-diagnosis
  - bounded-deliverable
  - background-job-idling
  - worktree-isolation
  - token-budget
---

# What delegated agents succeed and fail at

## Context

Roughly a dozen subagents ran across this session. The pattern that separated
success from failure was not agent quality — it was task shape.

**Bounded tasks with a known deliverable succeeded**, including twice catching
design errors the delegator itself had made. A subagent given a specific
artifact to produce (a report, a fix to a named function, a measurement to
run and record) with a clear definition of done reliably delivered it.

**Open-ended diagnosis consistently failed.** Tasks framed as "find out why
X" — with no specified deliverable, no bound on where to look, and no
stopping condition — repeatedly did not converge. Two agents together burned
roughly 640k tokens on one such open-ended diagnosis task and produced
nothing usable, while direct investigation (no delegation) found the actual
cause in about a dozen tool calls once someone stopped delegating and looked.

**A recurring operational failure, independent of task shape:** agents
launching a long-running background job and then idling to wait for it,
despite explicit instructions not to. Several agents exhausted their token
budget this way — burning turns polling or waiting rather than working, or
losing the session's productive window to an idle loop around a job that
would finish on its own.

**A collision failure specific to parallel dispatch:** parallel agents
writing to one shared checkout collided via `git stash` — one agent's stash
interfering with another's working tree. Isolated worktrees, one per agent,
fixed it; see
`docs/solutions/workflow-issues/silent-source-loss-worktree-parallel-merges-2026-07-01.md`
for the related (and more severe) failure mode of files silently dropped
during a shared-worktree merge sequence.

## Guidance

1. **Delegate the deliverable, not the question.** "Find out why the router
   is stuck at 83%" is a question; "measure completion_rate with the
   placeholder outline vs. the real outline, holding router/netlist/flags
   fixed, and report the delta" is a deliverable. The second has a
   verifiable definition of done before the agent starts; the first does
   not, and an agent without one has no way to know when to stop searching,
   report inconclusively, or claim false confidence.
2. **If a task is naturally open-ended, decompose it into bounded
   sub-deliverables before dispatching, or do not dispatch it at all.**
   Direct investigation — no delegation — found in about a dozen tool calls
   what two agents spent ~640k tokens failing to find, because direct
   investigation could follow the evidence adaptively; a delegated agent
   given only "find out why" had no cheaper way to narrow the search and
   burned budget exploring broadly instead.
3. **Never dispatch a subagent to launch a background job and wait on it.**
   If a task requires a long-running job, either run it in the foreground
   and budget the wall-clock time, or split dispatch (start the job) from
   collection (a later, separate step that reads the finished result) —
   never instruct or allow an agent to sit idle polling its own background
   process. This failure recurred despite explicit instructions against it,
   which means the instruction alone is not sufficient — the task must be
   structured so idling is not an available strategy (e.g., no dispatch
   until the job would already be done, or the job runs in the parent's
   foreground instead).
4. **Isolate parallel agents in separate worktrees, not a shared checkout.**
   `git stash` is per-checkout global state; two agents in the same checkout
   racing on it will corrupt each other's working tree. This is a subset of
   the same lesson as
   `docs/solutions/workflow-issues/parallel-worktree-sprint-pipeline.md` and
   `docs/solutions/workflow-issues/skill-driven-parallel-refactoring-2026-07-22.md`,
   applied at the dispatch layer rather than the merge layer.
5. **Bounded tasks still need independent verification of their output.**
   Even where delegation succeeded, subagent claims should be checked the
   same way any other measurement is — see
   `docs/solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md`,
   which documents two consecutive subagent reports with confident,
   specific, and false claims, caught only by independent re-measurement.
   "The task shape was bounded" is a predictor of *completion*, not of
   *correctness*.

## Why This Matters

The asymmetry is large enough to change how work gets split up front: a
bounded task costs roughly the size of the deliverable, while an unbounded
one has no natural stopping point and can consume budget without limit while
producing nothing. ~640k tokens for zero usable output on one open-ended
diagnosis, against ~12 tool calls for the same answer once someone
investigated directly, is not a close call — it is evidence that the
decision of *how* to frame a delegated task matters more than which agent
receives it. The background-job-idling failure is a second, independent way
budget disappears even on tasks that were otherwise well-scoped, which is why
it needs a structural fix (don't make idling possible) rather than a
politeness fix (ask the agent not to).

## When to Apply

- Before writing any subagent dispatch prompt — check whether it names a
  deliverable and a stopping condition, or only a question.
- Before delegating a "why is X happening" investigation — either you can
  state the specific measurement that would answer it (delegate that
  measurement), or you can't yet (investigate directly first, until you can).
- Before allowing a subagent to start a long-running process — decide up
  front whether it runs in the foreground now or is collected in a separate
  step later; do not leave "wait for it" as an option.
- Before dispatching 2+ agents in parallel against the same repository —
  confirm each has its own worktree, not a shared checkout.

## Examples

```
BAD prompt (open-ended, no deliverable, no stopping condition):
  "Find out why routing is stuck at 83%."

GOOD prompt (bounded deliverable, verifiable definition of done):
  "Run route_pcb() twice, once with the current 100x150mm placeholder
   Edge.Cuts and once with the real board outline, holding the router
   commit, netlist, and flags fixed. Report completion_rate, nets
   routed/failed, and segments emitted for both runs in a table.
   Do not diagnose the cause — only report the A/B measurement."
```

```
BAD dispatch (idling failure):
  Agent starts a 27-minute routing run in the background, then polls its
  own status every few minutes until budget runs out.

GOOD dispatch:
  Parent runs the long job in the foreground (or a separate step reads the
  result once the job's own completion is independently known to have
  happened), and the agent's turn ends without an open wait loop.
```

## Related

- `docs/solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md`
  — subagent claims need independent verification even on bounded tasks;
  two consecutive false-but-confident reports caught only by re-measurement
- `docs/solutions/workflow-issues/silent-source-loss-worktree-parallel-merges-2026-07-01.md`
  — the more severe sibling of the shared-checkout collision: files silently
  dropped during parallel merge, not just a `git stash` race during dispatch
- `docs/solutions/workflow-issues/parallel-worktree-sprint-pipeline.md` and
  `docs/solutions/workflow-issues/skill-driven-parallel-refactoring-2026-07-22.md`
  — the canonical isolated-worktree dispatch patterns this incident's fix
  matches
