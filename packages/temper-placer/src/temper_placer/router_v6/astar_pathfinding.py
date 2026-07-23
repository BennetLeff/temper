# mypy: ignore-errors
# ruff: noqa: ARG001, F821
"""
Router V6 Stage 4.2: Run A* Pathfinding

Implementation decomposed across internal modules:
- _astar_heuristics.py -- distance, EDT, demand-budget functions
- _astar_ordering.py -- _compute_net_order
- _astar_reconstruct.py -- data types, run_astar_pathfinding, route construction
"""

from __future__ import annotations

from ._astar_heuristics import (
    _build_edt_from_grid,
    _compute_bottleneck_widths,
    compute_demand_budget,
    manhattan_distance,
    min_edt_along_line,
)
from ._astar_ordering import _compute_net_order
from ._astar_reconstruct import (
    _SEGMENT_3D_FALLBACK_MAX_ITER,
    _TREE_SEGMENT_3D_FALLBACK_MAX_ITER,
    PathfindingResult,
    RoutingFailureReport,
    TreeRoutingFailure,
    _astar_route,
    _astar_route_multilayer,
    _astar_route_with_ripup,
    _has_safe_partial_geometry,
    _segment_search,
    run_astar_pathfinding,
)
from .astar_core import RoutePath, RoutePath3D
from .astar_grid import _extract_pad_centers_per_net

PROBLEM_NETS: frozenset[str] = frozenset({"/k02", "/k04", "/k25", "/k24", "/k15"})
_MAX_RIPUP_DEPTH_NORMAL = 15
_MAX_RIPUP_DEPTH_PROBLEM = 30
_MAX_REROUTE_ATTEMPTS_PER_NET = 2

__all__ = [
    "PROBLEM_NETS",
    "PathfindingResult",
    "RoutePath",
    "RoutePath3D",
    "RoutingFailureReport",
    "TreeRoutingFailure",
    "_MAX_REROUTE_ATTEMPTS_PER_NET",
    "_MAX_RIPUP_DEPTH_NORMAL",
    "_MAX_RIPUP_DEPTH_PROBLEM",
    "_SEGMENT_3D_FALLBACK_MAX_ITER",
    "_TREE_SEGMENT_3D_FALLBACK_MAX_ITER",
    "_astar_route",
    "_astar_route_multilayer",
    "_astar_route_with_ripup",
    "_build_edt_from_grid",
    "_compute_bottleneck_widths",
    "_compute_net_order",
    "_extract_pad_centers_per_net",
    "_has_safe_partial_geometry",
    "_segment_search",
    "compute_demand_budget",
    "manhattan_distance",
    "min_edt_along_line",
    "run_astar_pathfinding",
]
