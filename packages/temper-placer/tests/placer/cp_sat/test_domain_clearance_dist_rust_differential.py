"""Differential tests: the R24 domain-clearance audit's distance
recompute in Rust (``temper_geometry.dist_py``, Wave 3 #4) vs
``math.dist`` — the pre-migration oracle used by
``domain_clearance.py::audit_domain_clearance``.

The audit recomputes the real Euclidean center-to-center distance of
every generated ``domain_clearance_*`` constraint from the *solved*
placement coordinates (R24 item 3 — "does not trust the solver's own
bookkeeping").  ``math.dist(p, q)`` is CPython's Dekker double-double
compensated ``vector_norm`` over the per-coordinate differences — the
same algorithm ``temper-geometry``'s ``py_hypot`` replicates exactly
(pad_geometry.rs), so ``dist_py(ax, ay, bx, by)`` delegates to it with
the differences computed first, mirroring ``math.dist``'s
``vec[i] = p[i] - q[i]``.

The direct ``temper_geometry`` pin fails first (the function does not
exist yet); the module-level pin exercises the full delegation path
once wired.
"""

from __future__ import annotations

import math
import random

import temper_geometry as _tg


def _oracle_dist(ax, ay, bx, by):
    return math.dist((ax, ay), (bx, by))


def test_dist_rust_direct_pin():
    """Direct Rust pin — fails before the crate exposes dist_py."""
    rng = random.Random(20260731)
    for _ in range(500):
        ax, ay = rng.uniform(-200.0, 200.0), rng.uniform(-200.0, 200.0)
        bx, by = rng.uniform(-200.0, 200.0), rng.uniform(-200.0, 200.0)
        assert _tg.dist_py(ax, ay, bx, by) == _oracle_dist(ax, ay, bx, by)


def test_dist_wide_magnitude_span():
    """Mixed magnitudes stress the scaling path of vector_norm."""
    rng = random.Random(42)
    for _ in range(300):
        ax, ay = rng.uniform(-1e6, 1e6), rng.uniform(-1e-3, 1e-3)
        bx, by = rng.uniform(-1e6, 1e6), rng.uniform(-1e-3, 1e-3)
        assert _tg.dist_py(ax, ay, bx, by) == _oracle_dist(ax, ay, bx, by)


def test_dist_known_points():
    assert _tg.dist_py(0.0, 0.0, 3.0, 4.0) == 5.0
    assert _tg.dist_py(0.0, 0.0, 0.0, 0.0) == 0.0
    assert _tg.dist_py(1.0, 2.0, 1.0, 2.0) == 0.0
    assert _tg.dist_py(0.0, 0.0, 1.0, 0.0) == 1.0
    # 3-4-5 scaled to the integer grid: dist(0,0 -> 3000,4000) == 5000 exactly.
    assert _tg.dist_py(0.0, 0.0, 3000.0, 4000.0) == 5000.0


def test_dist_matches_module_level_audit_path():
    """Full delegation path: audit_domain_clearance on a solved pair."""
    from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
    from temper_placer.placer.cp_sat.domain_clearance import audit_domain_clearance

    c = SeparatedConstraint(
        a="A",
        b="B",
        min_distance_mm=4.0,
        tier=ConstraintTier.HARD,
        because="test separation constraint",
        id="domain_clearance_A_B",
    )
    violations = audit_domain_clearance(
        [c],
        {"A": (0.0, 0.0), "B": (3.0, 4.0)},
    )
    # Real distance 5.0 >= 4.0: no violation.
    assert violations == []
    violations = audit_domain_clearance(
        [c],
        {"A": (0.0, 0.0), "B": (1.0, 1.0)},
    )
    assert len(violations) == 1
    assert violations[0].actual_mm == math.sqrt(2.0)


def test_dist_edge_scale_and_axis_alignment():
    # Axis-aligned (one diff zero): exactly the nonzero diff.
    assert _tg.dist_py(-1e6, 0.0, 1e6, 0.0) == 2e6
    assert _oracle_dist(-1e6, 0.0, 1e6, 0.0) == 2e6
    # Tiny-but-representable separation is not flushed to zero.
    tiny = 1e-12
    assert _tg.dist_py(0.0, 0.0, tiny, tiny) == _oracle_dist(0.0, 0.0, tiny, tiny)
    assert _tg.dist_py(0.0, 0.0, tiny, tiny) > 0.0
    # One subnormal-scale component with a normal other component.
    sub = 1e-310
    assert _tg.dist_py(0.0, 0.0, 1.0, sub) == _oracle_dist(0.0, 0.0, 1.0, sub)
    assert _tg.dist_py(0.0, 0.0, 1.0, sub) == 1.0


def test_dist_non_finite_parity():
    """math.dist semantics: any NaN diff -> NaN; inf - finite -> inf;
    inf - inf -> NaN (the coincident-inf pair is NaN, not inf)."""
    nan = float("nan")
    assert math.isnan(_tg.dist_py(nan, 0.0, 0.0, 0.0))
    assert math.isnan(_oracle_dist(nan, 0.0, 0.0, 0.0))
    assert math.isnan(_tg.dist_py(0.0, nan, 0.0, 0.0))
    assert _tg.dist_py(float("inf"), 0.0, 0.0, 0.0) == float("inf")
    assert _oracle_dist(float("inf"), 0.0, 0.0, 0.0) == float("inf")
    assert math.isnan(_tg.dist_py(float("inf"), 0.0, float("inf"), 0.0))
    assert math.isnan(_oracle_dist(float("inf"), 0.0, float("inf"), 0.0))
