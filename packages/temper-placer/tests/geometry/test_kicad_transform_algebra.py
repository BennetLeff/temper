"""Exhaustive algebra suite for the sanctioned KiCad R(-theta) rotation
convention (``temper_placer.geometry.kicad_transform``).

This is R23 / plan 011's U1: the rotation convention is verified as an
*algebra* over the solver's finite angle set {0, 90, 180, 270}
(``temper_placer.geometry.ROTATION_ANGLES_DEG`` /
``temper-geometry/src/transform.rs``'s ``ROTATION_ANGLES_DEG``) -- every one
of the 16 composition pairs, every inverse round-trip, every one-hot
encoding round-trip -- replacing the spot coverage that let the R(+theta)
sign bug ship undetected twice (a sign flip is invisible on origin-symmetric
geometry at 90-degree multiples).

The algebraic oracle is the closed-form matrix law, not a second numerical
implementation: composition asserts ``R(-θ1)(R(-θ2)(p)) == R(-(θ1+θ2))(p)``
mod 360, inverse asserts ``R(θ)^T = R(-θ)``, and the convention anchors pin
the *sign* with pcbnew-verified expected values (``docs/evidence/
2026-07-29-cross-domain-creepage-rotation-convention.md`` and
``docs/evidence/2026-07-30-rotation-sign-remaining-sites.md``).

Mirror half of R23 -- non-applicable, not skipped
--------------------------------------------------
R23 names "rotation/mirror transform composition". No standalone mirror
transform kernel exists in ``temper_placer.geometry`` (grep-verified: no
mirror/flip transform in ``kicad_transform.py``, ``transform.py``, or the
geometry package's ``__init__``; bottom-side placement is side-tagged, not
mirror-transformed), and ``temper-geometry/src/transform.rs`` has none
either. The rotation half of R23 is exhaustive here; the mirror half is
recorded as a non-applicability note until a mirror kernel exists (plan
KTD5), rather than silently omitted.

Sign-flip discrimination -- what this suite can and cannot detect
-----------------------------------------------------------------
A sign flip (R(+theta) instead of R(-theta)) is caught by:

1. the convention anchors below at *asymmetric* offsets -- e.g. (2.0, -1.0)
   at 90 degrees: R(-90) gives (-1, -2), R(+90) gives (1, 2). The existing
   ground-truth anchors discriminate the same way (plan review,
   ``docs/evidence/2026-08-02-validation-portfolio-review.md``);
2. the composition law only on pairs whose angle sum is NOT in {0, 180} mod
   360. The identity R(-θ1)·R(-θ2) = R(+θ1)·R(+θ2) holds whenever
   θ1+θ2 ∈ {0, 180} mod 360 -- 8 of the 16 pairs over the finite set,
   including (90, 90) and (90, 270), cannot discriminate a sign flip. The
   falsifier tests below therefore assert discrimination ONLY on the 8
   non-masking pairs (sum ∉ {0, 180} mod 360) and pin the 8 masking pairs as
   non-discriminating, so the suite's coverage claim is precise rather than
   over-stated.
"""

from __future__ import annotations

import math
import random

import pytest

from temper_placer.geometry.kicad_transform import (
    rotate_local_to_world,
    rotate_local_to_world_deg,
    rotate_world_to_local,
)
from temper_placer.geometry.transform import (
    onehot_to_rotation_degrees,
    rotation_degrees_to_onehot,
)

# The solver's finite angle set (ROTATION_ANGLES_DEG in transform.rs; the
# only rotations the CP-SAT solver emits today).
FINITE_ANGLE_SET_DEG = (0.0, 90.0, 180.0, 270.0)

# Several offsets, deliberately including fully asymmetric ones (both
# coordinates nonzero) so the convention anchors and falsifier can
# discriminate a sign flip.
OFFSETS = ((0.5, 0.3), (2.0, -1.0), (5.0, 0.0), (3.7, -2.1), (-5.0, 5.0))

_EPS = 1e-9


def _closed_form_rotate(x: float, y: float, deg: float) -> tuple[float, float]:
    """The closed-form R(-theta) rotation at the finite angle set, with
    exact integer entries -- the algebraic oracle the implementation must
    satisfy. Not a second numerical implementation: this is the quadrant
    law ``(x, y) -> (y, -x)`` etc. that KiCad's R(-theta) convention
    implies, written out per angle with no trig.
    """
    d = deg % 360.0
    if d == 0.0:
        return (x, y)
    if d == 90.0:
        return (y, -x)
    if d == 180.0:
        return (-x, -y)
    if d == 270.0:
        return (-y, x)
    raise AssertionError(f"not a quadrant angle: {deg}")


def _r_plus(px: float, py: float, theta_rad: float) -> tuple[float, float]:
    """The flipped-convention reference: R(+theta) (standard-math CCW), the
    sign every pre-fix site computed.

    Deliberately reuses the sanctioned ``rotate_world_to_local`` -- the
    documented transpose of R(-theta), which for a rotation matrix is the
    inverse, i.e. exactly R(+theta) -- so the falsifier carries no
    independently-typed copy of the formula.
    """
    return rotate_world_to_local(px, py, theta_rad)


def _differs(a: tuple[float, float], b: tuple[float, float], tol: float = 1e-6) -> bool:
    """True when two points differ by more than ``tol`` in either
    coordinate. Used by the falsifier tests to prove discrimination: a
    genuine sign flip moves an asymmetric offset by O(1), many orders of
    magnitude above any float or pcbnew-nm noise."""
    return abs(a[0] - b[0]) > tol or abs(a[1] - b[1]) > tol


# =============================================================================
# 1. Composition closure -- all 16 pairs
# =============================================================================


@pytest.mark.parametrize("theta1_deg", FINITE_ANGLE_SET_DEG)
@pytest.mark.parametrize("theta2_deg", FINITE_ANGLE_SET_DEG)
def test_composition_matches_closed_form_for_all_pairs(theta1_deg, theta2_deg):
    """R(-θ1)(R(-θ2)(p)) == R(-(θ1+θ2 mod 360))(p) for every pair in the
    finite set and every offset: the composition law closes over the set.
    Fails on a composition error (wrong combined angle) or a dropped
    rotation.
    """
    for px, py in OFFSETS:
        composed = rotate_local_to_world(
            *rotate_local_to_world(px, py, math.radians(theta1_deg)),
            math.radians(theta2_deg),
        )
        expected = rotate_local_to_world(
            px, py, math.radians((theta1_deg + theta2_deg) % 360.0)
        )
        assert composed[0] == pytest.approx(expected[0], abs=_EPS), (
            theta1_deg,
            theta2_deg,
            (px, py),
        )
        assert composed[1] == pytest.approx(expected[1], abs=_EPS), (
            theta1_deg,
            theta2_deg,
            (px, py),
        )


# =============================================================================
# 2. Inverse round-trip -- all 4 angles
# =============================================================================


@pytest.mark.parametrize("theta_deg", FINITE_ANGLE_SET_DEG)
def test_world_to_local_inverts_local_to_world(theta_deg):
    """rotate_world_to_local(rotate_local_to_world(p, θ), θ) == p for every
    angle in the finite set. At 90-degree multiples the closed-form integer
    entries make the round-trip exact to float noise (asserted at 1e-9,
    the repo's closed-form-at-multiples discipline).
    """
    for px, py in OFFSETS:
        wx, wy = rotate_local_to_world(px, py, math.radians(theta_deg))
        lx, ly = rotate_world_to_local(wx, wy, math.radians(theta_deg))
        assert lx == pytest.approx(px, abs=_EPS), (theta_deg, (px, py))
        assert ly == pytest.approx(py, abs=_EPS), (theta_deg, (px, py))


# =============================================================================
# 3. Convention anchors -- every angle, several offsets (incl. asymmetric)
# =============================================================================


@pytest.mark.parametrize("theta_deg", FINITE_ANGLE_SET_DEG)
@pytest.mark.parametrize("offset", OFFSETS)
def test_convention_anchor_matches_closed_form(theta_deg, offset):
    """The convention-anchored expected value at every angle of the finite
    set for several offsets, including fully asymmetric ones. The expected
    value is the closed-form quadrant law (integer entries at 90-multiples)
    -- a sign flip produces the *opposite* quadrant result and fails here
    (e.g. (2.0, -1.0) at 90 degrees: R(-90) -> (-1, -2), R(+90) -> (1, 2)).
    """
    px, py = offset
    ex, ey = _closed_form_rotate(px, py, theta_deg)
    rx, ry = rotate_local_to_world_deg(px, py, theta_deg)
    assert rx == pytest.approx(ex, abs=_EPS), (theta_deg, offset)
    assert ry == pytest.approx(ey, abs=_EPS), (theta_deg, offset)


def test_convention_anchor_at_non_quadrant_angle_captured_from_pcbnew():
    """Dependency-free non-90-degree anchor: the (0.5, 0.3) offset at 37
    degrees, captured from a real ``pcbnew`` run while building
    ``docs/evidence/2026-07-30-rotation-sign-remaining-sites.md``
    (Sec. 3): pcbnew placed the offset at (0.579862, -0.061317). The
    R(+theta) answer for the same input is (0.218773, 0.540498) -- if this
    ever starts asserting that instead, the sign flipped back. Needs no
    pcbnew at test time (the number is already captured); the live-oracle
    version lives in ``test_transform_algebra_pcbnew_oracle.py``.
    """
    x, y = rotate_local_to_world(0.5, 0.3, math.radians(37.0))
    assert x == pytest.approx(0.579862, abs=1e-5)
    assert y == pytest.approx(-0.061317, abs=1e-5)


# =============================================================================
# 4. One-hot encoding round-trip -- all 4 angles
# =============================================================================


@pytest.mark.parametrize("theta_deg", FINITE_ANGLE_SET_DEG)
def test_onehot_round_trip_is_identity_on_finite_set(theta_deg):
    """degree -> one-hot -> degree is the identity on the finite set, and
    each encoding is a genuine one-hot (exactly one 1.0). Exercises the
    solver's rotation-encoding surface (``rotation_degrees_to_onehot`` /
    ``onehot_to_rotation_degrees``, Rust-backed via ``temper_geometry``).
    """
    onehot = rotation_degrees_to_onehot(theta_deg)
    assert sum(onehot) == pytest.approx(1.0, abs=1e-15)
    assert len([v for v in onehot if v == 1.0]) == 1, onehot
    deg_back = onehot_to_rotation_degrees(onehot)
    assert deg_back == pytest.approx(theta_deg, abs=1e-9)


# =============================================================================
# 5. Property tests -- random non-multiple angles
# =============================================================================


@pytest.mark.parametrize("seed", range(25))
def test_property_composition_and_inverse_laws_at_random_angles(seed):
    """The general (arbitrary-angle) composition and inverse laws hold
    within epsilon, so the exhaustive 90-multiple enumeration is a special
    case of a claim that extends to any angle the solver might one day emit.
    """
    rng = random.Random(seed * 104729 + 7)
    theta1_deg = rng.uniform(0.0, 360.0)
    theta2_deg = rng.uniform(0.0, 360.0)
    px, py = rng.uniform(-10.0, 10.0), rng.uniform(-10.0, 10.0)

    composed = rotate_local_to_world(
        *rotate_local_to_world(px, py, math.radians(theta1_deg)),
        math.radians(theta2_deg),
    )
    expected = rotate_local_to_world(px, py, math.radians((theta1_deg + theta2_deg) % 360.0))
    assert composed[0] == pytest.approx(expected[0], abs=_EPS)
    assert composed[1] == pytest.approx(expected[1], abs=_EPS)

    wx, wy = rotate_local_to_world(px, py, math.radians(theta1_deg))
    lx, ly = rotate_world_to_local(wx, wy, math.radians(theta1_deg))
    assert lx == pytest.approx(px, abs=_EPS)
    assert ly == pytest.approx(py, abs=_EPS)


# =============================================================================
# 6. Falsifier -- convention flip (R(+theta)) must fail this suite
# =============================================================================

# Composition discriminates a sign flip only when the angle sum is NOT in
# {0, 180} mod 360 (R(-θ1)·R(-θ2) ≡ R(+θ1)·R(+θ2) otherwise -- 8 of 16
# pairs, including (90, 270) and (90, 90), cannot discriminate). This is
# the plan-review correction
# (docs/evidence/2026-08-02-validation-portfolio-review.md): the falsifier
# is anchored on non-masking pairs and on convention anchors at asymmetric
# offsets, never on the masking pairs.
NON_MASKING_PAIRS = [
    (t1, t2)
    for t1 in FINITE_ANGLE_SET_DEG
    for t2 in FINITE_ANGLE_SET_DEG
    if ((t1 + t2) % 360.0) not in (0.0, 180.0)
]
MASKING_PAIRS = [
    (t1, t2)
    for t1 in FINITE_ANGLE_SET_DEG
    for t2 in FINITE_ANGLE_SET_DEG
    if ((t1 + t2) % 360.0) in (0.0, 180.0)
]

# Offsets with BOTH coordinates nonzero: at 90/270 these discriminate a
# sign flip at every finite-set angle where the conventions differ (0 and
# 180 are intrinsically non-discriminating for any offset: R(-0)=R(+0)=I
# and R(-180)=R(+180)=-I).
_ASYMMETRIC_OFFSETS = ((0.5, 0.3), (2.0, -1.0), (3.7, -2.1), (-5.0, 5.0))


@pytest.mark.parametrize("theta_deg", [90.0, 270.0])
@pytest.mark.parametrize("offset", _ASYMMETRIC_OFFSETS)
def test_falsifier_convention_anchor_discriminates_sign_flip(theta_deg, offset):
    """Proves the convention anchors used above actually discriminate: at
    90 and 270 degrees the implementation's R(-theta) output must differ
    from the flipped R(+theta) reference by O(1). If the implementation
    were reverted to R(+theta), this (and the anchor tests in section 3)
    fail immediately.
    """
    px, py = offset
    got = rotate_local_to_world_deg(px, py, theta_deg)
    flipped = _r_plus(px, py, math.radians(theta_deg))
    assert _differs(got, flipped), (theta_deg, offset, got, flipped)


@pytest.mark.parametrize(("theta1_deg", "theta2_deg"), NON_MASKING_PAIRS)
@pytest.mark.parametrize("offset", _ASYMMETRIC_OFFSETS)
def test_falsifier_composition_discriminates_sign_flip_only_on_non_masking_pairs(
    theta1_deg, theta2_deg, offset
):
    """For every NON-masking pair (sum ∉ {0, 180} mod 360) the composed
    R(-θ1)(R(-θ2)(p)) must differ from the flipped R(+(θ1+θ2))(p). Under a
    sign flip the composition equals the flipped reference and fails here.
    """
    px, py = offset
    composed = rotate_local_to_world(
        *rotate_local_to_world(px, py, math.radians(theta1_deg)),
        math.radians(theta2_deg),
    )
    flipped = _r_plus(px, py, math.radians((theta1_deg + theta2_deg) % 360.0))
    assert _differs(composed, flipped), (theta1_deg, theta2_deg, offset, composed, flipped)


@pytest.mark.parametrize(("theta1_deg", "theta2_deg"), MASKING_PAIRS)
@pytest.mark.parametrize("offset", _ASYMMETRIC_OFFSETS)
def test_masking_pairs_do_not_discriminate_sign_flip(theta1_deg, theta2_deg, offset):
    """Pins the masking property so the suite's coverage claim stays
    precise: for the 8 pairs with sum ∈ {0, 180} mod 360 (including (90,
    90) and (90, 270)), R(-θ1)·R(-θ2) coincides with R(+(θ1+θ2)) -- the
    composed result equals the flipped reference within float noise. These
    pairs cannot discriminate a sign flip; the falsifier never relies on
    them (this is why the anchors at asymmetric offsets and the non-masking
    pairs above are load-bearing).
    """
    px, py = offset
    composed = rotate_local_to_world(
        *rotate_local_to_world(px, py, math.radians(theta1_deg)),
        math.radians(theta2_deg),
    )
    flipped = _r_plus(px, py, math.radians((theta1_deg + theta2_deg) % 360.0))
    assert composed[0] == pytest.approx(flipped[0], abs=_EPS), (theta1_deg, theta2_deg, offset)
    assert composed[1] == pytest.approx(flipped[1], abs=_EPS), (theta1_deg, theta2_deg, offset)
