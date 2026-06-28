"""Path cost calculation for maze routing."""

from typing import Any


BLOCKED_COST = 1e9


def compute_path_cost(path: list, via_cost: float = 1.0) -> float:
    """Compute total cost for a path.

    Cost = path_length + (num_vias * via_cost)

    Args:
        path: List of cells representing the path (each with .layer attribute)
        via_cost: Cost per layer transition (via)

    Returns:
        Total path cost as float
    """
    path_length = len(path)
    num_vias = sum(1 for j in range(1, len(path)) if path[j].layer != path[j - 1].layer)
    return float(path_length + num_vias * via_cost)


def count_vias(path: list) -> int:
    """Count number of layer transitions (vias) in a path.

    Args:
        path: List of cells representing the path

    Returns:
        Number of layer transitions
    """
    if len(path) < 2:
        return 0
    return sum(1 for j in range(1, len(path)) if path[j].layer != path[j - 1].layer)


def compute_path_length_mm(path: list, cell_size: float) -> float:
    """Compute physical length of path in mm.

    Args:
        path: List of cells representing the path
        cell_size: Size of each cell in mm

    Returns:
        Path length in mm
    """
    if len(path) < 2:
        return 0.0
    return len(path) * cell_size


def extract_cells_from_paths(paths: list[list]) -> list:
    """Extract all unique cells from a list of paths.

    Args:
        paths: List of paths, each a list of cells

    Returns:
        List of unique cells
    """
    seen = set()
    result = []
    for path in paths:
        for cell in path:
            cell_key = (cell.x, cell.y, cell.layer)
            if cell_key not in seen:
                seen.add(cell_key)
                result.append(cell)
    return result


def analyze_path_difficulty(
    path: list,
    get_difficulty: Any,
) -> tuple[float, list]:
    """Analyze difficulty of a path.

    Args:
        path: List of cells representing the path
        get_difficulty: Function that takes a cell and returns difficulty

    Returns:
        Tuple of (total_difficulty, list_of_difficulties)
    """
    difficulties = [get_difficulty(cell) for cell in path]
    return sum(difficulties), difficulties
