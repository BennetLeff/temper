---
date: 2026-06-28
topic: pipeline-observability
origin: docs/ideation/2026-06-28-pipeline-observability-ideation.md
status: active
---

# Requirements: Pipeline Observability

## Summary

A CI-grounded observability system that wires the existing `ProgressObserver` chain and `PipelineProfiler` into per-stage metrics recording, surfaces every pipeline run as a self-contained HTML report in CI artifacts, auto-posts PR scorecards showing HPWL/timing/DRC deltas against baseline, and gates merges on SPC trend detection — all running in silent data-collection mode for 14 days or 20 runs before enforcement activates.

```
StageDAGEngine (already fires ProgressObserver on every stage)
        │
        ▼
  MetricsObserver (NEW — the one missing piece)
        │
        ├─► pipeline_metrics.jsonl (per-stage, cross-validated)
        │       │
        │       ├─► CI artifact: static HTML report (per-run visibility)
        │       ├─► PR comment: delta scorecard vs baseline (per-PR feedback)
        │       ├─► metrics-trend-check: SPC charts + SLO gates (drift detection)
        │       └─► health-digest: aggregated trend + compliance (weekly overview)
        │
        └─► Health data is derived directly from pipeline_metrics.jsonl (no separate artifact)
```

---

## Problem Frame

The pipeline runs but produces no usable observability data. `metrics-record.yml` creates a synthetic `ClosureResult(passed=True, ...)` with hardcoded `wall_clock_seconds=0` — the 96 records in `pipeline_metrics.jsonl` are zero-valued by design, not by accident. `PipelineProfiler` exists with full instrumentation and tests at `packages/temper-placer/src/temper_placer/profiling/instrumentation.py:131` but is not wired into the DAG engine. The `ProgressObserver` protocol fires 6 lifecycle events on every pipeline run but no implementation listens for metrics. Operators manually inspect pipeline output with no per-stage timing visibility, no trend awareness, and no way to know whether a PR regressed placement quality or routing performance.

The existing `CI` infrastructure (`metrics-record.yml`, `metrics-trend-check.yml`, `health-digest.yml`) is wired to consume `pipeline_metrics.jsonl` — the pipeline exists, the consumers exist, but the data between them is fake.

---

## Actors

- A1. **Pipeline operator**: Runs the pipeline, needs immediate visibility into what happened — which stage ran, how long it took, whether DRC passed, whether HPWL converged.
- A2. **PR author**: Makes code changes touching pipeline code, needs to know the quantitative performance and quality impact before merge.
- A3. **CI system**: Executes the pipeline automatically, records metrics, surfaces reports, and enforces regression gates.
- A4. **Pipeline maintainer**: Reviews health trends over weeks, investigates drift, and tunes SPC/SLO thresholds.

---

## Key Flows

- F1. **Pipeline run produces observability artifacts**
  - **Trigger:** Pipeline execution (local or CI)
  - **Actors:** A1, A3
  - **Steps:** DAG engine fires `ProgressObserver.on_stage_complete` for each stage → `MetricsObserver` records per-stage `PipelineMetricsRecord` → double-entry cross-validation → append to JSONL → generate static HTML report → publish as CI artifact
  - **Outcome:** `pipeline_metrics.jsonl` contains per-stage (not just closure) records with non-zero values; a self-contained HTML report is available in CI artifacts
  - **Covered by:** R1, R2, R3, R7, R8

- F2. **PR touches pipeline code**
  - **Trigger:** PR created or updated with changes to files under `packages/`
  - **Actors:** A2, A3
  - **Steps:** CI runs full pipeline on PR branch AND merge-base → computes delta table (HPWL%, wall-clock%, DRC error delta, per-stage timing deltas) → posts delta as PR comment
  - **Outcome:** PR author and reviewer see quantitative before/after comparison without manual inspection
  - **Covered by:** R9, R10

- F3. **Silent room → active enforcement transition**
  - **Trigger:** 14 calendar days elapsed since first run AND at least 20 pipeline runs recorded
  - **Actors:** A3
  - **Steps:** `metrics-trend-check.yml` checks activation condition → if met, flips from silent mode to enforcement mode → subsequent runs apply SPC rules and SLO gates
  - **Outcome:** Regressions that would have been silently recorded are now blocked at merge
  - **Covered by:** R13, R14

- F4. **Trend regression detected**
  - **Trigger:** SPC Western Electric rule fires on a tracked metric
  - **Actors:** A3, A4
  - **Steps:** `metrics-trend-check.yml` computes SPC on latest run → rule violation detected → CI gate blocks merge (if post-activation) → `health-digest.yml` surfaces the regression in its weekly issue
  - **Outcome:** A pipeline maintainer sees the regression in the health digest with the offending metric, rule that fired, and trend direction
  - **Covered by:** R11, R14, R15

---

## Requirements

### Metrics recording layer

- R1. A `MetricsObserver` implementation of the `ProgressObserver` protocol bridges DAG stage-complete events to `PipelineMetricsRecord` entries in `pipeline_metrics.jsonl`. Replaces the current hardcoded-zero `record_closure_result()` path in `metrics-record.yml`.
- R2. Every pipeline stage emits at minimum: `wall_time_ms`, `success` (boolean), and `drc_delta` (violation count change from prior stage, where DRC runs as a pipeline step or post-hoc check; stages that do not produce DRC data emit `drc_delta: null`). `PipelineExecutionLog.to_dict()` is extended to include the `events` list.
- R3. Every metric written to JSONL is computed via two independent code paths and reconciled at write time. The two paths must use demonstrably different instrumentation sources (e.g., Path A: `StageMeta.timings` accumulated in-process; Path B: `PipelineExecutionLog` reconstructed from DAG event timestamps post-hoc). Mismatch beyond tolerance raises `CrossValidationError` and the corrupt record is not written. Schema validation (R5) runs first; cross-validation runs on schema-valid metrics.
- R4. A structured logging context (`{board, git_commit, stage, run_id}`) is bound at DAG engine init and auto-attached to all log lines from any pipeline module.
- R5. A metric schema (YAML) declares per-field: `name`, `unit`, `valid_range`, and `zero_is_valid`. The writer validates against schema before appending. `wall_time_ms` is declared `zero_is_valid: false`.
- R6. A canary metric (`__pipeline_liveness__ = 42.0`) is injected at pipeline start, traverses the full recording path, and is verified at JSONL write time. If missing or wrong, `METRICS_PIPELINE_BROKEN` is emitted and the record is not written.

### Visibility

- R7. A self-contained static HTML report is generated from `pipeline_metrics.jsonl` + `PipelineExecutionLog` after every pipeline run and published as a CI artifact.
- R8. The report renders: an execution DAG timeline with stages color-coded by duration (green/yellow/red against historical p95), per-stage wall-clock breakdown, DRC violation summary with violation counts per stage, and HPWL convergence curve (when `TEMPER_PROFILE_JAX=1` is enabled).

### PR scorecard

- R9. A CI workflow triggered on PRs touching `packages/**` runs the full pipeline on both the PR branch and the merge-base (or latest `main`).
- R10. A delta table is auto-posted as a PR comment showing: HPWL delta%, wall-clock delta%, DRC error delta, per-stage timing deltas, and any SLO status change (after activation).

### Regression detection

- R11. `metrics-trend-check.yml` computes SPC control charts on key metrics derivable from the per-stage JSONL records (DRC violation delta, wall_time by stage, overall success rate) using Western Electric rules: (a) 1 point beyond 3σ, (b) 2 of 3 beyond 2σ, (c) 4 of 5 beyond 1σ, (d) 8 consecutive on one side of center line. Per-iteration HPWL tracking requires `TEMPER_PROFILE_JAX=1` and is opt-in; SPC on HPWL activates only when that data source is enabled.
- R12. An SLO definition file (YAML) declares per-stage objectives: `metric`, `threshold`, `evaluation_window` (N runs), `severity` (`block` or `warn`). CI gates PRs against these SLOs after activation.

### Silent room

- R13. For the first 14 calendar days AND at least 20 pipeline runs recorded, all metrics are collected, SPC is computed, and SLOs are evaluated but none block CI merges. All outputs (reports, scorecards) are produced in full. Activation requires both conditions — a minimum corpus (20 runs) is required for statistically meaningful SPC control limits regardless of elapsed time.
- R14. After activation, SPC rule violations always cause CI to fail the PR check. SLO breaches on the `block` severity tier also cause CI to fail. `warn` severity SLO violations surface in the PR comment but do not block.
- R15. `health-digest.yml` integrates SPC trend data and SLO compliance status, displaying per-stage trend direction (improving/stable/degrading) and any gates in violation.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3.** Given a pipeline run with 8 stages, when the run completes, `pipeline_metrics.jsonl` contains 8 records (one per stage) with `wall_time_ms > 0` and `drc_delta` populated. No record has all-zero metrics.
- AE2. **Covers R3.** Given a pipeline run where the primary `wall_time_ms` computation produces 0 but the independent crosscheck produces 5230, when the record is about to be written, `CrossValidationError` is raised and the record is not appended to JSONL.
- AE3. **Covers R6.** Given a pipeline run where the JSONL writer is broken and fails to record the canary metric, when the pipe completes, `METRICS_PIPELINE_BROKEN` is emitted and the record is not written.
- AE4. **Covers R9, R10.** Given a PR that adds a 50ms delay to stage 3, when CI runs the dual pipeline, the PR comment shows `| Stage 3 | +53ms | +4.2% |` and the reviewer sees it before reading code.
- AE5. **Covers R11, R14 (post-activation).** Given a pipeline where routing wall_time has increased 2% per run over the last 8 runs and the silent room has ended, when the 9th run completes, SPC rule (d) fires, CI blocks the merge, and health-digest surfaces "routing p95 trend: DEGRADING."
- AE6. **Covers R13.** Given a pipeline run on day 3 of the silent room, when SPC detects a 3σ outlier on HPWL, the report and PR comment note the deviation but CI does NOT block the merge.

---

## Success Criteria

- A pipeline operator can open a CI artifact and answer "what happened in this run?" within 30 seconds — which stages ran, how long they took, whether DRC passed.
- The 96-zero-records class of bug cannot recur — cross-validation and schema enforcement catch instrumentation failure within 1 record.
- A PR author receives quantitative performance/quality impact in their PR comment without running a manual before/after comparison.
- Gradual degradation (e.g., 10-run 1%-per-run routing slowdown) is detected before it becomes a hard failure, via SPC trend rules.
- `ce-plan` receives a complete scope and can focus on integration details (observer implementation, CI workflow changes, HTML report generation) without inventing product behavior.

---

## Scope Boundaries

- Live developer dashboard (WebSocket-bridged session-dashboard SPA) — interactive dev tool outside CI scope.
- Compiler-style diagnostic chains for DRC violations — interactive debugging tool outside CI scope.
- Convergence copilot (auto-early-stop on HPWL plateau) — needs per-board calibration data not yet available.
- Contract oracle (stage-boundary invariant assertions) — overlaps with existing pipeline-contracts brainstorm at `docs/brainstorms/2026-06-28-pipeline-contracts-integration-requirements.md`.
- Content-addressed run archives, differential pipeline execution, chaos monkey testing, observability budget management, and SCADA-style telemetry bus — exploratory ideas deferred until core system ships.

---

## Key Decisions

- **SPC + SLO full stack over simple threshold gate**: Richer drift detection catches gradual degradation but requires a calibration corpus. The silent room (R13) bridges this gap — 14 days / 20 runs of data before enforcement.
- **Static HTML CI artifact over live dashboard**: The pipeline runs in CI, not on developer laptops. A self-contained HTML file is zero-setup, survives CI artifact expiry, and can be shared in Slack. The existing `session-dashboard/` SPA remains available for future live wiring.
- **One new `ProgressObserver` implementation over per-stage instrumentation**: The DAG engine already fires `on_stage_complete` with duration and metadata for every stage. A single `MetricsObserver` captures all stages with no per-stage wiring changes.
- **Dual-run PR scorecard (PR branch + merge-base)**: Adds CI cost but eliminates the need for manual before/after comparison, which is the current bottleneck in pipeline-change review.

---

## Dependencies / Assumptions

- `PipelineProfiler` at `packages/temper-placer/src/temper_placer/profiling/instrumentation.py:131` is feature-complete with tests — wiring it into the observer chain is an integration task, not a build-from-scratch task.
- `PipelineExecutionLog.to_dict()` currently excludes the `events` list — extending it to include events is a low-risk change.
- The existing CI workflows (`metrics-record.yml`, `metrics-trend-check.yml`, `health-digest.yml`) are consumers of `pipeline_metrics.jsonl` — they can be extended to consume the new per-stage records without breaking existing behavior.
- The `power_pcb_dataset/metrics/pipeline_metrics.jsonl` path is stable and the `find_metrics_file()` function in `metrics_recorder.py` resolves it correctly in CI.
- `TEMPER_PROFILE_JAX=1` flag for per-iteration HPWL/density metrics uses `jax.debug.callback` which carries host-sync overhead — acceptable when opt-in, not suitable for always-on production runs.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R1][Technical] CI orchestration path uses `ClosureTest.run()` (not `StageDAGEngine`) — the `MetricsObserver` must instrument both paths or CI must migrate to the DAG engine. The current CI path (`scripts/ci_closure_test.py`) calls `resolve_and_run()` which creates a `PipelineRunner` that has no observer protocol. Either: (a) migrate `ClosureTest` to `StageDAGEngine`, (b) add observer hooks to `PipelineRunner`, or (c) instrument `ClosureTest.run()` directly.

- [Affects R8][Technical] HTML report rendering engine: extend `session-dashboard/` patterns or build standalone?
- [Affects R11][Needs research] Optimal SPC rule configuration per metric — which of the 4 Western Electric rules should apply to HPWL vs wall_time vs DRC count?
- [Affects R12][Technical] SLO YAML schema design — reuse `config.yaml` conventions from firmware or design standalone?
- [Affects R9][Technical] CI workflow structure for dual-run PR scorecard — reuse existing `ci_closure_test.yml` or new workflow?
