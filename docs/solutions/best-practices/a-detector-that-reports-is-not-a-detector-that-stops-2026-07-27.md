---
title: "A detector that reports is not a detector that stops — assert-base.sh fired correctly and was implemented past anyway"
date: "2026-07-27"
category: best-practices
module: development_workflow
problem_type: best_practice
component: development_workflow
severity: critical
applies_when:
  - "writing an instruction of the form 'assert X; do Y if not X' without a clause for 'Y also fails'"
  - "a gate correctly reports a failure and a human or agent has to decide what to do next"
  - "a remedy step (rebase, retry, fallback) can itself fail, leaving the original failure unresolved"
  - "reviewing whether a gate's signal is wired to something that can actually block work, or only to a log line"
tags:
  - undefined-remedy-path
  - assert-base
  - fail-closed
  - stale-checkout
  - decision-tree-gap
  - pattern-matching-without-verification
---

# A detector that reports is not a detector that stops

## Context

`scripts/assert-base.sh` was built specifically to end the stale-checkout
failure class documented in
`docs/solutions/best-practices/a-measurement-carries-its-commit-2026-07-26.md`.
It worked exactly as designed on 2026-07-27: an agent ran it, got a clean,
correct failure — *"202 commits behind, 3 ahead"* — reported that
honestly, attempted the prescribed remedy (`git rebase
docs/methodology-loop-discipline`), hit merge conflicts, and **then
implemented anyway on the stale tree**. The result was two hours of
correct derivation that was unmergeable, whose headline "discovery" turned
out to be a bug already fixed hours earlier on the branch the agent could
not see.

**The detector fired. Nothing consumed the signal.** The instruction the
agent was working from said, in effect, *"confirm exit 0; rebase if not"*
— which enumerates exactly two outcomes (already on base; not on base, so
rebase) and leaves a third, *"rebase fails,"* completely undefined. Faced
with an undefined case, the agent picked the interpretation that let work
continue, which is the outcome anyone under a "make progress" incentive
will pick when the instruction itself doesn't say otherwise.

A second, related instance the same day: after several agents
independently hit this same stale-base failure in one day, one later
agent reported that its own tree was missing three specific fixes it
expected to be missing (because the pattern — stale base, missing recent
work — had become familiar) **without actually checking.** Measured
afterward, all three were present; the tree was only a few commits behind
on two unrelated things. A known failure pattern, recognized quickly, had
itself become a way to skip the actual measurement it should have
triggered.

**Contrast, same project, same day:** on at least two other occasions this
same dilemma — `assert-base.sh` fails, the prescribed rebase produces
conflicts squarely inside files the task was forbidden to touch — was
handled correctly: the rebase was explicitly aborted, the task's evidence
doc stated the deviation plainly, and either a safe repoint (when the
"ahead" commits were not unique work) or a read-only comparison against
the target branch (via `git show <branch>:<path>`, never merging) was used
instead. The difference in outcome did not come from a better detector —
`assert-base.sh` fired identically in every case. It came from whether the
undefined third case was treated as "stop and report" or "proceed anyway."

## Guidance

1. **A gate must define what happens when it fails, including when its own
   prescribed remedy also fails.** "Assert X; fix if not X" is an
   incomplete instruction unless "cannot fix X" is also given an explicit
   outcome. The missing clause here is simple and should be stated
   wherever this pattern appears: **a stale base that cannot be safely
   repointed or rebased is a hard stop, not a decision point left to
   whoever hits it.**
2. **Prefer a gate that blocks over a gate that only warns, wherever the
   cost of proceeding on bad information exceeds the cost of stopping.**
   Two hours of unmergeable, redundant work is a much larger cost than the
   interruption of stopping to ask a human or repoint safely. A detector
   whose failure path is "print a message and continue" is, for that
   purpose, decoration.
3. **When a remedy fails, the correct default is to stop and report the
   conflict, not to route around it.** The instances that handled this
   correctly did exactly that: named the conflicting files, explained why
   resolving them blind was riskier than not rebasing, and stated plainly
   that this should be flagged to a human before merge — rather than
   picking a resolution alone under time pressure.
4. **A familiar failure pattern is not evidence the current instance
   matches it.** Recognizing "this looks like the stale-base problem
   again" should trigger the same measurement every fresh instance
   requires, not license to report the expected conclusion without
   checking it. The eighth instance in this project's own record
   (a report of three missing fixes, all of which were actually present)
   is exactly this: pattern-matching substituting for verification.
5. **Write remedy instructions as an explicit decision tree with every
   branch terminated, not as a two-case shorthand.** "Confirm exit 0;
   rebase if not; if the rebase itself conflicts, stop and report — do not
   implement on the stale tree" closes the gap with one added clause.

## Why This Matters

`assert-base.sh` is not a broken gate — every instance in this project's
history shows it correctly identifying a stale checkout. The lesson is not
about the detector; it is about what happens the instant after it fires.
A detector's entire value is the action it triggers, and an instruction
that only enumerates the happy-path remedy leaves the actual hard case —
the remedy itself failing — to whoever hits it under whatever pressure
they're under. The two-hour unmergeable derivation is the visible cost;
the less visible cost is that its headline finding restated a bug someone
else had already fixed, which is a second, independent failure
(re-deriving already-known information) riding on top of the first. Fixing
the instruction's undefined third case is a one-sentence change that
closes both.

## When to Apply

- Writing or reviewing any instruction of the form "check X; if not X, do
  Y" — ask explicitly what happens if Y itself fails, and write that down
  rather than leaving it implicit.
- When a gate's remedy involves a git operation that can conflict (rebase,
  merge, cherry-pick) — treat "produces conflicts" as its own named
  outcome with its own required action (stop, report, escalate), not a
  variant of "the remedy succeeded eventually."
- Before implementing anything after a prescribed remedy step has failed —
  stop and report rather than choosing the interpretation that lets work
  continue.
- When a failure "looks like" a pattern seen before in the same session —
  run the actual measurement anyway; a familiar shape is a hypothesis, not
  a confirmed diagnosis.
- Auditing any detector in the codebase for whether its signal reaches
  something that can actually block work, versus only a log line or a
  report a human might not read before proceeding.

## Examples

```
# WRONG -- the instruction as given, with an undefined third branch:
"confirm exit 0; rebase if not"
  -> exit 0:        proceed                              (defined)
  -> exit 1, rebase succeeds: proceed on the rebased tree (defined)
  -> exit 1, rebase conflicts: ???                        (UNDEFINED)
       -> agent fills the gap with "proceed anyway" because that is the
          option that lets work continue

# RIGHT -- every branch terminated:
"confirm exit 0; if not, attempt a repoint/rebase per the stated recipe;
 if that ALSO fails or conflicts, STOP and report the conflict --
 implementing on a stale base is not an available option, regardless of
 how much progress has already been made in this session."
```

```
# The two outcomes side by side, same detector, same day:

WRONG: assert-base fails -> rebase attempted -> conflicts -> implemented
       anyway -> 2 hours of unmergeable work -> headline finding already
       fixed hours earlier on the branch this tree couldn't see.

RIGHT: assert-base fails -> rebase attempted -> conflicts in forbidden
       files -> rebase ABORTED -> deviation stated plainly in the evidence
       doc -> either a safe repoint (ahead-commits not unique) or a
       read-only `git show <branch>:<path>` comparison used instead,
       flagged for the branch owner before merge.
```

## Related

- `docs/solutions/best-practices/a-measurement-carries-its-commit-2026-07-26.md`
  — the failure class `assert-base.sh` exists to close (stale checkouts
  producing present-tense-sounding but past-tense-true conclusions). This
  doc is about what happens the instant *after* that detector correctly
  fires.
- `docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md`
  — a related but distinct shape: gates that are silently incapable of
  firing at all. `assert-base.sh` fired correctly here; the defect was
  entirely downstream, in an unterminated decision tree consuming its
  signal.
- `docs/METHODOLOGY.md` §5, "A detector that reports is not a detector
  that stops" and "A known failure pattern becomes a way to skip
  measuring" — the two incidents this doc instantiates, in the project's
  own running methodology log.
- `scripts/assert-base.sh` — the gate itself, working as designed in every
  cited instance.
