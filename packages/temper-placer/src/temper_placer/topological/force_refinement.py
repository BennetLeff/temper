"""Force-directed position refinement.

This module refines initial positions using force simulation:
- Adjacency constraints create attraction forces
- Separation constraints create repulsion forces
- Zone boundaries create containment forces

The force simulation converges positions toward constraint satisfaction.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

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
    delta = pos_b - pos_a
    distance = np.linalg.norm(delta)

    if distance < 1e-6:
        # Prevent division by zero - apply small separation
        return np.array([0.1, 0.0]), np.array([-0.1, 0.0])

    # Direction from A to B
    direction = delta / distance

    # Force proportional to distance error
    error = distance - target_distance
    force_magnitude = error * 0.5  # Spring constant

    # A is pulled toward B, B is pulled toward A
    force_a = direction * force_magnitude
    force_b = -direction * force_magnitude

    return force_a, force_b


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
    delta = pos_b - pos_a
    distance = np.linalg.norm(delta)

    if distance < 1e-6:
        # Prevent division by zero - apply strong separation
        return np.array([-1.0, 0.0]), np.array([1.0, 0.0])

    # No force if already far enough apart
    if distance >= min_distance:
        return np.zeros(2), np.zeros(2)

    # Direction from A to B
    direction = delta / distance

    # Repulsion force - stronger when closer
    deficit = min_distance - distance
    force_magnitude = deficit * 1.0  # Strong repulsion

    # A pushed away from B, B pushed away from A
    force_a = -direction * force_magnitude
    force_b = direction * force_magnitude

    return force_a, force_b


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

    force = np.zeros(2)

    # Push right if outside left boundary
    if x < x_min:
        force[0] = (x_min - x) * 2.0

    # Push left if outside right boundary
    if x > x_max:
        force[0] = (x_max - x) * 2.0

    # Push up if outside bottom boundary
    if y < y_min:
        force[1] = (y_min - y) * 2.0

    # Push down if outside top boundary
    if y > y_max:
        force[1] = (y_max - y) * 2.0

    return force


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
    positions = positions.copy()
    n = positions.shape[0]

    for _ in range(iterations):
        forces = np.zeros((n, 2))

        # Adjacency forces (attraction)
        for i, j, target in adjacencies:
            force_i, force_j = compute_adjacency_force(positions[i], positions[j], target)
            forces[i] += force_i
            forces[j] += force_j

        # Separation forces (repulsion)
        for i, j, min_dist in separations:
            force_i, force_j = compute_separation_force(positions[i], positions[j], min_dist)
            forces[i] += force_i
            forces[j] += force_j

        # Boundary forces
        for i in range(n):
            zone = Zone(
                name=f"zone_{i}",
                bounds=tuple(zone_bounds[i]),  # type: ignore
            )
            forces[i] += compute_boundary_force(positions[i], zone)

        # Apply forces
        positions += forces * lr

    return positions


def apply_force_refinement(
    positions: dict[str, tuple[float, float]],
    graph: TopologicalGraph,
    zones: dict[str, Zone],
    zone_assignments: dict[str, str],
    iterations: int = 100,
    learning_rate: float = 0.1,
    backend: str = "numpy",
) -> dict[str, tuple[float, float]]:
    """Apply force-directed refinement to positions.

    Args:
        positions: Dict of component ref to (x, y) position
        graph: Topological graph with constraints
        zones: Dict of zone name to Zone
        zone_assignments: Dict of component ref to zone name
        iterations: Number of refinement iterations
        learning_rate: Step size for position updates
        backend: Computation backend ("numpy" or "jax")

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
            zone_bounds[i] = zones[zone_name].bounds
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

    # Run refinement
    if backend == "jax":
        try:
            # JAX backend - for now, fall back to numpy
            # Could implement JIT-compiled version later
            refined = _force_refine_numpy(
                pos_array, adjacencies, separations, zone_bounds, iterations, learning_rate
            )
        except ImportError:
            raise ImportError("JAX not available")
    else:
        refined = _force_refine_numpy(
            pos_array, adjacencies, separations, zone_bounds, iterations, learning_rate
        )

    # Convert back to dict
    return {ref: (float(refined[i, 0]), float(refined[i, 1])) for i, ref in enumerate(refs)}
