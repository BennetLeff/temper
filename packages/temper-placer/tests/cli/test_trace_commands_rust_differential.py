"""Differential test: cli/trace_commands.py compute, Rust vs oracle.

Wave 4, **Phase 5** (cli/adapters/temper-workflow slice). The decision-trace
filtering compute of ``temper_placer/cli/trace_commands.py`` moves to the
``temper-orchestration`` crate (``temper_orchestration.filter_decisions``,
``temper_orchestration.find_rejected_alternative``); the Python module
keeps its full click surface and delegates the filtering across the
boundary.

The pre-migration module is pinned VERBATIM as the oracle
(``tests/cli/_trace_commands_py_oracle.py``). The compute is INLINE in the
click command bodies, so the reference arms below are mechanical
extractions, annotated with the oracle line they came from:

1. ``_ref_filter_decisions`` — the ``why`` subject filter (oracle line
   ~20: ``[d for d in data.get("decisions", []) if d.get("subject") ==
   subject]``). Returns the ORIGINAL indices of the matching decisions
   (the shim's access pattern), i.e. ``[i for i, d in enumerate(decisions)
   if d.get("subject") == subject]``.
2. ``_ref_find_rejected`` — the ``why_not`` nested scan (oracle lines
   ~38-43): the first alternative whose ``str(alt.get("value")) == value``
   inside the first subject-matching decision. Returns the original
   decision index + alternative index.

The comparisons that decide the filters are Python value semantics
(``dict.get`` defaulting to ``None``, ``None == x``, ``str()`` of an
arbitrary JSON leaf), and the Rust side preserves them by calling back into
Python for each leaf comparison — ``d.call_method1("get", ...)`` (the
``AttributeError`` on a non-dict is Python's own), ``PyAny::str()`` and
``PyAny::eq``. The CONTROL FLOW (iteration, subject equality, the nested
scan, first-match return) is Rust. Error parity (non-iterable ``decisions``
→ ``TypeError`` with CPython's message) is asserted via ``canon_call`` and
comes from ``PyObject_GetIter`` on the Rust side, i.e. by identity.

Bit-exactness conventions (R1a): indices compare as plain ints; dicts are
canonicalized insertion-order-preserving (``canon``); error parity compares
exception type name AND message text.
"""

from __future__ import annotations

import json

import temper_orchestration as _to

import tests.cli._trace_commands_py_oracle as _oracle  # noqa: F401  (provenance anchor)
from tests.core._contract_canon import canon, canon_call

# Rust symbols under test — must exist or this file fails to collect (RED).
RS_FILTER = _to.filter_decisions
RS_FIND_REJECTED = _to.find_rejected_alternative


# ---------------------------------------------------------------------------
# Reference arms — mechanically extracted from the oracle's inline compute.
# ---------------------------------------------------------------------------

def _ref_filter_decisions(decisions: list[dict], subject) -> list[int]:
    """Extracted from the oracle's ``why`` (the subject filter, returned as
    original indices — the shim's access pattern)."""
    return [i for i, d in enumerate(decisions) if d.get("subject") == subject]


def _ref_find_rejected(decisions: list[dict], subject, value):
    """Extracted from the oracle's ``why_not`` (the nested scan)."""
    for di, d in enumerate(decisions):
        if d.get("subject") != subject:
            continue
        for ai, alt in enumerate(d.get("alternatives_considered", [])):
            if str(alt.get("value")) == value:
                return (di, ai)
    return None


# ---------------------------------------------------------------------------
# Fixtures — synthetic decision traces (the oracle's real input domain is
# json.load of a decision trace file; dicts with arbitrary JSON leaves).
# ---------------------------------------------------------------------------

def _decision(subject, value, phase="place", dtype="choice", reason="r", refs=None, alts=None):
    d = {
        "subject": subject,
        "value": value,
        "phase": phase,
        "decision_type": dtype,
        "reason": reason,
    }
    if refs is not None:
        d["constraint_refs"] = refs
    if alts is not None:
        d["alternatives_considered"] = alts
    return d


def _alt(value, reason="rej", violated=None, loss=None):
    a = {"value": value, "rejection_reason": reason}
    if violated is not None:
        a["constraint_violated"] = violated
    if loss is not None:
        a["loss_if_chosen"] = loss
    return a


BASE_TRACE = [
    _decision("Q1", 1, refs=["c1", "c2"],
              alts=[_alt(0, "Too far", violated="clearance"), _alt(2, "Off-grid")]),
    _decision("Q2", 5, alts=[_alt(4, "No route")]),
    _decision("Q1", 3, dtype="retry", alts=[_alt(0, "Too far"), _alt(1, "Loss")]),
    _decision("R1", {"x": 10}, refs=[]),
    _decision("Q1", 1, alts=[]),
]

# Traces reconstructed exactly as json.load would produce them.
TRACES = json.loads(json.dumps(BASE_TRACE))


def _assert_filter_equal(decisions, subject) -> None:
    ref = canon(_ref_filter_decisions(decisions, subject))
    got = canon(RS_FILTER(decisions, subject))
    assert ref == got, f"filter_decisions mismatch for subject={subject!r}\n  ref={ref}\n  got={got}"


def _assert_find_equal(decisions, subject, value) -> None:
    ref = canon_call(_ref_find_rejected, decisions, subject, value)
    got = canon_call(RS_FIND_REJECTED, decisions, subject, value)
    assert ref == got, (
        f"find_rejected_alternative mismatch subject={subject!r} value={value!r}\n"
        f"  ref={ref}\n  got={got}"
    )


# ---------------------------------------------------------------------------
# filter_decisions
# ---------------------------------------------------------------------------

def test_filter_decisions_basic():
    _assert_filter_equal(TRACES, "Q1")
    _assert_filter_equal(TRACES, "Q2")
    _assert_filter_equal(TRACES, "R1")
    _assert_filter_equal(TRACES, "NOPE")


def test_filter_decisions_empty_and_missing():
    _assert_filter_equal([], "Q1")
    _assert_filter_equal([{"subject": "Q1", "value": 1}], "Q1")
    # missing "subject" key -> dict.get returns None -> None == "Q1" is False
    _assert_filter_equal([{"value": 1}, {"subject": None, "value": 2}], "Q1")
    _assert_filter_equal([{"value": 1}, {"subject": None, "value": 2}], None)


def test_filter_decisions_numeric_subject():
    """dict leaves can be numbers; d.get(subject) == subject is type-exact."""
    decs = [{"subject": 5, "value": 1}, {"subject": "5", "value": 2}, {"subject": 5.0, "value": 3}]
    _assert_filter_equal(decs, 5)
    _assert_filter_equal(decs, "5")
    _assert_filter_equal(decs, 5.0)


def test_filter_decisions_order_preserved():
    """The filter is order-preserving (no reordering of matching items)."""
    decs = [{"subject": "A", "value": i} for i in range(10)]
    decs = decs + [{"subject": "B", "value": i} for i in range(10)]
    decs = [d for pair in zip(decs[:10], decs[10:]) for d in pair]  # interleave
    _assert_filter_equal(decs, "A")
    _assert_filter_equal(decs, "B")


def test_filter_decisions_mixed_realistic_trace():
    """A realistic trace with retries, dict values and missing keys."""
    trace = [
        {"subject": "U1", "value": {"x": 1, "y": 2}, "phase": "place",
         "decision_type": "place", "reason": "ok",
         "constraint_refs": ["c1"], "alternatives_considered": [
             {"value": {"x": 0, "y": 0}, "rejection_reason": "overlap",
              "constraint_violated": "drc_clearance"}]},
        {"subject": "U1", "value": 3, "phase": "route", "decision_type": "retry",
         "reason": "failed", "alternatives_considered": [
             {"value": 2, "rejection_reason": "loop"}, {"value": 1, "rejection_reason": "loss"}]},
        {"subject": "N1", "value": "top", "phase": "layer", "decision_type": "assign",
         "reason": "default"},
    ]
    _assert_filter_equal(trace, "U1")
    _assert_filter_equal(trace, "N1")
    _assert_filter_equal(trace, "missing")


def test_filter_decisions_non_iterable_raises_type_error():
    """decisions=None -> TypeError with CPython's message (by identity)."""
    ref = canon_call(_ref_filter_decisions, None, "Q1")
    got = canon_call(RS_FILTER, None, "Q1")
    assert ref == got
    assert ref[0] == "raised" and ref[1] == "TypeError"
    ref = canon_call(_ref_filter_decisions, 5, "Q1")
    got = canon_call(RS_FILTER, 5, "Q1")
    assert ref == got


def test_filter_decisions_non_dict_raises_attribute_error():
    """A non-dict element -> AttributeError ('list' object has no attribute 'get')."""
    decs = [{"subject": "Q1"}, ["not", "a", "dict"]]
    ref = canon_call(_ref_filter_decisions, decs, "Q1")
    got = canon_call(RS_FILTER, decs, "Q1")
    assert ref == got
    assert ref[0] == "raised" and ref[1] == "AttributeError"


def test_filter_decisions_tuple_input():
    """The oracle's data.get('decisions', []) may return any iterable; a tuple
    of dicts filters identically and indexes identically."""
    decs = ({"subject": "Q1", "value": 1}, {"subject": "Q2", "value": 2})
    _assert_filter_equal(decs, "Q1")


# ---------------------------------------------------------------------------
# find_rejected_alternative
# ---------------------------------------------------------------------------

def test_find_rejected_basic():
    _assert_find_equal(TRACES, "Q1", 0)
    _assert_find_equal(TRACES, "Q1", 2)
    _assert_find_equal(TRACES, "Q2", 4)
    _assert_find_equal(TRACES, "Q1", 99)   # never considered
    _assert_find_equal(TRACES, "Q2", 0)    # not an alternative of Q2's decision


def test_find_rejected_first_match_wins():
    """The oracle returns on the FIRST matching alternative in the FIRST
    subject-matching decision (nested iteration order is load-bearing)."""
    decs = [
        _decision("Q1", 1, alts=[_alt(0, "first"), _alt(0, "second")]),
        _decision("Q1", 2, alts=[_alt(0, "third")]),
    ]
    _assert_find_equal(decs, "Q1", 0)  # -> (0, 0): "first", not (0,1) or (1,0)


def test_find_rejected_str_of_value():
    """str(alt.get('value')) == value: int 5 matches '5'; dict value does not
    match its repr; None value matches 'None'."""
    decs = [
        _decision("Q1", 1, alts=[_alt(5), _alt({"x": 1}), _alt(None), _alt("str")]),
    ]
    _assert_find_equal(decs, "Q1", "5")
    _assert_find_equal(decs, "Q1", "{'x': 1}")   # str(dict) is its repr
    _assert_find_equal(decs, "Q1", "None")
    _assert_find_equal(decs, "Q1", "str")


def test_find_rejected_empty_alternatives_and_missing():
    _assert_find_equal([_decision("Q1", 1)], "Q1", 1)
    _assert_find_equal([_decision("Q1", 1, alts=[])], "Q1", 1)
    _assert_find_equal([{"subject": "Q1"}], "Q1", 1)   # no alternatives key
    _assert_find_equal([], "Q1", 1)
    # alternatives_considered present but None -> for alt in None -> TypeError
    decs = [{"subject": "Q1", "alternatives_considered": None}]
    ref = canon_call(_ref_find_rejected, decs, "Q1", 1)
    got = canon_call(RS_FIND_REJECTED, decs, "Q1", 1)
    assert ref == got
    assert ref[0] == "raised" and ref[1] == "TypeError"


def test_find_rejected_alt_missing_value_key():
    """alt without a 'value' key -> alt.get('value') is None -> str(None)."""
    decs = [_decision("Q1", 1, alts=[{"rejection_reason": "no-value"}])]
    _assert_find_equal(decs, "Q1", "None")
    _assert_find_equal(decs, "Q1", "no-value")


def test_find_rejected_nested_permutations():
    """Permutation of alternatives changes the match index; the differential
    must see the exact (decision, alt) pair both sides agree on."""
    for seed in range(12):
        decs = [
            _decision("Q1", 1, alts=[_alt(i) for i in range(seed % 5)]),
            _decision("Q1", 2, alts=[_alt(i) for i in range(3)]),
        ]
        for value in ["0", "1", "2", "3", "4"]:
            _assert_find_equal(decs, "Q1", value)


def test_find_rejected_full_trace_differential():
    """Drive the whole BASE_TRACE with every subject/value combination."""
    subjects = ["Q1", "Q2", "R1", "missing"]
    values = [0, 1, 2, 3, 4, 5, "0", "1", "2", {"x": 10}, None, "Too far"]
    for subj in subjects:
        for val in values:
            _assert_find_equal(TRACES, subj, val)


# ---------------------------------------------------------------------------
# CLI-surface A/B: the shim's click commands must produce byte-identical
# stdout and exit codes to the oracle's, driven on the same trace file.
# This is the "CLI surface (flags/help/exit codes) stays Python" proof.
# ---------------------------------------------------------------------------

from click.testing import CliRunner


def test_cli_surface_why_matches_oracle(tmp_path):
    trace_file = tmp_path / "trace.json"
    trace_file.write_text(json.dumps({"run_id": "r1", "decisions": BASE_TRACE}))

    runner = CliRunner()
    for subject in ["Q1", "Q2", "R1", "missing"]:
        shim_result = runner.invoke(_to_why_shim(), [str(trace_file), subject])
        oracle_result = runner.invoke(_to_why_oracle(), [str(trace_file), subject])
        assert shim_result.exit_code == oracle_result.exit_code, subject
        assert shim_result.output == oracle_result.output, subject


def test_cli_surface_why_not_matches_oracle(tmp_path):
    trace_file = tmp_path / "trace.json"
    trace_file.write_text(json.dumps({"run_id": "r1", "decisions": BASE_TRACE}))

    runner = CliRunner()
    for subject, value in [("Q1", 0), ("Q1", "0"), ("Q1", 99), ("Q2", 4), ("R1", "5")]:
        shim_result = runner.invoke(_to_why_shim(), [str(trace_file), subject, str(value)])
        oracle_result = runner.invoke(_to_why_oracle(), [str(trace_file), subject, str(value)])
        assert shim_result.exit_code == oracle_result.exit_code, (subject, value)
        assert shim_result.output == oracle_result.output, (subject, value)


def test_cli_surface_help_text_matches_oracle():
    """--help output (the flag/help surface) must be identical."""
    runner = CliRunner()
    shim_result = runner.invoke(_to_why_shim(), ["--help"])
    oracle_result = runner.invoke(_to_why_oracle(), ["--help"])
    assert shim_result.exit_code == oracle_result.exit_code
    assert shim_result.output == oracle_result.output


def _to_why_shim():
    from temper_placer.cli.trace_commands import trace as shim_trace

    return shim_trace


def _to_why_oracle():
    return _oracle.trace
