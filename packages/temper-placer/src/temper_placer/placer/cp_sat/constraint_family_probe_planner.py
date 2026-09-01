"""Pure planning for constraint-family feasibility experiments.

The production restoration experiment has to answer two different questions:
whether a family is compatible with the verified stripped creepage model, and
whether several individually compatible families interact.  This module only
plans the fresh models needed to answer those questions.  It deliberately
does not call CP-SAT or inspect a placement.

The input order is authoritative for cumulative prefixes.  Family sets are
canonicalized for identity, so a set written in a different order (or
reported once by two probe kinds) is still one exact probe.  ``unknown`` and
``timeout`` are recorded as tested but never become positive or negative
evidence; callers must resolve those rows before the planner can advance.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from temper_placer.placer.cp_sat.constraint_restoration_campaign import RestorationStageStatus


class ConstraintFamilyProbeKind(StrEnum):
    """Reason for scheduling a fresh constraint-family model."""

    INDEPENDENT = "independent"
    CUMULATIVE_PREFIX = "cumulative_prefix"
    LEAVE_ONE_OUT = "leave_one_out"
    INTERACTION_BISECTION = "interaction_bisection"

    # ``SINGLETON`` is a useful spelling for clients that describe the
    # independent family probes as singleton tests.
    SINGLETON = "independent"


@dataclass(frozen=True, slots=True)
class ConstraintFamilyProbe:
    """One solver-independent fresh-model probe.

    ``family_set`` is sorted and unique.  The sort is intentional: exact set
    identity, rather than the caller's spelling, controls deduplication.  A
    caller should execute cumulative probes in the order returned by the
    planner and carry a hint only from an accepted preceding prefix.
    """

    family_set: tuple[str, ...]
    kind: ConstraintFamilyProbeKind
    reason: str

    def __post_init__(self) -> None:
        if isinstance(self.family_set, (str, bytes)):
            raise TypeError("family_set must be a sequence of family names")
        families = tuple(self.family_set)
        if any(not isinstance(name, str) or not name.strip() for name in families):
            raise ValueError("family_set must contain non-empty strings")
        canonical = tuple(sorted({name.strip() for name in families}))
        if not canonical:
            raise ValueError("family_set must not be empty")
        if not isinstance(self.kind, ConstraintFamilyProbeKind):
            raise TypeError("kind must be a ConstraintFamilyProbeKind")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be a non-empty string")
        object.__setattr__(self, "family_set", canonical)
        object.__setattr__(self, "reason", self.reason.strip())

    @property
    def families(self) -> tuple[str, ...]:
        """Alias used by callers that call the set simply ``families``."""

        return self.family_set

    @property
    def canonical_key(self) -> tuple[str, ...]:
        """Exact-set identity, independent of probe kind or spelling."""

        return self.family_set

    @property
    def name(self) -> str:
        """Stable human-readable name for logs and cache keys."""

        return f"{self.kind.value}_{'_'.join(self.family_set)}"


@dataclass(frozen=True, slots=True)
class ConstraintFamilyPlannerState:
    """Evidence summary accompanying a planning decision."""

    tested: tuple[tuple[str, ...], ...]
    accepted: tuple[tuple[str, ...], ...]
    infeasible: tuple[tuple[str, ...], ...]
    unresolved: tuple[tuple[str, ...], ...]
    first_failed_prefix: tuple[str, ...] | None = None
    interaction_set: tuple[str, ...] | None = None


_ACCEPTED = frozenset({"accepted", "feasible", "optimal"})
_INFEASIBLE = frozenset({"infeasible"})
_UNRESOLVED = frozenset({"unknown", "timeout", "model_invalid", "invalid", "error"})


def _normalise_families(families: Sequence[str] | Mapping[str, object]) -> tuple[str, ...]:
    if isinstance(families, (str, bytes)):
        raise ValueError("families must be a sequence or mapping of names")
    raw: Iterable[object] = families.keys() if isinstance(families, Mapping) else families
    if not isinstance(raw, Iterable):
        raise ValueError("families must be a sequence or mapping of names")
    names: list[str] = []
    for name in raw:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("family names must be non-empty strings")
        clean = name.strip()
        if clean in names:
            raise ValueError(f"duplicate family name {clean!r}")
        names.append(clean)
    if not names:
        raise ValueError("families must not be empty")
    return tuple(names)


def _status_value(raw: object) -> str | None:
    value: object = raw.get("status") if isinstance(raw, Mapping) else getattr(raw, "status", raw)
    if isinstance(value, RestorationStageStatus):
        return value.value
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, str):
        return value.strip().lower()
    return None


def _family_set(raw: object, known: set[str]) -> tuple[str, ...] | None:
    value: Any
    if isinstance(raw, Mapping):
        value = raw.get("family_set")
        if value is None:
            value = raw.get("families")
        if value is None:
            value = raw.get("constraint_families")
    else:
        value = getattr(raw, "family_set", None)
        if value is None:
            value = getattr(raw, "families", None)
        if value is None:
            value = getattr(raw, "constraint_families", None)
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        return None
    names = tuple(value)
    if any(not isinstance(name, str) or not name.strip() for name in names):
        return None
    result = tuple(sorted({name.strip() for name in names}))
    if not result or any(name not in known for name in result):
        return None
    return result


def _evidence(
    families: Sequence[str], prior_outcomes: Iterable[object],
) -> dict[tuple[str, ...], str]:
    """Collapse duplicate rows conservatively and deterministically."""

    known = set(families)
    by_set: dict[tuple[str, ...], set[str]] = {}
    for outcome in prior_outcomes:
        key = _family_set(outcome, known)
        status = _status_value(outcome)
        if key is None or status not in _ACCEPTED | _INFEASIBLE | _UNRESOLVED:
            continue
        by_set.setdefault(key, set()).add(status)

    collapsed: dict[tuple[str, ...], str] = {}
    for key, statuses in by_set.items():
        # A valid positive result remains positive even if a duplicate cache
        # row is unresolved.  Likewise, proven infeasible is evidence despite
        # a duplicate timeout.  Invalid/unresolved rows alone stay unresolved.
        if statuses & _ACCEPTED:
            collapsed[key] = "accepted"
        elif statuses & _INFEASIBLE:
            collapsed[key] = "infeasible"
        else:
            collapsed[key] = "unresolved"
    return collapsed


def _make_probe(
    family_set: Sequence[str], kind: ConstraintFamilyProbeKind, reason: str,
    seen: set[tuple[str, ...]], output: list[ConstraintFamilyProbe],
) -> None:
    probe = ConstraintFamilyProbe(tuple(family_set), kind, reason)
    if probe.canonical_key not in seen:
        seen.add(probe.canonical_key)
        output.append(probe)


def _split_for_bisection(family_set: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split in declared order, with a deterministic balanced boundary."""

    ordered = tuple(family_set)
    midpoint = len(ordered) // 2
    if midpoint == 0:
        return ordered, ()
    return ordered[:midpoint], ordered[midpoint:]


def plan_constraint_family_probes(
    families: Sequence[str] | Mapping[str, object],
    prior_outcomes: Iterable[object] = (),
    *,
    max_probes: int | None = None,
) -> tuple[ConstraintFamilyProbe, ...]:
    """Return the next deterministic fresh-model family probes.

    The planner follows this evidence ladder:

    * schedule all missing independent singleton probes;
    * after every singleton is accepted, schedule the first missing
      cumulative prefix (in the declared family order);
    * at the first non-accepted prefix, schedule leave-one-out sets for that
      prefix; and
    * if every leave-one-out set is accepted, schedule a balanced interaction
      bisection of the prefix.

    A proven infeasible leave-one-out set becomes the new active set and is
    diagnosed recursively.  An unknown, timeout, invalid, or error result is
    unresolved and stops inference.  Such a result is never silently treated
    as either accepted or infeasible.  Existing rows and newly planned rows
    are deduplicated by exact canonical family set, even when their probe
    kinds differ.
    """

    ordered = _normalise_families(families)
    if max_probes is not None and (
        isinstance(max_probes, bool) or not isinstance(max_probes, int) or max_probes < 0
    ):
        raise ValueError("max_probes must be None or a non-negative integer")
    evidence = _evidence(ordered, prior_outcomes)
    output: list[ConstraintFamilyProbe] = []
    seen = set(evidence)

    def finish() -> tuple[ConstraintFamilyProbe, ...]:
        if max_probes is None:
            return tuple(output)
        return tuple(output[:max_probes])

    # Independent tests are intentionally first and can be run in parallel by
    # the caller.  An unresolved or infeasible singleton blocks interpretation
    # of interactions, but does not cause us to invent any further probes.
    missing_singletons = [
        (name,) for name in ordered if (name,) not in evidence
    ]
    if missing_singletons:
        for key in missing_singletons:
            _make_probe(key, ConstraintFamilyProbeKind.INDEPENDENT,
                        "independent family probe against the stripped creepage base", seen, output)
        return finish()
    if any(evidence[(name,)] != "accepted" for name in ordered):
        return ()

    prefixes = [tuple(ordered[:index]) for index in range(2, len(ordered) + 1)]
    first_failure: tuple[str, ...] | None = None
    for prefix in prefixes:
        status = evidence.get(tuple(sorted(prefix)))
        if status is None:
            _make_probe(prefix, ConstraintFamilyProbeKind.CUMULATIVE_PREFIX,
                        "next cumulative production-family prefix", seen, output)
            return finish()
        if status != "accepted":
            first_failure = prefix
            break
    if first_failure is None:
        # Every family has been restored successfully.  There is no
        # interaction diagnosis to run unless a larger caller supplies one.
        return ()

    active = first_failure
    while len(active) > 1:
        loo = [tuple(name for name in active if name != removed) for removed in active]
        missing = [key for key in loo if tuple(sorted(key)) not in evidence]
        if missing:
            for key in missing:
                _make_probe(key, ConstraintFamilyProbeKind.LEAVE_ONE_OUT,
                            "leave one family out of the first non-accepted prefix", seen, output)
            return finish()
        statuses = [evidence[tuple(sorted(key))] for key in loo]
        if any(status == "unresolved" for status in statuses):
            return ()
        failed = [key for key, status in zip(loo, statuses) if status == "infeasible"]
        if failed:
            # Keep the first failure in declared order.  It is a proven
            # smaller active set, so recursively apply the same diagnosis.
            active = failed[0]
            continue

        # All leave-one-out tests accepted: the prefix failure is an
        # interaction.  Split the active set in declared order.  Existing
        # exact sets are skipped, so bisection remains safe to resume.
        left, right = _split_for_bisection(active)
        halves = tuple(key for key in (left, right) if key)
        missing_halves = [key for key in halves if tuple(sorted(key)) not in evidence]
        if missing_halves:
            for key in missing_halves:
                _make_probe(key, ConstraintFamilyProbeKind.INTERACTION_BISECTION,
                            "balanced bisection of an interacting family set", seen, output)
            return finish()

        half_statuses = [evidence[tuple(sorted(key))] for key in halves]
        if any(status == "unresolved" for status in half_statuses):
            return ()
        failed_halves = [key for key, status in zip(halves, half_statuses) if status == "infeasible"]
        if failed_halves:
            # A failed half is a smaller proven non-accepted set.  Re-enter
            # the leave-one-out loop rather than treating the other half as
            # implicated or weakening either family.
            active = failed_halves[0]
            continue

        # Both halves are accepted, so the contradiction crosses the split.
        # A pure set planner cannot choose a geometric anchor; the accepted
        # half results are nevertheless retained as interaction evidence and
        # there is no duplicate exact set worth scheduling here.
        return finish()

    # A failed pair with both singleton members accepted is already the
    # smallest possible interaction; no duplicate singleton probe is useful.
    return ()


def constraint_family_planner_state(
    families: Sequence[str] | Mapping[str, object],
    prior_outcomes: Iterable[object] = (),
) -> ConstraintFamilyPlannerState:
    """Return normalized evidence for reporting and tests."""

    ordered = _normalise_families(families)
    evidence = _evidence(ordered, prior_outcomes)
    first_failed: tuple[str, ...] | None = None
    for index in range(2, len(ordered) + 1):
        key = tuple(sorted(ordered[:index]))
        if evidence.get(key) not in (None, "accepted"):
            first_failed = ordered[:index]
            break
    return ConstraintFamilyPlannerState(
        tested=tuple(sorted(evidence)),
        accepted=tuple(sorted(key for key, status in evidence.items() if status == "accepted")),
        infeasible=tuple(sorted(key for key, status in evidence.items() if status == "infeasible")),
        unresolved=tuple(sorted(key for key, status in evidence.items() if status == "unresolved")),
        first_failed_prefix=first_failed,
        interaction_set=first_failed if first_failed and len(first_failed) > 1 else None,
    )


# Short aliases make the planner discoverable without coupling callers to the
# exact experiment name used in the CE document.
plan_family_feasibility_probes = plan_constraint_family_probes
plan_constraint_family_feasibility = plan_constraint_family_probes


__all__ = [
    "ConstraintFamilyPlannerState",
    "ConstraintFamilyProbe",
    "ConstraintFamilyProbeKind",
    "constraint_family_planner_state",
    "plan_constraint_family_feasibility",
    "plan_constraint_family_probes",
    "plan_family_feasibility_probes",
]
