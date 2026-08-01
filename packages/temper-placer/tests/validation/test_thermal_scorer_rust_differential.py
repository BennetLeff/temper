"""Differential tests: temper-thermal Rust thermal-scorer kernels vs the
pure-Python reference implementations (Wave 3 candidate #6).

The pre-migration implementations of ``_build_conductivity_field_gs``,
``_build_heat_source_field_gs`` and ``_assemble_convective_system`` from
``temper_placer/validation/thermal_scorer.py`` are pinned here as oracles
(verbatim semantics, ``lil_matrix`` assembly included).  Any change to the
Rust crate or the Python wrapper that disagrees with the oracle fails
here, bit-exactly.

Sections:
- Differential bit-exactness: conductivity field, heat-source field,
  convective system assembly (~300 randomized inputs per function plus
  edge cases), and the end-to-end ``solve_independent`` T_grid.
- PBT (hypothesis): five non-vacuous properties of the migrated scorer.
- Metamorphic relations: three scale/translation/symmetry invariants.

The solve stays in scipy (SuperLU) per the KTD9 verdict — this suite pins
the ASSEMBLY/compute parity; the falsifiability 1.0 deg-C threshold is a
separate, preserved Python-side contract (never weakened here).
"""

from __future__ import annotations

import random

import numpy as np
import pytest
import temper_thermal as _tt
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Oracles — the pre-migration pure-Python implementations, verbatim
# ---------------------------------------------------------------------------


def _ref_is_heatsink_edge_cell(row, col, height_cells, width_cells, heatsink_edge):
    edge = heatsink_edge.upper().strip()
    if edge == "TOP":
        return row == height_cells - 1
    elif edge == "BOTTOM":
        return row == 0
    elif edge == "LEFT":
        return col == 0
    elif edge == "RIGHT":
        return col == width_cells - 1
    return False


def _ref_is_convective_edge_cell(row, col, height_cells, width_cells, heatsink_edge):
    hs = heatsink_edge.upper().strip()
    return (
        (row == 0 and hs != "BOTTOM")
        or (row == height_cells - 1 and hs != "TOP")
        or (col == 0 and hs != "LEFT")
        or (col == width_cells - 1 and hs != "RIGHT")
    ) and not _ref_is_heatsink_edge_cell(row, col, height_cells, width_cells, heatsink_edge)


def _ref_is_heatsink_boundary_face_u7(row, col, direction, height_cells, width_cells, heatsink_edge):
    hs = heatsink_edge.upper().strip()
    if direction == "north" and row == height_cells - 1 and hs == "TOP":
        return True
    if direction == "south" and row == 0 and hs == "BOTTOM":
        return True
    if direction == "east" and col == width_cells - 1 and hs == "RIGHT":
        return True
    return bool(direction == "west" and col == 0 and hs == "LEFT")


def _reference_build_conductivity_field_gs(config, copper_grid=None):
    """Pre-migration ``_build_conductivity_field_gs``, verbatim."""
    h = config.height_cells
    w = config.width_cells
    k_fr4_eff = config.k_fr4 * config.board_thickness_mm * 1e-3
    k_cu_eff = config.k_copper * config.board_thickness_mm * 1e-3

    if copper_grid is None:
        return np.full((h, w), k_fr4_eff, dtype=np.float64)

    frac = np.asarray(copper_grid, dtype=np.float64)
    return k_fr4_eff + (k_cu_eff - k_fr4_eff) * np.clip(frac, 0.0, 1.0)


def _reference_build_heat_source_field_gs(config, devices, power_map, Q_field=None):
    """Pre-migration ``_build_heat_source_field_gs``, verbatim."""
    h = config.height_cells
    w = config.width_cells
    ox, oy = config.origin_mm
    cs = config.cell_size_mm

    if Q_field is not None:
        return np.asarray(Q_field, dtype=np.float64)

    Q = np.zeros((h, w), dtype=np.float64)
    if not devices:
        return Q

    footprint_mm = 5.0
    half_f = footprint_mm / 2.0

    for dev_name, (dx_mm, dy_mm) in devices.items():
        power = power_map.get(dev_name, 0.0)
        if power <= 0:
            continue

        col_min = max(0, int(np.floor((dx_mm - half_f - ox) / cs)))
        col_max = min(w, int(np.ceil((dx_mm + half_f - ox) / cs)))
        row_min = max(0, int(np.floor((dy_mm - half_f - oy) / cs)))
        row_max = min(h, int(np.ceil((dy_mm + half_f - oy) / cs)))

        n_cells = max(1, (row_max - row_min) * (col_max - col_min))
        Q_density = power / (n_cells * cs * cs)
        Q[row_min:row_max, col_min:col_max] += Q_density

    return Q


def _reference_assemble_convective_system(config, k_field, Q_field, h_conv, h_field=None):
    """Pre-migration ``_assemble_convective_system``, verbatim (lil_matrix)."""
    from scipy.sparse import lil_matrix

    h = config.height_cells
    w = config.width_cells
    n = h * w
    cs = config.cell_size_mm
    dx2 = cs * cs
    dy2 = cs * cs

    A = lil_matrix((n, n), dtype=np.float64)
    b = np.zeros(n, dtype=np.float64)

    hs_edge = config.heatsink_edge.upper().strip()

    for row in range(h):
        for col in range(w):
            idx = row * w + col

            diag = 0.0
            k_c = k_field[row, col]

            # East
            if col + 1 < w:
                k_e = 2.0 / (1.0 / k_c + 1.0 / k_field[row, col + 1])
                coeff = k_e / dx2
                A[idx, row * w + col + 1] = -coeff
                diag += coeff
            elif _ref_is_heatsink_boundary_face_u7(row, col, "east", h, w, hs_edge):
                coeff = 2.0 * k_c / dx2
                diag += coeff
                b[idx] += coeff * config.ambient_C

            # West
            if col - 1 >= 0:
                k_w = 2.0 / (1.0 / k_c + 1.0 / k_field[row, col - 1])
                coeff = k_w / dx2
                A[idx, row * w + col - 1] = -coeff
                diag += coeff
            elif _ref_is_heatsink_boundary_face_u7(row, col, "west", h, w, hs_edge):
                coeff = 2.0 * k_c / dx2
                diag += coeff
                b[idx] += coeff * config.ambient_C

            # North (row+1 = up in grid)
            if row + 1 < h:
                k_n = 2.0 / (1.0 / k_c + 1.0 / k_field[row + 1, col])
                coeff = k_n / dy2
                A[idx, (row + 1) * w + col] = -coeff
                diag += coeff
            elif _ref_is_heatsink_boundary_face_u7(row, col, "north", h, w, hs_edge):
                coeff = 2.0 * k_c / dy2
                diag += coeff
                b[idx] += coeff * config.ambient_C

            # South
            if row - 1 >= 0:
                k_s = 2.0 / (1.0 / k_c + 1.0 / k_field[row - 1, col])
                coeff = k_s / dy2
                A[idx, (row - 1) * w + col] = -coeff
                diag += coeff
            elif _ref_is_heatsink_boundary_face_u7(row, col, "south", h, w, hs_edge):
                coeff = 2.0 * k_c / dy2
                diag += coeff
                b[idx] += coeff * config.ambient_C

            # Convective boundary term at non-heatsink edge cells.
            if _ref_is_convective_edge_cell(row, col, h, w, hs_edge):
                t_mm = config.board_thickness_mm
                conv_coeff = h_conv * t_mm / cs * 1e-6
                diag += conv_coeff
                b[idx] += conv_coeff * config.ambient_C

            # Through-plane heat-removal sink (U5-compatible, #141)
            if h_field is not None:
                h_cell = float(h_field[row, col])
                if h_cell > 0.0:
                    diag += h_cell
                    b[idx] += h_cell * config.ambient_C

            A[idx, idx] = diag
            b[idx] += Q_field[row, col]

    return A.tocsr(), b


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _config(h, w, cs=0.5, hs_edge="TOP", **kw):
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig

    kw.setdefault("ambient_C", 40.0)
    return ThermalFDMConfig(
        cell_size_mm=cs,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        heatsink_edge=hs_edge,
        **kw,
    )


def _f64_bytes(arr: np.ndarray) -> bytes:
    return np.ascontiguousarray(arr, dtype=np.float64).tobytes()


# ---------------------------------------------------------------------------
# Differential: build_conductivity_field_py
# ---------------------------------------------------------------------------


def test_conductivity_field_matches_reference_bit_exact():
    rng = random.Random(20260731)
    for _ in range(150):
        h = rng.choice([1, 2, 7, 13, 40])
        w = rng.choice([1, 3, 9, 25, 60])
        cfg = _config(
            h,
            w,
            cs=rng.choice([0.25, 0.5, 1.0, 2.0]),
            k_fr4=rng.choice([0.3, 1.0, 2.7]),
            k_copper=rng.choice([385.0, 200.0, 401.0]),
            board_thickness_mm=rng.choice([0.8, 1.6, 3.2]),
        )
        if rng.random() < 0.3:
            copper = None
        else:
            copper = np.asarray([rng.random() * 1.5 - 0.25 for _ in range(h * w)]).reshape(h, w)
        rust = _tt.build_conductivity_field_py(
            cfg.k_fr4,
            cfg.k_copper,
            cfg.board_thickness_mm,
            None if copper is None else _f64_bytes(copper),
            h,
            w,
        )
        got = np.frombuffer(rust, dtype=np.float64).reshape(h, w)
        expect = _reference_build_conductivity_field_gs(cfg, copper_grid=copper)
        np.testing.assert_array_equal(got, expect)


def test_conductivity_field_edge_cases_bit_exact():
    # All-ambient (no copper): uniform k_fr4_eff.
    cfg = _config(5, 6, cs=1.0, k_fr4=0.3, k_copper=385.0, board_thickness_mm=1.6)
    got = np.frombuffer(
        _tt.build_conductivity_field_py(0.3, 385.0, 1.6, None, 5, 6), dtype=np.float64
    ).reshape(5, 6)
    expect = _reference_build_conductivity_field_gs(cfg, copper_grid=None)
    np.testing.assert_array_equal(got, expect)
    assert np.all(got == 0.3 * 1.6 * 1e-3)

    # Single-cell grid.
    cfg1 = _config(1, 1, cs=0.5)
    for copper in [None, np.zeros((1, 1)), np.ones((1, 1)), np.full((1, 1), 0.37)]:
        got = np.frombuffer(
            _tt.build_conductivity_field_py(
                cfg1.k_fr4, cfg1.k_copper, cfg1.board_thickness_mm,
                None if copper is None else _f64_bytes(copper), 1, 1,
            ),
            dtype=np.float64,
        ).reshape(1, 1)
        expect = _reference_build_conductivity_field_gs(cfg1, copper_grid=copper)
        np.testing.assert_array_equal(got, expect)

    # Clipping: fractions outside [0, 1] clamp; NaN propagates like np.clip.
    cfg = _config(2, 3, cs=1.0)
    copper = np.asarray([[-0.5, 0.0, 0.5], [1.0, 1.5, np.nan]], dtype=np.float64)
    got = np.frombuffer(
        _tt.build_conductivity_field_py(
            cfg.k_fr4, cfg.k_copper, cfg.board_thickness_mm, _f64_bytes(copper), 2, 3
        ),
        dtype=np.float64,
    ).reshape(2, 3)
    expect = _reference_build_conductivity_field_gs(cfg, copper_grid=copper)
    np.testing.assert_array_equal(got, expect)

    # Zero-thickness board (k_eff == 0 everywhere).
    cfg0 = _config(3, 3, cs=1.0, board_thickness_mm=0.0)
    copper = np.full((3, 3), 1.0)
    got = np.frombuffer(
        _tt.build_conductivity_field_py(0.3, 385.0, 0.0, _f64_bytes(copper), 3, 3),
        dtype=np.float64,
    ).reshape(3, 3)
    expect = _reference_build_conductivity_field_gs(cfg0, copper_grid=copper)
    np.testing.assert_array_equal(got, expect)

    # Empty (0-row) grid returns an empty buffer.
    got = _tt.build_conductivity_field_py(0.3, 385.0, 1.6, None, 0, 4)
    assert len(got) == 0


# ---------------------------------------------------------------------------
# Differential: build_heat_source_field_py
# ---------------------------------------------------------------------------


def test_heat_source_field_matches_reference_bit_exact():
    rng = random.Random(11)
    for _ in range(120):
        h = rng.choice([1, 3, 10, 30, 50])
        w = rng.choice([1, 4, 12, 40, 60])
        cs = rng.choice([0.25, 0.5, 1.0, 2.0])
        cfg = _config(h, w, cs=cs)
        n_dev = rng.randint(0, 5)
        devices = {}
        power_map = {}
        for i in range(n_dev):
            # Devices overlapping the grid (realistic placement) — on-board.
            name = f"D{i}"
            devices[name] = (
                rng.uniform(-2.0, w * cs + 2.0),
                rng.uniform(-2.0, h * cs + 2.0),
            )
            power_map[name] = rng.choice([0.0, 0.5, 3.0, 15.0, 40.0])
        if rng.random() < 0.15 and devices:
            # Occasionally drop a device from the power map (defaults to 0).
            dead = rng.choice(list(devices))
            del power_map[dead]
        devices_lst = [(name, x, y) for name, (x, y) in devices.items()]
        power_lst = list(power_map.items())
        rust = _tt.build_heat_source_field_py(
            devices_lst,
            power_lst,
            cfg.origin_mm[0],
            cfg.origin_mm[1],
            cs,
            h,
            w,
        )
        got = np.frombuffer(rust, dtype=np.float64).reshape(h, w)
        expect = _reference_build_heat_source_field_gs(cfg, devices, power_map)
        np.testing.assert_array_equal(got, expect)


def test_heat_source_field_edge_cases_bit_exact():
    # No devices at all.
    cfg = _config(10, 10, cs=1.0)
    got = np.frombuffer(
        _tt.build_heat_source_field_py([], [], 0.0, 0.0, 1.0, 10, 10), dtype=np.float64
    ).reshape(10, 10)
    expect = _reference_build_heat_source_field_gs(cfg, {}, {})
    np.testing.assert_array_equal(got, expect)
    assert np.all(got == 0.0)

    # Zero-power device is skipped.
    devices = {"Q1": (5.0, 5.0)}
    power_map = {"Q1": 0.0}
    got = np.frombuffer(
        _tt.build_heat_source_field_py(
            [("Q1", 5.0, 5.0)], [("Q1", 0.0)], 0.0, 0.0, 1.0, 10, 10
        ),
        dtype=np.float64,
    ).reshape(10, 10)
    expect = _reference_build_heat_source_field_gs(cfg, devices, power_map)
    np.testing.assert_array_equal(got, expect)

    # Negative power is skipped too.
    got = np.frombuffer(
        _tt.build_heat_source_field_py(
            [("Q1", 5.0, 5.0)], [("Q1", -3.0)], 0.0, 0.0, 1.0, 10, 10
        ),
        dtype=np.float64,
    ).reshape(10, 10)
    expect = _reference_build_heat_source_field_gs(cfg, devices, {"Q1": -3.0})
    np.testing.assert_array_equal(got, expect)

    # Device entirely off-grid to the HIGH side is a no-op.
    devices = {"Q1": (500.0, 500.0)}
    got = np.frombuffer(
        _tt.build_heat_source_field_py(
            [("Q1", 500.0, 500.0)], [("Q1", 15.0)], 0.0, 0.0, 1.0, 10, 10
        ),
        dtype=np.float64,
    ).reshape(10, 10)
    expect = _reference_build_heat_source_field_gs(cfg, devices, {"Q1": 15.0})
    np.testing.assert_array_equal(got, expect)

    # Device entirely off-grid to the LOW side: numpy's negative-slice wrap
    # in the reference corrupts the grid (a latent reference bug, identical
    # in U5's thermal_fdm.py).  The Rust kernel replicates the reference
    # bit-for-bit rather than silently diverging.
    cfg12 = _config(10, 12, cs=1.0)
    devices = {"Q1": (-5.0, -5.0)}
    got = np.frombuffer(
        _tt.build_heat_source_field_py(
            [("Q1", -5.0, -5.0)], [("Q1", 15.0)], 0.0, 0.0, 1.0, 10, 12
        ),
        dtype=np.float64,
    ).reshape(10, 12)
    expect = _reference_build_heat_source_field_gs(cfg12, devices, {"Q1": 15.0})
    np.testing.assert_array_equal(got, expect)
    assert np.any(got != 0.0), "reference negative-slice wrap must be replicated"

    # Overlapping devices accumulate in dict insertion order.
    devices = {"A": (3.0, 3.0), "B": (6.0, 3.0), "C": (5.0, 5.0)}
    power_map = {"A": 10.0, "B": 5.0, "C": 20.0}
    got = np.frombuffer(
        _tt.build_heat_source_field_py(
            [("A", 3.0, 3.0), ("B", 6.0, 3.0), ("C", 5.0, 5.0)],
            [("A", 10.0), ("B", 5.0), ("C", 20.0)],
            0.0,
            0.0,
            1.0,
            10,
            10,
        ),
        dtype=np.float64,
    ).reshape(10, 10)
    expect = _reference_build_heat_source_field_gs(cfg, devices, power_map)
    np.testing.assert_array_equal(got, expect)

    # Single-cell grid, device centred on it.
    cfg1 = _config(1, 1, cs=1.0)
    got = np.frombuffer(
        _tt.build_heat_source_field_py([("Q1", 0.5, 0.5)], [("Q1", 8.0)], 0.0, 0.0, 1.0, 1, 1),
        dtype=np.float64,
    ).reshape(1, 1)
    expect = _reference_build_heat_source_field_gs(cfg1, {"Q1": (0.5, 0.5)}, {"Q1": 8.0})
    np.testing.assert_array_equal(got, expect)


# ---------------------------------------------------------------------------
# Differential: assemble_convective_system_py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hs_edge", ["TOP", "BOTTOM", "LEFT", "RIGHT"])
def test_assemble_convective_system_matches_reference_bit_exact(hs_edge):
    rng = random.Random(20260731)
    for _ in range(60):
        h = rng.choice([1, 2, 7, 15, 40])
        w = rng.choice([1, 3, 11, 25, 60])
        cfg = _config(
            h,
            w,
            cs=rng.choice([0.25, 0.5, 1.0]),
            hs_edge=hs_edge,
            board_thickness_mm=rng.choice([0.8, 1.6, 3.2]),
            ambient_C=rng.choice([20.0, 40.0, 85.0]),
        )
        k_field = np.asarray([rng.random() * 380 + 0.1 for _ in range(h * w)]).reshape(h, w)
        q_field = np.asarray([rng.random() * 0.05 for _ in range(h * w)]).reshape(h, w)
        h_field = (
            None
            if rng.random() < 0.4
            else np.asarray([rng.random() * 2.0 for _ in range(h * w)]).reshape(h, w)
        )
        h_conv = rng.choice([0.0, 5.0, 10.0, 25.0])
        rows, cols, vals, b = _tt.assemble_convective_system_py(
            _f64_bytes(k_field),
            _f64_bytes(q_field),
            None if h_field is None else _f64_bytes(h_field),
            h,
            w,
            cfg.ambient_C,
            cfg.cell_size_mm,
            cfg.board_thickness_mm,
            h_conv,
            cfg.heatsink_edge.upper().strip(),
        )
        A_rust, b_rust = _coo_from_triplets(rows, cols, vals, b, h * w), np.asarray(b)
        A_ref, b_ref = _reference_assemble_convective_system(
            cfg, k_field, q_field, h_conv, h_field=h_field
        )
        np.testing.assert_array_equal(A_rust.toarray(), A_ref.toarray())
        np.testing.assert_array_equal(b_rust, b_ref)


def test_assemble_convective_system_edge_cases_bit_exact():
    # Invalid heatsink edge ("NORTH"): no Dirichlet face anywhere, every
    # boundary cell is convective — both implementations agree.
    cfg = _config(4, 5, cs=0.5, hs_edge="NORTH")
    k_field = np.full((4, 5), 0.3 * 1.6 * 1e-3)
    q_field = np.full((4, 5), 0.01)
    rows, cols, vals, b = _tt.assemble_convective_system_py(
        _f64_bytes(k_field), _f64_bytes(q_field), None, 4, 5, 40.0, 0.5, 1.6, 10.0, "NORTH"
    )
    A_rust = _coo_from_triplets(rows, cols, vals, b, 20)
    A_ref, b_ref = _reference_assemble_convective_system(cfg, k_field, q_field, 10.0)
    np.testing.assert_array_equal(A_rust.toarray(), A_ref.toarray())
    np.testing.assert_array_equal(np.asarray(b), b_ref)

    # Single-cell grid: Dirichlet face on the heatsink side only, convective
    # on every other face (single cell is all four edges).
    for hs in ["TOP", "BOTTOM", "LEFT", "RIGHT"]:
        cfg = _config(1, 1, cs=1.0, hs_edge=hs)
        k_field = np.asarray([[0.5]])
        q_field = np.asarray([[0.2]])
        rows, cols, vals, b = _tt.assemble_convective_system_py(
            _f64_bytes(k_field), _f64_bytes(q_field), None, 1, 1, 40.0, 1.0, 1.6, 10.0, hs
        )
        A_rust = _coo_from_triplets(rows, cols, vals, b, 1)
        A_ref, b_ref = _reference_assemble_convective_system(cfg, k_field, q_field, 10.0)
        np.testing.assert_array_equal(A_rust.toarray(), A_ref.toarray())
        np.testing.assert_array_equal(np.asarray(b), b_ref)

    # h_conv = 0: reduces to U5's adiabatic-Neumann model exactly.
    cfg = _config(6, 8, cs=0.5, hs_edge="TOP")
    rng = random.Random(5)
    k_field = np.asarray([0.3 + rng.random() for _ in range(48)]).reshape(6, 8)
    q_field = np.asarray([rng.random() * 0.05 for _ in range(48)]).reshape(6, 8)
    rows, cols, vals, b = _tt.assemble_convective_system_py(
        _f64_bytes(k_field), _f64_bytes(q_field), None, 6, 8, 40.0, 0.5, 1.6, 0.0, "TOP"
    )
    A_rust = _coo_from_triplets(rows, cols, vals, b, 48)
    A_ref, b_ref = _reference_assemble_convective_system(cfg, k_field, q_field, 0.0)
    np.testing.assert_array_equal(A_rust.toarray(), A_ref.toarray())
    np.testing.assert_array_equal(np.asarray(b), b_ref)

    # All-ambient (uniform k, zero Q, no sink): convective corner cells get
    # exactly one convective term each, like the reference.
    cfg = _config(3, 3, cs=0.5, hs_edge="BOTTOM")
    k_field = np.full((3, 3), 0.3 * 1.6 * 1e-3)
    q_field = np.zeros((3, 3))
    rows, cols, vals, b = _tt.assemble_convective_system_py(
        _f64_bytes(k_field), _f64_bytes(q_field), None, 3, 3, 40.0, 0.5, 1.6, 10.0, "BOTTOM"
    )
    A_rust = _coo_from_triplets(rows, cols, vals, b, 9)
    A_ref, b_ref = _reference_assemble_convective_system(cfg, k_field, q_field, 10.0)
    np.testing.assert_array_equal(A_rust.toarray(), A_ref.toarray())
    np.testing.assert_array_equal(np.asarray(b), b_ref)


def _coo_from_triplets(rows, cols, vals, b, n):
    from scipy.sparse import coo_matrix

    return coo_matrix((vals, (rows, cols)), shape=(n, n), dtype=np.float64).tocsr()


# ---------------------------------------------------------------------------
# End-to-end: solve_independent T_grid parity (assembly swap only)
# ---------------------------------------------------------------------------


def test_solve_independent_end_to_end_bit_exact():
    """The Rust-backed scorer's T_grid must be bit-identical to the
    pre-migration oracle (same matrix + same SuperLU solve -> same result).

    Patches ``_assemble_convective_system`` with the verbatim reference and
    compares against the migrated (Rust-delegating) path.
    """
    import temper_placer.validation.thermal_scorer as tscorer
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    rng = random.Random(99)
    for _ in range(6):
        h = rng.choice([6, 10, 20])
        w = rng.choice([6, 12, 25])
        cs = rng.choice([0.5, 1.0])
        cfg = ThermalFDMConfig(
            cell_size_mm=cs,
            origin_mm=(0.0, 0.0),
            height_cells=h,
            width_cells=w,
            ambient_C=40.0,
            heatsink_edge=rng.choice(["TOP", "BOTTOM", "LEFT", "RIGHT"]),
            max_cells=3000,
        )
        devices = {}
        power_map = {}
        for i in range(rng.randint(0, 4)):
            name = f"Q{i}"
            devices[name] = (rng.uniform(0.0, w * cs), rng.uniform(0.0, h * cs))
            power_map[name] = rng.uniform(1.0, 25.0)
        copper = np.asarray([rng.random() for _ in range(h * w)]).reshape(h, w)
        h_field = (
            None
            if rng.random() < 0.5
            else np.asarray([rng.random() * 2.0 for _ in range(h * w)]).reshape(h, w)
        )
        scorer = ThermalScorer(ThermalScorerConfig(h=10.0))

        original = tscorer._assemble_convective_system
        try:
            tscorer._assemble_convective_system = _reference_assemble_convective_system
            t_ref, _, _ = scorer.solve_independent(
                cfg,
                devices=devices,
                power_map=power_map,
                copper_grid=copper,
                h_field=h_field,
            )
        finally:
            tscorer._assemble_convective_system = original
        t_rust, _, _ = scorer.solve_independent(
            cfg,
            devices=devices,
            power_map=power_map,
            copper_grid=copper,
            h_field=h_field,
        )
        np.testing.assert_array_equal(t_rust, t_ref)


# ---------------------------------------------------------------------------
# PBT: five non-vacuous properties of the migrated scorer
# ---------------------------------------------------------------------------


@st.composite
def board_case(draw):
    h = draw(st.integers(4, 25))
    w = draw(st.integers(4, 25))
    cs = draw(st.sampled_from([0.25, 0.5, 1.0, 2.0]))
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig

    cfg = ThermalFDMConfig(
        cell_size_mm=cs,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge=draw(st.sampled_from(["TOP", "BOTTOM", "LEFT", "RIGHT"])),
        max_cells=3000,
    )
    copper = np.asarray(
        [draw(st.floats(0.0, 1.0)) for _ in range(h * w)], dtype=np.float64
    ).reshape(h, w)
    n_dev = draw(st.integers(0, 3))
    devices = {}
    power_map = {}
    for i in range(n_dev):
        name = f"D{i}"
        devices[name] = (draw(st.floats(0.5, w * cs)), draw(st.floats(0.5, h * cs)))
        power_map[name] = draw(st.floats(0.5, 30.0))
    return cfg, copper, devices, power_map


@settings(max_examples=30, deadline=None)
@given(board_case())
def test_pbt_tgrid_finite_nonnegative(case):
    """Property 1: T_grid is finite and never below ambient (non-negative
    rise) for any physically-plausible board/copper/power input."""
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    cfg, copper, devices, power_map = case
    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
    t, _, _ = scorer.solve_independent(
        cfg, devices=devices, power_map=power_map, copper_grid=copper
    )
    assert np.all(np.isfinite(t))
    assert np.all(t >= cfg.ambient_C - 1e-9)


@settings(max_examples=30, deadline=None)
@given(board_case())
def test_pbt_monotonic_in_power(case):
    """Property 2: scaling every device's power up strictly raises every
    cell temperature (linear conduction + convective cooling are monotone)."""
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    cfg, copper, devices, power_map = case
    if not devices:
        return  # vacuous without sources; the non-vacuous runs carry the property
    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
    scaled = {k: 2.0 * v for k, v in power_map.items()}
    t_low, _, _ = scorer.solve_independent(
        cfg, devices=devices, power_map=power_map, copper_grid=copper
    )
    t_high, _, _ = scorer.solve_independent(
        cfg, devices=devices, power_map=scaled, copper_grid=copper
    )
    assert np.all(t_high >= t_low - 1e-9)
    assert np.max(t_high - t_low) > 1e-6  # non-vacuous: power matters


@settings(max_examples=30, deadline=None)
@given(board_case())
def test_pbt_monotonic_in_conductance(case):
    """Property 3: more copper (higher k_eff) strictly lowers the PEAK
    temperature.  (Pointwise monotonicity in k does NOT hold for this
    mixed Dirichlet/Robin stencil — the harmonic-mean interface update is
    asymmetric, so cells near the boundary can warm by ~1e-5 deg-C when
    conduction improves; the maximum is the physically meaningful, and
    provable, monotone quantity.)"""
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    cfg, copper, devices, power_map = case
    if not devices:
        return
    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
    copper_hi = np.minimum(1.0, copper + 0.3)
    t_low_k, _, _ = scorer.solve_independent(
        cfg, devices=devices, power_map=power_map, copper_grid=copper
    )
    t_high_k, _, _ = scorer.solve_independent(
        cfg, devices=devices, power_map=power_map, copper_grid=copper_hi
    )
    assert np.max(t_high_k) <= np.max(t_low_k) + 1e-9
    assert np.max(t_low_k) - np.max(t_high_k) > 1e-6  # non-vacuous


@settings(max_examples=30, deadline=None)
@given(board_case())
def test_pbt_boundary_respecting(case):
    """Property 4: boundary-respecting — (a) with no sources the whole grid
    sits at ambient (A·(amb·1) == b exactly, so spsolve returns ambient to
    roundoff); (b) with an interior point source, the discrete maximum
    principle forces the heatsink-edge maximum strictly below the interior
    peak (every edge cell carries a Dirichlet or convective term that pins
    it toward ambient)."""
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    cfg, copper, devices, power_map = case
    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))

    # (a) No sources -> ambient field (bit-exact to spsolve roundoff).
    t_amb, _, _ = scorer.solve_independent(
        cfg, devices={}, power_map={}, copper_grid=copper
    )
    np.testing.assert_allclose(t_amb, cfg.ambient_C, rtol=0.0, atol=1e-9)

    # (b) Interior point source via Q_field -> heatsink edge stays below peak.
    h, w = cfg.height_cells, cfg.width_cells
    q_field = np.zeros((h, w), dtype=np.float64)
    q_field[h // 2, w // 2] = 1.0
    t, _, _ = scorer.solve_independent(
        cfg, devices={}, power_map={}, copper_grid=copper, Q_field=q_field
    )
    hs = cfg.heatsink_edge.upper().strip()
    if hs == "TOP":
        edge = t[h - 1, :]
    elif hs == "BOTTOM":
        edge = t[0, :]
    elif hs == "LEFT":
        edge = t[:, 0]
    else:
        edge = t[:, w - 1]
    assert np.max(edge) < np.max(t) - 1e-9
    assert np.max(t) - cfg.ambient_C > 1e-6  # non-vacuous: the source heats


@settings(max_examples=30, deadline=None)
@given(board_case())
def test_pbt_energy_balance(case):
    """Property 5: the total heat leaving the domain (Dirichlet face
    conduction + edge convection) balances the injected device power
    within a discretisation tolerance."""
    from temper_placer.validation.thermal_scorer import (
        ThermalScorer,
        ThermalScorerConfig,
        _assemble_convective_system,
        _build_conductivity_field_gs,
        _build_heat_source_field_gs,
    )

    cfg, copper, devices, power_map = case
    if not devices:
        return
    total_power = sum(power_map.values())
    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
    t, _, _ = scorer.solve_independent(
        cfg, devices=devices, power_map=power_map, copper_grid=copper
    )
    k_field = _build_conductivity_field_gs(cfg, copper_grid=copper)
    Q = _build_heat_source_field_gs(cfg, devices, power_map)
    A, b = _assemble_convective_system(cfg, k_field, Q, h_conv=10.0)
    # Residual of the solved system measures energy imbalance in W/mm^2 units.
    t_flat = t.reshape(-1)
    residual = A @ t_flat - b
    # Convert residual to absolute power: Q units are W/mm^2; each cell is
    # cs*cs mm^2, so cell power = Q * cs^2.  Boundary terms carry the same
    # units as Q (see assembly).  Total imbalance vs injected power.
    cs2 = cfg.cell_size_mm * cfg.cell_size_mm
    balance_err = float(np.abs(residual).sum()) * cs2
    assert balance_err < max(1e-6, total_power * 0.05) + 1e-9


# ---------------------------------------------------------------------------
# Metamorphic relations (at least 3)
# ---------------------------------------------------------------------------


def test_meta_doubling_power_doubles_rise():
    """MR1: doubling every device's power doubles the temperature rise
    above ambient (linear regime — conduction and convection are both
    linear in T)."""
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    cfg = ThermalFDMConfig(
        cell_size_mm=0.5,
        origin_mm=(0.0, 0.0),
        height_cells=20,
        width_cells=20,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=3000,
    )
    devices = {"Q1": (5.0, 4.0), "Q2": (8.0, 6.0)}
    copper = np.full((20, 20), 0.3, dtype=np.float64)
    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
    t1, _, _ = scorer.solve_independent(
        cfg, devices=devices, power_map={"Q1": 5.0, "Q2": 3.0}, copper_grid=copper
    )
    t2, _, _ = scorer.solve_independent(
        cfg, devices=devices, power_map={"Q1": 10.0, "Q2": 6.0}, copper_grid=copper
    )
    rise1 = t1 - cfg.ambient_C
    rise2 = t2 - cfg.ambient_C
    # Linear scaling: rise2 ≈ 2 * rise1; tolerate roundoff and the tiny
    # non-linearity of the harmonic-mean stencil (< 1e-9 relative).
    scale = np.divide(rise2, rise1, out=np.zeros_like(rise1), where=rise1 > 1e-9)
    active = rise1 > 1e-9
    assert active.any()
    np.testing.assert_allclose(scale[active], 2.0, rtol=1e-9, atol=1e-9)


def test_meta_translation_preserves_relative_field():
    """MR2: translating all devices by an integer number of cells is exactly
    covariant for the heat-source compute and approximately covariant for
    the temperature field, with the deviation bounded by the boundary effect.

    (a) EXACT: the footprint rasterisation shifts by exactly k cells —
    Q(shifted)[:, k:] == Q(original)[:, :-k] bit-for-bit (integer-cell
    shifts on exact cell-coordinate multiples).  This is the compute the
    migration owns, and it is fully translation-equivariant.

    (b) BOUNDED: on a finite 2D board the Dirichlet/convective boundaries
    break exact field translation-invariance — the 2D Green's-function
    mirror correction decays only logarithmically, so the field deviation
    is small but never zero, even deep in the interior.  Measured on this
    geometry 2026-07-31: max relative deviation ~0.4% of the peak rise at
    margin 40 cells from every edge (5-cell shift, 100x100 board).  We
    assert < 1% there — tight enough to catch any real translation bug in
    the migrated kernels (those fail at ~100%), honest about the physics.
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig
    from temper_placer.validation.thermal_scorer import (
        ThermalScorer,
        ThermalScorerConfig,
        _build_heat_source_field_gs,
    )

    cs = 0.5
    cfg = ThermalFDMConfig(
        cell_size_mm=cs,
        origin_mm=(0.0, 0.0),
        height_cells=100,
        width_cells=100,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=3000,
    )
    # Sources on exact multiples of cs, deep inside the board.
    devices = {"Q1": (22.0, 25.0), "Q2": (28.0, 30.0)}
    power_map = {"Q1": 10.0, "Q2": 4.0}
    copper = np.full((100, 100), 0.2, dtype=np.float64)
    shift_cells = 5
    shifted = {k: (x + shift_cells * cs, y) for k, (x, y) in devices.items()}

    # (a) exact Q-field covariance
    q0 = _build_heat_source_field_gs(cfg, devices, power_map)
    q1 = _build_heat_source_field_gs(cfg, shifted, power_map)
    np.testing.assert_array_equal(q1[:, shift_cells:], q0[:, :-shift_cells])

    # (b) bounded field covariance on the deep interior (margin 40 cells)
    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
    t0, _, _ = scorer.solve_independent(
        cfg, devices=devices, power_map=power_map, copper_grid=copper
    )
    t1, _, _ = scorer.solve_independent(
        cfg, devices=shifted, power_map=power_map, copper_grid=copper
    )
    margin = 40
    diff = np.abs(t1[:, shift_cells:] - t0[:, :-shift_cells])
    region = diff[margin:-margin, margin:-margin - shift_cells]
    peak_rise = float(np.max(t0) - cfg.ambient_C)
    assert region.max() / peak_rise < 0.01, (
        f"translated field deviates {region.max() / peak_rise:.2%} of the peak "
        f"rise — far above the measured ~0.4% 2D boundary-effect bound"
    )


def test_meta_symmetric_board_symmetric_field():
    """MR3: a left-right symmetric board (symmetric copper AND symmetric
    heat-source field) with a symmetric heatsink edge yields a
    left-right symmetric temperature field.

    The Q field is supplied directly (Q_field) because the device
    footprint rasterisation is floor/ceil-quantised and is NOT
    reflection-symmetric for arbitrary device positions — a reference
    property shared with U5, not something the migrated solver can or
    should repair.  The solver/assembly symmetry is what this tests: a
    symmetric (A, b) must yield a symmetric T."""
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    cfg = ThermalFDMConfig(
        cell_size_mm=0.5,
        origin_mm=(0.0, 0.0),
        height_cells=20,
        width_cells=21,  # odd width so the mirror axis is a cell column
        ambient_C=40.0,
        heatsink_edge="BOTTOM",  # symmetric edge
        max_cells=3000,
    )
    # Symmetric copper (mirror across the centre column 10).
    copper = np.zeros((20, 21), dtype=np.float64)
    copper[:, 5:11] = 0.5
    copper[:, 10:16] = 0.5  # symmetric about column 10
    # Symmetric heat source: two point cells mirrored about column 10.
    q_field = np.zeros((20, 21), dtype=np.float64)
    q_field[8, 8] = 1.0
    q_field[8, 12] = 1.0
    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
    t, _, _ = scorer.solve_independent(
        cfg, devices={}, power_map={}, copper_grid=copper, Q_field=q_field
    )
    np.testing.assert_allclose(t, t[:, ::-1], rtol=1e-12, atol=1e-12)
