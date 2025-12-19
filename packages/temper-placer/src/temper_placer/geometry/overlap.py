"""
Component overlap detection for temper-placer.

This module provides differentiable overlap detection between PCB components.
Uses signed distance functions (SDF) and axis-aligned bounding box (AABB)
approximations for efficient, gradient-friendly overlap computation.

Key features:
- Differentiable overlap detection for gradient-based optimization
- Support for rotated components via AABB approximation
- Batch operations for computing all pairwise overlaps efficiently
- Smooth penalties suitable for loss functions
"""


import jax.numpy as jnp
from jax import Array

from temper_placer.geometry.smooth import smooth_relu
from temper_placer.geometry.transform import get_rotated_bounds

# =============================================================================
# Core Box-Box Distance Functions
# =============================================================================


def box_box_distance(
    pos1: Array,
    rot1: Array,
    width1: float,
    height1: float,
    pos2: Array,
    rot2: Array,
    width2: float,
    height2: float,
) -> Array:
    """
    Compute minimum distance between two rotated boxes.

    Uses AABB approximation: computes axis-aligned bounding boxes of rotated
    rectangles, then computes distance between AABBs. This is slightly
    conservative (may report overlap when corners just touch) but is
    efficient and differentiable.

    Args:
        pos1: Center of first box as (x, y) array
        rot1: Rotation of first box as one-hot vector (4,)
        width1: Width of first box (before rotation)
        height1: Height of first box (before rotation)
        pos2: Center of second box as (x, y) array
        rot2: Rotation of second box as one-hot vector (4,)
        width2: Width of second box (before rotation)
        height2: Height of second box (before rotation)

    Returns:
        Signed distance between boxes:
        - Positive: boxes are separated by this distance
        - Zero: boxes are touching
        - Negative: boxes overlap by this amount
    """
    # Get rotated bounds (accounting for width/height swap at 90°/270°)
    rw1, rh1 = get_rotated_bounds(width1, height1, rot1)
    rw2, rh2 = get_rotated_bounds(width2, height2, rot2)

    # Compute half-dimensions
    half_w1, half_h1 = rw1 / 2.0, rh1 / 2.0
    half_w2, half_h2 = rw2 / 2.0, rh2 / 2.0

    # Compute gaps in each dimension
    # Gap = center distance - sum of half-dimensions
    # Positive gap = separated, negative gap = overlapping
    gap_x = jnp.abs(pos1[0] - pos2[0]) - (half_w1 + half_w2)
    gap_y = jnp.abs(pos1[1] - pos2[1]) - (half_h1 + half_h2)

    # If both gaps are negative, boxes overlap
    # The overlap amount is min(|gap_x|, |gap_y|) in the most restrictive dimension
    # If at least one gap is positive, boxes are separated
    # The separation is the max of the gaps (need to cross both to overlap)

    # For separated boxes: distance = max(gap_x, gap_y) [need both to overlap]
    # For overlapping boxes: penetration = -min(gap_x, gap_y) [negative distance]

    # When both gaps are negative (overlapping), we want the smaller absolute value
    # When at least one is positive (separated), we want the larger (positive) value

    both_negative = (gap_x < 0) & (gap_y < 0)

    # Use differentiable selection
    # Overlap case: min(gap_x, gap_y) [most negative = largest overlap]
    # Separated case: max(gap_x, gap_y) [most positive = true separation]
    overlap_dist = jnp.minimum(gap_x, gap_y)  # Both negative, want min (most overlap)
    separated_dist = jnp.maximum(gap_x, gap_y)  # At least one positive

    # Soft selection between cases
    # When both_negative is True (1.0), use overlap_dist
    # When both_negative is False (0.0), use separated_dist
    return jnp.where(both_negative, overlap_dist, separated_dist)


def box_box_distance_aabb(
    min1: Array,
    max1: Array,
    min2: Array,
    max2: Array,
) -> Array:
    """
    Compute minimum distance between two axis-aligned bounding boxes.

    Simpler version when AABB corners are already computed.

    Args:
        min1, max1: First AABB corners
        min2, max2: Second AABB corners

    Returns:
        Signed distance between boxes (negative if overlapping)
    """
    # Compute gaps in each dimension
    gap_x = jnp.maximum(min1[0] - max2[0], min2[0] - max1[0])
    gap_y = jnp.maximum(min1[1] - max2[1], min2[1] - max1[1])

    # Handle separated vs overlapping cases
    both_negative = (gap_x < 0) & (gap_y < 0)
    overlap_dist = jnp.minimum(gap_x, gap_y)
    separated_dist = jnp.maximum(gap_x, gap_y)

    return jnp.where(both_negative, overlap_dist, separated_dist)


# =============================================================================
# Overlap Amount and Area
# =============================================================================


def component_overlap_amount(
    pos1: Array,
    rot1: Array,
    width1: float,
    height1: float,
    pos2: Array,
    rot2: Array,
    width2: float,
    height2: float,
) -> Array:
    """
    Compute overlap amount between two rotated components.

    Returns positive value for overlapping components, zero otherwise.
    The amount is an approximation of how much the boxes overlap.

    Args:
        pos1, rot1, width1, height1: First component parameters
        pos2, rot2, width2, height2: Second component parameters

    Returns:
        Overlap amount (0 if no overlap, positive if overlapping)
    """
    distance = box_box_distance(pos1, rot1, width1, height1, pos2, rot2, width2, height2)
    # Overlap is the negative of distance when overlapping
    # Use smooth_relu for differentiability
    return smooth_relu(-distance, beta=10.0)


def overlap_area_estimate(
    pos1: Array,
    rot1: Array,
    width1: float,
    height1: float,
    pos2: Array,
    rot2: Array,
    width2: float,
    height2: float,
) -> Array:
    """
    Estimate overlap area between two rotated boxes.

    Computes the actual intersection area of the AABBs, which is a good
    proxy for overlap severity.

    Args:
        pos1, rot1, width1, height1: First component parameters
        pos2, rot2, width2, height2: Second component parameters

    Returns:
        Estimated overlap area (0 if no overlap)
    """
    # Get rotated bounds
    rw1, rh1 = get_rotated_bounds(width1, height1, rot1)
    rw2, rh2 = get_rotated_bounds(width2, height2, rot2)

    # Compute AABB corners
    min1 = pos1 - jnp.array([rw1 / 2, rh1 / 2])
    max1 = pos1 + jnp.array([rw1 / 2, rh1 / 2])
    min2 = pos2 - jnp.array([rw2 / 2, rh2 / 2])
    max2 = pos2 + jnp.array([rw2 / 2, rh2 / 2])

    # Compute intersection dimensions
    # Intersection is [max(min1, min2), min(max1, max2)]
    inter_min = jnp.maximum(min1, min2)
    inter_max = jnp.minimum(max1, max2)

    # Intersection dimensions (clamped to >= 0)
    inter_dims = jnp.maximum(inter_max - inter_min, 0.0)

    # Area is product of dimensions
    return inter_dims[0] * inter_dims[1]


# =============================================================================
# Batch Operations for All Pairwise Overlaps
# =============================================================================


def compute_pairwise_distances(
    positions: Array,
    rotations: Array,
    widths: Array,
    heights: Array,
) -> Array:
    """
    Compute pairwise distances between all components.

    Args:
        positions: Component centers as (N, 2) array
        rotations: Component rotations as (N, 4) one-hot array
        widths: Component widths as (N,) array
        heights: Component heights as (N,) array

    Returns:
        Distance matrix of shape (N, N) where element [i, j] is the
        signed distance between components i and j. Diagonal is 0.
    """
    n = positions.shape[0]

    # Get rotated bounds for all components
    # Swap weights: [0°, 90°, 180°, 270°] -> [0, 1, 0, 1]
    swap_weights = jnp.array([0.0, 1.0, 0.0, 1.0])
    swap_amounts = rotations @ swap_weights  # (N,)

    rotated_widths = widths * (1 - swap_amounts) + heights * swap_amounts
    rotated_heights = heights * (1 - swap_amounts) + widths * swap_amounts

    # Half dimensions
    half_w = rotated_widths / 2.0  # (N,)
    half_h = rotated_heights / 2.0  # (N,)

    # Compute pairwise center distances
    # positions[:, None, :] - positions[None, :, :] gives (N, N, 2)
    center_diff = positions[:, None, :] - positions[None, :, :]
    center_dist_x = jnp.abs(center_diff[:, :, 0])  # (N, N)
    center_dist_y = jnp.abs(center_diff[:, :, 1])  # (N, N)

    # Sum of half-dimensions for each pair
    # half_w[:, None] + half_w[None, :] gives (N, N)
    sum_half_w = half_w[:, None] + half_w[None, :]
    sum_half_h = half_h[:, None] + half_h[None, :]

    # Compute gaps
    gap_x = center_dist_x - sum_half_w
    gap_y = center_dist_y - sum_half_h

    # Distance computation (same logic as box_box_distance)
    both_negative = (gap_x < 0) & (gap_y < 0)
    overlap_dist = jnp.minimum(gap_x, gap_y)
    separated_dist = jnp.maximum(gap_x, gap_y)

    distances = jnp.where(both_negative, overlap_dist, separated_dist)

    # Zero out diagonal (component vs itself)
    distances = distances.at[jnp.diag_indices(n)].set(0.0)

    return distances


def compute_total_overlap(
    positions: Array,
    rotations: Array,
    widths: Array,
    heights: Array,
) -> Array:
    """
    Compute total overlap amount for all component pairs.

    This is the sum of overlap amounts for all pairs, suitable for use
    as a loss function term.

    Args:
        positions: Component centers as (N, 2) array
        rotations: Component rotations as (N, 4) one-hot array
        widths: Component widths as (N,) array
        heights: Component heights as (N,) array

    Returns:
        Total overlap amount (scalar). Zero if no overlaps.
    """
    distances = compute_pairwise_distances(positions, rotations, widths, heights)

    # Convert negative distances (overlaps) to positive overlap amounts
    overlaps = smooth_relu(-distances, beta=10.0)

    # Sum upper triangle only (avoid double counting)
    # Use triu_indices to get upper triangle
    n = positions.shape[0]
    i_upper, j_upper = jnp.triu_indices(n, k=1)

    return jnp.sum(overlaps[i_upper, j_upper])


def compute_overlap_penalty(
    positions: Array,
    rotations: Array,
    widths: Array,
    heights: Array,
    penalty_weight: float = 100.0,
) -> Array:
    """
    Compute squared overlap penalty for use in loss function.

    Uses squared overlap for stronger gradient when heavily overlapping.

    Args:
        positions: Component centers as (N, 2) array
        rotations: Component rotations as (N, 4) one-hot array
        widths: Component widths as (N,) array
        heights: Component heights as (N,) array
        penalty_weight: Weight for the penalty term

    Returns:
        Weighted squared overlap penalty (scalar)
    """
    distances = compute_pairwise_distances(positions, rotations, widths, heights)

    # Squared overlap penalty
    overlaps = smooth_relu(-distances, beta=10.0)
    squared_overlaps = overlaps**2

    # Sum upper triangle
    n = positions.shape[0]
    i_upper, j_upper = jnp.triu_indices(n, k=1)

    return penalty_weight * jnp.sum(squared_overlaps[i_upper, j_upper])


# =============================================================================
# Clearance Checking
# =============================================================================


def check_clearance_violation(
    pos1: Array,
    rot1: Array,
    width1: float,
    height1: float,
    pos2: Array,
    rot2: Array,
    width2: float,
    height2: float,
    min_clearance: float,
) -> Array:
    """
    Check if minimum clearance between two components is violated.

    Args:
        pos1, rot1, width1, height1: First component parameters
        pos2, rot2, width2, height2: Second component parameters
        min_clearance: Required minimum clearance between components

    Returns:
        Clearance violation amount (0 if satisfied, positive if violated)
    """
    distance = box_box_distance(pos1, rot1, width1, height1, pos2, rot2, width2, height2)

    # Violation occurs when distance < min_clearance
    violation = smooth_relu(min_clearance - distance, beta=10.0)
    return violation


def compute_clearance_penalties(
    positions: Array,
    rotations: Array,
    widths: Array,
    heights: Array,
    clearance_matrix: Array,
) -> Array:
    """
    Compute clearance violation penalties for all pairs.

    Args:
        positions: Component centers as (N, 2) array
        rotations: Component rotations as (N, 4) one-hot array
        widths: Component widths as (N,) array
        heights: Component heights as (N,) array
        clearance_matrix: (N, N) array of required clearances between pairs

    Returns:
        Total clearance violation penalty (scalar)
    """
    distances = compute_pairwise_distances(positions, rotations, widths, heights)

    # Violation where distance < required clearance
    violations = smooth_relu(clearance_matrix - distances, beta=10.0)
    squared_violations = violations**2

    # Sum upper triangle
    n = positions.shape[0]
    i_upper, j_upper = jnp.triu_indices(n, k=1)

    return jnp.sum(squared_violations[i_upper, j_upper])


# =============================================================================
# Overlap Statistics
# =============================================================================


def count_overlaps(
    positions: Array,
    rotations: Array,
    widths: Array,
    heights: Array,
    threshold: float = 0.0,
) -> int:
    """
    Count number of overlapping component pairs.

    Note: This function is not differentiable due to discrete counting.
    Use for metrics/reporting only.

    Args:
        positions: Component centers as (N, 2) array
        rotations: Component rotations as (N, 4) one-hot array
        widths: Component widths as (N,) array
        heights: Component heights as (N,) array
        threshold: Minimum overlap to count (default 0 = any overlap)

    Returns:
        Number of overlapping pairs
    """
    distances = compute_pairwise_distances(positions, rotations, widths, heights)

    # Count pairs with distance < -threshold (overlapping by at least threshold)
    n = positions.shape[0]
    i_upper, j_upper = jnp.triu_indices(n, k=1)
    upper_distances = distances[i_upper, j_upper]

    return int(jnp.sum(upper_distances < -threshold))


def get_worst_overlap(
    positions: Array,
    rotations: Array,
    widths: Array,
    heights: Array,
) -> tuple[Array, int, int]:
    """
    Find the worst (most severe) overlap between any two components.

    Args:
        positions: Component centers as (N, 2) array
        rotations: Component rotations as (N, 4) one-hot array
        widths: Component widths as (N,) array
        heights: Component heights as (N,) array

    Returns:
        Tuple of (worst_overlap_amount, component_i, component_j)
        If no overlaps, returns (0, -1, -1)
    """
    distances = compute_pairwise_distances(positions, rotations, widths, heights)

    # Set diagonal to large positive value to ignore
    n = positions.shape[0]
    distances = distances.at[jnp.diag_indices(n)].set(jnp.inf)

    # Find minimum distance (most negative = worst overlap)
    min_idx = jnp.argmin(distances)
    min_dist = distances.ravel()[min_idx]

    i = min_idx // n
    j = min_idx % n

    # Overlap amount is negative of distance (positive when overlapping)
    overlap_amount = jnp.maximum(0.0, -min_dist)

    return overlap_amount, int(i), int(j)
