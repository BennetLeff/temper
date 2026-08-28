"""Tests for the bounded production constraint-restoration campaign."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationCampaignStatus,
    RestorationLimits,
    RestorationStage,
    RestorationStageStatus,
    default_restoration_stages,
    distance_tier_restoration_stages,
    neighborhood_batched_creepage_constraints,
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


def test_distance_tiers_restore_exact_pairs_in_sorted_cumulative_order() -> None:
    stages = distance_tier_restoration_stages(
        SimpleNamespace(
            requirements=(
                ("B", "C", 12.6),
                ("A", "C", 0.5),
                ("A", "B", 12.6),
            )
        )
    )

    assert [stage.name for stage in stages] == [
        "baseline",
        "creepage_0.5mm",
        "creepage_12.6mm",
    ]
    assert stages[0].kwargs == {"experimental_omit_generated_creepage": True}
    half_mm = stages[1].kwargs["extra_constraints"]
    strongest = stages[2].kwargs["extra_constraints"]
    assert [(constraint.a, constraint.b) for constraint in half_mm] == [("A", "C")]
    assert [(constraint.a, constraint.b) for constraint in strongest] == [
        ("A", "B"),
        ("B", "C"),
    ]


def test_distance_tiers_reject_duplicate_pair_rows() -> None:
    instance = SimpleNamespace(
        requirements=(("A", "B", 0.5), ("B", "A", 12.6))
    )

    try:
        distance_tier_restoration_stages(instance)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:  # pragma: no cover - assertion helper without pytest dependency
        raise AssertionError("duplicate pair was accepted")


def test_neighborhood_batch_selects_local_alternatives_deterministically() -> None:
    requirements = (
        ("A", "B", 12.6),
        ("A", "D", 10.0),
        ("B", "C", 6.0),
        ("C", "D", 2.0),
        ("A", "E", 0.5),
    )
    positions = {
        "A": (0.0, 0.0),
        "C": (1.0, 1.0),
        "B": (10.0, 0.0),
        "D": (11.0, 1.0),
        "E": (100.0, 100.0),
    }

    constraints = neighborhood_batched_creepage_constraints(
        requirements,
        (("B", "A", 12.6, 5.0),),
        positions,
        radius_mm=2.0,
    )

    assert [(constraint.a, constraint.b) for constraint in constraints] == [
        ("C", "D"),
        ("B", "C"),
        ("A", "D"),
        ("A", "B"),
    ]


def test_neighborhood_batch_skips_active_pairs_and_rejects_missing_positions() -> None:
    requirements = (("A", "B", 12.6), ("A", "C", 6.0), ("B", "C", 2.0))
    positions = {"A": (0.0, 0.0), "B": (5.0, 0.0), "C": (5.0, 1.0)}
    constraints = neighborhood_batched_creepage_constraints(
        requirements,
        (("A", "B", 12.6, 0.0),),
        positions,
        radius_mm=6.1,
        existing_pairs=(("B", "A"),),
    )
    assert [(constraint.a, constraint.b) for constraint in constraints] == [
        ("B", "C"),
        ("A", "C"),
    ]

    try:
        neighborhood_batched_creepage_constraints(
            (("A", "MISSING", 1.0),),
            (("A", "MISSING", 1.0, 0.0),),
            {"A": (0.0, 0.0)},
        )
    except ValueError as exc:
        assert "without a position" in str(exc)
    else:  # pragma: no cover - assertion helper without pytest dependency
        raise AssertionError("missing position was accepted")


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
    assert stages[0].kwargs["experimental_omit_generated_creepage"] is True
    assert stages[1].kwargs["experimental_omit_generated_creepage"] is False


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
