---
title: "LayerIndex IntEnum SSOT for Placer Layer Names (Python Consolidation)"
date: 2026-06-23
category: architecture-patterns
module: temper-placer/core
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "The same concept is encoded three different ways (string, int, dict) across the placer"
  - "Adding or renaming a layer requires a manual find-and-replace across N files"
  - "An existing dataclass already establishes the concept as first-class (e.g., `Layer`)"
  - "A enum can carry the canonical string (via `__str__`) and the numeric index (via `IntEnum.value`) at the same time"
tags: [ssot, intenum, layer-index, placer, core-board, refactor, consolidation, type-safety]
---

# LayerIndex IntEnum SSOT for Placer Layer Names

## Context

The placer accumulated three independent representations of "which layer is which": string names (`"F.Cu"`, `"In1.Cu"`), numeric indices (`{1, 2}`), and bidirectional dicts — across 13+ files. They drifted silently: `INTERNAL_LAYERS` in `routing/constraints/drc_oracle.py:60` was `{1, 2}` (numeric) while `PLANE_LAYERS` in `deterministic/stages/via_validation.py:21` was `{"In1.Cu", "In2.Cu"}` (string) for the same plane-layer concept. Every layer change was a manual find-and-replace, and a missed call site became a silent runtime bug (wrong layer, off-by-one, "Unknown" lookup).

`core/board.py` already had a `Layer` dataclass and a `LayerStackup.default_4layer()` that built four hand-written `Layer` instances — the layer concept was first-class; the index representation was the missing piece. This is one of four sequential consolidations (layer-names → pad-position → net classification → A* primitives).

## Guidance

Introduce a `LayerIndex(IntEnum)` in `core/board.py` colocated with the `Layer` dataclass, plus a small surface of constants and helpers. Big-bang migrate every duplicated representation in a single PR — intermediate states with two representations are confusing and review burden is bounded by reviewer patience, not diff size.

### The canonical surface (in `core/board.py`)

```python
class LayerIndex(IntEnum):
    F_CU = 0
    IN1_CU = 1
    IN2_CU = 2
    B_CU = 3

    def __str__(self) -> str:
        # .name returns the Python identifier ("F_CU").
        # __str__ returns the KiCad name ("F.Cu"). Document this.
        return _KICAD_NAME[self]  # or a small mapping

STANDARD_LAYER_ORDER: tuple[LayerIndex, ...] = (
    LayerIndex.F_CU, LayerIndex.IN1_CU, LayerIndex.IN2_CU, LayerIndex.B_CU,
)

PLANE_LAYER_INDICES: frozenset[LayerIndex] = frozenset(
    {LayerIndex.IN1_CU, LayerIndex.IN2_CU}
)

LAYER_IDX_TO_NAME: dict[LayerIndex, str] = {li: str(li) for li in LayerIndex}
LAYER_NAME_TO_IDX: dict[str, LayerIndex] = {v: k for k, v in LAYER_IDX_TO_NAME.items()}

def is_plane_layer(name_or_index: str | LayerIndex) -> bool: ...
def is_signal_layer(name_or_index: str | LayerIndex) -> bool: ...
def side_to_layer_name(side: int) -> str:  # raises ValueError for non-{0,1}
def layer_name_to_index(name: str) -> LayerIndex:  # raises KeyError for unknown
```

### Migration rules

1. **Replace every `["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]` literal** with `STANDARD_LAYER_ORDER` (iteration) or `LAYER_NAME_TO_IDX` (lookup).
2. **Replace every `frozenset({"In1.Cu", ...})` and `frozenset({1, 2})`** with `PLANE_LAYER_INDICES`. Membership is O(1); `IntEnum` is hashable.
3. **Replace every `layer = "F.Cu" if side == 0 else "B.Cu"`** with `side_to_layer_name(side)`. The new helper is stricter — non-{0,1} now raises `ValueError` instead of silently defaulting to `"B.Cu"`. That is a positive behavior change but is observable.
4. **Co-locate the canonical surface with the existing `Layer` dataclass.** Do not create a new module — the `Layer` type is the natural sibling.
5. **Do not migrate runtime lookups against parsed-KiCad data** (e.g., `stage2.skeletons.get("F.Cu")` — keyed by the file's actual layers, not the canonical 4).
6. **Audit `LAYER_IDX_TO_NAME.get(idx, "F.Cu")` defaults.** The string-literal fallback is itself a bug — after migration the dict is keyed by `LayerIndex`, so the default must be `LayerIndex.F_CU` or direct access (after verifying the index is always in range).
7. **Functions whose return type changes** (e.g., `_default_layer` returning `LayerIndex` instead of `str`) require a call-site sweep. For string-formatting sites, wrap with `str(value)`; for `==` comparisons against string literals, switch to `LayerIndex.XXX`.

## Why This Matters

`IntEnum` gives the type checker something to flag — a `str` argument where `LayerIndex` is expected becomes a `mypy`/`pyright` error, not a runtime `KeyError`. The `.value` is the int, the `__str__` is the KiCad name, and the `.name` is the Python identifier; choosing `__str__` over `.name` for the KiCad name is the linchpin (IntEnum's `.name` returns `"F_CU"`, not `"F.Cu"`).

A `frozenset[LayerIndex]` for membership is the right container: hashable, O(1) `in`, and the constant is module-imported once and shared by reference across files. A `tuple[LayerIndex, ...]` for `STANDARD_LAYER_ORDER` is immutable, can be a dict key if ever needed, and is the right default for a constant that no call site mutates.

The closure test bit-identicality check (`completion_rate`, trace coordinates, DRC violations) is the integration gate — refactors of canonical surfaces must not change routing output.

## When to Apply

- **Adding a new layer** to the standard stack: edit `LayerIndex` + `STANDARD_LAYER_ORDER` + (if plane) `PLANE_LAYER_INDICES`; nothing else.
- **Adding new layer-dependent code**: import from `core/board.py` — do not define local copies of the layer list, the name↔index dict, or the side ternary.
- **Hitting drift symptoms** (a layer change required updating N files; a `KeyError`/`IndexError` traced back to a duplicate layer literal): apply this pattern to the concept that drifted.
- **Considering a 6-layer extension**: out of scope until verified; no test currently uses a 6-layer `LayerStackup`. The 6-layer branch in `kicad_exporter.py:1277` and `kicad_parser.py:1277` keeps its inline list.

## Examples

### Before — three encodings, one concept

```python
# deterministic/stages/via_validation.py
PLANE_LAYERS = frozenset({"In1.Cu", "In2.Cu"})
if target_layer_name in PLANE_LAYERS: ...

# routing/constraints/drc_oracle.py
INTERNAL_LAYERS = frozenset({1, 2})
if target_layer in INTERNAL_LAYERS: ...

# router_v6/pipeline.py
layer = "F.Cu" if side == 0 else "B.Cu"

# Hard-coded lists scattered across 9 files
["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
```

### After — one import, one source

```python
from temper_placer.core.board import (
    LayerIndex, STANDARD_LAYER_ORDER, PLANE_LAYER_INDICES,
    LAYER_NAME_TO_IDX, LAYER_IDX_TO_NAME,
    is_plane_layer, side_to_layer_name,
)

# All "is this a plane layer?" checks now use the same constant:
if layer in PLANE_LAYER_INDICES: ...
if is_plane_layer(layer_name_or_index): ...

# Side-to-layer mapping:
layer = side_to_layer_name(side)  # raises ValueError for non-{0,1}

# Iteration over canonical 4-layer order:
for layer_idx in STANDARD_LAYER_ORDER:
    ...
```

### Test pattern (in `tests/core/test_board.py`)

```python
class TestLayerIndex:
    def test_str_is_kicad_name(self):
        assert str(LayerIndex.F_CU) == "F.Cu"
        assert LayerIndex.F_CU.name == "F_CU"  # IntEnum .name is the Python id

    def test_plane_membership(self):
        assert LayerIndex.IN1_CU in PLANE_LAYER_INDICES
        assert "In1.Cu" in {str(li) for li in PLANE_LAYER_INDICES}

    def test_helpers_accept_both(self):
        assert is_plane_layer(LayerIndex.IN1_CU) is True
        assert is_plane_layer("In1.Cu") is True
        assert is_plane_layer("F.Cu") is False

    def test_side_to_layer_name_strictness(self):
        assert side_to_layer_name(0) == "F.Cu"
        assert side_to_layer_name(1) == "B.Cu"
        with pytest.raises(ValueError):
            side_to_layer_name(2)
```

## Related

- `packages/temper-placer/src/temper_placer/core/board.py` — `LayerIndex`, `STANDARD_LAYER_ORDER`, `PLANE_LAYER_INDICES`, helpers
- `packages/temper-placer/src/temper_placer/core/net_types.py` — `_default_layer` returns `LayerIndex`
- `docs/plans/2026-06-23-008-refactor-layer-names-consolidation-plan.md` — the plan with full requirements (R1–R12) and verification
- `docs/brainstorms/2026-06-23-layer-names-consolidation-requirements.md` — origin requirements
- `docs/plans/2026-06-22-002-feat-safety-constant-ssot-plan.md` — sibling SSOT pattern (safety constants)
- `docs/solutions/architecture-patterns/x-macro-ssot-firmware.md` — parallel SSOT pattern (C X-macro for firmware enums)
- `docs/solutions/architecture-patterns/pydantic-dataclass-migration.md` — sibling "validate at construction" pattern
- `docs/solutions/architecture-patterns/4layer-invariant-chain-boundary-enforcement-2026-06-30.md` — invariant chain pattern that builds on this SSOT for end-to-end 4-layer board enforcement
