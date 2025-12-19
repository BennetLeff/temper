"""
Aesthetic quality metrics for PCB placement.

This module provides functions to quantify the "visual professionalism"
of a layout, which correlates with manufacturability and ease of inspection.
"""

from __future__ import annotations

import numpy as np

from temper_placer.core.state import PlacementState
from temper_placer.losses.aesthetic import get_prefix_groups


def compute_aesthetic_score(
    state: PlacementState,
    netlist,
    grid_size: float = 0.5,
) -> dict[str, float]:
    """
    Compute a multi-factor aesthetic score for a placement.

    Scores range from 0.0 (poor) to 1.0 (perfect).

    Factors:
    1. Grid Snap: Fraction of components perfectly on grid.
    2. Alignment: How well components with same prefix align to axes.
    3. Orientation: Entropy of rotation distribution (lower is better).
    4. Compactness: Ratio of component area to bounding box area.

    Returns:
        Dictionary of individual scores and an aggregated 'aesthetic_index'.
    """
    positions = np.array(state.positions)
    rotations = np.array(state.rotation_logits)
    n = positions.shape[0]

    if n == 0:
        return {"aesthetic_index": 1.0}

    # 1. Grid Snap Score
    x_off = np.mod(positions[:, 0], grid_size)
    y_off = np.mod(positions[:, 1], grid_size)
    dist_x = np.minimum(x_off, grid_size - x_off)
    dist_y = np.minimum(y_off, grid_size - y_off)

    # Components within 0.01mm of grid are considered "snapped"
    snapped = (dist_x < 0.01) & (dist_y < 0.01)
    grid_score = np.mean(snapped)

    # 2. Orientation Score
    # Get dominant rotations
    rotation_indices = np.argmax(rotations, axis=1)
    counts = np.bincount(rotation_indices, minlength=4)
    probs = counts / n
    entropy = -np.sum(probs * np.log(probs + 1e-8))

    # Normalized entropy (max is log(4) approx 1.38)
    # Score is 1.0 if all same rotation, ~0.0 if perfectly mixed
    orientation_score = np.clip(1.0 - (entropy / 1.386), 0.0, 1.0)

    # 3. Alignment Score (Prefix-based)
    prefix_groups_arr = get_prefix_groups(netlist)
    prefix_groups = []
    if prefix_groups_arr.shape[0] > 0:
        for i in range(prefix_groups_arr.shape[0]):
            group = prefix_groups_arr[i]
            valid = group[group != -1]
            if len(valid) > 1:
                prefix_groups.append(valid)

    alignment_scores = []
    for group in prefix_groups:
        group_pos = positions[group]
        var = np.var(group_pos, axis=0)
        # If variance in either axis is very low (< 0.1mm), it's aligned
        is_aligned = np.min(var) < 0.01
        alignment_scores.append(1.0 if is_aligned else 0.0)

    alignment_score = np.mean(alignment_scores) if alignment_scores else 1.0

    # Aggregate
    aesthetic_index = (grid_score * 0.4) + (orientation_score * 0.3) + (alignment_score * 0.3)

    return {
        "grid_snap_score": float(grid_score),
        "orientation_score": float(orientation_score),
        "prefix_alignment_score": float(alignment_score),
        "aesthetic_index": float(aesthetic_index),
    }
