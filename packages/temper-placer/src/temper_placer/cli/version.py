"""version command for temper-placer CLI.

Wave-4 Phase-5 R3-style record (see ``packages/temper-orchestration/VERIFICATION.md``):
prints a version string + notice through the rich console; zero compute, and
consumers rely on the click wiring in ``cli/__init__.py``. The click surface
stays Python.
"""

from __future__ import annotations

import click

from temper_placer._version import __version__

from ._io import console


@click.command()
def version() -> None:
    """Show version information."""
    console.print(f"temper-placer v{__version__}")

    console.print("JAX retired; CP-SAT is the sole placer.")
