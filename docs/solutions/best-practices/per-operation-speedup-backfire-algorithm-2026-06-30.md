---
title: Per-Operation Speedups Can Backfire If They Change Algorithm Behavior
date: 2026-06-30
category: best-practices
module: temper-placer
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - Optimizing sub-operations inside search or optimization algorithms
  - Sub-operation cost changes alter the exploration/expansion frontier
  - The sub-operation is invoked per-edge or per-neighbor in a graph search
tags: [algorithm-optimization, theta-star, jevons-paradox, a-star, performance]
---

# Per-Operation Speedups Can Backfire If They Change Algorithm Behavior

## Context

An LRU cache was added to `_line_of_sight` in `astar_core.py` to avoid
redundant Bresenham ray-casting checks during Theta* A* search. In
isolation, the cache achieved a 69% hit rate and made individual LOS
checks 3× faster. However, the full routing pipeline became 48% **slower**
because Theta* started exploring 4.6× more cells. The cheaper LOS checks
produced lower `g_score` values via shortcuts, which made more cells
competitive on the open set, increasing total expansions dramatically.

This is an instance of **Jevons Paradox** in algorithm design: making a
sub-operation cheaper caused the algorithm to use *more* of it, not less.

## Guidance

Always benchmark the **system-level** impact of an optimization, not just
the sub-operation in isolation. A micro-benchmark that shows a 3× speedup
on a single function is meaningless if the optimization changes how the
surrounding algorithm behaves.

Before committing a sub-operation optimization:

1. **Measure end-to-end throughput** (not just the optimized call site).
2. **Instrument the algorithm's expansion count** or equivalent metric to
   detect whether the optimization is increasing total work.
3. **Suspect feedback loops** when the sub-operation's output influences
   the algorithm's cost model — cheaper operations can lower a barrier
   that was implicitly constraining exploration.
4. **Prefer structural fixes** to caching. In this case, Lazy Theta* (which
   structurally limits LOS to 1 per expansion instead of 8 per neighbor)
   was the correct solution — it prevents the expansion explosion regardless
   of how fast LOS is.

## Why This Matters

Search and optimization algorithms have an implicit *exploration budget*.
The cost of sub-operations is part of what keeps expansion bounded. When
you make a sub-operation cheaper, you lower the barrier that was
constraining the algorithm's appetite. The algorithm doesn't do less
work — it does more.

This pattern is particularly dangerous in:

- **Theta\* and Lazy Theta\***: LOS checks determine whether shortcuts
  are taken. Cheaper LOS → more shortcuts accepted → lower g\_scores →
  more cells on the open set → more expansions.
- **Simulated annealing**: Cheaper neighbor generation can cause the
  algorithm to accept more moves before the temperature drops.
- **BFS/DFS with pruning**: A cheaper pruning predicate can admit more
  states into the frontier.
- **Congestion-aware routing**: In router V6, the congestion-tensor
  mechanism (`astar_core.py:292-294`) already monitors frontier growth;
  the LOS cache effectively defeated this guardrail by making every
  expansion cheaper, delaying plateau detection.

## When to Apply

- When adding a cache, memoization table, or precomputed structure to a
  sub-operation that influences the search frontier or cost model.
- When the sub-operation is called per-neighbor, per-edge, or per-state
  in an exploration loop.
- When the algorithm's expansion count is sensitive to the cost estimates
  produced by the sub-operation.

## Examples

### Before (LRU-cached LOS — made the pipeline 48% slower)

```python
# Hypothetical LRU cache added to _line_of_sight in astar_core.py
from functools import lru_cache

@lru_cache(maxsize=8192)
def _line_of_sight(p1, p2, grid_hash, net_id):
    # Bresenham check with caching
    ...
```

Each Theta* neighbor expansion checked LOS from parent to neighbor (up to
8 per cell expansion), and the cache made those checks cheap. Lower
g\_scores flooded the open set, increasing total expansions 4.6×.

### After (cache removed; Lazy Theta* limits LOS structurally)

```python
# In _astar_search_lazy_theta_star (astar_core.py:297-481):
# LOS is checked only when a node is EXPANDED (1 per expansion),
# not when a neighbor is CONSIDERED (8 per neighbor in classic Theta*).
# This prevents the expansion explosion regardless of LOS speed.

if parent and not los_fn(parent, current, grid, net_id):
    # LOS failed — find valid parent from closed neighbors
    ...
```

Lazy Theta* (`_astar_search_lazy_theta_star` at `astar_core.py:297`) was
already in the codebase. The fix was simply switching from `_astar_search_theta_star`
to `_astar_search_lazy_theta_star` and removing the cache, which structurally
bounds LOS invocations to 1 per cell expansion instead of 8 per neighbor.

## Related

- `astar_core.py:237-289` — `_line_of_sight` (un-cached, with BB shortcut)
- `astar_core.py:297-481` — `_astar_search_lazy_theta_star` (Lazy Theta*)
- `astar_core.py:484-605` — `_astar_search_theta_star` (classic Theta*)
- `astar_core.py:292-294` — congestion derivative tracking constants
- `performance-issues/router-v6-full-pipeline-5min-to-23s-2026-06-23.md` — broader pipeline performance work
