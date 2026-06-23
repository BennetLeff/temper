---
date: 2026-06-22
topic: test-and-build-next-priorities
focus: What to test and build next after pipeline strangler decomposition
mode: repo-grounded
---

# Ideation: What to Test and Build Next

## Grounding Context

### Codebase Context

Just completed: 7-feature pipeline decomposition (DSN seam, golden fixtures, unified protocol, DAG orchestrator, Stage 2 micro-stages, DRC fence, import-linter). Key gaps found by scan:

**Testing gaps:** `tests/protocol/` entirely missing (protocol.py, runner.py, strategy_registry.py have zero tests). Golden fixtures directory empty (README only, no .dsn files). Coverage measurement scoped to `temper_placer.core` only — router_v6, adapters, protocol, io, pipeline DAG not measured in CI despite having tests.

**CI soft-launches:** Two deadlines on 2026-07-06: import-linter goes from WARNING to hard-block, DRC fence performance budget enforcement activates. Import-linter baseline has ~130 entries to shrink before hard-block.

**Still monolithic:** RouterV6 Stage 3 (SAT) and Stage 4 (A*) — 300+ line monoliths. 21 of 26 DeterministicPipeline boundaries have no golden fixtures. PipelineOrchestrator old handlers still present with deprecation warnings. 118 scripts unrefactored.

**Active but unstarted plans:** Placer regression infrastructure (plan 010 — placement quality has zero systematic regression testing), Pipeline profiling toolkit (plan 015), Placement-routing pipeline gap (plan 011 — closure test producing false PASS).

### Past Learnings

1. CI-gate pattern: baseline + monotonic-shrink allowlist + hard-block on new violations — proven across 9 sprints
2. Per-stage DRC fence: RouterV6 Stage 1 & 4 no-op fence checks; performance budget soft-launch until July 6
3. Golden fixture ladder: covers only 5 of 26 DeterministicPipeline stages; 14MB fixture lesson
4. Stage 2 decomposition: 8 micro-stages with per-module coverage gates — pattern ready for Stages 3 & 4
5. What broke after refactors: PowerPlaneStage silent overwrite, PlacementResult broke router, OUTPUT-before-REFINEMENT ordering, skip_local_refinement silent no-op
6. Import-linter: ~130 baseline entries to shrink before July 6 hard-block deadline
7. Placer regression plan (010): active, not yet implemented

### External Context

- tscircuit/autorouting benchmark: problem taxonomy by difficulty, two-tier metrics, SVG snapshot tests
- FreeRouting: JUnit tests per issue, DSN fixtures for regression, KiCad DRC as independent oracle
- Strangler fig migration: shadow testing, reconciliation loops, canary rollout, anti-corruption layer
- Hypothesis PBT: routing invariants (DRC compliance, connectivity, transformation invariance, idempotence, monotonicity)
- Quality metric taxonomy: Gate tier (DRC>0 = fail) → Efficiency (wire length, vias) → Signal Integrity → Manufacturability → Aesthetics → Process cost

## Topic Axes

1. **Testing infrastructure** — protocol/adapters test gap, coverage measurement expansion, golden fixture population, per-module coverage gates
2. **CI gate hardening** — soft-launch deadlines (July 6), DRC fence CI wiring, golden-check meaningful, import-linter baseline shrink
3. **Pipeline quality improvement** — RouterV6 0.5%→10%, Stage 3/4 strangler decomposition, placement regression infrastructure
4. **Monitoring and observability** — profiling toolkit, stage coverage table, benchmark regression detection, quality metrics dashboard
5. **Debt resolution** — 118 scripts, 193 coverage allowlist entries, old orchestrator handler deletion, closure test false-PASS fix

## Ranked Ideas

### 1. Truth-Gate the Closure Test — Require Real Pipeline Results
**Axis:** CI gate hardening
**Basis:** `direct:` closure_test.py catches Exception and appends to warnings, never failing. Both placement and routing steps can throw ImportError and the test reports PASS with zero real results. 6 of 6 ideation frames independently converged on the false-PASS as the #1 testing gap.
**Rationale:** Every other gate (golden fixtures, DRC fence, protocol conformance) depends on a closure test that actually exercises the pipeline. Fixing this single test makes every subsequent quality investment visible.
**Confidence:** 95%
**Complexity:** Low
**Status:** Unexplored

### 2. Seed the Golden Ladder — 32 Fixtures for Stage 2 Micro-Stages
**Axis:** Testing infrastructure
**Basis:** `direct:` golden fixture ladder plan defines R1-R20 but populates nothing — `power_pcb_dataset/goldens/temper/` has only README.md. Stage 2 has 8 micro-stages × 4 canonical boards = 32 fixtures needed. 5 of 6 frames converged.
**Rationale:** The golden ladder is a plan, not a safety net. Seeding the first rung turns it into a functioning gate. Every subsequent stage extraction follows the same copy-paste pattern.
**Confidence:** 90%
**Complexity:** Medium
**Status:** Unexplored

### 3. Protocol Conformance Test Suite — Stage Contract Validation
**Axis:** Testing infrastructure
**Basis:** `direct:` `tests/protocol/` does not exist. protocol.py, runner.py, strategy_registry.py have zero tests. 8 new micro-stages about to be created. Hypothesis PBT already in use.
**Rationale:** Every future Stage subclass gets zero-cost conformance checking. Protocol violations caught at test time instead of in production routing failures.
**Confidence:** 85%
**Complexity:** Medium
**Status:** Unexplored

### 4. Deploy Strangler to RouterV6 Stage 3 (SAT Solver)
**Axis:** Pipeline quality improvement
**Basis:** `direct:` Stage 2 micro-stage pattern is proven (8 stages, 28 PBT, 32 golden parity). All infrastructure already built. Stage 3 is a single `_run_stage3` call with 5s timeout downstream of decomposed Stage 2.
**Rationale:** Each extracted sub-step removes one variable from the 0.5% debugging space. The infrastructure cost is already paid — Stage 3 extraction is now a well-paved path.
**Confidence:** 80%
**Complexity:** High
**Status:** Unexplored

### 5. Pipeline Quality Metrics Time-Series — Trend Detection
**Axis:** Monitoring and observability
**Basis:** `direct:` Closure test produces quality metrics on every PR but discards them after pass/fail. `external:` tscircuit/autorouting benchmark uses problem-taxonomy × solver matrix with trends.
**Rationale:** Answers "is decomposition actually making the pipeline better?" with data, not intuition. One JSONL append per CI run is near-zero cost.
**Confidence:** 82%
**Complexity:** Low
**Status:** Unexplored

### 6. Script Triage + Sunset — Reduce 118 Scripts
**Axis:** Debt resolution
**Basis:** `direct:` 118 scripts with blanket import-linter exemption. Import-linter July 6 deadline. Reducing scripts is a multiplier on every CI gate.
**Rationale:** Every script importing monolith internals is a time bomb on the strangler endgame. Reducing count reduces CI noise on every gate.
**Confidence:** 78%
**Complexity:** Medium
**Status:** Unexplored

### 7. Per-Stage Timing Regression Gate — Block Slowdowns
**Axis:** CI gate hardening
**Basis:** `direct:` CI-gate pattern proven across 9 sprints. Golden fixture diff gate provides architecture template. 26 stages × 5% each = 3.5× slowdown before detection.
**Rationale:** Golden fixtures catch correctness regressions; this catches speed regressions. Two together give each PR a complete quality gate at every stage boundary.
**Confidence:** 75%
**Complexity:** Medium
**Status:** Unexplored

## Rejection Summary

20+ ideas rejected. Key themes: boundary exerciser matrix (superseded by golden fixtures + protocol conformance), cost-per-route dashboard (folded into metrics time-series), DRC ceiling self-tightening (deferred), import-linter baseline auto-shrinker (secondary to script triage), placer regression (already planned), LOC 500-line ceiling (aspirational, planning-level), protocol fuzzer (deferred until goldens populate), pipeline Greeks sensitivity (deferred until metrics exist).
