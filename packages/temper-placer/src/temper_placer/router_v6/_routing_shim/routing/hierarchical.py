"""
Hierarchical Routing for Clearance-Constrained Nets

Implements 2-pass routing to avoid A* visit explosion caused by aggressive
clearance masks. Routes on relaxed grid first, then uses result as guide.

Issue: temper-edni
"""

from typing import TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from temper_placer.routing.maze_router import MazeRouter, RoutePath, GridCell
    from temper_placer.routing.layer_assignment import LayerAssignment
    from jax import Array


def route_net_hierarchical(
    router: "MazeRouter",
    net_name: str,
    pin_positions: list[tuple[float, float]],
    assignment: "LayerAssignment",
    **kwargs
) -> "RoutePath":
    """
    2-pass hierarchical routing for clearance-constrained nets.
    
    Pass 1: Route without clearance (fast) to find skeleton path
    Pass 2: Route with clearance, guided by skeleton
    
    Args:
        router: MazeRouter instance
        net_name: Name of net to route
        pin_positions: Pin positions in world coordinates
        assignment: Layer assignment
        **kwargs: Additional args for route_net_mst
    
    Returns:
        RoutePath with successful route or best attempt
    """
    print(f"HIERARCHICAL: Routing {net_name} with 2-pass approach")
    
    # Pass 1: Coarse routing (no clearance)
    print("  Pass 1: Coarse routing (no clearance)...")
    coarse_path = _route_coarse(router, net_name, pin_positions, assignment, **kwargs)
    
    if not coarse_path or not coarse_path.success:
        print("  ⚠️  Coarse routing failed - fallback to standard MST")
        return router.route_net_mst(net_name, pin_positions, assignment, **kwargs)
    
    # Debug layer distribution in coarse path
    layer_counts = {}
    for cell in coarse_path.cells:
        layer_counts[cell.layer] = layer_counts.get(cell.layer, 0) + 1
    print(f"  ✅ Coarse path found: {len(coarse_path.cells)} cells")
    print(f"     Layer distribution: {layer_counts}")
    print(f"     Via count: {coarse_path.via_count}")
    
    # Pass 2: Fine routing with clearance, guided by coarse path
    print("  Pass 2: Fine routing (with clearance, guided)...")
    fine_path = _route_fine_guided(
        router, net_name, pin_positions, assignment,
        guide_path=coarse_path,
        **kwargs
    )
    
    if fine_path and fine_path.success:
        print(f"  ✅ Fine routing succeeded: {len(fine_path.cells)} cells")
        return fine_path
    
    # Pass 2 failed - widen corridor and retry
    print("  ⚠️  Guided routing failed - widening corridor...")
    # Dynamic corridor width: at least 5mm, or 4x clearance
    # Large clearance nets (HV) need more room to deviate from the coarse skeleton
    clearance = kwargs.get('clearance_mm', 0.0) or 0.0
    corridor_width = max(5.0, clearance * 4.0)
    
    fine_path = _route_fine_corridor(
        router, net_name, pin_positions, assignment,
        guide_path=coarse_path,
        corridor_width_mm=corridor_width,
        **kwargs
    )
    
    if fine_path and fine_path.success:
        print(f"  ✅ Corridor routing succeeded: {len(fine_path.cells)} cells")
        return fine_path
    
    print("  ⚠️  All fine routing failed - returning coarse path")
    return coarse_path


def _route_coarse(
    router: "MazeRouter",
    net_name: str,
    pin_positions: list[tuple[float, float]],
    assignment: "LayerAssignment",
    **kwargs
) -> "RoutePath":
    """
    Route without clearance constraints to find skeleton path.
    
    This is fast because A* doesn't have to navigate around clearance masks.
    """
    # Temporarily disable clearance
    kwargs_coarse = kwargs.copy()
    kwargs_coarse['clearance_mm'] = 0.0
    kwargs_coarse['bypass_clearance_generation'] = True  # Skip clearance mask entirely
    
    # Route with standard MST
    return router.route_net_mst(net_name, pin_positions, assignment, **kwargs_coarse)


def _route_fine_guided(
    router: "MazeRouter",
    net_name: str,
    pin_positions: list[tuple[float, float]],
    assignment: "LayerAssignment",
    guide_path: "RoutePath",
    guide_bias: float = 0.5,
    **kwargs
) -> "RoutePath | None":
    """
    Route with clearance, using guide path to bias A* heuristic.

    Uses pre-computed guide map passed directly to Numba-accelerated router.

    Args:
        router: MazeRouter instance
        net_name: Net name
        pin_positions: Pin positions
        assignment: Layer assignment
        guide_path: Coarse path to use as guide
        guide_bias: Heuristic bias factor (0.5 = gentle, 2.0 = aggressive)
        **kwargs: Additional routing args

    Returns:
        RoutePath or None
    """
    # Create distance map from guide path
    print(f"  Creating guide map from {len(guide_path.cells)} coarse cells...")
    guide_map = _create_guide_map(router, guide_path)

    # Debug guide map statistics
    print(f"    Guide map shape: {guide_map.shape}")
    print(
        f"    Guide map min: {guide_map.min():.1f}, max: {guide_map.max():.1f}, mean: {guide_map.mean():.1f}"
    )

    try:
        # Pass guide map directly to router
        # This allows Numba implementation to handle the biasing efficiently
        kwargs_guided = kwargs.copy()
        kwargs_guided["clearance_mm"] = None
        kwargs_guided["bypass_clearance_generation"] = True
        kwargs_guided["guide_map"] = guide_map
        kwargs_guided["guide_bias"] = guide_bias

        result = router.route_net_mst(net_name, pin_positions, assignment, **kwargs_guided)

        return result
    finally:
        pass


def _route_fine_corridor(
    router: "MazeRouter",
    net_name: str,
    pin_positions: list[tuple[float, float]],
    assignment: "LayerAssignment",
    guide_path: "RoutePath",
    corridor_width_mm: float,
    **kwargs
) -> "RoutePath |None":
    """
    Route with clearance, after clearing corridor around guide path.
    
    This acts as a fallback when guided routing fails. We explicitly
    unblock cells within a corridor around the guide path to prevent
    clearance masks from blocking the route.
    """
    # Save original occupancy
    original_occ = router.occupancy.copy()
    
    # Calculate corridor width in cells
    corridor_cells = int(corridor_width_mm / router.cell_size) // 2
    
    # Clear corridor around guide path
    for cell in guide_path.cells:
        for dx in range(-corridor_cells, corridor_cells + 1):
            for dy in range(-corridor_cells, corridor_cells + 1):
                nx, ny = cell.x + dx, cell.y + dy
                if 0 <= nx < router.grid_size[0] and 0 <= ny < router.grid_size[1]:
                    # Unblock this cell on all layers
                    for layer in range(router.num_layers):
                        if router.occupancy[nx, ny, layer] == -1:
                            router.occupancy[nx, ny, layer] = 0
    
    try:
        # Route with cleared corridor
        result = router.route_net_mst(net_name, pin_positions, assignment, **kwargs)
        return result
    finally:
        # Restore original occupancy
        router.occupancy[:] = original_occ


def _create_guide_map(router: "MazeRouter", guide_path: "RoutePath") -> "Array":
    """
    Create a distance map showing distance from each cell to guide path.
    
    Uses distance transform to efficiently compute Manhattan distances.
    
    Returns:
        3D array (X, Y, Layer) where each cell contains distance to
        nearest guide path cell (in Manhattan distance)
    """
    import numpy as np
    from scipy.ndimage import distance_transform_cdt
    
    # Initialize binary mask: 1 where guide path exists, 0 elsewhere
    guide_mask = np.zeros(
        (router.grid_size[0], router.grid_size[1], router.num_layers),
        dtype=np.uint8
    )
    
    # Mark guide cells
    for cell in guide_path.cells:
        guide_mask[cell.x, cell.y, cell.layer] = 1
    
    # Compute distance transform per layer (Manhattan distance)
    guide_map = np.zeros_like(guide_mask, dtype=np.float32)
    
    for layer in range(router.num_layers):
        # Invert mask: distance_transform_cdt computes distance to nearest 0
        inverted = 1 - guide_mask[:, :, layer]
        # Compute distance (chessboard metric = cityblock/Manhattan)
        guide_map[:, :, layer] = distance_transform_cdt(
            inverted,
            metric='taxicab'  # Manhattan distance
        )
    
    return guide_map
