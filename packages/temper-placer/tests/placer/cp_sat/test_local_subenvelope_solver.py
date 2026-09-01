"""Focused contract tests for the local sub-envelope CP-SAT boundary."""

from __future__ import annotations

import math

from temper_placer.placer.cp_sat.local_subenvelope_solver import (
    LocalComponentBounds,
    LocalSubEnvelopeSolveStatus,
    _verify_solution,
    solve_local_sub_envelope,
)


def test_packs_all_components_and_applies_exact_larger_pair_gap() -> None:
    result = solve_local_sub_envelope(
        "partition-A",
        [("U1", 4.0, 3.0), ("C1", 2.0, 2.0), ("R1", 3.0, 1.0)],
        [("U1", "C1", 6.0)],
        max_width_mm=20.0,
        max_height_mm=20.0,
        base_gap_mm=1.0,
        timeout_s=2.0,
        num_search_workers=1,
    )

    assert result.feasible
    assert result.status in (
        LocalSubEnvelopeSolveStatus.OPTIMAL,
        LocalSubEnvelopeSolveStatus.FEASIBLE,
    )
    assert set(result.component_bounds) == {"U1", "C1", "R1"}
    assert 0.0 < result.width_mm <= 20.0
    assert 0.0 < result.height_mm <= 20.0
    first, second = result.component_bounds["U1"], result.component_bounds["C1"]
    separation = max(
        second.x_min_mm - first.x_max_mm,
        first.x_min_mm - second.x_max_mm,
        second.y_min_mm - first.y_max_mm,
        first.y_min_mm - second.y_max_mm,
    )
    assert separation >= 6.0


def test_component_and_requirement_input_order_is_canonical() -> None:
    kwargs = {
        "max_width_mm": 20.0,
        "max_height_mm": 20.0,
        "base_gap_mm": 0.5,
        "timeout_s": 2.0,
        "num_search_workers": 1,
    }
    first = solve_local_sub_envelope(
        "partition-A",
        [("B", 2.0, 2.0), ("A", 2.0, 2.0)],
        [("B", "A", 4.0)],
        **kwargs,
    )
    second = solve_local_sub_envelope(
        "partition-A",
        [("A", 2.0, 2.0), ("B", 2.0, 2.0)],
        [("A", "B", 4.0)],
        **kwargs,
    )
    assert first.status == second.status
    assert first.width_mm == second.width_mm
    assert first.height_mm == second.height_mm
    assert first.component_bounds == second.component_bounds


def test_verify_solution_projects_mapping_through_component_order() -> None:
    components = [("A", 1.0, 1.0), ("B", 1.0, 1.0), ("C", 1.0, 1.0)]
    bound_a = LocalComponentBounds("A", 0.0, 0.0, 1.0, 1.0)
    bound_b = LocalComponentBounds("B", 0.0, 0.0, 1.0, 1.0)
    bound_c = LocalComponentBounds("C", 0.0, 0.0, 1.0, 1.0)
    bounds_in_input_order = {"A": bound_a, "B": bound_b, "C": bound_c}
    bounds_in_other_order = {"C": bound_c, "B": bound_b, "A": bound_a}
    kwargs = {
        "components": components,
        "requirements": [],
        "base_gap_mm": 1.0,
        "width_mm": 1.0,
        "height_mm": 1.0,
        "max_width_mm": 10.0,
        "max_height_mm": 10.0,
    }

    expected = _verify_solution(bounds_in_input_order, **kwargs)
    reordered = _verify_solution(bounds_in_other_order, **kwargs)
    assert expected == reordered == "components 'A' and 'B' violate base gap"


def test_invalid_infeasible_and_timeout_results_have_no_partial_geometry() -> None:
    invalid = solve_local_sub_envelope(
        "partition-A",
        [("U1", 4.0, math.nan)],
        [],
        20.0,
        20.0,
        1.0,
    )
    infeasible = solve_local_sub_envelope(
        "partition-A",
        [("A", 6.0, 6.0), ("B", 6.0, 6.0)],
        [],
        10.0,
        6.0,
        0.0,
        timeout_s=2.0,
        num_search_workers=1,
    )
    timeout = solve_local_sub_envelope(
        "partition-A",
        [("U1", 4.0, 3.0)],
        [],
        20.0,
        20.0,
        1.0,
        timeout_s=0.0,
    )
    for result in (invalid, infeasible, timeout):
        assert result.component_bounds == {}
        assert result.width_mm == 0.0
        assert result.height_mm == 0.0
        assert not result.feasible
    assert invalid.status is LocalSubEnvelopeSolveStatus.MODEL_INVALID
    assert infeasible.status is LocalSubEnvelopeSolveStatus.INFEASIBLE
    assert timeout.status is LocalSubEnvelopeSolveStatus.MODEL_INVALID


def test_base_gap_is_enforced_for_unlisted_pairs() -> None:
    result = solve_local_sub_envelope(
        "partition-A",
        [("A", 5.0, 5.0), ("B", 5.0, 5.0)],
        [],
        11.0,
        5.0,
        1.0,
        timeout_s=2.0,
        num_search_workers=1,
    )
    assert result.feasible
    first, second = result.component_bounds["A"], result.component_bounds["B"]
    assert max(
        second.x_min_mm - first.x_max_mm,
        first.x_min_mm - second.x_max_mm,
        second.y_min_mm - first.y_max_mm,
        first.y_min_mm - second.y_max_mm,
    ) >= 1.0


def test_envelope_dimensions_match_even_parity_consumer_grid() -> None:
    # The production ModelWrapper converts component sizes and envelope edges
    # to even 100-units/mm values for its midpoint equations.  A plain ceil
    # can emit an odd local extent (e.g. 1.01 mm -> 101 units), which the
    # consumer rounds down and makes the restricted envelope too small.
    result = solve_local_sub_envelope(
        "parity",
        [("A", 1.01, 1.01), ("B", 1.01, 1.01)],
        [],
        max_width_mm=10.0,
        max_height_mm=10.0,
        base_gap_mm=0.0,
        timeout_s=2.0,
        num_search_workers=1,
    )

    assert result.feasible
    assert round(result.width_mm * 100) % 2 == 0
    assert round(result.height_mm * 100) % 2 == 0

    def consumer_units(mm: float) -> int:
        raw = round(mm * 100)
        return raw - (raw % 2)

    # 1.01 mm is 101 fine-grid units, but the consumer's midpoint-compatible
    # conversion requires 102 even units.  The local result must survive that
    # conversion without shrinking below either component.
    assert consumer_units(result.width_mm) >= 102
    assert consumer_units(result.height_mm) >= 102


def test_headroom_expands_reported_extent_without_moving_components() -> None:
    kwargs = {
        "max_width_mm": 20.0,
        "max_height_mm": 20.0,
        "base_gap_mm": 1.0,
        "timeout_s": 2.0,
        "num_search_workers": 1,
    }
    without_headroom = solve_local_sub_envelope(
        "headroom",
        [("A", 2.0, 2.0), ("B", 2.0, 2.0)],
        [],
        **kwargs,
    )
    with_headroom = solve_local_sub_envelope(
        "headroom",
        [("A", 2.0, 2.0), ("B", 2.0, 2.0)],
        [],
        headroom_mm=1.0,
        **kwargs,
    )

    assert without_headroom.feasible
    assert with_headroom.feasible
    assert with_headroom.width_mm == without_headroom.width_mm + 1.0
    assert with_headroom.height_mm == without_headroom.height_mm + 1.0
    assert with_headroom.component_bounds == without_headroom.component_bounds


def test_headroom_overflow_fails_closed_without_geometry() -> None:
    result = solve_local_sub_envelope(
        "headroom-overflow",
        [("A", 9.0, 9.0)],
        [],
        max_width_mm=10.0,
        max_height_mm=10.0,
        base_gap_mm=0.0,
        headroom_mm=2.0,
        timeout_s=2.0,
        num_search_workers=1,
    )

    assert result.status is LocalSubEnvelopeSolveStatus.MODEL_INVALID
    assert result.component_bounds == {}
    assert result.width_mm == 0.0
    assert result.height_mm == 0.0


def test_objective_keeps_two_components_compact_inside_large_bound() -> None:
    result = solve_local_sub_envelope(
        "partition-A",
        [("A", 2.0, 2.0), ("B", 2.0, 2.0)],
        [],
        max_width_mm=100.0,
        max_height_mm=100.0,
        base_gap_mm=1.0,
        timeout_s=2.0,
        num_search_workers=1,
    )

    assert result.feasible
    # Either a 5x2 shelf or a 2x5 stack is safe; scattering toward the 100x100
    # bound is not an acceptable complete local envelope.
    assert result.width_mm <= 5.0
    assert result.height_mm <= 5.0


def test_objective_avoids_extreme_width_first_strip() -> None:
    result = solve_local_sub_envelope(
        "partition-strip-regression",
        [(f"C{index:02d}", 10.0, 10.0) for index in range(11)],
        [],
        max_width_mm=200.0,
        max_height_mm=200.0,
        base_gap_mm=1.0,
        timeout_s=3.0,
        num_search_workers=1,
    )

    assert result.feasible
    # A width-first objective can legally choose a 10x120 vertical strip.
    # Balanced normalized extent should choose a compact grid (approximately
    # 3x4), rather than consuming nearly the whole available height.
    assert result.width_mm <= 60.0
    assert result.height_mm <= 60.0
    assert max(result.width_mm, result.height_mm) / min(result.width_mm, result.height_mm) <= 2.0
