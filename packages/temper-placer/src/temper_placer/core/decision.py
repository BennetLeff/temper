from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import json

@dataclass
class Alternative:
    """A rejected alternative for a decision."""
    value: Any
    rejection_reason: str
    constraint_violated: Optional[str] = None
    loss_if_chosen: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "rejection_reason": self.rejection_reason,
            "constraint_violated": self.constraint_violated,
            "loss_if_chosen": self.loss_if_chosen
        }

@dataclass
class Decision:
    """Single auditable decision in the placement/routing process."""
    id: str
    subject: str # Component ref or net name
    value: Any # Position, rotation, layer, etc.
    timestamp: datetime = field(default_factory=datetime.now)
    phase: str = "geometric" # 'topological', 'geometric', 'routing'
    decision_type: str = "placement" # 'placement', 'rotation', 'layer', etc.
    
    # Why
    reason: str = ""
    constraint_refs: List[str] = field(default_factory=list)
    loss_contribution: float = 0.0
    
    # Alternatives
    alternatives_considered: List[Alternative] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "phase": self.phase,
            "decision_type": self.decision_type,
            "subject": self.subject,
            "value": self.value,
            "reason": self.reason,
            "constraint_refs": self.constraint_refs,
            "loss_contribution": self.loss_contribution,
            "alternatives_considered": [a.to_dict() for a in self.alternatives_considered]
        }

@dataclass
class DecisionTrace:
    """Complete audit trail for a placement/routing run."""
    run_id: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    decisions: List[Decision] = field(default_factory=list)
    final_metrics: Dict[str, float] = field(default_factory=dict)
    
    def add_decision(self, decision: Decision) -> None:
        """Add a decision to the trace."""
        self.decisions.append(decision)
        
    def query(self, subject: str) -> List[Decision]:
        """Get all decisions about a subject."""
        return [d for d in self.decisions if d.subject == subject]
    
    def why_not(self, subject: str, value: Any) -> str:
        """Explain why a particular value wasn't chosen."""
        # Search for subject decisions
        subject_decisions = self.query(subject)
        if not subject_decisions:
            return f"No decisions found for {subject}"
            
        for d in subject_decisions:
            for alt in d.alternatives_considered:
                if alt.value == value:
                    return f"Rejected because: {alt.rejection_reason}"
                    
        return f"Value {value} was not explicitly considered as an alternative for {subject}"

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "decisions": [d.to_dict() for d in self.decisions],
            "final_metrics": self.final_metrics
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
