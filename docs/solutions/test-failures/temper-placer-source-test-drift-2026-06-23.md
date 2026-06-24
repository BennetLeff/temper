---
title: "Pre-existing test failures in temper-placer: source/test drift reconciliation"
date: 2026-06-23
category: docs/solutions/test-failures/
module: "temper-placer (phased_component_assignment, router_v6, io, kicad_exporter)"
problem_type: test_failure
component: testing_framework
severity: high
symptoms:
  - "37 pre-existing test failures across phased_component_assignment, io, and router_v6 suites"
  - "PipelinePhase enum missing 8 sub-phases (ZONE_GEOMETRY, ZONE_ASSIGNMENT, ...) in both state.py and orchestrator.py"
  - "PlacementConstraints missing seed_filter field; drc_oracle not registering plane net stub traces; TEMPER_PLANE_NETS had 6 entries commented out"
  - "DesignRules dataclass fields lacked defaults so DesignRules() failed; _segment_search helper missing; OccupancyGrid used int16 instead of int8; validate_net_prep did not flag empty tht_locations"
  - "Vulture dead-code baseline carried 15 stale entries (unused imports, un-prefixed dead parameters, stale exception args) and 2 false-positive settings decorators"
root_cause: incomplete_setup
resolution_type: code_fix
tags:
  - temper-placer
  - jax
  - test-drift
  - pcb-io
  - router-v6
  - phased-assignment
  - vulture-baseline
  - enum-sync
related_components:
  - pydantic-dataclass-migration
  - declarative-stage-dag-replaces-orchestrator
  - unified-stage-protocol
---

# Pre-existing test failures in temper-placer: source/test drift reconciliation

## Problem

Across multiple sessions, `temper-placer` (the Python/JAX PCB placement
optimizer) accumulated 37 pre-existing test failures and 17 stale entries in
its vulture dead-code baseline. The unifying cause is bidirectional drift:
when features were added to source code (new enum members, new dataclass
fields, new required arguments, new algorithm paths), the corresponding
tests, validators, type stubs, and dead-code allowlist were not
synchronized.

## Symptoms

- `pytest temper-placer/` reports 37 failures with no recent code change to
  explain them; many tracebacks end in
  `AttributeError: 'PhasedComponentAssignment' object has no attribute 'w_r'`
  or `TypeError: DesignRules.__init__() missing N required positional
  arguments`.
- `vulture temper-placer/ --min-confidence 80` flags 17 entries including
  `ListedColormap`, `get_strategy_description`, and `Self` even though
  these names still appear in source.
- KiCad exporter tests assert `path.cells` geometry, but production code
  branches on `path.segments` / `path.coordinates` first and silently
  returns the wrong shape.
- Hypothesis-based property tests raise
  `InvalidArgument: @settings decorator must be paired with @given` at
  collection time, blocking the entire test module.
- `validate_net_prep` accepts `BoardState()` with the default
  `tht_locations=frozenset()` and reports it as valid, even though empty
  `tht_locations` should fail the check (the bug is a `None` check, but
  the default is non-`None`).

## What Didn't Work

- **Fixing tests first to match current source.** This made the suite green
  but masked the real intent of the feature additions (e.g. the 8 new
  `PipelinePhase` sub-phases, the new `seed_filter` field, the new
  `design_rules` parameter). It also locked in undocumented behavior and
  made future refactors harder.
- **Mass-deleting the vulture baseline.** Removing the baseline file
  outright silenced the warnings but eliminated protection against newly
  introduced dead code. A trimmed, accurate baseline is strictly more
  useful than no baseline.
- **Adding `try/except AttributeError` shims in source.** This was
  tempting for the `w_r` and `_bottleneck_map` cases — wrapping attribute
  access in `getattr(self, 'w_r', None)` would have made the tests pass
  — but it would have hidden a real initialization bug and made the class
  silently accept malformed construction.
- **Treating each failure as independent.** Running the suite 37 times,
  reading 37 tracebacks, and patching each in isolation burned several
  hours before the drift pattern (Categories A–H below) became visible.
  Once grouped, the same five-line fix applied to all three `__init__`
  bugs at once.

## Solution

The fixes cluster into eight categories. Each is a concrete instance of
"feature add in source code → dependent update skipped."

### Category A — Missing `__init__` initialization (3 fixes)

**File:** `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py`

Three separate attributes were accepted in `__init__` but never persisted
to `self`:

```python
# Before
class PhasedComponentAssignmentStage(Stage):
    def __init__(self, ..., w_r: float, ...):
        # w_r was in the signature but never assigned
        # _bottleneck_map was set by tests via self._bottleneck_map = ...
        #   but never declared here
        # logger was referenced in this method body but never created
        ...

# After
class PhasedComponentAssignmentStage(Stage):
    def __init__(self, ..., w_r: float, ...):
        ...
        self.channel_map = channel_map
        self.w_r = w_r
        if seed_filter is None:
            seed_filter = getattr(constraints, "seed_filter", None)
        self.seed_filter = seed_filter
        self._bottleneck_map = None
        self.compiler = ConstraintCompiler(constraints)
```

The test that exposed the bug (it set `obj._bottleneck_map = {...}`
directly and called a method that consumed it) was correct in its
assumption; the production class was wrong to require this to be set
externally.

### Category B — Unreachable code (3 fixes)

**Files:** `packages/temper-placer/src/temper_placer/io/kicad_exporter.py` and
`packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py`

Two parallel bugs in the KiCad exporter and one in phasing.

`path_to_segments` previously did:

```python
# Before — `.cells` branch was dead code (only reachable if `.segments` and `.coordinates` were both empty)
if hasattr(path, "segments") and path.segments:
    coords = path.segments
elif hasattr(path, "coordinates") and path.coordinates:
    coords = path.coordinates
else:
    return []  # ← returned here, never reached the .cells handling below
# ...
return segments

# Dead code below — never executed:
if not path.success or not hasattr(path, "cells") or len(path.cells) < 2:
    return []
simplified_cells = simplify_path(path.cells)
# ... actual segment generation from .cells

# After — `.cells` is the real primary handler
coords = []
if hasattr(path, "cells") and getattr(path, "cells", None):
    path_cell_size = getattr(path, "cell_size", cell_size)
    layer_map = layer_map or DEFAULT_LAYER_MAP
    simplified = simplify_path(path.cells)
    for c in simplified:
        x, y = grid_to_world(c, origin, path_cell_size)
        layer_name = layer_map.get(c.layer, "F.Cu")
        coords.append((x, y, layer_name))
elif hasattr(path, "segments") and path.segments:
    coords = list(path.segments)
elif hasattr(path, "coordinates") and path.coordinates:
    coords = list(path.coordinates)
else:
    return []
# ... unified segment generation
```

`path_to_vias` had the identical pattern with the identical fix (74 lines
of dead code deleted, primary handler promoted to top).

`_filter_by_domain` in `phased_component_assignment.py` was defined but
never called from `_place_optimize` (the optimizer had been refactored to
skip the call). Re-introducing the call:

```python
# In _place_optimize, after the bottleneck filter:
available_slots = self._apply_bottleneck_filter(
    ref, available_slots, comp_by_ref
)

if not available_slots:
    continue

# Re-introduced call (was missing)
available_slots = self._filter_by_domain(
    ref, available_slots, domain_for_ref, domain_regions
)
```

### Category C — Enum/dataclass missing values (4 fixes)

**File 1:** `packages/temper-placer/src/temper_placer/pipeline/state.py` and
`packages/temper-placer/src/temper_placer/pipeline/orchestrator.py`

`BOUNDARY_NAMES` had grown to 13 entries; `PipelinePhase` had not. Eight
sub-phases were added to both enums (kept in lockstep):

```python
# pipeline/state.py and pipeline/orchestrator.py (both)
class PipelinePhase(Enum):
    """Enumeration of pipeline phases in execution order."""
    INPUT = "input"
    SEMANTIC = "semantic"
    TOPOLOGICAL = "topological"
    PREFLIGHT = "preflight"
    GEOMETRIC = "geometric"
    ROUTING = "routing"
    REFINEMENT = "refinement"
    OUTPUT = "output"
    # Deterministic sub-phases (BoundaryRegistry boundaries).
    ZONE_GEOMETRY = "zone_geometry"
    ZONE_ASSIGNMENT = "zone_assignment"
    SLOT_GENERATION = "slot_generation"
    COMPONENT_ASSIGNMENT = "component_assignment"
    APPLY_PLACEMENTS = "apply_placements"
    COURTYARD_CHECK = "courtyard_check"
    APPLY_PLACEMENTS_REAPPLY = "apply_placements_reapply"
    PLACEMENT_VALIDATION = "placement_validation"
```

**File 2:** `packages/temper-placer/src/temper_placer/io/config_loader.py`

```python
# PlacementConstraints — added the missing field
seed_filter: SeedFilterConfig = field(default_factory=SeedFilterConfig)
```

`SeedFilterConfig` defaults to `enabled=True, threshold=0.7,
hv_threshold=0.5`, matching the design intent that the filter is active
by default.

**File 3:** `packages/temper-placer/src/temper_placer/router_v6/stage0_data.py`

`DesignRules` had six fields with no defaults, so `DesignRules()` (the
only sane call for tests) was a `TypeError`:

```python
# Before — every field required
@dataclass
class DesignRules:
    net_classes: dict[str, NetClassRules]
    net_class_assignments: dict[str, str]
    default_clearance_mm: float
    default_trace_width_mm: float
    default_via_diameter_mm: float
    default_via_drill_mm: float
    min_hole_to_hole_mm: float = 0.25
    min_annular_ring_mm: float = 0.1

# After — sensible defaults
@dataclass
class DesignRules:
    net_classes: dict[str, NetClassRules] = field(default_factory=dict)
    net_class_assignments: dict[str, str] = field(default_factory=dict)
    default_clearance_mm: float = 0.2
    default_trace_width_mm: float = 0.2
    default_via_diameter_mm: float = 0.6
    default_via_drill_mm: float = 0.3
    min_hole_to_hole_mm: float = 0.25
    min_annular_ring_mm: float = 0.1
```

**File 4:** `packages/temper-placer/src/temper_placer/core/design_rules.py`

`NetClassRules.dru_priority` was a required field with no default. Test
construction (`NetClassRules("name", ...)`) failed. Two changes:

```python
# Make dru_priority have a default
dru_priority: int = 0  # was: dru_priority: int  # lower emits earlier in DRU ...

# Accept a positional name for ergonomics
def __init__(self, name: str = "", **data: object) -> None:
    if name and "name" not in data:
        data["name"] = name
    super().__init__(**data)
```

### Category D — Optional/required signature drift (3 fixes)

**File 1:** `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py`

`run_astar_pathfinding` was hard-requiring `design_rules`, but tests
constructed a grid without one. Made it optional with a `DesignRules()`
default:

```python
# Before
def run_astar_pathfinding(
    channel_mapping: ChannelMapping,
    grid: OccupancyGrid,
    design_rules: DesignRules,  # required
    ...
) -> PathfindingResult: ...

# After
def run_astar_pathfinding(
    channel_mapping: ChannelMapping,
    grid: OccupancyGrid,
    design_rules: DesignRules | None = None,
    ...
) -> PathfindingResult:
    if design_rules is None:
        design_rules = DesignRules()
    ...
```

**File 2:** `packages/temper-placer/src/temper_placer/cli/__init__.py` and
`cli/optimize.py`

`optimize(...)` had its `spice_penalty_weight` parameter briefly renamed
to `_spice_penalty_weight` to silence vulture, but tests call it by name.
Reverted the rename — kept `spice_penalty_weight` (vulture baseline entry
is the suppression mechanism, not a rename). This is documented in the
spice_penalty_weight baseline entries in `deadcode-baseline.py`.

**File 3:** `packages/temper-placer/src/temper_placer/router_v6/astar_core.py` (caller fix)

`RoutePath.__init__` doesn't accept `segment_count`; it's a `@property`
computed from `len(coordinates) - 1`. Caller in `astar_pathfinding.py`
was passing `segment_count=len(detailed_coords) - 1` as a kwarg:

```python
# Before — caller passed segment_count as kwarg
return RoutePath(
    net_name=net_name,
    coordinates=detailed_coords,
    layer_name=grid.layer_name,
    segment_count=len(detailed_coords) - 1,  # TypeError: unexpected keyword
    path_length=path_length,
    forced_segment_count=forced_segments,
)

# After — let the @property compute it
return RoutePath(
    net_name=net_name,
    coordinates=detailed_coords,
    layer_name=grid.layer_name,
    path_length=path_length,
    forced_segment_count=forced_segments,
)
```

### Category E — Test-data staleness (2 fixes)

**File 1:** `packages/temper-placer/tests/io/test_dsn_boundary.py`

`BOUNDARY_NAMES` legitimately grew from 5 to 13 entries (8 new
deterministic sub-phases). Test was pinning the count:

```python
# Before — test pinned the old 5-boundary count
def test_list_boundaries_returns_five_names():
    names = BoundaryRegistry.list_boundaries()
    assert names == ["semantic", "topological", "placement", "routing", "validation"]

# After — test enumerates the current 13 boundaries
def test_list_boundaries_returns_thirteen_names():
    names = BoundaryRegistry.list_boundaries()
    assert names == [
        "semantic", "topological", "placement", "routing", "validation",
        "zone_geometry", "zone_assignment", "slot_generation",
        "component_assignment", "apply_placements", "courtyard_check",
        "apply_placements_reapply", "placement_validation",
    ]
```

**File 2:** `packages/temper-placer/tests/io/test_dsn_boundary.py` and
`test_dsn_integration.py`

`output_format` and `serialization_fn` vary per boundary type. The old
test asserted `output_format == "dsn"` for all 13 — but
`placement_validation` legitimately produces `output_format="json"` and
`serialization_fn="serialize_violations_to_json"`.

```python
# Before — over-strict assertions
assert bd.output_format == "dsn"
assert bd.serialization_fn == "export_pcb"

# After — allow the per-boundary variation
expected_output_format = {"dsn", "json"}
expected_serialization_fn = {
    "export_pcb", "serialize_boardstate_to_dsn", "serialize_violations_to_json",
}
for name in BOUNDARY_NAMES:
    bd = BoundaryRegistry.get_boundary(name)
    assert isinstance(bd, BoundaryDef)
    assert bd.output_format in expected_output_format
    assert bd.pipeline_class in expected_pipeline_class
    assert bd.serialization_fn in expected_serialization_fn
```

### Category F — Test-side bugs (3 fixes)

**File 1:** `packages/temper-placer/tests/io/test_kicad_exporter.py`

Test was correct (`path.cells` is the right attribute) — source was
wrong. Fixed in Category B.

**File 2:** `packages/temper-placer/tests/router_v6/test_astar_pathfinding.py`

Test was correct (callers shouldn't need to pass `design_rules`) — source
was wrong. Fixed in Category D.

**File 3:** Three property-based tests in
`packages/temper-placer/tests/router_v6/`

Hypothesis errors at collection: `@settings(...)` on a function without
`@given` is rejected. Three tests had `@settings` but no `@given`
(decorator left over from copy-paste of property-based tests).

```python
# Before — Hypothesis errors at collection
@settings(max_examples=50, deadline=30000)
def test_net_prep_name():
    """NetPrepStage has correct name."""
    stage = NetPrepStage()
    assert stage.name == "NetPrep"

# After — @settings removed; test is now a plain assertion test
def test_net_prep_name():
    """NetPrepStage has correct name."""
    stage = NetPrepStage()
    assert stage.name == "NetPrep"
```

Files: `test_net_prep_pbt.py`, `test_stage4_result_pbt.py`,
`test_stage4_route_pbt.py`.

### Category G — Validator logic bug (1 fix)

**File:** `packages/temper-placer/src/temper_placer/router_v6/net_prep_stage.py`

`validate_net_prep` only flagged `tht_locations is None`. But
`BoardState()` defaults `tht_locations` to `frozenset()` (empty, non-`None`).
The check passed for a freshly-constructed state with zero THT pads —
exactly the case the validator was meant to reject.

```python
# Before
def validate_net_prep(state: BoardState) -> list[StageDRCFailure]:
    """Validate net prep invariants."""
    failures: list[StageDRCFailure] = []
    if not hasattr(state, "tht_locations") or state.tht_locations is None:
        failures.append(StageDRCFailure(
            field="tht_locations",
            value=None,
            reason="THT pad locations not computed",
            stage="NetPrep",
        ))
    return failures

# After — catches both None and empty container
def validate_net_prep(state: BoardState) -> list[StageDRCFailure]:
    """Validate net prep invariants."""
    failures: list[StageDRCFailure] = []
    tht = getattr(state, "tht_locations", None)
    if tht is None or (hasattr(tht, "__len__") and len(tht) == 0):
        failures.append(StageDRCFailure(
            field="tht_locations",
            value=tht,
            reason="THT pad locations not computed",
            stage="NetPrep",
        ))
    return failures
```

### Category H — Vulture baseline hygiene (17 entries removed)

**File:** `deadcode-baseline.py`

The vulture baseline carried 15 stale entries (real dead code that had
been fixed but not yet trimmed from the baseline) and 2 stale line
numbers (line numbers shifted after a refactor).

Real dead code removed (imports):
- `temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py:716` — `from matplotlib.colors import ListedColormap` (imported, never used)
- `temper-placer/src/temper_placer/routing/unified_router.py:33` — `get_strategy_description` from `current_capacity_strategy` (imported, never used)
- `temper-validation/src/temper_validation/comparison/drc_compliance.py:8` — `from typing import Self` (Python 3.11+ feature not yet adopted)

Real dead code removed (function parameters prefixed with `_`):
- `cli/_signal.py:14` — `frame` (signal handler arg)
- `cli/optimize.py:728` — `frame` (signal handler arg)
- `cli/timing.py:267` — `ci_mode` (click option)
- `deterministic/stages/clearance_grid.py:703` — `highlight_nets` (visualization param)
- `routing/unified_router.py:268` — `trace_clearance` (push-shove param)
- `explainability/markdown_report.py:377` — `max_decisions_per_component` (render param)

Real dead code removed (`__exit__` exception args):
- `optimizer/checkpoint.py:94` and `explainability/traced_loss.py:217` —
  three args each (`exc_type`, `exc_val`, `exc_tb`) → `_exc_type`,
  `_exc_val`, `_exc_tb` (Python convention; required by signature,
  unused in body).

Side-effect imports marked with `# noqa: F401`:
- `routing/c_space_builder.py:13` — `import shapely` (only used via the
  `HAS_SHAPELY` flag; bare name on module was unused).
- `tests/geometry/test_drc_inflate.py:16` — `import shapely` inside
  `_has_shapely()` (same pattern).

Stale line numbers updated:
- `kicad_exporter.py:149` and `kicad_exporter.py:238` (unreachable code
  entries) — removed; the unreachable code itself was deleted in
  Category B.
- `kicad_exporter.py:565` → `:511` (redundant `if True:` block shifted
  after deletions).

## Why This Works

All eight categories share one root cause: when a feature is added to a
hot path, the change set is usually scoped to "the file I'm editing"
rather than "the whole dependency surface." The dependencies that drift
are predictable:

1. **Constructors** — any new field added to `__init__` must be assigned,
   or `__init__` itself is wrong. Three of the 37 failures were this.
2. **Enum/dataclass expansion** — adding members to a
   `PipelinePhase`-style enum means every `match` / `if phase == X`
   site, every dispatch table, and every test that enumerates members
   must be updated. Adding the new `seed_filter` field to
   `PlacementConstraints` was a 1-line fix; making `NetClassRules` work
   for tests required both a default value and a positional-name
   `__init__`.
3. **Optional vs. required** — turning a required parameter into an
   optional one (or vice versa) silently breaks every call site that
   passed positionally. `run_astar_pathfinding(design_rules=...)` was
   the right call; making the param optional is a backward-compat win.
4. **Algorithmic dead code** — when an algorithm is rewritten, the old
   function is often left behind. Either delete it or call it; both are
   correct, but keeping it "in case" creates unreachable code that
   vulture eventually flags. The 100+ lines of dead code in
   `kicad_exporter.py:149-238` is a canonical example.
5. **Test fixtures and assertions** — tests that pin specific values
   (`== 5`, `== "dsn"`) become load-bearing the moment the underlying
   state grows. The fix is either to update the value (Category E) or
   to assert a more abstract property (`in {"dsn", "json"}`).
6. **Validator truthiness** — `is None` is almost always wrong for
   collection-typed fields, because the natural default is an empty
   container, not `None`. `validate_net_prep` is the textbook case.
7. **Hypothesis / `@settings` without `@given`** — Hypothesis 6.x
   rejects `@settings` on a non-property test. The error is loud
   (collection-time `InvalidArgument`) but easy to miss when
   introducing a new test file via copy-paste.

The fix is not to add more defensive code in the source (that masks the
drift); it is to update the dependents when the source changes. The
`__init__` discipline, dataclass defaults, and vulture baseline all
encode the same lesson: every signature is a contract, and contracts
have consumers.

## Prevention

### 1. Use `@dataclass` for anything with more than three init fields

```python
# Before
class PhasedComponentAssignmentStage(Stage):
    def __init__(self, w_r, bottleneck_map=None, ...):
        # w_r was forgotten; the test caught it
        ...

# After
@dataclass
class PhasedComponentAssignmentStage(Stage):
    w_r: float
    bottleneck_map: Optional[dict] = None
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    # forgetting w_r is now a TypeError at construction time
```

### 2. Pin enum members in tests, not their count

```python
# Before — pin count, breaks on any expansion
assert len(PipelinePhase) == 5

# After — pin membership, survives any expansion
assert PipelinePhase.ZONE_GEOMETRY in PipelinePhase
assert PipelinePhase.EXPORT in PipelinePhase
# Or, if a count test is required, derive it from a known-good source:
assert len(PipelinePhase) == len(_load_expected_phases_from_manifest())
```

### 3. Codegen for enum/dataclass expansion

If `BOUNDARY_NAMES` and `PipelinePhase` must stay in lockstep, generate
one from the other:

```python
# In a tools/ script (run by CI):
class _BoundaryManifestLoader:
    def __post_init__(self):
        self.phases = [PipelinePhase(b.upper()) for b in BOUNDARY_NAMES]
```

CI fails if a new boundary is added to `BOUNDARY_NAMES` but no phase is
added to `PipelinePhase`.

### 4. Pre-commit hook for `__init__` completeness

```python
# .pre-commit-hooks/check_init_completeness.py
import ast
import sys

def check(path: str) -> int:
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            params = {arg.arg for arg in node.args.args + node.args.kwonlyargs}
            body_src = ast.unparse(node)
            missing = [p for p in params if p != "self" and
                       f"self.{p} " not in body_src and
                       f"self.{p}=" not in body_src and
                       f"self._{p} " not in body_src]
            if missing:
                print(f"{path}: __init__ params not assigned: {missing}")
                return 1
    return 0
```

### 5. Run vulture on every PR, with allowlist revalidation

```yaml
# .github/workflows/vulture.yml
- name: Vulture
  run: |
    vulture temper-placer/ --min-confidence 80 > /tmp/found.txt
    diff /tmp/found.txt temper-placer/deadcode-baseline.py  # CI fails on drift
```

Trim the baseline by hand every quarter; never `git rm` the file. The
existing `scripts/vulture_gate.py` (CI gate) treats the baseline as a
permissive allowlist: findings NOT in the baseline are NEW (block PR);
findings IN the baseline are accepted. Stale entries surface as
"STALE BASELINE ENTRIES — remove these lines" which fails the gate
until the source is updated to match.

### 6. Use `not container` for collection validation

```python
# Before
if board.tht_locations is None: ...

# After — handles None, [], (), {}. and frozenset() all at once
if not board.tht_locations: ...
```

### 7. PBT pairing check

```python
# In CI: a flake8 plugin or AST pass that flags:
#   @settings(...)  on a function without @given above it
# Hypothesis already does this at runtime, but catching it at lint time
# avoids the entire test module being skipped.
```

### 8. When renaming a parameter, grep for the old name in tests before committing

```bash
# Before any rename:
rg "\bspice_penalty_weight\b" temper-placer/ --type py
# If any test passes it by keyword, the rename is unsafe.
```

### 9. When introducing a new test file via copy-paste, strip unused Hypothesis decorators

`@settings` without `@given` is a collection-time error. Either add
`@given(...)` (turn it into a real property-based test) or remove
`@settings` (turn it into a plain assertion test). The 3 failing
`test_*_pbt.py` files in this fix are copy-paste artifacts of this
pattern.

## Related Issues

- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` —
  the meta-pattern this work is a concrete instance of. The 17-entry
  vulture trim is direct evidence the "Baseline + Monotonic Shrink"
  pattern works at scale; the gate is in
  `scripts/vulture_gate.py`.
- `docs/solutions/architecture-patterns/pydantic-dataclass-migration.md` —
  the `@dataclass → BaseModel` migration that produced the
  `NetClassRules` evolution; one of the data-model changes whose
  ripple effects are exactly the source/test drift described here.
- `docs/solutions/architecture-patterns/declarative-stage-dag-replaces-orchestrator-2026-06-22.md` —
  the refactor that introduced the new `PipelinePhase` semantics
  (`ZONE_GEOMETRY` etc.). The orchestrator's `PipelinePhase` enum was
  the breaking-change point that produced 3 of the 8 missing sub-phases
  fixes.
- `docs/solutions/architecture-patterns/unified-stage-protocol-multi-pipeline-2026-06-22.md` —
  defines the cross-pipeline `Stage` protocol that the seed filter,
  hv_lv partition, and astar stages now conform to — directly relevant
  to `test_seed_filter_integration.py` and `test_astar_pathfinding.py`.
- `docs/solutions/architecture-patterns/layer-index-ssot-placer-2026-06-23.md`
  and `docs/solutions/architecture-patterns/pad-position-ssot-placer-2026-06-23.md` —
  the U1/U2 SSOT consolidations that caused caller-side test drift in
  `OccupancyGrid` and `DesignRules` consumers.
- `AGENTS.md` → "Transition Table Regeneration" and "Script Manifest
  Convention" — the same discipline (single manifest, codegen,
  CI-rejected drift) applied to state machines and operational scripts.
