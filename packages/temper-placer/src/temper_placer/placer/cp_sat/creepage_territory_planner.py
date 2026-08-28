"""Thin Python boundary for the Rust weighted creepage quotient."""

from __future__ import annotations

from collections.abc import Sequence

import temper_orchestration


def plan_creepage_territories(
    component_refs: Sequence[str], cuts: Sequence[tuple[str, str, float]]
) -> tuple[list[list[str]], list[tuple[int, int, float]], list[tuple[int, float]]]:
    """Return Rust-owned exact twin classes and their weighted quotient."""

    return temper_orchestration.plan_creepage_territories_py(list(component_refs), list(cuts))


def plan_creepage_displacement_groups(
    component_refs: Sequence[str], cuts: Sequence[tuple[str, str, float]]
) -> list[list[str]]:
    """Return deterministic Rust-owned weighted-twin groups for diagnostics.

    The group index is stable for a fixed component/reference graph and the
    members are sorted.  This is intentionally a grouping-only view of
    :func:`plan_creepage_territories`; callers can use the groups to assign
    shared displacement assumptions without reimplementing the quotient in
    Python.
    """

    return temper_orchestration.plan_creepage_displacement_groups_py(
        list(component_refs), list(cuts)
    )


__all__ = ["plan_creepage_displacement_groups", "plan_creepage_territories"]
