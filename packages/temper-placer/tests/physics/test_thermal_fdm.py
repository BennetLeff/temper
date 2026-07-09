"""
Tests for thermal FDM field solver (U5).

Covers:
- K1: Solver matches closed-form analytic 1D bar with uniform heating
- K2: Hot component near offset pads shifts field where copper actually is
- K4: Determinism — two runs on identical inputs produce bit-stable fields
- Edge: Adjacent switches superimpose hot spots
- Integration: Wider routed trace lowers I²R heat vs thin trace
- Edge: Non-convergence returns UNMEASURED
"""

from __future__ import annotations

import numpy as np
import pytest

from temper_placer.fields.field import CostField
from temper_placer.fields.result import FieldResult
from temper_placer.placer.cp_sat.gates import GateResult, GateStatus

# ---------------------------------------------------------------------------
# K1: Closed-form analytic 1D bar with uniform heating
# ---------------------------------------------------------------------------


@pytest.mark.k1
def test_thermal_fdm_uniform_bar_analytic():
    """K1: Uniformly heated bar (Dirichlet top, adiabatic bottom/left/right).

    Analytic solution: T(y) = T_top + Q/(2k) * (H² - y²).

    The solver must match the parabolic profile within 2% relative error
    at the peak temperature (bottom edge, y=0).
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm

    cell_size = 0.5  # mm — fine grid for accuracy
    height_cells = 40
    width_cells = 5  # narrow so it's effectively 1D
    H = height_cells * cell_size  # 20 mm
    T_top = 40.0  # °C

    # Target k_eff = 1.0 W/K (in-plane conductance).
    # k_eff = k_fr4 * board_thickness_mm * 1e-3  =>  k_fr4 = k_eff / (thickness * 1e-3)
    k_eff_target = 1.0  # W/K
    board_thickness = 1.6  # mm
    k_fr4_val = k_eff_target / (board_thickness * 1e-3)  # = 625 W/(m·K)
    Q_uniform = 0.1  # W/mm² (areal power density)
    # Analytic: T(y) = T_top + Q/(2 k_eff) * (H² - y²)
    # At y=0: T(0) = 40 + 0.1/(2*1.0) * 400 = 40 + 20 = 60°C

    config = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=T_top,
        heatsink_edge="TOP",
        k_fr4=k_fr4_val,
        k_copper=k_fr4_val,  # uniform material for test
        board_thickness_mm=board_thickness,
    )

    devices: dict[str, tuple[float, float]] = {}
    power_map: dict[str, float] = {}

    # Uniform copper coverage = 0.0 everywhere (pure FR4-like)
    copper_grid = np.zeros((height_cells, width_cells), dtype=np.float64)

    # Inject uniform heat: Q in W/mm² per cell
    Q_field = np.full((height_cells, width_cells), Q_uniform, dtype=np.float64)

    result = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )

    assert result.is_usable, f"Expected usable field, got status={result.status}"
    assert result.field is not None
    field_grid = np.asarray(result.field.grid, dtype=np.float64)

    # Check grid shape
    assert field_grid.shape == (height_cells, width_cells)

    # Extract the center column to avoid boundary effects from left/right Neumann
    col = width_cells // 2
    T_numeric = field_grid[:, col]

    # Analytic profile: T(y) = T_top + Q/(2*k_eff) * (H² - y²)
    y_cells = np.arange(height_cells)
    y_world = y_cells * cell_size + cell_size / 2  # cell centers
    T_analytic = T_top + Q_uniform / (2 * k_eff_target) * (H**2 - y_world**2)

    # Relative error at each point; assert max < 2%
    rel_error = np.abs(T_numeric - T_analytic) / np.maximum(np.abs(T_analytic), 1e-6)
    max_rel_error = float(np.max(rel_error))

    assert max_rel_error < 0.02, (
        f"Max relative error {max_rel_error:.4f} exceeds 2% threshold\n"
        f"T_numeric: {T_numeric}\nT_analytic: {T_analytic}"
    )


# ---------------------------------------------------------------------------
# K2: Hot component near offset pads shifts field where copper actually is
# ---------------------------------------------------------------------------


@pytest.mark.k2
def test_thermal_fdm_copper_offset():
    """K2: A hot component near offset pads creates a hot spot shifted
    towards where the copper actually is, not centered on a naive box.

    We set up a grid with a copper strip offset to the right of a heat
    source.  The temperature peak should be shifted toward the copper
    (higher conductivity = better heat spreading = lower temperature on
    the copper side, but the gradient should be asymmetric).

    Actually: copper lowers resistance to heat spreading, so the
    temperature _drops_ faster on the copper side.  The peak remains at
    the source, but the field is asymmetric: steeper gradient on the
    non-copper side (more temperature drop per mm) and shallower on the
    copper side.
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm

    cell_size = 1.0
    height_cells = 20
    width_cells = 30
    T_ambient = 40.0

    config = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=T_ambient,
        heatsink_edge="TOP",
    )

    devices = {"hot": (width_cells / 2 * cell_size, 2.5)}
    power_map = {"hot": 5.0}

    # Offset copper strip: right half of the board has copper, left half is bare
    copper_grid = np.zeros((height_cells, width_cells), dtype=np.float64)
    mid_col = width_cells // 2
    copper_grid[:, mid_col:] = 1.0  # full copper on right half

    result = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
    )

    assert result.is_usable, f"Expected usable field, status={result.status}"
    field = result.field

    # Sample temperatures left and right of the source at the same y
    source_row = 2  # closest row to source
    left_col = mid_col - 3
    right_col = mid_col + 3

    fgrid = np.asarray(result.field.grid, dtype=np.float64)
    T_left = fgrid[source_row, left_col]
    T_right = fgrid[source_row, right_col]

    # Copper side (right) should be COOLER (better heat spreading away from source)
    assert T_right < T_left, (
        f"Expected copper side (right, T={T_right:.2f}) to be cooler "
        f"than bare side (left, T={T_left:.2f}) — copper should spread heat better"
    )


# ---------------------------------------------------------------------------
# K4: Determinism — bit-stable fields on two identical runs
# ---------------------------------------------------------------------------


@pytest.mark.k4
def test_thermal_fdm_determinism():
    """K4: Two runs with identical inputs produce bit-identical fields.

    Uses scipy.sparse.linalg.spsolve (direct solver / SuperLU) for
    bit-exact reproducibility.
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm

    cell_size = 1.0
    height_cells = 15
    width_cells = 15
    config = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )

    devices = {"d1": (5.0, 2.0), "d2": (10.0, 2.0)}
    power_map = {"d1": 3.0, "d2": 5.0}
    copper_grid = np.full((height_cells, width_cells), 0.5, dtype=np.float64)

    result1 = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
    )
    result2 = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
    )

    assert result1.is_usable
    assert result2.is_usable
    assert result1.field is not None
    assert result2.field is not None

    field1 = np.asarray(result1.field.grid, dtype=np.float64)
    field2 = np.asarray(result2.field.grid, dtype=np.float64)

    assert np.array_equal(field1, field2), (
        "K4 FAILED: two runs on identical inputs produced different fields\n"
        f"Max diff: {np.max(np.abs(field1 - field2))}"
    )


# ---------------------------------------------------------------------------
# Edge: Adjacent switches superimpose hot spots
# ---------------------------------------------------------------------------


def test_thermal_fdm_adjacent_superposition():
    """Two adjacent heat sources produce a field with overlapping hot spots.

    The temperature between two sources should be higher than the
    temperature at the same distance from a single source (superposition
    of heat contributions).
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm

    cell_size = 1.0
    height_cells = 20
    width_cells = 20
    config = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )

    copper_grid = np.zeros((height_cells, width_cells), dtype=np.float64)

    # Single source
    result1 = solve_thermal_fdm(
        config=config,
        devices={"d1": (10.0, 2.0)},
        power_map={"d1": 5.0},
        copper_grid=copper_grid,
    )

    # Two sources 6 mm apart
    result2 = solve_thermal_fdm(
        config=config,
        devices={"d1": (7.0, 2.0), "d2": (13.0, 2.0)},
        power_map={"d1": 5.0, "d2": 5.0},
        copper_grid=copper_grid,
    )

    assert result1.is_usable
    assert result2.is_usable
    f1 = np.asarray(result1.field.grid, dtype=np.float64)
    f2 = np.asarray(result2.field.grid, dtype=np.float64)

    # Temperature at midpoint between sources (10, y=2)
    mid_col = int(10.0 / cell_size)
    mid_row = 2
    T_mid_two = f2[mid_row, mid_col]

    # Temperature at same offset (3mm) from single source
    offset_col = int(3.0 / cell_size)
    T_offset_one = f1[mid_row, 10 + offset_col]

    # The midpoint between two equal sources should be hotter than a point
    # the same distance from a single source
    assert T_mid_two > T_offset_one, (
        f"Expected superposition: T_between_two ({T_mid_two:.2f}) > "
        f"T_offset_one ({T_offset_one:.2f})"
    )


# ---------------------------------------------------------------------------
# Integration: Wider trace lowers I²R heat vs thin trace
# ---------------------------------------------------------------------------


def test_thermal_fdm_wider_trace_cooler():
    """A wider trace has lower I²R heat density and spreads heat better.

    We simulate the same current through two trace widths:
    - Thin trace: high current density → high I²R per cell
    - Wide trace: low current density → low I²R per cell
    The wide trace should result in lower peak temperature.
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm

    cell_size = 1.0
    height_cells = 20
    width_cells = 15
    T_ambient = 40.0

    config = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=T_ambient,
        heatsink_edge="TOP",
    )

    copper_thin = np.zeros((height_cells, width_cells), dtype=np.float64)
    copper_thin[10, :] = 1.0  # 1-cell wide trace

    copper_wide = np.zeros((height_cells, width_cells), dtype=np.float64)
    copper_wide[9:12, :] = 1.0  # 3-cell wide trace

    # Same total current through both traces
    # Thin trace: Q per cell = P / (1 cell * cell_area)
    # Wide trace: Q per cell = P / (3 cells * cell_area)
    total_power = 3.0  # W
    cell_area = cell_size**2

    Q_thin = np.zeros((height_cells, width_cells), dtype=np.float64)
    Q_thin[10, :] = total_power / (width_cells * cell_area)

    Q_wide = np.zeros((height_cells, width_cells), dtype=np.float64)
    Q_wide[9:12, :] = total_power / (3 * width_cells * cell_area)

    result_thin = solve_thermal_fdm(
        config=config,
        devices={},
        power_map={},
        copper_grid=copper_thin,
        Q_field=Q_thin,
    )
    result_wide = solve_thermal_fdm(
        config=config,
        devices={},
        power_map={},
        copper_grid=copper_wide,
        Q_field=Q_wide,
    )

    assert result_thin.is_usable
    assert result_wide.is_usable
    T_peak_thin = float(np.max(result_thin.field.grid))
    T_peak_wide = float(np.max(result_wide.field.grid))

    assert T_peak_wide < T_peak_thin, (
        f"Expected wider trace to be cooler: "
        f"T_peak_thin={T_peak_thin:.2f}, T_peak_wide={T_peak_wide:.2f}"
    )


# ---------------------------------------------------------------------------
# Edge: Non-convergence returns UNMEASURED (never a silent flat/zero field)
# ---------------------------------------------------------------------------


def test_thermal_fdm_budget_exceeded_returns_unmeasured():
    """When max_cells is exceeded, return UNMEASURED, never a partial field."""
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm

    config = ThermalFDMConfig(
        cell_size_mm=0.1,
        origin_mm=(0.0, 0.0),
        height_cells=200,
        width_cells=200,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=100,  # much smaller than 200*200 = 40000
    )

    devices: dict[str, tuple[float, float]] = {}
    power_map: dict[str, float] = {}

    result = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
    )

    assert not result.is_usable, "Expected UNMEASURED when budget exceeded"
    assert result.status is GateStatus.UNMEASURED
    assert result.field is None, "UNMEASURED must have field=None (fail-closed)"


# ---------------------------------------------------------------------------
# Edge: Empty devices with no Q_field returns a flat ambient field
# ---------------------------------------------------------------------------


def test_thermal_fdm_no_sources_uniform():
    """No heat sources → uniform ambient temperature throughout."""
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm

    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=10,
        width_cells=10,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )

    result = solve_thermal_fdm(
        config=config,
        devices={},
        power_map={},
        copper_grid=np.zeros((10, 10), dtype=np.float64),
    )

    assert result.is_usable
    T_field = np.asarray(result.field.grid, dtype=np.float64)
    assert np.allclose(T_field, 40.0, atol=1e-6), (
        f"No sources should give uniform T_ambient, got range "
        f"[{T_field.min():.4f}, {T_field.max():.4f}]"
    )
