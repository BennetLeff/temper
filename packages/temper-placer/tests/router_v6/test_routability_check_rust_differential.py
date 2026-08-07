"""Differential tests: ``routability_check._edt_from_obstacle_mask``'s
``_exact_edt`` (Rust Felzenszwalb-Huttenlocher sweep, via
``temper_geometry.exact_edt_transform``) vs
``scipy.ndimage.distance_transform_edt``, the pre-migration oracle pinned
here per R19 (see ``docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md``
and ``docs/wave4-discipline-contract.md``).

Ground truth: ``docs/evidence/2026-08-07-exact-edt-rust-spike.md`` measured
bit-exact agreement between the Rust EDT and scipy across 7.4M+ cells on
every *reachable* input. The one documented divergence is the all-foreground
mask (no background cell anywhere): Rust returns +inf everywhere; scipy
returns a finite C-implementation boundary artifact.

This module does NOT become scipy-free by this migration: it also calls
``scipy.ndimage.label`` in ``check_routability`` (a different function,
connected-component labeling, not addressed here).
"""

from __future__ import annotations

import random

import numpy as np

from temper_placer.router_v6.routability_check import (
    _edt_from_obstacle_mask,
    check_routability,
    check_routability_direct,
)

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
        got_edt, got_interior = _edt_from_obstacle_mask(obstacle)
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
        got_edt, _ = _edt_from_obstacle_mask(obstacle)
        want_edt, _ = _scipy_edt_from_obstacle_mask(obstacle)
        assert np.array_equal(got_edt, want_edt), f"mismatch at shape ({h},{w}) density={density}"


def test_check_routability_direct_matches_pre_migration_behavior() -> None:
    """End-to-end: ``check_routability_direct`` (real call site) gives the
    same True/False answer as an independent scipy-backed rebuild, across
    a mix of open, blocked, and randomly-obstructed grids."""
    rng = random.Random(20260807)
    for _ in range(60):
        w, h = rng.choice([(20, 20), (50, 50), (12, 30)])
        density = rng.uniform(0.0, 0.4)
        obstacle = np.asarray(
            [rng.random() < density for _ in range(h * w)], dtype=bool
        ).reshape(h, w)
        sx, sy = rng.randrange(w), rng.randrange(h)
        gx, gy = rng.randrange(w), rng.randrange(h)
        obstacle[sy, sx] = False
        obstacle[gy, gx] = False

        got = check_routability_direct(
            "net", (sx, sy), (gx, gy), obstacle, trace_width=0.1, cell_size=1.0
        )

        want_edt, want_mask = _scipy_edt_from_obstacle_mask(obstacle)
        want = check_routability(
            net_name="net",
            start=(sx, sy),
            goal=(gx, gy),
            edt_grid=want_edt,
            edt_mask=want_mask,
            trace_width=0.1,
            cell_size=1.0,
        )
        assert got == want, f"seed case (w={w},h={h},density={density}): rust={got} scipy={want}"


# ---------------------------------------------------------------------------
# All-foreground reachability check (KTD8 spike section 4 divergence).
# ---------------------------------------------------------------------------


def test_open_grid_is_reachable_all_foreground_case() -> None:
    """The spike claimed an all-foreground mask is unreachable by all three
    consumers "by construction". That does NOT hold here: an obstacle-free
    mask (``obstacle_mask`` all ``False``) makes ``interior`` all ``True``,
    which is exactly the degenerate all-foreground EDT input -- and this
    repo's own test suite constructs it directly:
    ``TestCheckRoutabilityDirect.test_open_grid`` in
    ``test_routability_check.py`` calls ``check_routability_direct`` with
    ``mask = np.zeros((50, 50), dtype=bool)``.

    Verified explicitly here rather than trusted: Rust returns +inf
    everywhere; scipy returns a finite boundary artifact -- a real,
    reachable divergence in the raw EDT values. It does not change the
    final routability answer: ``check_routability``'s
    ``passable_mask = (edt_mask > 0) & (edt_grid >= min_edt)`` treats
    ``+inf >= min_edt`` as True unconditionally, and scipy's finite
    artifact values (>= 1.0 for a 50x50 grid) are also comfortably above
    the tiny thresholds used in this module's tests -- so the two
    implementations agree on the boolean answer despite disagreeing on the
    raw distance field.
    """
    obstacle_mask = np.zeros((50, 50), dtype=bool)
    edt, interior = _edt_from_obstacle_mask(obstacle_mask)
    assert np.all(np.isinf(edt)), "Rust EDT must be +inf everywhere on an all-free mask"
    assert interior.all()

    want_edt, _ = _scipy_edt_from_obstacle_mask(obstacle_mask)
    assert np.all(np.isfinite(want_edt)), "scipy's boundary artifact is finite by construction"
    assert not np.array_equal(edt, want_edt), "the two genuinely diverge on this reachable input"

    # The actual production call site: both give the same True/False.
    got = check_routability_direct(
        "test", (5, 5), (45, 45), obstacle_mask, trace_width=0.1, cell_size=0.1
    )
    want = check_routability(
        net_name="test",
        start=(5, 5),
        goal=(45, 45),
        edt_grid=want_edt,
        edt_mask=interior,
        trace_width=0.1,
        cell_size=0.1,
    )
    assert got is True
    assert want is True
    assert got == want
