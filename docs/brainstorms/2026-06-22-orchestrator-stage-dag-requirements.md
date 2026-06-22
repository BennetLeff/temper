---
date: 2026-06-22
topic: orchestrator-stage-dag
focus: Replace PipelineOrchestrator's imperative 8-phase methods with a declarative DAG + first-class feedback contracts
origin: docs/ideation/2026-06-22-orchestrator-stage-dag.md
status: active
actors: PipelineOrchestrator, RouterV6Pipeline, PlaceRouteIterator, CI system
---

# Requirements: Orchestrator → Declarative Stage DAG + Feedback Contracts

## Problem Frame

`PipelineOrchestrator` (`pipeline/orchestrator.py:163`, 668 lines) runs 8 phases — INPUT → SEMANTIC → TOPOLOGICAL → PREFLIGHT → GEOMETRIC → ROUTING → REFINEMENT → OUTPUT — through monolithic handler methods dispatched from a hardcoded `self.phases` dict. Each method is 60-100 lines with inline construction of dependencies (optimizers, routers, loss functions). This makes every structural change to the pipeline a code change:

- **Skip logic** is inline boolean checks at `get_phase_order()` lines 201-222 — adding a new skip condition requires touching the orchestrator.
- **The REFINEMENT→GEOMETRIC loop-back** is hardcoded at `run()` lines 256-265 as integer index manipulation (`idx = phase_order.index(PipelinePhase.GEOMETRIC)`) — coupling the execution engine to enum ordering.
- **Epoch counts and timeouts** are hardcoded: `_run_geometric` loops `min(state.config.epochs, 500)` (line 476), `_run_refinement` loops 200 epochs (line 593), SAT timeout is `5000.0` ms (router_v6/pipeline.py:363).
- **The waterfall pipeline failure** (past learning #6) was patched with an ad-hoc `PlaceRouteIterator` class that duplicates convergence logic.
- **Router V6** (`router_v6/pipeline.py:110`) has a cleaner 4-stage pattern but is equally imperative — stages call each other in a fixed sequence with no declared dependencies.

The result: pipeline topology is spread across three classes (`PipelineOrchestrator`, `RouterV6Pipeline`, `PlaceRouteIterator`), each encoding the same loop/back-edge/retry concepts in different, non-reusable ways.

## Actors

- **A1. Pipeline developer** — adds a new stage (e.g., THERMAL_VERIFY) or modifies the retry contract between GEOMETRIC and ROUTING. Today: modifies `get_phase_order()`, adds a handler to `self.phases`, edits `run()` for any loop logic. Target: edits a YAML config file.
- **A2. CI system** — runs `ClosureTest` and expects placement/routing to report timing and completion. Today: reads a single elapsed-time field. Target: receives per-stage timing, retry counts, and the stage DAG topology in structured output.
- **A3. Operator** — runs `temper-placer --pcb ...` and observes phase progress. Today: sees print statements embedded in handler methods. Target: sees a progress dashboard driven by stage lifecycle events from the execution engine.
- **A4. Router V6 maintainer** — already has a 4-stage pipeline but no way to compose it into the broader placement-routing loop without duplicating loop logic. Target: registers Router V6 stages as DAG nodes the orchestrator can schedule.

## Key Decisions

- **K1. DAG config format: YAML.** The project already uses YAML for constraints (`configs/constraints/`), PCB specs (`configs/pcb_spec.yaml`), and PCL (`configs/pcl/`). The DAG manifest follows the same convention. Pydantic validates it at load time, consistent with the `NetClassRules` migration (`docs/solutions/architecture-patterns/pydantic-dataclass-migration.md`). TOML is not used.

- **K2. Stages declare `requires`/`provides` data keys, not phase enums.** A stage like `geometric` declares `requires: [input, semantic, topological, preflight]` and `provides: [placement]`. The engine topologically sorts and runs stages whose requirements are satisfied. This is the standard compiler-pass-manager pattern (LLVM, Roslyn) — the same pattern cited in the seed idea. Stage names are free-form strings, not a closed enum.

- **K3. Feedback contracts are first-class stage configuration, not code.** A feedback contract is a block inside a stage definition that declares: (a) a trigger condition expressed as a predicate on stage output metrics, (b) parameter adjustments for the target stage, (c) a retry budget. Example from the seed idea expressed in YAML: `if routability < 50%, retry placement with spacing +10%, up to 3 retries`. The execution engine evaluates the trigger, applies parameter mutations, and re-executes the target stage without the target stage knowing about the contract.

- **K4. Backward compatibility: `PipelineOrchestrator.run()` signature preserved.** The existing `orchestrator = PipelineOrchestrator(config); orchestrator.run()` call sites (9 callers across `cli/pipeline_commands.py`, `cli/__init__.py`, `experiments/`, `tests/`) must work unchanged. The new DAG engine lives in `pipeline.dag_engine` and `PipelineOrchestrator` becomes a thin adapter that loads the default DAG YAML and delegates. `PipelineConfig` and `PipelineState` retain their existing fields.

- **K5. Stage handlers are registered functions, not orchestrator methods.** Each stage implements a callable with signature `(PipelineState) -> PipelineState` (same as today's handler methods). Stages are registered by module path string in the YAML config. The engine imports them lazily. This mirrors the existing `self.phases` dict pattern but moves registration from code to config.

- **K6. The 8-phase default DAG is the shipped default, not a special case.** A `pipeline_default.yaml` shipped in the package defines the current 8-phase topology as a DAG (INPUT → SEMANTIC → TOPOLOGICAL → PREFLIGHT → GEOMETRIC, with a feedback contract on GEOMETRIC that loops to REFINEMENT→ROUTING→GEOMETRIC). The DAG engine validates this config at import time. There is no "legacy mode" in the engine — the default config simply expresses the current behavior.

## Requirements

### R1. DAG Manifest YAML Schema
Status: required

Define a YAML schema for stage DAG manifests. The manifest contains:

- `pipeline.name`: string identifier
- `pipeline.version`: semver string
- `stages`: list of stage definitions, each with:
  - `name`: string (unique within pipeline)
  - `handler`: dotted Python module path (e.g., `temper_placer.pipeline.stages.geometric.GeometricStage`)
  - `requires`: list of data key strings this stage needs as input
  - `provides`: list of data key strings this stage produces
  - `skip_if`: optional predicate expression (e.g., `"config.dry_run == true"`)
  - `timeout_s`: optional float, per-stage time budget
  - `retry`: optional retry config with `max_attempts` (int) and `backoff_s` (float)
  - `feedback_contracts`: optional list of feedback contract definitions (see R3)
- `data_keys`: schema of data keys available for requires/provides (documentation and validation reference)

The schema is backed by a Pydantic model (`StageDAGManifest`) that validates at load time. Cycle detection and missing-key detection run during validation.

### R2. DAG Engine (Topological Sort + Execution)
Status: required

A `StageDAGEngine` class in `pipeline/dag_engine.py` that:

- Loads a DAG manifest (YAML → Pydantic model).
- Topologically sorts stages by `requires`/`provides` data keys. A stage is ready when all keys in its `requires` set are present in the shared data context.
- Validates the graph at load time: detects cycles (raises `DAGCycleError` with the cycle path), detects missing dependencies (a stage `requires` a key no stage `provides`, raises `DAGMissingDependencyError`), detects duplicate stage names.
- Executes stages in dependency order, providing each stage's handler with the shared `PipelineState`.
- After each stage completes, records its outputs (keyed by `provides` names) into the shared context for downstream stages.
- Evaluates `skip_if` predicates before executing a stage. If true, marks the stage as skipped and passes its `provides` keys through (downstream stages that require them fail unless another stage also provides them, caught at validation time).
- Enforces `timeout_s` per stage. If a stage exceeds its budget, the engine raises `StageTimeoutError`, records it, and either skips or fails the pipeline based on configuration.
- Implements retry at the engine level: if a stage's handler raises a retryable exception, the engine retries up to `max_attempts` with `backoff_s` delay between attempts.
- Emits lifecycle events (`on_stage_start`, `on_stage_complete`, `on_stage_skip`, `on_stage_error`, `on_feedback_triggered`) that progress observers can subscribe to.

### R3. Feedback Contracts
Status: required

A feedback contract is a declarative block within a stage definition that describes a conditional pipeline re-entry:

```yaml
feedback_contracts:
  - name: "routability-retry"
    trigger:
      metric: "routing_completion"
      condition: "lt"          # lt, gt, lte, gte, eq, neq
      threshold: 0.5           # if routing_completion < 0.5
    target_stage: "geometric"
    parameter_adjustments:
      spacing_multiplier: 1.1  # increase spacing by 10%
      epochs_boost: 200        # add 200 extra epochs
    max_retriggers: 3
```

The engine evaluates feedback contracts after the owning stage completes:

- Reads the trigger metric from the stage's output in the shared context.
- If the trigger condition is true and `max_retriggers` has not been exceeded, the engine:
  1. Records the feedback event.
  2. Applies `parameter_adjustments` to the data context (mutating the config or state fields the target stage reads).
  3. Invalidates the `provides` keys of the target stage (and any downstream stages transitively).
  4. Re-executes the target stage and all downstream stages with the adjusted parameters.
  5. Decrements the retrigger counter.
- If `max_retriggers` is exhausted without the trigger condition becoming false, the engine records a `FeedbackExhaustedError` and continues to OUTPUT (best-effort result).

Supported trigger conditions: `lt`, `gt`, `lte`, `gte`, `eq`, `neq`. Supported parameter adjustments: any field in `PipelineConfig` plus any key in the shared data context with a numeric or boolean value.

### R4. Stage Handlers
Status: required

Refactor each of the 8 existing phase handler methods into standalone stage callables:

- `pipeline/stages/input.py` — `InputStage.__call__(state) -> state`
- `pipeline/stages/semantic.py` — `SemanticStage`
- `pipeline/stages/topological.py` — `TopologicalStage`
- `pipeline/stages/preflight.py` — `PreflightStage` (already has `PreflightChecker`)
- `pipeline/stages/geometric.py` — `GeometricStage`
- `pipeline/stages/routing.py` — `RoutingStage`
- `pipeline/stages/refinement.py` — `RefinementStage` (built on `PlaceRouteIterator`)
- `pipeline/stages/output.py` — `OutputStage`

Each stage class:
- Implements `__call__(self, state: PipelineState, context: DataContext) -> PipelineState`.
- Reads configuration from `context.config` (a `PipelineConfig` or its evolution) rather than from hardcoded values.
- Does **not** contain skip logic, loop logic, feedback evaluation, or retry logic — those are engine concerns.
- Produces its output keys (matching its `provides` declaration) as fields on `PipelineState` or as entries in `DataContext`.
- Has a per-stage timeout that, when combined with the engine's enforcement, replaces hardcoded epoch counts (e.g., 500 epochs in geometric, 200 epochs in refinement, 5000ms SAT timeout).

### R5. Backward Compatibility
Status: required

- `PipelineOrchestrator(config)` and `.run()` retain the same signatures and return types (both at the Python type level and at the behavioral level for existing callers).
- Internally, `PipelineOrchestrator.__init__()` loads the default DAG manifest from `configs/pipeline_default.yaml` (shipped in the package), creates a `StageDAGEngine`, and delegates `run()` to the engine.
- `PipelineConfig` and `PipelineState` (already split into `state.py`) are not removed or renamed. New fields needed for DAG execution (e.g., data context) are added as optional with defaults so existing code that constructs them does not break.
- The `self.phases` dict and handler methods (`_run_input`, `_run_geometric`, etc.) remain in `orchestrator.py` until all callers and tests are migrated, but the `run()` method delegates to the engine. The handler methods gain deprecation warnings after the engine path is stable.
- All 84 test references to `PipelineOrchestrator` in `tests/pipeline/test_orchestrator.py` and `tests/pipeline/test_orchestrator_integration.py` continue to pass.

### R6. DAG Validation at Load Time
Status: required

When `StageDAGEngine` loads a manifest, it validates:

- **Cycle detection**: Tarjan's SCC algorithm. If a cycle exists, raises `DAGCycleError` listing the stages in the cycle.
- **Missing data key**: If a stage `requires` a key that no stage `provides` and that key is not in the initial data context (populated from `PipelineConfig` fields), raises `DAGMissingDependencyError` naming the missing key and the requiring stage.
- **Duplicate stage names**: Raises `DAGDuplicateStageError`.
- **Unreachable stages**: Stages that have no path from any root stage (stages with no dependencies) are flagged as a warning (not an error — they may be manually triggered stages).

Validation runs eagerly at manifest load time (during `StageDAGEngine.__init__`), not lazily during execution.

### R7. Per-Stage Timeout Budgets
Status: required

- Each stage definition includes an optional `timeout_s` field (float, in seconds).
- The engine enforces this by running the stage handler in a thread with a `threading.Timer` interrupt (or, if the handler is cooperative, by passing a `deadline` timestamp the handler checks).
- If a stage exceeds its budget, the engine raises `StageTimeoutError`, records the stage as timed-out, and either skips downstream stages or fails the pipeline depending on a `on_timeout: skip | fail` per-stage config field (default: fail).
- This replaces hardcoded epoch counts: `geometric` gets a 120s budget, `routing` gets a 60s budget, SAT gets a 5s budget per solve attempt.

### R8. Skip Conditions Declaratively
Status: required

- Stage definitions include an optional `skip_if` field with a predicate expression string.
- The engine evaluates `skip_if` expressions against a simple expression context that includes `config.*` (PipelineConfig fields), `state.*` (PipelineState boolean flags), and `context.*` (data context keys).
- Supported operators: `==`, `!=`, `<`, `>`, `<=`, `>=`, `and`, `or`, `not`, `true`, `false`, numeric and string literals.
- Example: `skip_if: "config.dry_run == true or config.skip_routing == true"`.
- The expression parser is a small Pratt parser or `ast.literal_eval`-based evaluator — it does NOT execute arbitrary Python. Invalid expressions are caught at manifest validation time.

### R9. Execution Observability
Status: required

- The engine emits structured events (not print statements) via a callback/listener pattern:
  - `on_stage_start(stage_name, iteration, context)`
  - `on_stage_complete(stage_name, duration_s, outputs)`
  - `on_stage_skip(stage_name, reason)`
  - `on_stage_error(stage_name, error)`
  - `on_feedback_triggered(contract_name, from_stage, to_stage, attempt)`
  - `on_pipeline_complete(success, total_duration_s, stage_timings)`
- A `ProgressObserver` protocol defines these callbacks. The existing `RichDashboard` and `TerminalProgress` classes in `pipeline/visualization.py` implement this protocol.
- The engine records per-stage timing and status into `PipelineState.phase_timings` (already exists).
- A structured execution log (JSON) is written to `output_pcb.parent / "pipeline_execution.json"` containing the DAG topology, stage ordering, per-stage timing, retry counts, and feedback contract activations.

### R10. Default Pipeline DAG Manifest
Status: required

Ship `configs/pipeline_default.yaml` expressing the current 8-phase pipeline as a DAG:

```yaml
# configs/pipeline_default.yaml
pipeline:
  name: "temper-default"
  version: "1.0.0"

stages:
  - name: input
    handler: temper_placer.pipeline.stages.input.InputStage
    requires: []
    provides: [board, netlist, constraints, loops]
    timeout_s: 60
    skip_if: "config.input_pcb == null"

  - name: semantic
    handler: temper_placer.pipeline.stages.semantic.SemanticStage
    requires: [input]
    provides: [loops_enriched]
    timeout_s: 30

  - name: topological
    handler: temper_placer.pipeline.stages.topological.TopologicalStage
    requires: [input, semantic]
    provides: [deterministic_result]
    skip_if: "config.skip_topological == true"
    timeout_s: 120

  - name: preflight
    handler: temper_placer.pipeline.stages.preflight.PreflightStage
    requires: [input, topological]
    provides: [preflight_report]
    timeout_s: 30

  - name: geometric
    handler: temper_placer.pipeline.stages.geometric.GeometricStage
    requires: [input, topological, preflight]
    provides: [placement_state]
    timeout_s: 120
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

  - name: routing
    handler: temper_placer.pipeline.stages.routing.RoutingStage
    requires: [input, geometric]
    provides: [routing_result, routing_completion]
    skip_if: "config.skip_routing == true"
    timeout_s: 60

  - name: refinement
    handler: temper_placer.pipeline.stages.refinement.RefinementStage
    requires: [input, geometric, routing]
    provides: [placement_state, routing_result]
    skip_if: "config.skip_routing == true"
    timeout_s: 300

  - name: output
    handler: temper_placer.pipeline.stages.output.OutputStage
    requires: [input, geometric]
    provides: [output_files, physics_report]
    skip_if: "config.dry_run == true"
    timeout_s: 30
```

This manifest defines the exact current behavior — including the REFINEMENT loop-back expressed as the feedback contract on `geometric` — without special-case code in the engine.

## Scope Boundaries

### In scope
- DAG manifest YAML schema + Pydantic validation model
- `StageDAGEngine` with topological sort, execution, retry, and event emission
- Feedback contract evaluation and re-execution loop
- `skip_if` predicate expression parser (simple, safe subset)
- Extraction of 8 phase handlers into standalone stage classes
- `PipelineOrchestrator` adapter that loads the default DAG and delegates
- Per-stage timeout enforcement
- Default `pipeline_default.yaml` manifest shipped in the package
- Execution observability events and JSON execution log output
- Migration of existing 84 orchestrator tests to use the new engine through the adapter

### Deferred for later
- **Router V6 stage registration in the DAG.** The default manifest only covers placement phases. Registering Router V6's 4 stages (`pcb_load`, `escape_vias`, `channel_analysis`, `topological_routing`, `geometric_realization`) as DAG nodes alongside placement stages is a follow-on that requires Router V6's handler interfaces to be adapted to the `(state, context) -> state` signature.
- **Dynamic DAG mutation at runtime.** The DAG topology is fixed at load time. Stages cannot be added or removed mid-execution (feedback contracts achieve re-entry without topology changes). Dynamic mutation (e.g., conditionally inserting a stage based on routing results) would require a `requires`/`provides` analysis at runtime and is a separate feature.
- **Distributed execution.** The engine runs all stages in-process. Multi-process or remote stage execution is not in scope.
- **UI for DAG editing.** The manifest is hand-edited YAML. A visual DAG editor or CLI wizard is not in scope.
- **Removal of old handler methods.** The `_run_input` etc. methods remain in `orchestrator.py` with deprecation warnings. Removal is tracked separately after all internal callers migrate.

### Outside this product's identity
- Replacing Router V6's internal pipeline. Router V6's 4 stages remain as-is within `router_v6/pipeline.py`. This work provides the DAG engine that *can* schedule them, but does not change Router V6 internals.
- Changing the optimizer or loss functions. Stage extraction moves code, it does not change optimization behavior.

## Success Criteria

- **SC1.** `PipelineOrchestrator(config).run()` with default config produces identical placement and routing results to the current orchestrator, verified by the existing integration test suite.
- **SC2.** Modifying `pipeline_default.yaml` to swap the REFINEMENT stage for a no-op or change the routability retry threshold does not require code changes to the orchestrator.
- **SC3.** A cycle intentionally introduced in the YAML manifest is caught at `StageDAGEngine` construction time with a `DAGCycleError` naming the cycle.
- **SC4.** The `routability-retry` feedback contract triggers when routing completion drops below 50%, up to 3 retries, and the execution log records each retrigger with the adjusted parameters.
- **SC5.** A stage that exceeds its `timeout_s` is terminated and the pipeline either fails or skips downstream stages as configured.
- **SC6.** All 84 existing `PipelineOrchestrator` tests pass through the adapter.
- **SC7.** `ClosureTest` runs end-to-end with the new engine and produces a `pipeline_execution.json` log containing stage timings and the DAG topology.

## Dependencies

- `temper_placer.pipeline.orchestrator.PipelineOrchestrator` — the adapter target (must not break)
- `temper_placer.pipeline.state.PipelineConfig` / `PipelineState` — shared state objects (extended, not replaced)
- `temper_placer.pipeline.convergence.ConvergenceChecker` — reused by the engine for stagnation detection
- `temper_placer.pipeline.feedback.RoutingFeedbackLoss` — current feedback mechanism; feedback contracts replace the need for ad-hoc loss construction in `_run_refinement`
- `temper_placer.pipeline.iterator.PlaceRouteIterator` — current refinement loop; feedback contracts subsume this loop, but the iterator is still used inside `RefinementStage`
- `temper_placer.pipeline.visualization.RichDashboard` / `TerminalProgress` — existing UI hooked into new event system
- `temper_placer.io.config_loader` — YAML loading patterns to follow
- `pydantic` — already in the dependency tree (used by `temper-drc` and `NetClassRules`); used for manifest validation

## Assumptions

1. **Pydantic is acceptable as a manifest validation dependency.** It is already in the dependency tree via `temper-drc`. The manifest model is loaded once at startup; attribute-access overhead on frozen models is irrelevant.
2. **The current 8-phase order is the only pipeline that must work on day one.** Router V6 integration into the DAG is deferred; the engine's generality is tested through the default manifest and unit tests for DAG manipulation, not through a multi-pipeline workload.
3. **Stage handlers can be refactored from methods to classes without behavioral change.** The handler logic itself (parsing, optimizing, routing) is not rewritten — only moved and given a uniform interface.
4. **Thread-based timeout enforcement is sufficient.** The geometric and routing stages run CPU-bound JAX/numpy code that does not release the GIL cooperatively. A `threading.Timer` that raises an exception in the main thread is acceptable for a CLI tool. For production hardening, signal-based or subprocess isolation can be added later.
5. **The `skip_if` expression language needs only simple comparisons and booleans.** We do not need arithmetic, function calls, or variable binding. The subset of Python expressions parseable by `ast.literal_eval` plus comparison operators is sufficient for skip conditions (`config.dry_run == true`, `config.skip_routing == true`).
6. **Backward compatibility means same inputs → same outputs, not same internal code path.** Tests that assert on internal state (e.g., `orchestrator.phases` dict keys) will need updating; tests that assert on pipeline outputs will pass unchanged.
