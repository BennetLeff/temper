---
title: Quality vs Human Oracle - Plan
type: feat
date: 2026-08-02
topic: quality-vs-human-oracle
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R13)
---

# Quality vs Human Oracle - Plan

## Goal Capsule

**Objective:** Compare extracted human reference layouts against solver output on functional-grouping and symmetry criteria, so layout quality is measured against a human baseline instead of self-scored.

**Product authority:** temper-placer maintainer (single-maintainer project; this plan is pulled from the portfolio menu, not scheduled).

**Open blockers:** none. The divergence threshold per criterion is a measured-at-pull-time quantity (origin Outstanding Questions, "Per-idea oracle divergence thresholds — measured at pull time"); this plan measures it on the corpus boards as its own unit.

---

## Product Contract

### Summary

Human-designed boards in `power_pcb_dataset/corpus/` are the quality baseline. Their extracted layouts are scored on functional-grouping and symmetry criteria. Solver placements are scored on the same criteria with the same metric functions. A comparison layer reports the delta and fails when solver quality diverges beyond a measured tolerance. Quality claims become differential against a human, never self-referential.

### Problem Frame

Quality metrics that only ever score the solver's own output can pass a bad placement that a human would reject. The failure class is self-scoring: the metric and the placement share the same assumptions, so drift in either is invisible. A human reference breaks the loop by supplying an independent quality baseline on the same board.

### Requirements

- R13. Extracted human reference layouts are compared against solver output on functional-grouping and symmetry criteria — layout quality is measured against a human baseline, not self-scored.
  - **Success signal:** a solver placement whose grouping or symmetry score falls outside the measured divergence band from the human reference on the same board fails the run, and the comparison is produced by a standing check.

### Key Technical Decisions

- KTD1. **One metric core for both sides.** The extractor and the solver-side evaluator call the same metric functions (`validation.metrics.compute_metrics` and the `temper-quality-oracle` Rust crate) so a delta reflects placement difference, not metric difference. Rationale: differing metric implementations would make the comparison uninterpretable, exactly the "apples-to-oranges oracle" anti-pattern in `docs/physics-verification-methodology.md` §3.
- KTD2. **Symmetry is measured, not mandated.** The symmetry criterion is a mirror-pair residual derived from the human layout's own structure (left-right and top-bottom mirror pairs), and the same computation runs on solver output. Rationale: the check compares how symmetric each layout is; it does not require the solver to be symmetric.
- KTD3. **Thresholds measured, not specified.** Each criterion's divergence tolerance is measured from the corpus boards and pinned with provenance, matching the origin's deferred-to-pull-time threshold convention.

### Assumptions

- A1. `power_pcb_dataset/corpus/temper/` is the primary reference board; `piantor_right`, `rp2040_designguide`, and `bitaxe_ultra` are secondary corpus subjects.
- A2. The extractor seed (`validation/human_reference_extractor.py`) exists and currently extracts placement, routing, detailed, aesthetic, quality, and DRC metrics — but it does not yet compute the functional-grouping and symmetry criteria this plan adds. That gap is the work of U1, not a blocker.
- A3. Functional-grouping is operationalized as the per-net connectivity clustering family already present in the quality stack (`connectivity_clustering_score` in the `temper-quality-oracle` crate), plus a per-functional-group scatter measure derived from the design's net classes and zone assignments.
- A4. The divergence band is a per-criterion tolerance on the corpus boards, measured with the same sample discipline the DRC ceiling convention documents in AGENTS.md.

---

## Implementation Units

### U1. Grouping and symmetry extraction in the human reference

**Goal:** Extend `validation/human_reference_extractor.py` so each extracted human reference carries functional-grouping and symmetry criteria alongside the existing metrics.

**Requirements:** R13

**Dependencies:** none

**Files:**
- `packages/temper-placer/src/temper_placer/validation/human_reference_extractor.py`
- `packages/temper-placer/src/temper_placer/metrics/grouping.py` (new)
- `packages/temper-placer/src/temper_placer/metrics/symmetry.py` (new)
- `packages/temper-placer/tests/validation/test_human_reference_extractor.py`
- `packages/temper-placer/tests/metrics/test_grouping_symmetry.py` (new)

**Approach:** Add two metric families to the extraction chain, each returning `MetricValue` records with the same provenance the file already writes. Grouping computes per-net clustering and per-functional-group scatter from the parsed netlist and zone assignments. Symmetry detects mirror pairs from the human layout (footprint-symmetric refs at mirrored coordinates about board mid-X and mid-Y) and reports per-pair residual error plus a layout-level symmetry score. Both families reuse the existing parse → `PlacementState` → metrics pipeline; failures raise loudly per the file's no-swallowed-exception rule.

**Patterns to follow:** The existing step functions (`_compute_placement_metrics`, `_compute_quality_metrics`) for structure and provenance; `validation/metrics.py` and the `temper-quality-oracle` crate for metric definitions.

**Test scenarios:**
1. Happy path — `extract_human_reference` on `power_pcb_dataset/corpus/temper/temper.kicad_pcb` returns grouping and symmetry keys with finite, non-negative values.
2. Edge case — a board with a single component yields a degenerate-but-valid grouping score (no division by zero), matching the `connectivity_clustering_score` empty-net convention.
3. Edge case — a board with no detectable mirror pairs yields a symmetry score of 1.0 (perfect by vacuity) with an explicit `mirror_pair_count: 0` marker, so a reviewer can see no pairs were found.
4. Error path — a netlist whose group references do not resolve raises, following the extractor's validate-mode assertion pattern rather than recording a sentinel.
5. Round-trip — the new metrics survive `HumanReference.save()` and reload with `extracted_at` and `pcb_git_hash` populated.

**Verification:** The corpus extraction tests pass with the new keys present, and a crafted placement with one component moved away from its group moves the grouping score in the expected direction in the metric unit tests.

### U2. Solver-side grouping and symmetry evaluation

**Goal:** Compute the identical grouping and symmetry criteria on a solver-produced placement so the comparison is side-by-side.

**Requirements:** R13

**Dependencies:** U1

**Files:**
- `packages/temper-placer/src/temper_placer/validation/quality_oracle_compare.py` (new)
- `packages/temper-placer/tests/validation/test_quality_oracle_compare.py` (new)

**Approach:** Build a comparison entry point that takes a solver placement (positions, rotations, sizes in mm) plus the parsed board, runs the same grouping and symmetry functions U1 defines, and returns a per-criterion value set. The solver placement is normalized the same way the extractor normalizes human positions (board-space coordinates via `io/reference_loader.netlist_to_placement_state`), so both sides measure the same quantity.

**Patterns to follow:** The reference-loader comparison infrastructure in `packages/temper-placer/src/temper_placer/io/reference_loader.py`; the `PlacementState` construction in `human_reference_extractor._build_state_and_context`.

**Test scenarios:**
1. Happy path — a solver placement that is the human placement verbatim yields a zero delta on every criterion.
2. Integration — a solver placement from a real solve (via the corpus constraints) produces a finite, complete criterion set with no exception.
3. Edge case — a placement missing a component ref is rejected with a named error, not silently scored over a partial set.
4. Consistency — applying U1's extraction to the same coordinates produces identical criterion values (the two entry points share the metric core, per KTD1).

**Verification:** The verbatim-copy test passes, proving the two sides measure the same thing.

### U3. Comparison gate with measured divergence band

**Goal:** Turn the per-criterion delta into a standing check that fails when solver quality diverges beyond a measured band from the human baseline.

**Requirements:** R13

**Dependencies:** U2

**Files:**
- `packages/temper-placer/src/temper_placer/validation/human_baseline_compare.py` (new)
- `packages/temper-placer/tests/validation/test_human_baseline_compare.py` (new)
- `power_pcb_dataset/human_quality_bands.json` (new)

**Approach:** Measure the per-criterion divergence band from the corpus boards: extract each human reference, run U2's evaluator on that same placement, and record the observed run-to-run band per criterion with provenance (board, extractor version, git hash), following the `drc_ceiling.json` provenance convention. The gate then compares a solver placement's criteria against the stored human reference and fails on any criterion outside the band. The band file is the single source of truth; a rise requires an attributed cause, mirroring the DRC-ceiling discipline.

**Patterns to follow:** The provenance + attribution discipline of `power_pcb_dataset/drc_ceiling.json` and `scripts/check_drc_ceiling_approval.py`; the fail-closed verdict style of `validation/validation_gates.py`.

**Test scenarios:**
1. Happy path — a solver placement within the band passes with a per-criterion delta report.
2. Fail path — a placement with one component moved far from its group fails with the grouping criterion named and the delta quantified.
3. Fail path — a placement whose mirror-pair residual is far worse than the human reference fails the symmetry criterion.
4. Edge case — a criterion with no measured band yet reports `UNMEASURED`, never a silent pass (the fail-closed discipline from `docs/physics-verification-methodology.md` §5).
5. Edge case — the human reference for the target board is missing; the gate fails closed with a named error.

**Verification:** A deliberately degraded placement fails the gate, and a verbatim human placement passes, proving the check bites in both directions.

---

## Verification Contract

The comparison gate runs as part of the placer validation suite in CI, extending the existing `checks` job in `.github/workflows/python-tests.yml` rather than adding a parallel workflow. The unit suites for grouping, symmetry, extraction, and comparison run under the existing pytest configuration in `packages/temper-placer/`. New public functions in `temper_placer/` must clear the coverage gate (`.coverage-allowlist`); new metric modules are not in the permanent `omit` list and therefore need coverage. No new `scripts/*.py` is introduced, so no `scripts/manifest.yaml` entry is required by this plan.

---

## Definition of Done

- The human reference for the temper board carries grouping and symmetry criteria (U1).
- A solver placement is scored on the same criteria with the same metric core (U2).
- The comparison gate fails a placement outside the measured band and reports `UNMEASURED` for unmeasured criteria (U3).
- The divergence band is recorded in `power_pcb_dataset/human_quality_bands.json` with provenance (U3).
- All new public functions in `temper_placer/` have executed-line coverage.
- The corpus extraction tests and the new comparison tests pass under the standard pytest run.

---

## Scope Boundaries

**In scope:** grouping and symmetry criteria on both extraction sides; the comparison gate; the measured divergence band for the corpus boards.

**Out of scope:** new metric families beyond grouping and symmetry; routing-quality criteria (the extractor already records routing metrics, but they are not re-scored here); changes to the human-designed boards themselves.

### Deferred to Follow-Up Work

- Extending the divergence band to boards outside the current corpus.
- A symmetry-requirement mode that mandates mirror symmetry in solver output — the check stays measurement-only per KTD2.
- Cross-criterion weighting into a single quality verdict.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — the portfolio origin (R13, Key Decisions D1–D6, Key Flow F1).
- `packages/temper-placer/src/temper_placer/validation/human_reference_extractor.py` — the seed; extraction chain and provenance pattern.
- `packages/temper-placer/src/temper_placer/io/reference_loader.py` — reference-design normalization and quality-config inference.
- `packages/temper-quality-oracle/` — canonical quality evaluator (`connectivity_clustering_score`, `evaluate_quality_py`).
- `packages/temper-placer/src/temper_placer/validation/metrics.py` — the shared placement-metric core.
- `docs/physics-verification-methodology.md` — independent-oracle rule (§3) and fail-closed discipline (§5).
- `power_pcb_dataset/drc_ceiling.json` — the provenance-and-attribution pattern the divergence band mirrors.
