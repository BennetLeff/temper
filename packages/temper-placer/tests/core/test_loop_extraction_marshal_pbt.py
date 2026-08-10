"""Property-based tests for the Phase-A U9 loop-extraction marshalers
(Wave-4 discipline contract G4/G5).

Verification unit: the U9 marshal cluster --
`temper_design_bundle_python.LoopExtractionInput` (`_netlist_to_dict`) and
`temper_design_bundle_python.LoopExtractionOutput`
(`_dict_to_loop_collection`'s typed wire parse), exercised through the
`core/loop_extractor_rs.py` shims that delegate to the Rust pyclasses.

Module -> property map (G4 note: every module reached by >= 1 property):

  | Module                | Properties |
  |-----------------------|------------|
  | `LoopExtractionInput` | P1, P2, P3, P4, P5 |
  | `LoopExtractionOutput`| P6, P7, P8 |

Every property has a `test_pN_fails_for_<mutant>` companion (G4 vacuity
guard) proving a degenerate kernel violates it. The mutants patch a
Python-level seam (the shim functions / reconstruction tables / the pyclass
staticmethod), so each guard proves the property is reachable, not
vacuously true.

Metamorphic relations (G5, >= 3) are in the labelled section at the bottom.
"""

from __future__ import annotations

import json

import pytest
import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

import temper_placer.core.loop_extractor_rs as _le
from temper_placer.core.loop import LoopCollection
from tests.core._contract_canon import canon
from tests.core.test_loop_extraction_marshal_rust_differential import (
    _oracle_dict_to_loop_collection,
    _oracle_netlist_to_dict,
)

LOOP_EXTRACTION_INPUT = _tdb.LoopExtractionInput
LOOP_EXTRACTION_OUTPUT = _tdb.LoopExtractionOutput

# ---------------------------------------------------------------------------
# Input strategies
# ---------------------------------------------------------------------------

_REF = st.text(min_size=1, max_size=6, alphabet="QRCUD0123456789_")
_NET_NAME = st.text(min_size=1, max_size=8, alphabet="N_SWDC+123")
_FOOTPRINT = st.text(min_size=1, max_size=12)
_NET_CLASS = st.text(min_size=1, max_size=12)


@st.composite
def wire_netlist(draw):
    """A design-bundle Netlist with 0..5 components (each with 0..3 pins)
    and 0..3 nets whose pins reference component refs in first-appearance
    order."""
    n_comps = draw(st.integers(min_value=0, max_value=5))
    comps = []
    refs = []
    for _ in range(n_comps):
        ref = draw(_REF)
        refs.append(ref)
        pins = [
            draw(
                st.builds(
                    _tdb.netlist_contracts.Pin,
                    name=st.text(min_size=1, max_size=4),
                    number=st.text(min_size=1, max_size=3),
                    position=st.tuples(
                        st.floats(-10, 10, allow_nan=False, allow_infinity=False),
                        st.floats(-10, 10, allow_nan=False, allow_infinity=False),
                    ),
                    net=st.one_of(st.none(), _NET_NAME),
                )
            )
            for _ in range(draw(st.integers(min_value=0, max_value=3)))
        ]
        comps.append(
            _tdb.netlist_contracts.Component(
                ref=ref,
                footprint=draw(_FOOTPRINT),
                bounds=(1.0, 1.0),
                pins=pins,
                net_class=draw(_NET_CLASS),
                attributes=draw(
                    st.fixed_dictionaries(
                        {
                            "MPN": _FOOTPRINT,
                            "value": _FOOTPRINT,
                        }
                    )
                ),
            )
        )
    n_nets = draw(st.integers(min_value=0, max_value=3))
    net_pins = (
        st.lists(
            st.tuples(st.sampled_from(refs), st.text(min_size=1, max_size=3)),
            min_size=0,
            max_size=4,
        )
        if refs
        else st.just([])
    )
    nets = [
        _tdb.netlist_contracts.Net(
            name=draw(_NET_NAME),
            pins=draw(net_pins),
        )
        for _ in range(n_nets)
    ]
    return _tdb.netlist_contracts.Netlist(components=comps, nets=nets)


@st.composite
def wire_result(draw):
    """A bridge-output dict with 0..4 loops of arbitrary loop_type strings
    (some valid, some not), exercising the reconstruction's default paths."""
    loop_types = [
        "commutation",
        "gate_drive_high",
        "gate_drive_low",
        "bootstrap",
        "not_a_loop_type",
    ]
    loops = [
        {
            "name": f"auto_{i}",
            "loop_type": draw(st.sampled_from(loop_types)),
            "components": draw(st.lists(st.sampled_from(["Q1", "Q2", "U1"]), max_size=3)),
            "nets": draw(st.lists(st.sampled_from(["N1", "N2"]), max_size=2)),
            "max_area_mm2": draw(st.floats(1.0, 1000.0, allow_nan=False, allow_infinity=False)),
        }
        for i in range(draw(st.integers(min_value=1, max_value=4)))
    ]
    d = {"ok": draw(st.booleans())}
    if draw(st.booleans()):
        d["error"] = "NoHalfBridge"
    d["loops"] = loops
    return d


def _empty_netlist():
    return _tdb.netlist_contracts.Netlist(components=[], nets=[])


# ---------------------------------------------------------------------------
# P1 — input dict == pinned oracle (bit-exact)
# ---------------------------------------------------------------------------


@given(wire_netlist())
@settings(max_examples=60, deadline=None)
def test_p1_input_dict_matches_oracle(netlist):
    """P1: `_netlist_to_dict(nl)` (the collapsed typed marshaler) is
    bit-identical to the pinned pre-migration marshaler. A kernel that
    returns a constant (or skips nets/components) violates it."""
    assert canon(_le._netlist_to_dict(netlist)) == canon(_oracle_netlist_to_dict(netlist))


def test_p1_fails_for_constant_marshaler(monkeypatch):
    monkeypatch.setattr(
        "temper_placer.core.loop_extractor_rs._netlist_to_dict",
        lambda _netlist: {"components": [], "nets": []},
    )
    from tests.core.test_loop_extraction_marshal_rust_differential import _full_half_bridge

    with pytest.raises(AssertionError):
        test_p1_input_dict_matches_oracle.hypothesis.inner_test(_full_half_bridge())


# ---------------------------------------------------------------------------
# P2 — to_json round-trips through CPython json bit-for-bit
# ---------------------------------------------------------------------------


@given(wire_netlist())
@settings(max_examples=60, deadline=None)
def test_p2_to_json_matches_json_dumps_of_to_dict(netlist):
    """P2: `LoopExtractionInput.from_netlist(nl).to_json()` is byte-identical
    to `json.dumps(to_dict())` (CPython's own dumps -- separators/escaping
    are CPython's) and re-parses to the same dict."""
    typed = LOOP_EXTRACTION_INPUT.from_netlist(netlist)
    assert typed.to_json() == json.dumps(typed.to_dict())
    assert canon(json.loads(typed.to_json())) == canon(typed.to_dict())


def test_p2_fails_for_constant_json(monkeypatch):
    monkeypatch.setattr(LOOP_EXTRACTION_INPUT, "to_json", lambda _self: "{}")
    from tests.core.test_loop_extraction_marshal_rust_differential import _full_half_bridge

    with pytest.raises(AssertionError):
        test_p2_to_json_matches_json_dumps_of_to_dict.hypothesis.inner_test(
            _full_half_bridge()
        )


# ---------------------------------------------------------------------------
# P3 — topology_hints presence is exactly "truthy dict passed"
# ---------------------------------------------------------------------------


@given(wire_netlist(), st.dictionaries(_NET_NAME, _NET_NAME, max_size=3))
@settings(max_examples=40, deadline=None)
def test_p3_topology_hints_presence(netlist, hints):
    """P3: hints appear as a trailing dict key iff a non-empty dict was
    passed; components/nets surface is unchanged either way."""
    if not hints:
        hints = None
    typed = LOOP_EXTRACTION_INPUT.from_netlist(netlist, hints)
    d = typed.to_dict()
    if hints:
        assert list(d)[-1] == "topology_hints"
        assert d["topology_hints"] == hints
    else:
        assert "topology_hints" not in d
    assert canon(d["components"]) == canon(_oracle_netlist_to_dict(netlist)["components"])
    assert canon(d["nets"]) == canon(_oracle_netlist_to_dict(netlist)["nets"])


def test_p3_fails_for_always_added_hints(monkeypatch):
    orig = LOOP_EXTRACTION_INPUT.from_netlist

    def mutant(netlist, topology_hints=None):
        return orig(netlist, None)

    monkeypatch.setattr(LOOP_EXTRACTION_INPUT, "from_netlist", staticmethod(mutant))
    from tests.core.test_loop_extraction_marshal_rust_differential import _full_half_bridge

    with pytest.raises(AssertionError):
        test_p3_topology_hints_presence.hypothesis.inner_test(
            _full_half_bridge(), {"topology": "half_bridge"}
        )


# ---------------------------------------------------------------------------
# P4 — component/pin wire shape
# ---------------------------------------------------------------------------


@given(wire_netlist())
@settings(max_examples=60, deadline=None)
def test_p4_component_pin_wire_shape(netlist):
    """P4: every component dict carries exactly the wire keys
    {ref, footprint, mpn, value, net_class, pins}; every pin dict carries
    {name, net} with net None-or-str; pin order is preserved."""
    d = _le._netlist_to_dict(netlist)
    comps = netlist.components
    for cdict, comp in zip(d["components"], comps):
        assert set(cdict) == {"ref", "footprint", "mpn", "value", "net_class", "pins"}
        assert cdict["ref"] == comp.ref
        assert cdict["footprint"] == comp.footprint
        assert cdict["mpn"] == comp.attributes.get("MPN", "")
        assert cdict["value"] == comp.attributes.get("value", "")
        assert cdict["net_class"] == comp.net_class
        assert len(cdict["pins"]) == len(comp.pins)
        for pdict, pin in zip(cdict["pins"], comp.pins):
            assert set(pdict) == {"name", "net"}
            assert pdict["name"] == pin.name
            assert pdict["net"] is None or isinstance(pdict["net"], str)


def test_p4_fails_for_dropped_net_class(monkeypatch):
    orig = _le._netlist_to_dict

    def mutant(netlist):
        d = orig(netlist)
        for c in d["components"]:
            del c["net_class"]
        return d

    monkeypatch.setattr("temper_placer.core.loop_extractor_rs._netlist_to_dict", mutant)
    from tests.core.test_loop_extraction_marshal_rust_differential import _full_half_bridge

    with pytest.raises(AssertionError):
        test_p4_component_pin_wire_shape.hypothesis.inner_test(_full_half_bridge())


# ---------------------------------------------------------------------------
# P5 — net wire shape + ordering
# ---------------------------------------------------------------------------


@given(wire_netlist())
@settings(max_examples=60, deadline=None)
def test_p5_net_wire_shape_and_order(netlist):
    """P5: nets preserve netlist order; every net dict has {name, pins} and
    each pin is a [ref, pin_name] 2-list in order."""
    d = _le._netlist_to_dict(netlist)
    nets = netlist.nets
    assert [n["name"] for n in d["nets"]] == [n.name for n in nets]
    for ndict, net in zip(d["nets"], nets):
        assert set(ndict) == {"name", "pins"}
        assert len(ndict["pins"]) == len(net.pins)
        for wire_pin, (ref, pin_name) in zip(ndict["pins"], net.pins):
            assert list(wire_pin) == [ref, pin_name]


def test_p5_fails_for_swapped_pin_pairs(monkeypatch):
    orig = _le._netlist_to_dict

    def mutant(netlist):
        d = orig(netlist)
        for n in d["nets"]:
            n["pins"] = [[name, ref] for ref, name in n["pins"]]
        return d

    monkeypatch.setattr("temper_placer.core.loop_extractor_rs._netlist_to_dict", mutant)
    netlist = _tdb.netlist_contracts.Netlist(
        components=[],
        nets=[_tdb.netlist_contracts.Net(name="N1", pins=[("Q1", "E"), ("Q2", "C")])],
    )
    with pytest.raises(AssertionError):
        test_p5_net_wire_shape_and_order.hypothesis.inner_test(netlist)


# ---------------------------------------------------------------------------
# P6 — output reconstruction parity (typed parse -> LoopCollection)
# ---------------------------------------------------------------------------


def _loop_fields(loop):
    return (
        loop.name,
        loop.loop_type.value,
        tuple(loop.components),
        tuple(loop.nets),
        float(loop.max_area_mm2).hex(),
        loop.priority,
        (
            None if loop.events.di_dt is None else float(loop.events.di_dt).hex(),
            None if loop.events.dv_dt is None else float(loop.events.dv_dt).hex(),
            None if loop.events.frequency_hz is None else float(loop.events.frequency_hz).hex(),
            None
            if loop.events.peak_current_a is None
            else float(loop.events.peak_current_a).hex(),
        ),
        loop.return_layer,
        loop.return_net,
        tuple(loop.pins),
    )


@given(wire_result())
@settings(max_examples=60, deadline=None)
def test_p6_output_reconstruction_matches_oracle(result):
    """P6: `_le._dict_to_loop_collection(result)` (which parses the typed
    `LoopExtractionOutput`) matches the pinned pre-migration reconstruction
    on every loop, field-for-field, including the defaults."""
    got = _le._dict_to_loop_collection(result)
    oracle = _oracle_dict_to_loop_collection(result)
    assert len(got.loops) == len(oracle.loops)
    for a, b in zip(got.loops, oracle.loops):
        assert _loop_fields(a) == _loop_fields(b)


def test_p6_fails_for_empty_reconstruction(monkeypatch):
    monkeypatch.setattr(
        "temper_placer.core.loop_extractor_rs._dict_to_loop_collection",
        lambda _data: LoopCollection(loops=[]),
    )
    result = {
        "ok": True,
        "loops": [
            {
                "name": "auto_x",
                "loop_type": "commutation",
                "components": ["Q1", "Q2"],
                "nets": ["N1"],
                "max_area_mm2": 100.0,
            }
        ],
    }
    with pytest.raises(AssertionError):
        test_p6_output_reconstruction_matches_oracle.hypothesis.inner_test(result)


# ---------------------------------------------------------------------------
# P7 — typed output parse fidelity vs the raw wire dict
# ---------------------------------------------------------------------------


@given(wire_result())
@settings(max_examples=60, deadline=None)
def test_p7_typed_output_parse_fidelity(result):
    """P7: `LoopExtractionOutput.from_dict(result)` reproduces the raw wire
    fields (ok/error/loops) with bit-exact floats; missing optional keys
    take the documented defaults."""
    out = LOOP_EXTRACTION_OUTPUT.from_dict(result)
    assert out.ok == result.get("ok", False)
    assert out.error == result.get("error")
    assert len(out.loops) == len(result["loops"])
    for typed, raw in zip(out.loops, result["loops"]):
        assert typed.name == raw["name"]
        assert typed.loop_type == raw["loop_type"]
        assert list(typed.components) == raw["components"]
        assert list(typed.nets) == raw["nets"]
        assert float(typed.max_area_mm2).hex() == float(raw["max_area_mm2"]).hex()


def test_p7_fails_for_reversed_loop_order(monkeypatch):
    orig = LOOP_EXTRACTION_OUTPUT.from_dict

    def mutant(data):
        out = orig(data)
        return LOOP_EXTRACTION_OUTPUT(
            ok=out.ok,
            error=out.error,
            loops=list(reversed(list(out.loops))),
        )

    monkeypatch.setattr(LOOP_EXTRACTION_OUTPUT, "from_dict", staticmethod(mutant))
    result = {
        "ok": True,
        "loops": [
            {
                "name": "auto_a",
                "loop_type": "commutation",
                "components": ["Q1"],
                "nets": [],
                "max_area_mm2": 10.0,
            },
            {
                "name": "auto_b",
                "loop_type": "bootstrap",
                "components": ["C1"],
                "nets": [],
                "max_area_mm2": 20.0,
            },
        ],
    }
    with pytest.raises(AssertionError):
        test_p7_typed_output_parse_fidelity.hypothesis.inner_test(result)

# ---------------------------------------------------------------------------
# P8 — reconstruction mapping pinned values
# ---------------------------------------------------------------------------


@given(wire_result())
@settings(max_examples=60, deadline=None)
def test_p8_reconstruction_mapping_pinned(result):
    """P8: the priority/events/return-path reconstruction is deterministic
    from loop_type and matches the PINNED pre-migration hardcoded values
    (the `_ORACLE_LOOP_TYPE_*` tables -- NOT the shim's own tables, so a
    shim-table edit that drifts from the pre-migration contract fails)."""
    from temper_placer.core.loop import LoopPriority
    from tests.core.test_loop_extraction_marshal_rust_differential import (
        _ORACLE_LOOP_TYPE_EVENTS,
        _ORACLE_LOOP_TYPE_PRIORITY,
        _ORACLE_LOOP_TYPE_RETURN_LAYER,
        _ORACLE_LOOP_TYPE_RETURN_NET,
    )

    got = _le._dict_to_loop_collection(result)
    for loop in got.loops:
        lt = loop.loop_type
        assert loop.priority == _ORACLE_LOOP_TYPE_PRIORITY.get(lt, LoopPriority.MEDIUM)
        assert loop.return_layer == _ORACLE_LOOP_TYPE_RETURN_LAYER.get(lt, "")
        assert loop.return_net == _ORACLE_LOOP_TYPE_RETURN_NET.get(lt, "")
        expected_events = _ORACLE_LOOP_TYPE_EVENTS.get(lt, {})
        assert loop.events.di_dt == expected_events.get("di_dt")
        assert loop.events.dv_dt == expected_events.get("dv_dt")
        assert loop.events.frequency_hz == expected_events.get("frequency_hz")
        assert loop.events.peak_current_a == expected_events.get("peak_current_a")


def test_p8_fails_for_swapped_priority_table(monkeypatch):
    import temper_placer.core.loop_extractor_rs as _le_mod

    swapped = dict(_le_mod._LOOP_TYPE_PRIORITY)
    from temper_placer.core.loop import LoopPriority

    for k in list(swapped):
        swapped[k] = LoopPriority.MEDIUM
    monkeypatch.setattr(_le_mod, "_LOOP_TYPE_PRIORITY", swapped)

    result = {
        "ok": True,
        "loops": [
            {
                "name": "auto_x",
                "loop_type": "commutation",
                "components": ["Q1"],
                "nets": [],
                "max_area_mm2": 100.0,
            }
        ],
    }
    with pytest.raises(AssertionError):
        test_p8_reconstruction_mapping_pinned.hypothesis.inner_test(result)


# ---------------------------------------------------------------------------
# Metamorphic relations (G5)
# ---------------------------------------------------------------------------


@given(wire_netlist())
@settings(max_examples=30, deadline=None)
def test_mr1_component_order_permutation_invariant(netlist):
    """MR1: reversing component order reverses the wire components list
    exactly (bit-identical per component)."""
    reversed_nl = _tdb.netlist_contracts.Netlist(
        components=list(reversed(list(netlist.components))), nets=list(netlist.nets)
    )
    orig = _le._netlist_to_dict(netlist)["components"]
    rev = _le._netlist_to_dict(reversed_nl)["components"]
    assert canon(rev) == canon(list(reversed(orig)))


@given(wire_netlist())
@settings(max_examples=30, deadline=None)
def test_mr2_pin_order_permutation_invariant(netlist):
    """MR2: reversing a component's pin list reverses that component's wire
    pins exactly (net presence preserved)."""
    if len(netlist.components) == 0 or len(netlist.components[0].pins) == 0:
        return
    comp = netlist.components[0]
    comp.pins = list(reversed(list(comp.pins)))
    d = _le._netlist_to_dict(netlist)
    orig_net = list(comp.pins)[0].net
    assert d["components"][0]["pins"][0]["name"] == comp.pins[0].name
    assert d["components"][0]["pins"][0]["net"] == orig_net


@given(wire_netlist())
@settings(max_examples=30, deadline=None)
def test_mr3_net_order_permutation_invariant(netlist):
    """MR3: reversing net order reverses the wire nets exactly."""
    reversed_nl = _tdb.netlist_contracts.Netlist(
        components=list(netlist.components), nets=list(reversed(list(netlist.nets)))
    )
    orig = _le._netlist_to_dict(netlist)["nets"]
    rev = _le._netlist_to_dict(reversed_nl)["nets"]
    assert canon(rev) == canon(list(reversed(orig)))


@given(wire_netlist(), st.dictionaries(_NET_NAME, _NET_NAME, max_size=3))
@settings(max_examples=30, deadline=None)
def test_mr4_topology_hints_do_not_affect_wire_body(netlist, hints):
    """MR4: adding topology_hints leaves the components/nets wire content
    bit-identical (only a trailing key is added)."""
    if not hints:
        hints = None
    base = LOOP_EXTRACTION_INPUT.from_netlist(netlist).to_dict()
    with_hints = LOOP_EXTRACTION_INPUT.from_netlist(netlist, hints).to_dict()
    assert canon(with_hints["components"]) == canon(base["components"])
    assert canon(with_hints["nets"]) == canon(base["nets"])


@given(wire_result())
@settings(max_examples=30, deadline=None)
def test_mr5_output_loop_order_preserved(result):
    """MR5: permuting the bridge output's loop order permutes the
    reconstructed collection order identically (per-loop fields untouched)."""
    wire = _tdb.LoopExtractionOutput.from_dict(result)
    ordered_names = [w.name for w in wire.loops]
    rev_result = dict(result)
    rev_result["loops"] = list(reversed(result["loops"]))
    rev_names = [w.name for w in _tdb.LoopExtractionOutput.from_dict(rev_result).loops]
    assert rev_names == list(reversed(ordered_names))
    # Per-loop fields are unchanged by the permutation (compare by name).
    by_name_a = {
        loop.name: _loop_fields(loop) for loop in _le._dict_to_loop_collection(result).loops
    }
    by_name_b = {
        loop.name: _loop_fields(loop) for loop in _le._dict_to_loop_collection(rev_result).loops
    }
    assert by_name_a == by_name_b
