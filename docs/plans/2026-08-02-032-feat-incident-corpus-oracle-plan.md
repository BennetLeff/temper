---
title: "Incident Corpus & Gate Canary Contract - Plan"
type: feat
date: 2026-08-02
topic: incident-corpus-oracle
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R19, R30)
---

# Incident Corpus & Gate Canary Contract - Plan

## Goal Capsule

**Objective:** Turn the historical incident record into a permanent regression corpus and extend it to totality: every past incident is re-encoded as a seeded artifact (mutated board, mutated constraint, mutated workflow) that the gate it escaped must now reject (R19), and every gate in the CI inventory carries a demonstrated failing case — a canary seed it must reject (R30). One shared runner executes both phases over the same `ci-corpus/` directory and verdict classes; CI fails when a seed stops being rejected, when a gate lacks a canary, or when the corpus or canary set is empty.

**Product authority:** temper-placer and firmware maintainer (single-maintainer project); the corpus grows by appending incidents as they are fixed; the gate inventory is owned through `scripts/manifest.yaml`.

**Open blockers:** none.

---

## Product Contract

### Summary

The incident corpus oracle makes the historical record executable and then upgrades the vacuity discipline to a per-gate canary contract. Each past incident ships as a committed seed artifact plus the gate that must reject it (Phase 1, the history tranche); every `disposition: ci-gate` script in `scripts/manifest.yaml` then carries a canary it is demonstrated to reject (Phase 2, the totality contract). Both phases run through the same runner with the same seed/pristine/expected-gate entry shape, the same verdict classes, and the same fail-closed-on-empty rule, so a silent corpus is impossible in either phase.

### Problem Frame

This idea exists for the recurring escape class: a defect ships because no gate rejected the artifact that contained it — courtyard 0-vs-43, rotation-sign across call sites, vacuous `all()` and tautological asserts, a workflow with no pre-merge trigger, a board changed without its ceiling re-measured. Each was fixed and documented in `docs/evidence/`, but nothing re-checks that the fixing gate still bites; the historical record is prose that nothing executes. The same trust-the-gate failure mode is why a gate is assumed to bite until a defect slips through — a rule that matched nothing (`docs/solutions/best-practices/a-rule-that-matches-nothing-reads-as-coverage-2026-07-28.md`), vacuous `all()` and tautological asserts (`scripts/check_vacuous_gates.py`), and a gate whose scope silently excluded most of its intended universe (`docs/evidence/2026-07-27-gate-subset-blindness-audit.md`). `check_vacuous_gates.py` catches syntactic vacuity; it cannot prove that a specific gate rejects a specific defect.

R19 and R30 are one mechanism at two granularities: R19 makes the historical record executable (seeds for the incidents that already happened), and R30 makes the demonstration per-gate and mandatory (a canary for every gate, whether or not it has an incident). They share the runner, the `ci-corpus/` directory, the seed/pristine/expected-gate shape, and the verdict classes, and they are sequentially dependent — the totality contract cannot start before the shared runner from the history phase exists. This plan merges them: Phase 1 (history tranche) and Phase 2 (totality contract) over one runner.

### Requirements

- R19. **Incident corpus oracle** (Oracle / CI / P1): every past incident is re-encoded as a seeded artifact (mutated board, mutated constraint, mutated workflow) that CI must fail on — the historical record becomes a permanent regression corpus. Seed: `scripts/check_vacuous_gates.py` and `docs/evidence/`.
- **Success signal:** every registered incident has a seed artifact and a named gate; the corpus gate runs each seed and fails when the seed's gate does not reject it; the corpus gate fails closed on an empty corpus.
- R30. **Proven non-vacuity for every CI gate** (Formal / CI / P1): every gate carries a demonstrated failing case (a seed artifact it must reject), upgraded from advisory vacuity checks to a per-gate canary contract. Seed: `scripts/check_vacuous_gates.py`.
- **Success signal:** every gate with `disposition: ci-gate` in `scripts/manifest.yaml` has a canary entry that resolves to a seed artifact its gate rejects; the contract check fails when any gate lacks a canary, when any canary no longer fails its gate, and when the canary set is empty.

### Key Technical Decisions

- KTD1. Corpus as declarative manifest plus committed fixtures: `ci-corpus/incidents.yaml` maps each incident id to its seed path, pristine path, expected-failing gate, and evidence doc. Rationale: a manifest is reviewable in the PR diff and enumerable for a denominator, matching the repo's `scripts/manifest.yaml` and `.github/required-checks.json` conventions.
- KTD2. Every seed is paired with a pristine counterpart that must pass the same gate. Rationale: without the pass side, a seed that fails every gate trivially (a malformed file) would satisfy the fail side and prove nothing about the specific gate.
- KTD3. Seeds are committed files under a new top-level `ci-corpus/` directory, one subdirectory per artifact class. Rationale: these are intentionally invalid artifacts that must never be picked up by normal tooling, so they need a dedicated, visible home.
- KTD4. Gate invocation matches CI's command shape (same script, same flags, external process, exit-code verdict). Rationale: the corpus proves wiring (trigger plus CLI plus exit code), not just detector logic.
- KTD5. One shared runner owns both phases. R19's history tranche and R30's totality contract execute through the same `scripts/check_incident_corpus.py` mechanism over the same `ci-corpus/` directory and verdict classes; the Phase 2 canary registry uses the same entry shape as the Phase 1 incident manifest. Rationale: one seed shape, one runner, one verdict semantics — the historical corpus feeds the contract for free, and the sequential dependency (Phase 2 cannot start before the Phase 1 runner) resolves to a single artifact instead of two parallel implementations.
- KTD6. The gate inventory is derived from `scripts/manifest.yaml` entries with `disposition: ci-gate`, never a new hand-maintained gate list. Rationale: the manifest is the existing single source of truth and already makes every new gate visible; `scripts/check_manifest_gate.py` already requires a manifest entry for every new script.
- KTD7. Directory-scanning gates need a per-incident temp-directory layout plus recorded invocation flags in the corpus manifest; a single-file "seed path" contract does not work for them. `check_vacuous_gates.py` scans `--packages-dir`/`--scripts-dir` and `check_workflow_pr_triggers.py` scans `--workflows-dir`, so their seeds materialize as a per-incident directory tree during the run, with the flags and the expected verdict recorded per entry. Rationale: a seed that must flip a directory-scanning gate cannot be expressed as one path; the materialization step is part of the manifest contract, and every such seed still pairs with a pristine directory that must pass.
- KTD8. A seed whose gate cannot currently run (gate not wired, or pristine not yet available because the defect is still on main) is registered with verdict UNVERIFIED, never dropped. Rationale: the corpus must stay honest about what it does and does not prove yet, and a dropped canary is a silent coverage loss.
- KTD9. A seed a gate legitimately stops rejecting is retired with a recorded reason, not silently removed. Rationale: a fix can make a seed's defect class impossible, and a gate's scope can legitimately narrow; retirement mirrors R42's declared-equivalent-with-justification discipline (`docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md`) so the corpus never ratchets a stale expectation or hides a real regression.
- KTD10. New gates register a canary in the same change that wires them; the contract check fails closed on an unregistered gate. Rationale: the AGENTS.md script-manifest convention already requires a manifest entry for every new script, so the canary requirement rides the same review surface.
- KTD11. All gates remain advisory while branch protection on `main` is disabled; advisory status is recorded per gate, and the must-bite requirement applies to fail-closed gates. Rationale: `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md` records that every gate is advisory until protection lands; the contract distinguishes must-bite gates from advisory ones rather than pretending the enforcement reality away.

### Assumptions

- The first tranche is populated from the incident classes named in the portfolio Problem Frame and the seed evidence docs; the exact fixture geometry for each seed is an execution-time detail.
- The `ci-corpus/` name and layout are this plan's choice; a different repo-root name is acceptable if it keeps the same layout contract.
- A still-unfixed defect (C1↔R7 short, tank capacitor off-board) registers its seed now with pristine marked pending; its verdict is UNVERIFIED until the fix lands and a pristine is available.
- Where no incident seed exists for a gate, canaries bootstrap from the falsifier and fail-closed fixtures already present in `scripts/tests/` rather than waiting for new incidents.
- Advisory gates (explicitly `continue-on-error` in workflows, e.g. the coverage gate) are registered with their advisory status recorded; the must-bite requirement applies to fail-closed gates.

---

## Implementation Units

**Unit mapping from the merged sources:** the surviving plan's U-IDs are kept (032 U1→U1, U2→U2, U3→U3, U4→U6); absorbed units take the next unused numbers (033 U1→U4, 033 U3→U5). 033's local-duplicate liveness runner (033 U2) and its CI-wiring unit (033 U4) are folded into the shared runner (U2) and the merged wiring unit (U6) rather than carried as separate units.

### U1. Corpus layout and incident manifest

**Goal:** Create the corpus directory structure and the declarative incident manifest that maps every incident to a seed artifact, an expected-failing gate, and its evidence doc — including the per-incident invocation contract that directory-scanning gates require.

**Requirements:** R19

**Dependencies:** none

**Files:**
- `ci-corpus/incidents.yaml` (new)
- `ci-corpus/README.md` (new)
- `ci-corpus/board/`, `ci-corpus/constraint/`, `ci-corpus/workflow/`, `ci-corpus/test/` (new directories)

**Approach:** Mirror the `scripts/manifest.yaml` entry shape, extended with incident-specific fields: incident id, artifact class (board/constraint/workflow/test), seed path, pristine path, expected gate (script path plus invocation flags), evidence doc path, and verdict status. The manifest is the single source of truth; every entry must be non-empty and resolvable. The seed-materialization contract is part of this manifest: for directory-scanning gates (`check_vacuous_gates.py` with `--packages-dir`/`--scripts-dir`, `check_workflow_pr_triggers.py` with `--workflows-dir`), a single-file "seed path" cannot express the seed — each such entry records its invocation flags and a per-incident temp-directory layout (which files the directory must contain, what the gate scans, and what verdict is expected), and the seed/pristine pair is a pair of directory trees, not a pair of files. Every seed, file-based or directory-based, is paired with a pristine counterpart that must pass. Schema validation lives in the U2 runner so a malformed manifest fails the gate, not a separate tool.

**Patterns to follow:** the entry shape of `scripts/manifest.yaml`; the versioned declarative manifest of `.github/required-checks.json`; the fail-closed denominator discipline of `scripts/check_domain_partition.py`.

**Test scenarios:**
1. Schema validation: an `incidents.yaml` entry missing its expected-gate field is reported by id and the manifest fails to load (runner exits non-zero).
2. Empty corpus: an `incidents.yaml` with zero entries produces a fail-closed message naming the file and a non-zero exit, never "0 incidents, pass".
3. Unresolvable seed path: an entry whose seed file does not exist on disk is a named failure listing the missing path.
4. Duplicate incident id: two entries with the same id are a named failure.
5. A well-formed entry for the tautological-assert incident (`docs/evidence/2026-07-27-vacuous-aggregation-audit.md`) validates and resolves its seed, pristine, and evidence paths.
6. A directory-scanning entry (e.g. `check_vacuous_gates.py` with `--scripts-dir`) records its invocation flags and temp-directory layout spec; materializing it produces a directory the gate flags, and its pristine counterpart produces a directory the gate passes.

**Verification:** The manifest loader reports the corpus denominator (N incidents, M classes) on both pass and fail; a hand-written sample manifest with one entry per class validates; each directory-scanning class materializes both its seed and pristine layout.

### U2. Shared runner (gate-rejects-seed oracle)

**Goal:** Implement `scripts/check_incident_corpus.py` — the shared runner that executes both phases. For each manifest entry it runs the named gate against the seed artifact (must fail) and the pristine counterpart (must pass) and reports per-entry verdicts; the same execution loop is the liveness mechanism for the Phase 2 canary registry, with no second runner.

**Requirements:** R19, R30

**Dependencies:** U1

**Files:**
- `scripts/check_incident_corpus.py` (new)
- `scripts/tests/test_check_incident_corpus.py` (new)
- `scripts/manifest.yaml` (edit: entry for the new script)

**Approach:** Load the manifest (Phase 1: `ci-corpus/incidents.yaml`; Phase 2: `ci-corpus/canaries.yaml`); for each entry, execute the named gate with its recorded flags against the seed path and the pristine path, capturing exit codes. Directory-scanning entries materialize their per-incident temp-directory layout before the gate run and tear it down after. One verdict semantics across both phases: PASS when the seed run fails and the pristine run passes; FAIL when a half broke — seed no longer rejected (the regression case) or pristine now rejected (over-broad gate) — with a message naming which half; UNVERIFIED when the demonstration cannot currently happen (gate error, missing seed, gate not wired, or pristine pending). Gate scripts run as the CI workflows invoke them, so the corpus proves wiring. Zero scanned entries fails closed in both phases, mirroring the zero-scan guard of `check_vacuous_gates.py`; an empty corpus or an empty canary set never reports "0, pass". Liveness rule, per phase: in Phase 2 every canary must demonstrate bite, so any verdict other than PASS fails the run and UNVERIFIED names its reason; in Phase 1 an UNVERIFIED entry with a recorded reason (pristine pending for a still-unfixed defect) passes with the reason recorded, while FAIL always fails.

**Patterns to follow:** the fail-closed zero-scan guard and denominator printing of `scripts/check_vacuous_gates.py`; the exit-code semantics documented in `scripts/check_manifest_gate.py`.

**Test scenarios:**
1. Happy path: a tiny synthetic gate in a temp dir rejects a seeded bad file and accepts a pristine file; the runner reports PASS for the entry.
2. Regression detection: the same synthetic gate modified to accept the seeded bad file; the runner reports FAIL naming the seed no longer rejected (the corpus's core purpose).
3. Over-broad gate: the gate modified to also reject the pristine file; the runner reports FAIL naming the pristine side.
4. Gate crash on the seed (non-zero for an unrelated reason): the runner distinguishes "rejected" (expected exit) from "gate error" (unexpected exit), reporting UNVERIFIED rather than PASS.
5. Empty corpus: fail-closed exit, mirroring U1 scenario 2.
6. One incident per class with hand-built minimal seeds: all verdict classes (PASS, regression FAIL, over-broad FAIL, UNVERIFIED) are observable.
7. A directory-scanning entry: the materialized seed directory flips the gate and the pristine directory passes, with recorded flags driving the invocation.
8. Phase 2 liveness: a registered canary whose gate accepts its seed reports FAIL on the regression side, naming the canary and the seed.
9. Phase 1 pristine-pending entry: UNVERIFIED with its recorded reason passes the run; the same verdict in Phase 2 (gate not wired) is reported as not-yet-demonstrated with its reason.
10. Empty canary set (Phase 2): fail-closed, never "0 canaries, pass".

**Verification:** The unit suite passes and the runner reports "N entries checked, M PASS, K FAIL/UNVERIFIED" on both pass and fail for each phase; a seed that regresses flips the run red; each verdict class is observable from the unit suite.

### U3. Phase 1 population (history tranche)

**Goal:** Encode the first tranche of past incidents as seed/pristine pairs and register them in `incidents.yaml`.

**Requirements:** R19

**Dependencies:** U1, U2

**Files:**
- `ci-corpus/incidents.yaml` (edit)
- `ci-corpus/board/` (new seed and pristine pairs)
- `ci-corpus/constraint/` (new seed and pristine pairs)
- `ci-corpus/workflow/` (new seed and pristine pairs, including temp-directory layouts)
- `ci-corpus/test/` (new seed and pristine pairs)

**Approach:** Derive each seed from the evidence doc's described defect and the pristine from the fixed state; prefer minimal fixtures over full-board copies where the gate reads a single file. Directory-scanning seeds (the workflow class) materialize as per-incident temp-directory layouts recorded in the manifest per U1. Candidate registrations, by class:
- Board class: C1↔R7 short (`docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md`) against the full-board DRC gate (`scripts/ci_check_drc.py` or the `_drc_api.run_drc` path), pristine pending until the short is fixed; tank capacitor staged off-board (`docs/evidence/2026-07-28-tank-cap-placement.md`) against the copper-net consistency gate (`scripts/check_copper_net_consistency.py`).
- Constraint class: `weak-nooverlap2d` (`docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md`), `atmostk` (`docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md`), `endpoint-bounding` (`docs/solutions/logic-errors/endpoint-bounding-unsound-without-monotonicity-2026-07-09.md`) against the post-solve audit or the BMC tests (`packages/temper-placer/src/temper_placer/placer/cp_sat/audit.py`, `scripts/bmc_adoption_gate.py`).
- Workflow class: push-without-pull_request (issue #315, referenced by `scripts/check_workflow_pr_triggers.py`) against `scripts/check_workflow_pr_triggers.py` — the seed is a per-incident temp directory containing the mutated workflow, the pristine its fixed counterpart.
- Test class: tautological assert (`docs/evidence/2026-07-27-vacuous-aggregation-audit.md`) and unguarded `all()` (the 13 findings in `docs/evidence/2026-07-27-gate-subset-blindness-audit.md`) against `scripts/check_vacuous_gates.py`, using the `--scripts-dir` temp-directory layout for directory-scanning runs.

**Patterns to follow:** the synthetic-fixture pattern of `scripts/tests/test_check_vacuous_gates.py` for the constraint and test classes; the YAML comment opt-out convention of `scripts/check_workflow_pr_triggers.py` for the workflow class.

**Test scenarios:**
1. Each registered board-class incident: seed board makes the named gate exit non-zero; pristine board makes it exit 0 (pristine pending for still-unfixed defects, verdict UNVERIFIED).
2. Each registered constraint-class incident: seed encoding is rejected by its audit/BMC check; pristine encoding passes.
3. Each registered workflow-class incident: the materialized seed directory makes `check_workflow_pr_triggers.py` exit 1; the pristine directory exits 0.
4. Each registered test-class incident: the seed file (or seed directory) is flagged by `check_vacuous_gates.py`; the pristine passes.
5. Full corpus run after population: every registered incident reports PASS or UNVERIFIED, and the runner's denominator equals the manifest entry count.

**Verification:** The corpus gate exits 0 with all incidents PASS/UNVERIFIED; reverting any one seed to its pristine state flips exactly that incident to FAIL (spot-check at least one per class).

### U4. Canary registry and gate inventory extraction

**Goal:** Define the Phase 2 canary registry and the inventory extraction that derives the gate set from `scripts/manifest.yaml` — the totality coverage contract over the shared runner.

**Requirements:** R30

**Dependencies:** U1, U2

**Files:**
- `ci-corpus/canaries.yaml` (new)
- `scripts/tests/test_canary_inventory.py` (new)

**Approach:** `canaries.yaml` maps each ci-gate script path to its canary: seed path, pristine path, invocation flags, evidence doc, and status (`fail-closed` or `advisory`). The entry shape is the same as `incidents.yaml` (seed, pristine, expected gate) — one mechanism at two granularities, executed by the same U2 runner. The extraction reads `scripts/manifest.yaml`, filters `disposition: ci-gate`, and cross-references `canaries.yaml`; any gate missing from the registry is a coverage violation. The gate inventory is derived from the manifest — never a new hand-maintained list — and the existing `scripts/check_manifest_gate.py` requirement of a manifest entry for every new script keeps the inventory aligned with the filesystem. First release is scoped to detector gates with existing falsifier fixtures: 24 of the 51 ci-gate scripts today have `test_<name>.py`; the remaining 27 — non-detector entries such as `pipeline_metrics.py`, codegen scripts (`gen_*.py`), and build-side helpers (`write_*_stamps.py`) — get an explicit triage entry in the registry recording why no canary applies yet or which fixture will serve, so the coverage gap is named, never silently skipped. Advisory status is recorded from the workflow `continue-on-error` state so the contract distinguishes must-bite gates from advisory ones.

**Patterns to follow:** the `disposition` field of `scripts/manifest.yaml`; the versioned declarative manifest of `.github/required-checks.json`; the denominator discipline of `scripts/check_domain_partition.py`.

**Test scenarios:**
1. A snapshot of `scripts/manifest.yaml` ci-gate entries is fully present in `canaries.yaml`; extraction reports N gates, all covered.
2. A gate removed from `canaries.yaml`: coverage violation naming the gate, extraction exits non-zero.
3. A gate whose manifest disposition changes from `ci-gate` to `utility` is no longer required to carry a canary (documented intended relaxation).
4. An advisory gate (recorded `continue-on-error` in a workflow) is registered with status `advisory` and does not trip the fail-closed requirement.
5. Empty `canaries.yaml`: fail-closed message, exit non-zero.
6. A non-detector ci-gate entry (e.g. `pipeline_metrics.py`) carries an explicit triage record; the extraction output names the coverage gap for entries without falsifier fixtures rather than treating them as covered.

**Verification:** The extraction reports the gate-count denominator on pass and fail; the coverage check fails on any missing canary.

### U5. Phase 2 population (totality canaries)

**Goal:** Register a canary for every current fail-closed detector gate with a falsifier fixture, sourcing from the Phase 1 corpus where an incident exists and from `scripts/tests/` falsifier fixtures otherwise — the totality contract, with the remaining gap named.

**Requirements:** R30

**Dependencies:** U2, U3, U4

**Files:**
- `ci-corpus/canaries.yaml` (edit)
- `ci-corpus/constraint/`, `ci-corpus/board/`, `ci-corpus/workflow/`, `ci-corpus/test/` (new seed/pristine pairs as needed)
- `scripts/tests/` (edit only when a fixture must be promoted to a committed seed)

**Approach:** Walk the ci-gate inventory; for each gate, find a Phase 1 incident seed already registered for it (referenced, not duplicated — deduplicated per gate), else a falsifier fixture in `scripts/tests/` that demonstrates a fail case, else construct a minimal seed from the gate's documented defect class. Register each canary with the invocation flags CI uses; directory-scanning gates use the per-incident temp-directory layout from U1/U2. For advisory gates, record status `advisory` with the canary still registered where one exists. First release covers the fail-closed detector gates with existing falsifier fixtures (24 of 51 today); every other ci-gate entry carries the explicit triage record from U4. Justified retirement: when a gate legitimately stops rejecting a registered seed (a fix makes the seed's defect class impossible, or the gate's scope legitimately narrows), the seed is retired with a recorded reason in the manifest — mirroring R42's declared-equivalent-with-justification discipline — rather than left failing liveness forever or silently dropped.

**Patterns to follow:** the synthetic-fixture pattern of `scripts/tests/test_check_vacuous_gates.py`; the documented fail-closed proofs in `docs/evidence/2026-07-27-gate-subset-blindness-audit.md`; R42's declared-equivalent-with-justification discipline (`docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md`).

**Test scenarios:**
1. Every fail-closed detector gate with a falsifier fixture in the inventory has exactly one canary entry; the coverage check reports full coverage.
2. For a sample gate per domain (board, netlist, workflow, validator, manifest), the shared runner reports PASS.
3. The coverage check passes after population (exit 0; covered fail-closed gate count equals canary count, gap entries named by triage).
4. A Phase 1 seed reused as a canary is referenced once and executed once; no double-registration.
5. A retired canary carries a recorded reason and drops out of the liveness denominator without failing the run; an unrecorded removal fails coverage.

**Verification:** The shared runner exits 0 on the populated registry with full coverage; the liveness report names every gate checked.

### U6. CI wiring and registration rule

**Goal:** Wire the shared runner's two phases into CI and make registration structurally mandatory for new gates and new incidents.

**Requirements:** R19, R30

**Dependencies:** U2, U3, U5

**Files:**
- `.github/workflows/python-tests.yml` (edit: one step in the consistency-gates job running both phases of the shared runner)
- `.github/required-checks.json` (edit: add the new scripts, their tests, and `ci-corpus/**` to `trigger_paths`)
- `.github/workflows/python-tests.yml` path lists (edit: both push and pull_request copies, per the drift convention)
- `scripts/manifest.yaml` (edit: entries for `scripts/check_incident_corpus.py` and any new test-inventory script with `disposition: ci-gate`)

**Approach:** Add a gate step after the consistency-gates setup barrier that runs the shared runner once per phase — Phase 1 against `ci-corpus/incidents.yaml`, Phase 2 against `ci-corpus/canaries.yaml` — reporting a denominator per phase; never `continue-on-error`. Add `ci-corpus/**`, the runner, and its tests to all three trigger-path copies (push, pull_request, manifest) so the existing three-way drift check stays green. Populate the manifest entries' `imports` via `scripts/trace_invocations.py`. The registration rules are enforced structurally: `scripts/check_manifest_gate.py` already requires a manifest entry for every new script; the U4 coverage check extends that to require a canaries entry for every ci-gate entry; U1's schema validation requires a resolvable seed for every registered incident. Advisory-gate reality: while branch protection on `main` is disabled (`docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md`), all gates including this one remain advisory — this plan's step still never carries `continue-on-error`, and the bite the gates will eventually enforce depends on protection being enabled.

**Patterns to follow:** the setup-barrier/independent-gate-step pattern documented in `.github/workflows/python-tests.yml`; the never-`continue-on-error` rule for fail-closed gates; the manifest entry requirement from AGENTS.md; the actionlint convention for workflow edits.

**Test scenarios:**
1. Workflow lint: the edited `python-tests.yml` passes actionlint with no new warnings (run locally per AGENTS.md: `SHELLCHECK_OPTS='--severity=error' actionlint -ignore 'constant expression "false" in condition'`).
2. Manifest gate: `scripts/check_manifest_gate.py` exits 0 with the new entries present.
3. Trigger drift: the `validate_trigger_manifest` check in `scripts/check_required_checks.py` passes with all three path copies updated identically (covered by `test_workflow_trigger_lists_match_manifest`).
4. Gate isolation: with the runner failing on a deliberately-broken seed, the step reports failure but later steps in the job still run.
5. Adding a new ci-gate script without a canary entry fails the Phase 2 coverage check; adding both together passes.
6. Registering a new incident without an `incidents.yaml` entry (or with an unresolvable seed) fails the Phase 1 check.
7. The step reports each phase's denominator independently — Phase 2 still reports its own count when Phase 1 has UNVERIFIED entries (pristine pending).

**Verification:** CI runs both phases of the shared runner and reports their denominators; the three-way trigger/manifest drift check stays green after the path additions; the structural rules block a gate without a canary and an incident without a seed.

---

## Verification Contract

- Unit suite: `uv run pytest scripts/tests/test_check_incident_corpus.py scripts/tests/test_canary_inventory.py -v --tb=short`.
- Gate self-check: `uv run python scripts/check_incident_corpus.py --manifest ci-corpus/incidents.yaml` and `uv run python scripts/check_incident_corpus.py --manifest ci-corpus/canaries.yaml` both report their denominator and all-PASS on the populated corpus/registry.
- Falsifier: revert one seed per class to its pristine state; the gate must flip exactly that incident to FAIL. Remove one canary entry; the coverage check fails. Weaken one fixture gate; liveness fails with the regression verdict.
- CI integration: the step runs on a PR touching `ci-corpus/**` or the runner, and reports independently of sibling gates.
- Workflow lint: actionlint passes on the edited workflow; the required-checks drift checks stay green.

---

## Definition of Done

- `ci-corpus/incidents.yaml` exists with at least one entry per artifact class (board, constraint, workflow, test), each with seed, pristine, expected gate, and evidence doc; directory-scanning entries record their temp-directory layout and invocation flags.
- `scripts/check_incident_corpus.py` passes its unit suite, fails closed on an empty corpus and an empty canary set, and serves both phases from one runner.
- The full first-tranche corpus run is all-PASS (or UNVERIFIED with a recorded reason) on the current tree.
- `ci-corpus/canaries.yaml` covers every fail-closed detector gate with a falsifier fixture in `scripts/manifest.yaml`; the remaining ci-gate entries carry explicit triage records naming the coverage gap.
- The shared runner passes for the whole registry; a new ci-gate without a canary fails coverage; a new incident without a seed fails Phase 1; a retired seed carries a recorded reason.
- The step is wired into `python-tests.yml` with all three trigger-path copies updated and drift-checked; it never carries `continue-on-error`.
- `scripts/manifest.yaml` has entries for the new scripts with populated imports and `disposition: ci-gate`.
- No launch-blocking open question remains; execution-time unknowns (exact fixture geometry for each board-class seed) are deferred to implementation.

---

## Scope Boundaries

- In scope: the corpus structure, the shared runner, the history tranche (Phase 1), the canary registry and gate inventory extraction (Phase 2 coverage contract), the totality population, CI wiring, the registration rules, and justified seed retirement.
- Out of scope: automatic generation of mutations or canaries (R42 owns gate mutation); closed-set trigger-path verification (R31); branch-protection enablement (a repo-settings decision recorded in `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md`).
- The corpus does not define new gates; it re-encodes what existing gates must already reject.

### Deferred to Follow-Up Work

- Encoding the remaining evidence docs beyond the first tranche; the manifest schema supports incremental growth.
- A pristine counterpart for still-unfixed defects (C1↔R7 short, tank capacitor), registered now as UNVERIFIED and completed when the fix lands.
- Canaries for advisory gates beyond recording their status, and for gates that are advisory today and later become fail-closed (the contract absorbs them automatically via the manifest disposition).
- The Phase 2 gap for ci-gate scripts without falsifier fixtures (24 of 51 today have `test_<name>.py`): triage entries name the gap at first release; canaries for those gates land as fixtures get promoted or incidents materialize.
- Enabling branch protection on `main` — the prerequisite for this gate (and all gates) to bite, recorded in `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md`.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` (R19, R30, R7, R8)
- `docs/evidence/2026-08-02-validation-portfolio-review.md` (verdicts, merge map 35 → 29, ground-truth corrections)
- `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md`
- `docs/evidence/2026-07-27-gate-subset-blindness-audit.md`
- `docs/evidence/2026-07-27-vacuous-aggregation-audit.md`
- `docs/evidence/2026-07-28-tank-cap-placement.md`
- `docs/solutions/logic-errors/` (weak-nooverlap2d, unsound-atmostk, endpoint-bounding, courtyard-check-stage-finds-zero-collisions)
- `docs/solutions/best-practices/a-rule-that-matches-nothing-reads-as-coverage-2026-07-28.md`
- `docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md` (R42 — the declared-equivalent-with-justification discipline this plan's retirement rule mirrors)
- `scripts/check_vacuous_gates.py`, `scripts/tests/test_check_vacuous_gates.py`
- `scripts/check_workflow_pr_triggers.py`
- `scripts/manifest.yaml`
