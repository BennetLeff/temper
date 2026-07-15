"""version command for temper-placer CLI."""

from __future__ import annotations

import click

from temper_placer._version import __version__

from ._io import console


@click.command()
def version() -> None:
    """Show version information."""
    console.print(f"temper-placer v{__version__}")

    console.print("JAX retired; CP-SAT is the sole placer.")
