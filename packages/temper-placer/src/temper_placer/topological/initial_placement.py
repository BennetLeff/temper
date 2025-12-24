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

import math
from dataclasses import dataclass, field

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

    x_min, y_min, x_max, y_max = zone.bounds
    zone_width = x_max - x_min
    zone_height = y_max - y_min
    center_x = (x_min + x_max) / 2
    center_y = (y_min + y_max) / 2

    # Check if zone is large enough for each component
    for ref in components:
        w, h = component_sizes[ref]
        if w > zone_width or h > zone_height:
            raise PlacementError(
                f"Zone '{zone.name}' is too small for component '{ref}' "
                f"(zone: {zone_width:.1f}x{zone_height:.1f}mm, "
                f"component: {w:.1f}x{h:.1f}mm)"
            )

    # For single component, place at center
    if len(components) == 1:
        return {components[0]: (center_x, center_y)}

    # Check total area
    total_area = sum(component_sizes[ref][0] * component_sizes[ref][1] for ref in components)
    zone_area = zone_width * zone_height
    if total_area > zone_area * 0.8:  # 80% packing limit
        raise PlacementError(
            f"Zone '{zone.name}' is too small to fit {len(components)} components "
            f"(total area: {total_area:.1f}mm², zone area: {zone_area:.1f}mm²)"
        )

    # Circular arrangement
    positions: dict[str, tuple[float, float]] = {}
    n = len(components)

    # Calculate radius - use smaller dimension, leave margin
    max_component_size = max(max(component_sizes[ref]) for ref in components)
    margin = max_component_size / 2 + 2.0  # Component half-size + 2mm
    radius = min(zone_width, zone_height) / 2 - margin
    radius = max(radius, max_component_size)  # Minimum radius

    for i, ref in enumerate(components):
        angle = 2 * math.pi * i / n
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)

        # Clamp to zone bounds with margin
        w, h = component_sizes[ref]
        x = max(x_min + w / 2, min(x, x_max - w / 2))
        y = max(y_min + h / 2, min(y, y_max - h / 2))

        positions[ref] = (x, y)

    return positions


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

    # Union-find data structures
    parent: dict[str, str] = {c: c for c in components}
    rank: dict[str, int] = dict.fromkeys(components, 0)

    def find(x: str) -> str:
        if parent[x] != x:
            parent[x] = find(parent[x])  # Path compression
        return parent[x]

    def union(x: str, y: str) -> None:
        px, py = find(x), find(y)
        if px == py:
            return
        # Union by rank
        if rank[px] < rank[py]:
            px, py = py, px
        parent[py] = px
        if rank[px] == rank[py]:
            rank[px] += 1

    # Process adjacency edges only - use graph's internal networkx graph
    component_set = set(components)
    for u, v, data in graph.graph.edges(data=True):
        if data.get("edge_type") != "adjacent":
            continue
        if u in component_set and v in component_set:
            union(u, v)

    # Collect clusters
    clusters_map: dict[str, set[str]] = {}
    for c in components:
        root = find(c)
        if root not in clusters_map:
            clusters_map[root] = set()
        clusters_map[root].add(c)

    return list(clusters_map.values())


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

    x_min, y_min, x_max, y_max = zone.bounds
    zone_width = x_max - x_min
    zone_height = y_max - y_min

    # Calculate sub-region for this cluster
    if total_clusters == 1:
        # Use whole zone
        sub_x_min, sub_y_min = x_min, y_min
        sub_x_max, sub_y_max = x_max, y_max
    else:
        # Divide zone into regions (horizontal split)
        region_width = zone_width / total_clusters
        sub_x_min = x_min + cluster_index * region_width
        sub_x_max = sub_x_min + region_width
        sub_y_min, sub_y_max = y_min, y_max

    center_x = (sub_x_min + sub_x_max) / 2
    center_y = (sub_y_min + sub_y_max) / 2

    components = sorted(cluster)  # Deterministic ordering
    positions: dict[str, tuple[float, float]] = {}

    if len(components) == 1:
        ref = components[0]
        w, h = component_sizes[ref]
        # Clamp to zone bounds
        x = max(x_min + w / 2, min(center_x, x_max - w / 2))
        y = max(y_min + h / 2, min(center_y, y_max - h / 2))
        return {ref: (x, y)}

    # For adjacent components in a cluster, use tight spacing
    # Find maximum adjacency distance constraint for this cluster
    max_adjacency_dist = 15.0  # Default
    for u, v, data in graph.graph.edges(data=True):
        if data.get("edge_type") == "adjacent":
            if u in cluster and v in cluster:
                dist = data.get("distance", 15.0)
                if dist < max_adjacency_dist:
                    max_adjacency_dist = dist

    # Calculate appropriate radius based on adjacency constraint
    n = len(components)
    max_size = max(max(component_sizes[ref]) for ref in components)

    # For tight clusters, use radius based on adjacency distance
    # Components on circle with radius r are at most 2*r apart (opposite sides)
    # For n components evenly spaced, adjacent ones are ~2*r*sin(pi/n) apart
    # We want adjacent distance <= max_adjacency_dist
    if n == 2:
        # Two components: place them max_adjacency_dist apart
        radius = max_adjacency_dist / 2
    else:
        # n components in circle: adjacent spacing = 2*r*sin(pi/n)
        # Solve: 2*r*sin(pi/n) = max_adjacency_dist
        radius = max_adjacency_dist / (2 * math.sin(math.pi / n))

    # Ensure radius is at least component size
    radius = max(radius, max_size)

    # But also cap at available space
    available_space = min(sub_x_max - sub_x_min, sub_y_max - sub_y_min) / 2 - max_size
    if available_space > 0:
        radius = min(radius, available_space)

    for i, ref in enumerate(components):
        angle = 2 * math.pi * i / n
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)

        # Clamp to zone bounds
        w, h = component_sizes[ref]
        x = max(x_min + w / 2, min(x, x_max - w / 2))
        y = max(y_min + h / 2, min(y, y_max - h / 2))

        positions[ref] = (x, y)

    return positions


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
