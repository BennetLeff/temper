"""Shared types for multi-layer A* pathfinding.

This package provides the canonical type definitions (RouteSegment,
MultiLayerPath) used by both the legacy deterministic routing pipeline
and the Router V6 pathfinder.

The find_path function was removed in June 2026 as part of the
A* consolidation (8→1 survivor).  The Cython implementation
(astar_core.pyx) and its Python fallback (python_astar.py)
were deleted; the active pathfinder lives in
temper_placer.router_v6.astar_pathfinding.
"""

from .types import MultiLayerPath, RouteSegment

__all__ = ["RouteSegment", "MultiLayerPath"]
