---
title: "Trigger-Path Mutation - Plan"
type: feat
date: 2026-08-02
topic: trigger-path-mutation
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R43)
---

# Trigger-Path Mutation - Plan

## Goal Capsule

**Objective:** Prove workflow trigger coverage live: remove a trigger path (or a trigger event) from a copy of a workflow and the R31 closed-form drift gate must fail. A removal the drift gate does not notice is a verifier gap, surfaced as a failure.

**Product authority:** temper-placer and firmware maintainer (single-maintainer project); the mutation suite is the injection-tier companion to R31's closed-form verifier.

**Open blockers:** none.

---

## Product Contract

### Summary

The trigger-path mutation suite removes each trigger path and each trigger event from a copy of every path-filtered workflow and asserts the closed-form verifier fails on the copy. Workflow coverage is proven live, not linted, and a verifier that misses a removal is itself a defect.

### Problem Frame

This idea exists for the workflow-trigger drift class: trigger drift is silent until branch protection or the merge path misbehaves — path-filtered workflows never reported, and the path list duplicated across three copies (`docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md`). R31 makes the drift a static hard failure, but linting cannot prove the verifier actually reads every path it polices. Removing a path and watching the verifier react is the only live proof.

### Requirements

- R43. **Trigger-path mutation** (Injection / CI / P2): a trigger path is removed from a workflow and the drift gate must fail — workflow coverage is proven live, not linted. Seed: `scripts/check_workflow_pr_triggers.py`.
- **Success signal:** for every path-filtered workflow, removing any single trigger path or trigger event from a copy makes the closed-form verifier fail; a removal the verifier tolerates is a surfaced verifier gap that fails the mutation run.

### Key Technical Decisions

- KTD1. Mutations are copy-based: each mutation writes a modified workflow to a temp copy (one path removed from one trigger list, or one trigger event removed) and runs the verifier against the copy. Rationale: committed workflows are never mutated, and the run stays side-effect free.
- KTD2. The mutation runner consumes the R31 verifier as the same code path CI runs, by importing its check functions or invoking the same script with a workflows-dir override. Rationale: a mutation the verifier misses then proves a real verifier gap, not a test-harness artifact.
- KTD3. The per-path mapping is the contract: each path in a path-filtered workflow's trigger lists must be individually removable with a detectable verdict change, and the same applies to each load-bearing trigger event. Rationale: a removal with no verdict change is exactly the coverage gap the suite exists to surface.
- KTD4. The `no-pr-trigger` opt-out and deliberate push-only workflows are handled through the R31 verifier's own semantics. Rationale: the mutation suite checks that the verifier reacts; it does not re-decide trigger policy.

### Assumptions

- The suite depends on R31's closed-form verifier (plan `2026-08-02-034`); where it has not landed, the runner bootstraps on `validate_trigger_manifest` from `scripts/check_required_checks.py` as the minimum verifier surface.
- Path-filtered workflows are those with a `paths:` block under push or pull_request; `required-checks.yml` (no path filter) contributes only to the context-resolution half and has no per-path mutations.
- `schedule` and `workflow_dispatch` triggers are not load-bearing for the merge path and are out of the per-event mutation set in the first release.

---

## Implementation Units

### U1. Trigger-path mutation runner

**Goal:** Implement the copy-based mutation runner that removes each trigger path and event and asserts the verifier's verdict changes.

**Requirements:** R43

**Dependencies:** R31 U1/U2 verifier surface

**Files:**
- `scripts/check_trigger_path_mutations.py` (new)
- `scripts/tests/test_check_trigger_path_mutations.py` (new)
- `scripts/manifest.yaml` (edit: entry for the new script)

**Approach:** For each path-filtered workflow, for each trigger path in each trigger list (push and pull_request), produce a temp copy with exactly that path removed and run the verifier against the copy's directory; assert the verifier now fails (the closed-set check catches the missing copy). Do the same for removing a whole trigger event (for example dropping pull_request where the verifier requires push equals pull_request). Verdict per mutation: DETECTED (verifier failed as expected), MISSED (verifier still passed — a verifier gap), or UNVERIFIED (mutation could not be applied or the verifier errored). Any MISSED or UNVERIFIED fails the run; zero applicable mutations fail closed.

**Patterns to follow:** the copy-based mutation discipline of the R42 engine (temp copies, side-effect free); the per-mutation verdict shape of R42.

**Test scenarios:**
1. DETECTED: remove one path from the pull_request list of a fixture workflow with push equal to pull_request — the verifier's equality check fails, verdict DETECTED.
2. DETECTED (manifest side): remove a path from the push list — the verifier's manifest-containment check fails.
3. MISSED: a fixture verifier that only checks push equals pull_request tolerates a manifest-only path removal — verdict MISSED, run fails (the gap class the suite exists to surface).
4. Event removal: dropping pull_request entirely from a path-filtered workflow — the verifier fails, verdict DETECTED.
5. Opt-out workflow: a push-only workflow with the `no-pr-trigger` comment — the suite still checks the paths it has, and the opt-out does not mask a removal the verifier should catch.
6. No path-filtered workflows: fail-closed.
7. Committed workflow files are byte-identical before and after a run (copy-based proof).

**Verification:** Each verdict class is observable from the unit suite; the runner reports per-mutation verdicts and totals on pass and fail.

### U2. Initial sweep over the workflow set

**Goal:** Run the mutation suite across every path-filtered workflow and fix the verifier gaps it surfaces.

**Requirements:** R43

**Dependencies:** U1

**Files:**
- `scripts/check_closed_form_triggers.py` (edit, only if a gap is found)
- `docs/evidence/` (new doc recording the sweep: per-workflow mutation coverage and any verifier gaps fixed)

**Approach:** Run the suite against the real `.github/workflows/` set; for every MISSED mutation, fix the R31 verifier (add the missing comparison) and re-run. Record the sweep outcome per workflow (paths covered, DETECTED count). The expected outcome: `python-tests.yml`'s three-way equality yields DETECTED for path removals; gaps are most likely in the manifest-containment direction if the R31 verifier scoped it narrowly.

**Patterns to follow:** the falsifier-first discipline (a sweep that finds nothing must state what it would have found); the measurement conventions of the `docs/evidence/` docs.

**Test scenarios:**
1. Every path in `python-tests.yml`'s push and pull_request lists is individually removable with DETECTED.
2. Every manifest path that maps to a workflow is DETECTED on removal from its workflow copy.
3. Any MISSED from the sweep is fixed, and the specific verifier change is recorded in the evidence doc with the mutation that exposed it.
4. Re-running the sweep after fixes is deterministic and all-DETECTED.

**Verification:** The sweep doc records per-workflow coverage; the suite exits 0 with all mutations DETECTED.

### U3. CI wiring

**Goal:** Wire the trigger-path mutation suite into CI alongside the R31 verifier.

**Requirements:** R43

**Dependencies:** U2

**Files:**
- `.github/workflows/required-checks.yml` (edit: new step, or extend the R31 verifier step)
- `.github/required-checks.json` (edit: add the new script and its test to `trigger_paths`)
- `.github/workflows/python-tests.yml` path lists (edit: both copies, if the script is added to them)
- `scripts/manifest.yaml` (edit: entry with `disposition: ci-gate`)

**Approach:** Run the mutation suite in the always-on job, in the same place as the R31 verifier, so a mutation test and its verifier run in one unit. Add the new script and test to the trigger-path copies. Never `continue-on-error`. The suite is cheap (a few workflows times path counts, each a verifier run on a temp directory) and safe per PR.

**Patterns to follow:** the always-on structure of `required-checks.yml`; the actionlint convention for workflow edits.

**Test scenarios:**
1. Workflow lint: actionlint passes on the edited workflow.
2. The three-way trigger-path copies stay in sync after additions.
3. A deliberately registered MISSED mutation (a verifier gap simulated in a fixture) fails the CI step, proving the wiring.
4. The mutation step reports independently of sibling checks.

**Verification:** CI runs the mutation suite on every PR and fails on any MISSED or UNVERIFIED mutation; a simulated gap is demonstrated to fail.

---

## Verification Contract

- Unit suite: `uv run pytest scripts/tests/test_check_trigger_path_mutations.py -v --tb=short`.
- Gate self-check: `uv run python scripts/check_trigger_path_mutations.py` exits 0 with all mutations DETECTED on the current tree; committed workflows are byte-identical after a run.
- Falsifier: register a known-MISSED fixture and the run fails naming the path and the verifier gap; drop one real path from a workflow copy by hand and the R31 verifier fails (static half) while the mutation runner reports DETECTED for that path (live half).
- CI integration: the always-on run executes the suite on every PR.
- Workflow lint: actionlint passes; the required-checks drift checks stay green.

---

## Definition of Done

- The mutation runner covers every path-filtered workflow and every load-bearing trigger event.
- The initial sweep is complete and recorded in `docs/evidence/`; any verifier gaps found are fixed in the R31 verifier and attributed in the evidence doc.
- The suite is wired into CI, and a simulated gap is demonstrated to fail the CI step.
- `scripts/manifest.yaml` has the new script entry with `disposition: ci-gate`.
- No launch-blocking open question remains.

---

## Scope Boundaries

- In scope: per-path and per-event trigger mutation against the R31 verifier.
- Out of scope: mutating gate scripts (R42 owns gate mutation); re-deciding trigger policy (the `no-pr-trigger` opt-out rule stays with `scripts/check_workflow_pr_triggers.py`); mutating `schedule` or `workflow_dispatch` triggers in the first release.

### Deferred to Follow-Up Work

- Per-event mutation for `schedule` crons if they become merge-gating.
- Merging the mutation runner into the R31 verifier script if the repo prefers one always-on gate (documented merge point with R31).
- Mutation coverage for `pull_request_target`-only workflows once they carry path filters.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` (R43)
- `docs/plans/2026-08-02-034-feat-trigger-path-closed-form-plan.md` (R31 — the verifier under test)
- `scripts/check_workflow_pr_triggers.py`
- `scripts/check_required_checks.py`, `scripts/tests/test_check_required_checks.py`
- `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md`
- `.github/workflows/` (the workflow set under mutation)
