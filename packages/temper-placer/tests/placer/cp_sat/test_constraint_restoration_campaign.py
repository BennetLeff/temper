"""Tests for the bounded production constraint-restoration campaign."""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationCampaignStatus,
    RestorationLimits,
    RestorationStage,
    RestorationStageStatus,
    default_restoration_stages,
    run_constraint_restoration_campaign,
)


@dataclass
class _Component:
    ref: str


@dataclass
class _Netlist:
    components: list[_Component]


@dataclass
class _Board:
    pass


@dataclass
class _Solve:
    status: str
    positions: dict[str, tuple[float, float]]
    rotations: dict[str, int]


def test_default_stage_order_is_deterministic() -> None:
    stages = default_restoration_stages(
        body_collision_audit={},
        exact_creepage={"lazy_creepage": True},
        isolation_barrier={"manifest_path": "barrier.yaml"},
        fixed_copper={"parse_result": object()},
    )
    assert [stage.name for stage in stages] == [
        "baseline",
        "exact_creepage",
        "isolation_barrier",
        "fixed_copper",
        "body_collision_audit",
    ]


def test_campaign_carries_previous_solution_as_a_hint_and_appends_constraints() -> None:
    netlist = _Netlist([_Component("A"), _Component("B")])

    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        # Encode the second-stage behavior in the result so this test remains
        # valid with the campaign's deliberately process-isolated worker.
        if kwargs.get("extra_constraints") == ["existing-hard-rule", "new-hard-rule"]:
            return _Solve("optimal", {"A": (1.0, 2.0), "B": (3.0, 4.0)}, {"A": 0, "B": 1})
        return _Solve("optimal", {"A": (5.0, 6.0), "B": (7.0, 8.0)}, {"A": 2, "B": 3})

    result = run_constraint_restoration_campaign(
        netlist,
        _Board(),
        stages=(
            RestorationStage("baseline"),
            RestorationStage("family", {"extra_constraints": ["new-hard-rule"]}),
        ),
        production_kwargs={"extra_constraints": ["existing-hard-rule"]},
        initial_hint_positions={"A": (10.0, 10.0, 0), "B": (12.0, 10.0, 0)},
        solver=solver,
        limits=RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )
    assert result.status is RestorationCampaignStatus.ACCEPTED
    assert result.placement == {"A": (1.0, 2.0), "B": (3.0, 4.0)}
    assert result.stages[0].positions == {"A": (5.0, 6.0), "B": (7.0, 8.0)}
    assert result.stages[1].rotations == {"A": 0, "B": 1}


def test_non_feasible_stage_stops_and_exposes_no_partial_placement() -> None:
    netlist = _Netlist([_Component("A")])
    def solver(_netlist: object, _board: object, **_kwargs: object) -> _Solve:
        return _Solve("unknown", {}, {})

    result = run_constraint_restoration_campaign(
        netlist,
        _Board(),
        stages=(RestorationStage("baseline"), RestorationStage("never-reached")),
        solver=solver,
        limits=RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )
    assert result.status is RestorationCampaignStatus.STOPPED
    assert result.placement == {}
    assert result.stages[0].status is RestorationStageStatus.UNKNOWN


def test_verifier_is_required_to_accept_when_supplied() -> None:
    netlist = _Netlist([_Component("A")])

    def solver(_netlist: object, _board: object, **_kwargs: object) -> _Solve:
        return _Solve("feasible", {"A": (1.0, 2.0)}, {"A": 0})

    class Verification:
        violations = ["not-clean"]

    result = run_constraint_restoration_campaign(
        netlist,
        _Board(),
        solver=solver,
        verify=lambda _result: Verification(),
        limits=RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )
    assert result.status is RestorationCampaignStatus.STOPPED
    assert result.stages[0].status is RestorationStageStatus.INVALID
    assert not result.placement


def test_duplicate_stage_option_replacement_fails_closed() -> None:
    netlist = _Netlist([_Component("A")])

    def solver(_netlist: object, _board: object, **_kwargs: object) -> _Solve:
        return _Solve("optimal", {"A": (1.0, 2.0)}, {"A": 0})

    result = run_constraint_restoration_campaign(
        netlist,
        _Board(),
        stages=(
            RestorationStage("baseline", {"seed": 1}),
            RestorationStage("bad", {"seed": 2}),
        ),
        solver=solver,
        limits=RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )
    assert result.status is RestorationCampaignStatus.INVALID
    assert result.stages[-1].status is RestorationStageStatus.INVALID
