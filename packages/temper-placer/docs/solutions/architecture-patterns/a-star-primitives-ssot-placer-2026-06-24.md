---
title: "A* Primitives Single Source of Truth in the Placer"
date: "2026-06-24"
category: architecture-patterns
module: routing/heuristics
problem_type: architecture_pattern
component: routing
severity: medium
applies_when:
  - Adding an A* search implementation to the placer
  - Adding or modifying octile distance, neighbor deltas, or bounds-check logic
  - Auditing A* code for duplicate primitives
tags: [astar, routing, primitives, octile, ssot, consolidation]
---

# A* Primitives Single Source of Truth in the Placer

## Context

The placer had multiple A* implementations with duplicated search primitives:
octile distance (`max(dx,dy) + 0.414*min(dx,dy)`), 8-direction neighbor deltas,
and inline bounds checks (`0 <= x < width and 0 <= y < height`). The deadcode
cleanup (commit `347fc34b`) removed four implementations, narrowing the remaining
duplication to two files: `router_v6/astar_core.py` (Python) and
`router_v6/astar_core_numba.py` (Numba JIT).

A divergence in the octile constant (Python `0.414` vs what `math.sqrt(2)-1` produces)
or in the neighbor-delta order between the two implementations could cause subtle
path-output differences between the Python and Numba routing paths. Centralizing
these primitives prevents that class of bug.

## Guidance

### Canonical surface

**Module:** `routing/heuristics.py` (extends the existing Manhattan/Euclidean
heuristic registry).

| Symbol | Type | Description |
|--------|------|-------------|
| `OCTILE_DIAG` | `Final[float]` | `math.sqrt(2.0) - 1.0` (~0.4142135), the octile heuristic diagonal delta |
| `_SAME_LAYER_DELTAS` | `tuple[tuple[int,int], ...]` | 8-direction neighbor offsets in canonical order |
| `octile_distance(a, b)` | `float` | Octile distance: `max(dx,dy) + OCTILE_DIAG * min(dx,dy)` |
| `in_bounds(x, y, w, h)` | `bool` | Bounds check: `0 <= x < w and 0 <= y < h` |

`_SAME_LAYER_DELTAS` order (cardinal first, then diagonals):
```python
((0, 1), (1, 0), (0, -1), (-1, 0),
 (1, 1), (1, -1), (-1, 1), (-1, -1))
```

`in_bounds` takes explicit width/height (not a grid object) to avoid coupling to
any specific grid type.

### How to use

```python
from temper_placer.routing.heuristics import (
    OCTILE_DIAG,
    _SAME_LAYER_DELTAS,
    in_bounds,
    octile_distance,
)

# Instead of: max(dx, dy) + 0.414 * min(dx, dy)
h = octile_distance(current, goal)

# Instead of: 0 <= x < grid.width_cells and 0 <= y < grid.height_cells
if in_bounds(x, y, grid.width_cells, grid.height_cells):
    ...

# Instead of: for dx, dy in [(0,1), (1,0), ...]:
for dx, dy in _SAME_LAYER_DELTAS:
    ...
```

### Numba special case

Numba JIT cannot import Python modules at runtime. The Numba kernel
(`astar_core_numba.py`) gets its own module-level float constant that must
match `OCTILE_DIAG`:

```python
import math
_HEURISTIC_OCTILE_DIAG: float = math.sqrt(2.0) - 1.0
```

A guardrail test asserts parity:
```python
from temper_placer.routing.heuristics import OCTILE_DIAG
from temper_placer.router_v6.astar_core_numba import _HEURISTIC_OCTILE_DIAG
assert abs(OCTILE_DIAG - _HEURISTIC_OCTILE_DIAG) < 1e-12
```

### What was migrated

| File | Before | After |
|------|--------|-------|
| `astar_core.py:174` | `max(dx, dy) + 0.414 * min(dx, dy)` | `octile_distance(a, b)` |
| `astar_core.py:207,344,464,662,664` | `0 <= x < grid.w and 0 <= y < grid.h` | `in_bounds(x, y, grid.w, grid.h)` |
| `astar_core.py:305-314,342,453-462,590` | Inline 8-delta lists | `_SAME_LAYER_DELTAS` |
| `astar_core_numba.py:221,311` | `0.414` literal | `_HEURISTIC_OCTILE_DIAG` |

### What was NOT migrated

- **`_DIRS_8` constant in `astar_core.py`** — serves a different purpose (tensor-indexed
  validity lookup matching `neighbor_validity.DIRS_8`). Its order is `(E, SE, S, SW, W, NW, N, NE)`,
  intentionally different from the neighbor-expansion loop order.
- **`1.414` diagonal move cost in `astar_core_numba.py`** — the move cost
  (`1.4142135` = sqrt(2) for diagonal moves) is distinct from the heuristic delta
  (`0.414` = sqrt(2)-1). Consolidating move cost precision is a separate concern.
- **Polyline length, cell↔world conversion, pad-inflation** — intentional variation
  per site serving different precision/performance tradeoffs.

## Why This Matters

**Before**: A change to the octile formula or neighbor order required edits in
multiple functions within two different files. A precision difference between
`0.414` (hardcoded) and `math.sqrt(2)-1` (~0.4142135) in the Numba kernel could
cause subtle path divergence.

**After**: One edit in `routing/heuristics.py` propagates to both implementations.
The guardrail test catches constant drift between the Python and Numba paths.

## When to Apply

- **When adding a new A* implementation**: import from `routing/heuristics.py`;
  for Numba kernels, define a matching module-level float constant.
- **When you find an inline `0.414` literal or bounds check in the codebase**:
  it's a duplicate — migrate it.
- **When modifying the neighbor search order**: update `_SAME_LAYER_DELTAS` and
  verify the monolith parity test (`test_stage2_monolith_parity`) still passes.

## Examples

### Before (astar_core.py)

```python
def _heuristic(a, b):
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return max(dx, dy) + 0.414 * min(dx, dy)

# ...
for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0),
               (1, 1), (1, -1), (-1, 1), (-1, -1)]:
    nx, ny = cx + dx, cy + dy
    if 0 <= nx < grid.width_cells and 0 <= ny < grid.height_cells:
        ...
```

### After

```python
def _heuristic(a, b):
    return octile_distance(a, b)

# ...
for dx, dy in _SAME_LAYER_DELTAS:
    nx, ny = cx + dx, cy + dy
    if in_bounds(nx, ny, grid.width_cells, grid.height_cells):
        ...
```

## Related Documents

- [Layer Index SSOT](layer-index-ssot-placer-2026-06-23.md)
- [Pad Position SSOT](pad-position-ssot-placer-2026-06-23.md)
- [Net Classification SSOT](net-classification-ssot-placer-2026-06-23.md)
- [A* Primitives Requirements](../../brainstorms/2026-06-24-a-star-primitives-consolidation-requirements.md)
- [A* Primitives Plan](../../plans/2026-06-24-012-refactor-a-star-primitives-consolidation-plan.md)
