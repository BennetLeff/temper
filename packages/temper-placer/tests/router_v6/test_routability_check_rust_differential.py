"""Differential tests for the Rust exact EDT API
(``temper_geometry.exact_edt_transform``) vs
``scipy.ndimage.distance_transform_edt``, the pre-migration oracle pinned
here per R19 (see ``docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md``
and ``docs/wave4-discipline-contract.md``).

Ground truth: ``docs/evidence/2026-08-07-exact-edt-rust-spike.md`` measured
bit-exact agreement between the Rust EDT and scipy across 7.4M+ cells on
every *reachable* input. The one documented divergence is the all-foreground
mask (no background cell anywhere): Rust returns +inf everywhere; scipy
returns a finite C-implementation boundary artifact.

The Python wrapper that used to own this call has been retired. Keep the
oracle and differential evidence anchored to the direct Rust API.
"""

from __future__ import annotations

import numpy as np
import temper_geometry as _tg


def _rust_edt_from_obstacle_mask(obstacle_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Call the production Rust API directly, preserving the old input shape."""
    interior = ~obstacle_mask
    h, w = interior.shape
    raw = _tg.exact_edt_transform(
        np.ascontiguousarray(interior, dtype=np.uint8).tobytes(), h, w
    )
    return np.frombuffer(raw, dtype="<f8").reshape(h, w), interior

# ---------------------------------------------------------------------------
# Oracle: the pre-migration scipy call, pinned verbatim (R19).
# ---------------------------------------------------------------------------


def _scipy_edt_from_obstacle_mask(obstacle_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pre-migration oracle: this is exactly what ``_edt_from_obstacle_mask``
    computed before the Rust EDT migration."""
    from scipy.ndimage import distance_transform_edt

    interior = ~obstacle_mask
    edt = distance_transform_edt(interior.astype(np.uint8))
    return edt, interior


def test_edt_from_obstacle_mask_matches_scipy_curated() -> None:
    """Curated masks (empty/no obstacles handled separately below since it
    is the degenerate all-foreground case; sparse, dense, non-square,
    boundary-touching obstacles): bit-exact agreement on interior + edt."""
    cases: list[np.ndarray] = []
    single = np.zeros((12, 9), dtype=bool)
    single[0, 0] = True
    cases.append(single)
    corner = np.zeros((8, 8), dtype=bool)
    corner[4, 4] = True
    cases.append(corner)
    for h, w in [(5, 5), (4, 60), (60, 4), (30, 30), (7, 23), (1, 9), (9, 1)]:
        rng = np.random.default_rng(hash((h, w)) & 0xFFFFFFFF)
        for density in (0.02, 0.1, 0.3, 0.5, 0.7, 0.95, 0.98):
            obstacle = rng.random((h, w)) < density
            obstacle[0, 0] = True  # guarantee >= 1 obstacle -> >= 1 background cell
            cases.append(obstacle)

    for obstacle in cases:
        got_edt, got_interior = _rust_edt_from_obstacle_mask(obstacle)
        want_edt, want_interior = _scipy_edt_from_obstacle_mask(obstacle)
        np.testing.assert_array_equal(got_interior, want_interior)
        assert np.array_equal(got_edt, want_edt), f"mismatch on shape {obstacle.shape}"


def test_edt_from_obstacle_mask_matches_scipy_random() -> None:
    """300 random trials, restricted to reachable (>= 1 obstacle) inputs:
    bit-exact agreement, mirroring the KTD8 spike's own random sweep."""
    rng = np.random.default_rng(42)
    for _ in range(300):
        h = int(rng.integers(2, 120))
        w = int(rng.integers(2, 120))
        density = rng.choice([0.02, 0.1, 0.3, 0.5, 0.7, 0.95, 0.98])
        obstacle = rng.random((h, w)) < density
        obstacle[0, 0] = True
        got_edt, _ = _rust_edt_from_obstacle_mask(obstacle)
        want_edt, _ = _scipy_edt_from_obstacle_mask(obstacle)
        assert np.array_equal(got_edt, want_edt), f"mismatch at shape ({h},{w}) density={density}"


# ---------------------------------------------------------------------------
# All-foreground reachability check (KTD8 spike section 4 divergence).
# ---------------------------------------------------------------------------


def test_open_grid_edt_is_all_foreground_case() -> None:
    """The spike claimed an all-foreground mask is unreachable by all three
    consumers "by construction". That does NOT hold here: an obstacle-free
    mask (``obstacle_mask`` all ``False``) makes ``interior`` all ``True``,
    which is exactly the degenerate all-foreground EDT input -- and this
    production grids can construct it directly with an obstacle-free mask.

    Verified explicitly here rather than trusted: Rust returns +inf
    everywhere; scipy returns a finite boundary artifact -- a real,
    reachable divergence in the raw EDT values. It does not change the
    final routability answer. The direct API differential intentionally
    compares the raw distance fields and documents this divergence.
    """
    obstacle_mask = np.zeros((50, 50), dtype=bool)
    edt, interior = _rust_edt_from_obstacle_mask(obstacle_mask)
    assert np.all(np.isinf(edt)), "Rust EDT must be +inf everywhere on an all-free mask"
    assert interior.all()

    want_edt, _ = _scipy_edt_from_obstacle_mask(obstacle_mask)
    assert np.all(np.isfinite(want_edt)), "scipy's boundary artifact is finite by construction"
    assert not np.array_equal(edt, want_edt), "the two genuinely diverge on this reachable input"
