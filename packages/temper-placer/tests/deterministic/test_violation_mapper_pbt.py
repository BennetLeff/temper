"""Property-based + metamorphic tests for the migrated violation-mapping
kernel.

Wave 4, Phase 5 (deterministic hubs slice). These properties exercise the
migrated ``temper_design_bundle_python.deterministic_hubs.map_violation_kernel``
through the ``temper_placer.deterministic.feedback.violation_mapper`` shim;
bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_violation_mapper_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Totality: any violation maps without raising and always yields
  ``MappedViolation``-shaped output.
- P2. Component extraction: every ``of <REF>`` / ``Pad <REF>-`` / ``Pad
  <REF>.`` token that names a known ref appears in ``components``.
- P3. Unknown-ref filtering: no unknown ref ever appears in ``components``.
- P4. Via/PTH flags: ``Via``/``PTH`` substrings (any case) set the flags.
- P5. Zone containment: a position strictly inside one zone maps to that zone
  (first-containing zone in insertion order).

Three metamorphic relations (R1d):

- MR1. Item-order invariance: reordering a violation's items preserves the
  mapped components/flags (the extraction is a per-item fold with union).
- MR2. Description independence: an unchanged position/type with a
  description that carries no clearance pattern leaves required/actual
  unchanged.
- MR3. Case invariance: case-swapped ``of``/``Pad``/``Via``/``PTH`` tokens
  map identically (IGNORECASE).
"""

from __future__ import annotations

import re

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from temper_placer.deterministic.feedback.violation_mapper import (
    DRCViolation,
    ViolationComponentMapper,
)

_REFS = ("Q2", "U_GATE", "D1", "R12", "C4")

_KNOWN_REFS = frozenset(_REFS)


class _NetlistStub:
    def __init__(self):
        self.components = [_Ref(r) for r in _REFS]


class _Ref:
    def __init__(self, ref):
        self.ref = ref


_MAPPER = ViolationComponentMapper(_NetlistStub())


_item_st = st.text(
    alphabet=st.sampled_from(
        list(" ofPadViaPTHQ2U_GATED1R12C4-_.()0123456789XF.CuIn1.B,LMS") + [" "]
    ),
    min_size=0,
    max_size=40,
)


def _make_violation(items, pos=None, description=""):
    return DRCViolation(
        type="clearance", items=list(items), pos=pos, description=description
    )


def _known_refs_in(item):
    found = set()
    for pattern in (
        re.compile(r"of ([A-Za-z0-9_]+)", re.IGNORECASE),
        re.compile(r"pad ([A-Za-z0-9_]+)-", re.IGNORECASE),
        re.compile(r"pad ([A-Za-z0-9_]+)\.", re.IGNORECASE),
    ):
        m = pattern.search(item)
        if m and m.group(1) in _KNOWN_REFS:
            found.add(m.group(1))
    return found


class TestProperties:
    @given(st.lists(_item_st, min_size=0, max_size=5))
    @settings(max_examples=100, deadline=None)
    def test_p1_totality(self, items):
        result = _MAPPER.map_violation(_make_violation(items))
        assert isinstance(result.components, list)
        assert isinstance(result.involves_via, bool)
        assert isinstance(result.involves_pth, bool)

    @given(st.lists(_item_st, min_size=0, max_size=5))
    @settings(max_examples=100, deadline=None)
    def test_p2_all_known_refs_extracted(self, items):
        expected = set()
        for item in items:
            expected |= _known_refs_in(item)
        result = _MAPPER.map_violation(_make_violation(items))
        assert expected.issubset(set(result.components))

    @given(st.lists(_item_st, min_size=0, max_size=5))
    @settings(max_examples=100, deadline=None)
    def test_p3_no_unknown_refs(self, items):
        result = _MAPPER.map_violation(_make_violation(items))
        assert set(result.components).issubset(_KNOWN_REFS)

    @given(st.lists(_item_st, min_size=0, max_size=5))
    @settings(max_examples=100, deadline=None)
    def test_p4_via_pth_flags(self, items):
        text = " ".join(items).lower()
        result = _MAPPER.map_violation(_make_violation(items))
        assert result.involves_via == ("via" in text)
        assert result.involves_pth == ("pth" in text)

    @given(st.floats(0.0, 100.0), st.floats(0.0, 100.0))
    @settings(max_examples=60, deadline=None)
    def test_p5_zone_containment(self, x, y):
        zone_config = {"HV": {"bounds": [(0, 0), (50, 50)]}, "LV": {"bounds": [(0, 0), (100, 100)]}}
        mapper = ViolationComponentMapper(_NetlistStub(), zone_config)
        result = mapper.map_violation(_make_violation([], pos=(x, y)))
        if x <= 50.0 and y <= 50.0:
            assert result.zone == "HV"
        else:
            assert result.zone == "LV"


class TestMetamorphic:
    @given(st.lists(_item_st, min_size=2, max_size=5))
    @settings(max_examples=80, deadline=None)
    def test_mr1_item_order_invariance(self, items):
        v1 = _MAPPER.map_violation(_make_violation(items))
        v2 = _MAPPER.map_violation(_make_violation(list(reversed(items))))
        assert v1.components == v2.components
        assert v1.involves_via == v2.involves_via
        assert v1.involves_pth == v2.involves_pth

    @given(_item_st)
    @settings(max_examples=80, deadline=None)
    def test_mr2_description_independence(self, item):
        assume("mm" not in item and "<" not in item and "clearance" not in item.lower())
        base = _MAPPER.map_violation(
            DRCViolation(type="clearance", items=[item], pos=(10.0, 10.0))
        )
        with_desc = _MAPPER.map_violation(
            DRCViolation(type="clearance", items=[item], pos=(10.0, 10.0), description=item)
        )
        assert with_desc.required_clearance == base.required_clearance
        assert with_desc.actual_clearance == base.actual_clearance
        assert with_desc.zone == base.zone

    @given(st.lists(_item_st, min_size=1, max_size=4))
    @settings(max_examples=80, deadline=None)
    def test_mr3_case_invariance(self, items):
        def swap_case(s):
            return "".join(c.upper() if c.islower() else c.lower() for c in s)

        base = _MAPPER.map_violation(_make_violation(items))
        swapped_items = [swap_case(i) for i in items]
        swapped = _MAPPER.map_violation(_make_violation(swapped_items))
        assert swapped.components == base.components
        assert swapped.involves_via == base.involves_via
        assert swapped.involves_pth == base.involves_pth
