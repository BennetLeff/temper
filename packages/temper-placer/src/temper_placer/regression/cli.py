"""Regression CLI command for temper-placer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _find_repo_root() -> Path:
    p = Path.cwd()
    while not (p / ".git").exists() and p != p.parent:
        p = p.parent
    return p


def run_regression(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else _find_repo_root()
    manifest_path = repo_root / "power_pcb_dataset" / "golden_manifest.yaml"

    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    from temper_placer.regression.manifest import GoldenManifest
    from temper_placer.regression.runner import RegressionRunner

    manifest = GoldenManifest.load(manifest_path)
    errors = manifest.validate(repo_root)
    if errors:
        for err in errors:
            print(f"WARNING: {err}", file=sys.stderr)

    runner = RegressionRunner(manifest, repo_root=repo_root)
    boards = args.boards if args.boards else None
    exit_code = runner.run(boards=boards, with_routing=args.with_routing)

    print(runner.reporter.summary())

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Run golden-board regression suite")
    parser.add_argument(
        "--repo-root", type=str, default=None, help="Repository root (default: auto-detect)"
    )
    parser.add_argument(
        "--boards", type=str, nargs="*", default=None, help="Specific board IDs to test"
    )
    parser.add_argument(
        "--with-routing",
        action="store_true",
        help="Include routing quality in GPBM comparison",
    )
    args = parser.parse_args()
    sys.exit(run_regression(args))


if __name__ == "__main__":
    main()
