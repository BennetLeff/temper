"""trace_export command for temper-placer CLI."""

from __future__ import annotations

import click
import json
import sys
from pathlib import Path
from ._io import console

@click.command()
@click.option(
    "--trace",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to decision trace JSON",
)
@click.option(
    "--format",
    type=click.Choice(["markdown", "html", "json"]),
    default="markdown",
    help="Output format",
)
@click.option(
    "-o", "--output", type=click.Path(path_type=Path), help="Output file (stdout if not specified)"
)
def trace_export(trace: Path, format: str, output: Path | None) -> None:
    """Export decision trace to various formats.

    Example:
        temper-placer trace-export --trace decisions.json --format html -o report.html
        temper-placer trace-export --trace decisions.json --format markdown
    """
    from temper_placer.explainability import (
        generate_html_report,
        load_trace,
        render_markdown_report,
        save_html_report,
        save_markdown_report,
        trace_to_json,
    )

    # Load trace
    try:
        decision_trace = load_trace(trace)
    except Exception as e:
        console.print(f"[red]Error loading trace:[/] {e}")
        sys.exit(1)

    # Generate output based on format
    try:
        if format == "json":
            json_str = trace_to_json(decision_trace)
            if output:
                output.write_text(json_str)
                console.print(f"[green]✓[/] JSON exported to {output}")
            else:
                print(json_str)

        elif format == "markdown":
            if output:
                save_markdown_report(decision_trace, output)
                console.print(f"[green]✓[/] Markdown report exported to {output}")
            else:
                md_content = render_markdown_report(decision_trace)
                print(md_content)

        elif format == "html":
            if not output:
                console.print("[red]Error:[/] HTML format requires --output flag")
                sys.exit(1)
            save_html_report(decision_trace, output)
            console.print(f"[green]✓[/] HTML report exported to {output}")

    except Exception as e:
        console.print(f"[red]Error exporting trace:[/] {e}")
        sys.exit(1)


# =============================================================================
# Pipeline Commands
# =============================================================================

from temper_placer.pipeline import (
    PipelineConfig,
    PipelineOrchestrator,
    PipelinePhase,
    PipelineState,
    RichDashboard,
    TerminalProgress,
    create_progress_display,
)
