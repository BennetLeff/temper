"""
Tests for per-cell vertical sink field builder and FDM with sink (issue #141).

Covers:
- Limit test: single device with sink, negligible in-plane → T_case ≈ T_amb + P·R_vert
- Closed-form: uniform h and uniform Q → T ≈ T_amb + Q/h
- Matrix class: with nonzero h_field, matrix is still SPD/M-matrix
- No-regression: h_field=None produces identical output to today
- h_field builder: footprint coverage, background convection, R_vert=0 skip
"""

from __future__ import annotations

import numpy as np
import pytest

from temper_placer.physics.heat_removal import (
    H_CONV_BACKGROUND,
    build_h_field,
)
from temper_placer.physics.thermal_fdm import (
    ThermalFDMConfig,
    get_system_matrix,
    solve_thermal_fdm,
)
from temper_placer.physics.tj_cross_check import DeviceThermalConfig


# ---------------------------------------------------------------------------
# Matrix property check helpers (mirror test_thermal_fdm_matrix_class.py)
# ---------------------------------------------------------------------------


def _check_symmetry(A: "scipy.sparse.csr_matrix", atol: float = 1e-12) -> bool:
    A_dense = A.toarray()
    return bool(np.allclose(A_dense, A_dense.T, atol=atol))


def _check_positive_definite(A: "scipy.sparse.csr_matrix") -> bool:
    A_dense = A.toarray()
    eigvals = np.linalg.eigvalsh(A_dense)
    return bool(np.all(eigvals > 1e-10))


def _check_m_matrix(A: "scipy.sparse.csr_matrix", atol: float = 1e-12) -> bool:
    A_dense = A.toarray()
    n = A_dense.shape[0]
    diag = np.diag(A_dense)
    if not np.all(diag > 0):
        return False
    for i in range(n):
        for j in range(n):
            if i != j and A_dense[i, j] > atol:
                return False
    off_diag_sum = np.sum(np.abs(A_dense), axis=1) - np.abs(diag)
    if not np.all(diag >= off_diag_sum - atol):
        return False
    if not np.any(diag > off_diag_sum + atol):
        return False
    return True


# ---------------------------------------------------------------------------
# Limit test: single device with sink, negligible in-plane conduction
# → T_case ≈ T_amb + P·R_vert
# ---------------------------------------------------------------------------


def test_sink_limit_single_device_lumped_agreement():
    """A single device with a strong through-plane sink and negligible
    in-plane conduction (very low k_fr4) produces T_case very close to
    the lumped estimate T_amb + P·R_vert.

    This validates the sink term's units, sign, and magnitude.
    """
    cell_size = 0.5  # mm
    height_cells = 20
    width_cells = 20
    T_amb = 40.0
    P = 5.0  # W
    R_vert = 2.25  # K/W  (R_θCS + R_θSA for a typical device)

    # Expected lumped T_case = T_amb + P * R_vert
    T_case_lumped = T_amb + P * R_vert  # 40 + 5*2.25 = 51.25°C

    config = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=T_amb,
        heatsink_edge="BOTTOM",
        # Make in-plane conduction negligible: very low k_fr4
        k_fr4=1e-6,
        k_copper=1e-6,
        board_thickness_mm=1.6,
    )

    devices = {"Q1": (5.0, 5.0)}
    power_map = {"Q1": P}

    device_thermal = {
        "Q1": DeviceThermalConfig(
            name="Q1",
            R_theta_jc=0.0,
            R_theta_cs=0.25,
            R_theta_sa=2.0,
            T_j_max=150.0,
            R_jc_because="test",
            R_cs_because="test: R_θCS = 0.25 K/W",
            R_sa_because="test: R_θSA = 2.0 K/W",
        ),
    }

    h_field = build_h_field(config, devices, device_thermal)

    result = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        h_field=h_field,
    )

    assert result.is_usable, f"FDM solve failed: {result.error_message}"

    T_grid = np.asarray(result.field.grid, dtype=np.float64)

    # Area-average T_case over the device footprint (5x5 mm)
    cs = cell_size
    ox, oy = 0.0, 0.0
    fp_mm = 5.0
    half = fp_mm / 2.0
    dx, dy = 5.0, 5.0

    col_min = max(0, int(np.floor((dx - half - ox) / cs)))
    col_max = min(width_cells, int(np.ceil((dx + half - ox) / cs)))
    row_min = max(0, int(np.floor((dy - half - oy) / cs)))
    row_max = min(height_cells, int(np.ceil((dy + half - oy) / cs)))

    T_case_fdm = float(np.mean(T_grid[row_min:row_max, col_min:col_max]))

    # With negligible in-plane, the sink dominates; T_case should be within
    # 10% of the lumped estimate
    rel_error = abs(T_case_fdm - T_case_lumped) / max(abs(T_case_lumped), 1.0)
    assert rel_error < 0.10, (
        f"Limit test: T_case_fdm={T_case_fdm:.2f}°C vs "
        f"T_case_lumped={T_case_lumped:.2f}°C, "
        f"rel_error={rel_error:.4f} > 10%"
    )


# ---------------------------------------------------------------------------
# Closed-form: uniform Q and uniform h → T ≈ T_amb + Q/h
# ---------------------------------------------------------------------------


def test_sink_closed_form_uniform_q_uniform_h():
    """Uniform areal heating Q with uniform per-area sink coefficient h
    and negligible in-plane conduction → all cells should be near
    T ≈ T_amb + Q/h.

    This is the screened-Poisson / fin solution: when in-plane gradients
    are negated by vanishing k, the PDE reduces to -h(T - T_amb) = -Q
    → T = T_amb + Q/h.
    """
    cell_size = 1.0  # mm
    height_cells = 10
    width_cells = 10
    T_amb = 40.0

    Q_val = 0.01  # W/mm² (uniform)
    h_val = 0.001  # W/(K·mm²) (uniform sink)

    T_expected = T_amb + Q_val / h_val  # 40 + 0.01/0.001 = 50°C

    config = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=T_amb,
        heatsink_edge="BOTTOM",
        # Negligible in-plane: very low k
        k_fr4=1e-6,
        k_copper=1e-6,
        board_thickness_mm=1.6,
    )

    # Uniform Q field and h field
    Q_field = np.full((height_cells, width_cells), Q_val, dtype=np.float64)
    h_field = np.full((height_cells, width_cells), h_val, dtype=np.float64)

    result = solve_thermal_fdm(
        config=config,
        devices={},
        power_map={},
        Q_field=Q_field,
        h_field=h_field,
    )

    assert result.is_usable
    T_grid = np.asarray(result.field.grid, dtype=np.float64)

    # All cells should be within 5% of the closed-form solution
    rel_error = np.max(np.abs(T_grid - T_expected)) / max(abs(T_expected), 1.0)
    assert rel_error < 0.05, (
        f"Closed-form test: max T={np.max(T_grid):.3f}°C, "
        f"expected {T_expected:.3f}°C, "
        f"max rel error={rel_error:.4f} > 5%"
    )


# ---------------------------------------------------------------------------
# Matrix class preserved: with nonzero h_field, matrix is still SPD/M-matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("h,w", [(5, 5), (8, 8), (6, 10)])
@pytest.mark.parametrize("heatsink_edge", ["TOP", "BOTTOM", "LEFT", "RIGHT"])
def test_sink_matrix_spd_m_matrix(h, w, heatsink_edge):
    """With a nonzero h_field, the system matrix remains symmetric,
    positive-definite, and an M-matrix (diagonal dominance improved).
    """
    rng = np.random.default_rng(42)
    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge=heatsink_edge,
    )
    copper = np.full((h, w), 0.5, dtype=np.float64)
    h_field = rng.uniform(0.0, 0.01, (h, w)).astype(np.float64)

    A = get_system_matrix(config, copper_grid=copper, h_field=h_field)

    assert _check_symmetry(A), f"Symmetry failed with h_field: {h}x{w} edge={heatsink_edge}"
    assert _check_positive_definite(A), (
        f"PD failed with h_field: {h}x{w} edge={heatsink_edge}"
    )
    assert _check_m_matrix(A), (
        f"M-matrix failed with h_field: {h}x{w} edge={heatsink_edge}"
    )


def test_sink_matrix_diagonal_dominance_improved():
    """The h_field sink adds positive values to the diagonal, improving
    diagonal dominance.  The row with the largest h should have the
    strictest diagonal dominance.
    """
    h, w = 6, 6
    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )

    # No sink
    A_no = get_system_matrix(config, copper_grid=np.full((h, w), 0.5, dtype=np.float64))

    # Strong sink in one corner
    h_field = np.zeros((h, w), dtype=np.float64)
    h_field[0, 0] = 100.0  # huge sink on one cell
    A_with = get_system_matrix(config, copper_grid=np.full((h, w), 0.5, dtype=np.float64), h_field=h_field)

    A_no_dense = A_no.toarray()
    A_with_dense = A_with.toarray()

    # The cell at (0,0) should have significantly larger diagonal
    idx = 0  # row=0, col=0
    diag_no = A_no_dense[idx, idx]
    diag_with = A_with_dense[idx, idx]
    assert diag_with > diag_no + 50.0, (
        f"Expected diagonal with sink much larger: "
        f"diag_no={diag_no:.3f}, diag_with={diag_with:.3f}"
    )


# ---------------------------------------------------------------------------
# No-regression: h_field=None produces byte-identical output to today
# ---------------------------------------------------------------------------


def test_no_regression_hfield_none():
    """h_field=None produces identical results to the solver without sink.
    """
    h, w = 10, 15
    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )

    devices = {"d1": (5.0, 3.0), "d2": (10.0, 8.0)}
    power_map = {"d1": 3.0, "d2": 5.0}
    copper_grid = np.full((h, w), 0.5, dtype=np.float64)

    result_no_sink = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
    )
    result_with_none = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        h_field=None,
    )

    assert result_no_sink.is_usable
    assert result_with_none.is_usable

    T_no = np.asarray(result_no_sink.field.grid, dtype=np.float64)
    T_none = np.asarray(result_with_none.field.grid, dtype=np.float64)

    assert np.allclose(T_no, T_none, atol=1e-14), (
        f"No-regression FAILED: h_field=None produced different result\n"
        f"Max diff: {np.max(np.abs(T_no - T_none))}"
    )


def test_no_regression_hfield_all_zero():
    """h_field=all-zero produces identical results to h_field=None.
    """
    h, w = 10, 15
    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )

    devices = {"d1": (5.0, 3.0), "d2": (10.0, 8.0)}
    power_map = {"d1": 3.0, "d2": 5.0}
    copper_grid = np.full((h, w), 0.5, dtype=np.float64)

    result_none = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        h_field=None,
    )
    result_zero = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        h_field=np.zeros((h, w), dtype=np.float64),
    )

    assert result_none.is_usable
    assert result_zero.is_usable

    T_none = np.asarray(result_none.field.grid, dtype=np.float64)
    T_zero = np.asarray(result_zero.field.grid, dtype=np.float64)

    assert np.allclose(T_none, T_zero, atol=1e-14), (
        f"No-regression FAILED: h_field=zeros produced different result\n"
        f"Max diff: {np.max(np.abs(T_none - T_zero))}"
    )


# ---------------------------------------------------------------------------
# h_field builder: footprint coverage, background, R_vert=0 skip
# ---------------------------------------------------------------------------


def test_build_h_field_footprint_coverage():
    """h_field has elevated values over device footprints and weak background
    elsewhere.  R_vert=0 devices are skipped."""
    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=30,
        width_cells=30,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )

    devices = {
        "Q1": (5.0, 5.0),    # board-heatsinked (R_vert=0)
        "Q2": (20.0, 5.0),   # full sink (R_vert > 0)
    }

    device_thermal = {
        "Q1": DeviceThermalConfig(
            name="Q1", R_theta_jc=0.6, R_theta_cs=0.0, R_theta_sa=0.0,
            T_j_max=150.0,
            R_jc_because="test",
            R_cs_because="test: board-heatsinked, R_vert=0",
            R_sa_because="test: board-heatsinked, R_vert=0",
        ),
        "Q2": DeviceThermalConfig(
            name="Q2", R_theta_jc=0.6, R_theta_cs=0.25, R_theta_sa=2.0,
            T_j_max=150.0,
            R_jc_because="test",
            R_cs_because="test: R_θCS = 0.25 K/W",
            R_sa_because="test: R_θSA = 2.0 K/W",
        ),
    }

    h_field = build_h_field(config, devices, device_thermal)

    assert h_field.shape == (30, 30)

    # Q1 footprint (board-heatsinked, R_vert=0): should match background
    bg = H_CONV_BACKGROUND * (1e-3) ** 2  # W/(m²·K) * m² / mm² = W/(K·mm²)
    cs = config.cell_size_mm
    cell_area_m2 = (cs * 1e-3) ** 2
    h_bg = H_CONV_BACKGROUND * cell_area_m2 / (cs * cs)
    # Check that Q1's footprint cells have only background h
    q1_cells = h_field[3:8, 3:8]  # rough footprint
    assert np.allclose(q1_cells, h_bg, atol=1e-16), (
        f"Q1 (R_vert=0) should have no elevated sink: "
        f"got max={np.max(q1_cells):.6e}, background={h_bg:.6e}"
    )

    # Q2 footprint: should be elevated above background
    q2_cells = h_field[3:8, 18:23]  # rough footprint
    assert np.max(q2_cells) > h_bg * 1.5, (
        f"Q2 (R_vert=2.25) should have elevated sink: "
        f"max={np.max(q2_cells):.6e}, background={h_bg:.6e}"
    )


def test_build_h_field_background_only():
    """When no devices are provided, h_field is uniform background."""
    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=10,
        width_cells=10,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )

    h_field = build_h_field(config, {}, {})

    assert h_field.shape == (10, 10)
    cs = config.cell_size_mm
    cell_area_m2 = (cs * 1e-3) ** 2
    h_bg = H_CONV_BACKGROUND * cell_area_m2 / (cs * cs)
    assert np.allclose(h_field, h_bg, atol=1e-16), (
        f"Background-only h_field should be uniform: "
        f"min={np.min(h_field):.6e}, max={np.max(h_field):.6e}, "
        f"expected={h_bg:.6e}"
    )


def test_build_h_field_missing_config_raises():
    """Device without DeviceThermalConfig raises ValueError."""
    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=10,
        width_cells=10,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )

    devices = {"Q1": (5.0, 5.0)}
    device_thermal: dict[str, DeviceThermalConfig] = {}

    with pytest.raises(ValueError, match="DeviceThermalConfig"):
        build_h_field(config, devices, device_thermal)


# ---------------------------------------------------------------------------
# Units check: background h_bg is physically reasonable
# ---------------------------------------------------------------------------


def test_h_bg_units_physical():
    """Background convection h_bg is numerically small but physically
    defensible: ~1e-5 W/(K·mm²) for 10 W/(m²·K) on 1 mm² cells.
    """
    cs = 1.0  # mm
    cell_area_m2 = (cs * 1e-3) ** 2  # 1e-6 m²
    h_bg = H_CONV_BACKGROUND * cell_area_m2 / (cs * cs)  # W/(mm²·K)

    # 10 W/(m²·K) * 1e-6 m² / 1 mm² = 1e-5 W/(K·mm²)
    expected = 1e-5
    assert abs(h_bg - expected) < 1e-16, (
        f"h_bg={h_bg:.6e}, expected {expected:.6e}"
    )

    # Compare with typical FR4 diagonal coefficient
    # k_eff = 0.3 W/(m·K) * 1.6e-3 m = 4.8e-4 W/K
    # diag ≈ 4 * k_eff / cs² = 4 * 4.8e-4 / 1.0 = 1.92e-3 W/(K·mm²)
    # h_bg is ~200x smaller → background convection is negligible
    # compared to in-plane conduction, as expected physically.
    assert h_bg < 1e-3, (
        f"Background convection ({h_bg:.6e}) should be much smaller "
        f"than typical in-plane conduction (~2e-3)"
    )
