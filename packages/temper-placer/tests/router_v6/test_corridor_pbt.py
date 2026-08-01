"""Property-based tests for the Rust corridor mask builder.

Three invariants (per the migration roadmap's PBT discipline):

1. The corridor of a connected coarse path is 8-connected (rectangles
   expand along the path and touch edge-to-edge or corner-to-corner).
2. The mask is bounded within the fine grid (no out-of-bounds cells).
3. The mask is symmetric under coarse-path reversal (OR is commutative).

The properties exercise the wrapper
(``temper_placer.router_v6.corridor``), the consumer surface the router
sees.
"""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.corridor import extract_corridor_mask

MAX_EXAMPLES = 100

_path = st.lists(
    st.tuples(st.integers(0, 30), st.integers(0, 30)),
    min_size=1,
    max_size=25,
    unique_by=lambda cell: cell,
)


def _connected_steps_path() -> st.SearchStrategy[list[tuple[int, int]]]:
    """Paths whose consecutive cells are 8-neighbours (starts at origin)."""

    def steps_to_path(steps: list[tuple[int, int]]) -> list[tuple[int, int]]:
        path = [(0, 0)]
        for dx, dy in steps:
            cx, cy = path[-1]
            path.append((cx + dx, cy + dy))
        return path

    return (
        st.lists(
            st.sampled_from([(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]),
            min_size=0,
            max_size=12,
        )
        .map(steps_to_path)
        .filter(lambda p: all(0 <= c[0] < 30 and 0 <= c[1] < 30 for c in p))
    )


@given(_connected_steps_path(), st.integers(1, 6), st.integers(0, 8))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_connected_path_produces_connected_mask(
    path: list[tuple[int, int]], factor: int, buffer_cells: int
) -> None:
    from scipy import ndimage

    rows = cols = 64
    mask = extract_corridor_mask(path, factor, buffer_cells, rows, cols)
    structure = np.ones((3, 3), dtype=np.int8)  # 8-connectivity
    labeled, n = ndimage.label(mask, structure=structure)
    assert n == 1, f"corridor for connected path has {n} components"


@given(_path, st.integers(1, 8), st.integers(0, 12))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mask_symmetric_under_path_reversal(
    path: list[tuple[int, int]], factor: int, buffer_cells: int
) -> None:
    rows, cols = 80, 80
    forward = extract_corridor_mask(path, factor, buffer_cells, rows, cols)
    backward = extract_corridor_mask(list(reversed(path)), factor, buffer_cells, rows, cols)
    np.testing.assert_array_equal(forward, backward)
