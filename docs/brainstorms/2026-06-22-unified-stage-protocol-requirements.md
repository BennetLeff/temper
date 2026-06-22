---
date: 2026-06-22
topic: unified-stage-protocol
focus: Define a single PipelineStage Protocol with typed run(input)->output, strategy dispatch, adapters for all three pipelines, and contract validation
origin: docs/ideation/2026-06-22-design-validation-ideation.md
status: active
actors: pipeline developers, CI system, closure test
---

# Requirements: Unified Stage Protocol

## Problem Frame

Temper has three pipeline systems, each with an incompatible execution interface:

| Pipeline | Interface signature | State model | Stage count |
|---|---|---|---|
| **DeterministicPipeline** | `Stage.run(state: BoardState) -> BoardState` | Frozen dataclass | 26 `Stage` subclasses |
| **PipelineOrchestrator** | `Orchestrator.run() -> PipelineState` | Mutable dataclass (`PipelineState`) | 8 phases in `dict[Phase, Callable]` |
| **RouterV6Pipeline** | `Pipeline.run(path: Path) -> RouterV6Result` | File-path-based; stages produce typed dataclass outputs | 4 internal stages |

Each pipeline is a closed system. A `PipelineOrchestrator` phase cannot be swapped into a `DeterministicPipeline` stage sequence. A `RouterV6Pipeline` stage cannot be composed with `DeterministicPipeline` stages without ad-hoc scripting. The 118 scripts under `scripts/` bypass all three pipeline APIs because no common interface exists.

The `PipelineOrchestrator` already embeds an ad-hoc strategy pattern — its `_run_geometric`, `_run_routing`, and `_run_refinement` methods hard-code which placement and routing backend to use. The `benders_placement` function in `placement/benders_loop.py` implements a proto-strategy dispatch (`if strategy == "template": ...`). The `RouterV6Pipeline` adapter in `router_v6/adapter.py` wraps `route_pcb()` as a standalone function. These are proto-protocols — the next step is to unify them.

The project roadmap calls for a closure test as the universal acceptance criterion: parse → place → route → DRC. Without a common stage protocol, each new placement or routing algorithm requires changes to the closure test, the orchestrator, and any script that exercises the pipeline.

## Actors

- **A1. Pipeline integrator** — composes stages from different backends (e.g., `DeterministicPipeline` clearance grid stage + `RouterV6Pipeline` topological routing stage) into a single run sequence
- **A2. Strategy author** — registers a new placement or routing strategy under the unified protocol; expects the strategy to be dispatchable by name from the closure test without modifying the test
- **A3. Script maintainer** — runs ad-hoc pipeline experiments from `scripts/`; needs a single `run` entry point that works regardless of which pipeline backend is active
- **A4. CI system** — runs the closure test and expects placement and routing stages to produce typed outputs validated by contracts

## Key Decisions

- **K1. Protocol over inheritance.** The `PipelineStage` type is a `typing.Protocol`, not an ABC. This allows existing classes to satisfy the interface without being subclassed. The `DeterministicPipeline`'s `Stage` ABC becomes a concrete implementation of the protocol rather than the protocol itself.
- **K2. Unified input/output types.** A single `StageInput` dataclass and `StageOutput` dataclass replace `BoardState`, `PipelineState`, and `RouterV6Result` at the protocol boundary. Adapters translate between internal types and the protocol types. The protocol does not constrain what data the input/output carries — only that it has a typed `data` field and optional `meta` field.
- **K3. Strategy registry with plug-in keying.** Strategies are registered by `(phase, name)` — e.g., `("placement", "template")` or `("routing", "router_v6")`. The registry is a module-level dict that backends populate at import time. The registry is the single source of truth for which backends are available.
- **K4. Adapter modules, not internal modifications.** Each adapter lives in its own module (e.g., `adapters/router_v6_adapter.py`, `adapters/orchestrator_adapter.py`). Adapters do not modify the wrapped pipeline's internals. This is the same pattern already used by `router_v6/adapter.py` and `placement/benders_loop.py`.
- **K5. Contract validation at stage boundaries.** Each stage declares `Contract(input_schema, output_schema)` — a lightweight schema check (field existence, type, not content correctness) executed at the boundary between stages. Schema violation raises `ContractViolationError` immediately.

## Requirements

### R1. PipelineStage Protocol

Status: **required**

Define a `PipelineStage` Protocol with a single method:

```python
class PipelineStage(Protocol):
    name: str
    
    def run(self, input: StageInput) -> StageOutput:
        """Execute the stage and return its output."""
        ...
```

- The `name` property identifies the stage in logs, traces, and the strategy registry
- `StageInput` is a dataclass with a `data` field (the stage-specific payload) and an optional `meta` field (shared metadata like seed, timestamp, trace context)
- `StageOutput` is a dataclass with `data` (the result payload), `meta` (forwarded + annotated metadata), and an optional `contract_satisfied: bool` flag
- The protocol must be importable from `temper_placer.protocol` without pulling in any pipeline implementation
- The protocol module must not import from `deterministic/`, `router_v6/`, or `pipeline/`

### R2. Strategy Registry

Status: **required**

Provide a module-level `PipelineStageRegistry` with:

- `register(phase: str, name: str, stage_factory: Callable[[], PipelineStage])` — register a stage factory keyed by `(phase, name)`
- `get(phase: str, name: str) -> PipelineStage` — instantiate and return a stage
- `list(phase: str | None = None) -> dict` — list available strategies, optionally filtered by phase
- `register_composite(name: str, stages: list[tuple[str, str]])` — register a named pipeline composed of existing stages (e.g., `"full_router" -> [("routing", "escape_vias"), ("routing", "topological"), ("routing", "geometric")]`)
- `get_composite(name: str) -> list[PipelineStage]` — return the ordered stage list for a composite

Phase names are strings (not enums) to avoid coupling the registry to any pipeline's phase definitions: `"placement"`, `"routing"`, `"drc"`, `"output"`, etc.

Backends register themselves at module import time. Registration must be idempotent — importing a backend module twice must not raise.

### R3. Adapter for PipelineOrchestrator

Status: **required**

Create `temper_placer.adapters.orchestrator_adapter` that:

- Wraps each `PipelineOrchestrator` phase handler as a `PipelineStage` implementation
- Translates `PipelineState` ↔ `StageInput`/`StageOutput` at adapter boundaries
- Registers each phase under the registry with phase = the `PipelinePhase` value and name = `"orchestrator"`
- The wrapped stages must not call `PipelineOrchestrator.run()` — the orchestrator is decomposed into individually callable stages
- Each adapter stage is a thin translation layer: extract data from `StageInput.data`, call the phase handler, wrap the returned `PipelineState` into `StageOutput.data`
- The adapter module must be importable without side effects beyond registry registration

### R4. Adapter for RouterV6Pipeline

Status: **required**

Create `temper_placer.adapters.router_v6_stage_adapter` that:

- Decomposes `RouterV6Pipeline` into four individually callable `PipelineStage` implementations: `Stage0_LoadPCB`, `Stage1_EscapeVias`, `Stage2_ChannelAnalysis`, `Stage3_TopologicalRouting`, `Stage4_GeometricRealization`
- Each stage accepts `StageInput` carrying the stage-specific data (e.g., `StageInput(data=ParsedPCB)` for Stage0) and produces `StageOutput` with the stage's typed dataclass (e.g., `StageOutput(data=Stage2Output(...))`)
- Registers all four stages under phase `"routing"` with name `"router_v6"`
- Registers a composite `"router_v6_full"` that chains all four stages in order
- Does **not** modify `RouterV6Pipeline` internals — the adapter calls the existing internal `_run_stage2`, `_run_stage3`, `_run_stage4` methods or equivalent public function calls
- Treats `RouterV6Pipeline.run()` as a black box: the adapter either wraps the full `.run()` as one stage OR decomposes it by calling the internal methods; both approaches are acceptable as long as the adapter does not modify `pipeline.py`

### R5. Contract Validation

Status: **required**

Each `PipelineStage` implementation may declare a `Contract`:

```python
@dataclass
class Contract:
    input_schema: dict[str, type]  # field name -> expected type
    output_schema: dict[str, type]
```

- When a stage has a `Contract`, the protocol runner validates `StageInput.data` against `input_schema` before execution and `StageOutput.data` against `output_schema` after execution
- Schema validation checks: (a) that the `data` object has all named fields, (b) that each field's type matches `isinstance(field, expected_type)`. It does NOT validate values, ranges, or semantic correctness.
- Validation failure raises `temper_placer.protocol.ContractViolation` with the stage name, which schema (input/output), and which field failed
- Contracts are optional — stages without a contract skip validation
- The `DeterministicPipeline` `Stage` base class does not need to implement `Contract` — the deterministic stages run within their own pipeline and do not require protocol-level contracts unless they are registered in the strategy registry

### R6. Stage Ordering Guarantee

Status: **required**

- Composite pipelines (registered via `register_composite`) provide stage ordering by construction: the ordered list is the declared order
- For ad-hoc pipelines built at runtime, the caller is responsible for ordering. The protocol runner accepts an ordered `list[PipelineStage]` and runs them sequentially
- Optionally (deferred): a `PhaseOrder` type that associates phases with a priority integer so that a `PipelineRunner` can topo-sort stages. This is **not** required for v1 — the composite registry already provides ordering
- Each stage must declare `requires: list[str]` and `provides: list[str]` — named data keys the stage consumes and produces. The protocol runner checks at pipeline construction time that the data flow is valid (no missing inputs, no type mismatches at key boundaries). This is a **runtime** check, not a compile-time phantom type

### R7. PipelineRunner

Status: **required**

A `PipelineRunner` class that takes an ordered list of `PipelineStage` instances and runs them:

```python
runner = PipelineRunner([stage1, stage2, stage3])
result = runner.run(initial_input)
```

- `run(initial_input: StageInput) -> StageOutput`: runs stages sequentially, feeding each stage's output as the next stage's input
- Validates contracts between stages (if declared)
- Collects per-stage timing and stores in `StageOutput.meta.timings`
- On `ContractViolation`, raises immediately (no recovery within the runner — fallback is handled at the strategy dispatch level)
- Provides a `trace()` method returning an execution trace: `list[(stage_name, timing_s, contract_satisfied)]`

### R8. Strategy Fallback

Status: **required**

The strategy dispatch function (`resolve_and_run`) must support fallback:

```python
def resolve_and_run(
    phase: str,
    strategies: list[str],
    input: StageInput,
    *,
    fallback: str | None = None,
) -> StageOutput:
```

- Tries each strategy name in `strategies` in order
- If a strategy raises (any exception), logs a warning and tries the next
- If none succeed and `fallback` is specified, tries the fallback strategy
- If fallback also fails, raises `StrategyExhaustedError` with the chain of failures
- This allows the closure test to try `strategy="benders"` with fallback to `"template"` — if Benders is not yet implemented and raises `NotImplementedError`, the template strategy runs instead

### R9. Backward Compatibility

Status: **required**

- **DeterministicPipeline**: The existing 26 `Stage` subclasses continue to work without modification. Their `run(state: BoardState) -> BoardState` interface is unchanged. A thin adapter wraps any `Stage` as a `PipelineStage` for use outside the deterministic pipeline, but the deterministic pipeline itself does not adopt the protocol internally.
- **PipelineOrchestrator**: `orchestrator.run()` continues to work as before. The adapter stages are opt-in — the orchestrator itself is not refactored.
- **RouterV6Pipeline**: `RouterV6Pipeline(path).run() -> RouterV6Result` continues to work. The adapter is additive.
- **Existing tests**: All tests in `tests/deterministic/`, `tests/regression/`, and `tests/` that call `stage.run(state)` or `PipelineOrchestrator(config).run()` continue to pass without modification.
- **Scripts**: The 118 scripts in `scripts/` are not required to adopt the protocol. They continue to work with direct imports. New scripts may optionally use the protocol.

### R10. Closure Test Integration

Status: **required**

The closure test at `packages/temper-placer/src/temper_placer/regression/closure_test.py` should use the strategy registry to dispatch placement and routing:

```python
placement_result = resolve_and_run(
    phase="placement",
    strategies=[strategy],  # from ClosureTest's strategy param
    input=StageInput(data=parsed, meta=StageMeta(seed=seed)),
    fallback="template",
)
routing_result = resolve_and_run(
    phase="routing",
    strategies=["router_v6"],
    input=StageInput(data=parsed, meta=StageMeta(seed=seed, placements=placement_result.data.placements)),
)
```

- The closure test imports from `temper_placer.protocol`, not from individual pipeline modules
- Changing the placement strategy requires only passing a different `strategy` string — no code changes to `closure_test.py`
- The closure test's expected output format (`benders_iterations`, `router_completion_pct`) is preserved through the adapter's `StageOutput.data` fields

## Success Criteria

- **SC1.** `from temper_placer.protocol import PipelineStage, StageInput, StageOutput, PipelineRunner` imports without pulling in any pipeline backend
- **SC2.** `PipelineRunner([stage1, stage2]).run(StageInput(data=...))` executes stages sequentially and returns a `StageOutput` with per-stage timings
- **SC3.** `resolve_and_run("placement", ["template"], input, fallback="template")` dispatches to the template strategy via the registry
- **SC4.** `resolve_and_run("placement", ["nonexistent"], input, fallback="template")` fails through to the fallback and returns the template strategy's result
- **SC5.** `resolve_and_run("placement", ["nonexistent"], input)` with no fallback raises `StrategyExhaustedError`
- **SC6.** The existing 26 deterministic `Stage` subclasses can be wrapped as `PipelineStage` via a single adapter function: `wrap_deterministic_stage(stage: Stage) -> PipelineStage`
- **SC7.** The existing `benders_placement(parsed, seed, strategy="template")` function continues to work unmodified
- **SC8.** A contract violation — e.g., a stage expecting `data.placements` but receiving `data` without that field — raises `ContractViolation` at the boundary before the next stage runs
- **SC9.** `PipelineRunner.trace()` returns accurate per-stage execution times for profiling
- **SC10.** The closure test produces real placement and routing results when run through `resolve_and_run`, without importing from `benders_loop` or `router_v6.adapter` directly

## Scope Boundaries

### In scope
- `PipelineStage` Protocol, `StageInput`, `StageOutput`, `PipelineRunner`, `Contract`
- Strategy registry with register/get/list/composite
- Adapter for `PipelineOrchestrator` phases as individually callable `PipelineStage` instances
- Adapter for `RouterV6Pipeline` as four `PipelineStage` instances
- `wrap_deterministic_stage()` adapter function
- `resolve_and_run()` with strategy fallback
- Contract validation at stage boundaries
- `requires`/`provides` data-flow validation at pipeline construction
- Integration with the closure test via `temper_placer.protocol`

### Deferred for later
- `PhaseOrder` topo-sort for ad-hoc stage ordering — v1 uses explicit ordered lists
- Compile-time phantom types for stage ordering — v1 uses runtime `requires`/`provides` checks
- Content-level validation (semantic checks beyond type matching) — v1 validates only field presence and type
- Unified pipeline configuration object — v1 passes configuration through `StageMeta` and individual stage constructors
- Migration of the 26 `DeterministicPipeline` stages to use the `PipelineStage` protocol internally — they are wrapped, not rewritten

### Outside this product's identity
- Replacing any existing pipeline system — all three pipelines continue as first-class citizens
- Changing the closure test's pass/fail criteria
- Performance optimization of the protocol layer — the adapter overhead is expected to be negligible relative to stage execution time
- Type-checker enforcement (mypy, pyright) of the Protocol — the Protocol enables type-checking but does not require CI gates on type coverage

## Dependencies

- `temper_placer.deterministic.pipeline.DeterministicPipeline` and 26 `Stage` subclasses — reference implementation
- `temper_placer.deterministic.stages.base.Stage` — existing ABC (wrapped, not modified)
- `temper_placer.router_v6.pipeline.RouterV6Pipeline` — existing implementation (wrapped, not modified)
- `temper_placer.pipeline.orchestrator.PipelineOrchestrator` — existing implementation (wrapped, not modified)
- `temper_placer.router_v6.adapter.route_pcb` — existing adapter (inspected for pattern, may be migrated to use protocol)
- `temper_placer.placement.benders_loop.benders_placement` — existing strategy function (inspected for pattern, may be migrated to use protocol)
- `temper_placer.regression.closure_test` — consumer of the protocol
- `scripts/` — 118 scripts that may optionally adopt the protocol

## Assumptions

1. The `PipelineOrchestrator`'s phase handlers can be called independently (they reference `self.state`, so the adapter must either create a fresh orchestrator per phase or extract the handler logic into standalone functions)
2. `RouterV6Pipeline`'s internal `_run_stage2`, `_run_stage3`, `_run_stage4` methods are callable with the outputs of the preceding stage — the adapter can construct the required `Stage2Output`/`Stage3Output` from the protocol-level data flow
3. The closure test's expected output format (`benders_iterations`, `router_completion_pct`) is fixed and authoritative; the adapter maps `StageOutput` fields to these expected keys
4. Strategy registration at module import time is acceptable — no conflicts arise from import ordering
5. The protocol layer overhead (dataclass construction, field validation) is negligible relative to stage execution times (seconds to minutes)
