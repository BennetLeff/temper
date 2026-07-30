"""TDD/PBT/metamorphic tests for absolute prover coverage."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from temper_placer.regression.coverage_ratchet import (
    CoverageSnapshot,
    evaluate_coverage,
)


def test_ratio_improvement_with_absolute_regression_fails() -> None:
    baseline = CoverageSnapshot.from_mapping(8, 10, {"signal": 8})
    narrowed_attempt = CoverageSnapshot.from_mapping(7, 8, {"signal": 7})

    result = evaluate_coverage(baseline, narrowed_attempt)

    assert result.passed is False
    assert "universe changed" in result.reason


def test_absolute_regression_with_stable_universe_fails() -> None:
    result = evaluate_coverage(
        CoverageSnapshot.from_mapping(8, 10, {"signal": 8}),
        CoverageSnapshot.from_mapping(7, 10, {"signal": 7}),
    )

    assert result.passed is False
    assert "absolute proven-net count regressed" in result.reason


def test_forward_absolute_progress_passes() -> None:
    result = evaluate_coverage(
        CoverageSnapshot.from_mapping(8, 10, {"signal": 8}),
        CoverageSnapshot.from_mapping(9, 10, {"signal": 8, "hv": 1}),
    )

    assert result.passed is True
    assert result.proven_delta == 1


def test_total_universe_change_fails_closed() -> None:
    result = evaluate_coverage(
        CoverageSnapshot.from_mapping(8, 10),
        CoverageSnapshot.from_mapping(8, 9),
    )

    assert result.passed is False
    assert "universe changed" in result.reason


@given(
    counts=st.dictionaries(
        st.sampled_from(["signal", "hv", "ac", "ground"]),
        st.integers(min_value=0, max_value=10),
        max_size=4,
    )
)
def test_breakdown_order_metamorphism(counts: dict[str, int]) -> None:
    first = CoverageSnapshot.from_mapping(5, 10, counts)
    second = CoverageSnapshot.from_mapping(
        5,
        10,
        dict(reversed(list(counts.items()))),
    )

    # Construction canonicalizes the domain order, so representation order
    # cannot alter the ratchet verdict or report.
    assert evaluate_coverage(first, first) == evaluate_coverage(second, second)
