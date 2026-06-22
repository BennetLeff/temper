"""Common Click argument/option constructors for the CLI."""

from __future__ import annotations

from pathlib import Path

import click


def input_pcb_arg(**kwargs: object) -> callable:
    """@click.argument for the input PCB file."""
    defaults: dict[str, object] = {
        "type": click.Path(exists=True, path_type=Path),
    }
    defaults.update(kwargs)
    return click.argument("input_pcb", **defaults)


def output_opt(**kwargs: object) -> callable:
    """@click.option for the output file (-o)."""
    defaults: dict[str, object] = {
        "--output",
        "-o",
        "type": click.Path(),
        "help": "Output file",
    }
    defaults.update({k: v for k, v in kwargs.items() if k != "--output"})
    return click.option("--output", "-o", **{k: v for k, v in defaults.items() if k not in ("--output",)})


def config_opt(**kwargs: object) -> callable:
    """@click.option for the config YAML file (-c)."""
    defaults: dict[str, object] = {
        "--config",
        "-c",
        "type": click.Path(exists=True),
        "help": "Optimization config YAML file",
    }
    return click.option("--config", "-c", **{k: v for k, v in defaults.items() if k not in ("--config", "-c")})


def constraints_opt(**kwargs: object) -> callable:
    """@click.option for constraints YAML (--constraints / -p)."""
    defaults: dict[str, object] = {
        "--constraints",
        "-p",
        "type": click.Path(exists=True),
        "help": "Constraints YAML file",
    }
    return click.option("--constraints", "-p", **{k: v for k, v in defaults.items() if k not in ("--constraints", "-p")})


def seed_opt(**kwargs: object) -> callable:
    """@click.option for random seed (--seed)."""
    defaults: dict[str, object] = {
        "--seed",
        "type": int,
        "default": 42,
        "help": "Random seed",
    }
    return click.option("--seed", **defaults)


def epochs_opt(**kwargs: object) -> callable:
    """@click.option for training epochs (--epochs)."""
    defaults: dict[str, object] = {
        "--epochs",
        "type": int,
        "default": 8000,
        "help": "Optimization epochs",
    }
    return click.option("--epochs", **defaults)


def visualize_opt(**kwargs: object) -> callable:
    """@click.option for visualisation flag (--visualize)."""
    defaults: dict[str, object] = {
        "--visualize",
        "is_flag": True,
        "help": "Show real-time visualisation",
    }
    return click.option("--visualize", **defaults)


def verbose_opt(**kwargs: object) -> callable:
    """@click.option for verbose flag (-v / --verbose)."""
    defaults: dict[str, object] = {
        "--verbose",
        "-v",
        "is_flag": True,
        "help": "Verbose output",
    }
    return click.option("--verbose", "-v", **{k: v for k, v in defaults.items() if k not in ("--verbose", "-v")})
