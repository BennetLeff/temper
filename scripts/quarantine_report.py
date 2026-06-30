#!/usr/bin/env python3
"""Report on dead-letter quarantine status and taxonomy distribution.

Reads the quarantine manifest at power_pcb_dataset/quarantine/manifest.json
and produces a human-readable summary suitable for CI gates.

Exit code 0: no regressions (previously-passing boards still pass).
Exit code 1: regressions detected (previously-passing boards now failing).
Exit code 2: new entries (novel failures, informational only).

Usage:
    uv run python scripts/quarantine_report.py [--quarantine-dir PATH] [--baseline PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_quarantine(quarantine_dir: Path) -> dict:
    manifest_path = quarantine_dir / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())
    return {"entries": [], "taxonomy_counts": {}}


def load_baseline(baseline_path: Path) -> dict:
    if baseline_path.exists():
        return json.loads(baseline_path.read_text())
    return {"known_failures": [], "passing_boards": []}


def main() -> None:
    parser = argparse.ArgumentParser(description="Quarantine status reporter")
    parser.add_argument(
        "--quarantine-dir",
        type=Path,
        default=Path("power_pcb_dataset/quarantine"),
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("power_pcb_dataset/quarantine/baseline.json"),
    )
    args = parser.parse_args()

    quarantine = load_quarantine(args.quarantine_dir)
    baseline = load_baseline(args.baseline)
    entries = quarantine.get("entries", [])
    taxonomy = quarantine.get("taxonomy_counts", {})

    print(f"Quarantine entries: {len(entries)}")
    for tax, count in sorted(taxonomy.items(), key=lambda x: -x[1]):
        print(f"  {tax}: {count}")

    known_failures = set(baseline.get("known_failures", []))
    passing_boards = set(baseline.get("passing_boards", []))

    regressions = 0
    for entry in entries:
        board_id = entry.get("board_id", "")
        if board_id in passing_boards:
            print(f"REGRESSION: {board_id} ({entry.get('stage', '?')} / {entry.get('taxonomy', '?')})")
            regressions += 1

    if regressions > 0:
        print(f"\n{regressions} regression(s) found — previously-passing boards now failing.")
        sys.exit(1)

    if len(entries) > len(known_failures):
        new_count = len(entries) - len(known_failures)
        print(f"\n{new_count} new quarantine entries (not regressions).")
        sys.exit(2)

    print("\nQuarantine clean — no regressions, no new entries.")
    sys.exit(0)


if __name__ == "__main__":
    main()
