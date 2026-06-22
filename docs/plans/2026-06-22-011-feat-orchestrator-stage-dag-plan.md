---
date: 2026-06-22
plan_id: 011-feat-orchestrator-stage-dag
title: PipelineOrchestrator → Declarative Stage DAG + Feedback Contracts
origin: docs/brainstorms/2026-06-22-orchestrator-stage-dag-requirements.md
status: planned
---

# Implementation Plan: Orchestrator Stage DAG

## Summary

Replace `PipelineOrchestrator`'s imperative 8-phase method dispatch (`orchestrator.py:163`) with a declarative DAG engine backed by a YAML manifest, first-class feedback contracts, and extracted stage handlers. The existing `PipelineOrchestrator.run()` signature and behavior are preserved through a thin adapter that loads the default DAG and delegates.

## Implementation Units

### IU-0: Foundation — `DataContext`, `StageResult`, and Error Types

Before any engine work, establish the shared runtime types that all other IUs depend on.

**New files:**

| File | Purpose |
|------|---------|
| `packages/temper-placer/src/temper_placer/pipeline/dag_types.py` | `DataContext` (mutable `dict[str, Any]`), `StageResult` (output dict + timing), error hierarchy (`DAGCycleError`, `DAGMissingDependencyError`, `DAGDuplicateStageError`, `StageTimeoutError`, `FeedbackExhaustedError`), `StageHandler` protocol (`(PipelineState, DataContext) -> StageResult`) |

**Key decisions encoded:**
- `DataContext` is a plain `dict[str, Any]` populated from `PipelineConfig` fields at engine init (`input_pcb` → `context["input_pcb"]`, `epochs` → `context["epochs"]`, etc.). Keys are the same names used in manifest `requires`/`provides` (lowercase, snake_case).
- `StageHandler` protocol signature: `(state: PipelineState, context: DataContext) -> StageResult`. The stage has read/write access to both — it reads `context` for config parameters, writes results to `context`, and also mutates `state` fields for backward compatibility.
- Error types have structured fields for observability (cycle path as list of stage names, missing key + requiring stage, etc.).

**Files to touch:** `packages/temper-placer/src/temper_placer/pipeline/dag_types.py` (new)

---

### IU-1: DAG Manifest YAML Schema + Pydantic Validation (R1)

The Pydantic model that loads, validates, and freezes a DAG manifest.

**New files:**

| File | Purpose |
|------|---------|
| `packages/temper-placer/src/temper_placer/pipeline/dag_schema.py` | Pydantic `v2` models: `StageDAGManifest`, `StageDefinition`, `FeedbackContract`, `TriggerCondition`, `RetryConfig`, `DataKeySpec`. Plus `load_manifest(path: Path) -> StageDAGManifest` helper. |

**Pydantic model structure:**
```python
class StageDAGManifest(BaseModel):
    pipeline: PipelineMeta          # name: str, version: str
    stages: list[StageDefinition]
    data_keys: dict[str, DataKeySpec] | None = None  # documentation / validation reference

class StageDefinition(BaseModel):
    name: str                       # unique within pipeline
    handler: str                    # dotted path, e.g. "temper_placer.pipeline.stages.geometric.GeometricStage"
    requires: list[str] = []        # data keys this stage reads
    provides: list[str] = []        # data keys this stage produces
    skip_if: str | None = None      # predicate expression (see IU-2)
    timeout_s: float | None = None  # per-stage time budget
    on_timeout: Literal["skip", "fail"] = "fail"
    retry: RetryConfig | None = None
    feedback_contracts: list[FeedbackContract] = []

class FeedbackContract(BaseModel):
    name: str
    trigger: TriggerCondition
    target_stage: str
    parameter_adjustments: dict[str, Any]
    max_retriggers: int = 3

class TriggerCondition(BaseModel):
    metric: str                     # data key to read, e.g. "routing_completion"
    condition: Literal["lt", "gt", "lte", "gte", "eq", "neq"]
    threshold: float
```

**Validation at model construction (`model_validator`):**
- Duplicate stage names → `DAGDuplicateStageError`
- Cycle detection via Tarjan's SCC on `requires`/`provides` edges → `DAGCycleError`
- Missing dependency: a stage `requires` key K that no stage `provides` and K is not a built-in config key → `DAGMissingDependencyError`
- Unreachable stages (no path from any root): warning emitted via `warnings.warn`, not an error
- `target_stage` in feedback contracts must name a real stage
- `skip_if` expressions are parsed (via IU-2's parser) and validated for syntax at load time

**Existing patterns to follow:** `NetClassRules` pydantic migration (referenced in K1), `PcbSpecification.load()` pattern for YAML loading.

**Files to touch:**
- `packages/temper-placer/src/temper_placer/pipeline/dag_schema.py` (new)

---

### IU-2: Skip Condition Expression Parser (R8)

A small, safe predicate expression evaluator — does NOT execute arbitrary Python.

**New files:**

| File | Purpose |
|------|---------|
| `packages/temper-placer/src/temper_placer/pipeline/dag_expr.py` | `SkipExpr` parser + evaluator |

**Grammar subset (implemented via `ast`-based parser, not `eval`):**
```
expr     = or_expr
or_expr  = and_expr ("or" and_expr)*
and_expr = not_expr ("and" not_expr)*
not_expr = "not" not_expr | comparison
comparison = atom (("==" | "!=" | "<" | ">" | "<=" | ">=") atom)?
atom     = "true" | "false" | NUMBER | STRING | accessor
accessor = ("config" | "state" | "context") "." IDENTIFIER
```

**Evaluator:** Walks the AST. `config.x` reads `PipelineConfig` fields via `getattr`. `state.x` reads `PipelineState` boolean flags. `context.x` reads `DataContext[x]`. Unknown accessors raise `DAGExprError` at evaluation time (schema loads are parsed, not evaluated, so unknown keys at load time are only a warning).

**Supported:**
- `==`, `!=`, `<`, `>`, `<=`, `>=`
- `and`, `or`, `not`
- `true`, `false`
- Numeric literals (int, float)
- String literals (single/double quoted)
- Dotted accessors: `config.dry_run`, `config.skip_routing`, `context.routing_completion`

**Not supported:** arithmetic, function calls, variable binding, list/dict literals.

**Public API:**
- `parse_skip_expr(source: str) -> ast.Expression` — returns parsed AST, raises `DAGExprSyntaxError` on bad syntax
- `evaluate_skip_expr(expr, config, state, context) -> bool` — evaluates against live objects

**Files to touch:**
- `packages/temper-placer/src/temper_placer/pipeline/dag_expr.py` (new)

---

### IU-3: Stage Handler Extraction — 8 Phase Methods → Standalone Stage Classes (R4)

Extract each handler method from `PipelineOrchestrator` into a standalone callable class in `pipeline/stages/`. The handler logic is moved, not rewritten.

**New package:** `packages/temper-placer/src/temper_placer/pipeline/stages/`

| File | Class | Moved from |
|------|-------|------------|
| `stages/__init__.py` | Re-exports all stages | — |
| `stages/input_stage.py` | `InputStage` | `orchestrator.py:301-360` (`_run_input`) |
| `stages/semantic_stage.py` | `SemanticStage` | `orchestrator.py:362-364` (`_run_semantic`) |
| `stages/topological_stage.py` | `TopologicalStage` | `orchestrator.py:366-417` (`_run_topological`) |
| `stages/preflight_stage.py` | `PreflightStage` | `orchestrator.py:419-431` (`_run_preflight`) |
| `stages/geometric_stage.py` | `GeometricStage` | `orchestrator.py:433-489` (`_run_geometric`) |
| `stages/routing_stage.py` | `RoutingStage` | `orchestrator.py:491-502` (`_run_routing`) |
| `stages/refinement_stage.py` | `RefinementStage` | `orchestrator.py:504-629` (`_run_refinement`) |
| `stages/output_stage.py` | `OutputStage` | `orchestrator.py:631-668` (`_run_output`) |

**Each stage class follows this pattern:**
```python
class GeometricStage:
    """Geometric JAX gradient-descent optimization stage."""

    def __call__(self, state: PipelineState, context: DataContext) -> StageResult:
        start = time.time()
        # ... existing _run_geometric logic, adapted to:
        #   - Read epochs from context["epochs"] instead of state.config.epochs
        #   - Read max_movement_mm from context["max_movement_mm"]
        #   - Write placement_state to both state.placement_state (backward compat)
        #     and context["placement_state"]
        #   - Remove skip logic (engine handles it)
        #   - Remove loop-back logic (feedback contracts handle it)
        elapsed = time.time() - start
        return StageResult(outputs={"placement_state": state.placement_state}, duration_s=elapsed)
```

**Specific adaptations per stage:**
- **InputStage**: Reads `context["input_pcb"]`, writes `board`, `netlist`, `constraints`, `loops` to context
- **SemanticStage**: Reads from context, writes `loops_enriched`
- **TopologicalStage**: Reads from context, writes `deterministic_result`; skip_if handled by engine
- **PreflightStage**: Reads board/netlist/constraints from context, writes `preflight_report`
- **GeometricStage**: Reads placement-related config from context; writes `placement_state`
- **RoutingStage**: Reads placement state from context; writes `routing_result`, `routing_completion`
- **RefinementStage**: Builds on `PlaceRouteIterator`; writes updated `placement_state`, `routing_result`
- **OutputStage**: Reads placement state; writes `output_files`, `physics_report`

**Existing code refs that carry forward:**
- `PreflightStage` wraps the existing `PreflightChecker` class (`preflight.py:48`)
- `RefinementStage` wraps the existing `PlaceRouteIterator` class (`iterator.py:41`)
- `TopologicalStage` uses the existing `run_topological_phase()` function (`topological.py:21`)
- `GeometricStage` uses the existing `run_geometric_phase()` function (`geometric.py:31`)

**Convention:** Stage classes are trivially-instantiable (no-arg `__init__` or optional config). The engine does `importlib.import_module` + `instantiate` the handler path string. Registration is by manifest path string, not code.

**Files to touch:**
- `packages/temper-placer/src/temper_placer/pipeline/stages/__init__.py` (new)
- `packages/temper-placer/src/temper_placer/pipeline/stages/input_stage.py` (new)
- `packages/temper-placer/src/temper_placer/pipeline/stages/semantic_stage.py` (new)
- `packages/temper-placer/src/temper_placer/pipeline/stages/topological_stage.py` (new)
- `packages/temper-placer/src/temper_placer/pipeline/stages/preflight_stage.py` (new)
- `packages/temper-placer/src/temper_placer/pipeline/stages/geometric_stage.py` (new)
- `packages/temper-placer/src/temper_placer/pipeline/stages/routing_stage.py` (new)
- `packages/temper-placer/src/temper_placer/pipeline/stages/refinement_stage.py` (new)
- `packages/temper-placer/src/temper_placer/pipeline/stages/output_stage.py` (new)

---

### IU-4: DAG Execution Engine (R2, R3, R7, R9)

The core engine that loads a manifest, topologically sorts stages, executes them, evaluates feedback contracts, enforces timeouts, and emits lifecycle events.

**New files:**

| File | Purpose |
|------|---------|
| `packages/temper-placer/src/temper_placer/pipeline/dag_engine.py` | `StageDAGEngine` class |
| `packages/temper-placer/src/temper_placer/pipeline/dag_observability.py` | `ProgressObserver` protocol, `StageEvent` dataclass, `PipelineExecutionLog`, `write_execution_log_json()` |

**`StageDAGEngine` API:**
```python
class StageDAGEngine:
    def __init__(self, manifest_path: Path | str):
        # Loads YAML → StageDAGManifest (IU-1 validation runs here)
        # Builds adjacency: maps stage name → StageDefinition
        # Builds provides_map: maps data_key → set[stage_name]
        # Builds requires_map: maps stage_name → set[data_key]
        # Topologically sorts: linear order of stages
        self.manifest: StageDAGManifest
        self.stage_order: list[str]       # topologically sorted names
        self.provides_map: dict[str, set[str]]
        self.observers: list[ProgressObserver] = []

    def add_observer(self, observer: ProgressObserver) -> None: ...

    def run(self, state: PipelineState) -> PipelineState:
        # Main entry point — returns mutated state
        ...
```

**`run()` algorithm:**
```
1. Initialize DataContext from PipelineConfig fields:
   context = {
       "input_pcb": config.input_pcb,
       "constraints_yaml": config.constraints_yaml,
       "output_pcb": config.output_pcb,
       "epochs": config.epochs,
       "seed": config.seed,
       "max_movement_mm": config.max_movement_mm,
       "max_iterations": config.max_iterations,
       "routability_threshold": config.routability_threshold,
       "convergence_threshold": config.convergence_threshold,
       "fab_preset": config.fab_preset,
       "skip_topological": config.skip_topological,   # for skip_if evaluation
       "skip_routing": config.skip_routing,
       "dry_run": config.dry_run,
       # ... all PipelineConfig fields
   }

2. Add built-in keys that are always available:
   context["deadline"] = time.time() + total_timeout (if configured)

3. For each stage_name in self.stage_order:
   a. Evaluate skip_if → if True, emit on_stage_skip, continue
   b. Emit on_stage_start(stage_name, iteration, context)
   c. Run handler with cooperative timeout check (stage polls context["deadline"])
   d. Record StageResult.outputs into context
   e. Record timing into state.phase_timings
   f. Emit on_stage_complete(stage_name, duration_s, outputs)
   g. Evaluate feedback_contracts (see below)

4. Emit on_pipeline_complete(success, total_duration_s, stage_timings)
5. Write pipeline_execution.json
```

**Feedback contract evaluation (R3):**
```
For each contract in stage.feedback_contracts:
  1. Read trigger metric from context[contract.trigger.metric]
  2. If condition is met AND retrigger_count < max_retriggers:
     a. Emit on_feedback_triggered(contract.name, from_stage, target_stage, attempt)
     b. Apply parameter_adjustments to context:
        for key, value in contract.parameter_adjustments.items():
            if key in PipelineConfig fields → set context[key] to mutated value
            else → set context[key] = value
     c. Invalidate context keys transitively:
        - Find target_stage and all downstream stages (topological reach via requires/provides edges)
        - Remove their provides keys from context
     d. Re-execute from target_stage forward through stage_order (resume from target index)
     e. Increment retrigger_count
     f. Loop back to step 1
  3. If max_retriggers exhausted with condition still true:
     Record FeedbackExhaustedError in context["feedback_errors"]
     Continue to next stage (best-effort)
```

**Transitive invalidation (K3 clarification):** "Transitively" means all stages topologically reachable from the target stage via `requires` edges forward (i.e., any stage that directly or indirectly depends on the target's `provides` keys). In practice: find the target stage index in `stage_order`, set a cursor to that index, and re-execute from there forward.

**Timeout enforcement (R7):**
- Per-stage `timeout_s` is stored in `StageDefinition`.
- The engine writes `context["deadline"] = time.time() + stage.timeout_s` before invoking the handler.
- Handlers cooperatively check `context["deadline"]` by polling (e.g., in optimization loops: `if time.time() > context["deadline"]: break`).
- If the handler returns and `time.time() > deadline`, the engine raises `StageTimeoutError`.
- `on_timeout: skip` → mark stage skipped, continue. `on_timeout: fail` → fail pipeline.
- This replaces hardcoded epoch counts: `GeometricStage` checks `context["deadline"]` in its epoch loop instead of `range(min(state.config.epochs, 500))`; `RefinementStage` does the same instead of `range(200)`.

**Retry at engine level (R2):**
- If a handler raises an exception and `stage.retry.max_attempts > 0`, the engine retries up to `max_attempts` with `backoff_s` delay.
- Retries are recorded in execution log.

**Lifecycle events (R9):**
```python
class ProgressObserver(Protocol):
    def on_stage_start(self, stage_name: str, iteration: int, context: DataContext) -> None: ...
    def on_stage_complete(self, stage_name: str, duration_s: float, outputs: dict[str, Any]) -> None: ...
    def on_stage_skip(self, stage_name: str, reason: str) -> None: ...
    def on_stage_error(self, stage_name: str, error: Exception) -> None: ...
    def on_feedback_triggered(self, contract_name: str, from_stage: str, to_stage: str, attempt: int) -> None: ...
    def on_pipeline_complete(self, success: bool, total_duration_s: float, stage_timings: dict[str, float]) -> None: ...
```

The existing `ProgressCallback` base class in `visualization.py:32` already has `on_phase_start`/`on_phase_complete`/`on_iteration`/`on_epoch`. A `DAGProgressAdapter` wrapper translates the new `ProgressObserver` events to the existing callback interface so `TerminalProgress` and `RichDashboard` work without modification.

**Execution log (R9):**
- `write_execution_log_json(state, manifest, events, path)` writes a `pipeline_execution.json` containing:
  - `dag_topology`: serialized manifest (stage names, requires/provides edges)
  - `stage_order`: the topological execution order
  - `stage_timings`: per-stage elapsed time
  - `retry_counts`: per-stage retry attempts
  - `feedback_activations`: list of {contract_name, from_stage, to_stage, attempt, adjusted_params}
  - `success`, `total_duration_s`
  - Written to `state.config.output_pcb.parent / "pipeline_execution.json"` (or cwd if no output_pcb)

**ConvergenceChecker reuse:** The existing `ConvergenceChecker` (`convergence.py:100`) is used by the refinement stage internally, not by the engine. The engine's retry + feedback contract loop replaces the convergence check at the pipeline level.

**Files to touch:**
- `packages/temper-placer/src/temper_placer/pipeline/dag_engine.py` (new)
- `packages/temper-placer/src/temper_placer/pipeline/dag_observability.py` (new)

---

### IU-5: Backward Compatibility Adapter (R5)

Transform `PipelineOrchestrator` into a thin adapter that loads the default DAG manifest and delegates to `StageDAGEngine`.

**Modified files:**

| File | Change |
|------|--------|
| `packages/temper-placer/src/temper_placer/pipeline/orchestrator.py` | Replace `run()` delegation; keep `self.phases` dict and handler methods with deprecation warnings |

**`PipelineOrchestrator` after migration:**
```python
class PipelineOrchestrator:
    def __init__(self, config: PipelineConfig, manifest_path: Path | str | None = None):
        self.config = config
        self.state = PipelineState(config=config)

        # Keep old phases dict for backward compat (deprecated)
        self.phases: dict = { ... }  # unchanged

        # New DAG path
        if manifest_path is None:
            manifest_path = Path(__file__).parent.parent.parent.parent / "configs" / "pipeline_default.yaml"
        self._engine = StageDAGEngine(manifest_path)

        # Wire observers (existing callback protocol)
        self._dag_observer = DAGToLegacyObserver(self)
        self._engine.add_observer(self._dag_observer)

        # Legacy callbacks (still work)
        self.on_phase_start: Callable | None = None  # set by legacy callers
        self.on_phase_complete: Callable | None = None
        self.on_iteration: Callable | None = None

    def run(self) -> PipelineState:
        """Execute the full pipeline via DAG engine."""
        return self._engine.run(self.state)

    def get_phase_order(self) -> list[PipelinePhase]:
        """Get the ordered list of phases (delegates to DAG manifest)."""
        # Derived from manifest stage order for backward compat
        ...

    # Old handler methods remain with deprecation warnings:
    def _run_input(self, state):  # pragma: no cover
        import warnings
        warnings.warn("_run_input is deprecated. Use InputStage.", DeprecationWarning)
        ...
```

**Call sites (9 callers across `cli/pipeline_commands.py`, `cli/__init__.py`, `experiments/`, `tests/`) remain unchanged** — they still do `PipelineOrchestrator(config).run()`.

**`pipeline_default.yaml` is discovered relative to the package:** use `importlib.resources` or a fallback path relative to `__file__` of `orchestrator.py`. The file is shipped via package data (`pyproject.toml` `[tool.hatch.build.targets.wheel]` or `MANIFEST.in`).

**Files to touch:**
- `packages/temper-placer/src/temper_placer/pipeline/orchestrator.py` (modify `__init__` + `run` + `get_phase_order`; keep handlers with deprecation warnings)
- `packages/temper-placer/src/temper_placer/pipeline/dag_observability.py` (add `DAGToLegacyObserver` adapter class)

---

### IU-6: Default Pipeline DAG Manifest (R10)

Ship the YAML manifest that expresses the current 8-phase pipeline as a DAG.

**New file:** `packages/temper-placer/configs/pipeline_default.yaml`

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
    handler: temper_placer.pipeline.stages.routing_stage.RoutingStage
    requires: [board, netlist, placement_state]
    provides: [routing_result, routing_completion]
    skip_if: "config.skip_routing == true"
    timeout_s: 60

  - name: refinement
    handler: temper_placer.pipeline.stages.refinement_stage.RefinementStage
    requires: [board, netlist, placement_state, routing_result]
    provides: [placement_state, routing_result]
    skip_if: "config.skip_routing == true"
    timeout_s: 300

  - name: output
    handler: temper_placer.pipeline.stages.output_stage.OutputStage
    requires: [input_pcb, board, netlist, placement_state]
    provides: [output_files, physics_report]
    skip_if: "config.dry_run == true"
    timeout_s: 30

data_keys:
  input_pcb: { type: Path, description: "Path to input KiCad PCB" }
  board: { type: Board, description: "Parsed board specification" }
  netlist: { type: Netlist, description: "Parsed netlist" }
  constraints: { type: PlacementConstraints, description: "PCL constraints" }
  loops: { type: list, description: "Loop definitions" }
  loops_enriched: { type: list, description: "Enriched loop definitions" }
  deterministic_result: { type: PlacementResult, description: "Step 1-2 topological placement" }
  placement_state: { type: PlacementState, description: "Current placement state" }
  routing_result: { type: RoutingResult, description: "Routing verification result" }
  routing_completion: { type: float, description: "Fraction of nets routed (0-1)" }
  preflight_report: { type: PreflightReport, description: "Preflight check results" }
  output_files: { type: list, description: "Generated output file paths" }
  physics_report: { type: PhysicsReport, description: "Physical metrics report" }
```

**This manifest expresses the current REFINEMENT→GEOMETRIC loop-back as the `routability-retry` feedback contract on `geometric`**, without special-case code in the engine. The engine evaluates `routing_completion < 0.5` after `routing` completes (or during refinement), and if triggered, applies `spacing_multiplier: 1.1` and `epochs_boost: 200` to the context, invalidates placement_state/routing_result transitively, and re-executes from `geometric` forward.

**Package data:** Update `pyproject.toml` to include `configs/pipeline_default.yaml` in the wheel. The project uses hatchling; add `[tool.hatch.build.targets.wheel]` with `packages` glob or `include` directive.

**Files to touch:**
- `packages/temper-placer/configs/pipeline_default.yaml` (new)
- `packages/temper-placer/pyproject.toml` (add package data include)

---

### IU-7: Testing — Unit, Integration, Migration (SC1–SC7)

**New test files:**

| File | What it tests |
|------|---------------|
| `tests/pipeline/test_dag_types.py` | `DataContext` population from config, error types stringification, `StageResult` dataclass |
| `tests/pipeline/test_dag_expr.py` | Skip expression parser: valid expressions, invalid syntax, evaluation against mock config/state/context, edge cases (empty, missing keys) |
| `tests/pipeline/test_dag_schema.py` | Manifest loading: valid YAML → model, cycle detection (`DAGCycleError`), missing dependency (`DAGMissingDependencyError`), duplicate names, unreachable stage warning, feedback contract `target_stage` validation |
| `tests/pipeline/test_dag_engine.py` | Engine execution: topological order correctness, stage skip via `skip_if`, timeout enforcement (mock slow stage), retry on exception, feedback contract trigger + re-execution + max_retriggers exhaustion, event emission, execution log JSON output |
| `tests/pipeline/test_stages.py` | Each extracted stage class: produces expected output keys, reads from context, writes to both context and state (backward compat), idempotency where applicable |

**Modified test files:**

| File | Change |
|------|--------|
| `tests/pipeline/test_orchestrator.py` (56 tests) | Update tests that assert on internal state (`orchestrator.phases` dict keys, `get_phase_order()` enum lists) to use new API. Tests that assert on pipeline outputs (placement positions, routing results) must pass unchanged (SC6). |
| `tests/pipeline/test_orchestrator_integration.py` (2 tests) | Must pass unchanged — end-to-end `PipelineOrchestrator(config).run()` produces identical results (SC1). |

**Test fixtures:**
- `conftest.py` fixtures: `sample_config` (a `PipelineConfig` with a synthetic board), `temp_pcb` (a minimal KiCad PCB for integration tests), `sample_manifest` (default manifest loaded from configs/).
- Mocks: `MockRouter` for routing stages, `MockObserver` capturing lifecycle events.

**Success criteria coverage:**

| SC | Verified by |
|----|-------------|
| SC1: Identical placement/routing results | `test_orchestrator_integration.py` regression |
| SC2: YAML change → no code change | `test_dag_engine.py` with variant manifests |
| SC3: Cycle detection at construction | `test_dag_schema.py::test_cycle_detection` |
| SC4: Feedback contract trigger + log | `test_dag_engine.py::test_feedback_contract_triggers` |
| SC5: Timeout enforcement | `test_dag_engine.py::test_stage_timeout` |
| SC6: All 84 existing tests pass | CI run on `test_orchestrator.py` + `test_orchestrator_integration.py` |
| SC7: ClosureTest + execution log | `test_dag_engine.py::test_execution_log_json` |

**Files to touch:**
- `tests/pipeline/test_dag_types.py` (new)
- `tests/pipeline/test_dag_expr.py` (new)
- `tests/pipeline/test_dag_schema.py` (new)
- `tests/pipeline/test_dag_engine.py` (new)
- `tests/pipeline/test_stages.py` (new)
- `tests/pipeline/test_orchestrator.py` (modify internal-state tests)
- `tests/pipeline/conftest.py` (new, or extend existing)

---

## Implementation Order

```
IU-0: dag_types.py (error types, DataContext, StageResult) ← no deps
 │
 ├─► IU-1: dag_schema.py (pydantic models) ← depends on IU-0
 │     │
 │     ├─► IU-2: dag_expr.py (skip expression parser) ← depends on IU-0
 │     │
 │     ├─► IU-6: pipeline_default.yaml ← depends on IU-1 schema knowledge
 │     │
 │     └─► IU-3: stages/* (handler extraction) ← depends on IU-0 (StageResult, DataContext)
 │
 └─► IU-4: dag_engine.py + dag_observability.py ← depends on IU-1, IU-2, IU-3
       │
       └─► IU-5: orchestrator.py adapter ← depends on IU-4
             │
             └─► IU-7: tests (all test files) ← depends on IU-5
```

**Parallelizable pairs:**
- IU-2 and IU-3 can proceed in parallel (both only depend on IU-0)
- IU-6 can proceed in parallel with IU-2 and IU-3
- IU-7 test files for IU-0/IU-1/IU-2 can be written alongside their implementations

## Rollout Strategy

1. **IU-0 through IU-4 are built behind a feature gate.** The DAG engine path is activated only when `PipelineOrchestrator` is constructed with a manifest path. The default constructor uses the old path initially (during IU-0 through IU-4 development).

2. **IU-5 flips the default.** Once the engine and all stage handlers pass integration tests, `PipelineOrchestrator.__init__` defaults to loading `pipeline_default.yaml`. The old handler methods remain with `DeprecationWarning` for any stray callers.

3. **Tests gate the flip.** All 84 existing tests pass through the adapter before the default is changed. CI enforces this.

4. **Old handler removal is a separate task** tracked after this plan is complete and stable (per scope boundaries: "Removal of old handler methods ... tracked separately").

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| JAX JIT compilation inside thread-based timeout not interruptible | Cooperative timeout via `context["deadline"]` polling in epoch loops; thread-based enforcement is best-effort (per Assumption 4) |
| Stage extraction changes optimization behavior (loss functions, seed, initial state) | Regression suite (SC1, SC6); extracted handlers start from the same `context` values as the old hardcoded defaults |
| `PipelineState` field typing (`Any`) makes `DataContext` population fragile | IU-0 defines explicit mapping from `PipelineConfig` fields → `DataContext` keys; validation in `dag_schema.py` checks `requires`/`provides` keys exist in that mapping or in upstream `provides` |
| Feedback contract re-execution could infinite-loop if target stage never reaches condition | `max_retriggers` hard cap at 3; `FeedbackExhaustedError` documented and included in execution log; engine continues to OUTPUT |
| `pipeline_default.yaml` not found at runtime (packaging issue) | `importlib.resources` as primary path; fallback to `__file__`-relative; CI tests both paths |

## Files Summary

| Action | Files |
|--------|-------|
| **New** (14 files) | `pipeline/dag_types.py`, `pipeline/dag_schema.py`, `pipeline/dag_expr.py`, `pipeline/dag_engine.py`, `pipeline/dag_observability.py`, `pipeline/stages/__init__.py`, `pipeline/stages/input_stage.py`, `pipeline/stages/semantic_stage.py`, `pipeline/stages/topological_stage.py`, `pipeline/stages/preflight_stage.py`, `pipeline/stages/geometric_stage.py`, `pipeline/stages/routing_stage.py`, `pipeline/stages/refinement_stage.py`, `pipeline/stages/output_stage.py`, `configs/pipeline_default.yaml`, `tests/pipeline/test_dag_types.py`, `tests/pipeline/test_dag_expr.py`, `tests/pipeline/test_dag_schema.py`, `tests/pipeline/test_dag_engine.py`, `tests/pipeline/test_stages.py` |
| **Modified** (3 files) | `pipeline/orchestrator.py`, `tests/pipeline/test_orchestrator.py`, `tests/pipeline/test_orchestrator_integration.py`, `pyproject.toml` |
