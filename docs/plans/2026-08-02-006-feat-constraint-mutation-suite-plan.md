---
title: Constraint Mutation Suite - Plan
type: feat
date: 2026-08-02
topic: constraint-mutation-suite
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R32)
---

# Constraint Mutation Suite - Plan

## Goal Capsule

**Objective:** Each constraint encoding is mutated (sign flip, dropped term, loosened bound) and the mutation must fail the constraint's own tests or post-solve audit — every encoding carries its kill set.

**Product authority:** temper-placer maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none. Mutation-suite sizing per encoding is decided at implementation time, per the portfolio's deferred question for R32.

---

## Product Contract

### Summary

Every CP-SAT constraint encoding is mutation-tested: a plausible bug (sign flip, dropped term, loosened bound) is injected into the encoder, and the encoding's own tests or post-solve audit must catch it. Each encoding therefore carries a registered kill set — the mutations its defenses detect. A new encoding with an empty or weak kill set fails CI.

### Problem Frame

This idea exists for the gates-trusted-until-they-slip incident class: a constraint's tests pass because nobody checked whether they could fail. The unsound `atmostk` and `weak-nooverlap2d` encodings shipped with green suites that never exercised the broken semantics. Mutation testing inverts the question: instead of asking whether a test suite passes, it asks which plausible bugs the suite would catch. The R4 fail-capable rule in `docs/physics-verification-methodology.md` already names the bug classes; this plan turns that rule into a standing, gated suite.

### Requirements

- R32. **Constraint mutation suite** (Injection / Physics / P1): each constraint encoding is mutated (sign flip, dropped term, loosened bound) and the mutation must fail the constraint's own tests or post-solve audit — every encoding carries its kill set. Origin: `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` (R32; no named seed).
  - **Success signal:** every registered encoding has a non-empty kill set; each mutation operator is demonstrated to be killed by the encoding's own tests or the post-solve audit, and CI fails on any encoding whose kill set is empty.
  - **Covers portfolio flows:** F1 (pull-to-plan), via the success signal as acceptance criteria.

### Key Technical Decisions

- KTD1. Mutation operators are limited to the R4 fail-capable bug classes: sign flip, dropped term, loosened bound, off-by-one, and double-count. Rationale: strawman mutations (multiply by 1000, return zero) prove a checksum, not a domain guard; the R4 rule already forbids them and names the valid classes.
- KTD2. Kill detection uses the encoding's own existing defenses — encoder unit tests, PBT invariant tests, and the post-solve `PlacementAuditor`. Rationale: no new oracle is invented; the mutation suite measures the defenses that already exist, which is the point.
- KTD3. The kill set is registered per encoding in a machine-readable register, enforced by a gate in the `bmc_adoption_gate.py` shape. Rationale: a kill set that is not gated is a report, not a contract; the AST-scan gate pattern extends directly.
- KTD4. A surviving mutation is triaged, not silently accepted: it either gets a strengthened test or a documented benign classification. Rationale: survivors are the signal the suite exists to produce; an untriaged survivor is the old trust-the-tests failure mode in new clothes.

### Assumptions

- "Each constraint encoding" covers the 8 PCL handlers in `placer/cp_sat/handlers/` and the router-V6 topology encodings, matching the R21 plan's family split.
- Mutation applies to the encoder (the CP-SAT encoding logic), not to the constraint model or the auditor; the auditor is the referee.
- The suite runs in CI at a cadence where its runtime is acceptable; per-encoding sizing is proportional to encoding complexity per the portfolio's deferred question.
- The R20 register's surface inventory is the authority for which encodings exist; a surface missing from it is a gap for this suite too.

---

## Implementation Units

### U1. Mutation operator library and runner

**Goal:** Apply each R4 bug-class mutation to an encoder and classify the outcome (killed or survived).

**Requirements:** R32, KTD1, KTD2.

**Dependencies:** none.

**Files:**
- `scripts/constraint_mutation_runner.py` (new; requires a `scripts/manifest.yaml` entry)
- `packages/temper-placer/tests/pcl/test_mutation_runner.py` (new tests)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/handlers/` (mutation targets; read-only except where a defect is found)

**Approach:**
1. Implement mutation operators per the R4 classes: sign flip on an axis term, dropped disjunct or term, loosened bound (margin halved), off-by-one on a boundary, double-counted term.
2. Implement the runner: apply one mutation to a copy of an encoder, run the encoder's existing test set plus the post-solve auditor, and record killed or survived.
3. Each mutation carries its bug-class label so a survivor is attributable to a specific plausible defect.

**Patterns to follow:** the fail-capable test conventions in `docs/physics-verification-methodology.md` section 4; the `bmc_adoption_gate.py` scan structure for discovering encodings.

**Test scenarios:**
- A sign flip in the `SEPARATED` x-axis term is killed by the existing encoder tests.
- A dropped `y_ok` disjunct in `SEPARATED` is killed by the auditor (the weak-nooverlap2d class).
- A loosened `min_distance_mm` bound (halved) is killed by the auditor.
- An off-by-one in `ENCLOSING`'s margin comparison is killed.
- The runner classifies a mutation as survived when no existing defense catches it.
- Strawman mutations (multiply output by 1000) are rejected by the runner as invalid operators.

**Verification:** the runner produces a per-encoding, per-mutation killed/survived classification with bug-class labels.

### U2. Kill-set register

**Goal:** Register each encoding's kill set and its survivors.

**Requirements:** R32, KTD3, KTD4.

**Dependencies:** U1.

**Files:**
- `power_pcb_dataset/constraint_kill_sets.yaml` (new register)
- `packages/temper-placer/tests/pcl/test_mutation_register.py` (new tests)

**Approach:**
1. Define the schema: per-encoding entry with applied mutations, killed set, surviving set, and triage status per survivor.
2. Run the initial suite across all PCL handlers and the router-V6 encodings; populate the register from the results.
3. Record for each survivor whether it is benign (documented with rationale) or a test-strengthening TODO.

**Patterns to follow:** the provenance and march-log conventions of `power_pcb_dataset/drc_ceiling.json`.

**Test scenarios:**
- Every registered encoding has a non-empty killed set.
- A survivor marked benign carries a one-line rationale naming the mutation and why it is acceptable.
- A survivor marked as a test gap carries a TODO reference.
- The register parses and every entry resolves to a real handler or constraint class.

**Verification:** the register is populated, parseable, and every encoding has a recorded kill set.

### U3. Mutation gate

**Goal:** Fail CI when an encoding has an empty kill set or a new encoding ships without a kill-set entry.

**Requirements:** R32, KTD3, KTD4.

**Dependencies:** U2.

**Files:**
- `scripts/constraint_mutation_gate.py` (new; requires a `scripts/manifest.yaml` entry)
- `scripts/manifest.yaml` (entry)
- `.github/workflows/python-tests.yml` (gate wiring)
- `packages/temper-placer/tests/pcl/test_mutation_gate.py` (new tests)

**Approach:**
1. AST-scan the encoder surfaces (handlers plus router-V6 constraint classes) and require a kill-set register entry for each, mirroring the `bmc_adoption_gate.py` shape.
2. Require a non-empty killed set per entry; exit non-zero naming the encodings with empty kill sets or missing entries.
3. Wire the gate into CI alongside the existing adoption gates.

**Patterns to follow:** the `bmc_adoption_gate.py` scan-and-report structure; the import-linter gate exit codes.

**Test scenarios:**
- A new handler without a kill-set entry fails the gate with the handler named.
- An entry whose killed set is empty fails the gate.
- Registering a non-empty kill set clears the failure.
- A survivor without triage status fails the gate (no untriaged survivors).
- The gate exits 0 on the fully populated register.

**Verification:** the gate is green on the current tree and red on a synthetic unregistered or empty-kill-set encoding.

### U4. Survivor triage and suite maintenance

**Goal:** Close or justify every surviving mutation and keep the suite cheap to run.

**Requirements:** R32, KTD4.

**Dependencies:** U3.

**Files:**
- `packages/temper-placer/tests/pcl/` (strengthened tests for triaged survivors)
- `power_pcb_dataset/constraint_kill_sets.yaml` (triage status updates)
- `docs/physics-verification-methodology.md` (document the standing suite)

**Approach:**
1. For each survivor marked a test gap, add the specific test that kills the mutation (encoder-level or auditor-level).
2. For each survivor marked benign, keep the rationale in the register; no code change.
3. Document the suite and its cadence in the methodology doc so it reads as a standing check, not a one-off.

**Patterns to follow:** the fail-capable scenario conventions from the methodology doc's worked table.

**Test scenarios:**
- A previously surviving dropped-term mutation is killed after its test is added.
- A benign survivor's rationale remains accurate after an unrelated encoder change (no false confidence).
- Re-running the full suite after the triage shows zero untriaged survivors.

**Verification:** the register has no untriaged survivors and the suite is documented.

---

## Verification Contract

- Unit tests: `uv run pytest packages/temper-placer/tests/pcl/ packages/temper-placer/tests/placer/cp_sat/ -q` from `packages/temper-placer/`.
- Mutation gate: `uv run python scripts/constraint_mutation_gate.py` at repo root; must exit 0.
- Import boundary gate: `uv run python scripts/import_linter_gate.py`.
- Script manifest: new scripts require entries in `scripts/manifest.yaml`; refresh with `uv run python scripts/trace_invocations.py`.
- Coverage gate: new public functions in `temper_placer` need tests or an allowlist entry (run per the standard `--cov` invocation from `packages/temper-placer/`).

---

## Definition of Done

- Every registered encoding has a non-empty, triaged kill set.
- The mutation gate fails on empty or missing kill sets and on untriaged survivors.
- Each R4 bug-class operator is demonstrated killed on at least one encoding.
- The suite and register are documented in the methodology doc.
- Abandoned experimental mutation code is removed before the branch is complete.

---

## Scope Boundaries

- **In scope:** mutation operators, runner, kill-set register, gate, survivor triage.
- **Out of scope:** mutating the post-solve auditor or the constraint model (the auditor is the referee); geometry-kernel mutation (the portfolio's R34 owns that); writer-error injection (R35).

### Deferred to Follow-Up Work

- Extending the suite to geometry kernels and the placement writer (R34, R35 in the portfolio).
- Full mutation coverage metrics (mutation score thresholds) once the initial kill sets are stable.
- Applying the same suite shape to firmware codegen once the placer suite is proven.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — origin (R32) and deferred-sizing question.
- `docs/physics-verification-methodology.md` — the R4 fail-capable rule that defines the valid bug classes.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/handlers/separated.py` — the worked encoder example whose docstring documents the soundness the suite probes.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/audit.py` — the post-solve auditor used as kill referee.
- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — the incident class and its dropped-term/single-clause failure shape.
- `scripts/bmc_adoption_gate.py` — the gate shape KTD3 follows.
