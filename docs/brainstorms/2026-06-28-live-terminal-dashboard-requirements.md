# Brainstorm: Live Terminal Pipeline Dashboard (`temper watch`)

**Date:** 2026-06-28

## Problem Statement

PCB pipeline runs take 3–15 minutes with silent gaps between 8 variable-depth stages. Developers running `temper-placer pipeline` (local) or `make regression` (CI) get either zero output or sparse epoch-level printfs with no aggregate timing, DAG structure feedback, or at-a-glance failure location. The three components — `RichDashboard`, `ProgressObserver`, and `Rich Live` — exist tested but unwired end-to-end.

**What changes:** `temper watch` — a single command rendering an animated terminal DAG panel with per-stage timers, pulse-on-activity, flash-on-completion, and sparkline for numeric metrics, connected to either a local `PipelineOrchestrator` or a CI pipeline via `PipelineExecutionLog` JSON replay.

## Existing Context

- **RichDashboard** (`visualization.py:141-273`): Dataclass with `Layout`, `Panel`, `Table`. `_layout` field + `create_layout()` exist but `Live` context never mounted
- **ProgressObserver** (`dag_observability.py:12-22`): 6 lifecycle methods. Only `DAGToLegacyObserver` implements it — no terminal observer
- **PipelineExecutionLog** (`dag_observability.py:39-59`): Populated by `StageDAGEngine.run()`. Written to `pipeline_execution.json`
- **Rich library** (`pyproject.toml:35`): `rich>=13.0.0` installed. `Live`, `Layout`, `Panel`, `Table`, `Progress` available
- **CLI**: `temper-placer pipeline` at `cli/__init__.py:3300-3454`. `--visualize` flag exists in `pipeline_commands.py` but `create_layout()` returns `Layout` without mounting `Live`
- **DAG manifest** (`configs/pipeline_default.yaml`): 8 stages with feedback contracts (routability-retry)

## Users & Use Cases

| Persona | Primary Use Case |
|---------|-----------------|
| PCB developer (local) | `temper watch pcb/temper.kicad_pcb` — sees which stage is executing, how long, whether feedback contracts fire |
| CI reviewer | `temper watch --replay pipeline_execution.json` — replays execution log with terminal DAG animation |
| New contributor | `temper watch --demo` — animated prerecorded log showing pipeline topology |

## Success Criteria

1. `temper-placer watch` renders animated terminal DAG with stage panels that pulse during execution and flash green/red on success/failure
2. Live per-stage timers update in place; total elapsed timer in header
3. Loss/throughput sparkline updates in geometric stage panel
4. Feedback contract retriggers display with visual indicators
5. Works both live (`watch` mode) and post-hoc (`--replay`)

## Approach 1: Thin Observer + Rich Live Context Manager — RECOMMENDED

**Description:** `TerminalDashboardObserver` implements `ProgressObserver` and owns a `rich.Live` context. Translates all 6 lifecycle events into `Live.update()` calls on per-stage panels. `temper watch` CLI registers the observer on `StageDAGEngine`.

**Pros:** ~500 lines new code (TerminalDashboardObserver ~200 lines + CLI subcommand ~60 lines + layout rendering ~80 lines + replay mode ~50 lines + tests ~150 lines). Event-driven, no polling. Already partially proven in `pipeline_commands.py`. Replay from `PipelineExecutionLog` is trivial.

**Cons / Risks:** `RichDashboard` implements `ProgressCallback` (phase-level with `PipelinePhase` enums), not `ProgressObserver` (stage-level with string names) — observer is new code, reuses only layout primitives. Epoch sparkline requires extending `ProgressObserver` with `on_epoch(stage_name, epoch, loss)`. Terminal layout for 8 stages in 80 columns is the largest unresolved design decision.

## Approach 2: Async Sidecar + PipelineExecutionLog Tail

**Description:** Pipeline writes JSON incrementally. Separate `temper watch` process tails the file and renders asynchronously. Enables remote watching (`temper watch --tail <job-id>`).

**Pros:** Compute and viz separate processes. Naturally supports remote. No pipeline changes except more frequent writes.

**Cons / Risks:** I/O overhead on fast stages. Tail polling latency (50-200ms). Two-process architecture harder to test.

## Approach 3: WebSocket Bridge — LiveVisualizer Terminal Client

**Description:** Repurpose existing `LiveVisualizer`/`LiveServer` WebSocket infrastructure. Write `TerminalClient` connecting to same WebSocket.

**Pros:** Reuses existing event stream. Single event source → multiple surfaces.

**Cons / Risks:** Heavyweight dependency. `LiveVisualizer` itself not wired to DAG engine. WebSocket server overengineered for terminal-only dashboard.

## Recommendation

**Approach 1 (Thin Observer + Rich Live Context Manager)** — all three components exist tested, this is a wiring exercise. Single-file addition (~200 lines). Sub-10ms latency, synchronous, no network or filesystem complexity. Approaches 2 and 3 can layer on later for CI-remote use.

## Scope Boundaries

**In scope for v1:** `TerminalDashboardObserver` class (implements `ProgressObserver`, reuses `RichDashboard` layout primitives), extend `ProgressObserver` with `on_epoch(stage_name, epoch, loss)`, `temper-placer watch` subcommand, live timers + status + DAG header, `--replay` mode, epoch sparkline in geometric stage, feedback retrigger indicator, skip/error rendering

**Deferred:** Standalone `temper` CLI binary, remote CI tailing, TUI interactivity (pause/resume, drill-down), multi-DAG support

**Outside:** Browser LiveVisualizer, session-dashboard SPA, static HTML reports (Plan 011), firmware build monitoring
