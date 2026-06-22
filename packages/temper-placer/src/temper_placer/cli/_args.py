"""Common Click argument/option constructors for the CLI."""
from __future__ import annotations
from pathlib import Path
import click

def input_pcb_arg(**kwargs):
    defaults = {"type": click.Path(exists=True, path_type=Path)}
    defaults.update(kwargs)
    return click.argument("input_pcb", **defaults)

def output_opt(**kwargs):
    return click.option("--output", "-o", type=click.Path(), help="Output file", **kwargs)

def config_opt(**kwargs):
    defaults = {"type": click.Path(exists=True), "help": "Config YAML"}
    defaults.update(kwargs)
    return click.option("--config", "-c", **defaults)

def constraints_opt(**kwargs):
    defaults = {"type": click.Path(exists=True), "help": "Constraints YAML"}
    defaults.update(kwargs)
    return click.option("--constraints", "-p", **defaults)

def seed_opt(**kwargs):
    defaults = {"type": int, "default": 42, "help": "Random seed"}
    defaults.update(kwargs)
    return click.option("--seed", **defaults)

def epochs_opt(**kwargs):
    defaults = {"type": int, "default": 8000, "help": "Epochs"}
    defaults.update(kwargs)
    return click.option("--epochs", **defaults)

def visualize_opt(**kwargs):
    defaults = {"is_flag": True, "help": "Show visualization"}
    defaults.update(kwargs)
    return click.option("--visualize", **defaults)

def verbose_opt(**kwargs):
    defaults = {"is_flag": True, "help": "Verbose output"}
    defaults.update(kwargs)
    return click.option("--verbose", "-v", **defaults)
