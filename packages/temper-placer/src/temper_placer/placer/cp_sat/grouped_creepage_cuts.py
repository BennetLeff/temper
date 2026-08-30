"""Thin CP-SAT bridge for Rust-planned grouped creepage cuts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import temper_orchestration

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.model import CpSatModel


@dataclass(frozen=True)
class GroupedCutStats:
    group_count: int
    shared_group_pair_count: int
    grouped_cut_count: int
    independent_cut_count: int
    direction_bool_count: int


def encode_grouped_creepage_cuts(
    model: CpSatModel,
    cuts: Sequence[tuple[str, str, float]],
    *,
    max_group_size: int = 8,
    min_cross_edges: int = 3,
) -> GroupedCutStats:
    """Encode exact pair margins, sharing four direction literals per dense block."""
    canonical = [(str(a), str(b), float(distance)) for a, b, distance in cuts]
    groups, dense_pairs = temper_orchestration.plan_grouped_creepage_cuts_py(
        canonical, max_group_size, min_cross_edges
    )
    group_of = {reference: group_id for group_id, group in enumerate(groups) for reference in group}
    dense = {tuple(pair) for pair in dense_pairs}
    shared = {}
    for group_a, group_b in sorted(dense):
        prefix = f"creepage_group_{group_a}_{group_b}"
        directions = tuple(model.new_bool_var(f"{prefix}_{name}") for name in ("left", "right", "below", "above"))
        model.model_ref.AddBoolOr(list(directions))
        shared[(group_a, group_b)] = directions

    grouped_count = 0
    independent_count = 0
    direction_bools = 4 * len(shared)
    for index, (ref_a, ref_b, required_mm) in enumerate(canonical):
        va = model.component_map[ref_a]
        vb = model.component_map[ref_b]
        group_a, group_b = group_of[ref_a], group_of[ref_b]
        key = (min(group_a, group_b), max(group_a, group_b))
        if key in shared:
            left, right, below, above = shared[key]
            if group_a > group_b:
                left, right, below, above = right, left, above, below
            grouped_count += 1
        else:
            prefix = f"creepage_pair_{index}_{ref_a}_{ref_b}"
            left, right, below, above = (
                model.new_bool_var(f"{prefix}_{name}")
                for name in ("left", "right", "below", "above")
            )
            model.model_ref.AddBoolOr([left, right, below, above])
            independent_count += 1
            direction_bools += 4
        margin = model.mm_to_units(required_mm)
        model.model_ref.Add(va.x_end + margin <= vb.x_start).OnlyEnforceIf(left)
        model.model_ref.Add(vb.x_end + margin <= va.x_start).OnlyEnforceIf(right)
        model.model_ref.Add(va.y_end + margin <= vb.y_start).OnlyEnforceIf(below)
        model.model_ref.Add(vb.y_end + margin <= va.y_start).OnlyEnforceIf(above)
    return GroupedCutStats(len(groups), len(shared), grouped_count, independent_count, direction_bools)
