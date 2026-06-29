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


def run_corpus(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else _find_repo_root()
    corpus_root = repo_root / "power_pcb_dataset" / "corpus"

    if not (corpus_root / "manifest.yaml").exists():
        print(f"Corpus manifest not found: {corpus_root / 'manifest.yaml'}", file=sys.stderr)
        return 1

    from temper_placer.regression.corpus_runner import CorpusRegressionRunner

    runner = CorpusRegressionRunner(
        corpus_root=corpus_root,
        repo_root=repo_root,
        skip_unchanged=args.skip_unchanged,
    )
    boards = args.board if args.board else None
    return runner.run(boards=boards, json_output=args.json)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run regression suite")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    # Run subcommand (original golden-board regression)
    run_parser = subparsers.add_parser("run", help="Run golden-board regression suite")
    run_parser.add_argument(
        "--repo-root", type=str, default=None, help="Repository root (default: auto-detect)"
    )
    run_parser.add_argument(
        "--boards", type=str, nargs="*", default=None, help="Specific board IDs to test"
    )
    run_parser.add_argument(
        "--with-routing",
        action="store_true",
        help="Include routing quality in GPBM comparison",
    )

    # Run-corpus subcommand
    corpus_parser = subparsers.add_parser("run-corpus", help="Run corpus optimization regression")
    corpus_parser.add_argument(
        "--repo-root", type=str, default=None, help="Repository root (default: auto-detect)"
    )
    corpus_parser.add_argument(
        "--board", type=str, default=None, help="Run a specific board"
    )
    corpus_parser.add_argument(
        "--json", action="store_true", help="Write JSON report to regression-report.json"
    )
    corpus_parser.add_argument(
        "--skip-unchanged",
        action="store_true",
        help="Skip boards whose inputs and source haven't changed since last green run",
    )

    args = parser.parse_args()

    if args.command == "run-corpus":
        sys.exit(run_corpus(args))
    elif args.command == "run":
        sys.exit(run_regression(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
