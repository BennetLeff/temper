"""
Routing invariant checks for correctness verification.

This module provides functions to validate that routing results satisfy
key invariants like path connectivity, endpoint validity, and no blocked
cell traversal.

Usage:
    from temper_placer.routing.routing_invariants import validate_route_result
    
    violations = validate_route_result(route, router)
    if violations:
        raise RoutingInvariantError(violations)
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from jax import Array

if TYPE_CHECKING:
    from temper_placer.routing.maze_router import GridCell, MazeRouter, RoutePath


class RoutingInvariantError(Exception):
    """Raised when a routing invariant is violated."""
    
    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__(f"Routing invariant violations: {violations}")


@dataclass
class InvariantViolation:
    """Details about a single invariant violation."""
    invariant: str
    message: str
    location: tuple[int, int, int] | None = None
    net: str | None = None


def validate_path_connectivity(path: list["GridCell"]) -> list[InvariantViolation]:
    """Check that each cell in the path is adjacent to the previous one.
    
    A valid path has each cell exactly 1 step away from the previous in
    exactly one dimension (x, y, or layer).
    
    Args:
        path: List of GridCell forming the route.
        
    Returns:
        List of violations (empty if valid).
    """
    if len(path) < 2:
        return []  # Single cell or empty path is trivially connected
    
    violations = []
    for i in range(1, len(path)):
        prev, curr = path[i-1], path[i]
        dx = abs(curr.x - prev.x)
        dy = abs(curr.y - prev.y)
        dl = abs(curr.layer - prev.layer)
        
        # Must move exactly 1 step in exactly one dimension
        total_steps = dx + dy + dl
        if total_steps != 1:
            violations.append(InvariantViolation(
                invariant="path_connectivity",
                message=f"Path discontinuity at step {i}: ({prev.x},{prev.y},L{prev.layer}) -> ({curr.x},{curr.y},L{curr.layer}) = {total_steps} steps",
                location=(curr.x, curr.y, curr.layer),
            ))
    
    return violations


def validate_endpoints(
    path: list["GridCell"],
    start: tuple[int, int],
    end: tuple[int, int],
) -> list[InvariantViolation]:
    """Check that path starts and ends at the correct locations.
    
    Note: Layer is not checked since paths may start/end on different layers.
    
    Args:
        path: List of GridCell forming the route.
        start: Expected (x, y) start position.
        end: Expected (x, y) end position.
        
    Returns:
        List of violations (empty if valid).
    """
    if not path:
        return [InvariantViolation(
            invariant="endpoints",
            message="Path is empty",
        )]
    
    violations = []
    
    if path[0].x != start[0] or path[0].y != start[1]:
        violations.append(InvariantViolation(
            invariant="endpoints",
            message=f"Path starts at ({path[0].x},{path[0].y}) but expected ({start[0]},{start[1]})",
            location=(path[0].x, path[0].y, path[0].layer),
        ))
    
    if path[-1].x != end[0] or path[-1].y != end[1]:
        violations.append(InvariantViolation(
            invariant="endpoints",
            message=f"Path ends at ({path[-1].x},{path[-1].y}) but expected ({end[0]},{end[1]})",
            location=(path[-1].x, path[-1].y, path[-1].layer),
        ))
    
    return violations


def validate_no_blocked_cells(
    path: list["GridCell"],
    occupancy: Array,
) -> list[InvariantViolation]:
    """Check that the path doesn't traverse blocked cells.
    
    Blocked cells have occupancy value of -1.
    
    Args:
        path: List of GridCell forming the route.
        occupancy: Occupancy grid from the router.
        
    Returns:
        List of violations (empty if valid).
    """
    violations = []
    
    for i, cell in enumerate(path):
        if int(occupancy[cell.x, cell.y, cell.layer]) == -1:
            violations.append(InvariantViolation(
                invariant="no_blocked_cells",
                message=f"Path traverses blocked cell at step {i}: ({cell.x},{cell.y},L{cell.layer})",
                location=(cell.x, cell.y, cell.layer),
            ))
    
    return violations


def validate_within_bounds(
    path: list["GridCell"],
    grid_size: tuple[int, int],
    num_layers: int,
) -> list[InvariantViolation]:
    """Check that all cells are within grid bounds.
    
    Args:
        path: List of GridCell forming the route.
        grid_size: (width, height) of the grid.
        num_layers: Number of routing layers.
        
    Returns:
        List of violations (empty if valid).
    """
    violations = []
    
    for i, cell in enumerate(path):
        if not (0 <= cell.x < grid_size[0] and 
                0 <= cell.y < grid_size[1] and 
                0 <= cell.layer < num_layers):
            violations.append(InvariantViolation(
                invariant="within_bounds",
                message=f"Cell out of bounds at step {i}: ({cell.x},{cell.y},L{cell.layer}) not in {grid_size}x{num_layers}",
                location=(cell.x, cell.y, cell.layer),
            ))
    
    return violations


def validate_route_result(
    result: "RoutePath",
    router: "MazeRouter",
) -> list[InvariantViolation]:
    """Run all invariant checks on a routing result.
    
    Args:
        result: RoutePath from the router.
        router: MazeRouter instance for context.
        
    Returns:
        List of all violations found (empty if valid).
    """
    if not result.success:
        return []  # Failed routes are expected to be invalid
    
    if not result.cells:
        return []  # Empty cells (e.g., single-pin nets) are valid
    
    violations: list[InvariantViolation] = []
    
    # Add net name to all violations for context
    def with_net(v: InvariantViolation) -> InvariantViolation:
        v.net = result.net
        return v
    
    # Connectivity check
    violations.extend(with_net(v) for v in validate_path_connectivity(result.cells))
    
    # Bounds check
    violations.extend(with_net(v) for v in validate_within_bounds(
        result.cells, router.grid_size, router.num_layers
    ))
    
    # Blocked cells check
    violations.extend(with_net(v) for v in validate_no_blocked_cells(
        result.cells, router.occupancy
    ))
    
    return violations


def validate_no_overlaps(
    routed_paths: dict[str, "RoutePath"],
) -> list[tuple[str, str, tuple[int, int, int]]]:
    """Check for overlapping routes between different nets.
    
    Args:
        routed_paths: Dict mapping net names to RoutePath results.
        
    Returns:
        List of (net1, net2, (x, y, layer)) tuples where overlap occurs.
    """
    cell_to_nets: dict[tuple[int, int, int], set[str]] = {}
    
    for net_name, route in routed_paths.items():
        if not route.success or not route.cells:
            continue
        for cell in route.cells:
            key = (cell.x, cell.y, cell.layer)
            if key not in cell_to_nets:
                cell_to_nets[key] = set()
            cell_to_nets[key].add(net_name)
    
    overlaps: list[tuple[str, str, tuple[int, int, int]]] = []
    for cell, nets in cell_to_nets.items():
        if len(nets) > 1:
            net_list = sorted(nets)
            for i, net1 in enumerate(net_list):
                for net2 in net_list[i+1:]:
                    overlaps.append((net1, net2, cell))
    
    return overlaps


def format_violations(violations: list[InvariantViolation]) -> str:
    """Format violations as a human-readable string.
    
    Args:
        violations: List of invariant violations.
        
    Returns:
        Formatted string for logging/display.
    """
    if not violations:
        return "✓ All invariants passed"
    
    lines = [f"✗ {len(violations)} invariant violation(s):"]
    for v in violations[:10]:  # Limit to first 10
        net_str = f"[{v.net}] " if v.net else ""
        loc_str = f" at {v.location}" if v.location else ""
        lines.append(f"  - {net_str}{v.invariant}: {v.message}{loc_str}")
    
    if len(violations) > 10:
        lines.append(f"  ... and {len(violations) - 10} more")
    
    return "\n".join(lines)
