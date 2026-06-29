---
title: feat: Pipeline observability system
type: feat
status: active
date: 2026-06-28
origin: docs/brainstorms/2026-06-28-pipeline-observability-requirements.md
---

# feat: Pipeline observability system

## Summary

Wire the existing `ProgressObserver` observer chain and `PipelineProfiler` into per-stage metrics recording, surface every CI pipeline run as a self-contained HTML report in GitHub Actions artifacts, auto-post PR scorecards showing HPWL/timing/DRC deltas against baseline, and gate merges on SPC trend detection — all running in silent data-collection mode for 14 calendar days AND 20 runs before enforcement activates.

---

## Problem Frame

The CI pipeline runs `ci_closure_test.py` which produces observable data (`ClosureResult`, DRC output, `PipelineExecutionLog`) but none of it reaches the recording path. `metrics-record.yml` creates a synthetic `ClosureResult(passed=True, wall_clock_seconds=0)` — the 96 records in `pipeline_metrics.jsonl` are zero-valued by design. The `ProgressObserver` protocol fires 6 lifecycle events per run but no implementation listens for metrics. Operators manually inspect output with no per-stage timing, no trend awareness, no regression detection.

---

## Requirements

- R1. A `MetricsObserver` (ProgressObserver impl) records per-stage wall_time, success, and drc_delta into `pipeline_metrics.jsonl`, replacing the hardcoded-zero path
- R2. Per-stage minimum metrics: `wall_time_ms`, `success`, `drc_delta` (nullable when DRC doesn't run per-stage); `PipelineExecutionLog.to_dict()` extended to include events
- R3. Double-entry cross-validation: two independent instrumentation sources reconciled at write time; mismatch → `CrossValidationError`
- R4. Structured logging context (`{board, git_commit, stage, run_id}`) bound at pipeline init
- R5. Metric schema YAML with per-field valid ranges and `zero_is_valid` flags
- R6. Canary metric injection + verification traversing full recording path
- R7. Self-contained static HTML report generated per run and published as CI artifact
- R8. Report contents: DAG timeline color-coded by duration vs historical p95, per-stage breakdown, DRC summary, HPWL curve (when profiling enabled)
- R9. PR-triggered CI workflow runs pipeline on PR branch + merge-base
- R10. Auto-posted PR comment delta table: HPWL%, wall-clock%, DRC delta, per-stage timing deltas
- R11. SPC control charts with Western Electric rules on JSONL-derived metrics
- R12. SLO definition YAML: per-stage objectives with thresholds, window, severity
- R13. Silent room: 14 days AND 20 runs of data collection before SPC/SLO enforcement
- R14. Post-activation: SPC violations block CI; SLO `block` tier blocks, `warn` surfaces in PR
- R15. Health-digest integration: per-stage trend direction and gate violations

**Origin actors:** A1 (pipeline operator), A2 (PR author), A3 (CI system), A4 (pipeline maintainer)
**Origin flows:** F1 (pipeline run produces artifacts), F2 (PR scorecard), F3 (silent room activation), F4 (trend regression detected)
**Origin acceptance examples:** AE1 (per-stage non-zero records), AE2 (cross-validation catches zero), AE3 (canary detects broken path), AE4 (PR delta comment), AE5 (SPC blocks after activation), AE6 (SPC silent during room)

---

## Scope Boundaries

- Live developer dashboard (WebSocket-bridged session-dashboard SPA) — dev tool, not CI
- Compiler-style diagnostic chains — interactive debugging, not CI
- Convergence copilot, contract oracle — separate brainstorms / calibration-dependent
- Content-addressed archives, differential execution, chaos monkey, observability budget, telemetry bus — deferred exploratory ideas

### Deferred to Follow-Up Work

- SPC distributional validation (normality/independence checks before enforcing rules) — needs empirical data corpus
- PR scorecard noise-floor calibration (historical variance per stage) — needs silent room data
- HTML report cold-start color-coding fallback (static budgets before historical p95 is meaningful) — implement static thresholds first, dynamic p95 activates after enough runs

---

## Key Technical Decisions

- **MetricsObserver targets both orchestration paths**: `ClosureTest.run()` (CI path) and `StageDAGEngine` (local/Orchestrator path). The observer hooks into `ProgressObserver` where available; `ClosureTest` gets a direct instrumentation shim until migration to DAG engine is complete. CI records metrics today; DAG engine path inherits for free when it becomes the canonical path.
- **Single `PipelineMetricsRecord` stream per run**: `MetricsObserver` writes one JSONL line per stage-complete event. The existing `PipelineMetricsRecord` schema (v1) is extended with `stage_name` and `drc_delta` fields, versioned to v2. Backward-compatible read for v1 records.
- **Cross-validation sources**: wall_time — Path A from `time.monotonic()` deltas captured in `MetricsObserver.on_stage_start/complete`; Path B from `PipelineExecutionLog.stage_timings` reconstructed post-hoc. DRC delta — Path A from per-stage DRC run; Path B from final DRC fence recomputation.
- **SPC implementation**: Pure Python module. No external stats dependency — Western Electric rules are simple sequential checks on mean/sigma from a rolling window. Reuses existing `scripts/pipeline_metrics.py` as the entry point.
- **HTML report**: Python script generating a single `.html` with inline CSS/JS and embedded JSON data. No server dependency. Uses the `session-dashboard/` rendering patterns (color scheme, DAG timeline layout) as design reference.
- **Dual-run PR workflow**: New CI workflow triggered on `pull_request: paths: packages/**`. Runs the pipeline on merge-base first, stores `pipeline_metrics.jsonl` as a CI artifact, runs on PR branch, downloads merge-base artifact, computes deltas, posts PR comment via `github-script`.
- **Silent room state**: A `observability_state.json` file committed to the repo tracking `first_run_date`, `total_runs`, and `activation_status`. `metrics-trend-check.yml` reads it to decide enforcement mode.

---

## High-Level Technical Design

*This illustrates the intended data flow and is directional guidance for review, not implementation specification.*

```
Pipeline Run (CI or local)
        │
        ▼
  ┌─────────────────────────────────────────┐
  │  MetricsObserver (new ProgressObserver)  │
  │  ┌──────────────┐  ┌──────────────────┐  │
  │  │ ClosureTest  │  │ StageDAGEngine   │  │
  │  │ (CI shim)    │  │ (observer chain) │  │
  │  └──────┬───────┘  └────────┬─────────┘  │
  │         │                   │            │
  │         └─────────┬─────────┘            │
  │                   ▼                      │
  │     on_stage_complete → PipelineMetrics  │
  │     Record {wall_time, success, drc_Δ}   │
  │                   │                      │
  │     ┌─────────────┼──────────────┐       │
  │     ▼             ▼              ▼       │
  │  Schema      Cross-validate    Canary   │
  │  validate    (dual source)     check    │
  └─────────────────────────────────────────┘
        │
        ▼
  pipeline_metrics.jsonl (v2, per-stage)
        │
        ├──► html_report.py → report.html (CI artifact)
        │
        ├──► metrics-record.yml (commits JSONL to repo)
        │
        ├──► metrics-trend-check.yml
        │        │
        │        ├── reads observability_state.json (silent room check)
        │        ├── computes SPC (Western Electric rules)
        │        ├── evaluates SLOs (from slo_definitions.yaml)
        │        └── fails CI if post-activation AND regression detected
        │
        ├──► PR scorecard workflow
        │        │
        │        ├── runs pipeline on merge-base → stores artifact
        │        ├── runs pipeline on PR branch
        │        ├── computes deltas (HPWL%, timing%, DRCΔ)
        │        └── posts GitHub comment
        │
        └──► health-digest.yml
                 └── surfaces trend direction + gate violations
```

---

## Implementation Units

### U1. MetricsObserver — core recording layer

**Goal:** Implement `MetricsObserver` implementing `ProgressObserver` that bridges stage-complete events to `PipelineMetricsRecord` entries and writes to JSONL.

**Requirements:** R1, R2, R3, R5, R6

**Dependencies:** None

**Files:**
- Create: `packages/temper-placer/src/temper_placer/pipeline/metrics_observer.py`
- Modify: `packages/temper-placer/src/temper_placer/pipeline/__init__.py` (export MetricsObserver)
- Create: `packages/temper-placer/tests/test_metrics_observer.py`
- Modify: `packages/temper-placer/src/temper_placer/pipeline/dag_observability.py` (extend `PipelineExecutionLog.to_dict()` to include events)
- Modify: `packages/temper-placer/src/temper_placer/regression/metrics_recorder.py` (extend `PipelineMetricsRecord` to v2 with `stage_name`, `drc_delta`)

**Approach:** MetricsObserver subscribes to all 6 `ProgressObserver` callbacks. `on_stage_complete` constructs a `PipelineMetricsRecord` from the `StageEvent` fields (name, duration_s, success, outputs). Cross-validation (R3) compares `StageEvent.duration_s` against `PipelineExecutionLog.stage_timings[stage_name]` — two independent timing sources. Canary metric (R6) is a `_canary_value` set at init, written as a field, and verified on each flush. Schema validation (R5) reads from `metrics_schema.yaml` (created in this unit). `PipelineExecutionLog.to_dict()` is extended to include `events` list. `PipelineMetricsRecord` gains `stage_name: str` and `drc_delta: Optional[int]` fields with schema v2.

**Patterns to follow:**
- `DAGToLegacyObserver` at `dag_observability.py:62-131` — same observer protocol, same `self.observers` registration
- `PipelineProfiler` at `profiling/instrumentation.py:131` — context-manager pattern for lifecycle

**Test scenarios:**
- Happy: Full pipeline run with 8 stages → JSONL has 8 entries with `wall_time_ms > 0`, `stage_name` populated, `drc_delta` nullable where DRC not run
- Happy: `PipelineExecutionLog.to_dict()` includes `events` list with correct `StageEvent` fields
- Edge: Single-stage pipeline → 1 entry, no overflow
- Edge: Stage with `drc_delta: null` → recorded as null, not 0
- Cross-validation: Primary timing 0ms, secondary 5234ms → `CrossValidationError` raised, record not written (Covers AE2)
- Cross-validation: Primary and secondary within 10ms tolerance → record written
- Schema: `wall_time_ms: 0` with `zero_is_valid: false` → schema validation error before cross-validation runs
- Canary: Canary metric missing after pipeline completion → `METRICS_PIPELINE_BROKEN`, record not written (Covers AE3)
- Canary: Canary present with correct value → record written
- Integration: `MetricsObserver` registered with `StageDAGEngine.add_observer()` → callbacks fire on stage transitions

**Verification:** Run full pipeline; `pipeline_metrics.jsonl` contains per-stage records with non-zero wall_time. Inject cross-validation mismatch; verify error. All tests pass.

---

### U2. ClosureTest instrumentation shim

**Goal:** Instrument `ClosureTest.run()` to record per-step timing and DRC results into the same `MetricsObserver`-backed JSONL path, bridging the CI gap until the DAG engine is the canonical orchestration path.

**Requirements:** R1, R2, R10, R9

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/closure_test.py`
- Modify: `scripts/ci_closure_test.py`
- Create: `packages/temper-placer/tests/test_closure_metrics.py`

**Approach:** Add an optional `observer: Optional[MetricsObserver]` parameter to `ClosureTest.run()`. At each major step boundary (placement complete, routing complete, DRC complete), emit a synthetic `StageEvent` through the observer. This is temporary scaffolding — the long-term path is `ClosureTest` migrating to `StageDAGEngine`, but this gives CI metrics today. The `ci_closure_test.py` script creates a `MetricsObserver`, passes it to `ClosureTest.run()`, and calls `observer.on_pipeline_complete()` at exit.

**Patterns to follow:**
- `PipelineOrchestrator.__init__()` at `orchestrator.py:199` — same `add_observer()` pattern
- Existing `closure_test.py:350-381` step boundaries

**Test scenarios:**
- Happy: `ClosureTest.run(observer=observer)` → observer receives stage events for placement, routing, DRC
- Happy: `ci_closure_test.py` script produces `pipeline_metrics.jsonl` with non-zero records (Covers AE1)
- Edge: `ClosureTest.run()` called without observer → no crash, existing behavior unchanged
- Integration: CI `metrics-record.yml` step produces non-zero `wall_time_ms` after this change

**Verification:** Run `python scripts/ci_closure_test.py`; `pipeline_metrics.jsonl` no longer contains all-zero records. Existing closure test behavior unchanged when no observer is passed.

---

### U3. Structured logging context

**Goal:** Bind `{board, git_commit, stage, run_id}` to all log lines from any pipeline module during a run.

**Requirements:** R4

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/pipeline/dag_engine.py` (add context binding to `StageDAGEngine`)
- Modify: `packages/temper-placer/src/temper_placer/closure_test.py` (add context binding to `ClosureTest.run()`)
- Create: `packages/temper-placer/tests/test_logging_context.py`

**Approach:** Use Python's `logging.LoggerAdapter` with a context dict populated at pipeline init. `StageDAGEngine`'s context is set from a new `run_metadata: Optional[dict]` parameter. `ClosureTest` binds context from `board_id` and git commit (`subprocess.check_output(['git', 'rev-parse', 'HEAD'])` or CI env var). The adapter wraps the root logger so all downstream `logging.getLogger(__name__)` calls inherit context without per-module changes.

**Patterns to follow:**
- Python `logging.LoggerAdapter` — standard library pattern, no dependency
- `StageDAGEngine.__init__` parameter extension at `dag_engine.py:37`

**Test scenarios:**
- Happy: Pipeline run with `run_metadata={'board': 'temper', 'commit': 'abc123', 'run_id': 'xyz'}` → log output includes these fields
- Happy: `ClosureTest.run()` with board_id='temper' → log lines include board identifier
- Edge: No `run_metadata` provided → logging works with empty context, no crash
- Edge: Exception at any stack depth → traceback includes context dict

**Verification:** Run pipeline with metadata; grep logs for board/commit/run_id. Log output from deep stack frames (e.g., inside JAX placement) still carries context.

---

### U4. Metric schema YAML and validation

**Goal:** Define `metrics_schema.yaml` declaring per-field name, unit, valid_range, and zero_is_valid. Wire schema validation into `MetricsObserver` write path.

**Requirements:** R5

**Dependencies:** U1

**Files:**
- Create: `packages/temper-placer/src/temper_placer/regression/metrics_schema.yaml`
- Create: `packages/temper-placer/src/temper_placer/regression/schema_validator.py`
- Modify: `packages/temper-placer/src/temper_placer/pipeline/metrics_observer.py` (integrate validation)
- Create: `packages/temper-placer/tests/test_schema_validator.py`

**Approach:** `metrics_schema.yaml` lists top-level keys mapping field names to `{unit, min, max, zero_is_valid, introduced: "YYYY-MM-DD"}`. `SchemaValidator` loads the YAML, validates each field in a `PipelineMetricsRecord.metrics` dict before write. Runs before cross-validation (R3). Fields absent from schema are rejected. Fields present in schema but missing from record with `zero_is_valid: false` are rejected.

**Patterns to follow:**
- `firmware/config.yaml` → `firmware/config.h` codegen pattern for YAML-as-config
- YAML parsing used throughout codebase (manifest, transition table, config)

**Test scenarios:**
- Happy: Record with `wall_time_ms: 5234` passes schema (`zero_is_valid: false`, `min: 0`, `max: 3600000`)
- Reject: `wall_time_ms: 0` → `SchemaValidationError`
- Reject: `wall_time_ms: -1` → range violation
- Reject: `wall_time_ms: 5000000` → exceeds max
- Accept: `drc_delta: 0` with `zero_is_valid: true` → passes
- Reject: Unknown field → rejected
- Integration: Schema validation runs before cross-validation — zero-valued metric is caught by schema, never reaches cross-validation

**Verification:** All schema validation test cases pass. Integration test: corrupt record rejected by schema before cross-validation fires.

---

### U5. SPC computation module

**Goal:** Implement Western Electric SPC rules as a pure Python module, integrated into `scripts/pipeline_metrics.py` with silent-room gating via `observability_state.json`.

**Requirements:** R11, R13, R14, R15

**Dependencies:** U1 (need real data to test against)

**Files:**
- Create: `scripts/spc_rules.py`
- Create: `scripts/tests/test_spc_rules.py`
- Modify: `scripts/pipeline_metrics.py` (integrate SPC trend subcommand, silent-room gating)
- Create: `power_pcb_dataset/metrics/observability_state.json` (initialized with `{first_run_date: null, total_runs: 0, activated: false}`)
- Modify: `.github/workflows/metrics-trend-check.yml` (SPC integration)
- Modify: `.github/workflows/health-digest.yml` (SPC trend data integration)

**Approach:** `spc_rules.py` implements four functions matching the Western Electric rules, each accepting a rolling window of values and returning `(violated: bool, rule_name: str)`. Rules: `rule_3sigma(values, mean, sigma)`, `rule_2of3_2sigma`, `rule_4of5_1sigma`, `rule_8consecutive`. `scripts/pipeline_metrics.py` gains an `spc` subcommand that reads `pipeline_metrics.jsonl`, groups by stage+metric, computes moving baseline (mean/sigma from rolling window of last N runs), evaluates each rule, outputs JSON with per-stage/per-metric violations. Silent room gating: reads `observability_state.json`; if `activated: false`, computes and reports but exit code is always 0. On run 20 (or when 14 days elapsed AND 20 runs), sets `activated: true`. `metrics-trend-check.yml` calls `spc` subcommand; exit code non-zero only post-activation. `health-digest.yml` calls `spc --summary` to get trend directions without blocking.

**Patterns to follow:**
- Existing `_compute_trends()` in `pipeline_metrics.py:33-82` — same data source, same output shape
- `metrics-trend-check.yml` — existing workflow structure for trend checking

**Test scenarios:**
- Happy: 9-run window with stable values → no rule fires
- Rule (a): Point beyond 3σ → `rule_3sigma` fires
- Rule (b): 2 of 3 beyond 2σ (one side) → `rule_2of3_2sigma` fires
- Rule (c): 4 of 5 beyond 1σ → `rule_4of5_1sigma` fires
- Rule (d): 8 consecutive above mean → `rule_8consecutive` fires (Covers AE5)
- Edge: Window smaller than required (e.g., 2 runs for 3σ rule) → returns not-enough-data
- Silent room: `activated: false` → SPC violations computed but exit code 0 (Covers AE6)
- Post-activation: `activated: true` → SPC violation → exit code 1 (Covers AE5)
- Integration: `metrics-trend-check.yml` fails CI only post-activation

**Verification:** Run `python scripts/pipeline_metrics.py spc --board temper` against historical data. Rules evaluate correctly. Silent room gating works. CI workflow integration verified via workflow dispatch.

---

### U6. SLO definitions and CI gating

**Goal:** Define SLO YAML schema, implement SLO evaluation, and wire into CI PR checks.

**Requirements:** R12, R14

**Dependencies:** U1

**Files:**
- Create: `power_pcb_dataset/metrics/slo_definitions.yaml`
- Create: `scripts/slo_evaluator.py`
- Create: `scripts/tests/test_slo_evaluator.py`
- Modify: `scripts/pipeline_metrics.py` (add `slo` subcommand)
- Modify: `.github/workflows/metrics-trend-check.yml` (SLO integration)

**Approach:** `slo_definitions.yaml` follows `firmware/config.yaml` conventions:
```yaml
stages:
  routing:
    - metric: wall_time_ms
      type: p95
      threshold: 120000
      window: 10
      severity: block
    - metric: drc_delta
      type: max
      threshold: 5
      window: 5
      severity: warn
```
`slo_evaluator.py` loads YAML, reads `pipeline_metrics.jsonl`, computes per-metric aggregate over window, compares to threshold, returns violations. `pipeline_metrics.py slo` subcommand outputs JSON with violations tagged by severity. CI gate: post-activation, `block` violations → exit code 1; `warn` violations → exit code 0 but reported in health-digest.

**Patterns to follow:**
- `firmware/config.yaml` YAML schema conventions
- Existing `_compute_trends()` in `pipeline_metrics.py` for window-based aggregation

**Test scenarios:**
- Happy: All metrics within thresholds → no violations
- Block: wall_time p95 exceeds threshold → `block` violation, exit code 1 post-activation
- Warn: drc_delta exceeds threshold but severity is `warn` → reported, exit code 0
- Edge: Insufficient runs in window → returns `insufficient_data`, no violation
- Silent room: `block` violation during silent room → exit code 0
- Integration: SLO violations surface in health-digest with metric name, threshold, observed value

**Verification:** Create SLO definition with known-failing threshold; run `slo` subcommand; verify violation output. Silent room gating works.

---

### U7. Static HTML report generation

**Goal:** Generate a self-contained HTML report from `pipeline_metrics.jsonl` + `PipelineExecutionLog` per pipeline run, published as CI artifact.

**Requirements:** R7, R8

**Dependencies:** U1

**Files:**
- Create: `scripts/pipeline_report.py`
- Create: `scripts/tests/test_pipeline_report.py`
- Modify: `.github/workflows/metrics-record.yml` (add report generation + artifact upload)

**Approach:** Python script reads `PipelineExecutionLog` (JSON) and `pipeline_metrics.jsonl`, embeds data as inline `<script>window.__PIPELINE_DATA__ = ...</script>` in a standalone HTML template. Template renders: (1) DAG timeline with stages as horizontal bars, width = duration, color = green (<p95 historical), yellow (p95-p99), red (>p99), grey (insufficient history); (2) per-stage wall-clock table; (3) DRC violation summary table; (4) HPWL convergence line chart (canvas element, data from JSON). No external CDN — Chart.js equivalent is a minimal inline canvas renderer (~100 lines). The report uses `session-dashboard/css/styles.css` color variables for visual consistency.

**Patterns to follow:**
- `session-dashboard/index.html` — color scheme, layout conventions
- `session-dashboard/js/session-card.js` — DOM-based rendering patterns
- `PipelineProfiler.report.to_json()` — machine-readable output pattern

**Test scenarios:**
- Happy: Pipeline run produces `report.html` → opening in browser shows DAG timeline with correct stage order and durations
- Happy: Report includes per-stage wall-clock table, DRC summary, HPWL curve (when JAX profiling enabled)
- Edge: First run (no historical p95) → all stages rendered in grey, "baseline building" note shown
- Edge: Stage with 0ms duration → rendered with 1px minimum width, "0ms" label
- Edge: Report with empty DRC data → "No DRC violations" shown, no crash
- Integration: CI artifact uploads `report.html`; downloading and opening produces correct report

**Verification:** Run pipeline, open `report.html` in browser, verify all sections render correctly. Test with empty data (first run), with DRC violations, with JAX profiling enabled.

---

### U8. PR scorecard CI workflow

**Goal:** New CI workflow triggered on PRs touching `packages/**` that runs pipeline on both merge-base and PR branch, computes deltas, and posts a PR comment.

**Requirements:** R9, R10

**Dependencies:** U1, U2

**Files:**
- Create: `.github/workflows/pr-pipeline-scorecard.yml`
- Create: `scripts/pr_scorecard.py`
- Create: `scripts/tests/test_pr_scorecard.py`

**Approach:** New workflow `pr-pipeline-scorecard.yml` triggered on `pull_request: paths: 'packages/**'`. Steps: (1) checkout merge-base, run `ci_closure_test.py`, upload `pipeline_metrics.jsonl` as artifact; (2) checkout PR head, run `ci_closure_test.py`, download merge-base artifact; (3) run `scripts/pr_scorecard.py --baseline baseline.jsonl --current current.jsonl` which computes per-stage deltas (wall_time%, drc_delta diff) and per-run deltas (total_wall_time%, completion_pct diff); (4) if `activated` in observability_state, also report SLO status changes; (5) post comment via `github-script@v7` with formatted markdown table. Delta computation: for each stage pair, compute `(current - baseline) / baseline * 100` for wall_time; absolute diff for drc_delta.

**Patterns to follow:**
- `health-digest.yml` — same `github-script@v7` issue comment pattern
- `metrics-record.yml` — same `ci_closure_test.py` invocation pattern
- `scripts/pipeline_metrics.py` — same JSON parsing pattern

**Test scenarios:**
- Happy: PR adds 50ms delay to stage 3 → PR comment shows `+53ms / +4.2%` for Stage 3 (Covers AE4)
- Happy: PR with no pipeline impact → comment shows all deltas within +/-1%
- Edge: Merge-base has no prior metrics → workflow runs pipeline on merge-base to generate baseline
- Edge: Stage present in current but not baseline (new stage) → "new" annotation, no delta
- Edge: Stage present in baseline but not current (removed stage) → "removed" annotation
- Edge: SPC/SLO not yet activated → no SLO status in comment
- Edge: PR touches non-pipeline files → workflow not triggered

**Verification:** Open test PR with known timing change; workflow runs, correct delta comment posted. Comment includes all stages and aggregate metrics.

---

## Risks & Dependencies

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| SPC false-positives from CI infrastructure variance | High | Silent room collects baseline; SPC rules tuneable per metric; Western Electric rules configurable (enable/disable per rule per metric) |
| `ClosureTest` instrumentation shim diverges from `StageDAGEngine` metrics | Medium | Shim is documented as temporary; DAG engine migration tracked in follow-up work |
| JAX profiling (`TEMPER_PROFILE_JAX=1`) host-sync overhead unacceptable | Medium | Flag is opt-in; HPWL SPC gated on flag being enabled; document overhead in assumptions |
| Dual-run PR workflow doubles CI cost | Medium | Workflow only triggers on `packages/**` changes; can be manually skipped via label |
| `pipeline_metrics.jsonl` grows unbounded | Low | Per-stage records are ~200 bytes each; 8 stages × 1000 runs = ~1.6MB; truncation policy deferred |
| HTML report generation depends on browser rendering assumptions | Low | Minimal canvas renderer; tested in headless CI via screenshot comparison |

---

## Outstanding Questions

### Deferred to Planning

- SPC distributional validation (normality/independence checks) before enforcing rules — wait for silent room data
- PR scorecard noise-floor calibration — wait for silent room variance data
- HTML report cold-start color-coding — use static thresholds until enough history
- `PipelineProfiler` wiring into `MetricsObserver` (currently standalone) — separate integration unit

### Deferred to Implementation

- Exact SPC rule configuration per metric (which Western Electric rules apply to each metric)
- SLO threshold values — initial values estimated from documentation; tuned post-silent-room
- HTML report rendering engine — extend `session-dashboard/` patterns as design reference
- CI workflow structure for dual-run: `ci_closure_test.yml` reuse vs new workflow
- `observability_state.json` commit strategy — auto-committed by `metrics-record.yml` with `[skip ci]` tag
