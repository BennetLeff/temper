"""``temper-placer watch`` — live terminal pipeline dashboard."""

from __future__ import annotations

import json
import time
from pathlib import Path

import click

from temper_placer.pipeline.dag_observability import StageEvent
from temper_placer.pipeline.terminal_dashboard import create_terminal_dashboard


@click.command()
@click.argument("input_pcb", type=click.Path(exists=True))
@click.option("--loops", type=click.Path(exists=True), help="Feedback loops YAML")
@click.option("--constraints", type=click.Path(exists=True), help="Constraints YAML")
@click.option("--dry-run", is_flag=True, help="Skip compute-intensive stages")
@click.option("--skip-routing", is_flag=True, help="Skip routing and refinement")
@click.option("--replay", "replay_path", type=click.Path(exists=True),
              help="Replay a saved pipeline_execution.json")
@click.option("--refresh", type=float, default=4.0,
              help="Dashboard refresh rate in Hz (default: 4)")
def watch(input_pcb: str, loops: str | None, constraints: str | None,
          dry_run: bool, skip_routing: bool,
          replay_path: str | None, refresh: float) -> None:
    """Watch pipeline execution with a live terminal dashboard.

    INPUT_PCB: Path to the KiCad PCB file.
    """
    if replay_path is not None:
        _watch_replay(Path(replay_path))
        return

    _watch_live(
        input_pcb=Path(input_pcb),
        loops=Path(loops) if loops else None,
        constraints=Path(constraints) if constraints else None,
        dry_run=dry_run,
        skip_routing=skip_routing,
        refresh=refresh,
    )


def _watch_live(*, input_pcb: Path, loops: Path | None, constraints: Path | None,
                dry_run: bool, skip_routing: bool, refresh: float) -> None:
    from temper_placer.pipeline import PipelineOrchestrator

    config_kwargs: dict = {"input_pcb": input_pcb}
    if loops:
        config_kwargs["loops_yaml"] = loops
    if constraints:
        config_kwargs["constraints_yaml"] = constraints
    if dry_run:
        config_kwargs["dry_run"] = True
    if skip_routing:
        config_kwargs["skip_routing"] = True

    orchestrator = PipelineOrchestrator.from_config(**config_kwargs)

    pipeline_kwargs: dict = {"input_pcb": input_pcb}
    if loops:
        pipeline_kwargs["loops"] = loops
    if constraints:
        pipeline_kwargs["constraints_yaml"] = constraints
    if dry_run:
        pipeline_kwargs["dry_run"] = True
    if skip_routing:
        pipeline_kwargs["skip_routing"] = True

    if not hasattr(orchestrator, 'dag_engine') or orchestrator.dag_engine is None:
        orchestrator.run(**pipeline_kwargs)
        click.echo("Pipeline completed (no DAG engine available for live dashboard).")
        return

    stage_order = orchestrator.dag_engine.stage_order
    if not stage_order:
        stage_order = [
            "input", "semantic", "topological", "preflight",
            "geometric", "routing", "refinement", "output",
        ]

    dashboard = create_terminal_dashboard(stage_order=stage_order,
                                           refresh_per_second=refresh)
    orchestrator.dag_engine.add_observer(dashboard)

    with dashboard:
        orchestrator.run(**pipeline_kwargs)
        dashboard.update()


def _watch_replay(replay_path: Path) -> None:
    with open(replay_path) as f:
        data = json.load(f)

    stage_order = data.get("stage_order", [])
    if not stage_order:
        topo = data.get("dag_topology", [])
        stage_order = [s["name"] for s in topo]

    events_raw = data.get("events", [])
    events: list[StageEvent] = []
    for e in events_raw:
        events.append(StageEvent(
            name=e.get("name", ""),
            kind=e.get("kind", ""),
            iteration=e.get("iteration", 0),
            duration_s=e.get("duration_s", 0.0),
            reason=e.get("reason", ""),
            error=e.get("error"),
            feedback_contract=e.get("feedback_contract"),
            feedback_attempt=e.get("feedback_attempt"),
            timestamp=e.get("timestamp", time.time()),
        ))

    if not events:
        click.echo("No events found in replay file.")
        return

    dashboard = create_terminal_dashboard(stage_order=stage_order, refresh_per_second=8.0)

    with dashboard:
        prev_ts = events[0].timestamp
        for event in events:
            delay = max(0.0, event.timestamp - prev_ts)
            if delay > 0:
                time.sleep(min(delay, 0.5))
            prev_ts = event.timestamp

            if event.kind == "start":
                dashboard.on_stage_start(event.name, event.iteration, {})
            elif event.kind == "complete":
                dashboard.on_stage_complete(event.name, event.duration_s,
                                            event.outputs or {})
            elif event.kind == "skip":
                dashboard.on_stage_skip(event.name, event.reason)
            elif event.kind == "error":
                dashboard.on_stage_error(event.name, Exception(event.error or ""))
            elif event.kind == "feedback_triggered":
                dashboard.on_feedback_triggered(
                    event.feedback_contract or "",
                    event.name,
                    "",
                    event.feedback_attempt or 0,
                )

            dashboard.update()

        success = data.get("success", True)
        total = data.get("total_duration_s", 0.0)
        timings = data.get("stage_timings", {})
        dashboard.on_pipeline_complete(success, total, timings)
        dashboard.update()

    click.echo(f"Replay complete. Pipeline {'passed' if success else 'failed'}.")
