#!/usr/bin/env python3
"""Generate golden baselines for all boards in the manifest.

Usage:
    python scripts/generate_golden_baselines.py [--board BOARD_ID]
"""

import sys
from pathlib import Path


def _find_repo_root() -> Path:
    p = Path.cwd()
    while not (p / ".git").exists() and p != p.parent:
        p = p.parent
    return p


def main() -> int:
    repo_root = _find_repo_root()
    manifest_path = repo_root / "power_pcb_dataset" / "golden_manifest.yaml"

    if not manifest_path.exists():
        print("No golden_manifest.yaml found. Run 'make manifest' first.")
        return 1

    from temper_placer.regression.manifest import GoldenManifest
    from temper_placer.validation.baseline_extractor import extract_baseline_metrics, BaselineMetrics

    manifest = GoldenManifest.load(manifest_path)
    baselines_dir = repo_root / "power_pcb_dataset" / "baselines"
    baselines_dir.mkdir(parents=True, exist_ok=True)

    for board_entry in manifest.boards:
        pcb_path = board_entry.resolve_path(repo_root)
        if not pcb_path.exists():
            print(f"SKIP: PCB not found: {pcb_path}")
            continue

        try:
            metrics = extract_baseline_metrics(pcb_path, board_entry.id)
            output_path = baselines_dir / f"{board_entry.id}_baseline.yaml"
            metrics.save(output_path)
            print(f"OK: {board_entry.id} -> {output_path}")
            print(f"  Components: {metrics.component_count}, Nets: {metrics.net_count}")
            if metrics.drc_available:
                print(f"  DRC: {metrics.drc_errors} errors, {metrics.drc_warnings} warnings")
        except Exception as e:
            print(f"FAIL: {board_entry.id}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
