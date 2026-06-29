# Brainstorm: Pipeline Andon Board — Manufacturing-Station DAG with ISA-101 Layering

**Date:** 2026-06-28

## Problem Statement

**Who:** E.E. engineers and ECAD integrators running temper-placer pipelines (non-deterministic 8-stage manufacturing workloads—10–60 minute runs).

**Problem today:** The pipeline runs as a black box. Terminal ASCII (`RichDashboard`) and a post-hoc JSON log tell you what happened, but only after the fact. During execution, you see phase labels and loss sparklines—but no spatial intuition for where the work is, what's stuck, or what just failed and why.

**What changes:** An Andon board renders the pipeline as a row of manufacturing stations. "Normal is gray and quiet" (ISA-101). Only problems get color. Zero training—the metaphor maps to universal factory-floor literacy.

## Existing Context

- **ProgressObserver protocol** (`dag_observability.py:12-22`): 6 lifecycle events map directly to station states (on_stage_start=active, on_stage_error=red light, on_feedback_triggered=yellow glow)
- **PipelineExecutionLog** (`dag_observability.py:40-59`): Stores topology (`dag_topology`), stage order, per-stage durations, retry counts, feedback history, events list — but `to_dict()` excludes events
- **Pipeline topology**: 8 stages: INPUT → SEMANTIC → TOPOLOGICAL → PREFLIGHT → GEOMETRIC → ROUTING → REFINEMENT → OUTPUT, with feedback contracts (routability-retry)
- **RichDashboard** (`visualization.py`): Terminal-only, Rich Panel/Table/sparkline. Not wired to ProgressObserver
- **Session-dashboard SPA**: Vanilla JS + Chart.js, dark theme, tabbed layout. Wired to agent session data, not pipeline events. CSS variables: `--accent: #58a6ff`, `--success: #3fb950`, `--warning: #d29922`, `--error: #f85149`
- **BottleneckReport**: Structured bottleneck data with regions, congestion heatmaps, failed nets — provides the "bottleneck glow" signal

## Users & Use Cases

| Persona | Primary Use Case |
|---------|-----------------|
| E.E. engineer running placement | Glances at Andon board every few minutes during a 20-minute run. Wants to know: is it alive? Which stage? Anything fail? |
| ECAD integrator debugging | Opens post-hoc Andon from saved `pipeline_execution.json`. Sees which stage failed, how long it ran, whether feedback retriggers fired |
| CI watcher | Nightly regression Andon showing per-stage health across all golden boards |

## Success Criteria

1. **Station-state fidelity**: All 6 ProgressObserver events map to correct visual states (idle/active/done/skip/error) with zero missed events
2. **Zero-training comprehension**: Engineer unfamiliar with temper correctly identifies running stage, failed stage, and active feedback loops — within 5 seconds
3. **ISA-101 "normal is boring"**: Healthy stations are gray/neutral. Only active (green), warning/retrigger (yellow), and error (red) get color
4. **Post-hoc playback**: Board renders correctly from a saved `pipeline_execution.json` alone (no live pipeline needed)
5. **Session-dashboard visual consistency**: Uses the same CSS custom properties, dark theme, and component conventions

## Approach 1: Pure Python HTTP Server (SSE Andon)

**Description:** `AndonBoard` observer implements `ProgressObserver` and runs a tiny HTTP server. Each lifecycle event updates in-memory station state. SSE pushes updates to a static HTML page. Post-hoc mode replays events from `pipeline_execution.json`.

**Pros:** Single Python module integrates directly with `StageDAGEngine.add_observer()`. SSE is simple.

**Cons / Risks:** HTTP server lives inside pipeline process; pipeline crash kills the board. SSE reconnection adds complexity.

## Approach 2: File-Watch Andon (Sidecar JSON + Static SPA) — RECOMMENDED

**Description:** `AndonObserver` writes station state to a continuously-updated JSON sidecar file. A fully static SPA reads this file via `fetch()` polling (250ms). Post-hoc mode: same SPA loads the completed execution log. No server dependency.

**Pros:** Zero runtime dependency between browser and pipeline. Works offline (file://). Post-hoc == live (same JSON format). Can inspect file with `cat` or `jq`.

**Cons / Risks:** 1s polling is coarse for fast stages. `PipelineExecutionLog.to_dict()` must include events.

## Approach 3: Dagster-Inspired Asset Graph (Inversion)

**Description:** Render pipeline as live-updating DAG node graph (Dagster-style asset lineage). Each stage is a node; edges show data flow. Node fill color encodes status.

**Pros:** Leverages existing `dag_topology` data. Familiar to data engineers.

**Cons / Risks:** DAG layout harder to render than linear station row. Pipeline is linear — DAG view is over-engineered.

## Recommendation

**Approach 2 (File-Watch Andon)** with polling granularity mitigation (250ms interval, detect state transitions from event list rather than catching every state). ~80 lines Python observer + ~200 lines HTML/CSS.

## Scope Boundaries

**In scope for v1:**
- `AndonObserver` Python class implementing `ProgressObserver`, writing incremental `pipeline_execution.json`
- Single HTML page rendering 8 stations as horizontal row: station name, Andon light, cycle-time ticker
- Post-hoc playback. Bottleneck glow on ROUTING when feedback contracts fire. Auto-refresh at 250ms

**Deferred:** Multiple-pipeline aggregation, interactive drill-down, WebSocket/SSE server, DAG graph view, mobile-responsive layout

**Outside:** Modifying pipeline engine, replacing RichDashboard, fixing pipeline_metrics.jsonl zero-records
