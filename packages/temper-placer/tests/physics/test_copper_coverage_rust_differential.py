"""Differential tests: Rust polygon rasterisation and the copper
coverage grid vs the original pure-numpy implementations.

The pre-migration implementations are pinned here as oracles — the
differential targets for the Rust rasteriser in temper-geometry and
the wrapper in ``temper_placer.physics.copper_coverage``.  Any change
to the Rust implementation or the wrapper that disagrees with the
oracle fails here.
"""

from __future__ import annotations

import random

import numpy as np

from temper_placer.core.board import Board, LayerStackup
from temper_placer.physics.copper_coverage import _rasterise_polygon_mask, copper_coverage_grid
from temper_placer.physics.thermal_fdm import ThermalFDMConfig


def _numpy_rasterise_oracle(
    polygon: list[tuple[float, float]],
    height_cells: int,
    width_cells: int,
    ox: float,
    oy: float,
    cs: float,
) -> np.ndarray:
    """The pre-migration pure-Python ray-casting loop, verbatim."""
    mask = np.zeros((height_cells, width_cells), dtype=bool)
    n = len(polygon)
    if n < 3:
        return mask
    px = np.array([p[0] for p in polygon], dtype=np.float64)
    py = np.array([p[1] for p in polygon], dtype=np.float64)
    for row in range(height_cells):
        cy = oy + (row + 0.5) * cs
        for col in range(width_cells):
            cx = ox + (col + 0.5) * cs
            inside = False
            j = n - 1
            for i in range(n):
                yi = py[i]
                yj = py[j]
                if ((yi > cy) != (yj > cy)) and (
                    cx < (px[j] - px[i]) * (cy - yi) / (yj - yi) + px[i]
                ):
                    inside = not inside
                j = i
            mask[row, col] = inside
    return mask


def _random_polygon(rng: random.Random, extent: float, n: int) -> list[tuple[float, float]]:
    """Random polygon within [0, extent] x [0, extent] (star-shaped around
    a random centre so it is usually simple)."""
    cx, cy = rng.uniform(0.2, 0.8) * extent, rng.uniform(0.2, 0.8) * extent
    angles = sorted(rng.uniform(0.0, 2 * np.pi) for _ in range(n))
    pts = []
    for a in angles:
        r = rng.uniform(0.05, 0.5) * extent
        pts.append((cx + r * np.cos(a), cy + r * np.sin(a)))
    return pts


def _board_with_outline(polygon: list[tuple[float, float]]) -> Board:
    return Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        layer_stackup=LayerStackup.default_4layer(),
        outline_polygon=polygon,
    )


def _mini_fdm_config(height_cells: int, width_cells: int, cell_size_mm: float) -> ThermalFDMConfig:
    return ThermalFDMConfig(
        cell_size_mm=cell_size_mm,
        height_cells=height_cells,
        width_cells=width_cells,
        origin_mm=(0.0, 0.0),
    )


# ---------------------------------------------------------------------------
# Rasteriser parity (bit-exact masks)
# ---------------------------------------------------------------------------


def test_rasterise_matches_oracle_on_random_polygons() -> None:
    rng = random.Random(20260731)
    for _ in range(30):
        poly = _random_polygon(rng, extent=100.0, n=rng.randrange(3, 12))
        h, w, cs = rng.choice([(10, 10, 5.0), (16, 24, 3.0), (7, 13, 8.0), (20, 20, 4.0)])
        ox, oy = rng.uniform(-5, 5), rng.uniform(-5, 5)
        rust = _rasterise_polygon_mask(poly, h, w, ox, oy, cs)
        python = _numpy_rasterise_oracle(poly, h, w, ox, oy, cs)
        np.testing.assert_array_equal(rust, python)


def test_rasterise_matches_oracle_on_degenerate_polygons() -> None:
    rng = random.Random(9)
    cases: list[list[tuple[float, float]]] = [
        [],  # no vertices
        [(0.0, 0.0)],  # one vertex
        [(0.0, 0.0), (10.0, 0.0)],  # segment
        [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (10.0, 0.0)],  # self-touching
        [(0.0, 0.0), (0.0, 0.0), (10.0, 10.0), (0.0, 10.0)],  # duplicate vertex
        [(0.0, 0.0), (10.0, 10.0), (20.0, 0.0)],  # triangle with diagonal edge
    ]
    for _ in range(10):
        cases.append(_random_polygon(rng, extent=50.0, n=rng.randrange(1, 6)))
    for poly in cases:
        rust = _rasterise_polygon_mask(poly, 12, 12, 0.0, 0.0, 4.0)
        python = _numpy_rasterise_oracle(poly, 12, 12, 0.0, 0.0, 4.0)
        np.testing.assert_array_equal(rust, python)


def test_rasterise_matches_oracle_with_axis_aligned_grid() -> None:
    # Cell centres land exactly on polygon edges/vertices (origin -0.5).
    poly = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    rust = _rasterise_polygon_mask(poly, 5, 5, -0.5, -0.5, 1.0)
    python = _numpy_rasterise_oracle(poly, 5, 5, -0.5, -0.5, 1.0)
    np.testing.assert_array_equal(rust, python)


# ---------------------------------------------------------------------------
# Grid parity (copper_coverage_grid end to end)
# ---------------------------------------------------------------------------


def test_coverage_grid_matches_python_end_to_end() -> None:
    rng = random.Random(3)
    for _ in range(8):
        poly = _random_polygon(rng, extent=100.0, n=rng.randrange(3, 10))
        board = _board_with_outline(poly)
        cfg = _mini_fdm_config(16, 24, 3.0)
        # The wrapper now routes through Rust; the oracle rebuilds the grid
        # with the pure-numpy rasteriser pinned above.
        grid = copper_coverage_grid(board, cfg)
        oracle_grid = _grid_with_oracle_rasteriser(board, cfg)
        np.testing.assert_array_equal(grid, oracle_grid)


def _grid_with_oracle_rasteriser(board: Board, cfg: ThermalFDMConfig) -> np.ndarray:
    """copper_coverage_grid with the numpy rasteriser forced back in via
    monkeypatching — the grid function itself is the production code."""
    import temper_placer.physics.copper_coverage as cc

    original = cc._rasterise_polygon_mask
    cc._rasterise_polygon_mask = _numpy_rasterise_oracle
    try:
        return copper_coverage_grid(board, cfg)
    finally:
        cc._rasterise_polygon_mask = original


def test_coverage_grid_rect_board_unchanged() -> None:
    # Rectangular boards never touched the rasteriser; the grid must be
    # unchanged end to end.
    board = Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        layer_stackup=LayerStackup.default_4layer(),
        keepouts=[(0.0, 0.0, 20.0, 20.0)],
    )
    cfg = _mini_fdm_config(20, 20, 5.0)
    grid = copper_coverage_grid(board, cfg)
    assert grid.shape == (20, 20)
    assert np.all(grid[10, 10] == np.float64(0.4))  # 2x1oz planes / 4 layers
    assert np.all(grid[:4, :4] == np.float64(0.0))  # keepout corner
