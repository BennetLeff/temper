"""Focused tests for the opt-in coarse creepage envelope integration."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from temper_placer.placer.cp_sat import _encoder_solve
from temper_placer.placer.cp_sat.envelope_solver import (
    EnvelopeBounds,
    EnvelopeSolveResult,
    EnvelopeSolveStatus,
)


def _inputs() -> tuple[SimpleNamespace, SimpleNamespace]:
    component = SimpleNamespace(ref="Q_HS1", bounds=(2.0, 2.0), pins=[])
    netlist = SimpleNamespace(components=[component], nets=[])
    board = SimpleNamespace(width=20.0, height=20.0, constraints=[], zones=[])
    return netlist, board


def _quantization_inputs() -> tuple[SimpleNamespace, SimpleNamespace]:
    components = [
        SimpleNamespace(ref="Q1", bounds=(1.055, 1.0), pins=[]),
        SimpleNamespace(ref="Q2", bounds=(1.055, 1.0), pins=[]),
    ]
    netlist = SimpleNamespace(components=components, nets=[])
    board = SimpleNamespace(width=20.0, height=20.0, constraints=[], zones=[])
    return netlist, board


def test_partition_ref_projection_preserves_prepared_input_order() -> None:
    """The coarse lookup must not materialize membership from a set."""
    partitions = [
        ("9", ("B2", "A1"), 4.0, 2.0),
        ("2", ("C3",), 3.0, 1.0),
    ]
    assert _encoder_solve._refs_by_partition_in_input_order(partitions) == {
        "9": ("B2", "A1"),
        "2": ("C3",),
    }


def test_experimental_creepage_omission_keeps_ordinary_encoder_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only auto-generated creepage is omitted by the diagnostic switch."""
    netlist, board = _inputs()
    monkeypatch.setattr(
        "temper_placer.io.netclass_loader.load_netclass_rules",
        lambda _path: SimpleNamespace(design_rules=SimpleNamespace()),
    )
    monkeypatch.setattr(_encoder_solve, "courtyard_clearance_mm", lambda _default: 1.0)
    captured: dict[str, object] = {}

    def capture_encode(*_args: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(_encoder_solve, "encode_constraints", capture_encode)
    result = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        experimental_omit_generated_creepage=True,
    )
    assert result.status in {"optimal", "feasible"}
    assert captured["enforce_creepage"] is False
    # NoOverlap2D and board-bound constraints are installed before the
    # encoder dispatch and therefore remain active in this mode.
    assert result.positions


def test_generated_creepage_remains_eager_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    netlist, board = _inputs()
    monkeypatch.setattr(
        "temper_placer.io.netclass_loader.load_netclass_rules",
        lambda _path: SimpleNamespace(design_rules=SimpleNamespace()),
    )
    monkeypatch.setattr(_encoder_solve, "courtyard_clearance_mm", lambda _default: 1.0)
    captured: dict[str, object] = {}

    def capture_encode(*_args: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(_encoder_solve, "encode_constraints", capture_encode)
    _encoder_solve.solve_placement(netlist, board, timeout_ms=2_000)
    assert captured["enforce_creepage"] is True


def test_experimental_creepage_omission_is_explicitly_incompatible_with_lazy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    netlist, board = _inputs()
    with pytest.raises(ValueError, match="cannot be combined"):
        _encoder_solve.solve_placement(
            netlist,
            board,
            timeout_ms=2_000,
            lazy_creepage=True,
            experimental_omit_generated_creepage=True,
        )


def _patch_coarse_dependencies(monkeypatch: pytest.MonkeyPatch, result):
    netlist, board = _inputs()
    monkeypatch.setattr(
        "temper_placer.io.netclass_loader.load_netclass_rules",
        lambda _path: SimpleNamespace(design_rules=SimpleNamespace()),
    )
    monkeypatch.setattr(_encoder_solve, "courtyard_clearance_mm", lambda _default: 1.0)
    def _skip_encoding(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(_encoder_solve, "encode_constraints", _skip_encoding)
    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.netclass_constraints.verify_generated_creepage",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.envelope_preparation.prepare_envelope_inputs",
        lambda *_args, **_kwargs: SimpleNamespace(
            partitions=[("7", ["Q_HS1"], 2.0, 2.0)],
            pair_requirements=[],
            ref_to_partition={"Q_HS1": "7"},
            initial_position_hints={"7": (1.0, 1.0)},
        ),
    )
    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.envelope_solver.solve_envelopes",
        lambda *_args, **_kwargs: result,
    )
    return netlist, board


def test_decomposed_envelope_bounds_are_hard_constraints(monkeypatch: pytest.MonkeyPatch) -> None:
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.FEASIBLE,
        envelopes={
            "7": EnvelopeBounds("7", x_min_mm=3.0, y_min_mm=4.0, x_max_mm=8.0, y_max_mm=9.0)
        },
        solve_time_s=0.01,
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)

    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        decomposed_creepage=True,
    )

    assert placement.status in {"optimal", "feasible"}
    x_mm, y_mm = placement.positions["Q_HS1"]
    # Envelope coordinates are relative to the 0.5mm-margin board interior.
    # The boundary adds configured restriction slack plus quantization slack
    # on each edge; the exact creepage constraints remain unchanged.
    assert 2.49 <= x_mm <= 9.51
    assert 3.49 <= y_mm <= 10.51
    assert placement.decomposed_creepage_partition_count == 1
    assert placement.decomposed_creepage_envelope_solve_time_ms == pytest.approx(10.0)
    assert placement.decomposed_creepage_remaining_violations == ()


def test_failed_coarse_plan_returns_unknown_without_positions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.UNKNOWN,
        envelopes={},
        solve_time_s=0.02,
        message="timed out",
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)

    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        decomposed_creepage=True,
    )

    assert placement.status == "unknown"
    assert placement.positions == {}
    assert placement.rotations == {}
    assert placement.placed_refs == []
    assert placement.unplaced_refs == ["Q_HS1"]
    assert placement.decomposed_creepage_remaining_violations == ()
    assert placement.decomposed_creepage_prior_cut_count == 0
    assert placement.decomposed_creepage_new_cut_count == 0


def test_seeded_early_failure_reports_active_prior_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.UNKNOWN,
        envelopes={},
        solve_time_s=0.02,
        message="timed out",
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)
    netlist.components.append(SimpleNamespace(ref="Q2", bounds=(2.0, 2.0), pins=[]))

    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        decomposed_creepage=True,
        decomposed_creepage_prior_cuts=[("Q2", "Q_HS1", 4.0)],
    )

    assert placement.status == "unknown"
    assert placement.decomposed_creepage_prior_cut_count == 1
    assert placement.decomposed_creepage_new_cut_count == 0
    assert placement.decomposed_creepage_cuts == [("Q2", "Q_HS1", 4.0)]
    assert placement.decomposed_creepage_remaining_violations == ()
    assert placement.decomposed_creepage_effective_restriction_slack_mm == 8.0


def test_restricted_model_infeasibility_is_not_global_infeasibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The coarse result claims success, but its x envelope is narrower than
    # Q_HS1. The downstream model is therefore infeasible only because of the
    # restriction; the unrestricted problem must not be reported as UNSAT.
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.FEASIBLE,
        envelopes={
            "7": EnvelopeBounds("7", x_min_mm=3.0, y_min_mm=4.0, x_max_mm=3.5, y_max_mm=9.0)
        },
        solve_time_s=0.01,
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)

    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        decomposed_creepage=True,
        decomposed_creepage_restriction_slack_mm=0.0,
    )

    assert placement.status == "unknown"
    assert placement.positions == {}
    assert placement.decomposed_creepage_remaining_violations == ()
    assert placement.rotations == {}
    assert placement.unsat_core == []
    assert placement.decomposed_creepage_error == (
        "restricted coarse-envelope model is infeasible"
    )


def test_full_rust_verifier_remains_acceptance_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.FEASIBLE,
        envelopes={
            "7": EnvelopeBounds("7", x_min_mm=3.0, y_min_mm=4.0, x_max_mm=8.0, y_max_mm=9.0)
        },
        solve_time_s=0.01,
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)
    netlist.components.append(SimpleNamespace(ref="Q2", bounds=(2.0, 2.0), pins=[]))
    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.netclass_constraints.verify_generated_creepage",
        lambda *_args, **_kwargs: [("Q_HS1", "Q2", 1.0, 0.0)],
    )

    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        lazy_creepage_max_rounds=0,
        decomposed_creepage=True,
    )

    assert placement.status == "unknown"
    assert placement.positions == {}
    assert placement.decomposed_creepage_remaining_violations == (
        ("Q2", "Q_HS1", 1.0, 0.0),
    )


def test_coarse_worker_count_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.FEASIBLE,
        envelopes={
            "7": EnvelopeBounds("7", x_min_mm=3.0, y_min_mm=4.0, x_max_mm=8.0, y_max_mm=9.0)
        },
        solve_time_s=0.01,
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)
    calls: dict[str, object] = {}

    def _capture_workers(*_args: object, **kwargs: object) -> EnvelopeSolveResult:
        calls.update(kwargs)
        return result

    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.envelope_solver.solve_envelopes",
        _capture_workers,
    )
    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        decomposed_creepage=True,
        decomposed_creepage_envelope_workers=3,
    )

    assert placement.status in {"optimal", "feasible"}
    # A successful exhaustive verifier clears the diagnostic snapshot.
    assert placement.decomposed_creepage_remaining_violations == ()
    assert calls["num_search_workers"] == 3
    assert calls["initial_position_hints"] == {"7": (1.0, 1.0)}
    assert calls["rotatable_partition_ids"] == set()


def test_decomposed_eager_constraints_enable_authoritative_generated_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.FEASIBLE,
        envelopes={
            "7": EnvelopeBounds("7", x_min_mm=3.0, y_min_mm=4.0, x_max_mm=8.0, y_max_mm=9.0)
        },
        solve_time_s=0.01,
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)
    calls: dict[str, object] = {}

    def capture_encode(*_args: object, **kwargs: object) -> None:
        calls.update(kwargs)

    monkeypatch.setattr(_encoder_solve, "encode_constraints", capture_encode)
    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        decomposed_creepage=True,
    )

    assert placement.status in {"optimal", "feasible"}
    # This is the switch into the existing Rust-backed generator; the
    # generator itself owns cross-pin reduction, pair maxima, and uniqueness.
    assert calls["enforce_creepage"] is True


def test_replayed_cuts_are_canonical_hard_constraints_and_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.FEASIBLE,
        envelopes={
            "7": EnvelopeBounds("7", x_min_mm=3.0, y_min_mm=4.0, x_max_mm=8.0, y_max_mm=9.0)
        },
        solve_time_s=0.01,
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)
    netlist.components.append(SimpleNamespace(ref="Q2", bounds=(2.0, 2.0), pins=[]))
    calls: dict[str, object] = {}

    def capture_encode(constraints: object, *_args: object, **kwargs: object) -> None:
        calls["constraints"] = constraints
        calls.update(kwargs)

    monkeypatch.setattr(_encoder_solve, "encode_constraints", capture_encode)
    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        decomposed_creepage=True,
        decomposed_creepage_prior_cuts=[
            ("Q2", "Q_HS1", 4.0),
            ("Q_HS1", "Q2", 12.6),
            ("Q2", "Q_HS1", 8.0),
        ],
    )

    constraints = calls["constraints"]
    assert isinstance(constraints, list)
    replayed = [
        constraint
        for constraint in constraints
        if getattr(constraint, "id", "").startswith("replayed_creepage_")
    ]
    assert len(replayed) == 1
    assert replayed[0].a == "Q2"
    assert replayed[0].b == "Q_HS1"
    assert replayed[0].min_distance_mm == 12.6
    assert placement.decomposed_creepage_cuts == [("Q2", "Q_HS1", 12.6)]
    assert placement.decomposed_creepage_prior_cut_count == 1
    assert placement.decomposed_creepage_new_cut_count == 0


def test_verifier_discovered_cuts_survive_unknown_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.FEASIBLE,
        envelopes={
            "7": EnvelopeBounds("7", x_min_mm=3.0, y_min_mm=4.0, x_max_mm=8.0, y_max_mm=9.0)
        },
        solve_time_s=0.01,
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)
    netlist.components.append(SimpleNamespace(ref="Q2", bounds=(2.0, 2.0), pins=[]))
    monkeypatch.setattr(_encoder_solve, "encode_constraints", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.netclass_constraints.verify_generated_creepage",
        lambda *_args, **_kwargs: [
            ("Q2", "Q_HS1", 8.0, 1.5),
            ("Q_HS1", "Q2", 12.6, 0.75),
            ("Q2", "Q_HS1", 12.6, 0.5),
        ],
    )

    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        lazy_creepage_max_rounds=0,
        decomposed_creepage=True,
        decomposed_creepage_prior_cuts=[("Q2", "Q_HS1", 8.0)],
    )

    assert placement.status == "unknown"
    assert placement.decomposed_creepage_cuts == [("Q2", "Q_HS1", 12.6)]
    assert placement.decomposed_creepage_remaining_violations == (
        ("Q2", "Q_HS1", 12.6, 0.5),
    )
    assert placement.decomposed_creepage_prior_cut_count == 1
    # Symmetric/duplicate verifier rows reduce to one stronger replacement.
    assert placement.decomposed_creepage_new_cut_count == 1


def test_decomposed_eager_constraints_can_be_disabled_for_lazy_cut_testing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.FEASIBLE,
        envelopes={
            "7": EnvelopeBounds("7", x_min_mm=3.0, y_min_mm=4.0, x_max_mm=8.0, y_max_mm=9.0)
        },
        solve_time_s=0.01,
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)
    calls: dict[str, object] = {}

    def capture_encode(*_args: object, **kwargs: object) -> None:
        calls.update(kwargs)

    monkeypatch.setattr(_encoder_solve, "encode_constraints", capture_encode)
    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        decomposed_creepage=True,
        decomposed_creepage_eager_constraints=False,
    )

    assert placement.status in {"optimal", "feasible"}
    assert calls["enforce_creepage"] is False


def test_eager_flag_does_not_change_non_decomposed_lazy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.FEASIBLE,
        envelopes={},
        solve_time_s=0.01,
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)
    calls: dict[str, object] = {}

    def capture_encode(*_args: object, **kwargs: object) -> None:
        calls.update(kwargs)

    monkeypatch.setattr(_encoder_solve, "encode_constraints", capture_encode)
    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        decomposed_creepage=False,
    )

    assert placement.status in {"optimal", "feasible"}
    assert calls["enforce_creepage"] is False


def test_local_pack_budget_leaves_bounded_outer_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.FEASIBLE,
        envelopes={
            "7": EnvelopeBounds("7", x_min_mm=3.0, y_min_mm=4.0, x_max_mm=8.0, y_max_mm=9.0)
        },
        solve_time_s=0.01,
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)
    preparation_kwargs: dict[str, object] = {}
    solve_kwargs: dict[str, object] = {}

    def capture_preparation(*_args: object, **kwargs: object) -> SimpleNamespace:
        preparation_kwargs.update(kwargs)
        return SimpleNamespace(
            partitions=[("7", ["Q_HS1"], 2.0, 2.0)],
            pair_requirements=[],
            ref_to_partition={"Q_HS1": "7"},
            initial_position_hints={"7": (1.0, 1.0)},
            rotatable_partition_ids={"7"},
        )

    def capture_envelope_solve(*_args: object, **kwargs: object) -> EnvelopeSolveResult:
        solve_kwargs.update(kwargs)
        return result

    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.envelope_preparation.prepare_envelope_inputs",
        capture_preparation,
    )
    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.envelope_solver.solve_envelopes",
        capture_envelope_solve,
    )

    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=5_000,
        lazy_creepage=True,
        decomposed_creepage=True,
        decomposed_creepage_envelope_timeout_ms=2_000,
        decomposed_creepage_local_pack_timeout_ms=1_000,
        decomposed_creepage_envelope_headroom_mm=3.25,
    )

    assert placement.status in {"optimal", "feasible"}
    local_budget = preparation_kwargs["local_pack_total_timeout_s"]
    outer_budget = solve_kwargs["time_limit_s"]
    assert isinstance(local_budget, float)
    assert isinstance(outer_budget, float)
    assert 0.0 < local_budget <= 1.0
    assert outer_budget > 0.0
    assert preparation_kwargs["rotatable_component_refs"] == {"Q_HS1"}
    assert preparation_kwargs["headroom_mm"] == 3.25
    assert solve_kwargs["initial_position_hints"] == {"7": (1.0, 1.0)}
    assert solve_kwargs["rotatable_partition_ids"] == {"7"}


def test_absent_partition_hints_are_not_passed_as_fake_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.FEASIBLE,
        envelopes={
            "7": EnvelopeBounds("7", x_min_mm=3.0, y_min_mm=4.0, x_max_mm=8.0, y_max_mm=9.0)
        },
        solve_time_s=0.01,
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)
    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.envelope_preparation.prepare_envelope_inputs",
        lambda *_args, **_kwargs: SimpleNamespace(
            partitions=[("7", ["Q_HS1"], 2.0, 2.0)],
            pair_requirements=[],
            ref_to_partition={"Q_HS1": "7"},
            initial_position_hints={"7": None},
        ),
    )
    solve_kwargs: dict[str, object] = {}

    def capture_envelope_solve(*_args: object, **kwargs: object) -> EnvelopeSolveResult:
        solve_kwargs.update(kwargs)
        return result

    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.envelope_solver.solve_envelopes",
        capture_envelope_solve,
    )
    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        decomposed_creepage=True,
    )

    assert placement.status in {"optimal", "feasible"}
    assert solve_kwargs["initial_position_hints"] == {}
    assert solve_kwargs["rotatable_partition_ids"] == set()


@pytest.mark.parametrize(
    ("enforce_coarse_pair_gaps", "expected_requirements"),
    [(False, []), (True, [("0", "1", 12.6)])],
)
def test_production_sized_plan_controls_coarse_pair_gaps(
    monkeypatch: pytest.MonkeyPatch,
    enforce_coarse_pair_gaps: bool,
    expected_requirements: list[tuple[str, str, float]],
) -> None:
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.FEASIBLE,
        envelopes={
            str(partition_id): EnvelopeBounds(
                str(partition_id),
                x_min_mm=1.0,
                y_min_mm=1.0,
                x_max_mm=3.0,
                y_max_mm=3.0,
            )
            for partition_id in range(8)
        },
        solve_time_s=0.01,
    )
    netlist, board = _patch_coarse_dependencies(monkeypatch, result)
    partitions = [
        (str(partition_id), ["Q_HS1" if partition_id == 7 else f"UNUSED_{partition_id}"], 2.0, 2.0)
        for partition_id in range(8)
    ]
    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.envelope_preparation.prepare_envelope_inputs",
        lambda *_args, **_kwargs: SimpleNamespace(
            partitions=partitions,
            pair_requirements=[("0", "1", 12.6)],
            ref_to_partition={"Q_HS1": "7"},
            initial_position_hints={"7": (1.0, 1.0)},
            rotatable_partition_ids={"7"},
        ),
    )
    calls: dict[str, object] = {}

    def capture_hierarchy(*_args: object, **kwargs: object) -> EnvelopeSolveResult:
        calls.update(kwargs)
        calls["pair_requirements"] = _args[1]
        return result

    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.hierarchical_envelope_solver.solve_hierarchical_envelopes",
        capture_hierarchy,
    )
    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.envelope_solver.solve_envelopes",
        lambda *_args, **_kwargs: pytest.fail(
            "direct solver should not be selected for production-sized plans"
        ),
    )

    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        decomposed_creepage=True,
        decomposed_creepage_enforce_coarse_pair_gaps=enforce_coarse_pair_gaps,
    )

    assert placement.status in {"optimal", "feasible"}
    assert placement.decomposed_creepage_partition_count == 8
    assert calls["num_search_workers"] == 16
    assert isinstance(calls["time_limit_s"], float)
    assert calls["time_limit_s"] > 0.0
    assert calls["pair_requirements"] == expected_requirements
    assert "initial_position_hints" not in calls
    assert calls["rotatable_partition_ids"] == {"7"}


def test_quantized_component_boxes_do_not_false_fail_inside_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    netlist, board = _quantization_inputs()
    result = EnvelopeSolveResult(
        status=EnvelopeSolveStatus.FEASIBLE,
        envelopes={
            "7": EnvelopeBounds("7", x_min_mm=0.0, y_min_mm=0.0, x_max_mm=2.11, y_max_mm=1.0)
        },
        solve_time_s=0.01,
    )
    monkeypatch.setattr(
        "temper_placer.io.netclass_loader.load_netclass_rules",
        lambda _path: SimpleNamespace(design_rules=SimpleNamespace()),
    )
    monkeypatch.setattr(_encoder_solve, "courtyard_clearance_mm", lambda _default: 0.0)
    monkeypatch.setattr(_encoder_solve, "encode_constraints", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.netclass_constraints.verify_generated_creepage",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.envelope_preparation.prepare_envelope_inputs",
        lambda *_args, **_kwargs: SimpleNamespace(
            partitions=[("7", ["Q1", "Q2"], 2.11, 1.0)],
            pair_requirements=[],
            ref_to_partition={"Q1": "7", "Q2": "7"},
            initial_position_hints={"7": None},
        ),
    )
    monkeypatch.setattr(
        "temper_placer.placer.cp_sat.envelope_solver.solve_envelopes",
        lambda *_args, **_kwargs: result,
    )

    placement = _encoder_solve.solve_placement(
        netlist,
        board,
        timeout_ms=2_000,
        lazy_creepage=True,
        decomposed_creepage=True,
    )

    assert placement.status in {"optimal", "feasible"}
    assert placement.positions.keys() == {"Q1", "Q2"}


def test_restriction_slack_expands_and_clamps_component_window() -> None:
    assert _encoder_solve._decomposed_restriction_window(
        (100, 120, 300, 320),
        padding_units=1,
        restriction_slack_units=20,
        margin_units=50,
        board_width_units=1_000,
        board_height_units=1_000,
    ) == (129, 149, 371, 391)
    assert _encoder_solve._decomposed_restriction_window(
        (10, 10, 900, 900),
        padding_units=1,
        restriction_slack_units=20,
        margin_units=50,
        board_width_units=1_000,
        board_height_units=1_000,
    ) == (50, 50, 950, 950)


def test_decomposed_mode_requires_lazy_verifier() -> None:
    netlist, board = _inputs()
    with pytest.raises(ValueError, match="requires lazy_creepage"):
        _encoder_solve.solve_placement(
            netlist,
            board,
            decomposed_creepage=True,
        )


@pytest.mark.parametrize("eager", [0, 1, None, "true"])
def test_decomposed_eager_constraints_requires_boolean(eager: Any) -> None:
    netlist, board = _inputs()
    with pytest.raises(ValueError, match="eager_constraints"):
        _encoder_solve.solve_placement(
            netlist,
            board,
            lazy_creepage=True,
            decomposed_creepage=True,
            decomposed_creepage_eager_constraints=eager,
        )


@pytest.mark.parametrize("timeout_ms", [0, -1, True, 1.5])
def test_decomposed_envelope_timeout_must_be_positive_integer(timeout_ms: Any) -> None:
    netlist, board = _inputs()
    with pytest.raises(ValueError, match="envelope_timeout_ms"):
        _encoder_solve.solve_placement(
            netlist,
            board,
            lazy_creepage=True,
            decomposed_creepage=True,
            decomposed_creepage_envelope_timeout_ms=timeout_ms,
        )


@pytest.mark.parametrize("workers", [0, -1, 65, True, 1.5])
def test_decomposed_envelope_workers_are_bounded_integers(workers: Any) -> None:
    netlist, board = _inputs()
    with pytest.raises(ValueError, match="envelope_workers"):
        _encoder_solve.solve_placement(
            netlist,
            board,
            lazy_creepage=True,
            decomposed_creepage=True,
            decomposed_creepage_envelope_workers=workers,
        )


@pytest.mark.parametrize("local_timeout_ms", [0, -1, True, 1.5])
def test_decomposed_local_pack_timeout_must_be_positive_integer(
    local_timeout_ms: Any,
) -> None:
    netlist, board = _inputs()
    with pytest.raises(ValueError, match="local_pack_timeout_ms"):
        _encoder_solve.solve_placement(
            netlist,
            board,
            lazy_creepage=True,
            decomposed_creepage=True,
            decomposed_creepage_local_pack_timeout_ms=local_timeout_ms,
        )


@pytest.mark.parametrize("headroom_mm", [float("nan"), float("inf"), -0.1, True, "2.0"])
def test_decomposed_envelope_headroom_is_finite_and_non_negative(
    headroom_mm: Any,
) -> None:
    netlist, board = _inputs()
    with pytest.raises(ValueError, match="envelope_headroom_mm"):
        _encoder_solve.solve_placement(
            netlist,
            board,
            lazy_creepage=True,
            decomposed_creepage=True,
            decomposed_creepage_envelope_headroom_mm=headroom_mm,
        )


@pytest.mark.parametrize(
    "slack_mm", [float("nan"), float("inf"), -0.1, True, "2.0"]
)
def test_decomposed_restriction_slack_is_finite_and_non_negative(
    slack_mm: Any,
) -> None:
    netlist, board = _inputs()
    with pytest.raises(ValueError, match="restriction_slack_mm"):
        _encoder_solve.solve_placement(
            netlist,
            board,
            lazy_creepage=True,
            decomposed_creepage=True,
            decomposed_creepage_restriction_slack_mm=slack_mm,
        )


@pytest.mark.parametrize("enabled", [None, 0, 1, "yes"])
def test_decomposed_coarse_pair_gap_control_must_be_boolean(enabled: Any) -> None:
    netlist, board = _inputs()
    with pytest.raises(ValueError, match="enforce_coarse_pair_gaps"):
        _encoder_solve.solve_placement(
            netlist,
            board,
            lazy_creepage=True,
            decomposed_creepage=True,
            decomposed_creepage_enforce_coarse_pair_gaps=enabled,
        )


def test_creepage_cut_canonicalization_is_deterministic_and_max_reduced() -> None:
    assert _encoder_solve._canonical_creepage_cuts(
        [("B", "A", 4.0), ("A", "B", 12.6), ("C", "A", 2.0)],
        {"A", "B", "C"},
    ) == [("A", "B", 12.6), ("A", "C", 2.0)]


def test_creepage_violation_canonicalization_preserves_required_and_gap() -> None:
    assert _encoder_solve._canonical_creepage_violations(
        [
            ("B", "A", 4.0, 0.8),
            ("A", "B", 12.6, 0.7),
            ("B", "A", 12.6, 0.5),
            ("C", "A", 2.0, 1.0),
        ],
        {"A", "B", "C"},
    ) == (
        ("A", "B", 12.6, 0.5),
        ("A", "C", 2.0, 1.0),
    )


@pytest.mark.parametrize(
    "violations, message",
    [
        ([
            ("A", "A", 1.0, 0.0),
        ], "same component"),
        ([
            ("A", "MISSING", 1.0, 0.0),
        ], "unknown component"),
        ([
            ("A", "B", 1.0),
        ], "must be"),
        ([
            ("A", "B", float("nan"), 0.0),
        ], "invalid distance"),
        ([
            ("A", "B", 1.0, -0.1),
        ], "invalid distance"),
        ([
            ("A", "B", True, 0.0),
        ], "invalid distance"),
    ],
)
def test_creepage_violation_canonicalization_rejects_malformed_input(
    violations: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _encoder_solve._canonical_creepage_violations(  # type: ignore[arg-type]
            violations, {"A", "B"}
        )


@pytest.mark.parametrize(
    "cuts, message",
    [
        ([("A", "A", 1.0)], "same component"),
        ([("A", "MISSING", 1.0)], "unknown component"),
        ([("A", "B")], "must be"),
        ([("A", "B", float("nan"))], "invalid required"),
        ([("A", "B", -1.0)], "invalid required"),
        ([("A", "B", True)], "invalid required"),
    ],
)
def test_creepage_cut_canonicalization_rejects_malformed_input(
    cuts: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _encoder_solve._canonical_creepage_cuts(cuts, {"A", "B"})  # type: ignore[arg-type]


def test_first_lazy_round_reserves_budget_for_a_posted_cut() -> None:
    assert _encoder_solve._lazy_solver_budget_seconds(
        5_000, 0.0, None, reserve_s=1.0
    ) == pytest.approx(4.0)
    assert _encoder_solve._lazy_solver_budget_seconds(
        500, 0.0, None, reserve_s=1.0
    ) == 0.0


@pytest.mark.parametrize("reserve_ms", [-1, True, 1.5, "100"])
def test_post_cut_reserve_requires_non_negative_integer(reserve_ms: Any) -> None:
    netlist, board = _inputs()
    with pytest.raises(ValueError, match="post_cut_reserve_ms"):
        _encoder_solve.solve_placement(
            netlist,
            board,
            lazy_creepage=True,
            decomposed_creepage=True,
            lazy_creepage_post_cut_reserve_ms=reserve_ms,
        )
