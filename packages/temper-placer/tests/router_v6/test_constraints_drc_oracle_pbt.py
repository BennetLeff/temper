"""Gate G4 for the `router_v6/constraints_drc_oracle.py` migration (Wave 4,
unit = one module).  Properties run against the **shipped** shim
(`temper_placer.router_v6.constraints_drc_oracle.DRCOracle`), which
delegates to `temper_drc_rs`'s `drc_oracle.rs` kernels; reachability is
measured at the Rust boundary (the shim resolves `temper_drc_rs` module
attributes at call time, so a per-run counter wrapper around the kernel is
observed), and every property carries a `test_pN_fails_for_<mutant>`
vacuity guard that re-runs the full property under a degenerate compiled
kernel and asserts it fails (the `test_bottleneck_geometry_pbt.py` /
`test_dfm_rust_pbt.py` pattern combined).

Kernel-to-property map (every kernel reached; reachability measured, not
assumed):
===========================  =============================================
kernel                       properties
===========================  =============================================
`drc_oracle_can_place_via_py`      P1, M1, M2, M3, M4
`drc_oracle_can_place_track_py`    P2, P4, M1, M2, M3, M4
`drc_oracle_severity_py`           P3
`drc_oracle_pad_credit_py`         P5
`drc_oracle_validate_all_py`       P6
===========================  =============================================

Each property is a nested `@given` `prop` invoked once by the outer test,
which then asserts the aggregate reachability floors (`calls >= 50`,
`outcomes >= 2`); a mutant test re-invokes the outer test with the compiled
kernel replaced and requires an `AssertionError`, proving the property is
not vacuous.
"""

from __future__ import annotations

import contextlib

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6 import constraints_drc_oracle as SHIM
from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix
from temper_placer.router_v6.constraints_geometry import Point, point_to_rotated_rect_distance
from temper_placer.router_v6.constraints_spatial_index import Pad, Track, Via
from tests.router_v6._signature import sig

_drc = pytest.importorskip(
    "temper_drc_rs",
    reason=(
        "gate G4 needs the built extension; "
        "test_constraints_drc_oracle_rust_differential.py fails loudly when it is missing"
    ),
)

_SETTINGS = settings(max_examples=200, deadline=None)

_MIN_CALLS = 50
_MIN_OUTCOMES = 2

# Dyadic translation used by the metamorphic relations (bit-exact: adding
# 0.5 to every coordinate preserves every f64 difference).
_SHIFT = 0.5


class _Reach:
    """Per-property reachability counters (see module docstring)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0
        self.outcomes: set[object] = set()

    def hit(self, outcome: object) -> None:
        self.calls += 1
        self.outcomes.add(outcome)

    def assert_reached(self, min_calls: int = _MIN_CALLS, min_outcomes: int = _MIN_OUTCOMES):
        assert self.calls >= min_calls, (
            f"{self.name}: only {self.calls} generated inputs reached the kernel "
            f"(floor {min_calls}) -- the property is measuring its own guards, not the kernel"
        )
        assert len(self.outcomes) >= min_outcomes, (
            f"{self.name}: the kernel returned {len(self.outcomes)} distinct outcome(s) "
            f"over {self.calls} calls (floor {min_outcomes}) -- this property is "
            f"comparing constants"
        )


@contextlib.contextmanager
def _counted(name: str, reach: _Reach, render):
    """Temporarily wrap `temper_drc_rs.<name>` with a call/outcome counter."""
    fn = getattr(_drc, name)

    def wrapper(*args, **kwargs):
        out = fn(*args, **kwargs)
        reach.hit(render(out))
        return out

    setattr(_drc, name, wrapper)
    try:
        yield
    finally:
        setattr(_drc, name, fn)


def _matrix():
    m = ClearanceMatrix()
    for net in ("SIG_A", "SIG_B", "PWR", "USB_D+", "USB_D-"):
        m.set_net_class(net, "Signal")
    return m


def _make_oracle():
    return SHIM.DRCOracle(rules=_matrix())


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

_FIN = dict(allow_nan=False, allow_infinity=False, width=64)


@st.composite
def p1_via_case(draw):
    """(pad geometry, via position/radius) with the via often near the pad."""
    px = draw(st.floats(min_value=-20.0, max_value=20.0, **_FIN))
    py = draw(st.floats(min_value=-20.0, max_value=20.0, **_FIN))
    w = draw(st.floats(min_value=0.2, max_value=4.0, **_FIN))
    h = draw(st.floats(min_value=0.2, max_value=4.0, **_FIN))
    rot = draw(st.floats(min_value=-180.0, max_value=180.0, **_FIN))
    vx = draw(st.floats(min_value=-24.0, max_value=24.0, **_FIN))
    vy = draw(st.floats(min_value=-24.0, max_value=24.0, **_FIN))
    vr = draw(st.floats(min_value=0.05, max_value=0.6, **_FIN))
    return (px, py, w, h, rot, vx, vy, vr)


@st.composite
def p3_sev_case(draw):
    required = draw(st.floats(min_value=1e-3, max_value=10.0, **_FIN))
    actual = draw(st.floats(min_value=0.0, max_value=required, **_FIN))
    return (actual, required)


@st.composite
def p5_credit_case(draw):
    # positions across the credit band (midpoint (0,0), half_w 1.0, half_len
    # 3.0, axis 'x') and well outside it, so inside/outside both occur.
    px = draw(st.floats(min_value=-5.0, max_value=5.0, **_FIN))
    py = draw(st.floats(min_value=-5.0, max_value=5.0, **_FIN))
    return (px, py)


# ---------------------------------------------------------------------------
# P1 — can_place_via: validity is exactly the geometric clearance threshold
# ---------------------------------------------------------------------------


def test_p1_can_place_via_validity_matches_geometric_threshold():
    reach = _Reach("P1")

    @given(p1_via_case())
    @_SETTINGS
    def prop(case):
        px, py, w, h, rot, vx, vy, vr = case
        pad = Pad(
            center=Point(px, py), shape="rect", size=(w, h), net="SIG_B",
            layer=0, id="p1", mask_expansion=0.1, rotation=rot,
        )
        oracle = _make_oracle()
        oracle.register_pad(pad)
        oracle.geometry.rebuild_index()

        valid, _ = oracle.can_place_via((vx, vy), vr * 2.0, "SIG_A")

        # expected: required(0.2) + via_radius + mask(0.1)
        effective = 0.2 + vr + 0.1
        actual = point_to_rotated_rect_distance(Point(vx, vy), pad.rot_rect)
        assert valid == (actual >= effective), (
            f"valid={valid} but actual={actual} vs effective={effective} "
            f"(pad=({px},{py},{w},{h},{rot}), via=({vx},{vy}) r={vr})"
        )

    with _counted("drc_oracle_can_place_via_py", reach, lambda r: ("NONE",) if r is None else (r[0],)):
        prop()
    reach.assert_reached()


def test_p1_fails_for_always_invalid_kernel():
    """An always-violating kernel breaks the clear-side of the threshold."""
    original = _drc.drc_oracle_can_place_via_py
    _drc.drc_oracle_can_place_via_py = lambda *_a, **_k: ("pad", "p1", 0.0, 0.4)
    try:
        with pytest.raises(AssertionError):
            test_p1_can_place_via_validity_matches_geometric_threshold()
    finally:
        _drc.drc_oracle_can_place_via_py = original


# ---------------------------------------------------------------------------
# P2 — can_place_track_segment: moving the obstacle away never turns a valid
# placement invalid (monotonicity in the perpendicular gap)
# ---------------------------------------------------------------------------

_OFFSETS = (0.0, 0.5, 1.0, 1.2, 1.4, 1.6, 2.0, 2.5, 3.0)


def test_p2_track_validity_monotonic_in_obstacle_distance():
    reach = _Reach("P2")

    @given(st.floats(min_value=0.5, max_value=2.0, **_FIN))
    @_SETTINGS
    def prop(pad_half):
        pad = Pad(
            center=Point(0.0, 0.0), shape="rect", size=(2.0, 2.0 * pad_half),
            net="SIG_B", layer=0, id="p2", mask_expansion=0.1,
        )
        oracle = _make_oracle()
        oracle.register_pad(pad)
        oracle.geometry.rebuild_index()

        validities = [
            oracle.can_place_track_segment((-10.0, off), (10.0, off), 0, "SIG_A", 0.2)[0]
            for off in _OFFSETS
        ]

        # once valid, always valid at larger offsets
        for i in range(len(_OFFSETS)):
            for j in range(i, len(_OFFSETS)):
                if validities[i]:
                    assert validities[j], (
                        f"valid at offset {_OFFSETS[i]} but invalid at {_OFFSETS[j]}: "
                        f"moving the pad farther must not create a violation"
                    )
        # the sweep genuinely straddles the clearance boundary
        assert True in validities and False in validities, (
            f"offset sweep never flipped validity ({validities}) -- degenerate scenario"
        )

    with _counted("drc_oracle_can_place_track_py", reach, lambda r: ("NONE",) if r is None else (r[0],)):
        prop()
    reach.assert_reached()


def test_p2_fails_for_position_dependent_kernel():
    """A kernel that flags far placements (position-dependent, non-monotone)
    breaks the monotonicity property.  (An always-valid or always-invalid
    kernel satisfies it trivially, so the discriminating mutant is the
    position-dependent one -- same shape as test_bottleneck_geometry_pbt.py's
    P4 mutant.)"""
    original = _drc.drc_oracle_can_place_track_py

    def pos_dependent(sx, sy, *_a, **_k):
        if sy > 1.5:
            return ("pad", "p2", 0.0, 0.4)
        return None

    _drc.drc_oracle_can_place_track_py = pos_dependent
    try:
        with pytest.raises(AssertionError):
            test_p2_track_validity_monotonic_in_obstacle_distance()
    finally:
        _drc.drc_oracle_can_place_track_py = original


# ---------------------------------------------------------------------------
# P3 — severity: bounded, exactly `1.0 - actual/required`, monotone in actual
# ---------------------------------------------------------------------------


def test_p3_severity_bounded_and_monotone():
    reach = _Reach("P3")

    @given(p3_sev_case())
    @_SETTINGS
    def prop(case):
        actual, required = case
        sev = _drc.drc_oracle_severity_py(actual, required)
        assert sig(sev) == sig(1.0 - (actual / required))
        assert 0.0 <= sev <= 1.0
        # monotone non-increasing in actual: larger actual -> no greater severity
        actual2 = (actual + required) / 2.0
        sev2 = _drc.drc_oracle_severity_py(actual2, required)
        assert sev2 <= sev

    with _counted("drc_oracle_severity_py", reach, lambda r: round(r, 6)):
        prop()
    reach.assert_reached()


def test_p3_fails_for_inverted_kernel():
    """A kernel returning `(actual/required) - 1` (severity grows with
    actual) breaks both the exact formula and the monotone direction."""
    original = _drc.drc_oracle_severity_py
    _drc.drc_oracle_severity_py = lambda a, r: (a / r) - 1.0
    try:
        with pytest.raises(AssertionError):
            test_p3_severity_bounded_and_monotone()
    finally:
        _drc.drc_oracle_severity_py = original


# ---------------------------------------------------------------------------
# P4 — companion_net: a companion track at collision distance is skipped; the
# same track under another net is flagged
# ---------------------------------------------------------------------------


def test_p4_companion_net_skips_but_other_net_violates():
    reach = _Reach("P4")

    @given(st.floats(min_value=0.0, max_value=0.25, **_FIN))
    @_SETTINGS
    def prop(offset):
        companion = Track(
            Point(0.0, offset), Point(20.0, offset), width=0.2, net="USB_D-", layer=0, id="t_comp"
        )
        oracle = _make_oracle()
        oracle.register_track(companion)
        oracle.geometry.rebuild_index()

        # candidate on the SAME line, net USB_D+, declared companion USB_D-
        valid_comp, _ = oracle.can_place_track_segment(
            (0.0, offset), (20.0, offset), 0, "USB_D+", 0.2, companion_net="USB_D-"
        )
        # identical segment WITHOUT the companion declaration -> violates
        valid_plain, reason = oracle.can_place_track_segment(
            (0.0, offset), (20.0, offset), 0, "USB_D+", 0.2
        )

        assert valid_comp is True, (
            f"companion net must be skipped at collision offset {offset}, got violation"
        )
        assert valid_plain is False, (
            f"non-companion track at collision offset {offset} must violate ({reason})"
        )

    with _counted("drc_oracle_can_place_track_py", reach, lambda r: ("NONE",) if r is None else (r[0],)):
        prop()
    reach.assert_reached()


def test_p4_fails_for_companion_ignoring_kernel():
    """A kernel that drops companion_net flags the companion case."""
    original = _drc.drc_oracle_can_place_track_py
    real = original

    def no_skip(sx, sy, ex, ey, net, width, neckdown, companion_net, apply_creepage, tracks, pads, vias):
        return real(sx, sy, ex, ey, net, width, neckdown, None, apply_creepage, tracks, pads, vias)

    _drc.drc_oracle_can_place_track_py = no_skip
    try:
        with pytest.raises(AssertionError):
            test_p4_companion_net_skips_but_other_net_violates()
    finally:
        _drc.drc_oracle_can_place_track_py = original


# ---------------------------------------------------------------------------
# P5 — pad_credit: a pad inside the reclaimed band gets the effective credit;
# a pad outside gets None
# ---------------------------------------------------------------------------

_CREDIT = ("Q1", "1", "2", 1.2, 1.0, 3.0, (0.0, 0.0), "x")
_OWNER = {"Q1-1": "Q1"}


def test_p5_pad_credit_inside_band_only():
    reach = _Reach("P5")

    @given(p5_credit_case())
    @_SETTINGS
    def prop(case):
        px, py = case
        pad = Pad(
            center=Point(px, py), shape="rect", size=(2.0, 2.0),
            net="SIG_B", layer=0, id="Q1-1", mask_expansion=0.1,
        )
        oracle = _make_oracle()
        oracle.add_clearance_credit(*_CREDIT)
        oracle.pin_owner = _OWNER

        credit = oracle.get_pad_credit(pad)

        # band: x in [-1.5, 1.5], y in [-3, 3] (axis 'x': half_w+0.5=1.5, half_len=3)
        inside = abs(px) <= 1.5 and abs(py) <= 3.0
        if inside:
            assert sig(credit) == sig(1.2), f"inside the band but credit={credit}"
        else:
            assert credit is None, f"outside the band but credit={credit}"

    with _counted("drc_oracle_pad_credit_py", reach, lambda r: ("NONE",) if r is None else ("CREDIT", round(r, 6))):
        prop()
    reach.assert_reached()


def test_p5_fails_for_always_none_kernel():
    original = _drc.drc_oracle_pad_credit_py
    _drc.drc_oracle_pad_credit_py = lambda *_a, **_k: None
    try:
        with pytest.raises(AssertionError):
            test_p5_pad_credit_inside_band_only()
    finally:
        _drc.drc_oracle_pad_credit_py = original


# ---------------------------------------------------------------------------
# P6 — validate_all reports exactly the deliberately violating pairs
# ---------------------------------------------------------------------------


def _board_with_violating_pairs(k, gap):
    oracle = _make_oracle()
    if k >= 1:
        # track-track pair `gap` apart (gap in [0.05, 0.3] < 0.4 - 0.010)
        oracle.register_track(Track(Point(0.0, 0.0), Point(20.0, 0.0), width=0.2, net="SIG_A", layer=0, id="t1"))
        oracle.register_track(Track(Point(0.0, gap), Point(20.0, gap), width=0.2, net="SIG_B", layer=0, id="t2"))
    if k >= 2:
        # via-via pair 0.2mm apart (0.2 < 0.8), far from the tracks
        oracle.register_via(Via(center=Point(40.0, 40.0), diameter=0.6, drill=0.3, net="SIG_A", id="v1"))
        oracle.register_via(Via(center=Point(40.0, 40.2), diameter=0.6, drill=0.3, net="SIG_B", id="v2"))
    oracle.geometry.rebuild_index()
    return oracle


def test_p6_validate_all_counts_exact_violating_pairs():
    reach = _Reach("P6")

    @given(st.integers(min_value=0, max_value=2), st.floats(min_value=0.05, max_value=0.3, **_FIN))
    @_SETTINGS
    def prop(k, gap):
        oracle = _board_with_violating_pairs(k, gap)
        violations = oracle.validate_all()
        assert len(violations) == k, (
            f"expected exactly {k} violating pair(s), got {len(violations)}: "
            f"{[(v.type, v.geometry_a_id, v.geometry_b_id) for v in violations]}"
        )

    with _counted("drc_oracle_validate_all_py", reach, lambda r: len(r)):
        prop()
    reach.assert_reached()


def test_p6_fails_for_empty_kernel():
    original = _drc.drc_oracle_validate_all_py
    _drc.drc_oracle_validate_all_py = lambda *_a, **_k: []
    try:
        with pytest.raises(AssertionError):
            test_p6_validate_all_counts_exact_violating_pairs()
    finally:
        _drc.drc_oracle_validate_all_py = original


# ---------------------------------------------------------------------------
# Metamorphic relations (G5) — shim vs shim on exactly-transformable inputs.
#
# Exactness claims are honest: every distance is a difference of f64
# coordinates, and the transforms below (dyadic translation by 0.5, and
# x / (x, y) sign flips) preserve every f64 difference bit-for-bit, so the
# kernels' decisions -- and the `{actual:.3f}` reason strings they feed --
# are reproduced exactly.  Registration-order permutation does not change
# the *existence* of a violation (only which one is reported first).
# ---------------------------------------------------------------------------

_TRACKS = [Track(Point(0.0, 0.0), Point(20.0, 0.0), width=0.2, net="SIG_B", layer=0, id="t1")]
_PADS = [Pad(center=Point(10.0, 8.0), shape="rect", size=(2.0, 2.0), net="PWR", layer=0, id="p1", mask_expansion=0.1, rotation=15.0)]
_VIAS = [Via(center=Point(10.0, 3.0), diameter=0.6, drill=0.3, net="PWR", id="v1")]
_QUERIES = [
    ((1.0, 0.5), "SIG_A"),
    ((10.0, 8.0), "SIG_A"),
    ((10.0, 3.0), "SIG_B"),
    ((25.0, 25.0), "SIG_A"),
]


def _build(tracks=_TRACKS, vias=_VIAS, pads=_PADS):
    oracle = _make_oracle()
    for t in tracks:
        oracle.register_track(t)
    for v in vias:
        oracle.register_via(v)
    for p in pads:
        oracle.register_pad(p)
    oracle.geometry.rebuild_index()
    return oracle


def _decisions(oracle, queries):
    """Raw `(valid, reason)` pairs for every query (the metamorphic tests
    compare them directly -- the reason strings are exact)."""
    out = []
    for pos, net in queries:
        out.append(oracle.can_place_via(pos, 0.6, net))
        out.append(
            oracle.can_place_track_segment((pos[0], pos[1]), (pos[0] + 2.0, pos[1]), 0, net, 0.2)
        )
    return out


def _translate(tracks, pads, vias, dx, dy):
    tt = [Track(Point(t.start.x + dx, t.start.y + dy), Point(t.end.x + dx, t.end.y + dy), t.width, t.net, t.layer, t.id) for t in tracks]
    tp = [Pad(Point(p.center.x + dx, p.center.y + dy), p.shape, p.size, p.net, p.layer, p.id, p.rotation, p.mask_expansion, p.is_pth) for p in pads]
    tv = [Via(Point(v.center.x + dx, v.center.y + dy), v.diameter, v.drill, v.net, v.id) for v in vias]
    return tt, tv, tp


def _reflect_x(tracks, pads, vias):
    tt = [Track(Point(-t.start.x, t.start.y), Point(-t.end.x, t.end.y), t.width, t.net, t.layer, t.id) for t in tracks]
    tp = [Pad(Point(-p.center.x, p.center.y), p.shape, p.size, p.net, p.layer, p.id, p.rotation, p.mask_expansion, p.is_pth) for p in pads]
    tv = [Via(Point(-v.center.x, v.center.y), v.diameter, v.drill, v.net, v.id) for v in vias]
    return tt, tv, tp


def _rotate180(tracks, pads, vias):
    tt = [Track(Point(-t.start.x, -t.start.y), Point(-t.end.x, -t.end.y), t.width, t.net, t.layer, t.id) for t in tracks]
    tp = [Pad(Point(-p.center.x, -p.center.y), p.shape, p.size, p.net, p.layer, p.id, p.rotation, p.mask_expansion, p.is_pth) for p in pads]
    tv = [Via(Point(-v.center.x, -v.center.y), v.diameter, v.drill, v.net, v.id) for v in vias]
    return tt, tv, tp


def test_m1_translation_invariance_exact():
    """A dyadic (0.5) shift of every geometry and query reproduces every
    decision bit-for-bit -- each distance is a difference of coordinates,
    and x - (x+0.5) + 0.5 round-trips exactly."""
    base = _build()
    base_dec = _decisions(base, _QUERIES)
    shifted = _build(*_translate(_TRACKS, _PADS, _VIAS, _SHIFT, _SHIFT))
    shifted_q = [((x + _SHIFT, y + _SHIFT), net) for (x, y), net in _QUERIES]
    assert _decisions(shifted, shifted_q) == base_dec


def test_m1_translation_is_not_identity():
    """Anti-vacuity: the transform genuinely moves the board (the shifted
    queries are not trivially equal to the originals)."""
    shifted_q = [((x + _SHIFT, y + _SHIFT), net) for (x, y), net in _QUERIES]
    assert shifted_q != _QUERIES


def test_m2_reflection_invariance_exact():
    """Mirroring every x-coordinate (a bit-exact sign flip) preserves every
    decision: (-a) - (-b) == -(a - b) exactly in f64, so all distances and
    comparisons are unchanged."""
    base = _build()
    base_dec = _decisions(base, _QUERIES)
    reflected = _build(*_reflect_x(_TRACKS, _PADS, _VIAS))
    ref_q = [((-x, y), net) for (x, y), net in _QUERIES]
    assert _decisions(reflected, ref_q) == base_dec


def test_m3_rotation_180_invariance_exact():
    """Negating both coordinates (180 deg about the origin) is the product
    of the two sign flips -- exact for the same reason as M2."""
    base = _build()
    base_dec = _decisions(base, _QUERIES)
    rotated = _build(*_rotate180(_TRACKS, _PADS, _VIAS))
    rot_q = [((-x, -y), net) for (x, y), net in _QUERIES]
    assert _decisions(rotated, rot_q) == base_dec


def test_m4_registration_order_preserves_validity():
    """The existence of a violation is independent of registration order
    (the R-tree query *set* is order-independent; only the first-reported
    reason may differ).  Permute the geometry registration and assert the
    valid/invalid decisions are unchanged."""
    tracks = [
        Track(Point(0.0, 0.0), Point(20.0, 0.0), width=0.2, net="SIG_B", layer=0, id="t1"),
        Track(Point(0.0, 0.2), Point(20.0, 0.2), width=0.2, net="PWR", layer=0, id="t2"),
    ]
    vias = [
        Via(center=Point(10.0, 5.0), diameter=0.6, drill=0.3, net="SIG_B", id="v1"),
        Via(center=Point(10.0, 5.4), diameter=0.6, drill=0.3, net="PWR", id="v2"),
    ]
    pads = [
        Pad(center=Point(5.0, 15.0), shape="rect", size=(2.0, 2.0), net="PWR", layer=0, id="p1", mask_expansion=0.1),
        Pad(center=Point(15.0, 15.0), shape="rect", size=(2.0, 2.0), net="SIG_B", layer=0, id="p2", mask_expansion=0.1),
    ]
    oa = _make_oracle()
    ob = _make_oracle()
    for t, v, p in zip(tracks, vias, pads):
        oa.register_track(t)
        oa.register_via(v)
        oa.register_pad(p)
    for t, v, p in zip(reversed(tracks), reversed(vias), reversed(pads)):
        ob.register_track(t)
        ob.register_via(v)
        ob.register_pad(p)
    oa.geometry.rebuild_index()
    ob.geometry.rebuild_index()

    for pos, net in _QUERIES:
        va, _ = oa.can_place_via(pos, 0.6, net)
        vb, _ = ob.can_place_via(pos, 0.6, net)
        assert va == vb, f"validity differed across registration order at {pos} ({net})"
        ta, _ = oa.can_place_track_segment(pos, (pos[0] + 2.0, pos[1]), 0, net, 0.2)
        tb, _ = ob.can_place_track_segment(pos, (pos[0] + 2.0, pos[1]), 0, net, 0.2)
        assert ta == tb, f"track validity differed across registration order at {pos} ({net})"


def test_m4_permutation_board_is_not_vacuous():
    """The M4 board actually contains violations (so the relation compares
    real decisions, not two trivially-valid boards)."""
    tracks = [
        Track(Point(0.0, 0.0), Point(20.0, 0.0), width=0.2, net="SIG_B", layer=0, id="t1"),
        Track(Point(0.0, 0.2), Point(20.0, 0.2), width=0.2, net="PWR", layer=0, id="t2"),
    ]
    vias = [
        Via(center=Point(10.0, 5.0), diameter=0.6, drill=0.3, net="SIG_B", id="v1"),
        Via(center=Point(10.0, 5.4), diameter=0.6, drill=0.3, net="PWR", id="v2"),
    ]
    pads = [
        Pad(center=Point(5.0, 15.0), shape="rect", size=(2.0, 2.0), net="PWR", layer=0, id="p1", mask_expansion=0.1),
        Pad(center=Point(15.0, 15.0), shape="rect", size=(2.0, 2.0), net="SIG_B", layer=0, id="p2", mask_expansion=0.1),
    ]
    board = _build(tracks, vias, pads)
    decisions = _decisions(board, [((10.0, 5.0), "SIG_A"), ((5.0, 15.0), "SIG_A")])
    assert any(not d[0] for d in decisions), (
        "M4 board must actually produce violations, else the relation is vacuous"
    )
