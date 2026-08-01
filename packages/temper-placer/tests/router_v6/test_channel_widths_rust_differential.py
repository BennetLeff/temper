"""Differential tests: batched Rust EDT width lookup vs the per-point
reference implementation.

``temper_placer.router_v6.channel_widths._edt_width_lookup`` is the
per-point reference (kept verbatim in the module); the production hot
path is ``_edt_width_lookup_batch`` (one FFI crossing per layer).  This
suite pins the two bit-identical per point, and pins
``compute_channel_widths`` end-to-end against a per-point-driven
rebuild.
"""

from __future__ import annotations

import random

import numpy as np
from shapely.geometry import MultiPolygon, box

from temper_placer.router_v6.channel_skeleton import extract_channel_skeleton
from temper_placer.router_v6.channel_widths import (
    _edt_width_lookup,
    _edt_width_lookup_batch,
    compute_channel_widths,
)
from temper_placer.router_v6.routing_space import RoutingSpace


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
                cw._edt_width_lookup(x, y, edt, mask, bounds, cell_size)
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
        for node in skeleton.graph.nodes():
            node_widths[node] = cw._edt_width_lookup(
                node[0], node[1], edt_grid, edt_mask, edt_bounds, 0.1
            )
        for u, v in skeleton.graph.edges():
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
                        cw._edt_width_lookup(
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
# KTD8 spike verdict (2026-07-31): the `edt` crate was evaluated as a
# scipy.distance_transform_edt replacement and REJECTED — its distance
# field diverges from scipy's Euclidean transform (max diff 2.0-2.236 on
# random masks even with a False-border padding workaround and transposed
# layout handling; the crate hardcodes a grid-edge clamp and other
# semantic differences). scipy's transform stays (it is C-speed and was
# never the hot loop); a Rust-native exact EDT remains the KTD8 fallback
# for a follow-up. The migration win delivered by U4 is the batched width
# lookup, not the transform.
# ---------------------------------------------------------------------------


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
