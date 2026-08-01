"""Differential tests: temper-thermal Rust assembly vs the pure-Python
reference implementations.

The pre-migration implementations of ``_assemble_system`` and
``_trace_to_cell_coverage`` are pinned here as oracles (verbatim
semantics).  Any change to the Rust crate or the wrapper that disagrees
with the oracle fails here, bit-exactly.
"""

from __future__ import annotations

import random

import numpy as np
import pytest

from temper_placer.physics.thermal_fdm import (
    ThermalFDMConfig,
    _assemble_system,
    _trace_to_cell_coverage,
    solve_thermal_fdm,
)


def _reference_assemble(config, k_field, Q_field, h_field=None):
    """The pre-migration pure-Python assembly, verbatim (lil_matrix)."""
    from scipy.sparse import lil_matrix

    h = config.height_cells
    w = config.width_cells
    n = h * w
    cs = config.cell_size_mm
    dx2 = cs * cs
    dy2 = cs * cs

    A = lil_matrix((n, n), dtype=np.float64)
    b = np.zeros(n, dtype=np.float64)

    for row in range(h):
        for col in range(w):
            idx = row * w + col

            diag = 0.0
            k_c = k_field[row, col]

            if col + 1 < w:
                k_e = 2.0 / (1.0 / k_c + 1.0 / k_field[row, col + 1])
                coeff = k_e / dx2
                A[idx, row * w + col + 1] = -coeff
                diag += coeff
            elif _heatsink_face(row, col, "east", config):
                coeff = 2.0 * k_c / dx2
                diag += coeff
                b[idx] += coeff * config.ambient_C

            if col - 1 >= 0:
                k_w = 2.0 / (1.0 / k_c + 1.0 / k_field[row, col - 1])
                coeff = k_w / dx2
                A[idx, row * w + col - 1] = -coeff
                diag += coeff
            elif _heatsink_face(row, col, "west", config):
                coeff = 2.0 * k_c / dx2
                diag += coeff
                b[idx] += coeff * config.ambient_C

            if row + 1 < h:
                k_n = 2.0 / (1.0 / k_c + 1.0 / k_field[row + 1, col])
                coeff = k_n / dy2
                A[idx, (row + 1) * w + col] = -coeff
                diag += coeff
            elif _heatsink_face(row, col, "north", config):
                coeff = 2.0 * k_c / dy2
                diag += coeff
                b[idx] += coeff * config.ambient_C

            if row - 1 >= 0:
                k_s = 2.0 / (1.0 / k_c + 1.0 / k_field[row - 1, col])
                coeff = k_s / dy2
                A[idx, (row - 1) * w + col] = -coeff
                diag += coeff
            elif _heatsink_face(row, col, "south", config):
                coeff = 2.0 * k_c / dy2
                diag += coeff
                b[idx] += coeff * config.ambient_C

            if h_field is not None:
                h_cell = float(h_field[row, col])
                if h_cell > 0.0:
                    diag += h_cell
                    b[idx] += h_cell * config.ambient_C

            A[idx, idx] = diag
            b[idx] += Q_field[row, col]

    return A.tocsr(), b


def _heatsink_face(row, col, direction, config):
    h = config.height_cells
    w = config.width_cells
    hs = config.heatsink_edge.upper().strip()
    if direction == "north" and row == h - 1 and hs == "TOP":
        return True
    if direction == "south" and row == 0 and hs == "BOTTOM":
        return True
    if direction == "east" and col == w - 1 and hs == "RIGHT":
        return True
    return bool(direction == "west" and col == 0 and hs == "LEFT")


def _reference_trace(trace_start, trace_end, trace_width_mm, origin_mm, cell_size_mm, h, w):
    """The pre-migration pure-Python trace rasterisation, verbatim."""
    coverage = np.zeros((h, w), dtype=np.float64)
    x0, y0 = trace_start
    x1, y1 = trace_end
    ox, oy = origin_mm
    cs = cell_size_mm
    half_w = trace_width_mm / 2.0
    x_min = min(x0, x1) - half_w
    x_max = max(x0, x1) + half_w
    y_min = min(y0, y1) - half_w
    y_max = max(y0, y1) + half_w
    col_min = max(0, int(np.floor((x_min - ox) / cs)))
    col_max = min(w, int(np.ceil((x_max - ox) / cs)))
    row_min = max(0, int(np.floor((y_min - oy) / cs)))
    row_max = min(h, int(np.ceil((y_max - oy) / cs)))
    if col_max <= col_min or row_max <= row_min:
        return coverage
    sub = 4
    for r in range(row_min, row_max):
        for c in range(col_min, col_max):
            hit = 0
            for sr in range(sub):
                y_s = oy + (r + (sr + 0.5) / sub) * cs
                for sc in range(sub):
                    x_s = ox + (c + (sc + 0.5) / sub) * cs
                    if _ref_segment_distance(x_s, y_s, x0, y0, x1, y1) <= half_w:
                        hit += 1
            coverage[r, c] = hit / (sub * sub)
    return coverage


def _ref_segment_distance(px, py, ax, ay, bx, by):
    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-18:
        return float(np.sqrt((px - ax) ** 2 + (py - ay) ** 2))
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    return float(np.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2))


def _config(h=12, w=16, cs=0.5, hs_edge="TOP"):
    return ThermalFDMConfig(
        cell_size_mm=cs,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge=hs_edge,
    )


# ---------------------------------------------------------------------------
# Assembly parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hs_edge", ["TOP", "BOTTOM", "LEFT", "RIGHT"])
def test_assembly_matches_reference_bit_exact(hs_edge):
    rng = random.Random(20260731)
    for _ in range(10):
        h = rng.choice([1, 4, 9, 15])
        w = rng.choice([1, 5, 11, 18])
        cfg = _config(h, w, cs=rng.choice([0.25, 0.5, 1.0]), hs_edge=hs_edge)
        k_field = np.asarray([rng.random() * 380 + 0.1 for _ in range(h * w)]).reshape(h, w)
        q_field = np.asarray([rng.random() * 0.05 for _ in range(h * w)]).reshape(h, w)
        h_field = (
            None
            if rng.random() < 0.5
            else np.asarray([rng.random() * 2.0 for _ in range(h * w)]).reshape(h, w)
        )
        A_rust, b_rust = _assemble_system(cfg, k_field, q_field, h_field=h_field)
        A_ref, b_ref = _reference_assemble(cfg, k_field, q_field, h_field=h_field)
        np.testing.assert_array_equal(A_rust.toarray(), A_ref.toarray())
        np.testing.assert_array_equal(b_rust, b_ref)


# ---------------------------------------------------------------------------
# KTD9 spike: faer vs scipy solver parity (measured contract).
# Executed 2026-07-31. Verdict: faer numerically viable (max|T_faer -
# T_scipy| = 5.1e-13 K on the 2500-cell FDM matrix, residuals ~1e-15) but
# adoption NOT warranted: no perf win (scipy spsolve is C-speed at these
# sizes) and it would break bit-parity with the deterministic reference
# for zero measured benefit. scipy stays; the contract below is the
# recorded measurement for any future solver change.
# ---------------------------------------------------------------------------


def test_solve_thermal_fdm_end_to_end_identical():
    rng = random.Random(3)
    cfg = _config(10, 14, cs=1.0, hs_edge="BOTTOM")
    k_field = np.asarray([0.3 + rng.random() for _ in range(140)]).reshape(10, 14)
    devices = {"Q1": (5.0, 5.0), "Q2": (9.0, 3.0)}
    power_map = {"Q1": 15.0, "Q2": 7.5}

    import temper_placer.physics.thermal_fdm as tfdm

    original = tfdm._assemble_system
    try:
        tfdm._assemble_system = _reference_assemble
        result_ref = solve_thermal_fdm(
            config=cfg, devices=devices, power_map=power_map, copper_grid=k_field
        )
    finally:
        tfdm._assemble_system = original
    result_rust = solve_thermal_fdm(
        config=cfg, devices=devices, power_map=power_map, copper_grid=k_field
    )
    assert result_rust.is_usable and result_ref.is_usable
    np.testing.assert_array_equal(result_rust.field.grid, result_ref.field.grid)


# ---------------------------------------------------------------------------
# Trace rasterisation parity
# ---------------------------------------------------------------------------


def test_trace_to_cell_coverage_matches_reference_bit_exact():
    rng = random.Random(7)
    for _ in range(25):
        h, w = rng.choice([(10, 12), (20, 30), (6, 6)])
        cs = rng.choice([0.25, 0.5, 1.0])
        x0 = rng.random() * w * cs
        y0 = rng.random() * h * cs
        x1 = rng.random() * w * cs
        y1 = rng.random() * h * cs
        tw = rng.choice([0.2, 0.5, 0.8])
        rust = _trace_to_cell_coverage((x0, y0), (x1, y1), tw, (0.0, 0.0), cs, h, w)
        ref = _reference_trace((x0, y0), (x1, y1), tw, (0.0, 0.0), cs, h, w)
        np.testing.assert_array_equal(rust, ref)


def test_trace_to_cell_coverage_degenerate_and_offgrid():
    # zero-length segment (the 1e-18 fallback)
    rust = _trace_to_cell_coverage((5.0, 5.0), (5.0, 5.0), 0.5, (0.0, 0.0), 0.5, 10, 10)
    ref = _reference_trace((5.0, 5.0), (5.0, 5.0), 0.5, (0.0, 0.0), 0.5, 10, 10)
    np.testing.assert_array_equal(rust, ref)
    # trace fully off-grid
    rust = _trace_to_cell_coverage((100.0, 100.0), (105.0, 102.0), 0.5, (0.0, 0.0), 0.5, 10, 10)
    ref = _reference_trace((100.0, 100.0), (105.0, 102.0), 0.5, (0.0, 0.0), 0.5, 10, 10)
    np.testing.assert_array_equal(rust, ref)
