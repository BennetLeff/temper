"""Shared argparse helpers for CI gate scripts."""

from __future__ import annotations

import argparse


def add_standard_args(parser: argparse.ArgumentParser, *, with_config: bool = False) -> None:
    """Register common CLI flags on *parser*.

    Adds ``--source-root``, ``--allowlist``, and ``--output``.  When
    *with_config* is true also adds ``--config``.
    """
    parser.add_argument(
        "--source-root",
        type=str,
        default=".",
        help="Root directory of scanned source code",
    )
    parser.add_argument(
        "--allowlist",
        type=str,
        default=None,
        help="Path to the allowlist file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path for output (report, baseline, etc.)",
    )
    if with_config:
        parser.add_argument(
            "--config",
            type=str,
            default=None,
            help="Path to a configuration file",
        )
