---
title: "Unified CI Profiling Platform Architecture — Canonical Metrics Contract Pattern"
date: "2026-06-28"
category: architecture-patterns
module: CI
problem_type: architecture_pattern
component: development_workflow
severity: medium
applies_when:
  - Multiple profiling subsystems need to coexist in CI, each emitting structured performance data
  - Profiling systems are developed incrementally across multiple sprints and need to participate in CI observability from day one
  - Adding new profilers should require only an adapter method, not new CI workflows or storage files
tags:
  - profiling
  - ci
  - jsonl
  - metrics
  - pipeline-metrics-record
  - time-series
---

# Unified CI Profiling Platform Architecture

## Context

The temper-placer project had three profiling dimensions evolving independently — pipeline closure tests, JAX loss function microbenchmarks, and router corpus benchmarks — each with its own output format, its own CI step, and its own ad-hoc aggregation. There was no way to compare PR performance against historical main-branch data, detect drift across all profiling dimensions from a single query, or render a unified dashboard. Three implementation plans (010, 015, 022) converged on a single architectural pattern: designate a canonical metrics contract and make every profiling subsystem adapt to it.

## Guidance

### The Canonical Contract: `PipelineMetricsRecord`

All profiling output is emitted as a `PipelineMetricsRecord` dataclass with four routing fields and an open `metrics` dict:

| Field   | Purpose |
|---------|---------|
| `module` | Namespace for routing: `pipeline`, `loss-fn`, `router-bench`, `pipeline-timing`, `autoprof`, `firmware` |
| `board`  | Board identifier (e.g., `temper`, `piantor`, `all`) |
| `stage`  | Granularity within a module (e.g., `closure`, `loss-fn`, `benchmark`, or an individual pipeline stage name) |
| `metrics` | Open `dict[str, float]` — each module defines its own metric keys |

Every record is appended to a single JSONL file (`power_pcb_dataset/metrics/pipeline_metrics.jsonl`), creating one append-only time-series store for the entire project.

### The Adapter Pattern

Each profiling system implements a `to_pipeline_metrics_record()` method — or, alternatively, pushes records directly through an observer:

```
Profiling System              Adapter / Observer                         Canonical Store
─────────────────            ───────────────────────                    ────────────────
MetricsObserver          →  Push-based (on_stage_complete             ┐
                            creates PipelineMetricsRecord directly)   │
PipelineProfiler         →  ProfileReport.to_pipeline_metrics_record()├→ pipeline_metrics.jsonl
TimingResult             →  TimingResult.to_pipeline_metrics_record() ┤
AutoprofReport           →  AutoprofReport.to_pipeline_metrics_record()┘
StageTimingEntry         →  StageTimingEntry.to_pipeline_metrics_record()
```

`MetricsObserver` implements ProgressObserver and writes per-stage records (wall_time, success, drc_delta) directly into the canonical store during pipeline execution — no adapter needed. This is the primary write path for pipeline observability; the `--from-stdin` path serves profiling subsystems that run independently.

### The `--from-stdin` Pipeline

Profiling modules produce NDJSON on stdout (`temper profile run --module all --json`). Shell pipes feed that output into `pipeline_metrics.py record --from-stdin`, which deserializes each line into a `PipelineMetricsRecord` and appends to the canonical file:

```yaml
- name: Profile router benchmarks
  continue-on-error: true
  run: |
    uv run temper profile run \
      --module router-bench --commit "${{ github.sha }}" --json \
      | uv run python scripts/pipeline_metrics.py record \
          --board temper --commit "${{ github.sha }}" --from-stdin
```

### Multi-Module CI Topology

All consumers read a single file:

```
                                pipeline_metrics.jsonl
                                        │
           ┌────────────────────────────┼────────────────────────────┐
           │                            │                            │
           v                            v                            v
 metrics-trend-check.yml         pr-perf-check.yml           dashboard-deploy.yml
 (weekly drift detection,        (rolling-window median      (copy JSONL → gh-pages,
  per module/board/stage)         comparison vs main)         Chart.js per-module view)
```

Adding a new profiling dimension requires only: define a `module` string, implement `to_pipeline_metrics_record()`, emit NDJSON to `--from-stdin`, and add a render function to `app.js`. No new CI workflows, no new storage files.

## Why This Matters

**Single source of truth.** All profiling data — closure wall-clock, JAX loss timings, router p95 latency, per-stage pipeline timing, autoprof delta tables — lives in one JSONL file. Every CI consumer reads that same file. There is no per-module silo, no format negotiation between systems.

**Zero new CI workflow for new dimensions.** Adding `pipeline-timing` in Plan 022 required only a new `to_pipeline_metrics_record()` adapter — the existing `record --from-stdin` pipeline, trend-check infrastructure, and dashboard consumed the new module automatically.

**Backwards compatibility without migration.** `load_metrics()` fills in `module="pipeline"` for pre-Plan-010 records that lack the field. Schema versioning allows forward/backward compatibility — future schema versions are skipped with a warning, not rejected.

**Git-native time-series.** JSONL stored in the repo means every commit carries its profiling snapshot. No external database, no retention policy. `git log -- power_pcb_dataset/metrics/pipeline_metrics.jsonl` is the audit trail.

## When to Apply

Apply when a project has **multiple independent profiling dimensions** being built incrementally across sprints, and each needs to participate in CI observability from day one without rebuilding the storage layer.

Do NOT apply when data volume exceeds what's reasonable for a git-tracked file (hundreds of thousands of per-run micro-timing records), or when the profiling system has real-time streaming requirements. JSONL is append-only and read via full-scan.

## Examples

### Adapter: TimingResult → PipelineMetricsRecord

```python
class TimingResult:
    board_id: str
    pipeline: str
    stage_name: str
    wall_ms: float

    def to_pipeline_metrics_record(self) -> PipelineMetricsRecord:
        return PipelineMetricsRecord(
            board=self.board_id,
            stage=self.stage_name,
            module="pipeline-timing",
            metrics={
                "wall_ms_mean": self.wall_ms,
                "n_runs": self.n_runs,
                "wall_ms_min": min(self.individual_ms),
                "wall_ms_max": max(self.individual_ms),
            },
        )
```

### Adapter: ProfileReport → PipelineMetricsRecord

```python
class ProfileReport:
    stage_timings: dict[str, StageTiming]

    def to_pipeline_metrics_record(self, board, stage, module="profiler") -> PipelineMetricsRecord:
        metrics = {}
        for name, timing in self.stage_timings.items():
            metrics[f"{name}_wall_ms"] = round(timing.wall_time_ms, 3)
            for sub_name, sub in timing.sub_steps.items():
                metrics[f"{name}_{sub_name}_ms"] = round(sub.wall_time_ms, 3)
        return PipelineMetricsRecord(board=board, stage=stage, module=module, metrics=metrics)
```

### Dashboard: Module-routed rendering

```javascript
// Single JSONL fetch filtered by module field
async function loadData() {
    const response = await fetch('./pipeline_metrics.jsonl');
    allRecords = (await response.text()).trim().split('\n')
        .map(line => JSON.parse(line));
}

function switchModule(module) {
    currentModule = module;
    renderModule();  // filters allRecords by r.module === currentModule
}
```

### PR Comparison: Rolling-window median baseline

```python
def load_main_baselines(records, window=5):
    groups = {}
    for r in records:
        key = (r.get("module"), r.get("board"), r.get("stage"))
        groups.setdefault(key, []).append(r)
    for key, group in groups.items():
        group.sort(key=lambda r: r.get("timestamp", ""))
        recent = group[-window:]  # last N entries from main branch
    # compute per-metric median → baseline
```

## Related

- `docs/plans/2026-06-28-010-feat-ci-profiling-regression-platform-plan.md` — Plan 010 (foundation: PipelineMetricsRecord, multi-module CI)
- `docs/plans/2026-06-22-015-feat-pipeline-profiling-validation-toolkit-plan.md` — Plan 015 (PipelineProfiler, Hypothesis PBT, golden fixtures)
- `docs/plans/2026-06-22-022-feat-per-stage-timing-regression-gate-plan.md` — Plan 022 (per-stage timing gate, CI ancestry check)
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — structural CI gate enforcement pattern (evolved by this platform)
