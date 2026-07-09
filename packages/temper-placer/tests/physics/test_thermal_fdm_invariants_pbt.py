"""
Property-based invariant battery for the thermal FDM solver (U4).

Invariants tested (each fail-capable against a realistic bug class):
  R7  — energy/flux conservation: total injected power ≈ Dirichlet boundary flux
  R8  — source monotonicity: Q1 ≤ Q2 ⇒ T1 ≤ T2 (M-matrix property)
  R9  — discrete maximum principle: all-heating + cold Dirichlet ⇒ no cell < ambient
  R10 — SPD well-posedness: system matrix is symmetric positive-definite
  R12 — metamorphic symmetry: translation/reflection/rotation transforms field identically

Uses Hypothesis PBT over boards ≤ 20×20.  Heavy PBT is marked
``@pytest.mark.property`` and ``@pytest.mark.l3_pbt``.

@req(2026-07-09-001-feat-physics-verification-rigor-plan, R7): energy/flux conservation invariant
@req(2026-07-09-001-feat-physics-verification-rigor-plan, R8): source monotonicity invariant
@req(2026-07-09-001-feat-physics-verification-rigor-plan, R9): discrete maximum principle invariant
@req(2026-07-09-001-feat-physics-verification-rigor-plan, R10): SPD well-posedness invariant
@req(2026-07-09-001-feat-physics-verification-rigor-plan, R12): metamorphic symmetry invariant
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from temper_placer.physics.thermal_fdm import (
    ThermalFDMConfig,
    _assemble_system,
    _build_conductivity_field,
    _is_neumann_boundary,
    get_system_matrix,
    solve_thermal_fdm,
)

# Aliases for brevity; kept inline to avoid polluting global namespace.
_HEATSINKS = ("TOP", "BOTTOM", "LEFT", "RIGHT")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _dirichlet_rows(A_dense: np.ndarray) -> np.ndarray:
    """Boolean mask of Dirichlet identity rows (vacuous with boundary-aligned
    Dirichlet face terms — the full matrix has no identity rows)."""
    diag = np.abs(np.diag(A_dense))
    off_sum = np.sum(np.abs(A_dense), axis=1) - diag
    return (off_sum < 1e-14) & (np.abs(diag - 1.0) < 1e-14)


def _is_dirichlet_mask(config: ThermalFDMConfig) -> np.ndarray:
    """Boolean mask of Dirichlet (heatsink) cells, shape (H, W).

    With boundary-aligned Dirichlet face terms there are no Dirichlet cells
    (all cells are active solved cells), so this returns all False.
    """
    h, w = config.height_cells, config.width_cells
    return np.zeros((h, w), dtype=bool)


def _heatsink_indices(config: ThermalFDMConfig):
    """Return ``(row, col)`` indices of all heatsink edge cells."""
    h, w = config.height_cells, config.width_cells
    edge = config.heatsink_edge.upper().strip()
    if edge == "TOP":
        return [(h - 1, c) for c in range(w)]
    elif edge == "BOTTOM":
        return [(0, c) for c in range(w)]
    elif edge == "LEFT":
        return [(r, 0) for r in range(h)]
    else:  # RIGHT
        return [(r, w - 1) for r in range(h)]


def _check_full_spd(A: "scipy.sparse.csr_matrix") -> bool:
    """Return True if the full matrix *A* is symmetric positive-definite."""
    A_dense = A.toarray()
    if not np.allclose(A_dense, A_dense.T, atol=1e-12):
        return False
    eigvals = np.linalg.eigvalsh(A_dense)
    return bool(np.all(eigvals > 1e-10))


def _total_injected_power(
    config: ThermalFDMConfig, Q_field: np.ndarray, cell_size_mm: float
) -> float:
    """Sum of Q_i * dx² over all cells (W).

    With boundary-aligned Dirichlet face terms, all cells are active
    solved cells — no Q values are excluded.
    """
    return float(np.sum(Q_field) * cell_size_mm * cell_size_mm)


def _dirichlet_boundary_flux(
    config: ThermalFDMConfig, T: np.ndarray, k_field: np.ndarray
) -> float:
    """Compute total heat flux (W) leaving through the Dirichlet boundary faces.

    With boundary-aligned Dirichlet face terms, the flux per heatsink-edge
    cell is 2 * k_c * (T_cell − T_ambient) — the conductance is 2*k_c
    because the cell centre is cs/2 from the physical boundary.
    """
    ambient = config.ambient_C
    flux = 0.0
    for row, col in _heatsink_indices(config):
        k_c = k_field[row, col]
        flux += 2.0 * k_c * (T[row, col] - ambient)
    return flux


def _safe_solve(config, Q_field, copper_grid=None):
    """Solve and return (T_grid, k_field) or skip if UNMEASURED.

    All cells are active solved cells — no Q values are masked.
    """
    h, w = config.height_cells, config.width_cells
    if copper_grid is None:
        copper_grid = np.zeros((h, w), dtype=np.float64)

    result = solve_thermal_fdm(
        config, copper_grid=copper_grid, Q_field=Q_field,
    )
    if not result.is_usable:
        pytest.skip("Solver returned UNMEASURED")
    T = np.asarray(result.field.grid, dtype=np.float64)
    k_field = _build_conductivity_field(config, copper_grid=copper_grid)
    return T, k_field


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


@st.composite
def small_grid_and_q(draw):
    """Generate a small board config + non-negative heat source field."""
    h = draw(st.integers(3, 15))
    w = draw(st.integers(3, 15))
    edge = draw(st.sampled_from(_HEATSINKS))
    cell = draw(st.floats(0.5, 2.0))
    k_fr4 = draw(st.floats(1.0, 500.0))
    k_cu = draw(st.floats(100.0, 500.0))

    config = ThermalFDMConfig(
        cell_size_mm=cell,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge=edge,
        k_fr4=k_fr4,
        k_copper=k_cu,
        board_thickness_mm=1.6,
        max_cells=2000,
    )

    q_vals = draw(
        st.lists(
            st.floats(0.0, 5.0),
            min_size=h * w,
            max_size=h * w,
        )
    )
    Q_field = np.array(q_vals, dtype=np.float64).reshape(h, w)

    return config, Q_field


@st.composite
def small_grid_q_and_copper(draw):
    """Generate config + Q_field + random copper grid."""
    config, Q_field = draw(small_grid_and_q())
    h, w = config.height_cells, config.width_cells
    cu_vals = draw(
        st.lists(
            st.floats(0.0, 1.0),
            min_size=h * w,
            max_size=h * w,
        )
    )
    copper = np.array(cu_vals, dtype=np.float64).reshape(h, w)
    return config, Q_field, copper


@st.composite
def small_grid_config(draw):
    """Generate a config only (no heat source)."""
    config, _ = draw(small_grid_and_q())
    return config


# ---------------------------------------------------------------------------
# R7  Energy / flux conservation
# ---------------------------------------------------------------------------


@pytest.mark.property
@pytest.mark.l3_pbt
@given(data=small_grid_q_and_copper())
@settings(max_examples=100, deadline=2000)
def test_r7_energy_conservation(data):
    """R7: total injected power ≈ Dirichlet boundary flux within tolerance."""
    config, Q_field, copper = data
    h, w = config.height_cells, config.width_cells
    cs = config.cell_size_mm

    result = solve_thermal_fdm(config, copper_grid=copper, Q_field=Q_field)
    assume(result.is_usable)
    T = np.asarray(result.field.grid, dtype=np.float64)
    k_field = _build_conductivity_field(config, copper_grid=copper)

    total_power = _total_injected_power(config, Q_field, cs)
    boundary_flux = _dirichlet_boundary_flux(config, T, k_field)

    atol = max(1e-9, 1e-12 * h * w * cs * cs)
    assert abs(total_power - boundary_flux) < atol, (
        f"Conservation violated: total_power={total_power:.6e} W, "
        f"boundary_flux={boundary_flux:.6e} W, diff={abs(total_power - boundary_flux):.6e}"
    )


def test_r7_fail_capable_sign_flip():
    """Fail-capable: flipping the sign of boundary flux breaks conservation check.

    Simulates a bug where the flux direction is reversed (e.g. wrong sign
    in the stencil Dirichlet coupling).  The negative total computed flux
    will disagree with the (positive) injected power.
    """
    h, w = 8, 10
    cs = 1.0
    config = ThermalFDMConfig(
        cell_size_mm=cs,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=2000,
    )
    Q_field = np.full((h, w), 0.1, dtype=np.float64)
    copper = np.full((h, w), 0.5, dtype=np.float64)

    T, k_field = _safe_solve(config, Q_field, copper_grid=copper)
    total_power = _total_injected_power(config, Q_field, cs)
    correct_flux = _dirichlet_boundary_flux(config, T, k_field)

    # The check passes on the un-bugged solver
    assert abs(total_power - correct_flux) < 1e-8

    # Bug: flip the flux sign (simulates reversed Dirichlet coupling)
    buggy_flux = -correct_flux
    assert not (abs(total_power - buggy_flux) < 1e-8), (
        "Fail-capable check: a sign-flipped boundary flux MUST be "
        "detected as violating energy conservation"
    )


# ---------------------------------------------------------------------------
# R8  Source monotonicity
# ---------------------------------------------------------------------------


def _monotonicity_check(config, copper, Q1, Q2):
    """Return True if T1 ≤ T2 elementwise, False otherwise."""
    r1 = solve_thermal_fdm(config, copper_grid=copper, Q_field=Q1)
    r2 = solve_thermal_fdm(config, copper_grid=copper, Q_field=Q2)
    if not r1.is_usable or not r2.is_usable:
        return None  # skip
    T1 = np.asarray(r1.field.grid, dtype=np.float64)
    T2 = np.asarray(r2.field.grid, dtype=np.float64)
    return bool(np.all(T1 <= T2 + 1e-12))


@pytest.mark.property
@pytest.mark.l3_pbt
@given(data=small_grid_q_and_copper())
@settings(max_examples=50, deadline=2000)
def test_r8_source_monotonicity(data):
    """R8: Q1 ≤ Q2 elementwise ⇒ T1 ≤ T2 elementwise (M-matrix property)."""
    config, _, copper = data

    h, w = config.height_cells, config.width_cells
    rng = np.random.default_rng(
        int(abs(hash((config.height_cells, config.width_cells, config.heatsink_edge))))
        % (2**31)
    )
    Q1 = rng.uniform(0.0, 3.0, (h, w)).astype(np.float64)
    delta = rng.uniform(0.0, 3.0, (h, w)).astype(np.float64)
    Q2 = Q1 + delta

    result = _monotonicity_check(config, copper, Q1, Q2)
    assume(result is not None)
    assert result, "Monotonicity violated: Q1 ≤ Q2 but T1 > T2 somewhere"


def test_r8_fail_capable_assembly_sign_error():
    """Fail-capable: flipping an off-diagonal sign in the system matrix
    breaks the M-matrix property, which in turn breaks monotonicity.

    A real assembly bug (e.g. missing a minus sign on a stencil coefficient)
    makes at least one off-diagonal positive — the inverse then has a negative
    entry, violating T = A⁻¹b ≥ 0 monotonicity for a source increase.
    """
    from scipy.sparse.linalg import spsolve

    h, w = 6, 6
    cs = 1.0
    config = ThermalFDMConfig(
        cell_size_mm=cs,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=2000,
    )
    copper = np.full((h, w), 0.5, dtype=np.float64)
    k_field = _build_conductivity_field(config, copper_grid=copper)

    # Verify monotonicity holds with the correct matrix
    Q1 = np.full((h, w), 0.1, dtype=np.float64)
    Q2 = np.full((h, w), 0.5, dtype=np.float64)
    assert _monotonicity_check(config, copper, Q1, Q2)

    # Construct a buggy matrix: flip the sign of one interior off-diagonal
    A_correct, b1 = _assemble_system(config, k_field, Q1)
    _, b2 = _assemble_system(config, k_field, Q2)

    A_lil = A_correct.tolil()
    n_total = h * w
    for idx in range(n_total):
        row_sum = sum(abs(A_lil[idx, j]) for j in range(n_total))
        # All rows are active (no identity rows); any row with off-diagonals
        if row_sum > 0 and any(abs(A_lil[idx, j]) > 1e-12 for j in range(n_total) if j != idx):
            # Pick the first non-zero off-diagonal and flip sign
            for j in range(n_total):
                if j != idx and abs(A_lil[idx, j]) > 1e-12:
                    A_lil[idx, j] = abs(A_lil[idx, j])
                    A_bad = A_lil.tocsr()
                    T1_bad = spsolve(A_bad, b1).reshape(h, w)
                    T2_bad = spsolve(A_bad, b2).reshape(h, w)
                    # This should violate monotonicity somewhere
                    if not np.all(T1_bad <= T2_bad + 1e-10):
                        return  # fail-capable: the bug was detected
                    # Reset and try next
                    A_lil[idx, j] = -abs(A_lil[idx, j])

    pytest.fail(
        "Fail-capable: flipping an off-diagonal sign should have broken "
        "monotonicity but did not — the invariant check might be vacuous"
    )


# ---------------------------------------------------------------------------
# R9  Discrete maximum principle
# ---------------------------------------------------------------------------


@pytest.mark.property
@pytest.mark.l3_pbt
@given(data=small_grid_q_and_copper())
@settings(max_examples=50, deadline=2000)
def test_r9_maximum_principle(data):
    """R9: all-heating (Q ≥ 0 everywhere) + cold Dirichlet → no interior
    cell below ambient temperature."""
    config, Q_field, copper = data

    T, _ = _safe_solve(config, Q_field, copper_grid=copper)
    ambient = config.ambient_C

    # All cells are active solved cells — maximum principle applies everywhere
    min_all = float(np.min(T))
    assert min_all >= ambient - 1e-10, (
        f"Maximum principle violated: ambient={ambient}°C, "
        f"min cell={min_all:.6f}°C"
    )


def test_r9_fail_capable_bc_swap():
    """Fail-capable: flipping the sign of an off-diagonal matrix coefficient
    creates a positive off-diagonal — breaking the M-matrix property.  With
    Q ≥ 0 and a cold Dirichlet edge, the maximum principle (no cell below
    ambient) can now be violated because the inverse may have negative entries.

    Simulates a real assembly bug where a minus sign is missing on a
    stencil coefficient connecting an interior cell to a Dirichlet neighbour.
    """
    from scipy.sparse.linalg import spsolve

    h, w = 6, 8
    cs = 1.0
    config = ThermalFDMConfig(
        cell_size_mm=cs,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=2000,
    )

    # Non-uniform heat: strong source far from Dirichlet, weak near it
    Q_field = np.zeros((h, w), dtype=np.float64)
    Q_field[0, :] = 10.0  # bottom row — far from TOP Dirichlet
    Q_field[h - 2, :] = 0.01  # near-heatsink — negligible

    copper = np.full((h, w), 0.5, dtype=np.float64)

    # Verify the correct solver obeys the maximum principle
    T_correct, _ = _safe_solve(config, Q_field, copper_grid=copper)
    ambient = config.ambient_C
    assert np.min(T_correct) >= ambient - 1e-10, (
        "Expected maximum principle to hold on correct solver"
    )

    # Bug: flip one off-diagonal sign in the matrix (makes it positive),
    # simulating a missing minus sign in stencil assembly.
    k_field = _build_conductivity_field(config, copper_grid=copper)
    A_correct, b = _assemble_system(config, k_field, Q_field)

    A_lil = A_correct.tolil()
    n = h * w
    violated = False
    for idx in range(n):
        diag_val = A_lil[idx, idx]
        row_sum_off = sum(abs(A_lil[idx, j]) for j in range(n) if j != idx)
        # Every row is an active (non-identity) row with boundary-aligned BC
        if row_sum_off > 1e-12:
            for j in range(n):
                if j != idx and abs(A_lil[idx, j]) > 1e-12:
                    # Flip sign -> positive off-diagonal
                    A_lil[idx, j] = abs(A_lil[idx, j])
                    A_bad = A_lil.tocsr()
                    T_bad = spsolve(A_bad, b).reshape(h, w)
                    if np.min(T_bad) < ambient - 1e-10:
                        violated = True
                        break
                    # Reset
                    A_lil[idx, j] = -abs(A_lil[idx, j])
            if violated:
                break

    assert violated, (
        "Fail-capable: a positive off-diagonal (simulating a missing minus "
        "in stencil assembly) must break the M-matrix property and allow "
        "interior temperatures below ambient"
    )


# ---------------------------------------------------------------------------
# R10  SPD well-posedness  (delegates to U1 approach)
# ---------------------------------------------------------------------------


@pytest.mark.property
@pytest.mark.l3_pbt
@given(config=small_grid_config())
@settings(max_examples=50, deadline=2000)
def test_r10_full_spd(config):
    """R10: full system matrix of get_system_matrix is symmetric positive-definite."""
    h, w = config.height_cells, config.width_cells
    copper = np.full((h, w), 0.5, dtype=np.float64)
    A = get_system_matrix(config, copper_grid=copper)
    assert _check_full_spd(A), (
        f"Full matrix not SPD: h={h} w={w} edge={config.heatsink_edge}"
    )


def test_r10_fail_capable():
    """Fail-capable: flipping a diagonal entry negative
    destroys positive-definiteness; the SPD check must detect it."""
    h, w = 6, 6
    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=2000,
    )
    copper = np.full((h, w), 0.5, dtype=np.float64)
    A = get_system_matrix(config, copper_grid=copper)

    # Verify correct matrix is SPD
    assert _check_full_spd(A), "Expected SPD on correct matrix"

    # Perturb any diagonal (all rows are active now)
    A_lil = A.tolil()
    n = h * w
    for idx in range(n):
        # Find the first interior row (any row with non-zero off-diagonals)
        if A_lil[idx, idx] != 1.0 and sum(abs(A_lil[idx, j]) for j in range(n) if j != idx) > 0:
            A_lil[idx, idx] = -abs(A_lil[idx, idx])
            break

    A_bad = A_lil.tocsr()
    assert not _check_full_spd(A_bad), (
        "Fail-capable: a negative diagonal entry must trip the SPD check"
    )


def test_r10_spd_random_copper():
    """Deterministic cross-check: SPD holds for a random copper field."""
    rng = np.random.default_rng(1234)
    h, w = 10, 12
    copper = rng.uniform(0.0, 1.0, (h, w)).astype(np.float64)
    for edge in _HEATSINKS:
        config = ThermalFDMConfig(
            cell_size_mm=1.0,
            origin_mm=(0.0, 0.0),
            height_cells=h,
            width_cells=w,
            ambient_C=40.0,
            heatsink_edge=edge,
            max_cells=2000,
        )
        A = get_system_matrix(config, copper_grid=copper)
        assert _check_full_spd(A), f"SPD failed for edge={edge}"


# ---------------------------------------------------------------------------
# R12  Metamorphic symmetry
# ---------------------------------------------------------------------------


def _apply_vertical_mirror(config, Q_field, copper):
    """Reflect about horizontal midline (heatsink TOP ↔ BOTTOM).

    Dirichlet-cell Q values are zeroed before mirroring — they are
    semantically meaningless (the solver ignores them) and must not
    become active heat sources in the transformed configuration.
    """
    Q_eff = Q_field.copy()
    Q_eff[_is_dirichlet_mask(config)] = 0.0
    copper_eff = copper.copy()

    edge = config.heatsink_edge.upper().strip()
    mirror_map = {"TOP": "BOTTOM", "BOTTOM": "TOP", "LEFT": "LEFT", "RIGHT": "RIGHT"}
    new_edge = mirror_map.get(edge, edge)
    new_config = ThermalFDMConfig(
        cell_size_mm=config.cell_size_mm,
        origin_mm=config.origin_mm,
        height_cells=config.height_cells,
        width_cells=config.width_cells,
        ambient_C=config.ambient_C,
        heatsink_edge=new_edge,
        k_fr4=config.k_fr4,
        k_copper=config.k_copper,
        board_thickness_mm=config.board_thickness_mm,
        max_cells=config.max_cells,
    )
    return new_config, np.flipud(Q_eff), np.flipud(copper_eff)


def _apply_horizontal_mirror(config, Q_field, copper):
    """Reflect about vertical midline (heatsink LEFT ↔ RIGHT)."""
    Q_eff = Q_field.copy()
    Q_eff[_is_dirichlet_mask(config)] = 0.0
    copper_eff = copper.copy()

    edge = config.heatsink_edge.upper().strip()
    mirror_map = {"LEFT": "RIGHT", "RIGHT": "LEFT", "TOP": "TOP", "BOTTOM": "BOTTOM"}
    new_edge = mirror_map.get(edge, edge)
    new_config = ThermalFDMConfig(
        cell_size_mm=config.cell_size_mm,
        origin_mm=config.origin_mm,
        height_cells=config.height_cells,
        width_cells=config.width_cells,
        ambient_C=config.ambient_C,
        heatsink_edge=new_edge,
        k_fr4=config.k_fr4,
        k_copper=config.k_copper,
        board_thickness_mm=config.board_thickness_mm,
        max_cells=config.max_cells,
    )
    return new_config, np.fliplr(Q_eff), np.fliplr(copper_eff)


def _apply_90cw_rotation(config, Q_field, copper):
    """Rotate 90° clockwise (heatsink rotates: TOP→RIGHT→BOTTOM→LEFT→TOP).

    Dirichlet-cell Q values are zeroed before rotation so they don't become
    spurious heat sources in the rotated configuration.

    Note: with grid rows increasing upward (row 0 = bottom, row h-1 = top),
    the 90° CW physical rotation corresponds to ``np.rot90(k=1)``.
    """
    Q_eff = Q_field.copy()
    Q_eff[_is_dirichlet_mask(config)] = 0.0
    copper_eff = copper.copy()

    edge = config.heatsink_edge.upper().strip()
    rot_map = {"TOP": "RIGHT", "RIGHT": "BOTTOM", "BOTTOM": "LEFT", "LEFT": "TOP"}
    new_edge = rot_map[edge]
    new_config = ThermalFDMConfig(
        cell_size_mm=config.cell_size_mm,
        origin_mm=config.origin_mm,
        height_cells=config.width_cells,
        width_cells=config.height_cells,
        ambient_C=config.ambient_C,
        heatsink_edge=new_edge,
        k_fr4=config.k_fr4,
        k_copper=config.k_copper,
        board_thickness_mm=config.board_thickness_mm,
        max_cells=config.max_cells,
    )
    return (
        new_config,
        np.rot90(Q_eff, k=1),
        np.rot90(copper_eff, k=1),
    )


# ----- Vertical mirror ------------------------------------------------------


@pytest.mark.property
@pytest.mark.l3_pbt
@given(data=small_grid_q_and_copper())
@settings(max_examples=30, deadline=2000)
def test_r12_vertical_mirror(data):
    """R12: vertical reflection of a board transforms the field identically."""
    config, Q_field, copper = data
    assume(config.heatsink_edge.upper().strip() in ("TOP", "BOTTOM"))

    T_orig, _ = _safe_solve(config, Q_field, copper_grid=copper)

    cfg_m, Q_m, cu_m = _apply_vertical_mirror(config, Q_field, copper)
    T_mirror, _ = _safe_solve(cfg_m, Q_m, copper_grid=cu_m)

    T_expected = np.flipud(T_orig)
    assert np.allclose(T_mirror, T_expected, atol=1e-9), (
        f"Vertical mirror mismatch: max_diff={np.max(np.abs(T_mirror - T_expected)):.2e}"
    )


# ----- Horizontal mirror ----------------------------------------------------


@pytest.mark.property
@pytest.mark.l3_pbt
@given(data=small_grid_q_and_copper())
@settings(max_examples=30, deadline=2000)
def test_r12_horizontal_mirror(data):
    """R12: horizontal reflection of a board transforms the field identically."""
    config, Q_field, copper = data
    assume(config.heatsink_edge.upper().strip() in ("LEFT", "RIGHT"))

    T_orig, _ = _safe_solve(config, Q_field, copper_grid=copper)

    cfg_m, Q_m, cu_m = _apply_horizontal_mirror(config, Q_field, copper)
    T_mirror, _ = _safe_solve(cfg_m, Q_m, copper_grid=cu_m)

    T_expected = np.fliplr(T_orig)
    assert np.allclose(T_mirror, T_expected, atol=1e-9), (
        f"Horizontal mirror mismatch: max_diff={np.max(np.abs(T_mirror - T_expected)):.2e}"
    )


# ----- 90° CW rotation ------------------------------------------------------


@pytest.mark.property
@pytest.mark.l3_pbt
@given(data=small_grid_q_and_copper())
@settings(max_examples=30, deadline=2000)
def test_r12_90cw_rotation(data):
    """R12: 90° CW rotation of a board transforms the field identically."""
    config, Q_field, copper = data

    T_orig, _ = _safe_solve(config, Q_field, copper_grid=copper)

    cfg_r, Q_r, cu_r = _apply_90cw_rotation(config, Q_field, copper)
    T_rot, _ = _safe_solve(cfg_r, Q_r, copper_grid=cu_r)

    T_expected = np.rot90(T_orig, k=1)
    assert np.allclose(T_rot, T_expected, atol=1e-9), (
        f"90° CW rotation mismatch: max_diff={np.max(np.abs(T_rot - T_expected)):.2e}"
    )


# ----- Fail-capable: x/y swap -----------------------------------------------


def test_r12_fail_capable_xy_swap():
    """Fail-capable: applying the wrong transformation to the heat source
    field (e.g. transposing Q instead of flipping it) produces a temperature
    field that does NOT match the correct metamorphic expectation.

    Simulates a row/col-major or x/y coordinate-swap bug in the source
    rasteriser that maps heat to the wrong grid position.
    """
    h, w = 6, 8
    cs = 1.0
    config = ThermalFDMConfig(
        cell_size_mm=cs,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=2000,
    )
    copper = np.full((h, w), 0.3, dtype=np.float64)

    # Asymmetric heat source so position matters
    Q_field = np.zeros((h, w), dtype=np.float64)
    Q_field[1, 3] = 5.0
    Q_field[4, 2] = 2.0

    T_orig, _ = _safe_solve(config, Q_field, copper_grid=copper)

    # Correct vertical mirror: TOP→BOTTOM, flipud both Q and copper and T
    cfg_m, Q_m_correct, cu_m = _apply_vertical_mirror(config, Q_field, copper)
    T_m_correct, _ = _safe_solve(cfg_m, Q_m_correct, copper_grid=cu_m)
    T_expected = np.flipud(T_orig)
    assert np.allclose(T_m_correct, T_expected, atol=1e-9), (
        "Precondition: correct vertical mirror must match"
    )

    # Bug: use fliplr (horizontal reflection) instead of flipud on the
    # heat source, while keeping the correct heatsink change (TOP→BOTTOM).
    # This is an x/y mismatch bug — the heat pattern is mirrored about the
    # wrong axis.
    Q_wrong = np.fliplr(Q_field)
    T_wrong, _ = _safe_solve(cfg_m, Q_wrong, copper_grid=cu_m)

    # The wrongly-transformed field should NOT match the correct mirror
    assert not np.allclose(T_wrong, T_expected, atol=1e-9), (
        "Fail-capable: an x/y-swapped transformation (fliplr instead of "
        "flipud) must produce a field that does NOT match the correct "
        "vertical-mirror expectation"
    )


# ----- R12: deterministic cross-checks on uniform/symmetric boards ----------


def test_r12_vertical_mirror_uniform():
    """Deterministic vertical mirror check on a uniform symmetric board."""
    h, w = 8, 8
    cs = 1.0
    config = ThermalFDMConfig(
        cell_size_mm=cs,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=2000,
    )
    copper = np.full((h, w), 0.5, dtype=np.float64)
    Q_field = np.ones((h, w), dtype=np.float64) * 0.1

    T_orig, _ = _safe_solve(config, Q_field, copper_grid=copper)

    cfg_m, Q_m, cu_m = _apply_vertical_mirror(config, Q_field, copper)
    T_mirror, _ = _safe_solve(cfg_m, Q_m, copper_grid=cu_m)

    assert np.allclose(T_mirror, np.flipud(T_orig), atol=1e-9)


def test_r12_horizontal_mirror_uniform():
    """Deterministic horizontal mirror check on a uniform symmetric board."""
    h, w = 8, 8
    cs = 1.0
    config = ThermalFDMConfig(
        cell_size_mm=cs,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="LEFT",
        max_cells=2000,
    )
    copper = np.full((h, w), 0.5, dtype=np.float64)
    Q_field = np.ones((h, w), dtype=np.float64) * 0.1

    T_orig, _ = _safe_solve(config, Q_field, copper_grid=copper)

    cfg_m, Q_m, cu_m = _apply_horizontal_mirror(config, Q_field, copper)
    T_mirror, _ = _safe_solve(cfg_m, Q_m, copper_grid=cu_m)

    assert np.allclose(T_mirror, np.fliplr(T_orig), atol=1e-9)


def test_r12_90cw_uniform_square():
    """Deterministic 90° CW rotation on a uniform square board."""
    h = w = 8
    cs = 1.0
    config = ThermalFDMConfig(
        cell_size_mm=cs,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=2000,
    )
    copper = np.full((h, w), 0.5, dtype=np.float64)
    Q_field = np.ones((h, w), dtype=np.float64) * 0.1

    T_orig, _ = _safe_solve(config, Q_field, copper_grid=copper)

    cfg_r, Q_r, cu_r = _apply_90cw_rotation(config, Q_field, copper)
    T_rot, _ = _safe_solve(cfg_r, Q_r, copper_grid=cu_r)

    T_expected = np.rot90(T_orig, k=1)
    assert np.allclose(T_rot, T_expected, atol=1e-9)


def test_r12_180deg_as_dual_rotation():
    """Two 90° CW rotations give a 180° rotation — composability check."""
    h = w = 8
    cs = 1.0
    config = ThermalFDMConfig(
        cell_size_mm=cs,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=2000,
    )
    copper = np.full((h, w), 0.3, dtype=np.float64)
    Q_field = np.random.default_rng(42).uniform(0, 3, (h, w)).astype(np.float64)

    T_orig, _ = _safe_solve(config, Q_field, copper_grid=copper)

    # One 90° CW
    cfg1, Q1, cu1 = _apply_90cw_rotation(config, Q_field, copper)
    # Another 90° CW
    cfg2, Q2, cu2 = _apply_90cw_rotation(cfg1, Q1, cu1)

    T_double, _ = _safe_solve(cfg2, Q2, copper_grid=cu2)
    T_expected = np.rot90(T_orig, k=2)

    assert np.allclose(T_double, T_expected, atol=1e-9), (
        f"180° rotation mismatch: max_diff={np.max(np.abs(T_double - T_expected)):.2e}"
    )
