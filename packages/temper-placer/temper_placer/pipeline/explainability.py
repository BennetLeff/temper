from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from temper_placer.core.decision import Alternative, Decision, DecisionTrace

if TYPE_CHECKING:
    pass

class DecisionLogger:
    """Logs decisions during the placement and routing process."""

    def __init__(self, run_id: str | None = None):
        self.trace = DecisionTrace(
            run_id=run_id or str(uuid.uuid4()),
            start_time=datetime.now()
        )

    def log_placement(
        self,
        component: str,
        value: Any,
        reason: str,
        phase: str = "geometric",
        constraints: list[str] = None,
        alternatives: list[Alternative] = None
    ) -> None:
        """Log a component placement decision."""
        decision = Decision(
            id=f"place-{uuid.uuid4().hex[:8]}",
            phase=phase,
            decision_type="placement",
            subject=component,
            value=value,
            reason=reason,
            constraint_refs=constraints or [],
            alternatives_considered=alternatives or []
        )
        self.trace.add_decision(decision)

    def log_routing(
        self,
        net: str,
        value: Any,
        reason: str,
        phase: str = "routing",
        constraints: list[str] = None
    ) -> None:
        """Log a routing decision."""
        decision = Decision(
            id=f"route-{uuid.uuid4().hex[:8]}",
            phase=phase,
            decision_type="routing",
            subject=net,
            value=value,
            reason=reason,
            constraint_refs=constraints or []
        )
        self.trace.add_decision(decision)

    def finish(self, metrics: dict[str, float]) -> DecisionTrace:
        """Finalize the trace with metrics and end time."""
        self.trace.end_time = datetime.now()
        self.trace.final_metrics = metrics
        return self.trace

def generate_markdown_report(trace: DecisionTrace) -> str:
    """Generate a human-readable Markdown report from a decision trace."""
    lines = [
        f"# Placement Decision Trace: {trace.run_id}",
        f"- **Start Time**: {trace.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **End Time**: {trace.end_time.strftime('%Y-%m-%d %H:%M:%S') if trace.end_time else 'N/A'}",
        "",
        "## Summary Metrics",
    ]

    for k, v in trace.final_metrics.items():
        lines.append(f"- **{k}**: {v:.4f}" if isinstance(v, float) else f"- **{k}**: {v}")

    lines.append("")
    lines.append("## Decisions")

    # Group decisions by subject
    by_subject: dict[str, list[Decision]] = {}
    for d in trace.decisions:
        if d.subject not in by_subject:
            by_subject[d.subject] = []
        by_subject[d.subject].append(d)

    for subject, decisions in by_subject.items():
        lines.append(f"### {subject}")
        for d in decisions:
            lines.append(f"- **Type**: {d.decision_type} ({d.phase})")
            lines.append(f"- **Value**: {d.value}")
            lines.append(f"- **Reason**: {d.reason}")
            if d.constraint_refs:
                lines.append(f"- **Constraints**: {', '.join(d.constraint_refs)}")

            if d.alternatives_considered:
                lines.append("  #### Alternatives Rejected")
                for i, alt in enumerate(d.alternatives_considered, 1):
                    lines.append(f"  {i}. **{alt.value}**: {alt.rejection_reason}")
                    if alt.constraint_violated:
                        lines.append(f"     - Violated: {alt.constraint_violated}")
        lines.append("")

    return "\n".join(lines)
