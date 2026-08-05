"""Differential test: explainability/traced_loss.py + pipeline.py compute
(temper-io-types) vs the pinned Python oracles.

Wave 4, Phase 5 — the explainability surface migration. The Rust migration
(reproducing ``temper_placer/explainability/traced_loss.py``'s and
``pipeline.py``'s compute bit-identically in the ``temper-io-types`` crate)
is driven through the delegation shims; the pre-migration implementations
are pinned verbatim as oracles (``explain_oracle/traced_loss_oracle.py``,
``explain_oracle/pipeline_oracle.py``).

Migrated:
- ``traced_loss.constraint_to_traced_loss`` subject/because introspection
  (the hasattr chain), and the ``traced``/``traced_loss`` threshold gate
  (``float()`` conversion and ``sum()`` stay Python — float() accepts
  str/bytes and sum() is Neumaier-compensated, both Python runtime
  semantics per the guide).
- ``pipeline.compose_traces`` — the monoid fold (order-preserving
  concatenation of N traces).

``TracedPipeline.run`` / ``traced_pipeline_example`` / the demo/example
functions stay Python: they orchestrate calls to arbitrary Python
callables, so migrating them would ADD boundary crossings without removing
any compute (R1e non-applicability — see VERIFICATION.md).
"""

from __future__ import annotations

import random

import temper_io_types as _rust

from temper_placer.explainability.pipeline import TracedPipeline, compose_traces
from temper_placer.explainability.trace import Trace
from temper_placer.explainability.traced_loss import (
    TracedLossContext,
    combine_traced_losses,
    constraint_to_traced_loss,
    traced,
    traced_loss,
)
from tests.explainability.explain_oracle import (
    pipeline_oracle as _pipeline_oracle,
)
from tests.explainability.explain_oracle import (
    traced_loss_oracle as _oracle,
)

# Module-scope RED arm.
assert hasattr(_rust, "explain_constraint_subject")
assert hasattr(_rust, "explain_trace_threshold")
assert hasattr(_rust, "explain_compose_traces")


def _trace(entries):
    t = Trace.empty()
    for subject, value, because in entries:
        t = t.add(subject, value, because)
    return t


def _entries_key(trace):
    return [(e.subject, e.because) for e in trace.entries]


# ---------------------------------------------------------------------------
# traced_loss
# ---------------------------------------------------------------------------

class _Constraint:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_constraint_subject_introspection_identical():
    cases = [
        _Constraint(a="Q1", because="bc"),
        _Constraint(component="C1", because="x"),
        _Constraint(components=["R1", "R2"], because="y"),
        _Constraint(components=[], because="z"),
        _Constraint(a="Q1"),  # no because -> "constraint"
        _Constraint(foo="bar"),  # no subject -> "unknown"
    ]
    for constraint in cases:
        ours = constraint_to_traced_loss(constraint, lambda *_a, **_k: 1.0)
        theirs = _oracle.constraint_to_traced_loss(constraint, lambda *_a, **_k: 1.0)
        # The wrapped functions are closures; compare via a call.
        assert ours(1.0)[1].entries[0].subject == theirs(1.0)[1].entries[0].subject
        assert ours(1.0)[1].entries[0].because == theirs(1.0)[1].entries[0].because


def test_traced_threshold_gate_identical():
    @traced(subject="S", because="B")
    def fn(x):
        return x

    @_oracle.traced(subject="S", because="B")
    def oracle_fn(x):
        return x

    for value in [0.0, 1e-7, 1e-6, 2e-6, 5.0, -3.0, 0.5]:
        ours_val, ours_trace = fn(value)
        theirs_val, theirs_trace = oracle_fn(value)
        assert ours_val == theirs_val
        assert _entries_key(ours_trace) == _entries_key(theirs_trace)
        assert len(ours_trace.entries) == len(theirs_trace.entries)


def test_traced_float_conversion_accepts_strings():
    """float("1.5") works -> recorded with the converted float."""

    @traced(subject="S", because="B")
    def fn():
        return "1.5"

    @_oracle.traced(subject="S", because="B")
    def oracle_fn():
        return "1.5"

    _, ours = fn()
    _, theirs = oracle_fn()
    assert len(ours.entries) == len(theirs.entries) == 1
    assert ours.entries[0].value == theirs.entries[0].value == 1.5


def test_traced_non_float_records_raw():
    @traced(subject="S", because="B")
    def fn():
        return "not-a-number"

    @_oracle.traced(subject="S", because="B")
    def oracle_fn():
        return "not-a-number"

    _, ours = fn()
    _, theirs = oracle_fn()
    assert _entries_key(ours) == _entries_key(theirs)
    assert ours.entries[0].value == "not-a-number"


def test_traced_defaults_subject_and_because():
    @traced()
    def compute():
        return 5.0

    @_oracle.traced()
    def oracle_compute():
        return 5.0

    _, ours = compute()
    _, theirs = oracle_compute()
    # Each side defaults to its OWN function name (func.__name__ — a Python
    # runtime semantic); the differential pins that both sides apply the
    # same default rule, not that the names are literally equal.
    assert ours.entries[0].subject == "compute"
    assert theirs.entries[0].subject == "oracle_compute"
    assert ours.entries[0].because == "Result of compute"
    assert theirs.entries[0].because == "Result of oracle_compute"


def test_traced_context_mode():
    with TracedLossContext() as ctx:
        result = _traced_fn(1.0)
    with _oracle.TracedLossContext() as oracle_ctx:
        oracle_result = _oracle_traced_fn(1.0)
    assert result == oracle_result
    assert _entries_key(ctx.result()[1]) == _entries_key(oracle_ctx.result()[1])


@traced(subject="ctx", because="in-context")
def _traced_fn(x):
    return x * 2


@_oracle.traced(subject="ctx", because="in-context")
def _oracle_traced_fn(x):
    return x * 2


def test_traced_loss_wrapper_identical():
    def loss_fn(a, b):
        return a + b

    wrapped = traced_loss(loss_fn, "Q1", "because")
    oracle_wrapped = _oracle.traced_loss(loss_fn, "Q1", "because")
    ours_val, ours_trace = wrapped(1.0, 2.0)
    theirs_val, theirs_trace = oracle_wrapped(1.0, 2.0)
    assert ours_val == theirs_val
    assert _entries_key(ours_trace) == _entries_key(theirs_trace)


def test_combine_traced_losses_matches_oracle():
    traces = [
        (1.0, _trace([("A", 1.0, "r1")])),
        (2.0, _trace([("B", 2.0, "r2")])),
    ]
    ours = combine_traced_losses(traces)
    theirs = _oracle.combine_traced_losses(traces)
    assert ours[0] == theirs[0]
    assert _entries_key(ours[1]) == _entries_key(theirs[1])
    # Empty list.
    assert combine_traced_losses([]) == (0.0, Trace.empty())


def test_traced_loss_context_result_empty():
    ctx = TracedLossContext()
    assert ctx.result() == (0.0, Trace.empty())


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------

def test_compose_traces_identical():
    rng = random.Random(11)
    for _ in range(30):
        traces = [
            _trace([(f"S{i}{j}", rng.uniform(0, 10), f"r{j}") for j in range(rng.randint(0, 4))])
            for i in range(rng.randint(0, 5))
        ]
        ours = compose_traces(*traces)
        theirs = _pipeline_oracle.compose_traces(*traces)
        assert _entries_key(ours) == _entries_key(theirs)
        assert len(ours) == len(theirs)


def test_compose_traces_order_preserved():
    t1 = _trace([("A", 1, "r1")])
    t2 = _trace([("B", 2, "r2")])
    t3 = _trace([("C", 3, "r3")])
    combined = compose_traces(t1, t2, t3)
    assert [e.subject for e in combined.entries] == ["A", "B", "C"]
    assert combined.entries[0].value == 1


def test_compose_traces_empty():
    assert len(compose_traces()) == 0
    assert len(compose_traces(_trace([]))) == 0


def test_compose_traces_identity():
    """compose(t, empty) == compose(empty, t) == t (monoid identity)."""
    t = _trace([("A", 1, "r1"), ("B", 2, "r2")])
    empty = Trace.empty()
    assert _entries_key(compose_traces(t, empty)) == _entries_key(t)
    assert _entries_key(compose_traces(empty, t)) == _entries_key(t)


def test_traced_pipeline_run_order():
    def stage_a(data):
        return data + 1, _trace([("A", data, "stage-a")])

    def stage_b(data):
        return data * 2, _trace([("B", data, "stage-b")])

    pipeline = TracedPipeline()
    pipeline.add_stage("a", stage_a)
    pipeline.add_stage("b", stage_b)
    result, trace = pipeline.run(5)
    assert result == 12
    assert [e.subject for e in trace.entries] == ["A", "B"]
    assert trace.entries[0].value == 5
    assert trace.entries[1].value == 6
