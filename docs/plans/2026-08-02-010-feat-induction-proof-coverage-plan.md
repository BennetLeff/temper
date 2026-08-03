---
title: Induction-proof Coverage for Compute Crates - Plan
type: feat
date: 2026-08-02
topic: induction-proof-coverage
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R22)
---

# Induction-proof Coverage for Compute Crates - Plan

## Goal Capsule

**Objective:** The `VERIFICATION.md` induction convention extends until every crate with recursive or computational structure carries a proof or an explicit non-applicability note, enforced by a coverage register and a CI gate.

**Product authority:** temper-placer and firmware maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none.

---

## Product Contract

### Summary

The four crates that already carry induction proofs (temper-geometry, temper-thermal, temper-rust-router-core, temper-placer/temper-constraints) become the seeded members of a crate-coverage register. The register classifies every crate under `packages/` as proof-carried, structural-proof, non-applicability-noted, or gap. A checker gate fails on any gap. Coverage then grows until every compute crate is provable or explicitly noted, and stays complete as new crates land.

### Problem Frame

Induction proofs exist where the migration program wrote them, by wave, not by inventory. A compute crate that never received a proof is indistinguishable from one that did — nothing enumerates the crates, classifies them, or fails on a gap. The convention is a policy with no register and no bite. This idea makes "every compute crate is provable or noted" a checked property instead of an aspiration.

### Requirements

- R22. **Induction-proof coverage for compute crates** (Formal / Geometry / P2): the `VERIFICATION.md` induction convention extends until every crate with recursive or computational structure carries a proof or an explicit non-applicability note — four crates today, all compute crates eventually.
- **Success signal:** every crate under `packages/` with recursive or computational structure carries either a proof or an explicit non-applicability note, and a gate fails when any crate lacks one.

### Key Technical Decisions

- KTD1. **The register is a per-crate `VERIFICATION.md` plus a repo-level index.** Each crate owns its proof or non-applicability note in its own `VERIFICATION.md` (created if missing); `docs/verification/crate-verification-coverage.md` enumerates one row per crate with the classification and the owning file. Rationale: the per-crate file is the machine-checkable contract and the index is the human scannable summary.
- KTD2. **The classification rule reuses the Wave-4 program's R1e rule.** Recursive or computational structure requires an induction proof (base case + induction step, per the geometry convention's shape); data-only, pure-delegation, or tooling modules record a structural proof or an explicit non-applicability note instead. Rationale: one rule across both programs avoids a second, drifting definition.
- KTD3. **The gate is a new checker script, `scripts/check_crate_verification_coverage.py`.** It walks `packages/*/Cargo.toml` (plus the nested temper-constraints crate), requires an index row and an owning `VERIFICATION.md` entry per crate, and fails on gaps. Rationale: no existing gate inspects crate verification coverage; per the script-manifest convention it gets a `scripts/manifest.yaml` entry.
- KTD4. **Proofs are written into the owning crate's `VERIFICATION.md` following the geometry convention's shape**, not summarized in the index. Rationale: the index cites; the proof lives next to the code it verifies, matching the established convention.

### Assumptions

- "Four crates today" names temper-geometry, temper-thermal, temper-rust-router-core, and temper-placer/temper-constraints, matching the Wave-4 program plan's R1 gate set; all four have a `VERIFICATION.md` today.
- The starting gap set is confirmed by U1's inventory, not assumed: the register's initial classifications are derived from the actual crate list and current `VERIFICATION.md` contents.
- Crates that are pure build/derive scaffolding or have no runtime code at all qualify for a non-applicability note under KTD2.

---

## Implementation Units

### U1. Coverage register and inventory

**Goal:** Enumerate every crate under `packages/`, classify each as proof-carried, structural-proof, non-applicability-noted, or gap, and publish the register.

**Requirements:** R22

**Dependencies:** none

**Files:**
- New: `docs/verification/crate-verification-coverage.md`

**Approach:**
1. Enumerate all crate roots under `packages/` (including the nested `packages/temper-placer/temper-constraints`).
2. For each crate, classify it from its existing `VERIFICATION.md` content and its code shape: induction proof present, structural proof, non-applicability note, or gap.
3. Publish the register with one row per crate: crate path, classification, owning verification file, and gap status.
4. Record the four seeded crates with their existing proofs as the convention's exemplars.

**Patterns to follow:** the `VERIFICATION.md` shape in `packages/temper-geometry/VERIFICATION.md`; the Wave-4 program plan's R1e classification language; the script-manifest convention's category fields for the later gate.

**Test expectation:** none — this unit is documentation and inventory; verified by review of the register against the actual `packages/` listing and each crate's `VERIFICATION.md`.

**Verification:** The register's crate list matches the on-disk crate inventory exactly; every row carries a classification and a gap status; the four seeded crates are marked proof-carried.

### U2. Gap closure

**Goal:** Every crate classified as a gap in U1 gains either an induction proof or an explicit non-applicability note in its own `VERIFICATION.md`.

**Requirements:** R22

**Dependencies:** U1

**Files:**
- New or modified: `packages/<crate>/VERIFICATION.md` for each gap crate identified in U1

**Approach:**
1. For each gap crate with recursive or computational structure, write an induction proof following the geometry convention's shape: base case, induction step, and empirical verification (the crate's differential or property suites as the empirical anchor).
2. For each gap crate without such structure, write an explicit non-applicability note naming the reason (data-only, pure delegation, no runtime code).
3. Update the register's rows as each gap closes.
4. Leave crate source code untouched — proofs and notes are documentation only.

**Patterns to follow:** the base-case/induction-step/empirical-verification sections in `packages/temper-geometry/VERIFICATION.md`; the differential-suite citations (`test_*_rust_differential.py`) as the empirical anchor; the non-applicability phrasing style from the Wave-4 plan's R1e carve-out.

**Test scenarios:**
1. A compute crate with a differential suite (e.g. a kernel crate): its proof cites the differential suite as empirical verification and follows the base-case/induction-step shape.
2. A data-only crate: its non-applicability note names the reason and states no proof is required.
3. A gap crate with no code change: after U2, the register shows no gaps for any compute crate.
4. The four seeded crates' existing proofs are unchanged by this unit.

**Verification:** Every compute crate now has either a proof or a non-applicability note; the touched crates' existing test suites remain green (documentation-only change); the register shows zero gaps.

### U3. Enforcement gate

**Goal:** A checker fails when any crate lacks a register row or an owning `VERIFICATION.md` entry, including newly added crates.

**Requirements:** R22

**Dependencies:** U1, U2

**Files:**
- New: `scripts/check_crate_verification_coverage.py`
- Modify: `scripts/manifest.yaml` (entry for the new script)
- Modify: the CI workflow that hosts the formal-tier checks (add a step invoking the checker)

**Approach:**
1. Implement a checker that enumerates crates from `packages/`, requires each to have an index row in `docs/verification/crate-verification-coverage.md` and an owning `VERIFICATION.md` with either an induction-proof section or an explicit non-applicability note.
2. Make the checker fail on: a crate with no row, a compute crate with no proof or note, and a row whose classification does not match the owning file's content.
3. Add the checker to CI so a new crate or a removed proof fails the run.
4. Register the script in `scripts/manifest.yaml` per the script-manifest convention.

**Patterns to follow:** the parse-and-fail structure of existing check scripts (e.g. `scripts/check_drc_ceiling_approval.py`); the manifest entry format in `scripts/manifest.yaml`; the coverage-gate's allowlist-style explicit-state checking.

**Test scenarios:**
1. Full coverage (post-U2 register): the checker exits 0.
2. A compute crate with no `VERIFICATION.md`: the checker exits nonzero, naming the crate.
3. A crate whose `VERIFICATION.md` lacks both a proof section and a non-applicability note: the checker exits nonzero.
4. A data-only crate with a valid non-applicability note: the checker exits 0.
5. A newly added crate under `packages/` with no row: the checker exits nonzero — the register cannot go stale.

**Verification:** The checker passes on the post-U2 tree and fails on each gap scenario; the manifest entry is present; CI runs the checker and is green.

---

## Verification Contract

- `uv run python scripts/check_crate_verification_coverage.py` — exits 0 on full coverage, nonzero on each gap scenario.
- `uv run pytest` on the differential and property suites of any crate whose `VERIFICATION.md` is touched — unchanged and green (documentation-only).
- `make extensions-check` — untouched by this plan (no Rust source changes).
- `uv run python scripts/trace_invocations.py` — refresh the invocation graph after the manifest entry per the script-manifest convention.

---

## Definition of Done

- The register exists, matches the on-disk crate inventory, and shows zero gaps.
- Every compute crate carries a proof or an explicit non-applicability note in its own `VERIFICATION.md`.
- The checker fails on every gap scenario and passes on full coverage.
- The checker runs in CI and the manifest entry is committed.
- No crate source code changed; all existing suites green.

---

## Scope Boundaries

**In scope:** crates under `packages/` with runtime code, classified and covered.

**Deferred to Follow-Up Work**

- Proofs for non-Rust compute surfaces outside `packages/` (e.g. standalone scripts) — the register covers crates per R22's wording.
- Writing fresh differential suites to enable proofs for gap crates that lack empirical anchors — U2 cites existing suites; a crate with no suite gets its proof's empirical section marked as pending rather than fabricated.
- Extending the register to the firmware transition-table manifest — a different domain, owned by the firmware formal tier (R28/R29).

---

## Sources / Research

- `packages/temper-geometry/VERIFICATION.md` — the induction convention (seed) and the proof shape to follow.
- `packages/temper-thermal/VERIFICATION.md` and `packages/temper-rust-router-core/VERIFICATION.md` — sibling convention carriers.
- `packages/temper-placer/temper-constraints/VERIFICATION.md` — the fourth seeded crate.
- `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md` — the R1e classification rule and the "4 crates" baseline.
- `scripts/manifest.yaml` — the script-manifest convention for the new gate.
- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — the origin (R22).
