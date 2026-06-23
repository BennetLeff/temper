"""version command for temper-placer CLI."""

from __future__ import annotations

import click
from temper_placer import __version__
from ._io import console

@click.command()
def version() -> None:
    """Show version information."""
    console.print(f"temper-placer v{__version__}")

    try:
        import jax

        console.print(f"JAX v{jax.__version__}")
        console.print(f"  Backend: {jax.default_backend()}")
        console.print(f"  Devices: {jax.device_count()}")
    except ImportError:
        console.print("JAX: [red]not installed[/]")

    try:
        import optax

        console.print(f"optax v{optax.__version__}")
    except ImportError:
        console.print("optax: [red]not installed[/]")
