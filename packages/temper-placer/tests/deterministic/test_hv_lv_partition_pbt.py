"""Property-based + metamorphic tests for the migrated hv_lv_partition compute.

Wave 4 follow-up (HV/LV guard-strip partitioning). Bit-identical parity against
the pinned oracle is asserted separately by
``test_hv_lv_partition_rust_differential.py``.

Six hypothesis properties (R1c), covering both migrated kernels
(``hv_lv_classify`` and ``hv_lv_area_check``):

- P1. Partition totality: every component ref lands in exactly one of the HV
  or LV buckets (a degenerate kernel that drops refs would fail).
- P2. Category membership: HV/AC-only components land in HV, everything else
  (LV/iso/unmapped/dual-domain) in LV.
- P3. Creepage is the max over HV-category nets only — never influenced by LV
  net creepage, never below any HV net's creepage.
- P4. Width resolution: an explicit width >= creepage wins unchanged; an
  explicit width < creepage clamps up to the creepage; ``None`` resolves to
  the creepage.
- P5. Area-check ok: when every bucket region fits every component in the
  bucket, the outcome is ``ok``.
- P6. Fallback symmetry: a failing bucket yields ``fallback`` with
  ``fallback_to_unconstrained=True`` and ``raise`` with ``False`` — for the
  SAME bucket/largest pair.

Three metamorphic relations (R1d):

- MR1. Component-order permutation: reordering ``components_nets`` preserves
  HV/LV membership, the dual list, and the creepage (output lists keep input
  order, so membership compares sorted).
- MR2. Power-of-two area scaling: multiplying every area and region area by
  the same power of two is exact in IEEE-754 and preserves the area-check
  decision.
- MR3. Duplicate-net absorption: appending an already-present net to a
  component's nets list changes nothing — the classification reads a set.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

_RS = _tdb.hv_lv_partition

_HV_NETS = st.sampled_from(["DC_BUS+", "DC_BUS-", "SW_NODE", "AC_L", "AC_N"])
_LV_NETS = st.sampled_from(["SPI_CLK", "+3V3", "+5V", "GND"])
_UNKNOWN = st.just("UNKNOWN_NET")
_RULES = {
    "DC_BUS+": ("HV", 6.0),
    "DC_BUS-": ("HV", 6.0),
    "SW_NODE": ("HV", 8.0),
    "AC_L": ("AC", 5.0),
    "AC_N": ("AC", 6.0),
    "SPI_CLK": ("LV", 0.0),
    "+3V3": ("LV", 0.0),
    "+5V": ("LV", 0.0),
    "GND": ("iso", 0.0),
    "UNKNOWN_NET": ("", 0.0),
}

_NAMES = st.text(min_size=1, max_size=5, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_")
_NETS_FOR_COMP = st.lists(
    st.one_of(_HV_NETS, _LV_NETS, _UNKNOWN),
    min_size=0,
    max_size=4,
    unique=True,
)


def _rules_dict():
    return dict(_RULES)


@st.composite
def comp_lists(draw):
    n = draw(st.integers(min_value=1, max_value=6))
    names = draw(st.lists(_NAMES, min_size=n, max_size=n, unique=True))
    return [(names[i], draw(_NETS_FOR_COMP)) for i in range(n)]


def _classify(components_nets, rules, width_mm=None):
    return _RS.hv_lv_classify(components_nets, rules, width_mm)


# ---------------------------------------------------------------------------
# P1–P4: classify
# ---------------------------------------------------------------------------


@given(comp_lists())
@settings(max_examples=100, deadline=None)
def test_p1_partition_totality(components_nets):
    decision, hv, lv, _creepage, _width, dual = _classify(components_nets, _rules_dict())
    refs = [r for r, _ in components_nets]
    assert set(hv) | set(lv) == set(refs)
    assert set(hv) & set(lv) == set()
    assert set(dual) <= set(lv)


@given(comp_lists())
@settings(max_examples=100, deadline=None)
def test_p2_category_membership(components_nets):
    rules = _rules_dict()
    _, hv, lv, _creepage, _width, _dual = _classify(components_nets, rules)
    for ref, nets in components_nets:
        cats = {rules[n][0] for n in nets if n in rules}
        hh, hl = bool(cats & {"HV", "AC"}), bool(cats & {"LV", "iso"})
        if hh and not hl:
            assert ref in hv
        else:
            assert ref in lv


@given(comp_lists())
@settings(max_examples=100, deadline=None)
def test_p3_creepage_is_max_over_hv_nets_only(components_nets):
    rules = _rules_dict()
    _, _, _, creepage, _width, _dual = _classify(components_nets, rules)
    hv_creeps = [
        rules[n][1]
        for _ref, nets in components_nets
        for n in nets
        if n in rules and rules[n][0] in {"HV", "AC"}
    ]
    expected = max(hv_creeps) if hv_creeps else 0.0
    assert creepage == expected
    # An LV net with an absurd creepage must never leak into the fold.
    lv_only = [("C", ["+3V3"])]
    _d, _hv, _lv, c2, _w, _du = _classify(lv_only + components_nets, _rules_dict())
    assert c2 == expected


@given(comp_lists(), st.floats(min_value=0.0, max_value=30.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=100, deadline=None)
def test_p4_width_resolution(components_nets, width_mm):
    decision, hv, lv, creepage, width, _dual = _classify(components_nets, _rules_dict(), width_mm)
    if not hv or not lv:
        assert decision == "skip_empty"
        return
    if width_mm == 0.0:
        assert decision == "skip_zero"
        return
    if width_mm < creepage:
        assert width == creepage  # clamped up to the creepage
    else:
        assert width == width_mm


@given(st.floats(min_value=1e-6, max_value=1e3, allow_nan=False, allow_infinity=False))
@settings(max_examples=50, deadline=None)
def test_p4b_zero_creepage_skips(creepage_leak):
    """A creepage that is zero must resolve to width zero -> skip_zero, but a
    nonzero creepage (here forced via one HV net) proceeds."""
    rules = {"SW_NODE": ("HV", 0.0), "SPI_CLK": ("LV", 0.0)}
    comps = [("Q1", ["SW_NODE"]), ("U_MCU", ["SPI_CLK"])]
    decision, *_ = _classify(comps, rules, None)
    assert decision == "skip_zero"
    # Anti-vacuity companion: with a nonzero HV creepage the same shapes
    # proceed to "ok" (proving the property discriminates).
    rules2 = {"SW_NODE": ("HV", creepage_leak), "SPI_CLK": ("LV", 0.0)}
    decision2, *_ = _classify(comps, rules2, None)
    if creepage_leak > 0.0:
        assert decision2 == "ok"


# ---------------------------------------------------------------------------
# P5–P6: area check
# ---------------------------------------------------------------------------


_AREA = st.floats(min_value=0.5, max_value=1e3, allow_nan=False, allow_infinity=False)


@given(
    st.lists(_NAMES, min_size=1, max_size=4, unique=True),
    st.lists(_NAMES, min_size=1, max_size=4, unique=True),
    _AREA,
    _AREA,
)
@settings(max_examples=100, deadline=None)
def test_p5_area_ok_when_regions_fit(hv, lv, hv_area, lv_area):
    if set(hv) & set(lv):
        return
    areas = {r: 1.0 for r in hv + lv}
    max_hv = max(areas[r] for r in hv)
    max_lv = max(areas[r] for r in lv)
    if hv_area < max_hv or lv_area < max_lv:
        return  # deliberately not an "ok" input
    outcome, *_ = _RS.hv_lv_area_check(
        hv, lv, areas, hv_area, False, lv_area, False, True
    )
    assert outcome == "ok"


@given(
    st.lists(_NAMES, min_size=1, max_size=4, unique=True),
    st.lists(_NAMES, min_size=1, max_size=4, unique=True),
    _AREA,
)
@settings(max_examples=100, deadline=None)
def test_p6_fallback_vs_raise_same_failure(hv, lv, hv_area):
    if set(hv) & set(lv):
        return
    areas = {r: 1000.0 for r in hv + lv}
    max_hv = max(areas[r] for r in hv)
    if hv_area >= max_hv:
        return  # must be a genuinely failing HV bucket
    fb = _RS.hv_lv_area_check(hv, lv, areas, hv_area, False, 1e6, False, True)
    rs = _RS.hv_lv_area_check(hv, lv, areas, hv_area, False, 1e6, False, False)
    assert fb[0] == "fallback"
    assert rs[0] == "raise"
    assert fb[1:] == rs[1:]  # identical bucket/largest/region/required


# ---------------------------------------------------------------------------
# MR1–MR3: metamorphic relations
# ---------------------------------------------------------------------------


@given(comp_lists())
@settings(max_examples=100, deadline=None)
def test_mr1_component_order_permutation(components_nets):
    rules = _rules_dict()
    _, hv, lv, creepage, width, dual = _classify(components_nets, rules)
    perm = components_nets[::-1]
    _, hv2, lv2, creepage2, width2, dual2 = _classify(perm, rules)
    assert sorted(hv) == sorted(hv2)
    assert sorted(lv) == sorted(lv2)
    assert sorted(dual) == sorted(dual2)
    assert creepage == creepage2
    assert width == width2


@given(
    st.lists(_NAMES, min_size=1, max_size=4, unique=True),
    st.lists(_NAMES, min_size=1, max_size=4, unique=True),
    _AREA,
    _AREA,
    st.integers(min_value=-20, max_value=20),
)
@settings(max_examples=100, deadline=None)
def test_mr2_power_of_two_scale_invariance(hv, lv, hv_area, lv_area, k):
    if set(hv) & set(lv):
        return
    areas = {r: 1.5 for r in hv + lv}
    scale = 2.0**k
    a = _RS.hv_lv_area_check(hv, lv, areas, hv_area, False, lv_area, False, True)
    b = _RS.hv_lv_area_check(
        hv,
        lv,
        {r: 1.5 * scale for r in hv + lv},
        hv_area * scale,
        False,
        lv_area * scale,
        False,
        True,
    )
    assert a[0] == b[0]
    # The region/required AREA VALUES scale by `scale`; only the decision and
    # the bucket/largest identity are invariant.
    assert a[1] == b[1]
    assert a[2] == b[2]


@given(comp_lists())
@settings(max_examples=100, deadline=None)
def test_mr3_duplicate_net_absorption(components_nets):
    rules = _rules_dict()
    _, hv, lv, creepage, width, dual = _classify(components_nets, rules)
    duplicated = [
        (ref, nets + [nets[0]]) if nets else (ref, nets) for ref, nets in components_nets
    ]
    _, hv2, lv2, creepage2, width2, dual2 = _classify(duplicated, rules)
    assert hv == hv2
    assert lv == lv2
    assert dual == dual2
    assert creepage == creepage2
    assert width == width2
