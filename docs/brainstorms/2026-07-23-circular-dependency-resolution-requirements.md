---
date: 2026-07-23
topic: circular-dependency-resolution
---

# Circular Dependency Resolution: Eliminating PEP 562 Workarounds and Extracted Type Stubs

## Summary

Resolve the two documented circular dependency workarounds in `temper_placer/`: (1) the PEP 562 `__getattr__` lazy-loading hack in `router_v6/__init__.py` (165 lines) that breaks the `router_v6 -> constraint_model -> deterministic -> router_v6` cycle, and (2) the `_constraint_types/` package extracted from `io/config_loader` to break a `constraints -> io` cycle. The resolution applies standard techniques -- dependency inversion, interface extraction, and deferred binding -- to eliminate the need for runtime lazy-loading and generated type-stub packages.

---

## Problem Frame

`temper_placer/` has two documented circular dependency workarounds that exist because the architecture evolved faster than the module boundaries could be restructured:

**Workaround 1: `router_v6/__init__.py` PEP 562 lazy loading (165 lines)**

The cycle is router_v6 <-> deterministic. Specifically, 19 router_v6/ files import Stage and BoardState from deterministic, while deterministic imports 25+ concrete types from router_v6/ submodules. The dominant direction is mutual: deterministic defines the stage framework that router_v6 stages plug into, and router_v6 provides routing-specific implementations that deterministic stages consume. Rather than resolving the cycle structurally, `router_v6/__init__.py` uses `__getattr__` (PEP 562) to defer imports until attribute access:

```python
def __getattr__(name: str):
    if name == "Pipeline":
        from temper_placer.router_v6.pipeline import Pipeline
        return Pipeline
    if name == "Adapter":
        from temper_placer.router_v6.adapter import Adapter
        return Adapter
    # ... 20+ more deferred imports
```

This has concrete costs:
- **Tooling blindness**: Static analyzers (mypy, ruff, Vulture) see `from router_v6 import Pipeline` as possibly unresolved. Type checking and dead-code detection are degraded.
- **Startup latency**: First access to any deferred symbol triggers a file-system import. In hot paths (CI test runs importing router_v6 100+ times), this adds measurable overhead.
- **Cognitive load**: New contributors see a 165-line `__init__.py` that is essentially a hand-maintained registry. Understanding what `router_v6` exports requires reading the `__getattr__` function, not the module's public API.
- **Maintenance fragility**: Adding a new public symbol to `router_v6` requires updating the `__getattr__` registry. Forgetting to do so causes `AttributeError` at runtime, not at import time.

The `.importlinter` contract `router-v6-public-interface-only` enforces that external packages must import through `__init__.py` -- which means the lazy-loading hack is load-bearing infrastructure, not a temporary shim.

**Workaround 2: `_constraint_types/` extracted type stubs (9 files)**

The cycle was: `constraints/` imported from `io/config_loader` (to read default values), and `io/config_loader` imported from `constraints/` (to create constraint objects from config). The fix was extracting 9 pure `@dataclass` files into `_constraint_types/` -- a package with no I/O logic, no imports from `io/`, and no imports from `constraints/`. Both `io/config_loader` and `constraints/` now import from `_constraint_types/`.

This is structurally sound (the type definitions belong in their own layer) but incomplete:
- The `_` prefix signals "internal, don't import directly" yet both `io/` and `constraints/` import from it -- it's not internal, it's shared.
- The package is explicitly excluded from coverage gates via `omit = ["**/_constraint_types/**"]` -- not because it's untestable, but because it's "generated." This is a gap.
- The naming (`_constraint_types`) doesn't communicate that these are the shared data model for the constraint system.

Workaround 2 was structurally resolved by the `_constraint_types` extraction. The remaining work is rename (`_constraint_types` -> `constraint_types`) and adding test coverage -- no dependency edges are changing. This is a cosmetic cleanup, not a dependency restructure.

---

## Prerequisites

- **PREREQ-1.** `router_v6/adapter.py` must be decomposed (per the monster-file-decomposition requirements) before protocol extraction begins. The adapter is the likely coupling point between `deterministic` and `router_v6`; extracting a protocol from a 1,127-line file risks creating a poorly-designed interface.
- **PREREQ-2.** Before deleting `__getattr__`, replace it with eager imports one symbol at a time in a draft branch. For each symbol, verify that `python -c 'from temper_placer.router_v6 import <symbol>'` succeeds without circular import errors. Any symbol that fails indicates an undocumented cycle.
- **PREREQ-3.** Before implementation: audit every symbol in the `__getattr__` registry. For each, verify it can be imported directly from its canonical submodule. Any symbol without a canonical submodule must be given one or handled as a re-export. Document the audit results.

---

## Requirements

### Router v6 Cycle Resolution

- **R1.** Identify the minimal interface that `deterministic` needs from `router_v6`. Extract this into a protocol or abstract base class in a shared location (either `core/` or a new `interfaces/` package). The protocol defines WHAT deterministic needs (e.g., `route_nets(nets, state) -> RoutedBoard`), not HOW router_v6 implements it.
- **R1c.** Identify all types used in the protocol's signature (`RoutedBoard`, net representations, state types). Verify their current module location. Any type defined in `router_v6/` must either (i) also be extracted to the shared location, or (ii) the protocol must use only types already in `core/`. Document the chosen path.
- **R2.** `deterministic` depends on the protocol, not on `router_v6`. `router_v6` implements the protocol. This breaks the `deterministic -> router_v6` edge.
- **R2b.** Identify the injection point: the module that constructs the router implementation and passes it to `deterministic`. Verify this module is not in `router_v6/`, `deterministic/`, or `constraint_model/`. If no suitable injection point exists, document the new wiring module as part of scope.
- **R3a.** Before implementation: audit `constraint_model`'s imports from `deterministic`. Classify each import as data-structure or orchestration.
- **R3b.** If all imports are data-structure: extract them to `core/` so `constraint_model` no longer depends on `deterministic` directly.
- **R3c.** If any imports are orchestration: document the tighter cycle and create a follow-up plan -- do not block R1/R2/R4.
- **R4.** After the cycle is broken structurally, `router_v6/__init__.py` becomes a normal re-export hub (like `core/__init__.py`) without `__getattr__` lazy loading. The 165-line hack is deleted. The `router-v6-public-interface-only` contract is updated to reflect normal submodule imports rather than lazy-loaded symbols.
- **R4a.** Before removing `__getattr__`, identify every import-linter allowlist entry resolved by the cycle-breaking changes. Remove resolved entries. Verify that no new violations are introduced by adding previously unlisted submodules to `forbidden_modules`.

### Constraint Types Rename and Integration

- **R5.** Rename `_constraint_types/` to `constraint_types/` (removing the misleading `_` prefix). Update all imports in `io/` and `constraints/` to use the new path. The package keeps its current role as the shared data model with zero I/O dependencies. After rename, run `find . -path '*_constraint_types*' -name '__pycache__' -exec rm -rf {} +` to remove stale bytecode.
- **R6.** Remove the `_constraint_types/` entry from `[tool.coverage.run] omit` in `pyproject.toml`. Add basic tests for the dataclass validation (e.g., default values, field types, serialization round-trips). The tests are lightweight -- these are pure data classes, not business logic.
- **R7.** Document `constraint_types/` as "shared constraint data model" in a module-level docstring. Add a `# WARNING: Do not add I/O dependencies` comment so future contributors know the no-I/O contract.

### General Principle

- **R8.** Any future circular dependency discovered by import-linter is resolved structurally (dependency inversion, interface extraction, or layer reordering) rather than with runtime workarounds (lazy loading, deferred imports, `sys.modules` hacks). The import-linter `.importlinter` configuration is the canonical specification of allowed dependency directions.

---

## Acceptance Examples

- **AE1. Covers R4.** Given the cycle is resolved, when `rg '__getattr__' packages/temper-placer/src/temper_placer/router_v6/__init__.py` runs, it returns zero hits. The `__init__.py` is a normal re-export hub with explicit imports.
- **AE2. Covers R1, R2.** Given a router protocol exists in a shared location (per the decision on R1), deterministic imports the protocol, not router_v6.
- **AE3. Covers R5.** Given `_constraint_types/` is renamed, (a) `rg '_constraint_types' packages/ scripts/ tests/ --type py` returns zero hits. (b) `rg '_constraint_types' pyproject.toml .github/` returns zero hits.
- **AE4. Covers R6.** Given tests exist for `constraint_types/`, when `pytest .../tests/constraint_types/ -v` runs, it reports >=80% line coverage on hand-written code in `constraint_types/`. Auto-generated `@dataclass` boilerplate (`__init__`, `__repr__`, `__eq__`) is excluded from the denominator. If `__post_init__` validators exist, they must be tested at 100%.

---

## Success Criteria

- `router_v6/__init__.py` has zero `__getattr__` or other lazy-loading machinery
- `_constraint_types/` directory no longer exists; `constraint_types/` replaces it with test coverage
- Import-linter reports zero cycles involving `router_v6`, `deterministic`, `constraint_model`, `io`, or `constraints`
- Closure test, CP-SAT parity tests, and deterministic placement tests produce results within existing CP-SAT parity tolerance (if any is defined) or pass the existing parity test suite with no regressions
- No regressions in CI gating: existing hard-fail steps remain hard-fail; existing soft-launch steps continue to pass (warn-level output unchanged or improved); no new `continue-on-error` annotations introduced

---

## Scope Boundaries

- **In scope:** The two documented circular dependencies (`router_v6 -> constraint_model -> deterministic -> router_v6` and `constraints <-> io`). Any additional cycles discovered during resolution that involve `router_v6`, `deterministic`, `constraint_model`, `io`, or `constraints`.
- **In scope:** Updating test file imports to match renamed modules and new import paths. Test logic and assertions should not change -- only import statements.
- **Out of scope:** Re-architecting the entire module dependency graph. The goal is to eliminate cycles, not to achieve a perfect layered architecture.
- **Out of scope:** Router v6 consolidation (covered by dead-code elimination requirements) or monster file decomposition (covered separately).
- **Out of scope:** Changing the `.importlinter` boundary declaration format (the YAML structure itself) or the import-linter enforcement mechanism (the CI gate). Updating existing contract rules (e.g., `router-v6-public-interface-only`) to reflect new import paths is in scope and required by R4. Any allowlist entries resolved by cycle-breaking changes must be removed.

---

## Abort Criteria

If any of the following are discovered during implementation, stop and escalate to architecture review:

1. `constraint_model` imports orchestration functions from `deterministic`.
2. The router protocol requires more than 5 methods or involves types that cannot be extracted without restructuring `router_v6/`.
3. Removing `__getattr__` reveals a second hidden cycle not documented here.

---

## Key Decisions

- **Protocol over ABC.** Python `Protocol` (structural subtyping) is preferred over `ABC` (nominal subtyping) for the router interface because `deterministic` only needs to call `route_nets()`, not to be the parent class of `router_v6.Pipeline`. This avoids introducing an inheritance relationship where a structural one suffices.
- **Protocol type isolation.** The protocol's method signatures must use only types from `core/` or the standard library. Any `router_v6`-specific type that appears in a protocol signature must be extracted to `core/` as part of this work. If a type cannot be extracted without pulling in `router_v6` implementation details, the protocol approach must be reconsidered.
- **Shared location preference: `core/` over `interfaces/`.** Adding a new top-level package (`interfaces/`) creates a new layer that every other package depends on. Placing the protocol in `core/` leverages the existing dependency direction (everything already depends on `core/`). A new `interfaces/` package is warranted only if the router protocol is large enough (>=5 methods) to justify its own module.
- **Rename `_constraint_types` rather than merging back.** The extraction was correct -- constraint type definitions are conceptually independent of both I/O and constraint construction logic. The only problem is the misleading `_` prefix and missing tests.

---

## Dependencies / Assumptions

- **Methodology.** All implementation follows TDD (Red-Green-Refactor per AGENTS.md). Dependency inversion is validated by property-based tests (Hypothesis) proving that the extracted Protocol interface is sufficient: for any conforming implementation, every call path that exercised the original concrete type also succeeds through the protocol. Base cases are proven correct via unit tests on the protocol's method set; the PBT invariant generalizes to arbitrary implementations (induction over the implementation space). No protocol extraction ships without at least one PBT invariant proving behavioral equivalence.
- **Assumption:** `constraint_model`'s dependency on `deterministic` is for data structures only (e.g., `PlacementState`, `Board`) not for orchestration (e.g., `run_deterministic_pipeline()`). Verified by checking `constraint_model`'s imports from `deterministic`. If orchestration is imported, the cycle is tighter than estimated.
- **Assumption:** The router_v6 import-linter contract (`router-v6-public-interface-only`) can be updated to use normal submodule imports without breaking external consumers. The 20+ deferred symbols in `__getattr__` correspond to distinct submodules that are already importable directly -- `__getattr__` is a convenience, not a necessity.
- **Dependency:** This work must be sequenced after or alongside monster file decomposition for `router_v6/adapter.py` (1,127 lines) since the adapter is likely where `deterministic` and `router_v6` couple.

---

## Outstanding Questions

### Resolve Before Planning

- **[Affects R1][User decision]** Where should the router protocol live? Option A: `temper_placer.core.interfaces` (follows existing convention that `core/` is the shared foundation). Option B: a new `temper_placer.interfaces/` package (cleaner separation but adds a new top-level dependency). Option C: inline in `deterministic` as a local protocol (simplest, but means `router_v6` imports from `deterministic` which reintroduces an edge in the other direction).
- **[Affects R3][Technical]** What exactly does `constraint_model` import from `deterministic`? The answer determines whether a simple data-structure extraction (to `core/`) suffices or if the cycle requires a different split. This investigation gates whether the R3 approach (data-structure extraction to `core/`) is sufficient. If the answer reveals orchestration imports, the overall plan must be re-scoped.

### Deferred to Planning

- **[Affects R2][Technical]** What is the minimal method set for the router protocol? `route_nets(nets, state) -> RoutedBoard` is the obvious entry point, but does `deterministic` also need progress callbacks, cancellation, or per-net status queries?
- **[Affects R5][Technical]** Do any external consumers (scripts, CI workflows, tests outside `packages/`) import from `_constraint_types`? A repo-wide `rg` is needed before renaming.
