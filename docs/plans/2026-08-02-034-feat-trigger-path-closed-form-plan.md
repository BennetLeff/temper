---
title: "Closed-Form Trigger-Path Verification - Plan"
type: feat
date: 2026-08-02
topic: trigger-path-closed-form
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R31)
---

# Closed-Form Trigger-Path Verification - Plan

## Goal Capsule

**Objective:** Make workflow triggers and the required-check manifest a closed set: every path-filtered workflow's push and pull_request trigger lists must match each other and match the manifest, every required context must resolve to a real job name, and any divergence is a hard CI failure.

**Product authority:** temper-placer and firmware maintainer (single-maintainer project); CI policy is owned through the existing gate scripts.

**Open blockers:** none.

---

## Product Contract

### Summary

The trigger-path verification becomes closed-form and repo-wide: the three-way drift check that today guards only `python-tests.yml` is generalized to every path-filtered workflow and to the required-check contexts. The branch-protection near-miss class fails at CI time instead of at enablement time.

### Problem Frame

This idea exists for the branch-protection near-miss class: path-filtered workflows never reported for unrelated PRs, which wedged branch protection (`docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md`), and the trigger path list is duplicated across three copies (push, pull_request, manifest) so any addition must be made three times. Today only `python-tests.yml` is drift-checked (`validate_trigger_manifest` in `scripts/check_required_checks.py`), and the required contexts are never checked to resolve to real job names — an aggregator context that names no job can never report.

### Requirements

- R31. **Closed-form trigger-path verification** (Formal / CI / P2): workflow triggers and required-check manifests are verified as a closed set — a path present in one manifest but not the other is a hard failure, preventing the branch-protection near-miss class. Seed: `scripts/check_required_checks.py` and `.github/required-checks.json`.
- **Success signal:** a path added to any one of the three copies (push list, pull_request list, manifest) without the other two fails CI; a required context that does not resolve to a job name in any workflow fails CI; the check runs on every PR and fails closed on an empty workflow set.

### Key Technical Decisions

- KTD1. Extend the existing drift-check logic rather than build a separate mechanism: `validate_trigger_manifest` already proves the three-way match for `python-tests.yml`, and the closed-form verifier reuses its parsing functions. Rationale: the repo convention prefers extending existing gates, and the drift logic is proven.
- KTD2. The closed set is defined per workflow with path-filtered triggers: push list equals pull_request list, and that list is contained in the manifest's `trigger_paths`; the manifest remains the reference the aggregator enforces against. Rationale: containment, not equality, is the right relation when the manifest is the enforced contract.
- KTD3. The check is bidirectional: every manifest path must also appear in at least one workflow's trigger lists, so a dead manifest entry (a path no workflow fires on) is caught. Rationale: a path present in one manifest but not the other must fail in either direction, per the requirement's wording.
- KTD4. Required contexts resolve to real job names through a registry derived from the workflows' `name:` fields; an unresolvable context is a hard failure. Rationale: the exact-name-matching fragility documented in the handoff is made explicit rather than implicit.
- KTD5. The verifier runs always-on, independent of path filters. Rationale: a drift in trigger coverage must be caught even on PRs whose changed paths would not have triggered the drifted workflow.

### Assumptions

- `.github/required-checks.json` remains the single enforced manifest; a path-filtered workflow absent from the manifest is itself a violation.
- Workflows with no path filters (e.g. `required-checks.yml`) are out of scope for the path-list equality half but still contribute job names to the context-resolution registry.
- The push-requires-pull_request rule stays with `scripts/check_workflow_pr_triggers.py`; this plan does not subsume it.

---

## Implementation Units

### U1. Repo-wide workflow trigger parser

**Goal:** Generalize trigger and path parsing from `python-tests.yml` to every workflow in `.github/workflows/`.

**Requirements:** R31

**Dependencies:** none

**Files:**
- `scripts/check_closed_form_triggers.py` (new)
- `scripts/tests/test_check_closed_form_triggers.py` (new)
- `scripts/manifest.yaml` (edit: entry for the new script)

**Approach:** Parse every `.github/workflows/*.yml` for trigger events (push, pull_request, pull_request_target, schedule, workflow_dispatch; shorthand, list, and block forms) and path-filter lists. Reuse the literal path-list parser of `load_workflow_trigger_paths` in `scripts/check_required_checks.py` and the YAML preprocessing of `scripts/check_workflow_pr_triggers.py` (the `on:` and `${{ }}` quirks). Honor the `no-pr-trigger` YAML comment opt-out so deliberate push-only workflows do not pollute the closed-set check. Output per workflow: events, path lists, job names, and a parse-error verdict; an unparseable workflow fails closed.

**Patterns to follow:** the dependency-free literal parser of `load_workflow_trigger_paths`; the YAML preprocessing in `scripts/check_workflow_pr_triggers.py`.

**Test scenarios:**
1. A workflow whose push and pull_request path lists match parses to identical lists.
2. A workflow whose push list is missing one path parses to divergent lists (drift detected downstream).
3. Shorthand triggers (`on: push`, `on: [push, pull_request]`) parse to the correct event sets.
4. The `no-pr-trigger` opt-out comment suppresses the push-without-pull_request finding but still yields the path list for the closed-set check.
5. An unparseable workflow file produces a parse-error verdict and a non-zero exit (fail-closed).
6. Real repo: the parser reports N workflows parsed and M path-filtered, with the same facts the existing gates see for `python-tests.yml`.

**Verification:** The parser's per-workflow facts match the facts `scripts/check_required_checks.py` and `scripts/check_workflow_pr_triggers.py` produce for `python-tests.yml`, cross-checked by test.

### U2. Closed-set verifier (manifest to workflow)

**Goal:** Implement the closed-form comparison: every path-filtered workflow's push and pull_request lists are identical and contained in the manifest, and every manifest path appears in at least one workflow list.

**Requirements:** R31

**Dependencies:** U1

**Files:**
- `scripts/check_closed_form_triggers.py` (edit)
- `scripts/tests/test_check_closed_form_triggers.py` (edit)
- `.github/required-checks.json` (read)

**Approach:** Treat `required-checks.json` `trigger_paths` as the reference. For each path-filtered workflow, assert push equals pull_request and the list is a subset of the manifest paths; conversely, assert every manifest path appears in at least one workflow's lists. Any divergence is a hard failure naming the path and the two sides. This makes the "path present in one manifest but not the other" rule bidirectional.

**Patterns to follow:** the error shape of `validate_trigger_manifest` ("lists diverge from required-checks manifest"); the fail-closed denominator discipline.

**Test scenarios:**
1. A path added to the push list only: failure naming the path and the missing pull_request copy.
2. A path added to the manifest only: failure naming the path absent from every workflow list.
3. A path added to one workflow's lists but not the manifest: failure naming the path and the workflow.
4. All three copies in sync: pass, with the manifest path count as the denominator.
5. A workflow with no path filters is not required to appear in the manifest (no false positive).
6. Real repo: the current three copies are in sync, so the verifier passes.

**Verification:** The verifier passes on the current tree; each of the three drift directions (push-only, manifest-only, workflow-only) is a covered unit test with a named failure message.

### U3. Required-context resolution registry

**Goal:** Verify every `required_context` in the manifest resolves to a job name in the workflows.

**Requirements:** R31

**Dependencies:** U1

**Files:**
- `scripts/check_closed_form_triggers.py` (edit)
- `scripts/tests/test_check_closed_form_triggers.py` (edit)

**Approach:** Collect `name:` values of every job across all workflows; assert every entry in the manifest's `required_contexts` appears in that set, with exact matching. An unresolvable context fails, naming the orphaned name — this is the "aggregator context names no job, so it can never report" class that would wedge branch protection.

**Patterns to follow:** the exact-name-matching fragility documented in `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md`, made explicit as a check.

**Test scenarios:**
1. Every manifest context resolves to a job name in the current tree: pass.
2. A context renamed in a workflow but not in the manifest: failure naming the orphaned context.
3. A context added to the manifest that no workflow emits: failure.
4. A workflow job renamed: the manifest's old context fails resolution (the exact near-miss this check exists for).
5. Duplicate job names across workflows: resolution requires an exact match against at least one, and ambiguity is reported.

**Verification:** Resolution is exact-match and covered for the four drift directions; the current tree passes.

### U4. Always-on CI wiring

**Goal:** Run the closed-form verifier on every PR, independent of path filters.

**Requirements:** R31

**Dependencies:** U2, U3

**Files:**
- `.github/workflows/required-checks.yml` (edit: new step in the always-on aggregator)
- `.github/required-checks.json` (edit: add the new script and its test to `trigger_paths`)
- `.github/workflows/python-tests.yml` path lists (edit: both copies, if the script is added to them)
- `scripts/manifest.yaml` (edit: entry with `disposition: ci-gate`)

**Approach:** Run the verifier in the always-on `required-checks.yml` aggregator so it fires even when no trigger path matches the PR; the aggregator already checks out the trusted base revision, so a PR cannot weaken the verifier that judges it. Add the new script and test to the trigger-path copies so changes to the verifier itself re-run the relevant suite. The step is never `continue-on-error`.

**Patterns to follow:** the always-on structure and base-revision checkout of `required-checks.yml`; the actionlint convention for workflow edits.

**Test scenarios:**
1. Workflow lint: actionlint passes on the edited workflow.
2. A PR touching only `.github/workflows/*.yml` still runs the verifier, and a deliberate drift in a workflow fails the aggregator.
3. The manifest trigger paths and `python-tests.yml` lists stay in sync (the three-way drift check remains green).
4. The verifier step's failure does not mask sibling checks (independent reporting).

**Verification:** The always-on run reports the closed-set verdict on every PR; a temporary drift (removing one path from a workflow copy) fails the run — the scenario R43's trigger-path mutation will exploit.

---

## Verification Contract

- Unit suite: `uv run pytest scripts/tests/test_check_closed_form_triggers.py -v --tb=short`.
- Gate self-check: `uv run python scripts/check_closed_form_triggers.py` passes on the current tree and reports the manifest and context denominators.
- Falsifier: each of the six drift directions (push-only, pull_request-only, manifest-only, workflow-only, orphaned context, renamed job) is a unit test with a named failure.
- CI integration: the always-on run reports the closed-set verdict on every PR.
- Workflow lint: actionlint passes; the existing `check_required_checks.py` suite stays green (no behavior change to it).

---

## Definition of Done

- The verifier covers every path-filtered workflow and every manifest context.
- All six drift directions are covered by unit tests with named failures.
- The verifier runs always-on in CI.
- `scripts/manifest.yaml` has the new script entry with `disposition: ci-gate`.
- The current tree passes the verifier with no drift.
- No launch-blocking open question remains.

---

## Scope Boundaries

- In scope: closed-set verification of trigger paths and required contexts.
- Out of scope: re-verifying the push-requires-pull_request rule (`scripts/check_workflow_pr_triggers.py` owns it); live trigger-path mutation (R43 owns it); branch-protection enablement.
- The verifier checks drift; it does not decide which checks are required.

### Deferred to Follow-Up Work

- Extending the closed set to schedule crons and `workflow_dispatch` inputs if they ever become load-bearing for merge gating.
- Migrating the verifier into `scripts/check_required_checks.py` if the repo prefers one script (documented merge point with R43, which mutates the same verifier).
- A context-resolution registry for job names emitted by reusable workflows if those become part of the check surface.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` (R31)
- `scripts/check_required_checks.py`, `scripts/tests/test_check_required_checks.py`
- `.github/required-checks.json`, `.github/workflows/required-checks.yml`, `.github/workflows/python-tests.yml`
- `scripts/check_workflow_pr_triggers.py`
- `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md`
- `docs/plans/2026-08-02-036-feat-trigger-path-mutation-plan.md` (R43, the injection-tier consumer)
