---
category: architecture-patterns
topic: oracle-worktree-hierarchy
last_reviewed: 2026-07-05
status: accepted
plan: 2026-07-05-004
---

# Oracle Worktree Hierarchy

## Decision

Two oracle worktrees serve distinct roles in the placement pipeline. Their
relationship is formalized here to prevent scope drift and parallel-branch
mental model residue.

## Oracles

### `physics-derived-oracle` — Acceptance Inner-Gate Oracle

**Role:** Provides fast per-solve physics scoring for the inner acceptance gate
(see `AcceptanceGate.inner_gate()` in `placer/cp_sat/gate.py`).

**Scores produced:**
- Thermal anchoring scores (component-edge proximity)
- Dual-rail clearance scores (HV/LV separation)
- Non-DRC physics scores (electrical, EMI, thermal safety)

**Invocation:** Every solve cycle. Fast enough for the inner gate
(no external tool dependency).

**Accuracy:** Over-approximates (Chebyshev clearance at 8.5mm) to err
on the side of safety. The truth gate (KiCad DRC at 6mm Euclidean)
catches any false positives.

**Documentation:** This oracle is the *acceptance inner-gate oracle*.
It is NOT the final word on placement correctness — the truth gate is.
When audit + physics-oracle pass but DRC fails, the disagreement is
the signal this two-tier design exists to detect.

### `human-reference-corpus-oracle` — Regression-Floor Corpus Liveness

**Role:** Provides regression-floor confidence for the placement pipeline
by running across a 49-board corpus.

**Checks performed:**
- No-crash: pipeline must not crash on any board
- Geometric-no-regress: no geometric degradation vs. previous run

**Invocation:** CI regression gate. NOT invoked by the acceptance path.

**Accuracy:** Was correct at its purpose (corpus liveness regression);
was wrong at its aspirational purpose (acceptance gate). Demoted to
regression-floor status, not deleted. The corpus oracle is fit for purpose
as a liveness gate — it answers "does the pipeline still run?" not
"is this placement correct?".

**Documentation:** This oracle is a *regression-floor corpus liveness gate*.
The acceptance path never imports from this oracle. It is a separate CI gate.

### `viz-server` — Out of Scope

The viz-server worktree remains out of scope for the acceptance-gate workstream.
Its disposition belongs to a future workstream.

## Rationale

The oracle paradigm shifted from "multiple parallel oracles producing
confidence-coded acceptance verdicts" to "one inner-gate oracle (fast,
over-approximated) feeding into one truth gate (slow, authoritative)."
This match-up is simpler, more correct, and eliminates the false sense of
security from non-DRC acceptance verdicts.

## Cross-References

- `placer/cp_sat/gate.py` — `AcceptanceGate` two-tier implementation
- `validation/drc_runner.py` — KiCad DRC truth-gate runner
- Plan: `docs/plans/2026-07-05-004-feat-acceptance-gate-drc-unsat-ux-plan.md`
