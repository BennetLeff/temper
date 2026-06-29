---
title: BFS oracle validates hop count not octile cost — wrong cost model for A* correctness
date: "2026-06-28"
category: best-practices
module: temper_placer
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - "implementing a pathfinding algorithm with non-uniform edge costs (octile, weighted terrain, Euclidean)"
  - "using a reference implementation as a correctness oracle for A* or Dijkstra variants"
  - "validating that a production pathfinder returns optimal-cost paths under its own cost model"
symptoms:
  - "Oracle validates hop count instead of the production pathfinder's actual cost metric"
  - "Bugs in the heuristic or cost function go undetected because the oracle optimizes a different objective"
tags:
  - pathfinding
  - oracle-testing
  - dijkstra
  - astar
  - correctness
  - octile-cost
---

# BFS oracle validates hop count not octile cost — wrong cost model for A* correctness

## Context

The original A* validation design proposed using BFS/Lee's algorithm as a correctness oracle. BFS on an 8-connected grid finds minimum-**hop** paths (all edges weight 1). A* with octile heuristic finds minimum-**octile-cost** paths (cardinal = 1.0, diagonal = √2 ≈ 1.414). These are different optimization objectives. On an obstructed grid, multiple paths can have the same hop count but different octile costs — BFS returns whichever it encounters first, A* returns the cheapest. Agreement between them proves nothing; disagreement may falsely flag a correct A*.

## Guidance

Use a **weighted Dijkstra** oracle on the same cost graph as the production pathfinder. The oracle and production code must share the same edge-cost function. The production result must be within floating-point epsilon of the oracle:

```
dijkstra_cost(start, goal) ≤ production_cost(start, goal) + ε  (lower bound)
production_cost(start, goal) ≤ dijkstra_cost(start, goal) + ε  (optimality)
```

A convenient implementation uses `networkx.algorithms.shortest_paths.weighted.dijkstra_path` with octile edge weights:

```python
SQRT2 = math.sqrt(2.0)
DIAG_COST = SQRT2       # diagonal step = √2
CARD_COST = 1.0         # cardinal step = 1.0

def octile_step_cost(dr: int, dc: int) -> float:
    return DIAG_COST if dr != 0 and dc != 0 else CARD_COST

def dijkstra_shortest_path(start, goal, grid) -> tuple[list, float]:
    """Weighted Dijkstra oracle: finds true minimum-octile-cost path."""
    import networkx as nx
    G = nx.DiGraph()
    for r in range(grid.height_cells):
        for c in range(grid.width_cells):
            if grid.grid[r, c] != 0:
                continue
            for dr, dc in [(0,1),(1,0),(0,-1),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < grid.height_cells and 0 <= nc < grid.width_cells:
                    if grid.grid[nr, nc] == 0:
                        G.add_edge((r, c), (nr, nc), weight=octile_step_cost(dr, dc))
    path = nx.dijkstra_path(G, start, goal, weight="weight")
    cost = nx.dijkstra_path_length(G, start, goal, weight="weight")
    return path, cost
```

## Why This Matters

A mismatched oracle is worse than no oracle — it produces **false confidence**. When A* and BFS agree, there is no guarantee A* is correct (BFS may have found a same-hop path with identical octile cost by coincidence). When they disagree, the user may "fix" a correct A* to match BFS, making the pathfinder *worse*. This class of bug applies to any domain with non-uniform edge costs: octile grids, weighted terrain, navmeshes, time-dependent costs.

## When to Apply

- Edge costs are non-uniform (diagonals, terrain weights, fuel costs)
- You need a ground-truth oracle for A*, Dijkstra, Theta*, or any variant
- An existing BFS oracle is producing false positives/negatives
- You're adding a new cost model to a pathfinder and need to validate it

## Examples

**Before (BFS oracle — wrong):**
```
bfs_hops = len(bfs_path(start, goal)) - 1
astar_cost = sum(octile_cost(step) for step in astar_path(start, goal))
# ↓ meaningless — BFS optimizes hops, not octile cost
assert bfs_hops <= astar_cost / 1.0  # nonsense comparison
```

**After (weighted Dijkstra oracle — correct):**
```
d_path, d_cost = dijkstra_shortest_path(start, goal, grid)
a_path = astar_search(start, goal, grid)
a_cost = sum(octile_cost(step) for step in zip(a_path, a_path[1:]))
# ↓ compare same cost metric
assert d_cost <= a_cost + 1e-6   # lower bound
assert a_cost <= d_cost + 1e-6   # optimality
```

## Related

- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — dual-solver cross-validation pattern
- `docs/solutions/logic-errors/clearance-false-negatives-per-net-pair-2026-06-28.md` — completeness oracle pattern
- `packages/temper-placer/tests/router_v6/astar_oracle_utils.py` — Dijkstra oracle implementation
