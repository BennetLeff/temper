"""terative version checker (stub — full implementation in future PR)."""

import click
from ._io import console


@click.command()
def version():
    """Check available versions of temper-placer and dependencies."""
    from temper_placer import __version__

    console.print(f"temper-placer version: {__version__}")
