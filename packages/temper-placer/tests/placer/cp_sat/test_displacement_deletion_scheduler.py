"""Pure planning contracts for multi-group deletion testing."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from temper_placer.placer.cp_sat.constraint_restoration_campaign import RestorationStageStatus
from temper_placer.placer.cp_sat.displacement_deletion_scheduler import (
    DeletionProbeKind,
    deletion_planner_state,
    plan_displacement_deletion_tests,
)


@dataclass(frozen=True)
class _Outcome:
    released_groups: tuple[str, ...]
    status: object


GROUPS = {
    "g0": ("A", "B"),
    "g1": ("C",),
    "g2": ("D", "E", "F"),
    "g3": ("G", "H"),
}


def _outcome(*groups: str, status: object) -> _Outcome:
    return _Outcome(tuple(groups), status)


def test_schedules_unseen_singletons_in_canonical_order() -> None:
    plans = plan_displacement_deletion_tests(
        GROUPS,
        [_outcome("g2", status="infeasible"), _outcome("g0", status="unknown")],
    )
    assert [plan.released_groups for plan in plans] == [("g1",), ("g3",)]
    assert all(plan.kind is DeletionProbeKind.SINGLETON for plan in plans)


def test_unknown_and_timeout_are_tested_but_never_negative_evidence() -> None:
    prior = [
        _outcome("g0", status="unknown"),
        _outcome("g1", status="timeout"),
        _outcome("g2", status=RestorationStageStatus.TIMEOUT),
    ]
    plans = plan_displacement_deletion_tests(GROUPS, prior)
    assert {plan.released_groups for plan in plans} == {("g3",)}
    state = deletion_planner_state(GROUPS, prior)
    assert state.proven_insufficient_singletons == ()
    assert state.untested_singletons == ("g3",)


def test_unknown_singletons_block_combination_frontier() -> None:
    prior = [_outcome(name, status="unknown") for name in GROUPS]
    assert plan_displacement_deletion_tests(GROUPS, prior) == ()


def test_all_singletons_infeasible_proposes_balanced_halves() -> None:
    prior = [_outcome(name, status="infeasible") for name in GROUPS]
    plans = plan_displacement_deletion_tests(GROUPS, prior)
    assert [plan.released_groups for plan in plans] == [("g1", "g2"), ("g0", "g3")]
    assert [plan.kind for plan in plans] == [DeletionProbeKind.BALANCED_HALF] * 2
    assert plans[0].released_refs == ("C", "D", "E", "F")


def test_singleton_negative_does_not_trigger_refinement_or_duplicate() -> None:
    prior = [_outcome(name, status="infeasible") for name in GROUPS]
    first = plan_displacement_deletion_tests(GROUPS, prior)
    second = plan_displacement_deletion_tests(GROUPS, [*prior, *first])
    assert all("." not in name for plan in first for name in plan.released_groups)
    # The halves have now been tested, so the next frontier is cross-half
    # combinations, not group subdivisions or duplicate halves.
    assert all(plan.kind is DeletionProbeKind.COMBINATION for plan in second)
    assert len({plan.canonical_key for plan in second}) == len(second)
    assert all(len(plan.released_groups) == 2 for plan in second)


def test_proven_infeasible_combination_prunes_its_subsets() -> None:
    prior = [_outcome(name, status="infeasible") for name in GROUPS]
    halves = plan_displacement_deletion_tests(GROUPS, prior)
    prior.extend(_outcome(*plan.released_groups, status="infeasible") for plan in halves)
    combos = plan_displacement_deletion_tests(GROUPS, prior)
    # The first half has 3 members and is proven insufficient; its internal
    # pairs are not scheduled.  Cross-half pairs remain valid candidates.
    assert all(not set(plan.released_groups).issubset(set(halves[0].released_groups)) for plan in combos)


def test_feasible_prior_result_stops_the_search() -> None:
    prior = [_outcome("g0", status="feasible")]
    assert plan_displacement_deletion_tests(GROUPS, prior) == ()


def test_canonical_dedup_accepts_mapping_and_report_order() -> None:
    prior = [
        {"released_groups": ("g1",), "status": "unknown"},
        _outcome("g0", status="timeout"),
    ]
    plans = plan_displacement_deletion_tests(GROUPS, prior, max_tests=1)
    assert len(plans) == 1
    assert plans[0].released_groups == ("g2",)


@pytest.mark.parametrize(
    "groups, message",
    [
        ({"g0": ("A",), "g1": ("A",)}, "distinct refs"),
        ({"g0": ()}, "must not be empty"),
        ({}, "groups must not be empty"),
    ],
)
def test_invalid_partitions_fail_closed(groups: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        plan_displacement_deletion_tests(groups)  # type: ignore[arg-type]
