"""trace_info command for temper-placer CLI."""

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
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def trace_info(trace: Path | None, output_json: bool) -> None:
    """Show summary of a decision trace.

    Example:
        temper-placer trace-info
        temper-placer trace-info --trace decisions.json
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

    # Get summary
    summary = decision_trace.summary()

    if output_json:
        print(json.dumps(summary, indent=2))
    else:
        console.print("[bold]Decision Trace Summary[/]\n")
        console.print(f"Run ID: {summary.get('run_id', 'N/A')}")
        console.print(f"Total Decisions: {summary.get('total_decisions', 0)}")
        console.print(f"Components: {summary.get('component_count', 0)}")

        if summary.get("unique_subjects"):
            console.print(f"Subject List: {', '.join(sorted(summary['unique_subjects']))}")

        if "decisions_by_type" in summary:
            console.print("\n[bold]Decisions by Type:[/]")
            for dtype, count in summary["decisions_by_type"].items():
                console.print(f"  {dtype}: {count}")

        if "decisions_by_phase" in summary:
            console.print("\n[bold]Decisions by Phase:[/]")
            for phase, count in summary["decisions_by_phase"].items():
                console.print(f"  {phase}: {count}")

        if "final_metrics" in summary:
            console.print("\n[bold]Final Metrics:[/]")
            for key, value in summary["final_metrics"].items():
                console.print(f"  {key}: {value}")
