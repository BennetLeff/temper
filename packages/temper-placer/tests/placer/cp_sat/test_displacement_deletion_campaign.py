"""Contracts for unconditional displacement deletion testing."""

from __future__ import annotations

import time
from dataclasses import dataclass

from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationLimits,
    RestorationStageStatus,
)
from temper_placer.placer.cp_sat.displacement_deletion_campaign import (
    DisplacementDeletionCampaignStatus,
    run_displacement_deletion_campaign,
)


@dataclass
class _Component:
    ref: str


@dataclass
class _Netlist:
    components: list[_Component]


@dataclass
class _WarmStart:
    hints: dict[str, tuple[float, float, int]]
    usable: bool = True


@dataclass
class _Solve:
    status: str
    positions: dict[str, tuple[float, float]] | None = None
    rotations: dict[str, int] | None = None


def _netlist(*refs: str) -> _Netlist:
    return _Netlist([_Component(ref) for ref in refs])


def _warm_start(*refs: str) -> _WarmStart:
    return _WarmStart({ref: (float(index), 10.0, 0) for index, ref in enumerate(refs)})


def _limits() -> RestorationLimits:
    return RestorationLimits(total_timeout_s=10.0, stage_timeout_s=2.0, memory_limit_mb=None)


def test_baseline_and_singletons_are_fresh_unconditional_models() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        radii = dict(kwargs["hard_displacement_radii_mm"])
        assert "hard_displacement_assumption_labels" not in kwargs
        assert kwargs["hard_displacement_assumptions"] is False
        assert kwargs["hard_displacement_to"] == {"A": (0.0, 10.0), "B": (1.0, 10.0), "C": (2.0, 10.0)}
        if all(value == 2.0 for value in radii.values()):
            return _Solve("infeasible")
        return _Solve(
            "infeasible",
            positions={ref: (float(index), 10.0) for index, ref in enumerate(("A", "B", "C"))},
            rotations=dict.fromkeys(("A", "B", "C"), 0),
        )

    result = run_displacement_deletion_campaign(
        _netlist("A", "B", "C"),
        object(),
        _warm_start("A", "B", "C"),
        {"z_group": ("C",), "a_group": ("A", "B")},
        solver=solver,
        limits=_limits(),
        test_balanced_halves=False,
    )

    assert result.status is DisplacementDeletionCampaignStatus.COMPLETE
    assert result.baseline is not None
    assert result.baseline.status is RestorationStageStatus.INFEASIBLE
    assert [report.released_groups for report in result.singleton_tests] == [
        ("a_group",),
        ("z_group",),
    ]
    assert [report.released_refs for report in result.singleton_tests] == [("A", "B"), ("C",)]
    assert result.baseline.component_radii_mm == {"A": 2.0, "B": 2.0, "C": 2.0}
    assert result.singleton_tests[0].component_radii_mm == {"A": 40.0, "B": 40.0, "C": 2.0}
    assert result.singleton_tests[1].component_radii_mm == {"A": 2.0, "B": 2.0, "C": 40.0}


def test_unknown_singleton_does_not_qualify_for_balanced_halves() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        radii = dict(kwargs["hard_displacement_radii_mm"])
        if all(value == 2.0 for value in radii.values()):
            return _Solve("infeasible")
        if radii["A"] == 40.0:
            return _Solve("unknown")
        return _Solve("infeasible")

    result = run_displacement_deletion_campaign(
        _netlist("A", "B", "C", "D"),
        object(),
        _warm_start("A", "B", "C", "D"),
        {"g0": ("A", "B"), "g1": ("C",), "g2": ("D",)},
        solver=solver,
        limits=_limits(),
    )

    assert result.status is DisplacementDeletionCampaignStatus.COMPLETE
    assert [report.status for report in result.singleton_tests] == [
        RestorationStageStatus.UNKNOWN,
        RestorationStageStatus.INFEASIBLE,
        RestorationStageStatus.INFEASIBLE,
    ]
    assert result.balanced_half_tests == ()


def test_balanced_halves_are_only_run_after_all_singletons_proven_infeasible() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        radii = dict(kwargs["hard_displacement_radii_mm"])
        if all(value == 2.0 for value in radii.values()):
            return _Solve("infeasible")
        return _Solve("infeasible")

    result = run_displacement_deletion_campaign(
        _netlist("A", "B", "C", "D"),
        object(),
        _warm_start("A", "B", "C", "D"),
        {"g0": ("A",), "g1": ("B",), "g2": ("C",), "g3": ("D",)},
        solver=solver,
        limits=_limits(),
    )

    assert result.status is DisplacementDeletionCampaignStatus.COMPLETE
    assert [report.released_groups for report in result.balanced_half_tests] == [
        ("g0", "g2"),
        ("g1", "g3"),
    ]


def test_verifier_only_sees_complete_feasible_candidates() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        radii = dict(kwargs["hard_displacement_radii_mm"])
        if all(value == 2.0 for value in radii.values()):
            return _Solve("infeasible")
        # Feasible status but incomplete candidate: exact verification must
        # not be called, and the report must retain the invalid solver result.
        return _Solve("feasible", positions={"A": (1.0, 1.0)}, rotations={"A": 0})

    def verify(_candidate: object) -> object:
        raise AssertionError("incomplete candidate reached exact verifier")

    result = run_displacement_deletion_campaign(
        _netlist("A", "B"),
        object(),
        _warm_start("A", "B"),
        {"all": ("A", "B")},
        solver=solver,
        verify=verify,
        limits=_limits(),
        test_balanced_halves=False,
    )

    report = result.singleton_tests[0]
    assert result.status is DisplacementDeletionCampaignStatus.INVALID
    assert report.status is RestorationStageStatus.INVALID
    assert report.verification_passed is False
    assert report.violation_count is None
    assert "incomplete placement" in result.diagnostics[0]


def test_baseline_unknown_stops_without_inventing_singleton_evidence() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        del kwargs
        return _Solve("unknown")

    result = run_displacement_deletion_campaign(
        _netlist("A"),
        object(),
        _warm_start("A"),
        {"all": ("A",)},
        solver=solver,
        limits=_limits(),
    )

    assert result.status is DisplacementDeletionCampaignStatus.STOPPED
    assert result.baseline is not None
    assert result.baseline.status is RestorationStageStatus.UNKNOWN
    assert result.singleton_tests == ()


def test_per_test_timeout_is_distinguished_from_campaign_deadline() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        radii = dict(kwargs["hard_displacement_radii_mm"])
        if all(value == 2.0 for value in radii.values()):
            return _Solve("infeasible")
        time.sleep(0.25)
        return _Solve("unknown")

    result = run_displacement_deletion_campaign(
        _netlist("A"),
        object(),
        _warm_start("A"),
        {"all": ("A",)},
        solver=solver,
        limits=RestorationLimits(total_timeout_s=2.0, stage_timeout_s=0.05, memory_limit_mb=None),
        test_balanced_halves=False,
    )

    assert result.status is DisplacementDeletionCampaignStatus.TIMEOUT
    assert result.singleton_tests[0].status is RestorationStageStatus.TIMEOUT
    assert result.diagnostics == ("one or more deletion tests timed out",)
