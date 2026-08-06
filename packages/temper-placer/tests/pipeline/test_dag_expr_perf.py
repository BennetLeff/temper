"""R1b: performance A/B for the dag_expr Rust port.

Both arms assert PARITY IN-HARNESS. A benchmark that only measures can drift
into timing two things that no longer compute the same answer, at which point
the number is meaningless; here every timed iteration's result is captured and
compared by the same type-carrying signature the differential uses.

Inputs come from ``_dag_expr_fixtures`` -- the exact corpus and nesting depths
the differential covers. No parameter is invented here (#714/#721).

This module writes NO measurement artifact. It asserts a generous floor
(the port must not be dramatically SLOWER) and reports the ratio; committing a
timing baseline from a test is what silently rewrote a baseline -292/+91 in
this program, so the numbers go to stdout and the PR body, not to a file.
"""

from __future__ import annotations

import time

import pytest

from ._dag_expr_fixtures import (
    CORPUS,
    EVAL_CORPUS,
    NESTING_DEPTHS,
    make_env,
    nested_expr,
    outcome_signature,
    py_oracle,
    rust_impl,
)

#: Re-exported under the names the differential's coverage check asserts on.
#: These are the SAME objects, not copies -- that is the point.
BENCH_CORPUS = CORPUS
BENCH_DEPTHS = NESTING_DEPTHS

_REPEATS = 30

# An unoptimised build of the SAME Rust code measured 0.51x vs Python where
# the release build measures 2.70x -- a 5x swing that has nothing to do with
# the port. Ratio assertions are therefore only meaningful against a release
# build; parity assertions run either way, because correctness does not care
# about the profile.
_BUILD_PROFILE = getattr(rust_impl._rs, "BUILD_PROFILE", "unknown")
_IS_RELEASE = _BUILD_PROFILE == "release"
_DEBUG_REASON = (
    f"timing ratios are meaningless against a {_BUILD_PROFILE} build of "
    "temper_io_types; rebuild with --release to gate on speed"
)


def _time_parse(impl, sources: tuple[str, ...], repeats: int) -> tuple[float, list]:
    """Time parsing, capturing every outcome so parity can be checked."""
    outcomes: list = []
    # Warm up (regex compilation, import caches) outside the timed region.
    for src in sources:
        outcome_signature(impl.parse_skip_expr, src)

    start = time.perf_counter()
    for _ in range(repeats):
        for src in sources:
            outcomes.append(outcome_signature(impl.parse_skip_expr, src))
    elapsed = time.perf_counter() - start
    return elapsed, outcomes


def _time_eval(impl, sources: tuple[str, ...], repeats: int) -> tuple[float, list]:
    cfg, state, ctx = make_env()
    trees = [impl.parse_skip_expr(src) for src in sources]
    for tree in trees:
        outcome_signature(lambda t=tree: impl.evaluate_skip_expr(t, cfg, state, ctx))

    outcomes: list = []
    start = time.perf_counter()
    for _ in range(repeats):
        for tree in trees:
            outcomes.append(
                outcome_signature(lambda t=tree: impl.evaluate_skip_expr(t, cfg, state, ctx))
            )
    elapsed = time.perf_counter() - start
    return elapsed, outcomes


def test_parse_perf_ab_with_parity() -> None:
    py_time, py_outcomes = _time_parse(py_oracle, BENCH_CORPUS, _REPEATS)
    rs_time, rs_outcomes = _time_parse(rust_impl, BENCH_CORPUS, _REPEATS)

    # Parity first: a timing comparison between two different behaviours is
    # not a measurement of anything.
    assert rs_outcomes == py_outcomes, "arms diverged DURING the timed run"
    assert len(rs_outcomes) == _REPEATS * len(BENCH_CORPUS)

    ratio = py_time / rs_time if rs_time else float("inf")
    print(
        f"\n[dag_expr parse, {_BUILD_PROFILE}] python={py_time * 1e3:.2f}ms "
        f"rust={rs_time * 1e3:.2f}ms speedup={ratio:.2f}x "
        f"over {len(BENCH_CORPUS)} exprs x {_REPEATS}"
    )
    if not _IS_RELEASE:
        pytest.skip(_DEBUG_REASON)
    # Deliberately loose: this gate exists to catch a catastrophic regression
    # (e.g. re-parsing per call), not to police normal machine variance.
    assert ratio > 1.0, f"Rust parse is {1 / ratio:.1f}x SLOWER than Python"


def test_eval_perf_ab_with_parity() -> None:
    py_time, py_outcomes = _time_eval(py_oracle, EVAL_CORPUS, _REPEATS)
    rs_time, rs_outcomes = _time_eval(rust_impl, EVAL_CORPUS, _REPEATS)

    assert rs_outcomes == py_outcomes, "arms diverged DURING the timed run"

    ratio = py_time / rs_time if rs_time else float("inf")
    print(
        f"\n[dag_expr eval, {_BUILD_PROFILE}] python={py_time * 1e3:.2f}ms "
        f"rust={rs_time * 1e3:.2f}ms speedup={ratio:.2f}x "
        f"over {len(EVAL_CORPUS)} exprs x {_REPEATS}"
    )
    if not _IS_RELEASE:
        pytest.skip(_DEBUG_REASON)
    assert ratio > 1.0, f"Rust eval is {1 / ratio:.1f}x SLOWER than Python"


@pytest.mark.parametrize("depth", BENCH_DEPTHS, ids=lambda d: f"depth{d}")
def test_nested_parse_perf_ab_with_parity(depth: int) -> None:
    """Deep nesting is the parser's worst case; covered at every shared depth."""
    sources = (nested_expr(depth),)
    py_time, py_outcomes = _time_parse(py_oracle, sources, _REPEATS)
    rs_time, rs_outcomes = _time_parse(rust_impl, sources, _REPEATS)

    assert rs_outcomes == py_outcomes, f"arms diverged at depth {depth}"

    ratio = py_time / rs_time if rs_time else float("inf")
    print(f"\n[dag_expr parse depth={depth}, {_BUILD_PROFILE}] speedup={ratio:.2f}x")
    if not _IS_RELEASE:
        pytest.skip(_DEBUG_REASON)
    assert ratio > 1.0, f"Rust parse at depth {depth} is {1 / ratio:.1f}x SLOWER"
