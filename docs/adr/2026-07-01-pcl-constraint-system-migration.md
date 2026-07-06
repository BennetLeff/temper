---
date: 2026-07-01
status: accepted
plan-id: 2026-07-01-pcl-constraint-migration
supersedes: []
---

# ADR-001: PCL as Single Source of Truth for Placement Constraints

## Context

The temper-placer pipeline maintains **two independent constraint systems**:

1. **Legacy** (`io/config_loader.py`, ~1730 lines): `PlacementConstraints`
   dataclass loaded from YAML via `load_constraints()`. Used by
   `input_stage.py` to apply fixed components, zones, and board constraints.
   Full-featured but built on dataclass serialization rather than PCL's
   type-safe constraint DSL.

2. **PCL** (`pcl/constraints.py`, ~752 lines): Type-safe constraint DSL with
   `@constraint(...)` decorators, `Constraint` base class, `GeometryConstraint`,
   `ElectricalConstraint`, `ThermalConstraint`, `ComposedConstraint`, and a
   constraint registry. Used by the geometric and refinement stages for
   programmatic constraint generation.

This dual-system state **broke the optimize path**. When the geometric stage
was forked to accept `deterministic_result` from the topological phase, the
`optimize` entry point began silently auto-discovering constraints from the
PCL registry, while `input_stage` continued loading the legacy
`PlacementConstraints`. The two constraint graphs could diverge with zero
diagnostics -- constraints defined in the legacy YAML would silently override PCL
equivalents, and PCL-only constraints would silently bypass compatibility
checks in the legacy loader.

A contributor encountering this code has no documented answer to "which
constraint system should I use?" and must reverse-engineer intent from two
divergent codebases.

### Affected Code Paths

| Path | Role |
|---|---|
| `packages/temper-placer/src/temper_placer/io/config_loader.py` | Legacy `load_constraints()`, `PlacementConstraints` dataclass, apply functions |
| `packages/temper-placer/src/temper_placer/pcl/constraints.py` | PCL constraint DSL, `Constraint` base, registry, decorators |
| `packages/temper-placer/src/temper_placer/pipeline/stages/input_stage.py` | Consumes legacy constraints via `config_loader.load_constraints()` |
| `packages/temper-placer/src/temper_placer/pipeline/stages/geometric_stage.py` | Consumes PCL constraints indirectly via loss functions |

## Decision

**PCL (`pcl/constraints.py`) is the single canonical source of truth for
all placement constraints.** The legacy `PlacementConstraints` dataclass and
`io/config_loader.py` constraint-loading path are deprecated and will be
removed.

The migration path:

1. **Phase 1 (2026-Q3, current):** `input_stage.py` is refactored to use
   PCL constraint loading instead of `config_loader.load_constraints()`.
   Legacy YAML schema continues to be supported via a PCL bridge adapter
   that translates the old format into PCL `Constraint` objects.

2. **Phase 2 (2026-Q3):** All consumers of `PlacementConstraints` (zones,
   fixed components, board constraints) are ported to PCL APIs. The legacy
   `PlacementConstraints` dataclass is marked `@deprecated` with a
   `DeprecationWarning` at import time.

3. **Phase 3 (2026-Q4, sunset):** `io/config_loader.py`'s constraint-loading
   functions are deleted. Remaining utility functions (Kicad parsing, zone
   management) are relocated to `io/kicad_parser.py` or `io/zone_manager.py`.
   The legacy YAML format's PCL bridge adapter becomes the documented
   backward-compatibility path.

### Sunset Conditions

The legacy `PlacementConstraints` dataclass and `io/config_loader.py`
constraint-loading path will be deleted when **all** of these conditions
are met:

- All pipeline stages that consume `constraints` (input, topological,
  preflight, routing, refinement) use PCL `Constraint` objects exclusively.
- No code imports `PlacementConstraints` or calls `load_constraints()`
  outside of tests for the PCL bridge adapter.
- The PCL bridge adapter has test coverage matching the legacy loader's
  existing test suite.
- All `@req` annotations referencing the legacy constraint system have been
  updated or retired.

## Consequences

### Positive

- **Single source of truth:** Contributors know PCL is the canonical
  constraint system without reverse-engineering.
- **Type safety:** PCL's `@constraint()` decorators and registry provide
  compile-time (mypy) verification that legacy dataclass serialization cannot.
- **Eliminates silent-skip bug:** No divergence path between `input_stage`
  and downstream consumers -- all stages read from the same constraint graph.
- **Extensibility:** Adding a new constraint type requires only a PCL
  subclass, not changes to two independent code paths.

### Negative

- **Migration cost:** The legacy YAML format has consumers outside the
  pipeline (scripts, tests) that must be updated or bridged.
- **Temporary complexity:** The PCL bridge adapter adds an intermediate
  translation layer during Phase 1-2.
- **Risk of YAML schema breakage:** If the bridge adapter misses edge cases
  in the legacy YAML format, downstream tools that read the old schema will
  break silently.

### Neutral

- This ADR establishes the MADR format and `docs/adr/` directory as the
  convention for all pipeline architecture decisions going forward.
- DAG topology changes (add/remove/rename/reorder stages in the pipeline
  manifest) require an ADR per the `check_adr_gate.py` CI gate.
