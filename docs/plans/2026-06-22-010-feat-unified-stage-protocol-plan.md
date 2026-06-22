---
date: 2026-06-22
type: feat
origin: docs/brainstorms/2026-06-22-unified-stage-protocol-requirements.md
status: active
---

# Plan: Unified Stage Protocol — Protocol Class, Strategy Registry, Adapters for All Three Pipelines

## Problem Frame

Temper has three pipeline systems with incompatible execution interfaces:

| Pipeline | Interface | State model | Stage count |
|---|---|---|---|
| **DeterministicPipeline** | `Stage.run(state: BoardState) -> BoardState` | Frozen dataclass | 26 `Stage` subclasses |
| **PipelineOrchestrator** | `Orchestrator.run() -> PipelineState` | Mutable dataclass | 8 phase handlers in `dict[Phase, Callable]` |
| **RouterV6Pipeline** | `Pipeline.run(path: Path) -> RouterV6Result` | File-path-based; typed dataclass outputs | 5 stages (0–4) |

Each pipeline is a closed system. A `PipelineOrchestrator` phase cannot be dropped into a `DeterministicPipeline` stage sequence. A `RouterV6Pipeline` stage cannot be composed with `DeterministicPipeline` stages without ad-hoc scripting. The 118 scripts under `scripts/` bypass all three pipeline APIs because no common interface exists.

The `PipelineOrchestrator` already embeds an ad-hoc strategy pattern — its `_run_geometric`, `_run_routing`, and `_run_refinement` methods hard-code which placement and routing backend to use. The `benders_placement` function in `placement/benders_loop.py` implements a proto-strategy dispatch (`if strategy == "template": ...`). The `RouterV6Pipeline` adapter in `router_v6/adapter.py` wraps `route_pcb()` as a standalone function. These are proto-protocols — the next step is to unify them.

The project roadmap calls for a closure test as the universal acceptance criterion: _parse → place → route → DRC_. Without a common stage protocol, each new placement or routing algorithm requires changes to the closure test, the orchestrator, and any script that exercises the pipeline.

## Requirements Trace

| Requirement | Source | Acceptance |
|---|---|---|
| R1 — PipelineStage Protocol | Req doc | `from temper_placer.protocol import PipelineStage, StageInput, StageOutput, PipelineRunner` imports without pulling in any pipeline backend (SC1) |
| R2 — Strategy Registry | Req doc | `register()`/`get()`/`list()`/`register_composite()`/`get_composite()` all functional; idempotent import (SC3, SC4, SC5) |
| R3 — Orchestrator Adapter | Req doc | 8 phases registered; each individually callable as `PipelineStage`; `PipelineOrchestrator.run()` still works |
| R4 — RouterV6 Adapter | Req doc | 5 stages registered under phase `"routing"`; composite `"router_v6_full"` chains all 5; `RouterV6Pipeline.run()` unmodified |
| R5 — Contract Validation | Req doc | Schema checks (field presence + `isinstance`) at stage boundaries; `ContractViolation` raised on mismatch (SC8) |
| R6 — Stage Ordering | Req doc | `requires`/`provides` data-key validation at pipeline construction; composite ordering by declaration |
| R7 — PipelineRunner | Req doc | Sequential run with contract validation, timing collection, `trace()` output (SC2, SC9) |
| R8 — Strategy Fallback | Req doc | `resolve_and_run(phase, strategies, input, fallback=...)` tries strategies in order, raises `StrategyExhaustedError` (SC3, SC4, SC5) |
| R9 — Backward Compatibility | Req doc | All 26 deterministic Stage subclasses, `orchestrator.run()`, `RouterV6Pipeline.run()`, all existing tests, and all 118 scripts unchanged (SC6, SC7) |
| R10 — Closure Test Integration | Req doc | `closure_test.py` uses `resolve_and_run` via `temper_placer.protocol`; strategy dispatch by string parameter (SC10) |

## Key Technical Decisions

**K1. Protocol over inheritance.** `PipelineStage` is a `typing.Protocol` with `name: str` and `run(input: StageInput) -> StageOutput`. Existing classes satisfy by structural subtyping — no subclassing of the protocol required.

**K2. Dataclass trio resolves the undefined gap.** The requirements doc introduces `StageInput`, `StageOutput`, and `StageMeta` as dataclasses but leaves them undefined. This plan defines them precisely:

```python
@dataclass
class StageMeta:
    seed: int = 42
    timestamp: float = 0.0          # time.time() at start
    trace_context: dict = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)  # stage_name -> seconds

@dataclass
class StageInput:
    data: Any                        # stage-specific payload
    meta: StageMeta = field(default_factory=StageMeta)

@dataclass
class StageOutput:
    data: Any                        # stage-specific result
    meta: StageMeta = field(default_factory=StageMeta)
    contract_satisfied: bool | None = None
```

`StageMeta` is the shared thread that passes seed, trace context, and accumulated timings across stages. Adapters populate `data` with their internal types (`ParsedPCB`, `Stage2Output`, `PipelineState`, `BoardState`, etc.) — the Protocol does not constrain `data`'s type.

**K3. Strategy registry with string phase keys.** Phases are `str` (not `Enum`) to avoid coupling the registry to any pipeline's phase definitions. Registration is module-level and idempotent. The registry is a module-global `dict[tuple[str, str], Callable[[], PipelineStage]]`.

**K4. Adapter modules — no internal modifications.** Each adapter lives in its own module under `temper_placer.adapters/`. Adapters translate at the protocol boundary only — the wrapped pipeline's internals are untouched. This extends the existing pattern already used by `router_v6/adapter.py` and `placement/benders_loop.py`.

**K5. `requires`/`provides` as runtime DAG validation.** Each stage declares `requires: list[str]` and `provides: list[str]` — named data keys consumed and produced. `PipelineRunner.__init__` checks at construction time that the data flow is valid: no missing inputs (a key required by stage _N+1_ must be provided by some stage ≤ _N_), and no type mismatches at key boundaries. Phantom types are deferred.

**K6. `wrap_deterministic_stage()` as a single function, not a class hierarchy.** The 26 deterministic stages keep their `run(state: BoardState) -> BoardState` signature. A single adapter function `wrap_deterministic_stage(stage: Stage, requires=None, provides=None) -> PipelineStage` creates a closure that translates `StageInput.data` (a `BoardState`) → `stage.run(state)` → `StageOutput(data=result_state)`.

**K7. Orchestrator adapter decomposes but does not rewrite.** The `PipelineOrchestrator`'s phase handlers reference `self.state`. The adapter creates a fresh `PipelineOrchestrator` per phase call, injects data into `self.state`, calls the handler, and extracts the result. This is non-destructive — `orchestrator.run()` works as before.

**K8. RouterV6 adapter wraps internal `_run_stage*` methods directly.** `RouterV6Pipeline._run_stage2/stage3/stage4` are public-enough methods. The adapter calls them with protocol-translated inputs. Stage0 is `parse_kicad_pcb_v6` wrapped as a stage. Stage1 is `generate_escape_vias`/`identify_dense_packages` wrapped as a stage.

## Directory Layout

```
temper_placer/
├── protocol.py                          # NEW — PipelineStage Protocol, StageInput/Output/Meta, Contract, ContractViolation
├── strategy_registry.py                 # NEW — register/get/list/register_composite/get_composite
├── runner.py                            # NEW — PipelineRunner, resolve_and_run, StrategyExhaustedError
├── adapters/
│   ├── __init__.py                      # NEW — re-exports
│   ├── deterministic_adapter.py         # NEW — wrap_deterministic_stage()
│   ├── orchestrator_adapter.py          # NEW — 8 phase-specific PipelineStage classes
│   └── router_v6_stage_adapter.py       # NEW — 5 stage-specific PipelineStage classes + composite
```

All new modules live under `packages/temper-placer/src/temper_placer/`.

## Implementation Units

---

### U1. Protocol Core Dataclasses (`StageMeta`, `StageInput`, `StageOutput`)

**Goal:** Define the shared data containers that resolve the undefined-gap from the requirements doc. These three dataclasses carry payloads across all adapters and the runner without coupling to any pipeline backend.

**Requirements:** R1

**Dependencies:** None

**Files:**
- New: `packages/temper-placer/src/temper_placer/protocol.py`

**Approach:**
- `StageMeta`: carries `seed: int`, `timestamp: float`, `trace_context: dict`, `timings: dict[str, float]` (accumulated per-stage wall-clock). Default-constructible.
- `StageInput`: carries `data: Any` (the stage-specific payload — `ParsedPCB`, `BoardState`, `PipelineState`, etc.) and `meta: StageMeta`.
- `StageOutput`: carries `data: Any` (the stage-specific result), `meta: StageMeta` (forwarded + annotated), and optional `contract_satisfied: bool | None`.
- All three are `@dataclass` with `field(default_factory=...)` for dict fields to avoid mutable-default traps.
- The module imports from `dataclasses`, `typing` only — no pipeline backend imports.

**Patterns to follow:** `BoardState` at `deterministic/state.py:15-39` (frozen dataclass with optional fields). `PipelineState` at `pipeline/orchestrator.py:106-161` (mutable dataclass with `field(default_factory=dict)` for timings).

**Test scenarios:**
- `StageMeta()` constructs with defaults (seed=42, empty timings/trace_context).
- `StageInput(data={"placements": {...}}, meta=StageMeta(seed=99))` round-trips fields.
- `StageOutput(data=result_obj, meta=meta, contract_satisfied=True)` preserves all fields.
- Timeline: `meta.timings["stage1"] = 1.23` survives through multiple stage outputs.

**Verification:** `from temper_placer.protocol import StageMeta, StageInput, StageOutput` imports with zero side-effects, no pipeline backend imports triggered. Success criterion SC1.

---

### U2. PipelineStage Protocol + Contract

**Goal:** Define the `PipelineStage` Protocol and `Contract`/`ContractViolation` types so stages from all three pipelines are structurally compatible.

**Requirements:** R1, R5

**Dependencies:** U1 (shares `protocol.py`)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/protocol.py` (add to file from U1)

**Approach:**
- `PipelineStage` is a `typing.Protocol` with:
  - `name: str` — class attribute or property.
  - `run(self, input: StageInput) -> StageOutput` — the single execution method.
  - Optional `requires: list[str]` and `provides: list[str]` — class-level declarations, default `[]`.
  - Optional `contract: Contract | None` — class-level declaration, default `None`.
- `Contract` is a `@dataclass` with `input_schema: dict[str, type]` and `output_schema: dict[str, type]`.
- `ContractViolation` extends `Exception` with `stage_name: str`, `schema: str` ("input" or "output"), `field_name: str`, `expected_type: type`, `actual_type: type`.
- The Protocol module imports only from `dataclasses`, `typing` — zero pipeline backend dependencies.

**Patterns to follow:** `Stage` ABC at `deterministic/stages/base.py:4-15` (abstract `name` property and `run` method). The Protocol mirrors this shape but as structural subtyping.

**Test scenarios:**
- A class with `name = "test"` and `def run(self, input: StageInput) -> StageOutput: ...` satisfies `isinstance(obj, PipelineStage)` without inheriting.
- `Contract(input_schema={"placements": dict}, output_schema={"routing_result": RoutingResult})` validates correctly.
- `ContractViolation("MyStage", "input", "placements", dict, int)` formats with all fields accessible.

**Verification:** `PipelineStage`, `Contract`, `ContractViolation` importable from `temper_placer.protocol`. No pipeline code imported. Success criterion SC1.

---

### U3. Strategy Registry

**Goal:** Provide a module-level registry keyed by `(phase: str, name: str)` for stage factories, with idempotent registration and composite pipeline support.

**Requirements:** R2

**Dependencies:** U2 (imports `PipelineStage` from `protocol`)

**Files:**
- New: `packages/temper-placer/src/temper_placer/strategy_registry.py`

**Approach:**
- Module-level `_registry: dict[tuple[str, str], Callable[[], PipelineStage]] = {}`.
- Module-level `_composites: dict[str, list[tuple[str, str]]] = {}`.
- `register(phase: str, name: str, stage_factory: Callable[[], PipelineStage]) -> None`: inserts into `_registry`. If key already exists, is a no-op (idempotent).
- `get(phase: str, name: str) -> PipelineStage`: calls `_registry[(phase, name)]()` to instantiate. Raises `KeyError` with descriptive message if not found.
- `list(phase: str | None = None) -> dict`: returns `{f"{phase}/{name}": stage} for (p, n) in _registry if phase is None or p == phase`.
- `register_composite(name: str, stages: list[tuple[str, str]]) -> None`: stores ordered `[(phase, name), ...]` in `_composites[name]`. Idempotent.
- `get_composite(name: str) -> list[PipelineStage]`: resolves each `(phase, name)` via `get()` and returns the ordered list.

**Patterns to follow:** `benders_loop.py:57-63` — the `if strategy == "template":` dispatch pattern generalized to a registry. `PipelineOrchestrator.__init__` at `orchestrator.py:172-181` — phase→handler mapping as a model for `(phase, name)` keying.

**Test scenarios:**
- `register("placement", "template", lambda: TemplateStage())` followed by `get("placement", "template")` returns a `TemplateStage` instance.
- Double `register` with same key is a no-op (no exception).
- `register_composite("full_test", [("a", "x"), ("b", "y")])` followed by `get_composite("full_test")` returns two instantiated stages in order.
- `get("nonexistent", "phase")` raises `KeyError`.
- `list("placement")` returns only placement-phase entries.

**Verification:** Success criteria SC3 (dispatch via registry), SC4 (fallback chain), SC5 (exhausted error) all depend on registry correctness.

---

### U4. PipelineRunner + Data-Flow Validation

**Goal:** Provide a `PipelineRunner` that executes an ordered list of stages sequentially, validates contracts and data-flow, collects timings, and exposes a `trace()` method.

**Requirements:** R6, R7

**Dependencies:** U1, U2 (imports `StageInput`, `StageOutput`, `StageMeta`, `PipelineStage`, `Contract`, `ContractViolation`)

**Files:**
- New: `packages/temper-placer/src/temper_placer/runner.py`

**Approach:**
- `PipelineRunner.__init__(self, stages: list[PipelineStage])`: validates the `requires`/`provides` data-flow DAG:
  - Iterate stages in order. Track a set of `available_keys` (initially empty).
  - For each stage: verify every key in `stage.requires` is in `available_keys`. Raise `DataFlowError(stage.name, missing, available_keys)` if not.
  - Add every key in `stage.provides` to `available_keys`.
  - This is a construction-time check, not a runtime check.
- `run(self, initial_input: StageInput) -> StageOutput`:
  - Set `initial_input.meta.timestamp = time.time()`.
  - For each stage:
    1. If `stage.contract` exists, validate `input.data` against `contract.input_schema` using `_validate_schema()`. Raise `ContractViolation` on failure.
    2. `t0 = time.perf_counter()`.
    3. `output = stage.run(input)`.
    4. `dt = time.perf_counter() - t0`.
    5. Set `output.meta.timings[stage.name] = dt`.
    6. If `stage.contract` exists, validate `output.data` against `contract.output_schema`.
    7. Set `output.contract_satisfied = True` if both validations passed (or `None` if no contract).
    8. `input = output` (feed-forward).
  - Return final `StageOutput` with accumulated `meta.timings`.
- `trace(self) -> list[tuple[str, float, bool | None]]`:
  - Returns `[(stage.name, timings[stage.name], contract_satisfied), ...]` from the last run.
  - Raises `RuntimeError` if `run()` has not been called.
- `_validate_schema(data: Any, schema: dict[str, type], stage_name: str, schema_name: str) -> None`:
  - For each `(field_name, expected_type)` in `schema`:
    - Assert `hasattr(data, field_name)` — raise `ContractViolation` with missing field info if not.
    - Assert `isinstance(getattr(data, field_name), expected_type)` — raise `ContractViolation` with type mismatch info if not.
- `DataFlowError` extends `Exception` with `stage_name`, `missing_keys`, `available_keys`.
- `StrategyExhaustedError` extends `Exception` with `phase`, `attempted_strategies`, `failure_chain: list[(str, Exception)]`.

**Patterns to follow:** `DeterministicPipeline.run()` at `deterministic/pipeline.py:14-18` — simple sequential loop. `PipelineOrchestrator.run()` at `pipeline/orchestrator.py:225-270` — per-phase timing via `time.time()`.

**Test scenarios:**
- `PipelineRunner([stage1, stage2]).run(StageInput(data=...))` executes both stages and returns `StageOutput` with non-empty `meta.timings`.
- `runner.trace()` returns per-stage timing tuples with correct names.
- Stage with `requires=["foo"]` where no prior stage provides `"foo"` raises `DataFlowError` at construction.
- Stage with `Contract(input_schema={"x": int})` receiving `data` with `x="string"` raises `ContractViolation` with `actual_type=str`.
- Stage without `Contract` skips validation (no error raised).
- `meta.timings` accumulates across stages: the second stage's output contains both its own and the first stage's timing.

**Verification:** Success criteria SC2 (sequential execution with timings), SC8 (contract violation at boundary), SC9 (trace accuracy).

---

### U5. Strategy Fallback (`resolve_and_run`)

**Goal:** Provide a dispatch function that tries a list of strategies in order, with optional fallback, and raises `StrategyExhaustedError` when all fail.

**Requirements:** R8

**Dependencies:** U3 (strategy registry), U4 (runs PipelineRunner internally)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/runner.py` (add `resolve_and_run` to file from U4)

**Approach:**
- `resolve_and_run(phase: str, strategies: list[str], input: StageInput, *, fallback: str | None = None) -> StageOutput`:
  - `failure_chain: list[(str, Exception)] = []`.
  - For each `name` in `strategies`:
    1. Try `stage = strategy_registry.get(phase, name)`.
    2. Try `runner = PipelineRunner([stage]); result = runner.run(input)`.
    3. If no exception, return `result`.
    4. On any `Exception`, log a warning with the strategy name and exception message. Append `(name, e)` to `failure_chain`. Continue.
  - If `fallback` is not None:
    1. Try `stage = strategy_registry.get(phase, fallback)`.
    2. Try `runner = PipelineRunner([stage]); result = runner.run(input)`.
    3. On success, return `result`.
    4. On exception, append to `failure_chain`.
  - Raise `StrategyExhaustedError(phase, strategies + ([fallback] if fallback else []), failure_chain)`.
- Imports `strategy_registry` module (not individual pipeline modules).

**Patterns to follow:** `benders_loop.py:57-63` — the `if strategy == "template":` try/fallback pattern generalized. `closure_test.py:86-114` — the existing Benders try/except block that becomes a single `resolve_and_run` call.

**Test scenarios:**
- `resolve_and_run("placement", ["template"], input)` returns `StageOutput` from template strategy (SC3).
- `resolve_and_run("placement", ["nonexistent"], input, fallback="template")` fails first, succeeds via fallback (SC4).
- `resolve_and_run("placement", ["nonexistent"], input)` with no fallback raises `StrategyExhaustedError` (SC5).
- `resolve_and_run("placement", ["bad_stage"], input, fallback="also_bad")` where both fail raises `StrategyExhaustedError` with `failure_chain` containing both exceptions.

**Verification:** Success criteria SC3, SC4, SC5.

---

### U6. DeterministicPipeline Stage Wrapper

**Goal:** Provide `wrap_deterministic_stage()` so any of the 26 `Stage` subclasses can be used as a `PipelineStage` without modification.

**Requirements:** R9, R6

**Dependencies:** U2 (PipelineStage Protocol), U1 (StageInput/StageOutput)

**Files:**
- New: `packages/temper-placer/src/temper_placer/adapters/__init__.py`
- New: `packages/temper-placer/src/temper_placer/adapters/deterministic_adapter.py`

**Approach:**
- `wrap_deterministic_stage(stage: Stage, *, requires: list[str] | None = None, provides: list[str] | None = None) -> PipelineStage`:
  - Returns an object with:
    - `name = stage.name`
    - `requires = requires or []`
    - `provides = provides or []`
    - `contract = None` (deterministic stages do not declare protocol-level contracts by default)
    - `run(self, input: StageInput) -> StageOutput`:
      1. Extract `board_state: BoardState = input.data` (adapter expects `data` to be a `BoardState`).
      2. Call `result_state = stage.run(board_state)`.
      3. Forward `meta` from input, annotate stage name.
      4. Return `StageOutput(data=result_state, meta=input.meta)`.
- The wrapper does **not** modify `Stage` ABC or any subclass. `Stage.run(state: BoardState) -> BoardState` is called as-is.
- The wrapper does **not** register stages in the strategy registry — deterministic stages are composed within `DeterministicPipeline`, not dispatched by name. Registration is opt-in via explicit `register()` calls if a stage is needed externally.

**Patterns to follow:** The deterministic pipeline's own run loop at `deterministic/pipeline.py:14-18` — state feeds from one stage to the next. The wrapper replicates this as a protocol translation layer.

**Test scenarios:**
- `wrapped = wrap_deterministic_stage(ClearanceGridStage()); isinstance(wrapped, PipelineStage)` is `True`.
- `wrapped.run(StageInput(data=board_state))` returns `StageOutput` with `data` being the modified `BoardState`.
- The original `ClearanceGridStage` instance is unmodified and still works with `stage.run(board_state)` directly.
- `wrap_deterministic_stage(MyStage(), requires=["board", "netlist"], provides=["clearance_grid"])` surfaces `requires`/`provides` for data-flow validation.

**Verification:** Success criterion SC6. All 26 `Stage` subclasses unmodified. Existing tests in `tests/deterministic/` pass unchanged.

---

### U7. PipelineOrchestrator Adapter (8 Phases)

**Goal:** Create adapter stages for all 8 `PipelineOrchestrator` phases, registered under the `"orchestrator"` name with their respective phase strings.

**Requirements:** R3, R9

**Dependencies:** U1 (StageInput/StageOutput), U2 (PipelineStage Protocol), U3 (strategy registry), U6 (adapters package)

**Files:**
- New: `packages/temper-placer/src/temper_placer/adapters/orchestrator_adapter.py`

**Approach:**
- Each of the 8 phases gets a standalone class (thin wrapper, not a class hierarchy):
  - `OrchestratorInputStage`, `OrchestratorSemanticStage`, `OrchestratorTopologicalStage`, `OrchestratorPreflightStage`, `OrchestratorGeometricStage`, `OrchestratorRoutingStage`, `OrchestratorRefinementStage`, `OrchestratorOutputStage`.
- Each class:
  - Has a `name` property: `"orchestrator/<phase_value>"` (e.g., `"orchestrator/geometric"`).
  - `run(self, input: StageInput) -> StageOutput`:
    1. Unpack `config: PipelineConfig = input.data` (adapter expects `data` to be a `PipelineConfig` + any upstream state).
    2. Create a fresh `PipelineOrchestrator(config)`. Populate `self.state` from `input.data` (the orchestrator's `PipelineState` or `None` for the first phase).
    3. Call only the specific phase handler: `orchestrator.phases[phase](orchestrator.state)`.
    4. Return `StageOutput(data=orchestrator.state, meta=input.meta)`.
  - The wrapped stages do **not** call `orchestrator.run()` — each phase is individually callable.
- At module import time, each stage registers itself:
  ```python
  register("input", "orchestrator", lambda: OrchestratorInputStage())
  register("semantic", "orchestrator", lambda: OrchestratorSemanticStage())
  # ... etc for all 8 phases
  ```
- The `PipelineOrchestrator` class itself is unmodified. `orchestrator.run()` still works as before.
- Each adapter stage declares `requires`/`provides` for data-flow validation:
  - Input stage: `requires=[]`, `provides=["board", "netlist", "constraints"]`.
  - Semantic stage: `requires=["board", "netlist"]`, `provides=["loops"]`.
  - Topological stage: `requires=["board", "netlist", "constraints"]`, `provides=["deterministic_result"]`.
  - Etc.

**Key implementation detail — the `self.state` problem:** The orchestrator's phase handlers reference `self.state`. The adapter creates a fresh orchestrator per phase call and injects data. This is safe because each phase handler is a pure function of `self.state` (it reads state fields, writes back, and returns). The adapter does not run the orchestrator's main loop — it only calls individual phase handlers.

**Patterns to follow:** `PipelineOrchestrator.__init__` at `pipeline/orchestrator.py:166-181` — the phase→handler dict. Each adapter class mirrors the handler type `Callable[[PipelineState], PipelineState]`.

**Test scenarios:**
- `OrchestratorGeometricStage().run(StageInput(data=pipeline_state))` calls only `_run_geometric` and returns updated state.
- All 8 phases are retrievable via `registry.get(phase_name, "orchestrator")`.
- `PipelineOrchestrator(config).run()` still works and produces the same result as before.
- Existing tests in `tests/regression/`, `tests/` that call `PipelineOrchestrator(config).run()` continue to pass.

**Verification:** All 8 phases registered and individually callable. `PipelineOrchestrator.run()` unbroken. Success criterion from R9.

---

### U8. RouterV6Pipeline Adapter (5 Stages)

**Goal:** Decompose `RouterV6Pipeline` into 5 individually callable `PipelineStage` instances and register them as a composite pipeline.

**Requirements:** R4, R9

**Dependencies:** U1, U2, U3, U6 (adapters package)

**Files:**
- New: `packages/temper-placer/src/temper_placer/adapters/router_v6_stage_adapter.py`

**Approach:**
- 5 adapter stage classes, one per Router V6 stage:

  1. **`RouterV6Stage0_LoadPCB`**
     - `name = "router_v6/load_pcb"`
     - `requires = []`, `provides = ["parsed_pcb"]`
     - `run(input)`: expects `input.data` to be a `Path` (pcb file path). Calls `parse_kicad_pcb_v6(path)`. Returns `StageOutput(data=parsed)`.

  2. **`RouterV6Stage1_EscapeVias`**
     - `name = "router_v6/escape_vias"`
     - `requires = ["parsed_pcb"]`, `provides = ["escape_vias"]`
     - `run(input)`: expects `input.data` to be `ParsedPCB`. Calls `identify_dense_packages(pcb.components)` and `generate_escape_vias(dense_pkg, pcb.design_rules, strategy="dog-bone")` with via-in-pad fallback. Returns `StageOutput(data=EscapeViasResult(escape_vias=..., dense_packages=...))`.

  3. **`RouterV6Stage2_ChannelAnalysis`**
     - `name = "router_v6/channel_analysis"`
     - `requires = ["parsed_pcb", "escape_vias"]`, `provides = ["stage2_output"]`
     - `run(input)`: expects `input.data` to carry `pcb` and `escape_vias`. Creates a temporary `RouterV6Pipeline` instance, calls `pipeline._run_stage2(pcb, escape_vias)`. Returns `StageOutput(data=stage2)`.

  4. **`RouterV6Stage3_TopologicalRouting`**
     - `name = "router_v6/topological_routing"`
     - `requires = ["parsed_pcb", "stage2_output"]`, `provides = ["stage3_output"]`
     - `run(input)`: expects `input.data` to carry `pcb` and `stage2`. Calls `pipeline._run_stage3(pcb, stage2)`. Returns `StageOutput(data=stage3)`.

  5. **`RouterV6Stage4_GeometricRealization`**
     - `name = "router_v6/geometric_realization"`
     - `requires = ["parsed_pcb", "stage2_output", "stage3_output", "escape_vias"]`, `provides = ["stage4_output", "routing_results"]`
     - `run(input)`: expects `input.data` to carry `pcb`, `stage2`, `stage3`, `escape_vias`. Calls `pipeline._run_stage4(pcb, stage2, stage3, escape_vias)`. Returns `StageOutput(data=stage4)`.

- At module import time:
  - Register all 5 stages under phase `"routing"` with name `"router_v6"`:
    ```python
    register("routing", "router_v6", lambda: RouterV6Stage0_LoadPCB())
    register("routing", "router_v6", lambda: RouterV6Stage1_EscapeVias())  # IDEMPOTENT — overrides previous. Fix: use distinct names.
    ```
    **Correction:** Each stage must have a distinct `(phase, name)` key. The 5 stages are:
    ```python
    register("routing", "router_v6_stage0", lambda: RouterV6Stage0_LoadPCB())
    register("routing", "router_v6_stage1", lambda: RouterV6Stage1_EscapeVias())
    register("routing", "router_v6_stage2", lambda: RouterV6Stage2_ChannelAnalysis())
    register("routing", "router_v6_stage3", lambda: RouterV6Stage3_TopologicalRouting())
    register("routing", "router_v6_stage4", lambda: RouterV6Stage4_GeometricRealization())
    ```
  - Register the composite:
    ```python
    register_composite("router_v6_full", [
        ("routing", "router_v6_stage0"),
        ("routing", "router_v6_stage1"),
        ("routing", "router_v6_stage2"),
        ("routing", "router_v6_stage3"),
        ("routing", "router_v6_stage4"),
    ])
    ```

- The adapter does **not** modify `RouterV6Pipeline` or `pipeline.py`.
- `RouterV6Pipeline(path).run()` continues to work unmodified.
- The existing `route_pcb()` function in `router_v6/adapter.py` is **not removed** — it continues to work for current consumers.

**Why stages 2-4 need a temporary `RouterV6Pipeline`:** The `_run_stage2/3/4` methods are instance methods that access `self.verbose`, `self.enable_theta_star`, etc. The adapter instantiates a pipeline with the desired flags (matching the closure test's current configuration: `verbose=False, enable_theta_star=True, enable_lazy_theta_star=True, enable_smoothing=True`) and calls the internal methods. Configuration flags are read from `StageMeta.trace_context` where needed.

**Patterns to follow:** `router_v6/adapter.py:31-95` — the existing `route_pcb()` adapter pattern. `RouterV6Pipeline.run()` at `router_v6/pipeline.py:143-239` — the stage sequence that the adapter decomposes.

**Test scenarios:**
- `RouterV6Stage0_LoadPCB().run(StageInput(data=path))` returns `StageOutput(data=ParsedPCB(...))`.
- All 5 stages registered and retrievable individually.
- `get_composite("router_v6_full")` returns 5 stages in order.
- Chaining a `PipelineRunner` with the composite produces a complete routing result equivalent to `RouterV6Pipeline(path).run()`.
- `RouterV6Pipeline(path).run()` still works unmodified.
- Existing tests in `tests/routing/` that use `RouterV6Pipeline` pass unchanged.

**Verification:** 5 stages registered. Composite pipeline runs end-to-end. `RouterV6Pipeline` unmodified. Success criterion from R9.

---

### U9. Closure Test Integration

**Goal:** Rewire `closure_test.py` to use `resolve_and_run` via `temper_placer.protocol` instead of direct imports from `benders_loop` and `router_v6.adapter`.

**Requirements:** R10

**Dependencies:** U5 (resolve_and_run), U7 (orchestrator adapter), U8 (router_v6 adapter), U6 (deterministic wrapper — for template placement registration)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/regression/closure_test.py`

**Approach:**
- Replace the Step 2 block (lines 84-114, Benders placement) with:
  ```python
  from temper_placer.protocol import StageInput, StageMeta
  from temper_placer.runner import resolve_and_run

  placement_result = resolve_and_run(
      phase="placement",
      strategies=[strategy_param],  # from ClosureTest config
      input=StageInput(data=parsed, meta=StageMeta(seed=self.benders_seed)),
      fallback="template",
  )
  benders_iterations = getattr(placement_result.data, "iterations", 0)
  benders_cuts = getattr(placement_result.data, "cuts", 0)
  optimized_placements = getattr(placement_result.data, "placements", {})
  ```
- Replace the Step 3 block (lines 117-127, Router V6 routing) with:
  ```python
  routing_result = resolve_and_run(
      phase="routing",
      strategies=["router_v6_full"],
      input=StageInput(
          data=parsed,
          meta=StageMeta(
              seed=self.router_seed,
              trace_context={"placements": optimized_placements},
          ),
      ),
  )
  router_completion_pct = getattr(routing_result.data, "completion_rate", 0.0)
  ```
- The closure test no longer imports from `temper_placer.placement.benders_loop` or `temper_placer.router_v6.adapter` directly. It imports only from `temper_placer.protocol` and `temper_placer.runner`.
- The `ClosureResult` format (`benders_iterations`, `router_completion_pct`) is preserved by mapping `StageOutput.data` fields.
- Add a `strategy` parameter to `ClosureTest.__init__` (default `"template"`) so the caller can select placement strategy without code changes.

**Backward compatibility note:** The closure test currently catches `ImportError` for missing backends (lines 101-102, 123-124). With the protocol, `resolve_and_run` raises `StrategyExhaustedError` when no backend is registered. The closure test should catch `StrategyExhaustedError` and emit a warning (preserving the current graceful-degradation behavior for missing backends).

**Patterns to follow:** Current `closure_test.py:86-127` — the try/except blocks that the new code replaces. `ClosureResult` dataclass at `closure_test.py:18-31`.

**Test scenarios:**
- `ClosureTest(pcb_path).run()` with default strategy produces same `ClosureResult` fields as before.
- `ClosureTest(pcb_path, strategy="template").run()` routes through the template placement adapter.
- `ClosureTest(pcb_path, strategy="nonexistent").run()` falls back to template (via `resolve_and_run` fallback).
- The closure test produces real placement and routing results without importing from `benders_loop` or `router_v6.adapter` directly (SC10).

**Verification:** Success criterion SC10. `closure_test.py` imports only from `temper_placer.protocol`. Output format preserved.

---

### U10. Backward Compatibility Gate

**Goal:** Verify that no existing code is broken and that all three pipelines remain first-class citizens.

**Requirements:** R9

**Dependencies:** All preceding units (U1–U9)

**Files:** None modified — this is a verification unit.

**Approach:**
- Run the full test suite before and after implementation:
  - `pytest packages/temper-placer/tests/deterministic/` — all 26 stages tested via `stage.run(state)`.
  - `pytest packages/temper-placer/tests/regression/` — closure test and regression tests.
  - `pytest packages/temper-placer/tests/` — all other tests.
  - Any tests that call `PipelineOrchestrator(config).run()`.
  - Any tests that call `RouterV6Pipeline(path).run()`.
- Verify import isolation:
  - `from temper_placer.protocol import PipelineStage` must not trigger `import jax`, `import temper_placer.router_v6`, `import temper_placer.deterministic`, or `import temper_placer.pipeline`.
  - Test: `python -c "from temper_placer.protocol import PipelineStage; print('OK')"` in a fresh interpreter.
- Verify existing scripts:
  - A spot-check of 5 representative scripts from `scripts/` confirms they import and run unchanged.
- Verify registration idempotency:
  - Import any adapter module twice — no exceptions, no duplicate entries.
- Verify `wrap_deterministic_stage()`:
  - Any `Stage` subclass wrapped with `wrap_deterministic_stage(stage)` satisfies `isinstance(wrapped, PipelineStage)` without modifying the original.

**Key invariants to preserve:**
1. `DeterministicPipeline(stages=[...]).run(state)` — unchanged.
2. `PipelineOrchestrator(config).run()` — unchanged.
3. `RouterV6Pipeline(path).run()` — unchanged.
4. `benders_placement(parsed, seed, strategy="template")` — unchanged (SC7).
5. `route_pcb(parsed, placements, seed)` — unchanged.
6. All tests in `tests/deterministic/`, `tests/regression/`, `tests/` — pass unchanged.
7. All 118 scripts in `scripts/` — no forced adoption.

**Verification:** Success criteria SC6, SC7. Zero test regressions. Import isolation confirmed.

---

### U11. Unit Tests for Protocol + Registry + Runner

**Goal:** Comprehensive tests for the new protocol layer, independent of any pipeline backend.

**Requirements:** All (R1–R10)

**Dependencies:** U1–U5

**Files:**
- New: `packages/temper-placer/tests/protocol/test_protocol.py`
- New: `packages/temper-placer/tests/protocol/test_strategy_registry.py`
- New: `packages/temper-placer/tests/protocol/test_runner.py`
- New: `packages/temper-placer/tests/protocol/__init__.py`

**Approach:**
- `test_protocol.py`:
  - Tests that `StageMeta`, `StageInput`, `StageOutput` construct with defaults and custom values.
  - Tests that a class structurally satisfying `PipelineStage` passes `isinstance` check.
  - Tests that `Contract` validates field presence and types correctly.
  - Tests that `ContractViolation` carries all required fields.
  - Tests that `from temper_placer.protocol import ...` does not import pipeline backends (check `sys.modules`).
- `test_strategy_registry.py`:
  - Tests `register`/`get` round-trip.
  - Tests idempotent double-register.
  - Tests `list()` with and without phase filter.
  - Tests `register_composite`/`get_composite` ordering.
  - Tests `get()` raises `KeyError` for unknown key.
- `test_runner.py`:
  - Tests `PipelineRunner` sequential execution.
  - Tests `trace()` returns correct timings.
  - Tests data-flow validation: missing `requires` key raises `DataFlowError`.
  - Tests data-flow validation: valid chain passes.
  - Tests `Contract` validation at input and output.
  - Tests `ContractViolation` raised with correct stage/schema/field info.
  - Tests `resolve_and_run` with single strategy (success).
  - Tests `resolve_and_run` with fallback chain.
  - Tests `resolve_and_run` exhausts all strategies (raises `StrategyExhaustedError`).
  - Tests `resolve_and_run` with empty strategies list (raises `StrategyExhaustedError` immediately).

**Test fixtures:** Use mock `PipelineStage` implementations that record calls and return controlled outputs. No real pipeline backend imports in test_protocol tests.

**Patterns to follow:** Existing test structure at `packages/temper-placer/tests/deterministic/` — `conftest.py` fixtures, `pytest` assertions, no test framework beyond `pytest`.

**Verification:** All new tests pass. Coverage on `protocol.py`, `strategy_registry.py`, `runner.py` ≥ 90% for core paths.

---

### U12. Adapter Integration Tests

**Goal:** Tests that adapters correctly translate between protocol types and internal pipeline types.

**Requirements:** R3, R4, R9

**Dependencies:** U6, U7, U8

**Files:**
- New: `packages/temper-placer/tests/protocol/test_deterministic_adapter.py`
- New: `packages/temper-placer/tests/protocol/test_orchestrator_adapter.py`
- New: `packages/temper-placer/tests/protocol/test_router_v6_adapter.py`

**Approach:**
- `test_deterministic_adapter.py`:
  - Wraps a real `Stage` subclass (e.g., `ClearanceGridStage`) and verifies `run(StageInput(data=BoardState(...)))` produces expected output.
  - Verifies `requires`/`provides` are correctly surfaced from adapter arguments.
  - Verifies the original stage instance is unmodified after wrapping.
- `test_orchestrator_adapter.py`:
  - Creates a minimal `PipelineConfig` with a real PCB path.
  - Tests that `OrchestratorInputStage().run(StageInput(data=config))` calls `_run_input` and populates `board`/`netlist`.
  - Tests that chaining Input → Semantic → Topological via `PipelineRunner` produces a `PipelineState` with `deterministic_result` populated.
  - Verifies the original `PipelineOrchestrator` class is unmodified.
  - **Requires:** A small test PCB fixture (`.kicad_pcb` file) in the test fixtures directory.
- `test_router_v6_adapter.py`:
  - Uses a test PCB fixture.
  - Tests `RouterV6Stage0_LoadPCB().run(StageInput(data=pcb_path))` returns a `ParsedPCB`.
  - Tests all 5 stages can be composed via `PipelineRunner` and produce a `Stage4Output`.
  - Verifies `get_composite("router_v6_full")` returns 5 stages.
  - Verifies the original `RouterV6Pipeline` class is unmodified.
  - **Requires:** A small test PCB fixture (`.kicad_pcb` file).

**Test fixtures:** Reuse existing test PCBs from `packages/temper-placer/tests/fixtures/` or `power_pcb_dataset/`. A minimal 2-component PCB may be created if no suitable fixture exists.

**Verification:** All adapter tests pass. Original pipeline classes unmodified (verified via `git diff`).

---

## Scope Boundaries

### In scope
- `StageMeta`, `StageInput`, `StageOutput` dataclasses (U1)
- `PipelineStage` Protocol with `name`, `run`, `requires`, `provides`, optional `contract` (U2)
- `Contract` dataclass and `ContractViolation` exception (U2)
- `DataFlowError` for requires/provides validation (U4)
- Strategy registry with `register`, `get`, `list`, `register_composite`, `get_composite` (U3)
- `PipelineRunner` with sequential execution, contract validation, timing collection, `trace()` (U4)
- `resolve_and_run()` with `StrategyExhaustedError` and fallback chain (U5)
- `wrap_deterministic_stage()` adapter function for 26 deterministic stages (U6)
- `PipelineOrchestrator` adapter — 8 individually callable `PipelineStage` instances (U7)
- `RouterV6Pipeline` adapter — 5 individually callable `PipelineStage` instances + composite (U8)
- Closure test integration via `resolve_and_run` (U9)
- Protocol registry + runner unit tests (U11)
- Adapter integration tests (U12)
- Backward compatibility verification (U10)

### Deferred for later
- `PhaseOrder` topo-sort for ad-hoc stage ordering — v1 uses explicit ordered lists and composites
- Compile-time phantom types for stage ordering — v1 uses runtime `requires`/`provides` checks
- Content-level validation (semantic checks beyond field presence and type) — v1 validates only field existence and `isinstance`
- Unified pipeline configuration object — v1 passes configuration through `StageMeta` and individual adapters
- Migration of the 26 `DeterministicPipeline` stages to use `PipelineStage` Protocol internally — they are wrapped, not rewritten
- Type-checker enforcement (mypy, pyright) of the Protocol — CI does not gate on type coverage of Protocol consumers yet

### Out of scope
- Replacing any existing pipeline system — all three pipelines continue as first-class citizens
- Changing the closure test's pass/fail criteria
- Performance optimization of the protocol layer — adapter overhead is negligible relative to stage execution times (seconds to minutes)
- Removing `benders_placement()` or `route_pcb()` — both functions continue to work for current consumers
- Migrating the 118 scripts in `scripts/` to use the protocol

## Implementation Order

Units must be implemented in dependency order:

```
U1 (dataclasses) ──┐
                    ├── U4 (runner) ── U5 (resolve_and_run) ── U9 (closure test)
U2 (protocol)    ──┤                     │
                    ├── U3 (registry) ────┘
                    │
U6 (det. adapter) ──┤
U7 (orch. adapter) ─┤── U12 (adapter tests)
U8 (router adapter) ─┘

U10 (compat gate) — after all units
U11 (unit tests) — after U1–U5
```

Parallelizable groups:
- **Wave 1:** U1 + U2 (same file, `protocol.py`)
- **Wave 2:** U3, U4, U6 (independent of each other; U3 depends on U2; U4 depends on U1–U2; U6 depends on U1–U2)
- **Wave 3:** U5 (depends on U3 + U4), U7, U8 (depend on U1–U3)
- **Wave 4:** U9 (depends on U5 + U7 + U8), U11 (depends on U1–U5), U12 (depends on U6–U8)
- **Wave 5:** U10 (final verification gate, depends on all)

## Success Criteria

| ID | Criterion | Verified by |
|---|---|---|
| SC1 | `from temper_placer.protocol import PipelineStage, StageInput, StageOutput, PipelineRunner` imports without pulling in any pipeline backend | U11 test: check `sys.modules` |
| SC2 | `PipelineRunner([stage1, stage2]).run(StageInput(data=...))` executes stages sequentially and returns `StageOutput` with timings | U11 test: `test_runner.py` |
| SC3 | `resolve_and_run("placement", ["template"], input, fallback="template")` dispatches via registry | U11 test: `test_runner.py` |
| SC4 | `resolve_and_run("placement", ["nonexistent"], input, fallback="template")` fails through to fallback | U11 test |
| SC5 | `resolve_and_run("placement", ["nonexistent"], input)` raises `StrategyExhaustedError` | U11 test |
| SC6 | Any of 26 deterministic `Stage` subclasses can be wrapped via `wrap_deterministic_stage(stage)` | U12 test: `test_deterministic_adapter.py` |
| SC7 | `benders_placement(parsed, seed, strategy="template")` continues to work unmodified | U10: existing tests unchanged |
| SC8 | Contract violation raises `ContractViolation` at boundary before next stage runs | U11 test: `test_runner.py` |
| SC9 | `PipelineRunner.trace()` returns accurate per-stage execution times | U11 test |
| SC10 | Closure test produces real results via `resolve_and_run` without importing from `benders_loop` or `router_v6.adapter` directly | U9 test: `closure_test.py` output preserved |

## Dependencies

- `temper_placer.deterministic.stages.base.Stage` — existing ABC (wrapped, not modified)
- `temper_placer.deterministic.state.BoardState` — existing data class (used by deterministic adapter)
- `temper_placer.deterministic.stages` — 26 Stage subclasses (wrapped, not modified)
- `temper_placer.pipeline.orchestrator.PipelineOrchestrator` + `PipelineState` + `PipelineConfig` — existing implementation (wrapped, not modified)
- `temper_placer.router_v6.pipeline.RouterV6Pipeline` — existing implementation (wrapped, not modified)
- `temper_placer.router_v6.adapter.route_pcb` — existing adapter (preserved, not removed)
- `temper_placer.placement.benders_loop.benders_placement` — existing strategy function (preserved, not removed)
- `temper_placer.regression.closure_test.ClosureTest` — consumer of the protocol (U9)

## Assumptions

1. The `PipelineOrchestrator`'s phase handlers can be called independently on a fresh orchestrator instance (they reference `self.state`, so the adapter creates a fresh orchestrator and injects data — confirmed safe because each handler is a pure function of `self.state`).
2. `RouterV6Pipeline`'s internal `_run_stage2`, `_run_stage3`, `_run_stage4` methods are callable with the correct typed inputs — the adapter constructs these from protocol-level data (confirmed from `pipeline.py:241-328`).
3. The closure test's expected output format (`benders_iterations`, `router_completion_pct`) is fixed and authoritative — the adapter maps `StageOutput.data` fields to these expected keys (confirmed from `closure_test.py:18-31`).
4. Strategy registration at module import time is acceptable — no conflicts arise from import ordering (verified by U10 import-isolation test).
5. The protocol layer overhead (dataclass construction, field validation) is negligible relative to stage execution times (seconds to minutes).
6. A test PCB fixture is available or can be minimal — if not, a 2-component fixture is created as part of U12.
