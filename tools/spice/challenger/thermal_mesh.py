"""
2D steady-state finite-difference thermal solver.

Implements the heat equation on a rectangular grid representing the PCB
cross-section (FR-4 substrate, copper layers, IGBT footprint). Uses
second-order central differences with Gauss-Seidel iteration.

The solver adapts the two-node R-theta network pattern from the temper-placer
cost function as its structural template:
  - R_jc: junction-to-case (component datasheet)
  - R_ca: case-to-ambient (convection boundary condition)
  - T_j = T_amb + P * (R_jc + R_ca)

The interface shape matches the placer (read per-corner Pdiss, return Tj)
but source files are completely independent (R7 compliance).

Verification: Known-good test case — two resistors on a uniform bar should
match analytical solution within 5%.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ThermalMeshConfig:
    """Configuration for the 2D thermal mesh solver."""

    width_mm: float = 100.0
    height_mm: float = 150.0
    grid_resolution_mm: float = 0.5

    board_thickness_mm: float = 1.6
    copper_thickness_mm: float = 0.035

    k_fr4_W_per_mK: float = 0.3
    k_copper_W_per_mK: float = 385.0

    T_ambient_C: float = 25.0

    h_convection_W_per_m2K: float = 10.0

    R_jc_K_per_W: float = 1.0
    R_ca_K_per_W: float = 10.0

    max_iterations: int = 50000
    convergence_tol: float = 1e-6


@dataclass
class HeatSource:
    """A discrete heat source on the PCB."""

    x_mm: float
    y_mm: float
    power_W: float
    width_mm: float = 10.0
    height_mm: float = 15.0


@dataclass
class ThermalResult:
    """Result of a thermal simulation."""

    T_max_C: float
    T_avg_C: float
    T_field: list[list[float]]
    converged: bool
    iterations: int
    residual: float


def solve_2d_steady_state(
    config: ThermalMeshConfig,
    heat_sources: list[HeatSource],
) -> ThermalResult:
    """Solve the 2D steady-state heat equation.

    Uses Gauss-Seidel iteration on a finite-difference grid.
    The heat equation: k * ∇²T + q''' = 0

    Boundary conditions: convection (Robin) at all edges.
    """
    nx = int(config.width_mm / config.grid_resolution_mm) + 1
    ny = int(config.height_mm / config.grid_resolution_mm) + 1
    dx = config.grid_resolution_mm * 1e-3
    dy = config.grid_resolution_mm * 1e-3

    k_eff = config.k_fr4_W_per_mK

    T = _initialize_temperature(nx, ny, config.T_ambient_C, heat_sources, config)

    q = _build_source_field(nx, ny, dx, dy, config, heat_sources)

    conv = config.h_convection_W_per_m2K

    converged = False
    final_residual = 0.0

    for _it in range(config.max_iterations):
        residual = 0.0
        for j in range(ny):
            for i in range(nx):
                if _is_boundary(i, j, nx, ny):
                    T_new = _boundary_update(
                        i, j, nx, ny, T, dx, dy, k_eff, conv, config.T_ambient_C
                    )
                else:
                    T_new = _interior_update(
                        i, j, T, dx, dy, k_eff, q[j][i]
                    )

                residual = max(residual, abs(T_new - T[j][i]))
                T[j][i] = T_new

        if residual < config.convergence_tol:
            converged = True
            final_residual = residual
            break
    else:
        final_residual = residual

    T_max = max(max(row) for row in T)
    T_sum = sum(sum(row) for row in T)
    T_avg = T_sum / (nx * ny)

    return ThermalResult(
        T_max_C=T_max,
        T_avg_C=T_avg,
        T_field=T,
        converged=converged,
        iterations=_it + 1,
        residual=final_residual,
    )


def _initialize_temperature(
    nx: int,
    ny: int,
    T_amb: float,
    heat_sources: list[HeatSource],
    config: ThermalMeshConfig,
) -> list[list[float]]:
    """Initialize temperature field with ambient."""
    T = [[T_amb for _ in range(nx)] for _ in range(ny)]
    return T


def _build_source_field(
    nx: int,
    ny: int,
    dx: float,
    dy: float,
    config: ThermalMeshConfig,
    heat_sources: list[HeatSource],
) -> list[list[float]]:
    """Build volumetric heat source field q''' [W/m³]."""
    q: list[list[float]] = [[0.0 for _ in range(nx)] for _ in range(ny)]
    thickness_m = config.board_thickness_mm * 1e-3

    for hs in heat_sources:
        if hs.power_W <= 0:
            continue
        hs_volume = (
            hs.width_mm * 1e-3 * hs.height_mm * 1e-3 * thickness_m
        )
        if hs_volume <= 0:
            continue
        q_vol = hs.power_W / hs_volume

        i_min = int((hs.x_mm - hs.width_mm / 2) / (config.grid_resolution_mm))
        i_max = int((hs.x_mm + hs.width_mm / 2) / (config.grid_resolution_mm))
        j_min = int((hs.y_mm - hs.height_mm / 2) / (config.grid_resolution_mm))
        j_max = int((hs.y_mm + hs.height_mm / 2) / (config.grid_resolution_mm))

        i_min = max(0, i_min)
        i_max = min(nx - 1, i_max)
        j_min = max(0, j_min)
        j_max = min(ny - 1, j_max)

        for j in range(j_min, j_max + 1):
            for i in range(i_min, i_max + 1):
                q[j][i] = q_vol

    return q


def _is_boundary(i: int, j: int, nx: int, ny: int) -> bool:
    return i == 0 or i == nx - 1 or j == 0 or j == ny - 1


def _interior_update(
    i: int,
    j: int,
    T: list[list[float]],
    dx: float,
    dy: float,
    k: float,
    q_vol: float,
) -> float:
    """Gauss-Seidel update for interior nodes (second-order central difference)."""
    T_e = T[j][i + 1] if i + 1 < len(T[0]) else T[j][i]
    T_w = T[j][i - 1] if i > 0 else T[j][i]
    T_n = T[j - 1][i] if j > 0 else T[j][i]
    T_s = T[j + 1][i] if j + 1 < len(T) else T[j][i]

    numerator = (T_e + T_w) / (dx * dx) + (T_n + T_s) / (dy * dy) + q_vol / k
    denominator = 2.0 / (dx * dx) + 2.0 / (dy * dy)

    if denominator == 0:
        return T[j][i]
    return numerator / denominator


def _boundary_update(
    i: int,
    j: int,
    nx: int,
    ny: int,
    T: list[list[float]],
    dx: float,
    dy: float,
    k: float,
    h: float,
    T_inf: float,
) -> float:
    """Convection (Robin) boundary condition update."""
    interior_i = 1 if i == 0 else (nx - 2 if i == nx - 1 else i)
    interior_j = 1 if j == 0 else (ny - 2 if j == ny - 1 else j)

    T_int = T[interior_j][interior_i]

    boundary_dist = dx if (i == 0 or i == nx - 1) else dy

    T_bound = (h * boundary_dist / k * T_inf + T_int) / (
        1.0 + h * boundary_dist / k
    )
    return T_bound


def compute_Tj_rtheta(
    power_W: float,
    T_ambient: float,
    R_jc: float,
    R_ca: float,
) -> float:
    """Compute junction temperature using two-node R-theta network.

    This is the structural pattern shared with the temper-placer
    cost function: T_j = T_amb + P * (R_jc + R_ca).
    """
    return T_ambient + power_W * (R_jc + R_ca)


def analytical_uniform_bar(
    length_m: float,
    width_m: float,
    thickness_m: float,
    k_W_per_mK: float,
    power_W: float,
    T_ambient: float,
    h_W_per_m2K: float,
) -> float:
    """Analytical 1D steady-state solution for uniform bar with convection.

    Used as verification test case.
    """
    perimeter = 2.0 * (width_m + thickness_m)
    area = width_m * thickness_m
    m = math.sqrt(h_W_per_m2K * perimeter / (k_W_per_mK * area))

    if m < 1e-15:
        return T_ambient

    T_max = T_ambient + power_W / (
        h_W_per_m2K * perimeter * length_m
    ) * (1.0 - math.exp(-m * length_m))

    T_max += power_W / (math.sqrt(h_W_per_m2K * perimeter * k_W_per_mK * area))

    T_base = T_ambient + power_W / (h_W_per_m2K * perimeter * length_m)
    T_max = T_base + (power_W * length_m) / (2.0 * k_W_per_mK * area)

    return T_max
