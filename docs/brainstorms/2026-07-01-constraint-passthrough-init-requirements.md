---
date: 2026-07-01
topic: constraint-passthrough-init-pipeline
focus: Thread PlacementConstraints through initialize_training_state() so every registered initializer can optionally consume domain rules
origin: docs/ideation/2026-07-01-placement-init-ideation.md (#1)
status: active
actors: Placement optimizer developer, CI system
---

# Requirements: Constraint-Passthrough Init Pipeline

## Problem Statement

**Gap: constraints authored vs. constraints used in initialization.**

`PlacementConstraints` (packages/temper-placer/src/temper_placer/io/config_loader.py:620)
codifies 30+ domain-rule categories — zones, component groups, HV/LV separation,
thermal constraints, critical loops, star grounds, clearances, keepouts, noise
isolation, matched-length groups, fixed positions. This object is parsed,
validated, and available at every call site that invokes the optimizer.

Today, `initialize_training_state()` (packages/temper-placer/src/temper_placer/optimizer/train.py:286)
receives `(netlist, board, config, initial_state)` — no `PlacementConstraints`.
Every registered initializer (`SpectralInitializer`, `ZoneAwareSpectralInitializer`,
`LearnedInitializer`) sees only `(netlist, board)` and is blind to codified rules.

**Concrete symptom:** the CLI (packages/temper-placer/src/temper_placer/cli/__init__.py:844-865)
calls `train_multiphase()` / `train()` with `constraints` in scope, then
`initialize_training_state()` is invoked at lines 738 and 1259 without it.
The constraints are dropped on the floor. Identical gap exists in
`corpus_runner.py` and `ablation/runner.py`.

**Impact:** zero of the 6 initializer-improvement ideas in the ideation doc
(constraint-weighted spectral Laplacian, C-CAP feasibility projections,
DPP-diversified multi-seed, thermal anchoring, group-centroid pre-clustering,
coarse-grid probe) can begin until constraints reach the init layer. Every one
of them must independently pipe constraints through — duplicating the same
boilerplate 6 times — or wait for this prerequisite.

## Proposed Change

### Core: Signature Change

Add an optional `constraints` parameter to the pipeline:

```
initialize_training_state(
    netlist: Netlist,
    board: Board,
    config: OptimizerConfig,
    initial_state: PlacementState | None = None,
    constraints: PlacementConstraints | None = None,   # NEW
) -> TrainingState
```

Pass `constraints` through to every registered initializer call site inside
the function body (lines 318-358). Forward downward to:

- `train()` — adds the same optional parameter, passes it through
- `train_multiphase()` — adds the same optional parameter, passes it through

### Current Initializer Signatures (targets to thread to)

| Initializer | File | Current `initialize()` signature |
|---|---|---|
| `SpectralInitializer` | `optimizer/initialization.py:228` | `(self, netlist, board, _rng_key=None)` |
| `ZoneAwareSpectralInitializer` | `optimizer/initialization.py:278` (nested) | inherits `SpectralInitializer` |
| `LearnedInitializer` | `optimizer/initialization.py:573` | `(self, netlist, board, rng_key=None)` |
| `PlacementState.random_init` | `core/state.py` | `(self, n_components, board_width, ...)` |
| force-directed (inline) | `train.py:359-450` | applied post-initializer |

### Add to Each Initializer

Each `initialize()` method gains `constraints: PlacementConstraints | None = None`.
Existing initializers ignore it (pass `None` at the call if no init-specific
handling is implemented yet). Constraint-aware variants added later read the
fields they need.

### Call Site Updates

Three call chains need the parameter threaded:

1. **CLI → `train()` / `train_multiphase()` → `initialize_training_state()`**
   (`cli/__init__.py:844-865`) — `constraints` is already in scope.

2. **Corpus runner → `train_multiphase()` → `initialize_training_state()`**
   (`regression/corpus_runner.py:384`) — `constraints` is already loaded and used on line 388.

3. **Ablation runner → `train()` / `train_multiphase()`**
   (`ablation/runner.py:612,625`) — `constraints` is already in scope.

(Deferred) phases.py → train_multiphase() — not in v1 scope (GeometricPhase does not own constraints; handled by None default).

### Tests

Existing tests in `tests/optimizer/test_train_initialization.py` and
`tests/optimizer/test_force_directed_init.py` call `initialize_training_state()`
without a `constraints` argument. Because the new parameter is optional
(`= None`), these tests pass unchanged — zero regression risk.

Add a minimal test: call `initialize_training_state()` with `constraints=PlacementConstraints(zones=[...])`,
Compare output position arrays and rotation logits element-wise — values must be bitwise-identical when the same RNG seed is used on both calls (existing initializers ignore the constraint parameter by design). The test must use a fixed RNG key (e.g., `jax.random.PRNGKey(0)`) on both constrained and unconstrained calls to ensure deterministic comparison.

## Success Criteria

1. **Compilability.** Code compiles and all existing tests pass with the
   optional parameter added.
2. **No behavioral change.** Existing initializers (spectral, random,
   zone-aware, learned) produce identical outputs whether `constraints=None`
   or a populated `PlacementConstraints` is passed.
3. **Constraint availability.** Any initializer implementation can access
   `PlacementConstraints` fields by reading `constraints.zones`,
   `constraints.component_groups`, `constraints.critical_loops`, etc.
   within `initialize()`.
4. **Failure safety.** `constraints=None` behaves identically to the current
   behavior — no init paths break when constraints are unavailable.
5. **Test addition.** One new test in `test_train_initialization.py` confirms
   the parameter is accepted and does not break existing init behavior.

## Scope Boundaries

### In Scope

- Adding `constraints: PlacementConstraints | None = None` to:
  - `initialize_training_state()` in `optimizer/train.py`
  - `train()` in `optimizer/train.py`
  - `train_multiphase()` in `optimizer/train.py`
- Threading `constraints` through the function body to each initializer dispatch
- Adding `constraints: PlacementConstraints | None = None` to `initialize()`
  on `SpectralInitializer`, `ZoneAwareSpectralInitializer`, `LearnedInitializer`
  (ignored for now)
- Passing `constraints` from call sites that already have it:
  - `cli/__init__.py`
  - `regression/corpus_runner.py`
  - `ablation/runner.py`
- One minimal integration test

### Out of Scope

- Implementing any constraint-aware initialization logic (weighted Laplacian,
  C-CAP projections, thermal anchoring, group pre-clustering, etc.)
- Changing the `OptimizerConfig` dataclass or `InitializationConfig` schema
- Adding new config keys or YAML schema changes
- Wiring constraints through `GeometricPhase` in `optimizer/phases.py`
  (out of scope: `phases.py` does not own the `PlacementConstraints` object)
- Updating `io/__init__.py` exports
- Any loss function changes or gradient modifications

## Dependencies / Prerequisites

- None. This change has no upstream dependencies. `PlacementConstraints` is
  already defined, parsed, and available at all target call sites.
- This change is the prerequisite for:
  - Constraint-weighted spectral Laplacian (ideation #2)
  - C-CAP feasibility projections (ideation #3)
  - Thermal-potential-field anchoring (ideation #6)
  - Hierarchical group-centroid pre-clustering (ideation #7)
  - DPO-Init coarse-grid probe (ideation #5)
  - Any future constraint-aware initializer

## Risks and Unknowns

| Risk | Likelihood | Mitigation |
|---|---|---|
| Type-checker / lint rejects the optional parameter pattern | Low | Follows existing `LossContext` pattern (also optional in many signatures); same typing conventions already in use |
| Some call site not yet identified lacks `constraints` | Low | The parameter is `= None` — all unidentified call sites silently fall through to zero-change behavior |
| `phases.py` needs threading but `GeometricPhase` doesn't own a constraints reference | Medium | Deferred to future work; `GeometricPhase` callers already have constraints but don't inject them into the phase object |
| Future initializers add required `constraints` but callers pass `None` | Medium | Add `assert constraints is not None` inside the constraint-aware initializer's `initialize()` as a self-documenting guard |
| Import cycle from `initialization.py` → `config_loader.py` | Low | `initialization.py` already imports `core.board` and `core.netlist`; `config_loader.py` is in a different sub-package (`io`), no cycle risk |

## Prior Art

Follows the composability pattern established in:
- `docs/solutions/architecture-patterns/declarative-stage-dag-replaces-orchestrator-2026-06-22.md` — each feature is an independent, stackable stage
- Ghost pads → seed filtering → channel-aware scoring — each incrementally added without modifying its predecessors
- This change uses the same pattern: a 3-line plumbing change that all constraint-aware init ideas compose atop
