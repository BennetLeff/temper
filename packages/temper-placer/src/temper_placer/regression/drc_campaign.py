"""Safety-ordered DRC error campaign evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class CampaignState:
    """Immutable campaign order and current active category."""

    order: tuple[str, ...]
    active_index: int = 0

    def __post_init__(self) -> None:
        if not self.order:
            raise ValueError("campaign order must not be empty")
        if len(set(self.order)) != len(self.order):
            raise ValueError("campaign categories must be unique")
        if not 0 <= self.active_index < len(self.order):
            raise ValueError("active_index must point into campaign order")

    @property
    def active_category(self) -> str:
        return self.order[self.active_index]


@dataclass(frozen=True)
class CampaignResult:
    """Structured campaign verdict and tightened ceiling proposal."""

    passed: bool
    closed: bool
    reason: str
    tightened_ceilings: tuple[tuple[str, int], ...]
    increases: tuple[tuple[str, int], ...]


def evaluate_campaign(
    state: CampaignState,
    baseline_by_type: Mapping[str, int],
    current_by_type: Mapping[str, int],
    *,
    ceiling_approval: bool = False,
) -> CampaignResult:
    """Evaluate one explicit baseline/current snapshot pair.

    A category omitted from a DRC report is not evidence of zero violations.
    Requiring matching, complete snapshots keeps a missing parser field from
    masquerading as campaign progress or an inactive-category improvement.
    """
    _validate_snapshot(state, baseline_by_type, "baseline")
    _validate_snapshot(state, current_by_type, "current")
    if set(baseline_by_type) != set(current_by_type):
        raise ValueError("baseline and current snapshots must contain the same categories")

    categories = set(baseline_by_type)
    increases = tuple(
        sorted(
            (name, current_by_type[name] - baseline_by_type[name])
            for name in categories
            if current_by_type[name] > baseline_by_type[name]
        )
    )
    if increases and not ceiling_approval:
        return CampaignResult(
            passed=False,
            closed=False,
            reason=f"DRC category increase requires Ceiling-Approval: {increases}",
            tightened_ceilings=tuple(sorted(baseline_by_type.items())),
            increases=increases,
        )

    active = state.active_category
    baseline_active = baseline_by_type[active]
    current_active = current_by_type[active]
    if current_active > 0 and current_active >= baseline_active:
        return CampaignResult(
            passed=False,
            closed=False,
            reason=(
                f"active campaign category {active!r} did not decrease "
                f"({baseline_active} -> {current_active})"
            ),
            tightened_ceilings=tuple(
                sorted(
                    (name, min(baseline_by_type[name], current_by_type[name]))
                    for name in categories
                )
            ),
            increases=increases,
        )

    tightened = tuple(
        sorted(
            (name, min(baseline_by_type[name], current_by_type[name]))
            for name in categories
        )
    )
    return CampaignResult(
        passed=True,
        closed=current_active == 0,
        reason=(
            f"campaign {active!r} closed at zero"
            if current_active == 0
            else f"campaign {active!r} progressed {baseline_active} -> {current_active}"
        ),
        tightened_ceilings=tightened,
        increases=increases,
    )


def _validate_snapshot(
    state: CampaignState,
    snapshot: Mapping[str, int],
    label: str,
) -> None:
    missing = set(state.order) - set(snapshot)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(f"{label} snapshot is missing categories: {missing_names}")
    invalid = [
        name
        for name, count in snapshot.items()
        if isinstance(count, bool) or not isinstance(count, int) or count < 0
    ]
    if invalid:
        names = ", ".join(sorted(invalid))
        raise ValueError(f"{label} snapshot has invalid counts: {names}")
