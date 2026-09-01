"""Force-directed position refinement.

This module refines initial positions using force simulation:
- Adjacency constraints create attraction forces
- Separation constraints create repulsion forces
- Zone boundaries create containment forces

The force simulation converges positions toward constraint satisfaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

import numpy as np

Array: TypeAlias = np.ndarray

if TYPE_CHECKING:
    from numpy.typing import NDArray
else:
    NDArray = np.ndarray

import temper_geometry as _rust

from temper_placer.core.board import Zone
from temper_placer.topological.graph import TopologicalGraph


def compute_adjacency_force(
    pos_a: NDArray[np.float64],
    pos_b: NDArray[np.float64],
    target_distance: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Compute attraction/repulsion force for adjacency constraint.

    If components are farther than target, they attract.
    If closer than target, they repel.

    Args:
        pos_a: Position of component A as [x, y]
        pos_b: Position of component B as [x, y]
        target_distance: Desired distance between components

    Returns:
        Tuple of (force_a, force_b) as numpy arrays
    """
    force_a, force_b = _rust.adjacency_force(
        (float(pos_a[0]), float(pos_a[1])),
        (float(pos_b[0]), float(pos_b[1])),
        target_distance,
    )
    return np.array(force_a), np.array(force_b)


def compute_separation_force(
    pos_a: NDArray[np.float64],
    pos_b: NDArray[np.float64],
    min_distance: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Compute repulsion force for separation constraint.

    Force only applies when components are closer than min_distance.

    Args:
        pos_a: Position of component A as [x, y]
        pos_b: Position of component B as [x, y]
        min_distance: Minimum required distance

    Returns:
        Tuple of (force_a, force_b) as numpy arrays
    """
    force_a, force_b = _rust.separation_force(
        (float(pos_a[0]), float(pos_a[1])),
        (float(pos_b[0]), float(pos_b[1])),
        min_distance,
    )
    return np.array(force_a), np.array(force_b)


def compute_boundary_force(
    position: NDArray[np.float64],
    zone: Zone,
) -> NDArray[np.float64]:
    """Compute force pushing component back into zone.

    Only applies when component is outside zone boundaries.

    Args:
        position: Component position as [x, y]
        zone: Zone to contain component

    Returns:
        Force vector as numpy array
    """
    x, y = position
    x_min, y_min, x_max, y_max = zone.bounds

    return np.array(
        _rust.boundary_force(
            (float(x), float(y)),
            (float(x_min), float(y_min), float(x_max), float(y_max)),
        )
    )


def _force_refine_numpy(
    positions: NDArray[np.float64],
    adjacencies: list[tuple[int, int, float]],
    separations: list[tuple[int, int, float]],
    zone_bounds: NDArray[np.float64],
    iterations: int,
    lr: float,
) -> NDArray[np.float64]:
    """NumPy implementation of force refinement.

    Args:
        positions: (N, 2) array of positions
        adjacencies: List of (i, j, target_distance) tuples
        separations: List of (i, j, min_distance) tuples
        zone_bounds: (N, 4) array of zone bounds per component
        iterations: Number of iterations
        lr: Learning rate

    Returns:
        Refined positions as (N, 2) array
    """
    refined = _rust.force_refine(
        [(float(x), float(y)) for x, y in positions],
        [(int(i), int(j), float(d)) for i, j, d in adjacencies],
        [(int(i), int(j), float(d)) for i, j, d in separations],
        [tuple(float(v) for v in row) for row in zone_bounds],
        iterations,
        lr,
    )
    return np.array(refined, dtype=np.float64).reshape(positions.shape)


def apply_force_refinement(
    positions: dict[str, tuple[float, float]],
    graph: TopologicalGraph,
    zones: dict[str, Zone],
    zone_assignments: dict[str, str],
    iterations: int = 100,
    learning_rate: float = 0.1,
) -> dict[str, tuple[float, float]]:
    """Apply force-directed refinement to positions.

    Args:
        positions: Dict of component ref to (x, y) position
        graph: Topological graph with constraints
        zones: Dict of zone name to Zone
        zone_assignments: Dict of component ref to zone name
        iterations: Number of refinement iterations
        learning_rate: Step size for position updates

    Returns:
        Refined positions dict
    """
    if not positions:
        return {}

    if iterations == 0:
        return dict(positions)

    # Build index mapping
    refs = sorted(positions.keys())
    ref_to_idx = {ref: i for i, ref in enumerate(refs)}
    n = len(refs)

    # Convert positions to array
    pos_array = np.array([positions[ref] for ref in refs])

    # Build zone bounds array
    zone_bounds = np.zeros((n, 4))
    for i, ref in enumerate(refs):
        zone_name = zone_assignments.get(ref, "")
        if zone_name in zones:
            # zones[zone_name].bounds is typed Rect | tuple[float, ...]:
            # Rect implements __len__/__getitem__/__iter__ and is a documented
            # drop-in for the legacy tuple (core/board.py), but its __getitem__
            # only accepts int, not slice, so it doesn't structurally satisfy
            # numpy's ndarray.__setitem__ Sequence protocol. Coercing to a
            # plain tuple here is a type-boundary conversion, not a behavior
            # change -- Rect unpacks to the identical 4 floats either way.
            zone_bounds[i] = tuple(zones[zone_name].bounds)
        else:
            # Default to large bounds if zone not found
            zone_bounds[i] = [-1000, -1000, 1000, 1000]

    # Extract constraints using graph's internal networkx graph
    adjacencies: list[tuple[int, int, float]] = []
    separations: list[tuple[int, int, float]] = []

    for u, v, data in graph.graph.edges(data=True):
        src_idx = ref_to_idx.get(u)
        tgt_idx = ref_to_idx.get(v)

        if src_idx is None or tgt_idx is None:
            continue

        edge_type = data.get("edge_type")
        if edge_type == "adjacent":
            target_dist = data.get("distance", 10.0)
            adjacencies.append((src_idx, tgt_idx, target_dist))
        elif edge_type == "separated":
            min_dist = data.get("distance", 20.0)
            separations.append((src_idx, tgt_idx, min_dist))

    # Run refinement through the Rust-backed NumPy-compatible kernel.
    refined = _force_refine_numpy(
        pos_array, adjacencies, separations, zone_bounds, iterations, learning_rate
    )

    # Convert back to dict
    return {ref: (float(refined[i, 0]), float(refined[i, 1])) for i, ref in enumerate(refs)}
