"""Fresh-model deletion tests for safe-placement displacement bounds.

The displacement UNSAT-core experiment is deliberately not used here.  A
deletion test keeps every displacement bound unconditional, preserving the
propagation that makes the all-bounds model useful, and widens only the
selected component group in a fresh model.

This module is an investigation harness.  It does not weaken production
constraints or claim that a solver timeout is evidence for or against a
group.  The exhaustive verifier is called only after a solver has returned a
complete feasible placement; its result is recorded separately from solver
feasibility.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationLimits,
    RestorationStageStatus,
    _expected_refs,
    _run_bounded_radius,
)
from temper_placer.placer.cp_sat.encoder import solve_placement


class DisplacementDeletionCampaignStatus(StrEnum):
    """Terminal status of deletion-test orchestration."""

    COMPLETE = "complete"
    STOPPED = "stopped"
    TIMEOUT = "timeout"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class DisplacementDeletionTestResult:
    """Result of one independent displacement-radius test.

    ``status`` is the production solver status.  A feasible report may still
    have ``verification_passed=False``: this is useful evidence about the
    production model and must not be relabeled as infeasible.
    """

    test_index: int
    name: str
    released_groups: tuple[str, ...]
    released_refs: tuple[str, ...]
    component_radii_mm: Mapping[str, float]
    status: RestorationStageStatus
    elapsed_s: float
    solver_status: str | None = None
    positions: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    rotations: Mapping[str, int] = field(default_factory=dict)
    verification_passed: bool | None = None
    violation_count: int | None = None
    diagnostics: tuple[str, ...] = ()

    @property
    def production_feasible(self) -> bool:
        """Whether this test returned a complete solver candidate."""

        return self.status is RestorationStageStatus.ACCEPTED

    @property
    def exact_creepage_clean(self) -> bool:
        """Whether the optional exact verifier explicitly passed."""

        return self.verification_passed is True


@dataclass(frozen=True, slots=True)
class DisplacementDeletionCampaignResult:
    """Structured result for baseline, singleton, and optional half tests."""

    status: DisplacementDeletionCampaignStatus
    groups: Mapping[str, tuple[str, ...]]
    baseline: DisplacementDeletionTestResult | None = None
    singleton_tests: tuple[DisplacementDeletionTestResult, ...] = ()
    balanced_half_tests: tuple[DisplacementDeletionTestResult, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @property
    def all_tests(self) -> tuple[DisplacementDeletionTestResult, ...]:
        """Return reports in deterministic execution order."""

        return tuple(
            report
            for report in (self.baseline, *self.singleton_tests, *self.balanced_half_tests)
            if report is not None
        )

    @property
    def feasible_tests(self) -> tuple[DisplacementDeletionTestResult, ...]:
        """Return tests with complete production candidates."""

        return tuple(report for report in self.all_tests if report.production_feasible)


def _normalise_groups(
    groups: Mapping[str, Sequence[str]] | Sequence[Sequence[str]],
    expected_refs: Sequence[str],
) -> dict[str, tuple[str, ...]]:
    """Validate and canonically order an authoritative partition."""

    if isinstance(groups, (str, bytes)):
        raise ValueError("groups must be a mapping or sequence of ref groups")
    if isinstance(groups, Mapping):
        raw_groups = groups.items()
    elif isinstance(groups, Sequence):
        raw_groups = ((f"group_{index:03d}", refs) for index, refs in enumerate(groups))
    else:
        raise ValueError("groups must be a mapping or sequence of ref groups")

    expected = set(expected_refs)
    normalised: dict[str, tuple[str, ...]] = {}
    members: list[str] = []
    for name_raw, refs_raw in raw_groups:
        if not isinstance(name_raw, str) or not name_raw.strip():
            raise ValueError("group names must be non-empty strings")
        name = name_raw.strip()
        if name in normalised:
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
        normalised[name] = refs
        members.extend(refs)
    if set(members) != expected or len(members) != len(expected):
        raise ValueError(
            "groups must partition netlist components exactly "
            f"(missing={sorted(expected - set(members))}, "
            f"extra={sorted(set(members) - expected)})"
        )
    return dict(sorted(normalised.items()))


def _validate_centers(verified_warm_start: object, expected_refs: Sequence[str]) -> dict[str, tuple[float, float]]:
    if getattr(verified_warm_start, "usable", False) is not True:
        raise ValueError("deletion testing requires a usable verified stripped warm-start")
    hints = getattr(verified_warm_start, "hints", None)
    if isinstance(hints, (str, bytes)) or not isinstance(hints, Mapping):
        raise ValueError("verified warm-start hints must be a mapping")
    if set(hints) != set(expected_refs):
        raise ValueError("verified warm-start must cover exactly the campaign netlist")
    centers: dict[str, tuple[float, float]] = {}
    for ref in expected_refs:
        hint = hints[ref]
        if not isinstance(hint, (tuple, list)) or len(hint) != 3:
            raise ValueError(f"verified warm-start hint for {ref!r} is not (x, y, rotation)")
        try:
            x, y = float(hint[0]), float(hint[1])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"verified warm-start hint for {ref!r} has invalid coordinates") from exc
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError(f"verified warm-start hint for {ref!r} has non-finite coordinates")
        centers[ref] = (x, y)
    return centers


def _timeout_report(
    test_index: int,
    name: str,
    released_groups: tuple[str, ...],
    released_refs: tuple[str, ...],
    radii: Mapping[str, float],
    diagnostic: str,
) -> DisplacementDeletionTestResult:
    return DisplacementDeletionTestResult(
        test_index,
        name,
        released_groups,
        released_refs,
        dict(radii),
        RestorationStageStatus.TIMEOUT,
        0.0,
        diagnostics=(diagnostic,),
    )


def _balanced_group_halves(
    groups: Mapping[str, tuple[str, ...]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Partition groups into two deterministic, member-count-balanced halves."""

    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    halves: list[list[str]] = [[], []]
    weights = [0, 0]
    for name, members in ordered:
        target = 0 if weights[0] <= weights[1] else 1
        halves[target].append(name)
        weights[target] += len(members)
    return tuple(sorted(halves[0])), tuple(sorted(halves[1]))


def run_displacement_deletion_campaign(
    netlist: object,
    board: object,
    verified_warm_start: object,
    groups: Mapping[str, Sequence[str]] | Sequence[Sequence[str]],
    *,
    base_radius_mm: float = 2.0,
    release_radius_mm: float = 40.0,
    production_kwargs: Mapping[str, object] | None = None,
    solver: Callable[..., object] = solve_placement,
    verify: Callable[[object], object] | None = None,
    limits: RestorationLimits = RestorationLimits(),
    test_balanced_halves: bool = True,
) -> DisplacementDeletionCampaignResult:
    """Run fresh unconditional deletion tests for an authoritative partition.

    First, every component is tested at ``base_radius_mm``.  Only when this
    baseline is *proven infeasible* are singleton group releases attempted.
    Each singleton is an independent fresh model with that group's members at
    ``release_radius_mm`` and every other member at the base radius.  Balanced
    half tests are scheduled only when every singleton is proven infeasible;
    an unknown, timeout, or other status never satisfies that condition.

    A solver-feasible result is retained even when exact verification finds
    creepage violations.  The verifier is never called for an incomplete,
    unknown, infeasible, timed-out, or invalid solver result.
    """

    try:
        expected_refs = _expected_refs(netlist)
        canonical_groups = _normalise_groups(groups, expected_refs)
        centers = _validate_centers(verified_warm_start, expected_refs)
        hints = verified_warm_start.hints
        base = float(base_radius_mm)
        release = float(release_radius_mm)
        if not math.isfinite(base) or base < 0.0:
            raise ValueError("base_radius_mm must be finite and non-negative")
        if not math.isfinite(release) or release <= base:
            raise ValueError("release_radius_mm must be finite and greater than base_radius_mm")
        base_kwargs = dict(production_kwargs or {})
        forbidden = {
            "hint_positions",
            "minimize_displacement_to",
            "max_displacement_mm",
            "hard_displacement_to",
            "hard_displacement_radii_mm",
            "hard_displacement_assumption_labels",
            "hard_displacement_assumptions",
        } & set(base_kwargs)
        if forbidden:
            raise ValueError(f"production_kwargs cannot override deletion options: {sorted(forbidden)}")
    except Exception as exc:
        return DisplacementDeletionCampaignResult(
            DisplacementDeletionCampaignStatus.INVALID,
            {},
            diagnostics=(str(exc),),
        )

    started = time.monotonic()
    expected = tuple(expected_refs)
    base_radii = dict.fromkeys(expected, base)

    def run_test(
        test_index: int,
        name: str,
        released_group_names: Sequence[str],
    ) -> DisplacementDeletionTestResult:
        selected = tuple(sorted(released_group_names))
        released_refs = tuple(sorted(ref for group_name in selected for ref in canonical_groups[group_name]))
        radii = dict(base_radii)
        for ref in released_refs:
            radii[ref] = release
        remaining = limits.total_timeout_s - (time.monotonic() - started)
        if remaining <= 0.0:
            return _timeout_report(
                test_index,
                name,
                selected,
                released_refs,
                radii,
                "campaign deadline exhausted before test",
            )
        kwargs = dict(base_kwargs)
        kwargs.update(
            {
                # Every deletion test starts from the original safe placement;
                # no candidate from a prior test can contaminate this result.
                "hint_positions": dict(hints),
                "hard_displacement_to": dict(centers),
                "hard_displacement_radii_mm": radii,
                # Deletion tests deliberately use unconditional hard bounds.
                # Keep this explicit even though the default may change: a
                # future solver default must not silently reify this probe.
                "hard_displacement_assumptions": False,
                "timeout_ms": max(1, int(min(limits.stage_timeout_s, remaining) * 1000.0)),
            }
        )
        report = _run_bounded_radius(
            release if selected else base,
            solver,
            netlist,
            board,
            kwargs,
            expected,
            verify,
            min(limits.stage_timeout_s, remaining),
            limits.memory_limit_mb,
        )
        return DisplacementDeletionTestResult(
            test_index,
            name,
            selected,
            released_refs,
            radii,
            report.status,
            report.elapsed_s,
            report.solver_status,
            report.positions,
            report.rotations,
            report.verification_passed,
            report.violation_count,
            report.diagnostics,
        )

    baseline = run_test(0, "baseline_all_base", ())
    if baseline.status is not RestorationStageStatus.INFEASIBLE:
        status = DisplacementDeletionCampaignStatus.TIMEOUT if baseline.status is RestorationStageStatus.TIMEOUT else (
            DisplacementDeletionCampaignStatus.INVALID
            if baseline.status in {
                RestorationStageStatus.INVALID,
                RestorationStageStatus.ERROR,
                RestorationStageStatus.MODEL_INVALID,
            }
            else DisplacementDeletionCampaignStatus.STOPPED
        )
        return DisplacementDeletionCampaignResult(
            status,
            canonical_groups,
            baseline=baseline,
            diagnostics=(
                "singleton releases require a proven infeasible all-base-radius baseline",
            ),
        )

    singleton: list[DisplacementDeletionTestResult] = []
    for index, group_name in enumerate(canonical_groups, start=1):
        singleton.append(run_test(index, f"release_{group_name}", (group_name,)))

    halves: list[DisplacementDeletionTestResult] = []
    all_singletons_infeasible = bool(singleton) and all(
        report.status is RestorationStageStatus.INFEASIBLE for report in singleton
    )
    if test_balanced_halves and all_singletons_infeasible and len(canonical_groups) >= 2:
        half_groups = _balanced_group_halves(canonical_groups)
        for offset, selected in enumerate(half_groups):
            halves.append(run_test(len(singleton) + 1 + offset, f"release_half_{offset}", selected))

    reports = (baseline, *singleton, *halves)
    malformed = any(
        report.status
        in {
            RestorationStageStatus.INVALID,
            RestorationStageStatus.ERROR,
            RestorationStageStatus.MODEL_INVALID,
        }
        for report in reports
    )
    timed_out = any(report.status is RestorationStageStatus.TIMEOUT for report in reports)
    deadline_exhausted = any(
        any("campaign deadline exhausted" in diagnostic for diagnostic in report.diagnostics)
        for report in reports
    )
    campaign_status = (
        DisplacementDeletionCampaignStatus.INVALID
        if malformed
        else DisplacementDeletionCampaignStatus.TIMEOUT
        if timed_out
        else DisplacementDeletionCampaignStatus.COMPLETE
    )
    first_bad = next(
        (
            report
            for report in reports
            if report.status
            in {
                RestorationStageStatus.INVALID,
                RestorationStageStatus.ERROR,
                RestorationStageStatus.MODEL_INVALID,
            }
        ),
        None,
    )
    return DisplacementDeletionCampaignResult(
        campaign_status,
        canonical_groups,
        baseline=baseline,
        singleton_tests=tuple(singleton),
        balanced_half_tests=tuple(halves),
        diagnostics=(
            (
                (
                    "one or more deletion tests were malformed or errored: "
                    f"{first_bad.diagnostics[0] if first_bad and first_bad.diagnostics else 'no diagnostic'}"
                )
                if malformed
                else "campaign deadline exhausted"
                if deadline_exhausted
                else "one or more deletion tests timed out"
                if timed_out
                else "all scheduled deletion tests completed"
            ),
        ),
    )


# Short alias for callers that use the investigation name from the solution
# document.  Keep one implementation so the two names cannot drift.
run_deletion_testing_campaign = run_displacement_deletion_campaign


__all__ = [
    "DisplacementDeletionCampaignStatus",
    "DisplacementDeletionTestResult",
    "DisplacementDeletionCampaignResult",
    "run_displacement_deletion_campaign",
    "run_deletion_testing_campaign",
]
