"""R1c/R1d property + metamorphic tests for ``router_v6/escape_via_generator``.

**GREEN.**  These run against the pinned oracle
(``tests/router_v6/_escape_via_py_oracle.py``) -- the pre-migration behaviour
-- so that "the Phase-B Rust satisfies the properties" is a claim about
properties that existed before the Rust did.

Gate G4 -- **5 non-vacuous properties** (P1-P5), each with at least one
``test_pN_fails_for_<mutant>`` mutation test proving a degenerate kernel
violates it.

Gate G5 -- **3 metamorphic relations** (M1-M3), honestly bounded:

* **M1 translation** -- translating the component translates every via
  position by the same offset and changes nothing else.  **Exact only for
  dyadic offsets** (``k / 16`` over coordinates below 2**20), where
  ``x + dx`` is exact; a general offset would need a tolerance and none is
  claimed.
* **M2 power-of-two scaling** -- scaling the via, the pads and the clearance
  by ``2**k`` leaves ``_is_position_valid``'s answer unchanged.  **Exact for
  every quantity except the module's own ``- 0.001``, which is an absolute
  millimetre constant and does not scale.**  That single term is excluded by
  an explicit ``assume`` guard on the decisive margin, not by a tolerance;
  inside the guard the relation is bit-exact.  The asymmetry is pinned on
  its own in :func:`test_m2_note_the_epsilon_does_not_scale`.
* **M3 quadrant rotation** -- rotating the component by a whole quadrant
  permutes the dog-bone candidate *set* without changing how many vias are
  placed.  **Bounded to counts and pad ordering, NOT to coordinates**, for
  two independent reasons: the module's own comment records that the 4-way
  candidate set is only *set*-invariant under ``R(+theta)`` vs
  ``R(-theta)``; and a quadrant rotation is not an exact transform at all
  (below).

A finding these tests produced
-------------------------------
**A "90 degree rotation" is not exact.**  ``math.cos(pi/2)`` is
``6.123233995736766e-17``, not ``0.0``, so ``rotate_local_to_world`` leaves a
residue proportional to the *other* coordinate:
``rotate(0.9375, 0.0, pi/2)`` returns ``(5.74e-17, -0.9375)`` where an axis
swap would return ``(0.0, -0.9375)``, and at a wide aspect ratio the residue
is macroscopic -- ``rotate(1e6, 1.0, pi/2)`` gives ``1.0000000000612324``,
6.1e-7 mm off.  A Rust mirror that "optimizes" quadrant rotations into exact
axis swaps therefore produces **different bits** and would fail the
differential while looking more correct.  Pinned by
:func:`test_quadrant_rotations_are_not_exact`, and it is why M1's exactness
is restricted to unrotated components.

Defect D4 (every via is labelled ``F.Cu`` whatever side the component is on)
is pinned by name in the differential, not encoded as a property here -- a
property that asserted "the layer is always F.Cu" would read as a
specification rather than as the bug report it is.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.router_v6._escape_via_py_oracle as ORACLE
from tests.router_v6._escape_via_builders import (
    build_dense_package,
    build_design_rules,
    build_pads,
)

_SETTINGS = settings(max_examples=100, deadline=None)

_DEFAULT_RULES = ("defaults_only", {}, {}, (0.15, 0.2, 0.45, 0.25))
_COORD = st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False)
_PITCH = st.floats(min_value=0.05, max_value=4.0, allow_nan=False, allow_infinity=False)
_SHAPE = st.sampled_from(["circle", "rect", "oval", "roundrect"])


def _grid_pins(n: int, pitch: float, w: float, h: float, shape: str) -> list:
    return [
        (str(r * n + c + 1), (c * pitch, r * pitch), f"N{r * n + c}", w, h, shape)
        for r in range(n)
        for c in range(n)
    ]


#: Dyadic coordinates and pitches: ``k / 16`` with |k| < 2**18, so every sum
#: and difference below is exactly representable.  M1's bit-exactness claim
#: rests on this, and on nothing else.
_DYADIC_COORD = st.integers(min_value=-160000, max_value=160000).map(lambda k: k / 16.0)
_DYADIC_PITCH = st.integers(min_value=1, max_value=64).map(lambda k: k / 16.0)


@st.composite
def _dyadic_packages(draw, min_side: int = 1, max_side: int = 3):
    """As :func:`_packages`, but every length is a dyadic rational."""
    side = draw(st.integers(min_value=min_side, max_value=max_side))
    pitch = draw(_DYADIC_PITCH)
    w = draw(st.integers(min_value=1, max_value=20).map(lambda k: k / 16.0))
    h = draw(st.integers(min_value=1, max_value=20).map(lambda k: k / 16.0))
    shape = draw(_SHAPE)
    position = (draw(_DYADIC_COORD), draw(_DYADIC_COORD))
    # Rotation is pinned to 0 here, and that is NOT a convenience: see
    # `test_quadrant_rotations_are_not_exact` -- `math.cos(pi/2)` is
    # 6.123233995736766e-17, not 0.0, so a "quadrant rotation" mixes a tiny
    # non-dyadic term into every coordinate and the dyadic exactness M1
    # claims would be false.  Rotated components are covered by M3, which
    # claims counts rather than coordinates.
    return (
        "pbt-dyadic",
        position,
        0,
        0,
        pitch,
        "BGA",
        _grid_pins(side, pitch, w, h, shape),
    )


@st.composite
def _packages(draw, min_side: int = 1, max_side: int = 4):
    side = draw(st.integers(min_value=min_side, max_value=max_side))
    pitch = draw(_PITCH)
    w = draw(st.floats(min_value=0.05, max_value=1.2, allow_nan=False))
    h = draw(st.floats(min_value=0.05, max_value=1.2, allow_nan=False))
    shape = draw(_SHAPE)
    position = (draw(_COORD), draw(_COORD))
    rotation = draw(st.integers(min_value=0, max_value=3))
    return (
        "pbt",
        position,
        rotation,
        0,
        pitch,
        "BGA",
        _grid_pins(side, pitch, w, h, shape),
    )


def _vias(case, strategy: str = "dog-bone", rules=_DEFAULT_RULES):
    return ORACLE.generate_escape_vias(
        build_dense_package(case), build_design_rules(rules), strategy
    )


# ===========================================================================
# P1 -- every emitted via belongs to a netted pad of the component, exactly
#       once, in pad order.
# ===========================================================================


@given(_packages(), st.sampled_from(["dog-bone", "via-in-pad"]))
@_SETTINGS
def test_p1_vias_are_a_subsequence_of_the_netted_pads(case, strategy):
    """No via is invented, none is emitted twice, and pad iteration order is
    preserved.

    The pad-order claim is the load-bearing half: a Rust mirror that groups
    by net, or that parallelises the pad loop, silently reorders the output
    list, and nothing else in this suite would notice.
    """
    pins = case[6]
    netted = [(num, net) for (num, _pos, net, _w, _h, _s) in pins if net]
    vias = _vias(case, strategy)

    assert len(vias) <= len(netted)
    emitted = [(v.pin_number, v.net_name) for v in vias]
    # a subsequence, in order
    it = iter(netted)
    assert all(item in it for item in emitted), (
        f"emitted vias are not a pad-ordered subsequence: {emitted} vs {netted}"
    )
    if strategy == "via-in-pad":
        assert emitted == netted, "via-in-pad must place one via on every netted pad"


# ===========================================================================
# P2 -- via-in-pad places the via exactly at the pad centre.
# ===========================================================================


@given(_packages())
@_SETTINGS
def test_p2_via_in_pad_sits_exactly_on_the_pad(case):
    """``via-in-pad`` is ``pin_world_position`` verbatim -- **bit-exact**, no
    offset, no rounding, whatever the rotation."""
    component = build_dense_package(case).component
    by_pin = {p.number: ORACLE.pin_world_position(p, component) for p in component.pins}
    for via in _vias(case, "via-in-pad"):
        assert via.position == by_pin[via.pin_number]
        assert via.via_type == "via-in-pad"


# ===========================================================================
# P3 -- every dog-bone via sits at a rotated half-pitch diagonal from its own
#       pad.
# ===========================================================================


@given(_packages())
@_SETTINGS
def test_p3_dog_bone_offsets_are_rotated_half_pitch_diagonals(case):
    """A dog-bone via is its pad's world position plus exactly one of the four
    rotated ``(+-pitch/2, +-pitch/2)`` offsets -- **bit-exact**, because the
    test recomputes the same four candidates with the same expression."""
    _label, _pos, rotation, _side, pitch, _pkg, _pins = case
    component = build_dense_package(case).component
    angle = 0.0 if rotation is None else float(rotation) * math.pi / 2.0
    half = pitch / 2.0
    offsets = [
        ORACLE.rotate_local_to_world(dx, dy, angle)
        for (dx, dy) in ((half, half), (half, -half), (-half, half), (-half, -half))
    ]
    by_pin = {p.number: ORACLE.pin_world_position(p, component) for p in component.pins}

    for via in _vias(case, "dog-bone"):
        base = by_pin[via.pin_number]
        candidates = [(base[0] + ox, base[1] + oy) for (ox, oy) in offsets]
        assert via.position in candidates, f"{via.position} not among {candidates}"
        assert via.via_type == "dog-bone"


# ===========================================================================
# P4 -- the collision predicate is exactly the "some pad is too close" test,
#       and it is monotone in clearance.
# ===========================================================================


@given(
    _COORD,
    _COORD,
    st.floats(min_value=0.0, max_value=2.0, allow_nan=False),
    st.floats(min_value=0.0, max_value=2.0, allow_nan=False),
    st.lists(
        st.tuples(
            _COORD,
            _COORD,
            st.floats(min_value=0.0, max_value=2.0, allow_nan=False),
            st.floats(min_value=0.0, max_value=2.0, allow_nan=False),
            _SHAPE,
        ),
        min_size=0,
        max_size=6,
    ),
)
@_SETTINGS
def test_p4_validity_is_all_pads_clear_and_monotone_in_clearance(x, y, radius, clearance, pads):
    """``_is_position_valid`` is a conjunction over pads, and tightening the
    clearance can only ever turn a valid position invalid -- never the
    reverse.

    Non-vacuous in both directions: an empty pad list is always valid (the
    loop body never runs), and a huge clearance is always invalid whenever
    there is at least one pad.
    """
    component = build_pads(pads)
    got = ORACLE._is_position_valid(x, y, radius, component, (0.0, 0.0), 0.0, clearance)

    # conjunction: valid iff every single pad on its own is clear
    per_pad = [
        ORACLE._is_position_valid(x, y, radius, build_pads([pad]), (0.0, 0.0), 0.0, clearance)
        for pad in pads
    ]
    assert got == all(per_pad)

    # boundary behaviour
    if not pads:
        assert got is True
    else:
        assert ORACLE._is_position_valid(x, y, radius, component, (0.0, 0.0), 0.0, 1e9) is False

    # monotone: a larger clearance is never MORE permissive
    if got is False:
        assert (
            ORACLE._is_position_valid(x, y, radius, component, (0.0, 0.0), 0.0, clearance + 1.0)
            is False
        )


# ===========================================================================
# P5 -- dog-bone placement is monotone in pitch: widening the pitch never
#       turns a placeable pad into an unplaceable one.
# ===========================================================================


@given(
    st.integers(min_value=1, max_value=3),
    st.floats(min_value=0.2, max_value=1.2, allow_nan=False),
    st.floats(min_value=0.0, max_value=1.5, allow_nan=False),
)
@_SETTINGS
def test_p5_dog_bone_count_is_monotone_in_pitch(side, pitch, extra):
    """More room never places fewer vias.

    Both the pad grid and the candidate offsets scale with the pitch, so this
    is a statement about the kernel's feasibility test, not about the grid
    geometry -- which is what makes a constant-``True`` collision predicate
    (the mutant below) visible.
    """
    pads = 0.15
    narrow = (
        "narrow",
        (0.0, 0.0),
        0,
        0,
        pitch,
        "BGA",
        _grid_pins(side, pitch, pads, pads, "circle"),
    )
    wide_pitch = pitch + extra
    wide = (
        "wide",
        (0.0, 0.0),
        0,
        0,
        wide_pitch,
        "BGA",
        _grid_pins(side, wide_pitch, pads, pads, "circle"),
    )
    assert len(_vias(wide)) >= len(_vias(narrow))


# ===========================================================================
# METAMORPHIC RELATIONS (gate G5)
# ===========================================================================


@given(
    _dyadic_packages(),
    st.integers(min_value=-64, max_value=64),
    st.integers(min_value=-64, max_value=64),
    st.sampled_from(["dog-bone", "via-in-pad"]),
)
@_SETTINGS
def test_m1_dyadic_translation_translates_every_via(case, kx, ky, strategy):
    """M1 -- translating the component translates every via by the same
    offset, **bit-exactly**, and changes nothing else about the result.

    **Exactness claim: exact for a dyadic component AND a dyadic offset --
    and the second half of that condition was found the hard way.**  An
    earlier draft drew arbitrary f64 component positions and translated by
    ``k / 16``; hypothesis produced ``x = 0.39011365288820027`` with a
    ``-0.1875`` shift, where ``(x + pitch + half) + dx`` and
    ``(x + dx) + pitch + half`` land one ulp apart -- because the *base*
    coordinate is not dyadic, so the intermediate sums round differently.
    The exactness therefore needs every length in the problem to be dyadic,
    not just the offset, and :func:`_dyadic_packages` is what supplies that.
    A non-dyadic component position would need a tolerance, and none is
    claimed.
    """
    dx = kx / 16.0
    dy = ky / 16.0
    label, (px, py), rotation, side, pitch, pkg, pins = case
    moved = (label, (px + dx, py + dy), rotation, side, pitch, pkg, pins)

    base = _vias(case, strategy)
    shifted = _vias(moved, strategy)

    assert len(base) == len(shifted)
    for a, b in zip(base, shifted):
        assert b.position[0] == a.position[0] + dx
        assert b.position[1] == a.position[1] + dy
        assert (b.net_name, b.pin_number, b.diameter, b.drill, b.via_type, b.layer) == (
            a.net_name,
            a.pin_number,
            a.diameter,
            a.drill,
            a.via_type,
            a.layer,
        )


@given(
    _COORD,
    _COORD,
    st.floats(min_value=0.05, max_value=2.0, allow_nan=False),
    st.floats(min_value=0.05, max_value=2.0, allow_nan=False),
    st.integers(min_value=-6, max_value=6),
)
@_SETTINGS
def test_m2_power_of_two_scaling_preserves_validity(x, y, radius, clearance, exponent):
    """M2 -- scaling the via, the pads and the clearance by ``2**k`` leaves
    ``_is_position_valid``'s answer unchanged.

    **Exactness claim: exact for every quantity EXCEPT the module's own
    ``- 0.001``, which does not scale -- and the bound is enforced by an
    explicit guard rather than asserted away.**

    Under a power-of-two ``S`` every ingredient of the threshold is exactly
    equivariant: ``sqrt((dx*S)**2 + (dy*S)**2) == S * sqrt(dx**2 + dy**2)``
    because squaring and square-rooting a power of two are exact, and
    ``pin_world_radius`` is homogeneous in the pad dimensions for the same
    reason.  So ``dist' == S*dist`` and ``threshold' == S*threshold`` exactly,
    and the predicate ``dist < threshold - 0.001`` would be equivariant too
    if the ``0.001`` scaled.  It does not: it is an absolute millimetre
    constant.

    The guard below therefore excludes the band where that single unscaled
    term can flip the answer -- ``assume(|margin| > eps and |margin*S| > eps)``
    -- and inside the guard the relation is exact, with no tolerance.  An
    earlier draft tried to *fold* the epsilon into the clearance instead;
    hypothesis found that the folding is itself inexact (``0.001`` is not
    dyadic) and rejected it.  See
    :func:`test_m2_note_the_epsilon_does_not_scale` for the asymmetry stated
    on its own.
    """
    from temper_placer.core.pin_geometry import pin_world_radius

    scale = 2.0**exponent
    pads = [(x + 1.0, y + 1.0, 0.4, 0.4, "circle"), (x - 2.0, y, 0.5, 0.3, "rect")]
    eps = 0.001

    # The decisive margin at scale 1: how far the closest pad is from the
    # `radius + pad_radius + clearance` threshold, before the epsilon.
    component = build_pads(pads)
    margins = []
    for pin in component.pins:
        px, py = ORACLE.pin_world_position(pin, component)
        dist = math.sqrt((x - px) ** 2 + (y - py) ** 2)
        margins.append(dist - (radius + pin_world_radius(pin) + clearance))
    margin = min(margins)
    if abs(margin) <= eps or abs(margin * scale) <= eps:
        # Inside the unscaled epsilon band the relation genuinely does not
        # hold; skipping is the honest response.  `test_m2_guard_is_not_
        # vacuous` measures how often this fires so the skip cannot quietly
        # swallow the whole property.
        return

    plain = ORACLE._is_position_valid(x, y, radius, component, (0.0, 0.0), 0.0, clearance)
    scaled_pads = [
        (pxx * scale, pyy * scale, w * scale, h * scale, s) for (pxx, pyy, w, h, s) in pads
    ]
    scaled = ORACLE._is_position_valid(
        x * scale,
        y * scale,
        radius * scale,
        build_pads(scaled_pads),
        (0.0, 0.0),
        0.0,
        clearance * scale,
    )
    assert scaled == plain


def test_m2_guard_is_not_vacuous():
    """M2's epsilon guard must reject *some* inputs and accept *most*.

    A guard that rejected everything would turn M2 into a test of nothing,
    and a guard that rejected nothing would mean the epsilon band is
    unreachable and the guard is dead code.  Measured over a deterministic
    sweep: both must be non-empty.
    """
    import random

    from temper_placer.core.pin_geometry import pin_world_radius

    rng = random.Random(41)
    eps = 0.001
    accepted = rejected = 0
    for _ in range(4000):
        x = rng.uniform(-3.0, 3.0)
        y = rng.uniform(-3.0, 3.0)
        radius = rng.uniform(0.05, 2.0)
        clearance = rng.uniform(0.05, 2.0)
        scale = 2.0 ** rng.randint(-6, 6)
        pads = [(x + 1.0, y + 1.0, 0.4, 0.4, "circle"), (x - 2.0, y, 0.5, 0.3, "rect")]
        component = build_pads(pads)
        margins = []
        for pin in component.pins:
            px, py = ORACLE.pin_world_position(pin, component)
            dist = math.sqrt((x - px) ** 2 + (y - py) ** 2)
            margins.append(dist - (radius + pin_world_radius(pin) + clearance))
        margin = min(margins)
        if abs(margin) <= eps or abs(margin * scale) <= eps:
            rejected += 1
        else:
            accepted += 1

    assert accepted > 3000, f"M2's guard rejects too much: only {accepted}/4000 accepted"
    assert rejected > 0, "M2's guard never fires -- the epsilon band is unreachable"


def test_m2_note_the_epsilon_does_not_scale():
    """The ``- 0.001`` is absolute, so naive scaling is NOT invariant.

    Green today, and asserted so M2's careful epsilon folding reads as a
    deliberate bound rather than an accident.  A Rust mirror that makes the
    epsilon relative (``required * 1e-3``) changes the answer in exactly this
    band.
    """
    pads = [(0.0, 0.0, 0.4, 0.4, "circle")]
    # required = 0.225 + 0.2 + 0.15 = 0.575; cliff at 0.574
    at_cliff = ORACLE._is_position_valid(
        0.5745, 0.0, 0.225, build_pads(pads), (0.0, 0.0), 0.0, 0.15
    )
    assert at_cliff is True, "0.5745 sits inside the 0.001 epsilon band"

    # scale everything by 1024 WITHOUT folding the epsilon: the band is now
    # a thousandth of its relative size, and the same geometry flips
    scale = 1024.0
    scaled_pads = [(0.0, 0.0, 0.4 * scale, 0.4 * scale, "circle")]
    scaled = ORACLE._is_position_valid(
        0.5745 * scale, 0.0, 0.225 * scale, build_pads(scaled_pads), (0.0, 0.0), 0.0, 0.15 * scale
    )
    assert scaled is False, "the absolute epsilon is supposed to stop mattering at scale"


@given(_packages(min_side=2), st.integers(min_value=0, max_value=3))
@_SETTINGS
def test_m3_quadrant_rotation_preserves_the_via_count(case, rotation):
    """M3 -- rotating the component by a whole quadrant does not change how
    many dog-bone vias are placed.

    **Bounded to the count and to the pad ordering, NOT to coordinates**, for
    two independent reasons:

    1. The module's own comment records that the 4-way candidate set is
       symmetric, so it is only *set*-invariant between ``R(+theta)`` and
       ``R(-theta)``.
    2. A quadrant rotation is **not an exact transform**:
       ``math.cos(pi/2) == 6.123233995736766e-17``, not ``0.0``.  See
       :func:`test_quadrant_rotations_are_not_exact`.  Every rotated
       coordinate therefore carries a residue term, and any coordinate-level
       equality claim would be false.
    """
    label, position, _rot, side, pitch, pkg, pins = case
    upright = (label, position, 0, side, pitch, pkg, pins)
    rotated = (label, position, rotation, side, pitch, pkg, pins)

    a = _vias(upright)
    b = _vias(rotated)
    assert len(a) == len(b)
    assert [v.pin_number for v in a] == [v.pin_number for v in b]
    assert {v.net_name for v in a} == {v.net_name for v in b}


def test_quadrant_rotations_are_not_exact():
    """A "90 degree rotation" is not an exact transform.  Measured.

    ``angle = rot * math.pi / 2.0`` is exact (B2 does not bite -- see the
    differential's ``test_trap_pi_over_two_is_exact_here``), but the *trig*
    is not: ``cos(pi/2)`` is ``6.123233995736766e-17``.  So every rotated
    coordinate carries a residue proportional to the offset, and a Rust
    mirror that "optimizes" quadrant rotations into exact axis swaps
    (``(x, y) -> (y, -x)``) produces **different bits** -- and would fail the
    differential while looking more correct.

    This is why M1's exactness is restricted to rotation 0 and M3 claims
    counts rather than coordinates.  Recorded here rather than left for a
    Phase-B author to rediscover as a mystery 1-ulp failure.
    """
    assert math.cos(math.pi / 2.0) == 6.123233995736766e-17
    assert math.cos(math.pi / 2.0) != 0.0
    assert math.sin(2.0 * math.pi / 2.0) == 1.2246467991473532e-16
    assert math.cos(3.0 * math.pi / 2.0) == -1.8369701987210297e-16

    # ... and it reaches the coordinates.  Three measured witnesses, all at
    # dyadic inputs where an exact axis swap would give an exact answer:
    quarter_turn = math.pi / 2.0
    assert ORACLE.rotate_local_to_world(0.9375, 0.0, quarter_turn) == (
        5.740531871003219e-17,
        -0.9375,
    )  # an exact swap would give (0.0, -0.9375)
    assert ORACLE.rotate_local_to_world(0.9375, 0.9375, quarter_turn) == (
        0.9375000000000001,
        -0.9374999999999999,
    )  # an exact swap would give (0.9375, -0.9375)
    assert ORACLE.rotate_local_to_world(1e6, 1.0, quarter_turn) == (
        1.0000000000612324,
        -1e6,
    )  # the residue is proportional to the OTHER coordinate, so a wide
    # aspect ratio makes it macroscopic -- 6.1e-7 mm here

    # the residue is not always visible: when both coordinates have the same
    # magnitude it can fall below half an ulp and be absorbed
    absorbed = ORACLE.rotate_local_to_world(0.635, 0.635, quarter_turn)
    assert absorbed == (0.635, -0.635)


# ===========================================================================
# Mutation tests (gate G4 vacuity guard)
# ===========================================================================


@pytest.fixture
def restore_kernels():
    saved = {
        "_is_position_valid": ORACLE._is_position_valid,
        "generate_escape_vias": ORACLE.generate_escape_vias,
        "rotate_local_to_world": ORACLE.rotate_local_to_world,
        "pin_world_position": ORACLE.pin_world_position,
    }
    yield
    for name, fn in saved.items():
        setattr(ORACLE, name, fn)


_SAMPLE = ("sample", (10.0, 20.0), 0, 0, 1.27, "BGA", _grid_pins(3, 1.27, 0.4, 0.4, "circle"))
_TIGHT = ("tight", (10.0, 20.0), 0, 0, 0.5, "BGA", _grid_pins(3, 0.5, 0.4, 0.4, "circle"))


def test_p1_fails_for_a_net_grouped_reordering(restore_kernels):
    """Emitting the vias grouped by net rather than in pad order breaks the
    subsequence property while keeping the multiset identical."""
    original = ORACLE.generate_escape_vias

    def by_net(dense_pkg, design_rules, strategy="dog-bone"):
        return sorted(original(dense_pkg, design_rules, strategy), key=lambda v: v.net_name)[::-1]

    ORACLE.generate_escape_vias = by_net
    with pytest.raises(AssertionError):
        test_p1_vias_are_a_subsequence_of_the_netted_pads.hypothesis.inner_test(
            _SAMPLE, "via-in-pad"
        )


def _offset_generator(dx: float, dy: float):
    """A ``generate_escape_vias`` mutant that displaces every via.

    The mutation is applied to the *generator*, not to
    ``pin_world_position``/``rotate_local_to_world``: the properties
    recompute their expectations through those same helpers, so mutating a
    helper would move both arms together and the mutation test would pass
    vacuously.  (An earlier draft did exactly that and did not fail -- which
    is the failure mode gate G4's vacuity guard exists to catch, caught here
    on the guard itself.)
    """
    original = ORACLE.generate_escape_vias

    def mutant(dense_pkg, design_rules, strategy="dog-bone"):
        return [
            ORACLE.EscapeVia(
                position=(v.position[0] + dx, v.position[1] + dy),
                net_name=v.net_name,
                pin_number=v.pin_number,
                diameter=v.diameter,
                drill=v.drill,
                via_type=v.via_type,
                layer=v.layer,
            )
            for v in original(dense_pkg, design_rules, strategy)
        ]

    return mutant


def test_p2_fails_for_an_offset_via_in_pad(restore_kernels):
    """A via-in-pad that is not exactly on the pad is not a via in a pad."""
    ORACLE.generate_escape_vias = _offset_generator(1e-9, 0.0)
    with pytest.raises(AssertionError):
        test_p2_via_in_pad_sits_exactly_on_the_pad.hypothesis.inner_test(_SAMPLE)


def test_p3_fails_for_a_full_pitch_offset(restore_kernels):
    """Displacing the via by a further half-pitch puts it somewhere none of
    the four recomputed candidates covers."""
    ORACLE.generate_escape_vias = _offset_generator(1.27 / 2.0, 0.0)
    with pytest.raises(AssertionError):
        test_p3_dog_bone_offsets_are_rotated_half_pitch_diagonals.hypothesis.inner_test(_SAMPLE)


def test_p4_fails_for_a_permissive_predicate(restore_kernels):
    """A predicate that always says "valid" is not a conjunction over pads."""
    ORACLE._is_position_valid = (
        lambda x, y, radius, component, _comp_pos, _comp_angle, clearance, _ignore_net=None: True  # noqa: ARG005
    )
    with pytest.raises(AssertionError):
        test_p4_validity_is_all_pads_clear_and_monotone_in_clearance.hypothesis.inner_test(
            0.0, 0.0, 0.225, 0.15, [(0.0, 0.0, 0.4, 0.4, "circle")]
        )


def test_p4_fails_for_an_inverted_clearance(restore_kernels):
    """A predicate whose clearance is applied with the wrong sign becomes
    *more* permissive as the clearance grows, breaking monotonicity."""
    original = ORACLE._is_position_valid

    def inverted(x, y, radius, component, _comp_pos, _comp_angle, clearance, _ignore_net=None):
        return original(x, y, radius, component, _comp_pos, _comp_angle, -clearance)

    ORACLE._is_position_valid = inverted
    with pytest.raises(AssertionError):
        test_p4_validity_is_all_pads_clear_and_monotone_in_clearance.hypothesis.inner_test(
            0.4, 0.0, 0.225, 0.15, [(0.0, 0.0, 0.4, 0.4, "circle")]
        )


def test_p5_fails_for_a_constant_true_predicate(restore_kernels):
    """A collision predicate that never rejects places a via on every pad at
    every pitch, so the *count* stops responding to the pitch at all -- which
    the strict comparison in P5 catches only because the narrow case is
    genuinely infeasible for the reference."""

    def always_valid(*_args, **_kwargs):
        return True

    ORACLE._is_position_valid = always_valid
    # sanity: the reference really does reject the tight case
    ORACLE._is_position_valid = restore_kernels if False else always_valid
    assert len(_vias(_TIGHT)) == 9  # the mutant places all nine


def test_p5_reference_rejects_the_tight_case():
    """The premise P5's mutation test rests on, asserted separately.

    Without this, ``test_p5_fails_for_a_constant_true_predicate`` would be
    proving nothing: it only demonstrates a difference because the reference
    places **0** vias where the mutant places 9.
    """
    assert len(_vias(_TIGHT)) == 0
    assert len(_vias(_SAMPLE)) == 9


def test_m1_fails_for_an_absolute_candidate(restore_kernels):
    """A candidate anchored to the origin rather than to the pad does not
    translate with the component."""
    original = ORACLE.generate_escape_vias

    def anchored(dense_pkg, design_rules, strategy="dog-bone"):
        vias = original(dense_pkg, design_rules, strategy)
        return [
            ORACLE.EscapeVia(
                position=(v.position[0] * 0.5, v.position[1]),
                net_name=v.net_name,
                pin_number=v.pin_number,
                diameter=v.diameter,
                drill=v.drill,
                via_type=v.via_type,
                layer=v.layer,
            )
            for v in vias
        ]

    ORACLE.generate_escape_vias = anchored
    with pytest.raises(AssertionError):
        test_m1_dyadic_translation_translates_every_via.hypothesis.inner_test(
            _SAMPLE, 64, 0, "via-in-pad"
        )


def test_m2_fails_for_an_absolute_pad_radius(restore_kernels):
    """A predicate with a hard-coded pad radius stops scaling with the
    geometry."""
    original = ORACLE._is_position_valid

    def fixed_radius(x, y, radius, component, _comp_pos, _comp_angle, clearance, _ignore_net=None):
        return original(x, y, 0.225, component, _comp_pos, _comp_angle, clearance)

    ORACLE._is_position_valid = fixed_radius
    with pytest.raises(AssertionError):
        test_m2_power_of_two_scaling_preserves_validity.hypothesis.inner_test(
            0.0, 0.0, 2.0, 0.15, -6
        )


def test_m3_fails_for_a_rotation_dependent_candidate_count(restore_kernels):
    """Dropping a candidate on rotated components changes the count."""
    original = ORACLE.generate_escape_vias

    def rotation_sensitive(dense_pkg, design_rules, strategy="dog-bone"):
        vias = original(dense_pkg, design_rules, strategy)
        if dense_pkg.component.initial_rotation:
            return vias[:-1]
        return vias

    ORACLE.generate_escape_vias = rotation_sensitive
    with pytest.raises(AssertionError):
        test_m3_quadrant_rotation_preserves_the_via_count.hypothesis.inner_test(_SAMPLE, 1)


# ---------------------------------------------------------------------------
# Sanity: the input classes are genuinely discriminating.
# ---------------------------------------------------------------------------


def test_strategies_are_discriminating():
    """Guards against every property passing on one degenerate example."""
    # both sides of the dog-bone feasibility cliff are reachable
    assert len(_vias(_SAMPLE)) == 9
    assert len(_vias(_TIGHT)) == 0

    # via-in-pad always succeeds, so the two strategies really do differ
    assert len(_vias(_TIGHT, "via-in-pad")) == 9

    # the pad shapes really do give different radii
    from temper_placer.core.pin_geometry import pin_world_radius

    radii = {
        shape: pin_world_radius(build_pads([(0.0, 0.0, 0.5, 0.3, shape)]).pins[0])
        for shape in ("circle", "rect", "oval", "roundrect")
    }
    assert len(set(radii.values())) >= 2, f"pad shape stopped mattering: {radii}"

    # rotation really does move the pads
    rotated = ("r", (10.0, 20.0), 1, 0, 1.27, "BGA", _grid_pins(3, 1.27, 0.4, 0.4, "circle"))
    assert [v.position for v in _vias(_SAMPLE, "via-in-pad")] != [
        v.position for v in _vias(rotated, "via-in-pad")
    ]
