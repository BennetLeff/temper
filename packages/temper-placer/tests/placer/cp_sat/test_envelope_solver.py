"""Focused tests for the Rust-plan-facing coarse envelope solver."""

from __future__ import annotations

import math

from ortools.sat.python import cp_model

from temper_placer.placer.cp_sat.envelope_solver import (
    EnvelopeSolveStatus,
    solve_envelopes,
)


def _production_plan() -> list[tuple[str, list[str], float, float]]:
    return [
        ("HighVoltage", ["Q1", "GATE_H", "DC_BUS+"], 8.0, 6.0),
        ("Signal", ["U7", "SPI_CLK", "PWM_HS"], 7.0, 5.0),
        ("Tank", ["C6", "tank.c_tank1-p2"], 6.0, 6.0),
    ]


def _minimum_axis_gap(first: object, second: object) -> float:
    return max(
        second.x_min_mm - first.x_max_mm,  # type: ignore[attr-defined]
        first.x_min_mm - second.x_max_mm,  # type: ignore[attr-defined]
        second.y_min_mm - first.y_max_mm,  # type: ignore[attr-defined]
        first.y_min_mm - second.y_max_mm,  # type: ignore[attr-defined]
    )


def test_solves_realistic_partition_plan_with_maximum_pair_requirements() -> None:
    result = solve_envelopes(
        _production_plan(),
        [("HighVoltage", "Signal", 12.6), ("Signal", "Tank", 3.0)],
        board_width_mm=100.0,
        board_height_mm=80.0,
        time_limit_s=2.0,
    )

    assert result.status in (EnvelopeSolveStatus.OPTIMAL, EnvelopeSolveStatus.FEASIBLE)
    assert set(result.envelopes) == {"HighVoltage", "Signal", "Tank"}
    assert result.feasible
    for envelope in result.envelopes.values():
        assert 0.0 <= envelope.x_min_mm < envelope.x_max_mm <= 100.0
        assert 0.0 <= envelope.y_min_mm < envelope.y_max_mm <= 80.0
    assert (
        _minimum_axis_gap(result.envelopes["HighVoltage"], result.envelopes["Signal"])
        >= 12.6
    )
    assert _minimum_axis_gap(result.envelopes["Signal"], result.envelopes["Tank"]) >= 3.0


def test_input_order_does_not_change_canonical_result() -> None:
    requirements = [("Signal", "HighVoltage", 12.6), ("Tank", "Signal", 3.0)]
    first = solve_envelopes(
        _production_plan(),
        requirements,
        100.0,
        80.0,
        time_limit_s=2.0,
        num_search_workers=1,
        optimize_layout=True,
    )
    second = solve_envelopes(
        list(reversed(_production_plan())),
        list(reversed(requirements)),
        100.0,
        80.0,
        time_limit_s=2.0,
        num_search_workers=1,
        optimize_layout=True,
    )

    assert first.status == second.status
    assert first.envelopes == second.envelopes


def test_malformed_or_unsafe_inputs_fail_closed_without_bounds() -> None:
    malformed = solve_envelopes(
        [("HighVoltage", ["Q1"], math.nan, 6.0)],
        [],
        100.0,
        80.0,
        time_limit_s=2.0,
    )
    timeout_not_allowed = solve_envelopes(
        _production_plan(), [], 100.0, 80.0, time_limit_s=0.0
    )
    unknown_partition = solve_envelopes(
        _production_plan(), [("HighVoltage", "Missing", 12.6)], 100.0, 80.0, time_limit_s=2.0
    )
    invalid_workers = solve_envelopes(
        _production_plan(), [], 100.0, 80.0, time_limit_s=2.0, num_search_workers=0
    )
    excessive_workers = solve_envelopes(
        _production_plan(), [], 100.0, 80.0, time_limit_s=2.0, num_search_workers=65
    )

    for result in (
        malformed,
        timeout_not_allowed,
        unknown_partition,
        invalid_workers,
        excessive_workers,
    ):
        assert result.status is EnvelopeSolveStatus.MODEL_INVALID
        assert result.envelopes == {}
        assert not result.feasible


def test_infeasible_board_returns_no_partial_envelopes() -> None:
    result = solve_envelopes(
        [
            ("HighVoltage", ["Q1", "GATE_H"], 6.0, 10.0),
            ("Signal", ["U7", "SPI_CLK"], 6.0, 10.0),
        ],
        [],
        board_width_mm=10.0,
        board_height_mm=10.0,
        time_limit_s=2.0,
    )

    assert result.status is EnvelopeSolveStatus.INFEASIBLE
    assert result.envelopes == {}
    assert not result.feasible


def test_zero_requirement_still_uses_global_nonoverlap() -> None:
    result = solve_envelopes(
        [("HV", ["Q1"], 5.0, 5.0), ("LV", ["U1"], 5.0, 5.0)],
        [("HV", "LV", 0.0)],
        board_width_mm=10.0,
        board_height_mm=5.0,
        time_limit_s=2.0,
    )

    assert result.feasible
    assert result.envelopes["HV"].x_max_mm <= result.envelopes["LV"].x_min_mm or (
        result.envelopes["LV"].x_max_mm <= result.envelopes["HV"].x_min_mm
    )


def test_partition_may_rotate_when_only_the_90_degree_orientation_fits() -> None:
    result = solve_envelopes(
        [("GateDriveHV", ["U_GATE", "GATE_H"], 6.0, 4.0)],
        [],
        board_width_mm=4.0,
        board_height_mm=6.0,
        time_limit_s=2.0,
        num_search_workers=1,
        optimize_layout=True,
    )

    assert result.status is EnvelopeSolveStatus.OPTIMAL
    envelope = result.envelopes["GateDriveHV"]
    assert envelope.width_mm == 4.0
    assert envelope.height_mm == 6.0


def test_rotation_can_be_forbidden_globally_or_per_partition() -> None:
    globally_forbidden = solve_envelopes(
        [("GateDriveHV", ["U_GATE", "GATE_H"], 6.0, 4.0)],
        [],
        board_width_mm=4.0,
        board_height_mm=6.0,
        time_limit_s=2.0,
        num_search_workers=1,
        rotatable_partition_ids=set(),
    )
    per_partition_forbidden = solve_envelopes(
        [
            ("GateDriveHV", ["U_GATE", "GATE_H"], 6.0, 4.0),
            ("Signal", ["U7", "SPI_CLK"], 2.0, 2.0),
        ],
        [],
        board_width_mm=10.0,
        board_height_mm=10.0,
        time_limit_s=2.0,
        num_search_workers=1,
        rotatable_partition_ids={"Signal"},
    )

    assert globally_forbidden.status is EnvelopeSolveStatus.MODEL_INVALID
    assert globally_forbidden.envelopes == {}
    assert per_partition_forbidden.feasible
    envelope = per_partition_forbidden.envelopes["GateDriveHV"]
    assert (envelope.width_mm, envelope.height_mm) == (6.0, 4.0)


def test_rotation_control_and_hint_orientation_validation_fail_closed() -> None:
    unknown_id = solve_envelopes(
        [("GateDriveHV", ["U_GATE"], 4.0, 6.0)],
        [],
        board_width_mm=6.0,
        board_height_mm=4.0,
        time_limit_s=2.0,
        rotatable_partition_ids={"Missing"},
    )
    forbidden_hint = solve_envelopes(
        [("GateDriveHV", ["U_GATE"], 6.0, 4.0)],
        [],
        board_width_mm=4.0,
        board_height_mm=6.0,
        time_limit_s=2.0,
        initial_position_hints={"GateDriveHV": (0.0, 0.0)},
        rotatable_partition_ids=set(),
    )

    assert unknown_id.status is EnvelopeSolveStatus.MODEL_INVALID
    assert unknown_id.envelopes == {}
    assert forbidden_hint.status is EnvelopeSolveStatus.MODEL_INVALID
    assert forbidden_hint.envelopes == {}


def test_origin_hint_is_applied_without_weakening_geometry_checks(
    monkeypatch,
) -> None:
    hint_values: list[int] = []
    original_add_hint = cp_model.CpModel.add_hint

    def capture_hint(model, variable, value):
        hint_values.append(value)
        return original_add_hint(model, variable, value)

    monkeypatch.setattr(cp_model.CpModel, "add_hint", capture_hint)
    result = solve_envelopes(
        [("GateDriveHV", ["U_GATE", "GATE_H"], 4.0, 2.0)],
        [],
        board_width_mm=10.0,
        board_height_mm=10.0,
        time_limit_s=2.0,
        num_search_workers=1,
        initial_position_hints={"GateDriveHV": (6.0, 8.0)},
    )

    assert result.feasible
    envelope = result.envelopes["GateDriveHV"]
    assert 0.0 <= envelope.x_min_mm < envelope.x_max_mm <= 10.0
    assert 0.0 <= envelope.y_min_mm < envelope.y_max_mm <= 10.0
    assert hint_values == [600, 800, 0]


def test_pair_origin_hints_emit_one_deterministic_direction_hint(monkeypatch) -> None:
    captured: list[tuple[str, int]] = []
    original_add_hint = cp_model.CpModel.add_hint

    def capture_hint(model, variable, value):
        captured.append((variable.Name(), value))
        return original_add_hint(model, variable, value)

    monkeypatch.setattr(cp_model.CpModel, "add_hint", capture_hint)
    result = solve_envelopes(
        [("A", ["Q1"], 2.0, 2.0), ("B", ["Q2"], 2.0, 2.0)],
        [("A", "B", 1.0)],
        board_width_mm=10.0,
        board_height_mm=5.0,
        time_limit_s=2.0,
        num_search_workers=1,
        initial_position_hints={"A": (1.0, 1.0), "B": (6.0, 1.0)},
    )

    direction_hints = [
        (name, value) for name, value in captured if name.startswith("separation_")
    ]
    assert result.feasible
    assert len(direction_hints) == 4
    assert [value for _name, value in direction_hints].count(1) == 1
    assert direction_hints[0] == ("separation_left_0", 1)


def test_partial_hints_are_optional_but_malformed_hints_fail_closed() -> None:
    partial = solve_envelopes(
        _production_plan(),
        [],
        100.0,
        80.0,
        time_limit_s=2.0,
        initial_position_hints={"HighVoltage": (1.0, 1.0)},
    )
    unknown_id = solve_envelopes(
        _production_plan(),
        [],
        100.0,
        80.0,
        time_limit_s=2.0,
        initial_position_hints={"Missing": (1.0, 1.0)},
    )
    malformed = solve_envelopes(
        _production_plan(),
        [],
        100.0,
        80.0,
        time_limit_s=2.0,
        initial_position_hints={"HighVoltage": (math.nan, 1.0)},
    )
    infinite = solve_envelopes(
        _production_plan(),
        [],
        100.0,
        80.0,
        time_limit_s=2.0,
        initial_position_hints={"HighVoltage": (math.inf, 1.0)},
    )

    assert partial.feasible
    assert unknown_id.status is EnvelopeSolveStatus.MODEL_INVALID
    assert unknown_id.envelopes == {}
    assert malformed.status is EnvelopeSolveStatus.MODEL_INVALID
    assert malformed.envelopes == {}
    assert infinite.status is EnvelopeSolveStatus.MODEL_INVALID
    assert infinite.envelopes == {}
