"""Thin Python boundary for the Rust weighted creepage quotient."""

from __future__ import annotations

from collections.abc import Sequence

import temper_orchestration


def plan_creepage_territories(
    component_refs: Sequence[str], cuts: Sequence[tuple[str, str, float]]
) -> tuple[list[list[str]], list[tuple[int, int, float]], list[tuple[int, float]]]:
    """Return Rust-owned exact twin classes and their weighted quotient."""

    return temper_orchestration.plan_creepage_territories_py(list(component_refs), list(cuts))


__all__ = ["plan_creepage_territories"]
