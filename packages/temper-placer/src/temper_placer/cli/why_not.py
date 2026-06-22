"""why_not command for temper-placer CLI."""

from __future__ import annotations

import click
import json
import sys
from pathlib import Path
from ._io import console

@click.command()
@click.argument("component")
@click.argument("position")
@click.option(
    "--trace", type=click.Path(exists=True, path_type=Path), help="Path to decision trace JSON"
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def why_not(
    component: str, position: str, trace: Path | None, output_json: bool, verbose: bool
) -> None:
    """Explain why a particular position was rejected.

    Example:
        temper-placer why-not Q1 "(50, 10)"
        temper-placer why-not Q1 50,10
    """
    from temper_placer.explainability import load_trace

    # Parse position string
    try:
        # Handle formats: "(50, 10)", "50,10", "(50.0, 10.0)"
        cleaned = position.strip().replace("(", "").replace(")", "")
        parts = cleaned.split(",")
        pos_tuple = (float(parts[0].strip()), float(parts[1].strip()))
    except (ValueError, IndexError):
        console.print(f"[red]Error:[/] Invalid position format: {position}")
        console.print("Expected format: '(x, y)' or 'x,y'")
        sys.exit(1)

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
    explanation = decision_trace.why_not(component, pos_tuple)

    if output_json:
        # Find the decision with rejected alternatives
        relevant_decision = None
        for d in decision_trace.decisions:
            if d.subject == component:
                for alt in d.alternatives:
                    if (
                        abs(alt.value[0] - pos_tuple[0]) < 0.1
                        and abs(alt.value[1] - pos_tuple[1]) < 0.1
                    ):
                        relevant_decision = d
                        break

        if relevant_decision:
            matching_alts = [
                {
                    "value": alt.value,
                    "rejection_reason": alt.rejection_reason,
                    "constraint_violated": alt.constraint_violated,
                    "loss_if_chosen": alt.loss_if_chosen,
                }
                for alt in relevant_decision.alternatives
                if abs(alt.value[0] - pos_tuple[0]) < 0.1 and abs(alt.value[1] - pos_tuple[1]) < 0.1
            ]
            output = {
                "component": component,
                "position": pos_tuple,
                "rejected": len(matching_alts) > 0,
                "alternatives": matching_alts,
            }
        else:
            output = {
                "component": component,
                "position": pos_tuple,
                "rejected": False,
                "alternatives": [],
            }

        print(json.dumps(output, indent=2))
    else:
        console.print(explanation)
