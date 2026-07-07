"""Netclass-aware separation constraint generation.

Generates ``SeparatedConstraint`` for every cross-class component pair,
driven by the netclass rules SSOT (single source of truth).

Used by the CP-SAT encoder to inject safety-critical isolation
constraints automatically, without repeating clearance values.

SAFETY_FACTOR (√2) converts from Chebyshev to Euclidean space,
ensuring the solver enforces the nominal Euclidean clearance
regardless of component orientation.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from temper_placer.core.netclass_rules import (
    get_pair_because,
    get_pair_clearance,
    resolve_net_class,
)
from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint

if TYPE_CHECKING:
    from temper_placer.core.netlist import Component, Netlist
    from temper_placer.pcl.constraints import BaseConstraint

SAFETY_FACTOR = math.sqrt(2)  # Chebyshev → Euclidean conversion


def generate_netclass_separated_constraints(
    netlist: Netlist,
    components: list[Component],
    rules,  # NetClassRulesDict (avoid import cycle)
    existing_constraints: list[BaseConstraint] | None = None,
) -> list[SeparatedConstraint]:
    """Generate ``SeparatedConstraint`` for every cross-class component pair.

    For each component, the dominant net class is resolved from its
    connected nets (highest self-clearance wins).  Cross-class pairs
    get an isolation constraint with clearance pulled from the netclass
    rules SSOT and multiplied by ``SAFETY_FACTOR``.

    Pairs that already have a user-defined ``SeparatedConstraint`` in
    ``existing_constraints`` are skipped — manual rules take precedence.

    Args:
        netlist: Netlist with components, nets, and pin connectivity.
        components: Component instances (from ``netlist.components``).
        rules: ``NetClassRulesDict`` loaded from ``netclass_rules.yaml``.
        existing_constraints: Existing PCL constraints; pairs in this
            set are NOT duplicated.

    Returns:
        List of ``SeparatedConstraint`` objects, one per cross-class pair.
    """
    existing_pairs: set[tuple[str, str]] = set()
    if existing_constraints:
        for c in existing_constraints:
            if isinstance(c, SeparatedConstraint):
                existing_pairs.add(tuple(sorted([c.a, c.b])))

    comp_net_class: dict[str, str] = {}
    for comp in components:
        net_names = netlist.get_component_nets(comp.ref)
        if not net_names:
            comp_net_class[comp.ref] = comp.net_class or "Signal"
            continue

        resolved = [resolve_net_class(n) for n in net_names]
        best = resolved[0]
        best_clearance = get_pair_clearance(best, best, rules=rules)
        for nc in resolved[1:]:
            nc_clearance = get_pair_clearance(nc, nc, rules=rules)
            if nc_clearance > best_clearance:
                best = nc
                best_clearance = nc_clearance
        comp_net_class[comp.ref] = best

    result: list[SeparatedConstraint] = []
    n = len(components)
    for i in range(n):
        for j in range(i + 1, n):
            comp_a = components[i]
            comp_b = components[j]
            class_a = comp_net_class[comp_a.ref]
            class_b = comp_net_class[comp_b.ref]

            if class_a == class_b:
                continue

            pair_key = tuple(sorted([comp_a.ref, comp_b.ref]))
            if pair_key in existing_pairs:
                continue

            clearance_mm = get_pair_clearance(class_a, class_b, rules=rules)
            clearance_mm *= SAFETY_FACTOR

            because = get_pair_because(class_a, class_b, rules=rules)
            if not because:
                because = (
                    f"Netclass clearance {class_a}↔{class_b}"
                    f" at {clearance_mm:.1f}mm"
                )

            result.append(
                SeparatedConstraint(
                    a=comp_a.ref,
                    b=comp_b.ref,
                    min_distance_mm=clearance_mm,
                    tier=ConstraintTier.HARD,
                    because=because,
                    id=(
                        f"netclass_sep_{class_a}_{class_b}_"
                        f"{comp_a.ref}_{comp_b.ref}"
                    ),
                )
            )

    return result
