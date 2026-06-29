"""
UNSAT core to PCL upward compiler.

Compiles SAT UNSAT cores back into new or escalated PCL constraints,
closing the placement-routing feedback loop.

Algorithm (R14):
1. Parse UNSAT core constraint names
2. Look up PCL origin via ConstraintOrigin registry
3. For each conflict:
   - If PCL constraint with tier < HARD: escalate it
   - If no PCL origin: synthesize new SeparatedConstraint
   - If empty core: raise InfeasibleConstraintSet
4. Deduplicate: merge identical component pairs at same tier
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import (
    BaseConstraint,
    CompilationContext,
    ConstraintTier,
    SeparatedConstraint,
)
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.pcl.sat_bridge import ConstraintOrigin

if TYPE_CHECKING:
    pass

# Per-run escalation counter (R15).
_escalation_counts: dict[str, int] = {}


def reset_escalation_counts() -> None:
    """Reset the escalation counter (call at start of each pipeline run)."""
    _escalation_counts.clear()


class InfeasibleConstraintSet(Exception):
    """Raised when the constraint set is trivially infeasible (empty UNSAT core)."""

    pass


def compile_unsat_to_pcl(
    unsat_core: list[str],
    pcl_constraints: ConstraintCollection,
    origin: ConstraintOrigin,
    context: CompilationContext,
    max_escalations: int = 3,
) -> ConstraintCollection:
    """Compile a SAT UNSAT core into PCL constraint adjustments.

    Args:
        unsat_core: List of SAT constraint names in the UNSAT core.
        pcl_constraints: The current PCL constraint collection.
        origin: ConstraintOrigin registry from downward compilation.
        context: CompilationContext with netlist, board, etc.
        max_escalations: Max times a constraint can be escalated (R15).

    Returns:
        ConstraintCollection containing new and escalated constraints.

    Raises:
        InfeasibleConstraintSet: If the core is empty (trivially UNSAT).
    """
    if not unsat_core:
        raise InfeasibleConstraintSet(
            "Empty UNSAT core: the constraint set is trivially infeasible. "
            "Check board geometry, channel dimensions, or contradictory PCL constraints."
        )

    # Build PCL constraint lookup by ID.
    pcl_by_id: dict[str, BaseConstraint] = {
        c.id: c for c in pcl_constraints.constraints
    }

    new_constraints: list[BaseConstraint] = []
    escalated_ids: set[str] = set()

    for sat_name in unsat_core:
        pcl_id = origin.lookup_pcl_id(sat_name)

        if pcl_id and pcl_id in pcl_by_id:
            # Known PCL constraint: try escalation.
            pcl_constraint = pcl_by_id[pcl_id]
            if pcl_constraint.tier == ConstraintTier.HARD:
                continue  # Already at max, cannot escalate further (R15).
            if pcl_id in escalated_ids:
                continue  # Already escalated in this pass.

            count = _escalation_counts.get(pcl_id, 0)
            if count >= max_escalations:
                continue  # Exceeded escalation limit.

            pcl_constraint.escalate()
            _escalation_counts[pcl_id] = count + 1
            escalated_ids.add(pcl_id)
            new_constraints.append(pcl_constraint)

        else:
            # Unknown SAT constraint: synthesize new PCL constraint (R16).
            synthesized = _synthesize_constraint(sat_name, context)
            if synthesized is not None:
                new_constraints.append(synthesized)

    # Deduplicate: merge constraints with identical (a, b) component pairs.
    merged = _deduplicate_constraints(new_constraints)

    return ConstraintCollection(constraints=merged, version="unsat_diff")


def _synthesize_constraint(
    sat_name: str, context: CompilationContext,
) -> SeparatedConstraint | None:
    """Synthesize a new SeparatedConstraint from an unknown SAT conflict.

    Derives min_distance_mm from channel bottleneck geometry when available.
    Carries 'because' with conflict description and 'unsat_' prefixed ID (R16).
    """
    # Extract net/channel info from SAT constraint name.
    # Examples: "cap_L1_E42_..." or "chan_sep_sep_HV_ZONE_MCU_ZONE_L1_E42"
    parts = sat_name.split("_")

    # Try to identify a,b components from the name.
    a = "*"
    b = "*"
    for part in parts:
        if "ZONE" in part and a == "*":
            a = part
        elif "ZONE" in part:
            b = part

    # Derive bottleneck distance from channel widths if available.
    min_distance_mm = 6.0  # Default: conservative 6mm separation.
    if context.channel_widths:
        for widths in context.channel_widths.values():
            spacing = getattr(widths, 'spacing_mm', 0.0)
            if spacing > 0:
                min_distance_mm = max(min_distance_mm, spacing * 2)
                break

    desc = f"SAT conflict: {sat_name}"
    description_hash = hashlib.sha256(desc.encode()).hexdigest()[:12]
    constraint_id = f"unsat_{description_hash}"

    return SeparatedConstraint(
        a=a,
        b=b,
        min_distance_mm=min_distance_mm,
        tier=ConstraintTier.STRONG,
        because=f"Synthesized from SAT UNSAT core: {desc}",
        id=constraint_id,
    )


def _deduplicate_constraints(
    constraints: list[BaseConstraint],
) -> list[BaseConstraint]:
    """Merge constraints with identical (a, b) pairs at the same tier.

    For SeparatedConstraints targeting the same component pair,
    takes the maximum min_distance_mm. Other constraint types are
    deduplicated by identity (first wins).
    """
    from temper_placer.pcl.constraints import SeparatedConstraint

    seen: dict[tuple, SeparatedConstraint] = {}
    result: list[BaseConstraint] = []

    for c in constraints:
        if isinstance(c, SeparatedConstraint):
            key = (c.a, c.b, c.tier)
            if key in seen:
                existing = seen[key]
                existing.min_distance_mm = max(
                    existing.min_distance_mm, c.min_distance_mm
                )
            else:
                seen[key] = c
                result.append(c)
        else:
            result.append(c)

    return result
