---
title: "Declarative Stage DAG Replaces Monolithic PipelineOrchestrator"
date: 2026-06-22
category: architecture-patterns
module: temper_placer
problem_type: architecture_pattern
component: development_workflow
severity: high
applies_when:
  - Refactoring a sequential pipeline into independently testable stages
  - Replacing imperative phase dispatch with topology-driven execution
  - Adding new pipeline stages without touching orchestration logic
  - Introducing feedback loops (placement-routing retry) into a linear pipeline
tags:
  - dag
  - declarative
  - yaml-manifest
  - topological-sort
  - pydantic-validation
  - feedback-contracts
  - skip-expression
  - stage-protocol
  - backward-compatibility
  - observability
  - pipeline-migration
  - sprint-N4
---

# Declarative Stage DAG Replaces Monolithic PipelineOrchestrator

## Context

The temper-placer pipeline was an 8-phase monolith inside `PipelineOrchestrator`
(`orchestrator.py:169`). Each of the 8 phases had a dedicated handler method
(`_run_input`, `_run_semantic`, `_run_topological`, etc.) averaging 60-100 lines
of imperative code. Adding a new phase meant touching the orchestrator class,
the `PipelinePhase` enum, the `run()` methods dispatch chain, the skip-logic
conditionals, and the snapshot-writing code. The execution order was hardcoded
as a sequential list with config-driven boolean skips (`skip_topological`,
`skip_routing`, `dry_run`). Feedback loops (placement-routing retry) were
implemented as inline `while`/`for` loops inside `_run_refinement` and
`_run_routing` with no structured contract.

The replacement is a declarative YAML-driven stage DAG: each phase becomes a
Stage implementing the `StageHandler` protocol. A YAML manifest declares stages
with `requires`/`provides` data-key contracts, `skip_if` expressions, timeout
policies, retry configs, and feedback contracts. Topological sort drives
execution order. The `PipelineOrchestrator` class remains as a thin adapter
that delegates to `StageDAGEngine`; old handler methods are retained with
`DeprecationWarning` for backward compatibility.

## Guidance

### Architecture

The DAG engine (`dag_engine.py`) loads a YAML manifest, topologically sorts
stages by their data-key dependencies, and executes them. Each stage is a
Python class implementing `StageHandler(state, context) -> StageResult`.

```
┌──────────┐     ┌────────────┐     ┌──────────────────┐
│  YAML    │────▶│ Pydantic   │────▶│ Topological      │
│ Manifest │     │ Validation │     │ Sort (Kahn's)    │
└──────────┘     └────────────┘     └────────┬─────────┘
                                             │
                    ┌────────────────────────┘
                    ▼
   ┌────────────────────────────────────────┐
   │  StageDAGEngine.run(state)             │
   │  ┌──────┐  ┌──────┐       ┌──────────┐ │
   │  │Input │─▶│Seman.│─▶ ... ▶│ Output   │ │
   │  └──────┘  └──────┘       └──────────┘ │
   │       ▲ feedback contracts loop back   │
   └────────────────────────────────────────┘
```

### Manifest Structure

The YAML manifest (`configs/pipeline_default.yaml`) declares:

```yaml
pipeline:
  name: "temper-default"
  version: "1.0.0"

stages:
  - name: input
    handler: temper_placer.pipeline.stages.input_stage.InputStage
    requires: []
    provides: [board, netlist, constraints, loops]
    timeout_s: 60
    skip_if: "config.input_pcb == null"

  - name: routing
    handler: temper_placer.pipeline.stages.routing_stage.RoutingStage
    requires: [board, netlist, placement_state]
    provides: [routing_result, routing_completion]
    skip_if: "config.skip_routing == true"
    feedback_contracts:
      - name: "routability-retry"
        trigger:
          metric: "routing_completion"
          condition: "lt"
          threshold: 0.5
        target_stage: "geometric"
        parameter_adjustments:
          spacing_multiplier: 1.1
          epochs_boost: 200
        max_retriggers: 3

  - name: output
    handler: temper_placer.pipeline.stages.output_stage.OutputStage
    requires: [input_pcb, board, netlist, placement_state, refinement_placement]
    provides: [output_files, physics_report]
    skip_if: "config.dry_run == true"
```

Key manifest elements:
- **`requires`/`provides`** — data-key contracts that define the dependency
  graph. A stage may list built-in config keys (e.g., `input_pcb`, `epochs`)
  in `requires` without any stage providing them — these are passed through
  the `DataContext` from `PipelineConfig`.
- **`skip_if`** — a DSL expression evaluated against `config`, `state`, and
  `context` namespaces. If true, the stage is skipped.
- **`timeout_s`** — best-effort cooperative timeout. The stage handler polls
  `context["deadline"]`; subprocess isolation is deferred.
- **`retry`** — max attempts and backoff for transient failures.
- **`feedback_contracts`** — a structured feedback loop declaration: trigger
  metric, comparison operator, threshold, target stage to rewind to,
  parameter adjustments to inject on retrigger, and a max retrigger cap.

### Pydantic Validation at Load Time

The `StageDAGManifest` model (`dag_schema.py:88`) runs `@model_validator(mode="after")`
on construction, catching:

| Problem | Detection |
|---|---|
| Duplicate stage names | `DAGDuplicateStageError` |
| `requires` key with no provider AND not a built-in config key | `DAGMissingDependencyError` |
| Cycle in requires/provides graph | Tarjan's SCC DFS with `DAGCycleError` |
| `skip_if` expression syntax error | AST parse at validation time with `DAGExprSyntaxError` |
| Feedback contract `target_stage` not in manifest | `ValueError` |
| Unreachable stage (no root path) | `UserWarning` |

### Topological Sort with First-Provider-Only Rule

Kahn's algorithm (`dag_engine.py:64-116`, `dag_schema.py:140-188`) builds
in-degree edges only from the **first** provider of each data key (lowest
declaration-order index in the manifest). This is critical: when multiple
stages provide the same key (e.g., `geometric` and `refinement` both provide
`placement_state`; `routing` and `refinement` both provide `routing_result`),
counting all providers as inbound edges creates false-positive cycles.

The `_first_provider()` helper (`dag_engine.py:75-79`, `dag_schema.py:147-151`)
resolves this:

```python
def _first_provider(key: str) -> str | None:
    providers = provides_map.get(key, set())
    if not providers:
        return None
    return min(providers, key=lambda p: stage_decl_order.index(p))
```

Without this rule, a manifest like `{geometric → provides placement_state,
refinement → provides placement_state, refinement → requires routing_result,
routing → requires placement_state}` would appear cyclic because both
`geometric` and `refinement` appear to depend on each other transitively
through shared keys. In reality, only the first provider's edge counts.

### Skip Expression DSL

The `skip_if` field uses a sandboxed AST-based expression language
(`dag_expr.py`) with the grammar:

```
expr     = or_expr
or_expr  = and_expr ("or" and_expr)*
and_expr = not_expr ("and" not_expr)*
not_expr = "not" not_expr | comparison
comparison = atom (("==" | "!=" | "<" | ">" | "<=" | ">=") atom)?
atom     = "true" | "false" | "null" | NUMBER | STRING | accessor
accessor = ("config" | "state" | "context") "." IDENTIFIER
```

Tokens are parsed into `ast.Expression` nodes, which are evaluated against
live `config` (attributes), `state` (attributes), and `context` (dict keys)
objects. Unknown identifiers raise `DAGExprError` with a clear message.
Bare identifiers (without a `config.`/`state.`/`context.` prefix) are
rejected at parse time to prevent accidental namespace ambiguity.

Examples:
- `"config.skip_routing == true"` — boolean skip
- `"config.input_pcb == null"` — null check
- `"context.routing_completion > 0.5"` — runtime metric check
- `"config.dry_run == true and not state.iteration > 0"` — compound condition

### Feedback Contracts

Feedback contracts replace the old inline placement-routing retry loop with a
declarative, config-driven mechanism (`dag_engine.py:316-374`). Each contract
declares:

1. **Trigger**: a metric key in context, a comparison operator, and a threshold
2. **Target stage**: where to rewind execution on retrigger
3. **Parameter adjustments**: key-value pairs injected into context before
   the target stage reruns (e.g., `spacing_multiplier: 1.1`)
4. **Max retriggers**: cap to prevent infinite loops

On retrigger, the engine clears all context keys provided by stages between
the target and the current stage (context invalidation), then resumes from
the target. A `FeedbackExhaustedError` is recorded (but does not halt the
pipeline) when a contract hits its retrigger cap.

### Timeouts (Best-Effort Cooperative)

Timeout enforcement is cooperative: the engine sets `context["deadline"]`
before invoking a stage handler (`dag_engine.py:293`). The stage handler is
responsible for polling `context.get("deadline")` during long-running loops
(e.g., `geometric_stage.py:72-73`, `refinement_stage.py:75-76`). After the
handler returns, the engine checks `time.time() > deadline` and raises
`StageTimeoutError` if exceeded. The stage's `on_timeout` policy (`"skip"` or
`"fail"`) determines whether the pipeline continues or halts.

Subprocess isolation (running stages in separate OS processes with hard-kill
timeouts) is deferred but the `deadline` pattern is designed to extend to it:
a subprocess wrapper would set `deadline` before spawning and the engine's
post-return check would validate the deadline was met.

### Observability and Backward Compatibility

**DAGToLegacyObserver** (`dag_observability.py:62-130`) adapts `ProgressObserver`
events to legacy `PipelineOrchestrator` callbacks (`on_phase_start`,
`on_phase_complete`, `on_iteration`). It preserves state snapshots (JSON + SVG)
that the old orchestrator wrote via `save_json_snapshot()` and
`save_svg_snapshot()`, writing them to a `snapshots/` directory with the same
naming convention (`{idx}_{phase}_{iter}.json`).

**PipelineExecutionLog** (`dag_observability.py:40-59`) captures DAG topology,
stage order, per-stage timings, retry counts, and feedback activation history
as a structured `pipeline_execution.json` written on pipeline completion.

**MetricsObserver** (`metrics_observer.py`) is a `ProgressObserver` implementation
that records per-stage metrics (wall_time, success, drc_delta) into the project's
canonical `pipeline_metrics.jsonl` time-series store during pipeline execution.
It includes double-entry cross-validation against the observer's own
`time.monotonic()` clock, YAML schema validation per metric, and canary
integrity checks to detect recording-path corruption. This observer is the
primary metrics write path for pipeline observability.

**Backward compatibility**: The `PipelineOrchestrator` class
(`orchestrator.py:169-207`) remains as a thin adapter. Its constructor creates a
`StageDAGEngine` from the default manifest (or a custom path) and attaches a
`DAGToLegacyObserver`. The `run()` method delegates entirely to
`self._engine.run(self.state)`. The old `_run_input`, `_run_semantic`, etc.
methods remain with `DeprecationWarning` until the DAG engine passes all 84
pipeline tests across `test_orchestrator.py`, `test_dag_engine.py`,
`test_dag_schema.py`, and integration tests.

### Key Bugs Found and Fixed

**OUTPUT-before-REFINEMENT ordering bug**: The topological sort placed
`output` before `refinement` because `output` required `placement_state`
(provided by `geometric`) and the `refinement_placement` key (only provided
by `refinement`) was not in `output`'s `requires`. The algorithm had no edge
from `refinement` to `output`, so it could schedule `output` immediately after
`geometric`. Fixed by adding `refinement_placement` to `output`'s `requires`
list in the manifest (`pipeline_default.yaml:66`).

**`skip_local_refinement` silent no-op**: `PipelineConfig.skip_local_refinement`
was read by the old orchestrator's hardcoded skip logic (`orchestrator.py:235-238`)
but had no corresponding `skip_if` in the geometric stage. The DAG engine only
evaluates manifest-level `skip_if` expressions. Fixed by adding
`skip_if: "config.skip_local_refinement == true"` to the `geometric` stage
definition (`pipeline_default.yaml:36`).

## Why This Matters

The monolithic orchestrator made three common operations dangerous:
- **Adding a phase** required editing the enum, the dispatch dict, the
  hardcoded skip conditions, the snapshot writer, and the `run()` loop.
  With the DAG, adding a phase is one YAML block and one Stage class.
- **Changing execution order** meant reordering enum members (risking
  state-machine corruption) and manually reasoning about which phases
  depend on which. With the DAG, declare `requires`/`provides` and the
  sort handles the rest.
- **Testing a phase in isolation** required mocking the entire orchestrator
  and all prior phases' outputs. With the DAG, a Stage can be tested by
  providing its required context keys and asserting its outputs.

The feedback contract formalizes what was an ad-hoc, untestable inline loop
into a configurable, reusable mechanism. The validation at load time catches
configuration errors (cycles, missing deps, syntax errors in skip expressions)
before any computation starts — eliminating an entire class of runtime-only
pipeline configuration bugs.

## When to Apply

Apply this pattern when:
- A pipeline has 5+ sequential phases and phase count is growing.
- The execution order should be derived from data dependencies, not hardcoded.
- Phases need independent testing with minimal mocking.
- Feedback loops should be configurable, not embedded in imperative code.
- Pipeline configuration (skips, timeouts, retries) should be editable without
  touching Python code.

Do NOT apply when:
- The pipeline has 1-3 phases with fixed, never-changing order.
- All phases are tightly coupled and cannot be tested independently.
- There is no need for dynamic skip logic or feedback loops.
- The codebase has no existing Pydantic/YAML infrastructure and adding them
  is prohibitive.

## Examples

### Before: Monolithic Orchestrator (excerpt)

```python
class PipelinePhase(Enum):
    INPUT = "input"
    SEMANTIC = "semantic"
    TOPOLOGICAL = "topological"
    PREFLIGHT = "preflight"
    GEOMETRIC = "geometric"
    ROUTING = "routing"
    REFINEMENT = "refinement"
    OUTPUT = "output"


class PipelineOrchestrator:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.state = PipelineState(config=config)
        self.phases = {
            PipelinePhase.INPUT: self._run_input,
            PipelinePhase.SEMANTIC: self._run_semantic,
            PipelinePhase.TOPOLOGICAL: self._run_topological,
            PipelinePhase.PREFLIGHT: self._run_preflight,
            PipelinePhase.GEOMETRIC: self._run_geometric,
            PipelinePhase.ROUTING: self._run_routing,
            PipelinePhase.REFINEMENT: self._run_refinement,
            PipelinePhase.OUTPUT: self._run_output,
        }

    def run(self) -> PipelineState:
        phases = [
            PipelinePhase.INPUT, PipelinePhase.SEMANTIC,
            PipelinePhase.TOPOLOGICAL, PipelinePhase.PREFLIGHT,
            PipelinePhase.GEOMETRIC, PipelinePhase.ROUTING,
            PipelinePhase.REFINEMENT, PipelinePhase.OUTPUT,
        ]
        if self.config.skip_topological:
            phases.remove(PipelinePhase.TOPOLOGICAL)
        if self.config.skip_routing:
            phases.remove(PipelinePhase.ROUTING)
            phases.remove(PipelinePhase.REFINEMENT)
        if self.config.dry_run:
            phases = phases[:5]  # stop after preflight

        for phase in phases:
            self.state.current_phase = phase
            self.phases[phase](self.state)
            self._save_snapshot(phase)

            # Ad-hoc feedback loop
            if phase == PipelinePhase.ROUTING:
                for i in range(3):
                    if not self.state.routing_result.is_feasible():
                        self._run_geometric(self.state)
                        self._run_routing(self.state)
                    else:
                        break

        return self.state

    # 8 handler methods, each 60-100 lines
    # _run_input: 44 lines / _run_topological: 52 lines
    # _run_geometric: 58 lines / _run_routing: 14 lines
    # _run_refinement: 126 lines / _run_output: 24 lines
```

### After: Declarative Manifest + DAG Engine

**Manifest** (`configs/pipeline_default.yaml`):

```yaml
pipeline:
  name: "temper-default"
  version: "1.0.0"

stages:
  - name: input
    handler: temper_placer.pipeline.stages.input_stage.InputStage
    requires: []
    provides: [board, netlist, constraints, loops]
    timeout_s: 60
    skip_if: "config.input_pcb == null"

  - name: semantic
    handler: temper_placer.pipeline.stages.semantic_stage.SemanticStage
    requires: [board, netlist, loops]
    provides: [loops_enriched]
    timeout_s: 30

  - name: topological
    handler: temper_placer.pipeline.stages.topological_stage.TopologicalStage
    requires: [board, netlist, constraints]
    provides: [deterministic_result]
    skip_if: "config.skip_topological == true"
    timeout_s: 120

  - name: preflight
    handler: temper_placer.pipeline.stages.preflight_stage.PreflightStage
    requires: [board, netlist, constraints]
    provides: [preflight_report]
    timeout_s: 30

  - name: geometric
    handler: temper_placer.pipeline.stages.geometric_stage.GeometricStage
    requires: [board, netlist, deterministic_result]
    provides: [placement_state]
    skip_if: "config.skip_local_refinement == true"
    timeout_s: 120

  - name: routing
    handler: temper_placer.pipeline.stages.routing_stage.RoutingStage
    requires: [board, netlist, placement_state]
    provides: [routing_result, routing_completion]
    skip_if: "config.skip_routing == true"
    timeout_s: 60
    feedback_contracts:
      - name: "routability-retry"
        trigger:
          metric: "routing_completion"
          condition: "lt"
          threshold: 0.5
        target_stage: "geometric"
        parameter_adjustments:
          spacing_multiplier: 1.1
          epochs_boost: 200
        max_retriggers: 3

  - name: refinement
    handler: temper_placer.pipeline.stages.refinement_stage.RefinementStage
    requires: [board, netlist, placement_state, routing_result]
    provides: [refinement_placement, refinement_routing_result]
    skip_if: "config.skip_routing == true"
    timeout_s: 300

  - name: output
    handler: temper_placer.pipeline.stages.output_stage.OutputStage
    requires: [input_pcb, board, netlist, placement_state, refinement_placement]
    provides: [output_files, physics_report]
    skip_if: "config.dry_run == true"
    timeout_s: 30
```

**Stage implementation** (example: `geometric_stage.py`):

```python
class GeometricStage:
    def __call__(self, state: Any, context: DataContext) -> StageResult:
        start_time = time.time()
        deterministic_result = context.get("deterministic_result")
        board = context["board"]
        netlist = context["netlist"]
        deadline = context.get("deadline", None)

        # ... JAX gradient descent optimization ...

        placement_state = PlacementState.from_positions(jnp.array(final_pos))
        state.placement_state = placement_state

        return StageResult(
            outputs={"placement_state": placement_state},
            duration_s=time.time() - start_time,
        )
```

**Thin orchestrator adapter** (`orchestrator.py`):

```python
class PipelineOrchestrator:
    def __init__(self, config: PipelineConfig, manifest_path=None):
        self.config = config
        self.state = PipelineState(config=config)
        if manifest_path is None:
            manifest_path = (
                Path(__file__).parent.parent.parent.parent
                / "configs" / "pipeline_default.yaml"
            )
        self._engine = StageDAGEngine(manifest_path)
        self._dag_observer = DAGToLegacyObserver(self)
        self._engine.add_observer(self._dag_observer)
        # Old handler methods remain with DeprecationWarning

    def run(self) -> PipelineState:
        return self._engine.run(self.state)
```

### Feedback Contract in Action

When the routing stage completes with `routing_completion < 0.5`:

1. Engine evaluates the `routability-retry` contract (`dag_engine.py:336-340`)
2. Injects `spacing_multiplier=1.1` and `epochs_boost=200` into context
3. Clears context keys from `geometric` through `refinement` (invalidation)
4. Resumes execution at `geometric` with the adjusted parameters
5. Tracks per-contract retrigger count in `_feedback_retrigger_counts`
6. Emits a `feedback_triggered` lifecycle event for observers
7. After `max_retriggers=3`, logs `FeedbackExhaustedError` and continues

### Adding a New Stage

To add a 9th stage (e.g., `thermal_analysis` after `output`):

1. Add one YAML block to `pipeline_default.yaml`:
   ```yaml
   - name: thermal_analysis
     handler: temper_placer.pipeline.stages.thermal_stage.ThermalStage
     requires: [board, netlist, placement_state, physics_report]
     provides: [thermal_report]
     timeout_s: 60
   ```
2. Implement `ThermalStage` as a class with `__call__(state, context) -> StageResult`
3. No changes to `PipelinePhase` enum, dispatch dict, skip logic, or snapshot code

## Related

- `packages/temper-placer/src/temper_placer/pipeline/dag_engine.py` — StageDAGEngine execution loop
- `packages/temper-placer/src/temper_placer/pipeline/dag_schema.py` — Pydantic manifest validation, cycle detection
- `packages/temper-placer/src/temper_placer/pipeline/dag_types.py` — StageHandler protocol, error hierarchy
- `packages/temper-placer/src/temper_placer/pipeline/dag_expr.py` — skip_if expression parser and evaluator
- `packages/temper-placer/src/temper_placer/pipeline/dag_observability.py` — ProgressObserver, DAGToLegacyObserver, PipelineExecutionLog
- `packages/temper-placer/configs/pipeline_default.yaml` — production pipeline manifest (8 stages)
- `packages/temper-placer/src/temper_placer/pipeline/stages/` — stage implementations (input, semantic, topological, preflight, geometric, routing, refinement, output)
- `packages/temper-placer/src/temper_placer/pipeline/orchestrator.py` — thin adapter with deprecated handler methods
- `packages/temper-placer/tests/pipeline/test_dag_engine.py` — engine execution tests
- `packages/temper-placer/tests/pipeline/test_dag_schema.py` — manifest validation tests
- `docs/solutions/architecture-patterns/pydantic-dataclass-migration.md` — sibling pattern (Pydantic for validation SSOT)
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — sibling pattern (baseline+monotonic shrink for CI gating)
