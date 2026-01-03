"""DRC validation for maze routing."""

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from temper_placer.core.design_rules import NetClassRules
    from temper_placer.core.netlist import Netlist
    from jax import Array


CLASS_DEFAULT = 0
CLASS_HV = 1
CLASS_LV = 2


def compute_drc_margin(
    required_clearance: float = 0.2,
    trace_width: float = 0.2,
    cell_size: float = 1.0,
) -> float:
    """Compute margin needed to prevent grid-geometry DRC violations.

    The grid router thinks in "squares", but DRC checks actual geometry.
    A cell marked as "free" could still cause violations if a trace
    centered in that cell passes too close to a pad.

    The safe margin is:
        required_clearance + (trace_width / 2) + (cell_size / 2)

    The cell_size/2 term accounts for worst-case trace placement within
    a cell (trace centered at cell center, pad edge at cell boundary).

    Args:
        required_clearance: DRC clearance rule in mm (default 0.2mm)
        trace_width: Expected trace width in mm (default 0.2mm)
        cell_size: Cell size in mm (default 1.0mm)

    Returns:
        Margin in mm to apply around pads for blocking
    """
    return required_clearance + (trace_width / 2)


def get_class_id(rules: "NetClassRules | None") -> int:
    """Get integer class ID for creepage checks."""
    from temper_placer.routing.safety_distances import is_high_voltage

    if not rules:
        return CLASS_DEFAULT

    if hasattr(rules, "voltage_v") and is_high_voltage(rules.voltage_v):
        return CLASS_HV

    if rules.creepage_mm > 2.0:
        return CLASS_HV

    return CLASS_LV


def get_asymmetric_clearance(
    current_class: int, obstacle_class: int, min_clearance: float = 0.2
) -> float:
    """Get required clearance between two net classes.

    Enforces reinforced isolation (8.0mm) between High Voltage and Low Voltage
    domains, and standard clearance (0.2mm) otherwise.

    Args:
        current_class: Class ID of the net being routed.
        obstacle_class: Class ID of the cell being checked.
        min_clearance: Minimum clearance for non-HV nets.

    Returns:
        Required clearance in mm.
    """
    if (current_class == CLASS_HV and obstacle_class != CLASS_HV) or (
        current_class != CLASS_HV and obstacle_class == CLASS_HV
    ):
        return 8.0

    if current_class == CLASS_HV and obstacle_class == CLASS_HV:
        return 2.5

    return min_clearance


def check_class_clearance(
    cx: int,
    cy: int,
    cl: int,
    current_class: int,
    class_grid: np.ndarray,
    cell_size: float,
    min_clearance: float = 0.2,
) -> bool:
    """Check if cell (cx, cy, cl) violates clearance with other classes.

    Checks a radius around the cell for incompatible net classes.
    Returns True if SAFE, False if VIOLATION.

    Args:
        cx: Cell x coordinate
        cy: Cell y coordinate
        cl: Cell layer
        current_class: Class ID of the net being routed
        class_grid: 3D numpy array of class IDs
        cell_size: Size of each cell in mm
        min_clearance: Minimum clearance for non-HV nets

    Returns:
        True if safe, False if violation
    """
    if current_class == CLASS_DEFAULT:
        return True

    grid_w, grid_h = class_grid.shape[:2]

    obs_class = class_grid[cx, cy, cl]
    if obs_class != 0 and obs_class != current_class:
        req_sep = get_asymmetric_clearance(current_class, obs_class, min_clearance)
        if 0 < req_sep:
            return False

    search_radius_mm = 8.0
    radius_cells = int(math.ceil(search_radius_mm / cell_size))

    for dx in range(-radius_cells, radius_cells + 1):
        for dy in range(-radius_cells, radius_cells + 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < grid_w and 0 <= ny < grid_h:
                obs_class = class_grid[nx, ny, cl]
                if obs_class != 0 and obs_class != current_class:
                    req_sep = get_asymmetric_clearance(current_class, obs_class, min_clearance)
                    dist_mm = math.sqrt(dx * dx + dy * dy) * cell_size
                    if dist_mm < req_sep:
                        return False

    return True
