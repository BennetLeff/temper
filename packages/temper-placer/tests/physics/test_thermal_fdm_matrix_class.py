"""
Confirm the shipped thermal FDM stencil yields a SPD M-matrix (U1, R23, R10).

Tests:
- Happy (R10): Symmetric, positive-definite, M-matrix sign pattern
- PBT: M-matrix sign pattern holds for any grid shape + copper fraction
- Edge/guard: Injected anisotropy or perturbation trips the guard
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.physics.thermal_fdm import ThermalFDMConfig, get_system_matrix


# ---------------------------------------------------------------------------
# Matrix property check helpers
# ---------------------------------------------------------------------------


def _dirichlet_rows(A_dense: np.ndarray) -> np.ndarray:
    """Return boolean mask of Dirichlet identity rows.

    Dirichlet rows have ``A[i,i] == 1.0`` and all off-diagonals zero.
    """
    n = A_dense.shape[0]
    diag = np.abs(np.diag(A_dense))
    off_sum = np.sum(np.abs(A_dense), axis=1) - diag
    return (off_sum < 1e-14) & (np.abs(diag - 1.0) < 1e-14)


def _check_symmetry(A: "scipy.sparse.csr_matrix", atol: float = 1e-12) -> bool:
    """Return True if A is symmetric within *atol*.

    With boundary-aligned Dirichlet face terms there are no identity rows;
    the full matrix is symmetric.
    """
    A_dense = A.toarray()

    # Check full matrix symmetry
    if not np.allclose(A_dense, A_dense.T, atol=atol):
        return False
    return True


def _check_positive_definite(A: "scipy.sparse.csr_matrix") -> bool:
    """Return True if A is SPD (all eigenvalues > 0).

    Uses ``numpy.linalg.eigvalsh`` on the dense matrix — only safe for
    small grids.
    """
    A_dense = A.toarray()
    eigvals = np.linalg.eigvalsh(A_dense)
    return bool(np.all(eigvals > -1e-10))


def _check_m_matrix(A: "scipy.sparse.csr_matrix", atol: float = 1e-12) -> bool:
    """Return True if A has the M-matrix sign pattern.

    M-matrix properties checked:
    - Positive diagonal
    - Nonpositive off-diagonals
    - Weak diagonal dominance: |A[i,i]| >= sum_{j!=i} |A[i,j]|
    - At least one row is strictly diagonally dominant (heatsink face rows
      have the extra 2*k/dx2 Dirichlet face term)
    """
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
# Happy path (R10): SPD + M-matrix on representative isotropic grids
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("h,w", [(5, 5), (8, 12), (12, 6)])
def test_system_matrix_symmetry_isotropic(h, w):
    A = get_system_matrix(
        ThermalFDMConfig(
            cell_size_mm=1.0,
            origin_mm=(0.0, 0.0),
            height_cells=h,
            width_cells=w,
            ambient_C=40.0,
            heatsink_edge="TOP",
        ),
        copper_grid=np.full((h, w), 0.5, dtype=np.float64),
    )
    assert _check_symmetry(A), "System matrix should be symmetric"


@pytest.mark.parametrize("h,w", [(5, 5), (8, 12), (12, 6)])
def test_system_matrix_positive_definite_isotropic(h, w):
    A = get_system_matrix(
        ThermalFDMConfig(
            cell_size_mm=1.0,
            origin_mm=(0.0, 0.0),
            height_cells=h,
            width_cells=w,
            ambient_C=40.0,
            heatsink_edge="TOP",
        ),
        copper_grid=np.full((h, w), 0.5, dtype=np.float64),
    )
    assert _check_positive_definite(A), "System matrix should be positive-definite"


@pytest.mark.parametrize("h,w", [(5, 5), (8, 12), (12, 6)])
@pytest.mark.parametrize("heatsink_edge", ["TOP", "BOTTOM", "LEFT", "RIGHT"])
def test_system_matrix_m_matrix_pattern_isotropic(h, w, heatsink_edge):
    A = get_system_matrix(
        ThermalFDMConfig(
            cell_size_mm=1.0,
            origin_mm=(0.0, 0.0),
            height_cells=h,
            width_cells=w,
            ambient_C=40.0,
            heatsink_edge=heatsink_edge,
        ),
        copper_grid=np.full((h, w), 0.5, dtype=np.float64),
    )
    assert _check_m_matrix(A), (
        f"M-matrix pattern should hold (heatsink={heatsink_edge})"
    )


# ---------------------------------------------------------------------------
# Happy path (R10): SPD on a random isotropic board with copper variation
# ---------------------------------------------------------------------------


def test_system_matrix_spd_random_copper():
    rng = np.random.default_rng(1234)
    h, w = 10, 15
    copper = rng.uniform(0.0, 1.0, (h, w)).astype(np.float64)

    A = get_system_matrix(
        ThermalFDMConfig(
            cell_size_mm=1.0,
            origin_mm=(0.0, 0.0),
            height_cells=h,
            width_cells=w,
            ambient_C=40.0,
            heatsink_edge="TOP",
        ),
        copper_grid=copper,
    )
    assert _check_symmetry(A), "System matrix should be symmetric"
    assert _check_positive_definite(A), "System matrix should be positive-definite"
    assert _check_m_matrix(A), "System matrix should be an M-matrix"


# ---------------------------------------------------------------------------
# PBT: M-matrix sign pattern for any grid + copper fraction in [0, 1]
# ---------------------------------------------------------------------------


@st.composite
def config_and_copper(draw):
    h = draw(st.integers(3, 15))
    w = draw(st.integers(3, 15))
    edge = draw(st.sampled_from(["TOP", "BOTTOM", "LEFT", "RIGHT"]))
    cell = draw(st.floats(0.5, 2.0))
    k_fr4 = draw(st.floats(1.0, 1000.0))
    k_copper = draw(st.floats(100.0, 500.0))

    config = ThermalFDMConfig(
        cell_size_mm=cell,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge=edge,
        k_fr4=k_fr4,
        k_copper=k_copper,
        board_thickness_mm=1.6,
    )
    copper = draw(
        st.lists(
            st.floats(0.0, 1.0),
            min_size=h * w,
            max_size=h * w,
        ).map(lambda vals: np.array(vals, dtype=np.float64).reshape(h, w))
    )
    return config, copper


@given(cfg_cu=config_and_copper())
@settings(max_examples=100, deadline=2000)
def test_system_matrix_m_pattern_pbt(cfg_cu):
    config, copper = cfg_cu
    A = get_system_matrix(config, copper_grid=copper)
    assert _check_m_matrix(A), (
        f"M-matrix pattern violated: h={config.height_cells} w={config.width_cells}"
    )


# ---------------------------------------------------------------------------
# Precondition-failure branch: anisotropy / perturbation trips the guards
# ---------------------------------------------------------------------------


def _build_anisotropic_system_matrix(config, copper_grid):
    """Build a matrix with directional (anisotropic) interface conductivity.

    Uses the same pattern as ``_assemble_system`` but with different
    effective k for east/west vs north/south connections, so the matrix
    loses symmetry.  Dirichlet face terms at the heatsink edge follow
    the same boundary-aligned Dirichlet as the production code.

    This is a test-only tool to demonstrate the boundary of the SPD/M-matrix
    precondition — it is NOT a production feature.
    """
    from scipy.sparse import lil_matrix

    h = config.height_cells
    w = config.width_cells
    n = h * w
    cs = config.cell_size_mm
    dx2 = cs * cs
    dy2 = cs * cs

    k_f = _build_conductivity_field_aniso(config, copper_grid)
    A = lil_matrix((n, n), dtype=np.float64)

    for row in range(h):
        for col in range(w):
            idx = row * w + col

            diag = 0.0
            k_rowcol = k_f[row, col]

            # Directional: east uses cell's own k (no harmonic mean)
            if col + 1 < w:
                k_e = k_rowcol
                coeff = k_e / dx2
                A[idx, row * w + col + 1] = -coeff
                diag += coeff
            elif _is_heatsink_boundary_face(row, col, "east", config):
                coeff = 2.0 * k_rowcol / dx2
                diag += coeff

            if col - 1 >= 0:
                k_w = k_rowcol
                coeff = k_w / dx2
                A[idx, row * w + col - 1] = -coeff
                diag += coeff
            elif _is_heatsink_boundary_face(row, col, "west", config):
                coeff = 2.0 * k_rowcol / dx2
                diag += coeff

            # Different k-scaling for vertical connections (anisotropy)
            if row + 1 < h:
                k_n = k_rowcol * 10.0
                coeff = k_n / dy2
                A[idx, (row + 1) * w + col] = -coeff
                diag += coeff
            elif _is_heatsink_boundary_face(row, col, "north", config):
                coeff = 2.0 * k_rowcol * 10.0 / dy2
                diag += coeff

            if row - 1 >= 0:
                k_s = k_rowcol * 10.0
                coeff = k_s / dy2
                A[idx, (row - 1) * w + col] = -coeff
                diag += coeff
            elif _is_heatsink_boundary_face(row, col, "south", config):
                coeff = 2.0 * k_rowcol * 10.0 / dy2
                diag += coeff

            A[idx, idx] = diag

    return A.tocsr()


def _build_conductivity_field_aniso(config, copper_grid):
    """Return k_field for the anisotropic test helper."""
    from temper_placer.physics.thermal_fdm import _build_conductivity_field

    return _build_conductivity_field(config, copper_grid=copper_grid)


# Guard helper: symmetry violation check
def _guard_passes_symmetry(A):
    return _check_symmetry(A)


# Guard helper: positive-definiteness check
def _guard_passes_pd(A):
    return _check_positive_definite(A)


# Guard helper: M-matrix check
def _guard_passes_m_matrix(A):
    return _check_m_matrix(A)


def _is_heatsink_boundary_face(row, col, direction, config):
    """Inline copy of the private helper for test-only matrix construction."""
    from temper_placer.physics.thermal_fdm import _is_heatsink_boundary_face

    return _is_heatsink_boundary_face(row, col, direction, config)


def _is_neumann_boundary(row, col, direction, config):
    """Inline copy of the private helper for test-only matrix construction."""
    from temper_placer.physics.thermal_fdm import _is_neumann_boundary

    return _is_neumann_boundary(row, col, direction, config)


def test_anisotropic_matrix_trips_symmetry_guard():
    """An anisotropic stencil (directional k) produces an asymmetric matrix,
    so the symmetry guard must fail.

    We use a random non-uniform copper grid so that adjacent cells have
    different effective k.  In the anisotropic stencil each cell uses its
    *own* k for connections, so east(i→i+1) ≠ west(i+1→i).
    """
    h, w = 6, 6
    rng = np.random.default_rng(42)
    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )
    copper = rng.uniform(0.0, 1.0, (h, w)).astype(np.float64)
    A_aniso = _build_anisotropic_system_matrix(config, copper)

    assert not _guard_passes_symmetry(A_aniso), (
        "Anisotropic directional k (non-uniform copper) must trip the "
        "symmetry guard — asymmetry is the expected failure mode"
    )


def test_perturbed_off_diagonal_trips_m_matrix_guard():
    """A synthetic perturbation (positive off-diagonal) violates the
    M-matrix sign pattern, so the M-matrix guard must fail."""
    h, w = 6, 6
    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )
    copper = np.full((h, w), 0.5, dtype=np.float64)
    A = get_system_matrix(config, copper_grid=copper)
    A_lil = A.tolil()

    # Flip the sign of an off-diagonal: make it positive
    A_lil[0, 1] = abs(A_lil[0, 1])

    A_bad = A_lil.tocsr()
    assert not _guard_passes_m_matrix(A_bad), (
        "A positive off-diagonal must trip the M-matrix guard"
    )


def test_negative_diagonal_trips_pd_guard():
    """Making one diagonal entry negative destroys positive-definiteness,
    so the PD guard must fail."""
    h, w = 6, 6
    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )
    copper = np.full((h, w), 0.5, dtype=np.float64)
    A = get_system_matrix(config, copper_grid=copper)
    A_lil = A.tolil()

    # Flip an interior diagonal to negative
    interior_idx = 0  # row 0, col 0 — not a Dirichlet row
    A_lil[interior_idx, interior_idx] = -abs(A_lil[interior_idx, interior_idx])

    A_bad = A_lil.tocsr()
    assert not _guard_passes_pd(A_bad), (
        "A negative diagonal entry must trip the positive-definite guard"
    )


# ---------------------------------------------------------------------------
# Cross-check: the isotropic stencil satisfies all three properties
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("h,w", [(3, 3), (5, 7), (7, 5), (10, 10)])
@pytest.mark.parametrize("copper_frac", [0.0, 0.5, 1.0])
@pytest.mark.parametrize("heatsink_edge", ["TOP", "BOTTOM", "LEFT", "RIGHT"])
def test_isotropic_stencil_spd_m_matrix_crosscheck(h, w, copper_frac, heatsink_edge):
    """Full cross-check: for 48 (grid, copper, edge) combos, all three
    properties hold simultaneously on the shipped isotropic stencil."""
    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge=heatsink_edge,
    )
    copper = np.full((h, w), copper_frac, dtype=np.float64)

    A = get_system_matrix(config, copper_grid=copper)

    assert _check_symmetry(A), f"Symmetry failed: {h}x{w} copper={copper_frac} edge={heatsink_edge}"
    assert _check_positive_definite(A), (
        f"PD failed: {h}x{w} copper={copper_frac} edge={heatsink_edge}"
    )
    assert _check_m_matrix(A), (
        f"M-matrix failed: {h}x{w} copper={copper_frac} edge={heatsink_edge}"
    )
