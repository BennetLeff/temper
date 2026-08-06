---
title: DRC Ceiling as Monotone Contract - Plan
type: feat
date: 2026-08-02
topic: drc-ceiling-monotone-contract
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R27)
---

# DRC Ceiling as Monotone Contract - Plan

## Goal Capsule

**Objective:** formalize the `drc_ceiling.json` raise rule — an attributed cause plus a measured sample — as a machine-checked contract in the existing approval gate, so a raise without either fails CI.

**Product authority:** temper-placer and board maintainer (single-maintainer project).

**Open blockers:** none.

---

## Product Contract

### Summary

Today "Ceiling-Approval:" is a free-text commit trailer; any commit containing the string passes the approval gate. The contract makes a raise require two checkable artifacts in the same PR: a structured approval trailer naming the attributed cause, and a fresh measured-live provenance record satisfying the 120-sample all-track-errors contract.

### Problem Frame

The re-measurement convention is documented in AGENTS.md and in the ceiling file's own `_march` log, but the approval gate checks only a substring. A raise that names no cause and cites no measurement passes if the string "Ceiling-Approval:" appears anywhere in a commit message. The 2026-07-30 cascade — three stale records in one day, a PR merged red while its provenance gate failed — is the incident class: the convention is a review convention, not a checked one.

### Requirements

- R27. **DRC ceiling as monotone contract** (Formal / Board / P1): `power_pcb_dataset/drc_ceiling.json` raises require an attributed cause and a measured sample, formalized as a checked contract rather than a review convention. Seed: `scripts/check_drc_ceiling_approval.py`. (verbatim from origin)
  - Success signal: a raise without an attributed cause, or without a measured sample satisfying the measurement contract, fails the approval gate — mechanically, not by review.

### Key Technical Decisions

- KTD1. **Approval stays a structured commit-message trailer, not a sidecar file** — the PR's own commits are the approval ledger, and the existing gate already reads them; the trailer gains a parseable body carrying the attributed cause.
- KTD2. **Measurement evidence is validated from the ceiling file's own provenance and `_march` record** — no new registry; the gate checks the new record's provenance block (measured-live, at least 120 samples, tool version, dirty=false) and a `_march` entry naming the cause.
- KTD3. **The checks live in the existing gate and DrcRatchet, not a new script** — a second checker with the same logic is the vacuous-gate class that `scripts/check_vacuous_gates.py` exists to catch.

### Assumptions

- A "measured sample" means the AGENTS.md contract: at least 120 samples of `temper_placer.validation._drc_api.run_drc` with `--all-track-errors`, recorded in `provenance.measured_via` and `nondeterministic_error_types`.
- "Attributed cause" means the `_march` entry (or the structured trailer) names the component or commit driving each per-type delta, per the existing `_march` convention.
- Existing `_march` entries without structured trailers are grandfathered; the contract applies to new raises.

---

## Implementation Units

### U1. Structured approval-trailer contract

**Goal:** the Ceiling-Approval trailer has a defined, parseable structure carrying the attributed cause, and DrcRatchet validates it.

**Requirements:** R27.

**Dependencies:** none.

**Files:** `packages/temper-placer/src/temper_placer/regression/drc_ratchet.py`, `packages/temper-placer/tests/regression/test_drc_ratchet_approval.py` (new).

**Approach:** Define the trailer grammar: the approval marker plus a body naming the cause and the per-type deltas it explains. Extend `detect_ceiling_raise` to parse the trailer and reject a raise whose trailer has no parseable cause. Keep backward tolerance for legacy trailer forms (assumption).

**Patterns to follow:** `detect_ceiling_raise`'s existing raise-detection logic; the exit-code contract documented in `scripts/check_drc_ceiling_approval.py`.

**Test scenarios:**
1. A raise with a well-formed trailer naming its cause passes approval.
2. A raise with the bare legacy string and no cause fails, with the reason naming the missing cause.
3. A raise with no trailer at all fails, as today.
4. A malformed trailer body fails with a parse error, not a silent pass.
5. A ceiling decrease with no trailer still passes (no approval needed for tightening).

**Verification:** the DrcRatchet unit tests cover every raise and approval combination, and the existing non-raise cases still pass.

### U2. Measurement-evidence validation

**Goal:** the approval gate verifies that a raise is backed by a fresh measured-live provenance record satisfying the measurement contract.

**Requirements:** R27.

**Dependencies:** U1.

**Files:** `scripts/check_drc_ceiling_approval.py`, `packages/temper-placer/src/temper_placer/regression/drc_ratchet.py`, `scripts/tests/test_check_drc_ceiling_approval.py` (extend).

**Approach:** When a raise is detected, the gate validates the new board record's provenance block: source is measured-live, `measured_at_commit` resolves, dirty is false, the tool version matches the measured contract, sample count is at least 120, and the input hash matches `pcb/temper.kicad_pcb`. A raise whose new record fails any of these is an unapproved raise.

**Patterns to follow:** the provenance schema in `scripts/_lib/measurement_provenance.py`; the input-freshness checks in `scripts/check_measurement_provenance.py`; the 120-sample convention in `power_pcb_dataset/drc_ceiling.json`'s provenance.

**Test scenarios:**
1. A raise with a fresh provenance record (measured-live, 120 samples, matching input hash) and a cause passes.
2. A raise whose new record has fewer than 120 samples fails, naming the sample count.
3. A raise whose provenance source is backfilled-historical fails the measurement-evidence check.
4. A raise whose input hash does not match `pcb/temper.kicad_pcb` fails (stale measurement).
5. A raise with valid provenance but no attributed cause still fails (the two requirements are independent).

**Verification:** the gate's unit tests exercise every evidence-failure shape, and the real record passes.

### U3. Contract-violation corpus

**Goal:** every contract violation shape has a failing test, so the contract is proven to bite.

**Requirements:** R27.

**Dependencies:** U1, U2.

**Files:** `packages/temper-placer/tests/regression/test_drc_ratchet_approval.py`, `scripts/tests/test_check_drc_ceiling_approval.py`.

**Approach:** Enumerate the violation matrix — raise without trailer, trailer without cause, raise without measurement evidence, measurement evidence without cause, stale provenance, under-sampled record — and assert each fails. Assert the compliant raise passes.

**Patterns to follow:** the anti-vacuity discipline of `scripts/check_vacuous_gates.py`; the existing DrcRatchet unit tests.

**Test scenarios:**
1. Each row of the violation matrix fails with the specific reason named.
2. The compliant row passes.
3. A run over the current committed record (no raise) passes without touching approval logic.

**Verification:** the corpus passes, and weakening any single contract check makes at least one corpus row fail.

### U4. Contract documentation and CI sync

**Goal:** the AGENTS.md convention text and the ceiling file's `_goal` header state the checked contract, and the gate runs in the same CI job it already runs in.

**Requirements:** R27.

**Dependencies:** U1, U2.

**Files:** `AGENTS.md` (Board Change → DRC Ceiling Re-measurement section), `power_pcb_dataset/drc_ceiling.json` (`_goal` header), `scripts/manifest.yaml` (verify the `check_drc_ceiling_approval.py` entry).

**Approach:** Update the convention text to say the approval trailer and measurement evidence are machine-checked. Update the `_goal` header to name the checked contract. Confirm the gate's CI wiring and manifest entry are current.

**Patterns to follow:** the existing AGENTS.md convention section; the `_march` log's prose discipline.

**Test scenarios:**
1. The documentation states the checked contract and does not contradict the gate's behavior.
2. The gate is invoked by the same CI job that guards the ceiling today.

**Verification:** the docs match the implemented checks; the CI job runs the updated gate.

---

## Verification Contract

- `uv run pytest packages/temper-placer/tests/regression/test_drc_ratchet_approval.py scripts/tests/test_check_drc_ceiling_approval.py` passes.
- `uv run python scripts/check_drc_ceiling_approval.py` passes on a no-raise PR and fails on each corpus violation.
- `uv run python scripts/import_linter_gate.py` passes.
- No new zero-coverage public functions in `temper_placer/` (contract code is exercised by tests).

---

## Definition of Done

- A raise requires an attributed cause and a measured sample; both are machine-checked by the existing gate.
- The contract-violation corpus proves every violation shape fails.
- AGENTS.md and the `_goal` header document the checked contract.
- No new scripts (the contract lives in the existing gate); the existing manifest entry is current.
- Dead-end or experimental code from implementation is removed from the diff.

---

## Scope Boundaries

- The contract applies to new raises; existing `_march` entries are grandfathered.
- The gate does not re-run DRC; it validates the evidence a raise claims.

### Deferred to Follow-Up Work

- Applying the same checked contract to `fab_ceiling.json` once R15 lands — the contract is artifact-generic.
- Branch-protection rollout that gives the gate merge-blocking authority — the 2026-07-30 cascade's durable fix, out of scope here.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` (R27)
- `scripts/check_drc_ceiling_approval.py` (seed gate)
- `packages/temper-placer/src/temper_placer/regression/drc_ratchet.py` (detect_ceiling_raise)
- `scripts/check_measurement_provenance.py` and `scripts/_lib/measurement_provenance.py` (provenance schema)
- `power_pcb_dataset/drc_ceiling.json` (`_goal`, `_march`, provenance conventions)
- `docs/evidence/2026-07-30-drc-ceiling-remeasurement-cascade.md` (incident class)
