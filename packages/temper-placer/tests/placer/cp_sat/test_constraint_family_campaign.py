"""Focused contracts for fresh-model constraint-family probes."""

from __future__ import annotations

import multiprocessing as mp
from types import SimpleNamespace

from temper_placer.placer.cp_sat.constraint_family_campaign import (
    ConstraintFamilyCampaignResult,
    ConstraintFamilyCampaignStatus,
    ConstraintFamilyProbe,
    default_constraint_family_probes,
    run_constraint_family_campaign,
)
from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationLimits,
    RestorationStageStatus,
)


class _Netlist:
    components = (SimpleNamespace(ref="A"), SimpleNamespace(ref="B"))


def _limits() -> RestorationLimits:
    return RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None)


def test_default_plan_has_independent_singletons_then_cumulative_prefixes() -> None:
    probes = default_constraint_family_probes({"alpha": {}, "beta": {}, "gamma": {}})

    assert [probe.family_set for probe in probes] == [
        (),
        ("alpha",),
        ("beta",),
        ("gamma",),
        ("alpha", "beta"),
        ("alpha", "beta", "gamma"),
    ]


def test_each_probe_composes_fresh_exact_family_set_and_only_prior_accept_is_hint() -> None:
    manager = mp.Manager()
    calls = manager.list()

    def solver(_netlist: object, _board: object, **kwargs: object) -> SimpleNamespace:
        calls.append(dict(kwargs))
        if kwargs.get("beta_enabled") and not kwargs.get("alpha_enabled"):
            return SimpleNamespace(status="infeasible", positions={}, rotations={})
        return SimpleNamespace(
            status="optimal",
            positions={"A": (1.0, 2.0), "B": (3.0, 4.0)},
            rotations={"A": 0, "B": 1},
        )

    probes = (
        ConstraintFamilyProbe((), "base"),
        ConstraintFamilyProbe(("alpha",), "alpha"),
        ConstraintFamilyProbe(("beta",), "beta"),
        ConstraintFamilyProbe(("alpha", "beta"), "both"),
    )
    result = run_constraint_family_campaign(
        _Netlist(),
        object(),
        families={"alpha": {"alpha_enabled": True}, "beta": {"beta_enabled": True}},
        probes=probes,
        production_kwargs={"fixed": "base"},
        initial_hint_positions={"A": (9.0, 9.0, 0), "B": (8.0, 8.0, 0)},
        solver=solver,
        limits=_limits(),
    )

    assert result.status is ConstraintFamilyCampaignStatus.COMPLETE
    assert [report.status for report in result.probes] == [
        RestorationStageStatus.ACCEPTED,
        RestorationStageStatus.ACCEPTED,
        RestorationStageStatus.INFEASIBLE,
        RestorationStageStatus.ACCEPTED,
    ]
    assert [call.get("alpha_enabled", False) for call in calls] == [False, True, False, True]
    assert [call.get("beta_enabled", False) for call in calls] == [False, False, True, True]
    assert "hint_positions" in calls[0]
    assert calls[1]["hint_positions"] == {"A": (1.0, 2.0, 0), "B": (3.0, 4.0, 1)}
    # The failed beta probe must not become a hint for the fresh combined probe.
    assert "hint_positions" not in calls[3]
    assert calls[3]["fixed"] == "base"
    manager.shutdown()


def test_verifier_runs_only_for_complete_solver_candidates_and_is_separate_from_status() -> None:
    manager = mp.Manager()
    verified = manager.list()

    def solver(_netlist: object, _board: object, **kwargs: object) -> SimpleNamespace:
        if kwargs.get("which") == "bad":
            return SimpleNamespace(status="unknown", positions={}, rotations={})
        return SimpleNamespace(
            status="feasible",
            positions={"A": (1.0, 2.0), "B": (3.0, 4.0)},
            rotations={"A": 0, "B": 0},
        )

    def verify(candidate: object) -> SimpleNamespace:
        verified.append(candidate)
        return SimpleNamespace(violations=["one violation"])

    result = run_constraint_family_campaign(
        _Netlist(),
        object(),
        families={"bad": {"which": "bad"}, "good": {"which": "good"}},
        probes=((), ("bad",), ("good",)),
        solver=solver,
        verify=verify,
        limits=_limits(),
    )

    assert len(verified) == 2
    assert [report.status for report in result.probes] == [
        RestorationStageStatus.ACCEPTED,
        RestorationStageStatus.UNKNOWN,
        RestorationStageStatus.ACCEPTED,
    ]
    assert result.probes[0].verification_passed is False
    assert result.probes[0].violation_count == 1
    assert result.probes[1].verification_passed is None
    assert result.probes[2].verification_passed is False
    manager.shutdown()


def test_family_sets_are_rejected_when_options_conflict_or_assumptions_are_enabled() -> None:
    def solver(_netlist: object, _board: object, **_kwargs: object) -> SimpleNamespace:
        raise AssertionError("invalid family options must fail before worker start")

    conflict = run_constraint_family_campaign(
        _Netlist(),
        object(),
        families={"a": {"same": 1}, "b": {"same": 2}},
        probes=(("a", "b"),),
        solver=solver,
        limits=_limits(),
    )
    assert conflict.status is ConstraintFamilyCampaignStatus.INVALID
    assert conflict.probes[0].status is RestorationStageStatus.INVALID

    assumptions = run_constraint_family_campaign(
        _Netlist(),
        object(),
        families={"a": {"hard_displacement_assumptions": True}},
        probes=(("a",),),
        solver=solver,
        limits=_limits(),
    )
    assert assumptions.status is ConstraintFamilyCampaignStatus.INVALID
    assert assumptions.probes[0].status is RestorationStageStatus.INVALID


def test_custom_pure_planner_and_frontier_are_consumed() -> None:
    class Frontier:
        def __init__(self) -> None:
            self.rows: dict[tuple[str, ...], object] = {}

        def lookup(self, key: tuple[str, ...]) -> object | None:
            return self.rows.get(key)

        def add(self, key: tuple[str, ...], value: object) -> Frontier:
            self.rows[key] = value
            return self

    frontier = Frontier()
    planner_calls: list[tuple[object, object]] = []

    def planner(families: object, prior: object) -> tuple[ConstraintFamilyProbe, ...]:
        planner_calls.append((families, prior))
        return (ConstraintFamilyProbe(("one",), "planned"),)

    def solver(_netlist: object, _board: object, **kwargs: object) -> SimpleNamespace:
        if "marker" in kwargs:
            return SimpleNamespace(status="infeasible", positions={}, rotations={})
        return SimpleNamespace(status="optimal", positions={"A": (1.0, 1.0), "B": (2.0, 2.0)}, rotations={"A": 0, "B": 0})

    first = run_constraint_family_campaign(
        _Netlist(), object(), families={"one": {"marker": True}}, planner=planner,
        solver=solver, frontier=frontier, limits=_limits(),
    )
    second = run_constraint_family_campaign(
        _Netlist(), object(), families={"one": {"marker": True}}, planner=planner,
        solver=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cache miss")),
        frontier=frontier, limits=_limits(),
    )

    assert [probe.status for probe in first.probes] == [
        RestorationStageStatus.ACCEPTED,
        RestorationStageStatus.INFEASIBLE,
    ]
    assert [probe.status for probe in second.probes] == [
        RestorationStageStatus.ACCEPTED,
        RestorationStageStatus.INFEASIBLE,
    ]
    assert len(frontier.rows) == 2
    assert planner_calls and len(planner_calls[0][1]) == 1


def test_dynamic_planner_stops_after_nonaccepted_stripped_baseline() -> None:
    planner_calls: list[object] = []

    def planner(_families: object, prior: object) -> tuple[ConstraintFamilyProbe, ...]:
        planner_calls.append(prior)
        return (ConstraintFamilyProbe(("family",), "must-not-run"),)

    def solver(_netlist: object, _board: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(status="infeasible", positions={}, rotations={})

    result = run_constraint_family_campaign(
        _Netlist(),
        object(),
        families={"family": {}},
        planner=planner,
        solver=solver,
        limits=_limits(),
    )

    assert len(result.probes) == 1
    assert result.probes[0].family_set == ()
    assert result.probes[0].status is RestorationStageStatus.INFEASIBLE
    assert planner_calls == []


def test_cp_sat_package_exports_runner_without_shadowing_planner_probe() -> None:
    import temper_placer.placer.cp_sat as cp_sat
    from temper_placer.placer.cp_sat.constraint_family_probe_planner import (
        ConstraintFamilyProbe as PlannerProbe,
    )

    assert cp_sat.ConstraintFamilyProbe is PlannerProbe
    assert cp_sat.ConstraintFamilyProbeSpec is not PlannerProbe
    assert cp_sat.ConstraintFamilyCampaignResult is ConstraintFamilyCampaignResult
    assert callable(cp_sat.run_constraint_family_feasibility_campaign)
