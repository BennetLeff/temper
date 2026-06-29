---
date: 2026-06-28
topic: pipeline-visualization
focus: "visualization of the pipeline so it's easy to tell what's working, when how well, etc. connect to observability data once that's available and perf data too but start with just surfacing an up to date view of the entire temper pipeline"
mode: repo-grounded
---

# Ideation: Pipeline Visualization

## Grounding Context

### Codebase Context
- **Temper**: ESP32-S3 induction cooker. Placement pipeline: Placement (JAX NSGA-II) → Plane Generation → Routing (Router V6, 4-stage) → DRC fence.
- **Current state**: Two dashboards (`dashboard/` CI profiling, `session-dashboard/` agent sessions) but no unified pipeline overview. 114 all-zero records in `pipeline_metrics.jsonl` (broken recording path). `ProgressObserver` protocol exists with 6 lifecycle events but no `MetricsObserver`. `RichDashboard` is terminal-only. `session-dashboard/` SPA has Chart.js + dark theme but wired to agent data, not pipeline events.
- **Active plan**: Plan 011 targets a static HTML report. `PipelineExecutionLog.to_dict()` excludes events list.

### Past Learnings
- Existing pipeline-observability ideation (#5 Live Dashboard, #6 Static Report). Canonical requirements R7/R8 for static HTML report.
- **Critical**: `infrastructure-components-unwired` — 3 components built, tested, merged but never wired into pipeline. `session-dashboard/` SPA never connected to pipeline events.
- `ProgressObserver` is the intended hook. `PipelineExecutionLog.to_dict()` excludes events.

### External Context
- CI/CD DAG views (GitHub Actions, GitLab CI, CircleCI) as dominant pattern. Dagster asset graph strongest reference. Buildkite annotations pattern. ISA-101 "normal is boring" — gray nominal, color for anomalies. Static HTML + Mermaid DAG + D3 timeline recommended. Three-level hierarchy (overview → stage detail → root cause). PCB tools lack pipeline dashboards entirely.

## Topic Axes
1. Pipeline topology visual encoding — How to render placement → planes → routing → DRC as a scannable visual
2. Per-stage status & time representation — Visual encoding of stage health, progress, duration, performance
3. Quality & anomaly signal layering — How DRC violations, regressions, failures surface in the view
4. Navigation & drill-down design — Progressive disclosure from overview → stage → root cause
5. Delivery surface selection — Static HTML, live dashboard, terminal HUD, CI annotations, or multi-surface

## Ranked Ideas

### 1. Pipeline Andon Board — Manufacturing-Station DAG with ISA-101 Layering
**Description:** Each pipeline stage is a manufacturing "station" with an Andon light (green/yellow/red/grey), cycle-time ticker, and bottleneck glow. Healthy stations are gray and quiet; problems are the only things with color. ProgressObserver lifecycle events drive station state. Zero training — the metaphor is universal manufacturing literacy.
**Axis:** Pipeline topology visual encoding + Quality & anomaly signal layering
**Basis:** `external:` Toyota Andon + ISA-101 "normal is boring." `direct:` ProgressObserver's 6 events map directly to station states.
**Rationale:** A PCB designer sees 4 "stations" on an assembly line. Pre-attentive anomaly detection via color. The metaphor fits the physical-manufacturing nature of the product.
**Downsides:** Metaphor may feel forced to software engineers; needs consistent color discipline.
**Confidence:** 85%
**Complexity:** Low
**Status:** Explored

### 2. Historical Baseline Watermarking + Margin-to-Failure Sparklines
**Description:** Per-stage durations encoded as ratios against rolling historical baseline ("2.1× p90"). Inline sparklines show DRC violation counts, placement scores, and congestion over the last N runs with a red threshold line. Auto-annotation labels anomalies ("16% slower than median").
**Axis:** Per-stage status & time representation + Quality & anomaly signal layering
**Basis:** `direct:` pipeline_metrics.jsonl stores run records. `reasoned:` Raw durations uninterpretable without context; sparklines catch degradation before binary failure.
**Rationale:** Answers "is the pipeline getting slower?" and "how close are we to failing DRC?" — the two highest-signal pipeline questions.
**Downsides:** Requires fixing recording path first; needs historical data corpus (minimum ~20 runs); rolling baseline computation adds complexity.
**Confidence:** 80%
**Complexity:** Medium
**Status:** Explored

### 3. Live Terminal Pipeline Dashboard (`temper watch`)
**Description:** Rich Live animated terminal DAG. Stage panels pulse during execution, flash on completion, show live timers and sparklines. `temper watch` connects to CI or local pipeline. Three components already exist and are tested — they were just never wired together.
**Axis:** Delivery surface selection
**Basis:** `direct:` RichDashboard exists at `pipeline/visualization.py:141`, Rich supports `Live`/`Layout`, ProgressObserver fires lifecycle events. All 3 exist, tested, unwired.
**Rationale:** The target audience (PCB designers, firmware engineers) lives in terminals. Zero-friction: one command from current workflow.
**Downsides:** Terminal-only; no persistence for post-run review. Complementary to HTML report.
**Confidence:** 90%
**Complexity:** Low
**Status:** Explored

### 4. Self-Contained HTML Report as Canonical Artifact
**Description:** Single HTML file: Mermaid DAG at top, D3 timeline/waterfall, per-stage metrics tables, anomaly table. URL-fragment navigation (#stage=routing&baseline=run-42) makes every drill-down state shareable with ~30 lines of JS. CI artifact, Slack-shareable, digest-hashed.
**Axis:** Delivery surface selection + Navigation & drill-down design
**Basis:** `direct:` Plan 011 targets static HTML; R7/R8 specify contents. `external:` Single-file HTML + Mermaid + D3 + embedded JSON is the recommended architecture.
**Rationale:** Server-free, portable, Slack-shareable. The report you attach to a CI run page or send in Slack after a failed pipeline.
**Downsides:** Static (no streaming/live updates); CDN dependency for D3/Mermaid; JS-rendered content not searchable in CI artifact archives.
**Confidence:** 85%
**Complexity:** Medium
**Status:** Explored

### 5. Stage-Card Visual Grammar — One Design System, All Surfaces
**Description:** Each stage is a consistent "card" — status icon, duration bar, sub-stage summary, anomaly indicator. The grammar is a Python dataclass serialized to dict. Terminal Rich renders as panels; HTML renders as CSS grid; CI annotations render as sections. Write visual meaning once; render everywhere.
**Axis:** Pipeline topology visual encoding + Delivery surface selection
**Basis:** `reasoned:` A grammar defined once compounds — adding a surface becomes a renderer mapping, not a redesign. `external:` Buildkite annotations use structured output blocks that map to card-structured data.
**Rationale:** Adding a new pipeline stage propagates to all surfaces automatically. Adding a new surface is a renderer, not a redesign.
**Downsides:** Design upfront cost; cards must be flexible enough for different surface constraints (terminal width, CI annotation limits).
**Confidence:** 70%
**Complexity:** Medium
**Status:** Explored

### 6. Root-Cause Breadcrumb Trail
**Description:** Backward trace from failed stage through upstream artifacts: "DRC failed → Plane 3 overlapping pad U2-14 → placement at (12.7, 3.4) → netlist pitch constraint." Transforms "the pipeline is red" into "the pipeline is red because U2 was placed too close to the edge at iteration 47."
**Axis:** Navigation & drill-down design
**Basis:** `reasoned:` Multi-stage EDA failures notoriously difficult to attribute. Three-level hierarchy (overview → stage → root cause) is the Plan 011 recommended structure.
**Rationale:** Every minute an engineer spends bisecting pipeline stages is a minute the breadcrumb trail should have saved them.
**Downsides:** Requires pipeline to emit causal metadata (which stage decision caused which downstream problem); non-trivial instrumentation investment.
**Confidence:** 70%
**Complexity:** Medium-High
**Status:** Explored

## Rejection Summary

| # | Idea | Reason Rejected |
|---|------|-----------------|
| - | Multiple ISA-101/anomaly-coloring variants (5 frames produced this) | Merged into #1 Andon Board |
| - | Multiple static HTML report variants | Strongest synthesis is #4 |
| - | Multiple terminal dashboard variants | htop-style + RichDashboard variants merged into #3 |
| - | DAG-as-First-Class-Resource Model | Infrastructure enabler merged into #5 Stage-Card Grammar |
| - | Pipeline Diff Visualization, Auto-Annotation from Baselines | Merged into #2 Historical Baseline |
| - | Billboard Single-Scroll, Mermaid-in-Markdown | UX/format details covered by #4 HTML Report |
| - | Subway Line Map, Cricket Scoreboard, ATC Radar, Patient Flow Board, Shipment Tracking, OEE Triptych | Cross-domain analogies; Andon Board (#1) strongest fit for manufacturing product |
| - | Data-Flow Narrative (transformation story) | Clever but narrow audience; supplementary to primary DAG view |
| - | Code-Annotation Layer (pipeline perf inline in source) | Niche audience, premature for v1 |
| - | Semantic Layer (cooking-metaphor topology) | Dual labeling risks confusion for primary audience (engineers) |
| - | Role-Parameterized Pipeline Views | 3 lens modes add complexity; premature for single-team pipeline |
| - | Temporal Microscope (sub-stage event animation) | Requires sub-stage instrumentation not yet available |
| - | PR-Embedded Pipeline Topology Diff | Too narrow — only fires on DAG shape changes, not performance |
| - | Ambient Pipeline Health (git status, commit checks, Slack) | Partial overlap with #3 (terminal) and #4 (CI annotations) |
| - | Pairwise Stage-Delta Heatmap Across All Runs | Niche diagnostic tool; not the primary pipeline view |
| - | Temporal Topology (scrollable history) | Overlaps with time-series aspect of #2 |
| - | CI Job Summary as Primary Pipeline Surface | #4 (HTML artifact) + CI annotation embedding covers this |
| - | Duration-Encoded Pipeline Score Layout | Novel but questionable readability when stage durations vary |
| - | Negligence-First Coloring (nothing renders unless broken) | Too extreme; ISA-101 gray nominal maintains visual presence |
| - | Git-Diff Native (pipeline reports as version-controlled) | Clever but narrow; #4 HTML report is more shareable |
