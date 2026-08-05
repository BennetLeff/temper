"""Differential test: explainability/trace.py compute (temper-io-types) vs
the pinned Python oracle.

Wave 4, Phase 5 — the explainability surface migration. The Rust migration
(reproducing ``temper_placer/explainability/trace.py``'s NL-generation
compute bit-identically in the ``temper-io-types`` crate) is driven through
the delegation shim ``temper_placer.explainability.trace``; the
pre-migration implementation is pinned verbatim as the oracle
(``explain_oracle/trace_oracle.py``).

``Entry``/``Trace`` stay Python dataclasses (frozen tuple storage, monoid
concat, filtering, repr are data-structure semantics with zero formatting
compute); the migrated compute is ``Trace.why`` — subject filtering, final
value selection, tuple float rendering and reason aggregation. Output is
compared byte-identical; the tuple-value ``:.1f`` rendering pins the
``py_float_fmt_1`` seam (NaN/inf render as ``nan``/``inf``).
"""

from __future__ import annotations

import random

import pytest
import temper_io_types as _rust

from tests.explainability.explain_oracle import trace_oracle as _oracle
from temper_placer.explainability.trace import Entry, Trace

# Module-scope RED arm.
assert hasattr(_rust, "explain_trace_why")


def _entry(subject, value, because):
    return Entry(subject, value, because)


def _trace(entries):
    t = Trace.empty()
    for e in entries:
        t = t.add(e.subject, e.value, e.because)
    return t


def _fixtures() -> list[tuple[Trace, str, int]]:
    rng = random.Random(0x7AACE)
    out = []

    # Empty trace.
    out.append((Trace.empty(), "Q1", 3))

    # Simple tuple values.
    for _ in range(30):
        entries = []
        subjects = ["Q1", "Q2", "U1", "VCC"]
        for _ in range(rng.randint(0, 6)):
            subject = rng.choice(subjects)
            kind = rng.randint(0, 3)
            if kind == 0:
                value = (rng.uniform(-100, 100), rng.uniform(-100, 100))
            elif kind == 1:
                value = rng.choice([0, 5, 90, -30])
            elif kind == 2:
                value = rng.choice(["L1", "F.Cu", "path", "ø3mm", "é"])
            else:
                value = rng.choice([None, True, 1.5, (1, 2, 3)])
            entries.append(_entry(subject, value, f"reason {rng.randint(1, 99)}"))
        out.append((_trace(entries), rng.choice(subjects), rng.choice([1, 3, 5, 10])))

    # Hand-built: int tuples (format as floats), negative coords, single entry.
    out.append((_trace([_entry("Q1", (10, 20), "initial")]), "Q1", 3))
    out.append((_trace([_entry("Q1", (-1.25, 2.5), "r1")]), "Q1", 3))
    out.append((_trace([_entry("Q1", (1, 2), "r1"), _entry("Q1", (3, 4), "r2"),
                        _entry("Q1", (5, 6), "r3"), _entry("Q1", (7, 8), "r4")]), "Q1", 2))
    out.append((_trace([_entry("Q1", "not-a-tuple", "r1"),
                        _entry("Q2", (1, 2), "r2")]), "Q1", 3))
    # More reasons than max_reasons.
    many = [_entry("C1", (i, i), f"reason {i}") for i in range(10)]
    out.append((_trace(many), "C1", 3))
    # Subject with no entries.
    out.append((_trace([_entry("Q1", (1, 2), "r")]), "Z9", 3))
    return out


def test_why_byte_identical():
    for trace, subject, max_reasons in _fixtures():
        assert trace.why(subject, max_reasons) == _oracle.Trace(trace.entries).why(
            subject, max_reasons
        )


def test_why_empty_subject_message():
    trace = Trace.empty()
    assert trace.why("Q1") == "No decisions recorded for Q1"
    assert trace.why("Q1") == _oracle.Trace(()).why("Q1")


def test_why_value_tuple_float_formatting():
    trace = _trace([_entry("Q1", (1.0, 2.0), "r")])
    assert trace.why("Q1") == "Q1 is at (1.0, 2.0) because:\n  - r"


def test_why_uses_final_value():
    trace = _trace([_entry("Q1", (1.0, 1.0), "first"), _entry("Q1", (9.5, 8.25), "last")])
    text = trace.why("Q1")
    # f"{8.25:.1f}" is round-half-even -> "8.2" (8.25 is exactly
    # representable and 2 is even), matching the oracle byte-for-byte.
    assert "Q1 is at (9.5, 8.2)" in text
    assert "first" in text and "last" in text


def test_why_max_reasons_truncation_pinned():
    trace = _trace([_entry("C1", (i, i), f"reason {i}") for i in range(10)])
    text = trace.why("C1", 3)
    assert text == _oracle.Trace(trace.entries).why("C1", 3)
    assert "  ... and 7 more reasons" in text


def test_why_float_edge_values():
    """NaN/inf tuples render via py_float_fmt_1 (nan/inf, not NaN/Inf)."""
    import math

    trace = _trace([_entry("Q1", (float("nan"), 1.0), "r")])
    text = trace.why("Q1")
    assert "nan" in text
    assert "NaN" not in text
    trace2 = _trace([_entry("Q1", (float("inf"), -float("inf")), "r")])
    text2 = trace2.why("Q1")
    assert "inf" in text2
