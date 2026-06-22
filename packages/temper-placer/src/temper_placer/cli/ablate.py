"""ablate command for temper-placer CLI."""

from __future__ import annotations

import click
import sys
from pathlib import Path
from ._io import console
from ._io import Panel
from ._io import Progress
from ._io import BarColumn
from ._io import SpinnerColumn
from ._io import TaskProgressColumn
from ._io import TextColumn

@click.group()
def ablate() -> None:
    """Run and analyze ablation studies."""
    pass


@ablate.command()
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--resume/--no-resume",
    default=True,
    help="Resume from checkpoint if available.",
)
@click.option(
    "--retry-failed",
    is_flag=True,
    help="Retry previously failed experiment runs.",
)
@click.option(
    "--parallel",
    type=int,
    help="Override number of parallel workers.",
)
@click.option(
    "--no-report",
    is_flag=True,
    help="Do not generate HTML report after completion.",
)
def run(
    config_file: Path,
    resume: bool,
    retry_failed: bool,
    parallel: int | None,
    no_report: bool,
) -> None:
    """
    Run an ablation study defined in CONFIG_FILE.

    Executes multiple optimization runs with different components enabled/disabled
    to analyze their impact on placement quality.
    """
    console.print(
        Panel.fit(
            "[bold blue]temper-placer ablate run[/]\nExecuting ablation study pipeline",
            border_style="blue",
        )
    )

    try:
        from temper_placer.ablation.analysis import AblationAnalyzer
        from temper_placer.ablation.config import AblationStudyConfig
        from temper_placer.ablation.metrics import MetricAggregator
        from temper_placer.ablation.report import AblationReportGenerator
        from temper_placer.ablation.runner import ExperimentRunner

        # Load config
        console.print(f"[dim]Loading study config from {config_file}...[/]")
        study_cfg = AblationStudyConfig.load(config_file)

        if parallel:
            study_cfg.parallel_workers = parallel

        console.print(f"  [green]✓[/] Study: {study_cfg.study_name}")
        console.print(f"  [green]✓[/] Experiments: {len(study_cfg.experiments)}")
        console.print(f"  [green]✓[/] Seeds: {len(study_cfg.seeds)}")
        console.print(f"  [green]✓[/] Test Cases: {len(study_cfg.test_cases)}")
        console.print(f"  [green]✓[/] Total Runs: {study_cfg.get_total_runs()}")

        # Initialize runner
        runner = ExperimentRunner(study_cfg)

        # Run experiments
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            total_task = progress.add_task("Total Progress", total=study_cfg.get_total_runs())

            def update_progress(completed, total):
                progress.update(total_task, completed=completed)

            results = runner.run_all(
                resume=resume, retry_failed=retry_failed, progress_callback=update_progress
            )

        if not results:
            console.print("[yellow]No results generated.[/]")
            return

        # Analyze and Report
        if not no_report:
            console.print("\n[bold cyan]Generating Analysis and Report...[/]")

            aggregator = MetricAggregator()
            aggregated = aggregator.aggregate(results)

            analyzer = AblationAnalyzer(aggregated)

            report_gen = AblationReportGenerator(study_cfg.output_dir)
            report_path = report_gen.generate(study_cfg.study_name, aggregated, analyzer)

            console.print(f"  [green]✓[/] Report saved to: {report_path}")

    except Exception as e:
        console.print(f"[red]Ablation study failed: {e}[/]")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    console.print("\n[bold green]Ablation study complete![/]")


@ablate.command()
@click.argument("results_dir", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--name",
    type=str,
    default="Ablation Analysis",
    help="Name for the study in the report.",
)
def report(
    results_dir: Path,
    name: str,
) -> None:
    """
    Generate an HTML report from existing ablation results.
    """
    console.print(f"[bold blue]Generating Ablation Report for:[/] {results_dir}")

    try:
        import pickle

        from temper_placer.ablation.analysis import AblationAnalyzer
        from temper_placer.ablation.metrics import MetricAggregator
        from temper_placer.ablation.report import AblationReportGenerator

        checkpoint_path = results_dir / "checkpoint.pkl"
        if not checkpoint_path.exists():
            console.print(f"[red]Results checkpoint not found at {checkpoint_path}[/]")
            sys.exit(1)

        with open(checkpoint_path, "rb") as f:
            checkpoint = pickle.load(f)

        results = checkpoint.results
        console.print(f"  [green]✓[/] Loaded {len(results)} experiment runs")

        aggregator = MetricAggregator()
        aggregated = aggregator.aggregate(results)

        analyzer = AblationAnalyzer(aggregated)

        report_gen = AblationReportGenerator(results_dir)
        report_path = report_gen.generate(name, aggregated, analyzer)

        console.print(f"  [green]✓[/] Report saved to: {report_path}")

    except Exception as e:
        console.print(f"[red]Report generation failed: {e}[/]")
        sys.exit(1)
