---
title: "Pattern: Invariant Chain with Multi-Boundary Enforcement (4-Layer Board Example)"
date: 2026-06-30
category: architecture-patterns
module: temper-placer
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "A physical design constraint (e.g., layer count, material stackup) is canonical for the product but not structurally enforced in tooling — a deviation can silently produce invalid outputs"
  - "A factory method or default path produces a variant that contradicts the canonical design and must be gated to test-only"
  - "Multiple serialization/writer call sites exist and each independently needs guardrail validation before committing output"
  - "The enforcement requires defense-in-depth: construction-time invariants, pipeline-stage checks, output-writer guards, and CI-level semantic verification"
symptoms:
  - "A `default_2layer()` factory method existed alongside `default_4layer()` with no structural barrier preventing production use of the 2-layer path"
  - "Board objects accepted any `LayerStackup` at construction without validating layer count against the canonical design"
  - "KiCad `.kicad_pcb` files could be written with any number of copper layers — no output-time invariant check existed on `to_file()`"
  - "No CI gate verified that the committed `.kicad_pcb` maintained the canonical 4-copper-layer structure"
root_cause: missing_validation
resolution_type: tooling_addition
tags:
  - invariant-chain
  - defense-in-depth
  - layer-stackup
  - canonical-design
  - pcb-manufacturing
  - kicad-export
  - property-testing
  - ci-gate
  - board-construction
  - boundary-enforcement
  - ssot
  - fail-fast
---

# Pattern: Invariant Chain with Multi-Boundary Enforcement

## Context

A system has a critical invariant — say, "the board must have exactly 4 layers with
canonical names" — but code paths exist that can violate it silently. The canonical
factory (`default_4layer()`) coexists with an alternative factory (`default_2layer()`)
with no guard preventing misuse. A downstream writer dynamically selects between
output formats based on input content rather than the invariant. The result: silent
wrong output that passes all existing checks but is electrically broken.

Per-boundary checks (a CI gate alone, or a construction-time check alone) are
insufficient because each boundary has a different bypass vector. The invariant
must be enforced at every transition between systems.

## Guidance

Define a **canonical source of truth** for the invariant, then **validate it
independently at every boundary** where data crosses between domains:
construction, pipeline entry, serialization/output, and CI. Each boundary runs
its own check — no boundary trusts any other.

### 1. Canonical Source of Truth

A single, immutable constant defines what "correct" means. Every enforcement
point imports from this one location. No boundary defines its own notion of the
invariant.

```python
# core/model.py — single source of truth, frozen

class LayerIndex(IntEnum):
    """Canonical layer identifiers. .value is the int, str() gives the name."""
    F_CU = 0
    IN1_CU = 1
    IN2_CU = 2
    B_CU = 3

    def __str__(self) -> str:
        return _KICAD_NAME[self]

STANDARD_LAYER_ORDER: tuple[LayerIndex, ...] = (
    LayerIndex.F_CU, LayerIndex.IN1_CU, LayerIndex.IN2_CU, LayerIndex.B_CU,
)

CANONICAL_LAYER_NAMES: frozenset[str] = frozenset({
    str(li) for li in LayerIndex
})
```

### 2. Construction-Time Validation (Fail Fast)

The model object rejects invalid state at creation. A dataclass `__post_init__`
is the natural hook; the model should be `frozen=True` so the invariant cannot
drift post-construction.

```python
@dataclass(frozen=True)
class LayerStackup:
    layers: tuple[Layer, ...]

    def __post_init__(self):
        if len(self.layers) != len(LAYER_INDEX):
            raise ValueError(
                f"Expected {len(LAYER_INDEX)} layers, got {len(self.layers)}"
            )
        actual = {layer.name for layer in self.layers}
        if actual != CANONICAL_LAYER_NAMES:
            raise ValueError(
                f"Layer names mismatch. Expected {CANONICAL_LAYER_NAMES}, got {actual}"
            )

@dataclass
class Board:
    layer_stackup: LayerStackup = field(default_factory=default_4layer)

    def __post_init__(self):
        # validate even after default factory — catches manual construction
        if len(self.layer_stackup.layers) != len(LAYER_INDEX):
            raise ValueError("Board must have canonical layer stackup")
```

Key: `__post_init__` runs on every construction path — direct, factory, and
deserialization. No bypass.

### 3. Pipeline Entry Validation (Fence Invariant)

Even with frozen models, serialization/deserialization boundaries can bypass
`__post_init__` (e.g., `pickle`, `json.loads`, or rehydrated state objects).
Add a pipeline-entry invariant that re-validates before processing begins.

```python
# pipeline/stages/preflight.py

from core.fence import InvariantSpec

class PreflightStage(Stage):
    @property
    def invariants(self) -> tuple[InvariantSpec, ...]:
        return (
            InvariantSpec(
                check_name="stackup_has_4_copper_layers",
                guarantees="Board has exactly the canonical 4 copper layers",
            ),
        )
```

The fence auto-discovers invariants from the stage and runs them at the boundary.
If the invariant fails, the pipeline halts immediately with an attributed error
naming the violating stage and the expected vs actual values.

Additionally, validate nested objects that could carry a non-canonical board
through deserialization:

```python
@dataclass(frozen=True)
class BoardState:
    board: Board

    def __post_init__(self):
        # Catches deserialization bypass — Board.__post_init__ may not have run
        if len(self.board.layer_stackup.layers) != len(LAYER_INDEX):
            raise ValueError("BoardState contains board with non-canonical stackup")
```

### 4. Output Validation (Pre-Write Assertion)

The serializer/writer validates the invariant immediately before writing to
disk. This is the last line of defense — even if every upstream guard failed,
the writer refuses to produce wrong output.

```python
def write_output(model, path: str):
    _validate_invariant(model)  # raises before any I/O
    model.to_file(path)

def _validate_invariant(model):
    layers = model.copper_layers()
    if len(layers) != len(LAYER_INDEX):
        raise RuntimeError(
            f"Refusing to write: expected {len(LAYER_INDEX)} copper layers, "
            f"found {len(layers)}: {[l.name for l in layers]}"
        )
    names = {l.name for l in layers}
    if names != CANONICAL_LAYER_NAMES:
        raise RuntimeError(
            f"Refusing to write: layer names mismatch. "
            f"Expected {CANONICAL_LAYER_NAMES}, got {names}"
        )
```

Call `_validate_invariant()` before every `to_file()` call site. If there are
multiple writer modules, each module calls it independently — no shared
assumption that "someone else already checked."

### 5. Property Tests (Combinatorial Coverage)

A property test verifies that _for any valid input_, the output respects the
invariant. This catches edge cases that unit tests miss.

```python
from hypothesis import given, settings
from hypothesis import strategies as st

@given(board_state=valid_board_state_strategy())
@settings(max_examples=100)
def test_output_has_4_canonical_layers(board_state):
    """Theorem: any pipeline output has exactly 4 copper layers with canonical names."""
    pcb = export_and_parse(board_state)
    copper_layers = [l for l in pcb.layers if l.type == "copper"]

    assert len(copper_layers) == len(LAYER_INDEX), \
        f"Expected {len(LAYER_INDEX)} copper layers, found {len(copper_layers)}"

    names = {l.name for l in copper_layers}
    assert names == CANONICAL_LAYER_NAMES, \
        f"Expected {CANONICAL_LAYER_NAMES}, got {names}"
```

### 6. CI Gate (Regen-Diff + Semantic Check)

Two complementary CI checks catch drift in the committed artifact:

**Regen-diff:** Regenerate the artifact from spec, diff against the committed
copy. Any difference — including layer count — fails CI.

```yaml
# .github/workflows/check.yml
- name: Regenerate output and diff
  run: |
    python pipeline/generate.py --output pcb/board.kicad_pcb
    git diff --exit-code pcb/board.kicad_pcb
```

**Semantic layer check:** Parse the committed artifact and validate the invariant
semantically. This tolerates benign format changes (version upgrades, whitespace
reformatting) that a textual `git diff` would reject.

```yaml
- name: Verify layer count in committed file
  run: python tools/check_layers.py pcb/board.kicad_pcb
```

```python
# tools/check_layers.py
def check_layers(path: str) -> None:
    board = parse_kicad_pcb(path)
    copper = [l for l in board.layers if l.type == "copper"]
    if len(copper) != len(LAYER_INDEX):
        sys.exit(f"ERROR: {path} has {len(copper)} copper layers, expected {len(LAYER_INDEX)}")
    names = {l.name for l in copper}
    if names != CANONICAL_LAYER_NAMES:
        sys.exit(f"ERROR: {path} layer names {names}, expected {CANONICAL_LAYER_NAMES}")
```

### 7. Remove Legacy Paths

Delete the bypass path — don't just gate it. The alternative factory,
alternative layer map, and dynamic format selection logic are all removed.
A `_test_only_*()` helper with a call-site guard remains for tests that need
a simplified model:

```python
import inspect, sys

def _test_only_2layer() -> LayerStackup:
    """Test-only 2-layer stackup. Raises if called from non-test code."""
    caller = inspect.stack()[1].filename
    if not any(part in caller for part in ("/tests/", "/test_", "conftest.py")):
        raise RuntimeError(
            "_test_only_2layer() may only be called from test files. "
            f"Called from: {caller}"
        )
    return LayerStackup(layers=(...))
```

### The Full Chain

```
Canonical SSOT (frozen constant)
    │
    ▼
Construction (__post_init__) ─── rejects non-canonical before it exists in memory
    │
    ▼
Deserialization (BoardState.__post_init__) ─── catches pickle/json bypass
    │
    ▼
Pipeline Entry (Preflight InvariantSpec) ─── fence halts pipeline on violation
    │
    ▼
Output (pre-write _validate()) ─── refuses to write wrong output, 12 call sites
    │
    ▼
Property Tests ─── combinatorial fuzz catches edge cases
    │
    ▼
CI Gate (regen-diff + semantic) ─── blocks commits that change the invariant
```

No boundary trusts any other boundary. Each runs the same check against the
same canonical constant. An invariant broken at any level is caught at the
next — layered defense, not single-point.

## Why This Matters

Single-boundary enforcement has a single point of failure. Construction-time
validation catches direct misuse but not deserialization bypass. Output-time
validation catches wrong output but can't tell you _where_ the invariant was
broken — you discover it at the end of a long pipeline run. A CI gate alone
catches committed drift but doesn't stop the developer from running the
pipeline locally with wrong output for hours.

The multi-boundary chain converts silent wrong output into a fast, attributed
error at the earliest possible boundary. A developer who constructs a wrong
board gets a `ValueError` before any pipeline code runs — not a mysterious DRC
failure 5 minutes later.

Removing the legacy path is equally important. A gated-but-present alternative
factory is a trap for the next developer. "Just for testing" becomes "just for
this one case" becomes a production path. Deletion is the only durable guard.

## When to Apply

Apply this pattern when:

- **The invariant is critical to correctness** and violation produces output
  that passes all checks but is functionally wrong (silent failure).
- **Multiple code paths can violate it**: construction, deserialization,
  serialization, output formatting, committed artifacts.
- **A legacy bypass path exists** (alternative factory, dynamic format selection,
  feature-flag-gated alternate code) that must be surgically removed.
- **The canonical source of truth already exists** (e.g., an IntEnum, a
  dataclass, a `frozenset`) — you wire it into boundaries rather than creating
  it from scratch.
- **You have property-test infrastructure** that can exercise the invariant
  combinatorially.

Do NOT apply when:

- The invariant is verified by the type checker alone (e.g., a non-nullable
  field on a dataclass — construction-time is enough).
- There are no serialization boundaries (no pickle, no JSON, no file I/O) —
  construction + CI may suffice.
- The bypass path has zero callers and the caller audit is trivial — just
  delete it, no chain needed.
- Every pipeline run costs minutes and the invariant check dominates runtime
  — use CI-only enforcement with a fast property test suite.

## Examples

### Before: silent wrong output

```python
# core/board.py — two valid factories, no guard
def default_4layer():
    return LayerStackup(layers=[F_Cu, In1_Cu, In2_Cu, B_Cu])

def default_2layer():  # <-- valid path, silent wrong output
    return LayerStackup(layers=[F_Cu, B_Cu])

# io/exporter.py — dynamic format selection based on input
TWO_LAYER_MAP = {0: "F.Cu", 1: "B.Cu"}
FOUR_LAYER_MAP = {0: "F.Cu", 1: "In1.Cu", 2: "In2.Cu", 3: "B.Cu"}

def write(board: Board, path: str):
    layer_map = TWO_LAYER_MAP if len(board.stackup.layers) == 2 else FOUR_LAYER_MAP
    # No validation — writes whatever layer_map resolves to
    ...
```

A board with 2 layers passes all checks. The `.kicad_pcb` has 2 copper layers.
No error. No warning. The board is electrically broken.

### After: invariant chain

```python
# core/board.py — one canonical factory, invariant enforced at construction
CANONICAL_LAYER_NAMES: frozenset[str] = frozenset({"F.Cu", "In1.Cu", "In2.Cu", "B.Cu"})

@dataclass(frozen=True)
class LayerStackup:
    layers: tuple[Layer, ...]

    def __post_init__(self):
        names = {l.name for l in self.layers}
        if names != CANONICAL_LAYER_NAMES:
            raise ValueError(f"Expected {CANONICAL_LAYER_NAMES}, got {names}")

@dataclass(frozen=True)
class BoardState:
    board: Board

    def __post_init__(self):
        # Re-validates — catches deserialization bypass
        names = {l.name for l in self.board.layer_stackup.layers}
        if names != CANONICAL_LAYER_NAMES:
            raise ValueError(...)

# pipeline/stages/preflight.py — fence invariant
class PreflightStage(Stage):
    @property
    def invariants(self):
        return (InvariantSpec(check_name="stackup_has_4_copper_layers"),)

# io/exporter.py — pre-write validation at every call site
def _validate_4_layer_output(pcb):
    copper = [l for l in pcb.layers if l.type == "copper"]
    if len(copper) != len(LAYER_INDEX):
        raise RuntimeError(...)
    if {l.name for l in copper} != CANONICAL_LAYER_NAMES:
        raise RuntimeError(...)

def write_placements(board: Board, path: str):
    pcb = _build_layer_map(board)
    _validate_4_layer_output(pcb)  # <-- called before to_file()
    pcb.to_file(path)

# tools/check_layers.py — CI semantic gate
def main(path):
    board = parse(path)
    copper = [l for l in board.layers if l.type == "copper"]
    if len(copper) != 4 or {l.name for l in copper} != CANONICAL_LAYER_NAMES:
        sys.exit(1)

# tests/test_4layer_properties.py — property test
@given(board_state=valid_board_strategy())
def test_output_has_4_canonical_layers(board_state):
    pcb = export_and_parse(board_state)
    copper = [l for l in pcb.layers if l.type == "copper"]
    assert len(copper) == 4
    assert {l.name for l in copper} == CANONICAL_LAYER_NAMES
```

A wrong board is caught at the earliest possible boundary — construction — with
a clear error message naming the mismatch. Failing that, the pipeline fence
catches it. Failing that, the writer refuses to write. Failing that, the
property test catches it. Failing that, CI catches it.

## Related

- `docs/solutions/architecture-patterns/layer-index-ssot-placer-2026-06-23.md` — the LayerIndex SSOT this invariant chain builds on
- `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md` — pipeline invariant pattern reused for the preflight fence
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — sibling CI gate pattern (baseline + monotonic shrink)
- `docs/solutions/architecture-patterns/pydantic-dataclass-migration.md` — sibling "validate at construction" pattern
- `docs/brainstorms/2026-06-30-4-layer-enforcement-requirements.md` — origin requirements (R1–R12)
- `docs/plans/2026-06-30-001-feat-4-layer-enforcement-plan.md` — implementation plan (U1–U7)
- `packages/temper-placer/src/temper_placer/core/board.py` — `LayerIndex`, `LayerStackup`, `Board` with `__post_init__` validation
- `packages/temper-placer/src/temper_placer/io/kicad_exporter.py` — `_validate_4_layer_output()` at 12 write call sites
- `packages/temper-placer/src/temper_placer/io/kicad_writer.py` — output validation in placement writer
- `packages/temper-placer/src/temper_placer/manufacturing/stackup_validator.py` — professional stackup quality checks (copper symmetry, return-path adjacency, impedance, copper balance)
- `packages/temper-placer/tests/io/test_4layer_output_properties.py` — Hypothesis property test for 4-layer output invariant
- `tools/check_kicad_layers.py` — CI semantic layer-count gate
