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

from temper_placer.router_v6.astar_pathfinding import _compute_bottleneck_widths

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
