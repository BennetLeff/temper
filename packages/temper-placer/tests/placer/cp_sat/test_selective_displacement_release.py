"""Focused contracts for UNSAT-core-driven selective displacement release."""

from __future__ import annotations

import time
from dataclasses import dataclass

from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationLimits,
    RestorationStageStatus,
    SelectiveDisplacementCampaignStatus,
    run_selective_displacement_campaign,
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
    unsat_core: object = ()
    positions: dict[str, tuple[float, float]] | None = None
    rotations: dict[str, int] | None = None


def _netlist(*refs: str) -> _Netlist:
    return _Netlist([_Component(ref) for ref in refs])


def _warm_start(*refs: str) -> _WarmStart:
    return _WarmStart({ref: (float(i), 10.0, 0) for i, ref in enumerate(refs)})


def _limits() -> RestorationLimits:
    return RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None)


def test_core_labels_are_stable_and_non_bound_assumptions_are_only_reported() -> None:
    """Only this campaign's exact labels may release a component."""

    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        assert kwargs["hard_displacement_assumption_labels"] == {
            "A": "displacement_bound_A",
            "B": "displacement_bound_B",
        }
        return _Solve(
            "infeasible",
            # Include all common solver payload shapes and a foreign label.
            [
                {"name": "foreign_production_constraint"},
                "displacement_bound_B",
                {"name": "displacement_bound_A"},
                {"name": "displacement_bound_A"},
            ],
        )

    result = run_selective_displacement_campaign(
        _netlist("A", "B"),
        object(),
        _warm_start("A", "B"),
        radii_mm=(5.0,),
        max_rounds=1,
        solver=solver,
        limits=_limits(),
    )

    assert result.status is SelectiveDisplacementCampaignStatus.STOPPED
    report = result.rounds[0]
    assert report.status is RestorationStageStatus.INFEASIBLE
    assert report.core_labels == (
        "displacement_bound_A",
        "displacement_bound_B",
        "foreign_production_constraint",
    )
    assert report.implicated_refs == ("A", "B")
    assert report.component_radii_mm == {"A": 2.0, "B": 2.0}
    # A foreign assumption is visible for diagnosis, but cannot release a
    # component because it is absent from the campaign-owned label map.
    assert "foreign_production_constraint" in report.core_labels


def test_escalation_is_deterministic_and_only_core_components_advance() -> None:
    """A fixed core produces a fixed per-component radius ladder."""

    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        radii = kwargs["hard_displacement_radii_mm"]
        assert isinstance(radii, dict)
        if radii["A"] == 2.0:
            return _Solve("infeasible", ["displacement_bound_A"])
        if radii["A"] == 5.0:
            return _Solve("infeasible", ["displacement_bound_A"])
        return _Solve(
            "optimal",
            positions={"A": (1.0, 1.0), "B": (2.0, 2.0)},
            rotations={"A": 0, "B": 0},
        )

    result = run_selective_displacement_campaign(
        _netlist("A", "B"),
        object(),
        _warm_start("A", "B"),
        radii_mm=(5.0, 10.0),
        solver=solver,
        limits=_limits(),
    )

    assert result.status is SelectiveDisplacementCampaignStatus.ACCEPTED
    assert [round_.component_radii_mm for round_ in result.rounds] == [
        {"A": 2.0, "B": 2.0},
        {"A": 5.0, "B": 2.0},
        {"A": 10.0, "B": 2.0},
    ]
    assert result.component_radii_mm == {"A": 10.0, "B": 2.0}


def test_repeated_core_stops_when_no_ladder_progress_remains() -> None:
    """A repeated core at the ladder ceiling must fail closed."""

    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        return _Solve("infeasible", ["displacement_bound_A"])

    result = run_selective_displacement_campaign(
        _netlist("A", "B"),
        object(),
        _warm_start("A", "B"),
        radii_mm=(5.0,),
        max_rounds=8,
        solver=solver,
        limits=_limits(),
    )

    assert result.status is SelectiveDisplacementCampaignStatus.STOPPED
    assert len(result.rounds) == 2
    assert result.rounds[0].implicated_refs == ("A",)
    assert result.rounds[1].implicated_refs == ("A",)
    assert result.component_radii_mm == {"A": 5.0, "B": 2.0}
    assert "top of the radius ladder" in result.diagnostics[0]


def test_malformed_core_labels_do_not_release_any_component() -> None:
    """Malformed/whitespace labels cannot be interpreted as bound labels."""

    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        return _Solve(
            "infeasible",
            [None, 42, {"name": 7}, {"name": " displacement_bound_A"}],
        )

    result = run_selective_displacement_campaign(
        _netlist("A"),
        object(),
        _warm_start("A"),
        radii_mm=(5.0,),
        max_rounds=1,
        solver=solver,
        limits=_limits(),
    )

    assert result.status is SelectiveDisplacementCampaignStatus.STOPPED
    assert result.rounds[0].core_labels == (" displacement_bound_A",)
    assert result.rounds[0].implicated_refs == ()
    assert result.component_radii_mm == {"A": 2.0}
    assert "no recognized displacement assumptions" in result.diagnostics[0]


def test_solver_error_is_fail_closed_without_placement_or_verification() -> None:
    verifier_called = False

    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        raise RuntimeError("synthetic solver failure")

    def verify(_result: object) -> object:
        nonlocal verifier_called
        verifier_called = True
        raise AssertionError("verification must not run after solver failure")

    result = run_selective_displacement_campaign(
        _netlist("A"),
        object(),
        _warm_start("A"),
        solver=solver,
        verify=verify,
        max_rounds=1,
        limits=_limits(),
    )

    assert result.status is SelectiveDisplacementCampaignStatus.STOPPED
    assert result.rounds[0].status is RestorationStageStatus.ERROR
    assert not result.placement
    assert not verifier_called


def test_timeout_is_fail_closed_without_running_exact_verifier() -> None:
    verifier_called = False

    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        time.sleep(0.5)
        return _Solve("optimal")

    def verify(_result: object) -> object:
        nonlocal verifier_called
        verifier_called = True
        raise AssertionError("verification must not run after timeout")

    result = run_selective_displacement_campaign(
        _netlist("A"),
        object(),
        _warm_start("A"),
        solver=solver,
        verify=verify,
        max_rounds=1,
        limits=RestorationLimits(total_timeout_s=2.0, stage_timeout_s=0.05, memory_limit_mb=None),
    )

    assert result.status is SelectiveDisplacementCampaignStatus.TIMEOUT
    assert result.rounds[0].status is RestorationStageStatus.TIMEOUT
    assert not result.placement
    assert not verifier_called


def test_exact_verifier_runs_only_after_complete_feasible_candidate() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        return _Solve(
            "feasible",
            positions={"A": (1.0, 1.0)},
            rotations={"A": 0},
        )

    def verify(candidate: object) -> object:
        assert isinstance(candidate, _Solve)
        assert candidate.positions == {"A": (1.0, 1.0)}
        # The worker runs in a child process, so an intentional exception is
        # the observable proof that the verifier was called after the
        # complete candidate passed the solver-status/shape gates.
        raise RuntimeError("verifier reached a complete feasible candidate")

    result = run_selective_displacement_campaign(
        _netlist("A"),
        object(),
        _warm_start("A"),
        solver=solver,
        verify=verify,
        max_rounds=1,
        limits=_limits(),
    )

    assert result.status is SelectiveDisplacementCampaignStatus.STOPPED
    assert result.rounds[0].status is RestorationStageStatus.ERROR
    assert "verifier reached a complete feasible candidate" in result.rounds[0].diagnostics[0]
    assert not result.placement
