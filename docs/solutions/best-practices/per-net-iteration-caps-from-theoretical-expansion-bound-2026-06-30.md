---
title: "Derive iteration caps from problem geometry, not empirical tuning"
date: 2026-06-30
category: best-practices
module: router_v6
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - "tuning iteration limits for A* or similar search algorithms"
  - "allocating computational budget proportional to problem difficulty"
  - "replacing a magic-number global constant with a derived per-instance bound"
tags:
  - router-v6
  - a-star
  - iteration-cap
  - theoretical-bound
  - search-algorithms
  - complexity
related_docs:
  - docs/solutions/architecture-patterns/router-v6-closure-rate-100pct-2026-06-24.md
---

# Derive iteration caps from problem geometry, not empirical tuning

## Context

Router V6 used a single global `max_iter` parameter (1,000,000) for all
A* searches. This was an empirically-tuned magic number with no
theoretical justification. Easy nets (e.g., VCC_BOOT, ~2.4mm span)
needed roughly 452 theoretical A* expansions but were allocated 1M
(2,200x waste). Hard nets (e.g., PWM_L, ~84mm span) needed roughly
554K expansions but were capped at 1M. The iteration cap was
simultaneously too high (wasting cycles on easy nets) and too low
(failing hard nets that needed more than 1M in congested regions).

The solution: derive per-net iteration caps from the theoretical A*
expansion bound.

## Guidance

A* with an admissible heuristic expands cells in an ellipse between
start and goal. The number of such cells is approximately:

    π × (span_cells / 2)²

where `span_cells` is the Manhattan distance between start and goal
in grid cells. The per-net cap is:

    min(grid_area, max(1000, π × (span_cells / 2)²))

This is bounded below by 1,000 (trivial nets; avoids zero-budget edge
cases) and above by the total grid area (degenerate worst case). The
global `max_iter` parameter serves as an absolute ceiling.

**Implementation** (`astar_pathfinding.py:351-360`):

```python
# Fallback: derive per-net cap from theoretical expansion bound
per_net_max_iter = max_iter  # global ceiling
waypoints = channel_path.waypoints
if waypoints and len(waypoints) >= 2:
    dx = abs(waypoints[-1][0] - waypoints[0][0])
    dy = abs(waypoints[-1][1] - waypoints[0][1])
    span_cells = int((dx + dy) / primary_grid.cell_size)
    grid_area = primary_grid.width_cells * primary_grid.height_cells
    ellipse_cells = int(math.pi * (span_cells / 2.0) ** 2)
    derived = max(1000, min(ellipse_cells, grid_area))
    per_net_max_iter = min(max_iter, derived)
```

**Before/After on representative nets (temper.kicad_pcb, 0.1mm cell size):**

| Net | Span (mm) | Theoretical cap | Old cap | Ratio |
|-----|-----------|----------------|---------|-------|
| VCC_BOOT | 2.4 | ~2K | 1M | 500:1 waste |
| PWM_L | 84 | ~554K | 1M | 1.8:1 waste |
| I_SENSE | 76 | ~454K | 1M | 2.2:1 waste |

**Companion changes** that completed the picture:

1. Global default reduced from 1M to 500K (`pipeline.py:333`) — the
   empirically-proven sweet spot for the hardest nets on this board
   (see `docs/solutions/architecture-patterns/router-v6-closure-rate-100pct-2026-06-24.md`)
2. Rip-up retries reduced from 5 to 2 (`_MAX_REROUTE_ATTEMPTS_PER_NET = 2`)
   since the cap is now correctly sized per net, reducing the need to
   retry nets that were previously starved

## Why This Matters

**Before**: A single magic number (1M) governed all A* searches.
Easy nets wasted budget, hard nets hit the wall. The number had no
relationship to the problem being solved — it was purely empirical
tuning on one board.

**After**: Each net gets a cap derived from its geometry. The cap is
proportional to the theoretical search space, so hard nets naturally
receive more budget than easy ones without manual tuning. The 1,000
floor avoids degenerate zero-budget cases for trivial nets, and the
grid-area ceiling bounds the worst case.

This transforms the parameter from "tuned on this board" to "derived
from first principles." The same derivation works for any board, any
cell size — no re-tuning needed when the design changes.

## When to Apply

- When an algorithm has a hard iteration cap that is a single constant
  across all inputs of varying sizes
- When you can compute the size of the problem instance in the same
  units as the search space (e.g., cells, states, nodes)
- When the search algorithm's complexity is bounded by a known function
  of the instance size (here: A* with admissible heuristic expands
  O(span²) cells)

## Examples

**Anti-pattern — global magic number:**

```python
# Every net, regardless of span, gets the same cap
max_iter = 1_000_000  # "tuned" empirically, meaning unknown
path = astar_search(start, goal, max_iter=max_iter)
```

**Pattern — geometry-derived per-instance cap:**

```python
span_cells = manhattan_distance(start, goal) // cell_size
# A* with admissible heuristic expands an ellipse area
ellipse_cells = int(math.pi * (span_cells / 2.0) ** 2)
# Floor at 1000 (trivial nets), ceiling at grid area (worst case)
per_instance_cap = max(1000, min(ellipse_cells, grid_area))
path = astar_search(start, goal, max_iter=per_instance_cap)
```

This generalizes to any search algorithm whose expansion volume grows
polynomially with instance size — A* with admissible heuristic,
Dijkstra, weighted A*, etc.

## Related

- `docs/solutions/architecture-patterns/router-v6-closure-rate-100pct-2026-06-24.md` — empirical 500k sweet spot for the global ceiling
- `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py:351-360` — per-net derivation in `attempt_route`
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:333` — global `max_iter` default (500k)
