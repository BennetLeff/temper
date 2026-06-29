"""
Domain-specific Hypothesis strategies for PCB placement testing.

Reusable strategies that generate realistic test data.
"""

from __future__ import annotations

import importlib.util
from typing import Any

import hypothesis.strategies as st
import numpy as np
from hypothesis import assume

HAS_JAX = importlib.util.find_spec("jax") is not None


# =============================================================================
# Primitive Strategies
# =============================================================================

def mm_value(min_val: float = 0.1, max_val: float = 100.0) -> st.SearchStrategy[float]:
    """Generate realistic millimeter values."""
    return st.floats(min_value=min_val, max_value=max_val, allow_nan=False, allow_infinity=False)


def positive_mm() -> st.SearchStrategy[float]:
    """Generate positive millimeter values."""
    return mm_value(min_val=0.1, max_val=500.0)


def small_mm() -> st.SearchStrategy[float]:
    """Generate small millimeter values (component scale)."""
    return mm_value(min_val=0.5, max_val=30.0)


def angle_degrees() -> st.SearchStrategy[float]:
    """Generate rotation angles in degrees."""
    return st.sampled_from([0.0, 90.0, 180.0, 270.0])


def rotation_index() -> st.SearchStrategy[int]:
    """Generate rotation index (0-3)."""
    return st.integers(min_value=0, max_value=3)


def grid_cell() -> st.SearchStrategy[tuple[int, int]]:
    """Generate grid cell coordinates."""
    return st.tuples(
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=0, max_value=100),
    )


def layer_index(max_layers: int = 4) -> st.SearchStrategy[int]:
    """Generate layer index."""
    return st.integers(min_value=0, max_value=max_layers - 1)


# =============================================================================
# Component Strategies
# =============================================================================

@st.composite
def component_bounds(
    draw,
    min_size: float = 1.0,
    max_size: float = 30.0,
) -> tuple[float, float]:
    """Generate realistic component bounds (width, height)."""
    width = draw(st.floats(min_value=min_size, max_value=max_size))
    height = draw(st.floats(min_value=min_size, max_value=max_size))
    return (width, height)


@st.composite
def component_ref(draw) -> str:
    """Generate component reference designator."""
    prefix = draw(st.sampled_from(["U", "R", "C", "L", "Q", "D", "J", "SW"]))
    number = draw(st.integers(min_value=1, max_value=999))
    return f"{prefix}{number}"


@st.composite
def pin_positions_on_edge(
    draw,
    width: float,
    height: float,
    num_pins: int,
) -> list[tuple[float, float]]:
    """Generate pin positions along component edges."""
    pins = []
    for _ in range(num_pins):
        side = draw(st.integers(min_value=0, max_value=3))

        if side == 0:  # Top
            x = draw(st.floats(min_value=-width/2 + 0.5, max_value=width/2 - 0.5))
            y = height / 2
        elif side == 1:  # Right
            x = width / 2
            y = draw(st.floats(min_value=-height/2 + 0.5, max_value=height/2 - 0.5))
        elif side == 2:  # Bottom
            x = draw(st.floats(min_value=-width/2 + 0.5, max_value=width/2 - 0.5))
            y = -height / 2
        else:  # Left
            x = -width / 2
            y = draw(st.floats(min_value=-height/2 + 0.5, max_value=height/2 - 0.5))

        pins.append((x, y))

    return pins


@st.composite
def realistic_component(
    draw,
    pins: tuple[int, int] = (2, 20),
    size: tuple[float, float] = (1.0, 30.0),
) -> dict[str, Any]:
    """
    Generate a realistic component with pins.

    Returns dict with: ref, bounds, pins, footprint.
    """
    ref = draw(component_ref())
    width = draw(st.floats(min_value=size[0], max_value=size[1]))
    height = draw(st.floats(min_value=size[0], max_value=size[1]))
    num_pins = draw(st.integers(min_value=pins[0], max_value=pins[1]))

    pin_positions = draw(pin_positions_on_edge(width, height, num_pins))

    footprint = draw(st.sampled_from([
        "SOIC-8", "SOIC-14", "SOIC-16",
        "QFP-32", "QFP-44", "QFP-64",
        "0402", "0603", "0805", "1206",
        "SOT-23", "SOT-223", "TO-220",
    ]))

    return {
        "ref": ref,
        "bounds": (width, height),
        "pins": pin_positions,
        "footprint": footprint,
    }


# =============================================================================
# Board Strategies
# =============================================================================

@st.composite
def board_dimensions(
    draw,
    min_size: float = 20.0,
    max_size: float = 200.0,
) -> tuple[float, float]:
    """Generate board dimensions (width, height)."""
    width = draw(st.floats(min_value=min_size, max_value=max_size))
    height = draw(st.floats(min_value=min_size, max_value=max_size))
    return (width, height)


@st.composite
def board_origin(
    draw,
    max_offset: float = 200.0,
) -> tuple[float, float]:
    """Generate board origin (can be non-zero for KiCad imports)."""
    x = draw(st.floats(min_value=0.0, max_value=max_offset))
    y = draw(st.floats(min_value=0.0, max_value=max_offset))
    return (x, y)


@st.composite
def valid_position_on_board(
    draw,
    board_width: float,
    board_height: float,
    margin: float = 5.0,
    origin: tuple[float, float] = (0.0, 0.0),
) -> tuple[float, float]:
    """Generate a valid position within board bounds."""
    x = draw(st.floats(
        min_value=origin[0] + margin,
        max_value=origin[0] + board_width - margin,
    ))
    y = draw(st.floats(
        min_value=origin[1] + margin,
        max_value=origin[1] + board_height - margin,
    ))
    return (x, y)


# =============================================================================
# Placement Strategies
# =============================================================================

@st.composite
def component_positions(
    draw,
    num_components: int,
    board_width: float,
    board_height: float,
    margin: float = 5.0,
) -> np.ndarray:
    """Generate positions for multiple components."""
    positions = []
    for _ in range(num_components):
        x = draw(st.floats(min_value=margin, max_value=board_width - margin))
        y = draw(st.floats(min_value=margin, max_value=board_height - margin))
        positions.append([x, y])
    return np.array(positions)


@st.composite
def non_overlapping_positions(
    draw,
    num_components: int,
    component_sizes: list[tuple[float, float]],
    board_width: float,
    board_height: float,
    min_spacing: float = 1.0,
) -> np.ndarray:
    """
    Generate non-overlapping component positions.

    Uses rejection sampling - may fail for tight packing.
    """
    positions = []
    max_attempts = 100

    for i in range(num_components):
        w, h = component_sizes[i]

        for _attempt in range(max_attempts):
            x = draw(st.floats(min_value=w/2, max_value=board_width - w/2))
            y = draw(st.floats(min_value=h/2, max_value=board_height - h/2))

            # Check overlap with existing
            overlaps = False
            for j, (px, py) in enumerate(positions):
                pw, ph = component_sizes[j]
                dx = abs(x - px)
                dy = abs(y - py)
                if dx < (w + pw) / 2 + min_spacing and dy < (h + ph) / 2 + min_spacing:
                    overlaps = True
                    break

            if not overlaps:
                positions.append([x, y])
                break
        else:
            # Fallback: just place it (may overlap)
            assume(False)  # Reject this example

    return np.array(positions)


# =============================================================================
# Grid/Routing Strategies
# =============================================================================

@st.composite
def occupancy_grid(
    draw,
    width: int = 20,
    height: int = 20,
    blocked_fraction: float = 0.2,
) -> np.ndarray:
    """Generate random occupancy grid."""
    grid = np.zeros((height, width), dtype=np.int32)

    num_blocked = int(width * height * blocked_fraction)
    for _ in range(num_blocked):
        x = draw(st.integers(min_value=0, max_value=width - 1))
        y = draw(st.integers(min_value=0, max_value=height - 1))
        grid[y, x] = 1

    return grid


@st.composite
def path_on_grid(
    draw,
    grid_width: int,
    grid_height: int,
    min_length: int = 3,
    max_length: int = 20,
) -> list[tuple[int, int]]:
    """Generate a connected path on grid."""
    length = draw(st.integers(min_value=min_length, max_value=max_length))

    # Start position
    x = draw(st.integers(min_value=0, max_value=grid_width - 1))
    y = draw(st.integers(min_value=0, max_value=grid_height - 1))

    path = [(x, y)]

    for _ in range(length - 1):
        # Random direction
        dx, dy = draw(st.sampled_from([(0, 1), (0, -1), (1, 0), (-1, 0)]))
        nx, ny = x + dx, y + dy

        # Stay in bounds
        if 0 <= nx < grid_width and 0 <= ny < grid_height:
            x, y = nx, ny
            if (x, y) not in path:  # Avoid self-intersection
                path.append((x, y))

    return path


# =============================================================================
# Net Strategies
# =============================================================================

@st.composite
def net_connectivity(
    draw,
    num_components: int,
    num_nets: int,
    pins_per_net: tuple[int, int] = (2, 5),
) -> list[list[tuple[int, int]]]:
    """
    Generate net connectivity.

    Returns list of nets, where each net is list of (component_idx, pin_idx).
    """
    nets = []

    for _ in range(num_nets):
        num_pins = draw(st.integers(min_value=pins_per_net[0], max_value=pins_per_net[1]))

        net = []
        for _ in range(num_pins):
            comp_idx = draw(st.integers(min_value=0, max_value=num_components - 1))
            pin_idx = draw(st.integers(min_value=0, max_value=10))
            net.append((comp_idx, pin_idx))

        nets.append(net)

    return nets


# =============================================================================
# Edge Case Strategies
# =============================================================================

def empty_component_list() -> st.SearchStrategy[list]:
    """Generate empty component list (edge case)."""
    return st.just([])


def single_component() -> st.SearchStrategy[list[dict]]:
    """Generate single component (edge case)."""
    return st.lists(realistic_component(), min_size=1, max_size=1)


@st.composite
def boundary_position(
    draw,
    board_width: float,
    board_height: float,
) -> tuple[float, float]:
    """Generate position exactly on board boundary (edge case)."""
    side = draw(st.integers(min_value=0, max_value=3))

    if side == 0:  # Top
        return (draw(st.floats(min_value=0, max_value=board_width)), board_height)
    elif side == 1:  # Right
        return (board_width, draw(st.floats(min_value=0, max_value=board_height)))
    elif side == 2:  # Bottom
        return (draw(st.floats(min_value=0, max_value=board_width)), 0.0)
    else:  # Left
        return (0.0, draw(st.floats(min_value=0, max_value=board_height)))


@st.composite
def outside_board_position(
    draw,
    board_width: float,
    board_height: float,
    max_distance: float = 50.0,
) -> tuple[float, float]:
    """Generate position outside board (edge case for boundary testing)."""
    side = draw(st.integers(min_value=0, max_value=3))
    distance = draw(st.floats(min_value=1.0, max_value=max_distance))

    if side == 0:  # Above
        return (draw(st.floats(min_value=0, max_value=board_width)), board_height + distance)
    elif side == 1:  # Right
        return (board_width + distance, draw(st.floats(min_value=0, max_value=board_height)))
    elif side == 2:  # Below
        return (draw(st.floats(min_value=0, max_value=board_width)), -distance)
    else:  # Left
        return (-distance, draw(st.floats(min_value=0, max_value=board_height)))
