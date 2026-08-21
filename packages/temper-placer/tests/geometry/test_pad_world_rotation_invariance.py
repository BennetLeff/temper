"""A pad-to-pad distance INSIDE one footprint cannot change when the footprint
is rotated. This file is that sentence, executed.

Every pad of one footprint is carried by the same rigid motion, so an
intra-package pad-to-pad distance is a rigid-body invariant. Any transform
that reports a different number at a different placement angle is not
measuring a distance -- and that is disqualifying on its own, without needing
to know which number is right.

This property has now caught the same root cause **four** times on this
codebase, each time by an agent that happened to check:

1. ``compute_pad_groups`` never read ``Pin.pad_rotation_deg``.
2. ``analysis/settle-cst3015-copper-span`` (``6a240af9b``) -- the disputed
   transform returned 9.1/7.8/9.1/7.8 mm for the CST3015 across 0/90/180/270,
   and 8.0/5.425/8.0/5.425 for the G4A-E relay.
3. ``2026-08-19-per-pairing-placement-compliance.py`` -- 1243 intra-package
   pairs drifting, worst 5.15 mm.
4. The R53 dispute: 0.8625 vs 18.3283 vs 0.5500 mm for one pad-to-via gap.

Square angles hide sign errors, so the tests below never rely on them alone.

Two invariants, deliberately separated
--------------------------------------
``pad_geometry``'s ``rotation_rad`` parameter is currently applied as
R(+angle) while a pad *centre* is placed with R(-theta) (see
``temper_placer.geometry.pad_world``'s closing note and
``fix/pad-rotation-convention-rust`` / ``2bda7bf98``, which fixes it inside
``pad_geometry`` against a pcbnew oracle). Until that lands, the two agree at
every multiple of 90 degrees and diverge off it. So:

* **Centres** are tested at fully arbitrary angles (37, 13.5, -101.25, ...).
  Nothing about the body sign touches a centre, so this is the strongest form
  of the property and it is asserted in full.
* **Copper** is tested with the ``+90k`` form of the invariant -- *from a
  non-square base angle*. Turning a footprint by a further quarter turn is a
  rigid motion under either body handedness (a quarter turn maps a
  centro-symmetric pad onto itself), so this holds today and keeps holding
  after the ``pad_geometry`` fix, while still starting from 37 degrees where
  a sign error cannot hide.

``test_the_invariants_have_teeth`` proves neither form is vacuous by running
the three historically-wrong transforms through them.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from temper_placer.core.pad_geometry import pad_pair_distance
from temper_placer.geometry.kicad_transform import rotate_local_to_world_deg
from temper_placer.geometry.pad_world import (
    pad_pair_spec,
    pad_world_center,
    pad_world_rotation_deg,
    pin_pad_world,
)

# Angles a rigid invariant must survive. 0/90/180/270 are the quadrant cases
# every previous bug survived; 37 / 13.5 / -101.25 are the ones that catch a
# sign or shear error, which quadrant angles cannot.
ANGLES = (0.0, 90.0, 180.0, 270.0, 37.0, 13.5, -101.25, 359.75)

# Non-square bases for the +90k copper invariant.
NON_SQUARE_BASES = (37.0, 13.5, -101.25, 22.5)

TOL_MM = 1e-9

# Deliberately asymmetric pads: different aspect ratios, off-axis offsets, a
# non-zero intrinsic pad angle, and every shape pad_geometry models. A square
# pad at the origin would satisfy a broken transform by accident.
PADS: tuple[dict, ...] = (
    {"width": 9.0, "height": 4.8, "shape": "rect", "local": (7.68, -6.85),
     "pad_rotation_deg": 0.0, "roundrect_ratio": 0.25},
    {"width": 3.0, "height": 4.6, "shape": "rect", "local": (-6.88, 6.95),
     "pad_rotation_deg": 0.0, "roundrect_ratio": 0.25},
    {"width": 6.35, "height": 1.2, "shape": "roundrect", "local": (-3.175, 9.5),
     "pad_rotation_deg": 90.0, "roundrect_ratio": 0.2},
    {"width": 1.8, "height": 1.8, "shape": "circle", "local": (3.175, 0.0),
     "pad_rotation_deg": 180.0, "roundrect_ratio": 0.25},
    {"width": 1.125, "height": 1.75, "shape": "roundrect", "local": (-1.4625, 0.0),
     "pad_rotation_deg": 270.0, "roundrect_ratio": 0.25},
    {"width": 4.0, "height": 1.0, "shape": "oval", "local": (-9.0, -7.5),
     "pad_rotation_deg": 45.0, "roundrect_ratio": 0.25},
)

ORIGIN = (114.35, 141.26)


def _pair_ids() -> list[tuple[int, int]]:
    return [(i, j) for i in range(len(PADS)) for j in range(i + 1, len(PADS))]


# ---------------------------------------------------------------------------
# The canonical composition, and the three historically-wrong ones.
# Each takes (pad, theta) and returns a pad_pair_distance 7-tuple.
# ---------------------------------------------------------------------------


def _canonical(pad: dict, theta: float) -> tuple:
    return pad_pair_spec(
        pad["width"], pad["height"], pad["shape"],
        pad["local"][0], pad["local"][1],
        ORIGIN[0], ORIGIN[1], theta,
        pad["pad_rotation_deg"], pad["roundrect_ratio"],
    )


def _body_gets_pad_rotation_alone(pad: dict, theta: float) -> tuple:
    """DEFECT: centre rotated by the full footprint angle, but the pad BODY
    handed the footprint-RELATIVE ``pad_rotation_deg`` on its own. The
    justification ("a pad angle in a .kicad_pcb is already absolute, do not
    compose it") is true of the FILE but applied to a variable that no longer
    holds the file's value."""
    cx, cy = pad_world_center(pad["local"][0], pad["local"][1], ORIGIN[0], ORIGIN[1], theta)
    return (pad["width"], pad["height"], pad["shape"], cx, cy,
            math.radians(pad["pad_rotation_deg"]), pad["roundrect_ratio"])


def _body_drops_pad_rotation(pad: dict, theta: float) -> tuple:
    """DEFECT: ``pad_rotation_deg`` never read at all."""
    cx, cy = pad_world_center(pad["local"][0], pad["local"][1], ORIGIN[0], ORIGIN[1], theta)
    return (pad["width"], pad["height"], pad["shape"], cx, cy,
            math.radians(theta), pad["roundrect_ratio"])


def _center_never_rotated(pad: dict, theta: float) -> tuple:
    """DEFECT: the local offset summed straight onto the component position."""
    return (pad["width"], pad["height"], pad["shape"],
            ORIGIN[0] + pad["local"][0], ORIGIN[1] + pad["local"][1],
            math.radians(pad_world_rotation_deg(theta, pad["pad_rotation_deg"])),
            pad["roundrect_ratio"])


BROKEN = {
    "body gets pad_rotation_deg alone": _body_gets_pad_rotation_alone,
    "body drops pad_rotation_deg": _body_drops_pad_rotation,
    "centre never rotated": _center_never_rotated,
}


def _center_distance(i: int, j: int, theta: float) -> float:
    a = pin_pad_world(*PADS[i]["local"], *ORIGIN, theta, PADS[i]["pad_rotation_deg"])
    b = pin_pad_world(*PADS[j]["local"], *ORIGIN, theta, PADS[j]["pad_rotation_deg"])
    return math.dist(a.center, b.center)


def _copper_distance(i: int, j: int, theta: float, spec=_canonical) -> float:
    return pad_pair_distance(spec(PADS[i], theta), spec(PADS[j], theta))


# ---------------------------------------------------------------------------
# 1. Centres -- the full property, at arbitrary angles.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("i", "j"), _pair_ids())
def test_pad_centre_distance_is_a_rigid_invariant(i: int, j: int) -> None:
    """An intra-package centre-to-centre distance cannot depend on the angle
    the footprint is placed at. Asserted at arbitrary, non-square angles."""
    values = {theta: _center_distance(i, j, theta) for theta in ANGLES}
    spread = max(values.values()) - min(values.values())
    assert spread < TOL_MM, (
        f"pads {i}<->{j}: centre-to-centre distance moved by {spread:.6f} mm under "
        f"a RIGID rotation of the footprint -- it is therefore not a distance. "
        f"{ {k: round(v, 6) for k, v in values.items()} }"
    )
    # Non-vacuity: these pads are genuinely separated, so a transform that
    # collapsed everything to 0.0 would not pass by accident.
    assert min(values.values()) > 1.0


def test_pad_centre_distance_matches_the_hand_composition() -> None:
    """The kernel is not merely self-consistent: its centre agrees with
    ``kicad_transform`` applied by hand, at every angle."""
    for theta in ANGLES:
        for pad in PADS:
            rx, ry = rotate_local_to_world_deg(pad["local"][0], pad["local"][1], theta)
            got = pad_world_center(pad["local"][0], pad["local"][1], *ORIGIN, theta)
            assert got == (ORIGIN[0] + rx, ORIGIN[1] + ry)


def test_world_rotation_composes_component_and_pad_angles() -> None:
    """``pad_rotation_deg`` is stored footprint-RELATIVE, so the world body
    angle is the sum -- never either half on its own."""
    for theta in ANGLES:
        for pad in PADS:
            assert pad_world_rotation_deg(theta, pad["pad_rotation_deg"]) == pytest.approx(
                theta + pad["pad_rotation_deg"]
            )
    assert pad_world_rotation_deg(90.0, None) == 90.0  # None is "no intrinsic angle"


# ---------------------------------------------------------------------------
# 2. Copper -- the +90k form, from non-square bases.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("base", NON_SQUARE_BASES)
@pytest.mark.parametrize(("i", "j"), _pair_ids())
def test_pad_copper_distance_is_a_rigid_invariant(i: int, j: int, base: float) -> None:
    """Exact copper-to-copper distance, through the canonical kernel, cannot
    change when the footprint is turned by a further quarter turn -- starting
    from a NON-SQUARE base angle, where a sign or shear error cannot hide."""
    values = {base + k * 90.0: _copper_distance(i, j, base + k * 90.0) for k in range(4)}
    spread = max(values.values()) - min(values.values())
    assert spread < TOL_MM, (
        f"pads {i}<->{j} from base {base}: copper-to-copper distance moved by "
        f"{spread:.6f} mm under a RIGID rotation. "
        f"{ {k: round(v, 6) for k, v in values.items()} }"
    )


def test_copper_invariance_is_not_vacuous_through_touching_pads() -> None:
    """``pad_pair_distance`` clamps overlap to 0.0, so an all-zero population
    would satisfy the invariance test trivially. It does not: every pair here
    is genuinely apart."""
    apart = [
        _copper_distance(i, j, 37.0) for i, j in _pair_ids()
    ]
    assert min(apart) > 0.0, apart
    assert len(apart) >= 15


# ---------------------------------------------------------------------------
# 3. Teeth.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(BROKEN))
def test_the_invariants_have_teeth(name: str) -> None:
    """Each transform this repo actually shipped is caught. Without this, a
    kernel that returned a constant would pass every test above."""
    spec = BROKEN[name]
    worst = 0.0
    for i, j in _pair_ids():
        for base in NON_SQUARE_BASES:
            vals = [_copper_distance(i, j, base + k * 90.0, spec) for k in range(4)]
            worst = max(worst, max(vals) - min(vals))
        vals = [_copper_distance(i, j, t, spec) for t in ANGLES]
        worst = max(worst, max(vals) - min(vals))
    assert worst > 0.1, (
        f"{name!r} drifted by only {worst:.6f} mm -- the invariance assertions "
        "above would not have caught it, so they are not doing their job."
    )


def test_centre_invariant_catches_an_unrotated_offset() -> None:
    """The centre-only property has teeth too."""
    def broken(i: int, theta: float) -> tuple[float, float]:
        return (ORIGIN[0] + PADS[i]["local"][0], ORIGIN[1] + PADS[i]["local"][1])

    spreads = []
    for i, j in _pair_ids():
        vals = [math.dist(broken(i, t), broken(j, t)) for t in ANGLES]
        spreads.append(max(vals) - min(vals))
    # An unrotated offset gives a CONSTANT (hence "invariant") centre distance,
    # so the centre property alone cannot see it -- the copper property and
    # `test_pad_centre_distance_matches_the_hand_composition` are what do.
    assert max(spreads) == 0.0
    for theta in (37.0, 90.0):
        rx, ry = rotate_local_to_world_deg(*PADS[0]["local"], theta)
        assert (ORIGIN[0] + rx, ORIGIN[1] + ry) != broken(0, theta)


# ---------------------------------------------------------------------------
# 4. The board-specific precondition under which the open pad-body handedness
#    question is unobservable. A guard, not a design rule: if a pad ever lands
#    off the 90-degree grid, this fires and says so.
# ---------------------------------------------------------------------------

_BOARD = Path(__file__).resolve().parents[4] / "pcb" / "temper.kicad_pcb"
_AT_RE = re.compile(r"\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+(-?[\d.]+))?\s*\)")


def test_pad_body_handedness_is_unobservable_on_this_board() -> None:
    """``pad_geometry`` applies ``rotation_rad`` as R(+angle) while a centre is
    placed with R(-theta) (see ``pad_world``'s closing note). The two coincide
    exactly at multiples of 90 degrees. Every pad on this board sits at one, so
    the open question costs this board nothing -- assert that precondition
    rather than assume it.

    If this ever fails, the ``pad_geometry`` handedness fix
    (``fix/pad-rotation-convention-rust``, ``2bda7bf98``) has become
    load-bearing for a real measurement and must land before the affected
    figures are trusted.
    """
    if not _BOARD.exists():  # pragma: no cover - the board is in-tree
        pytest.fail(f"board not found at {_BOARD}")
    text = _BOARD.read_text(errors="replace")

    off_grid: list[str] = []
    checked = 0
    for fp_block in text.split("\n  (footprint ")[1:]:
        m = _AT_RE.search(fp_block)
        if m is None:
            continue
        fp_angle = float(m.group(3) or 0.0)
        if fp_angle % 90.0 != 0.0:
            off_grid.append(f"footprint angle {fp_angle}")
        for pad_block in fp_block.split("(pad ")[1:]:
            pm = _AT_RE.search(pad_block)
            if pm is None:
                continue
            checked += 1
            pad_angle = float(pm.group(3) or 0.0)
            if pad_angle % 90.0 != 0.0:
                off_grid.append(f"pad absolute angle {pad_angle}")

    assert checked > 500, f"only {checked} pads parsed -- the guard is not measuring the board"
    assert not off_grid, (
        "a pad or footprint now sits off the 90-degree grid: "
        f"{sorted(set(off_grid))}. The pad-body handedness question in "
        "pad_geometry is no longer unobservable -- land 2bda7bf98 "
        "(fix/pad-rotation-convention-rust) before trusting affected figures."
    )
