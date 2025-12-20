from typing import Any

import click


# Placeholder for run_profiling - will implement later
def run_profiling(
    target: str | None,
    output_dir: str,
    profile_type: str,
    include_dependencies: bool,
    config_file: str | None,
) -> dict[str, dict[str, Any]]:
    """Placeholder for profiling function."""
    return {"example": {"metric": "value"}}


def validate_target(ctx, param, value):  # type: (click.Context, click.Parameter, str) -> Optional[str]
    """Validate that target is a valid package directory."""
    if value is None:
        return None

    import os

    if not os.path.exists(value):
        raise click.BadParameter(f"Directory does not exist: {value}")

    if not os.path.isdir(value):
        raise click.BadParameter(f"Not a directory: {value}")

    # Check for common package indicators
    common_files = ["pyproject.toml", "setup.py", "__init__.py"]
    has_indicator = any(os.path.exists(os.path.join(value, f)) for f in common_files)
    if not has_indicator:
        raise click.BadParameter(f"Not a valid Python package directory: {value}")

    return value


def validate_output(ctx, param, value):  # type: (click.Context, click.Parameter, str) -> str
    """Validate output directory."""
    import os

    # Create directory if it doesn't exist
    if not os.path.exists(value):
        os.makedirs(value, exist_ok=True)

    if not os.path.isdir(value):
        raise click.BadParameter(f"Not a directory: {value}")

    return value


@click.group()
@click.version_option()
def cli():
    """Automated profiling infrastructure for Temper project."""
    pass


@cli.command()
@click.option(
    "--target",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    callback=validate_target,
    help="Target package directory to profile (default: all discoverable packages)",
)
@click.option(
    "--output",
    type=click.Path(file_okay=False, dir_okay=True),
    default="profiling-results",
    callback=validate_output,
    help="Output directory for profiling results (default: profiling-results)",
)
@click.option(
    "--profile-type",
    type=click.Choice(["memory", "cpu", "all"]),
    default="all",
    help="Type of profiling to run (default: all)",
)
@click.option(
    "--include-dependencies",
    is_flag=True,
    help="Include dependency packages in profiling",
)
@click.option(
    "--config",
    type=click.Path(exists=True, dir_okay=False),
    help="Configuration file for profiling settings",
)
def run(
    target,  # type: Optional[str]
    output,  # type: str
    profile_type,  # type: str
    include_dependencies,  # type: bool
    config,  # type: Optional[str]
):
    """Run automated profiling on target package(s)."""

    click.echo(f"Starting {profile_type} profiling...")
    click.echo(f"Target: {target if target else 'all packages'}")
    click.echo(f"Output: {output}")

    # Run profiling
    results = run_profiling(
        target=target,
        output_dir=output,
        profile_type=profile_type,
        include_dependencies=include_dependencies,
        config_file=config,
    )

    # Output summary
    click.echo("\nProfiling complete!")
    click.echo(f"Results saved to: {output}")

    # Print summary
    for package, metrics in results.items():
        click.echo(f"\n{package}:")
        for metric, value in metrics.items():
            click.echo(f"  {metric}: {value}")


@cli.command()
@click.option(
    "--results-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default="profiling-results",
    help="Directory containing profiling results (default: profiling-results)",
)
@click.option(
    "--format",
    type=click.Choice(["text", "json", "html"]),
    default="text",
    help="Output format for report (default: text)",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False),
    help="Output file for report (optional)",
)
def report(
    results_dir,  # type: str
    format,  # type: str
    output,  # type: Optional[str]
):
    """Generate report from profiling results."""

    click.echo(f"Generating {format} report from {results_dir}...")

    # TODO: Implement report generation
    click.echo("Report generation not yet implemented")

    if output:
        click.echo(f"Report saved to: {output}")


@cli.command()
@click.option(
    "--results-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default="profiling-results",
    help="Directory containing profiling results (default: profiling-results)",
)
def compare(
    results_dir,  # type: str
):
    """Compare profiling results across different runs."""

    click.echo(f"Comparing results from {results_dir}...")

    # TODO: Implement comparison
    click.echo("Comparison not yet implemented")


def main():
    """CLI entry point."""
    cli()


if __name__ == "__main__":
    main()
