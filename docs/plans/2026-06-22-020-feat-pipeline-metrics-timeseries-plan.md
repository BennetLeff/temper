---
date: 2026-06-22
type: feat
origin: docs/ideation/2026-06-22-test-and-build-next-ideation.md
status: active
---

# Plan: Pipeline Quality Metrics Time-Series & Trend Detection

## Problem Frame

Closure tests and CI gates produce per-PR quality metrics (completion rate, DRC errors, wall-clock time, placement iterations) but discard them after pass/fail. No time-series view answers the question: **"Is decomposition actually making the pipeline better?"**

The data is already computed—`ClosureResult` fields and GPBM `measurements.jsonl` entries carry the numbers—but nothing persists them across CI runs. One JSONL append per CI run is near-zero cost and turns gut-feel quality assessments into data.

This plan adds three things: (1) a metrics-recording step in CI that appends structured records, (2) a `temper metrics trend` CLI to query regressions, and (3) a weekly drift-detection job that flags metrics moving >1σ from the trailing 30-day window.

## High-Level Technical Design

```
CI Run                         Weekly CI Job
┌───────────────────┐          ┌──────────────────────┐
│ closure_test.py   │          │ trend_check.py       │
│   │               │          │                      │
│   ▼               │          │ load pipeline_       │
│ ClosureResult ────┤          │   metrics.jsonl      │
│   │               │          │                      │
│   ▼               │          │ per-board/stage      │
│ pipeline_metrics  │          │ sliding 30d window   │
│   .py append ─────┤          │                      │
│   │               │          │ flag if >1σ drift ───┤─► Slack / issue
│   ▼               │          │                      │
│ pipeline_metrics  │          └──────────────────────┘
│   .jsonl (commit) │
└───────────────────┘
```

*Directional guidance for review, not implementation specification.*

## Output Structure

```
power_pcb_dataset/metrics/
    .gitkeep                           # keep dir tracked
    pipeline_metrics.jsonl             # append-only time-series
scripts/pipeline_metrics.py            # CLI: temper metrics trend
packages/temper-placer/src/temper_placer/regression/
    metrics_recorder.py                # record() from ClosureResult
.github/workflows/
    metrics-record.yml                 # per-PR append step
    metrics-trend-check.yml            # weekly drift check (cron)
```

## Requirements

### R1. Append metrics on each passing CI run
- **R1.1.** On every PR merge (or push to main), after closure test passes, append one JSONL line to `power_pcb_dataset/metrics/pipeline_metrics.jsonl`.
- **R1.2.** Each line schema:
  ```json
  {"schema_version": 1, "timestamp": "...", "git_commit": "abc1234", "board": "temper", "stage": "closure", "metrics": {"completion_pct": 98.5, "drc_errors": 0, "drc_warnings": 2, "wall_time_ms": 42000, "benders_iterations": 12, "benders_cuts": 5}}
  ```
- **R1.3.** The file is committed and pushed to the repo; CI appends, commits, and pushes back.

### R2. `temper metrics trend` CLI
- **R2.1.** Subcommand under the existing `temper` CLI (or `temper-placer`/`temper-tools` depending on CLI host package).
- **R2.2.** `temper metrics trend --board <id> --stage <stage> --window 30d` prints a table and exit code for regression.
- **R2.3.** Computes mean μ and σ over the trailing window. Flags any metric whose current value is outside [μ - kσ, μ + kσ] (k=1 default, configurable with `--sigma-multiple`).
- **R2.4.** Outputs JSON with `--json` flag for scripting.
- **R2.5.** `temper metrics trend --list` shows available boards and stages in the JSONL.

### R3. Weekly CI drift check
- **R3.1.** Scheduled workflow (cron: weekly) runs `temper metrics trend --json` across all boards/stages.
- **R3.2.** If any metric drifts >1σ, workflow creates a GitHub issue with the drift details.
- **R3.3.** Drift threshold is configurable via workflow input (`sigma_multiple`, default 1.0).

### R4. Schema versioning
- **R4.1.** `schema_version` field in each JSONL line. Current schema = 1.
- **R4.2.** Reader code validates schema_version and skips unknown future versions with a warning.
- **R4.3.** Adding a field increments minor version; removing/renaming fields increments major version with a migration note in the file header.

## Scope Boundaries

### In scope
- Per-PR metrics record step in CI
- `pipeline_metrics.jsonl` in `power_pcb_dataset/metrics/`
- `temper metrics trend` CLI with sliding-window μ/σ regression detection
- Weekly cron CI job for drift alerting
- Schema versioning in the record format
- `ClosureResult` → JSONL adapter (metrics_recorder.py)

### Deferred
- Dashboard visualization (Grafana, Datadog) — data format designed to feed dashboards, but no UI
- Per-stage micro-metrics (Stage 2 sub-steps, router internal phases) — infrastructure supports it via the `stage` field, but Stage 2 decomposition gating metrics is separate work
- Machine-learning anomaly detection (beyond μ/σ)
- Auto-rollback on regression (just alert for now)

### Out of scope
- Replacing GPBM `measurements.jsonl` — this is a separate pipeline-metrics stream, not a replacement
- Historical backfill from closed PRs
- Cross-repo metrics aggregation

## Implementation Units

### U1. Metrics Recorder

**Goal:** Adapt `ClosureResult` into JSONL lines and provide a `record()` function callable from closure test CI.

**Dependencies:** None

**Files:**
- Create: `packages/temper-placer/src/temper_placer/regression/metrics_recorder.py`
- Modify: `packages/temper-placer/src/temper_placer/regression/closure_test.py` (optional export of metrics dict)
- Create: `power_pcb_dataset/metrics/.gitkeep`

**Approach:**
- `PipelineMetricsRecord` dataclass with `to_jsonl()` method
- `record_closure_result(result: ClosureResult, board_id: str, commit: str)` helper
- `load_metrics(filepath: Path) -> list[dict]` reader that validates schema_version
- Schema version 1 fields: `timestamp` (ISO 8601), `git_commit` (short SHA), `board` (str), `stage` (str), `metrics` (dict of numeric values)
- Derive `wall_time_ms` from `ClosureResult.wall_clock_seconds`

**Patterns to follow:** `temper_workflow/gpbm/measure.py:MeasurementResult.to_jsonl()` for JSONL format; `ClosureResult` dataclass already has all needed fields

### U2. CLI: `temper metrics trend`

**Goal:** Add `metrics trend` subcommand to the Temper CLI for regression querying.

**Dependencies:** U1 (for `load_metrics`)

**Files:**
- Create: `scripts/pipeline_metrics.py` (standalone CLI entrypoint), OR
- Modify: existing CLI host package to add `metrics` command group with `trend` subcommand

**Approach:**
- Determine CLI host: `bd` or `temper-placer` or `temper-tools`. Check which package owns the CLI entrypoint. If `temper-tools`, add a `metrics` group there; otherwise create `scripts/pipeline_metrics.py` as a standalone script.
- `trend` subcommand:
  - Parse `pipeline_metrics.jsonl` with `load_metrics()`
  - Filter by `--board`, `--stage`, `--window` (e.g., `30d`, `7d`, `90d`)
  - For each metric key: compute μ and σ over window, compare latest value
  - Print table: metric name, latest value, μ, σ, drift (σ multiples), status (OK/WARN/REGRESSION)
  - Exit code 0 if no regressions, 1 if any metric drifted >1σ
- `--json` flag outputs structured JSON with full statistics
- `--list` flag prints unique (board, stage) pairs in the JSONL

**Patterns to follow:** `temper_drc/cli.py` Click command groups; `temper_workflow/gpbm/measure.py` JSONL parsing

### U3. CI Workflow: Metrics Record Step

**Goal:** Hook into the existing PR/push CI to append metrics after a passing closure test.

**Dependencies:** U1

**Files:**
- Create: `.github/workflows/metrics-record.yml` OR modify existing CI workflow to add a step

**Approach:**
- Since no `.github/workflows/` directory exists yet, create the directory and add a workflow.
- Alternative: add a step to the existing CI pipeline (if one exists in a non-standard location). Search for existing CI configuration (tox.ini, Makefile targets, CI scripts in `scripts/`).
- Workflow trigger: on push to `main` (post-merge) or on workflow_call from PR CI.
- Steps:
  1. Checkout repo with full history
  2. Run closure test (or reuse artifact from PR CI)
  3. Run `python scripts/pipeline_metrics.py record --board ... --commit $GITHUB_SHA`
  4. Commit and push `pipeline_metrics.jsonl` back to repo
- Handle concurrent pushes: use `git pull --rebase` before push; retry on conflict

**Patterns to follow:** Standard GitHub Actions workflow format; `git-auto-commit-action` for automated commits

### U4. CI Workflow: Weekly Trend Check

**Goal:** Scheduled cron job that runs trend analysis and creates issues on drift.

**Dependencies:** U2, U3

**Files:**
- Create: `.github/workflows/metrics-trend-check.yml`

**Approach:**
- Cron trigger: `0 8 * * 1` (Monday 8 AM UTC)
- Steps:
  1. Checkout repo
  2. Run `python scripts/pipeline_metrics.py trend --json --window 30d`
  3. If exit code != 0, parse JSON output for regressed metrics
  4. Use `gh issue create` to file an issue with title "Metrics drift detected: {board}/{stage}" and body containing the drift table
- Threshold defaults: 1σ, configurable via `SIGMA_MULTIPLE` workflow input

### U5. Schema Versioning + Tests

**Goal:** Ensure forward/backward compatibility of the JSONL format.

**Dependencies:** U1

**Files:**
- Modify: U1 files to include `schema_version` field
- Create: `packages/temper-placer/tests/test_metrics_recorder.py`
- Create: `packages/temper-placer/tests/test_metrics_trend.py` (integration test for trend CLI)

**Approach:**
- `schema_version: 1` in every line
- `load_metrics()` skips lines with unknown major versions, warns on unknown minor versions
- Tests:
  - `test_record_to_jsonl()` — roundtrip ClosureResult → JSONL → parsed dict
  - `test_schema_version_skip_future()` — lines with schema_version 99 are skipped with warning
  - `test_trend_computes_mu_sigma()` — known window produces correct statistics
  - `test_trend_flags_regression()` — outlier outside 1σ triggers exit code 1
  - `test_trend_no_regression_stable()` — in-range values produce exit code 0

**Patterns to follow:** `test_state_machine_only.c` for test organization pattern; use `pytest` with fixtures for JSONL test data

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Concurrent main-branch pushes cause JSONL merge conflicts | CI uses `git pull --rebase` with retry; JSONL append-only means conflicts are always resolvable |
| JSONL file grows unboundedly | Weekly cron can archive lines older than 90 days to `pipeline_metrics_archive/YYYY-QN.jsonl` (deferred until file exceeds 10k lines) |
| Schema drift breaks trend CLI | `schema_version` field + skip-unknown policy in reader |
| Closure test not wired into CI yet | U3 should detect and use whatever CI already runs the closure test; if none, add a workflow_call trigger |

## CI Soft-Launch Plan

- **Week 1:** Ship U1 + U2 (metrics recorder + trend CLI). Run record step in CI but do not gate on it. Manual `temper metrics trend` available.
- **Week 2:** Enable U4 (weekly drift check) with issue creation but no Slack ping.
- **Week 3:** Full activation. Weekly drift issues auto-filed. Add `temper metrics trend` exit code to the merge gate (soft: warning only).
- **Week 4+:** After 30 days of data in JSONL, make trend check a hard merge gate for metrics that have sufficient history (≥14 data points).
