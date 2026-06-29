"""Update .regression-cache.json from regression reports.

Reads one or more regression-report-*.json files, computes current
fingerprints for boards that passed, and updates the cache.
Preserves existing cache entries for boards not present in the reports.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _find_repo_root() -> Path:
    p = Path.cwd()
    while not (p / ".git").exists() and p != p.parent:
        p = p.parent
    return p


def _get_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update regression fingerprint cache from JSON reports"
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        required=True,
        help="Directory containing regression-report-*.json files",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detect)",
    )
    args = parser.parse_args()

    repo_root = args.repo_root or _find_repo_root()
    corpus_root = repo_root / "power_pcb_dataset" / "corpus"

    if not (corpus_root / "manifest.yaml").exists():
        print(f"ERROR: Corpus manifest not found: {corpus_root / 'manifest.yaml'}",
              file=sys.stderr)
        sys.exit(1)

    from temper_placer.regression.corpus_runner import CorpusManifest
    from temper_placer.regression.fingerprint import (
        compute_input_fingerprint,
        compute_source_fingerprint,
        load_cache,
        save_cache,
        update_cache_entry,
    )

    manifest = CorpusManifest.load(corpus_root / "manifest.yaml")
    cache = load_cache(corpus_root)
    source_fingerprint = compute_source_fingerprint(repo_root)
    commit_sha = _get_git_sha()

    reports_dir = args.reports_dir.resolve()
    if not reports_dir.is_dir():
        print(f"ERROR: Reports directory not found: {reports_dir}", file=sys.stderr)
        sys.exit(1)

    updated = 0
    preserved = 0
    report_files = sorted(reports_dir.glob("regression-report*.json"))

    for report_path in report_files:
        try:
            with open(report_path) as f:
                report = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: Skipping unreadable report {report_path}: {e}",
                  file=sys.stderr)
            continue

        for board_result in report.get("boards", []):
            board_id = board_result.get("board_id", "")
            if not board_id:
                continue

            entry = manifest.get_board(board_id)
            if entry is None:
                print(f"WARNING: Board {board_id} not in manifest, skipping",
                      file=sys.stderr)
                continue

            if board_result.get("skipped") and board_result.get("skip_reason", "").startswith(
                "Inputs unchanged"
            ):
                preserved += 1
                continue

            if board_result.get("passed") and not board_result.get("skipped"):
                input_fp = compute_input_fingerprint(
                    entry.pcb_path(corpus_root),
                    entry.constraints_path(corpus_root),
                    entry.baseline_path(corpus_root),
                    manifest_seed=entry.seed,
                    manifest_epochs=entry.epochs,
                )
                update_cache_entry(
                    cache, board_id, input_fp, source_fingerprint, commit_sha
                )
                updated += 1

    save_cache(corpus_root, cache)
    print(f"Cache updated: {updated} board(s) updated, {preserved} preserved",
          file=sys.stderr)


if __name__ == "__main__":
    main()
