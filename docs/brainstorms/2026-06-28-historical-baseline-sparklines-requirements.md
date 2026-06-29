# Brainstorm: Historical Baseline Watermarking + Margin-to-Failure Sparklines

**Date:** 2026-06-28

## Problem Statement

**Who:** Pipeline operators and PR authors looking at pipeline results.

**Problem:** Today's dashboard shows raw values — a `wall_time_ms` of 48723 is meaningless without knowing whether it's normal, fast, or dangerously slow. A 30% routing slowdown goes unnoticed. The sigma-based trend check catches severe drift weekly — but that's batch, not inline context per run.

**What changes:** Augment the planned HTML report (Plan 011 U7) and existing dashboard with: per-stage duration ratios against rolling historical percentiles, compact inline sparklines for DRC/placement/congestion metrics with threshold lines, and automated anomaly labeling.

## Existing Context

- **pipeline_metrics.jsonl**: 123 records, all-zero currently (broken path being fixed). Schema v1: `{schema_version, timestamp, git_commit, board, stage, module, metrics}`
- **pipeline_metrics.py**: `_compute_trends()` computes μ, σ, drift in sigma-multiples over sliding window
- **CI:** `metrics-record.yml` (records), `metrics-trend-check.yml` (weekly sigma drift check), `pr-perf-check.yml` (PR comparison)
- **Dashboard** (`dashboard/js/app.js`): Chart.js SPA with per-module line/bar charts. No sparklines, no baselines, no anomaly labels
- **Plan 011 U5**: SPC rules (Western Electric), rolling window, silent room activation — specified but no code written
- **What doesn't exist:** No sparkline rendering, no historical baseline computation beyond μ/σ, no auto-annotation, no `MetricsObserver` implementation

## Users & Use Cases

| Persona | Primary Use Case |
|---------|-----------------|
| Pipeline Operator (A1) | Opens HTML report — sees "routing: 2.1× p90" flagged red, DRC sparkline trending up, placement score 16% below median |
| PR Author (A2) | PR scorecard shows per-stage deltas against historical medians with inline context |
| Pipeline Maintainer (A4) | Weekly health-digest includes anomaly annotations providing leading indicators |

## Success Criteria

1. Per-stage durations displayed as ratios against historical p50/p90/p95 within one line of stage name
2. Sparklines for DRC violations, placement scores, congestion show last N=12 runs with red threshold line at p95
3. Anomaly auto-annotation triggers when metric is beyond 2σ or outside [p10, p90]
4. Cold-start: <5 runs shows "baseline building" with grey sparkline
5. Existing dashboard Chart.js rendering is preserved — sparklines are additive

## Approach 1: Python-Generated Static SVG Sparklines

**Description:** HTML report generator produces sparklines as inline SVG from Python. Anomaly annotations computed server-side. No JS needed — report is fully static.

**Pros:** Zero JS dependency. Works offline, in email, any browser. Deterministic.

**Cons / Risks:** SVG generation brittle to style changes. No interactivity. Only in static report, not live dashboard.

## Approach 2: Client-Side Sparklines in Chart.js Dashboard

**Description:** Extend `dashboard/js/app.js` with ~50-line canvas sparkline renderer in a new "per-stage health" panel. Anomaly annotations computed client-side from `allRecords[]`.

**Pros:** Single JS codebase. Interactive (hover shows values). Live data updates.

**Cons / Risks:** Canvas 24px height blurry on HiDPI. Flatlines until real data accumulates.

## Approach 3: Text-Only Watermark Labels (No Sparklines) — RECOMMENDED for v1

**Description:** Skip sparklines. Show per-stage text annotations: `placement → 2.1×p90 | Δ+16% | drc=0→3`. Works in HTML report, PR scorecard, dashboard tooltips. Near-zero rendering effort.

**Pros:** Works identically everywhere (text is universal). No rendering complexity. 80% of value at 20% of effort.

**Cons / Risks:** No visual trend detection. Users must read numbers across runs.

## Recommendation

**Approach 3 (Text-Only Watermark Labels) for v1**, with Approach 2 (Client-Side Sparklines) deferred to v2 when per-stage data exceeds ~20 runs. Text labels provide immediate value as soon as real data flows and are the lowest-integration-friction option across all three existing surfaces.

## Scope Boundaries

**In scope for v1:** Add `compute_percentiles()` to `pipeline_metrics.py`. Extend Plan 011 U7 report to annotate stage bars with watermark labels. Extend PR scorecard with delta columns. Add tooltip baselines to dashboard. Cold-start behavior (<5 runs → "baseline building").

**Deferred:** Client-side sparklines, SVG sparklines, natural-language annotation text ("16% slower than median"), SLO threshold sparklines

**Outside:** SPC rule implementation (Plan 011 U5), SLO definitions (Plan 011 U6), new JSONL schema changes
