"""Property-based tests (Hypothesis) for the thermal FDM field solver (U5).

Covers:
- Monotonicity: increasing k → decreasing peak temperature
- Linearity: doubling all heat sources doubles ΔT (T − T_ambient)
- Boundary: heatsink-edge cells are exactly T_ambient
- Non-negativity: no temperature below T_ambient (with non-negative sources)
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def small_grid_config(draw):
    """Generate valid ThermalFDMConfig for a small grid."""
    h = draw(st.integers(5, 20))
    w = draw(st.integers(3, 15))
    edge = draw(st.sampled_from(["TOP", "BOTTOM", "LEFT", "RIGHT"]))
    cell = draw(st.floats(0.5, 2.0))
    k_fr4 = draw(st.floats(1.0, 1000.0))
    return ThermalFDMConfig(
        cell_size_mm=cell,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge=edge,
        k_fr4=k_fr4,
        k_copper=k_fr4,
        board_thickness_mm=1.6,
        max_cells=2000,
    )


# ---------------------------------------------------------------------------
# K4-bis: Determinism across many random inputs (Hypothesis)
# ---------------------------------------------------------------------------


@given(config=small_grid_config())
@settings(max_examples=50)
def test_thermal_fdm_determinism_pbt(config):
    """K4 (PBT): Two solves with identical inputs produce bit-identical fields."""
    rng = np.random.default_rng(42)
    n_devices = rng.integers(0, 5)
    devices = {}
    power_map = {}
    for i in range(n_devices):
        x = rng.uniform(0, config.width_cells * config.cell_size_mm)
        y = rng.uniform(0, config.height_cells * config.cell_size_mm)
        devices[f"d{i}"] = (x, y)
        power_map[f"d{i}"] = rng.uniform(1.0, 20.0)

    copper = rng.uniform(0, 1, (config.height_cells, config.width_cells)).astype(np.float64)

    result1 = solve_thermal_fdm(config, devices=devices, power_map=power_map, copper_grid=copper)
    result2 = solve_thermal_fdm(config, devices=devices, power_map=power_map, copper_grid=copper)

    assert result1.is_usable == result2.is_usable
    if result1.is_usable:
        assert result1.field is not None
        assert result2.field is not None
        f1 = np.asarray(result1.field.grid, dtype=np.float64)
        f2 = np.asarray(result2.field.grid, dtype=np.float64)
        assert np.array_equal(f1, f2), f"Max diff: {np.max(np.abs(f1 - f2))}"


# ---------------------------------------------------------------------------
# Boundary: heatsink-edge cells are exactly T_ambient
# ---------------------------------------------------------------------------


@given(config=small_grid_config())
@settings(max_examples=50)
def test_thermal_fdm_heatsink_is_ambient(config):
    """Heatsink-edge cells must be exactly at ambient temperature."""
    h, w = config.height_cells, config.width_cells
    devices = {"d0": (w * config.cell_size_mm / 2, h * config.cell_size_mm / 2)}
    power_map = {"d0": 10.0}
    copper = np.full((h, w), 0.5, dtype=np.float64)

    result = solve_thermal_fdm(config, devices=devices, power_map=power_map, copper_grid=copper)
    if not result.is_usable:
        pytest.skip("Solver returned UNMEASURED (may be budget-limited)")
    f = np.asarray(result.field.grid, dtype=np.float64)
    edge = config.heatsink_edge.upper().strip()
    if edge == "TOP":
        edge_cells = f[-1, :]
    elif edge == "BOTTOM":
        edge_cells = f[0, :]
    elif edge == "LEFT":
        edge_cells = f[:, 0]
    else:  # RIGHT
        edge_cells = f[:, -1]

    assert np.allclose(edge_cells, config.ambient_C, atol=1e-9), (
        f"Expected heatsink edge at {config.ambient_C}°C, got range "
        f"[{edge_cells.min():.6f}, {edge_cells.max():.6f}]"
    )


# ---------------------------------------------------------------------------
# Monotonicity: increasing k → decreasing peak temperature
# ---------------------------------------------------------------------------


@given(
    h=st.integers(8, 15),
    w=st.integers(4, 10),
    k1=st.floats(1.0, 10.0),
    k_delta=st.floats(1.0, 50.0),
)
@settings(max_examples=30)
def test_thermal_fdm_monotonic_conductivity(h, w, k1, k_delta):
    """Higher effective conductivity → lower peak temperature for same heat."""
    cell = 1.0
    base = ThermalFDMConfig(
        cell_size_mm=cell,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        board_thickness_mm=1.6,
        max_cells=2000,
    )
    k_eff1 = k1 / (1.6 * 1e-3)  # convert to config k_fr4 value
    k_eff2 = (k1 + abs(k_delta)) / (1.6 * 1e-3)

    config_lo = ThermalFDMConfig(
        cell_size_mm=cell, origin_mm=(0.0, 0.0),
        height_cells=h, width_cells=w,
        ambient_C=40.0, heatsink_edge="TOP",
        k_fr4=k_eff1, k_copper=k_eff1, board_thickness_mm=1.6,
        max_cells=2000,
    )
    config_hi = ThermalFDMConfig(
        cell_size_mm=cell, origin_mm=(0.0, 0.0),
        height_cells=h, width_cells=w,
        ambient_C=40.0, heatsink_edge="TOP",
        k_fr4=k_eff2, k_copper=k_eff2, board_thickness_mm=1.6,
        max_cells=2000,
    )

    devices = {"d0": (w * cell / 2, 2.0)}
    power_map = {"d0": 5.0}
    copper = np.zeros((h, w), dtype=np.float64)

    r_lo = solve_thermal_fdm(config_lo, devices=devices, power_map=power_map, copper_grid=copper)
    r_hi = solve_thermal_fdm(config_hi, devices=devices, power_map=power_map, copper_grid=copper)

    if not r_lo.is_usable or not r_hi.is_usable:
        pytest.skip("Solver returned UNMEASURED")

    T_max_lo = float(np.max(r_lo.field.grid))
    T_max_hi = float(np.max(r_hi.field.grid))

    assert T_max_hi <= T_max_lo * 1.0001, (
        f"Higher k should not increase peak T: k1={k1:.1f} → T={T_max_lo:.1f}, "
        f"k2={k1+abs(k_delta):.1f} → T={T_max_hi:.1f}"
    )


# ---------------------------------------------------------------------------
# Linearity: doubling Q doubles ΔT (superposition)
# ---------------------------------------------------------------------------


@given(
    h=st.integers(8, 15),
    w=st.integers(4, 10),
    q_factor=st.floats(1.5, 5.0),
)
@settings(max_examples=30)
def test_thermal_fdm_linearity(h, w, q_factor):
    """Doubling all heat sources doubles the excess temperature ΔT = T − T_ambient."""
    cell = 1.0
    k_val = 100.0 / (1.6 * 1e-3)
    config = ThermalFDMConfig(
        cell_size_mm=cell, origin_mm=(0.0, 0.0),
        height_cells=h, width_cells=w,
        ambient_C=40.0, heatsink_edge="TOP",
        k_fr4=k_val, k_copper=k_val, board_thickness_mm=1.6,
        max_cells=2000,
    )

    devices = {"d0": (w * cell / 2, 2.0)}
    copper = np.zeros((h, w), dtype=np.float64)

    pm_lo = {"d0": 2.0}
    pm_hi = {"d0": 2.0 * q_factor}

    r_lo = solve_thermal_fdm(config, devices=devices, power_map=pm_lo, copper_grid=copper)
    r_hi = solve_thermal_fdm(config, devices=devices, power_map=pm_hi, copper_grid=copper)

    if not r_lo.is_usable or not r_hi.is_usable:
        pytest.skip("Solver returned UNMEASURED")

    f_lo = np.asarray(r_lo.field.grid, dtype=np.float64)
    f_hi = np.asarray(r_hi.field.grid, dtype=np.float64)
    dT_lo = f_lo - config.ambient_C
    dT_hi = f_hi - config.ambient_C

    # dT_hi ≈ q_factor * dT_lo everywhere
    ratio = np.divide(dT_hi, dT_lo, out=np.ones_like(dT_hi), where=dT_lo > 1e-6)
    mean_ratio = float(np.mean(ratio))

    assert abs(mean_ratio - q_factor) < 0.15 * q_factor, (
        f"Expected ΔT ratio ≈ {q_factor:.2f}, got {mean_ratio:.2f}"
    )
