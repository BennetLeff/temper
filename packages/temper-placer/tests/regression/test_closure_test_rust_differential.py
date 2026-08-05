"""Differential test: closure-test self-consistency kernels in Rust
(``temper_drc_rs.closure_validate`` / ``temper_drc_rs.closure_summary``)
vs the pinned Python oracle (Wave 4, Phase 4 — regression slice).

``temper_placer/regression/closure_test.py`` moves its self-consistency
compute — ``ClosureResult.validate`` (the zero-results / insufficient-stages
assertions) and ``ClosureResult.summary`` (the exact report string, including
the ``:.1f`` formatting) — into ``temper_drc-rs``. The pre-migration module
is pinned verbatim as the oracle (``_closure_test_py_oracle.py``, commit
``0a29f15e3``).

Design boundaries, argued in the migrated module and
``packages/temper-drc-rs/VERIFICATION.md``:

- The ``ClosureTest.run()`` orchestration (Benders -> Router V6 -> KiCad DRC
  pipeline calls) stays Python — it consumes harness/pipeline modules that
  are out of this slice's surface; only the two self-consistency kernels
  migrate.
- The ``:.1f`` fixed-point report formatting is measured CPython-parity
  (the validation-slice precedent: 100k/100k on random values).
"""

from __future__ import annotations

import random

import pytest
import temper_drc_rs as _tdrc

import tests.regression._closure_test_py_oracle as _oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
CLOSURE_VALIDATE = _tdrc.closure_validate
CLOSURE_SUMMARY = _tdrc.closure_summary

from temper_placer.regression.closure_test import ClosureResult as ShimResult  # noqa: E402


# ---------------------------------------------------------------------------
# R1a — differential, bit-exact on every observable
# ---------------------------------------------------------------------------


def _random_params(rng):
    return dict(
        passed=bool(rng.getrandbits(1)),
        board_id="b1",
        benders_iterations=rng.randint(0, 4),
        benders_cuts=rng.randint(0, 20),
        router_completion_pct=rng.uniform(0.0, 100.0),
        drc_errors=rng.randint(0, 30),
        drc_warnings=rng.randint(0, 30),
        wall_clock_seconds=rng.uniform(0.0, 1000.0),
        stages_exercised=rng.randint(0, 6),
        errors=[f"e{i}" for i in range(rng.randint(0, 3))],
        warnings=[f"w{i}" for i in range(rng.randint(0, 3))],
    )


def test_differential_random_summary_and_validate():
    rng = random.Random(0x5EED)
    for _ in range(300):
        params = _random_params(rng)
        oracle = _oracle.ClosureResult(**params)
        shim = ShimResult(**params)
        assert shim.validate() == oracle.validate()
        assert shim.summary() == oracle.summary()


def test_differential_validate_edge_cases():
    cases = [
        dict(benders_iterations=1, router_completion_pct=50.0, stages_exercised=4),
        dict(benders_iterations=0, router_completion_pct=50.0, stages_exercised=4),
        dict(benders_iterations=1, router_completion_pct=0.0, stages_exercised=4),
        dict(benders_iterations=0, router_completion_pct=0.0, stages_exercised=4),
        dict(benders_iterations=1, router_completion_pct=50.0, stages_exercised=1),
        dict(benders_iterations=0, router_completion_pct=0.0, stages_exercised=0),
        dict(benders_iterations=0, router_completion_pct=0.0, stages_exercised=2),
        dict(benders_iterations=2, router_completion_pct=0.0, stages_exercised=2),
    ]
    for c in cases:
        oracle = _oracle.ClosureResult(passed=True, board_id="b", **c)
        shim = ShimResult(passed=True, board_id="b", **c)
        assert shim.validate() == oracle.validate()


def test_differential_summary_formatting():
    """The report string — including the .1f rendering of the pct/seconds —
    must match the oracle byte-for-byte."""
    params = dict(
        passed=False,
        board_id="temper_routed",
        benders_iterations=3,
        benders_cuts=17,
        router_completion_pct=94.25,
        drc_errors=3042,
        drc_warnings=0,
        wall_clock_seconds=123.456,
        stages_exercised=4,
        errors=["Placement not available: nope"],
        warnings=["Channel analysis failed: x"],
    )
    oracle = _oracle.ClosureResult(**params)
    shim = ShimResult(**params)
    o_summary = oracle.summary()
    s_summary = shim.summary()
    assert s_summary == o_summary
    assert "=== Closure Test: temper_routed ===" in s_summary
    assert "Status: FAIL" in s_summary
    assert "Router completion: 94.2%" in s_summary
    assert "Wall clock: 123.5s" in s_summary
    assert "ERROR: Placement not available: nope" in s_summary
    assert "WARNING: Channel analysis failed: x" in s_summary


def test_differential_summary_empty_lists():
    params = dict(
        passed=True,
        board_id="clean",
        benders_iterations=2,
        benders_cuts=0,
        router_completion_pct=100.0,
        drc_errors=0,
        drc_warnings=0,
        wall_clock_seconds=0.05,
        stages_exercised=4,
        errors=[],
        warnings=[],
    )
    oracle = _oracle.ClosureResult(**params)
    shim = ShimResult(**params)
    assert shim.summary() == oracle.summary()
    assert "Wall clock: 0.1s" in shim.summary()


# ---------------------------------------------------------------------------
# R1d — metamorphic relations (>=3, honestly bounded)
# ---------------------------------------------------------------------------


def test_mr1_iteration_monotonicity():
    """More Benders iterations can only remove the 'no placement iterations'
    failure, never add it; more stages_exercised can only remove the
    insufficient-stages failure."""
    for iters in range(0, 3):
        f_low = CLOSURE_VALIDATE(iters, 50.0, 4)
        f_high = CLOSURE_VALIDATE(iters + 1, 50.0, 4)
        # high has no failures that low lacks (the per-field assertions are
        # monotone in their own quantity)
        assert set(f_high) <= set(f_low)
    for stages in range(0, 3):
        f_low = CLOSURE_VALIDATE(2, 50.0, stages)
        f_high = CLOSURE_VALIDATE(2, 50.0, stages + 1)
        assert set(f_high) <= set(f_low)


def test_mr2_summary_warning_message_append_invariant():
    """Appending a warning to the warnings list appends exactly one
    ``WARNING:`` line and changes nothing else (same prefix length)."""
    base = _random_params(random.Random(7))
    base["warnings"] = []
    s0 = CLOSURE_SUMMARY(**base)
    base["warnings"] = ["w"]
    s1 = CLOSURE_SUMMARY(**base)
    assert s1 == s0 + "\n  WARNING: w"


def test_mr3_validate_zero_results_superset():
    """The 'zero-results' conjunctive failure is present iff BOTH placement
    and routing produced nothing; turning either nonzero removes only that
    line while keeping the per-field assertion."""
    for iters in (0, 1):
        for pct in (0.0, 10.0):
            f = CLOSURE_VALIDATE(iters, pct, 4)
            assert ("zero-results: both placement and routing produced no results" in f) == (
                iters <= 0 and pct <= 0.0
            )


# ---------------------------------------------------------------------------
# R1c — non-vacuous properties (>=5)
# ---------------------------------------------------------------------------


def test_prop1_no_failures_for_healthy_run():
    assert CLOSURE_VALIDATE(1, 50.0, 4) == []
    assert CLOSURE_VALIDATE(5, 100.0, 6) == []


def test_prop2_zero_placement_failure():
    assert CLOSURE_VALIDATE(0, 50.0, 4) == [
        "benders_iterations <= 0: pipeline produced no placement iterations"
    ]


def test_prop3_zero_routing_failure():
    assert CLOSURE_VALIDATE(1, 0.0, 4) == [
        "router_completion_pct <= 0: pipeline produced no routing results"
    ]


def test_prop4_insufficient_stages_message_embeds_count():
    f = CLOSURE_VALIDATE(1, 50.0, 1)
    assert f == ["stages_exercised (1) < 2: insufficient pipeline execution"]


def test_prop5_summary_status_matches_passed_flag():
    for passed in (True, False):
        s = CLOSURE_SUMMARY(
            board_id="b",
            passed=passed,
            benders_iterations=1,
            benders_cuts=0,
            router_completion_pct=50.0,
            drc_errors=0,
            drc_warnings=0,
            wall_clock_seconds=1.0,
            stages_exercised=4,
            errors=[],
            warnings=[],
        )
        assert f"Status: {'PASS' if passed else 'FAIL'}" in s


def test_prop6_summary_lines_are_stable_ordered():
    s = CLOSURE_SUMMARY(
        board_id="b",
        passed=True,
        benders_iterations=2,
        benders_cuts=3,
        router_completion_pct=50.0,
        drc_errors=1,
        drc_warnings=2,
        wall_clock_seconds=4.0,
        stages_exercised=4,
        errors=["e"],
        warnings=["w1", "w2"],
    )
    lines = s.split("\n")
    assert lines[0] == "=== Closure Test: b ==="
    assert lines[1] == "Status: PASS"
    assert lines[2] == "Benders iterations: 2, cuts: 3"
    assert lines[3] == "Router completion: 50.0%"
    assert lines[4] == "DRC: 1 errors, 2 warnings"
    assert lines[5] == "Wall clock: 4.0s"
    assert lines[6] == "Stages exercised: 4"
    assert lines[7] == "  ERROR: e"
    assert lines[8] == "  WARNING: w1"
    assert lines[9] == "  WARNING: w2"


def test_prop7_summary_round_trips_known_fields():
    """The numeric fields are recoverable from the rendered report."""
    s = CLOSURE_SUMMARY(
        board_id="b",
        passed=True,
        benders_iterations=7,
        benders_cuts=0,
        router_completion_pct=33.33,
        drc_errors=0,
        drc_warnings=0,
        wall_clock_seconds=9.999,
        stages_exercised=4,
        errors=[],
        warnings=[],
    )
    assert "Benders iterations: 7, cuts: 0" in s
    assert "Router completion: 33.3%" in s
    assert "Wall clock: 10.0s" in s
