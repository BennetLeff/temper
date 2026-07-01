---
title: "feat: Constraint-Passthrough Init Pipeline"
plan_id: "2026-07-01-001-feat-constraint-passthrough-init"
type: feat
status: planned
date: 2026-07-01
origin: docs/brainstorms/2026-07-01-constraint-passthrough-init-requirements.md
related: docs/ideation/2026-07-01-placement-init-ideation.md (idea #1)
---

# feat: Constraint-Passthrough Init Pipeline

## Summary

Add an optional `constraints: PlacementConstraints | None = None` parameter to `initialize_training_state()`, `train()`, `train_multiphase()`, and every initializer's `initialize()` method, then thread the `PlacementConstraints` object through the three call chains that already have it in scope (CLI, corpus runner, ablation runner). This is a 3-line core change plus threading through 3 call sites — zero behavioral change, zero regression risk.

---

## Problem Frame

`PlacementConstraints` (`packages/temper-placer/src/temper_placer/io/config_loader.py:620`) codifies 30+ domain-rule categories (zones, component groups, HV/LV separation, thermal constraints, critical loops, star grounds, clearances, keepouts, noise isolation, matched-length groups, fixed positions). This object is parsed, validated, and available at every call site that invokes the optimizer.

Today, `initialize_training_state()` (`packages/temper-placer/src/temper_placer/optimizer/train.py:286`) receives `(netlist, board, config, initial_state)` — no `PlacementConstraints`. Every registered initializer (`SpectralInitializer`, `ZoneAwareSpectralInitializer`, `LearnedInitializer`) sees only `(netlist, board)` and is blind to codified rules.

**Concrete symptom:** the CLI (`packages/temper-placer/src/temper_placer/cli/__init__.py:335`) loads `constraints` at step 2, then calls `train_multiphase()` / `train()` at lines 844-865 without passing it through. The constraints are dropped on the floor. Identical gap exists in `corpus_runner.py:438` and `ablation/runner.py:614,627`.

**Impact:** zero of the 6 initializer-improvement ideas in the ideation doc can begin until constraints reach the init layer. Each must independently pipe constraints through — duplicating the same boilerplate 6 times — or wait for this prerequisite.

---

## Scope Boundaries

### In Scope

- Adding `constraints: PlacementConstraints | None = None` to:
  - `initialize_training_state()` in `optimizer/train.py:286`
  - `train()` in `optimizer/train.py:685`
  - `train_multiphase()` in `optimizer/train.py:1207`
- Threading `constraints` through the function body of `initialize_training_state()` to each initializer dispatch site (lines 318-351)
- Adding `constraints: PlacementConstraints | None = None` to `initialize()` on:
  - `SpectralInitializer` (`optimizer/initialization.py:227`)
  - `ZoneAwareSpectralInitializer` (`optimizer/zone_aware_init.py:226`)
  - `LearnedInitializer` (`optimizer/initialization.py:588`)
- Passing `constraints` from the three call sites that already have it in scope:
  - `cli/__init__.py:844-865`
  - `regression/corpus_runner.py:438`
  - `ablation/runner.py:614,627`
- Property-based test: invariant that `initialize_training_state()` outputs are element-wise identical with `constraints=None` vs. a populated `PlacementConstraints` (same RNG seed)
- Unit tests for each initializer accepting the new `constraints` parameter
- CI verification that existing test suite passes unmodified

### Out of Scope

- Implementing any constraint-aware initialization logic (weighted Laplacian, C-CAP projections, thermal anchoring, group pre-clustering, etc.)
- Changing the `OptimizerConfig` dataclass or `InitializationConfig` schema
- Adding new config keys or YAML schema changes
- Wiring constraints through `GeometricPhase` in `optimizer/phases.py` (the phase object does not own `PlacementConstraints`)
- Updating `io/__init__.py` exports
- Any loss function changes or gradient modifications

---

## Implementation Units

### IU-1: Core — Signature change on `initialize_training_state()`

**Goal:** Add `constraints: PlacementConstraints | None = None` to the function signature and thread it through to each initializer call site.

**File:** `packages/temper-placer/src/temper_placer/optimizer/train.py`

**Changes:**

1. **Import `PlacementConstraints`** (top of file, after existing `from temper_placer.optimizer.zone_aware_init import ...`):
   ```python
   from temper_placer.io.config_loader import PlacementConstraints
   ```

2. **Signature change** (line 286):
   ```python
   def initialize_training_state(
       netlist: Netlist,
       board: Board,
       config: OptimizerConfig,
       initial_state: PlacementState | None = None,
       constraints: PlacementConstraints | None = None,
   ) -> TrainingState:
   ```
   Update docstring to include the new parameter.

3. **Thread to `SpectralInitializer.initialize()` call** (line 323):
   ```python
   positions = initializer.initialize(netlist, board, constraints=constraints)
   ```

4. **Thread to `ZoneAwareSpectralInitializer.initialize()` call** (line 335):
   ```python
   positions = initializer.initialize(netlist, board, constraints=constraints)
   ```

5. **Thread to `LearnedInitializer.initialize()` call** (line 345):
   ```python
   positions = initializer.initialize(netlist, board, constraints=constraints)
   ```

**Lines touched:** ~10 (import + signature + docstring + 3 call sites)

**Design notes:**
- The random-init fallback block (lines 348-358) does not call any initializer's `.initialize()` — it directly constructs a `PlacementState` via `random_init`. No constraint threading needed there.
- Force-directed unfolding at line 377 does not need `constraints` (it operates on positions post-init).

**Verification:** Existing tests in `test_train_initialization.py` and `test_force_directed_init.py` call `initialize_training_state()` without the new parameter — they pass unchanged because the parameter defaults to `None`.

---

### IU-2: Signature change on `train()`

**Goal:** Add `constraints: PlacementConstraints | None = None` to `train()` and pass it through to `initialize_training_state()`.

**File:** `packages/temper-placer/src/temper_placer/optimizer/train.py`

**Changes:**

1. **Signature change** (line 685):
   ```python
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
       constraints: PlacementConstraints | None = None,
   ) -> TrainingResult:
   ```

2. **Pass through to `initialize_training_state()`** (line 738):
   ```python
   state = initialize_training_state(netlist, board, config, initial_state, constraints=constraints)
   ```

**Lines touched:** ~3 (signature + call site)

---

### IU-3: Signature change on `train_multiphase()`

**Goal:** Add `constraints: PlacementConstraints | None = None` to `train_multiphase()` and pass it through to `initialize_training_state()`.

**File:** `packages/temper-placer/src/temper_placer/optimizer/train.py`

**Changes:**

1. **Signature change** (line 1207):
   ```python
   def train_multiphase(
       netlist: Netlist,
       board: Board,
       loss_factory: Callable[[dict[str, float]], CompositeLoss],
       context: LossContext,
       config: OptimizerConfig | None = None,
       initial_state: PlacementState | None = None,
       callback: Callable[[TrainingMetrics], None] | None = None,
       validation_callback: ValidationCallback | None = None,
       profile_dir: str | None = None,
       drc_oracle: Any | None = None,
       constraints: PlacementConstraints | None = None,
   ) -> TrainingResult:
   ```

2. **Pass through to `initialize_training_state()`** (line 1259):
   ```python
   state = initialize_training_state(netlist, board, config, initial_state, constraints=constraints)
   ```

**Lines touched:** ~3 (signature + call site)

---

### IU-4: Add `constraints` parameter to initializer `initialize()` methods

**Goal:** Each init class's `initialize()` method accepts `constraints`, defaults to `None`, and ignores it (for now). This ensures the parameter is available when constraint-aware init logic is implemented later.

#### IU-4a: `SpectralInitializer` (`optimizer/initialization.py:227`)

**File:** `packages/temper-placer/src/temper_placer/optimizer/initialization.py`

Add import at top:
```python
from temper_placer.io.config_loader import PlacementConstraints
```

Change signature (line 227):
```python
def initialize(
    self,
    netlist: Netlist,
    board: Board,
    _rng_key: Array | None = None,
    constraints: PlacementConstraints | None = None,
) -> Array:
```

Update docstring to document the new ignored parameter. No logic changes.

**Note:** `ZoneAwareSpectralInitializer` (`optimizer/zone_aware_init.py:226`) inherits from `SpectralInitializer` and calls `super().initialize(netlist, board, rng_key, constraints=constraints)` — it will inherit the new signature via the parent class, but we **must** also update the override in `zone_aware_init.py` to accept and forward the parameter to avoid a `TypeError` on the `constraints=` kwarg:

**File:** `packages/temper-placer/src/temper_placer/optimizer/zone_aware_init.py`

Add import at top:
```python
from temper_placer.io.config_loader import PlacementConstraints
```

Change signature (line 226):
```python
def initialize(
    self,
    netlist: Netlist,
    board: Board,
    rng_key: Array | None = None,
    constraints: PlacementConstraints | None = None,
) -> Array:
```

Update the `super().initialize()` call (line 249):
```python
positions = super().initialize(netlist, board, rng_key, constraints=constraints)
```

#### IU-4b: `LearnedInitializer` (`optimizer/initialization.py:588`)

**File:** `packages/temper-placer/src/temper_placer/optimizer/initialization.py`

Change signature (line 588):
```python
def initialize(
    self,
    netlist: Netlist,
    board: Board,
    rng_key: Array | None = None,
    constraints: PlacementConstraints | None = None,
) -> Array:
```

Update docstring. No logic changes. The `fallback.initialize(netlist, board, rng_key)` call at line 608 should also forward `constraints`:
```python
return self.fallback.initialize(netlist, board, rng_key, constraints=constraints)
```

**Lines touched across IU-4a, IU-4b:** ~8 (2 imports + 3 signatures + 2 docstrings + 2 forward-thru sites, 1 super call update)

---

### IU-5: Thread `constraints` through call sites

**Goal:** The three call chains that already have `constraints` in scope pass it to `train()` / `train_multiphase()`.

#### IU-5a: CLI `optimize()` (`cli/__init__.py:844-865`)

**File:** `packages/temper-placer/src/temper_placer/cli/__init__.py`

**Context:** `constraints` is loaded at line 335 and remains in scope through the remainder of `optimize()`. Both `train_multiphase()` (line 844) and `train()` (line 856) calls need the kwarg:

```python
# Line 844 (curriculum path):
result = train_multiphase(
    netlist, board, make_loss, context, cfg,
    initial_state=initial_state,
    callback=progress_callback,
    profile_dir=profile_dir_str,
    constraints=constraints,
)

# Line 856 (single-phase path):
result = train(
    netlist, board, composite_loss, context, cfg,
    initial_state=initial_state,
    callback=progress_callback,
    profile_dir=profile_dir_str,
    constraints=constraints,
)
```

**Lines touched:** ~2

#### IU-5b: Corpus runner (`regression/corpus_runner.py:438`)

**File:** `packages/temper-placer/src/temper_placer/regression/corpus_runner.py`

**Context:** `constraints` is passed to the heuristic pipeline at line 388. The `train_multiphase()` call at line 438 needs the kwarg:

```python
result = train_multiphase(
    netlist, board, make_loss, context, cfg,
    initial_state=initial_state,
    constraints=constraints,
)
```

**Lines touched:** ~1

#### IU-5c: Ablation runner (`ablation/runner.py:612,627`)

**File:** `packages/temper-placer/src/temper_placer/ablation/runner.py`

**Context:** `constraints` is loaded at lines 516-521 and used throughout. Both the `train_multiphase()` call at line 614 and the `train()` call at line 627 need the kwarg:

```python
# Line 614 (curriculum path):
training_result = train_multiphase(
    netlist, board,
    loss_factory=lambda w: LossRegistry.create_composite_loss(experiment.losses, w),
    context=context,
    config=optimizer_config,
    initial_state=initial_state,
    constraints=constraints,
)

# Line 627 (single-phase path):
training_result = train(
    netlist, board,
    composite_loss=composite_loss,
    context=context,
    config=optimizer_config,
    initial_state=initial_state,
    constraints=constraints,
)
```

**Lines touched:** ~2

---

## Key Technical Decisions

### 1. `PlacementConstraints | None` over `Optional[PlacementConstraints]`

Follows the existing codebase convention — `train.py` already uses `X | None` throughout (e.g., `PlacementState | None`, `str | None`, `ValidationCallback | None`). This is Python 3.10+ union syntax, which the project's `from __future__ import annotations` makes available.

### 2. `from __future__ import annotations` — no deferred-eval risk

`train.py` already has `from __future__ import annotations` at line 19, making all annotations strings at runtime. This means `PlacementConstraints` does not need to be imported at runtime for type-checking — only for actual use. However, we add the import anyway for clarity and to surface import-cycle issues early (the requirements doc assesses cycle risk as low — `initialization.py` imports from `core/`, `config_loader.py` is in `io/`, no cycle).

### 3. `= None` default preserves backward compatibility

Every function that gains the parameter defaults it to `None`. All existing callers — including tests, scripts, and internal call chains — continue to work without modification. This is the same pattern as the `initial_state: PlacementState | None = None` parameter already on these functions.

### 4. `constraints` threading uses keyword arg consistently

At `initialize_training_state()` → initializer call sites, the parameter is passed as `constraints=constraints` (keyword, not positional). This avoids confusion with existing positional args (`netlist`, `board`, `rng_key`) and documents the intent at each pass-through point.

### 5. `ZoneAwareSpectralInitializer` override must be explicitly updated

`ZoneAwareSpectralInitializer.initialize()` overrides the parent method. Python resolves `super().initialize()` to the parent's signature at runtime, so calling `super().initialize(netlist, board, rng_key, constraints=constraints)` requires the parent to accept it. Both the override and the parent signature must be updated. If the override is not updated, `initialize_training_state()` would pass `constraints=` to `ZoneAwareSpectralInitializer.initialize()` and get a `TypeError`.

---

## Risks & Dependencies

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Type-checker / lint rejects the optional parameter pattern | Low | Codebase already uses `X \| None` extensively (e.g., `TrainStepState` fields, `LossContext` params); `pyright` / `ruff` have no issue with this |
| Unidentified call site lacks `constraints` | None | The parameter defaults to `None` — all unidentified sites silently pass through to zero-change behavior |
| `phases.py` needs threading but `GeometricPhase` lacks a constraints reference | Medium | Deferred to future work; `phases.py` callers already have constraints but don't inject them into the phase object; `GeometricPhase` does not call `initialize_training_state()` |
| Future initializers add required `constraints` but callers pass `None` | Medium | Add `assert constraints is not None` inside the constraint-aware initializer's `initialize()` as a self-documenting guard |
| Import cycle from `initialization.py` ↔ `config_loader.py` | Low | `initialization.py` imports from `core/`; `config_loader.py` is in `io/`; no cycle risk. Adding `from temper_placer.io.config_loader import PlacementConstraints` to `initialization.py` is a one-way import |
| CI / test suite failure from the new parameter | None | The parameter defaults to `None`; existing tests call functions without the new arg; they pass unchanged |

**Dependencies:** None. `PlacementConstraints` is already defined, parsed, validated, and available at all target call sites.

**Prerequisite for:** Constraint-weighted spectral Laplacian, C-CAP feasibility projections, thermal-potential-field anchoring, hierarchical group-centroid pre-clustering, DPO-Init coarse-grid probe, and any future constraint-aware initializer.

---

## System-Wide Impact

### Files That Change (by layer)

| Layer | File | Change |
|-------|------|--------|
| **Core plumbing** | `optimizer/train.py` | Import `PlacementConstraints`; add `constraints` param to `initialize_training_state()`, `train()`, `train_multiphase()`; thread through body |
| **Initializers** | `optimizer/initialization.py` | Import `PlacementConstraints`; add `constraints` param to `SpectralInitializer.initialize()`, `LearnedInitializer.initialize()` |
| **Initializers** | `optimizer/zone_aware_init.py` | Import `PlacementConstraints`; add `constraints` param to `ZoneAwareSpectralInitializer.initialize()`; pass to `super()` call |
| **Call sites** | `cli/__init__.py` | Pass `constraints=constraints` to `train_multiphase()` and `train()` |
| **Call sites** | `regression/corpus_runner.py` | Pass `constraints=constraints` to `train_multiphase()` |
| **Call sites** | `ablation/runner.py` | Pass `constraints=constraints` to `train_multiphase()` and `train()` |
| **Tests (new)** | `tests/optimizer/test_constraint_passthrough_init.py` | Property-based test + per-initializer unit tests |

### Files That Must NOT Change

| File | Reason |
|------|--------|
| `optimizer/phases.py` | `GeometricPhase` does not own a `PlacementConstraints` reference; defer to future work |
| `core/state.py` | `PlacementState.random_init` does not need constraints (random init is constraint-agnostic) |
| `io/config_loader.py` | `PlacementConstraints` is already defined; no schema changes needed |
| `optimizer/config.py` | `OptimizerConfig` / `InitializationConfig` are unchanged |
| Any YAML / config schema | No new config keys |

### Import Graph Impact

Before:
```
cli -> optimizer.train (train/train_multiphase/initialize_training_state)
corpus_runner -> optimizer.train (train_multiphase)
ablation/runner -> optimizer.train (train/train_multiphase)
optimizer.train -> optimizer.initialization (SpectralInitializer, LearnedInitializer)
optimizer.train -> optimizer.zone_aware_init (ZoneAwareSpectralInitializer)
```

After (2 new edges):
```
optimizer.train -> io.config_loader (PlacementConstraints)       [NEW]
optimizer.initialization -> io.config_loader (PlacementConstraints)  [NEW]
optimizer.zone_aware_init -> io.config_loader (PlacementConstraints) [NEW]
```

Both new imports are one-way into `io/` — no cycle risk.

---

## Verification Strategy

### 1. Property-Based Invariant Test

**New file:** `packages/temper-placer/tests/optimizer/test_constraint_passthrough_init.py`

**Test 1: Invariance under constraints passthrough**

Property: `initialize_training_state()` outputs are element-wise identical whether `constraints=None` or a populated `PlacementConstraints` is passed, given the same RNG seed and config.

```python
def test_initialize_training_state_constraint_invariance():
    """
    Given: identical netlist, board, config, and seed.
    When: called with constraints=None vs. populated PlacementConstraints.
    Then: positions, rotation_logits, and net_virtual_nodes are element-wise identical.
    """
    # Setup: small test netlist, board, config with spectral init
    # Seeded config (same seed for both calls)
    config = OptimizerConfig(
        initialization=InitializationConfig(method="spectral"),
        seed=42
    )
    state_none = initialize_training_state(netlist, board, config, constraints=None)
    state_populated = initialize_training_state(
        netlist, board, config,
        constraints=PlacementConstraints(zones=[...], component_groups=[...])
    )
    assert jnp.allclose(state_none.positions, state_populated.positions)
    assert jnp.allclose(state_none.rotation_logits, state_populated.rotation_logits)
    assert jnp.allclose(state_none.net_virtual_nodes, state_populated.net_virtual_nodes)
```

**Test 2: Per-initializer constraint acceptance**

Each initializer's `initialize()` method can be called with `constraints=PlacementConstraints(...)` without error, and produces the same output as `constraints=None`.

```python
def test_spectral_initializer_accepts_constraints():
    initializer = SpectralInitializer()
    pos_none = initializer.initialize(netlist, board, constraints=None)
    pos_populated = initializer.initialize(
        netlist, board, constraints=PlacementConstraints()
    )
    assert jnp.allclose(pos_none, pos_populated)

def test_zone_aware_initializer_accepts_constraints():
    initializer = ZoneAwareSpectralInitializer()
    pos_none = initializer.initialize(netlist, board, constraints=None)
    pos_populated = initializer.initialize(
        netlist, board, constraints=PlacementConstraints()
    )
    assert jnp.allclose(pos_none, pos_populated)

def test_learned_initializer_accepts_constraints():
    initializer = LearnedInitializer()
    pos_none = initializer.initialize(netlist, board, constraints=None)
    pos_populated = initializer.initialize(
        netlist, board, constraints=PlacementConstraints()
    )
    assert jnp.allclose(pos_none, pos_populated)
```

### 2. Regression: Existing Test Suite

All existing tests call functions without the new `constraints` parameter. Because the parameter defaults to `None`, they pass unchanged.

Key test files to verify:
- `tests/optimizer/test_train_initialization.py` — calls `initialize_training_state()` (3 arg, no constraints)
- `tests/optimizer/test_force_directed_init.py` — calls `initialize_training_state()` (3 arg, no constraints)
- `tests/optimizer/test_initialization.py` — calls `SpectralInitializer.initialize()` (2 arg, no constraints)
- `tests/optimizer/test_train.py` — calls `train()` (8 arg, no constraints)
- `tests/optimizer/test_phases.py` — indirect via curriculum, no `train()` sig change impacts

### 3. CI Gate Strategy

The change triggers two natural CI gates:

1. **Type-check (`pyright`):** The new type annotations on `constraints: PlacementConstraints | None = None` must type-check clean.
2. **All existing tests:** `pytest` on the full test suite must pass with zero diffs (parameter is optional).
3. **Import boundary check** (`import-linter`): The new imports from `optimizer/` → `io/config_loader` must not violate module boundaries. `optimizer` already depends on `io` indirectly via `heuristics` (which imports `PlacementConstraints`); adding a direct `optimizer → io` edge should be permitted or allowlisted.

To run: `cd packages/temper-placer && uv run pytest tests/optimizer/ -x -q`

### 4. Manual Verification — A/B Comparison

Run optimization on a representative board (e.g., the Temper PCB) with and without constraints passthrough:

```bash
# With constraints (post-change, via CLI)
temper-placer optimize board.kicad_pcb -c constraints.yaml -o output_with.kicad_pcb --epochs 100

# Without constraints (pre-change, same seed)
# Compare final loss, wirelength, component positions — must be bitwise-identical
```

**Null hypothesis:** No difference in final placement quality (wirelength, loss, convergence epoch).
**Metric:** Element-wise max position delta, final loss delta, HPWL delta — all must be zero (same seed, same init, same optimizer path).

---

## Mathematical Basis

### Induction Proof: Adding an Optional Parameter Preserves All Existing Behavior

**Theorem:** Let `f(x, y, z)` be a function with call sites `c₁, ..., cₙ`. Define `f'(x, y, z, w = None)` where the body of `f'` is identical to `f` except that the parameter `w` is forwarded (via keyword) to internal functions that also gain the optional parameter. Then, for all call sites `cᵢ` that invoke `f'` without `w` (i.e., `f'(x, y, z)`):

```
∀i ∈ [1, n]: f'(x, y, z) ≡ f(x, y, z)
```

**Proof by structural induction:**

**Base case (leaf initializers):** `SpectralInitializer.initialize(self, netlist, board, _rng_key=None, constraints=None)`. The method body does not reference `constraints`. Therefore `initialize(netlist, board)` ≡ `initialize(netlist, board, constraints=None)` ≡ `initialize(netlist, board, constraints=PlacementConstraints(...))`. The `constraints` parameter has no effect on the return value.

**Inductive step 1 (`initialize_training_state`):** Let `g(netlist, board, config)` be the original `initialize_training_state`. Let `g'(netlist, board, config, initial_state=None, constraints=None)` be the modified version. Inside `g'`, the `constraints` parameter is only forwarded to initializer `initialize()` calls via `initializer.initialize(netlist, board, constraints=constraints)`. By the base case, the initializer output is invariant to the value of `constraints`. Therefore `g'(netlist, board, config)` ≡ `g(netlist, board, config)`.

**Inductive step 2 (`train` and `train_multiphase`):** By the same reasoning, `train'` and `train_multiphase'` differ from their originals only in that they accept and forward `constraints` to `initialize_training_state`. Since `g'` is invariant to `constraints`, both outer functions are invariant.

**Conclusion:** Adding the optional `constraints: PlacementConstraints | None = None` parameter to the entire call chain preserves all existing behavior. The parameter acts as a pass-through conduit with zero side effects until a downstream initializer reads it.

### Formal Invariant Specification

```
Original:  initialize_training_state(netlist, board, rng_key)
Modified:  initialize_training_state(netlist, board, rng_key, constraints=None)

Invariant: ∀ netlist, board, rng_key:
  initialize_training_state(netlist, board, rng_key, constraints=None)
  ≡ initialize_training_state(netlist, board, rng_key, constraints=c)
  for any population of PlacementConstraints c
```

This invariant is enforced by the property-based test (Verification Strategy item 1).

---

## Implementation Ordering

| Order | Unit | Depends On | Estimated Complexity |
|-------|------|------------|---------------------|
| 1 | IU-4: Initializer signatures | None | Simple (signature + import) |
| 2 | IU-1: `initialize_training_state()` | IU-4 | Simple (import + signature + 3 forward-thru) |
| 3 | IU-2: `train()` | IU-1 | Trivial (signature + 1 forward-thru) |
| 4 | IU-3: `train_multiphase()` | IU-1 | Trivial (signature + 1 forward-thru) |
| 5 | IU-5a: CLI call sites | IU-2, IU-3 | Trivial (2 kwarg additions) |
| 6 | IU-5b: Corpus runner call site | IU-3 | Trivial (1 kwarg addition) |
| 7 | IU-5c: Ablation runner call sites | IU-2, IU-3 | Trivial (2 kwarg additions) |
| 8 | Property-based tests | All above | Write test file |
| 9 | Regression run | All above | `pytest tests/optimizer/` |

**Total estimated diff:** ~25 lines across 6 files, plus ~80 lines of test code.

---

## References

- Requirements: `docs/brainstorms/2026-07-01-constraint-passthrough-init-requirements.md`
- Ideation (idea #1): `docs/ideation/2026-07-01-placement-init-ideation.md`
- `PlacementConstraints` definition: `packages/temper-placer/src/temper_placer/io/config_loader.py:620`
- Composability pattern precedent: `docs/solutions/architecture-patterns/declarative-stage-dag-replaces-orchestrator-2026-06-22.md`
