---
date: 2026-06-28
topic: pipeline-observability
focus: "adding observability to the pipeline for monitoring observables"
mode: repo-grounded
---

# Ideation: Pipeline Observability

## Grounding Context

### Codebase Context
- **Temper**: ESP32-S3 induction cooker. Placement pipeline: Placement (JAX NSGA-II) -> Plane Generation -> Routing (Router V6, 4-stage) -> DRC fence.
- **CRITICAL BUG**: 96 records in `pipeline_metrics.jsonl` all have `wall_time_ms: 0`, `completion_pct: 0.0`, `benders_iterations: 0`, `benders_cuts: 0`.
- **Existing infra**: `ProgressObserver` protocol (6 lifecycle events), `PipelineExecutionLog`, `StageMeta.timings`, `dag_observability.py`, `session-dashboard/` SPA, `temper-autoprof` scaffold (dead code).
- **Plans**: Plan 020 (metrics time-series) partially implemented; Plan 015 (profiling toolkit) unimplemented.
- **CI**: `metrics-record.yml`, `metrics-trend-check.yml`, `health-digest.yml` exist.
- **Profiling patterns proven**: Scalar counters, one-shot logging guards, cProfile + JSON, JIT warm-up + min-of-N.

### Past Learnings
- `ProgressObserver` protocol — any monitoring surface should implement it
- `PipelineExecutionLog` captures DAG topology, stage timings, retries — not plumbed to JSONL
- Cross-validate independently computed metrics (250M-value corruption cautionary tale)
- Per-stage DRC fence provides structured diagnostic output with stage attribution
- Router V6 profiling: scalar counters, one-shot logging guards, cProfile + per-stage attribution

### External Context
- DREAMPlace: logs HPWL, density, objective, gradient norm per iteration
- JAX RecordWriter pattern: pure JAX returns metrics dict; host-side logging handles side effects
- OpenTelemetry spans for pipeline stages; structlog for structured JSON logs
- RED method adapted as PED: Progress/Errors/Duration per iteration
- Manufacturing SPC (Western Electric rules) for drift detection

## Topic Axes
1. Data collection & metrics pipeline — What to measure, how to capture it, where to store it
2. Real-time visibility & dashboards — How to surface data during/after runs
3. Profiling & performance instrumentation — How to measure without slowing things down
4. Quality & correctness signals — DRC violations, convergence detection, constraint satisfaction
5. Operational health & alerting — Success/failure tracking, drift detection, CI integration

## Ranked Ideas

### 1. ProgressObserver-Backed Metrics Recording
**Description:** Implement `ProgressObserver` as the single write path to `pipeline_metrics.jsonl`. Every stage that emits observer events gets per-stage timings, completion %, DRC counts for free. Self-validates on write (asserts non-zero for fields that should never be zero). Includes stage-granular DRC deltas in StageEvent payload. Fixes the 96-zero-records bug at root cause.
**Axis:** Data collection & metrics pipeline
**Basis:** `direct:` 96 records with wall_time_ms=0; ProgressObserver protocol at dag_observability.py:12; PipelineExecutionLog captures stage timings but doesn't plumb to JSONL.
**Rationale:** Two parallel recording systems that disagree is the root cause. Single write path eliminates an entire class of drift bugs. Every future stage gets metrics for free.
**Downsides:** Touches DAG engine; existing ProgressObserver implementors need compatibility review.
**Confidence:** 90%
**Complexity:** Medium
**Status:** Unexplored

### 2. Structured Logging Context
**Description:** Bind `{board, git_commit, stage, iteration, run_id}` at pipeline start so every log line from any module carries it. Uses `structlog` or Python `LoggerAdapter`. DAG engine already knows topology at init — one-line addition.
**Axis:** Data collection & metrics pipeline
**Basis:** `direct:` dag_engine.py already has PipelineExecutionLog with topology at init. `external:` structlog bind-context-once pattern.
**Rationale:** Every future debugging session gets instant filtering. Error triage time drops from "find which run" (manual) to "the log line tells you" (instant).
**Downsides:** None significant; purely additive.
**Confidence:** 90%
**Complexity:** Low
**Status:** Unexplored

### 3. Metric Schema Registry
**Description:** Define `metrics_schema.yaml` declaring per-field: name, units, valid range, `zero_is_valid` flag, provenance, commit-introduced. Writer validates against schema; reader distinguishes "never populated before" from "just broke." The zero-bug would have been caught: `wall_time_ms` has `zero_is_valid: false`.
**Axis:** Data collection & metrics pipeline
**Basis:** `reasoned:` Plan 020 has schema versioning at record level but not per-field — too coarse to catch the zero-bug. `direct:` Current load_metrics() checks schema_version > CURRENT only.
**Rationale:** Adding a new metric drops from 30-min plumbing exercise to 30-sec schema entry. Registry is the single point of truth for what every number in JSONL means.
**Downsides:** Schema maintenance overhead; need versioning for backward compat.
**Confidence:** 80%
**Complexity:** Low
**Status:** Unexplored

### 4. Signal Injection Probe
**Description:** Inject canary metric `__pipeline_liveness__ = 42.0` at pipeline start that traverses the full recording path. At JSONL write time, assert the canary exists with correct value. If missing or wrong, emit `METRICS_PIPELINE_BROKEN` and refuse to write.
**Axis:** Data collection & metrics pipeline
**Basis:** `reasoned:` Oscilloscope calibration analogy — inject known signal, verify it appears undistorted at output. The zero-bug would have been caught on record 1.
**Rationale:** Catches instrumentation breakage at the earliest possible moment. 1-record latency instead of 96-record latency for detecting broken recording.
**Downsides:** Adds one extra field per record; small write-path overhead.
**Confidence:** 85%
**Complexity:** Low
**Status:** Unexplored

### 5. Live Pipeline Dashboard (NOT FOR CI — dev tool only)
**Description:** Wire ProgressObserver callbacks to push updates via WebSocket/SSE to session-dashboard SPA. Extend SPA with HPWL convergence plots, per-stage waterfall, DRC trend panels. Developer tool for interactive sessions.
**Axis:** Real-time visibility & dashboards
**Basis:** `direct:` ProgressObserver protocol exists; session-dashboard SPA exists; no connection.
**Rationale:** Multi-hour runs are a black box. Live visibility lets operators abort early on obvious failures.
**Downsides:** WebSocket adds moving part; headless CI can't use it.
**Confidence:** 85%
**Complexity:** Medium
**Status:** Explored (not for CI/CD)

### 6. Forensic Static Report
**Description:** Generate single self-contained HTML file from pipeline artifacts. No server, no npm. Renders full execution DAG, colors stages by status/duration, overlays contract violations, links DRC violations to source. Post-run autopsy report surfacing in CI artifacts.
**Axis:** Real-time visibility & dashboards
**Basis:** `direct:` session-dashboard SPA exists; CI artifacts exist; PipelineExecutionLog captures topology.
**Rationale:** Server-free dashboard. Shareable via CI artifacts. The report you attach to a Slack thread after a failed run.
**Downsides:** Static; no streaming. Complementary to live dashboard.
**Confidence:** 80%
**Complexity:** Low
**Status:** Unexplored

### 7. Ship Plan 015 PipelineProfiler
**Description:** Implement `PipelineProfiler` as pure aggregator over `PipelineExecutionLog` + `StageMeta.timings` — no new instrumentation. Add `TEMPER_PROFILE_JAX=1` flag for per-iteration HPWL/density/gradient via `jax.debug.callback` (zero overhead when off). Remove dead `temper-autoprof` scaffold. Generalize Router V6 scalar-counter pattern as reusable `@profiled` decorator.
**Axis:** Profiling & performance instrumentation
**Basis:** `direct:` StageMeta.timings auto-accumulates; Plan 015 unimplemented; temper-autoprof dead code; Router V6 patterns proven.
**Rationale:** Profiling becomes a reader of existing data, not a new instrumentation burden. Dead code removal reduces confusion.
**Downsides:** jax.debug.callback host-sync overhead when enabled; needs guardrails.
**Confidence:** 80%
**Complexity:** Medium-Low
**Status:** Unexplored

### 8. Double-Entry Cross-Validation Guard
**Description:** Every metric written to JSONL computed two independent ways, reconciled at write time. Primary: during execution. Secondary: from serialized output post-hoc. Mismatch → `CrossValidationError`. Extends naturally into stage-boundary contracts.
**Axis:** Quality & correctness signals
**Basis:** `direct:` 250M-value silent corruption cautionary tale; 96 zero-valued records. `reasoned:` Financial double-entry — every debit must balance with credit.
**Rationale:** Single highest-ROI defense against silent data lies. Both past corruption incidents would have been caught immediately.
**Downsides:** Requires secondary computation path per metric; adds write-path latency.
**Confidence:** 90%
**Complexity:** Low
**Status:** Unexplored

### 9. Contract Oracle — Stage-Boundary Invariants
**Description:** Each stage declares input/output invariants as assertable contracts. Pipeline proves contracts hold at every boundary; stops with structured violation report if not. `ProgressObserver.on_stage_error` is the hook point. Extends DRC fence from final stage to every inter-stage handoff.
**Axis:** Quality & correctness signals
**Basis:** `reasoned:` Extends DRC fence pattern to every boundary. Zero-bug caught at first boundary with "wall_time > 0" contract.
**Rationale:** Catches corruption at its source stage, not at the final DRC fence. Makes every stage transition a verified handoff.
**Downsides:** Each stage needs contract authoring; some stages have non-trivial invariants.
**Confidence:** 75%
**Complexity:** Medium
**Status:** Unexplored

### 10. Stage-Granular DRC Attribution
**Description:** Capture DRC violation count after each stage completes. Store `drc_delta_per_stage` in metrics record. Turns "DRC regressed, binary-search 8 stages" into "Stage 4 introduced 3 clearance violations" instantly.
**Axis:** Quality & correctness signals
**Basis:** `direct:` DRC fence already produces per-stage structured output with stage attribution. PipelineExecutionLog.events is per-stage — adding drc_snapshot is one field.
**Rationale:** Debugging time for DRC regressions drops from O(n) binary-search to O(1). Directly informs which team/tooling to debug.
**Downsides:** Requires running DRC after each stage (perf cost); mitigated by making it optional/CI-only.
**Confidence:** 90%
**Complexity:** Low
**Status:** Unexplored

### 11. Convergence Copilot — Auto-Early-Stop
**Description:** Sliding-window HPWL/density/violation flatline detection. All three flatline below threshold for N consecutive generations → self-termination with `CONVERGED` status + confidence score. Uses same scalar-counter pattern proven in Router V6.
**Axis:** Quality & correctness signals
**Basis:** `external:` DREAMPlace convergence curves. `direct:` scalar-counter patterns proven in Router V6.
**Rationale:** Saves wasted CI minutes on overspecified iteration counts. Key signal: "did the optimizer converge, stall, or diverge?"
**Downsides:** Flatline threshold tuning is domain-specific; needs per-board calibration data.
**Confidence:** 75%
**Complexity:** Medium
**Status:** Unexplored

### 12. SPC Control Charts with Western Electric Rules
**Description:** Replace simple threshold checks with SPC charts on 4-6 key metrics. Implement 4 Western Electric rules: (1) beyond 3sigma, (2) 2/3 beyond 2sigma, (3) 4/5 beyond 1sigma, (4) 8 consecutive on one side of center. Integrated into metrics-trend-check.yml and health-digest.yml.
**Axis:** Operational health & alerting
**Basis:** `reasoned:` Manufacturing SPC — gradual 98%→92% drift passes thresholds until catastrophic failure. Rule 4 catches on run 8. `direct:` metrics-trend-check.yml exists; 96 historical records available.
**Rationale:** Detects degradation before it becomes a hard failure. Critical for hardware-safety gates where quality drifts silently over weeks.
**Downsides:** SPC unfamiliar to most dev teams; needs rule-configuration per metric.
**Confidence:** 80%
**Complexity:** Medium
**Status:** Unexplored

### 13. SLO-as-Code — Declarative Regression Gates
**Description:** YAML file declaring per-stage SLOs: metric expression, threshold, evaluation window, severity (block/warn). CI computes against benchmark corpus on every PR. Extends 24-gate hardware-safety precedent to performance-safety.
**Axis:** Operational health & alerting
**Basis:** `direct:` 24 non-negotiable gates set CI-gating precedent. metrics-trend-check.yml and health-digest.yml exist. Plan 020 defines time-series tracking.
**Rationale:** 20% routing slowdown blocks merge immediately, not after a human notices. Closes the loop: metrics exist to feed automated decisions.
**Downsides:** Threshold tuning is time-consuming; false-positives block developer velocity.
**Confidence:** 80%
**Complexity:** Medium
**Status:** Unexplored

### 14. Per-PR Metrics Scorecard
**Description:** On every PR touching pipeline code, CI runs full pipeline on PR branch AND merge-base. Posts delta table as PR comment: HPWL%, wall-clock%, DRC error delta, per-stage timing deltas. Data from pipeline_metrics.jsonl.
**Axis:** Operational health & alerting
**Basis:** `direct:` metrics_recorder.py exists; ClosureResult has all fields; scripts/pipeline_metrics.py exists; Plan 020 U3/U4 unclear.
**Rationale:** Every PR author gets instant quantitative feedback. Reviewer sees impact before reading code. Delta history becomes searchable corpus of "which PR changed HPWL and by how much."
**Downsides:** 2x CI pipeline cost; requires baseline stability.
**Confidence:** 85%
**Complexity:** Medium
**Status:** Unexplored

### 15. Stage Health Cards — Persistent Logbooks
**Description:** Each stage gets persistent health card: `{stage, total_runs, success_rate, p50/p95/p99_ms, last_failure, drc_violations_this_week, trend}`. Cards persist alongside pipeline_metrics.jsonl. health-digest.yml surfaces them. Aviation logbook analogy.
**Axis:** Operational health & alerting
**Basis:** `reasoned:` Aviation maintenance logbooks — tracking hours, inspections, repairs makes months-scale drift visible before urgent. `direct:` health-digest.yml already synthesizes multiple CI signals.
**Rationale:** Months-scale routing degradation invisible without logbooks. health-digest surfaces "routing p95 trend: DEGRADING" before a gate fires.
**Downsides:** Another artifact to maintain; trend computation is fuzzy.
**Confidence:** 75%
**Complexity:** Low
**Status:** Unexplored

### 16. Compiler-Style Diagnostic Chains (NOT FOR CI — dev tool only)
**Description:** Extend DRC output into causal chains: `DRC: trace too close -> route-stage pass 3 -> constrained by U3 from placement iter 47`. Each link carries severity level. LLVM/clang analogy. Interactive debugging tool.
**Axis:** Quality & correctness signals
**Basis:** `reasoned:` LLVM diagnostic infrastructure — chains answer "why" not "what." `direct:` DRC fence already produces per-stage structured output.
**Rationale:** Current DRC says "what failed" not "why" or "which upstream decision caused it." Full provenance needed for hardware-safety decisions.
**Downsides:** Heavy; interactive-use only; CI can't action a diagnostic chain.
**Confidence:** 70%
**Complexity:** Medium
**Status:** Explored (not for CI/CD)

## Rejection Summary

| # | Idea | Reason Rejected |
|---|------|-----------------|
| - | Black-Box Crash Recorder | PipelineExecutionLog already covers most of this |
| - | Content-Addressed Run Archive | Whole-project-level infra investment |
| - | SCADA Telemetry Bus | Premature abstraction at current scale |
| - | PED-as-Primary | Scope overrun — changes pipeline identity |
| - | Exhaustive State Broadcast | Over-engineered; subset covered by dashboard |
| - | Observability Budget | Premature; need instrumentation first |
| - | Frame-Budget HUD | UX detail folded into dashboard |
| - | Inverse-Profiler | Complex; PipelineProfiler covers profiling more simply |
| - | Differential Pipeline Execution | 2x CI time; cross-validation + contracts provide similar protection |
| - | Fuzzing / Chaos Monkey | Heavy; follow-up once core system exists |
