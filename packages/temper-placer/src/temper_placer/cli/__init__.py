"""temper-placer CLI dispatcher — discovers subcommands via entry_points."""

from __future__ import annotations

from importlib.metadata import entry_points

import click
from temper_placer import __version__


@click.group()
@click.version_option(version=__version__, prog_name="temper-placer")
def main() -> None:
    """temper-placer: JAX-based PCB placement optimizer."""
    pass


for ep in entry_points(group="temper_placer.cli.subcommands"):
    cmd = ep.load()
    main.add_command(cmd)


if __name__ == "__main__":
    main()
