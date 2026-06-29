

def snap_to_grid(pos: tuple[float, float], grid_size: float = 0.25) -> tuple[float, float]:
    """Snap position to nearest grid point."""
    return (
        round(pos[0] / grid_size) * grid_size,
        round(pos[1] / grid_size) * grid_size
    )

def add_endpoint_nudge(path: list[tuple[float, float]],
                       actual_start: tuple[float, float],
                       actual_end: tuple[float, float]) -> list[tuple[float, float]]:
    """Add short segments connecting grid-snapped path to actual pad centers."""
    if not path:
        return []

    result = []

    # Nudge from actual start to first grid point
    # We use a threshold to avoid zero-length segments
    dist_start = ((path[0][0] - actual_start[0])**2 + (path[0][1] - actual_start[1])**2)**0.5
    if dist_start > 1e-4:
        result.append(actual_start)

    result.extend(path)

    # Nudge from last grid point to actual end
    dist_end = ((path[-1][0] - actual_end[0])**2 + (path[-1][1] - actual_end[1])**2)**0.5
    if dist_end > 1e-4:
        result.append(actual_end)

    return result
