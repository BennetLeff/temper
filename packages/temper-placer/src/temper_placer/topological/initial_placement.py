"""Initial placement generation from topological analysis.

This module generates initial (x, y) coordinates from topological relationships
(zone assignments, adjacency clusters) to provide a good starting point for
geometric optimization.

Key functions:
- generate_initial_placement: Main entry point
- place_components_in_zone: Place components in circular arrangement
- identify_clusters: Find connected components via adjacency
- place_cluster: Position a cluster within a zone
"""

from __future__ import annotations

import math  # noqa: F401 -- re-exported trig constants kept for API compatibility
from dataclasses import dataclass, field

import temper_placement_topology as _rust

from temper_placer.core.board import Zone
from temper_placer.topological.graph import TopologicalGraph
from temper_placer.topological.zone_solver import ZoneAssignment


class PlacementError(Exception):
    """Error during initial placement generation."""

    pass


@dataclass
class InitialPlacement:
    """Result of initial placement generation.

    Attributes:
        positions: Map of component ref to (x, y) center position
        zone_assignments: Map of component ref to zone name
        clusters: List of component clusters (sets of refs)
        rotation_hints: Optional rotation suggestions (0, 90, 180, 270)
        warnings: Non-fatal warnings during placement
    """

    positions: dict[str, tuple[float, float]]
    zone_assignments: dict[str, str]
    clusters: list[set[str]]
    rotation_hints: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def place_components_in_zone(
    zone: Zone,
    components: list[str],
    component_sizes: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    """Place components in circular arrangement within a zone.

    Components are arranged in a circle around the zone center,
    leaving room for force-directed refinement.

    Args:
        zone: Zone to place components in
        components: List of component refs to place
        component_sizes: Map of component ref to (width, height)

    Returns:
        Dict mapping component ref to (x, y) position

    Raises:
        PlacementError: If zone is too small for components
    """
    if not components:
        return {}

    bounds = tuple(float(v) for v in zone.bounds)
    sizes = [(float(component_sizes[ref][0]), float(component_sizes[ref][1])) for ref in components]

    outcome = _rust.place_components_in_zone(bounds, sizes)

    # Error text is rendered here, not in Rust: the messages interpolate
    # floats with `{:.1f}` and CPython's own formatting is what the callers
    # and the pinned oracle assert against.
    if outcome[0] == "component_too_large":
        _, idx, zone_width, zone_height = outcome
        ref = components[idx]
        w, h = component_sizes[ref]
        raise PlacementError(
            f"Zone '{zone.name}' is too small for component '{ref}' "
            f"(zone: {zone_width:.1f}x{zone_height:.1f}mm, "
            f"component: {w:.1f}x{h:.1f}mm)"
        )
    if outcome[0] == "zone_too_small":
        _, total_area, zone_area = outcome
        raise PlacementError(
            f"Zone '{zone.name}' is too small to fit {len(components)} components "
            f"(total area: {total_area:.1f}mm², zone area: {zone_area:.1f}mm²)"
        )

    return {ref: tuple(pos) for ref, pos in zip(components, outcome[1], strict=True)}


def identify_clusters(
    graph: TopologicalGraph,
    components: list[str],
) -> list[set[str]]:
    """Identify clusters of adjacent components.

    Uses union-find to group components connected by adjacency constraints.
    Separation constraints do NOT create clusters.

    Args:
        graph: Topological graph with adjacency/separation edges
        components: List of component refs to cluster

    Returns:
        List of clusters (sets of component refs)
    """
    if not components:
        return []

    # Index adjacency edges against the component list, in graph order.
    index_of = {c: i for i, c in enumerate(components)}
    adjacent = [
        (index_of[u], index_of[v])
        for u, v, data in graph.graph.edges(data=True)
        if data.get("edge_type") == "adjacent" and u in index_of and v in index_of
    ]

    return [
        {components[i] for i in cluster}
        for cluster in _rust.identify_clusters(list(components), adjacent)
    ]


def place_cluster(
    cluster: set[str],
    zone: Zone,
    graph: TopologicalGraph,
    component_sizes: dict[str, tuple[float, float]],
    cluster_index: int,
    total_clusters: int,
) -> dict[str, tuple[float, float]]:
    """Place a cluster of components within a zone.

    Adjacent components are placed close together. Multiple clusters
    are given separate regions within the zone.

    Args:
        cluster: Set of component refs in this cluster
        zone: Zone to place cluster in
        graph: Topological graph for adjacency info
        component_sizes: Map of component ref to (width, height)
        cluster_index: Index of this cluster (0-based)
        total_clusters: Total number of clusters in zone

    Returns:
        Dict mapping component ref to (x, y) position
    """
    if not cluster:
        return {}

    components = sorted(cluster)  # Deterministic ordering

    # Tightest adjacency constraint inside the cluster (a min-reduction, so
    # order-invariant; NaN never displaces the incumbent, as in Python).
    min_adjacency_dist = 15.0  # Default
    for u, v, data in graph.graph.edges(data=True):
        if data.get("edge_type") == "adjacent" and u in cluster and v in cluster:
            dist = data.get("distance", 15.0)
            if dist < min_adjacency_dist:
                min_adjacency_dist = dist

    positions = _rust.place_cluster(
        tuple(float(v) for v in zone.bounds),
        [(float(component_sizes[r][0]), float(component_sizes[r][1])) for r in components],
        float(min_adjacency_dist),
        cluster_index,
        total_clusters,
    )
    return {ref: tuple(pos) for ref, pos in zip(components, positions, strict=True)}


def generate_initial_placement(
    graph: TopologicalGraph,
    zone_assignment: ZoneAssignment,
    zones: list[Zone],
    component_sizes: dict[str, tuple[float, float]],
    board_bounds: tuple[float, float, float, float] | None = None,
    force_iterations: int = 100,
    backend: str = "numpy",
) -> InitialPlacement:
    """Generate initial placement from topological analysis.

    This is the main entry point for initial placement generation.
    It combines zone assignments, cluster identification, and
    force-directed refinement.

    Args:
        graph: Topological graph with components and constraints
        zone_assignment: Zone assignments from ZoneSolver
        zones: List of available zones
        component_sizes: Map of component ref to (width, height)
        board_bounds: Optional fallback bounds if no zones
        force_iterations: Number of force refinement iterations
        backend: Computation backend ("numpy" or "jax")

    Returns:
        InitialPlacement with positions, clusters, etc.

    Raises:
        PlacementError: If placement is impossible
    """
    # Check for conflicts
    if zone_assignment.conflicts:
        conflict_desc = "; ".join(f"{c[0]}: {c[2]}" for c in zone_assignment.conflicts)
        raise PlacementError(f"Zone assignment has conflicts: {conflict_desc}")

    # Check for unassigned components
    if zone_assignment.unassigned:
        raise PlacementError(f"Components not assigned to zones: {zone_assignment.unassigned}")

    # Handle empty case
    if not zone_assignment.assignments:
        return InitialPlacement(
            positions={},
            zone_assignments={},
            clusters=[],
        )

    # Build zone lookup
    zone_map = {z.name: z for z in zones}

    # Handle _BOARD_ pseudo-zone
    if board_bounds is not None:
        zone_map["_BOARD_"] = Zone(
            name="_BOARD_",
            bounds=board_bounds,
        )

    # Validate all assigned zones exist
    for ref, zone_name in zone_assignment.assignments.items():
        if zone_name not in zone_map:
            raise PlacementError(f"Zone '{zone_name}' not found for component '{ref}'")

    # Group components by zone
    components_by_zone: dict[str, list[str]] = {}
    for ref, zone_name in zone_assignment.assignments.items():
        if zone_name not in components_by_zone:
            components_by_zone[zone_name] = []
        components_by_zone[zone_name].append(ref)

    # Generate initial positions per zone
    all_positions: dict[str, tuple[float, float]] = {}
    all_clusters: list[set[str]] = []

    for zone_name, component_refs in components_by_zone.items():
        zone = zone_map[zone_name]

        # Identify clusters within this zone
        zone_clusters = identify_clusters(graph, component_refs)
        all_clusters.extend(zone_clusters)

        # Place each cluster
        for i, cluster in enumerate(zone_clusters):
            cluster_positions = place_cluster(
                cluster=cluster,
                zone=zone,
                graph=graph,
                component_sizes=component_sizes,
                cluster_index=i,
                total_clusters=len(zone_clusters),
            )
            all_positions.update(cluster_positions)

    # Apply force-directed refinement
    if force_iterations > 0:
        from temper_placer.topological.force_refinement import apply_force_refinement

        all_positions = apply_force_refinement(
            positions=all_positions,
            graph=graph,
            zones=zone_map,
            zone_assignments=dict(zone_assignment.assignments),
            iterations=force_iterations,
            learning_rate=0.1,
            backend=backend,
        )

    return InitialPlacement(
        positions=all_positions,
        zone_assignments=dict(zone_assignment.assignments),
        clusters=all_clusters,
    )
