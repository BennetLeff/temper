---
date: 2026-06-24
plan_id: 012
topic: a-star-primitives-consolidation
req_doc: docs/brainstorms/2026-06-24-a-star-primitives-consolidation-requirements.md
status: awaiting-implementation
---

# A* Primitives Consolidation Plan (Doc 4 of 4)

## Intent

Consolidate the three duplicated A* search primitives — octile distance, bounds check,
and 8-direction neighbor deltas — into `routing/heuristics.py` as free functions and
constants. Migrate the two remaining A* implementations (`router_v6/astar_core.py` and
`router_v6/astar_core_numba.py`) to use them.

## Scoping Summary

After the deadcode cleanup (commit `347fc34b`), only two A* implementations remain in
the placer. The consolidation covers:

- **Octile distance**: `max(dx, dy) + 0.414 * min(dx, dy)` in `astar_core.py:174` and
  `astar_core_numba.py:221,311` → replaced by `octile_distance()` and `OCTILE_DIAG`.
- **Bounds check**: `0 <= x < width and 0 <= y < height` inlined 5 times in
  `astar_core.py` → replaced by `in_bounds(x, y, w, h)`.
- **Neighbor deltas**: inline/list-comp 8-direction offsets → replaced by
  `_SAME_LAYER_DELTAS` in neighbor-expansion loops.

**Not in scope:**
- The `1.414` diagonal move *cost* literal — distinct from the `0.414` heuristic constant.
  Consolidating move cost precision is a separate concern.
- The `_DIRS_8` constant in `astar_core.py` — it serves a tensor-indexing purpose matching
  `neighbor_validity.DIRS_8`. It is NOT replaced by `_SAME_LAYER_DELTAS`.
- Polyline length, cell↔world conversion, pad-inflation (intentional variation per site).

## Implementation Units

### U1 — Canonical Surface in `routing/heuristics.py`

Add four items to `routing/heuristics.py`:

```python
import math
from typing import Final

OCTILE_DIAG: Final[float] = math.sqrt(2.0) - 1.0  # ≈ 0.4142135

_SAME_LAYER_DELTAS: tuple[tuple[int, int], ...] = (
    (0, 1),   # up
    (1, 0),   # right
    (0, -1),  # down
    (-1, 0),  # left
    (1, 1),   # up-right
    (1, -1),  # down-right
    (-1, 1),  # up-left
    (-1, -1), # down-left
)


def octile_distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Octile distance heuristic for 8-connected grid search."""
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return max(dx, dy) + OCTILE_DIAG * min(dx, dy)


def in_bounds(x: int, y: int, width_cells: int, height_cells: int) -> bool:
    """Check if grid cell coordinates are within bounds."""
    return 0 <= x < width_cells and 0 <= y < height_cells
```

**Design decisions:**

- `OCTILE_DIAG` uses `math.sqrt(2.0) - 1.0` (not hardcoded `0.414`) for precision parity
  with the Numba kernel's `1.4142135` move cost.
- `in_bounds` takes explicit width/height, not a grid object — avoids coupling to any
  specific grid type.
- `_SAME_LAYER_DELTAS` uses the canonical order from `astar_core.py`'s inline lists.
  The `_DIRS_8` constant keeps its tensor-matching order (different purpose).

**Tests:** Add `tests/routing/test_astar_primitives.py` covering:
- `octile_distance` on known grid points (0,0)→(3,4), (0,0)→(0,0), (5,0)→(0,5)
- `in_bounds` edge cases: in-bounds, at-origin, at-edge, one-past-edge on both axes
- `_SAME_LAYER_DELTAS` has exactly 8 entries and matches expected order
- `OCTILE_DIAG` precision test: `abs(OCTILE_DIAG - (math.sqrt(2) - 1)) < 1e-12`

### U2 — Migrate `router_v6/astar_core.py`

Replace 3 duplicated primitives with canonical imports:

1. **`_heuristic` function (line 174):** Replace `max(dx, dy) + 0.414 * min(dx, dy)` with
   `octile_distance(a, b)`.

2. **Bounds checks (lines 207, 344, 464, 662, 664):** Replace each inline
   `0 <= nx < grid.width_cells and 0 <= ny < grid.height_cells` with
   `in_bounds(nx, ny, grid.width_cells, grid.height_cells)`.

3. **Neighbor expansion loops (lines ~195-200, ~332-340, ~452-462):** Replace inlined
   or loop-generated deltas with `_SAME_LAYER_DELTAS`. Example:

   ```python
   # Before (inline list):
   for dx, dy in [(0,1), (1,0), (0,-1), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]:

   # After (canonical):
   for dx, dy in _SAME_LAYER_DELTAS:
   ```

   The `_DIRS_8` constant at the top of the file stays unchanged — it serves a different
   purpose (tensor-indexed validity lookup matching `neighbor_validity.DIRS_8`).

**Import:**
```python
from temper_placer.routing.heuristics import (
    OCTILE_DIAG,
    _SAME_LAYER_DELTAS,
    in_bounds,
    octile_distance,
)
```

### U3 — Migrate `router_v6/astar_core_numba.py`

Replace the inline `0.414` literal with a named float constant:

1. Add a module-level constant **before the Numba JIT functions**:
   ```python
   import math
   _HEURISTIC_OCTILE_DIAG: float = math.sqrt(2.0) - 1.0
   ```

2. Replace `0.414` at line 221 (`heuristic_start`) and line 311 (neighbor heuristic):
   ```python
   # Before:
   h = np.float32(max(gdx, gdy) + 0.414 * min(gdx, gdy))
   # After:
   h = np.float32(max(gdx, gdy) + _HEURISTIC_OCTILE_DIAG * min(gdx, gdy))
   ```

3. **Numba constraint:** Numba JIT cannot import Python modules at JIT time, so the
   constant must be defined in the same module. Add a guardrail test in U4:

   ```python
   from temper_placer.routing.heuristics import OCTILE_DIAG
   from temper_placer.router_v6.astar_core_numba import _HEURISTIC_OCTILE_DIAG
   assert abs(OCTILE_DIAG - _HEURISTIC_OCTILE_DIAG) < 1e-12
   ```

**Out of scope for U3:** The `1.414` diagonal move cost literal in the Numba kernel
(lines using `1.4142135`) stays unchanged. That is the move cost, not the heuristic
constant. Consolidating move cost precision is a separate concern.

### U4 — Validation

1. **Unit tests:** `pytest tests/routing/test_astar_primitives.py` — new tests for U1
2. **Regression:** `pytest tests/router_v6/test_astar_pathfinding.py` — 5 passed (same as baseline)
3. **Parity:** `pytest tests/router_v6/test_stage2_monolith_parity.py` — document pre-existing
   failure (grid mismatch on F.Cu, unrelated to A* primitives)
4. **Constant parity:** assert `OCTILE_DIAG == _HEURISTIC_OCTILE_DIAG` within 1e-12
5. **Lint:** `ruff check` clean on changed modules
6. **Import gate:** `python3 scripts/import_linter_gate.py` — 0 new violations

## Reviews

- correctness (R4 deterministic parity)
- testing (U4 validation matrix)
- maintainability (duplicate removal, clear API)
- keiran-python (Python module additions)
- project-standards (AGENTS.md import-boundary rules)

## References

- Requirements: `docs/brainstorms/2026-06-24-a-star-primitives-consolidation-requirements.md`
- Scope note: `docs/brainstorms/2026-06-23-a-star-primitives-consolidation-scope-note.md`
- Affected files: `routing/heuristics.py`, `router_v6/astar_core.py`, `router_v6/astar_core_numba.py`
