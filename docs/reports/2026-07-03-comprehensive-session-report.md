---
title: "Session Report: CP-SAT Feasibility-First Placer — End-to-End Delivery"
date: 2026-07-03
branch: feat/cp-sat-feasibility-first-placer
pr: https://github.com/BennetLeff/temper/pull/121
---

# Session Report: CP-SAT Feasibility-First Placer

## Overview

One continuous session delivered the complete CP-SAT feasibility-first placer
pipeline: plan review, implementation, parity testing, JAX retirement
brainstorming, calendar-gate planning, partial implementation, and CI cleanup.
16 commits pushed to PR [#121](https://github.com/BennetLeff/temper/pull/121).

## Timeline

| # | Phase | Skill | Outcome |
|---|-------|-------|---------|
| 1 | Worktree setup | ce-worktree | Branch `feat/cp-sat-feasibility-first-placer` from `main` |
| 2 | Plan review | ce-doc-review | 5 personas, 20 findings, 11 fixes applied |
| 3 | Implementation | ce-work | U0-U8 completed, 86 tests passing |
| 4 | Parity testing | — | Feasibility 0.1s, with-objective 60s, 652/652 audit |
| 5 | Report | — | Implementation report with feasibility validation |
| 6 | Compound | ce-compound | 3 learnings documented in `docs/solutions/` |
| 7 | Refresh | ce-compound-refresh | C-CAP doc marked `superseded` |
| 8 | Brainstorm | ce-brainstorm | Calendar-gate JAX retirement requirements (23 review fixes) |
| 9 | Doc review | ce-doc-review | 23 findings, 23 fixes applied |
| 10 | Plan | ce-plan | Calendar-gate implementation plan (6 units) |
| 11 | Implementation | ce-work | U1-U5 (frozen receipt, quality gaps, parity retirement, JAX deletion) |
| 12 | CI fix | — | Removed `tests/losses/` from CI, added CP-SAT test step |

## Deliverables

### Source Code

| Module | Lines | Tests | Description |
|--------|-------|-------|-------------|
| `placer/cp_sat/model.py` | 365 | — | CP-SAT model builder + 5 constraint helpers + solver |
| `placer/cp_sat/encoder.py` | 380 | 26 | PCL→CP-SAT handler dispatch, 5 type handlers, assumption vars |
| `placer/cp_sat/audit.py` | 553 | 33 | Post-solve constraint audit (5 checks, unconditional) |
| `placer/cp_sat/unsat.py` | 265 | 13 | UNSAT core extraction + MUS refinement |
| `metrics/external_oracle.py` | 173 | 8 | `score_placement()` adapter |
| `regression/cp_sat_comparison.py` | 160 | — | Extracted `MetricComparison`/`ParityComparisonResult` primitives |
| **Total new** | **~1,900** | **80** | |

### Modified Files

| File | Change |
|------|--------|
| `cli/__init__.py` | `--placer cp-sat` flag + inline dispatch (later: jax-deprecated no-op) |
| `core/state.py` | `PlacementState.from_positions_dict()` factory |
| `pcl/constraints.py` | `CompilationTarget.CP_SAT` enum + frozenset updates |
| `pyproject.toml` | `ortools>=9.12` + `cp_sat` pytest marker |
| `configs/pcl/temper_induction.yaml` | OnSideConstraint for Q1/Q2 (thermal-edge anchoring) |
| 22 surviving modules | `losses`/`optimizer` imports wrapped in try/except |

### Deletions

| Scope | Lines | Description |
|-------|-------|-------------|
| Source | 32,420 | `optimizer/`, `losses/`, `ablation/`, `loss_bridge.py`, `placement/` (5 files), `heuristics/force_directed.py` |
| Tests | 57,800 | ~50 JAX-dependent test files, 6 test directories |
| **Total deleted** | **90,220** | |

### Documentation

| Document | Lines | Description |
|----------|-------|-------------|
| `docs/plans/...cp-sat-feasibility-first-placer-plan.md` | 917 | Original plan with 11 review fixes |
| `docs/reports/...implementation-report.md` | 322 | Implementation report with feasibility validation |
| `docs/solutions/logic-errors/or-tools-sufficient-assumptions-proto-indices-...md` | 100 | OR-Tools API discovery |
| `docs/solutions/logic-errors/cp-sat-spread-variable-bounds-infeasible-...md` | 90 | Spread variable bounds fix |
| `docs/solutions/architecture-patterns/cp-sat-feasibility-first-paradigm-...md` | 160 | Feasibility-first performance paradigm |
| `docs/solutions/architecture-patterns/alternating-projections-...md` | +12 | C-CAP marked `superseded` |
| `docs/brainstorms/...calendar-gate-jax-retirement-requirements.md` | 200 | Calendar-gate requirements (23 review fixes) |
| `docs/plans/...calendar-gate-jax-retirement-plan.md` | 240 | Calendar-gate implementation plan (6 units) |
| `docs/evidence/cp-sat-jax-parity-2026-07-03.md` | 80 | Frozen parity receipt |
| `docs/reports/...comprehensive-session-report.md` | — | This report |

## Review Findings Summary

### Plan Review (ce-doc-review, round 1)

5 personas reviewed the CP-SAT implementation plan. 20 findings surfaced; 11 applied:

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 1 | P0 | `legalization.py` deletion breaks `router_v6/pipeline.py` | U9 modification list extended |
| 2 | P1 | `force_directed.py` deletion breaks `heuristics/pipeline.py` and `ablation/` | Extra files in U9 delete/modify lists |
| 3 | P1 | `benders_loop.py` deletion breaks `adapters/` | Adapters added to U9 modification list |
| 4 | P1 | `PlacementState` JAX-coupled; U5 verification wrong | `from_positions_dict()` factory + relaxed criterion |
| 5 | P1 | Cold-start solver timeout unaccounted | Bootstrap provision added to KTD |
| 6 | P1 | No-recovery JAX deletion (no legacy flag) | `--placer jax-deprecated` for one cycle |
| 7 | P2 | Experiment-unbundling undocumented | Decision log added to KTD |
| 8 | P2 | Routability not a blocking parity gate | Routability made hard gate in U8 |
| 9 | P2 | Wirelength omitted from parity metrics | Wirelength with 5% tolerance added |
| 10 | P2 | No feasibility spike before full build | U0 spike unit added |
| 11 | P2 | `supported_targets` frozensets not updated | Frozensets updated for 4 CP-SAT types |

### Requirements Review (ce-doc-review, round 2)

5 personas reviewed the calendar-gate requirements doc. 24 findings surfaced; 23 applied:

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 1 | P0 | Calendar gate replaces falsifiable verdict with unfalsifiable date | Skipped (user preference) |
| 2 | P1 | `jax-deprecated` flag can't work after optimizer deleted | Flag → no-op deprecation warning |
| 3 | P1 | Feasibility conflated with quality (652/652 ≠ good placement) | T1/T2 gate tiers separated |
| 4 | P1 | No head-to-head receipt for future maintainers | Frozen parity receipt added |
| 5 | P1 | R12 corpus confidence undefined | Moved to deferred |
| 6 | P1 | Calendar gate recreates deferral surface | Sunset decision at deadline |
| 7 | P1 | Origin traceability broken | `origin:` + Deviations from Origin section |
| 8-24 | P2-P3 | Granularity, success criteria gaps, U_BUCK analysis, experiment rationale | All applied in batch rewrite |

## Technical Discoveries

### OR-Tools `SufficientAssumptionsForInfeasibility()` Proto Indices

The function returns variable proto indices (`var.Index()`), not Python list
positions. A reverse map (`_build_proto_index_map()`) is required to translate.
Without it, UNSAT core constraint mappings are silently incorrect. Documented in
`docs/solutions/logic-errors/or-tools-sufficient-assumptions-proto-indices-2026-07-03.md`.

### CP-SAT Spread Variable Bounds

`add_soft_wirelength_objective()` derived variable domains from max component
size × 2, which was too small for the actual board span. Components at opposite
board ends would need values exceeding their domain caps, causing INFEASIBLE.
Fixed by accepting board dimensions as parameters. Documented in
`docs/solutions/logic-errors/cp-sat-spread-variable-bounds-infeasible-2026-07-03.md`.

### Feasibility-First Performance

For 33 components with 5 hard constraint types:
- Feasibility-only (no objective): **OPTIMAL in 0.1s**
- With wirelength objective: **FEASIBLE in 60s** (hits timeout without proving optimality)
- Constraint audit: **652/652 checks passed**

The feasibility solve is ~600× faster than the optimization solve. Documented in
`docs/solutions/architecture-patterns/cp-sat-feasibility-first-paradigm-2026-07-03.md`.

## CI Changes

| File | Change |
|------|--------|
| `python-tests.yml` | Removed `tests/losses/` from invariant tests; added CP-SAT test step (`tests/placer/cp_sat/`, `tests/metrics/test_external_oracle.py`, `tests/cli/test_cp_sat_flag.py`) |
| `placer-regression.yml` | No changes needed (already `continue-on-error: true`; regression runner gracefully degrades with import wraps) |

## Remaining Work

1. **22 surviving module import wraps** — per-file refactoring for pipeline,
   regression, and validation modules still referencing `losses`/`optimizer`
   through try/except blocks. The wraps are a graceful degradation, not a final
   state.
2. **Calendar-gate retirement PR** — the plan (`docs/plans/2026-07-03-002-...`)
   and implementation are ready to open as a separate PR.
3. **CI smoke test verification** — run the full 5,209-test collection on CI to
   confirm no unexpected breakages from the import wraps.
