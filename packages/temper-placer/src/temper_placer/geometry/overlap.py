"""
Component overlap detection — Rust-backed via temper_geometry.

This module provides overlap detection between PCB components using
temper_geometry's Rust implementation of signed distance functions (SDF)
and axis-aligned bounding box (AABB) approximations.

All functions delegate to the temper_geometry Rust crate.
"""
import temper_geometry as _tg

# =============================================================================
# Core Box-Box Distance Functions
# =============================================================================


def box_box_distance(ax, ay, aw, ah, bx, by, bw, bh):
    """Compute minimum distance between two axis-aligned boxes.

    Args:
        ax, ay: Center of first box
        aw, ah: Width and height of first box
        bx, by: Center of second box
        bw, bh: Width and height of second box

    Returns:
        Signed distance: positive if separated, negative if overlapping
    """
    return _tg.box_box_distance(ax, ay, aw, ah, bx, by, bw, bh)


def box_box_distance_aabb(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
    """Compute minimum distance between two axis-aligned bounding boxes.

    Args:
        ax1, ay1, ax2, ay2: First AABB corners
        bx1, by1, bx2, by2: Second AABB corners

    Returns:
        Signed distance (negative if overlapping)
    """
    return _tg.box_box_distance_aabb(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2)


# =============================================================================
# Overlap Amount and Area
# =============================================================================


def component_overlap_amount(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
    """Compute overlap amount between two components (AABB approximation).

    Args:
        ax1, ay1, ax2, ay2: First AABB corners
        bx1, by1, bx2, by2: Second AABB corners

    Returns:
        Overlap amount (0 if no overlap, positive if overlapping)
    """
    return _tg.component_overlap_amount(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2)


def overlap_area_estimate(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
    """Estimate overlap area between two AABBs.

    Args:
        ax1, ay1, ax2, ay2: First AABB corners
        bx1, by1, bx2, by2: Second AABB corners

    Returns:
        Estimated overlap area (0 if no overlap)
    """
    return _tg.overlap_area_estimate(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2)


# =============================================================================
# Batch Operations for All Pairwise Overlaps
# =============================================================================


def compute_pairwise_distances(rects):
    """Compute pairwise distances between all components.

    Args:
        rects: List of rects, each [cx, cy, w, h]

    Returns:
        Distance matrix
    """
    return _tg.compute_pairwise_distances(rects)


def compute_total_overlap(rects):
    """Compute total overlap amount for all component pairs.

    Args:
        rects: List of rects, each [cx, cy, w, h]

    Returns:
        Total overlap amount (scalar)
    """
    return _tg.compute_total_overlap(rects)


def compute_overlap_penalty(rects, weight=100.0):
    """Compute squared overlap penalty for use in loss function.

    Args:
        rects: List of rects, each [cx, cy, w, h]
        weight: Penalty weight

    Returns:
        Weighted squared overlap penalty (scalar)
    """
    return _tg.compute_overlap_penalty(rects, weight)


# =============================================================================
# Clearance Checking
# =============================================================================


def check_clearance_violation(rects, clearance_mm):
    """Check if minimum clearance between components is violated.

    Args:
        rects: List of rects, each [cx, cy, w, h]
        clearance_mm: Required minimum clearance

    Returns:
        Clearance violation amounts
    """
    return _tg.check_clearance_violation(rects, clearance_mm)


def compute_clearance_penalties(rects, clearances):
    """Compute clearance violation penalties for all pairs.

    Args:
        rects: List of rects, each [cx, cy, w, h]
        clearances: Clearance matrix values

    Returns:
        Total clearance violation penalty (scalar)
    """
    return _tg.compute_clearance_penalties(rects, clearances)


# =============================================================================
# Overlap Statistics
# =============================================================================


def count_overlaps(rects):
    """Count number of overlapping component pairs.

    Args:
        rects: List of rects, each [cx, cy, w, h]

    Returns:
        Number of overlapping pairs
    """
    return _tg.count_overlaps(rects)


def get_worst_overlap(rects):
    """Find the worst (most severe) overlap between any two components.

    Args:
        rects: List of rects, each [cx, cy, w, h]

    Returns:
        (worst_overlap_amount, component_i, component_j)
    """
    return _tg.get_worst_overlap(rects)
