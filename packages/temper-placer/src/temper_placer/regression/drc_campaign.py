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
    """Evaluate one run without silently absorbing a category increase."""
    categories = set(baseline_by_type) | set(current_by_type) | set(state.order)
    increases = tuple(
        sorted(
            (name, current_by_type.get(name, 0) - baseline_by_type.get(name, 0))
            for name in categories
            if current_by_type.get(name, 0) > baseline_by_type.get(name, 0)
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
    baseline_active = baseline_by_type.get(active, 0)
    current_active = current_by_type.get(active, 0)
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
                    (name, min(baseline_by_type.get(name, 0), current_by_type.get(name, 0)))
                    for name in categories
                )
            ),
            increases=increases,
        )

    tightened = tuple(
        sorted(
            (name, min(baseline_by_type.get(name, 0), current_by_type.get(name, 0)))
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
