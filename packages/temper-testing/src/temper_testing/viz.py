"""
Visual debugging utilities for grid-based algorithms.

Render ASCII art of grids, paths, and placements for easy debugging.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence
import numpy as np

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


# Unicode box-drawing characters for prettier output
CHARS = {
    "empty": "·",
    "blocked": "█",
    "component": "▒",
    "pin": "○",
    "path": "━",
    "path_v": "┃",
    "start": "S",
    "goal": "G",
    "via": "◉",
    "error": "✗",
}

# ANSI colors
COLORS = {
    "reset": "\033[0m",
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "magenta": "\033[95m",
    "cyan": "\033[96m",
}


@dataclass
class GridCell:
    """A cell in the grid visualization."""
    x: int
    y: int
    char: str
    color: str = "reset"
    layer: int = 0


def render_grid(
    occupancy: np.ndarray,
    components: Sequence[Any] | None = None,
    positions: np.ndarray | None = None,
    path: Sequence[tuple[int, int, int]] | None = None,
    pins: Sequence[tuple[int, int]] | None = None,
    start: tuple[int, int] | None = None,
    goal: tuple[int, int] | None = None,
    layer: int = 0,
    max_width: int = 80,
    max_height: int = 40,
    title: str | None = None,
) -> str:
    """
    Render a grid as ASCII art.

    Args:
        occupancy: 2D or 3D array (height, width) or (layers, height, width).
                   Values: 0=free, 1=blocked, 2=routed.
        components: Optional list of components to highlight.
        positions: Component positions as (N, 2) array.
        path: Optional path as list of (x, y, layer) tuples.
        pins: Optional pin locations as (x, y) tuples.
        start: Start cell (x, y).
        goal: Goal cell (x, y).
        layer: Which layer to render (for 3D grids).
        max_width: Maximum output width.
        max_height: Maximum output height.
        title: Optional title for the grid.

    Returns:
        ASCII string representation.

    Example:
        >>> grid = np.zeros((10, 10))
        >>> grid[3:7, 3:7] = 1  # Blocked region
        >>> print(render_grid(grid))
        · · · · · · · · · ·
        · · · · · · · · · ·
        · · · · · · · · · ·
        · · · █ █ █ █ · · ·
        · · · █ █ █ █ · · ·
        · · · █ █ █ █ · · ·
        · · · █ █ █ █ · · ·
        · · · · · · · · · ·
        · · · · · · · · · ·
        · · · · · · · · · ·
    """
    # Handle 3D grid
    if occupancy.ndim == 3:
        grid = occupancy[layer]
    else:
        grid = occupancy

    height, width = grid.shape

    # Downsample if too large
    if width > max_width or height > max_height:
        scale_x = max(1, width // max_width)
        scale_y = max(1, height // max_height)
        grid = grid[::scale_y, ::scale_x]
        height, width = grid.shape

    # Build character grid
    chars = [[CHARS["empty"] for _ in range(width)] for _ in range(height)]
    colors = [["reset" for _ in range(width)] for _ in range(height)]

    # Fill blocked cells
    for y in range(height):
        for x in range(width):
            if grid[y, x] == 1:
                chars[y][x] = CHARS["blocked"]
                colors[y][x] = "red"
            elif grid[y, x] == 2:
                chars[y][x] = CHARS["path"]
                colors[y][x] = "green"

    # Draw path
    if path:
        for i, (px, py, pl) in enumerate(path):
            if pl == layer and 0 <= py < height and 0 <= px < width:
                if i > 0:
                    prev_x, prev_y, _ = path[i - 1]
                    if px != prev_x:
                        chars[py][px] = CHARS["path"]
                    else:
                        chars[py][px] = CHARS["path_v"]
                else:
                    chars[py][px] = CHARS["path"]
                colors[py][px] = "green"

    # Draw pins
    if pins:
        for px, py in pins:
            if 0 <= py < height and 0 <= px < width:
                chars[py][px] = CHARS["pin"]
                colors[py][px] = "cyan"

    # Draw start/goal
    if start:
        sx, sy = start
        if 0 <= sy < height and 0 <= sx < width:
            chars[sy][sx] = CHARS["start"]
            colors[sy][sx] = "blue"

    if goal:
        gx, gy = goal
        if 0 <= gy < height and 0 <= gx < width:
            chars[gy][gx] = CHARS["goal"]
            colors[gy][gx] = "magenta"

    # Build output string
    lines = []
    if title:
        lines.append(f"=== {title} ===")
        lines.append(f"Size: {width}x{height}, Layer: {layer}")
        lines.append("")

    for y in range(height):
        row = ""
        for x in range(width):
            c = colors[y][x]
            char = chars[y][x]
            if c != "reset":
                row += f"{COLORS[c]}{char}{COLORS['reset']} "
            else:
                row += f"{char} "
        lines.append(row.rstrip())

    # Legend
    lines.append("")
    lines.append(f"Legend: {CHARS['empty']}=free {CHARS['blocked']}=blocked {CHARS['pin']}=pin {CHARS['start']}=start {CHARS['goal']}=goal")

    return "\n".join(lines)


def render_placement(
    board_width: float,
    board_height: float,
    components: Sequence[Any],
    positions: np.ndarray,
    rotations: np.ndarray | None = None,
    cell_size: float = 2.0,
    title: str | None = None,
) -> str:
    """
    Render component placement as ASCII art.

    Args:
        board_width: Board width in mm.
        board_height: Board height in mm.
        components: List of components with .ref and .bounds attributes.
        positions: Component positions as (N, 2) array.
        rotations: Optional rotation indices (0-3).
        cell_size: Size of each ASCII cell in mm.
        title: Optional title.

    Returns:
        ASCII string representation.
    """
    # Convert to grid
    grid_width = int(board_width / cell_size)
    grid_height = int(board_height / cell_size)

    grid = [[" " for _ in range(grid_width)] for _ in range(grid_height)]

    # Draw board border
    for x in range(grid_width):
        grid[0][x] = "─"
        grid[grid_height - 1][x] = "─"
    for y in range(grid_height):
        grid[y][0] = "│"
        grid[y][grid_width - 1] = "│"
    grid[0][0] = "┌"
    grid[0][grid_width - 1] = "┐"
    grid[grid_height - 1][0] = "└"
    grid[grid_height - 1][grid_width - 1] = "┘"

    # Draw components
    for i, comp in enumerate(components):
        if i >= len(positions):
            continue

        x, y = positions[i]
        w, h = comp.bounds if hasattr(comp, "bounds") else (5, 5)

        # Convert to grid coords
        gx = int(x / cell_size)
        gy = int(y / cell_size)
        gw = max(1, int(w / cell_size))
        gh = max(1, int(h / cell_size))

        # Get component label (first 3 chars of ref)
        ref = comp.ref if hasattr(comp, "ref") else f"C{i}"
        label = ref[:3]

        # Draw component box
        for dy in range(gh):
            for dx in range(gw):
                cx, cy = gx + dx, gy + dy
                if 0 < cx < grid_width - 1 and 0 < cy < grid_height - 1:
                    if dy == gh // 2 and dx < len(label):
                        grid[cy][cx] = label[dx]
                    else:
                        grid[cy][cx] = "▒"

    # Build output
    lines = []
    if title:
        lines.append(f"=== {title} ===")
        lines.append(f"Board: {board_width}x{board_height}mm, Components: {len(components)}")
        lines.append("")

    for row in grid:
        lines.append("".join(row))

    return "\n".join(lines)


def render_loss_landscape(
    loss_fn: Any,
    center: np.ndarray,
    range_x: float = 10.0,
    range_y: float = 10.0,
    resolution: int = 20,
    component_idx: int = 0,
) -> str:
    """
    Render 2D slice of loss landscape as heatmap.

    Args:
        loss_fn: Loss function.
        center: Center position.
        range_x: Range in X direction.
        range_y: Range in Y direction.
        resolution: Grid resolution.
        component_idx: Which component to vary.

    Returns:
        ASCII heatmap of loss values.
    """
    # Sample loss values
    xs = np.linspace(center[0] - range_x, center[0] + range_x, resolution)
    ys = np.linspace(center[1] - range_y, center[1] + range_y, resolution)

    values = np.zeros((resolution, resolution))

    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            test_pos = center.copy()
            test_pos[component_idx * 2] = x
            test_pos[component_idx * 2 + 1] = y
            try:
                values[i, j] = float(loss_fn(test_pos))
            except Exception:
                values[i, j] = np.nan

    # Normalize to 0-9 for display
    valid = ~np.isnan(values)
    if np.any(valid):
        vmin, vmax = np.nanmin(values), np.nanmax(values)
        if vmax > vmin:
            normalized = (values - vmin) / (vmax - vmin) * 9
        else:
            normalized = np.zeros_like(values)
    else:
        normalized = np.zeros_like(values)

    # Build heatmap
    chars = " ░▒▓█"
    lines = []
    lines.append(f"Loss landscape (component {component_idx})")
    lines.append(f"X: [{center[0]-range_x:.1f}, {center[0]+range_x:.1f}]")
    lines.append(f"Y: [{center[1]-range_y:.1f}, {center[1]+range_y:.1f}]")
    lines.append("")

    for i in range(resolution):
        row = ""
        for j in range(resolution):
            if np.isnan(values[i, j]):
                row += "X"
            else:
                idx = min(4, int(normalized[i, j] / 2.5))
                row += chars[idx]
        lines.append(row)

    lines.append("")
    lines.append(f"Min: {np.nanmin(values):.4f}, Max: {np.nanmax(values):.4f}")

    return "\n".join(lines)


# Pytest integration
def pytest_assertion_grid(
    grid: np.ndarray,
    expected: np.ndarray,
    actual: np.ndarray | None = None,
) -> str:
    """
    Generate detailed assertion message for grid comparison.

    Use in pytest assertions:
        assert np.allclose(actual, expected), pytest_assertion_grid(...)
    """
    lines = []
    lines.append("Grid assertion failed:")
    lines.append("")
    lines.append("Expected:")
    lines.append(render_grid(expected, max_width=40, max_height=20))
    lines.append("")
    if actual is not None:
        lines.append("Actual:")
        lines.append(render_grid(actual, max_width=40, max_height=20))
        lines.append("")
        lines.append("Difference:")
        diff = (expected != actual).astype(int)
        lines.append(render_grid(diff, max_width=40, max_height=20))

    return "\n".join(lines)
