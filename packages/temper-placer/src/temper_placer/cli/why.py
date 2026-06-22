"""why command for temper-placer CLI."""

from __future__ import annotations

import click
import json
import sys
from pathlib import Path
from ._io import console

@click.command()
@click.argument("component")
@click.option(
    "--trace", type=click.Path(exists=True, path_type=Path), help="Path to decision trace JSON"
)
@click.option("--history", is_flag=True, help="Show complete decision history")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def why(
    component: str, trace: Path | None, history: bool, output_json: bool, verbose: bool
) -> None:
    """Explain why a component is at its current position.

    Example:
        temper-placer why Q1
        temper-placer why Q1 --trace decisions.json --history
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

    # Get explanation
    if history:
        explanation = decision_trace.history(component)
    else:
        explanation = decision_trace.why(component)

    if output_json:
        # Get decisions for component
        decisions = [d for d in decision_trace.decisions if d.subject == component]
        output = {
            "component": component,
            "decision_count": len(decisions),
            "decisions": [
                {
                    "type": d.decision_type.value,
                    "phase": d.phase.value if d.phase else None,
                    "value": d.value,
                    "reason": d.reason,
                    "epoch": d.epoch,
                }
                for d in decisions
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        console.print(explanation)
