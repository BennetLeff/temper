"""
Commutation-loop area computation from routed PCB traces.

Compute the area (mm²) of the closed polygon formed by the commutation
loop traces: DC_BUS+ → Q1 collector → Q1 emitter → SW_NODE →
Q2 emitter → Q2 collector → DC_BUS−.

The primary entry point is :func:`commutation_loop_area`, which accepts
a path to a routed ``.kicad_pcb`` file.  Internally it uses
:func:`auto_extract_loops` for topology and the shoelace formula on the
routed trace graph for the true enclosed-polygon area.  When the trace
graph does not produce a closable cycle, the convex-hull area is used
as a conservative fallback.

.. note::

   The convex-hull fallback is an over-estimate.  A tight non-convex
   loop whose true area is under the threshold may still pass under the
   hull proxy, but the *actual* gate check (U5) uses the shoelace area
   when available (see plan requirement R1).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import numpy as np

if TYPE_CHECKING:
    import networkx as nx


class MeasurementError(Exception):
    """Raised when area measurement cannot be performed."""


class _TraceLike(Protocol):
    """Minimal trace interface accepted by the area helpers."""

    start: tuple[float, float]
    end: tuple[float, float]
    net: str | None


def commutation_loop_area(routed_pcb_path: Path) -> float | None:
    """Compute the area (mm²) of the closed polygon formed by the
    commutation loop traces: DC_BUS+ → Q1 collector → Q1 emitter →
    SW_NODE → Q2 emitter → Q2 collector → DC_BUS−.

    Returns None if trace extraction fails (gate returns UNMEASURED).
    """
    try:
        from temper_placer.core.loop import LoopType
        from temper_placer.core.loop_extractor import auto_extract_loops
        from temper_placer.io.kicad_parser import parse_kicad_pcb
    except ImportError:
        return None

    try:
        result = parse_kicad_pcb(routed_pcb_path)
    except Exception:
        return None

    netlist = result.netlist
    trace_data: list[_TraceLike] = list(result.traces)

    try:
        loops = auto_extract_loops(netlist)
    except Exception:
        return None

    comm_loops = loops.get_loops_by_type(LoopType.COMMUTATION)
    if not comm_loops:
        return None

    loop = comm_loops[0]
    net_names: set[str] = set(loop.nets)

    loop_traces = [t for t in trace_data if t.net in net_names]
    return _compute_area_from_traces(loop_traces)


def _compute_area_from_traces(traces: Sequence[_TraceLike]) -> float | None:
    """Compute enclosed area from a collection of routed trace segments.

    Builds a graph from trace endpoints, finds the main cycle, and
    applies the shoelace formula.  Falls back to convex-hull area when
    the cycle is not closable or fewer than 3 unique points exist.

    Returns:
        Area in mm², or None when no measurable geometry is present.
    """
    if not traces:
        return None

    points_set: set[tuple[float, float]] = set()
    for t in traces:
        points_set.add((round(t.start[0], 3), round(t.start[1], 3)))
        points_set.add((round(t.end[0], 3), round(t.end[1], 3)))

    if len(points_set) < 3:
        return None

    import networkx as nx

    G = _build_trace_graph(traces)

    if G.number_of_nodes() == 0:
        return None

    largest_cc = max(nx.connected_components(G), key=len)
    subgraph = G.subgraph(largest_cc).copy()

    cycle = _find_main_cycle(subgraph)
    if cycle is not None and len(cycle) >= 3:
        return _shoelace_area(np.array(cycle, dtype=np.float64))

    pts_list = list(largest_cc)
    if len(pts_list) >= 3:
        return _convex_hull_area(pts_list)

    return None


def _build_trace_graph(
    traces: Sequence[_TraceLike],
) -> nx.Graph:
    """Build an undirected graph where nodes are unique trace endpoints.

    Edges represent trace segments.  Coordinates are rounded to 3 decimal
    places (1 µm) to account for floating-point noise in KiCad output.
    """
    import networkx as nx

    G: nx.Graph = nx.Graph()
    for t in traces:
        u = (round(t.start[0], 3), round(t.start[1], 3))
        v = (round(t.end[0], 3), round(t.end[1], 3))
        if u == v:
            continue
        length = math.hypot(v[0] - u[0], v[1] - u[1])
        G.add_edge(u, v, weight=length)
    return G


def _find_main_cycle(
    graph: nx.Graph,
) -> list[tuple[float, float]] | None:
    """Find and order the longest cycle in *graph*.

    Uses ``nx.cycle_basis`` (undirected cycle space basis) and picks the
    longest cycle.  The vertices are then ordered so that sequential
    vertices are adjacent in the graph.

    Returns:
        Ordered list of (x, y) vertices forming a closed loop, or None
        when no cycle exists.
    """
    import networkx as _nx

    cycles: list[list] = list(_nx.cycle_basis(graph))
    if not cycles:
        return None

    longest_cycle: list = max(cycles, key=len)
    if len(longest_cycle) < 3:
        return None

    return _order_cycle_vertices(graph, longest_cycle)


def _order_cycle_vertices(
    graph: nx.Graph,
    cycle_vertices: list,
) -> list[tuple[float, float]]:
    """Produce an ordered walk around *cycle_vertices*.

    Starting at the first vertex the function greedily walks to the
    next cycle-vertex that is adjacent in *graph* and has not yet been
    visited.  The walk stops when all cycle vertices are visited or
    no unvisited neighbour remains.
    """
    if len(cycle_vertices) < 3:
        return list(cycle_vertices)

    cycle_set: set = set(cycle_vertices)

    start: tuple = cycle_vertices[0]
    ordered: list[tuple[float, float]] = [start]
    visited: set[tuple[float, float]] = {start}
    current: tuple[float, float] = start

    while len(visited) < len(cycle_set):
        next_v: tuple[float, float] | None = None
        for n in graph.neighbors(current):
            n_tuple: tuple[float, float] = (float(n[0]), float(n[1]))
            if n_tuple in cycle_set and n_tuple not in visited:
                next_v = n_tuple
                break
        if next_v is None:
            break
        ordered.append(next_v)
        visited.add(next_v)
        current = next_v

    return ordered


def _shoelace_area(vertices: np.ndarray) -> float:
    """Compute the signed polygon area via the shoelace formula.

    Args:
        vertices: (N, 2) array of (x, y) coordinates.

    Returns:
        Absolute area in mm².
    """
    x = vertices[:, 0]
    y = vertices[:, 1]
    area = 0.5 * abs(float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))
    return area


def _convex_hull_area(points: list[tuple[float, float]]) -> float:
    """Compute convex-hull area as a conservative upper-bound proxy.

    Used as the fallback when the true routed polygon cannot be formed
    (e.g. trace graph contains spurs that prevent cycle detection).
    """
    from scipy.spatial import ConvexHull

    pts = np.array(points, dtype=np.float64)
    try:
        hull = ConvexHull(pts)
        return float(hull.volume)
    except Exception:
        return 0.0
