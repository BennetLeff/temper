---
title: "Unified Stage Protocol: Composing Three Incompatible Pipeline Systems"
date: 2026-06-22
category: architecture-patterns
module: temper_placer
problem_type: architecture_pattern
component: development_workflow
severity: high
applies_when:
  - Multiple pipeline systems with incompatible interfaces need to share stages
  - Existing pipeline code cannot be modified internally
  - Stages from different subsystems need drop-in composition
  - A shared contract is needed without forcing base-class inheritance
tags:
  - protocol
  - structural-subtyping
  - pipeline
  - adapter-pattern
  - strategy-registry
  - dag-validation
  - backward-compatibility
---

# Unified Stage Protocol: Composing Three Incompatible Pipeline Systems

## Context

temper had three pipeline systems with fundamentally incompatible interfaces:

| Pipeline | Interface | Invocation |
|---|---|---|
| `PipelineOrchestrator` (8 phases) | `(PipelineState) -> PipelineState` | phase handler on `self.state` |
| `RouterV6Pipeline` (4 stages) | `.run(Path) -> RoutingResult` | monolithic instance method |
| `DeterministicPipeline` (26 stages) | `Stage.run(state: BoardState) -> BoardState` | individual stage instances |

Without a shared contract, stages from one system could not be used in another.
Composing, for example, RouterV6's escape-via detection inside the
DeterministicPipeline's placement pipeline required either duplicating code or
coupled integration adapters. Three separate strategy-dispatch mechanisms
existed (one per system), each with different lifecycle and error semantics.

The goal was a single Python Protocol class that all stages could satisfy
without modifying any existing pipeline internals, combined with a
string-keyed strategy registry and DAG-validated data-flow chain.

## Guidance

### Core architecture

```
                    PipelineStage (Protocol)
                   ┌────────────────────────┐
                   │ name: str              │
                   │ run(StageInput)        │
                   │   -> StageOutput       │
                   │ requires: list[str]    │
                   │ provides: list[str]    │
                   │ contract: Contract|None│
                   └────────────────────────┘
                              ▲
         ┌────────────────────┼────────────────────┐
         │                    │                    │
  Orchestrator         RouterV6             Deterministic
  Adapter              Adapter              Adapter
  (8 stages)           (5 stages)           (26 stages)
```

Each adapter wraps its pipeline's stages into `PipelineStage`-conformant
objects without modifying the original classes. The wrapped stages register
themselves into a module-level strategy registry keyed by `(phase: str,
name: str)`.

### StageMeta — the shared thread

`StageMeta` is the data container forwarded across every stage, carrying
context that all pipeline systems need but none should own:

```python
@dataclass
class StageMeta:
    seed: int = 42                # Reproducibility across runs
    timestamp: float = 0.0        # Pipeline start time
    trace_context: dict[str, Any] # Opaque per-stage configuration
    timings: dict[str, float]     # Per-stage wall-clock times
```

`PipelineRunner` accumulates timings in `meta.timings` automatically as
stages execute, and forward-accumulates them from input→output. No stage
needs to know about timing collection.

### Strategy registry with priority ordering

The registry decouples pipeline phases from strategy selection:

```python
# Module-level, idempotent
register("routing", "router_v6_stage0", lambda: RouterV6Stage0_LoadPCB())
register("routing", "orchestrator", lambda: OrchestratorRoutingStage())

# Composite: ordered (phase, name) sequence
register_composite("router_v6_full", [
    ("routing", "router_v6_stage0"),
    ("routing", "router_v6_stage1"),
    ("routing", "router_v6_stage2"),
    ("routing", "router_v6_stage3"),
    ("routing", "router_v6_stage4"),
])
```

`resolve_and_run(phase, strategies, input, fallback=...)` tries strategies
in priority order: each name is first looked up as a composite; if not found,
it is treated as a single `(phase, name)` lookup. The first strategy that
completes without exception wins.

### String-based requires/provides with DAG validation

Stages declare data dependencies via class-level lists:

```python
class OrchestratorRoutingStage:
    requires = ["board", "netlist", "placement_state"]
    provides = ["routing_result"]
```

At `PipelineRunner` construction time, `_validate_data_flow()` walks the
ordered stage list and verifies every `requires` key is provided by a prior
stage. This is a forward-only DAG check — cycles are impossible by
construction (sequential execution). The check raises `DataFlowError` with
the stage name, missing keys, and currently available keys.

### Contract enforcement

The optional `Contract` dataclass enables schema validation on input and
output data:

```python
@dataclass
class Contract:
    input_schema: dict[str, type]   # e.g., {"board": ParsedPCB}
    output_schema: dict[str, type]  # e.g., {"result": PlacementResult}
```

`PipelineRunner` checks input contracts before each stage and output
contracts after each stage, raising `ContractViolation` on missing fields
or type mismatches. Stages with no `contract` (or `contract=None`) skip
validation.

### Adapter pattern — no internal modifications

Each pipeline system is wrapped via a thin adapter that translates between
protocol types and the pipeline's native types:

**DeterministicPipeline (26 stages):** Trivially wrapped via
`_WrappedDeterministicStage`, which translates `StageInput.data` (a
`BoardState` frozen dataclass) → `stage.run(state)` → `StageOutput`.
The frozen-dataclass design of `BoardState` mapped cleanly — no
mutability issues, no hidden state.

**RouterV6Pipeline (5 stages):** Required temporary `RouterV6Pipeline`
instance creation inside each `run()` because the internal `_run_stage*`
methods reference `self.*` attributes (configuration flags, accumulators).
The adapter instantiates a fresh pipeline instance per invocation, sets the
configuration, calls the target `_run_stage*` method, and discards the
instance. Slightly more overhead than the deterministic adapter but zero
modifications to `RouterV6Pipeline`.

**PipelineOrchestrator (8 phases):** Factory function
`_make_orchestrator_stage()` creates a class per phase. Each `run()` either
injects a `PipelineConfig` (for the first phase) or a `PipelineState` (for
subsequent phases) into a fresh `PipelineOrchestrator` instance, calls the
target phase handler, and returns the resulting state.

### Backward compatibility gate

All 84 existing tests passed unchanged. The Protocol class does not require
any existing stage to import, inherit from, or know about `PipelineStage`.
Structural subtyping means any object with `name: str` and
`run(self, input: StageInput) -> StageOutput` satisfies the protocol,
whether or not it explicitly declares conformance.

## Why This Matters

Before the Protocol, adding a new strategy to the routing phase meant
writing bespoke dispatch logic inside the phase's handler function, with
ad-hoc error handling and no shared validation. Strategy selection was
tightly coupled to the pipeline system — RouterV6's routing was invisible
to the orchestrator, and vice versa.

The Protocol + registry makes strategy dispatch declarative. To add a new
routing strategy, write a class with `name`, `requires`, `provides`, and
`run(StageInput) -> StageOutput`, then call `register("routing", name,
factory)`. `resolve_and_run` handles fallback, error collection, and
strategy exhaustion without changes to any existing code.

The adapter pattern preserves the existing pipeline systems as-is. No
internal refactoring of `PipelineOrchestrator`, `RouterV6Pipeline`, or
`DeterministicPipeline` was required. Each adapter is ~60–190 lines and
lives in its own module under `adapters/`. If a pipeline system is
eventually removed, its adapter can be deleted without impact on the
others.

The DAG validation at construction time catches data-flow errors before any
stage runs. A missing `requires` key fails at `PipelineRunner.__init__`
rather than at the Nth stage after N-1 stages have already executed and
mutated state. This is a material improvement over the previous behavior,
where data-flow errors manifested as late-stage `KeyError` or `AttributeError`
with no indication of which stage failed to provide the data.

## When to Apply

Apply this pattern when:

- Multiple pipeline systems with incompatible interfaces need to share
  stages or be composed into a single execution graph.
- You need a shared contract that existing code can satisfy without
  modification (inheritance is not an option).
- Strategy dispatch needs to be decoupled from the runner — phases are
  plain strings, strategies are registry entries, and the runner just
  resolves and executes in priority order.
- Data-flow validation at construction time is valuable (catching
  configuration errors before any work is done).

Do NOT apply when:

- A single pipeline system is sufficient and there is no composition
  requirement across systems.
- Performance is critical and the adapter overhead (per-stage instance
  creation, `isinstance` checks, schema validation) is unacceptable in a
  hot loop. The adapters add ~0.1–1ms per stage for contract validation and
  type translation.
- The pipeline systems share a common base class and the migration cost
  to a Protocol is higher than the composition benefit.

## Examples

### The Protocol class

```python
@runtime_checkable
class PipelineStage(Protocol):
    """Structural protocol for any pipeline stage."""

    name: str

    def run(self, input: StageInput) -> StageOutput: ...
```

### Deterministic adapter (trivial wrapping)

```python
class _WrappedDeterministicStage:
    def __init__(self, stage: Stage, requires=None, provides=None):
        self._stage = stage
        self.name = stage.name
        self.requires = requires or []
        self.provides = provides or []
        self.contract = None

    def run(self, input: StageInput) -> StageOutput:
        state = input.data          # BoardState
        result = self._stage.run(state)
        return StageOutput(data=result, meta=input.meta)
```

### RouterV6 adapter (temporary instance)

```python
class RouterV6Stage3_TopologicalRouting:
    name = "router_v6/topological_routing"
    requires = ["parsed_pcb", "stage2_output"]
    provides = ["stage3_output"]
    contract = None

    def run(self, input):
        data = input.data
        pcb = data.pcb if hasattr(data, "pcb") else data
        stage2 = data.stage2_output if hasattr(data, "stage2_output") else data
        pipeline = RouterV6Pipeline(
            verbose=False,
            enable_theta_star=True,
            enable_lazy_theta_star=True,
            enable_smoothing=True,
        )
        stage3 = pipeline._run_stage3(pcb, stage2)
        return StageOutput(data=stage3, meta=input.meta)
```

### Orchestrator adapter (factory per phase)

```python
def _make_orchestrator_stage(phase_value, handler_name, requires, provides):
    class _OrchestratorPhaseStage:
        name = f"orchestrator/{phase_value}"
        requires = requires
        provides = provides
        contract = None

        def run(self, input):
            phase = PipelinePhase(phase_value)
            data = input.data
            if isinstance(data, PipelineConfig):
                orchestrator = PipelineOrchestrator(data)
            elif isinstance(data, PipelineState):
                orchestrator = PipelineOrchestrator(data.config)
                orchestrator.state = data
            handler = getattr(orchestrator, handler_name)
            new_state = handler(orchestrator.state)
            return StageOutput(data=new_state, meta=input.meta)

    return _OrchestratorPhaseStage

OrchestratorRoutingStage = _make_orchestrator_stage(
    "routing", "_run_routing",
    requires=["board", "netlist", "placement_state"],
    provides=["routing_result"],
)
```

### Strategy dispatch with fallback

```python
def resolve_and_run(
    phase: str,
    strategies: list[str],
    input: StageInput,
    *,
    fallback: str | None = None,
) -> StageOutput:
    from temper_placer import strategy_registry

    failure_chain: list[tuple[str, Exception]] = []
    all_names = list(strategies)
    if fallback:
        all_names.append(fallback)

    for name in all_names:
        try:
            try:
                stages = strategy_registry.get_composite(name)
            except KeyError:
                stages = [strategy_registry.get(phase, name)]
            runner = PipelineRunner(stages)
            return runner.run(input)
        except Exception as exc:
            logger.warning("Strategy '%s' failed: %s", name, exc)
            failure_chain.append((name, exc))

    raise StrategyExhaustedError(phase, all_names, failure_chain)
```

### DAG validation at construction time

```python
def _validate_data_flow(stages: list[PipelineStage]) -> None:
    available: set[str] = set()
    for stage in stages:
        requires = getattr(stage, "requires", []) or []
        provides = getattr(stage, "provides", []) or []
        missing = [k for k in requires if k not in available]
        if missing:
            raise DataFlowError(stage.name, missing, available)
        available.update(provides)
```

This fires at `PipelineRunner.__init__`, not at `run()`. A broken
requires/provides chain is caught immediately, before any computation.

## Related

- `packages/temper-placer/src/temper_placer/protocol.py` — `StageMeta`, `StageInput`, `StageOutput`, `PipelineStage`, `Contract`
- `packages/temper-placer/src/temper_placer/runner.py` — `PipelineRunner`, `_validate_data_flow`, `resolve_and_run`
- `packages/temper-placer/src/temper_placer/strategy_registry.py` — module-level `(phase, name)` registry and composites
- `packages/temper-placer/src/temper_placer/adapters/deterministic_adapter.py` — wraps `Stage.run(state)→state` as `PipelineStage`
- `packages/temper-placer/src/temper_placer/adapters/router_v6_stage_adapter.py` — 5 RouterV6 stages as `PipelineStage`
- `packages/temper-placer/src/temper_placer/adapters/orchestrator_adapter.py` — 8 orchestrator phases as `PipelineStage`
- `docs/solutions/architecture-patterns/pydantic-dataclass-migration.md` — sibling pattern (structural typing for data models)
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — sibling pattern (structural quality enforcement)
