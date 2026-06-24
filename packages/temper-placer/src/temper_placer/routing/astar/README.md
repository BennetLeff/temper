# A* Pathfinding Types

Shared type definitions for multi-layer A* pathfinding in the Temper PCB router.

## Overview

This package provides canonical type definitions used by both the legacy
deterministic routing pipeline and the Router V6 pathfinder:

- `RouteSegment` -- a segment of a routed path (start, end, layer)
- `MultiLayerPath` -- result of multi-layer pathfinding (segments, via positions, total cost)

## Usage

```python
from temper_placer.routing.astar import RouteSegment, MultiLayerPath
```

## History

- **Jan 2026**: The Cython A* twin (`astar_core.pyx`) was removed in commit `3314d94a`
  ("Major Cleanup: JAX Removal, Legacy Purge, and Structural Flattening").
  `MultiLayerAStar` switched to its inline pure-Python implementation.

- **Jun 2026**: A* consolidation (8→1 survivor). The deprecated Python fallback
  (`python_astar.py`) and vestigial Cython source files were deleted.
  The active pathfinder lives in `temper_placer.router_v6.astar_pathfinding`.

## Architecture

```
MultiLayerAStar (deterministic/stages/multilayer_astar.py)
  └─> inline pure-Python A* (no external pathfinder dependency)

Router V6 (router_v6/astar_pathfinding.py)
  └─> router_v6/astar_core.py (search kernels)
       └─> router_v6/astar_core_numba.py (Numba acceleration, optional)
```

## Files

- `__init__.py` -- re-exports `RouteSegment`, `MultiLayerPath`
- `types.py` -- shared dataclass definitions
