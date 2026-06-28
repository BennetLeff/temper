---
date: 2026-06-24
topic: a-star-primitives-consolidation
---

# A* Primitives Consolidation (Doc 4 of 4)

## Summary

Consolidate the A* search primitives — octile distance, 8-direction neighbor deltas, and
bounds check — duplicated across the two remaining A* implementations (`router_v6/astar_core.py`
and `router_v6/astar_core_numba.py`) into a single canonical source in
`routing/heuristics.py`. This is the fourth and final consolidation in the SSOT sequence
(layer names → pad-position → net classification → A* primitives).

## Problem Frame

The placer had multiple A* implementations with duplicated search primitives. The deadcode
commit (`347fc34b`) removed the Cython A* twin, the Python fallback, and three deterministic
A* variants, narrowing the remaining duplication to two files. After the cleanup, the
following primitives are still duplicated:

- **Octile distance** formula `max(dx, dy) + (sqrt(2)-1) * min(dx, dy))` appears in
  `astar_core.py:174` (Python `0.414` literal) and `astar_core_numba.py:221,311`
  (Numba `0.414` literal). A divergence in the constant (0.41429 vs 0.414) or formula
  shape could cause subtle tie-break differences between the Python and Numba paths.
- **Bounds check** `0 <= x < width and 0 <= y < height` is inlined 5 times in
  `astar_core.py` (lines 207, 344, 464, 662, 664) with identical logic.
- **8-direction neighbor table** `[(0,1), (1,0), (0,-1), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]`
  is inlined or loop-generated in both files. The order matters for deterministic
  tie-breaking; a divergence would change path output.

A divergence in this session changed path output and broke the
`test_stage2_monolith_parity` test. Centralizing these primitives prevents that class of bug.

## Requirements

### R1 — Canonical Surface

Add to `routing/heuristics.py`:

- `OCTILE_DIAG: Final[float] = math.sqrt(2.0) - 1.0` — octile diagonal cost delta
- `_SAME_LAYER_DELTAS: tuple[tuple[int, int], ...]` — 8-direction neighbor offsets in
  canonical order: `[(0,1), (1,0), (0,-1), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]`
- `octile_distance(a: tuple[int, int], b: tuple[int, int]) -> float` —
  `max(|dx|, |dy|) + OCTILE_DIAG * min(|dx|, |dy|)`
- `in_bounds(x: int, y: int, width_cells: int, height_cells: int) -> bool` —
  `0 <= x < width_cells and 0 <= y < height_cells`

These are free functions and constants, not a class — matching the existing pattern
(`manhattan_heuristic`, `euclidean_heuristic`, `_HEURISTICS` dict) in `routing/heuristics.py`.

### R2 — Migrate astar_core.py

Replace the 3 duplicated primitives in `router_v6/astar_core.py` with imports from
`routing/heuristics.py`:

- `_heuristic` (line 174): replace the inline `max + 0.414*min` with `octile_distance`
- `in_bounds` checks (lines 207, 344, 464, 662, 664): replace inline
  `0 <= x < grid.width_cells and 0 <= y < grid.height_cells` with `in_bounds(x, y, grid.width_cells, grid.height_cells)`
- Neighbor expansion loops: replace inlined/loop-generated deltas with `_SAME_LAYER_DELTAS`

### R3 — Migrate astar_core_numba.py

Replace the inline octile heuristic in the Numba kernel with the canonical formula using
precomputed float constants. Numba cannot import `routing.heuristics` at JIT time, so the
kernel must reference float values defined in the same module or passed as arguments:

- `_HEURISTIC_OCTILE_DIAG: float = math.sqrt(2.0) - 1.0` — module-level float constant
  in `astar_core_numba.py`, equal to `OCTILE_DIAG` from `routing/heuristics.py`
- `_octile_distance` helper (or inline): `max(dx, dy) + _HEURISTIC_OCTILE_DIAG * min(dx, dy)`
- Replace the `0.414` literal at lines 221 and 311 with `_HEURISTIC_OCTILE_DIAG`

### R4 — Deterministic Parity

The Python path (`astar_core.py`) and Numba path (`astar_core_numba.py`) must produce
identical path outputs after migration. The parity test `test_stage2_monolith_parity`
must continue passing (if it was passing before) or be updated to match the new
deterministic output.

### R5 — No New Imports from heuristics.py into Numba

`routing/heuristics.py` must not depend on `router_v6/astar_core_numba.py` or any
other file that creates a circular import. The canonical surface in `routing/heuristics.py`
is a plain module with no internal imports from `router_v6/`.

## Success Criteria

- `octile_distance("0,0", "3,4")` returns `4.0 + 3.0 * OCTILE_DIAG` (Python: ~5.242)
- `in_bounds(10, 20, 100, 100)` returns `True`; `in_bounds(-1, 0, 10, 10)` returns `False`
- `_SAME_LAYER_DELTAS` has exactly 8 elements in the specified order
- `astar_core.py` no longer contains the `0.414` literal or inline bounds checks
- `astar_core_numba.py` no longer contains the `0.414` literal (replaced by named constant)
- `pytest tests/router_v6/test_astar_pathfinding.py` — 5 passed (same as baseline)
- `pytest tests/router_v6/test_stage2_monolith_parity.py` — parity preserved or documented
- `ruff check` clean on new/changed modules
- Import boundary gate passes (0 new violations)

## Scope Boundaries

### In scope
- `OCTILE_DIAG`, `_SAME_LAYER_DELTAS`, `octile_distance`, `in_bounds` in `routing/heuristics.py`
- Migration of `astar_core.py` and `astar_core_numba.py` to use these primitives
- Tests for the new canonical surface (`tests/routing/test_heuristics.py`)

### Out of scope
- Polyline length, cell↔world conversion, pad-inflation (intentionally different per site;
  variations serve different precision/performance tradeoffs)
- `CongestionLevel.order` property (the level_order dict was in files removed by deadcode
  cleanup; the enum in `iteration_budget.py` remains the SSOT)
- `create_distance_map_heuristic` closure pattern (unchanged, different concept from
  octile/grid primitives)
- 4-direction neighbor generators in `routing/neighbors/generator.py` (different concept)
- World↔grid conversion unification (3 different APIs with different precision needs)

## Key Decisions

1. **Canonical home: `routing/heuristics.py`** — extends the existing heuristic registry
   (`manhattan_heuristic`, `euclidean_heuristic`) with A* primitives. Free functions match
   the existing pattern. No new module needed.

2. **Numba float constant: module-level in `astar_core_numba.py`** — Numba JIT cannot import
   Python modules at runtime. The constant is defined locally and documented as equal to
   `OCTILE_DIAG`. A test asserts they match.

3. **`in_bounds` takes explicit width/height, not a grid object** — avoids coupling
   `routing/heuristics.py` to `router_v6/astar_core.py`'s OccupancyGrid or any specific
   grid type. Callers pass `grid.width_cells, grid.height_cells`.

4. **`_SAME_LAYER_DELTAS` order is the canonical order used in `astar_core.py`** —
   `[(0,1), (1,0), (0,-1), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]`.
   This preserves the existing tie-breaking behavior in the Numba kernel.

5. **Big-bang migration** — matching the D1-D3 pattern. No deprecation window; duplicates
   are wrong today and should be removed in a single atomic commit.

## Dependencies

- Doc 1 (layer names), Doc 2 (pad-position), Doc 3 (net classification) must be shipped
  in main before Doc 4 begins. **All three are shipped** as of this document's creation.

## Outstanding Questions

1. **Deterministic parity**: The `test_stage2_monolith_parity` test was failing at
   baseline (grid mismatch on F.Cu, unrelated to A* primitives). If parity is still
   failing after the consolidation, document the pre-existing status and do not block
   the consolidation on fixing it.
