"""
Routability Signal Validation Experiment.

Validates that placement loss gradients contain a routability signal
that correlates with actual routing success/failure outcomes.

This experiment was lost during a hard reset and is being re-created
as a minimal placeholder. See the feat/routability-gradient branch for
the intended implementation.
"""

import argparse


def cli_main(argv: list[str] | None = None) -> None:
    """CLI entry point for routability signal validation."""
    parser = argparse.ArgumentParser(
        description="Validate routability signal in placement gradients"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="routability_signal_results",
        help="Directory for experiment outputs",
    )
    _args = parser.parse_args(argv)

    raise NotImplementedError(
        "routability_signal_validation: experiment not yet re-implemented "
        "(lost during hard reset)"
    )


if __name__ == "__main__":
    cli_main()
