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

**Microbenchmark (80mm path, 20 runs):**
- Python A*: 3.5ms per path
- Cython A*: 0.086ms per path
- **Speedup: 40x**

**Full Pipeline:**
- With Python A*: >10min (timeout)
- With Cython A*: 85 seconds
- Routing stage: 20.88 seconds (24 nets)

**Key Fix (Jan 2026):**
The heuristic function was multiplying by `cell_size`, returning millimeters while edge costs were in grid cells. This broke A* admissibility and caused 750x more state exploration. After fixing to use grid cell units consistently, state exploration dropped from ~120,000 to ~160 states per path.

## Implementation Details

### Data Structures
- **MinHeap**: Custom C min-heap (replaces Python heapq)
- **State indexing**: Flattened 3D array `(layer * height * width + row * width + col)` for cache efficiency  
- **GridView**: Direct memory access to clearance grid via NumPy arrays

### Algorithm Features
- 8-connected movement (cardinal + diagonal) + layer transitions
- Octile distance heuristic with via cost penalty
- Adaptive iteration budgets (configurable max iterations)
- Deterministic tie-breaking (stable heap ordering)
- Automatic fallback to Python on Cython errors

### Files
- `__init__.py` - Public API with implementation selection
- `types.py` - Shared Python types (RouteSegment, MultiLayerPath)
- `astar_core.pyx` - Cython implementation (684 lines)
- `astar_core.pxd` - Cython header declarations
- `python_astar.py` - Reference Python implementation
- `astar_core.cpp` - Generated C++ code (do not edit)
- `astar_core.*.so` - Compiled Cython extension

## Development

### Building from Source

```bash
cd packages/temper-placer

# Full rebuild (Cythonize + Compile)
python -c "
from Cython.Build import cythonize
from setuptools import Extension
import numpy as np

ext = Extension(
    'temper_placer.routing.astar.astar_core',
    ['src/temper_placer/routing/astar/astar_core.pyx'],
    include_dirs=[np.get_include()],
    language='c++',
    extra_compile_args=['-O3', '-std=c++11'],
)
cythonize([ext], compiler_directives={'language_level': '3', 'boundscheck': False, 'wraparound': False, 'cdivision': True})
"

# Compile C++ to .so
python -c "
import numpy as np, os
cmd = f'''clang++ -O3 -std=c++11 -shared -fPIC \
  -I{np.get_include()} \
  -I/opt/homebrew/opt/python@3.11/Frameworks/Python.framework/Versions/3.11/include/python3.11 \
  src/temper_placer/routing/astar/astar_core.cpp \
  -o src/temper_placer/routing/astar/astar_core.cpython-311-darwin.so \
  -L/opt/homebrew/opt/python@3.11/Frameworks/Python.framework/Versions/3.11/lib -lpython3.11'''
os.system(cmd)
"
```

### Running Tests

```bash
# All A* tests
pytest tests/deterministic/stages/test_astar.py tests/deterministic/test_astar_multilayer.py -v

# With Cython enabled (default)
TEMPER_USE_CYTHON_ASTAR=1 pytest tests/deterministic/stages/test_astar.py -v

# With Python fallback
TEMPER_USE_CYTHON_ASTAR=0 pytest tests/deterministic/stages/test_astar.py -v
```

### Benchmarking

```bash
# Quick benchmark
cd packages/temper-placer
TEMPER_USE_CYTHON_ASTAR=1 python3.11 -c "
import sys, time
sys.path.insert(0, 'src')
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar

grid = ClearanceGrid(100, 100, 0.5, 4)
astar = MultiLayerAStar(grid=grid, net_name='test', via_cost=5.0)

t0 = time.perf_counter()
for _ in range(20):
    astar.find_path((10.0, 10.0), (90.0, 90.0), 0, -1)
print(f'Cython: {(time.perf_counter()-t0)/20*1000:.3f}ms per path')
"
```

## Status

**Phase 1: Infrastructure** ✅ Complete
- Module structure created
- Types extracted  
- Toggle mechanism implemented

**Phase 2: Data Structures** ✅ Complete
- MinHeap with priority queue operations
- State indexing for 3D grid
- GridView for direct memory access

**Phase 3: Algorithm Port** ✅ Complete
- Core A* implementation in Cython
- Heuristic bug fixed (grid cells vs mm)
- 40x speedup achieved

**Phase 4: Integration** ✅ Complete
- MultiLayerAStar uses Cython by default
- Automatic Python fallback on errors
- All 11 tests pass

**Phase 5: Performance Validation** ✅ Complete
- Microbenchmark: 40x speedup confirmed
- Full pipeline: 85s (was >10min timeout)
- Routing stage: 20.88s (24 nets)

**Phase 6: Documentation** ✅ Complete
- This README updated with real performance data
- Code comments added
- Build instructions documented

## Known Issues & Future Work

1. **DRC validation bottleneck**: Many paths rejected for clearance violations. The A* is now fast but DRC checking is slow.

2. **Power net routing**: +5V net takes 17.82s alone (85% of routing time) due to many pins and high DRC rejection rate.

3. **Single-layer A***: The `DeterministicAStar` class (single-layer fallback) is still pure Python. Could be Cythonized for additional speedup.

4. **Vectorized neighbor checking**: Could batch-check all 8 neighbors at once using NumPy for further speedup.

## Architecture Notes

### Integration Points

```
SequentialRoutingStage
  └─> MultiLayerAStar.find_path()
       └─> routing.astar.find_path()
            ├─> astar_core.find_path_cython() [Cython, default]
            └─> python_astar.find_path_python() [fallback]
```

### Environment Variable Toggle

The `__init__.py` checks `TEMPER_USE_CYTHON_ASTAR` at module import time:
- `1` or `true` or `yes` → Use Cython (default)
- `0` or `false` or `no` → Use Python
- Import errors automatically fall back to Python with warning

## References

- Original Python implementation: `python_astar.py`
- Cython core: `astar_core.pyx` (684 lines)
- Integration: `packages/temper-placer/src/temper_placer/deterministic/stages/multilayer_astar.py`
- Tests: `tests/deterministic/stages/test_astar.py`, `tests/deterministic/test_astar_multilayer.py`
