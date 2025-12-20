"""Decision and DecisionTrace data structures for auditable placement.

This module provides the core data structures for tracking every decision
the placer makes. Each decision includes:
- What was decided (subject, value, previous value)
- Why (reason, constraint references, loss contribution)
- What alternatives were considered and rejected

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

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


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


@dataclass
class Alternative:
    """A rejected alternative that was considered.

    Attributes:
        value: The alternative value (position, rotation, etc.)
        rejection_reason: Human-readable explanation for why it was rejected
        constraint_violated: PCL constraint ID if applicable
        loss_if_chosen: What the loss would have been if this was chosen
    """

    value: Any
    rejection_reason: str
    constraint_violated: str | None = None
    loss_if_chosen: float | None = None


@dataclass
class Decision:
    """Single auditable decision.

    Every placement, rotation, or routing choice is recorded as a Decision
    with full context about why it was made and what alternatives were rejected.

    Attributes:
        id: Unique decision identifier (auto-generated)
        timestamp: When the decision was made
        phase: Which pipeline phase (semantic, topological, geometric, routing)
        decision_type: What kind of decision (position, rotation, constraint, etc.)
        subject: Component ref, net name, or cluster name
        value: The chosen value
        previous_value: What it was before (for updates)
        reason: Human-readable explanation
        constraint_refs: PCL constraint IDs that influenced this decision
        loss_contribution: How much this improved the total loss
        alternatives: List of rejected alternatives
        epoch: Optimizer epoch if applicable
        iteration: Pipeline iteration
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    phase: DecisionPhase = DecisionPhase.GEOMETRIC
    decision_type: DecisionType = DecisionType.POSITION_UPDATE

    # What was decided
    subject: str = ""
    value: Any = None
    previous_value: Any = None

    # Why
    reason: str = ""
    constraint_refs: list[str] = field(default_factory=list)
    loss_contribution: float = 0.0

    # Alternatives considered
    alternatives: list[Alternative] = field(default_factory=list)

    # Metadata
    epoch: int | None = None
    iteration: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "phase": self.phase.value,
            "decision_type": self.decision_type.value,
            "subject": self.subject,
            "value": self.value,
            "previous_value": self.previous_value,
            "reason": self.reason,
            "constraint_refs": self.constraint_refs,
            "loss_contribution": self.loss_contribution,
            "alternatives": [
                {
                    "value": alt.value,
                    "rejection_reason": alt.rejection_reason,
                    "constraint_violated": alt.constraint_violated,
                    "loss_if_chosen": alt.loss_if_chosen,
                }
                for alt in self.alternatives
            ],
            "epoch": self.epoch,
            "iteration": self.iteration,
        }


@dataclass
class DecisionTrace:
    """Complete audit trail for a pipeline run.

    Collects all decisions made during a placement/routing run and provides
    query methods to understand why the final state is what it is.

    Attributes:
        run_id: Unique identifier for this run
        start_time: When the run started
        end_time: When the run ended (None if still running)
        config_snapshot: Copy of configuration at run start
        decisions: All decisions made during the run
        final_positions: Final component positions
        final_metrics: Final quality metrics

    Example:
        >>> trace = DecisionTrace()
        >>> trace.add(Decision(subject='Q1', value=(10, 20), reason='Initial placement'))
        >>> trace.add(Decision(subject='Q1', value=(15, 25), previous_value=(10, 20),
        ...                    reason='Moved for thermal clearance'))
        >>> print(trace.why('Q1'))
        Q1 is at (15, 25) because: Moved for thermal clearance
    """

    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None

    # Configuration snapshot
    config_snapshot: dict[str, Any] = field(default_factory=dict)

    # All decisions
    decisions: list[Decision] = field(default_factory=list)

    # Final results
    final_positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    final_metrics: dict[str, float] = field(default_factory=dict)

    def add(self, decision: Decision) -> None:
        """Add a decision to the trace.

        Args:
            decision: The decision to record
        """
        self.decisions.append(decision)

    def query_subject(self, subject: str) -> list[Decision]:
        """Get all decisions about a subject (component, net, etc).

        Args:
            subject: The component reference or net name

        Returns:
            List of decisions in chronological order
        """
        return [d for d in self.decisions if d.subject == subject]

    def query_phase(self, phase: DecisionPhase) -> list[Decision]:
        """Get all decisions in a specific phase.

        Args:
            phase: The pipeline phase to filter by

        Returns:
            List of decisions in that phase
        """
        return [d for d in self.decisions if d.phase == phase]

    def query_type(self, dtype: DecisionType) -> list[Decision]:
        """Get all decisions of a specific type.

        Args:
            dtype: The decision type to filter by

        Returns:
            List of decisions of that type
        """
        return [d for d in self.decisions if d.decision_type == dtype]

    def query_constraint(self, constraint_ref: str) -> list[Decision]:
        """Get all decisions influenced by a specific constraint.

        Args:
            constraint_ref: The PCL constraint ID

        Returns:
            List of decisions referencing that constraint
        """
        return [d for d in self.decisions if constraint_ref in d.constraint_refs]

    def why(self, subject: str) -> str:
        """Get human-readable explanation for final state of subject.

        Args:
            subject: Component reference or net name

        Returns:
            Human-readable explanation string
        """
        decisions = self.query_subject(subject)
        if not decisions:
            return f"No decisions recorded for {subject}"

        last = decisions[-1]
        return f"{subject} is at {last.value} because: {last.reason}"

    def why_not(self, subject: str, value: Any) -> str:
        """Explain why a particular value wasn't chosen.

        Searches through all decisions about the subject to find if the
        specified value was ever considered and rejected.

        Args:
            subject: Component reference or net name
            value: The value to explain rejection of

        Returns:
            Explanation of why the value was rejected, or indication
            that it wasn't found in the decision history
        """
        decisions = self.query_subject(subject)
        for d in decisions:
            for alt in d.alternatives:
                if alt.value == value:
                    return f"{value} was rejected: {alt.rejection_reason}"
        return f"No record of {value} being considered for {subject}"

    def history(self, subject: str) -> list[tuple[Any, str]]:
        """Get the complete value history for a subject.

        Args:
            subject: Component reference or net name

        Returns:
            List of (value, reason) tuples in chronological order
        """
        return [(d.value, d.reason) for d in self.query_subject(subject)]

    def finalize(
        self,
        positions: dict[str, tuple[float, float]] | None = None,
        metrics: dict[str, float] | None = None,
    ) -> None:
        """Mark the trace as complete.

        Args:
            positions: Final component positions
            metrics: Final quality metrics
        """
        self.end_time = datetime.now()
        if positions:
            self.final_positions = positions
        if metrics:
            self.final_metrics = metrics

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "config_snapshot": self.config_snapshot,
            "decisions": [d.to_dict() for d in self.decisions],
            "final_positions": self.final_positions,
            "final_metrics": self.final_metrics,
        }

    def summary(self) -> dict[str, Any]:
        """Get a summary of the trace.

        Returns:
            Dictionary with decision counts by phase and type
        """
        by_phase: dict[str, int] = {}
        by_type: dict[str, int] = {}
        subjects: set[str] = set()

        for d in self.decisions:
            by_phase[d.phase.value] = by_phase.get(d.phase.value, 0) + 1
            by_type[d.decision_type.value] = by_type.get(d.decision_type.value, 0) + 1
            subjects.add(d.subject)

        return {
            "run_id": self.run_id,
            "total_decisions": len(self.decisions),
            "unique_subjects": len(subjects),
            "by_phase": by_phase,
            "by_type": by_type,
            "duration_seconds": (
                (self.end_time - self.start_time).total_seconds() if self.end_time else None
            ),
        }

    def __len__(self) -> int:
        """Return the number of decisions in the trace."""
        return len(self.decisions)

    def __iter__(self):
        """Iterate over decisions."""
        return iter(self.decisions)
