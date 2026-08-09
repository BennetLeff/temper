"""
Aesthetic quality metrics for PCB placement.

This module provides functions to quantify the "visual professionalism"
of a layout, which correlates with manufacturability and ease of inspection.
"""

from __future__ import annotations

import numpy as np
import temper_quality_oracle as _tqo

from temper_placer.core.state import PlacementState


def compute_aesthetic_score(
    state: PlacementState,
    netlist,  # noqa: ARG001  # API compatibility; see docstring
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
    # The numeric kernel lives in temper-quality-oracle
    # (temper_quality_oracle.aesthetic_score_py).  The `*_are_f32` flags
    # carry the source array dtypes so the kernel reproduces the numpy
    # NEP 50 chains bit-for-bit: with float32 state (the PlacementState
    # default), `np.mod` / `np.minimum` / `< 0.01` and `np.argmax` all run
    # in float32.  `netlist` is accepted for API compatibility but no longer
    # consulted: the prefix-group alignment machinery was retired with the
    # JAX migration, and the module's own default makes `prefix_alignment_score`
    # a constant 1.0 when no groups exist (recorded divergence, see
    # packages/temper-quality-oracle/VERIFICATION.md).
    positions = np.asarray(state.positions)
    rotations = np.asarray(state.rotation_logits)
    positions_are_f32 = positions.dtype == np.float32
    rotations_are_f32 = rotations.dtype == np.float32
    return dict(
        _tqo.aesthetic_score_py(
            [tuple(r) for r in positions.tolist()],
            [tuple(r) for r in rotations.tolist()],
            grid_size,
            positions_are_f32,
            rotations_are_f32,
        )
    )
