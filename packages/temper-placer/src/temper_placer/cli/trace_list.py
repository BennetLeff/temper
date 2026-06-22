"""trace_list command for temper-placer CLI."""

from __future__ import annotations

import click
import json
import sys
from pathlib import Path
from ._io import console

@click.command()
@click.option(
    "--trace", type=click.Path(exists=True, path_type=Path), help="Path to decision trace JSON"
)
@click.option("--component", help="Filter by component")
@click.option("--phase", help="Filter by phase")
@click.option("--type", "dtype", help="Filter by decision type")
@click.option("--limit", type=int, help="Limit number of results")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def trace_list(
    trace: Path | None,
    component: str | None,
    phase: str | None,
    dtype: str | None,
    limit: int | None,
    output_json: bool,
) -> None:
    """List all decisions in a trace.

    Example:
        temper-placer trace-list --component Q1
        temper-placer trace-list --phase GEOMETRIC --limit 10
    """
    from temper_placer.explainability import load_trace

    # Find trace file
    if trace is None:
        trace = Path(".temper-placer/decisions.json")
        if not trace.exists():
            console.print(
                "[red]Error:[/] No decision trace found. Run optimization first or specify --trace."
            )
            sys.exit(1)

    # Load trace
    try:
        decision_trace = load_trace(trace)
    except Exception as e:
        console.print(f"[red]Error loading trace:[/] {e}")
        sys.exit(1)

    # Apply filters
    decisions = decision_trace.decisions
    if component:
        decisions = [d for d in decisions if d.subject == component]
    if phase:
        decisions = [d for d in decisions if d.phase and d.phase.value == phase]
    if dtype:
        decisions = [d for d in decisions if d.decision_type.value == dtype]
    if limit:
        decisions = decisions[:limit]

    if output_json:
        output = [
            {
                "subject": d.subject,
                "type": d.decision_type.value,
                "phase": d.phase.value if d.phase else None,
                "value": d.value,
                "reason": d.reason,
                "timestamp": d.timestamp.isoformat(),
            }
            for d in decisions
        ]
        print(json.dumps(output, indent=2))
    else:
        console.print(
            f"[bold]Decisions:[/] (showing {len(decisions)} of {len(decision_trace.decisions)} total)\n"
        )

        for d in decisions:
            phase_str = f"[{d.phase.value}]" if d.phase else ""
            console.print(f"• {d.subject} {phase_str} - {d.decision_type.value} ({d.id})")
            console.print(f"  Value: {d.value}")
            console.print(f"  Reason: {d.reason}")
            console.print()
