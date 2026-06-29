# Brainstorm: Stage-Card Visual Grammar — One Design System, All Surfaces

**Date:** 2026-06-28

## Problem Statement

**Who:** PCB designers and firmware engineers running the Temper pipeline. They have three disconnected visualization surfaces (terminal Rich, web session-dashboard, CI profiling dashboard) that each encode pipeline stage information differently. Adding a new pipeline stage requires touching every surface's rendering code independently.

**What changes:** A single Python dataclass — the "grammar" — serialized to dict, with surface-specific renderers (Rich panels, CSS grid, CI annotation blocks) reading from the same grammar. Write visual meaning once; render everywhere.

## Existing Context

- **RichDashboard** (`visualization.py`): Uses Rich `Panel`/`Layout`/`Table`. No card concept. `ProgressCallback` has 4 events — misses skip/error/feedback present in `ProgressObserver`
- **ProgressObserver** (`dag_observability.py`): 6 events. `StageEvent` carries name, kind, iteration, duration_s, reason, outputs, error. `PipelineExecutionLog` collects events but `to_dict()` excludes them
- **Session-dashboard card pattern:** `.session-card` CSS class, dark theme tokens, badge row, clamped summary, expandable detail. Renders from `renderCard(session)` function. StageCard and SessionCard serve distinct objects (pipeline stages vs agent sessions) — they share CSS custom properties but remain separate concerns. HtmlCardRenderer generates pipeline stage cards; session-card remains for agent session data
- **ClosureResult:** `passed`, `board_id`, `benders_*`, `router_completion_pct`, `drc_errors`, `drc_warnings`, `wall_clock_seconds`, `errors`, `warnings`, `stages_exercised`
- **CI dashboard:** Purely Chart.js time-series; no card concept
- **Rendering libraries:** `rich>=13.0.0`, `plotly>=5.18.0`. No HTML template engine
- **Unwired state:** `ProgressObserver`, `PipelineExecutionLog`, and `RichDashboard` are all built, tested, but never wired together

## Users & Use Cases

| Persona | Primary Use Case | Surface |
|---------|-----------------|---------|
| PCB Designer (local) | `temper watch` — pipeline progress live | Terminal (Rich) |
| PCB Designer (post-run) | Share which stages passed/failed | Static HTML or terminal |
| Firmware Engineer (CI) | Quick scan of stage health in PR check | CI annotations |
| Pipeline Developer | Inspect stage durations and anomalies | Web dashboard |

## Success Criteria

1. **One grammar, three surfaces:** A single Python dataclass produces valid output for Rich panels, CSS grid HTML, and CI annotations without surface-specific logic in the grammar
2. **Adding a stage propagates automatically:** Adding a `StageDefinition` to the DAG manifest results in that stage appearing in all three surfaces with zero renderer code changes
3. **ISA-101 coloring:** Stages are gray and quiet; only anomalies carry color. Consistent across surfaces
4. **Grammars are serializable:** Dataclass can be `asdict()`'d or emitted as `.json`. `PipelineExecutionLog.to_dict()` bug is fixed
5. **Renderer isolation:** Adding a 4th surface requires only a new renderer module — grammar untouched

## Approach 1: Grammar-as-ValueObject + Adapter Renderers — RECOMMENDED

**Description:** `StageCard` dataclass: `name`, `status` (enum: pending/running/skipped/success/error), `duration_s`, `icon`, `anomalies: list[str]`, `sub_stages: list[SubStageCard]`, `metadata: dict`. Three renderers: `RichCardRenderer`, `HtmlCardRenderer`, `CiAnnotationRenderer`. `GrammarObserver` populates from `ProgressObserver`.

**Pros:** Clean separation. Trivially serializable. Adding surface = new renderer (~50-100 lines). Fits existing ProgressObserver hook.

**Cons / Risks:** SubStageCard requires sub-stage instrumentation not yet available. Renderer sync requires per-surface tests.

## Approach 2: Grammar-as-Pydantic-Model + Auto-Discovered Renderers

**Description:** Pydantic v2 model with `model_dump(mode="json")`. Renderers auto-discovered via naming convention. Free schema validation + JSON Schema export.

**Pros:** Free JSON serialization. Validation catches malformed grammar. schema_version enables compatibility.

**Cons / Risks:** Pydantic already present but adds complexity over plain dataclass for v1.

## Approach 3: Grammar-as-Shared-CSS + Progressive Enhancement (Inversion)

**Description:** Grammar defined as CSS custom properties and HTML structure. `<stage-card.html>` partial is canonical. Python reads template for field knowledge. Terminal and CI are degraded ports.

**Pros:** Web-first development. Designers iterate in browser. CSS properties are the true visual grammar.

**Cons / Risks:** Python must parse HTML — fragile. CI annotations have limited HTML support. Terminal can't consume HTML.

## Recommendation

**Approach 1 (Grammar-as-ValueObject + Adapter Renderers)** — lowest friction, idiomatic (every type in the codebase is a dataclass), exploits existing infrastructure. Pydantic can be deferred. Web Components deferred to v2 when surface count grows.

## Scope Boundaries

**In scope for v1:** `StageCard` dataclass + `CardGrammar`, `RichCardRenderer` (terminal), `HtmlCardRenderer` (web), fix `PipelineExecutionLog.to_dict()`, `GrammarObserver` implementing `ProgressObserver`, 3 integration tests per surface

**Deferred:** SubStageCard/sub-stage breakdown, CiAnnotationRenderer, anomaly baseline comparison, Pydantic migration, Web Components

**Outside:** Live streaming to web dashboard, historical baseline sparklines (#2 in ideation), root-cause breadcrumb trail (#6 in ideation), replacing Chart.js in CI dashboard
