"""Plan fresh-model displacement deletion probes.

This module deliberately contains no solver calls.  It answers the smaller,
deterministic question of *which release set should be tested next* from an
authoritative partition and the outcomes already recorded by a deletion
campaign.

The planner is conservative.  Only an explicitly proven ``infeasible``
outcome is negative evidence.  In particular, a timeout or an ``unknown``
solver result is not used to justify refining, pruning, or declaring a group
insufficient.  Release is monotone: if releasing a set was proven
insufficient, every subset is insufficient too.  This is what makes a proven
insufficient singleton useful -- its members are not recursively split while
searching for a sufficient release set.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from temper_placer.placer.cp_sat.constraint_restoration_campaign import RestorationStageStatus


class DeletionProbeKind(StrEnum):
    """Reason a planned release set was selected."""

    SINGLETON = "singleton"
    BALANCED_HALF = "balanced_half"
    COMBINATION = "combination"


@dataclass(frozen=True, slots=True)
class DeletionProbePlan:
    """A canonical, solver-independent deletion probe description."""

    released_groups: tuple[str, ...]
    released_refs: tuple[str, ...]
    kind: DeletionProbeKind
    reason: str

    @property
    def canonical_key(self) -> tuple[str, ...]:
        """The deduplication key; group ordering never changes a probe."""

        return self.released_groups

    @property
    def name(self) -> str:
        """Stable human-readable name suitable for a campaign report."""

        if self.kind is DeletionProbeKind.SINGLETON:
            return f"release_{self.released_groups[0]}"
        if self.kind is DeletionProbeKind.BALANCED_HALF:
            # The two halves are represented by one release set.  The name is
            # intentionally set-based and therefore stable under input order.
            return "release_half_" + "_".join(self.released_groups)
        return "release_combo_" + "_".join(self.released_groups)


@dataclass(frozen=True, slots=True)
class DeletionPlannerState:
    """Evidence summary used to explain a planner decision."""

    tested: tuple[tuple[str, ...], ...]
    proven_insufficient: tuple[tuple[str, ...], ...]
    proven_insufficient_singletons: tuple[str, ...]
    untested_singletons: tuple[str, ...]


def _normalise_groups(
    groups: Mapping[str, Sequence[str]] | Sequence[Sequence[str]],
) -> dict[str, tuple[str, ...]]:
    if isinstance(groups, (str, bytes)):
        raise ValueError("groups must be a mapping or sequence of ref groups")
    if isinstance(groups, Mapping):
        raw = groups.items()
    elif isinstance(groups, Sequence):
        raw = ((f"group_{index:03d}", refs) for index, refs in enumerate(groups))
    else:
        raise ValueError("groups must be a mapping or sequence of ref groups")

    result: dict[str, tuple[str, ...]] = {}
    members: list[str] = []
    for name_raw, refs_raw in raw:
        if not isinstance(name_raw, str) or not name_raw.strip():
            raise ValueError("group names must be non-empty strings")
        name = name_raw.strip()
        if name in result:
            raise ValueError(f"duplicate group name {name!r}")
        if isinstance(refs_raw, (str, bytes)) or not isinstance(refs_raw, Sequence):
            raise ValueError(f"group {name!r} must contain a sequence of refs")
        refs = tuple(sorted(refs_raw))
        if not refs:
            raise ValueError(f"group {name!r} must not be empty")
        if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
            raise ValueError(f"group {name!r} contains an invalid ref")
        if len(set(refs)) != len(refs):
            raise ValueError(f"group {name!r} contains duplicate refs")
        result[name] = refs
        members.extend(refs)
    if not result:
        raise ValueError("groups must not be empty")
    if len(set(members)) != len(members):
        raise ValueError("groups must partition distinct refs")
    return dict(sorted(result.items()))


def _status_value(raw: object) -> str | None:
    """Extract a normalized solver status from a report-like object."""

    value = raw.get("status") if isinstance(raw, Mapping) else getattr(raw, "status", raw)
    if isinstance(value, RestorationStageStatus):
        return value.value
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, str):
        return value.strip().lower()
    return None


def _released_groups(raw: object) -> tuple[str, ...] | None:
    """Extract and canonicalize a release-set key from a report-like object."""

    value: Any
    if isinstance(raw, Mapping):
        value = raw.get("released_groups")
        if value is None:
            value = raw.get("groups_released")
    else:
        value = getattr(raw, "released_groups", None)
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        return None
    names = tuple(value)
    if any(not isinstance(name, str) or not name.strip() for name in names):
        return None
    return tuple(sorted({name.strip() for name in names}))


def _balanced_halves(groups: Mapping[str, tuple[str, ...]]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Assign groups greedily to two member-count-balanced, stable halves."""

    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    halves: list[list[str]] = [[], []]
    weights = [0, 0]
    for name, refs in ordered:
        target = 0 if weights[0] <= weights[1] else 1
        halves[target].append(name)
        weights[target] += len(refs)
    return tuple(sorted(halves[0])), tuple(sorted(halves[1]))


def _is_proven_infeasible(status: str | None) -> bool:
    # Do not broaden this list: ``unknown``, timeout, model-invalid, and
    # malformed reports are all non-evidence for deletion planning.
    return status == RestorationStageStatus.INFEASIBLE.value or status == "infeasible"


def _is_feasible(status: str | None) -> bool:
    return status in {"accepted", "feasible", "optimal"}


def _subset_pruned(candidate: tuple[str, ...], insufficient: Sequence[tuple[str, ...]]) -> bool:
    candidate_set = set(candidate)
    return any(set(negative).issuperset(candidate_set) for negative in insufficient)


def plan_displacement_deletion_tests(
    groups: Mapping[str, Sequence[str]] | Sequence[Sequence[str]],
    prior_outcomes: Iterable[object] = (),
    *,
    max_tests: int | None = None,
    combination_size: int = 2,
) -> tuple[DeletionProbePlan, ...]:
    """Return the next canonical deletion probes.

    ``prior_outcomes`` accepts ``DisplacementDeletionTestResult`` instances,
    or small mappings with ``released_groups`` and ``status`` fields.  Unknown
    and timed-out outcomes count as already-tested keys (so they are not
    rerun accidentally), but never as proven-insufficient evidence.

    Singleton probes are scheduled first.  Once every singleton has a
    *proven-insufficient* outcome, the planner proposes two member-balanced
    halves.  If a singleton is unknown or timed out, no combination is
    proposed: that uncertainty must be resolved before widening the release
    set.  After both halves are themselves proven insufficient, it proposes
    deterministic cross-half combinations of ``combination_size`` groups.  Any
    candidate already tested or contained in a proven-insufficient set is
    omitted.  A feasible outcome terminates the plan: callers should consume
    that candidate rather than launch unrelated probes.
    """

    canonical = _normalise_groups(groups)
    if isinstance(combination_size, bool) or not isinstance(combination_size, int) or combination_size < 2:
        raise ValueError("combination_size must be an integer >= 2")
    if max_tests is not None and (isinstance(max_tests, bool) or not isinstance(max_tests, int) or max_tests < 0):
        raise ValueError("max_tests must be None or a non-negative integer")

    known_groups = set(canonical)
    tested: set[tuple[str, ...]] = set()
    insufficient: set[tuple[str, ...]] = set()
    has_feasible = False
    for outcome in prior_outcomes:
        key = _released_groups(outcome)
        if key is None or any(name not in known_groups for name in key):
            # Invalid historical rows cannot safely prune a future probe.
            continue
        status = _status_value(outcome)
        tested.add(key)
        if _is_proven_infeasible(status):
            insufficient.add(key)
        elif _is_feasible(status):
            has_feasible = True
    if has_feasible:
        return ()

    plans: list[DeletionProbePlan] = []
    seen: set[tuple[str, ...]] = set(tested)

    def add(key: Sequence[str], kind: DeletionProbeKind, reason: str) -> None:
        canonical_key = tuple(sorted(set(key)))
        if not canonical_key or any(name not in known_groups for name in canonical_key):
            return
        if canonical_key in seen or _subset_pruned(canonical_key, insufficient):
            return
        seen.add(canonical_key)
        refs = tuple(sorted(ref for name in canonical_key for ref in canonical[name]))
        plans.append(DeletionProbePlan(canonical_key, refs, kind, reason))

    singleton_outcomes = {key[0] for key in tested if len(key) == 1}
    # An insufficient singleton proves that all of its subsets are
    # insufficient.  It is therefore intentionally not split/refined.
    untested = tuple(sorted(known_groups - singleton_outcomes))
    for name in untested:
        add((name,), DeletionProbeKind.SINGLETON, "singleton has no prior outcome")

    # If even one singleton is unresolved, wait for it before making a
    # combination recommendation.  In particular, unknown/timeouts are not
    # silently promoted to the all-singletons-infeasible condition.
    if untested:
        return tuple(plans[:max_tests] if max_tests is not None else plans)

    insufficient_singletons = {key[0] for key in insufficient if len(key) == 1}
    if insufficient_singletons != known_groups:
        return tuple(plans[:max_tests] if max_tests is not None else plans)

    left, right = _balanced_halves(canonical)
    if left and right:
        add(left, DeletionProbeKind.BALANCED_HALF, "all singleton outcomes are proven insufficient")
        add(right, DeletionProbeKind.BALANCED_HALF, "all singleton outcomes are proven insufficient")

    # Once the halves themselves have been tested, search across the split.
    # Cross-half combinations preserve the useful balance and avoid wasting
    # tests on subsets of a proven-insufficient half.
    if tuple(left) in insufficient and tuple(right) in insufficient:
        candidates = itertools.combinations(sorted(set(left) | set(right)), combination_size)
        for combo in candidates:
            if set(combo).intersection(left) and set(combo).intersection(right):
                add(combo, DeletionProbeKind.COMBINATION, "balanced halves already tested")

    return tuple(plans[:max_tests] if max_tests is not None else plans)


def deletion_planner_state(
    groups: Mapping[str, Sequence[str]] | Sequence[Sequence[str]],
    prior_outcomes: Iterable[object] = (),
) -> DeletionPlannerState:
    """Return normalized evidence for reporting and tests.

    This helper shares the planner's strict status parsing, making reports
    and scheduling agree about what counts as proof.
    """

    canonical = _normalise_groups(groups)
    known = set(canonical)
    tested: set[tuple[str, ...]] = set()
    insufficient: set[tuple[str, ...]] = set()
    for outcome in prior_outcomes:
        key = _released_groups(outcome)
        if key is None or any(name not in known for name in key):
            continue
        tested.add(key)
        if _is_proven_infeasible(_status_value(outcome)):
            insufficient.add(key)
    singleton_names = {key[0] for key in tested if len(key) == 1}
    return DeletionPlannerState(
        tuple(sorted(tested)),
        tuple(sorted(insufficient)),
        tuple(sorted(key[0] for key in insufficient if len(key) == 1)),
        tuple(sorted(known - singleton_names)),
    )


# Short aliases make the pure planner discoverable without coupling callers
# to the displacement-specific investigation name.
plan_deletion_tests = plan_displacement_deletion_tests
plan_next_deletion_tests = plan_displacement_deletion_tests


__all__ = [
    "DeletionProbeKind",
    "DeletionProbePlan",
    "DeletionPlannerState",
    "deletion_planner_state",
    "plan_deletion_tests",
    "plan_displacement_deletion_tests",
    "plan_next_deletion_tests",
]
