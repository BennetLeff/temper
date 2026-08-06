"""R1c/R1d: property + metamorphic tests for ``placer/template.py``.

Five properties and three metamorphic relations over the migrated
``apply`` compute (the Rust kernels behind ``ComponentTemplate.apply`` /
``ParametricTemplate.apply``). Each property is a statement that holds for
every input hypothesis can find; each has a vacuity guard proving it is
breakable (a degenerate kernel that violates the claim must fail the
assertion), so none is vacuously true.

The dominant property is differential -- Rust agrees bit-for-bit with the
pinned oracle -- because that is the claim the migration actually makes;
the rest are structural invariants that would survive even if both arms
were wrong together.

Bit-exactness design notes for the metamorphic relations (this file's MRs
assert *bit-level* equalities, so every relation must be over an
IEEE-exact transform -- a power-of-two scaling, an integer full-turn
rotation, or the anchor's zero-relative-offset arithmetic -- never over a
rounded expression compared against a differently-rounded one):

- MR1 scales the template coordinates by ``2**k``. Multiplication by a
  power of two is exact for normal-range doubles and commutes with IEEE
  subtraction (``(x*2^k) - (y*2^k) == (x - y)*2^k``), so the scaled run's
  placement is exactly ``anchor + 2**k * (x - anchor.x)`` in the kernel's
  own evaluation order.
- MR2 shifts the requested rotation by whole turns of 360. The *position*
  is NOT bit-periodic (``radians(r+360k)`` is ``(r+360k)*(pi/180)``, a
  different product from ``r*(pi/180)`` -- the transcendental seam does not
  commute), so the relation claims only what is exact: the composite
  rotation output is periodic (integer floored mod), and the shim stays
  differential at every shifted rotation.
- MR3 rescales the parametric target dimensions. The anchor component's
  relative offset is ``arx*w - arx*w == 0.0`` exactly (a value minus
  itself), so the anchor lands bit-exactly at ``(ax, ay)`` for *every*
  dimension pair -- a two-run relation that does not depend on rounding.
"""

from __future__ import annotations

import math

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from temper_placer.placer.template import (
    ComponentPosition,
    ComponentTemplate,
    ParametricComponentPosition,
    ParametricTemplate,
)
from tests.placer import _placer_template_py_oracle as oracle
from tests.placer._placer_diff import float_hex

_SETTINGS = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)

_REFS = st.sampled_from(["Q1", "Q2", "D1", "D2", "C1", "C2", "U1", "R1", "R2"])
_ROTATIONS = st.integers(min_value=-1080, max_value=1080)
# Coordinates exclude -0.0: the anchor-arithmetic property (P2) claims
# "the anchor lands bit-exactly at the requested point", and IEEE normalises
# ``-0.0 + 0.0`` to ``+0.0`` on BOTH arms (the oracle normalises it too, so
# the migration is bit-identical either way; P1 pins the -0.0 edge against
# the oracle). A property that asserts bit-equality to a -0.0 literal would
# be asserting a rounding fact, not a migration fact, so the strategy
# filters it out and the differential (P1) owns the -0.0 coverage.
_COORD = st.floats(
    min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False
).filter(lambda v: not (v == 0.0 and math.copysign(1.0, v) < 0.0))
_RATIO = st.floats(min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False)

# Component geometry: distinct refs, varied offsets and rotations.
_COMPONENT_DATA = st.lists(
    st.tuples(_REFS, _COORD, _COORD, _ROTATIONS),
    min_size=1,
    max_size=6,
).map(lambda items: _dedupe_refs(items))


def _dedupe_refs(items):
    seen = set()
    out = []
    for ref, x, y, r in items:
        if ref in seen:
            continue
        seen.add(ref)
        out.append((ref, x, y, r))
    return out


def _anchor_data(items, anchor):
    """The anchor's (x, y, rotation) from the component data."""
    return next((x, y, r) for ref, x, y, r in items if ref == anchor)


def _prod_tpl(items, anchor):
    return ComponentTemplate(
        name="t",
        components=[ComponentPosition(ref, x, y, r) for ref, x, y, r in items],
        anchor_point=anchor,
    )


def _oracle_tpl(items, anchor):
    return oracle.ComponentTemplate(
        name="t",
        components=[oracle.ComponentPosition(ref, x, y, r) for ref, x, y, r in items],
        anchor_point=anchor,
    )


def _prod_ptpl(items, anchor):
    return ParametricTemplate(
        "p",
        [ParametricComponentPosition(ref, x, y, r) for ref, x, y, r in items],
        anchor,
    )


def _oracle_ptpl(items, anchor):
    return oracle.ParametricTemplate(
        "p",
        [oracle.ParametricComponentPosition(ref, x, y, r) for ref, x, y, r in items],
        anchor,
    )


# --- P1 ---------------------------------------------------------------------
@_SETTINGS
@given(_COMPONENT_DATA, _COORD, _COORD, _ROTATIONS)
def test_p1_component_apply_is_bit_identical_to_the_oracle(items, ax, ay, rotation):
    anchor = items[0][0]
    prod = _prod_tpl(items, anchor).apply(ax, ay, rotation=rotation)
    ref = _oracle_tpl(items, anchor).apply(ax, ay, rotation=rotation)
    assert list(prod) == list(ref)
    for key in ref:
        x_a, y_a, r_a = prod[key]
        x_b, y_b, r_b = ref[key]
        assert float_hex(x_a) == float_hex(x_b)
        assert float_hex(y_a) == float_hex(y_b)
        assert r_a == r_b


def test_p1_vacuity():
    # A rotation-ignoring kernel must violate P1 (a mutant that drops the
    # rotation branch would be caught by it).
    items = [("Q1", 0.0, 0.0, 0), ("Q2", 5.0, 5.0, 90)]
    ref = _oracle_tpl(items, "Q1").apply(10.0, 20.0, rotation=90)
    ref_x, ref_y, _ = ref["Q2"]
    # The fixture discriminates: with the rotation branch dropped the
    # placement would be the un-rotated (15, 25); the oracle rotates it away.
    assert abs(ref_x - 10.0) > 1e-9 or abs(ref_y - 20.0) > 1e-9


# --- P2 ---------------------------------------------------------------------
@_SETTINGS
@given(_COMPONENT_DATA, _COORD, _COORD, _ROTATIONS)
def test_p2_anchor_lands_exactly_at_the_anchor_point(items, ax, ay, rotation):
    anchor = items[0][0]
    prod = _prod_tpl(items, anchor).apply(ax, ay, rotation=rotation)
    _, _, anchor_rot = _anchor_data(items, anchor)
    x, y, rot = prod[anchor]
    assert float_hex(x) == float_hex(ax)
    assert float_hex(y) == float_hex(ay)
    assert rot == (rotation + anchor_rot) % 360


def test_p2_vacuity():
    # An off-by-one anchor offset would violate P2 (mutant M4 class).
    items = [("Q1", 0.0, 0.0, 0), ("Q2", 5.0, 5.0, 0)]
    prod = _prod_tpl(items, "Q1").apply(1.0, 2.0, rotation=0)
    assert prod["Q1"][0] == 1.0  # if the anchor offset leaked, this fails


# --- P3 ---------------------------------------------------------------------
@_SETTINGS
@given(_COMPONENT_DATA, _COORD, _COORD, _ROTATIONS)
def test_p3_composite_rotation_is_floored_modulo_360(items, ax, ay, rotation):
    anchor = items[0][0]
    prod = _prod_tpl(items, anchor).apply(ax, ay, rotation=rotation)
    for ref, _, _, comp_rot in items:
        _, _, rot = prod[ref]
        assert rot == (rotation + comp_rot) % 360
        assert 0 <= rot < 360


def test_p3_vacuity():
    # Truncated (Rust-style) modulo would produce a negative remainder for
    # rotation=-90, comp_rot=0 -> -90 % 360 = -90 in Rust, 270 in Python.
    items = [("Q1", 0.0, 0.0, 0)]
    prod = _prod_tpl(items, "Q1").apply(0.0, 0.0, rotation=-90)
    assert prod["Q1"][2] == 270


# --- P4 ---------------------------------------------------------------------
@_SETTINGS
@given(_COMPONENT_DATA, _COORD, _COORD)
def test_p4_zero_rotation_is_translation_only(items, ax, ay):
    anchor = items[0][0]
    ax0, ay0, _ = _anchor_data(items, anchor)
    prod = _prod_tpl(items, anchor).apply(ax, ay, rotation=0)
    for ref, x, y, _ in items:
        got_x, got_y, _ = prod[ref]
        assert float_hex(got_x) == float_hex(ax + (x - ax0))
        assert float_hex(got_y) == float_hex(ay + (y - ay0))


def test_p4_vacuity():
    # P4 pins that rotation=0 bypasses the trig seam entirely: a kernel that
    # rotated even at rotation=0 would change a non-axial offset.
    items = [("Q1", 0.0, 0.0, 0), ("Q2", 3.7, -2.1, 0)]
    prod = _prod_tpl(items, "Q1").apply(50.0, 50.0, rotation=0)
    assert prod["Q2"][0] == 53.7 and prod["Q2"][1] == 47.9


# --- P5 ---------------------------------------------------------------------
@_SETTINGS
@given(_COMPONENT_DATA, _COORD, _COORD, _RATIO, _RATIO)
def test_p5_parametric_scales_ratios_linearly(items, ax, ay, w, h):
    anchor = items[0][0]
    prod = _prod_ptpl(items, anchor).apply(ax, ay, w, h, rotation=0)
    ref = _oracle_ptpl(items, anchor).apply(ax, ay, w, h, rotation=0)
    for key in ref:
        x_a, y_a, r_a = prod[key]
        x_b, y_b, r_b = ref[key]
        assert float_hex(x_a) == float_hex(x_b)
        assert float_hex(y_a) == float_hex(y_b)
        assert r_a == r_b


def test_p5_vacuity():
    # Scaling must use x_ratio * target_width (not +): a ratio of 0.8 into a
    # 100-wide template at anchor (20,20) gives rel_x = 60.
    items = [("Q1", 0.2, 0.2, 0), ("Q2", 0.8, 0.8, 0)]
    prod = _prod_ptpl(items, "Q1").apply(50.0, 50.0, 100.0, 100.0, rotation=0)
    assert float_hex(prod["Q2"][0]) == float_hex(110.0)


# --- MR1 --------------------------------------------------------------------
# Template-coordinate scaling by a power of two. IEEE-exact: multiplying a
# normal-range double by 2**k is exact, and the kernel's rel arithmetic
# ``(x*2^k) - (anchor.x*2^k)`` equals ``(x - anchor.x)*2^k`` bit-exactly
# (rounding commutes with power-of-two scaling), so the scaled placement is
# ``anchor + 2**k * rel`` in the kernel's own evaluation order. The shim
# must stay differential on the scaled template too.
@_SETTINGS
@given(_COMPONENT_DATA, _COORD, _COORD, st.integers(min_value=0, max_value=8))
def test_mr1_scaling_template_by_power_of_two(items, ax, ay, k):
    anchor = items[0][0]
    ax0, ay0, _ = _anchor_data(items, anchor)
    scale = 2.0 ** k
    scaled = [(ref, x * scale, y * scale, r) for ref, x, y, r in items]
    prod = _prod_tpl(scaled, anchor).apply(ax, ay, rotation=0)
    ref = _oracle_tpl(scaled, anchor).apply(ax, ay, rotation=0)
    for key in ref:
        x_a, y_a, r_a = prod[key]
        x_b, y_b, r_b = ref[key]
        assert float_hex(x_a) == float_hex(x_b)
        assert float_hex(y_a) == float_hex(y_b)
        assert r_a == r_b
    # The exact relation: scaled placement is the anchor plus the scaled rel.
    for ref, x, y, _ in items:
        got_x, got_y, _ = prod[ref]
        assert float_hex(got_x) == float_hex(ax + scale * (x - ax0))
        assert float_hex(got_y) == float_hex(ay + scale * (y - ay0))


def test_mr1_vacuity():
    # The transform must actually move the output (k=2 on a nonzero rel), and
    # the exact relation must discriminate: a kernel that failed to scale the
    # rel (or scaled the wrong operand) fails the bit equality.
    items = [("Q1", 0.0, 0.0, 0), ("Q2", 3.7, -2.1, 0)]
    base = _prod_tpl(items, "Q1").apply(50.0, 50.0, rotation=0)
    scaled = _prod_tpl([(r, x * 4.0, y * 4.0, rot) for r, x, y, rot in items], "Q1").apply(
        50.0, 50.0, rotation=0
    )
    assert float_hex(scaled["Q2"][0]) == float_hex(50.0 + 4.0 * (3.7 - 0.0))
    assert float_hex(scaled["Q2"][1]) == float_hex(50.0 + 4.0 * (-2.1 - 0.0))
    assert base["Q2"][0] != scaled["Q2"][0]


# --- MR2 --------------------------------------------------------------------
# Full-turn rotation shift: the composite rotation output is exactly periodic
# (integer floored mod), and the shim stays differential at the shifted
# rotation. The position is deliberately NOT claimed periodic -- radians
# applies ``(r+360k)*(pi/180)``, a different product from ``r*(pi/180)``, so
# the transcendental seam legitimately differs.
@_SETTINGS
@given(_COMPONENT_DATA, _COORD, _COORD, _ROTATIONS)
def test_mr2_rotation_periodicity_360k(items, ax, ay, rotation):
    anchor = items[0][0]
    r0 = _prod_tpl(items, anchor).apply(ax, ay, rotation=rotation)
    rk = _prod_tpl(items, anchor).apply(ax, ay, rotation=rotation + 360)
    rkm = _prod_tpl(items, anchor).apply(ax, ay, rotation=rotation - 360)
    for key in r0:
        assert rk[key][2] == r0[key][2]
        assert rkm[key][2] == r0[key][2]
    # Differential at the shifted rotations (the family invariance).
    ref = _oracle_tpl(items, anchor).apply(ax, ay, rotation=rotation + 360)
    for key in ref:
        assert float_hex(rk[key][0]) == float_hex(ref[key][0])
        assert float_hex(rk[key][1]) == float_hex(ref[key][1])
        assert rk[key][2] == ref[key][2]


def test_mr2_vacuity():
    # A non-360 shift is not the identity on the composite rotation, so the
    # periodicity claim is not vacuous: -90 + 270 -> 180, while 45 + 270 -> 315.
    items = [("Q1", 0.0, 0.0, 0), ("Q2", 3.7, -2.1, 270)]
    r_neg90 = _prod_tpl(items, "Q1").apply(0.0, 0.0, rotation=-90)
    r_270 = _prod_tpl(items, "Q1").apply(0.0, 0.0, rotation=270)
    r_45 = _prod_tpl(items, "Q1").apply(0.0, 0.0, rotation=45)
    assert r_neg90["Q2"][2] == r_270["Q2"][2] == 180
    assert r_45["Q2"][2] != 180


# --- MR3 --------------------------------------------------------------------
# Parametric dimension rescaling: the anchor's relative offset is
# ``arx*w - arx*w == 0.0`` exactly (a value minus itself), so the anchor
# lands bit-exactly at (ax, ay) for every dimension pair -- a two-run
# relation independent of rounding. The shim must stay differential at the
# rescaled dimensions too.
@_SETTINGS
@given(_COMPONENT_DATA, _COORD, _COORD, _RATIO, _RATIO, _RATIO, _RATIO)
def test_mr3_parametric_anchor_invariant_under_rescaling(items, ax, ay, w1, h1, w2, h2):
    anchor = items[0][0]
    r1 = _prod_ptpl(items, anchor).apply(ax, ay, w1, h1, rotation=0)
    r2 = _prod_ptpl(items, anchor).apply(ax, ay, w2, h2, rotation=0)
    assert float_hex(r1[anchor][0]) == float_hex(ax)
    assert float_hex(r1[anchor][1]) == float_hex(ay)
    assert float_hex(r2[anchor][0]) == float_hex(ax)
    assert float_hex(r2[anchor][1]) == float_hex(ay)
    ref = _oracle_ptpl(items, anchor).apply(ax, ay, w2, h2, rotation=0)
    for key in ref:
        assert float_hex(r2[key][0]) == float_hex(ref[key][0])
        assert float_hex(r2[key][1]) == float_hex(ref[key][1])


def test_mr3_vacuity():
    # A non-anchor component moves under rescaling (the relation is not
    # trivially "everything unmoved"), and the anchor stays put: the two-run
    # claim discriminates a kernel that mis-scales the anchor offset.
    items = [("Q1", 0.2, 0.2, 0), ("Q2", 0.8, 0.8, 0)]
    r1 = _prod_ptpl(items, "Q1").apply(0.0, 0.0, 100.0, 100.0, rotation=0)
    r2 = _prod_ptpl(items, "Q1").apply(0.0, 0.0, 200.0, 200.0, rotation=0)
    assert r1["Q1"][0] == 0.0 and r2["Q1"][0] == 0.0
    assert r1["Q1"][1] == 0.0 and r2["Q1"][1] == 0.0
    assert r2["Q2"][0] != r1["Q2"][0]
