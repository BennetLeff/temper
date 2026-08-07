"""Differential tests: batched bottleneck-width EDT lookup vs the original
per-point loop.

``temper_placer.router_v6._astar_heuristics._compute_bottleneck_widths``
sampled the EDT width per point (one Python call per waypoint-segment
sample).  The cleanup C3 change replaced that loop with a single
``_edt_width_lookup_batch`` FFI crossing per call (bit-identical per
point to the per-point reference lookup, pinned verbatim in the
differential test suites — see ``packages/temper-geometry/VERIFICATION.md``).

Two pins here:

1. ``test_bottleneck_widths_batch_matches_original_loop`` — the PRE-CHANGE
   per-point loop, copied verbatim into this file as the oracle, must
   produce bit-identical per-net widths on ~200 randomized channel
   mappings (empty paths, single waypoints, degenerate segments,
   out-of-bounds samples, varied cell sizes / sample distances).
2. ``test_bottleneck_widths_uses_single_batch_call`` — the per-point loop
   must actually be gone: exactly ONE ``_edt_width_lookup_batch`` call per
   ``_compute_bottleneck_widths`` invocation, with all sample points
   collected up front.  This test FAILED against the old implementation
   (zero batch calls) and passes only once the loop is batched.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np

from temper_placer.router_v6._astar_heuristics import (
    _build_edt_from_grid,
    compute_demand_budget,
    min_edt_along_line,
)
from temper_placer.router_v6.astar_pathfinding import _compute_bottleneck_widths
from temper_placer.router_v6.occupancy_grid import OccupancyGrid

# ---------------------------------------------------------------------------
# Oracle: the pre-migration per-point EDT width lookup, pinned verbatim.
# (Removed from channel_widths.py in cleanup C5; the differential suites
# keep it here so the batched path stays bit-identical to the reference.)
# ---------------------------------------------------------------------------


def _edt_width_lookup(
    x: float,
    y: float,
    edt: np.ndarray,
    mask: np.ndarray,
    bounds: tuple[float, float, float, float],
    cell_size: float,
) -> float:
    """Query width from a precomputed EDT grid.

    Maps world coordinates (x, y) to grid indices, reads the EDT
    distance, and returns width = 2 * distance * cell_size.

    For sub-cell accuracy, bilinear interpolation is used over the
    4 nearest grid points.
    """
    min_x, min_y, _, _ = bounds
    gx = (x - min_x) / cell_size
    gy = (y - min_y) / cell_size

    ix, iy = int(np.floor(gx)), int(np.floor(gy))
    fx, fy = gx - ix, gy - iy

    h, w = edt.shape
    if ix < 0 or iy < 0 or ix + 1 >= w or iy + 1 >= h:
        return 0.0

    d00 = edt[iy, ix] if mask[iy, ix] else 0.0
    d10 = edt[iy, ix + 1] if mask[iy, ix + 1] else 0.0
    d01 = edt[iy + 1, ix] if mask[iy + 1, ix] else 0.0
    d11 = edt[iy + 1, ix + 1] if mask[iy + 1, ix + 1] else 0.0

    d = (d00 * (1 - fx) + d10 * fx) * (1 - fy) + (d01 * (1 - fx) + d11 * fx) * fy
    return 2.0 * d * cell_size


@dataclass
class FakeChannelPath:
    net_name: str
    waypoints: list[tuple[float, float]]
    total_length: float = 0.0
    preferred_layer: str = "F.Cu"
    channel_sequence: list = None


class FakeChannelMapping:
    def __init__(self, paths: dict[str, FakeChannelPath]):
        self.channel_paths = paths


# ---------------------------------------------------------------------------
# Oracle: the PRE-CHANGE per-point loop, verbatim (width resolution via the
# per-point reference lookup pinned above in this file).
# ---------------------------------------------------------------------------


def _bottleneck_widths_per_point_oracle(
    channel_mapping: FakeChannelMapping,
    edt: np.ndarray,
    mask: np.ndarray,
    bounds: tuple[float, float, float, float],
    cell_size: float = 0.1,
    sample_distance: float = 0.5,
) -> dict[str, float]:
    """Verbatim copy of the pre-batch ``_compute_bottleneck_widths``."""
    widths: dict[str, float] = {}
    for net_name, path in channel_mapping.channel_paths.items():
        waypoints = path.waypoints
        if len(waypoints) < 2:
            widths[net_name] = float("inf")
            continue

        min_width = float("inf")
        for i in range(len(waypoints) - 1):
            x1, y1 = waypoints[i]
            x2, y2 = waypoints[i + 1]
            dx = x2 - x1
            dy = y2 - y1
            seg_len = math.sqrt(dx * dx + dy * dy)

            if seg_len < 1e-9:
                w = _edt_width_lookup(x1, y1, edt, mask, bounds, cell_size)
                if w < min_width:
                    min_width = w
                continue

            num_samples = max(1, int(seg_len / sample_distance))
            for s in range(num_samples + 1):
                t = s / num_samples
                sx = x1 + t * dx
                sy = y1 + t * dy
                w = _edt_width_lookup(sx, sy, edt, mask, bounds, cell_size)
                if w < min_width:
                    min_width = w

        widths[net_name] = min_width if min_width != float("inf") else 0.0

    return widths


# ---------------------------------------------------------------------------
# Randomised fixtures
# ---------------------------------------------------------------------------


def _random_edt_mask(rng: random.Random, h: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    """Random interior mask with a smooth EDT field (mirrors what scipy
    produces semantically, without paying for the transform per case)."""
    mask = np.asarray([rng.random() > 0.2 for _ in range(h * w)], dtype=bool).reshape(h, w)
    rows = np.arange(h, dtype=np.float64).reshape(-1, 1)
    cols = np.arange(w, dtype=np.float64).reshape(1, -1)
    noise = np.asarray([rng.random() for _ in range(h * w)], dtype=np.float64).reshape(h, w)
    edt = np.sqrt((rows - h / 2.0) ** 2 + (cols - w / 2.0) ** 2) + noise * 0.5
    return edt, mask


def _random_waypoints(rng: random.Random, w_world: float, h_world: float) -> list[tuple[float, float]]:
    """Random waypoints; ~10% fall outside the grid bounds (lookup -> 0.0)."""
    n = rng.choice([0, 1, 2, 3, 4, 6])
    pts: list[tuple[float, float]] = []
    for _ in range(n):
        mode = rng.random()
        if mode < 0.9:
            x = rng.random() * w_world
            y = rng.random() * h_world
        else:
            x = rng.uniform(-2.0, -0.01) or rng.uniform(w_world + 0.01, w_world + 2.0)
            y = rng.uniform(-2.0, -0.01) or rng.uniform(h_world + 0.01, h_world + 2.0)
        pts.append((float(x), float(y)))
    # Inject degenerate (zero-length) segments by duplicating a waypoint.
    if len(pts) >= 2 and rng.random() < 0.3:
        k = rng.randrange(1, len(pts))
        pts[k] = pts[k - 1]
    return pts


def _random_channel_mapping(rng: random.Random, w_world: float, h_world: float) -> FakeChannelMapping:
    paths: dict[str, FakeChannelPath] = {}
    for i in range(rng.randint(0, 6)):
        paths[f"net{i}"] = FakeChannelPath(
            net_name=f"net{i}",
            waypoints=_random_waypoints(rng, w_world, h_world),
        )
    return FakeChannelMapping(paths)


def _random_case(rng: random.Random) -> tuple:
    """One random (mapping, edt, mask, bounds, cell_size, sample_distance)."""
    h, w = rng.choice([(5, 7), (10, 10), (3, 20), (12, 4)])
    cell_size = rng.choice([0.1, 0.5, 1.0])
    edt, mask = _random_edt_mask(rng, h, w)
    bounds = (0.0, 0.0, float(w) * cell_size, float(h) * cell_size)
    mapping = _random_channel_mapping(rng, float(w) * cell_size, float(h) * cell_size)
    sample_distance = rng.choice([0.1, 0.5, 1.0, 2.0])
    return mapping, edt, mask, bounds, cell_size, sample_distance


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_bottleneck_widths_batch_matches_original_loop() -> None:
    """~200 randomized mappings: batched implementation is bit-identical to
    the verbatim per-point oracle, including empty/single/degenerate paths
    and out-of-bounds samples."""
    rng = random.Random(20260731)
    for _ in range(200):
        mapping, edt, mask, bounds, cell_size, sample_distance = _random_case(rng)
        got = _compute_bottleneck_widths(
            mapping, edt, mask, bounds, cell_size=cell_size, sample_distance=sample_distance
        )
        expect = _bottleneck_widths_per_point_oracle(
            mapping, edt, mask, bounds, cell_size=cell_size, sample_distance=sample_distance
        )
        assert set(got) == set(expect), f"net keys differ: {got} vs {expect}"
        for net_name in expect:
            assert got[net_name] == expect[net_name], (
                f"net {net_name}: batched {got[net_name]} != oracle {expect[net_name]} "
                f"(case: cell={cell_size} sample_d={sample_distance} "
                f"waypoints={mapping.channel_paths[net_name].waypoints})"
            )


def test_bottleneck_widths_uses_single_batch_call(monkeypatch) -> None:
    """The per-point loop must be gone: exactly ONE ``_edt_width_lookup_batch``
    call per invocation, with every sample point collected up front.

    Red-green: this test FAILED against the pre-change implementation
    (which never called the batch), and passes only after the loop is
    batched.
    """
    import temper_placer.router_v6.channel_widths as cw

    calls: list[tuple[list[float], list[float]]] = []
    original = cw._edt_width_lookup_batch

    def recorder(xs, ys, *args, **kwargs):
        calls.append((list(xs), list(ys)))
        return original(xs, ys, *args, **kwargs)

    monkeypatch.setattr(cw, "_edt_width_lookup_batch", recorder)

    paths = {
        "a": FakeChannelPath(
            net_name="a", waypoints=[(0.0, 0.0), (5.0, 0.0), (5.0, 3.0)]
        ),
        "b": FakeChannelPath(net_name="b", waypoints=[(1.0, 1.0)]),  # single -> inf
        "c": FakeChannelPath(net_name="c", waypoints=[]),  # empty -> inf
    }
    cm = FakeChannelMapping(paths)
    edt = np.full((10, 10), 5.0, dtype=np.float64)
    mask = np.ones((10, 10), dtype=bool)
    bounds = (0.0, 0.0, 10.0, 10.0)

    bw = _compute_bottleneck_widths(cm, edt, mask, bounds, cell_size=1.0, sample_distance=2.0)

    assert len(calls) == 1, f"expected exactly one batch call, got {len(calls)}"
    xs, ys = calls[0]
    # net "a": seg(0,0)->(5,0) len 5, sample_d 2 -> num_samples=2 -> 3 pts;
    #          seg(5,0)->(5,3) len 3, sample_d 2 -> num_samples=1 -> 2 pts.
    assert len(xs) == 5, f"expected 5 collected samples, got {len(xs)}"
    assert len(xs) == len(ys)
    assert bw["b"] == float("inf")
    assert bw["c"] == float("inf")
    assert bw["a"] == min(original(np.asarray(xs), np.asarray(ys), edt, mask, bounds, 1.0))


# ---------------------------------------------------------------------------
# EDT migration (KTD8): ``_build_edt_from_grid``'s ``_exact_edt`` (Rust FH
# sweep, via temper_geometry) vs ``scipy.ndimage.distance_transform_edt``,
# the pre-migration oracle pinned here per R19. See
# docs/evidence/2026-08-07-exact-edt-rust-spike.md.
# ---------------------------------------------------------------------------


def _scipy_build_edt_from_grid(grid: OccupancyGrid):
    """Pre-migration oracle, pinned verbatim (R19): this is exactly what
    ``_build_edt_from_grid`` computed before the Rust EDT migration."""
    from scipy.ndimage import distance_transform_edt

    mask = (grid.grid == 0).astype(np.uint8)
    edt = distance_transform_edt(mask)
    min_x, min_y = grid.origin
    max_x = min_x + grid.width_cells * grid.cell_size
    max_y = min_y + grid.height_cells * grid.cell_size
    return edt, (min_x, min_y, max_x, max_y), grid.cell_size


def test_build_edt_from_grid_matches_scipy_oracle_bit_exact() -> None:
    """50 randomized OccupancyGrids, each with >= 1 blocked cell (reachable,
    finite-EDT inputs): ``_build_edt_from_grid`` is bit-exact vs the pinned
    scipy oracle."""
    rng = random.Random(20260807)
    for _ in range(50):
        h = rng.randint(3, 40)
        w = rng.randint(3, 40)
        grid_arr = np.zeros((h, w), dtype=np.int8)
        n_blocked = rng.randint(1, max(1, (h * w) // 3))
        for _ in range(n_blocked):
            grid_arr[rng.randrange(h), rng.randrange(w)] = 1
        grid = OccupancyGrid(
            layer_name="F.Cu",
            grid=grid_arr,
            origin=(rng.uniform(-5.0, 5.0), rng.uniform(-5.0, 5.0)),
            cell_size=rng.choice([0.1, 0.5, 1.0]),
            width_cells=w,
            height_cells=h,
        )
        got_edt, got_bounds, got_cell = _build_edt_from_grid(grid)
        want_edt, want_bounds, want_cell = _scipy_build_edt_from_grid(grid)
        np.testing.assert_array_equal(got_edt, want_edt)
        assert got_bounds == want_bounds
        assert got_cell == want_cell


def test_build_edt_from_grid_all_free_grid_is_reachable_and_diverges() -> None:
    """All-foreground reachability check (KTD8 spike section 4 divergence):
    the spike claimed an all-foreground mask is unreachable by all three
    consumers "by construction". That does NOT hold for
    ``_build_edt_from_grid``: an all-free ``OccupancyGrid`` (no blocked
    cell anywhere) produces exactly this input, and it IS constructed in
    this repo -- ``test_budget_via_run_astar_pathfinding`` in
    ``test_demand_budget_pbt.py`` builds
    ``OccupancyGrid("F.Cu", np.zeros((30, 30), dtype=np.int8), ...)``.

    Verified explicitly here rather than trusted: Rust returns +inf
    everywhere, scipy returns a finite boundary artifact -- a real,
    reachable divergence. It does not silently propagate downstream:
    ``min_edt_along_line``'s ``if min_dist == float("inf")`` branch already
    exists to handle an unbounded EDT and returns the documented
    single-cell-width fallback.
    """
    grid = OccupancyGrid(
        layer_name="F.Cu",
        grid=np.zeros((30, 30), dtype=np.int8),
        origin=(0.0, 0.0),
        cell_size=1.0,
        width_cells=30,
        height_cells=30,
    )
    edt, bounds, cell_size = _build_edt_from_grid(grid)
    assert np.all(np.isinf(edt)), "Rust EDT must be +inf everywhere on an all-free grid"

    want_edt, _, _ = _scipy_build_edt_from_grid(grid)
    assert np.all(np.isfinite(want_edt)), "scipy's boundary artifact is finite by construction"
    assert not np.array_equal(edt, want_edt), "the two genuinely diverge on this reachable input"

    # Downstream: the inf-fallback branch actually fires and returns the
    # documented fallback, not a propagated inf/nan.
    val = min_edt_along_line(edt, bounds, cell_size, (2.0, 2.0), (28.0, 28.0))
    assert val == cell_size


def test_compute_demand_budget_all_free_grid_stays_bounded() -> None:
    """End-to-end: an all-free grid's budget computation stays in the
    documented [1000, base_budget] range despite the raw EDT being +inf
    everywhere (no NaN/inf propagation into the public output)."""
    grid = OccupancyGrid(
        layer_name="F.Cu",
        grid=np.zeros((30, 30), dtype=np.int8),
        origin=(0.0, 0.0),
        cell_size=1.0,
        width_cells=30,
        height_cells=30,
    )
    edt, bounds, cell_size = _build_edt_from_grid(grid)
    mapping = FakeChannelMapping(
        {"n0": FakeChannelPath(net_name="n0", waypoints=[(2.0, 2.0), (28.0, 28.0)])}
    )
    budget = compute_demand_budget(edt, bounds, cell_size, mapping)
    assert 1000 <= budget["n0"] <= 100000
