---
title: Solution Mutation Canaries - Plan
type: feat
date: 2026-08-02
topic: solution-mutation-canaries
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R36)
---

# Solution Mutation Canaries - Plan

## Goal Capsule

**Objective:** Perturb a known-good placement (component moved, pair swapped) and assert that quality metrics move in the expected direction — so metric monotonicity is asserted, not hoped.

**Product authority:** temper-placer maintainer (single-maintainer project; this plan is pulled from the portfolio menu, not scheduled).

**Open blockers:** none.

---

## Product Contract

### Summary

Quality metrics are only trustworthy if they respond monotonically to perturbations a human would call worse. A known-good placement is taken, a single named mutation is applied, and each quality metric must move in its declared direction — wirelength up when a component moves away, boundary violations up when a component moves off-board, clustering down when a group is scattered. A metric that does not move, or moves the wrong way, fails the run: the metric itself is broken. The canaries validate the meters, not the placements.

### Problem Frame

A metric that scores the solver's own output can silently stop meaning anything — the five-metric silent-fail class where every value recorded `0.0` yet the gate passed (`docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md`). Monotonicity is the cheapest fail-capable property: a metric whose value does not change when its defining quantity is demonstrably degraded is dead, and a dead metric is worse than no metric because it reports a clean verdict.

### Requirements

- R36. A known-good placement is perturbed (component moved, pair swapped) and quality metrics must move in the expected direction — monotonicity is asserted, not hoped.
  - **Success signal:** a standing canary suite applies each named mutation to a known-good placement, and every declared metric direction is asserted with a strict inequality; a metric that fails its direction fails the suite.

### Key Technical Decisions

- KTD1. **Use the canonical quality evaluator as the metric source.** The canaries read metrics from the shared placement-metric core (`validation.metrics.compute_metrics`) and the `temper-quality-oracle` Rust crate, the same sources the rest of the validation stack uses. Rationale: a canary validating a throwaway metric would prove nothing about the metrics the pipeline actually consumes.
- KTD2. **One declared direction per metric, asserted as a strict inequality.** Each metric in the canary table declares one direction (up, down, or invariant-under-this-mutation) and the assertion uses a small epsilon. Rationale: "metrics change at all" is a weak check; direction and strictness are the monotonicity claim this idea names.
- KTD3. **Mutations are single and named.** Each scenario applies exactly one mutation (component moved away from its group, component moved off-board, pair swapped, component overlapped) so a direction failure names the mutation and the metric. Rationale: compound mutations make failures uninterpretable.

### Assumptions

- A1. No seed is named in the origin for R36. The natural anchors are the known-good placements in `power_pcb_dataset/corpus/` (baseline and golden files) and the metric core in `packages/temper-placer/src/temper_placer/validation/metrics.py`.
- A2. "Known-good" means a placement the project already treats as a baseline — the corpus board baselines, not a freshly computed placement whose quality is itself unverified.
- A3. Mutations reuse the `PlacementState` machinery the human-reference extractor builds, so positions, rotations, and sizes are mutated in the same coordinate space the metrics consume.
- A4. The canary suite runs in CI as a standing check, extending an existing gate surface rather than a new parallel script.

---

## Implementation Units

### U1. Mutation driver

**Goal:** Apply each named single mutation to a known-good placement and return the mutated `PlacementState`.

**Requirements:** R36

**Dependencies:** none

**Files:**
- `packages/temper-placer/src/temper_placer/validation/mutation_canary.py` (new)
- `packages/temper-placer/tests/validation/test_mutation_canary.py` (new)

**Approach:** Build a driver that loads a known-good placement, applies one named mutation, and returns the mutated state plus a description. Named mutations: move a component away from its functional group; move a component off-board; swap two components' positions; overlap one component onto another; rotate a component away from its group orientation. The driver validates that exactly one mutation was requested, so a scenario cannot silently compound.

**Patterns to follow:** The `PlacementState` construction and coordinate conventions in `validation/human_reference_extractor._build_state_and_context`; the `validation/metrics.compute_metrics` input contract.

**Test scenarios:**
1. Happy path — each named mutation returns a state differing from the source only in the mutated components.
2. Edge case — requesting two mutations at once raises, naming the rule.
3. Edge case — a mutation naming a component absent from the placement raises.
4. Round-trip — applying and then inverting a move restores the original state bit-for-bit.

**Verification:** The driver tests pass, and each mutation produces the intended single change.

### U2. Declared-direction canary table

**Goal:** Define the per-metric expected direction for each mutation and assert it with a strict inequality.

**Requirements:** R36

**Dependencies:** U1

**Files:**
- `packages/temper-placer/src/temper_placer/validation/mutation_canary.py`
- `packages/temper-placer/tests/validation/test_mutation_canary.py`

**Approach:** Encode a table of (mutation, metric, expected direction) pairs. The table drives the assertions: metric value on the mutated state must move strictly in the declared direction relative to the known-good value, within epsilon. Seed entries cover wirelength (up on move-away, up on pair swap), overlap (up on overlap mutation, invariant on move-away), boundary (up on off-board move, invariant on within-board moves), grouping/clustering (down on group-scatter, down on pair swap), and symmetry-pair residual (up on asymmetric swap) where the metric family exists.

**Patterns to follow:** The fail-capable rule (R4) in `docs/physics-verification-methodology.md` §4 — each assertion names the bug class (dead metric, inverted direction) it would catch.

**Test scenarios:**
1. Happy path — every seeded (mutation, metric) pair moves in the declared direction on the temper corpus baseline.
2. Fail path — a deliberately dead metric (constant value) fails its direction assertion.
3. Fail path — a deliberately inverted metric (moving the wrong way) fails its direction assertion.
4. Edge case — a metric marked invariant-under-mutation is asserted within epsilon, not strictly equal, tolerating float noise.
5. Coverage — every metric the pipeline's gates consume is present in at least one canary row.

**Verification:** The canary suite passes on the corpus baselines and fails on both injected dead and inverted metrics, proving the table bites.

### U3. Standing canary gate in CI

**Goal:** Run the canary suite on corpus baselines in CI as a standing check.

**Requirements:** R36

**Dependencies:** U2

**Files:**
- `packages/temper-placer/tests/validation/test_mutation_canary.py`
- `.github/workflows/python-tests.yml` (extend the existing `checks` job)

**Approach:** Add the canary suite to the existing validation test run so it executes on every CI pass over the corpus baselines, extending the `checks` job rather than adding a workflow. A canary failure surfaces the mutation name and the metric that violated its direction.

**Patterns to follow:** The repo convention of extending existing gates over new parallel scripts (AGENTS.md); the `checks` job structure in `.github/workflows/python-tests.yml`.

**Test scenarios:**
1. Integration — a clean CI run passes the canary suite.
2. Fail path — a deliberately broken metric (per U2 scenario 2) makes the CI run fail with the mutation and metric named.
3. Regression — existing validation behavior is unchanged when canaries pass.

**Verification:** The CI `checks` job passes on clean runs and fails on the injected-dead-metric scenario.

---

## Verification Contract

The canary suite runs under the standard pytest configuration in `packages/temper-placer/` and is wired into the existing `checks` job of `.github/workflows/python-tests.yml`; no new workflow file is introduced. New public functions in `temper_placer/` must clear the coverage gate (`.coverage-allowlist`). No new `scripts/*.py` is introduced, so no `scripts/manifest.yaml` entry is required.

---

## Definition of Done

- The mutation driver applies each named single mutation to a corpus baseline (U1).
- The declared-direction table asserts every seeded (mutation, metric) pair with a strict inequality (U2).
- The suite fails on an injected dead metric and an injected inverted metric, proving it bites (U2).
- The suite runs in CI as a standing check (U3).
- All new public functions have executed-line coverage.
- The validation test suite passes under the standard pytest run.

---

## Scope Boundaries

**In scope:** single-mutation canaries over the metric core on corpus baselines; the declared-direction table; the CI wiring.

**Out of scope:** mutating constraints or encodings (that is the portfolio's R32 constraint-mutation suite); asserting that solver output is near-optimal (that is R14/R25); adding new quality metrics — the canaries validate the metrics that exist.

### Deferred to Follow-Up Work

- Canary rows for routing-quality metrics (RDL, via counts) once those are part of the metric core the pipeline consumes.
- Automatic direction discovery from metric definitions (the table stays hand-declared per KTD2).
- Mutation canaries on boards beyond the current corpus.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — the portfolio origin (R36).
- `packages/temper-placer/src/temper_placer/validation/metrics.py` — the shared placement-metric core.
- `packages/temper-quality-oracle/` — the canonical quality evaluator the canaries read.
- `packages/temper-placer/src/temper_placer/validation/human_reference_extractor.py` — `PlacementState` construction conventions.
- `power_pcb_dataset/corpus/` — the known-good baseline placements.
- `docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md` — the silent-fail metric class these canaries prevent.
- `docs/physics-verification-methodology.md` — the fail-capable rule (R4) that shapes the assertion table.
