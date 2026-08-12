"""Wave-4 tail-tooling migration: behavioural A/B of the regression reporter
compute (temper-orchestration ``reporter`` module) against the pinned
pre-migration oracle.

The pre-migration ``temper_placer/regression/reporter.py`` is pinned VERBATIM
as ``tests/regression/_reporter_py_oracle.py`` (content-hash registered in
``scripts/oracle_hashes.json`` AND in this file's body digests). Both arms are
driven with IDENTICAL inputs; every assertion is bit-exact:

- ``MetricDelta`` — ``delta_display``, ``message()``, dataclass ``repr``/
  ``str``/``eq`` (sign-prefixed delta rendering, the ``name: current vs
  baseline (delta)`` line, the settable ``regression`` flag);
- ``BoardResult`` / ``BatteryVerdictReport`` — dataclass ``repr``/``str``/
  ``eq`` and field defaults;
- ``RegressionReporter`` — the ``total``/``passed``/``failed``/``skipped``/
  ``has_failures`` counting, the ``summary()`` renderer (result lines,
  board_shape, skip reasons, REGRESSION deltas, warnings, errors, the
  battery-verdicts section) and the ``battery_report()`` renderer.

Anti-vacuity: ``test_shim_and_oracle_are_different_implementations`` asserts
the shim re-exports the ``temper_orchestration`` pyclasses (identical
objects) while the oracle still defines the Python dataclasses; the
delegation is proven by identity, not by a recording stub.

The helps-battery *decision* that produces the verdicts/budget_exceeded stays
in ``validation/_thermal_battery.py`` (out of this module's scope — the
reporter only renders what it is handed). See the module header in
``packages/temper-orchestration/src/reporter.rs`` and its VERIFICATION.md for
the split argument.
"""

from __future__ import annotations

import hashlib
import inspect
import textwrap
from pathlib import Path

import pytest
import temper_orchestration as _to
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.regression import reporter as shim_mod
from tests.regression import _reporter_py_oracle as _oracle

# ---------------------------------------------------------------------------
# The oracle must stay verbatim
# ---------------------------------------------------------------------------

_ORACLE_PATH = Path(__file__).with_name("_reporter_py_oracle.py")

# Body digests of the four ported classes, extracted from the oracle file
# (ClassDef AST ranges, dedented) — pinned here so a body edit in the oracle
# fails this test rather than silently re-pinning the differential.
_BODY_DIGESTS = {
    "BatteryVerdictReport": "40619a60619d6234a74611092afe1ab4d4962a77528a527193404d6bdd00c006",
    "MetricDelta": "3e6bb270df82efdaf455976b64f85626a18bd7a06544715b41c7e9e2dd169ff4",
    "BoardResult": "6027d1bbe18786cadfcc215a68b3a26ca527e0f7c22b8c3ed444c2f955ddbcdc",
    "RegressionReporter": "167c040623b8acbe326938af2c94a7fcc781b6df3969f2ed87838c3881080a09",
}


def _oracle_class_digests(path: Path) -> dict[str, str]:
    import ast

    src = path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    out: dict[str, str] = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.ClassDef):
            body = "".join(lines[node.lineno - 1 : node.end_lineno])
            out[node.name] = hashlib.sha256(textwrap.dedent(body).encode()).hexdigest()
    return out


def test_oracle_bodies_match_pinned_digests() -> None:
    """The oracle is evidence only while it is unmodified.

    A differential whose oracle can be edited to agree with the port proves
    nothing, so the copied bodies are content-addressed. If this fails,
    either the oracle was edited (revert it) or a pre-migration module's
    source really changed upstream (re-pin deliberately, in its own commit).
    """
    digests = _oracle_class_digests(_ORACLE_PATH)
    for name, want in _BODY_DIGESTS.items():
        assert digests.get(name) == want, (
            f"the pinned oracle body {name} changed; it must stay verbatim "
            "(see scripts/oracle_hashes.json for the registered hash)"
        )


def test_shim_and_oracle_are_different_implementations() -> None:
    """Anti-vacuity: the shim re-exports the temper_orchestration pyclasses
    by identity; the oracle defines distinct Python dataclasses."""
    for name in ("MetricDelta", "BoardResult", "BatteryVerdictReport", "RegressionReporter"):
        shim_cls = getattr(shim_mod, name)
        rust_cls = getattr(_to, name)
        oracle_cls = getattr(_oracle, name)
        assert shim_cls is rust_cls, f"{name} shim is not the pyo3 class"
        assert shim_cls.__module__ == "temper_orchestration"
        assert oracle_cls.__module__ == "tests.regression._reporter_py_oracle"
    # The shim no longer defines the classes inline.
    src = inspect.getsource(shim_mod)
    assert "class MetricDelta" not in src
    assert "class RegressionReporter" not in src


# ---------------------------------------------------------------------------
# MetricDelta
# ---------------------------------------------------------------------------

_METRIC_CASES = [
    dict(name="drc_errors", baseline=10.0, current=15.0, delta=5.0),
    dict(name="drc_errors", baseline=10.0, current=5.0, delta=-5.0),
    dict(name="wirelength", baseline=100.0, current=100.0, delta=0.0),
    dict(name="time_ms", baseline=0.25, current=0.5, delta=0.25),
    dict(name="x", baseline=-1.5, current=2.5, delta=4.0),
    dict(name="big", baseline=1e6, current=1.000001e6, delta=1.0),
]


def _shim_delta(case, regression=False):
    return _to.MetricDelta(
        name=case["name"], baseline=case["baseline"], current=case["current"],
        delta=case["delta"], regression=regression,
    )


def _oracle_delta(case, regression=False):
    return _oracle.MetricDelta(
        name=case["name"], baseline=case["baseline"], current=case["current"],
        delta=case["delta"], regression=regression,
    )


def test_metric_delta_display_matches_oracle() -> None:
    for case in _METRIC_CASES:
        assert _shim_delta(case).delta_display == _oracle_delta(case).delta_display
        assert _shim_delta(case).delta_display == (
            ("+" if case["delta"] > 0 else "") + str(case["delta"])
        )


def test_metric_delta_message_matches_oracle() -> None:
    for case in _METRIC_CASES:
        got = _shim_delta(case).message()
        want = _oracle_delta(case).message()
        assert got == want
        assert case["name"] in got


def test_metric_delta_repr_and_str_match_oracle() -> None:
    for case in _METRIC_CASES:
        for regression in (False, True):
            got = _shim_delta(case, regression)
            want = _oracle_delta(case, regression)
            assert repr(got) == repr(want)
            assert str(got) == str(want)


def test_metric_delta_regression_flag_is_settable() -> None:
    """runner.py sets `delta.regression = True` after construction."""
    delta = _to.MetricDelta(name="drc_errors", baseline=10.0, current=15.0, delta=5.0)
    assert delta.regression is False
    delta.regression = True
    assert delta.regression is True


def test_metric_delta_equality_is_dataclass_strict() -> None:
    a = _shim_delta(_METRIC_CASES[0])
    same = _shim_delta(_METRIC_CASES[0])
    diff = _shim_delta(_METRIC_CASES[1])
    assert a == same
    assert a != diff
    # Type-strict: a dataclass is never == to the pyclass.
    assert a != _oracle_delta(_METRIC_CASES[0])


# ---------------------------------------------------------------------------
# BoardResult / BatteryVerdictReport
# ---------------------------------------------------------------------------


def _shim_board(**kw):
    defaults = dict(board_id="b1", passed=True)
    defaults.update(kw)
    return _to.BoardResult(**defaults)


def _oracle_board(**kw):
    defaults = dict(board_id="b1", passed=True)
    defaults.update(kw)
    return _oracle.BoardResult(**defaults)


def test_board_result_repr_matches_oracle() -> None:
    cases = [
        {},
        {"skipped": True, "skip_reason": "missing"},
        {"board_shape": {"component_count": 5, "net_count": 3}},
        {"warnings": ["w1"], "errors": ["e1", "e2"]},
        {"metrics": {"g": 1.5}},
    ]
    for case in cases:
        got = _shim_board(**case)
        want = _oracle_board(**case)
        assert repr(got) == repr(want)
        assert str(got) == str(want)
    # The deltas case: the oracle arm must mirror the list-of-deltas shape.
    got = _shim_board(deltas=[_shim_delta(_METRIC_CASES[0], regression=True)])
    want = _oracle_board(deltas=[_oracle_delta(_METRIC_CASES[0], regression=True)])
    assert repr(got) == repr(want)
    assert str(got) == str(want)


def test_board_result_defaults_match_oracle() -> None:
    got = _shim_board()
    want = _oracle_board()
    assert got.board_id == want.board_id
    assert got.passed == want.passed
    assert got.metrics == want.metrics
    assert got.baseline_metrics == want.baseline_metrics
    assert got.deltas == want.deltas
    assert got.warnings == want.warnings
    assert got.errors == want.errors
    assert got.skipped == want.skipped
    assert got.skip_reason == want.skip_reason
    assert got.board_shape == want.board_shape


def test_battery_verdict_report_repr_and_eq() -> None:
    cases = [
        dict(field_name="thermal", verdict="keep", verdict_details="ok", cost_seconds=1.5, budget_exceeded=False),
        dict(field_name="thermal", verdict="kill", verdict_details="KILL: margin", cost_seconds=12.5, budget_exceeded=True, event="kill"),
    ]
    for case in cases:
        got = _to.BatteryVerdictReport(**case)
        want = _oracle.BatteryVerdictReport(**case)
        assert repr(got) == repr(want)
        assert str(got) == str(want)
        assert got == _to.BatteryVerdictReport(**case)
        assert got != want  # type-strict dataclass eq


# ---------------------------------------------------------------------------
# RegressionReporter — counting + renderers
# ---------------------------------------------------------------------------


def _shim_reporter(results, verdicts=None):
    r = _to.RegressionReporter()
    for res in results:
        r.add_result(res)
    for bv in (verdicts or []):
        r.add_battery_verdict(bv)
    return r


def _oracle_reporter(results, verdicts=None):
    r = _oracle.RegressionReporter()
    for res in results:
        r.add_result(res)
    for bv in (verdicts or []):
        r.add_battery_verdict(bv)
    return r


_RESULT_SETS = [
    [],
    [_shim_board(board_id="b1", passed=True)],
    [_shim_board(board_id="b1", passed=True), _shim_board(board_id="b2", passed=False)],
    [_shim_board(board_id="b2", passed=False)],
    [_shim_board(board_id="b3", passed=False, skipped=True, skip_reason="missing")],
    [
        _shim_board(board_id="b1", passed=True),
        _shim_board(board_id="b2", passed=False, errors=["boom"]),
        _shim_board(board_id="b3", passed=False, skipped=True, skip_reason="no pcb"),
    ],
]


def test_reporter_counts_match_oracle() -> None:
    for results in _RESULT_SETS:
        got = _shim_reporter(results)
        want = _oracle_reporter(results)
        assert got.total == want.total
        assert got.passed == want.passed
        assert got.failed == want.failed
        assert got.skipped == want.skipped
        assert got.has_failures == want.has_failures


def test_reporter_summary_matches_oracle() -> None:
    for results in _RESULT_SETS:
        got = _shim_reporter(results).summary()
        want = _oracle_reporter(results).summary()
        assert got == want


def test_reporter_full_summary_matches_oracle() -> None:
    """The richest shape: board_shape, regression deltas, warnings, errors,
    skip reasons and battery verdicts all present."""
    shim_results = [
        _shim_board(
            board_id="b1", passed=True, board_shape={"component_count": 5, "net_count": 3},
            deltas=[_shim_delta(_METRIC_CASES[0])],
        ),
        _shim_board(
            board_id="b2", passed=False, board_shape={"component_count": 0, "net_count": 0},
            deltas=[
                _shim_delta(_METRIC_CASES[0]),
                _shim_delta(dict(name="drc_warnings", baseline=2.0, current=9.0, delta=7.0), regression=True),
            ],
            warnings=["warned"], errors=["errored"],
        ),
        _shim_board(board_id="b3", passed=False, skipped=True, skip_reason="no pcb"),
    ]
    oracle_results = [
        _oracle_board(
            board_id="b1", passed=True, board_shape={"component_count": 5, "net_count": 3},
            deltas=[_oracle_delta(_METRIC_CASES[0])],
        ),
        _oracle_board(
            board_id="b2", passed=False, board_shape={"component_count": 0, "net_count": 0},
            deltas=[
                _oracle_delta(_METRIC_CASES[0]),
                _oracle_delta(dict(name="drc_warnings", baseline=2.0, current=9.0, delta=7.0), regression=True),
            ],
            warnings=["warned"], errors=["errored"],
        ),
        _oracle_board(board_id="b3", passed=False, skipped=True, skip_reason="no pcb"),
    ]
    verdicts_shim = [
        _to.BatteryVerdictReport(field_name="thermal", verdict="keep", verdict_details="KEEP: margin", cost_seconds=12.5, budget_exceeded=False, event="keep"),
        _to.BatteryVerdictReport(field_name="cold", verdict="kill", verdict_details="KILL: over", cost_seconds=0.3, budget_exceeded=True),
    ]
    verdicts_oracle = [
        _oracle.BatteryVerdictReport(field_name="thermal", verdict="keep", verdict_details="KEEP: margin", cost_seconds=12.5, budget_exceeded=False, event="keep"),
        _oracle.BatteryVerdictReport(field_name="cold", verdict="kill", verdict_details="KILL: over", cost_seconds=0.3, budget_exceeded=True),
    ]
    got = _shim_reporter(shim_results, verdicts_shim).summary()
    want = _oracle_reporter(oracle_results, verdicts_oracle).summary()
    assert got == want
    assert "REGRESSION: drc_warnings" in got
    assert "BOARD: component_count=5, net_count=3" in got
    assert "[KEEP] thermal" in got
    assert "cost=12.5s" in got


def test_reporter_battery_report_matches_oracle() -> None:
    empty_got = _to.RegressionReporter().battery_report()
    empty_want = _oracle.RegressionReporter().battery_report()
    assert empty_got == empty_want == "No battery verdicts recorded."
    verdicts_shim = [
        _to.BatteryVerdictReport(field_name="thermal", verdict="keep", verdict_details="ok", cost_seconds=2.0, budget_exceeded=False),
        _to.BatteryVerdictReport(field_name="cold", verdict="inconclusive", verdict_details="budget over", cost_seconds=0.25, budget_exceeded=True),
    ]
    verdicts_oracle = [
        _oracle.BatteryVerdictReport(field_name="thermal", verdict="keep", verdict_details="ok", cost_seconds=2.0, budget_exceeded=False),
        _oracle.BatteryVerdictReport(field_name="cold", verdict="inconclusive", verdict_details="budget over", cost_seconds=0.25, budget_exceeded=True),
    ]
    got = _shim_reporter([], verdicts_shim).battery_report()
    want = _oracle_reporter([], verdicts_oracle).battery_report()
    assert got == want


def test_reporter_repr_matches_oracle() -> None:
    got = _shim_reporter([_shim_board(board_id="b1", passed=True)])
    want = _oracle_reporter([_oracle_board(board_id="b1", passed=True)])
    assert repr(got) == repr(want)


# ---------------------------------------------------------------------------
# PBT (Hypothesis): differential + invariants
# ---------------------------------------------------------------------------

_name = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_"),
    min_size=1,
    max_size=20,
)
# Float domain restricted to ordinary magnitudes — the David-Gay rendering
# stays CPython-routed (so parity holds everywhere), but Hypothesis stays in
# the values the pipeline actually produces.
_float = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False)


@settings(deadline=None)
@given(name=_name, baseline=_float, current=_float)
def test_pbt_delta_display_matches_oracle(name, baseline, current):
    delta = current - baseline
    got = _to.MetricDelta(name=name, baseline=baseline, current=current, delta=delta)
    want = _oracle.MetricDelta(name=name, baseline=baseline, current=current, delta=delta)
    assert got.delta_display == want.delta_display


@settings(deadline=None)
@given(name=_name, baseline=_float, current=_float, regression=st.booleans())
def test_pbt_delta_message_and_repr_match_oracle(name, baseline, current, regression):
    delta = current - baseline
    got = _to.MetricDelta(name=name, baseline=baseline, current=current, delta=delta, regression=regression)
    want = _oracle.MetricDelta(name=name, baseline=baseline, current=current, delta=delta, regression=regression)
    assert got.message() == want.message()
    assert repr(got) == repr(want)


@settings(deadline=None)
@given(n=st.integers(min_value=0, max_value=6), passed_count=st.integers(min_value=0, max_value=3), skipped_count=st.integers(min_value=0, max_value=2))
def test_pbt_reporter_counts_match_oracle(n, passed_count, skipped_count):
    """Differential: total/passed/failed/skipped/has_failures match the
    oracle over random mixes of passed/failed/skipped results."""
    results = [
        _shim_board(board_id=f"p{i}", passed=True) for i in range(passed_count)
    ] + [
        _shim_board(board_id=f"f{i}", passed=False) for i in range(n)
    ] + [
        _shim_board(board_id=f"s{i}", passed=False, skipped=True, skip_reason="missing") for i in range(skipped_count)
    ]
    oracle_results = [
        _oracle_board(board_id=f"p{i}", passed=True) for i in range(passed_count)
    ] + [
        _oracle_board(board_id=f"f{i}", passed=False) for i in range(n)
    ] + [
        _oracle_board(board_id=f"s{i}", passed=False, skipped=True, skip_reason="missing") for i in range(skipped_count)
    ]
    got = _shim_reporter(results)
    want = _oracle_reporter(oracle_results)
    assert got.total == want.total
    assert got.passed == want.passed
    assert got.failed == want.failed
    assert got.skipped == want.skipped
    assert got.has_failures == want.has_failures
    assert got.summary() == want.summary()


@settings(deadline=None)
@given(shape=st.dictionaries(st.sampled_from(["component_count", "net_count", "via_count"]), st.integers(min_value=0, max_value=50), min_size=0, max_size=3))
def test_pbt_board_shape_line_matches_oracle(shape):
    """Differential: the BOARD: shape line sorts keys and formats ints
    exactly like the oracle's sorted dict join."""
    got = _shim_reporter([_shim_board(board_id="b1", passed=True, board_shape=shape)]).summary()
    want = _oracle_reporter([_oracle_board(board_id="b1", passed=True, board_shape=shape)]).summary()
    assert got == want


@settings(deadline=None)
@given(
    name=_name, verdict=st.sampled_from(["keep", "kill", "inconclusive"]),
    cost=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    budget=st.booleans(),
)
def test_pbt_battery_report_matches_oracle(name, verdict, cost, budget):
    details = f"{verdict.upper()}: some details"
    got = _shim_reporter([], [
        _to.BatteryVerdictReport(field_name=name, verdict=verdict, verdict_details=details, cost_seconds=cost, budget_exceeded=budget)
    ]).battery_report()
    want = _oracle_reporter([], [
        _oracle.BatteryVerdictReport(field_name=name, verdict=verdict, verdict_details=details, cost_seconds=cost, budget_exceeded=budget)
    ]).battery_report()
    assert got == want


@settings(deadline=None)
@given(delta=_float)
def test_pbt_delta_display_sign_invariant(delta):
    """Invariant: delta_display is `str(delta)` with a single '+' prefix iff
    delta > 0 (0.0 and -0.0 carry no '+' — and -0.0 renders as '-0.0',
    matching the oracle's `str`)."""
    m = _to.MetricDelta(name="x", baseline=0.0, current=delta, delta=delta)
    want = f"+{delta}" if delta > 0 else f"{delta}"
    assert m.delta_display == want
    assert m.delta_display == _oracle.MetricDelta(
        name="x", baseline=0.0, current=delta, delta=delta
    ).delta_display


# ---------------------------------------------------------------------------
# Metamorphic relations (deterministic samples)
# ---------------------------------------------------------------------------


def test_meta_adding_a_failure_flips_has_failures() -> None:
    """Adding a failed result increments failed and flips has_failures; the
    passed/total counters move in lockstep."""
    r = _to.RegressionReporter()
    r.add_result(_shim_board(board_id="b1", passed=True))
    assert r.total == 1 and r.passed == 1 and not r.has_failures
    r.add_result(_shim_board(board_id="b2", passed=False))
    assert r.total == 2 and r.passed == 1 and r.failed == 1 and r.has_failures
    r.add_result(_shim_board(board_id="b3", passed=False, skipped=True, skip_reason="x"))
    assert r.total == 3 and r.skipped == 1 and r.failed == 1


def test_meta_only_regression_deltas_emit_lines() -> None:
    """summary() emits a REGRESSION line exactly for deltas whose regression
    flag is set, and the delta's message is the line body."""
    clean = _shim_delta(_METRIC_CASES[0], regression=False)
    reg = _shim_delta(dict(name="drc_errors", baseline=10.0, current=20.0, delta=10.0), regression=True)
    s = _shim_reporter([
        _shim_board(board_id="b1", passed=False, deltas=[clean, reg])
    ]).summary()
    assert "REGRESSION: drc_errors: 20.0 vs baseline 10.0 (+10.0)" in s
    assert s.count("REGRESSION:") == 1


def test_meta_summary_is_concatenation_of_result_lines() -> None:
    """summary() is a pure function of the results list: the per-board
    [PASS]/[FAIL]/[SKIP] lines appear in insertion order and each result's
    detail lines follow its header before the next board's."""
    s = _shim_reporter([
        _shim_board(board_id="a", passed=True, board_shape={"n": 1}),
        _shim_board(board_id="b", passed=False, errors=["e"]),
    ]).summary()
    assert s.index("[PASS] a") < s.index("[FAIL] b")
    assert s.index("BOARD: n=1") < s.index("[FAIL] b")
    assert s.index("ERROR: e") > s.index("[FAIL] b")


def test_meta_battery_report_empty_then_populated() -> None:
    """battery_report() is empty-exact before any verdict is added and
    includes every added verdict's fields after."""
    r = _to.RegressionReporter()
    assert r.battery_report() == "No battery verdicts recorded."
    r.add_battery_verdict(
        _to.BatteryVerdictReport(field_name="thermal", verdict="keep", verdict_details="ok", cost_seconds=2.0, budget_exceeded=False)
    )
    out = r.battery_report()
    assert "thermal: KEEP" in out
    assert "ok" in out
    assert "cost=2.0s, budget_exceeded=False" in out
