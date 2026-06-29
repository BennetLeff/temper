# Brainstorm: Self-Contained HTML Report as Canonical Artifact

**Date:** 2026-06-28

## Problem Statement

**Who:** Pipeline operators and PR authors need to answer "what happened in this run?" without manually inspecting `closure-result.json` or `pipeline_metrics.jsonl`. No human-readable per-run artifact exists. A pipeline operator who sees CI red must dig through raw JSONL to diagnose which stage degraded.

**What changes:** A single `.html` file is generated per pipeline run from `pipeline_metrics.jsonl` + `PipelineExecutionLog`, published as a CI artifact, and becomes the canonical post-run artifact — shareable via Slack URL, digest-hashed, and drill-down-navigable via URL fragment.

## Existing Context

- **Plan 011 (U7):** Active. `scripts/pipeline_report.py` does not exist yet. Design intent: Python script, inline CSS/JS, no CDN, session-dashboard design reference
- **R7/R8 (requirements):** Static HTML report per run, CI artifact. DAG timeline color-coded (green/yellow/red against historical p95), per-stage breakdown, DRC summary, HPWL convergence curve
- **PipelineExecutionLog.to_dict():** Excludes events list. Has `dag_topology`, `stage_order`, `stage_timings`, `retry_counts`, `feedback_activations`, `success`, `total_duration_s`
- **Session-dashboard:** Dark theme CSS variables (`--surface: #0d1117`, `--accent: #58a6ff`, `--success: #3fb950`, `--warning: #d29922`, `--error: #f85149`). Chart.js CDN. DOM-based rendering
- **Dashboard/:** CI Profiling SPA, same dark theme, Chart.js per-module charts, 7/30/90-day filter
- **Mermaid/D3:** Neither exists in the project. Only charting CDN is Chart.js@4
- **CI artifacts:** Currently only JSON (`regression-report`, `closure-result`). No HTML artifacts published
- **URL-fragment navigation:** No existing pattern in any project HTML

## Users & Use Cases

| Persona | Primary Use Case |
|---------|-----------------|
| Pipeline Operator (A1) | Opens CI artifact → DAG timeline shows stage durations vs historical p95, DRC pass/fail. Shares `#stage=routing&baseline=run-42` |
| PR Author (A2) | Before merge, opens report from PR scorecard comment → drills into per-stage timing delta |
| Pipeline Maintainer (A4) | Downloads 20-run corpus, diff-renders HPWL convergence curves |
| Slack reader | Clicks digest-hashed artifact URL → 15-second situational awareness |

## Success Criteria

1. **30-second comprehension:** Operator answers "what ran, how long, DRC status" within 30 seconds
2. **Self-contained portability:** Single `.html` file opens in any browser — no server, no CDN, no `file://` CORS issues
3. **Drill-down shareability:** `#stage=routing` in URL selects that stage; paste into Slack reproduces exact view
4. **CI artifact integration:** Report uploaded on every push to main; accessible from GH Actions run page
5. **Cold-start graceful:** First run renders with "baseline building" indicator

## Approach 1: Inline Canvas Renderer with Chart.js Bundled — RECOMMENDED

**Description:** Single `.html` with all CSS/JS inlined. Timeline as horizontal `<div>` bars with duration-proportional width. HPWL convergence on Chart.js (bundled inline, ~70KB). DAG as CSS grid. URL fragment navigation (~30 lines JS). Data embedded as `<script>window.__PIPELINE_DATA__</script>`.

**Pros:** Fully self-contained. Matches Plan 011 design intent. Reuses Chart.js expertise. ~400 lines Python + ~250 lines HTML/CSS/JS.

**Cons / Risks:** Chart.js ~70KB blob. No Mermaid DAG (CSS grid is linear/waterfall, confirmed appropriate for linear pipeline).

## Approach 2: Python-Generated SVG + Pure Canvas

**Description:** Same structure but hand-roll a ~100-line canvas line-plotter instead of bundling Chart.js. SVG sparklines generated server-side.

**Pros:** Truly zero external dependency. Even smaller file size.

**Cons / Risks:** Canvas line-plotters tedious to debug. Duplicates what Chart.js already provides well.

## Approach 3: Two-Layer Architecture (Report-as-API, Inversion)

**Description:** Split into JSON artifact (`run-summary.json`) + static viewer SPA on GitHub Pages. Report URL = `https://.../?run=<artifact-url>`. Full Chart.js + Mermaid CDN.

**Pros:** Zero HTML generation in CI. Visual quality unbounded. Evolution decoupled.

**Cons / Risks:** Breaches R7 "self-contained" requirement. GitHub artifacts require auth. JSON schema evolution adds maintenance.

## Recommendation

**Approach 1** — single `.html` with Chart.js bundled inline. Satisfies R7. Reuses existing Chart.js dark-theme configuration from `dashboard/js/charts.js`. DAG stays CSS grid (pipeline is linear). URL fragments are trivial. Approach 3 is the right long-term direction if the team revisits the "static over live" decision.

## Scope Boundaries

**In scope for v1:** `scripts/pipeline_report.py`, CSS-grid DAG timeline + color-coding, per-stage breakdown table, DRC violation summary, Chart.js HPWL curve, URL fragment navigation (`#stage=routing`), digest-hashed filename, CI artifact upload in `metrics-record.yml`

**Deferred:** Mermaid DAG (until topology becomes non-linear), cross-run baseline selector, `PipelineProfiler` HPWL wiring, browser screenshot comparison

**Outside:** Live WebSocket dashboard, PR scorecard delta (separate feature), SPC/SLO gate integration
