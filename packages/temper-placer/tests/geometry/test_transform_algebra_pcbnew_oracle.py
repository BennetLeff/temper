"""Non-90-degree pcbnew-oracle cross-check for the KiCad R(-theta) rotation
convention algebra (plan 011, U3; R23).

Why a real-KiCad oracle at a NON-90-degree angle
--------------------------------------------------
The exhaustive 90-multiple algebra in ``test_kicad_transform_algebra.py``
cannot, by itself, distinguish R(+theta) from R(-theta): at 0/180 the two
conventions coincide exactly, and at 90/270 they differ only in which of
X/Y gets negated -- so on origin-symmetric geometry the wrong sign ships
undetected (the quadrant-invariance masking the second sweep documented,
``docs/evidence/2026-07-30-rotation-sign-remaining-sites.md``). Only an
anchor against KiCad's own placement engine (``pcbnew``, not a
reimplementation of its rotation formula) at an angle that is not a
multiple of 90 can pin the *sign* of the general convention claim.

This file reuses the exact oracle plumbing built and battle-tested for
``test_rotation_convention_oracle.py`` /
``test_rotation_convention_remaining_sites_oracle.py``
(``_pcbnew_oracle_batch`` / ``_pcbnew_python_or_skip`` /
``_ORACLE_TOLERANCE_MM``) -- reused, not reimplemented.

SKIPPED-with-cause, never PASS-when-absent
------------------------------------------
When no interpreter with ``pcbnew`` bindings is available
(``_pcbnew_python_or_skip``), the tests below skip loudly with the reason;
they can never report PASS without the oracle. This matches the plan's
degradation rule (U3 approach item 4 / test scenario 5).
"""

from __future__ import annotations

import math

import pytest

from temper_placer.geometry.kicad_transform import (
    place_local_to_world,
    rotate_local_to_world,
    rotate_world_to_local,
)

# Reused, not reimplemented -- the same pcbnew-oracle batch plumbing the
# rotation-convention oracle tests already built and battle-tested.
from tests.requirements.safety.test_rotation_convention_oracle import (
    _ORACLE_TOLERANCE_MM,
    _pcbnew_oracle_batch,
    _pcbnew_python_or_skip,
)

# Non-90-degree angles used throughout -- deliberately never a multiple of
# 90 (see this module's docstring for why that matters).
_ANGLE_37 = 37.0
_ANGLE_45 = 45.0
# The local offset and board origin from the remaining-sites evidence doc
# (Sec. 3): pcbnew places (0.5, 0.3) at 37 deg about (0,0) at
# (0.579862, -0.061317); R(+theta) for the same input is (0.218773,
# 0.540498).
_DX, _DY = 0.5, 0.3
_ORIGIN_X, _ORIGIN_Y = 12.0, -4.0


def _oracle_world_point(dx: float, dy: float, angle_deg: float) -> tuple[float, float]:
    """A local offset rotated by ``angle_deg`` about the origin, per real
    ``pcbnew`` (footprint placed at (0, 0)). Skips loudly if no interpreter
    with pcbnew bindings is available, or if the oracle call itself fails."""
    interpreter = _pcbnew_python_or_skip()
    oracle = _pcbnew_oracle_batch(interpreter, [(dx, dy, angle_deg)])
    if oracle is None:
        pytest.skip(f"pcbnew oracle call failed for interpreter {interpreter}")
    return oracle[0]


def test_convention_anchor_at_37_degrees_matches_pcbnew():
    """The general convention claim, anchored against real KiCad at a
    non-90-degree angle: rotate_local_to_world of local offset (0.5, 0.3)
    about origin (12.0, -4.0) at 37 degrees must land where pcbnew actually
    places that pad -- (12.579862, -4.061317) per the evidence doc's
    measured value. The pre-fix R(+theta) answer (12.218773, -3.459502)
    differs by ~0.36 mm, three orders of magnitude above the 5 nm oracle
    tolerance -- a sign flip fails immediately.
    """
    ox, oy = _oracle_world_point(_DX, _DY, _ANGLE_37)
    got = place_local_to_world(_DX, _DY, _ORIGIN_X, _ORIGIN_Y, math.radians(_ANGLE_37))
    assert got[0] == pytest.approx(_ORIGIN_X + ox, abs=_ORACLE_TOLERANCE_MM)
    assert got[1] == pytest.approx(_ORIGIN_Y + oy, abs=_ORACLE_TOLERANCE_MM)


def test_convention_anchor_at_45_degrees_matches_pcbnew():
    """Same anchor at 45 degrees -- a second non-multiple angle, so the
    convention is not pinned at exactly one arbitrary offset."""
    ox, oy = _oracle_world_point(_DX, _DY, _ANGLE_45)
    got = place_local_to_world(_DX, _DY, _ORIGIN_X, _ORIGIN_Y, math.radians(_ANGLE_45))
    assert got[0] == pytest.approx(_ORIGIN_X + ox, abs=_ORACLE_TOLERANCE_MM)
    assert got[1] == pytest.approx(_ORIGIN_Y + oy, abs=_ORACLE_TOLERANCE_MM)


def test_composition_law_at_non_multiple_angle_matches_pcbnew():
    """The composition law R(-θ1)(R(-θ2)(p)) == R(-(θ1+θ2))(p) anchored
    externally at non-multiple angles: composing the 37- and 45-degree
    rotations must match what pcbnew does for a SINGLE step at the summed
    angle (82 degrees) -- so the general law is not just internally
    consistent, it agrees with real KiCad on the combined rotation.
    """
    composed = rotate_local_to_world(
        *rotate_local_to_world(_DX, _DY, math.radians(_ANGLE_37)),
        math.radians(_ANGLE_45),
    )
    # Internal consistency arm of the law (single-step closed form).
    single_step = rotate_local_to_world(_DX, _DY, math.radians(_ANGLE_37 + _ANGLE_45))
    assert composed[0] == pytest.approx(single_step[0], abs=1e-9)
    assert composed[1] == pytest.approx(single_step[1], abs=1e-9)
    # External anchor arm: pcbnew's own single-step placement at 82 degrees.
    ox, oy = _oracle_world_point(_DX, _DY, _ANGLE_37 + _ANGLE_45)
    assert composed[0] == pytest.approx(ox, abs=_ORACLE_TOLERANCE_MM)
    assert composed[1] == pytest.approx(oy, abs=_ORACLE_TOLERANCE_MM)


def test_sign_flip_fails_against_pcbnew_oracle_at_37_degrees():
    """Falsifier: proves the 37-degree anchor is genuinely discriminating.
    The R(+theta) reference (``rotate_world_to_local``, the documented
    transpose of R(-theta)) gives (0.218773, 0.540498) for this input while
    pcbnew places it at (0.579862, -0.061317) -- a ~0.7 mm disagreement, far
    beyond the 5 nm oracle tolerance. If the implementation were reverted to
    R(+theta), the anchor tests above would compare its output against the
    pcbnew value and fail immediately (the evidence doc records exactly this
    falsifier proof: 12.218773 != 12.579862 ± 5e-06).
    """
    ox, oy = _oracle_world_point(_DX, _DY, _ANGLE_37)
    flipped = rotate_world_to_local(_DX, _DY, math.radians(_ANGLE_37))
    assert abs((_ORIGIN_X + ox) - (_ORIGIN_X + flipped[0])) > _ORACLE_TOLERANCE_MM
    assert abs((_ORIGIN_Y + oy) - (_ORIGIN_Y + flipped[1])) > _ORACLE_TOLERANCE_MM
