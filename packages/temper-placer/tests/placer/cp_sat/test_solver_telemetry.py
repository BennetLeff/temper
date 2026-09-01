"""Focused tests for opt-in CP-SAT solver telemetry."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from temper_placer.core.netlist import Component, Netlist
from temper_placer.placer.cp_sat.encoder import solve_placement
from temper_placer.placer.cp_sat.solver_telemetry import (
    CpSatSolverTelemetry,
    extract_presolved_model_counts,
)


def _component(ref: str) -> Component:
    return Component(ref=ref, footprint="Synthetic", bounds=(4.0, 4.0), pins=[])


def _board() -> SimpleNamespace:
    return SimpleNamespace(width=60.0, height=60.0, zones=[], constraints=[])


def test_feasible_solve_reports_complete_telemetry() -> None:
    result = solve_placement(
        Netlist(components=[_component("U1")], nets=[]),
        _board(),
        extra_constraints=[],
        timeout_ms=1_000,
        capture_telemetry=True,
    )

    assert result.status in ("optimal", "feasible"), result.status
    telemetry = result.solver_telemetry
    assert isinstance(telemetry, CpSatSolverTelemetry)
    assert telemetry.input_model_source == "cp-model-proto"
    assert telemetry.input_variable_count >= 0
    assert telemetry.input_constraint_count >= 0
    assert telemetry.presolve_source == "solver-log"
    assert telemetry.presolved_variable_count is not None
    assert telemetry.presolved_variable_count >= 0
    assert telemetry.presolved_constraint_count is not None
    assert telemetry.presolved_constraint_count >= 0
    assert telemetry.presolve_unavailable_reason is None
    assert telemetry.presolve_source_lines
    assert telemetry.conflict_count >= 0
    assert telemetry.branch_count >= 0
    assert telemetry.solver_wall_time_s >= 0.0
    assert telemetry.first_incumbent_time_s is not None
    assert 0.0 <= telemetry.first_incumbent_time_s <= telemetry.solver_wall_time_s
    assert telemetry.first_incumbent_unavailable_reason is None
    assert "CpSolverResponse summary:" in telemetry.response_stats
    assert telemetry.input_model_stats


def test_infeasible_solve_records_why_first_incumbent_is_absent() -> None:
    result = solve_placement(
        Netlist(components=[_component("U1")], nets=[]),
        _board(),
        extra_constraints=[],
        timeout_ms=1_000,
        hard_displacement_to={"U1": (10.0, 12.0)},
        max_displacement_mm=0.0,
        fixed_positions={"U1": (20.0, 22.0, 0)},
        capture_telemetry=True,
    )

    assert result.status == "infeasible"
    telemetry = result.solver_telemetry
    assert telemetry is not None
    assert telemetry.first_incumbent_time_s is None
    assert telemetry.first_incumbent_unavailable_reason == (
        "solver returned INFEASIBLE without a complete incumbent"
    )
    assert telemetry.conflict_count >= 0
    assert telemetry.branch_count >= 0
    assert telemetry.solver_wall_time_s >= 0.0


def test_supported_presolve_text_extracts_variables_and_constraints() -> None:
    log_lines = (
        "Starting presolve at 0.00s",
        "Presolved satisfaction model 'probe': (model_fingerprint: 0x123)",
        "#Variables: 1,234 (1,000 primary variables)",
        "  - 1,200 Booleans in [0,1]",
        "#kBoolAnd: 20 (#enforced: 10)",
        "#kLinear2: 34",
        "",
        "Preloading model.",
    )

    counts = extract_presolved_model_counts(log_lines)

    assert counts.variable_count == 1_234
    assert counts.constraint_count == 54
    assert counts.source == "solver-log"
    assert counts.unavailable_reason is None
    assert counts.source_lines == log_lines[1:6]


def test_supported_presolve_text_accepts_ortools_apostrophe_separators() -> None:
    log_lines = (
        "Presolved satisfaction model 'probe': (model_fingerprint: 0x123)",
        "#Variables: 69'254 (68'577 primary variables)",
        "#kBoolOr: 14'308 (#literals: 52'832)",
        "#kLinear2: 52'982 (#enforced: 52'832)",
        "",
    )

    counts = extract_presolved_model_counts(log_lines)

    assert counts.variable_count == 69_254
    assert counts.constraint_count == 67_290


def test_changed_presolve_text_is_explicitly_unavailable() -> None:
    counts = extract_presolved_model_counts(
        (
            "Starting presolve at 0.00s",
            "Presolve model vNext: variables=12 constraints=4",
            "Preloading model.",
        )
    )

    assert counts.variable_count is None
    assert counts.constraint_count is None
    assert counts.source is None
    assert counts.source_lines == ()
    assert counts.unavailable_reason == (
        "supported 'Presolved ... model' block not found in solver log"
    )


def test_presolve_parsing_is_deterministic() -> None:
    log_lines = (
        "Presolved optimization model 'probe': (model_fingerprint: 0xabc)",
        "#Variables: 8 (3 primary variables)",
        "  - 8 in [0,10]",
        "#kLinear1: 2",
        "#kLinearN: 3 (#terms: 9)",
        "",
    )

    assert extract_presolved_model_counts(log_lines) == (
        extract_presolved_model_counts(tuple(log_lines))
    )


def test_telemetry_record_is_immutable() -> None:
    result = solve_placement(
        Netlist(components=[_component("U1")], nets=[]),
        _board(),
        extra_constraints=[],
        timeout_ms=1_000,
        capture_telemetry=True,
    )
    telemetry = result.solver_telemetry
    assert telemetry is not None

    with pytest.raises(FrozenInstanceError):
        telemetry.branch_count = 999  # type: ignore[misc]


def test_capture_disabled_preserves_default_result_and_stdout(capsys) -> None:
    result = solve_placement(
        Netlist(components=[_component("U1")], nets=[]),
        _board(),
        extra_constraints=[],
        timeout_ms=1_000,
    )

    captured = capsys.readouterr()
    assert result.status in ("optimal", "feasible"), result.status
    assert result.solver_telemetry is None
    assert captured.out == ""
    assert captured.err == ""


def test_capture_flag_rejects_non_boolean_values() -> None:
    with pytest.raises(ValueError, match="capture_telemetry must be a boolean"):
        solve_placement(
            Netlist(components=[_component("U1")], nets=[]),
            _board(),
            extra_constraints=[],
            capture_telemetry=1,  # type: ignore[arg-type]
        )
