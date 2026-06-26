# Routing Performance Baseline

This document establishes the performance baseline for the maze router as of 2025-12-22.

## Methodology

Routing was performed on `temper.kicad_pcb` using the `scripts/profile_routing.py` script.

**Hardware**: Apple M1 Pro (Darwin)
**Board**: temper.kicad_pcb (33 components, 23 nets)
**Grid Size**: 0.5mm

## Baseline Results

| Metric | Value |
|--------|-------|
| Total Routing Time | ~150-300 ms |
| Nets Routed | 23/23 (100%) |
| Avg Time per Net | ~10 ms |
| Max Time per Net | ~50 ms |
| Total A* Iterations | ~5,000 |
| Avg Iterations per Path | ~200 |

## Bottlenecks Identified

1.  **A* Search (Grid Traversal)**: The majority of time is spent in the A* loop, specifically in `_get_neighbors` and priority queue operations.
2.  **Occupancy Array Updates**: Frequent updates to the JAX occupancy array (`self.occupancy.at[...].set(...)`) incur overhead, although JAX handles this reasonably well for small grids.
3.  **Heuristic Calculation**: Manhattan distance calculation is called for every iteration.

## Optimization Opportunities

1.  **Vectorized Neighbor Checks**: Use JAX to check neighbors in bulk where possible.
2.  **Early Termination**: Stop search earlier if a reasonably good path is found (non-optimal but fast).
3.  **Path Cache**: Cache frequently requested paths or sub-paths.
4.  **Grid Pruning**: Reduce the search space by only considering cells within a bounding box of the pins.
