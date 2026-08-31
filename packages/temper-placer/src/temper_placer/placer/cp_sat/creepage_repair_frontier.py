"""Prepare a bounded conflict-focused repair from an existing placement."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import temper_orchestration

from temper_placer.placer.cp_sat.netclass_constraints import verify_generated_creepage


@dataclass(frozen=True, slots=True)
class CreepageRepairFrontier:
    violations: tuple[tuple[str, str, float, float], ...]
    movable_refs: frozenset[str]
    fixed_positions: dict[str, tuple[float, float, int]]

    @property
    def replay_cuts(self) -> tuple[tuple[str, str, float], ...]:
        return tuple((left, right, required) for left, right, required, _actual in self.violations)

    @property
    def expanded_movable_refs(self) -> frozenset[str]:
        """Return the next bounded LNS tier: every current violation endpoint."""

        return self.movable_refs | frozenset(
            ref for left, right, _required, _actual in self.violations for ref in (left, right)
        )


def prepare_initial_creepage_repair(
    netlist: Any, design_rules: Any, board: Any | None = None
) -> CreepageRepairFrontier:
    """Verify the current boxes and freeze the complement of a Rust cover."""

    components = list(getattr(netlist, "components", ()))
    boxes: list[tuple[str, float, float, float, float]] = []
    positions: dict[str, tuple[float, float, int]] = {}
    for component in components:
        ref = getattr(component, "ref", None)
        position = getattr(component, "initial_position", None)
        bounds = getattr(component, "bounds", None)
        try:
            x, y = position
            width, height = bounds
            x, y, width, height = map(float, (x, y, width, height))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"component {ref!r} lacks usable initial geometry") from exc
        if (
            not isinstance(ref, str)
            or not ref.strip()
            or not all(math.isfinite(value) for value in (x, y, width, height))
            or width <= 0.0
            or height <= 0.0
            or ref in positions
        ):
            raise ValueError(f"component {ref!r} lacks usable unique initial geometry")
        boxes.append((ref, x - width / 2.0, x + width / 2.0, y - height / 2.0, y + height / 2.0))
        # Bounds are already expressed in the parsed board orientation; zero
        # preserves that width/height ordering in the placement model.
        positions[ref] = (x, y, 0)
    violations = tuple(verify_generated_creepage(netlist, design_rules, boxes))
    movable_set = set(temper_orchestration.plan_creepage_repair_frontier_py(list(violations)))
    if board is not None:
        board_width = float(getattr(board, "width"))
        board_height = float(getattr(board, "height"))
        if not math.isfinite(board_width) or not math.isfinite(board_height):
            raise ValueError("board dimensions must be finite")
        for ref, x_min, x_max, y_min, y_max in boxes:
            if (
                x_min < 0.5
                or y_min < 0.5
                or x_max > board_width - 0.5
                or y_max > board_height - 0.5
            ):
                movable_set.add(ref)
    movable = frozenset(movable_set)
    if any(
        left not in positions or right not in positions
        for left, right, _required, _actual in violations
    ):
        raise ValueError("Rust creepage verifier returned an unknown component")
    if any(
        left not in movable and right not in movable
        for left, right, _required, _actual in violations
    ):
        raise ValueError("Rust creepage repair frontier failed to cover every violation")
    return CreepageRepairFrontier(
        violations=violations,
        movable_refs=movable,
        fixed_positions={ref: value for ref, value in positions.items() if ref not in movable},
    )


__all__ = ["CreepageRepairFrontier", "prepare_initial_creepage_repair"]
