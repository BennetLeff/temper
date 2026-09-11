"""Explicit v2 buck harness profile; v1 remains the default entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import qualify_buck

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "fixtures" / "buck-v2" / "buck-v2-contract.json"
FIXTURES = ROOT / "fixtures" / "buck-v2"
ADAPTER = ROOT / "buck_native_v2.py"


def configure() -> None:
    """Select only the repository-owned v2 contract and native adapter."""
    qualify_buck.CONTRACT = CONTRACT
    qualify_buck.FIXTURES = FIXTURES
    qualify_buck.ADAPTER = ADAPTER
    qualify_buck.Session.adapter = ADAPTER


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("qualify", "engineering", "trials"))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    configure()

    if args.command == "qualify":
        if len(args.arguments) != 1:
            parser.error("qualify requires exactly one output directory")
        qualify_buck.qualify(
            Path(args.arguments[0]).resolve(),
            rerun="python3 harness-lab/buck_v2.py qualify <fresh-output>",
        )
        return 0

    if args.command == "engineering":
        import engineering_host

        sys.argv = [str(ROOT / "engineering_host.py"), *args.arguments]
        return engineering_host.main()

    import run_buck_trials

    sys.argv = [str(ROOT / "run_buck_trials.py"), *args.arguments]
    return run_buck_trials.main()


if __name__ == "__main__":
    raise SystemExit(main())
