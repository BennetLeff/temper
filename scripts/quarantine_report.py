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
    today_failing_ids = {e.get("board_id", "") for e in entries if e.get("board_id")}

    regressions = passing_boards & today_failing_ids
    recovered = known_failures - today_failing_ids

    for bid in sorted(regressions):
        matching = [e for e in entries if e.get("board_id") == bid]
        summary = matching[0] if matching else {}
        print(
            f"REGRESSION: {bid} "
            f"({summary.get('stage', '?')} / {summary.get('taxonomy', '?')})"
        )

    if recovered:
        print(f"\n{len(recovered)} previously-failing board(s) recovered (no longer in quarantine).")

    if regressions:
        print(f"\n{len(regressions)} regression(s) found — previously-passing boards now failing.")
        sys.exit(1)

    new_failures = today_failing_ids - known_failures - passing_boards
    if new_failures:
        print(f"\n{len(new_failures)} new board(s) in quarantine (not regressions, not previously known).")
        sys.exit(2)

    if not entries:
        print("\nQuarantine empty — no entries.")
    else:
        print("\nQuarantine stable — no regressions, no new boards.")
    sys.exit(0)


if __name__ == "__main__":
    main()
