"""``temper-placer andon`` — live Andon Board pipeline visualization."""

from __future__ import annotations

from pathlib import Path

import click


@click.command()
@click.argument("input_pcb", type=click.Path(exists=True))
@click.option("--loops", type=click.Path(exists=True), help="Feedback loops YAML")
@click.option("--constraints", type=click.Path(exists=True), help="Constraints YAML")
@click.option("--dry-run", is_flag=True, help="Skip compute-intensive stages")
@click.option("--port", type=int, default=0, help="HTTP server port (0=auto)")
def andon(input_pcb: str, loops: str | None, constraints: str | None,
          dry_run: bool, port: int) -> None:
    """Start a live Andon Board for pipeline execution.

    Opens an HTTP server with SSE push.  Navigate to the printed URL
    to watch pipeline stages in real time.

    INPUT_PCB: Path to the KiCad PCB file.
    """
    raise NotImplementedError(
        "Andon board not yet migrated to DAG engine. "
        "See: temper-placer pipeline (StageDAGEngine)."
    )
