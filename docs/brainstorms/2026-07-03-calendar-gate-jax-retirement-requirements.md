---
date: 2026-07-03
topic: calendar-gate-jax-retirement
origin: docs/brainstorms/2026-07-03-cp-sat-feasibility-first-placer-paradigm-swap-requirements.md
---

# Calendar-Gate JAX Retirement (Override of Parity-Gate Requirement)

## Summary

Replace the parity-gate requirement for JAX retirement with a calendar gate
bounded by a sunset decision.  JAX is deleted on a fixed date with two quality
gaps (thermal-edge anchoring on Q1/Q2, loop-area honoring in the CP-SAT encoder)
closing as prerequisites on the same calendar.  If the date arrives and a
quality gap is unresolved, an explicit decision is required — no indefinite
slip.  The parity harness (#121) retires; `score_placement()` and
`MetricComparison` survive as regression infrastructure.  A frozen
CP-SAT-vs-JAX parity receipt is committed as a documentation artifact before the
harness is deleted.

---

## Problem Frame

The origin brainstorm for the CP-SAT feasibility-first placer required JAX
retirement to be gated on CP-SAT matching-or-beating JAX across five individual
oracle metrics (clearance 3mm, clearance 6mm, thermal, wirelength, routability).
This created a deferral surface: the parity comparison became a verdict
instrument that could block retirement indefinitely, even when the structural
case was settled.  Three weeks into the strangler cutover, the parity job remains
un-run, the verdict framework is unimplemented beyond its test harness, and the
decision to retire JAX has been deferred into an instrument that exists to
adjudicate it.

The structural argument for retirement is already complete: CP-SAT finds a
feasible placement in 0.1s (vs JAX's gradient-descent with weight-tuning
pathologies), the post-solve audit passes 652/652 constraint checks, and all
five hard constraint types are satisfied natively in CP-SAT without the penalty-
weight tuning that drove three cycles of optimizer pathology.  The remaining
gaps are two PCL constraint types (thermal-edge anchoring for Q1/Q2, loop-area
honoring in the CP-SAT encoder) that were deferred from v1 and need closing as
quality work for CP-SAT itself — not parity-equalizing work.

This brainstorm overrides the origin's parity-gate requirement with a calendar
gate bounded by a sunset decision.  It follows the same plan-deviation pattern as
the `--placer jax-deprecated` override from ce-doc-review: the origin said one
thing (parity is the gate), the implementation chose another (calendar is the
gate with sunset), and the deviation is documented rather than hidden.  See the
Deviations from Origin section below for the full trace.

---

## Actors

- A1. **CP-SAT placer engine**: Solves placement under hard feasibility constraints; target of quality-gap closure work.
- A2. **PCL constraint compiler**: Encodes PCL constraints for CP-SAT; extended with thermal-edge anchoring and loop-area honoring.
- A3. **Pipeline operator** (human or CI): Triggers JAX retirement; verifies `--placer jax-deprecated` no-op warning.
- A4. **Future maintainer**: Reads the decision log and frozen parity receipt to understand why parity was skipped and what evidence carries the decision.

---

## Requirements

**Calendar gate**

- R1. JAX retirement (U9 deletion of `optimizer/`, `losses/`, `loss_bridge.py`, plus the auxiliary file list from the plan's U9) fires on a fixed calendar date, not on a parity verdict.
- R2. The calendar date is a deadline bounded by a sunset decision.  Deletion does not fire until both quality gaps (R3, R4) are closed.  If the date arrives and any quality gap is unresolved, an explicit decision is required — accept the gap and delete, extend the date, or revert — rather than an indefinite slip.
- R3. The retirement commit cites the structural argument (U0 spike results, 652/652 audit pass), the two gap-close commits, and a frozen CP-SAT-vs-JAX parity receipt (R7) as its evidence.

**Quality gaps — prerequisite to deletion**

- R4. Thermal-edge anchoring on Q1 and Q2 in the PCL spec is compiled through the CP-SAT encoder as a hard edge-anchoring constraint.  This closes the gap between v1's `OnSideConstraint` coverage and the temper board's thermal-anchoring requirements.  (Note: U_BUCK was excluded from R4 because the 2026-07-01 thermal-anchoring analysis concluded it does not need edge anchoring — it is a 2W buck converter that needs spreading, not fixed positions.)
- R5. Loop-area honoring is added to the CP-SAT encoder.  The `LoopAreaConstraint` (currently deferred with a warning) compiles to a soft wirelength-term addition or a hard area bound in the CP-SAT model, closing the gap between the encoder's supported type set and the temper board's PCL spec.

**Parity harness retirement + evidence freeze**

- R6. The parity harness is retired: `tests/regression/test_cp_sat_parity.py` is deleted as a CI gate and decision framework.  `score_placement()` (in `metrics/external_oracle.py`), the `MetricComparison` / `ParityComparisonResult` dataclasses, and the supporting `@pytest.mark.cp_sat` test framework are extracted from the test file and survive as CP-SAT regression infrastructure independent of JAX.
- R7. Before the parity harness is deleted, a frozen CP-SAT-vs-JAX parity receipt is produced and committed as a documentation artifact (`docs/evidence/cp-sat-jax-parity-2026-07-XX.md`) containing per-metric scores for the temper board.  This serves as the head-to-head receipt for future maintainers without requiring the harness to remain active.

**Experiment retirement**

- R8. The in-flight `2026-07-02-001` JAX multi-seed experiment is fully retired.  No completion run, no informational run, no verdict extraction.  The experiment's configuration, runner code, and associated fixtures are deleted alongside the JAX optimizer stack in U9.  References to the experiment as a gate condition in the plan document are removed.  Rationale: the experiment was designed to tune JAX weights; since JAX is being retired, its output is moot regardless of completion status.  No informational run avoids extracting a pseudo-verdict from an experiment that cannot change the decision.

**Production safety**

- R9. The `--placer jax-deprecated` flag is retained as a no-op: it prints a deprecation warning and exits.  It does NOT run the JAX pipeline (the optimizer has been deleted).  The flag exists to surface the deprecation to any scripts or workflows that still reference it, not as a working rollback path.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3.** Given the calendar date has arrived and both quality gaps (R4, R5) are closed, when the JAX retirement PR lands, the deletion fires and the commit log cites the U0 spike results, the 652/652 audit pass, the two gap-close commits, and the frozen parity receipt as evidence.
- AE2. **Covers R2, R4.** Given the calendar date has arrived but the thermal-edge anchoring gap (R4) is not yet closed, when the retirement PR attempts to land, the sunset decision fires — accept and delete, extend the date, or revert — rather than an indefinite slip.
- AE3. **Covers R6, R7.** After parity harness retirement, `from temper_placer.metrics.external_oracle import score_placement` works and produces scores for CP-SAT placements; the `MetricComparison` dataclass is importable from CP-SAT regression tests; no JAX-vs-CP-SAT comparison test runs in CI; the frozen parity receipt is committed at `docs/evidence/cp-sat-jax-parity-2026-07-XX.md`.
- AE4. **Covers R8.** After experiment retirement, searching the codebase for `2026-07-02-001` returns zero references; the experiment's artifacts are deleted alongside the JAX optimizer stack.
- AE5. **Covers R9.** After JAX retirement, `temper optimize --placer jax-deprecated` prints a deprecation warning and exits with a non-zero code — it does not attempt to run the JAX pipeline.
- AE6. **Covers traceability.** A future maintainer reading this doc can navigate upstream via the `origin:` frontmatter to the brainstorm that was overridden, and read the Deviations from Origin section for the rationale for each deviation.

---

## Success Criteria

- JAX is deleted no later than the calendar date, or an explicit sunset decision is recorded.  The strangler cutover completes without a live parity verdict.
- Both quality gaps close on the same calendar and function as hard prerequisites — they do not defer past the deletion date without triggering the sunset decision.
- The parity harness is deleted as a CI gate; `score_placement()`, `MetricComparison`, and the supporting test framework survive as CP-SAT regression infrastructure.
- A frozen CP-SAT-vs-JAX parity receipt is committed before the harness is deleted.
- The `2026-07-02-001` experiment leaves no active artifacts in the codebase.
- `--placer jax-deprecated` prints a deprecation warning and exits; it does not attempt to run deleted code.
- The decision is documented with origin traceability and a Deviations from Origin section — a future reader can see what was overridden, why, and where.

---

## Scope Boundaries

### Deferred for later

- True Euclidean (NRA) spacing in CP-SAT — already deferred in the plan's v1 scope; not reopened here.
- Corpus-confidence threshold for fully removing `--placer jax-deprecated` — the flag is a no-op after deletion; the CLI option can be removed in a follow-up cleanup PR.

### Outside this product's identity

- Re-running CP-SAT-vs-JAX parity under any framing (live CI gate, ongoing comparison).  The decision is settled on structural grounds backed by a frozen receipt; the live comparison instrument is retired, not repurposed.
- Extracting a verdict from the `2026-07-02-001` experiment.  The experiment retires fully; no informational run, no partial completion.
- Re-debating the paradigm swap itself.  The structural argument for feasibility-first CP-SAT over soft-relaxation JAX is the premise of this work, not a question it reopens.

---

## Key Decisions

- **Calendar gate with sunset, not verdict gate**: The parity comparison was a deferral surface dressed as evidence.  Removing it forces the decision onto the structural argument, which was already the actual basis for the paradigm swap.  The sunset decision (accept/extend/revert at deadline) prevents the calendar date from becoming a deferral surface of its own.
- **Quality gaps as prerequisites, not parallel work**: Putting thermal-edge anchoring and loop-area honoring behind the same calendar as deletion prevents them from deferring indefinitely — the same structural pressure that the parity gate failed to provide.  The sunset decision provides an escape valve if a gap proves harder than expected.
- **Parity harness delete, frozen receipt survives**: The harness is deleted as a CI gate; `score_placement()` and `MetricComparison` survive as regression infrastructure.  A frozen parity receipt (one-time run before deletion) gives future maintainers the head-to-head evidence without maintaining the comparison infrastructure.
- **Experiment full retirement, no informational extraction**: The `2026-07-02-001` experiment was designed to tune JAX weights.  Since JAX is retiring, its output is moot.  Running it for documentation would extract a pseudo-verdict from an experiment that cannot change the decision.
- **`--placer jax-deprecated` as no-op warning**: Since the JAX optimizer is deleted, the flag cannot run the JAX pipeline.  It prints a deprecation warning and exits, surfacing the deprecation to any scripts still referencing the flag.
- **Decision-log and origin traceability**: This brainstorm declares its origin and includes a Deviations from Origin section.  The pattern matches the legacy-flag override from ce-doc-review: name the origin requirement, state the override, give the rationale.

---

## Deviations from Origin

The origin brainstorm (`docs/brainstorms/2026-07-03-cp-sat-feasibility-first-placer-paradigm-swap-requirements.md`) required:

| Origin Requirement | Deviation in this document | Rationale |
|---|---|---|
| R9: Deletion gated on CP-SAT matching-or-beating JAX on 5 oracle metrics | R1-R2: Deletion on a calendar date with sunset, not a parity verdict | The parity gate became a deferral surface; three weeks in, it remains un-run. The structural argument (0.1s feasibility, 652/652 audit) already carries the decision. A frozen parity receipt (R7) preserves the evidence without the live gate. |
| Key Decision: JAX retirement gate tied to 2026-07-02-001 experiment completion | R8: Experiment fully retired, no completion run | Tuning JAX weights is moot when JAX is being deleted. No informational extraction avoids a pseudo-verdict. |
| R11: `--placer cp-sat` flag runs alongside JAX until parity; JAX deleted outright with no legacy flag | R9: `--placer jax-deprecated` retained as no-op warning, not a working rollback | The plan already deviated from "no legacy flag" (ce-doc-review fix #7). This doc further adjusts: the flag can't work after optimizer deletion, so it becomes a deprecation surface. |
| Scope: U_BUCK included in thermal-edge anchoring requirements for v1 | R4: U_BUCK excluded from thermal-edge anchoring | The 2026-07-01 thermal-anchoring analysis concluded U_BUCK (2W buck converter) needs spreading, not fixed-position edge anchoring. |

---

## Outstanding Questions

### Resolve Before Planning

- [Affects R1, R2][Calendar scope] What is the calendar date or sprint?
- [Affects R7][Parity evidence] Is the frozen parity receipt produced before or after the quality gaps close? (Before: receipt captures CP-SAT-vs-JAX on current v1. After: receipt captures the post-gap-close quality.)

### Deferred to Planning

- [Affects R4][Technical] What is the exact PCL encoding for thermal-edge anchoring on Q1/Q2 — does it use the existing `OnSideConstraint` with updated parameters, or does it require a new constraint construct?
- [Affects R5][Technical] What is the CP-SAT encoding for loop-area honoring — a soft wirelength-term addition, a hard area bound, or a separate objective term?
- [Affects R6][Technical] Which specific classes and test methods in `test_cp_sat_parity.py` are extracted to a library module vs deleted?
- [Affects R8][Deletion scope] Which specific artifacts (config files, runner scripts, test fixtures) reference `2026-07-02-001` and need deletion?
- [Affects R3][Retirement PR structure] What form does the frozen parity receipt take — per-metric table, prose summary, or both — and where does it live in the retirement commit?
