"""Focused tests for bounded hierarchical coarse envelope placement."""

from __future__ import annotations

from temper_placer.placer.cp_sat.envelope_solver import (
    EnvelopeSolveStatus,
    solve_envelopes,
)
from temper_placer.placer.cp_sat.hierarchical_envelope_solver import (
    solve_hierarchical_envelopes,
)


def _plans() -> list[tuple[str, list[str], float, float]]:
    return [
        ("A", ["Q1"], 2.0, 2.0),
        ("B", ["Q2"], 2.0, 2.0),
        ("C", ["U1"], 2.0, 2.0),
        ("D", ["U2"], 2.0, 2.0),
    ]


def _separation(first: object, second: object) -> float:
    return max(
        second.x_min_mm - first.x_max_mm,  # type: ignore[attr-defined]
        first.x_min_mm - second.x_max_mm,  # type: ignore[attr-defined]
        second.y_min_mm - first.y_max_mm,  # type: ignore[attr-defined]
        first.y_min_mm - second.y_max_mm,  # type: ignore[attr-defined]
    )


def test_cross_batch_requirements_are_preserved_after_translation() -> None:
    result = solve_hierarchical_envelopes(
        _plans(),
        [("A", "C", 5.0), ("B", "D", 3.0)],
        board_width_mm=30.0,
        board_height_mm=30.0,
        time_limit_s=5.0,
        num_search_workers=1,
        max_batch_size=2,
    )

    assert result.feasible
    assert set(result.envelopes) == {"A", "B", "C", "D"}
    assert _separation(result.envelopes["A"], result.envelopes["C"]) >= 5.0
    assert _separation(result.envelopes["B"], result.envelopes["D"]) >= 3.0
    assert all(
        0.0 <= bound.x_min_mm <= bound.x_max_mm <= 30.0
        and 0.0 <= bound.y_min_mm <= bound.y_max_mm <= 30.0
        for bound in result.envelopes.values()
    )


def test_timeout_is_fail_closed_without_partial_batch_bounds() -> None:
    result = solve_hierarchical_envelopes(
        _plans(),
        [],
        board_width_mm=30.0,
        board_height_mm=30.0,
        time_limit_s=0.0,
        num_search_workers=1,
        max_batch_size=2,
    )

    assert result.status is EnvelopeSolveStatus.MODEL_INVALID
    assert result.envelopes == {}


def test_infeasible_batch_or_global_layout_has_no_partial_bounds() -> None:
    result = solve_hierarchical_envelopes(
        [
            ("A", ["Q1"], 10.0, 10.0),
            ("B", ["Q2"], 10.0, 10.0),
        ],
        [],
        board_width_mm=10.0,
        board_height_mm=10.0,
        time_limit_s=2.0,
        num_search_workers=1,
        max_batch_size=1,
    )

    assert result.status in (EnvelopeSolveStatus.UNKNOWN, EnvelopeSolveStatus.INFEASIBLE)
    assert result.envelopes == {}


def test_exact_global_requirements_avoid_batch_max_overconstraint() -> None:
    plans = [(f"p{index}", [f"r{index}"], 2.0, 2.0) for index in range(6)]
    exact_requirements = [
        ("p0", "p2", 7.0),
        ("p0", "p4", 7.0),
        ("p2", "p4", 7.0),
    ]
    # The retired abstraction replaced these three exact rows with a 7 mm
    # requirement between every pair of 4x2 batches.  That rectangle model is
    # infeasible on this board even though the exact component model fits.
    batch_rectangles = [
        ("g0", ("p0", "p1"), 4.0, 2.0),
        ("g1", ("p2", "p3"), 4.0, 2.0),
        ("g2", ("p4", "p5"), 4.0, 2.0),
    ]
    batch_max = [
        ("g0", "g1", 7.0),
        ("g0", "g2", 7.0),
        ("g1", "g2", 7.0),
    ]
    retired = solve_envelopes(
        batch_rectangles,
        batch_max,
        board_width_mm=11.0,
        board_height_mm=11.0,
        time_limit_s=2.0,
        num_search_workers=1,
    )
    exact = solve_hierarchical_envelopes(
        plans,
        exact_requirements,
        board_width_mm=11.0,
        board_height_mm=11.0,
        time_limit_s=5.0,
        num_search_workers=1,
        max_batch_size=2,
    )

    assert retired.status is EnvelopeSolveStatus.INFEASIBLE
    assert exact.feasible
    assert set(exact.envelopes) == {f"p{index}" for index in range(6)}
    assert _separation(exact.envelopes["p0"], exact.envelopes["p2"]) >= 7.0
    assert _separation(exact.envelopes["p0"], exact.envelopes["p4"]) >= 7.0
    assert _separation(exact.envelopes["p2"], exact.envelopes["p4"]) >= 7.0


def test_no_creepage_fallback_builds_warm_start_when_shelves_do_not_fit() -> None:
    # The two 4x6 singleton batches cannot be placed by the non-rotating
    # shelf assembler in a 6x8 board: the second shelf row would exceed the
    # height.  The no-requirement CP-SAT fallback can rotate both and stack
    # them as 6x4 rectangles, after which the exact global solve succeeds.
    result = solve_hierarchical_envelopes(
        [
            ("A", ["rA"], 4.0, 6.0),
            ("B", ["rB"], 4.0, 6.0),
        ],
        [],
        board_width_mm=6.0,
        board_height_mm=8.0,
        time_limit_s=3.0,
        num_search_workers=1,
        max_batch_size=1,
    )

    assert result.feasible
    assert set(result.envelopes) == {"A", "B"}
    assert all(
        0.0 <= bound.x_min_mm <= bound.x_max_mm <= 6.0
        and 0.0 <= bound.y_min_mm <= bound.y_max_mm <= 8.0
        for bound in result.envelopes.values()
    )


def test_rotation_control_is_forwarded_to_batch_and_final_kernel(monkeypatch) -> None:
    import temper_placer.placer.cp_sat.hierarchical_envelope_solver as hierarchy

    original = hierarchy.solve_envelopes
    forwarded: list[set[str] | None] = []

    def recording_kernel(*args, **kwargs):
        forwarded.append(kwargs.pop("rotatable_partition_ids"))
        return original(*args, **kwargs)

    monkeypatch.setattr(hierarchy, "solve_envelopes", recording_kernel)
    result = hierarchy.solve_hierarchical_envelopes(
        [("A", ["rA"], 2.0, 3.0)],
        [],
        board_width_mm=10.0,
        board_height_mm=10.0,
        time_limit_s=2.0,
        num_search_workers=1,
        rotatable_partition_ids=set(),
    )

    assert result.feasible
    assert forwarded == [set(), set()]


def test_rotation_allowlist_is_intersected_per_batch_and_preserved_globally(monkeypatch) -> None:
    import temper_placer.placer.cp_sat.hierarchical_envelope_solver as hierarchy

    original = hierarchy.solve_envelopes
    forwarded: list[set[str] | None] = []

    def recording_kernel(*args, **kwargs):
        forwarded.append(kwargs.pop("rotatable_partition_ids"))
        return original(*args, **kwargs)

    monkeypatch.setattr(hierarchy, "solve_envelopes", recording_kernel)
    result = hierarchy.solve_hierarchical_envelopes(
        [("A", ["rA"], 2.0, 3.0), ("B", ["rB"], 2.0, 3.0)],
        [],
        board_width_mm=10.0,
        board_height_mm=10.0,
        time_limit_s=2.0,
        num_search_workers=1,
        max_batch_size=1,
        rotatable_partition_ids={"A"},
    )

    assert result.feasible
    assert forwarded == [{"A"}, set(), {"A"}]
