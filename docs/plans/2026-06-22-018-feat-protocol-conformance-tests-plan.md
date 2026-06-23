---
date: 2026-06-22
type: feat
origin: docs/ideation/2026-06-22-test-and-build-next-ideation.md
status: active
---

# Plan: Protocol Conformance Test Suite — Stage Contract Validation

## Summary

Create `tests/protocol/` with four test modules covering the unified stage
protocol, strategy registry, runner, and adapter boundaries. Every test uses
Hypothesis PBT where applicable so that each of the 8 incoming micro-stages
(and all future `Stage` subclasses) gets zero-cost conformance checking.

## Problem Frame

`tests/protocol/` does not exist. `protocol.py`, `runner.py`, and
`strategy_registry.py` have zero tests. Eight new Stage 2 micro-stages are
about to land (plan 012). `Stage(ABC)` at `deterministic/stages/base.py`
has no automated conformance verification — nothing checks that a new
subclass satisfies immutability, determinism, or field provenance.

The unified protocol (plan 010) already defines `PipelineStage`,
`StageInput`, `StageOutput`, `Contract`, and `PipelineRunner`. The
strategy registry already has `register` / `get` / `register_composite` /
`get_composite`. The deterministic adapter already wraps `Stage` → `PipelineStage`.
All three pipeline adapters exist. What's missing: a test suite that makes
these contracts enforceable at test time.

## Requirements Trace

| Requirement | Source | Acceptance |
|---|---|---|
| R1 — `test_stage_conformance.py` | Ideation #3 | Generate random `BoardState` via Hypothesis; assert input immutability, output determinism, field provenance (stage only writes declared output fields), serialization round-trip with `dataclasses.replace` |
| R2 — `test_strategy_registry.py` | Ideation #3 | Test `register` idempotency, `get` instantiation, `list_stages` phase filtering, `register_composite` ordering, `get_composite` resolution, composite DAG validation, `KeyError` on unknown keys |
| R3 — `test_runner.py` | Ideation #3 | Test `requires`/`provides` DAG validation at construction, `Contract` enforcement at runtime, skip conditions (empty stage list), `trace()` output, `resolve_and_run` with fallback exhaustion |
| R4 — `test_adapters.py` | Ideation #3 | Test `wrap_deterministic_stage` wrapping without modifying internals, orchestrator adapter per-phase isolation, router_v6 adapter stage independence, composite pipeline correctness |
| R5 — Hypothesis PBT coverage | Ideation #3 | At least 100 examples per PBT test. `assume()` guards for invalid states. `settings(deadline=2000)` budget per test. |

## Key Technical Decisions

**K1. PBT over exhaustive enumeration.** Every deterministic stage subclass
(26 existing + 8 incoming) is tested via Hypothesis strategies that generate
valid `BoardState` instances. Writing per-stage unit tests for 34+ stages
would be ~10× the effort of one parameterized conformance suite that
auto-discovers subclasses.

**K2. Field provenance via diff, not static analysis.** Rather than
introspecting AST to determine declared output fields, the conformance test
compares `dataclasses.fields()` before/after `run()`. A stage that writes to
an undeclared field triggers a violation. This is simpler than a static
check and catches runtime mutations.

**K3. Registry tests drive real module-level state.** The strategy registry
is a module-global `dict`. Tests use `monkeypatch` or import-time isolation
(via `importlib.reload`) to reset state between test cases. Composite tests
chain real registered stages to verify end-to-end resolution.

**K4. Adapter tests wrap without mocking internals.** Each adapter test
instantiates a real `Stage` subclass (or a lightweight test double), passes
it through the adapter, and verifies the wrapped stage satisfies
`PipelineStage` structural subtyping via `isinstance(obj, PipelineStage)`.

**K5. Runner tests use lightweight mock stages.** Rather than pulling in a
real pipeline, `test_runner.py` defines minimal `PipelineStage`-satisfying
objects with controlled `requires`/`provides`/`contract` attributes. This
keeps runner tests fast and isolated from backend coupling.

## Directory Layout

```
packages/temper-placer/tests/
├── protocol/                            # NEW directory
│   ├── __init__.py                      # NEW (empty)
│   ├── test_stage_conformance.py        # NEW — PBT for all Stage subclasses
│   ├── test_strategy_registry.py        # NEW — register/get/composite
│   ├── test_runner.py                   # NEW — DAG validation, contract, resolve_and_run
│   └── test_adapters.py                 # NEW — deterministic, orchestrator, router_v6
```

## Implementation Units

---

### U1 — `test_stage_conformance.py`

**What:** Hypothesis PBT suite that auto-discovers all `Stage` subclasses
and verifies conformance to the deterministic stage contract.

**Approach:**
1. `conftest.py` or a helper function auto-discovers all concrete `Stage`
   subclasses via `__subclasses__()` on `deterministic.stages.base.Stage`.
2. `hypothesis` strategy generates valid `BoardState` instances:
   - Vary `board`, `netlist`, `placements`, `routes`, `vias`, `net_order`,
     `layer_assignments`, `grid`, `drc_violations`, `locked_routes`.
   - `assume()` guards: `board` requires `width > 0` and `height > 0`.
     `netlist` requires consistency with `placements` and `routes`.
   - `st.from_type(BoardState)` with custom `@st.composite` builders.
3. **Immutability test:** For each stage, deep-copy the input `BoardState`
   (via `dataclasses.astuple` + reconstruct), call `stage.run(state)`, assert
   the original input `state` is unchanged (`==` equality of all fields).
4. **Determinism test:** For each stage, call `run()` twice with the same
   input; assert `output_1 == output_2` (field-wise equality, with `np.allclose`
   for numpy arrays).
5. **Field provenance test:** For each stage, capture declared output fields
   (auto-discovered from the stage's `__doc__` or by comparing input vs.
   output `dataclasses.fields` and flagging any field that changed without
   being in the stage's declared output set). Non-declared fields must be
   identical between input and output `BoardState`.
6. **Serialization round-trip test:** For the output `BoardState`, simulate
   `dataclasses.replace(state, **{f: getattr(state, f.name) for f in fields(state)})`
   and assert equality.

**Validation:** Mark as `@pytest.mark.slow` for large Hypothesis runs.
Use `@settings(max_examples=100, deadline=2000)`.

---

### U2 — `test_strategy_registry.py`

**What:** Unit tests for the module-level strategy registry (no Hypothesis
needed — these are deterministic API tests).

**Test cases:**

| Test | Method | Expected |
|---|---|---|
| `test_register_and_get` | `register("p", "n", factory)`; `get("p", "n")` | Returns instance from factory |
| `test_register_idempotent` | `register("p", "n", f1)`; `register("p", "n", f2)`; `get("p", "n")` | Returns instance from `f1` (first registration wins) |
| `test_get_unknown_key` | `get("nonexistent", "n")` | Raises `KeyError` |
| `test_list_stages_unfiltered` | `register("p1", "n1", ...)`; `register("p2", "n2", ...)`; `list_stages()` | Returns `{"p1/n1": ..., "p2/n2": ...}` |
| `test_list_stages_filtered` | `list_stages(phase="p1")` | Returns only `{"p1/n1": ...}` |
| `test_register_composite` | `register_composite("c", [("p1","n1"), ("p2","n2")])`; `get_composite("c")` | Returns list of 2 stage instances |
| `test_composite_ordering` | Composite with 3 stages | Returned list preserves declaration order |
| `test_composite_unknown` | `get_composite("nonexistent")` | Raises `KeyError` |
| `test_composite_idempotent` | `register_composite("c", [...a...])`; `register_composite("c", [...b...])` | Second registration is no-op, returns `[...a...]` |
| `test_registry_isolation` | Fixture that resets registry to empty dict via `importlib.reload` | Tests don't leak state |

**Dependencies:** `pytest`, `importlib.reload`, mock `PipelineStage` factories.

---

### U3 — `test_runner.py`

**What:** Tests for `PipelineRunner`, `_validate_data_flow`, and
`resolve_and_run` with contract validation.

**Approach:** Define minimal test-double stages:

```python
class _MockStage:
    name: str
    requires: list[str] = []
    provides: list[str] = []
    contract: Contract | None = None
    _return: Any = None

    def run(self, input: StageInput) -> StageOutput:
        return StageOutput(data=self._return, meta=input.meta)
```

**Test cases — DataFlow DAG:**

| Test | Stages config | Expected |
|---|---|---|
| `test_empty_pipeline` | `PipelineRunner([]).run(initial)` | Returns `initial` unchanged |
| `test_valid_chain` | A provides `["x"]`, B requires `["x"]` | Runs successfully |
| `test_missing_require` | A provides `[]`, B requires `["x"]` | Raises `DataFlowError` at construction |
| `test_self_provides` | A provides `["x"]`, A requires `["x"]` | Raises `DataFlowError` (stage can't use its own output) |

**Test cases — Contract enforcement:**

| Test | Stage contract | Input data | Expected |
|---|---|---|---|
| `test_input_contract_passes` | `input_schema={"field": int}` | `_MockObj(field=5)` | Runs successfully |
| `test_input_contract_fails_missing` | `input_schema={"field": int}` | `object()` (no field) | Raises `ContractViolation` |
| `test_input_contract_fails_type` | `input_schema={"field": int}` | `_MockObj(field="str")` | Raises `ContractViolation` |
| `test_output_contract_passes` | `output_schema={"field": int}` | Stage returns `_MockObj(field=5)` | Runs successfully |
| `test_output_contract_fails` | `output_schema={"field": int}` | Stage returns `object()` | Raises `ContractViolation` |

**Test cases — `resolve_and_run`:**

| Test | Strategies | Fallback | Expected |
|---|---|---|---|
| `test_first_strategy_succeeds` | `["s1", "s2"]` | None | Returns `s1` result; `s2` never called |
| `test_second_strategy_succeeds` | `["failing", "s2"]` | None | Returns `s2` result |
| `test_fallback_used` | `["failing"]` | `"fb"` | Returns `"fb"` result |
| `test_all_exhausted` | `["failing1", "failing2"]` | None | Raises `StrategyExhaustedError` |
| `test_skip_on_strategy_not_found` | `["unknown"]` | None | Raises `StrategyExhaustedError` after single `KeyError` |

**Test cases — `trace()`:**

| Test | Condition | Expected |
|---|---|---|
| `test_trace_before_run` | `runner.trace()` without `run()` | Raises `RuntimeError` |
| `test_trace_after_run` | 2 stages run | Returns `[(name1, dt1, None), (name2, dt2, None)]` |
| `test_trace_includes_contract` | Stage with contract | `contract_satisfied` is `True` |

---

### U4 — `test_adapters.py`

**What:** Test each adapter wraps without modifying internals, and wrapped
stages satisfy the `PipelineStage` Protocol.

**Approach:** Use lightweight test doubles for each adapter target. Isolate
by testing each adapter individually (no cross-adapter integration needed).

**Deterministic adapter tests:**

| Test | What | Expected |
|---|---|---|
| `test_wrap_satisfies_protocol` | `isinstance(wrap_deterministic_stage(stage), PipelineStage)` | `True` |
| `test_wrapped_preserves_name` | `wrapped.name` | Equals `stage.name` |
| `test_wrapped_delegates_run` | `stage.run()` returns specific `BoardState` | Wrapped output `data` matches |
| `test_wrapped_preserves_meta` | Input has custom `StageMeta(seed=99)` | Output `meta.seed == 99` |
| `test_requires_provides_passthrough` | `wrap_deterministic_stage(s, requires=["x"], provides=["y"])` | Wrapped has `requires=["x"]`, `provides=["y"]` |
| `test_internals_unmodified` | After wrapping, call `stage.run()` directly | Original still works, same behavior |

**Orchestrator adapter tests:**

| Test | What | Expected |
|---|---|---|
| `test_each_phase_has_name` | All 8 phase stage classes | `name` starts with `"orchestrator/"` |
| `test_each_phase_has_requires_provides` | All 8 | Non-None `requires` and `provides` lists |
| `test_phases_registered` | `strategy_registry.get("geometric", "orchestrator")` | Returns `PipelineStage` instance |
| `test_phase_isolation` | Run one phase, check it doesn't leak into another | Each phase creates its own `PipelineOrchestrator` |

**RouterV6 adapter tests:**

| Test | What | Expected |
|---|---|---|
| `test_five_stages_registered` | `strategy_registry.list_stages("routing")` | Contains 5 entries matching `router_v6_*` |
| `test_composite_registered` | `strategy_registry.get_composite("router_v6_full")` | Returns list of 5 stages |
| `test_stage0_expects_path` | Run `RouterV6Stage0_LoadPCB` with non-path input | Raises `TypeError` |
| `test_composite_ordering` | Composite stages | Correct dependency order: 0→1→2→3→4 |
| `test_internals_unmodified` | `RouterV6Pipeline.run()` after adapter import | Original still works |

---

## Execution Order

1. **U2** `test_strategy_registry.py` — No dependencies; simplest.
2. **U3** `test_runner.py` — Depends on protocol.py only (already exists).
3. **U4** `test_adapters.py` — Depends on registry + protocol + adapters.
4. **U1** `test_stage_conformance.py` — Most complex; needs `State`
   strategy design. Can be partially parallel with U2/U3.

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| `BoardState` Hypothesis strategy too slow to generate | Start with `st.from_type(BoardState)` and prune; add `@st.composite` builder with 10ms budget |
| Numba JIT overhead falsifies determinism tests | `assume()` that stage uses JIT; `@settings(deadline=5000)` for JIT stages |
| Registry module-level state leaks between tests | `importlib.reload(temper_placer.strategy_registry)` in fixture teardown |
| Adapter tests import real heavy backends | Use `mock.patch` or test doubles where heavy imports would slow CI |

## Validation

```bash
cd packages/temper-placer
python -m pytest tests/protocol/ -v --tb=short
```
