"""Decision and DecisionTrace data structures for auditable placement.

This module provides the core data structures for tracking every decision
the placer makes. Each decision includes:
- What was decided (subject, value, previous value)
- Why (reason, constraint references, loss contribution)
- What alternatives were considered and rejected

Phase A, U8 (plan ``2026-08-09-001``): the data contracts —
``Alternative``, ``Decision``, ``DecisionTrace`` — are Rust pyclasses in
``temper-orchestration`` (re-exported here); ``DecisionType`` /
``DecisionPhase`` stay Python ``Enum`` classes (member identity, value
construction ``DecisionPhase(x)`` and class iteration ``list(DecisionPhase)``
are Python runtime semantics — pyo3 has no metaclass hook, so a pyclass
cannot be iterated as a class). The ``uuid``/``datetime`` default factories
are Python runtime semantics, invoked from the pyclass constructors. The
``why``/``why_not``/``history``/``summary`` NL-generation kernels stay
single-source in ``temper-io-types`` and are called back from the pyclass
methods (the Wave-4 differentials pin them).

Example:
    >>> trace = DecisionTrace()
    >>> trace.add(Decision(
    ...     decision_type=DecisionType.INITIAL_POSITION,
    ...     phase=DecisionPhase.GEOMETRIC,
    ...     subject='Q1',
    ...     value=(45.2, 12.3),
    ...     reason='Thermal edge constraint requires IGBT within 5mm of top edge',
    ...     constraint_refs=['thermal.Q1'],
    ...     alternatives=[
    ...         Alternative(
    ...             value=(50, 10),
    ...             rejection_reason='Violates 10mm HV clearance to U_MCU',
    ...             constraint_violated='clearance.hv_lv'
    ...         )
    ...     ]
    ... ))
    >>> trace.why('Q1')
    'Q1 is at (45.2, 12.3) because: Thermal edge constraint requires IGBT within 5mm of top edge'
"""

from __future__ import annotations

from enum import Enum

from temper_orchestration import (
    Alternative,
    Decision,
    DecisionTrace,
)

__all__ = [
    "Alternative",
    "Decision",
    "DecisionPhase",
    "DecisionTrace",
    "DecisionType",
]


class DecisionType(Enum):
    """Types of decisions that can be recorded."""

    # Placement decisions
    INITIAL_POSITION = "initial_position"
    POSITION_UPDATE = "position_update"
    ROTATION = "rotation"
    ZONE_ASSIGNMENT = "zone_assignment"
    CLUSTER_MEMBERSHIP = "cluster_membership"

    # Routing decisions
    NET_ORDER = "net_order"
    LAYER_ASSIGNMENT = "layer_assignment"
    PATH_SELECTION = "path_selection"
    VIA_PLACEMENT = "via_placement"

    # Constraint decisions
    CONSTRAINT_APPLIED = "constraint_applied"
    CONSTRAINT_RELAXED = "constraint_relaxed"
    TIER_ESCALATION = "tier_escalation"


class DecisionPhase(Enum):
    """Phases of the placement/routing pipeline."""

    SEMANTIC = "semantic"
    TOPOLOGICAL = "topological"
    GEOMETRIC = "geometric"
    ROUTING = "routing"
    REFINEMENT = "refinement"
