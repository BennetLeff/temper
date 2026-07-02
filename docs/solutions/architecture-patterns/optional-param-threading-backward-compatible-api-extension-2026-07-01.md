---
title: "Optional Parameter Threading Pattern for Backward-Compatible Pipeline API Extension"
date: "2026-07-01"
category: architecture-patterns
module: temper-placer
problem_type: architecture_pattern
component: development_workflow
severity: medium
applies_when:
  - "Extending a pipeline call chain with a new capability that not all consumers need"
  - "Adding an optional input (e.g., constraints, config, metadata) through N layers of functions"
  - "Preserving backward compatibility — existing call sites must continue to work with no changes"
  - "Using `from __future__ import annotations` with PEP 604 `X | None` union syntax"
tags:
  - api-design
  - backward-compatibility
  - keyword-arguments
  - induction-proof
  - pipeline-pattern
  - type-hints
  - python-310
---

# Optional Parameter Threading Pattern for Backward-Compatible Pipeline API Extension

## Context

The temper-placer placement optimizer has a 4-layer call chain:

```
CLI / corpus_runner / ablation_runner
  → train() / train_multiphase()
    → initialize_training_state()
      → SpectralInitializer.initialize()  (or ZoneAware / Learned variant)
```

A new `PlacementConstraints` type was introduced to encode zone assignments, component groups, fixed positions, and manufacturing rules. These constraints need to influence initialization (constraint-weighted Laplacian, C-CAP projection) and loss computation (thermal constraints, zone awareness). However, adding a required parameter at any layer would break every call site, test, and integration path.

The pattern: thread a single `constraints: PlacementConstraints | None = None` keyword argument through the entire chain, allowing downstream consumers that need it to read it and those that don't to silently ignore it.

## Guidance

### Core Mechanism

Add an optional keyword-only-or-positional parameter with a `None` default to **every function in the call chain**, from the top-level entry points down to every leaf initializer. Thread it forward via explicit `constraints=constraints` keyword arguments. Functions that don't consume it simply accept it in their signature and pass it along.

```python
from __future__ import annotations

def train(
    netlist: Netlist,
    board: Board,
    composite_loss: CompositeLoss,
    context: LossContext,
    config: OptimizerConfig | None = None,
    initial_state: PlacementState | None = None,
    callback: Callable[[TrainingMetrics], None] | None = None,
    validation_callback: ValidationCallback | None = None,
    profile_dir: str | None = None,
    constraints: PlacementConstraints | None = None,  # <-- added
) -> TrainingResult:
    ...
    state = initialize_training_state(
        netlist, board, config, initial_state, constraints=constraints  # <-- forwarded
    )
```

### Full Chain Layout

Every layer in `train.py` gained the parameter:

| Function | File:Line | Role |
|---|---|---|
| `train()` | `train.py:762` | Entry point — accepts, forwards to `initialize_training_state` |
| `train_multiphase()` | `train.py:1291` | Multi-phase variant — same pattern |
| `train_parallel()` | `train.py:1212` | Multi-seed wrapper — forwards to `train()` |
| `initialize_training_state()` | `train.py:292` | Dispatcher — passes `constraints=constraints` to each initializer |

Every initializer's `initialize()` accepts it:

| Initializer | File:Line | Behavior |
|---|---|---|
| `SpectralInitializer` | `initialization.py:240` | Accepts, ignores (unused parameter) |
| `ZoneAwareSpectralInitializer` | `zone_aware_init.py:231` | Accepts, ignores — calls `super().initialize(netlist, board, rng_key)` without forwarding |
| `LearnedInitializer` | `initialization.py:611` | Accepts, ignores — annotated with `# @req(2026-07-01-003, SC6): passthrough` |

Three call sites introduce the parameter at the top:

| Call site | File:Line | How it's introduced |
|---|---|---|
| CLI `run_placement` | `cli/__init__.py:419` | `pipeline.run(board, netlist, constraints=constraints, ...)` |
| `corpus_runner` | `regression/corpus_runner.py:441` | `train_multiphase(..., constraints=constraints)` |
| `ablation_runner` | `ablation/runner.py:531,586` | `pipeline.run(...)` and `LossContext.from_netlist_and_board(..., constraints=constraints)` |

### `from __future__ import annotations` + PEP 604 Union Syntax

The `X | None` syntax requires PEP 604 (Python 3.10+). With `from __future__ import annotations`, type annotations are strings at runtime, so `PlacementConstraints | None` is legal even if `PlacementConstraints` isn't yet defined at the point of the annotation. This avoids forward-reference boilerplate (`"PlacementConstraints" | None` as a string literal) while keeping the code readable:

```python
from __future__ import annotations
...
from temper_placer.io.config_loader import PlacementConstraints

def train(
    ...
    constraints: PlacementConstraints | None = None,
) -> TrainingResult:
```

Without `from __future__ import annotations`, the `|` operator would be evaluated at class/function definition time, requiring the type to be imported at module level. The future import defers evaluation, making the annotation a string literal that type checkers still understand.

### Induction Proof of Correctness

The pattern is provably backward-compatible by induction on the call chain:

**Base case (leaf initializers):** `SpectralInitializer.initialize()`, `ZoneAwareSpectralInitializer.initialize()`, and `LearnedInitializer.initialize()` all accept `constraints: Any | None = None` and ignore it. Their logic is unconditionally unchanged — the parameter is accepted in the signature and never read or branched on. Output is identical to calling without the parameter.

**Inductive step:** Every intermediate function (`initialize_training_state`, `train`, `train_multiphase`, `train_parallel`) does only two things with the parameter:
1. Accepts it with `= None` default (preserving the existing positional call signature for all other parameters)
2. Forwards it via `constraints=constraints` to exactly one callee

No intermediate function introduces a code branch on `constraints is not None`. There is no `if constraints:` guard that changes behavior — only forwarding. Thus, the behavior of each function is identical whether `constraints` is `None` or a populated `PlacementConstraints` (at these layers — the branching happens in consumers like `constraint_weighted_spectral` and `C-CAP`, which are the intended consumers).

**Conclusion:** For any existing call site that omits `constraints`, the `None` default propagates through the entire chain unchanged, every leaf initializer ignores it, and the output is bitwise-identical to the pre-pattern version.

### Validation Strategy

The test suite at `tests/optimizer/test_constraint_passthrough_init.py` verifies the induction invariant directly:

```python
def test_initialize_training_state_spectral_invariant(self):
    state_none = initialize_training_state(netlist, board, config, constraints=None)
    state_populated = initialize_training_state(
        netlist, board, config, constraints=_empty_constraints()
    )
    assert jnp.allclose(state_none.positions, state_populated.positions)
```

Three classes of tests cover:
1. **Property-based invariant:** `None` vs. populated `PlacementConstraints` produce identical output for spectral, zone_aware_spectral, and random init
2. **Per-initializer acceptance:** Every initializer's `initialize()` accepts the parameter without raising
3. **Integration:** `train()` and `train_multiphase()` accept the kwarg and produce identical output with `None` vs. populated constraints

### When the Parameter Is Actually Consumed

The `None` default threads silently until a consumer that needs it reads it. In this implementation, two consumers branch on `constraints is not None`:

1. **`constraint_weighted_spectral`** (initialization path, `train.py:322-358`): If constraints are available, computes a constraint-weighted Laplacian; otherwise falls back to standard spectral
2. **C-CAP projection** (initialization path, `train.py:406-428`): If constraints are available AND `ccap_enabled`, projects initial positions to satisfy separation constraints

These consumers are in `initialize_training_state()` — the first function in the chain that has a reason to read the parameter. All higher layers are pure conduits.

## Why This Matters

**Each parameter addition at a middle layer creates O(N) call-site changes where N is the number of callers.** Without the threading pattern, adding `constraints` to `initialize_training_state()` would require updating `train()`, `train_multiphase()`, `train_parallel()`, and every test and script that calls them. With the pattern, existing callers continue to work because the default `None` preserves the old signature.

**Keyword arguments are self-documenting at call sites.** `constraints=constraints` makes the threading explicit and grep-able. A positional-only approach (`None` as a positional arg) would require callers to know the parameter order and would silently break if parameters are reordered.

**The induction proof is the design contract.** Anyone adding a new parameter can verify correctness by checking: (1) does every leaf initializer accept it?, (2) does every intermediate function forward it unchanged?, (3) are there zero new code branches introduced by the parameter's presence at intermediate layers? If all three hold, the change is backward-compatible.

## When to Apply

- When you need to thread new data through 3+ layers of a call chain
- When some consumers need the data and others don't
- When backward compatibility matters (existing call sites, CLI scripts, notebooks)
- When the new parameter is optional — the system should work correctly without it
- When the parameter has a natural `None` sentinel (i.e., "not provided" is meaningful)

Do NOT apply when:
- The new parameter is required for correctness at every layer (use a non-optional parameter and update all call sites)
- The parameter would require every intermediate function to restructure its logic (the threading pattern is for pass-through, not new branching)
- There is only one or two callers (just update them directly — the pattern's value grows with call chain depth)

## Examples

### Minimal Example: 3-Layer Chain

```python
from __future__ import annotations

def outer(*, constraints: MyConstraints | None = None) -> Result:
    return middle(constraints=constraints)

def middle(*, constraints: MyConstraints | None = None) -> Result:
    return inner(constraints=constraints)

def inner(*, constraints: MyConstraints | None = None) -> Result:
    # Leaf — ignores the parameter
    return compute()

# All of these work identically:
outer()                        # constraints=None threaded through
outer(constraints=None)        # explicit None
outer(constraints=some_con)    # threading still works; inner ignores it
```

### Actual Pattern: `train()` to Leaf Initializer

```python
# train.py — top-level entry point
def train(
    ...
    constraints: PlacementConstraints | None = None,
) -> TrainingResult:
    state = initialize_training_state(
        netlist, board, config, initial_state, constraints=constraints
    )
    ...

# train.py — dispatcher
def initialize_training_state(
    netlist: Netlist,
    board: Board,
    config: OptimizerConfig,
    initial_state: PlacementState | None = None,
    constraints: PlacementConstraints | None = None,
) -> TrainingState:
    ...
    if config.initialization.method == "spectral":
        positions = initializer.initialize(
            netlist, board, constraints=constraints
        )
    elif config.initialization.method == "zone_aware_spectral":
        positions = initializer.initialize(
            netlist, board, constraints=constraints
        )
    ...

# initialization.py — leaf initializer
class SpectralInitializer:
    def initialize(
        self,
        netlist: Netlist,
        board: Board,
        _rng_key: Array | None = None,
        constraints: Any | None = None,  # accepted, ignored
    ) -> Array:
        ...  # unconditionally unchanged logic
```

### Anti-Pattern: Branching at an Intermediate Layer

```python
# WRONG: introduces behavior change at an intermediate layer
def middle(*, constraints: Constraints | None = None):
    if constraints is not None:
        result = consumer_a(constraints=constraints)
    else:
        result = consumer_b()
    return result
    # This breaks induction — the function's output DIFFERS based on constraints
    # presence. The threading pattern is for pure forwarding at intermediate layers.
```

## Related

- `packages/temper-placer/src/temper_placer/optimizer/train.py` — full implementation of the chained `constraints` parameter
- `packages/temper-placer/src/temper_placer/optimizer/initialization.py` — leaf initializer signatures (lines 240, 611, 698)
- `packages/temper-placer/src/temper_placer/optimizer/zone_aware_init.py` — `ZoneAwareSpectralInitializer.initialize()` (line 231)
- `packages/temper-placer/tests/optimizer/test_constraint_passthrough_init.py` — property-based invariant tests
- `docs/solutions/architecture-patterns/pcl-constraint-system-triple-extension-2026-07-01.md` — the constraint system this pattern supports
