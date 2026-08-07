"""Differential tests: Rust occupancy-grid rasterisation kernels vs the
pre-migration pure-Python reference (Wave 4).

The kernels migrated to ``temper-geometry`` (``src/occupancy_raster.rs``):

- ``mark_path_blocked`` / ``mark_segment_blocked`` -- rectangular blocking,
  line-interpolated. NOT identical to each other: only
  ``mark_segment_blocked`` has the degenerate-steps (``steps<=0``) fallback
  that marks ``p1`` directly; ``mark_path_blocked`` silently skips a
  degenerate sub-segment.
- ``unmark_segment_blocked`` / ``unmark_path`` -- rectangular clearing,
  line-interpolated. NOT symmetric: only ``unmark_segment_blocked``
  restores the ``static_mask`` sentinel (-1); ``unmark_path`` never
  consults ``static_mask`` at all, even when the grid carries one.
- ``get_blocking_nets`` -- read-only sampling along a segment. Returns a
  Python ``set[int]``; the Rust kernel returns a sorted/deduped list, so no
  set/dict iteration order ever crosses the Rust boundary.
- ``mark_via_blocked`` -- circular blocking, per-cell integer-distance
  formula (`` ((x-cx)**2+(y-cy)**2)**0.5 * cell_size`` on grid-INDEX ints,
  not the float path-interpolation ``**2``/``**0.5``).
- ``downsample`` -- block-reduce OR-of-nonzero over ``factor``x``factor``
  sub-blocks, conservative (out-of-bounds padding cells count as blocked).

NOT migrated (see ``occupancy_raster.rs``'s module docstring and
``packages/temper-geometry/VERIFICATION.md`` for the full reasoning):

- ``build_occupancy_grid``: its hot path is ``shapely.contains()`` (GEOS)
  over points inside a polygon produced by GEOS buffer-erosion -- opaque
  library behaviour with no accessible bit-exact Rust equivalent (same
  shape of refusal as the ``np.dot``-dispatches-to-Accelerate-BLAS case
  elsewhere in this migration program).
- ``world_to_grid`` / ``grid_to_world``: trivial arithmetic, heavily used
  by OTHER router_v6 modules directly (not just internally) -- kept in
  Python; the migrated kernels below inline the identical bit-exact
  conversion themselves rather than calling back into it.
- ``is_free`` / ``is_blocked`` / ``free_cell_count`` / ``blocked_cell_count``
  / ``occupancy_ratio`` / ``width_mm`` / ``height_mm``: trivial property
  accessors (O(1) or a single vectorized numpy reduction already).
- ``mark_path_blocked_3d`` / ``OccupancyGridStage`` / ``validate_occupancy_grid``:
  orchestration / validation glue.

Traps this suite specifically pins (measured against numpy 2.4.6 / this
platform's libm):

- ``int(x)`` truncation-toward-zero for negative mm coordinates (NOT floor).
- ``int(np.ceil(x))`` raising OverflowError/ValueError for inf/nan radii or
  a zero ``cell_size`` -- where a naive ``as i64`` would saturate silently.
- Writing an out-of-int8-range ``net_id`` raises ``OverflowError`` from
  numpy's scalar-to-int8 cast, even for an EMPTY target slice; but only
  when at least one point is actually about to be written (an
  all-degenerate ``mark_path_blocked`` call never raises).
- ``mark_via_blocked``'s per-cell scalar assignment raises on the FIRST
  matching cell in row-major order, leaving earlier cells already mutated
  -- both the oracle and the Rust kernel must leave the SAME partial grid
  state behind.
"""

from __future__ import annotations

import random
import subprocess
from pathlib import Path

import numpy as np
import pytest

from temper_placer.router_v6 import occupancy_grid as occupancy_grid_module
from temper_placer.router_v6.occupancy_grid import CellState, OccupancyGrid

from ._occupancy_raster_py_oracle import _OracleOccupancyGrid
from ._occupancy_raster_py_oracle import CellState as _OracleCellState

_PINNED_COMMIT = "28366722f3f1c905877f1dc08533ac18d3d8825b"
_PINNED_PATH = "packages/temper-placer/src/temper_placer/router_v6/occupancy_grid.py"
_PINNED_LINE_RANGE = (27, 386)  # 1-indexed, inclusive: CellState .. end of mark_via_blocked
_ORACLE_FILE = Path(__file__).with_name("_occupancy_raster_py_oracle.py")


# ---------------------------------------------------------------------------
# Verbatim-copy check: the oracle file must be an EXACT git-show extraction
# of the pinned commit/line-range, modulo the single documented rename.
# ---------------------------------------------------------------------------


def test_oracle_is_verbatim_copy():
    repo_root = Path(__file__).resolve()
    while not (repo_root / ".git").exists():
        repo_root = repo_root.parent
    result = subprocess.run(
        ["git", "show", f"{_PINNED_COMMIT}:{_PINNED_PATH}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    lines = result.stdout.splitlines(keepends=True)
    start, end = _PINNED_LINE_RANGE
    extracted = "".join(lines[start - 1 : end])
    renamed = extracted.replace("OccupancyGrid", "_OracleOccupancyGrid")

    oracle_text = _ORACLE_FILE.read_text()
    assert renamed in oracle_text, (
        "The pinned commit's CellState + OccupancyGrid class body (with the "
        "single OccupancyGrid -> _OracleOccupancyGrid rename) is no longer "
        "byte-identical to _occupancy_raster_py_oracle.py -- the oracle has "
        "drifted from its pin."
    )


# ---------------------------------------------------------------------------
# Wiring: the shipped module must actually delegate. Monkeypatch each Rust
# entry point to raise a distinctive marker exception, call the shipped
# OccupancyGrid method, and require the marker to propagate -- proving the
# method calls into temper_geometry rather than doing its own computation.
# ---------------------------------------------------------------------------


class _WiringMarker(RuntimeError):
    """Distinctive exception raised by a monkeypatched Rust entry point."""


def _raise_marker(*_args, **_kwargs):
    raise _WiringMarker("kernel called")


def _make_grid(w=10, h=10, cell_size=1.0, static_mask=None):
    return OccupancyGrid(
        "F.Cu", np.zeros((h, w), dtype=np.int8), (0.0, 0.0), cell_size, w, h, static_mask
    )


def test_mark_path_blocked_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(occupancy_grid_module._tg, "mark_path_rect_into_grid_py", _raise_marker)
    grid = _make_grid()
    with pytest.raises(_WiringMarker):
        grid.mark_path_blocked([(1.0, 1.0), (2.0, 2.0)], 0.2, 0.1, 5)


def test_mark_segment_blocked_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(occupancy_grid_module._tg, "mark_segment_rect_into_grid_py", _raise_marker)
    grid = _make_grid()
    with pytest.raises(_WiringMarker):
        grid.mark_segment_blocked((1.0, 1.0), (2.0, 2.0), 0.2, 0.1, 5)


def test_unmark_segment_blocked_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(
        occupancy_grid_module._tg, "unmark_segment_rect_into_grid_py", _raise_marker
    )
    grid = _make_grid()
    with pytest.raises(_WiringMarker):
        grid.unmark_segment_blocked((1.0, 1.0), (2.0, 2.0), 0.2, 0.1, 5)


def test_unmark_path_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(occupancy_grid_module._tg, "unmark_path_rect_into_grid_py", _raise_marker)
    grid = _make_grid()
    with pytest.raises(_WiringMarker):
        grid.unmark_path([(1.0, 1.0), (2.0, 2.0)], 0.2, 0.1, 5)


def test_get_blocking_nets_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(occupancy_grid_module._tg, "blocking_net_ids_py", _raise_marker)
    grid = _make_grid()
    with pytest.raises(_WiringMarker):
        grid.get_blocking_nets((1.0, 1.0), (2.0, 2.0))


def test_mark_via_blocked_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(occupancy_grid_module._tg, "mark_via_circle_into_grid_py", _raise_marker)
    grid = _make_grid()
    with pytest.raises(_WiringMarker):
        grid.mark_via_blocked(5.0, 5.0, 0.6, 0.1, 5)


def test_downsample_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(occupancy_grid_module._tg, "downsample_or_blocks_py", _raise_marker)
    grid = _make_grid()
    with pytest.raises(_WiringMarker):
        grid.downsample(2)


# ---------------------------------------------------------------------------
# Fixture builders for the randomized differential
# ---------------------------------------------------------------------------


def _paired_grids(rng: random.Random, w: int, h: int, cell_size: float, with_static: bool):
    """Return (real, oracle) OccupancyGrid pair sharing identical initial
    state (independent numpy arrays -- mutation of one must not touch the
    other)."""
    base = rng.choice([0, -1])
    arr = np.full((h, w), base, dtype=np.int8)
    # Scatter a handful of pre-existing "already routed" cells so
    # unmark/get_blocking_nets have real net occupancy to interact with.
    for _ in range(rng.randint(0, 5)):
        r, c = rng.randrange(h), rng.randrange(w)
        arr[r, c] = rng.choice([1, 2, 3, 7, 11])
    static = None
    if with_static:
        static = arr == -1
    real = OccupancyGrid("F.Cu", arr.copy(), (0.0, 0.0), cell_size, w, h, static.copy() if static is not None else None)
    oracle = _OracleOccupancyGrid(
        "F.Cu", arr.copy(), (0.0, 0.0), cell_size, w, h, static.copy() if static is not None else None
    )
    return real, oracle


def _random_path(rng: random.Random, n: int, lo: float, hi: float) -> list[tuple[float, float]]:
    return [(rng.uniform(lo, hi), rng.uniform(lo, hi)) for _ in range(n)]


# ---------------------------------------------------------------------------
# mark_path_blocked / mark_segment_blocked
# ---------------------------------------------------------------------------


def test_mark_path_blocked_matches_oracle_randomized():
    rng = random.Random(20260806)
    matched = 0
    for _ in range(80):
        w, h = rng.randint(3, 30), rng.randint(3, 30)
        cell_size = rng.choice([0.1, 0.25, 0.5, 1.0])
        real, oracle = _paired_grids(rng, w, h, cell_size, with_static=False)
        path = _random_path(rng, rng.randint(0, 5), -2.0, cell_size * max(w, h) + 2.0)
        trace_width = rng.uniform(0.0, 1.0)
        clearance = rng.uniform(0.0, 0.5)
        net_id = rng.randint(1, 120)
        real.mark_path_blocked(path, trace_width, clearance, net_id)
        oracle.mark_path_blocked(path, trace_width, clearance, net_id)
        assert np.array_equal(real.grid, oracle.grid), (w, h, cell_size, path, trace_width, clearance, net_id)
        matched += 1
    assert matched == 80


def test_mark_segment_blocked_matches_oracle_randomized():
    rng = random.Random(19)
    for _ in range(80):
        w, h = rng.randint(3, 30), rng.randint(3, 30)
        cell_size = rng.choice([0.1, 0.25, 0.5, 1.0])
        real, oracle = _paired_grids(rng, w, h, cell_size, with_static=False)
        p1 = (rng.uniform(-2.0, cell_size * w + 2.0), rng.uniform(-2.0, cell_size * h + 2.0))
        p2 = (rng.uniform(-2.0, cell_size * w + 2.0), rng.uniform(-2.0, cell_size * h + 2.0))
        trace_width = rng.uniform(0.0, 1.0)
        clearance = rng.uniform(0.0, 0.5)
        net_id = rng.randint(1, 120)
        real.mark_segment_blocked(p1, p2, trace_width, clearance, net_id)
        oracle.mark_segment_blocked(p1, p2, trace_width, clearance, net_id)
        assert np.array_equal(real.grid, oracle.grid), (w, h, cell_size, p1, p2, trace_width, clearance, net_id)


def test_mark_segment_blocked_degenerate_fallback_marks_p1():
    real, oracle = _paired_grids(random.Random(1), 5, 5, 1.0, with_static=False)
    p = (2.5, 2.5)
    real.mark_segment_blocked(p, p, 0.0, 0.0, 9)
    oracle.mark_segment_blocked(p, p, 0.0, 0.0, 9)
    assert np.array_equal(real.grid, oracle.grid)
    assert real.grid[2, 2] == 9


def test_mark_path_blocked_degenerate_segment_marks_nothing():
    """mark_path_blocked has NO degenerate fallback -- unlike
    mark_segment_blocked, a zero-length sub-segment is silently skipped."""
    real, oracle = _paired_grids(random.Random(2), 5, 5, 1.0, with_static=False)
    p = (2.5, 2.5)
    real.mark_path_blocked([p, p], 0.0, 0.0, 9)
    oracle.mark_path_blocked([p, p], 0.0, 0.0, 9)
    assert np.array_equal(real.grid, oracle.grid)
    assert real.grid[2, 2] == 0  # NOT marked -- confirms the asymmetry


def test_mark_path_blocked_empty_and_single_point_paths_are_noops():
    for path in ([], [(1.0, 1.0)]):
        real, oracle = _paired_grids(random.Random(3), 5, 5, 1.0, with_static=False)
        real.mark_path_blocked(path, 0.5, 0.1, 200)  # out-of-int8-range net_id
        oracle.mark_path_blocked(path, 0.5, 0.1, 200)
        assert np.array_equal(real.grid, oracle.grid)  # neither raised nor wrote


# ---------------------------------------------------------------------------
# unmark_segment_blocked / unmark_path (incl. the static_mask asymmetry)
# ---------------------------------------------------------------------------


def test_unmark_segment_blocked_matches_oracle_with_static_mask():
    rng = random.Random(2027)
    for _ in range(60):
        w, h = rng.randint(3, 25), rng.randint(3, 25)
        cell_size = rng.choice([0.1, 0.5, 1.0])
        real, oracle = _paired_grids(rng, w, h, cell_size, with_static=True)
        p1 = (rng.uniform(-1.0, cell_size * w + 1.0), rng.uniform(-1.0, cell_size * h + 1.0))
        p2 = (rng.uniform(-1.0, cell_size * w + 1.0), rng.uniform(-1.0, cell_size * h + 1.0))
        trace_width = rng.uniform(0, 1)
        clearance = rng.uniform(0, 0.5)
        net_id = rng.choice([1, 2, 3, 7, 11])
        real.unmark_segment_blocked(p1, p2, trace_width, clearance, net_id)
        oracle.unmark_segment_blocked(p1, p2, trace_width, clearance, net_id)
        assert np.array_equal(real.grid, oracle.grid), (w, h, cell_size, p1, p2, trace_width, clearance, net_id)


def test_unmark_segment_blocked_restores_static_sentinel():
    w, h = 5, 5
    arr = np.zeros((h, w), dtype=np.int8)
    arr[2, 2] = 7
    static = np.zeros((h, w), dtype=bool)
    static[2, 2] = True
    real = OccupancyGrid("F.Cu", arr.copy(), (0.0, 0.0), 1.0, w, h, static.copy())
    oracle = _OracleOccupancyGrid("F.Cu", arr.copy(), (0.0, 0.0), 1.0, w, h, static.copy())
    real.unmark_segment_blocked((2.5, 2.5), (2.5, 2.5), 0.0, 0.0, 7)
    oracle.unmark_segment_blocked((2.5, 2.5), (2.5, 2.5), 0.0, 0.0, 7)
    assert real.grid[2, 2] == oracle.grid[2, 2] == -1


def test_unmark_path_never_restores_static_even_when_grid_has_one():
    """The real asymmetry: unmark_path never reads static_mask, so a static
    cell that was overwritten by a net gets cleared to 0, NOT restored to
    -1 -- even though unmark_segment_blocked (same net, same cell) WOULD
    restore it. Both the oracle and the Rust kernel must agree."""
    w, h = 5, 5
    arr = np.zeros((h, w), dtype=np.int8)
    arr[2, 2] = 7
    static = np.zeros((h, w), dtype=bool)
    static[2, 2] = True
    real = OccupancyGrid("F.Cu", arr.copy(), (0.0, 0.0), 1.0, w, h, static.copy())
    oracle = _OracleOccupancyGrid("F.Cu", arr.copy(), (0.0, 0.0), 1.0, w, h, static.copy())
    real.unmark_path([(2.0, 2.5), (2.99, 2.5)], 0.0, 0.0, 7)
    oracle.unmark_path([(2.0, 2.5), (2.99, 2.5)], 0.0, 0.0, 7)
    assert real.grid[2, 2] == oracle.grid[2, 2] == 0  # NOT -1


def test_unmark_path_matches_oracle_randomized():
    rng = random.Random(555)
    for _ in range(60):
        w, h = rng.randint(3, 25), rng.randint(3, 25)
        cell_size = rng.choice([0.1, 0.5, 1.0])
        real, oracle = _paired_grids(rng, w, h, cell_size, with_static=True)
        path = _random_path(rng, rng.randint(0, 4), -1.0, cell_size * max(w, h) + 1.0)
        trace_width = rng.uniform(0, 1)
        clearance = rng.uniform(0, 0.5)
        net_id = rng.choice([1, 2, 3, 7, 11])
        real.unmark_path(path, trace_width, clearance, net_id)
        oracle.unmark_path(path, trace_width, clearance, net_id)
        assert np.array_equal(real.grid, oracle.grid), (w, h, cell_size, path, trace_width, clearance, net_id)


# ---------------------------------------------------------------------------
# get_blocking_nets
# ---------------------------------------------------------------------------


def test_get_blocking_nets_matches_oracle_randomized():
    rng = random.Random(777)
    for _ in range(80):
        w, h = rng.randint(3, 25), rng.randint(3, 25)
        cell_size = rng.choice([0.1, 0.5, 1.0])
        real, oracle = _paired_grids(rng, w, h, cell_size, with_static=False)
        p1 = (rng.uniform(-1.0, cell_size * w + 1.0), rng.uniform(-1.0, cell_size * h + 1.0))
        p2 = (rng.uniform(-1.0, cell_size * w + 1.0), rng.uniform(-1.0, cell_size * h + 1.0))
        real_ids = real.get_blocking_nets(p1, p2)
        oracle_ids = oracle.get_blocking_nets(p1, p2)
        assert real_ids == oracle_ids, (w, h, cell_size, p1, p2)
        assert isinstance(real_ids, set)


# ---------------------------------------------------------------------------
# mark_via_blocked
# ---------------------------------------------------------------------------


def test_mark_via_blocked_matches_oracle_randomized():
    rng = random.Random(31337)
    for _ in range(80):
        w, h = rng.randint(3, 25), rng.randint(3, 25)
        cell_size = rng.choice([0.1, 0.5, 1.0])
        real, oracle = _paired_grids(rng, w, h, cell_size, with_static=False)
        x = rng.uniform(-1.0, cell_size * w + 1.0)
        y = rng.uniform(-1.0, cell_size * h + 1.0)
        via_dia = rng.uniform(0.1, 1.0)
        clearance = rng.uniform(0.0, 0.5)
        net_id = rng.randint(1, 120)
        real.mark_via_blocked(x, y, via_dia, clearance, net_id)
        oracle.mark_via_blocked(x, y, via_dia, clearance, net_id)
        assert np.array_equal(real.grid, oracle.grid), (w, h, cell_size, x, y, via_dia, clearance, net_id)


def test_mark_via_blocked_overflow_raises_before_any_write():
    """net_id is constant across the call, so the int8-range check fails
    identically on every matching cell -- meaning it always fails on the
    very FIRST match, before that cell's own write lands. A raising call
    therefore mutates nothing at all, and both the oracle (numpy's own
    int8 scalar-assignment check) and the Rust kernel must agree on that."""
    w, h = 9, 9
    real = _make_grid(w, h, 1.0)
    oracle = _OracleOccupancyGrid(
        "F.Cu", np.zeros((h, w), dtype=np.int8), (0.0, 0.0), 1.0, w, h
    )
    with pytest.raises(OverflowError):
        real.mark_via_blocked(4.5, 4.5, 5.0, 0.0, 500)
    with pytest.raises(OverflowError):
        oracle.mark_via_blocked(4.5, 4.5, 5.0, 0.0, 500)
    assert np.array_equal(real.grid, oracle.grid)
    assert not np.any(real.grid != 0)


def test_mark_via_blocked_zero_matches_raises_nothing():
    """When NO cell falls within the radius, an out-of-range net_id never
    raises (the reference's scalar assignment only happens per matching
    cell) -- unlike the rectangular kernels, which raise unconditionally
    once at least one point would be marked."""
    w, h = 5, 5
    real = _make_grid(w, h, 1.0)
    oracle = _OracleOccupancyGrid(
        "F.Cu", np.zeros((h, w), dtype=np.int8), (0.0, 0.0), 1.0, w, h
    )
    # radius 0, clearance 0 -> only dist==0 cell (the centre) matches.
    # Place the via off-grid entirely so the bbox is empty -> no cell loop
    # iterations at all -> never raises despite net_id=500.
    real.mark_via_blocked(-100.0, -100.0, 0.0, 0.0, 500)
    oracle.mark_via_blocked(-100.0, -100.0, 0.0, 0.0, 500)
    assert np.array_equal(real.grid, oracle.grid)


# ---------------------------------------------------------------------------
# downsample
# ---------------------------------------------------------------------------


def test_downsample_matches_oracle_randomized():
    rng = random.Random(9001)
    for _ in range(60):
        w, h = rng.randint(1, 40), rng.randint(1, 40)
        factor = rng.choice([1, 2, 3, 4])
        arr = np.zeros((h, w), dtype=np.int8)
        for _ in range(w * h // 3):
            arr[rng.randrange(h), rng.randrange(w)] = rng.choice([1, -1, 5])
        real = OccupancyGrid("F.Cu", arr.copy(), (0.0, 0.0), 0.1, w, h)
        oracle = _OracleOccupancyGrid("F.Cu", arr.copy(), (0.0, 0.0), 0.1, w, h)
        real_c = real.downsample(factor)
        oracle_c = oracle.downsample(factor)
        assert (real_c.width_cells, real_c.height_cells) == (oracle_c.width_cells, oracle_c.height_cells)
        assert real_c.cell_size == oracle_c.cell_size
        assert np.array_equal(real_c.grid, oracle_c.grid), (w, h, factor)
        assert real_c.grid.dtype == oracle_c.grid.dtype == np.int8


def test_downsample_dtype_tolerance_int16():
    """downsample must also work on non-int8 grids (test fixtures use
    int16 directly -- see test_occupancy_grid_pbt.py); the Rust kernel
    receives a dtype-agnostic uint8 nonzero mask, not the raw dtype."""
    rng = random.Random(55)
    w, h = rng.randint(10, 40), rng.randint(10, 40)
    arr = np.zeros((h, w), dtype=np.int16)
    for _ in range(w * h // 4):
        arr[rng.randrange(h), rng.randrange(w)] = 1
    real = OccupancyGrid("F.Cu", arr.copy(), (0.0, 0.0), 0.1, w, h)
    oracle = _OracleOccupancyGrid("F.Cu", arr.copy(), (0.0, 0.0), 0.1, w, h)
    real_c = real.downsample(2)
    oracle_c = oracle.downsample(2)
    assert np.array_equal(real_c.grid, oracle_c.grid)
    assert real_c.grid.dtype == oracle_c.grid.dtype == np.int16


# ---------------------------------------------------------------------------
# int(x) truncation-toward-zero for negative coordinates (world_to_grid,
# inlined into every migrated kernel)
# ---------------------------------------------------------------------------


def test_negative_coordinate_truncation_matches_oracle_not_floor():
    """int(x) truncates toward zero; floor(x) would differ for negative
    x. mark_via_blocked at a negative-but-fractional coordinate must land
    on the truncated cell, matching the oracle bit-for-bit."""
    w, h = 10, 10
    real = OccupancyGrid("F.Cu", np.zeros((h, w), dtype=np.int8), (-5.0, -5.0), 1.0, w, h)
    oracle = _OracleOccupancyGrid(
        "F.Cu", np.zeros((h, w), dtype=np.int8), (-5.0, -5.0), 1.0, w, h
    )
    # x_mm=-4.5, origin=-5.0 -> (x_mm-origin)/cell = 0.5 -> int() truncates to 0.
    # x_mm=-5.5 would be out of grid; use an in-range negative-ish case.
    real.mark_via_blocked(-4.5, -4.5, 0.4, 0.0, 3)
    oracle.mark_via_blocked(-4.5, -4.5, 0.4, 0.0, 3)
    assert np.array_equal(real.grid, oracle.grid)


# ---------------------------------------------------------------------------
# int(np.ceil(x)) overflow on non-finite radii / zero cell_size
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cell_size,expected_exc",
    [
        # cell_size=0.0: `radius_mm / self.cell_size` is a plain Python
        # float division, which raises ZeroDivisionError directly --
        # np.ceil()/int() never even run (measured: unlike numpy division,
        # `0.6 / 0.0` in plain Python raises rather than producing inf).
        (0.0, ZeroDivisionError),
        # cell_size=nan: the division succeeds (nan/nan = nan), np.ceil
        # propagates nan, and int(nan) is what raises ValueError.
        (float("nan"), ValueError),
    ],
)
def test_expansion_overflow_matches_oracle(cell_size, expected_exc):
    real = OccupancyGrid("F.Cu", np.zeros((5, 5), dtype=np.int8), (0.0, 0.0), cell_size, 5, 5)
    oracle = _OracleOccupancyGrid(
        "F.Cu", np.zeros((5, 5), dtype=np.int8), (0.0, 0.0), cell_size, 5, 5
    )
    with pytest.raises(expected_exc):
        oracle.mark_via_blocked(2.0, 2.0, 1.0, 0.1, 3)
    with pytest.raises(expected_exc):
        real.mark_via_blocked(2.0, 2.0, 1.0, 0.1, 3)


# ---------------------------------------------------------------------------
# CellState sanity: the oracle's own enum matches production's.
# ---------------------------------------------------------------------------


def test_oracle_cellstate_matches_production():
    assert _OracleCellState.FREE.value == CellState.FREE.value == 0
    assert _OracleCellState.BLOCKED.value == CellState.BLOCKED.value == 1
    assert _OracleCellState.RESERVED.value == CellState.RESERVED.value == 2
