"""Differential tests: batched Rust EDT width lookup vs the per-point
reference implementation.

The per-point reference lookup is pinned verbatim in this file as
``_edt_width_lookup`` (copied from the pre-migration implementation in
``temper_placer.router_v6.channel_widths``); the production hot path is
``_edt_width_lookup_batch`` (one FFI crossing per layer).  This suite
pins the two bit-identical per point, and pins
``compute_channel_widths`` end-to-end against a per-point-driven
rebuild.
"""

from __future__ import annotations

import random

import numpy as np
from shapely.geometry import MultiPolygon, Polygon, box

from temper_placer.router_v6.channel_skeleton import extract_channel_skeleton
from temper_placer.router_v6.channel_widths import (
    _build_edt,
    _edt_width_lookup_batch,
    compute_channel_widths,
)
from temper_placer.router_v6.routing_space import RoutingSpace
from tests.router_v6 import _channel_ops_py_oracle as _oracle

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


def _random_edt_grid(
    rng: random.Random, h: int, w: int
) -> tuple[np.ndarray, np.ndarray]:
    """Random interior mask; EDT = distance to the nearest False cell
    (computed exactly, mirroring what scipy produces semantically)."""
    mask = np.asarray([rng.random() > 0.25 for _ in range(h * w)], dtype=bool).reshape(h, w)
    # smooth field satisfying the bilinear-interpolation contract
    rows = np.arange(h, dtype=np.float64).reshape(-1, 1)
    cols = np.arange(w, dtype=np.float64).reshape(1, -1)
    noise = np.asarray([rng.random() for _ in range(h * w)], dtype=np.float64).reshape(h, w)
    edt = np.sqrt((rows - h / 2) ** 2 + (cols - w / 2) ** 2) + noise * 0.5
    return edt, mask


def _random_points(rng: random.Random, n: int, h: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.asarray([rng.random() * (w + 2) - 1 for _ in range(n)]),
        np.asarray([rng.random() * (h + 2) - 1 for _ in range(n)]),
    )


def test_batch_matches_per_point_reference_bit_exact() -> None:
    rng = random.Random(20260731)
    for _ in range(20):
        h, w = rng.choice([(10, 14), (6, 30), (20, 20), (3, 5)])
        edt, mask = _random_edt_grid(rng, h, w)
        xs, ys = _random_points(rng, 200, h, w)
        bounds = (0.0, 0.0, float(w), float(h))
        cell = rng.choice([0.1, 0.5, 1.0])
        batch = _edt_width_lookup_batch(xs, ys, edt, mask, bounds, cell)
        reference = np.asarray(
            [
                _edt_width_lookup(x, y, edt, mask, bounds, cell)
                for x, y in zip(xs.tolist(), ys.tolist())
            ],
            dtype=np.float64,
        )
        np.testing.assert_array_equal(batch, reference)


def test_batch_matches_reference_with_offset_bounds() -> None:
    rng = random.Random(5)
    h, w = 12, 16
    edt, mask = _random_edt_grid(rng, h, w)
    xs = np.asarray([10.0 + rng.random() * 8 for _ in range(50)])
    ys = np.asarray([-5.0 + rng.random() * 6 for _ in range(50)])
    bounds = (10.0, -5.0, 26.0, 1.0)
    cell = 0.5
    batch = _edt_width_lookup_batch(xs, ys, edt, mask, bounds, cell)
    reference = np.asarray(
        [_edt_width_lookup(x, y, edt, mask, bounds, cell) for x, y in zip(xs, ys)],
        dtype=np.float64,
    )
    np.testing.assert_array_equal(batch, reference)


def test_batch_out_of_bounds_returns_zero() -> None:
    rng = random.Random(9)
    edt, mask = _random_edt_grid(rng, 8, 8)
    bounds = (0.0, 0.0, 8.0, 8.0)
    xs = np.asarray([-0.5, 8.5, 4.0, 100.0])
    ys = np.asarray([4.0, 4.0, 8.5, -3.0])
    batch = _edt_width_lookup_batch(xs, ys, edt, mask, bounds, 1.0)
    np.testing.assert_array_equal(batch, np.zeros(4))


def test_batch_masked_cells_contribute_zero() -> None:
    # All-False mask: every interpolated value must be exactly 0.0
    # (masked cells contribute 0.0, not the EDT value).
    h, w = 10, 10
    edt = np.full((h, w), 42.0, dtype=np.float64)
    mask = np.zeros((h, w), dtype=bool)
    xs = np.asarray([0.5, 3.3, 7.7])
    ys = np.asarray([0.5, 5.5, 2.2])
    batch = _edt_width_lookup_batch(xs, ys, edt, mask, (0.0, 0.0, 10.0, 10.0), 1.0)
    np.testing.assert_array_equal(batch, np.zeros(3))


# ---------------------------------------------------------------------------
# End-to-end: compute_channel_widths (batched EDT path) vs per-point rebuild
# ---------------------------------------------------------------------------


def _routing_space(geom) -> RoutingSpace:
    area = float(geom.area)
    return RoutingSpace(
        layer_name="F.Cu",
        available_area=geom,
        total_area=area,
        obstacle_area=0.0,
        routing_area=area,
    )


def _per_point_rebuild(routing_space, skeleton, sample_distance: float) -> dict:
    """compute_channel_widths as the PRE-BATCH implementation: the
    per-point reference loop, independently re-implemented here so the
    batched collection, sample offsets, and min() assembly are pinned
    rather than shared with the code under test."""
    import temper_placer.router_v6.channel_widths as cw

    original = cw._edt_width_lookup_batch

    def per_point_batch(xs, ys, edt, mask, bounds, cell_size):
        return np.asarray(
            [
                _edt_width_lookup(x, y, edt, mask, bounds, cell_size)
                for x, y in zip(xs.tolist(), ys.tolist())
            ],
            dtype=np.float64,
        )

    cw._edt_width_lookup_batch = per_point_batch
    try:
        # The batched code path is disabled via the monkeypatch above;
        # re-run the ORIGINAL pre-batch loop against the same EDT inputs
        # by calling the reference lookup directly.
        import numpy as np

        from temper_placer.router_v6.channel_widths import _build_edt

        node_widths: dict = {}
        edge_widths: dict = {}
        edt_grid, edt_mask, edt_bounds = _build_edt(routing_space, 0.1)
        for node in skeleton.graph.nodes:
            node_widths[node] = _edt_width_lookup(
                node[0], node[1], edt_grid, edt_mask, edt_bounds, 0.1
            )
        for u, v in skeleton.graph.edges:
            widths_along_edge = [node_widths[u], node_widths[v]]
            dx = v[0] - u[0]
            dy = v[1] - u[1]
            edge_length = (dx**2 + dy**2) ** 0.5
            if edge_length > sample_distance:
                num_samples = int(edge_length / sample_distance)
                for i in range(1, num_samples):
                    t = i / num_samples
                    sample_x = u[0] + t * dx
                    sample_y = u[1] + t * dy
                    widths_along_edge.append(
                        _edt_width_lookup(
                            sample_x, sample_y, edt_grid, edt_mask, edt_bounds, 0.1
                        )
                    )
            edge_widths[(u, v)] = min(widths_along_edge) if widths_along_edge else 0.0
        all_widths = list(node_widths.values()) + list(edge_widths.values())
        if all_widths:
            min_width = min(all_widths)
            max_width = max(all_widths)
            avg_width = sum(all_widths) / len(all_widths)
        else:
            min_width = max_width = avg_width = 0.0
        return cw.ChannelWidths(
            layer_name=routing_space.layer_name,
            node_widths=node_widths,
            edge_widths=edge_widths,
            min_width=min_width,
            max_width=max_width,
            avg_width=avg_width,
        )
    finally:
        cw._edt_width_lookup_batch = original


def _assert_channel_widths_identical(a, b) -> None:
    assert a.layer_name == b.layer_name
    assert set(a.node_widths) == set(b.node_widths)
    for node in a.node_widths:
        assert a.node_widths[node] == b.node_widths[node]
    assert set(a.edge_widths) == set(b.edge_widths)
    for edge in a.edge_widths:
        assert a.edge_widths[edge] == b.edge_widths[edge]
    assert a.min_width == b.min_width
    assert a.max_width == b.max_width
    assert a.avg_width == b.avg_width


def test_compute_channel_widths_batch_matches_per_point() -> None:
    rng = random.Random(13)
    for _ in range(6):
        # corridor shapes with varying aspect ratios
        w = rng.choice([10.0, 20.0, 50.0])
        h = rng.choice([10.0, 25.0])
        geom = MultiPolygon([box(0, 0, w, h)])
        routing_space = _routing_space(geom)
        skeleton = extract_channel_skeleton(routing_space)
        batch = compute_channel_widths(routing_space, skeleton)
        per_point = _per_point_rebuild(routing_space, skeleton, 1.0)
        _assert_channel_widths_identical(batch, per_point)


def test_compute_channel_widths_multipolygon_batch_matches_per_point() -> None:
    geom = MultiPolygon([box(0, 0, 20, 10), box(30, 0, 50, 10)])
    routing_space = _routing_space(geom)
    skeleton = extract_channel_skeleton(routing_space)
    batch = compute_channel_widths(routing_space, skeleton)
    per_point = _per_point_rebuild(routing_space, skeleton, 1.0)
    _assert_channel_widths_identical(batch, per_point)


# ---------------------------------------------------------------------------
# KTD8 history: the third-party `edt` crate (2026-07-31) was evaluated as a
# scipy.distance_transform_edt replacement and REJECTED -- its distance
# field diverged from scipy's Euclidean transform (max diff 2.0-2.236 on
# random masks even with a False-border padding workaround and transposed
# layout handling; the crate hardcoded a grid-edge clamp and other semantic
# differences). That rejection was of the third-party crate, not of a
# Rust-native EDT in general. A follow-up spike (2026-08-07, see
# docs/evidence/2026-08-07-exact-edt-rust-spike.md) implemented an exact
# Felzenszwalb-Huttenlocher sweep in `packages/temper-geometry/src/edt.rs`
# and measured bit-exact agreement with scipy (0.0 max abs diff over
# 7.4M+ cells). `_build_edt` (below, via `_exact_edt`) now delegates to it;
# `_scipy_edt` in this file pins the pre-migration scipy call as the
# differential's oracle (R19). U4's migration win was the batched width
# lookup; this later migration is the transform itself.
# ---------------------------------------------------------------------------


def _scipy_edt(mask: np.ndarray) -> np.ndarray:
    """Pre-migration oracle, pinned verbatim (R19): this is exactly what
    ``_build_edt`` called before the Rust EDT migration -- ``mask`` cast to
    ``uint8``, no ``sampling``, no ``return_indices``."""
    from scipy.ndimage import distance_transform_edt

    return distance_transform_edt(mask.astype(np.uint8))


def _curated_edt_masks() -> list[np.ndarray]:
    """Masks spanning the categories from the KTD8 spike corpus, restricted
    to reachable inputs (>= 1 background cell -- see
    test_rasterize_boundary_mask_always_has_background_cell below for why
    that restriction models this module's actual call site)."""
    cases: list[np.ndarray] = []
    cases.append(np.zeros((10, 10), dtype=bool))  # all background
    single = np.ones((12, 9), dtype=bool)
    single[0, 0] = False
    cases.append(single)  # single seed, corner
    corner = np.ones((8, 8), dtype=bool)
    corner[4, 4] = False
    cases.append(corner)  # single seed, center
    for h, w in [(5, 5), (4, 60), (60, 4), (30, 30), (7, 23), (1, 9), (9, 1)]:
        rng = np.random.default_rng(hash((h, w)) & 0xFFFFFFFF)
        for density in (0.02, 0.1, 0.3, 0.5, 0.7, 0.95, 0.98):
            mask = rng.random((h, w)) > density
            mask[0, 0] = False  # guarantee >= 1 background cell
            cases.append(mask)
    return cases


def test_exact_edt_matches_scipy_bit_exact_curated() -> None:
    """`_exact_edt` (Rust FH sweep) vs `_scipy_edt` (pinned oracle):
    bit-exact agreement on every reachable-shape case in the curated
    corpus, mirroring the KTD8 spike's own differential."""
    from temper_placer.router_v6.channel_widths import _exact_edt

    for mask in _curated_edt_masks():
        got = _exact_edt(mask)
        want = _scipy_edt(mask)
        assert got.dtype == np.float64
        assert np.array_equal(got, want), f"mismatch on shape {mask.shape}"


def test_exact_edt_matches_scipy_bit_exact_random() -> None:
    """300 random trials (grid dims, density varied): bit-exact agreement,
    restricted to reachable (>= 1 background cell) inputs."""
    from temper_placer.router_v6.channel_widths import _exact_edt

    rng = np.random.default_rng(42)
    for _ in range(300):
        h = int(rng.integers(2, 120))
        w = int(rng.integers(2, 120))
        density = rng.choice([0.02, 0.1, 0.3, 0.5, 0.7, 0.95, 0.98])
        mask = rng.random((h, w)) > density
        mask[0, 0] = False
        got = _exact_edt(mask)
        want = _scipy_edt(mask)
        assert np.array_equal(got, want), f"mismatch at shape ({h},{w}) density={density}"


def test_build_edt_end_to_end_matches_scipy_oracle() -> None:
    """`_build_edt` (the real call site, uncached) matches an independent
    scipy rebuild of the same rasterized mask, end to end."""
    from temper_placer.router_v6.channel_widths import _build_edt

    geom = MultiPolygon([box(0, 0, 20, 15), box(30, 5, 45, 25)])
    routing_space = _routing_space(geom)
    edt, mask, bounds = _build_edt(routing_space, 1.0, use_cache=False)

    expected_mask = _oracle._rasterize_boundary_mask(routing_space.available_area, bounds, 1.0)
    expected_edt = _scipy_edt(expected_mask)

    np.testing.assert_array_equal(mask, expected_mask)
    np.testing.assert_array_equal(edt, expected_edt)


def test_build_edt_raster_matches_oracle_on_asymmetric_hole_boundaries() -> None:
    """The migrated mask path keeps strict GEOS boundary semantics.

    This deliberately uses a non-axis-symmetric exterior and a hole whose
    edges land on grid samples; rectangular production fixtures alone would
    not exercise the slanted crossing and hole-boundary cases.
    """
    geom = Polygon(
        [(0.0, 0.0), (7.0, 1.0), (5.0, 8.0), (1.0, 6.0)],
        holes=[[(2.0, 2.0), (4.0, 2.5), (3.5, 4.5), (2.0, 4.0)]],
    )
    routing_space = _routing_space(MultiPolygon([geom]))
    _, got_mask, got_bounds = _build_edt(routing_space, 0.5, use_cache=False)
    want_mask = _oracle._rasterize_boundary_mask(geom, got_bounds, 0.5)
    np.testing.assert_array_equal(got_mask, want_mask)


def test_rasterize_boundary_mask_always_has_background_cell() -> None:
    """All-foreground reachability check (KTD8 spike section 4 divergence):
    `_exact_edt` returns +inf everywhere on an all-foreground mask (no
    background cell anywhere), while scipy returns a finite C-implementation
    artifact -- a real behavioral difference IF this call site could ever
    produce an all-foreground mask.

    It cannot, by construction: `xs`/`ys` in `_rasterize_boundary_mask`
    start exactly at `bounds`' own (min_x, min_y) -- the geometry's own
    bounding-box corner. A bounding box's minimum corner can never be
    strictly interior to the geometry it bounds (if it were, the geometry
    would have to extend past that corner in the direction that made the
    box tight, contradicting minimality), so `shapely.contains_xy` is
    always False there and cell (0, 0) of the mask is always background.
    This test verifies that reasoning empirically across varied geometries,
    including ones designed to stress it (rectangle exactly filling its own
    bounds, multi-part geometry, geometry touching the bounds on one edge
    only).
    """
    geoms = [
        MultiPolygon([box(0, 0, 10, 10)]),  # exactly fills its own bbox
        MultiPolygon([box(0, 0, 10, 10), box(20, 0, 30, 10)]),  # multi-part
        MultiPolygon([box(0, 0, 5, 5), box(0, 8, 5, 13)]),  # touches one edge only
        MultiPolygon([box(-5, -5, 5, 5)]),  # negative-coordinate bounds
    ]
    for geom in geoms:
        bounds = geom.bounds
        routing_space = _routing_space(geom)
        _, production_mask, production_bounds = _build_edt(
            routing_space, 1.0, use_cache=False
        )
        oracle_mask = _oracle._rasterize_boundary_mask(geom, bounds, 1.0)
        np.testing.assert_array_equal(production_mask, oracle_mask)
        assert not production_mask.all(), (
            f"all-foreground mask reachable for geom bounds={bounds}"
        )
        assert not production_mask[0, 0], "bounding-box min corner must be background"
        assert production_bounds == bounds


def test_compute_channel_widths_empty_space_still_empty() -> None:
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon(),
        total_area=100.0,
        obstacle_area=100.0,
        routing_area=0.0,
    )
    skeleton = extract_channel_skeleton(routing_space)
    widths = compute_channel_widths(routing_space, skeleton)
    assert widths.min_width == 0.0
    assert len(widths.node_widths) == 0
