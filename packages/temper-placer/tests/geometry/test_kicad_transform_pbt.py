"""Property-based tests for the Rust ``kicad_transform`` kernels
(``temper_placer.geometry.kicad_transform``, a shim over
``temper_geometry.kicad_*_py`` — see
``packages/temper-geometry/src/kicad_transform.rs``).

Six non-vacuous properties over the shim's public API (all through the
shipped delegation, i.e. through the Rust kernels):

- P1  quadrant anchor: R(-theta) matches the closed-form quadrant law at
      {0, 90, 180, 270} degrees — a sign flip violates it at 90/270
- P2  ``place_local_to_world`` is exactly rotate-then-translate (bit-exact)
- P3  ``rotate_world_to_local`` is the exact inverse of
      ``rotate_local_to_world`` (tight tolerance; trig round-trip)
- P4  composition closure over the finite angle set: R(-θ1)·R(-θ2) == the
      closed-form quadrant law at (θ1+θ2) mod 360 (tight tolerance;
      anchored to the exact-integer law so a sign flip falsifies it)
- P5  degree wrappers equal the radians path (bit-exact) for both
      transforms
- P6  isometry: rotation preserves the squared Euclidean norm (tight
      tolerance)

Reachability: every property calls the shim functions, which resolve
``temper_geometry.kicad_*_py`` at call time, so a mutated kernel attribute
reaches the property (see the G4 "reachability must be measured" note —
the vacuity guards below prove each kernel's behavior is observable by its
property, because swapping in a degenerate kernel changes the outcome).

Non-vacuity: every property has a mutation test at the bottom proving a
mutated kernel violates it — none of the properties is satisfied by a
degenerate implementation.

Metamorphic relations (G5, >= 3), exactness claims stated per relation:
- MR1 zero-angle identity (bit-exact for nonzero x AND y)
- MR2 odd symmetry of ``shapely_rotation_angle_deg`` (bit-exact)
- MR3 rotation preserves pairwise distance between two offsets (tight
      tolerance)
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import temper_geometry as _tg
from temper_placer.geometry.kicad_transform import (
    place_local_to_world,
    rotate_local_to_world,
    rotate_local_to_world_deg,
    rotate_world_to_local,
    rotate_world_to_local_deg,
    shapely_rotation_angle_deg,
)

_FINITE_ANGLE_DEG = (0.0, 90.0, 180.0, 270.0)

# Closed-form quadrant law R(-theta): 0 -> (x, y), 90 -> (y, -x),
# 180 -> (-x, -y), 270 -> (-y, x). A sign flip (R(+theta): 90 -> (-y, x),
# 270 -> (y, -x)) violates it at 90/270 on asymmetric offsets.
_QUADRANT_LAW = {
    0.0: lambda x, y: (x, y),
    90.0: lambda x, y: (y, -x),
    180.0: lambda x, y: (-x, -y),
    270.0: lambda x, y: (-y, x),
}

_ST_FLOAT = st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False)
_ST_THETA = st.floats(min_value=-4 * math.pi, max_value=4 * math.pi, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# P1 — quadrant anchor
# ---------------------------------------------------------------------------


@given(_ST_FLOAT, _ST_FLOAT)
@settings(max_examples=50, deadline=20000)
def test_p1_quadrant_anchor_matches_closed_form(x: float, y: float) -> None:
    for angle_deg, transform in _QUADRANT_LAW.items():
        rx, ry = rotate_local_to_world_deg(x, y, angle_deg)
        ex, ey = transform(x, y)
        assert rx == pytest.approx(ex, abs=1e-9), f"angle {angle_deg} offset ({x}, {y})"
        assert ry == pytest.approx(ey, abs=1e-9), f"angle {angle_deg} offset ({x}, {y})"


# ---------------------------------------------------------------------------
# P2 — place_local_to_world is exactly rotate-then-translate
# ---------------------------------------------------------------------------


@given(_ST_FLOAT, _ST_FLOAT, _ST_FLOAT, _ST_FLOAT, _ST_THETA)
@settings(max_examples=50, deadline=20000)
def test_p2_place_is_rotate_then_translate(x, y, ox, oy, theta_rad) -> None:
    rx, ry = rotate_local_to_world(x, y, theta_rad)
    got = place_local_to_world(x, y, ox, oy, theta_rad)
    # Bit-exact: place_local_to_world composes the SAME intermediate
    # (rx, ry) that rotate_local_to_world returns, then adds the origin —
    # both sides compute the identical two operations.
    assert got[0].hex() == (ox + rx).hex(), f"({x}, {y}, {ox}, {oy}, {theta_rad})"
    assert got[1].hex() == (oy + ry).hex(), f"({x}, {y}, {ox}, {oy}, {theta_rad})"


# ---------------------------------------------------------------------------
# P3 — world-to-local is the inverse of local-to-world
# ---------------------------------------------------------------------------


@given(_ST_FLOAT, _ST_FLOAT, _ST_THETA)
@settings(max_examples=50, deadline=20000)
def test_p3_world_to_local_inverse_round_trip(x, y, theta_rad) -> None:
    wx, wy = rotate_local_to_world(x, y, theta_rad)
    lx, ly = rotate_world_to_local(wx, wy, theta_rad)
    assert lx == pytest.approx(x, abs=1e-9), f"({x}, {y}, {theta_rad})"
    assert ly == pytest.approx(y, abs=1e-9), f"({x}, {y}, {theta_rad})"


# ---------------------------------------------------------------------------
# P4 — composition closure over the finite angle set
# ---------------------------------------------------------------------------


@given(_ST_FLOAT, _ST_FLOAT)
@settings(max_examples=50, deadline=20000)
def test_p4_composition_closure_anchored_to_quadrant_law(x, y) -> None:
    """Composing two finite-set rotations R(-θ1)·R(-θ2) equals the closed-form
    quadrant law at (θ1+θ2) mod 360 — the law is the exact-integer oracle
    (NOT the sign-agnostic self-composition form: a sign-flipped R(+θ)
    kernel satisfies R(+θ1)·R(+θ2) == R(+(θ1+θ2)) and would pass an
    unanchored comparison, so the anchor is what makes this property able to
    detect the convention's sign)."""
    for t1_deg in _FINITE_ANGLE_DEG:
        for t2_deg in _FINITE_ANGLE_DEG:
            rx, ry = rotate_local_to_world(x, y, math.radians(t1_deg))
            cx, cy = rotate_local_to_world(rx, ry, math.radians(t2_deg))
            ex, ey = _QUADRANT_LAW[(t1_deg + t2_deg) % 360.0](x, y)
            assert cx == pytest.approx(ex, abs=1e-9), f"({x}, {y}, {t1_deg}, {t2_deg})"
            assert cy == pytest.approx(ey, abs=1e-9), f"({x}, {y}, {t1_deg}, {t2_deg})"


# ---------------------------------------------------------------------------
# P5 — degree wrappers are bit-exact with the radians path
# ---------------------------------------------------------------------------


@given(_ST_FLOAT, _ST_FLOAT, st.floats(min_value=-720.0, max_value=720.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=50, deadline=20000)
def test_p5_degree_wrappers_match_radians_path(x, y, theta_deg) -> None:
    got = rotate_local_to_world_deg(x, y, theta_deg)
    expected = rotate_local_to_world(x, y, math.radians(theta_deg))
    assert got[0].hex() == expected[0].hex(), f"rl2wd ({x}, {y}, {theta_deg})"
    assert got[1].hex() == expected[1].hex(), f"rl2wd ({x}, {y}, {theta_deg})"
    got = rotate_world_to_local_deg(x, y, theta_deg)
    expected = rotate_world_to_local(x, y, math.radians(theta_deg))
    assert got[0].hex() == expected[0].hex(), f"rw2ld ({x}, {y}, {theta_deg})"
    assert got[1].hex() == expected[1].hex(), f"rw2ld ({x}, {y}, {theta_deg})"
    assert shapely_rotation_angle_deg(theta_deg).hex() == (-theta_deg).hex()


# ---------------------------------------------------------------------------
# P6 — isometry: rotation preserves the squared Euclidean norm
# ---------------------------------------------------------------------------


@given(_ST_FLOAT, _ST_FLOAT, _ST_THETA)
@settings(max_examples=50, deadline=20000)
def test_p6_isometry_preserves_squared_norm(x, y, theta_rad) -> None:
    rx, ry = rotate_local_to_world(x, y, theta_rad)
    before = x * x + y * y
    after = rx * rx + ry * ry
    assert after == pytest.approx(before, abs=1e-9), f"({x}, {y}, {theta_rad})"


# ---------------------------------------------------------------------------
# Mutated kernels for the vacuity guards (each replaces one
# temper_geometry.kicad_*_py attribute; the shim resolves those attributes
# at call time, so the mutation reaches the property).
# ---------------------------------------------------------------------------


def _mutant_rplus_deg(x, y, theta_deg):
    """R(+theta) instead of R(-theta) — the pre-fix sign this whole module
    exists to prevent."""
    c, s = math.cos(math.radians(theta_deg)), math.sin(math.radians(theta_deg))
    return (x * c - y * s, x * s + y * c)


def _mutant_rplus_rad(x, y, theta_rad):
    """R(+theta) instead of R(-theta), radians form (falsifies P4's
    composition closure on the non-masking pairs)."""
    c, s = math.cos(theta_rad), math.sin(theta_rad)
    return (x * c - y * s, x * s + y * c)


def _mutant_place_drops_origin(local_x, local_y, origin_x, origin_y, theta_rad):
    """Correct R(-theta), but no origin translation."""
    c, s = math.cos(theta_rad), math.sin(theta_rad)
    rx = local_x * c + local_y * s
    ry = -local_x * s + local_y * c
    return (rx, ry)


def _mutant_forward_as_inverse(x, y, theta_rad):
    """Re-applies R(-theta) where the real inverse needs R(+theta)."""
    c, s = math.cos(theta_rad), math.sin(theta_rad)
    return (x * c + y * s, -x * s + y * c)


def _mutant_deg_is_radians(x, y, theta_deg):
    """Correct R(-theta) formula, but treats the degree value as radians."""
    c, s = math.cos(theta_deg), math.sin(theta_deg)
    return (x * c + y * s, -x * s + y * c)


def _mutant_scales(x, y, theta_rad):
    """Correct R(-theta), then scales the result by 2."""
    c, s = math.cos(theta_rad), math.sin(theta_rad)
    rx = x * c + y * s
    ry = -x * s + y * c
    return (2.0 * rx, 2.0 * ry)


_MUTABLE_ATTRS = (
    "kicad_rotate_local_to_world_py",
    "kicad_rotate_local_to_world_deg_py",
    "kicad_rotate_world_to_local_py",
    "kicad_rotate_world_to_local_deg_py",
    "kicad_place_local_to_world_py",
    "kicad_shapely_rotation_angle_deg_py",
)


@pytest.fixture
def _restore_kernels():
    originals = {attr: getattr(_tg, attr) for attr in _MUTABLE_ATTRS}
    yield
    for attr, value in originals.items():
        setattr(_tg, attr, value)


# ---------------------------------------------------------------------------
# Non-vacuity: each property fails against a mutated (degenerate) kernel
# ---------------------------------------------------------------------------


def test_p1_fails_for_sign_flip(_restore_kernels) -> None:
    """A kernel implementing R(+theta) violates the quadrant anchor at 90/270
    on asymmetric offsets: (2, -1) at 90° -> R(-90)(1, 2)-vs-R(+90)(-1, -2)."""
    _tg.kicad_rotate_local_to_world_deg_py = _mutant_rplus_deg
    with pytest.raises(AssertionError):
        test_p1_quadrant_anchor_matches_closed_form.hypothesis.inner_test(2.0, -1.0)


def test_p2_fails_for_origin_dropping_place(_restore_kernels) -> None:
    """A place kernel that ignores the origin fails the exact decomposition."""
    _tg.kicad_place_local_to_world_py = _mutant_place_drops_origin
    with pytest.raises(AssertionError):
        test_p2_place_is_rotate_then_translate.hypothesis.inner_test(2.0, -1.0, 100.0, 200.0, 0.7)


def test_p3_fails_for_same_sign_inverse(_restore_kernels) -> None:
    """A 'world_to_local' that re-applies R(-theta) instead of R(+theta)
    fails the round trip by O(1): (1, 0) at 90° -> forward (0, -1), then
    same-sign -> (-1, 0), not (1, 0)."""
    _tg.kicad_rotate_world_to_local_py = _mutant_forward_as_inverse
    with pytest.raises(AssertionError):
        test_p3_world_to_local_inverse_round_trip.hypothesis.inner_test(1.0, 0.0, math.pi / 2)


def test_p4_fails_for_sign_flip_composition(_restore_kernels) -> None:
    """An R(+theta) kernel violates the quadrant-anchored composition closure
    on the 8 non-masking pairs (θ1+θ2 ∉ {0, 180} mod 360) of the finite
    angle set: the composed R(+θ1)·R(+θ2) result differs by O(1) from the
    anchored R(-(θ1+θ2)) quadrant law there. (The 8 masking pairs —
    including (90, 270) and (90, 90) — coincide with the flipped reference,
    which is why a composition-based sign-flip detector never relies on
    them.)"""
    _tg.kicad_rotate_local_to_world_py = _mutant_rplus_rad
    with pytest.raises(AssertionError):
        test_p4_composition_closure_anchored_to_quadrant_law.hypothesis.inner_test(1.0, 0.0)


def test_p5_fails_for_degrees_treated_as_radians(_restore_kernels) -> None:
    """A degree wrapper that forwards degrees as radians breaks the bit-exact
    equality with the radians path."""
    _tg.kicad_rotate_local_to_world_deg_py = _mutant_deg_is_radians
    _tg.kicad_rotate_world_to_local_deg_py = _mutant_deg_is_radians
    with pytest.raises(AssertionError):
        test_p5_degree_wrappers_match_radians_path.hypothesis.inner_test(1.5, -3.25, 90.0)


def test_p6_fails_for_scaling_kernel(_restore_kernels) -> None:
    """A kernel that scales by 2 changes the squared norm by 4x, violating
    isometry."""
    _tg.kicad_rotate_local_to_world_py = _mutant_scales
    with pytest.raises(AssertionError):
        test_p6_isometry_preserves_squared_norm.hypothesis.inner_test(3.0, 4.0, 0.7)


# sanity: the kernels are genuinely rotation-sensitive (not trivially
# satisfied) — the sign-flip mutant changes real output
def test_p1_fixture_is_rotation_asymmetric() -> None:
    rx, ry = rotate_local_to_world_deg(2.0, -1.0, 90.0)
    assert rx == pytest.approx(-1.0, abs=1e-9)
    assert ry == pytest.approx(-2.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Metamorphic relations (G5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("x", "y"),
    [
        (1.0, -2.0),
        (0.3, 7.25),
        (-5.0, 5.0),
        (12.5, -7.25),
        (3.7, -2.1),
        (-50.0, 50.0),
    ],
)
def test_mr1_zero_angle_is_exact_identity(x, y):
    """Zero-angle rotation is the identity, bit-exact.

    Claim bounded to NONZERO x and y: at theta == 0.0, ``sin(theta)`` is
    ``-0.0`` when theta is ``-0.0`` and ``+0.0`` when theta is ``0.0``, so
    a coordinate that is exactly zero (or whose partner's ``-x*s``/``y*s``
    term carries a signed zero) can have its zero sign flipped by the
    ``+ (signed zero)`` addition — exactly as the pre-migration module did
    (the differential pins shim == oracle on those inputs bit-for-bit).
    For nonzero coordinates the ``y*s`` / ``-x*s`` terms are ``±0.0`` and
    ``x + ±0.0 == x`` exactly, so the identity is bit-for-bit.
    """
    got = rotate_local_to_world(x, y, 0.0)
    assert got[0].hex() == x.hex()
    assert got[1].hex() == y.hex()
    got = rotate_world_to_local(x, y, 0.0)
    assert got[0].hex() == x.hex()
    assert got[1].hex() == y.hex()


@pytest.mark.parametrize("theta_deg", [-720.0, -90.0, -0.0, 0.0, 0.1, 45.0, 360.0])
def test_mr2_shapely_angle_is_odd(theta_deg):
    """``shapely_rotation_angle_deg`` is an odd function: negating the input
    negates the output, bit-exactly (IEEE negation)."""
    assert shapely_rotation_angle_deg(theta_deg).hex() == (-shapely_rotation_angle_deg(-theta_deg)).hex()
    assert shapely_rotation_angle_deg(theta_deg).hex() == (-theta_deg).hex()


@pytest.mark.parametrize("seed", range(20))
def test_mr3_rotation_preserves_pairwise_distance(seed):
    """Rotating two offsets by the SAME angle preserves the distance between
    them (an isometry). Tight tolerance: rotation preserves distance in
    exact arithmetic; the trig evaluation leaves only a ~1e-12 relative
    error, and both offsets share the same cos/sin so the error is
    correlated — measured well within 1e-9 for board-scale coordinates."""
    import random

    rng = random.Random(seed * 63337 + 5)
    x1, y1 = rng.uniform(-100, 100), rng.uniform(-100, 100)
    x2, y2 = rng.uniform(-100, 100), rng.uniform(-100, 100)
    theta = rng.uniform(-4 * math.pi, 4 * math.pi)
    dx, dy = x1 - x2, y1 - y2
    before = math.sqrt(dx * dx + dy * dy)
    r1 = rotate_local_to_world(x1, y1, theta)
    r2 = rotate_local_to_world(x2, y2, theta)
    after = math.sqrt((r1[0] - r2[0]) ** 2 + (r1[1] - r2[1]) ** 2)
    assert after == pytest.approx(before, abs=1e-9), f"seed {seed}"
