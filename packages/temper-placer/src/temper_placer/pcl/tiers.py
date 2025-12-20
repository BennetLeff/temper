"""
Constraint tier system with penalty escalation.

Implements dynamic tier adjustment where constraints can escalate from
soft → strong → hard based on violation severity or persistence.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .constraints import BaseConstraint, ConstraintTier


class EscalationReason(Enum):
    """Reason why a constraint was escalated."""

    SEVERITY = "severity"  # Violation too large
    PERSISTENT = "persistent"  # Failed for N iterations
    SAFETY = "safety"  # Safety-critical constraint
    MANUAL = "manual"  # User requested


@dataclass
class ConstraintStatus:
    """
    Runtime status of a constraint.

    Tracks violation history and current tier, allowing dynamic escalation
    based on severity or persistence.
    """

    constraint_id: str
    original_tier: ConstraintTier
    current_tier: ConstraintTier
    violation_history: list[float]
    escalation_reason: Optional[EscalationReason] = None

    @property
    def is_escalated(self) -> bool:
        """Check if constraint has been escalated from original tier."""
        # Lower tier value = more strict (HARD=1, STRONG=2, SOFT=3)
        return self.current_tier.value < self.original_tier.value

    def record_violation(self, amount: float) -> None:
        """
        Record a violation amount in history.

        History is capped at 10 entries (sliding window).

        Args:
            amount: Violation magnitude (0 = satisfied)
        """
        self.violation_history.append(amount)
        if len(self.violation_history) > 10:
            self.violation_history.pop(0)

    def check_escalation(self, config: "EscalationConfig") -> bool:
        """
        Check if constraint should escalate based on config rules.

        Args:
            config: Escalation configuration

        Returns:
            True if constraint should escalate
        """
        if self.current_tier == ConstraintTier.HARD:
            return False  # Already at max

        # Severity check
        if self.violation_history:
            latest = self.violation_history[-1]
            threshold = config.severity_thresholds.get(self.current_tier)
            if threshold is not None and latest > threshold:
                self.escalation_reason = EscalationReason.SEVERITY
                return True

        # Persistence check
        if len(self.violation_history) >= config.persistence_window:
            window = self.violation_history[-config.persistence_window :]
            all_violated = all(v > 0 for v in window)
            if all_violated:
                self.escalation_reason = EscalationReason.PERSISTENT
                return True

        return False

    def escalate(self) -> None:
        """Escalate to next tier (soft → strong → hard)."""
        if self.current_tier == ConstraintTier.SOFT:
            self.current_tier = ConstraintTier.STRONG
        elif self.current_tier == ConstraintTier.STRONG:
            self.current_tier = ConstraintTier.HARD
        # HARD stays HARD


@dataclass
class EscalationConfig:
    """
    Configuration for escalation behavior.

    Controls when and how constraints escalate from soft → strong → hard.
    """

    # Violation thresholds (in mm) that trigger escalation
    severity_thresholds: dict[ConstraintTier, float] = field(
        default_factory=lambda: {
            ConstraintTier.SOFT: 5.0,  # 5mm violation → escalate to strong
            ConstraintTier.STRONG: 2.0,  # 2mm violation → escalate to hard
        }
    )

    # How many consecutive violations trigger escalation
    persistence_window: int = 5

    # Auto-escalate constraints with these keywords in 'because'
    safety_keywords: list[str] = field(
        default_factory=lambda: ["clearance", "creepage", "isolation", "safety"]
    )


def calculate_penalty(
    constraint: BaseConstraint,
    status: ConstraintStatus,
    violation: float,
) -> float:
    """
    Calculate penalty based on tier and violation amount.

    Penalty is quadratic for smooth gradients:
        penalty = weight * (violation^2)

    Escalated constraints get 2x multiplier.

    Args:
        constraint: The constraint being evaluated
        status: Current runtime status with tier info
        violation: Violation magnitude (0 = satisfied)

    Returns:
        Penalty value (0 if satisfied)
    """
    if violation <= 0:
        return 0.0  # Constraint satisfied

    # Base penalty weights by tier
    weights = {
        ConstraintTier.HARD: 1e6,  # Effectively infinite
        ConstraintTier.STRONG: 1e3,
        ConstraintTier.SOFT: 1e1,
    }

    base_weight = weights[status.current_tier]

    # Quadratic penalty for smooth gradients
    penalty = base_weight * (violation**2)

    # Escalation multiplier
    if status.is_escalated:
        penalty *= 2.0  # Extra penalty for escalated constraints

    return penalty


def check_hard_constraints(
    constraints: list[BaseConstraint],
    statuses: dict[str, ConstraintStatus],
    violations: dict[str, float],
) -> tuple[bool, list[str]]:
    """
    Check if all hard constraints are satisfied.

    Args:
        constraints: List of all constraints
        statuses: Runtime status for each constraint
        violations: Current violation amounts by constraint ID

    Returns:
        Tuple of (all_passed, list_of_failed_ids)
    """
    failed = []

    for constraint in constraints:
        status = statuses.get(constraint.id)
        if status and status.current_tier == ConstraintTier.HARD:
            violation = violations.get(constraint.id, 0.0)
            if violation > 1e-6:  # Tolerance for numerical errors
                failed.append(constraint.id)

    return len(failed) == 0, failed


class TieredConstraintManager:
    """
    Manages constraint tiers during optimization.

    Tracks violation history, applies escalation rules, and provides
    current penalty weights for the optimizer.
    """

    def __init__(self, constraints: list[BaseConstraint], config: EscalationConfig) -> None:
        """
        Initialize manager with constraints and config.

        Args:
            constraints: List of all constraints
            config: Escalation configuration
        """
        self.constraints = constraints
        self.config = config
        self.statuses = {
            c.id: ConstraintStatus(
                constraint_id=c.id,
                original_tier=c.tier,
                current_tier=c.tier,
                violation_history=[],
            )
            for c in constraints
        }

    def update(self, violations: dict[str, float]) -> None:
        """
        Update after each optimization step.

        Records violations and checks for escalation.

        Args:
            violations: Current violation amounts by constraint ID
        """
        for cid, amount in violations.items():
            if cid in self.statuses:
                status = self.statuses[cid]
                status.record_violation(amount)

                if status.check_escalation(self.config):
                    status.escalate()
                    print(f"Constraint {cid} escalated to {status.current_tier}")

    def get_penalty_weights(self) -> dict[str, float]:
        """
        Get current penalty weights for all constraints.

        Returns:
            Dict mapping constraint ID to current weight
        """
        weights = {}
        tier_to_weight = {
            ConstraintTier.HARD: 1e6,
            ConstraintTier.STRONG: 1e3,
            ConstraintTier.SOFT: 1e1,
        }

        for constraint in self.constraints:
            status = self.statuses[constraint.id]
            weights[constraint.id] = tier_to_weight[status.current_tier]

        return weights
