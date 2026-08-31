"""Deterministic planning contracts for constraint-family probes."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from temper_placer.placer.cp_sat.constraint_family_probe_planner import (
    ConstraintFamilyProbeKind,
    constraint_family_planner_state,
    plan_constraint_family_probes,
)
from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationStageStatus,
)

FAMILIES = ("exact_creepage", "fixed_copper", "isolation_barrier", "validator_audit")


@dataclass(frozen=True)
class _Outcome:
    family_set: tuple[str, ...]
    status: object


def _outcome(*families: str, status: object) -> _Outcome:
    return _Outcome(tuple(families), status)


def _accepted_singletons() -> list[_Outcome]:
    return [_outcome(name, status="accepted") for name in FAMILIES]


def test_independent_probes_follow_declared_order_and_are_pure() -> None:
    first = plan_constraint_family_probes(FAMILIES)
    second = plan_constraint_family_probes(tuple(reversed(FAMILIES)))

    assert [probe.family_set for probe in first] == [(name,) for name in FAMILIES]
    assert all(probe.kind is ConstraintFamilyProbeKind.INDEPENDENT for probe in first)
    assert [probe.family_set for probe in second] == [(name,) for name in reversed(FAMILIES)]
    assert first == plan_constraint_family_probes(FAMILIES)


def test_cumulative_prefixes_start_after_all_independents() -> None:
    prior = _accepted_singletons()
    probes = plan_constraint_family_probes(FAMILIES, prior)

    assert [probe.family_set for probe in probes] == [("exact_creepage", "fixed_copper")]
    assert probes[0].kind is ConstraintFamilyProbeKind.CUMULATIVE_PREFIX

    prior.append(_outcome("fixed_copper", "exact_creepage", status="accepted"))
    next_probes = plan_constraint_family_probes(FAMILIES, prior)
    assert [probe.family_set for probe in next_probes] == [
        ("exact_creepage", "fixed_copper", "isolation_barrier")
    ]


def test_first_nonaccepted_prefix_schedules_leave_one_out_without_inference() -> None:
    prior = [*_accepted_singletons(),
             _outcome("exact_creepage", "fixed_copper", status="accepted"),
             _outcome("exact_creepage", "fixed_copper", "isolation_barrier", status="infeasible")]
    probes = plan_constraint_family_probes(FAMILIES, prior)

    assert [probe.family_set for probe in probes] == [
        ("fixed_copper", "isolation_barrier"),
        ("exact_creepage", "isolation_barrier"),
    ]
    assert all(probe.kind is ConstraintFamilyProbeKind.LEAVE_ONE_OUT for probe in probes)


def test_unknown_and_timeout_are_non_evidence_and_block_advancement() -> None:
    prior = [*_accepted_singletons(),
             _outcome("exact_creepage", "fixed_copper", status="accepted"),
             _outcome("exact_creepage", "fixed_copper", "isolation_barrier", status="timeout")]
    probes = plan_constraint_family_probes(FAMILIES, prior)
    assert {probe.family_set for probe in probes} == {
        ("fixed_copper", "isolation_barrier"),
        ("exact_creepage", "isolation_barrier"),
    }

    loo = [*_accepted_singletons(),
           _outcome("exact_creepage", "fixed_copper", status="accepted"),
           _outcome("exact_creepage", "fixed_copper", "isolation_barrier", status="infeasible"),
           _outcome("fixed_copper", "isolation_barrier", status="unknown"),
           _outcome("exact_creepage", "isolation_barrier", status="accepted"),
           _outcome("exact_creepage", "fixed_copper", status="accepted")]
    assert plan_constraint_family_probes(FAMILIES, loo) == ()


def test_infeasible_leave_one_out_recurses_to_smaller_active_set() -> None:
    prior = [*_accepted_singletons(),
             _outcome("exact_creepage", "fixed_copper", status="accepted"),
             _outcome("exact_creepage", "fixed_copper", "isolation_barrier", status="infeasible"),
             _outcome("fixed_copper", "isolation_barrier", status="infeasible"),
             _outcome("exact_creepage", "isolation_barrier", status="accepted"),
             _outcome("exact_creepage", "fixed_copper", status="accepted")]
    # The failed leave-one-out set is now the active pair.  Its members were
    # already accepted independently, so the pair is the minimal interaction.
    assert plan_constraint_family_probes(FAMILIES, prior) == ()


def test_all_leave_one_out_accepted_schedules_deterministic_bisection() -> None:
    prior = [*_accepted_singletons(),
             _outcome("exact_creepage", "fixed_copper", status="accepted"),
             _outcome("exact_creepage", "fixed_copper", "isolation_barrier", status="accepted"),
             _outcome("exact_creepage", "fixed_copper", "isolation_barrier", "validator_audit",
                      status="infeasible"),
             _outcome("fixed_copper", "isolation_barrier", "validator_audit", status="accepted"),
             _outcome("exact_creepage", "isolation_barrier", "validator_audit", status="accepted"),
             _outcome("exact_creepage", "fixed_copper", "validator_audit", status="accepted")]
    probes = plan_constraint_family_probes(FAMILIES, prior)

    # The lower half is an already-tested prefix and is deduplicated by exact
    # family set; only the fresh upper half remains to schedule.
    assert [probe.family_set for probe in probes] == [
        ("isolation_barrier", "validator_audit")
    ]
    assert probes[0].kind is ConstraintFamilyProbeKind.INTERACTION_BISECTION


def test_duplicate_exact_sets_are_canonicalized_across_kinds() -> None:
    prior = [*_accepted_singletons(),
             _outcome("fixed_copper", "exact_creepage", status="accepted"),
             _outcome("exact_creepage", "fixed_copper", status="accepted")]
    # The reordered duplicate is the cumulative prefix already known accepted.
    probes = plan_constraint_family_probes(FAMILIES, prior)
    assert probes[0].family_set == ("exact_creepage", "fixed_copper", "isolation_barrier")
    assert len({probe.canonical_key for probe in probes}) == len(probes)


def test_state_uses_restoration_status_and_retains_unresolved_rows() -> None:
    outcomes = [
        _outcome("exact_creepage", status=RestorationStageStatus.ACCEPTED),
        _outcome("fixed_copper", status=RestorationStageStatus.TIMEOUT),
    ]
    state = constraint_family_planner_state(FAMILIES, outcomes)
    assert state.accepted == (("exact_creepage",),)
    assert state.unresolved == (("fixed_copper",),)
    assert state.infeasible == ()


@pytest.mark.parametrize(
    "families, message",
    [
        ((), "must not be empty"),
        (("a", "a"), "duplicate"),
        (("a", ""), "non-empty"),
    ],
)
def test_invalid_family_lists_fail_closed(families: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        plan_constraint_family_probes(families)  # type: ignore[arg-type]
