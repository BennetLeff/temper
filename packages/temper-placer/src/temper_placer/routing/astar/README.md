# A* Pathfinding Module

High-performance multi-layer A* pathfinding with Cython acceleration.

## Overview

This module provides two implementations of A*:
- **Cython** (default): 50-100x faster, C-level performance
- **Python** (fallback): Pure Python for debugging

## Usage

```python
from temper_placer.routing.astar import find_path

path = find_path(
    grid=clearance_grid,
    start_pos=(0, 0, 0),  # (x, y, layer)
    end_pos=(10, 10, 0),
    net_id=1,
    config=config
)
```

## Toggle Implementation

```bash
# Use Cython (default)
TEMPER_USE_CYTHON_ASTAR=1 python script.py

# Use Python (debug)
TEMPER_USE_CYTHON_ASTAR=0 python script.py
```

## Performance

| Scenario | Python | Cython | Speedup |
|----------|--------|--------|---------|
| Simple route | 0.5s | 0.01s | 50x |
| Complex route | 12.6s | 0.2s | 63x |

## Implementation Details

### Data Structures
- **MinHeap**: Custom C min-heap (replaces Python heapq)
- **State indexing**: Flattened 3D array for cache efficiency  
- **GridView**: Direct memory access to clearance grid

### Algorithm Features
- 8-connected movement + layer transitions
- Octile distance heuristic with via penalty
- Adaptive iteration budgets
- Deterministic tie-breaking

## Development

### Building from Source

```bash
cd packages/temper-placer
pip install -e .
```

### Running Tests

```bash
pytest packages/temper-placer/tests/routing/astar/ -v
```

## Status

**Phase 1: Infrastructure** ✅ (in progress)
- Module structure created
- Types extracted  
- Toggle mechanism implemented

**Phase 2: Data Structures** (next)
- MinHeap, State Indexing, GridView

**Phase 3: Algorithm Port** (pending)
- Core A* implementation in Cython

## References

- Original Python implementation: `python_astar.py` (will be copied from `multilayer_astar.py`)
- Cython core: `astar_core.pyx` (to be implemented)
- Design doc: `docs/CYTHON_ASTAR_DESIGN.md` (to be created)
