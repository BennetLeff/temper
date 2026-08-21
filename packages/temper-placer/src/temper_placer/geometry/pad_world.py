"""The single sanctioned way to put a pad into board (world) coordinates.

``kicad_transform`` already owns the *rotation matrix*. This module owns the
step above it: turning "a pad of a footprint that is placed somewhere at some
angle" into the ``(centre, world orientation)`` pair -- and into the exact
7-tuple ``core.pad_geometry.pad_pair_distance`` consumes. That composition,
not the matrix, is what this repo has now got wrong four separate times.

The convention
--------------
A ``.kicad_pcb`` footprint carries ``(at FX FY THETA)``. Each of its pads
carries ``(at LX LY [PAD_ANGLE])``. The two tokens do **not** mean the same
kind of thing:

* ``LX, LY`` is a **footprint-local, UNROTATED** offset. KiCad applies the
  footprint's ``THETA`` to it at load time; the file never stores the rotated
  value.
* ``PAD_ANGLE`` is the pad body's **ABSOLUTE** world orientation. The parent
  footprint's ``THETA`` is *not* added to it. (That additive convention holds
  only inside ``.kicad_mod`` library files -- see
  ``scripts/check_pad_orientation.py``, the gate that polices exactly this.)

So::

    world_centre     = (FX, FY) + R(-THETA) . (LX, LY)
    world_body_angle = PAD_ANGLE

and, because this codebase's parser stores the pad angle **footprint-relative**
(``parse_engine.rs``: ``pad_rotation_deg = PAD_ANGLE - THETA``) alongside a
likewise-local ``Pin.position``, the same two lines expressed over parsed
objects are::

    world_centre     = comp_position + R(-comp_rotation_deg) . Pin.position
    world_body_angle = comp_rotation_deg + Pin.pad_rotation_deg

Both halves must move together. Rotating the centre while leaving the body --
or handing the body ``pad_rotation_deg`` *alone*, which is what a
footprint-relative angle degenerates to if you forget to compose it -- is a
shear, not a rigid motion, and the number that falls out is not a distance.

Evidence for each half
----------------------
**Positions are stored unrotated (hence THETA must be applied at load).**
Measured on ``pcb/temper.kicad_pcb`` itself: of the library footprints that
this board places at two or more distinct angles, **267 of 267** pads carry
byte-identical ``(at LX LY)`` offsets across those placements. A stored
offset that does not change when the part is turned is a local offset.

**The rotation is R(-THETA), not R(+THETA).** Decided by the board's own
routed copper rather than by a vote among this repo's callers. KiCad anchors
a track on a pad's centre, so for every pad of every footprint placed at 90
or 270 degrees (the angles at which the two matrices differ) both candidate
centres were computed and matched against same-net segment endpoints and via
centres already on the board:

    R(-theta) matched where R(+theta) did not : 73
    R(+theta) matched where R(-theta) did not :  0

Independently: ``kicad-cli 10.0.4`` DRC ``shorting_items``, 57/57
(``docs/evidence/2026-07-29-intra-component-shorts-root-cause.md``) and
``pcbnew 10.0.5`` pad corners, 10/10 (``docs/evidence/
2026-07-29-cross-domain-creepage-rotation-convention.md``).

**The pad angle is absolute.** ``scripts/check_pad_orientation.py``'s premise,
and visible in the board: T1 (``CST3015``) is placed at 90 and every one of
its pads carries an absolute 90 -- a faithful rigid placement of a library
part whose pads are intrinsically at 0.

The rigid-body test that pins all of it
---------------------------------------
Every pad of one footprint is carried by the *same* rigid motion, so a
pad-to-pad distance **inside one footprint** is a rigid-body invariant: it
cannot change when the footprint is turned. That single property is what
caught this defect three separate times, and it lives permanently in
``tests/geometry/test_pad_world_rotation_invariance.py``.

A caveat this module does not paper over
----------------------------------------
:func:`pad_pair_spec` reports the world body angle through
``pad_geometry``'s ``rotation_rad`` parameter, whose own documented meaning
is "the pad's total world rotation". That parameter is currently applied by
``pad_core_polygon``/``pad_polygon``/``pad_support_radius`` as **R(+angle)**
(Shapely's native CCW sense), i.e. the *opposite* handedness to the R(-theta)
this module applies to the centre. The two agree exactly at every multiple of
90 degrees -- where a centro-symmetric pad maps onto itself -- and **all 527
pads on ``pcb/temper.kicad_pcb`` sit at a multiple of 90**, so no figure on
this board is affected either way. Off that grid they diverge, and the
divergence is ``pad_geometry``'s, not this module's:
``fix/pad-rotation-convention-rust`` (``2bda7bf98``) fixes it there against a
pcbnew oracle. This module therefore keeps passing ``+radians(world_angle)``,
which is correct today at every angle this board uses and becomes correct at
*every* angle the moment that fix lands -- rather than pre-negating here,
which would silently double-negate once it does. See the invariance test's
``test_pad_body_handedness_is_unobservable_on_this_board``.
"""

from __future__ import annotations

import math

from temper_placer.geometry.kicad_transform import place_local_to_world

__all__ = [
    "PadWorld",
    "pad_pair_spec",
    "pad_world_center",
    "pad_world_rotation_deg",
    "pad_world_rotation_rad",
    "pin_pad_world",
    "pin_pair_spec",
    "pin_world_center",
]

_DEFAULT_ROUNDRECT_RATIO = 0.25


def pad_world_center(
    local_x: float,
    local_y: float,
    comp_x: float,
    comp_y: float,
    comp_rotation_deg: float,
) -> tuple[float, float]:
    """The pad's centre in board coordinates.

    ``local_x/local_y`` is the pad's footprint-local, unrotated offset (a
    ``.kicad_pcb`` pad ``(at LX LY)``, or a parsed ``Pin.position``);
    ``comp_rotation_deg`` is the parent footprint's board angle in degrees.
    """
    return place_local_to_world(
        float(local_x),
        float(local_y),
        float(comp_x),
        float(comp_y),
        math.radians(float(comp_rotation_deg)),
    )


def pad_world_rotation_deg(
    comp_rotation_deg: float,
    pad_rotation_deg: float = 0.0,
) -> float:
    """The pad body's orientation in the board frame, in degrees.

    ``pad_rotation_deg`` is the **footprint-relative** angle this codebase's
    parser stores (``PAD_ANGLE - THETA``), so the world angle is the sum. Pass
    ``0.0`` for a pad that has no intrinsic rotation of its own.

    Not reduced modulo 360: callers that compare angles want to choose their
    own canonicalisation, and every downstream trig call is periodic anyway.
    """
    return float(comp_rotation_deg) + float(pad_rotation_deg or 0.0)


def pad_world_rotation_rad(
    comp_rotation_rad: float,
    pad_rotation_deg: float = 0.0,
) -> float:
    """:func:`pad_world_rotation_deg` for a caller that already holds the
    component's rotation in **radians**.

    Deliberately ``comp_rotation_rad + radians(pad_rotation_deg)`` rather
    than ``radians(degrees(comp_rotation_rad) + pad_rotation_deg)``: the
    round trip through degrees is not bit-exact, and several consumers of
    this value are pinned bit-for-bit against a frozen oracle. This form is
    what those consumers already compute, to the ULP.
    """
    return float(comp_rotation_rad) + math.radians(float(pad_rotation_deg or 0.0))


class PadWorld(tuple):
    """A pad placed on the board: ``(cx, cy, rotation_deg)``.

    A ``tuple`` subclass so it unpacks like the ad-hoc tuples it replaces,
    with names so a call site cannot silently swap the centre and the angle.
    """

    __slots__ = ()

    def __new__(cls, cx: float, cy: float, rotation_deg: float) -> PadWorld:
        return super().__new__(cls, (float(cx), float(cy), float(rotation_deg)))

    @property
    def cx(self) -> float:
        return self[0]

    @property
    def cy(self) -> float:
        return self[1]

    @property
    def rotation_deg(self) -> float:
        return self[2]

    @property
    def rotation_rad(self) -> float:
        return math.radians(self[2])

    @property
    def center(self) -> tuple[float, float]:
        return (self[0], self[1])


def pin_pad_world(
    local_x: float,
    local_y: float,
    comp_x: float,
    comp_y: float,
    comp_rotation_deg: float,
    pad_rotation_deg: float = 0.0,
) -> PadWorld:
    """Centre **and** body angle in one call -- the composition itself.

    Prefer this over calling :func:`pad_world_center` and
    :func:`pad_world_rotation_deg` separately: computing one without the
    other is exactly the defect this module exists to prevent.
    """
    cx, cy = pad_world_center(local_x, local_y, comp_x, comp_y, comp_rotation_deg)
    return PadWorld(cx, cy, pad_world_rotation_deg(comp_rotation_deg, pad_rotation_deg))


def pad_pair_spec(
    width: float,
    height: float,
    shape: str,
    local_x: float,
    local_y: float,
    comp_x: float,
    comp_y: float,
    comp_rotation_deg: float,
    pad_rotation_deg: float = 0.0,
    roundrect_ratio: float | None = None,
) -> tuple[float, float, str, float, float, float, float]:
    """The exact 7-tuple ``core.pad_geometry.pad_pair_distance`` consumes:
    ``(width, height, shape, cx, cy, rotation_rad, roundrect_ratio)``.

    ``roundrect_ratio=None`` falls back to KiCad's own default of 0.25 -- see
    ``pad_geometry``'s "roundrect_ratio, when unknown" note for why that
    fallback never under-reports copper.
    """
    world = pin_pad_world(
        local_x, local_y, comp_x, comp_y, comp_rotation_deg, pad_rotation_deg
    )
    ratio = _DEFAULT_ROUNDRECT_RATIO if roundrect_ratio is None else float(roundrect_ratio)
    return (
        float(width),
        float(height),
        str(shape),
        world.cx,
        world.cy,
        world.rotation_rad,
        ratio,
    )


def _pin_attrs(pin: object) -> tuple[float, float, float]:
    """``(local_x, local_y, pad_rotation_deg)`` from a duck-typed ``Pin``."""
    px, py = pin.position  # type: ignore[attr-defined]
    return (float(px), float(py), float(getattr(pin, "pad_rotation_deg", 0.0) or 0.0))


def pin_world_center(
    pin: object, comp_x: float, comp_y: float, comp_rotation_deg: float
) -> tuple[float, float]:
    """:func:`pad_world_center` for a parsed ``Pin``."""
    lx, ly, _ = _pin_attrs(pin)
    return pad_world_center(lx, ly, comp_x, comp_y, comp_rotation_deg)


def pin_pair_spec(
    pin: object, comp_x: float, comp_y: float, comp_rotation_deg: float
) -> tuple[float, float, str, float, float, float, float]:
    """:func:`pad_pair_spec` for a parsed ``Pin``, reading its own declared
    ``width``/``height``/``shape``/``roundrect_ratio``/``pad_rotation_deg``."""
    lx, ly, pad_rot = _pin_attrs(pin)
    return pad_pair_spec(
        float(getattr(pin, "width", 0.0) or 0.0),
        float(getattr(pin, "height", 0.0) or 0.0),
        str(getattr(pin, "shape", "rect") or "rect"),
        lx,
        ly,
        comp_x,
        comp_y,
        comp_rotation_deg,
        pad_rot,
        getattr(pin, "roundrect_ratio", None),
    )
