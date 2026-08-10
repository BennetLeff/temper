"""Property-based tests for the Phase-A U9 DRC-feedback wire types
(Wave-4 discipline contract G4/G5).

Verification unit: the U9 feedback wire cluster --
`temper_drc_rs.Violation` (`DRCViolation` wire) and `temper_drc_rs.DrcReport`
(`parse_kicad_drc`'s typed container), exercised through the
`deterministic/feedback/drc_parser.py` / `violation_mapper.py` shims.

Module -> property map (G4 note: every module reached by >= 1 property):

  | Module       | Properties |
  |--------------|------------|
  | `Violation`  | P1, P2, P3, P4, P5 |
  | `DrcReport`  | P6 |

Every property has a `test_pN_fails_for_<mutant>` companion (G4 vacuity
guard) proving a degenerate kernel violates it. The mutants patch a
Python-level seam (the shim `_process_raw_violation`, or a pyclass
method), so each guard proves the property is reachable.

Metamorphic relations (G5, >= 3) are in the labelled section at the bottom.
"""

from __future__ import annotations

import pytest
import temper_drc_rs as _tdrc
from hypothesis import given, settings
from hypothesis import strategies as st
from tests.core._contract_canon import canon
from tests.deterministic.test_violation_report_rust_differential import (
    _oracle_process_raw_violation,
    _violation_fields,
)

import temper_placer.deterministic.feedback.drc_parser as _dp

VIOLATION = _tdrc.Violation
DRC_REPORT = _tdrc.DrcReport

# ---------------------------------------------------------------------------
# Input strategies
# ---------------------------------------------------------------------------

_text = st.text(min_size=0, max_size=40)
_float = st.floats(-1000, 1000, allow_nan=False, allow_infinity=False)

_item_st = st.fixed_dictionaries(
    {"description": _text},
    optional={
        "pos": st.fixed_dictionaries({"x": st.one_of(st.integers(-100, 100), _float),
                                       "y": st.one_of(st.integers(-100, 100), _float)}),
    },
)

_payload_st = st.fixed_dictionaries(
    {},
    optional={
        "type": st.one_of(_text, st.integers(-10, 10)),
        "severity": st.one_of(_text, st.integers(-10, 10)),
        "description": _text,
        "items": st.lists(_item_st, min_size=0, max_size=6),
    },
)

_clearance_description_st = st.one_of(
    st.builds(
        lambda required, actual: f"clearance {required} mm; actual {actual} mm",
        required=st.floats(0.001, 5.0, allow_nan=False, allow_infinity=False),
        actual=st.floats(0.001, 5.0, allow_nan=False, allow_infinity=False),
    ),
    st.builds(
        lambda actual, required: f"Clearance violation ({actual}mm < {required}mm required)",
        actual=st.floats(0.001, 5.0, allow_nan=False, allow_infinity=False),
        required=st.floats(0.001, 5.0, allow_nan=False, allow_infinity=False),
    ),
)


def _f(value):
    """Bit-exact float key."""
    return None if value is None else float(value).hex()


# ---------------------------------------------------------------------------
# P1 — totality + typed return
# ---------------------------------------------------------------------------


@given(_payload_st)
@settings(max_examples=100, deadline=None)
def test_p1_totality_typed(payload):
    """P1: any raw-violation dict parses through the shim into a typed
    `Violation` with the full field surface."""
    v = _dp._process_raw_violation(payload)
    assert isinstance(v, VIOLATION)
    assert isinstance(v.type, (str, int))
    assert isinstance(v.items, list)
    assert isinstance(v.severity, (str, int))
    assert v.required is None or isinstance(v.required, float)
    assert v.actual is None or isinstance(v.actual, float)


def test_p1_fails_for_none_return(monkeypatch):
    monkeypatch.setattr(_dp, "_process_raw_violation", lambda _v: None)
    with pytest.raises(AssertionError):
        test_p1_totality_typed.hypothesis.inner_test({})


# ---------------------------------------------------------------------------
# P2 — shim parity with the pinned pre-migration oracle (bit-exact)
# ---------------------------------------------------------------------------


@given(_payload_st)
@settings(max_examples=100, deadline=None)
def test_p2_parse_matches_pinned_oracle(payload):
    """P2: `_process_raw_violation(payload)` (typed Violation) is
    bit-identical to the pinned pre-migration parse on every field --
    including non-str pass-through and int-typed pos coordinates (canon is
    type-carrying)."""
    got = _dp._process_raw_violation(payload)
    oracle = _oracle_process_raw_violation(payload)
    assert _violation_fields(got) == _violation_fields(oracle)


def test_p2_fails_for_constant_parse(monkeypatch):
    monkeypatch.setattr(
        _dp,
        "_process_raw_violation",
        lambda _v: VIOLATION(type="constant"),
    )
    with pytest.raises(AssertionError):
        test_p2_parse_matches_pinned_oracle.hypothesis.inner_test({})


# ---------------------------------------------------------------------------
# P3 — defaults
# ---------------------------------------------------------------------------


@given(_payload_st)
@settings(max_examples=100, deadline=None)
def test_p3_defaults(payload):
    """P3: absent type/severity/description yield the dataclass defaults
    ("unknown"/"error"/"")."""
    v = _dp._process_raw_violation(payload)
    if "type" not in payload:
        assert v.type == "unknown"
    if "severity" not in payload:
        assert v.severity == "error"
    if "description" not in payload:
        assert v.description == ""


def test_p3_fails_for_wrong_default(monkeypatch):
    monkeypatch.setattr(
        _dp,
        "_process_raw_violation",
        lambda _v: VIOLATION(type="wrong_default"),
    )
    with pytest.raises(AssertionError):
        test_p3_defaults.hypothesis.inner_test({})


# ---------------------------------------------------------------------------
# P4 — items are description strings in order
# ---------------------------------------------------------------------------


@given(_payload_st)
@settings(max_examples=100, deadline=None)
def test_p4_items_are_description_strings_in_order(payload):
    """P4: each item's description becomes an entry in `items` (empty string
    for absent description), in item order."""
    v = _dp._process_raw_violation(payload)
    expected = [i.get("description", "") for i in payload.get("items", [])]
    assert v.items == expected


def test_p4_fails_for_reversed_items(monkeypatch):
    orig = _dp._process_raw_violation

    def mutant(v):
        out = orig(v)
        out.items = list(reversed(out.items))
        return out

    monkeypatch.setattr(_dp, "_process_raw_violation", mutant)
    payload = {
        "items": [
            {"description": "a"},
            {"description": "b"},
        ]
    }
    with pytest.raises(AssertionError):
        test_p4_items_are_description_strings_in_order.hypothesis.inner_test(payload)


# ---------------------------------------------------------------------------
# P5 — clearance extraction (bit-exact floats)
# ---------------------------------------------------------------------------


@given(_payload_st, _clearance_description_st)
@settings(max_examples=100, deadline=None)
def test_p5_clearance_extraction_bit_exact(payload, description):
    """P5: a description carrying one of the two clearance patterns fills
    required/actual with the parsed floats, bit-exact (both pattern orders)."""
    p = dict(payload)
    p["description"] = description
    v = _dp._process_raw_violation(p)
    oracle = _oracle_process_raw_violation(p)
    assert _f(v.required) == _f(oracle.required)
    assert _f(v.actual) == _f(oracle.actual)
    assert v.required is not None
    assert v.actual is not None


def test_p5_fails_for_cleared_clearance(monkeypatch):
    orig = _dp._process_raw_violation

    def mutant(v):
        out = orig(v)
        out.required = None
        out.actual = None
        return out

    monkeypatch.setattr(_dp, "_process_raw_violation", mutant)
    payload = {"description": "clearance 0.2000 mm; actual 0.1958 mm"}
    with pytest.raises(AssertionError):
        test_p5_clearance_extraction_bit_exact.hypothesis.inner_test(payload, payload["description"])


# ---------------------------------------------------------------------------
# P6 — DrcReport container semantics
# ---------------------------------------------------------------------------


@given(st.lists(_payload_st, min_size=0, max_size=6))
@settings(max_examples=100, deadline=None)
def test_p6_drc_report_container_semantics(payloads):
    """P6: `DrcReport` preserves construction order and matches
    list-compatible `len`/`bool`/iteration over the source violations."""
    violations = [_dp._process_raw_violation(p) for p in payloads]
    report = DRC_REPORT(violations=violations)
    assert len(report) == len(payloads)
    assert bool(report) == bool(payloads)
    assert [canon(v.type) for v in report] == [canon(_dp._process_raw_violation(p).type) for p in payloads]
    assert len(report.violations) == len(payloads)


def test_p6_fails_for_dropped_report_rows(monkeypatch):
    def mutant_iter(self):
        return iter([])

    monkeypatch.setattr(DRC_REPORT, "__iter__", mutant_iter)
    payloads = [{"type": "a"}, {"type": "b"}]
    with pytest.raises(AssertionError):
        test_p6_drc_report_container_semantics.hypothesis.inner_test(payloads)


# ---------------------------------------------------------------------------
# Metamorphic relations (G5)
# ---------------------------------------------------------------------------


@given(_payload_st, st.text(min_size=1, max_size=12))
@settings(max_examples=30, deadline=None)
def test_mr1_extraneous_keys_ignored(payload, extra_key):
    """MR1: adding arbitrary extra top-level keys never changes the parsed
    violation (the parse reads a fixed key set)."""
    p = dict(payload)
    p[extra_key] = {"nested": 1, "more": [1, 2, 3]}
    assert _violation_fields(_dp._process_raw_violation(p)) == _violation_fields(
        _dp._process_raw_violation(payload)
    )


@given(_payload_st, st.text(min_size=1, max_size=60))
@settings(max_examples=30, deadline=None)
def test_mr2_plain_description_leaves_clearance_none(payload, plain_text):
    """MR2: a description without a clearance pattern leaves required/actual
    None regardless of its other text."""
    p = dict(payload)
    p["description"] = plain_text
    v = _dp._process_raw_violation(p)
    assert v.required is None
    assert v.actual is None


@given(st.lists(_item_st, min_size=1, max_size=6))
@settings(max_examples=30, deadline=None)
def test_mr3_single_pos_item_order_invariant(items):
    """MR3: with exactly one pos-bearing item, permuting item order leaves
    pos unchanged (the parser takes the FIRST pos-bearing item)."""
    pos_bearers = [i for i in items if "pos" in i]
    if len(pos_bearers) != 1:
        return
    base = _dp._process_raw_violation({"items": items})
    swapped = _dp._process_raw_violation({"items": list(reversed(items))})
    assert canon(base.pos) == canon(swapped.pos)


@given(st.lists(_payload_st, min_size=1, max_size=6))
@settings(max_examples=30, deadline=None)
def test_mr4_report_iteration_preserves_construction_order(payloads):
    """MR4: report iteration and `.violations` follow the construction list
    order exactly (a reorder in construction reorders iteration identically)."""
    violations = [_dp._process_raw_violation(p) for p in payloads]
    report = DRC_REPORT(violations=violations)
    assert [canon(v.type) for v in report] == [canon(v.type) for v in violations]
    assert [canon(v.type) for v in report.violations] == [canon(v.type) for v in violations]
