---
title: "Gate-Mutation Testing - Plan"
type: feat
date: 2026-08-02
topic: gate-mutation-testing
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R42)
---

# Gate-Mutation Testing - Plan

## Goal Capsule

**Objective:** Prove gates bite by mutating them: each gate in the inventory is weakened (threshold loosened, scope path removed, condition inverted) and its own canary must stop failing. A mutation the canary fails to detect is a surfaced gap, and the trust-the-trust layer runs in CI.

**Product authority:** temper-placer and firmware maintainer (single-maintainer project); the mutation suite is the injection-tier companion to R30's canary contract.

**Open blockers:** none; the first sweep will surface surviving mutations that need triage, which is the point, not a blocker.

---

## Product Contract

### Summary

The gate-mutation suite weakens each gate and asserts its canary flips from pass to fail. When weakening the gate leaves the canary green, the canary does not exercise the weakened behavior, and the mutation is reported as survived. The trust-the-trust layer proves gates bite, per gate and per mutation axis.

### Problem Frame

This idea exists for the trust-the-gate incident class: a gate is assumed to bite until a bug slips through — a threshold that never binds (`docs/solutions/best-practices/a-rule-that-matches-nothing-reads-as-coverage-2026-07-28.md`), a scope that silently excluded most of its universe (`docs/evidence/2026-07-27-gate-subset-blindness-audit.md`), a gate reporting zero violations because it scanned nothing. `check_vacuous_gates.py` catches syntactic vacuity; R42 proves behavioral bite by weakening the gate and requiring the canary to notice.

### Requirements

- R42. **Gate-mutation testing** (Injection / CI / P1): each gate is weakened (threshold loosened, path removed) and its own canary must fail — the trust-the-trust layer proves gates bite. Seed: the incident corpus of R19.
- **Success signal:** every fail-closed gate in the inventory has at least one registered mutation whose canary flips from pass to fail under the mutation; the mutation run reports per-(gate, mutation, canary) verdicts; a survived mutation fails the run and must be triaged (canary strengthened, or mutation declared equivalent with justification).

### Key Technical Decisions

- KTD1. Mutation axes are declarative and human-reviewable: threshold loosening, scope/path removal, condition inversion, and allowlist widening, each recorded in `ci-corpus/mutations.yaml` as a (gate, mutation, canary) triple. Rationale: a reviewer sees every weakening in the diff instead of trusting a blind generator.
- KTD2. Mutation application is mechanical where possible (an AST rewrite of numeric thresholds and scope globs) but the pairing to canaries is explicit in the manifest. Rationale: a mutation with no registered canary is a contract violation, tying this plan to R30.
- KTD3. The runner executes the mutated gate against the R19 corpus canary the same way CI invokes the gate (external process, exit-code verdict); the baseline must reject the seed and pass the pristine, and the mutated gate must fail to reject the seed. Rationale: otherwise the mutation survived, meaning the canary does not exercise the weakened behavior.
- KTD4. Survived mutations are surfaced, not silenced: the run fails and lists them, and each is resolved by strengthening the canary or declaring the mutation equivalent with a recorded justification. Rationale: a blanket allowlist would repeat the exact silent-coverage failure this suite exists to kill.
- KTD5. Mutations are applied to a copy of the gate script, never the committed file. Rationale: the suite must be side-effect free and safe to run in CI.

### Assumptions

- The suite depends on R19's incident corpus and R30's canary contract, both owned by the merged plan `2026-08-02-032` (Incident Corpus & Gate Canary Contract), for canaries and coverage; where that plan has not landed, the runner bootstraps from the falsifier fixtures in `scripts/tests/` so the mechanism is testable independently.
- Not every mutation axis applies to every gate; the manifest records the axes that apply, and a gate with zero applicable axes is noted rather than forced.
- Advisory gates (`continue-on-error`) are outside the must-bite requirement in the first release, matching R30's advisory carve-out.

---

## Implementation Units

### U1. Mutation manifest and mutation engine

**Goal:** Define the mutation manifest schema and implement the mechanical mutation engine for the declarative axes.

**Requirements:** R42

**Dependencies:** none (manifest schema defined here; canary shape from R19 U1)

**Files:**
- `ci-corpus/mutations.yaml` (new)
- `scripts/gate_mutate.py` (new)
- `scripts/tests/test_gate_mutate.py` (new)
- `scripts/manifest.yaml` (edit: entry for the new script)

**Approach:** `mutations.yaml` entries carry: gate script path, mutation id, axis (`threshold-loosen`, `scope-remove`, `condition-invert`, `allowlist-widen`), and the canary reference (gate, seed, pristine from the R19 corpus). The engine applies one mutation to a temp copy: threshold loosening via an AST rewrite of the gate's primary comparison thresholds, scope removal by dropping one glob from the gate's scope, condition inversion by negating one guard, allowlist widening by adding a wildcard entry. Output is the mutated copy at a temp path plus a machine-readable diff record, so the runner can report what changed.

**Patterns to follow:** the AST-rewrite approach of `scripts/check_vacuous_gates.py`; the synthetic-fixture pattern of `scripts/tests/test_check_vacuous_gates.py`.

**Test scenarios:**
1. Threshold-loosen: a gate with a 10.0 threshold produces a mutated copy carrying 100.0, and the diff record names the constant and its line.
2. Scope-remove: a gate with a two-glob scope produces a mutated copy missing one glob, and the diff record names it.
3. Condition-invert: a guard such as `if not items:` produces a mutated copy with the guard negated, and the diff record names the expression.
4. Allowlist-widen: a per-file allowlist gains a wildcard entry, and the diff record names it.
5. A mutation the engine cannot apply (no threshold found) is recorded as not-applicable, not silently skipped.
6. Mutated copies are written to a temp location and the committed gate files are byte-identical before and after a run.

**Verification:** The engine's diff record matches the applied mutation for each axis, and the committed gate files are byte-identical after a run.

### U2. Mutation runner (canary-flip oracle)

**Goal:** Implement `scripts/check_gate_mutations.py`, which for each (gate, mutation, canary) triple runs baseline and mutated and asserts the canary flips from pass to fail.

**Requirements:** R42

**Dependencies:** U1; R19 U2 runner semantics

**Files:**
- `scripts/check_gate_mutations.py` (new)
- `scripts/tests/test_check_gate_mutations.py` (new)
- `scripts/manifest.yaml` (edit: entry for the new script)

**Approach:** For each manifest triple: run the unmutated gate on the canary's seed (must reject) and pristine (must pass); then run the mutated copy on the seed. The mutation is KILLED when the mutated gate no longer rejects the seed (the canary flipped to fail). It SURVIVED when the mutated gate still rejects the seed (the canary cannot see the weakening) or when the baseline itself is already broken (reported UNVERIFIED). Any SURVIVED or UNVERIFIED verdict fails the run with per-triple messages; zero triples fail closed.

**Patterns to follow:** the external-process contract and verdict classes of the R19 corpus runner; the fail-closed zero-scan guard.

**Test scenarios:**
1. Killed: a fixture gate whose threshold the canary exercises — the threshold-loosen mutation flips the canary to fail, verdict KILLED, run passes.
2. Survived: a fixture gate with a threshold no seed exercises — the threshold-loosen mutation leaves the canary green, verdict SURVIVED, run fails naming the triple.
3. Scope-remove survived: a seed outside the dropped scope glob — the canary stays green, verdict SURVIVED (the gate-subset-blindness class, mechanized).
4. Baseline broken: the gate already accepts its seed before mutation — verdict UNVERIFIED, run fails.
5. Empty manifest: fail-closed.
6. A mutated copy that fails to run (syntax error from a bad mutation): verdict UNVERIFIED with the error, run fails.

**Verification:** The runner reports per-triple verdicts and a total (N triples, K killed, S survived, U unverified) on both pass and fail; each verdict class is observable from the unit suite.

### U3. Initial mutation sweep and triage

**Goal:** Run the mutation suite across the fail-closed gate inventory, strengthen canaries for survived mutations, and record the sweep's outcome.

**Requirements:** R42

**Dependencies:** U2; R30 U3 (canary population) and R19 U3 (corpus population) as the canary source

**Files:**
- `ci-corpus/mutations.yaml` (edit)
- `ci-corpus/` (new seed/pristine pairs added where a survived mutation shows a canary gap)
- `docs/evidence/` (new doc recording the sweep: per-gate mutation coverage and triage outcomes)

**Approach:** Enumerate the fail-closed ci-gate inventory, register the applicable mutation axes per gate, run the suite, and for each survived mutation either strengthen the canary by adding the R19 seed that encodes the weakened behavior, or declare the mutation equivalent with a recorded justification in the sweep evidence doc. The sweep's outcome is a measured statement of per-gate mutation coverage, not a claim that every axis is covered from day one.

**Patterns to follow:** the honest-measurement discipline of the `docs/evidence/` docs (report what the sweep found, including gaps); the attribution convention of the `_march` log in `power_pcb_dataset/drc_ceiling.json`.

**Test scenarios:**
1. Every registered triple's verdict is KILLED or explicitly justified after the sweep; the suite exits 0.
2. A survived mutation fixed by adding a seed: the new seed makes the canary flip, verdict becomes KILLED.
3. A declared-equivalent mutation is recorded with its justification and does not fail the run (an explicit declaration field, not an allowlist).
4. Re-running the suite after the sweep is deterministic (same verdicts, no order dependence).

**Verification:** The sweep doc records per-gate mutation coverage; the suite exits 0 with every triple KILLED or justified; the corpus grew only where a gap was demonstrated.

### U4. CI wiring

**Goal:** Wire the mutation suite into CI and keep it cheap enough to run per PR.

**Requirements:** R42

**Dependencies:** U2, U3

**Files:**
- `.github/workflows/python-tests.yml` (edit: new step in the consistency-gates job)
- `.github/required-checks.json` (edit: add the new scripts, their tests, and `ci-corpus/**` to `trigger_paths`)
- `.github/workflows/python-tests.yml` path lists (edit: both push and pull_request copies)
- `scripts/manifest.yaml` (edit: entries for both new scripts with `disposition: ci-gate`)

**Approach:** Run the mutation suite in the same job as the corpus and canary gates, which share setup. Because the suite re-executes each gate against seeds, run the registered triples per PR; if wall time is a concern, run a smoke subset (one mutation per gate) per PR and the full sweep on schedule — the split is a budget decision recorded at implementation. The step is never `continue-on-error`.

**Patterns to follow:** the independent-gate-step convention in `.github/workflows/python-tests.yml`; the actionlint convention for workflow edits.

**Test scenarios:**
1. Workflow lint: actionlint passes on the edited workflow.
2. The three-way trigger-path copies stay in sync after additions.
3. A known-surviving triple deliberately registered in `mutations.yaml` fails the CI step, proving the wiring.
4. The mutation step reports independently of sibling gates.

**Verification:** CI runs the mutation suite and fails on any SURVIVED or UNVERIFIED triple; the smoke subset completes within the job budget.

---

## Verification Contract

- Unit suite: `uv run pytest scripts/tests/test_gate_mutate.py scripts/tests/test_check_gate_mutations.py -v --tb=short`.
- Gate self-check: `uv run python scripts/check_gate_mutations.py` exits 0 with all registered triples KILLED or justified; the engine leaves committed gate files byte-identical.
- Falsifier: register a known-surviving triple and the run fails naming it; weaken a canary seed so the baseline breaks and the run fails with UNVERIFIED.
- CI integration: the mutation step runs on PRs touching `ci-corpus/**` or the runner and reports independently.
- Workflow lint: actionlint passes; the required-checks drift checks stay green.

---

## Definition of Done

- The mutation manifest covers every fail-closed ci-gate with its applicable axes.
- The runner reports per-triple verdicts and fails closed on empty input and on any survived or unverified triple.
- The initial sweep is complete and recorded in `docs/evidence/` with per-gate coverage and triage justifications.
- The suite is wired into CI, and a deliberately surviving triple is demonstrated to fail the CI step.
- `scripts/manifest.yaml` has entries for both new scripts with populated imports.
- No launch-blocking open question remains.

---

## Scope Boundaries

- In scope: gate mutation along the four declarative axes, canary-flip verification, the initial sweep, and CI wiring.
- Out of scope: mutating non-gate validation code (constraint mutation is R32; geometry-kernel mutation is R34); mutations not registered in the manifest (the human-reviewable manifest is the contract); mutating workflow trigger paths (R43 owns that axis for workflows).

### Deferred to Follow-Up Work

- Expanding mutation axes beyond the four (off-by-one thresholds, whole-function negation).
- Per-PR full-sweep budget tuning if the smoke subset proves insufficient.
- Mutation coverage targets per gate (e.g. "every gate kills at least its primary axis") as a ratchet, once the first sweep establishes the baseline.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` (R42, R32, R34)
- `docs/plans/2026-08-02-032-feat-incident-corpus-oracle-plan.md` (R19 + R30 — the incident corpus and canary contract)
- `docs/solutions/best-practices/a-rule-that-matches-nothing-reads-as-coverage-2026-07-28.md`
- `docs/evidence/2026-07-27-gate-subset-blindness-audit.md`
- `scripts/check_vacuous_gates.py` (AST patterns to mirror)
