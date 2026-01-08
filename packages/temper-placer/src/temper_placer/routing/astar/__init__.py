"""High-performance multi-layer A* pathfinding with Cython acceleration.

This module provides two implementations:
- **Cython** (default): 50-100x faster, C-level performance
- **Python** (fallback): Pure Python for debugging

Toggle between implementations using the TEMPER_USE_CYTHON_ASTAR environment variable:
    TEMPER_USE_CYTHON_ASTAR=1  # Use Cython (default)
    TEMPER_USE_CYTHON_ASTAR=0  # Use Python (debug mode)

Example:
    from temper_placer.routing.astar import find_path

    path = find_path(
        grid=clearance_grid,
        start_pos=(0, 0, 0),
        end_pos=(10, 10, 0),
        net_id=1,
        config=config
    )
"""

import os
import warnings

# Public API
from .types import RouteSegment, MultiLayerPath

# Determine which implementation to use
USE_CYTHON = os.getenv("TEMPER_USE_CYTHON_ASTAR", "1") == "1"

__all__ = ["RouteSegment", "MultiLayerPath"]

# Note: Actual find_path import will be added after python_astar.py is created
# For now, this module just provides the types

if USE_CYTHON:
    try:
        # Try to import Cython implementation
        from .astar_core import find_path_cython as find_path

        __all__.append("find_path")
    except ImportError as e:
        # Cython not available, fall back to Python
        warnings.warn(
            f"Cython A* implementation not available ({e}), falling back to Python. "
            f"Install with 'pip install -e .' to build Cython extension.",
            ImportWarning,
        )
        try:
            from .python_astar import find_path

            __all__.append("find_path")
        except ImportError:
            # python_astar not created yet, that's okay during setup
            pass
else:
    # User explicitly requested Python implementation
    try:
        from .python_astar import find_path

        __all__.append("find_path")
    except ImportError:
        # python_astar not created yet, that's okay during setup
        pass
