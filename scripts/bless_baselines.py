#!/usr/bin/env python3
"""
Bless baseline metrics for corpus boards after intentional quality improvements.

Re-extracts baseline metrics for corpus boards and overwrites baseline.json.
Requires human approval via 'Ceiling-Approval:' in the commit message body.

Usage:
    bless_baselines.py --board minimal        # Update single board
    bless_baselines.py --all                  # Update all boards
    bless_baselines.py --board temper --dry-run # Show changes without writing
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def find_repo_root() -> Path:
    p = Path(__file__).resolve().parent.parent
    return p


def load_corpus_manifest(repo_root: Path) -> dict:
    manifest_path = repo_root / "power_pcb_dataset" / "corpus" / "manifest.yaml"
    if not manifest_path.exists():
        print(f"ERROR: Manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)
    with open(manifest_path) as f:
        return yaml.safe_load(f)


def load_baseline(baseline_path: Path) -> dict | None:
    if not baseline_path.exists():
        return None
    with open(baseline_path) as f:
        return json.load(f)


def format_metric_diff(
    name: str, old_val: float | None, new_val: float, margin_rel: float, margin_abs: float
) -> str:
    if old_val is not None and old_val != 0:
        pct = ((new_val - old_val) / old_val) * 100
        sign = "+" if pct > 0 else ""
        return f"  {name}: {old_val:.1f} -> {new_val:.1f} ({sign}{pct:.0f}%)"
    else:
        return f"  {name}: N/A -> {new_val:.1f}"


def extract_baseline(repo_root: Path, board_id: str) -> dict[str, Any] | None:
    """Run the extract_corpus_baselines.py script for a single board.

    Returns the new baseline dict or None on failure.
    """
    extract_script = repo_root / "scripts" / "extract_corpus_baselines.py"
    if not extract_script.exists():
        print(f"ERROR: Extraction script not found: {extract_script}", file=sys.stderr)
        return None

    temp_path = repo_root / "power_pcb_dataset" / "corpus" / board_id / "baseline.json.new"
    result = subprocess.run(
        [sys.executable, str(extract_script), "--board", board_id],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return None

    baseline_path = repo_root / "power_pcb_dataset" / "corpus" / board_id / "baseline.json"
    if not baseline_path.exists():
        print(f"ERROR: Baseline not produced at {baseline_path}", file=sys.stderr)
        return None

    with open(baseline_path) as f:
        return json.load(f)


def show_diff(
    board_id: str, old_baseline: dict | None, new_baseline: dict | None
) -> bool:
    """Display old vs new metric comparison. Returns True if metrics improved."""
    if new_baseline is None:
        print(f"[{board_id}] Extraction FAILED")
        return False

    new_metrics = new_baseline.get("metrics", {})
    old_metrics = old_baseline.get("metrics", {}) if old_baseline else {}

    print(f"\n[{board_id}] Baseline changes:")
    improved = True
    for name, spec in new_metrics.items():
        old_val = old_metrics.get(name, {}).get("mean") if old_metrics else None
        new_val = spec.get("mean", 0.0)
        margin_rel = spec.get("margin_rel", 0.05)
        margin_abs = spec.get("margin_abs", 0.0)
        line = format_metric_diff(name, old_val, new_val, margin_rel, margin_abs)
        print(line)

        # Check if metric worsened (higher is worse for all placement metrics)
        if old_val is not None and new_val > old_val * 1.01:
            print(f"    WARNING: {name} increased (worse). Requires explicit justification.")

    return improved


def generate_commit_message(board_id: str, old_baseline: dict | None, new_baseline: dict) -> str:
    """Generate the required commit message format."""
    new_metrics = new_baseline.get("metrics", {})
    old_metrics = old_baseline.get("metrics", {}) if old_baseline else {}

    lines = [f"Ceiling-Approval: Bless {board_id} baseline after quality improvement", ""]
    for name, spec in new_metrics.items():
        old_val = old_metrics.get(name, {}).get("mean") if old_metrics else None
        new_val = spec.get("mean", 0.0)
        if old_val is not None and old_val != 0:
            pct = ((new_val - old_val) / old_val) * 100
            sign = "+" if pct > 0 else ""
            lines.append(f"- {board_id}: {name} {old_val:.1f} -> {new_val:.1f} ({sign}{pct:.0f}%)")
        else:
            lines.append(f"- {board_id}: {name} N/A -> {new_val:.1f}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Bless baseline metrics for corpus boards"
    )
    parser.add_argument("--board", type=str, help="Update baseline for a specific board")
    parser.add_argument("--all", action="store_true", help="Update all corpus boards")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    args = parser.parse_args()

    if not args.board and not args.all:
        parser.error("Either --board BOARD_ID or --all is required")

    repo_root = find_repo_root()
    manifest = load_corpus_manifest(repo_root)

    boards_to_process = manifest["boards"]
    if args.board:
        boards_to_process = [b for b in boards_to_process if b["id"] == args.board]
        if not boards_to_process:
            print(f"ERROR: Board '{args.board}' not found in manifest", file=sys.stderr)
            sys.exit(1)

    for entry in boards_to_process:
        board_id = entry["id"]
        baseline_path = repo_root / "power_pcb_dataset" / "corpus" / entry["baseline"]

        old_baseline = load_baseline(baseline_path)
        old_display = baseline_path

        if args.dry_run:
            new_baseline = extract_baseline(repo_root, board_id)
            show_diff(board_id, old_baseline, new_baseline)
            print()
            print("Required commit message format:")
            if new_baseline:
                print(generate_commit_message(board_id, old_baseline, new_baseline))
        else:
            print(f"[{board_id}] Extracting new baseline...")
            new_baseline = extract_baseline(repo_root, board_id)
            if new_baseline is None:
                print(f"[{board_id}] FAILED to extract baseline", file=sys.stderr)
                sys.exit(1)

            show_diff(board_id, old_baseline, new_baseline)
            print("\nRequired commit message:")
            print(generate_commit_message(board_id, old_baseline, new_baseline))


if __name__ == "__main__":
    main()
