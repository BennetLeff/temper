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
    from temper_placer.pipeline import PipelineOrchestrator
    from temper_placer.pipeline.andon_observer import AndonObserver

    config_kwargs: dict = {"input_pcb": Path(input_pcb)}
    if loops:
        config_kwargs["loops_yaml"] = Path(loops)
    if constraints:
        config_kwargs["constraints_yaml"] = Path(constraints)
    if dry_run:
        config_kwargs["dry_run"] = True

    orchestrator = PipelineOrchestrator.from_config(**config_kwargs)  # type: ignore[attr-defined]

    pipeline_kwargs: dict = {"input_pcb": Path(input_pcb)}
    if loops:
        pipeline_kwargs["loops"] = Path(loops)
    if constraints:
        pipeline_kwargs["constraints_yaml"] = Path(constraints)
    if dry_run:
        pipeline_kwargs["dry_run"] = True

    if not hasattr(orchestrator, 'dag_engine') or orchestrator.dag_engine is None:
        stage_order = [
            "input", "semantic", "topological", "preflight",
            "geometric", "routing", "refinement", "output",
        ]
        orchestrator.run(**pipeline_kwargs)
        click.echo("Pipeline completed (no DAG engine for live dashboard).")
        return
    else:
        stage_order = orchestrator.dag_engine.stage_order or [
            "input", "semantic", "topological", "preflight",
            "geometric", "routing", "refinement", "output",
        ]

    observer = AndonObserver(stage_order=stage_order, port=port)
    observer.start()
    click.echo(f"Andon Board: http://127.0.0.1:{observer.port}")

    try:
        orchestrator.dag_engine.add_observer(observer)
        orchestrator.run(**pipeline_kwargs)
    finally:
        observer.stop()
