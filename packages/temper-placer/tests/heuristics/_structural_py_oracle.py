"""Pinned Python oracle for Wave-4 heuristics/ Phase B -- ``create_keepout_mask``.

DO NOT EDIT -- THIS IS THE REFERENCE.
======================================
``create_keepout_mask`` below is a **verbatim** ``git show`` extraction from
commit ``d5f4593142da87c75f9b21734e0e65d0e991f16d`` (``origin/main`` tip at
the time this migration was pulled; the function itself last changed in
``b9c766059c34649c2947f04f89a578fdb48a2756``, "make component placement
independent of PYTHONHASHSEED", which did not touch this function -- the
text is identical at both commits) of
``packages/temper-placer/src/temper_placer/heuristics/structural.py``.

Nothing here has been cleaned up, refactored, reformatted, or fixed. The
only change from the source file is import scoping: the surrounding
classes (``KeepoutAwarenessHeuristic`` and everything below it) are not
copied, because they are orchestration (netlist iteration, logging,
``HeuristicResult`` construction) around this one compute kernel, not part
of the kernel itself. ``test_oracle_is_verbatim_copy`` in the differential
suite re-extracts the function from the pinned commit via ``git show`` and
compares the source text character for character, so any drift here (a
"helpful" fix, a reformat, anything) fails CI rather than passing quietly.

Why this is the module singled out for Phase B
------------------------------------------------
``heuristics/`` is dominated by netlist/regex orchestration (component
classification, dict bookkeeping, ``HeuristicResult`` assembly) around a
handful of scalar arithmetic call sites. ``create_keepout_mask`` is the
one exception: it builds a full ``(H, W)`` boolean numpy array via
``np.ones`` plus three keepout passes (board-edge margin, circular
mounting-hole clearance, rectangular keepout regions) -- genuine
array-shaped compute, not just a few floats. It is the largest, and only
substantial, pure-compute block in the package (see
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``
Phase 5, and the PR description for the fuller heuristics/ survey).

Traps this pin exercises (see
``packages/temper-geometry/src/heuristics_geometry.rs`` module doc for the
Rust-side mirror of each)
--------------------------------------------------------------------------
* ``int(x)`` truncation toward zero for ``margin_cells``, ``cx``/``cy``/``cr``
  (mounting holes), and the per-region ``mx_min``/``my_min``/``mx_max``/``my_max``
  -- all computed from float division, all truncated toward zero, never
  floored.
* ``mask[-margin_cells:, :] = False`` -- a **literal negative slice**, whose
  start clamps to ``max(height_cells - margin_cells, 0)``, guarded entirely
  behind ``if margin_cells > 0``.
* The keepout-region loop computes ``mx_max = min(width_cells, int(...) + 1)``
  from a *plain int variable*, not a slice literal. When that computed value
  is itself negative (a keepout region whose buffered edge lies to the left
  of / above the board), Python's slicing semantics for
  ``mask[my_min:my_max, mx_min:mx_max]`` treat the negative bound as
  "count back from the end", not "clamp to zero" -- a materially different
  result from the naive Rust port (``.max(0)``) that this pin's differential
  test ``test_keepout_region_bound_going_negative_counts_from_end`` measures
  directly against a hand ray-traced expectation.
* Every pass in this function only ever writes ``False`` -- never restores
  ``True`` -- so the three keepout sources compose as a set union,
  independent of application order. This is asserted by
  ``test_hole_and_region_ordering_is_order_independent``, precisely because
  a reimplementation might be tempted to assume the JIT-rasteriser
  convention elsewhere in the repo (``grid_raster.rs``) where net-id merge
  order DOES matter, and get this one wrong by analogy.
"""

from __future__ import annotations

from typing import TypeAlias

import numpy as np
from numpy.typing import NDArray

from temper_placer.core.board import Board
from temper_placer.io.config_loader import PlacementConstraints

Array: TypeAlias = NDArray


def create_keepout_mask(
    board: Board,
    constraints: PlacementConstraints,
    resolution_mm: float = 1.0,
    buffer_mm: float = 1.0,
) -> Array:
    """
    Create a placement mask where True = valid placement, False = keep-out.

    This generates a 2D boolean array covering the board area at the given
    resolution. Keep-out regions include:
    - Board edges (board margin)
    - Mounting hole clearance zones
    - Explicit keepout_regions from board definition
    - Explicit zones from config (if any are marked as keepout)

    Args:
        board: Board definition with mounting holes, keepouts, etc.
        constraints: Placement constraints (board margin, etc.)
        resolution_mm: Grid resolution in mm (default 1.0)
        buffer_mm: Additional buffer around keepouts

    Returns:
        (H, W) boolean JAX array where True = valid for placement
    """
    ox, oy = board.origin
    width_cells = int(board.width / resolution_mm) + 1
    height_cells = int(board.height / resolution_mm) + 1

    # Start with all valid
    mask = np.ones((height_cells, width_cells), dtype=np.bool_)

    # Mark board edges as invalid (margin)
    margin = constraints.board_margin_mm + buffer_mm
    margin_cells = int(margin / resolution_mm)

    if margin_cells > 0:
        # Top and bottom edges
        mask[:margin_cells, :] = False
        mask[-margin_cells:, :] = False
        # Left and right edges
        mask[:, :margin_cells] = False
        mask[:, -margin_cells:] = False

    # Mark mounting holes as invalid
    for hole in board.mounting_holes:
        hx, hy = hole.position
        clearance = hole.keepout_radius + buffer_mm

        # Convert to mask coordinates
        cx = int((hx - ox) / resolution_mm)
        cy = int((hy - oy) / resolution_mm)
        cr = int(clearance / resolution_mm)

        # Create circular keepout
        for dy in range(-cr, cr + 1):
            for dx in range(-cr, cr + 1):
                if dx * dx + dy * dy <= cr * cr:
                    mx, my = cx + dx, cy + dy
                    if 0 <= mx < width_cells and 0 <= my < height_cells:
                        mask[my, mx] = False

    # Mark explicit keepout regions
    for x_min, y_min, x_max, y_max in board.keepout_regions:
        # Add buffer
        x_min_buf = x_min - buffer_mm
        y_min_buf = y_min - buffer_mm
        x_max_buf = x_max + buffer_mm
        y_max_buf = y_max + buffer_mm

        # Convert to mask coordinates
        mx_min = max(0, int((x_min_buf - ox) / resolution_mm))
        my_min = max(0, int((y_min_buf - oy) / resolution_mm))
        mx_max = min(width_cells, int((x_max_buf - ox) / resolution_mm) + 1)
        my_max = min(height_cells, int((y_max_buf - oy) / resolution_mm) + 1)

        mask[my_min:my_max, mx_min:mx_max] = False

    return mask
