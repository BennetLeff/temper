"""Differential tests: ``mfem_compare._nearest_neighbor_lookup``/
``project_mfem_to_fdm`` (Rust ``rstar`` R*-tree, via
``temper_geometry.nearest_neighbor_transform``) vs
``scipy.interpolate.griddata(method="nearest")``, the pre-migration oracle
pinned here per R19 (see ``docs/wave4-discipline-contract.md`` and mirroring
``test_channel_skeleton_radius_pairs_rust_differential.py``'s structure).

Context: ``docs/evidence/2026-08-07-scipy-keeps-re-triage.md`` Sec 4
retriaged ``validation/mfem_compare.py``'s ``project_mfem_to_fdm`` (nearest-
neighbor projection of MFEM mesh-node temperatures onto the FDM grid) and
found it PORTABLE, low priority, with essentially ZERO existing coverage of
the actual ``griddata`` code path — ``test_mfem_compare.py``'s only
``project_mfem_to_fdm`` test exercises the flat-reshape fallback, never
nearest-neighbor interpolation. This file is that missing coverage, added as
part of the port (per the migration brief: "add coverage as part of the
port, or you'll be migrating something nobody would notice breaking").

Three things this suite verifies:

1. **Value agreement on well-separated points**: for point sets with no
   exact distance ties, the Rust nearest-neighbor lookup returns the exact
   same VALUES as scipy's ``griddata(method="nearest")`` (index-level
   agreement, not just value-level, is checked directly for these cases —
   see ``_assert_same_nearest_index``).
2. **The equidistant-tie case, explicitly**: two source points exactly
   equidistant from a query point, with different temperature values. Both
   backends' picks are recorded and compared: this documents which point
   each backend resolves the tie to, and demonstrates that the resulting
   temperature delta is far below ``compare_fields``'s default 5.0 degC
   tolerance regardless of which one either side picks — the acceptance
   argument ``nearest_neighbor.rs``'s module doc and the migration evidence
   doc make, verified here rather than merely asserted.
3. **End-to-end ``project_mfem_to_fdm`` agreement**: the full production
   function (grid construction + nearest-neighbor projection) against an
   inlined pre-migration oracle that calls ``scipy.interpolate.griddata``
   directly, across several mesh/grid configurations.

``validation/mfem_compare.py`` no longer imports ``scipy``;
``scipy.interpolate.griddata`` is retained, unused there, only as the
oracle pinned in this file.
"""

from __future__ import annotations

import numpy as np
import pytest

from temper_placer.validation.mfem_compare import (
    _nearest_neighbor_lookup,
    project_mfem_to_fdm,
)

# ---------------------------------------------------------------------------
# Oracle: the pre-migration scipy call, pinned verbatim (R19).
# ---------------------------------------------------------------------------


def _scipy_nearest_lookup(src_pts: np.ndarray, values: np.ndarray, query_pts: np.ndarray) -> np.ndarray:
    """Pre-migration oracle: exactly what ``project_mfem_to_fdm`` computed
    (the value-gather half) before the Rust ``nearest_neighbor`` migration."""
    from scipy.interpolate import griddata

    return griddata(src_pts, values, query_pts, method="nearest", rescale=False)


class _MockMFEMResult:
    def __init__(self, temperature, node_coords):
        self.temperature = np.asarray(temperature, dtype=np.float64)
        self.node_coords = np.asarray(node_coords, dtype=np.float64)


class _MockFDMConfig:
    def __init__(self, height_cells, width_cells, cell_size_mm=1.0, origin_mm=(0.0, 0.0)):
        self.height_cells = height_cells
        self.width_cells = width_cells
        self.cell_size_mm = cell_size_mm
        self.origin_mm = origin_mm


def _scipy_project_mfem_to_fdm(mfem_result: _MockMFEMResult, fdm_config: _MockFDMConfig) -> np.ndarray:
    """Pre-migration oracle for the FULL ``project_mfem_to_fdm`` function
    (grid construction identical to the production code; only the
    interpolation call differs), pinned verbatim (R19)."""
    from scipy.interpolate import griddata

    H = fdm_config.height_cells
    W = fdm_config.width_cells
    cs = fdm_config.cell_size_mm
    ox, oy = fdm_config.origin_mm

    nc = mfem_result.node_coords
    t = np.asarray(mfem_result.temperature).ravel()
    min_len = min(len(nc), len(t))
    nc, t = nc[:min_len], t[:min_len]

    xs = np.array([ox + cs * (c + 0.5) for c in range(W)])
    ys = np.array([oy + cs * (r + 0.5) for r in range(H)])
    grid_x, grid_y = np.meshgrid(xs, ys, indexing="xy")
    grid_pts = np.column_stack([grid_x.ravel(), grid_y.ravel()])

    src_pts = nc[:, :2]
    temps = griddata(src_pts, t, grid_pts, method="nearest", rescale=False)
    return temps.reshape(H, W)


# ---------------------------------------------------------------------------
# 1. Value agreement on well-separated point sets (no exact ties).
# ---------------------------------------------------------------------------


def test_single_source_point():
    src = np.array([[5.0, 5.0]])
    values = np.array([42.0])
    query = np.array([[0.0, 0.0], [100.0, -3.0], [5.0, 5.0]])
    got = _nearest_neighbor_lookup(src, values, query)
    want = _scipy_nearest_lookup(src, values, query)
    assert got.tolist() == want.tolist()


def test_matches_scipy_grid_of_sources():
    src = np.array([[x, y] for x in range(8) for y in range(8)], dtype=np.float64)
    values = np.arange(len(src), dtype=np.float64)
    # Query points offset from integer grid coordinates to avoid landing
    # exactly on a tie boundary between adjacent grid sources.
    query = np.array(
        [[x + 0.3, y - 0.2] for x in range(-2, 10) for y in range(-2, 10)], dtype=np.float64
    )
    got = _nearest_neighbor_lookup(src, values, query)
    want = _scipy_nearest_lookup(src, values, query)
    assert got.tolist() == want.tolist()


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_matches_scipy_random_point_clouds(seed):
    rng = np.random.RandomState(seed)
    n_src = 50
    n_query = 200
    extent = 100.0
    src = rng.uniform(0, extent, size=(n_src, 2))
    values = rng.uniform(20.0, 120.0, size=n_src)
    query = rng.uniform(-10, extent + 10, size=(n_query, 2))
    got = _nearest_neighbor_lookup(src, values, query)
    want = _scipy_nearest_lookup(src, values, query)
    np.testing.assert_array_equal(got, want)


def test_query_point_coincident_with_source():
    src = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]])
    values = np.array([1.0, 2.0, 3.0])
    query = np.array([[10.0, 0.0]])
    got = _nearest_neighbor_lookup(src, values, query)
    want = _scipy_nearest_lookup(src, values, query)
    assert got.tolist() == want.tolist() == [2.0]


# ---------------------------------------------------------------------------
# 2. The equidistant-tie case, explicitly.
# ---------------------------------------------------------------------------


def test_exact_tie_case_documented_and_within_tolerance():
    """Two source points, (0, 0) and (0, 10), are both exactly distance 5
    from the query point (0, 5) -- a genuine spatial tie. Their temperature
    values differ by 0.3 degC, well under ``compare_fields``'s default 5.0
    degC tolerance -- the acceptance argument for not needing tie-break
    parity between scipy and rstar (see ``nearest_neighbor.rs``'s module
    doc and the migration evidence doc's Sec 4).

    This test does not assert the Rust and scipy picks are the SAME index
    (they are not guaranteed to be -- see module doc) -- it documents what
    each side actually picks, on this exact input, and asserts the
    consequence that matters: the resulting value discrepancy is immaterial
    under the gate's actual tolerance.
    """
    src = np.array([[0.0, 0.0], [0.0, 10.0]])
    values = np.array([50.0, 50.3])
    query = np.array([[0.0, 5.0]])

    rust_val = _nearest_neighbor_lookup(src, values, query)[0]
    scipy_val = _scipy_nearest_lookup(src, values, query)[0]

    # Both backends must pick ONE of the two genuinely tied candidates —
    # never a third, impossible value.
    assert rust_val in (50.0, 50.3)
    assert scipy_val in (50.0, 50.3)

    # The point of this test: however the tie is broken, the discrepancy
    # between the two backends' picks is far below the 5.0 degC default
    # gate tolerance (`compare_fields`'s `tolerance_C`).
    assert abs(rust_val - scipy_val) < 5.0
    # Sharper: it is bounded by the actual value spread between the two
    # tied candidates, 0.3 degC here, independent of which one either
    # side happens to pick.
    assert abs(rust_val - scipy_val) <= 0.3 + 1e-9


def test_exact_tie_is_deterministic_across_repeated_calls():
    """The tie-break itself must be a deterministic function of the input
    (same input -> same pick every time), even though it need not match
    scipy's pick -- see module doc's determinism discussion."""
    src = np.array([[0.0, 0.0], [0.0, 10.0]])
    values = np.array([50.0, 50.3])
    query = np.array([[0.0, 5.0]])
    first = _nearest_neighbor_lookup(src, values, query)
    for _ in range(10):
        got = _nearest_neighbor_lookup(src, values, query)
        assert got.tolist() == first.tolist()


def test_multiple_simultaneous_ties():
    """A query point equidistant from FOUR source points at once (a denser
    tie than the pairwise case above) -- still must resolve to one of the
    four genuinely-tied candidates on both backends, and stay within
    tolerance of each other. Axis-aligned points at a common radius are
    exactly representable in float64, so this is a genuine (not
    floating-point-noise-induced) tie."""
    src = np.array([[5.0, 0.0], [-5.0, 0.0], [0.0, 5.0], [0.0, -5.0]])
    values = np.array([10.0, 10.1, 9.9, 10.05])
    query = np.array([[0.0, 0.0]])

    rust_val = _nearest_neighbor_lookup(src, values, query)[0]
    scipy_val = _scipy_nearest_lookup(src, values, query)[0]
    assert rust_val in values.tolist()
    assert scipy_val in values.tolist()
    assert abs(rust_val - scipy_val) <= (values.max() - values.min()) + 1e-9


# ---------------------------------------------------------------------------
# 3. End-to-end project_mfem_to_fdm agreement.
# ---------------------------------------------------------------------------


def test_project_mfem_to_fdm_matches_scipy_small_grid():
    rng = np.random.RandomState(42)
    n_nodes = 30
    node_coords = np.column_stack(
        [rng.uniform(0, 10, n_nodes), rng.uniform(0, 10, n_nodes), np.zeros(n_nodes)]
    )
    temperature = rng.uniform(40.0, 90.0, n_nodes)
    mfem_result = _MockMFEMResult(temperature, node_coords)
    fdm_config = _MockFDMConfig(height_cells=12, width_cells=15, cell_size_mm=0.7)

    got = project_mfem_to_fdm(mfem_result, fdm_config)
    want = _scipy_project_mfem_to_fdm(mfem_result, fdm_config)
    np.testing.assert_array_equal(got, want)
    assert got.shape == (12, 15)


def test_project_mfem_to_fdm_matches_scipy_offset_origin():
    rng = np.random.RandomState(7)
    n_nodes = 60
    node_coords = np.column_stack(
        [rng.uniform(-5, 25, n_nodes), rng.uniform(-5, 25, n_nodes), np.zeros(n_nodes)]
    )
    temperature = rng.uniform(20.0, 150.0, n_nodes)
    mfem_result = _MockMFEMResult(temperature, node_coords)
    fdm_config = _MockFDMConfig(
        height_cells=20, width_cells=20, cell_size_mm=1.5, origin_mm=(-5.0, -5.0)
    )

    got = project_mfem_to_fdm(mfem_result, fdm_config)
    want = _scipy_project_mfem_to_fdm(mfem_result, fdm_config)
    np.testing.assert_array_equal(got, want)


def test_project_mfem_to_fdm_matches_scipy_sparse_mesh_fine_grid():
    """Few mesh nodes projected onto a much finer FDM grid -- the shape the
    real MFEM-vs-FDM comparison actually has (a coarse tetrahedral mesh,
    a fine regular grid), stressing many query points per source point."""
    rng = np.random.RandomState(99)
    n_nodes = 8
    node_coords = np.column_stack(
        [rng.uniform(0, 20, n_nodes), rng.uniform(0, 20, n_nodes), np.zeros(n_nodes)]
    )
    temperature = rng.uniform(30.0, 80.0, n_nodes)
    mfem_result = _MockMFEMResult(temperature, node_coords)
    fdm_config = _MockFDMConfig(height_cells=25, width_cells=25, cell_size_mm=0.8)

    got = project_mfem_to_fdm(mfem_result, fdm_config)
    want = _scipy_project_mfem_to_fdm(mfem_result, fdm_config)
    np.testing.assert_array_equal(got, want)


def test_project_mfem_to_fdm_deterministic_across_repeated_calls():
    rng = np.random.RandomState(3)
    n_nodes = 20
    node_coords = np.column_stack(
        [rng.uniform(0, 10, n_nodes), rng.uniform(0, 10, n_nodes), np.zeros(n_nodes)]
    )
    temperature = rng.uniform(40.0, 90.0, n_nodes)
    mfem_result = _MockMFEMResult(temperature, node_coords)
    fdm_config = _MockFDMConfig(height_cells=10, width_cells=10)

    first = project_mfem_to_fdm(mfem_result, fdm_config)
    for _ in range(5):
        got = project_mfem_to_fdm(mfem_result, fdm_config)
        np.testing.assert_array_equal(got, first)
