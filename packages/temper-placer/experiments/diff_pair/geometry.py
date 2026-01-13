"""
Geometry Helpers for Differential Pair Routing

Provides functions for corner geometry, serpentine generation, and spacing calculations.
"""

from typing import List, Tuple
import math


def calculate_spacing(pos: Tuple[float, float], neg: Tuple[float, float]) -> float:
    """
    Calculate Euclidean distance between P and N positions.

    Args:
        pos: (x, y) position of P trace in mm
        neg: (x, y) position of N trace in mm

    Returns:
        Distance in mm
    """
    dx = pos[0] - neg[0]
    dy = pos[1] - neg[1]
    return math.sqrt(dx * dx + dy * dy)


def is_45_degree_angle(
    p1: Tuple[float, float], p2: Tuple[float, float], p3: Tuple[float, float]
) -> bool:
    """
    Check if three points form a 45° or 90° angle (valid for mitered corners).

    Args:
        p1, p2, p3: Three consecutive points defining the angle at p2

    Returns:
        True if angle is 45° or 90° (valid), False otherwise
    """
    # Calculate vectors
    v1 = (p1[0] - p2[0], p1[1] - p2[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])

    # Calculate angle using dot product
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    mag2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)

    if mag1 == 0 or mag2 == 0:
        return False

    cos_angle = dot / (mag1 * mag2)
    angle_rad = math.acos(max(-1, min(1, cos_angle)))  # Clamp to [-1, 1]
    angle_deg = math.degrees(angle_rad)

    # Allow 45° and 90° with small tolerance
    return abs(angle_deg - 45) < 5 or abs(angle_deg - 90) < 5 or abs(angle_deg - 135) < 5


def generate_trombone_serpentine(
    start_pos: Tuple[float, float],
    direction: Tuple[float, float],  # Unit vector of trace direction
    required_length_mm: float,
    width_mm: float = 1.0,
    spacing_mm: float = 0.5,
) -> List[Tuple[float, float]]:
    """
    Generate a trombone (rectangular) serpentine to add length to a trace.

    Args:
        start_pos: Starting position (x, y) in mm
        direction: Unit vector indicating trace direction
        required_length_mm: Additional length needed
        width_mm: Width of serpentine bump
        spacing_mm: Spacing between serpentine legs

    Returns:
        List of waypoints for the serpentine path
    """
    # TODO: Implement in EXP-4
    # For now, return empty list
    return []


def offset_parallel_traces(
    centerline_path: List[Tuple[float, float]], offset_distance: float
) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """
    Create parallel offset paths from a centerline path.

    This is used to visualize how post-processing offset would work
    (for comparison with the coupled router approach).

    Args:
        centerline_path: List of (x, y) waypoints
        offset_distance: Distance to offset (half of spacing)

    Returns:
        (pos_path, neg_path) - Offset paths for P and N traces
    """
    pos_path = []
    neg_path = []

    for i, (x, y) in enumerate(centerline_path):
        # Calculate perpendicular direction
        if i > 0:
            # Use direction from previous point
            dx = x - centerline_path[i - 1][0]
            dy = y - centerline_path[i - 1][1]
        elif i < len(centerline_path) - 1:
            # Use direction to next point
            dx = centerline_path[i + 1][0] - x
            dy = centerline_path[i + 1][1] - y
        else:
            # Single point, use default
            dx, dy = 1, 0

        # Normalize
        length = math.sqrt(dx * dx + dy * dy)
        if length > 0:
            dx /= length
            dy /= length

        # Perpendicular (rotate 90°)
        perp_x = -dy
        perp_y = dx

        # Offset positions
        pos_path.append((x + perp_x * offset_distance, y + perp_y * offset_distance))
        neg_path.append((x - perp_x * offset_distance, y - perp_y * offset_distance))

    return pos_path, neg_path
