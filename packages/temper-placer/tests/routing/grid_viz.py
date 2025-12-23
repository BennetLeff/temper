"""
Visual Grid Rendering for Router Tests

Provides ASCII art visualization of routing grids for debugging test failures.
Makes failures immediately understandable by showing grid state, obstacles, paths, etc.

Usage:
    from temper_placer.tests.routing.grid_viz import render_grid, print_grid_on_failure
    
    # In test:
    router = MazeRouter(grid_size=(10, 10))
    # ... setup and routing ...
    
    # On assertion failure, print grid:
    if not path:
        print(render_grid(router, path=None, start=(0,0), end=(9,9)))
        assert False, "Path not found"
"""

from typing import Optional, List, Tuple, Set
import jax.numpy as jnp
from temper_placer.routing.maze_router import GridCell, MazeRouter


def render_grid(
    router: MazeRouter,
    path: Optional[List[GridCell]] = None,
    start: Optional[Tuple[int, int]] = None,
    end: Optional[Tuple[int, int]] = None,
    layer: int = 0,
    pins: Optional[Set[Tuple[int, int]]] = None,
    components: Optional[Set[Tuple[int, int]]] = None,
    max_size: int = 40,
) -> str:
    """
    Render a routing grid as ASCII art.
    
    Legend:
        . = free cell
        # = blocked cell
        P = pin
        C = component center
        * = path cell
        S = start
        E = end
        + = path crossing (if multiple paths)
    
    Args:
        router: MazeRouter instance
        path: Optional path to highlight
        start: Optional start coordinate (x, y)
        end: Optional end coordinate (x, y)
        layer: Which layer to visualize (default 0)
        pins: Set of pin coordinates
        components: Set of component center coordinates
        max_size: Maximum grid dimension to render (prevents huge output)
    
    Returns:
        ASCII art string representation of the grid
    """
    width, height = router.grid_size
    
    # Safety check
    if width > max_size or height > max_size:
        return f"Grid too large to render ({width}x{height} > {max_size}x{max_size})"
    
    # Convert path to set of coordinates for fast lookup
    path_coords = set()
    if path:
        path_coords = {(cell.x, cell.y) for cell in path if cell.layer == layer}
    
    # Build grid
    lines = []
    lines.append(f"Grid {width}x{height}, Layer {layer}")
    lines.append("  " + "".join(str(x % 10) for x in range(width)))
    
    for y in range(height):
        row = f"{y:2d}"
        for x in range(width):
            # Priority order for symbols
            if start and (x, y) == start:
                row += "S"
            elif end and (x, y) == end:
                row += "E"
            elif (x, y) in path_coords:
                row += "*"
            elif pins and (x, y) in pins:
                row += "P"
            elif components and (x, y) in components:
                row += "C"
            elif int(router.occupancy[x, y, layer]) == 1:
                row += "#"
            else:
                row += "."
        lines.append(row)
    
    # Add legend
    lines.append("")
    lines.append("Legend: . = free, # = blocked, P = pin, C = component, * = path, S = start, E = end")
    
    return "\n".join(lines)


def render_multi_layer(
    router: MazeRouter,
    path: Optional[List[GridCell]] = None,
    start: Optional[Tuple[int, int]] = None,
    end: Optional[Tuple[int, int]] = None,
    max_size: int = 40,
) -> str:
    """
    Render all layers of a routing grid side-by-side.
    
    Args:
        router: MazeRouter instance
        path: Optional path to highlight (shows layer transitions)
        start: Optional start coordinate
        end: Optional end coordinate
        max_size: Maximum grid dimension to render
    
    Returns:
        ASCII art showing all layers
    """
    width, height = router.grid_size
    num_layers = router.occupancy.shape[2]
    
    if width > max_size or height > max_size:
        return f"Grid too large to render ({width}x{height} > {max_size}x{max_size})"
    
    # Render each layer
    layer_renders = []
    for layer in range(num_layers):
        layer_renders.append(render_grid(router, path, start, end, layer=layer, max_size=max_size))
    
    # Show via transitions if path exists
    via_info = []
    if path:
        for i, cell in enumerate(path[:-1]):
            next_cell = path[i + 1]
            if cell.layer != next_cell.layer:
                via_info.append(f"  Via at ({cell.x}, {cell.y}): L{cell.layer} → L{next_cell.layer}")
    
    result = "\n\n".join(layer_renders)
    
    if via_info:
        result += "\n\nVia Transitions:\n" + "\n".join(via_info)
    
    return result


def print_grid_on_failure(
    router: MazeRouter,
    path: Optional[List[GridCell]],
    start: Tuple[int, int],
    end: Tuple[int, int],
    expected_success: bool = True,
) -> None:
    """
    Helper to print grid visualization when a test fails.
    
    Usage in tests:
        path = router.find_path(start, end)
        if path is None:
            print_grid_on_failure(router, path, start, end, expected_success=True)
        assert path is not None
    
    Args:
        router: MazeRouter instance
        path: The path result (may be None)
        start: Start coordinate
        end: End coordinate
        expected_success: Whether we expected routing to succeed
    """
    print("\n" + "=" * 60)
    print("ROUTING FAILURE VISUALIZATION")
    print("=" * 60)
    print(f"Start: {start}, End: {end}")
    print(f"Expected success: {expected_success}, Got: {path is not None}")
    
    if router.occupancy.shape[2] > 1:
        print(render_multi_layer(router, path, start, end))
    else:
        print(render_grid(router, path, start, end))
    
    print("=" * 60)


def render_path_comparison(
    router: MazeRouter,
    actual_path: Optional[List[GridCell]],
    expected_path: Optional[List[GridCell]],
    start: Tuple[int, int],
    end: Tuple[int, int],
) -> str:
    """
    Render two paths side-by-side for comparison.
    
    Args:
        router: MazeRouter instance
        actual_path: The path that was actually found
        expected_path: The path that was expected
        start: Start coordinate
        end: End coordinate
    
    Returns:
        Side-by-side comparison string
    """
    width, height = router.grid_size
    
    # Convert paths to coordinate sets
    actual_coords = set()
    if actual_path:
        actual_coords = {(cell.x, cell.y) for cell in actual_path}
    
    expected_coords = set()
    if expected_path:
        expected_coords = {(cell.x, cell.y) for cell in expected_path}
    
    # Build comparison grid
    lines = []
    lines.append(f"Path Comparison - Grid {width}x{height}")
    lines.append("Legend: . = free, # = blocked, A = actual only, E = expected only, B = both, S = start, G = end")
    lines.append("")
    lines.append("  " + "".join(str(x % 10) for x in range(width)))
    
    for y in range(height):
        row = f"{y:2d}"
        for x in range(width):
            if (x, y) == start:
                row += "S"
            elif (x, y) == end:
                row += "G"
            elif (x, y) in actual_coords and (x, y) in expected_coords:
                row += "B"
            elif (x, y) in actual_coords:
                row += "A"
            elif (x, y) in expected_coords:
                row += "E"
            elif int(router.occupancy[x, y, 0]) == 1:
                row += "#"
            else:
                row += "."
        lines.append(row)
    
    # Add path length comparison
    lines.append("")
    actual_len = len(actual_path) if actual_path else 0
    expected_len = len(expected_path) if expected_path else 0
    lines.append(f"Actual path length: {actual_len}")
    lines.append(f"Expected path length: {expected_len}")
    if actual_len and expected_len:
        diff = actual_len - expected_len
        lines.append(f"Difference: {diff:+d} cells")
    
    return "\n".join(lines)
