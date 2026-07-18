"""Regression test for the njit fallback shim in clearance_grid.py.

Covers the bug documented in docs/solutions/dependency-issues/
njit-fallback-shim-discards-function-on-bare-decorator-2026-07-17.md:
when numba fails to import (e.g. a NumPy version incompatibility), the
fallback `def njit(*args, **kwargs): return lambda f: f` is only correct
for the `@njit(...)` call style. For the bare `@njit` style (used by
_block_circle_numba and _block_segment_numba in this file), Python calls
`njit(func)` directly -- the fallback discarded `func` entirely and
returned a generic `lambda f: f` in its place, silently replacing the
real function with a useless 1-argument identity lambda. Any real call
then crashed with a confusing arity TypeError that gives no hint the
actual cause is numba being unavailable.

This test calls the decorated functions directly with real arguments --
if the shim is broken, this raises TypeError regardless of whether numba
is actually installed in the test environment (the real numba-compiled
function has the same call signature and would also accept these args).
"""

import numpy as np

from temper_placer.deterministic.stages.clearance_grid import (
    _block_circle_numba,
    _block_segment_numba,
)


def test_block_circle_numba_is_callable_with_real_arguments():
    grid = np.zeros((20, 20), dtype=np.int32)
    _block_circle_numba(
        grid, 5.0, 5.0, 3.0, 42, 1.0, 0, 20, 0, 20
    )
    assert (grid == 42).any(), "expected at least one cell inside the circle to be blocked"
    assert grid[5, 5] == 42


def test_block_segment_numba_is_callable_with_real_arguments():
    grid = np.zeros((20, 20), dtype=np.int32)
    _block_segment_numba(
        grid, 0.0, 0.0, 10.0, 10.0, 1.0, 7, 1.0, 0, 20, 0, 20
    )
    assert (grid == 7).any(), "expected at least one cell along the segment to be blocked"
